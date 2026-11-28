"""
scraper.py - 競馬スクレイピング・分析処理統制オーケストレータークラス
"""

import os
import json
import random
import time
import logging
from pathlib import Path
from datetime import datetime
from typing import List, Dict, Optional, Any, Union
from concurrent.futures import ThreadPoolExecutor, as_completed

from src.core.fetcher import NkFetcher
from src.core.writer import NkWriter
from src.core.formatter import NkFormatter
from src.core.analyzer import NkAnalyzer
from src.core.report_analyzer import NkReportAnalyzer
from src.constants.netkeibatag import JYO_NAME_MAP, EXCLUDE_COURSES, JRA_MAX_COURSE_CODE
from src.client.all_html_dump import fetch_js_html, NkPlaywrightClient, NkPlaywrightClientManager
from src.core.generate_personnel_report import generate_daily_personnel_reports
from src.core.simulator import SimulationEngine, VenueRuleFinder
from src.core.logic_generator import NkLogicGenerator
from src.core.prediction_verifier import NkPredictionVerifier

from src.utils.date_utils import (
    get_today_jst,
    get_yesterday_date,
    normalize_date_format,
    determine_target_date,
)
from src.utils.text_utils import (
    get_race_num_from_id,
    get_course_code_from_id,
    is_nar_race_id,
)

logger = logging.getLogger(__name__)

DEFAULT_BASE_DIR = "data"
SELECTOR_HORSE_DB = "table.db_h_race_results"
SELECTOR_KAISAI_HP = ".RaceList_Body"
SELECTOR_SHUTUBA_HP = ".RaceName"
SELECTOR_RESULT_HP = ".ResultTableFrame"


