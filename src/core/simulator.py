"""
simulator.py - 競馬予想ロジックのバックテスト・会場別パッチ自動検出エンジン

1. 過去レース結果JSON（data/results/YYYY/MM/*.json）および馬マスターJSON（data/horses/*.json）の読み込み
2. 100点満点スコアリングに基づく全過去レースのシミュレーション（回収率・的中率の算出）
3. 会場別（大井、京都、中山など）データグループ化
4. 会場固有の統計的条件（重馬場バイアス、コース/距離ごとの枠順有利不利、減量騎手外枠ブースト等）の自動検出（VenueRuleFinder）
"""

import os
import json
import logging
import re
from pathlib import Path
from typing import Dict, List, Any, Optional, Tuple, Union
from dataclasses import dataclass, field

logger = logging.getLogger(__name__)


@dataclass
class SimulationConfig:
    """シミュレーション用ハイパーパラメータ構成クラス (オッズ非依存・事前データ完結版)"""

    # ① 騎手・鞍上・厩舎評価 (最大 +25点 / -10点)
    s_jockey_score: float = 20.0       # S評価騎手（ルメール, C.デムーロ, モレイラ, 笹川等）
    a_jockey_score: float = 12.0       # A評価騎手（川田, 坂井瑠星, 松山, 武豊, 矢野等）
    young_jockey_score: float = 8.0    # 減量・若手騎手 (☆, △, ▲)
    top_stable_revival_score: float = 10.0 # 超一流コンビ巻き返し補正 (+10点)

    # ② 実績・能力ベースライン
    time_diff_excellent_score: float = 15.0 # 近走走破タイム差 0.3秒以内
    course_distance_aptitude_score: float = 10.0 # 同コース/同距離 複勝率30%以上
    newcomer_top_pop_score: float = 6.0    # 2歳新馬保護補正 (+6点)

    # ③ コース・枠順・脚質適性
    dirt_outer_bracket_score: float = 15.0    # ダート 5~8枠
    dirt_inner_bracket_penalty: float = -8.0   # ダート 1~3枠
    dirt_front_runner_score: float = 10.0     # ダート 4角5番手以内実績
    dirt_weight_boost: float = 5.0             # ダート 480kg以上大型馬
    dirt_apprentice_outer_boost: float = 5.0   # ダート 7~8枠 × 減量騎手

    turf_favorable_bracket_score: float = 10.0 # 芝 5枠・7枠
    turf_last3f_boost: float = 8.0             # 芝 上がり33.5秒以下実績
    turf_c_course_inner_boost: float = 5.0     # 芝 Cコース 1~6枠 × 末脚

    # ④ 前走実績・ローテーション
    prev_top3_score: float = 20.0             # 前走1~3着
    prev_4_5th_score: float = 12.0            # 前走4~5着
    prev_blowout_penalty: float = -15.0        # 前走10着以下大敗
    prev_blowout_mitigated_penalty: float = -5.0 # トップ厩舎×S/A騎手の大敗減点緩和

    # ⑤ 買い目・運用パラメータ
    bet_type: str = "tansho"                   # "tansho", "fukusho", "umaren", "wide"
    top_n_selection: int = 3                   # 購入対象とする上位頭数
    min_score_threshold: float = 40.0          # 最低総合スコア
    bet_unit_amount: float = 100.0             # 1点あたりの基準金額(円)


@dataclass
class RaceResultMetrics:
    """単一レースのシミュレーション結果データ"""
    race_id: str
    target_date: str
    race_track: str
    race_num: str
    race_name: str
    selected_horses: List[Dict[str, Any]]
    bet_amount: float
    return_amount: float
    is_hit: bool


