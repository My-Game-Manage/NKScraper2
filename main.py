# main.py

import argparse
import sys
import logging
import json
from pathlib import Path
from datetime import datetime, timedelta, timezone

from src.constants.netkeibatag import JYO_NAME_MAP
from src.scraper import NkScraper
from src.core.simulator import (
    SimulationEngine,
    RaceEvaluator,
    RacePredictor,
    PersonnelTrendAnalyzer,
    SimulationConfig,
)
from src.core.prediction_verifier import NkPredictionVerifier
from src.core.writer import NkWriter
from src.utils.date_utils import get_today_jst, get_yesterday_date


def parse_list_arg(arg):
    """カンマ区切りの文字列をリストに変換する汎用関数"""
    if not arg:
        return []
    return [item.strip() for item in arg.split(',')]

NAME_TO_CODE = {v: k for k, v in JYO_NAME_MAP.items()}

def convert_to_course_codes(input_list: list) -> list:
    clean_codes = []
    for item in input_list:
        item = item.strip()
        if item.isdigit():
            clean_codes.append(item.zfill(2))
        elif item in NAME_TO_CODE:
            clean_codes.append(NAME_TO_CODE[item])
        else:
            print(f"Warning: 会場名 '{item}' が見つかりません。")
    return clean_codes

def get_today_jst_str() -> str:
    return datetime.now(timezone(timedelta(hours=9), 'JST')).strftime('%Y%m%d')

def normalize_date_format(date_val) -> str:
    if not date_val:
        return ""
    if isinstance(date_val, str) and len(date_val) == 8 and date_val.isdigit():
        return date_val
    if isinstance(date_val, datetime):
        return date_val.strftime('%Y%m%d')
    date_str = str(date_val).strip()
    return "".join(filter(str.isdigit, date_str))

def load_shutuba_races(target_date: str, is_test: bool = False) -> list:
    """
    指定日付の出馬表（Markdownファイル data/{YYYYMMDD}/{会場}/*.md または JSON）を全自動探索・パースする
    """
    base_dir = Path("data_test") if is_test else Path("data")
    date_str = target_date or get_today_jst_str()
    date_dir = base_dir / date_str

    md_files = []

    # 1. 00_race_overview.md ファイルを最優先検索
    if date_dir.exists():
        md_files = list(date_dir.glob("**/*00_race_overview.md"))
        if not md_files:
            # 見つからなければ会場直下の統合Markdownファイルを探索
            md_files = [
                f for f in date_dir.glob("*/*.md")
                if not f.name.startswith("logic-") and not f.name.endswith("-bias.md")
            ]

    # 2. 日付ディレクトリで見つからない場合、全体から探索
    if not md_files and base_dir.exists():
        md_files = list(base_dir.glob("**/*00_race_overview.md"))

    races = []
    for f in sorted(md_files):
        try:
            with open(f, "r", encoding="utf-8") as fp:
                content = fp.read()
            r_data = RacePredictor.parse_shutuba_markdown(content)
            if r_data and r_data.get("results"):
                races.append(r_data)
        except Exception as e:
            logging.error(f"Markdown出馬表パースエラー ({f}): {e}")

    # 3. JSONファイルもバックアップ探索 (racesディレクトリ等)
    races_dir = Path("data_test/races") if is_test else Path("data/races")
    if races_dir.exists():
        json_files = list(races_dir.glob(f"**/{date_str}*.json"))
        if not json_files:
            json_files = list(races_dir.glob("**/*.json"))
        for jf in json_files:
            try:
                with open(jf, "r", encoding="utf-8") as fp:
                    j_data = json.load(fp)
                    if j_data.get("results") or j_data.get("horses"):
                        races.append(j_data)
            except Exception:
                pass

    return races

