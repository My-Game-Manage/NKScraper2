"""
NkFetcher モジュール
netkeibaの各種ページ（開催一覧、出馬表、レース結果、馬プロフィール、戦績）から
データを抽出・集約するクラスを提供します。
"""

import re
import logging
from typing import List, Dict, Any, Optional
from bs4 import BeautifulSoup

from src.constants.netkeibatag import ShutubaSelector, ResultSelector
from src.netkeiba_client import NkClientSoup
from src.parser import NkParser

# ロガー設定
logger = logging.getLogger(__name__)


class NkFetcher:
    """
    HTMLコンテンツを解析し、構造化されたデータ（辞書・リスト）として抽出するフェッチャークラス。
    """

    def __init__(self, client: Optional[NkClientSoup] = None, parser: Optional[NkParser] = None):
        self.client = client or NkClientSoup()
        self.parser = parser or NkParser()

    def fetch_kaisai_race_ids(self, url: str, html_contents: str) -> List[str]:
        """
        レースの開催ページHTMLからレースID一覧を取得する
        """
        results = []
        if not self._is_kaisai_url(url):
            return results

        soup = self.client.get_soup_as_html(html_contents)

        try:
            pattern = re.compile(r'race_id=(\d+)')
            links = soup.find_all('a', href=pattern)
            for link in links:
                href = link.get('href', '')
                match = pattern.search(href)
                if match:
                    race_id = match.group(1)
                    results.append(race_id)
        except Exception as e:
            logger.info(f'データ抽出中にエラーが発生しました: {e}')
        
        return sorted(list(set(results)))

    def _parse_race_info(self, url: str, soup: BeautifulSoup) -> Dict[str, Any]:
        """
        出馬表・レース結果ページ共通のレース基本情報抽出内部メソッド
        """
        results = {}
        is_nar = self.parser.is_nar(url)

        try:
            # 1. 基本情報（ID、番号、レース名）
            results["race_id"] = self.parser.get_race_id(url)
            results["race_num"] = self.parser.get_race_num(url)
            results["race_name"] = self.parser.get_race_name(soup)

            # 2. 各種詳細項目（時刻、グレード、種別、距離、コース、天候、馬場）
            race_info_line1 = self.parser.get_race_info_line1(soup)
            results["start_time"] = self.parser.get_race_time(race_info_line1)
            
            grade = self.parser.get_race_grade(soup)
            if not grade:
                grade = self.parser.get_race_grade_in_title(results["race_name"])
            results["race_grade"] = grade

            r_types = self.parser.get_race_types(race_info_line1)
            results["race_type"] = r_types.get("race_type", "")
            results["race_distance"] = r_types.get("distance", "")
            results["race_course"] = r_types.get("course", "")

            if is_nar:
                # 地方競馬
                get_weather = getattr(self.parser, 'get_race_weather', self.parser.get_race_weahter)
                results["weather"] = get_weather(race_info_line1)
                results["condition"] = self.parser.get_race_condition(race_info_line1)
            else:
                # 中央競馬
                info_w_c = self.fetch_weather_condition_as_jra(soup)
                results["weather"] = info_w_c["weather"]
                results["condition"] = info_w_c["condition"]

            # 3. 開催情報（開催回、場所、日数、クラス、頭数）
            race_info_line2 = self.parser.get_race_info_line2(soup)
            held_info = self.parser.get_race_held_info(race_info_line2)
            results["race_held_times"] = held_info.get("race_kai", "")
            results["race_track"] = held_info.get("race_track", "")
            results["race_days"] = held_info.get("race_days", "")
            results["race_class"] = held_info.get("race_class", "")
            results["horses_num"] = held_info.get("horses_num", "")

        except Exception as e:
            logger.error(f'レース情報抽出中にエラーが発生しました: {e}')

        return results

    def fetch_race_info(self, url: str, html_contents: str) -> Dict[str, Any]:
        """
        出馬表または結果ページHTMLからレース情報を取得する
        """
        if not (self._is_shutuba_url(url) or self._is_result_url(url)):
            logger.error(f"invalid shutuba/result url: {url}")
            return {}

        soup = self.client.get_soup_as_html(html_contents)
        return self._parse_race_info(url, soup)

    def fetch_shutuba_horse_info(self, url: str, html_contents: str) -> List[Dict[str, Any]]:
        """
        出馬表HTMLから出走馬一覧情報を取得する
        """
        results = []
        if not self._is_shutuba_url(url):
            logger.error(f"invalid shutuba url: {url}")
            return results

        soup = self.client.get_soup_as_html(html_contents)

        try:
            is_nar = self.parser.is_nar(url)
            rows = soup.select(ShutubaSelector.HORSE_LIST)

            for row in rows:
                if not self.parser.is_horse_shutuba_data_line(row):
                    continue

                horse_url = self.parser.get_horse_url(row)
                jockey_url = self.parser.get_jockey_url(row)
                stable_url = self.parser.get_stable_url(row)

                data = {
                    "bracket_num": self.parser.get_bracket_num(row),
                    "horse_num": self.parser.get_horse_num(row),
                    "horse_name": self.parser.get_horse_name(row),
                    "horse_age": self.parser.get_horse_age(row, is_nar),
                    "weight_carried": self.parser.get_horse_weight_carried(row),
                    "jockey": self.parser.get_horse_jockey(row),
                    "jockey_id": self.parser.conv_jockey_id_from_url(jockey_url),
                    "stable": self.parser.get_stable(row),
                    "stable_id": self.parser.conv_stable_id_from_url(stable_url),
                    "horse_id": self.parser.conv_horse_id_from_url(horse_url),
                    "horse_url": horse_url,
                }
                results.append(data)
        
        except Exception as e:
            logger.info(f'出馬情報抽出中にエラーが発生しました: {e}')

        return results

    def fetch_race_result(self, url: str, html_contents: str) -> List[Dict[str, Any]]:
        """
        レース結果HTMLからレース基本情報・払戻情報・各馬結果を取得する
        """
        results = []
        if not self._is_result_url(url):
            logger.error(f"invalid result url: {url}")

        soup = self.client.get_soup_as_html(html_contents)
        is_nar = self.parser.is_nar(url)

        try:
            # 1. レース基本情報の取得（共通内部メソッドを利用して重複解消）
            race_info = self._parse_race_info(url, soup)
            results.append(race_info)

            # 2. 払い戻しテーブル情報の取得
            payouts_info = self.parser.parse_payouts(soup)
            results.append(payouts_info)

            # 3. 結果テーブルからの馬別データ取得
            rows = soup.select("tr")
            get_weight_info = getattr(
                self.parser, 
                'get_horse_weight_and_diff_as_result', 
                getattr(self.parser, 'get_horse_wieght_and_diff_as_result', None)
            )

            for row in rows:
                if not self.parser.is_horse_result_data_line(row):
                    continue

                horse_url = self.parser.get_horse_url(row)
                jockey_url = self.parser.get_jockey_url(row)
                stable_url = self.parser.get_stable_url(row)
                horse_num = self.parser.get_horse_num_as_result(row, is_nar)
                
                w_info = get_weight_info(row) if get_weight_info else {}
                horse_weight = w_info.get("horse_weight", "")
                weight_diff = w_info.get("weight_diff", "")

                passing_order = self.parser.get_horse_passing_order(row, soup, is_nar, horse_num)

                data = {
                    "rank": self.parser.get_horse_rank(row),
                    "bracket_num": self.parser.get_bracket_num_as_result(row),
                    "horse_num": horse_num,
                    "horse_name": self.parser.get_horse_name_as_result(row),
                    "horse_age": self.parser.get_horse_age_as_result(row),
                    "weight_carried": self.parser.get_horse_weight_carried_as_result(row),
                    "jockey": self.parser.get_horse_jockey_as_result(row),
                    "jockey_id": self.parser.conv_jockey_id_from_url(jockey_url),
                    "stable": self.parser.get_stable_as_result(row),
                    "stable_id": self.parser.conv_stable_id_from_url(stable_url),
                    "time": self.parser.get_finished_time(row),
                    "margin": self.parser.get_finished_margin(row),
                    "popularity": self.parser.get_popularity(row),
                    "odds": self.parser.get_odds(row),
                    "last3f": self.parser.get_last3f(row),
                    "passing_order": passing_order,
                    "horse_weight": horse_weight,
                    "weight_diff": weight_diff,
                    "horse_id": self.parser.conv_horse_id_from_url(horse_url),
                    "horse_url": horse_url,
                }
                results.append(data)

        except Exception as e:
            logger.info(f'レース結果抽出中にエラーが発生しました: {e}')

        return results

    def fetch_weather_condition_as_jra(self, soup: BeautifulSoup) -> Dict[str, str]:
        """
        JRA（中央競馬）ページ用の天候・馬場情報取得
        """
        race_data_div = soup.select_one("div.RaceData01")
        weather = "不明"
        condition = "不明"

        if race_data_div:
            weather_span = race_data_div.select_one("span[class*='Icon_Weather']")
            if weather_span:
                weather = weather_span.get("title") or weather_span.get("aria-label") or "不明"

            condition_span = race_data_div.select_one("span.Item04")
            if condition_span:
                condition = condition_span.text.strip()

        return {"weather": weather, "condition": condition}

    # タイポ互換用エイリアス
    fetch_weather_conditon_as_jra = fetch_weather_condition_as_jra

    def fetch_horse_profile(self, html_contents: str) -> Dict[str, Any]:
        """
        競走馬の個別プロフィール（基本情報、プロフィール詳細、血統）を取得
        """
        results = {}
        soup = self.client.get_soup_as_html(html_contents)

        try:
            h_head = self.parser.get_horse_profile_header(soup)
            prof_info = self.parser.get_horse_profile_base_info(h_head)
            prof_details = self.parser.get_horse_profile_details(soup)
            blood_info = self.parser.get_horse_blood_info(soup)
            results = results | prof_info | prof_details | blood_info
        except Exception as e:
            logger.info(f'馬プロフィール抽出中にエラーが発生しました: {e}')

        return results

    def fetch_horse_history(self, html_contents: str) -> List[Any]:
        """
        競走馬の過去戦績リストを取得
        """
        results = []
        soup = self.client.get_soup_as_html(html_contents)

        try:
            results = self.parser.get_horse_race_records_history(soup)
        except Exception as e:
            logger.info(f'馬戦績抽出中にエラーが発生しました: {e}')

        return results

    def _is_shutuba_url(self, url: str) -> bool:
        return 'shutuba' in url

    def _is_result_url(self, url: str) -> bool:
        return 'result' in url

    def _is_kaisai_url(self, url: str) -> bool:
        return 'kaisai' in url