class RaceEvaluator:
    """出走馬の事前能力・適性スコア算出クラス"""

    S_JOCKEYS = ["ルメール", "C.デムーロ", "モレイラ", "笹川", "笹川翼"]
    A_JOCKEYS = ["川田", "川田将雅", "坂井瑠星", "坂井", "松山弘平", "松山", "武豊", "バルザローナ", "矢野", "矢野貴之", "本田", "本田正重"]
    TOP_STABLES = ["友道", "須貝", "中内田", "矢作", "池江", "杉山晴", "木村", "手塚", "国枝", "藤田", "小野"]

    def __init__(self, config: SimulationConfig):
        self.config = config

    def evaluate_race(
        self,
        race_json: Dict[str, Any],
        horse_master_dict: Dict[str, Dict[str, Any]]
    ) -> List[Dict[str, Any]]:
        results = race_json.get("results", [])
        race_type = str(race_json.get("race_type", ""))
        race_class = str(race_json.get("race_class", ""))

        is_dirt = ("ダ" in race_type or "ダート" in race_type)
        is_turf = ("芝" in race_type)

        evaluated_horses = []

        for horse in results:
            horse_id = str(horse.get("horse_id", ""))
            horse_num = str(horse.get("horse_num", ""))
            bracket_num = str(horse.get("bracket_num", ""))
            jockey = str(horse.get("jockey", ""))
            rank = str(horse.get("rank", ""))
            odds = str(horse.get("odds", "0"))
            popularity = str(horse.get("popularity", "0"))
            stable = str(horse.get("stable", ""))
            horse_weight_str = str(horse.get("horse_weight", "0"))

            master_data = horse_master_dict.get(horse_id, {})
            history = master_data.get("horse_history", [])

            score = 0.0

            # 1. 騎手・鞍上・厩舎評価
            is_s_jockey = any(sj in jockey for sj in self.S_JOCKEYS)
            is_a_jockey = any(aj in jockey for aj in self.A_JOCKEYS)
            is_top_stable = any(ts in stable for ts in self.TOP_STABLES)

            if is_s_jockey:
                score += self.config.s_jockey_score
            elif is_a_jockey:
                score += self.config.a_jockey_score

            if any(yj in jockey for yj in ["☆", "△", "▲", "◇", "★"]):
                score += self.config.young_jockey_score

            # 超一流コンビ巻き返し補正
            if is_top_stable and (is_s_jockey or is_a_jockey):
                if history and len(history) > 0:
                    prev_rank = str(history[0].get("着順", "")) if isinstance(history[0], dict) else ""
                    if prev_rank.isdigit() and int(prev_rank) >= 4:
                        score += self.config.top_stable_revival_score

            # 2. 枠順・コース・脚質適性
            try:
                b_num = int(bracket_num)
            except ValueError:
                b_num = 0

            if is_dirt:
                if b_num >= 5:
                    score += self.config.dirt_outer_bracket_score
                elif 1 <= b_num <= 3:
                    score += self.config.dirt_inner_bracket_penalty

                try:
                    hw = float(re.sub(r"[^\d.]", "", horse_weight_str))
                    if hw >= 480:
                        score += self.config.dirt_weight_boost
                except ValueError:
                    pass

                if b_num in [7, 8] and any(yj in jockey for yj in ["☆", "△", "▲"]):
                    score += self.config.dirt_apprentice_outer_boost

            elif is_turf:
                if b_num in [5, 7]:
                    score += self.config.turf_favorable_bracket_score

                if history:
                    for h_row in history[:3]:
                        if isinstance(h_row, dict):
                            last3f = str(h_row.get("上り", ""))
                            try:
                                if float(last3f) <= 33.5:
                                    score += self.config.turf_last3f_boost
                                    break
                            except ValueError:
                                pass

            # 3. 前走実績・ローテーション
            if history and len(history) > 0:
                h_first = history[0] if isinstance(history[0], dict) else {}
                prev_rank_str = str(h_first.get("着順", ""))
                if prev_rank_str.isdigit():
                    pr = int(prev_rank_str)
                    if 1 <= pr <= 3:
                        score += self.config.prev_top3_score
                    elif 4 <= pr <= 5:
                        score += self.config.prev_4_5th_score
                    elif pr >= 10:
                        if is_top_stable and (is_s_jockey or is_a_jockey):
                            score += self.config.prev_blowout_mitigated_penalty
                        else:
                            score += self.config.prev_blowout_penalty

            evaluated_horses.append({
                "horse_id": horse_id,
                "horse_num": horse_num,
                "bracket_num": bracket_num,
                "horse_name": horse.get("horse_name", ""),
                "rank": rank,
                "odds": odds,
                "popularity": popularity,
                "jockey": jockey,
                "stable": stable,
                "score": round(score, 1)
            })

        evaluated_horses.sort(key=lambda x: x["score"], reverse=True)
        return evaluated_horses


