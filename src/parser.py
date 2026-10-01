from bs4 import BeautifulSoup
import json
import re
import requests
import urllib
from urllib.parse import parse_qs, urlparse

# ロガー設定
import logging
logger = logging.getLogger(__name__)

from src.constants.netkeibatag import ShutubaSelector, ResultSelector, GradeSelector, HorseDBSelector


class NkParser:

    def get_race_id(self, url: str) -> str:
        """レースIDの取得"""
        parsed_url = urlparse(url)
        query_params = parse_qs(parsed_url.query)
        race_id_list = query_params.get("race_id")

        if race_id_list:
            race_id = race_id_list[0]
        else:
            race_id = "202600000000"
        return race_id

    def get_race_num(self, url: str) -> str:
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

    def get_race_name(self, soup: BeautifulSoup) -> str:
        return (
            soup.select_one(ShutubaSelector.RACE_NAME).get_text(strip=True)
            if soup.select_one(ShutubaSelector.RACE_NAME)
            else "Unknown"
        )

    def get_race_grade(self, soup: BeautifulSoup) -> str:
        """グレードを取得する（存在する場合）"""
        for selector in GradeSelector.selectors():
            # `select_one` を使うことで、`.Icon_GradeType1` のようなCSSセレクタとして検索可能
            elem = soup.select_one(selector)
            if elem:
                # 見つかった場合は対応する日本語に変換して返す
                return GradeSelector.to_japanese(selector)
        return ""

    def get_race_grade_in_title(self, title: str) -> str:
        """
        レースタイトルからクラス名（C1, B1など）を抽出する
        - 括弧がある場合：括弧の中身を抽出する（例: 爽秋特別(C2) -> C2）
        - 括弧がない場合：タイトルをそのまま返す（例: B1 -> B1）
        """
        if not title:
            return ""
    
        # 半角または全角の括弧とその中身を探す正規表現
        # [（\(] で開き括弧、(.*?) で中の文字列、[）\)] で閉じ括弧にマッチ
        match = re.search(r'[（\(](.*?)[）\)]', title)
    
        if match:
            # 括弧の中身を返す（前後の空白を除去）
            return match.group(1).strip()
        else:
            # 括弧がない場合はタイトル全体を返す
            return title.strip()

    def get_race_info_line1(self, soup: BeautifulSoup) -> str:
        return (
            soup.select_one(ShutubaSelector.RACE_DATA).get_text(strip=True)
            if soup.select_one(ShutubaSelector.RACE_DATA)
            else "Unknown"
        )

    def get_race_info_line2(self, soup: BeautifulSoup) -> str:
        return (
            soup.select_one(ShutubaSelector.RACE_DATA02).get_text(strip=True)
            if soup.select_one(ShutubaSelector.RACE_DATA02)
            else "Unknown"
        )

    def get_race_time(self, info_text: str) -> str:
        r_match = re.search(r'(\d{1,2}:\d{2})', info_text)
        return r_match.group(0)

    def get_race_types(self, info_text: str) -> object:
        line_type_strs = info_text.split('/')
        r_match = re.search(r"^([芝ダ障])(\d+m)(\(.*\))$", line_type_strs[1])
        race_types = {}
        if r_match:
            race_types['race_type'] = r_match.group(1)
            race_types['distance'] = r_match.group(2)
            race_types['course'] = r_match.group(3)
        else:
            logger.info('パースに失敗しました')
        return race_types

    def conv_race_type(self, type_text: str) -> str:
        if "ダ" in type_text:
            return "ダート"
        elif "芝" in type_text:
            return "芝"
        elif "障" in type_text:
            return "障害"
        else:
            return "Unknown"
    
    def get_race_weahter(self, type_text: str) -> str:
        r_match = re.search(r"天候[:：]?\s*([^\s/]+)", type_text)
        return r_match.group(1)

    def get_race_condition(self, type_text: str) -> str:
        r_match = re.search(r"馬場[:：]?\s*([^\s/]+)", type_text)
        return r_match.group(1)

    def get_race_held_info(self, info_text: str) -> object:
        r_infos = {}

        pattern = r"^(\d+回)([^\d]+)(\d+日目)(.*?)(?=\d+頭)"
        r_match = re.search(pattern, info_text)

        if r_match:
            r_infos["race_kai"] = r_match.group(1)
            r_infos["race_track"] = r_match.group(2)
            r_infos["race_days"] = r_match.group(3)
            r_infos["race_class"] = r_match.group(4)
            tosu_match = re.search(r"(\d+頭)", info_text)
            r_infos["horses_num"] = tosu_match.group(1) if tosu_match else "不明"
        else:
            logger.info("パースに失敗しました")
        return r_infos

    def is_nar(self, url: str) -> bool:
        return "nar.netkeiba.com" in url

    def get_result_horse_num_selector(self, is_nar: bool) -> str:
        return ResultSelector.HORSE_NUM_NAR if is_nar else ResultSelector.HORSE_NUM

    def is_horse_result_data_line(self, row: object) -> bool:
        h_tag = row.select(ResultSelector.HORSE_NAME)
        r_tag = row.select(ResultSelector.RANK)
        return h_tag and r_tag

    def get_horse_url(self, row: object) -> str:
        a_elem = row.find("a")
        if a_elem and a_elem.has_attr("href"):
            horse_url = a_elem["href"]
        else:
            horse_url = ""
        return horse_url

    def conv_horse_id_from_url(self, url: str) -> str:
        return url.rstrip("/").split("/")[-1]

    def get_horse_num_as_result(self, row: object, is_nar: bool) -> str:
        selector = self.get_result_horse_num_selector(is_nar)
        return (
                row.select_one(selector).get_text(strip=True)
                if row.select_one(selector)
                else ""
            )

    def get_horse_wieght_and_diff_as_result(self, row: object) -> object:
        result = {}
        weight_text = (
                row.select_one(ResultSelector.HORSE_WEIGHT).get_text(strip=True)
                if row.select_one(ResultSelector.HORSE_WEIGHT)
                else ""
            )
        pattern = r"^(\d+)(?:\s*\(([+-]?\d+)\))?$"
        match = re.search(pattern, weight_text)
        if match:
            result["horse_weight"] = match.group(1)
            result["weight_diff"] = match.group(2) if match.group(2) is not None else "0"
        else:
            result["horse_weight"] = ""
            result["weight_diff"] = ""
        return result

    def get_horse_passing_order(self, row: object, soup: BeautifulSoup, is_nar: bool, horse_num: str) -> str:
        result = ""
        if not is_nar:
            # JRAはそのままタグから取得
            result =  (
                    row.select_one(ResultSelector.PASSING_ORDER).get_text(strip=True)
                    if row.select_one(ResultSelector.PASSING_ORDER)
                    else ""
            )
        else:
            # 地方馬は別の箇所記載なので関数で取得
            pass_map = self.get_horse_passing_orders_map(soup)
            result = pass_map.get(horse_num, "")
        return result

    def get_horse_rank(self, row: object) -> str:
        return (
            row.select_one(ResultSelector.RANK).get_text(strip=True)
            if row.select_one(ResultSelector.RANK)
            else ""
        )

    def get_bracket_num(self, row: object) -> str:
        return (
            row.select_one(ShutubaSelector.BRACKET_NUM).get_text(strip=True)
            if row.select_one(ShutubaSelector.BRACKET_NUM)
            else ""
        )

    def get_bracket_num_as_result(self, row: object) -> str:
        return (
            row.select_one(ResultSelector.BRACKET_NUM).get_text(strip=True)
            if row.select_one(ResultSelector.BRACKET_NUM)
            else ""
        )

    def get_horse_num(self, row: object) -> str:
        return (
            row.select_one(ShutubaSelector.HORSE_NUM).get_text(strip=True)
            if row.select_one(ShutubaSelector.HORSE_NUM)
            else ""
        )

    def get_horse_name(self, row: object) -> str:
        return (
            row.select_one(ShutubaSelector.HORSE_NAME).get_text(strip=True)
            if row.select_one(ShutubaSelector.HORSE_NAME)
            else ""
        )

    def get_horse_name_as_result(self, row: object) -> str:
        return (
            row.select_one(ResultSelector.HORSE_NAME).get_text(strip=True)
            if row.select_one(ResultSelector.HORSE_NAME)
            else ""
        )

    def get_horse_age(self, row: object, is_nar: bool) -> str:
        selector = ShutubaSelector.AGE_NAR if is_nar else ShutubaSelector.AGE
        return (
            row.select_one(selector).get_text(strip=True)
            if row.select_one(selector)
            else ""
        )

    def get_horse_age_as_result(self, row: object) -> str:
        return (
            row.select_one(ResultSelector.AGE).get_text(strip=True)
            if row.select_one(ResultSelector.AGE)
            else ""
        )

    def get_horse_weight_carried(self, row: object) -> str:
        return (
            row.select_one(ShutubaSelector.WEIGHT_CARRIED).get_text(strip=True)
            if row.select_one(ShutubaSelector.WEIGHT_CARRIED)
            else ""
        )

    def get_horse_weight_carried_as_result(self, row: object) -> str:
        return (
            row.select_one(ResultSelector.WEIGHT_CARRIED).get_text(strip=True)
            if row.select_one(ResultSelector.WEIGHT_CARRIED)
            else ""
        )

    def get_horse_jockey(self, row: object) -> str:
        return (
            row.select_one(ShutubaSelector.JOCKEY).get_text(strip=True)
            if row.select_one(ShutubaSelector.JOCKEY)
            else ""
        )

    def get_horse_jockey_as_result(self, row: object) -> str:
        return (
            row.select_one(ResultSelector.JOCKEY).get_text(strip=True)
            if row.select_one(ResultSelector.JOCKEY)
            else ""
        )

    def get_stable(self, row: object) -> str:
        return (
            row.select_one(ShutubaSelector.STABLE).get_text(strip=True)
            if row.select_one(ShutubaSelector.STABLE)
            else ""
        )

    def get_stable_as_result(self, row: object) -> str:
        return (
            row.select_one(ResultSelector.STABLE).get_text(strip=True)
            if row.select_one(ResultSelector.STABLE)
            else ""
        )

    def get_finished_time(self, row: object) -> str:
        return (
            row.select_one(ResultSelector.TIME).get_text(strip=True)
            if row.select_one(ResultSelector.TIME)
            else ""
        )

    def get_finished_margin(self, row: object) -> str:
        return (
            row.select_one(ResultSelector.MARGIN).get_text(strip=True)
            if row.select_one(ResultSelector.MARGIN)
            else ""
        )

    def get_popularity(self, row: object) -> str:
        return (
            row.select_one(ResultSelector.POPULARITY).get_text(strip=True)
            if row.select_one(ResultSelector.POPULARITY)
            else ""
        )

    def get_odds(self, row: object) -> str:
        return (
            row.select_one(ResultSelector.ODDS).get_text(strip=True)
            if row.select_one(ResultSelector.ODDS)
            else ""
        )

    def get_last3f(self, row: object) -> str:
        return (
            row.select_one(ResultSelector.LAST_3F).get_text(strip=True)
            if row.select_one(ResultSelector.LAST_3F)
            else ""
        )

    def get_horse_passing_orders_map(self, soup: BeautifulSoup) -> dict:
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

    def get_horse_profile_header(self, soup: BeautifulSoup) -> str:
        return soup.select_one(".horse_title").get_text(strip=True)

    def get_horse_profile_base_info(self, prof_text: str) -> object:
        results = {}
        pattern = r"^([^\x00-\x7F]+)([A-Za-z\s]+?)([牡牝セ]\d+歳)\s*(.+毛)$"
        match = re.search(pattern, prof_text)
        if match:
            results["horse_name"] = match.group(1)
            results["horse_eng_name"] = match.group(2)
            results["horse_age"] = match.group(3)
            results["horse_type"] = match.group(4)
        else:
            logger.error("馬ヘッダー情報のパースに失敗しました")
            results["horse_name"] = ""
            results["horse_eng_name"] = ""
            results["horse_age"] = ""
            results["horse_type"] = ""
        return results

    def get_horse_profile_details(self, soup: BeautifulSoup) -> object:
        results = {}
        prof_table = soup.find('table', class_='db_prof_table')
        rows = prof_table.find_all('tr')
        if not rows:
            logger.info("※馬データのプロフィール部分の解析に失敗したか、構造が異なります。")
            return {}
        for row in rows:
            th = row.find('th')
            td = row.find('td')
            # th と td が両方存在する場合のみ処理
            if th and td:
                # 項目名（例: "生年月日", "調教師"）から前後の空白や改行を削除
                key = th.get_text(strip=True)
        
                # 値（tdの中身）から不要なHTMLタグを除いたテキストを取得
                # .get_text(strip=True) を使うことで、<a>タグの中身なども綺麗にテキスト化されます
                value = td.get_text(strip=True)
                results[key] = value
        return results

    def get_horse_blood_info(self, soup: BeautifulSoup) -> object:
        results = {}
        blood_table = soup.find("table", class_="blood_table")
        if not blood_table:
            logger.info("※馬データの血統表部分の解析に失敗したか、構造が異なります。")
            return {}
        # 血統表内にあるすべての <a> タグを抽出する
        a_tags = blood_table.find_all("a")
        labels = [
            "sire",  # 父馬
            "sire_sire",  # 父父馬
            "sire_dam",  # 父母馬
            "dam",  # 母馬
            "dam_sire",  # 母父馬
            "dam_dam",  # 母母馬
        ]
        for i, a in enumerate(a_tags):
            if i < len(labels):
                key = labels[i]
                name = a.get_text(strip=True)
                url = a.get("href")

                # 馬名とURLをセットで格納
                results[key] = {"name": name, "url": url}
        return results

    def get_horse_race_records_history(self, soup: BeautifulSoup) -> list:
        results = []
        # 1. 「競走成績」のsummary属性を持つテーブルを特定する
        race_table = soup.find("table", class_="db_h_race_results")
        if not race_table:
            logger.info("※馬データの戦績部分の解析に失敗したか、構造が異なります。")
            return []
        # 2. テーブル内のすべての行（tr）を取得
        rows = race_table.find_all("tr")
        is_header = True
        for row in rows:
            # 3. 各行の中にあるセル（td または th）をすべて取得
            cells = row.find_all(["td", "th"])
            # 各セルのテキストを抽出し、前後の空白を除去してリスト化
            cell_data = [cell.get_text(strip=True) for cell in cells]
            # 上がり順位がある場合は追記
            last3f_num = ""
            i = 1
            for selector in [HorseDBSelector.LAST3F_1ST, HorseDBSelector.LAST3F_2ND, HorseDBSelector.LAST3F_3RD]:
                elm = row.find(selector)
                if elm:
                    last3f_num = f"{i}番"
                    break
            cell_data.append("上がり順位" if is_header else last3f_num)
            if is_header:
                is_header = False
            # データが存在する場合のみリストに追加（空行などを除外）
            if cell_data:
                results.append(cell_data)
        return results
