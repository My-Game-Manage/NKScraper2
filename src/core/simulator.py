"""
simulator.py - 競馬予想ロジックのバックテスト・全頭100点満点評価エンジン

1. 過去レース結果JSON (data/results/YYYY/MM/*.json) および馬マスターJSON (data/horses/*.json) の読み込み
2. 100点満点スコアリングに基づく全過去レースのシミュレーション（回収率・的中率の算出）
3. 会場別データグループ化 ＆ 統計的条件パッチ（重馬場補正、枠順リスク等）の自動検出 (VenueRuleFinder)
4. 出走全頭能力評価・100点満点スコアリング・予想印(◎○▲☆△)割り振りとnote用Markdown自動出力 (RacePredictor)
"""

import os
import json
import logging
import re
from pathlib import Path
from typing import Dict, List, Any, Optional, Tuple, Union
from dataclasses import dataclass, field

logger = logging.getLogger(__name__)


def normalize_horse_history(history: List[Any]) -> List[Dict[str, Any]]:
    """
    horse_history が list[list] (0行目がヘッダー) の場合も list[dict] の場合も
    統一して list[dict] の形式に変換して返す
    """
    if not history:
        return []

    # すでに list[dict] の場合
    if isinstance(history[0], dict):
        return [h for h in history if isinstance(h, dict)]

    # list[list] の場合 (0行目がヘッダー)
    if isinstance(history[0], (list, tuple)) and len(history) > 1:
        headers = [str(col).strip() for col in history[0]]
        dict_rows = []
        for row in history[1:]:
            if isinstance(row, (list, tuple)):
                r_dict = {}
                for h_name, val in zip(headers, row):
                    r_dict[h_name] = str(val).strip() if val is not None else ""
                dict_rows.append(r_dict)
        return dict_rows

    return []


@dataclass
class SimulationConfig:
    """100点満点評価・シミュレーション用ハイパーパラメータ構成クラス (馬能力最重視型)"""

    # 基礎点 (完全撤廃: 0点スタート)
    base_score: float = 0.0

    # ① 馬の絶対能力・競走性能評価 (最大 55点)
    ability_place_rate_high_score: float = 15.0 # 近5走複勝率60%以上 / 平均3.0位以内
    ability_place_rate_mid_score: float = 10.0  # 近5走複勝率40%以上 / 平均5.0位以内
    ability_place_rate_low_score: float = 5.0   # 近5走複勝率20%以上 / 平均7.0位以内

    time_diff_excellent_score: float = 15.0     # 勝ち馬とのタイム差 0.2秒以内 (+15点)
    time_diff_good_score: float = 10.0          # 勝ち馬とのタイム差 0.5秒以内 (+10点)
    time_diff_fair_score: float = 5.0           # 勝ち馬とのタイム差 0.8秒以内 (+5点)

    course_distance_aptitude_high: float = 15.0 # 同コース複勝率 50%以上
    course_distance_aptitude_mid: float = 10.0  # 同コース複勝率 30%以上
    course_distance_aptitude_low: float = 5.0   # 同コース複勝率 15%以上

    class_proven_score: float = 5.0            # 同クラス〜上級1~3着実績あり
    newcomer_base_ability_score: float = 15.0  # 新馬・データ未蓄積基本想定点

    # ② 前走実績・ローテーション (最大 20点)
    prev_1st_score: float = 20.0                # 前走1着 (勝ち馬)
    prev_top3_score: float = 15.0               # 前走2~3着
    prev_4_5th_score: float = 10.0              # 前走4~5着
    prev_blowout_penalty: float = -10.0          # 前走10着以下大敗
    prev_blowout_mitigated_penalty: float = -5.0 # トップコンビ時大敗減点緩和

    # ③ 騎手・鞍上・厩舎評価 (最大 15点)
    s_jockey_score: float = 15.0       # S評価騎手（ルメール, 川田, 笹川, 岡部, 吉原, 吉村等）
    a_jockey_score: float = 10.0       # A評価騎手（坂井, 武豊, 矢野, 本田, 下原等）
    young_jockey_score: float = 5.0    # 減量・若手騎手 (☆, △, ▲)
    top_stable_revival_score: float = 5.0 # トップコンビ巻き返し補正

    # ④ コース・枠順・脚質・馬体重適性 (最大 10点)
    dirt_outer_bracket_score: float = 10.0    # ダート 5~8枠
    dirt_inner_bracket_penalty: float = -5.0   # ダート 1~3枠 (被せリスク)
    dirt_weight_boost: float = 5.0             # ダート 480kg以上大型馬
    dirt_apprentice_outer_boost: float = 5.0   # ダート 7~8枠 × 減量騎手
    turf_favorable_bracket_score: float = 8.0  # 芝 5枠・7枠
    turf_last3f_boost: float = 8.0             # 芝 上がり33.5秒以下実績

    # ⑤ 買い目・運用パラメータ
    bet_type: str = "tansho"                   # "tansho", "fukusho", "umaren", "wide", "sanrenpuku"
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


