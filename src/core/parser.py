"""
NkParser: netkeiba HTMLコンテンツ用パーサーモジュール

BeautifulSoup を用いて HTML レース出馬表、レース結果、馬プロフィール、血統情報、
払い戻しデータ等の各種データを抽出し、構造化されたデータ（dict / list）に変換します。
"""

import logging
import re
from typing import Any, Dict, List, Optional, Union
from urllib.parse import parse_qs, urlparse

from bs4 import BeautifulSoup

try:
    from src.constants.netkeibatag import (
        GradeSelector,
        HorseDBSelector,
        ResultSelector,
        ShutubaSelector,
    )
except ImportError:
    # 依存関係読み込みフォールバック
    try:
        from constants.netkeibatag import (
            GradeSelector,
            HorseDBSelector,
            ResultSelector,
            ShutubaSelector,
        )
    except ImportError:
        # モック/ダミー定義（独立動作・単体テスト用）
        class ShutubaSelector:
            RACE_NAME = ".RaceName"
            RACE_DATA = ".RaceData01"
            RACE_DATA02 = ".RaceData02"
            BRACKET_NUM = ".Waku"
            HORSE_NUM = ".Umaban"
            HORSE_NAME = ".HorseInfo .HorseName"
            AGE = ".Barei"
            AGE_NAR = ".Barei"
            WEIGHT_CARRIED = ".Kinba"
            JOCKEY = ".Jockey"
            STABLE = ".Trainer"

        class ResultSelector:
            RANK = ".Rank"
            BRACKET_NUM = ".Waku"
            HORSE_NUM = ".Umaban"
            HORSE_NUM_NAR = ".Umaban"
            HORSE_NAME = ".HorseName"
            AGE = ".Barei"
            WEIGHT_CARRIED = ".Kinba"
            JOCKEY = ".Jockey"
            STABLE = ".Trainer"
            TIME = ".Time"
            MARGIN = ".Margin"
            POPULARITY = ".Ninki"
            ODDS = ".Odds"
            LAST_3F = ".Last3f"
            HORSE_WEIGHT = ".Weight"
            PASSING_ORDER = ".PassingOrder"

        class GradeSelector:
            @staticmethod
            def get_selectors():
                return []

            @staticmethod
            def to_japanese(selector):
                return ""

        class HorseDBSelector:
            LAST3F_1ST = ".last3f_1st"
            LAST3F_2ND = ".last3f_2nd"
            LAST3F_3RD = ".last3f_3rd"

try:
    from src.utils.text_utils import extract_id_from_url
except ImportError:
    try:
        from text_utils import extract_id_from_url
    except ImportError:

        def extract_id_from_url(url: str) -> str:
            if not url:
                return ""
            return url.rstrip("/").split("/")[-1]


logger = logging.getLogger(__name__)


