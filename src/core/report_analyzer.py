"""
NkReportAnalyzer モジュール
競馬の各種統計・バイアス・騎手・厩舎適性に関するMarkdownレポートを生成するクラス。
"""

import logging
import pandas as pd
from typing import Union, List, Dict, Any

from src.utils.text_utils import (
    dataframe_to_markdown_table,
    extract_last_corner_pos,
    get_tactics,
    normalize_track_type,
)

logger = logging.getLogger(__name__)

COLUMN_MAPPING = {
    "race_track": "開催",
    "rank": "着順",
    "bracket_num": "枠番",
    "horse_num": "馬番",
    "horse_name": "馬名",
    "horse_age": "性齢",
    "weight_carried": "斤量",
    "jockey": "騎手",
    "jockey_id": "騎手ID",
    "jockey_url": "騎手URL",
    "stable": "厩舎",
    "stable_id": "厩舎ID",
    "time": "タイム",
    "margin": "着差",
    "popularity": "人気",
    "odds": "オッズ",
    "last3f": "上り",
    "passing_order": "通過",
    "horse_weight": "馬体重",
    "weight_diff": "馬体重増減",
    "race_type": "タイプ",
    "race_distance": "距離",
}


def prepare_flat_dataframe(all_races_data: Union[List[Dict[str, Any]], Dict[str, Any]]) -> pd.DataFrame:
    """入力データをフラットなDataFrameに正規化し、英語キーを日本語キーにマッピングする共通関数"""
    if not all_races_data:
        return pd.DataFrame()

    if isinstance(all_races_data, dict):
        flat_data = []
        for race_key, race_list in all_races_data.items():
            if isinstance(race_list, list):
                flat_data.extend(race_list)
    else:
        flat_data = all_races_data

    if not flat_data:
        return pd.DataFrame()

    df = pd.DataFrame(flat_data)
    df.columns = df.columns.astype(str).str.replace(r'[\s\u3000]', '', regex=True)

    df = df.rename(columns=COLUMN_MAPPING)
    return df