class PersonnelTrendAnalyzer:
    """過去結果データから騎手・厩舎のパフォーマンスプロファイルを自動生成するクラス"""

    @staticmethod
    def extract_profiles_from_races(races: List[Dict[str, Any]]) -> Tuple[Dict[str, Dict[str, Any]], Dict[str, Dict[str, Any]]]:
        jockey_stats: Dict[str, Dict[str, Any]] = {}
        trainer_stats: Dict[str, Dict[str, Any]] = {}

        for race in races:
            results = race.get("results", [])
            track = race.get("race_track", "")
            for horse in results:
                if not isinstance(horse, dict):
                    continue
                jname = str(horse.get("jockey", "")).strip()
                tname = str(horse.get("stable", "")).strip()
                rank_str = str(horse.get("rank", ""))
                try:
                    rank = int(rank_str)
                except ValueError:
                    continue

                if jname:
                    if jname not in jockey_stats:
                        jockey_stats[jname] = {"rides": 0, "top3": 0}
                    jockey_stats[jname]["rides"] += 1
                    if rank <= 3:
                        jockey_stats[jname]["top3"] += 1

                if tname:
                    if tname not in trainer_stats:
                        trainer_stats[tname] = {"runs": 0, "top3": 0, "venues": {}}
                    trainer_stats[tname]["runs"] += 1
                    if rank <= 3:
                        trainer_stats[tname]["top3"] += 1
                    if track:
                        trainer_stats[tname]["venues"][track] = trainer_stats[tname]["venues"].get(track, 0) + (1 if rank <= 3 else 0)

        jockey_profiles = {}
        for jname, st in jockey_stats.items():
            rides = st["rides"]
            top3 = st["top3"]
            fukusho_rate = (top3 / rides * 100.0) if rides > 0 else 0.0
            jockey_profiles[jname] = {
                "rides": rides,
                "fukusho_rate": round(fukusho_rate, 1),
            }

        trainer_profiles = {}
        for tname, st in trainer_stats.items():
            runs = st["runs"]
            top3 = st["top3"]
            fukusho_rate = (top3 / runs * 100.0) if runs > 0 else 0.0
            best_venue = ""
            if st["venues"]:
                best_venue = max(st["venues"], key=st["venues"].get)
            trainer_profiles[tname] = {
                "runs": runs,
                "fukusho_rate": round(fukusho_rate, 1),
                "best_venue": best_venue
            }

        return jockey_profiles, trainer_profiles


