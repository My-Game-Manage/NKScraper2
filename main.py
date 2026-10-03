# main.py

import argparse
import sys
import logging
from datetime import datetime, timedelta, timezone

from src.constants.netkeibatag import JYO_NAME_MAP
from src.scraper import NkScraper


def parse_list_arg(arg):
    """カンマ区切りの文字列をリストに変換する汎用関数"""
    if not arg:
        return []
    return [item.strip() for item in arg.split(',')]

# 名前からコードを引くための辞書を事前に作成 {'札幌': '01', '大井': '44', ...}
NAME_TO_CODE = {v: k for k, v in JYO_NAME_MAP.items()}

def convert_to_course_codes(input_list: list) -> list:
    """
    ['大井', '54'] のような混在リストを ['44', '54'] に統一する
    """
    clean_codes = []
    for item in input_list:
        item = item.strip()
        
        if item.isdigit():
            # 数字ならそのまま採用（0埋めだけ念のため行う）
            clean_codes.append(item.zfill(2))
        elif item in NAME_TO_CODE:
            # 名前なら辞書からコードを引く
            clean_codes.append(NAME_TO_CODE[item])
        else:
            # どちらでもない場合は無視するか、ログを出す
            print(f"Warning: 会場名 '{item}' が見つかりません。")
            
    return clean_codes

def get_today_jst() -> str:
    """
    現在の日本時間を 'YYYYMMDD' 形式で返す
    """
    # UTC+9時間（日本時間）のタイムゾーンを定義
    # 現在時刻をJSTで取得
    return datetime.now(timezone(timedelta(hours=9), 'JST')).strftime('%Y%m%d')

def normalize_date_format(date_val) -> str:
    """
    あらゆる日付形式を 8桁の文字列ID 'YYYYMMDD' に変換する
    """
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

def main():
    parser = argparse.ArgumentParser(
        description="NetKeiba Data Collector: 開催日トップから指定条件のレースデータを取得します。"
    )

     # 1. 日付指定 (デフォルトは今日)
    parser.add_argument(
        "--date", 
        type=str, 
        default=get_today_jst(),
        help="対象日 (YYYYMMDD). デフォルトは今日の日本時間"
    )

    # 2. 会場フィルタ (コード指定: 44,54 など)
    parser.add_argument(
        "--course", 
        type=parse_list_arg, 
        default=[],
        help="会場コードのカンマ区切り (例: 44,54). 指定なしで全会場"
    )

    # 3. レース番号フィルタ (1,11 など)
    parser.add_argument(
        "--race_num", 
        type=parse_list_arg, 
        default=[],
        help="レース番号のカンマ区切り (例: 1,11). 指定なしで全レース"
    )

    # 4. ブラウザの表示設定
    parser.add_argument(
        "--no-headless", 
        action="store_false", 
        dest="headless",
        help="ブラウザを表示して実行する場合に指定"
    )
    parser.set_defaults(headless=True)

    # 5. レース結果を取得
    parser.add_argument(
        "--result", 
        action="store_true", 
        dest="result",
        help="レース結果を取得する場合こちらを設定"
    )
    parser.set_defaults(result=False)
    
    # 6. 馬の過去履歴の取得スキップ
    parser.add_argument(
        "--only_race", 
        action="store_true", 
        dest="only_race",
        help="出馬表のみ取得する場合これを指定（過去履歴をスキップ）"
    )
    parser.set_defaults(only_race=False)
    
    # 7. ログレベルの設定
    parser.add_argument(
        '--log', 
        default='INFO', 
        choices=['DEBUG', 'INFO', 'WARNING', 'ERROR'],
        help='ログレベルを指定します (デフォルト: INFO)'
    )

    # 1. 日付指定 (デフォルトは今日)

    # 2. 会場フィルタ (コード指定: 44,54 など)

    # 3. レース番号フィルタ (1,11 など)

    # 4. ブラウザの表示設定
    parser.add_argument(
        "--no-headless", 
        action="store_false", 
        dest="headless",
        help="ブラウザを表示して実行する場合に指定"
    )
    parser.set_defaults(headless=True)

    # 7. ログレベルの設定
    parser.add_argument(
        '--log', 
        default='INFO', 
        choices=['DEBUG', 'INFO', 'WARNING', 'ERROR'],
        help='ログレベルを指定します (デフォルト: INFO)'
    )
    args = parser.parse_args()
    
    # ログレベルの設定
    # setup_loggerに引数から渡されたレベルをセット
    # loggerの設定（プログラム全体で一度だけ設定）
    logging.basicConfig(
        level=args.log,
        format='%(asctime)s [%(levelname)s][%(funcName)s][%(lineno)d] %(name)s: %(message)s',
        datefmt='%Y-%m-%d %H:%M:%S'
    )

    # logger実行
    logging.debug("細かい計算過程を表示します（デバッグ用）")
    logging.info("シミュレーションを開始します")

    # 日付のフォーマットを 20260327 形式に正規化
    target_date = normalize_date_format(args.date)

    # 会場指定（名前またはコード）をすべてコードに変換
    target_course_codes = convert_to_course_codes(args.course)

    # コレクターの実行
    try:
        scraper = NkScraper(headless=args.headless)
        if args.result:
            # 結果取得
            scraper.scraping_results(
                target_date=target_date,
                course_filter=target_course_codes,
                race_num_filter=args.race_num,
            )
        else:
            # レース・出馬情報取得
            scraper.scraping_races(
                target_date=target_date,
                course_filter=target_course_codes,
                race_num_filter=args.race_num,
            )
    except KeyboardInterrupt:
        print("\nユーザーにより中断されました。")
        sys.exit(0)
    except Exception as e:
        print(f"致命的なエラーが発生しました: {e}")
        sys.exit(1)
    finally:
        scraper.fetcher.client.quit()

if __name__ == "__main__":
    main()