def run_prediction_workflow(target_date: str, course_codes: list, race_nums: list, is_test: bool = False):
    """保存済みの出馬表データ（Markdown / JSON）から自動予想Markdown(note用)を生成する"""
    target_date = target_date or get_today_jst_str()
    results_dir = Path("data_test/results") if is_test else Path("data/results")
    horses_dir = Path("data_test/horses") if is_test else Path("data/horses")
    out_dir = Path("data_test/predictions") if is_test else Path("data/predictions")

    sim_engine = SimulationEngine(results_dir=str(results_dir), horses_dir=str(horses_dir))
    all_races = sim_engine.load_all_races()
    horse_master = sim_engine.load_horse_master()
    j_prof, t_prof = PersonnelTrendAnalyzer.extract_profiles_from_races(all_races)

    evaluator = RaceEvaluator(SimulationConfig(), jockey_profiles=j_prof, trainer_profiles=t_prof)
    predictor = RacePredictor(evaluator)

    shutuba_races = load_shutuba_races(target_date, is_test=is_test)

    logging.info(f"【予想自動生成】{len(shutuba_races)} 件の出馬表データを読み込み中...")

    generated_count = 0
    target_race_nums = [str(n).zfill(2) for n in race_nums] + [str(int(n)) for n in race_nums if str(n).isdigit()]

    for race_data in shutuba_races:
        try:
            track = str(race_data.get("race_track", ""))
            r_num = str(race_data.get("race_num", ""))

            # 会場フィルタ (名前・コード両対応)
            if course_codes:
                track_code = NAME_TO_CODE.get(track, "")
                if track_code not in course_codes and track not in course_codes:
                    continue

            # レース番号フィルタ
            if race_nums and r_num not in target_race_nums:
                continue

            pred_res = predictor.predict_race(race_data, horse_master)
            if not pred_res:
                continue

            note_md = predictor.generate_note_markdown(pred_res)

            # 保存ディレクトリ作成 (data/predictions/YYYYMMDD/会場/)
            r_date = str(race_data.get("target_date", target_date))
            save_dir = out_dir / r_date / track
            save_dir.mkdir(parents=True, exist_ok=True)
            
            formatted_num = r_num.zfill(2)
            save_path = save_dir / f"{r_date}-{track}{formatted_num}R_prediction.md"

            with open(save_path, "w", encoding="utf-8") as fp:
                fp.write(note_md)

            logging.info(f"🎯 予想出力完了: {save_path}")
            generated_count += 1
        except Exception as e:
            logging.error(f"予想出力エラー ({race_data.get('race_id', '')}): {e}")

    logging.info(f"✅ 全 {generated_count} レースの予想Markdownを作成しました。 (出力先: {out_dir})")


def run_verification_workflow(target_date: str = "", is_test: bool = False):
    """スクレイピングを実行せず、既存の予想データとレース結果データから検証レポートのみを生成して保存する"""
    base_dir = "data_test" if is_test else "data"
    
    # 対象日付が未指定の場合、結果ディレクトリから検索または昨日の日付を使用
    if not target_date:
        results_dir = Path(base_dir) / "results"
        found_dates = []
        if results_dir.exists():
            for json_file in results_dir.glob("**/*.json"):
                try:
                    with open(json_file, "r", encoding="utf-8") as fp:
                        data = json.load(fp)
                        d = str(data.get("target_date", ""))
                        if d and len(d) == 8 and d.isdigit():
                            found_dates.append(d)
                except Exception:
                    pass
        if found_dates:
            target_date = max(found_dates)
        else:
            target_date = get_yesterday_date()

    logging.info(f"【予想検証モード】対象日付 ({target_date}) の予想と結果の照合を開始します...")
    
    verifier = NkPredictionVerifier(base_dir=base_dir, test_base_dir="data_test")
    verification_md = verifier.generate_verification_report(target_date, is_test=is_test)

    writer = NkWriter(base_dir=base_dir)
    verif_filename = f"prediction_verification_{target_date}.md"
    save_path = writer.save_as_markdown(target_date, "reports", verif_filename, verification_md, is_test=is_test)

    logging.info(f"✅ 検証レポートの出力が完了しました: {save_path}")
    return save_path


