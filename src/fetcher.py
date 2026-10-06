from bs4 import BeautifulSoup
import json
import re
import requests
import urllib
from urllib.parse import parse_qs, urlparse

# ロガー設定
import logging
logger = logging.getLogger(__name__)

from src.constants.netkeibatag import ShutubaSelector, ResultSelector
from src.netkeiba_client import NkClientSoup
from src.parser import NkParser


class NkFetcher:
    def __init__(self):
        self.client = NkClientSoup()
        self.parser = NkParser()

    def fetch_kaisai_race_ids(self, url: str, html_contents: str) -> list:
        """
        レースの開催ページからレースIDを取得する
        """
        results = []
        if not self._is_kaisai_url(url):
            return results

        soup = self.client.get_soup_as_html(html_contents)

        try:
            # 開催ID取得
            # 1. aタグのhref属性をすべてチェック
            # 地方(nar)と中央(race)両方のURLパターンに対応する正規表現
            # 例: /race/result.html?race_id=202654032801 や /race/shutuba.html?race_id=...
            pattern = re.compile(r'race_id=(\d+)')
            links = soup.find_all('a', href=pattern)
            for link in links:
                href = link.get('href')
                match = pattern.search(href)
                if match:
                    race_id = match.group(1)
                    results.append(race_id)
        except Exception as e:
            logger.info(f'データ抽出中にエラーが発生しました: {e}')
        # 2. 重複を除去し、昇順に並べ替えて返す
        return sorted(list(set(results)))

    def fetch_race_info(self, url: str, html_contents: str) -> dict:
        """
        レース情報を取得
        """
        results = {}
        if not self._is_shutuba_url(url):
            logger.error(f"invalid shutuba url: {url}")
            return results

        soup = self.client.get_soup_as_html(html_contents)

        try:
            # 1. レース基本情報取得
            # レースID取得
            results["race_id"] = self.parser.get_race_id(url)
            # レース番号取得
            results["race_num"] = self.parser.get_race_num(url)
            # レース名取得
            results["race_name"] = self.parser.get_race_name(soup)

            # 2. 各種項目取得
            race_info_line1 = self.parser.get_race_info_line1(soup)
            # レース時刻
            results["start_time"] = self.parser.get_race_time(race_info_line1)
            # レースグレード
            grade = self.parser.get_race_grade(soup)
            if not grade:
                grade = self.parser.get_race_grade_in_title(results["race_name"])
            results["race_grade"] = grade
            # レース種別
            r_types = self.parser.get_race_types(race_info_line1)
            results["race_type"] = r_types["race_type"]
            # 距離
            results["race_distance"] = r_types["distance"]
            # コース
            results["race_course"] = r_types["course"]
            # 天候
            results["weather"] = self.parser.get_race_weahter(race_info_line1)
            # 馬場
            results["condition"] = self.parser.get_race_condition(race_info_line1)

            # 3. 開催情報
            race_info_line2 = self.parser.get_race_info_line2(soup)
            held_info = self.parser.get_race_held_info(race_info_line2)
            # 開催回数
            results["race_held_times"] = held_info["race_kai"]
            # 開催場
            results["race_track"] = held_info["race_track"]
            # 開催日数
            results["race_days"] = held_info["race_days"]
            # 出走クラス
            results["race_class"] = held_info["race_class"]
            # 出走頭数
            results["horses_num"] = held_info["horses_num"]
        except Exception as e:
            logger.info(f'データ抽出中にエラーが発生しました: {e}')

        return results

    def fetch_shutuba_horse_info(self, url: str, html_contents: str) -> list[dict]:
        """
        出馬情報を取得
        """
        results = []
        if not self._is_shutuba_url(url):
            logger.error(f"invalid result url: {url}")
            return results

        soup = self.client.get_soup_as_html(html_contents)

        try:
            # 地方競馬(NAR)判定と年齢セレクタの切り替え
            is_nar = self.parser.is_nar(url)
            # 出馬表テーブルの解析
            rows = soup.select(ShutubaSelector.HORSE_LIST)
            # データの抽出
            for row in rows[0:-2]:
                # 馬URL取得
                horse_url = self.parser.get_horse_url(row)
                data = {
                    "bracket_num": self.parser.get_bracket_num(row),
                    "horse_num": self.parser.get_horse_num(row),
                    "horse_name": self.parser.get_horse_name(row),
                    "horse_age": self.parser.get_horse_age(row, is_nar),
                    "weight_carried": self.parser.get_horse_weight_carried(row),
                    "jockey": self.parser.get_horse_jockey(row),
                    "stable": self.parser.get_stable(row),
                    "horse_id": self.parser.conv_horse_id_from_url(horse_url),
                    "horse_url": horse_url,
                }
                results.append(data)
        
        except Exception as e:
            logger.info(f'データ抽出中にエラーが発生しました: {e}')
        return results

    def fetch_race_result(self, url: str, html_contents: str) -> list[dict]:
        """
        レース結果を取得
        TODO: 払い戻しのテーブル情報を取得するように追加修正
        """
        results = []
        if not self._is_result_url(url):
            logger.error(f"invalid result url: {url}")
        
        soup = self.client.get_soup_as_html(html_contents)

        try:
            # 地方競馬(NAR)判定と年齢セレクタの切り替え
            is_nar = self.parser.is_nar(url)
            # 結果表テーブルの解析
            rows = soup.select("tr")
            for row in rows:
                # 馬名リンクがない場合は目的行ではないのでスキップ
                if not self.parser.is_horse_result_data_line(row):
                    continue
                # HorseURL取得
                horse_url = self.parser.get_horse_url(row)
                # 馬番取得
                horse_num = self.parser.get_horse_num_as_result(row, is_nar)
                # 馬体重と差の取得
                w_info = self.parser.get_horse_wieght_and_diff_as_result(row)
                horse_weight = w_info["horse_weight"]
                weight_diff = w_info["weight_diff"]
                # 通貨順の取得
                passing_order = self.parser.get_horse_passing_order(row, soup, is_nar, horse_num)
                # 馬別の結果データの取得と作成
                data = {
                    "rank": self.parser.get_horse_rank(row),
                    "bracket_num": self.parser.get_bracket_num_as_result(row),
                    "horse_num": horse_num,
                    "horse_name": self.parser.get_horse_name_as_result(row),
                    "horse_age": self.parser.get_horse_age_as_result(row),
                    "weight_carried": self.parser.get_horse_weight_carried_as_result(row),
                    "jockey": self.parser.get_horse_jockey_as_result(row),
                    "stable": self.parser.get_stable_as_result(row),
                    "time": self.parser.get_finished_time(row),
                    "margin": self.parser.get_finished_margin(row),
                    "popularity": self.parser.get_popularity(row),
                    "odds": self.parser.get_odds(row),
                    "last3f": self.parser.get_last3f(row),
                    "passing_order":passing_order,
                    "horse_weight": horse_weight,
                    "weight_diff": weight_diff,
                    "horse_id": self.parser.conv_horse_id_from_url(horse_url),
                    "horse_url": horse_url,
                }
                results.append(data)

        except Exception as e:
            logger.info(f'データ抽出中にエラーが発生しました: {e}')
        return results

    def fetch_horse_profile(self, html_contents: str) -> dict:
        """
        個別の馬の基本情報、プロフィール、血統を取得
        """
        results = {}

        soup = self.client.get_soup_as_html(html_contents)

        try:
            # ヘッダー部分の情報取得
            h_head = self.parser.get_horse_profile_header(soup)
            prof_info = self.parser.get_horse_profile_base_info(h_head)
            # プロフィール部分の情報取得
            prof_details = self.parser.get_horse_profile_details(soup)
            # 血統表の取得
            blood_info = self.parser.get_horse_blood_info(soup)
            # データ結合
            results = results | prof_info | prof_details | blood_info
        except Exception as e:
            logger.info(f'データ抽出中にエラーが発生しました: {e}')

        return results

    def fetch_horse_history(self, html_contents: str) -> list[dict]:
        """
        個別の馬の過去レース戦績のリストを取得
        """
        results = []

        soup = self.client.get_soup_as_html(html_contents)

        try:
            results = self.parser.get_horse_race_records_history(soup)
        except Exception as e:
            logger.info(f'データ抽出中にエラーが発生しました: {e}')
        return results

    def _is_shutuba_url(self, url: str) -> bool:
        return 'shutuba' in url

    def _is_result_url(self, url: str) -> bool:
        return 'result' in url

    def _is_kaisai_url(self, url: str) -> bool:
        return 'kaisai' in url
