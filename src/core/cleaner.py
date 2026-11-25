# ロガー設定
import logging
logger = logging.getLogger(__name__)

from datetime import datetime, timedelta, timezone
from pathlib import Path


def clean_old_date_folders(base_dir: str = "/data", days_threshold: int = 7):
    """指定ディレクトリ(/data)以下にある「YYYYMMDD」形式のフォルダのうち、
    現在から指定日数（デフォルト7日前）より古いものをすべて削除する
    """
    target_path = Path(base_dir)

    if not target_path.exists():
        logger.info(f"対象ディレクトリが存在しません: {base_dir}")
        return

    # 日本時間（JST: UTC+9）のタイムゾーンを定義
    JST = timezone(timedelta(hours=9))
  
    # 日本時間での「現在時刻」を取得
    now_jst = datetime.now(JST)
    threshold_date = now_jst - timedelta(days=days_threshold)

    logger.info(f"基準日時 (JST): {now_jst.strftime('%Y-%m-%d %H:%M:%S')}")
    logger.info(
        f"削除閾値: {threshold_date.strftime('%Y%m%d')} 以前のフォルダを削除します"
    )

    # /data/ 以下のディレクトリを走査
    for item in target_path.iterdir():
        if item.is_dir():
            folder_name = item.name

        # フォルダ名が 8桁の数字（YYYYMMDD）形式であるかチェック
        if folder_name.isdigit() and len(folder_name) == 8:
            try:
                # フォルダ名を日付オブジェクトに変換
                folder_date = datetime.strptime(folder_name, "%Y%m%d").date()
                threshold_date_only = threshold_date.date()

                # 閾値より古い場合は削除対象
                if folder_date < threshold_date_only:
                    logger.info(
                        f"削除対象を発見: {folder_name} (基準日より古いため削除します)"
                    )
                    # フォルダ内のファイルおよびサブフォルダをごっそり削除
                    shutil_rmtree(item)
                else:
                    logger.info(f"保持対象: {folder_name} (直近7日以内)")

            except ValueError:
                # 数字8桁だが日付として不正な場合はスキップ
                continue


def shutil_rmtree(dir_path: Path):
    """サブディレクトリやファイルを含めてフォルダを再帰的に削除するヘルパー"""
    for child in dir_path.iterdir():
        if child.is_dir():
            shutil_rmtree(child)
        else:
            child.unlink()
    dir_path.rmdir()
    logger.info(f"  -> 削除完了: {dir_path}")

