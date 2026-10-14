import os
from pathlib import Path

# ロガー設定
import logging
logger = logging.getLogger(__name__)


class NkWriter:
    def __init__(self):
        self.base_dir = Path("data")
        self.test_base_dir = Path("data_test")
        os.makedirs(self.base_dir, exist_ok=True)
        os.makedirs(self.test_base_dir, exist_ok=True)

    def save_as_markdown(self, target_date: str, track_name: str, filename: str, contents: str, is_test: bool=False) -> str:
        """内容をmarkdownファイルとして指定の場所に指定のファイル名で保存する"""
        # ディレクトリ／ファイル名作成
        base_dir = self.test_base_dir if is_test else self.base_dir
        date_dir = target_date
        venue = track_name

        # 1. 保存先のディレクトリパスを組み立てる（data/20261011/中山）
        #       結果の場合は（data/20261011/中山-results）
        save_dir = base_dir / date_dir / venue

        # 2. フォルダが存在しない場合は自動作成する（parents=Trueで日付と場所を一括作成）
        save_dir.mkdir(parents=True, exist_ok=True)

        # 3. 最終的なファイルパス
        file_path = save_dir / filename

        # 1. すでにファイルが存在する場合は上書き（デフォルト）
        # TODO: 選択的スキップ（再実行・スクレイピング再開時に便利）できるように
        if os.path.exists(file_path):
            #logger.info(f"既に存在するので作成をスキップします: {file_path}")
            #return file_path
            logger.info(f"既に存在するので上書きします: {file_path}")

        # 2. 逐次保存
        with open(file_path, "w", encoding="utf-8") as f:
            f.write(contents)

        logger.info(f"保存完了: {file_path}")
        return file_path