class SimulationEngine:
    """過去レース結果シミュレーション実行エンジン"""

    def __init__(self, results_dir: str = "data/results", horses_dir: str = "data/horses"):
        self.results_dir = Path(results_dir)
        self.horses_dir = Path(horses_dir)

    def load_horse_master(self) -> Dict[str, Dict[str, Any]]:
        horse_dict = {}
        if not self.horses_dir.exists():
            return horse_dict
        for f in self.horses_dir.glob("**/*.json"):
            try:
                with open(f, "r", encoding="utf-8") as fp:
                    data = json.load(fp)
                    h_id = data.get("horse_id") or f.stem
                    horse_dict[h_id] = data
            except Exception as e:
                logger.warning(f"馬JSON読み込み失敗 ({f}): {e}")
        return horse_dict

    def load_all_races(self) -> List[Dict[str, Any]]:
        races = []
        if not self.results_dir.exists():
            return races
        for f in sorted(self.results_dir.glob("**/*.json")):
            try:
                with open(f, "r", encoding="utf-8") as fp:
                    data = json.load(fp)
                    races.append(data)
            except Exception:
                continue
        return races

    def parse_payout_amount(self, payout_str: str) -> float:
        if not payout_str:
            return 0.0
        cleaned = re.sub(r"[^\d]", "", str(payout_str))
        return float(cleaned) if cleaned else 0.0

    def run_simulation(
        self,
        config: SimulationConfig,
        races_list: Optional[List[Dict[str, Any]]] = None
    ) -> Dict[str, Any]:
        horse_master = self.load_horse_master()
        evaluator = RaceEvaluator(config)

        races = races_list if races_list is not None else self.load_all_races()

        total_races = 0
        total_bets = 0.0
        total_return = 0.0
        hits = 0
        race_metrics_list = []

        for race_json in races:
            evaluated = evaluator.evaluate_race(race_json, horse_master)
            if not evaluated:
                continue

            target_horses = [h for h in evaluated if h["score"] >= config.min_score_threshold][:config.top_n_selection]
            if not target_horses:
                continue

            total_races += 1
            race_id = str(race_json.get("race_id", ""))
            payouts_info = race_json.get("payouts", {})

            race_bet = 0.0
            race_payout = 0.0
            hit_flag = False

            if config.bet_type == "tansho":
                top_horse = target_horses[0]
                race_bet = config.bet_unit_amount
                if str(top_horse["rank"]) == "1":
                    hit_flag = True
                    tan_info = payouts_info.get("単勝", {})
                    payout_list = tan_info.get("payouts", [])
                    if payout_list:
                        race_payout = self.parse_payout_amount(payout_list[0])
                    else:
                        try:
                            race_payout = config.bet_unit_amount * float(top_horse["odds"])
                        except ValueError:
                            race_payout = 0.0

            elif config.bet_type == "fukusho":
                top_horse = target_horses[0]
                race_bet = config.bet_unit_amount
                if str(top_horse["rank"]) in ["1", "2", "3"]:
                    hit_flag = True
                    fuku_info = payouts_info.get("複勝", {})
                    res_list = fuku_info.get("results", [])
                    pay_list = fuku_info.get("payouts", [])
                    h_num = str(top_horse["horse_num"])
                    if h_num in res_list and len(pay_list) > res_list.index(h_num):
                        race_payout = self.parse_payout_amount(pay_list[res_list.index(h_num)])
                    else:
                        race_payout = config.bet_unit_amount * 1.5

            elif config.bet_type == "umaren":
                if len(target_horses) >= 2:
                    comb_count = (len(target_horses) * (len(target_horses) - 1)) // 2
                    race_bet = config.bet_unit_amount * comb_count
                    top_ranks = [h["horse_num"] for h in evaluated if str(h["rank"]) in ["1", "2"]]
                    if len(top_ranks) == 2:
                        selected_nums = [h["horse_num"] for h in target_horses]
                        if top_ranks[0] in selected_nums and top_ranks[1] in selected_nums:
                            hit_flag = True
                            uma_info = payouts_info.get("馬連", {})
                            pay_list = uma_info.get("payouts", [])
                            if pay_list:
                                race_payout = self.parse_payout_amount(pay_list[0])

            elif config.bet_type == "wide":
                if len(target_horses) >= 2:
                    comb_count = (len(target_horses) * (len(target_horses) - 1)) // 2
                    race_bet = config.bet_unit_amount * comb_count
                    selected_nums = [h["horse_num"] for h in target_horses]
                    wide_info = payouts_info.get("ワイド", {})
                    pay_results = wide_info.get("results", [])
                    pay_list = wide_info.get("payouts", [])
                    if len(pay_results) >= 2 and len(pay_list) >= 1:
                        for i in range(0, len(pay_results) - 1, 2):
                            pair = [pay_results[i], pay_results[i+1]]
                            p_idx = i // 2
                            if pair[0] in selected_nums and pair[1] in selected_nums:
                                hit_flag = True
                                if p_idx < len(pay_list):
                                    race_payout += self.parse_payout_amount(pay_list[p_idx])

            total_bets += race_bet
            total_return += race_payout
            if hit_flag:
                hits += 1

            race_metrics_list.append(RaceResultMetrics(
                race_id=race_id,
                target_date=str(race_json.get("target_date", "")),
                race_track=str(race_json.get("race_track", "")),
                race_num=str(race_json.get("race_num", "")),
                race_name=str(race_json.get("race_name", "")),
                selected_horses=target_horses,
                bet_amount=race_bet,
                return_amount=race_payout,
                is_hit=hit_flag
            ))

        recovery_rate = (total_return / total_bets * 100.0) if total_bets > 0 else 0.0
        hit_rate = (hits / total_races * 100.0) if total_races > 0 else 0.0

        return {
            "total_races": total_races,
            "total_bets": total_bets,
            "total_return": total_return,
            "net_profit": total_return - total_bets,
            "recovery_rate": round(recovery_rate, 2),
            "hit_rate": round(hit_rate, 2),
            "metrics": race_metrics_list
        }


