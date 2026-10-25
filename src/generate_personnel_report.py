# ロガー設定
import logging
logger = logging.getLogger(__name__)

import json
from pathlib import Path
from src.analyzer import NkAnalyzer  # 先ほど作成した分析クラスをインポート


def generate_daily_personnel_reports(target_date: str, is_test: bool = False):
    """
    指定した日付（YYYYMMDD形式）の保存済みJSONファイルをすべて読み込み、
    全場横断の「騎手データ」と「厩舎データ」のMarkdownファイルを生成・出力する
    
    Parameters:
    - target_date: 対象日付（例: "20260504"）
    - is_test: テスト環境かどうか
    """
    base_dir = Path("data_test/results") if is_test else Path("data/results")
    output_dir = "data_test/analysis" if is_test else "data/analysis"
    
    # 1. target_date（例: "20260504"）から年・月を切り出してディレクトリを特定
    if len(target_date) >= 8:
        year = target_date[:4]
        month = target_date[4:6]
        search_dir = base_dir / year / month
    else:
        search_dir = base_dir

    if not search_dir.exists():
        logger.error(f"指定された日付のディレクトリが存在しません: {search_dir}")
        return

    # 2. 該当する日付のJSONファイルをすべて検索 (例: 20260504*-result-*.json)
    pattern = f"{target_date[:4]}*-result-*.json"
    json_files = list(search_dir.glob(pattern))

    if not json_files:
        logger.error(f"該当する日付のJSONファイルが見つかりません (検索パターン: {pattern})")
        return

    # 3. 該当日の全レース（全会場）の結果データを1つのリストに統合
    all_races_flat_data = []
    for file_path in json_files:
        try:
            with open(file_path, "r", encoding="utf-8") as f:
                payload = json.load(f)
                
                # ルートにある開催会場名（例: "新潟"）を取得
                race_track = payload.get("race_track", "不明")
                
                # JSON内の "results" キーから各馬の成績リストを取得
                results = payload.get("results", [])
                if isinstance(results, list):
                    # 各馬の辞書データにルートの "race_track" を "開催" キーとして追加する
                    for horse_result in results:
                        if isinstance(horse_result, dict):
                            horse_result["開催"] = race_track
                        all_races_flat_data.append(horse_result)
        except Exception as e:
            logger.error(f"ファイル読み込みエラー ({file_path}): {e}")

    if not all_races_flat_data:
        logger.error("統合できる有効なレース結果データがありません。")
        return

    # 4. NkAnalyzer インスタンスの生成
    analyzer = NkAnalyzer()

    # 5. 騎手データ・厩舎データのMarkdown文字列を生成
    jockey_md = analyzer.generate_jockey_style_aptitude_markdown(all_races_flat_data)
    trainer_md = analyzer.generate_trainer_venue_aptitude_markdown(all_races_flat_data)

    # 6. 出力先ディレクトリの作成
    out_path = Path(output_dir)
    out_path.mkdir(parents=True, exist_ok=True)

    # 7. それぞれのMarkdownファイルとして書き出し
    jockey_file = out_path / f"{target_date}_jockey_trend.md"
    trainer_file = out_path / f"{target_date}_trainer_trend.md"

    with open(jockey_file, "w", encoding="utf-8") as f:
        f.write(jockey_md)
    
    with open(trainer_file, "w", encoding="utf-8") as f:
        f.write(trainer_md)

    logger.info(f"✅ 騎手データを出力しました: {jockey_file}")
    logger.info(f"✅ 厩舎データを出力しました: {trainer_file}")

if __name__ == "__main__":
    # 実行例: 2026年5月4日の保存済みJSONからレポートを生成する場合
    generate_daily_personnel_reports("20260504")