class RaceEvaluator:
    """出走馬の事前能力・適性スコア算出クラス（100点満点・馬能力最重視版）"""

    DEFAULT_S_JOCKEYS = ["ルメール", "C.デムーロ", "モレイラ", "川田", "川田将雅", "笹川", "笹川翼", "岡部誠", "吉原寛人", "吉村智洋"]
    DEFAULT_A_JOCKEYS = ["坂井瑠星", "坂井", "松山弘平", "松山", "武豊", "バルザローナ", "矢野", "矢野貴之", "本田", "本田正重", "今井貴大", "下原理", "藤原幹生"]
    DEFAULT_TOP_STABLES = ["友道", "須貝", "中内田", "矢作", "池江", "杉山晴", "木村", "手塚", "国枝", "藤田", "小野", "新子", "角川"]

    def __init__(
        self,
        config: SimulationConfig,
        jockey_profiles: Optional[Dict[str, Dict[str, Any]]] = None,
        trainer_profiles: Optional[Dict[str, Dict[str, Any]]] = None
    ):
        self.config = config
        self.jockey_profiles = jockey_profiles or {}
        self.trainer_profiles = trainer_profiles or {}

        self.s_jockeys = set(self.DEFAULT_S_JOCKEYS)
        self.a_jockeys = set(self.DEFAULT_A_JOCKEYS)
        self.top_stables = set(self.DEFAULT_TOP_STABLES)

        if self.jockey_profiles:
            for j_name, prof in self.jockey_profiles.items():
                rides = prof.get("rides", 0)
                rate = prof.get("fukusho_rate", 0.0)
                if rides >= 3:
                    if rate >= 35.0:
                        self.s_jockeys.add(j_name)
                    elif rate >= 22.0:
                        self.a_jockeys.add(j_name)

        if self.trainer_profiles:
            for t_name, prof in self.trainer_profiles.items():
                runs = prof.get("runs", 0)
                rate = prof.get("fukusho_rate", 0.0)
                if runs >= 3 and rate >= 28.0:
                    self.top_stables.add(t_name)

    def evaluate_race(
        self,
        race_json: Dict[str, Any],
        horse_master_dict: Dict[str, Dict[str, Any]]
    ) -> List[Dict[str, Any]]:
        results = race_json.get("results", []) or race_json.get("horses", [])
        race_track = str(race_json.get("race_track", ""))
        race_type = str(race_json.get("race_type", ""))
        race_class = str(race_json.get("race_class", ""))

        is_dirt = ("ダ" in race_type or "ダート" in race_type or any(v in race_track for v in ["大井", "浦和", "園田", "名古屋", "金沢", "船橋", "川崎", "門別"]))
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
            raw_history = master_data.get("horse_history", [])
            history = normalize_horse_history(raw_history)
            horse_prof = master_data.get("horse_prof", {})

            # 100点満点評価：基礎点は廃止し0点から採点
            score = self.config.base_score
            reasons = []

            # =========================================================
            # ① 【馬自身の絶対能力・競走性能評価】(最大 55点)
            # =========================================================
            if history and len(history) > 0:
                valid_ranks = []
                top3_cnt = 0
                same_course_top3 = 0
                same_course_cnt = 0
                min_time_diff = 99.0

                for h_row in history[:5]:
                    r_str = str(h_row.get("着順", ""))
                    if r_str.isdigit():
                        r_val = int(r_str)
                        valid_ranks.append(r_val)
                        if r_val <= 3:
                            top3_cnt += 1

                    h_track = str(h_row.get("開催", "") or h_row.get("場名", ""))
                    if race_track and race_track in h_track:
                        same_course_cnt += 1
                        if r_str.isdigit() and int(r_str) <= 3:
                            same_course_top3 += 1

                    td_str = str(h_row.get("着差", "") or h_row.get("タイム差", ""))
                    try:
                        td_val = float(re.sub(r"[^0-9.]", "", td_str))
                        if td_val < min_time_diff:
                            min_time_diff = td_val
                    except ValueError:
                        pass

                n_runs = len(valid_ranks)
                avg_rank = (sum(valid_ranks) / n_runs) if n_runs > 0 else 99.0
                place_rate = (top3_cnt / n_runs * 100.0) if n_runs > 0 else 0.0

                if place_rate >= 60.0 or avg_rank <= 3.0:
                    score += self.config.ability_place_rate_high_score
                    reasons.append(f"馬能力:近5走好走率高(複勝率{place_rate:.0f}%/平均{avg_rank:.1f}位) +{self.config.ability_place_rate_high_score:.0f}pt")
                elif place_rate >= 40.0 or avg_rank <= 5.0:
                    score += self.config.ability_place_rate_mid_score
                    reasons.append(f"馬能力:近5走安定(複勝率{place_rate:.0f}%/平均{avg_rank:.1f}位) +{self.config.ability_place_rate_mid_score:.0f}pt")
                elif place_rate >= 20.0 or avg_rank <= 7.0:
                    score += self.config.ability_place_rate_low_score
                    reasons.append(f"馬能力:近5走掲示板級(複勝率{place_rate:.0f}%/平均{avg_rank:.1f}位) +{self.config.ability_place_rate_low_score:.0f}pt")

                if min_time_diff <= 0.2:
                    score += self.config.time_diff_excellent_score
                    reasons.append(f"馬能力:最高スピード(接戦差{min_time_diff:.1f}s) +{self.config.time_diff_excellent_score:.0f}pt")
                elif min_time_diff <= 0.5:
                    score += self.config.time_diff_good_score
                    reasons.append(f"馬能力:接戦好走歴(着差{min_time_diff:.1f}s) +{self.config.time_diff_good_score:.0f}pt")
                elif min_time_diff <= 0.8:
                    score += self.config.time_diff_fair_score
                    reasons.append(f"馬能力:上位タイム差(着差{min_time_diff:.1f}s) +{self.config.time_diff_fair_score:.0f}pt")

                if same_course_cnt >= 2:
                    sc_rate = (same_course_top3 / same_course_cnt * 100.0)
                    if sc_rate >= 50.0:
                        score += self.config.course_distance_aptitude_high
                        reasons.append(f"馬能力:同コース超得意(複勝率{sc_rate:.0f}%) +{self.config.course_distance_aptitude_high:.0f}pt")
                    elif sc_rate >= 30.0:
                        score += self.config.course_distance_aptitude_mid
                        reasons.append(f"馬能力:同コース適性高(複勝率{sc_rate:.0f}%) +{self.config.course_distance_aptitude_mid:.0f}pt")
                    elif sc_rate >= 15.0:
                        score += self.config.course_distance_aptitude_low
                        reasons.append(f"馬能力:同コース実績あり(複勝率{sc_rate:.0f}%) +{self.config.course_distance_aptitude_low:.0f}pt")

                if any(r <= 3 for r in valid_ranks):
                    score += self.config.class_proven_score
                    reasons.append(f"馬能力:同クラス1~3着実績あり +{self.config.class_proven_score:.0f}pt")

                ts_str = str(horse_prof.get("通算成績", ""))
                win_match = re.search(r"(\d+)勝", ts_str)
                total_wins = int(win_match.group(1)) if win_match else sum(1 for h in history if str(h.get("着順", "")) == "1")
                if total_wins >= 5:
                    score += 5.0
                    reasons.append(f"馬能力:通算勝利数豊富({total_wins}勝) +5pt")
            else:
                score += self.config.newcomer_base_ability_score
                reasons.append(f"馬能力:新馬・データ未蓄積基本想定点 +{self.config.newcomer_base_ability_score:.0f}pt")

            # =========================================================
            # ② 【前走実績・ローテーション】(最大 20点)
            # =========================================================
            if history and len(history) > 0:
                h_first = history[0]
                prev_rank_str = str(h_first.get("着順", ""))
                if prev_rank_str.isdigit():
                    pr = int(prev_rank_str)
                    if pr == 1:
                        score += self.config.prev_1st_score
                        reasons.append(f"前走勝ち馬(1着) +{self.config.prev_1st_score:.0f}pt")
                    elif 2 <= pr <= 3:
                        score += self.config.prev_top3_score
                        reasons.append(f"前走好走({pr}着) +{self.config.prev_top3_score:.0f}pt")
                    elif 4 <= pr <= 5:
                        score += self.config.prev_4_5th_score
                        reasons.append(f"前走掲示板({pr}着) +{self.config.prev_4_5th_score:.0f}pt")
                    elif pr >= 10:
                        is_s_jockey = any(sj in jockey for sj in self.s_jockeys)
                        is_a_jockey = any(aj in jockey for aj in self.a_jockeys)
                        is_top_stable = any(ts in stable for ts in self.top_stables)
                        if is_top_stable and (is_s_jockey or is_a_jockey):
                            score += self.config.prev_blowout_mitigated_penalty
                            reasons.append(f"前走大敗(トップコンビ緩和) {self.config.prev_blowout_mitigated_penalty:.0f}pt")
                        else:
                            score += self.config.prev_blowout_penalty
                            reasons.append(f"前走10着以下大敗 {self.config.prev_blowout_penalty:.0f}pt")

            # =========================================================
            # ③ 【騎手・鞍上・厩舎評価】(最大 15点)
            # =========================================================
            is_s_jockey = any(sj in jockey for sj in self.s_jockeys)
            is_a_jockey = any(aj in jockey for aj in self.a_jockeys)
            is_top_stable = any(ts in stable for ts in self.top_stables)

            if is_s_jockey:
                score += self.config.s_jockey_score
                reasons.append(f"S評価騎手({jockey}) +{self.config.s_jockey_score:.0f}pt")
            elif is_a_jockey:
                score += self.config.a_jockey_score
                reasons.append(f"A評価騎手({jockey}) +{self.config.a_jockey_score:.0f}pt")

            if any(yj in jockey for yj in ["☆", "△", "▲", "◇", "★"]):
                score += self.config.young_jockey_score
                reasons.append(f"減量騎手起用({jockey}) +{self.config.young_jockey_score:.0f}pt")

            t_prof = self.trainer_profiles.get(stable, {})
            if t_prof and t_prof.get("best_venue") == race_track:
                score += 5.0
                reasons.append(f"厩舎・コース得意相性({race_track}) +5pt")

            if is_top_stable and (is_s_jockey or is_a_jockey):
                if history and len(history) > 0:
                    h_first = history[0]
                    prev_rank = str(h_first.get("着順", ""))
                    if prev_rank.isdigit() and int(prev_rank) >= 4:
                        score += self.config.top_stable_revival_score
                        reasons.append(f"トップコンビ巻き返し補正 +{self.config.top_stable_revival_score:.0f}pt")

            # =========================================================
            # ④ 【コース・枠順・脚質・馬体重適性】(最大 10点)
            # =========================================================
            try:
                b_num = int(bracket_num)
            except ValueError:
                b_num = 0

            if is_dirt:
                if b_num >= 5:
                    score += self.config.dirt_outer_bracket_score
                    reasons.append(f"ダート外枠優位({b_num}枠) +{self.config.dirt_outer_bracket_score:.0f}pt")
                elif 1 <= b_num <= 3:
                    score += self.config.dirt_inner_bracket_penalty
                    reasons.append(f"ダート内枠被せリスク({b_num}枠) {self.config.dirt_inner_bracket_penalty:.0f}pt")

                try:
                    hw = float(re.sub(r"[^\d.]", "", horse_weight_str))
                    if hw >= 480:
                        score += self.config.dirt_weight_boost
                        reasons.append(f"ダート大型馬({hw:.0f}kg) +{self.config.dirt_weight_boost:.0f}pt")
                except ValueError:
                    pass

                if b_num in [7, 8] and any(yj in jockey for yj in ["☆", "△", "▲"]):
                    score += self.config.dirt_apprentice_outer_boost
                    reasons.append(f"ダート減量×外枠ブースト +{self.config.dirt_apprentice_outer_boost:.0f}pt")

            elif is_turf:
                if b_num in [5, 7]:
                    score += self.config.turf_favorable_bracket_score
                    reasons.append(f"芝好走枠({b_num}枠) +{self.config.turf_favorable_bracket_score:.0f}pt")

                if history:
                    for h_row in history[:3]:
                        last3f = str(h_row.get("上り", ""))
                        try:
                            if float(last3f) <= 33.5:
                                score += self.config.turf_last3f_boost
                                reasons.append(f"芝極限末脚({last3f}s) +{self.config.turf_last3f_boost:.0f}pt")
                                break
                        except ValueError:
                            pass

            final_score = min(100.0, max(0.0, round(score, 1)))

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
                "score": final_score,
                "reasons": reasons
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
        j_prof, t_prof = PersonnelTrendAnalyzer.extract_profiles_from_races(races_list or self.load_all_races())
        evaluator = RaceEvaluator(config, jockey_profiles=j_prof, trainer_profiles=t_prof)

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
        patches = []
        if not venue_races:
            return patches

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
        all_races = self.engine.load_all_races()
        venue_map = self.group_races_by_venue(all_races)

        results_by_venue = {}
        search_grid = [
            SimulationConfig(bet_type="tansho", top_n_selection=1, min_score_threshold=40.0),
            SimulationConfig(bet_type="tansho", top_n_selection=1, min_score_threshold=30.0),
            SimulationConfig(bet_type="fukusho", top_n_selection=1, min_score_threshold=30.0),
            SimulationConfig(bet_type="wide", top_n_selection=3, min_score_threshold=35.0),
        ]

        for venue_name, venue_races in venue_map.items():
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


