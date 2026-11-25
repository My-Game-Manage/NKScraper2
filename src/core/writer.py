"""
writer.py - データ保存ユーティリティモジュール

スクレイピング結果（Markdownテキスト、構造化JSONデータ）のファイル保存と
ディレクトリ自動生成を管理します。
"""

import os
import json
import logging
from pathlib import Path
from typing import List, Dict, Any, Optional, Union

# date_utils から年月抽出ヘルパーをインポート
try:
    from src.utils.date_utils import extract_year_month
except ImportError:
    try:
        from src.utils.date_utils import extract_year_month
    except ImportError:
        def extract_year_month(date_val: str) -> tuple[str, str]:
            digits = "".join(filter(str.isdigit, str(date_val)))
            if len(digits) >= 6:
                return digits[:4], digits[4:6]
            return "unknown", "unknown"

logger = logging.getLogger(__name__)


class NkWriter:
    """レースデータおよび分析レポートのローカル保存を担当するクラス"""

    def __init__(self, base_dir: Union[str, Path] = "data", test_base_dir: Union[str, Path] = "data_test"):
        self.base_dir = Path(base_dir)
        self.test_base_dir = Path(test_base_dir)
        self.base_dir.mkdir(parents=True, exist_ok=True)
        self.test_base_dir.mkdir(parents=True, exist_ok=True)

    def save_as_markdown(
        self,
        target_date: str,
        track_name: str,
        filename: str,
        contents: str,
        is_test: bool = False,
    ) -> Path:
        """
        内容をMarkdownファイルとして指定のディレクトリ構造に保存する

        Args:
            target_date (str): 対象日付 (例: "20261011")
            track_name (str): 会場名/ディレクトリ構造 (例: "中山" または "中山-results")
            filename (str): 保存ファイル名 (例: "20261011-中山01R.md")
            contents (str): 保存するMarkdown文字列
            is_test (bool): テスト保存用フラグ (Trueの場合 data_test 配下に保存)

        Returns:
            Path: 保存されたファイルのパス
        """
        base_dir = self.test_base_dir if is_test else self.base_dir
        save_dir = base_dir / target_date / track_name
        save_dir.mkdir(parents=True, exist_ok=True)

        file_path = save_dir / filename

        if file_path.exists():
            logger.info(f"既存ファイルを上書きします: {file_path}")

        with open(file_path, "w", encoding="utf-8") as f:
            f.write(contents)

        logger.info(f"Markdown保存完了: {file_path}")
        return file_path

    def save_race_result_to_json(
        self,
        data_list: List[Dict[str, Any]],
        race_id: str,
        race_track: str,
        race_num: str,
        target_date: str = "",
        filename: str = "",
        is_test: bool = False,
    ) -> Path:
        """
        レース結果データを data/results/YYYY/MM/ 階層に構造化JSONとして保存する

        Args:
            data_list (List[Dict]): [0]=race_info, [1]=payouts_info, [2:]=着順リスト
            race_id (str): レースID
            race_track (str): 競馬場名
            race_num (str): レース番号
            target_date (str): 日付文字列
            filename (str): Markdownの元のファイル名 (例: "...R.md")
            is_test (bool): テスト環境フラグ

        Returns:
            Path: 保存されたJSONファイルのパス
        """
        base_dir = Path("data_test/results") if is_test else Path("data/results")

        # date_utils の extract_year_month を使用して YYYY/MM ディレクトリ構築
        if target_date:
            year, month = extract_year_month(target_date)
            save_dir = base_dir / year / month if year and month else base_dir
        else:
            save_dir = base_dir

        save_dir.mkdir(parents=True, exist_ok=True)

        # 安全な拡張子変更 (.md -> .json)
        md_path = Path(filename) if filename else Path(f"{race_id}.md")
        json_filename = md_path.with_suffix(".json").name
        file_path = save_dir / json_filename

        # 安全なデータ取り出し（要素数チェック）
        race_info = data_list[0] if len(data_list) > 0 and isinstance(data_list[0], dict) else {}
        payouts_info = data_list[1] if len(data_list) > 1 and isinstance(data_list[1], dict) else {}
        results_list = data_list[2:] if len(data_list) > 2 else []

        payload = {
            "race_id": race_id,
            "race_track": race_track,
            "race_num": race_num,
            "target_date": target_date,
            "race_name": race_info.get("race_name", ""),
            "race_grade": race_info.get("race_grade", ""),
            "race_type": race_info.get("race_type", ""),
            "race_distance": race_info.get("race_distance", ""),
            "weather": race_info.get("weather", ""),
            "condition": race_info.get("condition", ""),
            "race_class": race_info.get("race_class", ""),
            "results": results_list,
            "payouts": payouts_info,
        }

        try:
            with open(file_path, "w", encoding="utf-8") as f:
                json.dump(payload, f, ensure_ascii=False, indent=2)
            logger.info(f"レース結果のJSON保存に成功しました: {file_path}")
        except Exception as e:
            logger.error(f"レース結果のJSON保存に失敗しました ({file_path}): {e}")
            raise e

        return file_path

    def save_horse_to_json(
        self,
        horse_data: Dict[str, Any],
        horse_id: str,
        target_date: str = "",
        is_test: bool = False,
    ) -> Path:
        """
        個別の馬データを日付によらない汎用フォルダ data/horses/ 配下に {horse_id}.json として直接保存（上書き更新）する

        Args:
            horse_data (Dict[str, Any]): 馬のデータ辞書 (horse_name, horse_prof, horse_history, analyzed_data など)
            horse_id (str): 馬ID (例: "2021104567")
            target_date (str): 取得・更新日付 (例: "20261011")
            is_test (bool): テスト環境フラグ (Trueの場合 data_test 配下に保存)

        Returns:
            Path: 保存されたJSONファイルのパス
        """
        base_dir = Path("data_test/horses") if is_test else Path("data/horses")
        base_dir.mkdir(parents=True, exist_ok=True)

        file_path = base_dir / f"{horse_id}.json"

        payload = {
            "horse_id": horse_id,
            "horse_name": horse_data.get("horse_name", ""),
            "updated_at": target_date,
            "horse_prof": horse_data.get("horse_prof", {}),
            "horse_history": horse_data.get("horse_history", []),
            "analyzed_data": horse_data.get("analyzed_data", ""),
            "refine_history": horse_data.get("refine_history", ""),
        }

        try:
            with open(file_path, "w", encoding="utf-8") as f:
                json.dump(payload, f, ensure_ascii=False, indent=2)
            logger.info(f"馬データのJSON保存に成功しました: {file_path}")
        except Exception as e:
            logger.error(f"馬データのJSON保存に失敗しました ({file_path}): {e}")
            raise e

        return file_path
