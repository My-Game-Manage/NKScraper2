import os
from pathlib import Path
import json

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
    
    def save_race_result_to_json(
        self, 
        data_list: list[dict], 
        race_id: str, 
        race_track: str, 
        race_num: str, 
        target_date: str = "",
        filename: str = "",
        is_test: bool = False,
    ) -> Path:
        """
        conv_race_result_to_markdown に渡される list[dict] 形式のレース結果データを、
        data/results/YYYY/MM/ 形式のディレクトリ階層で JSON 形式として保存する
        """
        base_dir = Path("data_test/results") if is_test else Path("data/results")
        
        # 1. target_date（例: "20260504" または "2026-05-04"）を元に、年/月のディレクトリ階層を構築
        if target_date:
            # 文字列から数字のみを抽出し、YYYYMMDDの形とみなして年・月を取得する
            digits_only = "".join(filter(str.isdigit, target_date))
            if len(digits_only) >= 6:
                year = digits_only[:4]
                month = digits_only[4:6]
                save_dir = base_dir / year / month
            else:
                save_dir = base_dir
        else:
            save_dir = base_dir

        # 2. ディレクトリが存在しない場合は自動作成（parents=True）
        save_dir.mkdir(parents=True, exist_ok=True)

        # 3. 既存のファイル命名規則メソッドを流用してJSON用のファイル名を生成
        md_filename = filename
        json_filename = md_filename.replace(".md", ".json")
        file_path = save_dir / json_filename

        # 4. 保存するデータの構造化（メタデータと結果のリストをラップ）
        payload = {
            "race_id": race_id,
            "race_track": race_track,
            "race_num": race_num,
            "target_date": target_date,
            "results": data_list
        }

        # 5. JSONファイルとして書き出し
        try:
            with open(file_path, "w", encoding="utf-8") as f:
                json.dump(payload, f, ensure_ascii=False, indent=2)
            logger.info(f"レース結果のJSON保存に成功しました: {file_path}")
        except Exception as e:
            logger.error(f"レース結果のJSON保存に失敗しました ({file_path}): {e}")
            raise e

        return file_path