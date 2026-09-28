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


class ScraperRaceInfo:
    def __init__(self):
        self.client = NkClientSoup()

    def get_shutuba_race_info(self, url: str) -> object:
        race_data = {}

        if not self._is_shutuba_page(url):
            logger.error(f"invalid shutuba url: {url}")
            return race_data
        
        soup = self.client.get_soup(url)

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

    def get_race_result(self, url: str) -> list:
        """レース結果の取得"""
        results = []

        if not self._is_result_page(url):
            logger.error(f"Invalid result page url: {url}")
            return results
        
        soup = self.client.get_soup(url)

        try:
            # 地方競馬(NAR)判定と年齢セレクタの切り替え
            is_nar = "nar.netkeiba.com" in url
            horse_num_selector = "td[class='Num Waku']" if is_nar else "td[class='Num Txt_C']"

            # 結果表テーブルの解析
            rows = soup.select("tr")
            for row in rows:
                # 馬名リンクがない場合は目的行ではないのでスキップ
                h_tag = row.select(ResultSelector.HORSE_NAME)
                r_tag = row.select(ResultSelector.RANK)
                if not h_tag or not r_tag:
                    continue
                # HorseID と URL取得
                a_elem = row.find("a")
                if a_elem and a_elem.has_attr("href"):
                    horse_url = a_elem["href"]
                else:
                    horse_url = ""
                # 馬番取得
                horse_num = (
                    row.select_one(horse_num_selector).get_text(strip=True)
                    if row.select_one(horse_num_selector)
                    else ""
                )
                # 馬体重と差の取得
                weight_text = (
                    row.select_one(ResultSelector.HORSE_WEIGHT).get_text(strip=True)
                    if row.select_one(ResultSelector.HORSE_WEIGHT)
                    else ""
                )
                weight_pattern = r"^(\d+)(?:\s*\(([+-]?\d+)\))?$"
                weight_match = re.search(weight_pattern, weight_text)
                if weight_match:
                    horse_weight = weight_match.group(1)
                    weight_diff = weight_match.group(2) if weight_match.group(2) is not None else "0"
                else:
                    horse_weight = ""
                    weight_diff = ""
                # 通貨順の取得
                if not is_nar:
                    # JRAはそのままタグから取得
                    passing_order =  (
                        row.select_one(ResultSelector.PASSING_ORDER).get_text(strip=True)
                        if row.select_one(ResultSelector.PASSING_ORDER)
                        else ""
                    )
                else:
                    # 地方馬は別の箇所記載なので関数で取得
                    pass_map = self._get_horse_passing_orders_map(soup)
                    passing_order = pass_map.get(horse_num, "")
                data = {
                    "rank": (
                        row.select_one(ResultSelector.RANK).get_text(strip=True)
                        if row.select_one(ResultSelector.RANK)
                        else ""
                    ),
                    "bracket_num": (
                        row.select_one(ResultSelector.BRACKET_NUM).get_text(strip=True)
                        if row.select_one(ResultSelector.BRACKET_NUM)
                        else ""
                    ),
                    "horse_num": horse_num,
                    "horse_name": (
                        row.select_one(ResultSelector.HORSE_NAME).get_text(strip=True)
                        if row.select_one(ResultSelector.HORSE_NAME)
                        else ""
                    ),
                    "horse_age": (
                        row.select_one(ResultSelector.AGE).get_text(strip=True)
                        if row.select_one(ResultSelector.AGE)
                        else ""
                    ),
                    "weight_carried": (
                        row.select_one(ResultSelector.WEIGHT_CARRIED).get_text(strip=True)
                        if row.select_one(ResultSelector.WEIGHT_CARRIED)
                        else ""
                    ),
                    "jockey": (
                        row.select_one(ResultSelector.JOCKEY).get_text(strip=True)
                        if row.select_one(ResultSelector.JOCKEY)
                        else ""
                    ),
                    "stable": (
                        row.select_one(ResultSelector.STABLE).get_text(strip=True)
                        if row.select_one(ResultSelector.STABLE)
                        else ""
                    ),
                    "time": (
                        row.select_one(ResultSelector.TIME).get_text(strip=True)
                        if row.select_one(ResultSelector.TIME)
                        else ""
                    ),
                    "margin": (
                        row.select_one(ResultSelector.MARGIN).get_text(strip=True)
                        if row.select_one(ResultSelector.MARGIN)
                        else ""
                    ),
                    "popularity": (
                        row.select_one(ResultSelector.POPULARITY).get_text(strip=True)
                        if row.select_one(ResultSelector.POPULARITY)
                        else ""
                    ),
                    "odds": (
                        row.select_one(ResultSelector.ODDS).get_text(strip=True)
                        if row.select_one(ResultSelector.ODDS)
                        else ""
                    ),
                    "last3f": (
                        row.select_one(ResultSelector.LAST_3F).get_text(strip=True)
                        if row.select_one(ResultSelector.LAST_3F)
                        else ""
                    ),
                    "passing_order":passing_order,
                    "horse_weight": horse_weight,
                    "weight_diff": weight_diff,
                    "horse_id": self._conv_horseid_from_url(horse_url),
                    "horse_url": horse_url,
                }
                results.append(data)
        except Exception as e:
            logger.info(f'データ抽出中にエラーが発生しました: {e}')
        return results

    def get_shutuba_horse_info(self, url: str) -> list:
        """出馬表から出馬情報の取得"""
        soup = self.client.get_soup(url)
        results = []

        try:        
            # 地方競馬(NAR)判定と年齢セレクタの切り替え
            is_nar = "nar.netkeiba.com" in url
            age_selector = ShutubaSelector.AGE_NAR if is_nar else ShutubaSelector.AGE

            # 出馬表テーブルの解析
            rows = soup.select(ShutubaSelector.HORSE_LIST)
            if not rows:
                logger.info("※出馬表テーブルの解析に失敗したか、構造が異なります。")
                return []

            # データの抽出
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
                    "horse_id": self._conv_horseid_from_url(horse_url),
                    "horse_url": horse_url,
                }
                results.append(data)
        except Exception as e:
            logger.info(f'データ抽出中にエラーが発生しました: {e}')
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

    def _is_shutuba_page(self, url: str) -> bool:
        return "shutuba" in url

    def _is_result_page(self, url: str) -> bool:
        return 'result.html' in url

    def _conv_horseid_from_url(self, url: str) -> str:
        return url.rstrip("/").split("/")[-1]
    
    def _get_horse_passing_orders_map(self, soup: BeautifulSoup) -> dict:
        """
        地方競馬のサイトは通過順が異なるので、こちらを使う
        """
        pass_map = {}
        try:
            # 指定されたクラスの行をすべて取得
            corner_rows = soup.select(".RaceCommon_Table.Corner_Num tr")
            temp_pass_data = {}
            logger.debug(f"通過順： {corner_rows}")

            for row in corner_rows:
                th = row.find('th')
                td = row.find('td')
                th_text = th.get_text(strip=True) if td else ""
                td_text = td.get_text(strip=True) if td else ""
                if not th or not td:
                    continue
                
                # 1. 「コーナー」という文字で分割して、右側の馬番リストを取得
                if 'コーナー' in th_text:
                    # 右側だけを取り出し、改行や余計な空白をすべて削除＞これ不要？
                    order_raw = th_text

                    # 2. カッコ「()」をカンマ「,」に置換して、すべてカンマ区切りのリストにする
                    order_processed = td_text.replace('(', ',').replace(')', ',')
                    # カンマで分割し、空要素を除去して純粋な馬番だけのリストにする
                    order_list = [h.strip() for h in order_processed.split(',') if h.strip()]

                    # 3. リストの並び順をそのまま「通過順位」として記録
                    for rank_idx, h_num in enumerate(order_list):
                        # 数字以外の記号があれば除去（馬番のみ抽出）
                        h_num_clean = re.sub(r'\D', '', h_num)
                        if h_num_clean:
                            if h_num_clean not in temp_pass_data:
                                temp_pass_data[h_num_clean] = []
                            # その馬のこのコーナーでの位置(1番目なら"1")を記録
                            temp_pass_data[h_num_clean].append(str(rank_idx + 1))

            # 4. 全コーナー分を「1-1-2-2」形式の文字列に変換
            for h_num, ranks in temp_pass_data.items():
                pass_map[h_num] = "-".join(ranks)
                logger.debug(f"pass_map: {pass_map}")
            return pass_map
        except Exception as e:
            logger.warning(f"コーナー通過順の解析エラー: {e}")
            return {}