class NkReportAnalyzer:
    """Markdown形式の各種競馬レポート（バイアス・騎手適性・厩舎適性）生成クラス"""

    def generate_daily_bias_markdown(
        self,
        target_date: str,
        all_races_data: Union[List[Dict[str, Any]], Dict[str, Any]],
        race_date_str: str = "",
        venue_str: str = "",
    ) -> str:
        """
        全レース分のデータをまとめたものから当該日バイアスを解析し、Markdownを生成する（ID主体管理）
        """
        df = prepare_flat_dataframe(all_races_data)
        if df.empty:
            return "# 当該日レース傾向・馬場バイアス分析データ\n\n有効なデータが存在しません。"

        non_numeric_tokens = ["取", "除", "中", "失", "取消", "除外", "中止", "失格", "データなし", ""]

        # 着順の数値化
        if "着順" in df.columns:
            df["着順"] = df["着順"].replace(non_numeric_tokens, pd.NA)
            df["着順"] = pd.to_numeric(df["着順"], errors="coerce")

        # 枠番の調整
        if "枠" in df.columns and "枠番" not in df.columns:
            df["枠番"] = df["枠"]
        if "枠番" in df.columns:
            df["枠番"] = pd.to_numeric(df["枠番"], errors="coerce")

        if "人気" in df.columns:
            df["人気"] = pd.to_numeric(df["人気"], errors="coerce")

        # 勝率・連対率・複勝率計算用のフラグ
        df["is_win"] = (df["着順"] == 1).fillna(False).astype(int)
        df["is_top2"] = (df["着順"].le(2)).fillna(False).astype(int)
        df["is_top3"] = (df["着順"].le(3)).fillna(False).astype(int)

        # 1. 枠番・馬番別のバイアス集計
        draw_summary_df = pd.DataFrame()
        if "枠番" in df.columns:
            draw_grouped = df.groupby("枠番").agg(
                出走頭数=("着順", "count"),
                勝利数=("is_win", "sum"),
                連対数=("is_top2", "sum"),
                複勝数=("is_top3", "sum"),
            ).reset_index()

            draw_grouped["勝率"] = (draw_grouped["勝利数"] / draw_grouped["出走頭数"] * 100).round(1).astype(str) + "%"
            draw_grouped["連対率"] = (draw_grouped["連対数"] / draw_grouped["出走頭数"] * 100).round(1).astype(str) + "%"
            draw_grouped["複勝率"] = (draw_grouped["複勝数"] / draw_grouped["出走頭数"] * 100).round(1).astype(str) + "%"
            draw_summary_df = draw_grouped[["枠番", "出走頭数", "勝利数", "勝率", "連対数", "連対率", "複勝数", "複勝率"]]

        # 2. 脚質・4角ポジション別の残存率集計
        corner_summary_df = pd.DataFrame()
        if "通過" in df.columns:
            df["4角順位"] = df["通過"].apply(extract_last_corner_pos)

            def categorize_4th_corner(pos):
                if pd.isna(pos):
                    return "不明"
                if pos == 1:
                    return "1番手 (逃げ)"
                elif pos <= 3:
                    return "2〜3番手 (好位・先行)"
                elif pos <= 5:
                    return "4〜5番手 (中団前)"
                else:
                    return "6番手以降 (中団後・追込)"

            df["4角位置帯"] = df["4角順位"].apply(categorize_4th_corner)

            corner_grouped = df.groupby("4角位置帯").agg(
                該当頭数=("着順", "count"),
                勝利数=("is_win", "sum"),
                連対数=("is_top2", "sum"),
                複勝数=("is_top3", "sum"),
            ).reset_index()

            corner_grouped["勝率"] = (corner_grouped["勝利数"] / corner_grouped["該当頭数"] * 100).round(1).astype(str) + "%"
            corner_grouped["連対率"] = (corner_grouped["連対数"] / corner_grouped["該当頭数"] * 100).round(1).astype(str) + "%"
            corner_grouped["複勝率"] = (corner_grouped["複勝数"] / corner_grouped["該当頭数"] * 100).round(1).astype(str) + "%"

            category_order = ["1番手 (逃げ)", "2〜3番手 (好位・先行)", "4〜5番手 (中団前)", "6番手以降 (中団後・追込)", "不明"]
            corner_grouped["sort_key"] = corner_grouped["4角位置帯"].apply(lambda x: category_order.index(x) if x in category_order else 99)
            corner_grouped = corner_grouped.sort_values("sort_key").drop(columns=["sort_key"]).reset_index(drop=True)

            corner_summary_df = corner_grouped[["4角位置帯", "該当頭数", "勝利数", "勝率", "連対数", "連対率", "複勝数", "複勝率"]]

        # 3. 当日騎手・厩舎トレンド集計（ID主体管理）
        jockey_summary_df = pd.DataFrame()
        if "騎手ID" in df.columns:
            jockey_grouped = df.groupby("騎手ID").agg(
                騎手=("騎手", lambda x: x.mode()[0] if not x.mode().empty else "不明"),
                騎乗数=("着順", "count"),
                勝利数=("is_win", "sum"),
                連対数=("is_top2", "sum"),
                複勝数=("is_top3", "sum"),
            ).reset_index()

            jockey_grouped["勝率"] = (jockey_grouped["勝利数"] / jockey_grouped["騎乗数"] * 100).round(1).astype(str) + "%"
            jockey_grouped["複勝率"] = (jockey_grouped["複勝数"] / jockey_grouped["騎乗数"] * 100).round(1).astype(str) + "%"
            jockey_grouped = jockey_grouped.sort_values(by=["勝利数", "複勝数", "騎乗数"], ascending=[False, False, False]).reset_index(drop=True)
            jockey_summary_df = jockey_grouped[["騎手ID", "騎手", "騎乗数", "勝利数", "勝率", "連対数", "複勝数", "複勝率"]].head(10)

        trainer_summary_df = pd.DataFrame()
        if "厩舎ID" in df.columns:
            trainer_grouped = df.groupby("厩舎ID").agg(
                厩舎=("厩舎", lambda x: x.mode()[0] if not x.mode().empty else "不明"),
                出走数=("着順", "count"),
                勝利数=("is_win", "sum"),
                複勝数=("is_top3", "sum"),
            ).reset_index()

            trainer_grouped["勝率"] = (trainer_grouped["勝利数"] / trainer_grouped["出走数"] * 100).round(1).astype(str) + "%"
            trainer_grouped["複勝率"] = (trainer_grouped["複勝数"] / trainer_grouped["出走数"] * 100).round(1).astype(str) + "%"
            trainer_grouped = trainer_grouped.sort_values(by=["勝利数", "複勝数", "出走数"], ascending=[False, False, False]).reset_index(drop=True)
            trainer_summary_df = trainer_grouped[["厩舎ID", "厩舎", "出走数", "勝利数", "勝率", "複勝数", "複勝率"]].head(10)

        # Markdownの組み立て
        year = target_date[:4] if len(target_date) >= 8 else ""
        month = target_date[4:6] if len(target_date) >= 8 else ""
        day = target_date[6:8] if len(target_date) >= 8 else ""

        title_header = f"# {year}-{month}-{day}日傾向・馬場バイアス解析レポート"
        if race_date_str or venue_str:
            title_header = f"# 【{race_date_str} {venue_str}】傾向・馬場バイアス解析レポート"

        md_parts = [
            title_header,
            "\n## 1. 枠番・馬番別バイアスサマリー\n",
            dataframe_to_markdown_table(draw_summary_df),
            "\n## 2. 4角ポジション別残存率サマリー\n",
            dataframe_to_markdown_table(corner_summary_df),
            "\n## 3. 当日好調騎手トップ10（ID管理）\n",
            dataframe_to_markdown_table(jockey_summary_df),
            "\n## 4. 当日好調厩舎トップ10（ID管理）\n",
            dataframe_to_markdown_table(trainer_summary_df),
        ]

        return "".join(md_parts)

    def generate_jockey_style_aptitude_markdown(self, all_history_data: Union[List[Dict[str, Any]], Dict[str, Any]]) -> str:
        """
        蓄積されたレース結果データから「騎手IDベース」で戦術（脚質）適性を分析する
        """
        df = prepare_flat_dataframe(all_history_data)
        if df.empty or "騎手ID" not in df.columns:
            return "# 騎手スタイル・戦術適性分析プロファイル\n\nデータが存在しません。"

        df["着順_num"] = pd.to_numeric(df["着順"], errors="coerce")
        df["is_win"] = (df["着順_num"] == 1).fillna(False).astype(int)
        df["is_top3"] = (df["着順_num"] <= 3).fillna(False).astype(int)

        df["タイプ_norm"] = df["タイプ"].apply(normalize_track_type) if "タイプ" in df.columns else "不明"
        df["展開脚質"] = df["通過"].apply(get_tactics) if "通過" in df.columns else "不明"

        jockey_tactics = df.groupby(["騎手ID", "展開脚質"]).agg(
            騎乗数=("着順_num", "count"),
            勝利数=("is_win", "sum"),
            複勝数=("is_top3", "sum"),
        ).reset_index()

        jockey_tactics["複勝率_num"] = (jockey_tactics["複勝数"] / jockey_tactics["騎乗数"] * 100).round(1)

        jockey_course = df.groupby(["騎手ID", "タイプ_norm"]).agg(
            騎乗数=("着順_num", "count"),
            複勝数=("is_top3", "sum"),
        ).reset_index()
        jockey_course["複勝率_num"] = (jockey_course["複勝数"] / jockey_course["騎乗数"] * 100).round(1)

        results = []
        for j_id, group in jockey_tactics.groupby("騎手ID"):
            total_rides = group["騎乗数"].sum()
            if total_rides < 1:
                continue

            jockey_name = df[df["騎手ID"] == j_id]["騎手"].mode()[0] if "騎手" in df.columns and not df[df["騎手ID"] == j_id]["騎手"].mode().empty else str(j_id)

            best_tactic_row = group.loc[group["複勝率_num"].idxmax()]
            best_tactic = f"{best_tactic_row['展開脚質']} (複勝率:{best_tactic_row['複勝率_num']}%)"

            c_group = jockey_course[jockey_course["騎手ID"] == j_id]
            if not c_group.empty:
                best_course_row = c_group.loc[c_group["複勝率_num"].idxmax()]
                best_course = f"{best_course_row['タイプ_norm']} (複勝率:{best_course_row['複勝率_num']}%)"
            else:
                best_course = "データ不足"

            results.append({
                "騎手ID": j_id,
                "騎手名": jockey_name,
                "通算騎乗数": total_rides,
                "得意戦術 (最高複勝率脚質)": best_tactic,
                "得意コース (芝/ダート)": best_course,
            })

        res_df = pd.DataFrame(results)
        if res_df.empty:
            return "# 騎手スタイル・戦術適性分析プロファイル\n\n条件に合うデータがありません。"

        res_df = res_df.sort_values(by="通算騎乗数", ascending=False).reset_index(drop=True)
        table_text = dataframe_to_markdown_table(res_df)

        return f"# 騎手スタイル・戦術適性分析プロファイル\n\n{table_text}"

    def generate_trainer_venue_aptitude_markdown(self, all_history_data: Union[List[Dict[str, Any]], Dict[str, Any]]) -> str:
        """
        蓄積されたレース結果データから「厩舎IDベース」で会場別適性を分析する
        """
        df = prepare_flat_dataframe(all_history_data)
        if df.empty or "厩舎ID" not in df.columns:
            return "# 厩舎バイタル・会場適性分析プロファイル\n\nデータが存在しません。"

        if "開催" not in df.columns:
            df["開催"] = "当日開催"

        df["着順_num"] = pd.to_numeric(df["着順"], errors="coerce")
        df["is_win"] = (df["着順_num"] == 1).fillna(False).astype(int)
        df["is_top3"] = (df["着順_num"] <= 3).fillna(False).astype(int)

        trainer_venue = df.groupby(["厩舎ID", "開催"]).agg(
            出走数=("着順_num", "count"),
            勝利数=("is_win", "sum"),
            複勝数=("is_top3", "sum"),
        ).reset_index()

        trainer_venue["複勝率_num"] = (trainer_venue["複勝数"] / trainer_venue["出走数"] * 100).round(1)

        results = []
        for t_id, group in trainer_venue.groupby("厩舎ID"):
            total_runs = group["出走数"].sum()
            if total_runs < 1:
                continue

            trainer_name = df[df["厩舎ID"] == t_id]["厩舎"].mode()[0] if "厩舎" in df.columns and not df[df["厩舎ID"] == t_id]["厩舎"].mode().empty else str(t_id)

            total_top3 = df[df["厩舎ID"] == t_id]["is_top3"].sum()
            overall_top3_rate = f"{round(total_top3 / total_runs * 100, 1)}%"

            if not group.empty:
                best_row = group.loc[group["複勝率_num"].idxmax()]
                best_venue = f"{best_row['開催']} (複勝率:{best_row['複勝率_num']}%)"
                worst_row = group.loc[group["複勝率_num"].idxmin()]
                worst_venue = f"{worst_row['開催']} (複勝率:{worst_row['複勝率_num']}%)"
            else:
                best_venue, worst_venue = "データ不足", "データ不足"

            results.append({
                "厩舎ID": t_id,
                "厩舎名": trainer_name,
                "総出走数": total_runs,
                "通算複勝率": overall_top3_rate,
                "得意競馬場（輸送・コース適性）": best_venue,
                "苦手競馬場（遠征苦戦等）": worst_venue,
            })

        res_df = pd.DataFrame(results)
        if res_df.empty:
            return "# 厩舎バイタル・会場適性分析プロファイル\n\n条件に合うデータがありません。"

        res_df = res_df.sort_values(by="総出走数", ascending=False).reset_index(drop=True)
        table_text = dataframe_to_markdown_table(res_df)

        return f"# 厩舎バイタル・会場適性分析プロファイル\n\n{table_text}"