def main():
    parser = argparse.ArgumentParser(
        description="NetKeiba Data Collector: 開催日トップから指定条件のレースデータを取得し、AI・note用予想を出力します。"
    )

    parser.add_argument("--date", type=str, default="", help="対象日 (YYYYMMDD). デフォルトは今日の日本時間")
    parser.add_argument("--course", type=parse_list_arg, default=[], help="会場コードのカンマ区切り (例: 44,54)")
    parser.add_argument("--race_num", type=parse_list_arg, default=[], help="レース番号のカンマ区切り (例: 1,11)")
    parser.add_argument("--no-headless", action="store_false", dest="headless", help="ブラウザを表示して実行")
    parser.set_defaults(headless=True)

    parser.add_argument("--result", action="store_true", dest="result", help="レース結果を取得する場合こちらを設定")
    parser.set_defaults(result=False)

    parser.add_argument("--update_logic", action="store_true", dest="update_logic", help="予想ロジック(Markdown)の更新のみを実行")
    parser.set_defaults(update_logic=False)

    parser.add_argument("--predict", action="store_true", dest="predict", help="出馬表データから自動予想(note投稿用MD)を生成")
    parser.set_defaults(predict=False)

    parser.add_argument("--verify", action="store_true", dest="verify", help="既存の予想データとレース結果データから検証レポート(note用Markdown)のみを生成")
    parser.set_defaults(verify=False)

    parser.add_argument("--only_race", action="store_true", dest="only_race", help="出馬表のみ取得する場合指定")
    parser.set_defaults(only_race=False)

    parser.add_argument("--test", action="store_true", dest="test", help="データ取得テスト用のフォルダに保存")

    parser.add_argument('--log', default='INFO', choices=['DEBUG', 'INFO', 'WARNING', 'ERROR'], help='ログレベル')
    args = parser.parse_args()

    logging.basicConfig(
        level=args.log,
        format='%(asctime)s [%(levelname)s][%(funcName)s][%(lineno)d] %(name)s: %(message)s',
        datefmt='%Y-%m-%d %H:%M:%S'
    )

    target_date = normalize_date_format(args.date)
    target_course_codes = convert_to_course_codes(args.course)

    try:
        if args.verify:
            # 予想検証モード（スクレイピングなし・既存データ照合のみ）
            logging.info("【検証モード】既存の予想MDおよび結果JSONから検証レポートのみを出力します...")
            run_verification_workflow(target_date, is_test=args.test)

        elif args.predict:
            # 自動予想出力モード
            logging.info("【予想生成モード】出馬表データから印・評価スコア・買い目Markdownを自動生成します...")
            run_prediction_workflow(target_date, target_course_codes, args.race_num, is_test=args.test)

        elif args.update_logic:
            # ロジック更新モード
            scraper = NkScraper(headless=args.headless)
            logging.info("【ロジック更新モード】既存の蓄積データから会場別予想プロトコルを更新します...")
            saved_paths = scraper.update_logic_protocols(target_date=target_date, is_test=args.test)
            for venue, path in saved_paths.items():
                logging.info(f"プロトコル作成完了 ({venue}): {path}")

        elif args.result:
            # 結果取得
            scraper = NkScraper(headless=args.headless)
            scraper.scraping_results(
                input_date=target_date,
                course_filter=target_course_codes,
                race_num_filter=args.race_num,
                is_test=args.test,
            )
        else:
            # レース・出馬情報取得（直後に自動予想作成も連動）
            scraper = NkScraper(headless=args.headless)
            scraper.scraping_races(
                input_date=target_date,
                course_filter=target_course_codes,
                race_num_filter=args.race_num,
                is_test=args.test,
            )
            logging.info("【自動予想実行】出馬表取得完了に伴い、自動予想Markdownを出力します...")
            run_prediction_workflow(target_date, target_course_codes, args.race_num, is_test=args.test)

    except KeyboardInterrupt:
        print("\nユーザーにより中断されました。")
        sys.exit(0)
    except Exception as e:
        print(f"致命的なエラーが発生しました: {e}")
        sys.exit(1)
    finally:
        if 'scraper' in locals() and hasattr(scraper, 'fetcher'):
            scraper.fetcher.client.quit()

if __name__ == "__main__":
    main()