class NkScraper:
    """
    競馬スクレイピング・分析処理を統制するオーケストレータークラス
    マルチスレッド安全な2スレッド並列アクセスマネージャーを常駐化
    """

    def __init__(self, headless: bool = True, base_dir: str = DEFAULT_BASE_DIR):
        self.fetcher = NkFetcher()
        self.writer = NkWriter()
        self.formatter = NkFormatter()
        self.analyzer = NkAnalyzer()
        self.headless = headless
        self.base_dir = base_dir
        
        # 🌟 マルチスレッド対応 Playwright マネージャーを保持
        self.pw_mgr = NkPlaywrightClientManager(headless=self.headless)
        os.makedirs(self.base_dir, exist_ok=True)

    def close(self):
        """全スレッドの Playwright ブラウザプロセスを安全に一括破棄"""
        if hasattr(self, "pw_mgr") and self.pw_mgr:
            self.pw_mgr.close_all()

    def is_horse_cache_valid(
        self,
        horse_id: str,
        target_date: str = "",
        is_test: bool = False,
        max_days: int = 5
    ) -> bool:
        """
        馬マスターJSON (data/horses/{horse_id}.json) が存在し、
        そのデータ作成・更新日時 (updated_at) が target_date から 5日未満であるかを判定する。
        5日未満であれば Webスクレイピングをスキップしてキャッシュを利用可能。
        """
        if not horse_id:
            return False

        base_dir = Path("data_test/horses") if is_test else Path("data/horses")
        horse_file = base_dir / f"{horse_id}.json"

        if not horse_file.exists():
            return False

        try:
            with open(horse_file, "r", encoding="utf-8") as fp:
                cached_data = json.load(fp)

            updated_at = str(cached_data.get("updated_at", "")).strip()

            if target_date and len(target_date) == 8 and target_date.isdigit():
                ref_dt = datetime.strptime(target_date, "%Y%m%d")
            else:
                ref_dt = datetime.now()

            if updated_at and len(updated_at) == 8 and updated_at.isdigit():
                up_dt = datetime.strptime(updated_at, "%Y%m%d")
                diff_days = (ref_dt - up_dt).days
                return 0 <= diff_days < max_days
            else:
                mtime = datetime.fromtimestamp(horse_file.stat().st_mtime)
                diff_days = (ref_dt - mtime).days
                return 0 <= diff_days < max_days
        except Exception as e:
            logger.warning(f"馬データキャッシュチェックエラー ({horse_id}): {e}")
            return False

    def load_cached_horse_data(self, horse_id: str, is_test: bool = False) -> Optional[Dict[str, Any]]:
        """
        ローカルに保存された馬マスターJSONを読み込む
        """
        base_dir = Path("data_test/horses") if is_test else Path("data/horses")
        horse_file = base_dir / f"{horse_id}.json"
        if not horse_file.exists():
            return None
        try:
            with open(horse_file, "r", encoding="utf-8") as fp:
                return json.load(fp)
        except Exception as e:
            logger.error(f"馬データキャッシュ読み込み失敗 ({horse_file}): {e}")
            return None

    def update_logic_protocols(
        self,
        target_date: Optional[str] = None,
        is_test: bool = False,
        save_latest_copy: bool = True,
    ) -> Dict[str, Any]:
        """
        蓄積されたレース結果JSONと馬データから会場別の最適パラメータ・特例パッチを自動抽出し、
        日付スタンプ付き (例: logic-浦和-20261126.md) および 最新参照用 (logic-浦和-latest.md)
        の両形式で予想プロトコルMarkdownを自動更新・保存する
        """
        date_str = self.normalize_date_format(target_date) if target_date else get_today_jst()
        results_dir = "data_test/results" if is_test else "data/results"
        horses_dir = "data_test/horses" if is_test else "data/horses"

        sim_engine = SimulationEngine(results_dir=results_dir, horses_dir=horses_dir)
        finder = VenueRuleFinder(sim_engine)
        venue_results = finder.analyze_all_venues()

        generator = NkLogicGenerator(writer=self.writer)
        saved_paths = {}

        for venue_name, data in venue_results.items():
            if data.get("race_count", 0) == 0:
                continue

            md_content = generator.generate_markdown_protocol(
                config=data["best_config"],
                version=f"v1.8-{date_str}",
                target_venue=venue_name,
                backtest_stats=data["best_stats"],
                detected_patches=data["patches"],
            )

            date_filename = f"logic-{venue_name}-{date_str}.md"
            venue_dir = f"protocols/{venue_name}"
            saved_date_path = self.writer.save_as_markdown(
                target_date=date_str,
                track_name=venue_dir,
                filename=date_filename,
                contents=md_content,
                is_test=is_test,
            )

            if save_latest_copy:
                latest_filename = f"logic-{venue_name}-latest.md"
                self.writer.save_as_markdown(
                    target_date="latest",
                    track_name=venue_dir,
                    filename=latest_filename,
                    contents=md_content,
                    is_test=is_test,
                )

            saved_paths[venue_name] = saved_date_path
            logger.info(f"【プロトコル更新完了】{venue_name}: {saved_date_path}")

        return saved_paths

    def _fetch_single_horse(
        self,
        horse_row: Dict[str, Any],
        max_retries: int = 3
    ) -> Dict[str, Any]:
        """
        1頭分の馬データをWebからスクレイピング取得（自動リトライ＆段階的バックオフ、マナーウェイト付き）
        """
        horse_id = horse_row.get("horse_id", "")
        horse_url = horse_row.get("horse_url", "")
        horse_name = horse_row.get("horse_name", "")

        if not horse_url or not horse_id:
            return {}

        logger.info(f"🌐 [並行取得] 馬データをスクレイピング中: {horse_name} ({horse_id})")

        pw_client = self.pw_mgr.get_client()

        for attempt in range(1, max_retries + 1):
            try:
                horse_html = pw_client.fetch_js_html(horse_url, SELECTOR_HORSE_DB)
                if not horse_html:
                    raise ValueError("HTMLの取得結果が空です")

                data: Dict[str, Any] = {
                    "horse_id": horse_id,
                    "horse_name": horse_name,
                    "horse_prof": self.fetcher.fetch_horse_profile(horse_html),
                    "is_freshly_scraped": True
                }

                history = self.fetcher.fetch_horse_history(horse_html)
                data["horse_history"] = history

                if history:
                    data["analyzed_data"] = self.analyzer.analyze_horse_history(history)
                    data["refine_history"] = self.analyzer.refine_data_horse_history(history)
                else:
                    data["analyzed_data"] = "- 戦績データがない、または新馬です。\n\n"
                    data["refine_history"] = "> データなし\n\n"

                # 正常取得後のマナーウェイト (1.5〜2.5秒の間隔制御)
                time.sleep(random.uniform(1.5, 2.5))
                return data

            except Exception as e:
                logger.warning(
                    f"⚠️ [リトライ {attempt}/{max_retries}] 馬データ取得エラー ({horse_name} / {horse_id}): {e}"
                )
                if attempt < max_retries:
                    # 段階的バックオフ (5.0〜10.0秒待機してから再試行)
                    backoff = random.uniform(5.0, 10.0)
                    logger.info(f"⏳ {backoff:.1f}秒間一時停止してから再試行します...")
                    time.sleep(backoff)
                else:
                    logger.error(f"❌ 規定回数のリトライ失敗: {horse_name} ({horse_id})")

        return {
            "horse_id": horse_id,
            "horse_name": horse_name,
            "horse_prof": {},
            "horse_history": [],
            "analyzed_data": "- データ取得に失敗しました。\n\n",
            "refine_history": "> データなし\n\n",
            "is_freshly_scraped": False
        }

    def fetch_race_info_by_id(
        self,
        race_id: str,
        target_date: str = "",
        is_test: bool = False,
        max_workers: int = 2
    ) -> Dict[str, Any]:
        """
        1レース分の出馬表および出走馬データを取得・抽出する。
        5日未満のキャッシュ馬データは自動スキップ。
        未キャッシュ馬は安全な2スレッド並列処理（リトライ＆ウェイト制御付き）で取得。
        """
        results: Dict[str, Any] = {}
        is_nar = self.is_nar_race_id(race_id)
        target_url = self.race_url_from_race_id(race_id, is_nar)

        pw_client = self.pw_mgr.get_client()
        html_contents = pw_client.fetch_js_html(target_url, SELECTOR_SHUTUBA_HP)

        race_info = self.fetcher.fetch_race_info(target_url, html_contents)
        results["race_info"] = race_info

        shutuba_horses = self.fetcher.fetch_shutuba_horse_info(target_url, html_contents)
        if not shutuba_horses:
            logger.warning(f"race_id: {race_id} の出走馬一覧が取得できませんでした (HTML空/タイムアウト)")
            return {}

        results["shutuba_horses"] = shutuba_horses

        horses_data_map: Dict[str, Dict[str, Any]] = {}
        uncached_rows: List[Dict[str, Any]] = []
        cached_count = 0

        for horse_row in shutuba_horses:
            horse_id = horse_row.get("horse_id", "")
            horse_name = horse_row.get("horse_name", "")

            if not horse_id:
                continue

            # 🌟【キャッシュチェック】更新日時が5日未満であればWebスクレイピングをスキップ
            if self.is_horse_cache_valid(horse_id, target_date=target_date, is_test=is_test, max_days=5):
                cached_horse = self.load_cached_horse_data(horse_id, is_test=is_test)
                if cached_horse:
                    cached_horse["is_freshly_scraped"] = False
                    horses_data_map[horse_id] = cached_horse
                    cached_count += 1
                    logger.debug(f"⚡ 馬データキャッシュ適用 (<5日): {horse_name} ({horse_id})")
                    continue

            uncached_rows.append(horse_row)

        scraped_count = len(uncached_rows)

        # 🌟【2スレッド並列処理の実行】
        if uncached_rows:
            logger.info(f"🚀 未キャッシュの {scraped_count} 頭の馬データを {max_workers} スレッド並列取得開始...")

            with ThreadPoolExecutor(max_workers=max_workers) as executor:
                future_to_id = {
                    executor.submit(self._fetch_single_horse, row): row.get("horse_id", "")
                    for row in uncached_rows
                }

                for future in as_completed(future_to_id):
                    h_id = future_to_id[future]
                    try:
                        h_data = future.result()
                        if h_data and h_data.get("horse_id"):
                            horses_data_map[h_id] = h_data
                    except Exception as e:
                        logger.error(f"スレッド実行中に予期せぬエラーが発生しました (horse_id={h_id}): {e}")

        # 出走順 (shutuba_horses の順序) に再整列して集計結果を構築
        ordered_horses_data = []
        for horse_row in shutuba_horses:
            h_id = horse_row.get("horse_id", "")
            if h_id in horses_data_map:
                ordered_horses_data.append(horses_data_map[h_id])

        logger.info(
            f"race_id: {race_id} 馬データ処理完了 "
            f"(キャッシュ利用: {cached_count}頭 / 2スレッド並列Web取得: {scraped_count}頭)"
        )
        results["horse_infos"] = ordered_horses_data
        return results

    def fetch_race_result_by_id(self, race_id: str) -> List[Dict[str, Any]]:
        is_nar = self.is_nar_race_id(race_id)
        target_url = self.race_result_url_from_race_id(race_id, is_nar)

        pw_client = self.pw_mgr.get_client()
        html_contents = pw_client.fetch_js_html(target_url, SELECTOR_RESULT_HP)
        return self.fetcher.fetch_race_result(target_url, html_contents)

    def scraping_races(
        self,
        input_date: Optional[str] = None,
        course_filter: Optional[List[Union[str, int]]] = None,
        race_num_filter: Optional[List[Union[str, int]]] = None,
        is_test: bool = False,
    ) -> None:
        """
        出馬表データのスクレイピングおよびJSON保存メイン処理 (個別のMarkdownファイル出力は全廃)
        5日未満のキャッシュ馬データは自動スキップして高速化
        """
        logger.info("出馬表のスクレイピングを開始します")
        target_date = self.determine_target_date(input_date)
        target_race_ids = self.get_target_race_ids(target_date, course_filter, race_num_filter)

        logger.info(f"対象レースID ({len(target_race_ids)}件): {target_race_ids}")

        try:
            for race_id in target_race_ids:
                logger.info(f"race_id: {race_id} の解析開始")
                race_info = self.fetch_race_info_by_id(race_id, target_date=target_date, is_test=is_test)
                if not race_info or not race_info.get("race_info") or not race_info.get("shutuba_horses"):
                    logger.warning(f"race_id: {race_id} の出馬表データ取得不全のため保存をスキップします")
                    continue

                info = race_info["race_info"]
                race_track = info.get("race_track", self.get_jyo_name(race_id))
                race_num = info.get("race_num", self.get_race_num_from_id(race_id))

                # 出馬表データをJSON形式で保存 (data/shutuba/YYYY/MM/)
                self.writer.save_shutuba_to_json(
                    race_info_dict=race_info,
                    race_id=race_id,
                    race_track=race_track,
                    race_num=race_num,
                    target_date=target_date,
                    is_test=is_test,
                )

                # 個別馬データマスターJSONの更新保存 (data/horses/{horse_id}.json)
                horse_infos = race_info.get("horse_infos", [])
                for h_info in horse_infos:
                    h_id = h_info.get("horse_id", "")
                    if h_id and h_info.get("is_freshly_scraped", True):
                        self.writer.save_horse_to_json(
                            horse_data=h_info,
                            horse_id=h_id,
                            target_date=target_date,
                            is_test=is_test,
                        )

                self.wait_idle_time()
        finally:
            self.close()

    def scraping_results(
        self,
        input_date: Optional[str] = None,
        course_filter: Optional[List[Union[str, int]]] = None,
        race_num_filter: Optional[List[Union[str, int]]] = None,
        is_test: bool = False,
    ) -> None:
        """
        レース結果のスクレイピングおよび成果物レポート生成メイン処理 (個別の結果Markdown出力は全廃)
        """
        logger.info("レース結果のスクレイピングを開始します")
        target_date = self.determine_target_date(input_date) if input_date else get_yesterday_date()
        target_race_ids = self.get_target_race_ids(target_date, course_filter, race_num_filter)

        logger.info(f"対象レースID ({len(target_race_ids)}件): {target_race_ids}")

        results_by_venue: Dict[str, Dict[str, Any]] = {}
        daily_venue_results: Dict[str, List[Dict[str, Any]]] = {}

        try:
            for race_id in target_race_ids:
                result_info = self.fetch_race_result_by_id(race_id)
                if not result_info or len(result_info) < 3:
                    continue

                race_track = self.get_jyo_name(race_id)
                race_num = self.get_race_num_from_id(race_id)

                if race_track not in results_by_venue:
                    results_by_venue[race_track] = {}
                    daily_venue_results[race_track] = []

                results_by_venue[race_track][race_num] = result_info
                daily_venue_results[race_track].extend(result_info[2:])

                # レース結果JSON保存 (data/results/YYYY/MM/)
                filename = self.formatter.get_filename_from_race_result(race_id, race_track, race_num)
                self.writer.save_race_result_to_json(result_info, race_id, race_track, race_num, target_date, filename, is_test)

                self.wait_idle_time()

            # 当日バイアスレポートの生成 (data/{YYYYMMDD}/{会場}-results/)
            for venue, venue_results in results_by_venue.items():
                logger.info(f"【馬場バイアス解析】{venue} の当日傾向レポートを作成中...")
                bias_md = self.analyzer.generate_daily_bias_markdown(target_date, venue_results, target_date, venue)
                bias_filename = f"{target_date}-{venue}-bias.md"
                self.writer.save_as_markdown(target_date, f"{venue}-results", bias_filename, bias_md, is_test)

            # 騎手・厩舎レポート作成
            logger.info(f"【人事レポート作成】{target_date} 全場の騎手・厩舎レポートを作成中...")
            generate_daily_personnel_reports(target_date, is_test)

            # 予想検証レポート作成 (JRA / NAR 別)
            logger.info(f"【予想検証レポート作成】{target_date} の予想・結果整合性レポート(JRA/NAR別)を作成中...")
            verifier = NkPredictionVerifier(base_dir=self.base_dir, test_base_dir="data_test")

            for cat in ["JRA", "NAR"]:
                verification_md = verifier.generate_verification_report(target_date, category=cat, is_test=is_test)
                if "⚠️" not in verification_md:
                    verif_filename = f"prediction_verification_{cat}_{target_date}.md"
                    self.writer.save_as_markdown(target_date, "reports", verif_filename, verification_md, is_test)
                    logger.info(f"✅ 予想検証レポート({cat})を作成しました: {verif_filename}")

            # 最新蓄積データに基づく会場別プロトコルの自動更新
            logger.info("【プロトコル自動更新】最新結果データに基づく会場別プロトコルを更新中...")
            self.update_logic_protocols(target_date=target_date, is_test=is_test)
        finally:
            self.close()

    def get_target_race_ids(
        self,
        date: str,
        course_filter: Optional[List[Union[str, int]]] = None,
        race_num_filter: Optional[List[Union[str, int]]] = None,
    ) -> List[str]:
        results = []
        for is_nar in [True, False]:
            results.extend(self.get_kaisai_ids(date, is_nar))

        results = self.exclude_race_ids(results)

        if results and (course_filter or race_num_filter):
            return self.filtered_race_ids(results, course_filter, race_num_filter)
        return results

    def get_kaisai_ids(self, date: str, is_nar: bool) -> List[str]:
        top_url = self.get_top_page_url(date, is_nar)
        pw_client = self.pw_mgr.get_client()
        html_contents = pw_client.fetch_js_html(top_url, SELECTOR_KAISAI_HP)
        return self.fetcher.fetch_kaisai_race_ids(top_url, html_contents)

    def filtered_race_ids(
        self,
        kaisai_ids: List[str],
        course_codes: Optional[List[Union[str, int]]],
        race_nums: Optional[List[Union[str, int]]],
    ) -> List[str]:
        results = kaisai_ids
        if course_codes:
            results = self.filter_race_ids_by_course(results, course_codes)
        if race_nums:
            results = self.filter_race_ids_by_number(results, race_nums)
        return results

    def get_top_page_url(self, target_date: str, is_nar: bool = True) -> str:
        domain = self.netkeiba_domain_from(is_nar)
        return f"https://{domain}.netkeiba.com/top/race_list.html?kaisai_date={target_date}"

    def netkeiba_domain_from(self, is_nar: bool) -> str:
        return "nar" if is_nar else "race"

    def determine_target_date(self, input_date: Optional[str]) -> str:
        return determine_target_date(input_date)

    def get_today_jst(self) -> str:
        return get_today_jst()

    def get_yesterday_date(self) -> str:
        return get_yesterday_date()

    def normalize_date_format(self, date_val: Any) -> str:
        return normalize_date_format(date_val)

    def get_jyo_name(self, kaisai_id: str) -> str:
        if not kaisai_id or len(str(kaisai_id)) < 6:
            return "不明"
        code = str(kaisai_id)[4:6]
        return JYO_NAME_MAP.get(code, "不明")

    def get_race_num_from_id(self, race_id: str) -> str:
        return get_race_num_from_id(race_id)

    def exclude_race_ids(self, kaisai_ids: List[str]) -> List[str]:
        valid_ids_list = []
        for k_id in kaisai_ids:
            actual_course = self.get_jyo_name(k_id)
            if actual_course in EXCLUDE_COURSES:
                logger.info(f"スキップ中: {actual_course}({k_id}) は取得対象外です。")
                continue
            valid_ids_list.append(k_id)
        return valid_ids_list

    def filter_race_ids_by_course(self, race_ids: List[str], target_course_codes: List[Union[str, int]]) -> List[str]:
        if not race_ids:
            return []
        target_codes = [str(c).zfill(2) for c in target_course_codes]
        filtered = [rid for rid in race_ids if get_course_code_from_id(rid) in target_codes]
        return sorted(filtered)

    def is_nar_race_id(self, race_id: str) -> bool:
        return is_nar_race_id(race_id)

    def filter_race_ids_by_number(self, race_ids: List[str], target_nums: List[Union[str, int]]) -> List[str]:
        if not race_ids:
            return []
        target_str_list = [str(n).zfill(2) for n in target_nums]
        filtered = [rid for rid in race_ids if get_race_num_from_id(rid) in target_str_list]
        return sorted(filtered)

    def race_url_from_race_id(self, race_id: str, is_nar: bool) -> str:
        domain = self.netkeiba_domain_from(is_nar)
        return f"https://{domain}.netkeiba.com/race/shutuba.html?race_id={race_id}"

    def race_result_url_from_race_id(self, race_id: str, is_nar: bool) -> str:
        domain = self.netkeiba_domain_from(is_nar)
        return f"https://{domain}.netkeiba.com/race/result.html?race_id={race_id}"

    def wait_idle_time(self) -> None:
        sleep_time = random.uniform(2.5, 5.0)
        time.sleep(sleep_time)
