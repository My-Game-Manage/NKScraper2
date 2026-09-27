# main.py

import argparse
import sys
import logging

def main():
    parser = argparse.ArgumentParser(
        description="NetKeiba Data Collector: 開催日トップから指定条件のレースデータを取得します。"
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

if __name__ == "__main__":
    main()
