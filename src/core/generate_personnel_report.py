import json
import logging
from pathlib import Path
from typing import Any, Dict, List, Optional

from src.utils.date_utils import extract_year_month, normalize_date_format

# リファクタリング済みのレポート分析クラスを使用（フォールバック付き）
try:
    from src.core.report_analyzer import NkReportAnalyzer
except ImportError:
    try:
        from src.core.analyzer import NkAnalyzer as NkReportAnalyzer
    except ImportError:
        from src.core.analyzer import NkAnalyzer as NkReportAnalyzer

logger = logging.getLogger(__name__)


def generate_daily_personnel_reports(target_date: str, is_test: bool = False) -> None:
    """
    指定した日付（YYYYMMDD形式）の保存済みJSONファイルをすべて読み込み、
    全場横断の「騎手データ」と「厩舎データ」のMarkdownファイルを生成・出力する。

    Parameters:
    - target_date: 対象日付（例: "20260504" または "2026-05-04"）
    - is_test: テスト環境かどうか
    """
    # 1. 日付形式の正規化
    norm_date = normalize_date_format(target_date)
    if not norm_date:
        logger.error(f"無効な日付形式です: {target_date}")
        return

    base_dir = Path("data_test/results") if is_test else Path("data/results")
    output_dir = Path("data_test/analysis") if is_test else Path("data/analysis")

    # 2. date_utils を活用して年・月ディレクトリを特定
    year, month = extract_year_month(norm_date)
    search_dir = base_dir / year / month

    if not search_dir.exists():
        search_dir = base_dir

    if not search_dir.exists():
        logger.error(f"指定された日付のディレクトリが存在しません: {search_dir}")
        return

    # 3. 該当する日付のJSONファイルを検索
    # 日付IDで始まるファイルを検索（例: 20260504*-result-*.json）
    pattern = f"{norm_date}*-result-*.json"
    json_files = list(search_dir.glob(pattern))

    # 見つからない場合はディレクトリ内の全JSONから特定
    if not json_files:
        json_files = list(search_dir.glob("*.json"))

    if not json_files:
        logger.error(f"該当する日付のJSONファイルが見つかりません (検索パターン: {pattern}, ディレクトリ: {search_dir})")
        return

    # 4. 該当日の全レース（全会場）の結果データを1つのリストに統合
    all_races_flat_data: List[Dict[str, Any]] = []
    for file_path in json_files:
        try:
            with open(file_path, "r", encoding="utf-8") as f:
                payload = json.load(f)

                # payload内に target_date が記録されている場合の一致チェック
                payload_date = normalize_date_format(payload.get("target_date", ""))
                if payload_date and payload_date != norm_date:
                    continue

                race_track = payload.get("race_track", "不明")
                race_type = payload.get("race_type", payload.get("タイプ", ""))
                race_distance = payload.get("race_distance", payload.get("距離", ""))

                results = payload.get("results", [])
                if isinstance(results, list):
                    for horse_result in results:
                        if isinstance(horse_result, dict):
                            horse_result["開催"] = race_track
                            if "タイプ" not in horse_result and race_type:
                                horse_result["タイプ"] = race_type
                            if "距離" not in horse_result and race_distance:
                                horse_result["距離"] = race_distance

                            # IDキーが欠損している場合のフォールバック
                            if "jockey_id" not in horse_result:
                                horse_result["jockey_id"] = horse_result.get("jockey", "unknown")
                            if "stable_id" not in horse_result:
                                horse_result["stable_id"] = horse_result.get("stable", "unknown")

                            all_races_flat_data.append(horse_result)
        except Exception as e:
            logger.error(f"ファイル読み込みエラー ({file_path}): {e}")

    if not all_races_flat_data:
        logger.error(f"【{norm_date}】統合できる有効なレース結果データがありません。")
        return

    # 5. NkReportAnalyzer インスタンスの生成
    analyzer = NkReportAnalyzer()

    # 6. 騎手データ・厩舎データのMarkdown文字列を生成
    jockey_md = analyzer.generate_jockey_style_aptitude_markdown(all_races_flat_data)
    trainer_md = analyzer.generate_trainer_venue_aptitude_markdown(all_races_flat_data)

    # 7. 出力先ディレクトリの作成とファイル書き出し
    output_dir.mkdir(parents=True, exist_ok=True)

    jockey_file = output_dir / f"{norm_date}_jockey_trend.md"
    trainer_file = output_dir / f"{norm_date}_trainer_trend.md"

    with open(jockey_file, "w", encoding="utf-8") as f:
        f.write(jockey_md)

    with open(trainer_file, "w", encoding="utf-8") as f:
        f.write(trainer_md)

    logger.info(f"✅ 騎手データを出力しました: {jockey_file}")
    logger.info(f"✅ 厩舎データを出力しました: {trainer_file}")


if __name__ == "__main__":
    # 実行例: 2026年5月4日の保存済みJSONからレポートを生成する場合
    generate_daily_personnel_reports("20260504")
