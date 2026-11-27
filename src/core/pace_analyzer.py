"""
競馬スクレイピング・分析エンジン - 展開・隊列シミュレーションモジュール (src/core/pace_analyzer.py)
"""

from typing import Dict, List, Any, Optional, Tuple
import re


class NkPaceSimulator:
    """レースの展開パターン（ハイ・スロー・ミドル）と隊列シナリオを自動算出・シミュレーションするクラス"""

    # 各会場の代表的な馬場バイアス（見解自動生成用）
    VENUE_BIAS_MAP = {
        "浦和": "浦和の強烈な「逃げ馬複勝率85.7%」バイアス",
        "川崎": "川崎の「小回り・先行粘り込み」バイアス",
        "園田": "園田の「4角先頭押し切り」バイアス",
        "高知": "高知の「内馬場回避・外差し/先行」バイアス",
        "大井": "大井の「外目スムーズ先行・直線の決め手」バイアス",
        "船橋": "船橋の「スパイラルカーブ・差し脚持続」バイアス",
    }

    def __init__(self, venue_name: str = "", distance_m: int = 1400):
        self.venue_name = venue_name
        self.distance_m = distance_m

    def _determine_tactic(
        self,
        horse: Dict[str, Any],
        horse_master: Optional[Dict[str, Any]] = None
    ) -> Tuple[str, float]:
        """
        馬の過去戦績・評価根拠から主戦脚質（逃げ/先行/差し/追込）とテンのスピードスコアを算出
        """
        passing_list = []
        if horse_master and "past_races" in horse_master:
            for r in horse_master["past_races"][:5]:
                p_str = r.get("passing", "")
                if p_str and isinstance(p_str, str):
                    first_pos = p_str.split("-")[0]
                    if first_pos.isdigit():
                        passing_list.append(int(first_pos))

        reasons = " ".join(horse.get("reasons", []))

        if passing_list:
            avg_first_pos = sum(passing_list) / len(passing_list)
            min_first_pos = min(passing_list)
        else:
            # 理由コメントからの補完推定
            if "逃げ" in reasons or "ハナ" in reasons:
                avg_first_pos, min_first_pos = 1.5, 1
            elif "先行" in reasons:
                avg_first_pos, min_first_pos = 3.0, 2
            elif "差し" in reasons:
                avg_first_pos, min_first_pos = 6.0, 4
            else:
                avg_first_pos, min_first_pos = 8.0, 6

        # 脚質判定とテンの速さスコア
        if min_first_pos == 1 and avg_first_pos <= 2.5:
            tactic = "逃げ"
            speed_score = 10.0 - avg_first_pos
        elif avg_first_pos <= 4.5:
            tactic = "先行"
            speed_score = 8.0 - avg_first_pos
        elif avg_first_pos <= 8.0:
            tactic = "差し"
            speed_score = 5.0 - (avg_first_pos * 0.3)
        else:
            tactic = "追込"
            speed_score = 2.0 - (avg_first_pos * 0.1)

        return tactic, speed_score

    def simulate(
        self,
        predictions: List[Dict[str, Any]],
        race_info: Dict[str, Any],
        horse_master_dict: Optional[Dict[str, Dict[str, Any]]] = None
    ) -> Dict[str, Any]:
        """
        出走全頭の評価結果から3パターンの展開シナリオをシミュレーション
        """
        if not predictions:
            return {}

        horse_master_dict = horse_master_dict or {}
        venue = race_info.get("race_track", self.venue_name) or self.venue_name

        # 各馬の脚質とテンのスピードスコアを集計
        analyzed_horses = []
        for h in predictions:
            h_id = str(h.get("horse_id", ""))
            master = horse_master_dict.get(h_id)
            tactic, speed = self._determine_tactic(h, master)
            analyzed_horses.append({
                "horse_num": int(h.get("horse_num", 0)) if str(h.get("horse_num", "")).isdigit() else h.get("horse_num", 0),
                "horse_name": h.get("horse_name", ""),
                "bracket_num": h.get("bracket_num", ""),
                "jockey": h.get("jockey", ""),
                "score": float(h.get("score", 0.0)),
                "mark": h.get("mark", "−"),
                "tactic": tactic,
                "speed_score": speed
            })

        # テンの速さ順（スピードスコア降順）にソート
        analyzed_horses.sort(key=lambda x: x["speed_score"], reverse=True)

        escape_candidates = [h for h in analyzed_horses if h["tactic"] == "逃げ" or h["speed_score"] >= 7.0]

        # 逃げ馬頭数によるシナリオ発生確率の動的決定
        num_escapes = len(escape_candidates)
        if num_escapes >= 3:
            prob_high, prob_slow, prob_mid = 45, 20, 35
        elif num_escapes == 1:
            prob_high, prob_slow, prob_mid = 20, 45, 35
        else:
            prob_high, prob_slow, prob_mid = 35, 25, 40

        # 想定タイムの補正（1400m基準 1:26.8）
        base_sec = 86.8
        high_sec = base_sec - 0.6
        slow_sec = base_sec + 1.0

        def format_sec(sec: float) -> str:
            m = int(sec // 60)
            s = sec % 60
            return f"{m}:{s:04.1f}"

        # 隊列の自動分け関数
        def build_formation(high_pace: bool = False, slow_pace: bool = False):
            if slow_pace:
                esc = analyzed_horses[:1]
                lead = analyzed_horses[1:5]
                mid = analyzed_horses[5:9]
                rear = analyzed_horses[9:]
            elif high_pace:
                esc = analyzed_horses[:3]
                lead = analyzed_horses[3:7]
                mid = analyzed_horses[7:11]
                rear = analyzed_horses[11:]
            else:
                esc = analyzed_horses[:2]
                lead = analyzed_horses[2:6]
                mid = analyzed_horses[6:10]
                rear = analyzed_horses[10:]

            def fmt(list_h):
                return ", ".join([f"{h['horse_num']}{h['horse_name']}" for h in list_h])

            return {
                "escape": fmt(esc),
                "leading": fmt(lead),
                "middle": fmt(mid),
                "rear": fmt(rear),
                "esc_horses": esc
            }

        form_a = build_formation(high_pace=True)
        form_b = build_formation(slow_pace=True)
        form_c = build_formation(high_pace=False, slow_pace=False)

        # 対応可能馬の抽出
        high_suitable = sorted(analyzed_horses, key=lambda x: (x["tactic"] in ["差し", "追込"], x["score"]), reverse=True)[:4]
        slow_suitable = sorted(analyzed_horses, key=lambda x: (x["tactic"] in ["逃げ", "先行"], x["score"]), reverse=True)[:4]
        mid_suitable = sorted(analyzed_horses, key=lambda x: x["score"], reverse=True)[:5]

        def fmt_suitable(list_h):
            return "、".join([f"{h['horse_num']}番{h['horse_name']}" for h in list_h])

        # 展開見解文の動的組み立て
        venue_bias = self.VENUE_BIAS_MAP.get(venue, f"{venue}のコース特性")
        esc_names_a = "、".join([f"{h['horse_num']}{h['horse_name']}" for h in form_a["esc_horses"][:3]])
        sash_names_a = "、".join([f"{h['horse_num']}{h['horse_name']}" for h in high_suitable[:2]])

        esc_lead_b = form_b["esc_horses"][0] if form_b["esc_horses"] else (analyzed_horses[0] if analyzed_horses else {})
        jockey_str_b = f"{esc_lead_b.get('jockey', '')}騎手の" if esc_lead_b.get("jockey") else ""

        insight_a = (
            f"テンの速度を誇る{esc_names_a}が激しいハナ争いを繰り広げて前半3Fが引き締まったハイペースへ。"
            f"先頭集団が牽制し合うことで、好位待機・中団から差す{sash_names_a}らに絶好の展開が向きます。"
        )
        insight_b = (
            f"{esc_lead_b.get('bracket_num', '')}枠{esc_lead_b.get('horse_num', '')}番から{jockey_str_b}{esc_lead_b.get('horse_name', '')}が抜群のスタートを決めてハナを奪いきり、単騎マイペースを維持。"
            f"{venue_bias}がフルに作用し、前目につけた馬だけで決着する前残り決着となります。"
        )
        insight_c = (
            f"{form_c['esc_horses'][0].get('horse_name', '') if form_c['esc_horses'] else ''}らが適度な引き締まった流れを作り、3コーナーから後続が進出。"
            f"4角のポジショニングと持ちタイム上位の地力がそのまま反映される、能力通りの結果となります。"
        )

        return {
            "scenario_a": {
                "name": "ハイペース（前崩れ・スタミナ戦）",
                "probability": prob_high,
                "target_time": format_sec(high_sec),
                "suitable_horses": fmt_suitable(high_suitable),
                "formation": form_a,
                "insight": insight_a
            },
            "scenario_b": {
                "name": "スローペース（前残り・位置取り戦）",
                "probability": prob_slow,
                "target_time": format_sec(slow_sec),
                "suitable_horses": fmt_suitable(slow_suitable),
                "formation": form_b,
                "insight": insight_b
            },
            "scenario_c": {
                "name": "ミドルペース（標準・実力戦）",
                "probability": prob_mid,
                "target_time": format_sec(base_sec),
                "suitable_horses": fmt_suitable(mid_suitable),
                "formation": form_c,
                "insight": insight_c
            }
        }


def format_pace_simulation_markdown(pace_scenarios: Dict[str, Any]) -> str:
    """
    Pace別展開＆隊列シナリオシミュレーション結果をnote用Markdown形式に整形
    """
    if not pace_scenarios:
        return ""

    lines = [
        "## 📊 Pace别展開 ＆ 隊列シナリオシミュレーション",
        ""
    ]

    key_map = [("scenario_a", "A"), ("scenario_b", "B"), ("scenario_c", "C")]

    for key, code in key_map:
        sc = pace_scenarios.get(key)
        if not sc:
            continue

        fmt = sc["formation"]
        lines.extend([
            f"* **シナリオ{code}：{sc['name']}** [発生確率: {sc['probability']}%]",
            f"  * **シナリオ想定タイム** : **{sc['target_time']}**",
            f"  * **対応可能馬リスト** : {sc['suitable_horses']}",
            "  * **想定隊列** : ",
            f"    `[逃げ]` {fmt['escape']}",
            f"    `[先行]` {fmt['leading']}",
            f"    `[中団]` {fmt['middle']}",
            f"    `[後方]` {fmt['rear']}",
            f"  * **展開見解** : {sc['insight']}",
            ""
        ])

    return "\n".join(lines)
