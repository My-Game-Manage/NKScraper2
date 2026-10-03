import os

# ロガー設定
import logging
logger = logging.getLogger(__name__)


class NkWriter:
    def __init__(self):
        pass

    def save_as_markdown(self, target_date: str, filename: str, contents: str) -> str:
        """内容をmarkdownファイルとして指定の場所に指定のファイル名で保存する"""
        # ディレクトリ／ファイル名作成
        dir_path = os.path.join("data", target_date)
        os.makedirs(dir_path, exist_ok=True)
        
        file_path = os.path.join(dir_path, filename)

        # 1. すでにファイルが存在する場合はスキップ（再実行・スクレイピング再開時に便利）
        if os.path.exists(file_path):
            logger.info(f"既に存在するので作成をスキップします: {file_path}")
            return file_path

        # 2. 逐次保存
        with open(file_path, "w", encoding="utf-8") as f:
            f.write(contents)

        logger.info(f"保存完了: {file_path}")
        return file_path