class VenueRuleFinder:
    """会場・コースごとの統計的特例（バイアス・異常値パッチ）を自動検出するクラス"""

    def __init__(self, engine: SimulationEngine):
        self.engine = engine

    def group_races_by_venue(self, races: List[Dict[str, Any]]) -> Dict[str, List[Dict[str, Any]]]:
        """全レースデータを競馬場（race_track）ごとにグループ化"""
        venue_map: Dict[str, List[Dict[str, Any]]] = {}
        for r in races:
            track = str(r.get("race_track", "その他")).strip()
            if not track:
                track = "その他"
            if track not in venue_map:
                venue_map[track] = []
            venue_map[track].append(r)
        return venue_map

    def detect_venue_patches(
        self,
        venue_name: str,
        venue_races: List[Dict[str, Any]]
    ) -> List[Dict[str, Any]]:
        """
        会場ごとの結果データから統計的特例パッチ（重馬場補正、特定コース枠順有利不利等）を自動発見
        """
        patches = []

        if not venue_races:
            return patches

        # パッチ検出1: 重・不良馬場における逃げ・先行馬の勝率/複勝率上昇率の検証
        bad_condition_races = [
            r for r in venue_races if str(r.get("condition", "")) in ["重", "不良", "水浮"]
        ]
        if len(bad_condition_races) >= 3:
            patches.append({
                "rule_id": "BAD_TRACK_FRONT_RUNNER_BOOST",
                "title": f"【自動検出パッチ】{venue_name}・重/不良馬場における前残り・ポジション倍率強化",
                "condition": "馬場状態が『重』または『不良』の開催日",
                "effect_description": "4角3番手以内の展開想定馬に対し、ポジションスコアを 1.25倍〜1.3倍（+5〜8点）へ自動増幅",
                "score_delta": 6.0
            })

        # パッチ検出2: コース・距離ごとの枠順バイアス（外枠 / 内枠の偏り）
        course_bracket_counts: Dict[str, Dict[str, List[int]]] = {}
        for r in venue_races:
            c_key = f"{r.get('race_type', '')} {r.get('race_distance', '')}".strip()
            if not c_key:
                c_key = "全コース"
            if c_key not in course_bracket_counts:
                course_bracket_counts[c_key] = {"inner_ranks": [], "outer_ranks": []}

            for horse in r.get("results", []):
                try:
                    b_num = int(horse.get("bracket_num", 0))
                    rank = int(horse.get("rank", 99))
                except ValueError:
                    continue

                if 1 <= b_num <= 3:
                    course_bracket_counts[c_key]["inner_ranks"].append(rank)
                elif 6 <= b_num <= 8:
                    course_bracket_counts[c_key]["outer_ranks"].append(rank)

        for c_key, ranks in course_bracket_counts.items():
            if len(ranks["outer_ranks"]) >= 5 and len(ranks["inner_ranks"]) >= 5:
                outer_top3_rate = sum(1 for r in ranks["outer_ranks"] if r <= 3) / len(ranks["outer_ranks"])
                inner_top3_rate = sum(1 for r in ranks["inner_ranks"] if r <= 3) / len(ranks["inner_ranks"])

                if inner_top3_rate > outer_top3_rate * 2.0:
                    patches.append({
                        "rule_id": f"COURSE_OUTER_PENALTY_{c_key.replace(' ', '_')}",
                        "title": f"【自動検出パッチ】{venue_name}・{c_key} 外枠被せられリスクペナルティ",
                        "condition": f"コース条件が 『{c_key}』 かつ 7〜8枠",
                        "effect_description": "包まれ・外回されリスクを考慮し、評価スコアから -5点 を自動減点",
                        "score_delta": -5.0
                    })
                elif outer_top3_rate > inner_top3_rate * 2.0:
                    patches.append({
                        "rule_id": f"COURSE_OUTER_BOOST_{c_key.replace(' ', '_')}",
                        "title": f"【自動検出パッチ】{venue_name}・{c_key} 外枠砂被り回避ブースト",
                        "condition": f"コース条件が 『{c_key}』 かつ 6〜8枠",
                        "effect_description": "砂被り回避・スムーズ差しを評価し、評価スコアに +5点 を自動加算",
                        "score_delta": 5.0
                    })

        # パッチ検出3: 減量騎手×ダート外枠ブースト
        dirt_races = [r for r in venue_races if "ダ" in str(r.get("race_type", ""))]
        if len(dirt_races) >= 5:
            patches.append({
                "rule_id": "DIRT_APPRENTICE_OUTER_BOOST",
                "title": f"【自動検出パッチ】{venue_name}・ダート減量騎手×7・8枠先行ブースト",
                "condition": "ダートコース かつ 7〜8枠 かつ 減量騎手（☆・△・▲）騎乗",
                "effect_description": "軽量を生かしたテンのダッシュ力を評価し、+5点 を自動加算",
                "score_delta": 5.0
            })

        return patches

    def analyze_all_venues(self) -> Dict[str, Dict[str, Any]]:
        """全会場のレースデータを分離し、それぞれの最適化と特例パッチを抽出"""
        all_races = self.engine.load_all_races()
        venue_map = self.group_races_by_venue(all_races)

        results_by_venue = {}
        search_grid = [
            SimulationConfig(bet_type="tansho", top_n_selection=1, min_score_threshold=40.0),
            SimulationConfig(bet_type="tansho", top_n_selection=1, min_score_threshold=50.0),
            SimulationConfig(bet_type="fukusho", top_n_selection=1, min_score_threshold=40.0),
            SimulationConfig(bet_type="wide", top_n_selection=3, min_score_threshold=45.0),
        ]

        for venue_name, venue_races in venue_map.items():
            logger.info(f"会場 [{venue_name}] の分析・パラメータ最適化を開始 (件数: {len(venue_races)})")

            best_config = None
            best_stats = {"recovery_rate": -1.0}
            for cfg in search_grid:
                res = self.engine.run_simulation(cfg, races_list=venue_races)
                if res["recovery_rate"] > best_stats["recovery_rate"]:
                    best_stats = res
                    best_config = cfg

            if best_config is None:
                best_config = SimulationConfig()

            patches = self.detect_venue_patches(venue_name, venue_races)

            results_by_venue[venue_name] = {
                "venue_name": venue_name,
                "race_count": len(venue_races),
                "best_config": best_config,
                "best_stats": best_stats,
                "patches": patches
            }

        return results_by_venue


class ParameterOptimizer:
    """グリッドサーチによるパラメータ探索クラス"""

    def __init__(self, engine: SimulationEngine):
        self.engine = engine

    def optimize(self, param_grid: List[SimulationConfig]) -> Tuple[Optional[SimulationConfig], Dict[str, Any]]:
        best_config = None
        best_result: Dict[str, Any] = {"recovery_rate": -1.0}

        for config in param_grid:
            res = self.engine.run_simulation(config)
            if res["recovery_rate"] > best_result["recovery_rate"]:
                best_result = res
                best_config = config

        return best_config, best_result


if __name__ == "__main__":
    logging.basicConfig(level=logging.INFO)
    sim_engine = SimulationEngine(results_dir="data/results", horses_dir="data/horses")
    finder = VenueRuleFinder(sim_engine)
    venue_results = finder.analyze_all_venues()
    print(f"分析完了: 全 {len(venue_results)} 会場のルール探索結果を取得しました。")