class NkParser:
    """netkeiba WebページのHTML解析およびデータ抽出演算を行うクラス"""

    # ----------------------------------------------------------------------
    # 汎用ヘルパーメソッド
    # ----------------------------------------------------------------------
    def _get_cell_text(self, row: Any, selector: str) -> str:
        """指定されたCSSセレクタに一致する要素のテキストを取得する汎用関数"""
        if not row or not selector:
            return ""
        elem = row.select_one(selector)
        return elem.get_text(strip=True) if elem else ""

    # ----------------------------------------------------------------------
    # URL・レース基本情報関連
    # ----------------------------------------------------------------------
    def get_race_id(self, url: str) -> str:
        """URLからレースIDを抽出する"""
        parsed_url = urlparse(url)
        query_params = parse_qs(parsed_url.query)
        race_id_list = query_params.get("race_id")
        return race_id_list[0] if race_id_list else "202600000000"

    def get_race_num(self, url: str) -> str:
        """URLからレース番号を抽出する (例: "12")"""
        race_id = self.get_race_id(url)
        return race_id[-2:] if len(race_id) >= 2 else "00"

    def get_race_name(self, soup: BeautifulSoup) -> str:
        """レース名を取得する"""
        return self._get_cell_text(soup, ShutubaSelector.RACE_NAME) or "Unknown"

    def get_race_grade(self, soup: BeautifulSoup) -> str:
        """レースの重賞グレード（G1, G2, G3等）を取得する"""
        for selector in GradeSelector.get_selectors():
            elem = soup.select_one(selector)
            if elem:
                return GradeSelector.to_japanese(selector)
        return ""

    def get_race_grade_in_title(self, title: str) -> str:
        """タイトルからクラス/条件名（C1, B1等）を抽出する"""
        if not title:
            return ""
        match = re.search(r"[（\(](.*?)[）\)]", title)
        return match.group(1).strip() if match else title.strip()

    def get_race_info_line1(self, soup: BeautifulSoup) -> str:
        """レース詳細1行目（発走時刻、距離、天候、馬場等）を取得"""
        return self._get_cell_text(soup, ShutubaSelector.RACE_DATA) or "Unknown"

    def get_race_info_line2(self, soup: BeautifulSoup) -> str:
        """レース詳細2行目（回数、開催場、日数、クラス、頭数等）を取得"""
        return self._get_cell_text(soup, ShutubaSelector.RACE_DATA02) or "Unknown"

    def get_race_time(self, info_text: str) -> str:
        """レース発走時刻（例: "15:35"）を取得"""
        match = re.search(r"(\d{1,2}:\d{2})", info_text)
        return match.group(0) if match else ""

    def get_race_types(self, info_text: str) -> Dict[str, str]:
        """コース種別、距離、詳細コース情報を分解取得"""
        line_type_strs = info_text.split("/")
        if len(line_type_strs) < 2:
            logger.info("パースに失敗しました: フォーマットが不正です")
            return {}

        target_str = line_type_strs[1].strip()
        match = re.search(r"^([芝ダ障])(\d+m)(.*)$", target_str)
        if match:
            return {
                "race_type": match.group(1),
                "distance": match.group(2),
                "course": match.group(3).strip(),
            }
        logger.info("レースタイプのパースに失敗しました")
        return {}

    def conv_race_type(self, type_text: str) -> str:
        """文字表記からコース種別を正規化変換"""
        if "ダ" in type_text:
            return "ダート"
        if "芝" in type_text:
            return "芝"
        if "障" in type_text:
            return "障害"
        return "Unknown"

    def get_race_weather(self, type_text: str) -> str:
        """天候文字列を取得"""
        match = re.search(r"天候[:：]?\s*([^\s/]+)", type_text)
        return match.group(1) if match else ""

    def get_race_weahter(self, type_text: str) -> str:
        """旧メソッド互換（タイポ修正用エイリアス）"""
        return self.get_race_weather(type_text)

    def get_race_condition(self, type_text: str) -> str:
        """馬場状態文字列（良・稍重・重・不良）を取得"""
        match = re.search(r"馬場[:：]?\s*([^\s/]+)", type_text)
        return match.group(1) if match else ""

    def get_race_held_info(self, info_text: str) -> Dict[str, str]:
        """開催回数・開催場・日数・クラス・頭数を一括抽出"""
        r_infos = {}
        pattern = r"^(\d+回)([^\d]+)(\d+日目)(.*?)(?=\d+頭)"
        match = re.search(pattern, info_text)
        if match:
            r_infos["race_kai"] = match.group(1)
            r_infos["race_track"] = match.group(2)
            r_infos["race_days"] = match.group(3)
            r_infos["race_class"] = match.group(4)
            tosu_match = re.search(r"(\d+頭)", info_text)
            r_infos["horses_num"] = tosu_match.group(1) if tosu_match else "不明"
        else:
            logger.info("開催情報のパースに失敗しました")
        return r_infos

    def is_nar(self, url: str) -> bool:
        """地方競馬(NAR)サイトのURLか判定"""
        return "nar.netkeiba.com" in url

    def get_result_horse_num_selector(self, is_nar: bool) -> str:
        """地方/中央別の結果馬番セレクタを取得"""
        return ResultSelector.HORSE_NUM_NAR if is_nar else ResultSelector.HORSE_NUM

    def is_horse_shutuba_data_line(self, row: Any) -> bool:
        """行要素が出馬表の競走馬データ行か判定"""
        return bool(row.select(ShutubaSelector.HORSE_NAME))

    def is_horse_result_data_line(self, row: Any) -> bool:
        """行要素がレース結果の競走馬データ行か判定"""
        h_tag = row.select(ResultSelector.HORSE_NAME)
        r_tag = row.select(ResultSelector.RANK)
        return bool(h_tag and r_tag)

    # ----------------------------------------------------------------------
    # URL・ID抽出（text_utils 一元化）
    # ----------------------------------------------------------------------
    def get_horse_url(self, row: Any) -> str:
        a_elem = row.find("a")
        return a_elem["href"] if a_elem and a_elem.has_attr("href") else ""

    def get_jockey_url(self, row: Any) -> str:
        jockey_a = row.select_one("td.Jockey a")
        return jockey_a["href"] if jockey_a and jockey_a.has_attr("href") else ""

    def get_stable_url(self, row: Any) -> str:
        trainer_a = row.select_one("td.Trainer a")
        return trainer_a["href"] if trainer_a and trainer_a.has_attr("href") else ""

    def conv_horse_id_from_url(self, url: str) -> str:
        """URLから競走馬IDを取得"""
        return extract_id_from_url(url)

    def conv_jockey_id_from_url(self, url: str) -> str:
        """URLから騎手IDを取得"""
        return extract_id_from_url(url)

    def conv_stable_id_from_url(self, url: str) -> str:
        """URLから調教師IDを取得"""
        return extract_id_from_url(url)

    # ----------------------------------------------------------------------
    # 馬情報・成績セルパース（出馬表 vs レース結果）
    # ----------------------------------------------------------------------
    def get_bracket_num(self, row: Any) -> str:
        """出馬表：枠番"""
        return self._get_cell_text(row, ShutubaSelector.BRACKET_NUM)

    def get_bracket_num_as_result(self, row: Any) -> str:
        """レース結果：枠番"""
        return self._get_cell_text(row, ResultSelector.BRACKET_NUM)

    def get_horse_num(self, row: Any) -> str:
        """出馬表：馬番"""
        return self._get_cell_text(row, ShutubaSelector.HORSE_NUM)

    def get_horse_num_as_result(self, row: Any, is_nar: bool = False) -> str:
        """レース結果：馬番"""
        selector = self.get_result_horse_num_selector(is_nar)
        return self._get_cell_text(row, selector)

    def get_horse_name(self, row: Any) -> str:
        """出馬表：馬名"""
        return self._get_cell_text(row, ShutubaSelector.HORSE_NAME)

    def get_horse_name_as_result(self, row: Any) -> str:
        """レース結果：馬名"""
        return self._get_cell_text(row, ResultSelector.HORSE_NAME)

    def get_horse_age(self, row: Any, is_nar: bool = False) -> str:
        """出馬表：性齢"""
        selector = ShutubaSelector.AGE_NAR if is_nar else ShutubaSelector.AGE
        return self._get_cell_text(row, selector)

    def get_horse_age_as_result(self, row: Any) -> str:
        """レース結果：性齢"""
        return self._get_cell_text(row, ResultSelector.AGE)

    def get_horse_weight_carried(self, row: Any) -> str:
        """出馬表：斤量"""
        return self._get_cell_text(row, ShutubaSelector.WEIGHT_CARRIED)

    def get_horse_weight_carried_as_result(self, row: Any) -> str:
        """レース結果：斤量"""
        return self._get_cell_text(row, ResultSelector.WEIGHT_CARRIED)

    def get_horse_jockey(self, row: Any) -> str:
        """出馬表：騎手"""
        return self._get_cell_text(row, ShutubaSelector.JOCKEY)

    def get_horse_jockey_as_result(self, row: Any) -> str:
        """レース結果：騎手"""
        return self._get_cell_text(row, ResultSelector.JOCKEY)

    def get_stable(self, row: Any) -> str:
        """出馬表：調教師/厩舎"""
        return self._get_cell_text(row, ShutubaSelector.STABLE)

    def get_stable_as_result(self, row: Any) -> str:
        """レース結果：調教師/厩舎"""
        return self._get_cell_text(row, ResultSelector.STABLE)

    def get_horse_rank(self, row: Any) -> str:
        """レース結果：着順"""
        return self._get_cell_text(row, ResultSelector.RANK)

    def get_finished_time(self, row: Any) -> str:
        """レース結果：走破タイム"""
        return self._get_cell_text(row, ResultSelector.TIME)

    def get_finished_margin(self, row: Any) -> str:
        """レース結果：着差"""
        return self._get_cell_text(row, ResultSelector.MARGIN)

    def get_popularity(self, row: Any) -> str:
        """レース結果：人気"""
        return self._get_cell_text(row, ResultSelector.POPULARITY)

    def get_odds(self, row: Any) -> str:
        """レース結果：単勝オッズ"""
        return self._get_cell_text(row, ResultSelector.ODDS)

    def get_last3f(self, row: Any) -> str:
        """レース結果：上がり3Fタイム"""
        return self._get_cell_text(row, ResultSelector.LAST_3F)

    def get_horse_weight_and_diff_as_result(self, row: Any) -> Dict[str, str]:
        """レース結果：馬体重および増減の分解取得"""
        weight_text = self._get_cell_text(row, ResultSelector.HORSE_WEIGHT)
        match = re.search(r"^(\d+)(?:\s*\(([+-]?\d+)\))?$", weight_text)
        if match:
            return {
                "horse_weight": match.group(1),
                "weight_diff": match.group(2) if match.group(2) is not None else "0",
            }
        return {"horse_weight": "", "weight_diff": ""}

    def get_horse_wieght_and_diff_as_result(self, row: Any) -> Dict[str, str]:
        """旧メソッド互換（タイポ修正用エイリアス）"""
        return self.get_horse_weight_and_diff_as_result(row)

    def get_horse_passing_order(
        self, row: Any, soup: BeautifulSoup, is_nar: bool, horse_num: str
    ) -> str:
        """レース結果：コーナー通過順位の取得"""
        if not is_nar:
            result = self._get_cell_text(row, ResultSelector.PASSING_ORDER)
            if result:
                return result

        pass_map = self.get_horse_passing_orders_map(soup)
        return pass_map.get(horse_num, "")

    def get_horse_passing_orders_map(self, soup: BeautifulSoup) -> Dict[str, str]:
        """地方競馬・コーナー通過順テーブルから全馬の通過順マップ（例: {"1": "1-1-2"}）を作成"""
        pass_map: Dict[str, str] = {}
        try:
            corner_rows = soup.select(".RaceCommon_Table.Corner_Num tr")
            temp_pass_data: Dict[str, List[str]] = {}

            for row in corner_rows:
                th = row.find("th")
                td = row.find("td")
                if not th or not td:
                    continue

                th_text = th.get_text(strip=True)
                td_text = td.get_text(strip=True)

                if "コーナー" in th_text:
                    order_processed = td_text.replace("(", ",").replace(")", ",")
                    order_list = [
                        h.strip() for h in order_processed.split(",") if h.strip()
                    ]

                    for rank_idx, h_num in enumerate(order_list):
                        h_num_clean = re.sub(r"\D", "", h_num)
                        if h_num_clean:
                            if h_num_clean not in temp_pass_data:
                                temp_pass_data[h_num_clean] = []
                            temp_pass_data[h_num_clean].append(str(rank_idx + 1))

            for h_num, ranks in temp_pass_data.items():
                pass_map[h_num] = "-".join(ranks)
            return pass_map
        except Exception as e:
            logger.warning(f"コーナー通過順の解析エラー: {e}")
            return {}

    # ----------------------------------------------------------------------
    # 馬プロフィール・血統・戦績詳細パース
    # ----------------------------------------------------------------------
    def get_horse_profile_header(self, soup: BeautifulSoup) -> str:
        """馬基本ページヘッダーテキスト取得"""
        return self._get_cell_text(soup, ".horse_title")

    def get_horse_profile_base_info(self, prof_text: str) -> Dict[str, str]:
        """馬名、英語名、性齢、毛色のパース"""
        results = {
            "horse_name": "",
            "horse_eng_name": "",
            "horse_age": "",
            "horse_type": "",
        }
        pattern = r"^([^\x00-\x7F]+)([A-Za-z\s]+?)([牡牝セ]\d+歳)\s*(.+毛)$"
        match = re.search(pattern, prof_text)
        if match:
            results["horse_name"] = match.group(1)
            results["horse_eng_name"] = match.group(2)
            results["horse_age"] = match.group(3)
            results["horse_type"] = match.group(4)
        else:
            logger.error("馬ヘッダー情報のパースに失敗しました")
        return results

    def get_horse_profile_details(self, soup: BeautifulSoup) -> Dict[str, str]:
        """馬プロフィール詳細テーブル（生年月日、調教師、馬主等）のパース"""
        results = {}
        prof_table = soup.find("table", class_="db_prof_table")
        if not prof_table:
            logger.info("※馬データのプロフィール部分の解析に失敗したか、構造が異なります。")
            return {}

        rows = prof_table.find_all("tr")
        for row in rows:
            th = row.find("th")
            td = row.find("td")
            if th and td:
                key = th.get_text(strip=True)
                value = td.get_text(strip=True)
                results[key] = value
        return results

    def get_horse_blood_info(self, soup: BeautifulSoup) -> Dict[str, Any]:
        """血統表（父、父父、父母、母、母父、母母）のパース"""
        results = {}
        blood_table = soup.find("table", class_="blood_table")
        if not blood_table:
            logger.info("※馬データの血統表部分の解析に失敗したか、構造が異なります。")
            return {}

        a_tags = blood_table.find_all("a")
        labels = ["sire", "sire_sire", "sire_dam", "dam", "dam_sire", "dam_dam"]
        for i, a in enumerate(a_tags):
            if i < len(labels):
                key = labels[i]
                name = a.get_text(strip=True)
                url = a.get("href")
                results[key] = {"name": name, "url": url}
        return results

    def get_horse_race_records_history(self, soup: BeautifulSoup) -> List[List[str]]:
        """過去戦績テーブルのパース"""
        results = []
        race_table = soup.find("table", class_="db_h_race_results")
        if not race_table:
            logger.info("※馬データの戦績部分の解析に失敗したか、構造が異なります。")
            return []

        rows = race_table.find_all("tr")
        is_header = True
        for row in rows:
            cells = row.find_all(["td", "th"])
            cell_data = [cell.get_text(strip=True) for cell in cells]

            last3f_num = ""
            for i, selector in enumerate(
                [
                    HorseDBSelector.LAST3F_1ST,
                    HorseDBSelector.LAST3F_2ND,
                    HorseDBSelector.LAST3F_3RD,
                ],
                1,
            ):
                elm = row.find(selector)
                if elm:
                    last3f_num = f"{i}番"
                    break

            cell_data.append("上がり順位" if is_header else last3f_num)
            if is_header:
                is_header = False

            if cell_data:
                results.append(cell_data)
        return results

    def parse_payouts(self, soup: BeautifulSoup) -> Dict[str, Any]:
        """払い戻し情報のパース"""
        payout_data = {}
        rows = soup.select("table.Payout_Detail_Table tr")

        for row in rows:
            th = row.select_one("th")
            if not th:
                continue
            bet_type = th.get_text(strip=True)

            payout_td = row.select_one("td.Payout")
            payouts = list(payout_td.stripped_strings) if payout_td else []

            ninki_td = row.select_one("td.Ninki")
            ninkis = list(ninki_td.stripped_strings) if ninki_td else []

            result_td = row.select_one("td.Result")
            results = []
            if result_td:
                results = [
                    span.get_text(strip=True)
                    for span in result_td.select("span")
                    if span.get_text(strip=True)
                ]

            payout_data[bet_type] = {
                "results": results,
                "payouts": payouts,
                "popularity": ninkis,
            }

        return payout_data
