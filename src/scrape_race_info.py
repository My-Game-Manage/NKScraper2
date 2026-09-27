from bs4 import BeautifulSoup
import json
import re
import requests
import urllib
from urllib.parse import parse_qs, urlparse

# ロガー設定
import logging
logger = logging.getLogger(__name__)

from src.constants.netkeibatag import ShutubaSelector
from src.netkeiba_client import NkClientSoup


class ScraperRaceInfo:
    def __init__(self):
        self.client = NkClientSoup()

    def get_shutuba_race_info(self, url: str) -> object:
        soup = self.client.get_soup(url)

        race_data = {}

        try:
            # レースIDの取得
            race_data["race_id"] = self._get_race_id(url)
            # レース番号取得
            race_data["race_num"] = self._get_race_num(url)
            # レース名取得
            race_data["race_name"] = self._get_race_name(soup)
            # 各種レース項目
            # 各行取得
            race_data_line1 = self._get_race_data1(soup)
            race_data_line2 = self._get_race_data2(soup)
            r1 = race_data_line1.split('/')
            r2 = race_data_line2.split('/')
            print(r1)
            print(r2)

            # レース時刻
            race_data["start_time"] = self._get_race_time(race_data_line1)
            # レース種別
            r_types = self._get_race_types(race_data_line1)
            race_data["race_type"] = self._conv_race_type(r_types['race_type'])
            race_data["distance"] = r_types['distance']
            race_data["course"] = r_types["course"]
            race_data["weather"] = self._get_race_weather(race_data_line1)
            race_data["condition"] = self._get_race_condition(race_data_line1)
            # レース情報詳細
            r_infos = self._get_race_info_details(race_data_line2)
            race_data["race_kai"] = r_infos["race_kai"]
            race_data["race_course"] = r_infos["race_course"]
            race_data["race_days"] = r_infos["race_days"]
            race_data["race_class"] = r_infos["race_class"]
            race_data["horses_num"] = r_infos["horses_num"]
        except Exception as e:
            logger.info(f'データ抽出中にエラーが発生しました: {e}')
        return race_data

    def get_shutuba_horse_info(self, url: str) -> list:
        """出馬表から出馬情報の取得"""
        soup = self.client.get_soup(url)
        
        # 地方競馬(NAR)判定と年齢セレクタの切り替え[cite: 1]
        is_nar = "nar.netkeiba.com" in url
        age_selector = ShutubaSelector.AGE_NAR if is_nar else ShutubaSelector.AGE

        # 出馬表テーブルの解析
        rows = soup.select(ShutubaSelector.HORSE_LIST)
        if not rows:
            logger.info("※出馬表テーブルの解析に失敗したか、構造が異なります。")
            return []

        # データの抽出
        results = []
        for row in rows[0:-2]:
            a_elem = row.find("a")
            if a_elem and a_elem.has_attr("href"):
                horse_url = a_elem["href"]
            else:
                horse_url = ""
            data = {
                "bracket_num": (
                    row.select_one(ShutubaSelector.BRACKET_NUM).get_text(strip=True)
                    if row.select_one(ShutubaSelector.BRACKET_NUM)
                    else ""
                ),
                "horse_num": (
                    row.select_one(ShutubaSelector.HORSE_NUM).get_text(strip=True)
                    if row.select_one(ShutubaSelector.HORSE_NUM)
                    else ""
                ),
                "horse_name": (
                    row.select_one(ShutubaSelector.HORSE_NAME).get_text(strip=True)
                    if row.select_one(ShutubaSelector.HORSE_NAME)
                    else ""
                ),
                "horse_age": (
                    row.select_one(age_selector).get_text(strip=True)
                    if row.select_one(age_selector)
                    else ""
                ),
                "weight_carried": (
                    row.select_one(ShutubaSelector.WEIGHT_CARRIED).get_text(strip=True)
                    if row.select_one(ShutubaSelector.WEIGHT_CARRIED)
                    else ""
                ),
                "jockey": (
                    row.select_one(ShutubaSelector.JOCKEY).get_text(strip=True)
                    if row.select_one(ShutubaSelector.JOCKEY)
                    else ""
                ),
                "stable": (
                    row.select_one(ShutubaSelector.STABLE).get_text(strip=True)
                    if row.select_one(ShutubaSelector.STABLE)
                    else ""
                ),
                "horse_id": horse_url.split("/")[-1],
                "horse_url": horse_url,
            }
            results.append(data)
        return results

    def _get_race_id(self, url: str) -> str:
        """レースIDの取得"""
        parsed_url = urlparse(url)
        query_params = parse_qs(parsed_url.query)
        race_id_list = query_params.get("race_id")

        if race_id_list:
            race_id = race_id_list[0]
        else:
            race_id = "202600000000"
        return race_id

    def _get_race_num(self, url: str) -> str:
        """レース番号の取得"""
        parsed_url = urlparse(url)
        query_params = parse_qs(parsed_url.query)
        race_id_list = query_params.get("race_id")

        if race_id_list:
            race_id = race_id_list[0]
            race_num = race_id[-2:]  # 例: 12R
        else:
            race_num = "00"
        return race_num

    def _get_race_name(self, soup: BeautifulSoup) -> str:
        race_name = (
            soup.select_one(ShutubaSelector.RACE_NAME).get_text(strip=True)
            if soup.select_one(ShutubaSelector.RACE_NAME)
            else "Unknown"
        )
        return race_name

    def _get_race_data1(self, soup :BeautifulSoup) -> object:
        race_data1 = (
            soup.select_one(ShutubaSelector.RACE_DATA).get_text(strip=True)
            if soup.select_one(ShutubaSelector.RACE_DATA)
            else "Unknown"
        )
        return race_data1

    def _get_race_data2(self, soup :BeautifulSoup) -> object:
        race_data2 = (
            soup.select_one(ShutubaSelector.RACE_DATA02).get_text(strip=True)
            if soup.select_one(ShutubaSelector.RACE_DATA02)
            else "Unknown"
        )
        return race_data2

    def _get_race_time(self, line_text: str) -> str:
        r_match = re.search(r'(\d{1,2}:\d{2})', line_text)
        return r_match.group(0)

    def _get_race_types(self, line_text: str) -> str:
        line_type_strs = line_text.split('/')
        r_match = re.search(r"^([芝ダ障])(\d+m)(\(.*\))$", line_type_strs[1])
        race_types = {}
        if r_match:
            race_types['race_type'] = r_match.group(1)
            race_types['distance'] = r_match.group(2)
            race_types['course'] = r_match.group(3)
        else:
            logger.info('パースに失敗しました')
        return race_types

    def _conv_race_type(self, type_text: str) -> str:
        if "ダ" in type_text:
            return "ダート"
        elif "芝" in type_text:
            return "芝"
        elif "障" in type_text:
            return "障害"
        else:
            return "Unknown"

    def _get_race_weather(self, line_text: str) -> str:
        r_match = re.search(r"天候[:：]?\s*([^\s/]+)", line_text)
        return r_match.group(1)

    def _get_race_condition(self, line_text: str) -> str:
        r_match = re.search(r"馬場[:：]?\s*([^\s/]+)", line_text)
        return r_match.group(1)

    def _get_race_info_details(self, line_text: str) -> object:
        r_infos = {}

        pattern = r"^(\d+回)([^\d]+)(\d+日目)(.*?)(?=\d+頭)"
        r_match = re.search(pattern, line_text)

        if r_match:
            r_infos["race_kai"] = r_match.group(1)
            r_infos["race_course"] = r_match.group(2)
            r_infos["race_days"] = r_match.group(3)
            r_infos["race_class"] = r_match.group(4)
            tosu_match = re.search(r"(\d+頭)", line_text)
            r_infos["horses_num"] = tosu_match.group(1) if tosu_match else "不明"
        else:
            logger.info("パースに失敗しました")
        return r_infos