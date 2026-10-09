import os
from datetime import datetime, timedelta, timezone
import random
import time
import pandas as pd

# ロガー設定
import logging
logger = logging.getLogger(__name__)

from src.fetcher import NkFetcher
from src.writer import NkWriter
from src.formatter import NkFormatter
from src.analyzer import NkAnalyzer
from src.constants.netkeibatag import JYO_NAME_MAP, EXCLUDE_COURSES, JRA_MAX_COURSE_CODE
from src.all_html_dump import fetch_js_html

DEFAULT_BASE_DIR = "data"

SELECTOR_HORSE_DB = "table.db_h_race_results"
SELECTOR_KAISAI_HP = ".RaceList_Body"
SELECTOR_SHUTUBA_HP = ".RaceName"
SELECTOR_RESULT_HP = ".RaceTable01"

class NkScraper:
    def __init__(self, headless: bool = True, base_dir: str = DEFAULT_BASE_DIR):
        self.fetcher = NkFetcher()
        self.writer = NkWriter()
        self.formatter = NkFormatter()
        self.analyzer = NkAnalyzer()

        # 基本設定
        self.base_dir = 'data'
        # ディレクトリがなければ作成
        os.makedirs(self.base_dir, exist_ok=True)

    def scraping_races(self, input_date=None, course_filter=None, race_num_filter=None, is_test: bool=False):
        """
        レースデータのスクレイピング
        """
        logger.info("スクレイピングを開始します")

        # 1. 目的のレースIDを取得する
        # 取得日付を決定
        target_date = self.determinate_target_date(input_date)
        target_race_ids = self.get_target_race_ids(target_date, course_filter, race_num_filter)

        logger.info(f"target race ids: {target_race_ids}")

        # 2. レースID毎に処理していく
        for race_id in target_race_ids:
            logger.info(f"race_id: {race_id} の解析開始")
            # レース情報
            race_info = self.fetch_race_info_by_id(race_id)
            # データの変換
            markdown = self.conv_race_shutuba_data_to_markdown(target_date, race_info)
            # データの保存
            filename = self.formatter.get_filename_from_race_info(race_info)
            self.writer.save_as_markdown(target_date, filename, markdown, is_test)
            # 次までのアイドルタイム
            self.wait_idle_time()

    def scraping_results(self, input_date=None, course_filter=None, race_num_filter=None, is_test: bool=False):
        """
        レース結果のスクレイピング
        """
        logger.info("結果のスクレイピングを開始します")
        logger.info(f"date: {input_date}")

        # 1. 目的のレースIDを取得する
        # 取得日付を決定（基本は無指定で前日分）
        target_date = self.determinate_target_date(input_date) if input_date else self.get_yesterday_date()
        target_race_ids = self.get_target_race_ids(target_date, course_filter, race_num_filter)

        logger.info(f"target race ids: {target_race_ids}")

        # 2. レースID毎に処理していく
        for race_id in target_race_ids:
            # レース結果
            result_info = self.fetch_race_result_by_id(race_id)
            # データの変換
            markdown = self.conv_race_result_data_to_markdown(race_id, result_info)
            # データの保存
            race_track = self.get_jyo_name(race_id)
            race_num = self.get_race_num_from_id(race_id)
            filename = self.formatter.get_filename_from_race_result(race_id, race_track, race_num)
            self.writer.save_as_markdown(target_date, filename, markdown, is_test)
            # 次までのアイドルタイム
            self.wait_idle_time()

    def fetch_race_info_by_id(self, race_id: str) -> object:
        """
        レース出馬情報（レース情報、出馬情報、各馬のプロフィール、各馬の戦績リスト）の取得
        """
        results = {}

        is_nar = self.is_nar_race_id(race_id)

        # レースIDからURL作成
        target_url = self.race_url_from_race_id(race_id, is_nar)

        # html取得
        html_contents = fetch_js_html(target_url, SELECTOR_SHUTUBA_HP)

        # レース情報取得
        logger.info("fetch race_info")
        results["race_info"] = self.fetcher.fetch_race_info(target_url, html_contents)
        # 出走馬情報取得
        logger.info("fetch shutuba horses")
        results["shutuba_horses"] = self.fetcher.fetch_shutuba_horse_info(target_url, html_contents)
        # リスト内包表記を使って horse_url だけを抽出する
        #horse_urls = [horse["horse_url"] for horse in shutuba_horses_list]
        horses_data = []
        logger.info("fetch horses data")
        for horse_row in results["shutuba_horses"]:
            data = {}
            horse_id = horse_row["horse_id"]
            horse_url = horse_row["horse_url"]
            # 馬のページ取得
            horse_html = fetch_js_html(horse_url, SELECTOR_HORSE_DB)
            # 馬のプロフィール取得
            data["horse_id"] = horse_id
            data["horse_prof"] = self.fetcher.fetch_horse_profile(horse_html)
            history = self.fetcher.fetch_horse_history(horse_html)
            data["horse_history"] = history
            # 馬のレースデータ分析
            if history:
                # タイム
                analyzed_data = self.analyzer.analyze_horse_history(history)
                data["analyzed_data"] = analyzed_data
            else:
                data["analyzed_data"] = "- 戦績データがない、または新馬です。\n\n"
            horses_data.append(data)
            # 次の取得までのアイドルタイム
            self.wait_idle_time()
        results["horse_infos"] = horses_data
        return results

    def fetch_race_result_by_id(self, race_id: str) -> list:
        is_nar = self.is_nar_race_id(race_id)

        # レースIDからURL作成
        target_url = self.race_result_url_from_race_id(race_id, is_nar)

        # html取得
        html_contents = fetch_js_html(target_url, SELECTOR_RESULT_HP)

        # レース結果情報取得
        result = self.fetcher.fetch_race_result(target_url, html_contents)

        return result

    def conv_race_shutuba_data_to_markdown(self, target_date: str, race_info: list[dict]) -> str:
        """レース出馬情報等をmarkdownに変換する"""
        results = []

        # レース基本情報
        race_base_info = self.formatter.conv_race_info_to_markdown(target_date, race_info["race_info"])
        results.append(race_base_info + "\n\n")
        # 出馬情報
        shutuba_info = self.formatter.conv_shutuba_to_markdown(race_info["shutuba_horses"])
        results.append(shutuba_info + "\n\n")
        # 馬のプロフィールと戦績
        horse_infos = race_info["horse_infos"]
        horse_ids = []
        profiles = []
        histories = []
        analyzed = []
        for h_info in horse_infos:
            h_id = h_info["horse_id"]
            h_prof = h_info["horse_prof"]
            h_hist = h_info["horse_history"]
            h_anal = h_info["analyzed_data"]
            # 馬のプロフィール
            prof = self.formatter.conv_horse_profile_to_markdown(h_prof)
            history = self.formatter.conv_history_to_markdown(h_hist)
            horse_ids.append(f"### 馬ID：{h_id}" + "\n\n")
            profiles.append(prof + "\n\n")
            histories.append(history + "\n\n")
            analyzed.append(h_anal + "\n\n")
        results.append("## 3. 出走馬プロフィール\n\n")
        for i, prof in enumerate(profiles):
            results.append(horse_ids[i])
            results.append(prof)
        results.append("## 4. 各馬データ分析\n\n")
        for i, anal in enumerate(analyzed):
            results.append(horse_ids[i])
            results.append(anal)
        results.append("## 5. 各馬の過去戦績\n\n")
        for i, hist in enumerate(histories):
            results.append(horse_ids[i])
            results.append(hist)
        
        # データ結合
        return "".join(results)

    def conv_race_result_data_to_markdown(self, race_id: str, race_result: list[dict]) -> str:
        """レース結果をmarkdownに変換する"""
        results = []

        jyo_name = self.get_jyo_name(race_id)
        race_num = self.get_race_num_from_id(race_id)
        # タイトル行
        results.append(f"# レースID：{race_id}\n\n")
        results.append(f"## レース：{jyo_name} - {race_num}R\n\n")
        # 結果ページ
        race_result_md = self.formatter.conv_race_result_to_markdown(race_result)
        results.append(race_result_md + "\n\n")

        # データ結合
        return "".join(results)

    def get_target_race_ids(self, date, course_filter, race_num_filter) -> list:
        """
        目的のレースIDリストを返す
        """
        results = []
        # 地方競馬、中央競馬、両方を回す
        for is_nar in [True, False]:
            results += self.get_kaisai_ids(date, is_nar)

        # ばんえい、不明は除外する
        results = self.exclued_race_ids(results)

        logger.info(f"check taget ids before: {results}")

        # 指定がある場合はフィルタリングする
        if results and (course_filter or race_num_filter):
            filtered_ids = self.filtered_race_ids(results, course_filter, race_num_filter)
            return filtered_ids
        else:
            return results

    def get_kaisai_ids(self, date: str, is_nar: bool):
        """
        指定日の開催IDリスト（10桁）を取得
        """
        top_url = self.get_top_page_url(date, is_nar)

        # ページをDUMPする
        html_contents = fetch_js_html(top_url, SELECTOR_KAISAI_HP)

        return self.fetcher.fetch_kaisai_race_ids(top_url, html_contents)

    def filtered_race_ids(self, kaisai_ids: list, course_codes: list, race_nums: list):
        """
        フィルタリングしたレースIDを返す
        """
        results = kaisai_ids
        # 開催会場でフィルタリング
        if course_codes:
            results = self.filter_race_ids_by_course(results, course_codes)
        # レース番号でフィルタリング
        if race_nums:
            results = self.filter_race_ids_by_number(results, race_nums)
        return results

    def get_top_page_url(self, target_date: str, is_nar: bool = True) -> str:
        """日付から開催トップページのURLを生成する"""
        domain = self.netkeiba_domain_from(is_nar)
        return f"https://{domain}.netkeiba.com/top/race_list.html?kaisai_date={target_date}"

    def netkeiba_domain_from(self, is_nar: bool) -> str:
        return 'nar' if is_nar else 'race'

    def determinate_target_date(self, input_date: str) -> str:
        """
        取得する日付の決定
        - 指定がある場合>>指定日を返す
        - 指定がない場合>>nowの日付を返す
        """
        return self.normalize_date_format(input_date if input_date else self.get_today_jst())

    def get_today_jst(self) -> str:
        """現在の日本時間を 'YYYYMMDD' 形式で返す"""
        # UTC+9時間（日本時間）のタイムゾーンを定義
        # 現在時刻をJSTで取得
        return datetime.now(timezone(timedelta(hours=9), 'JST')).strftime('%Y%m%d')

    def normalize_date_format(self, date_val) -> str:
        """あらゆる日付形式を 8桁の文字列ID 'YYYYMMDD' に変換する"""
        if not date_val:
            return ""

        # すでに 20260327 形式の文字列ならそのまま返す
        if isinstance(date_val, str) and len(date_val) == 8 and date_val.isdigit():
            return date_val

        # datetimeオブジェクトの場合
        if isinstance(date_val, datetime):
            return date_val.strftime('%Y%m%d')

        # それ以外（ハイフンあり文字列など）
        date_str = str(date_val).strip()
        # 数字だけを抽出
        normalized = "".join(filter(str.isdigit, date_str))
    
        return normalized

    def get_jyo_name(self, kaisai_id: str) -> str:
        """10桁または12桁のIDから会場名を特定"""
        if not kaisai_id or len(kaisai_id) < 6:
            return "不明"
            
        code = kaisai_id[4:6]
        # 定数から取得。なければ "不明" を返す
        return JYO_NAME_MAP.get(code, "不明")

    def get_race_num_from_id(self, race_id: str) -> str:
        """レースIDからレース番号を取得"""
        return str(race_id)[-2:]

    def exclued_race_ids(self, kaisai_ids: list) -> list:
        """レースIDリストから、除外対象を取り除く"""
        valid_ids_list = []
        for k_id in kaisai_ids:
            actual_course = self.get_jyo_name(k_id)
        
            if actual_course in EXCLUDE_COURSES:
                logger.info(f"スキップ中: {actual_course}({k_id}) は取得対象外です。")
                continue
            valid_ids_list.append(k_id)
        return valid_ids_list

    def filter_race_ids_by_course(self, race_ids: list, target_course_codes: list) -> list:
        """
        レースIDリストの中から、指定した会場コードに合致するものだけを抽出する
    
        Args:
            race_ids (list): IDのリスト
            target_course_codes (list): ['44', '54'] のような場所コードのリスト
    
        Returns:
            list: フィルタリングされたレースIDリスト
        """
        if not race_ids:
            return []
    
        # 文字列として比較するために正規化 (54 -> "54")
        target_codes = [str(c).zfill(2) for c in target_course_codes]
    
        # IDの5-6文字目が場所コード
        filtered = [
            rid for rid in race_ids 
            if str(rid)[4:6] in target_codes
        ]
    
        return sorted(filtered)

    def is_nar_race_id(self, race_id: str) -> bool:
        """レースIDから開催場所がNARかJRAか判別する"""
        return int(str(race_id)[4:6]) > JRA_MAX_COURSE_CODE

    def filter_race_ids_by_number(self, race_ids: list, target_nums: list) -> list:
        """
        レースIDリストの中から、指定したレース番号に合致するものだけを抽出する
    
        Args:
            race_ids (list): ['202654032801', '202654032802', ...] のようなIDリスト
            target_nums (list): [1, 11] のような取得したいレース番号のリスト
    
        Returns:
            list: フィルタリングされたレースIDリスト
        """
        if not race_ids:
            return []
    
        # 比較用にターゲット番号を文字列の2桁ゼロ埋めに変換しておく (1 -> "01")
        target_str_list = [str(n).zfill(2) for n in target_nums]
    
        # 末尾2桁がターゲットに含まれるものだけを抽出
        filtered = [
            rid for rid in race_ids 
            if str(rid)[-2:] in target_str_list
        ]
    
        return sorted(filtered)

    def race_url_from_race_id(self, race_id: str, is_nar: bool) -> str:
        """レースIDからURL作成"""
        domain = self.netkeiba_domain_from(is_nar)
        return f"https://{domain}.netkeiba.com/race/shutuba.html?race_id={race_id}"
    
    def race_result_url_from_race_id(self, race_id: str, is_nar: bool) -> str:
        """レースIDからURL作成"""
        domain = self.netkeiba_domain_from(is_nar)
        return f"https://{domain}.netkeiba.com/race/result.html?race_id={race_id}"

    def get_yesterday_date(self) -> str:
        """現在時刻から昨日の日付を取得"""
        # 日本時間（JST: UTC+9）のタイムゾーンを定義
        JST = timezone(timedelta(hours=9))

        # 日本時間での「現在時刻」を取得
        now_jst = datetime.now(JST)
        # 日本時間ベースで「前日」の日付を計算
        target_date = (now_jst - timedelta(days=1)).strftime("%Y%m%d")

        return target_date

    def wait_idle_time(self):
        sleep_time = random.uniform(2.5, 5.0)
        time.sleep(sleep_time)