class RacePredictor:
    """出馬表データから自動でスコア計算・印割り振り・買い目生成・全頭評価note用Markdownを出力するクラス"""

    def __init__(self, evaluator: RaceEvaluator):
        self.evaluator = evaluator

    @staticmethod
    def parse_shutuba_markdown(md_content: Any) -> Dict[str, Any]:
        """
        00_race_overview.md または 統合出馬表 .md をパースして race_json 辞書を復元する
        """
        if isinstance(md_content, Path):
            with open(md_content, "r", encoding="utf-8") as fp:
                md_content = fp.read()
        elif isinstance(md_content, str) and ("\n" not in md_content) and os.path.exists(md_content):
            with open(md_content, "r", encoding="utf-8") as fp:
                md_content = fp.read()

        lines = str(md_content).splitlines()
        target_date = ""
        race_track = ""
        race_num = ""
        race_name = ""
        race_type = ""
        race_id = ""

        horses = []
        in_table = False

        for line in lines:
            line_str = line.strip()
            if "第" in line_str and "R:" in line_str:
                match = re.search(r"#+\s*(\d+)\s*-\s*【([^】]+)】第(\d+)R:\s*(.*)", line_str)
                if match:
                    target_date = match.group(1)
                    race_track = match.group(2)
                    race_num = str(int(match.group(3)))
                    race_name = match.group(4)
            elif "レースID" in line_str:
                race_id = re.sub(r"[^\d]", "", line_str)
            elif "コース" in line_str:
                race_type = re.sub(r"[\*\-\s\*]*\*\*コース\*\*\s*:\s*", "", line_str).strip()
            elif line_str.startswith("| 枠 | 馬番 |") or line_str.startswith("|枠|馬番|"):
                in_table = True
                continue
            elif in_table and (line_str.startswith("| ---") or line_str.startswith("|---")):
                continue
            elif in_table and line_str.startswith("|"):
                cols = [c.strip() for c in line_str.split("|")[1:-1]]
                if len(cols) >= 7:
                    b_num = cols[0]
                    h_num = cols[1]
                    h_name_raw = cols[2]
                    h_name = re.sub(r"\[(.*?)\]\(.*?\)", r"\g<1>", h_name_raw)
                    h_name = re.sub(r"<[^>]+>", "", h_name).replace("<br>", "").replace("<br/>", "").strip()
                    h_name = re.sub(r"\[(.*?)\]\(.*?\)", r"\g<1>", h_name_raw)
                    h_name = re.sub(r"<[^>]+>", "", h_name).replace("<br>", "").replace("<br/>", "").strip()
                    age = cols[3]
                    weight = cols[4]
                    jockey = cols[5]
                    stable = cols[6]
                    h_id = cols[7] if len(cols) > 7 else ""

                    horses.append({
                        "bracket_num": b_num,
                        "horse_num": h_num,
                        "horse_name": h_name,
                        "horse_age": age,
                        "weight_carried": weight,
                        "jockey": jockey,
                        "stable": stable,
                        "horse_id": h_id
                    })

        return {
            "target_date": target_date,
            "race_track": race_track,
            "race_num": race_num,
            "race_name": race_name,
            "race_id": race_id,
            "race_type": race_type,
            "results": horses
        }

    def predict_race(self, race_json: Dict[str, Any], horse_master_dict: Dict[str, Dict[str, Any]]) -> Dict[str, Any]:
        evaluated = self.evaluator.evaluate_race(race_json, horse_master_dict)
        if not evaluated:
            return {}

        predictions = []
        for idx, h in enumerate(evaluated):
            mark = "−"
            if idx == 0:
                mark = "◎"
            elif idx == 1:
                mark = "○"
            elif idx == 2:
                mark = "▲"
            elif 3 <= idx <= 5:
                b_num = int(h.get("bracket_num", 0)) if str(h.get("bracket_num", "")).isdigit() else 0
                jockey = h.get("jockey", "")
                if b_num in [7, 8] or any(yj in jockey for yj in ["☆", "△", "▲"]) or h["score"] >= 40.0:
                    mark = "☆"
                else:
                    mark = "△"
            elif h["score"] >= 20.0:
                mark = "△"
            else:
                mark = "−"

            h["mark"] = mark
            predictions.append(h)

        honmei = predictions[0] if len(predictions) > 0 else None
        taikou = predictions[1] if len(predictions) > 1 else None
        tanana = predictions[2] if len(predictions) > 2 else None
        himo_list = [h for h in predictions[1:6] if len(predictions) > 1]

        bets = {}
        if honmei:
            h_num = honmei['horse_num']
            h_name = honmei['horse_name']
            bets["単勝"] = f"【単勝】 {h_num} ({h_name}) 1点"

            if himo_list:
                himo_nums = ", ".join([h['horse_num'] for h in himo_list])
                bets["馬連"] = f"【馬連軸流し】 {h_num} − {himo_nums} (計 {len(himo_list)} 点)"
                bets["ワイド"] = f"【ワイド軸流し】 {h_num} − {himo_nums} (計 {len(himo_list)} 点)"

            if taikou and tanana:
                t_num = taikou['horse_num']
                a_num = tanana['horse_num']
                other_himos = ", ".join([h['horse_num'] for h in predictions[3:6]]) if len(predictions) > 3 else f"{t_num},{a_num}"
                bets["3連複"] = f"【3連複フォーメーション】 1頭目:{h_num} − 2頭目:{t_num},{a_num} − 3頭目:{other_himos}"

        return {
            "race_info": race_json,
            "predictions": predictions,
            "recommended_bets": bets
        }

    def generate_note_markdown(self, prediction_result: Dict[str, Any]) -> str:
        race_info = prediction_result.get("race_info", {})
        preds = prediction_result.get("predictions", [])
        bets = prediction_result.get("recommended_bets", {})

        track = race_info.get("race_track", "")
        race_num = race_info.get("race_num", "")
        race_name = race_info.get("race_name", "")
        target_date = race_info.get("target_date", "")

        lines = [
            f"# 【出走全頭能力評価・徹底予想】{target_date} {track}{race_num}R {race_name}",
            "",
            "## 🎯 出走全頭・総合評価スコア一覧 (100点満点採点 / 馬能力最重視版)",
            "",
            "| 印 | 馬番 | 枠 | 馬名 | 騎手 | 総合スコア | 主な評価根拠 |",
            "| :---: | :---: | :---: | :--- | :--- | :---: | :--- |"
        ]

        for p in preds:
            reasons_str = " / ".join(p.get("reasons", [])[:2]) if p.get("reasons") else "基本能力評価"
            score_val = p["score"]
            score_val = p["score"]
            score_val = p["score"]
            score_val = p["score"]
            lines.append(f"| **{p['mark']}** | {p['horse_num']} | {p['bracket_num']} | **{p['horse_name']}** | {p['jockey']} | `{score_val:.1f}点` | {reasons_str} |")
        lines.extend([
            "",
            "## 💡 上位・注目馬の個別評価詳細解説",
            ""
        ])

        for p in preds:
            if p["mark"] in ["◎", "○", "▲", "☆"]:
                mark_label = "本命" if p["mark"] == "◎" else ("対抗" if p["mark"] == "○" else ("単穴" if p["mark"] == "▲" else "特注穴馬"))
                lines.append(f"### {p['mark']} {mark_label}：{p['horse_num']}番 {p['horse_name']} (総合スコア: {p['score']}点)")
                for r in p.get("reasons", []):
                    lines.append(f"- {r}")
                lines.append("")

        lines.extend([
            "## 🎫 推奨買い目・資金配分アドバイス",
            ""
        ])
        for b_type, b_desc in bets.items():
            lines.append(f"- **{b_desc}**")

        lines.extend([
            "",
            "---",
            "*※本予想は馬自身の競走実績・タイム差・複勝率等の絶対能力評価を最重視した100点満点スコアリングロジックに基づき自動生成されています。*"
        ])

        return "\n".join(lines)
