"""
NkAnalyzer モジュール
競馬データの集計・分析、馬の過去戦績分析、および5大サマリーテーブルの作成を行うコアクラス。
"""

import logging
import pandas as pd
from typing import Union, List, Dict, Any, Optional

from text_utils import (
    time_to_seconds,
    seconds_to_time,
    dataframe_to_markdown_table,
    simplify_track_condition,
)
from report_analyzer import NkReportAnalyzer, prepare_flat_dataframe

logger = logging.getLogger(__name__)


def safe_normalize_dataframe(df: pd.DataFrame) -> pd.DataFrame:
    """DataFrameの文字列正規化（空白除去、開催場の数字除去など）"""
    data = df.copy()

    data.columns = (
        data.columns.astype(str).str.replace(r'[\s\u3000]', '', regex=True)
    )

    for col in data.select_dtypes(include=['object']).columns:
        data[col] = data[col].astype(str).str.strip()

    if "開催" in data.columns:
        data["開催"] = data["開催"].astype(str).str.replace(r"\d+", "", regex=True)

    return data


class NkAnalyzer:
    """競馬データの総合分析およびサマリー作成エンジン"""

    def __init__(self):
        self._report_analyzer = NkReportAnalyzer()

    def refine_data_horse_history(self, history: list[dict]) -> str:
        """
        過去戦績から余計な項目を除去し、ハルシネーション防止策を施したテーブル形式で返す
        """
        if not history or len(history) <= 1:
            return "> **【制約事項】**\n> 過去データはありません。\n\n| データなし |\n|:---|\n| データなし |\n\n"

        df = pd.DataFrame(history[1:], columns=history[0])
        norm_df = safe_normalize_dataframe(df)

        target_columns = [
            "日付",
            "開催",
            "天気",
            "R",
            "レース名",
            "頭数",
            "枠番",
            "馬番",
            "オッズ",
            "人気",
            "着順",
            "騎手",
            "斤量",
            "距離",
            "馬場",
            "タイム",
            "着差",
            "通過",
            "上り",
            "馬体重",
            "勝ち馬(2着馬)",
        ]
        existing_cols = [col for col in target_columns if col in norm_df.columns]
        filtered_df = norm_df[existing_cols]

        return dataframe_to_markdown_table(filtered_df)

    def analyze_horse_history(self, history: list[dict]) -> str:
        """
        過去レースデータを分析し、予想ロジックに特化した5大サマリーのマークダウンを生成する
        """
        if not history or len(history) <= 1:
            return "> **【制約事項】**\n> 過去データはありません。\n\n| データなし |\n|:---|\n| データなし |\n\n"

        df = pd.DataFrame(history[1:], columns=history[0])
        norm_df = safe_normalize_dataframe(df)

        # 5大分析サマリーの作成
        corner_df = self.create_corner_position_summary(norm_df)                 # 1. コーナー位置取り力
        venue_dist_df = self.create_venue_distance_performance_summary(norm_df)  # 2. コース・距離別実績
        track_cond_df = self.create_track_condition_performance_summary(norm_df) # 3. 馬場状態別パフォーマンス
        draw_bias_df = self.create_draw_bias_risk_summary(norm_df)               # 4. 枠番傾向＆包まれリスク
        recent_form_df = self.create_recent_class_form_summary(norm_df)          # 5. 近走クラス＆着差信頼度

        # マークダウンテーブル変換
        corner_text = dataframe_to_markdown_table(corner_df)
        venue_dist_text = dataframe_to_markdown_table(venue_dist_df)
        track_cond_text = dataframe_to_markdown_table(track_cond_df)
        draw_bias_text = dataframe_to_markdown_table(draw_bias_df)
        recent_form_text = dataframe_to_markdown_table(recent_form_df)

        result = []

        # 整形（Markdown組み立て）
        result.append("##### 1. コーナー位置取り力サマリー\n\n")
        result.append(corner_text)

        result.append("##### 2. コース・距離別実績サマリー\n\n")
        result.append(venue_dist_text)

        result.append("##### 3. 馬場状態（良稍 vs 重不）別パフォーマンスサマリー\n\n")
        result.append(track_cond_text)

        result.append("##### 4. 枠番傾向＆包まれリスク・サマリー\n\n")
        result.append(draw_bias_text)

        result.append("##### 5. 近走クラス・勝ち馬との着差＆人気信頼度サマリー\n\n")
        result.append(recent_form_text)

        return "".join(result)

    def create_corner_position_summary(self, df: pd.DataFrame) -> pd.DataFrame:
        """1. コーナー位置取り力サマリーを作成する"""
        data = df.copy()

        if "通過" not in data.columns:
            return pd.DataFrame(columns=["コーナー", "対象レース数", "3番手以内率", "平均通過順位"])

        records = []
        for _, row in data.iterrows():
            passing_str = row["通過"]
            if pd.isna(passing_str) or not isinstance(passing_str, str):
                continue
            positions = [int(p) for p in passing_str.split("-") if p.isdigit()]
            if not positions:
                continue
            records.append(positions)

        if not records:
            return pd.DataFrame(columns=["コーナー", "対象レース数", "3番手以内率", "平均通過順位"])

        corner_stats = {1: [], 2: [], 3: [], 4: []}
        for pos_list in records:
            for i, pos in enumerate(pos_list[:4], start=1):
                corner_stats[i].append(pos)

        summary_rows = []
        corner_names = {1: "1角", 2: "2角", 3: "3角", 4: "4角"}

        for c_num, pos_list in corner_stats.items():
            if not pos_list:
                continue
            total = len(pos_list)
            top3_count = sum(1 for p in pos_list if p <= 3)
            top3_rate = round(top3_count / total * 100, 1)
            avg_pos = round(sum(pos_list) / total, 1)

            summary_rows.append({
                "コーナー": corner_names[c_num],
                "対象レース数": total,
                "3番手以内率": f"{top3_rate}%",
                "平均通過順位": f"{avg_pos}番手"
            })

        return pd.DataFrame(summary_rows)

    def create_venue_distance_performance_summary(self, df: pd.DataFrame) -> pd.DataFrame:
        """2. コース・距離別実績サマリーを作成する"""
        data = df.copy()

        if "開催" not in data.columns or "距離" not in data.columns or "着順" not in data.columns:
            return pd.DataFrame(columns=["競馬場・距離", "出走数", "勝利数", "連対数", "複勝数", "勝率", "連対率", "複勝率", "最速タイム", "平均タイム"])

        data["着順"] = pd.to_numeric(data["着順"], errors="coerce")
        data["タイム_秒"] = data["タイム"].apply(time_to_seconds) if "タイム" in data.columns else None

        data["場・距離"] = data["開催"].astype(str) + data["距離"].astype(str)

        data["is_win"] = (data["着順"] == 1).astype(int)
        data["is_top2"] = (data["着順"] <= 2).astype(int)
        data["is_top3"] = (data["着順"] <= 3).astype(int)

        grouped = (
            data.groupby("場・距離")
            .agg(
                出走数=("着順", "count"),
                勝利数=("is_win", "sum"),
                連対数=("is_top2", "sum"),
                複勝数=("is_top3", "sum"),
                最速秒=("タイム_秒", "min"),
                平均秒=("タイム_秒", "mean"),
            )
            .reset_index()
        )

        grouped["勝率"] = (grouped["勝利数"] / grouped["出走数"] * 100).round(1).astype(str) + "%"
        grouped["連対率"] = (grouped["連対数"] / grouped["出走数"] * 100).round(1).astype(str) + "%"
        grouped["複勝率"] = (grouped["複勝数"] / grouped["出走数"] * 100).round(1).astype(str) + "%"

        grouped["最速タイム"] = grouped["最速秒"].apply(seconds_to_time)
        grouped["平均タイム"] = grouped["平均秒"].apply(seconds_to_time)

        grouped = grouped.sort_values(by="出走数", ascending=False).reset_index(drop=True)

        result_df = grouped[[
            "場・距離",
            "出走数",
            "勝利数",
            "連対数",
            "複勝数",
            "勝率",
            "連対率",
            "複勝率",
            "最速タイム",
            "平均タイム",
        ]].rename(columns={"場・距離": "競馬場・距離"})

        return result_df

    def create_track_condition_performance_summary(self, df: pd.DataFrame) -> pd.DataFrame:
        """3. 【馬場バイアス対応】馬場状態（良稍 vs 重不）別パフォーマンスサマリー"""
        data = df.copy()
        if "馬場" not in data.columns or "着順" not in data.columns:
            return pd.DataFrame(columns=["馬場コンディション", "出走数", "平均着順", "勝利数", "勝率", "連対数", "連対率", "複勝数", "複勝率"])

        data["着順"] = pd.to_numeric(data["着順"], errors="coerce")
        data["馬場区分"] = data["馬場"].apply(simplify_track_condition)
        data["馬場区分"] = data["馬場区分"].replace("", "不明")

        data["is_win"] = (data["着順"] == 1).astype(int)
        data["is_top2"] = (data["着順"] <= 2).astype(int)
        data["is_top3"] = (data["着順"] <= 3).astype(int)

        grouped = (
            data.groupby("馬場区分")
            .agg(
                出走数=("着順", "count"),
                平均着順=("着順", "mean"),
                勝利数=("is_win", "sum"),
                連対数=("is_top2", "sum"),
                複勝数=("is_top3", "sum"),
            )
            .reset_index()
        )

        grouped["平均着順"] = grouped["平均着順"].round(1)
        grouped["勝率"] = (grouped["勝利数"] / grouped["出走数"] * 100).round(1).astype(str) + "%"
        grouped["連対率"] = (grouped["連対数"] / grouped["出走数"] * 100).round(1).astype(str) + "%"
        grouped["複勝率"] = (grouped["複勝数"] / grouped["出走数"] * 100).round(1).astype(str) + "%"

        result_df = grouped[[
            "馬場区分",
            "出走数",
            "平均着順",
            "勝利数",
            "勝率",
            "連対数",
            "連対率",
            "複勝数",
            "複勝率",
        ]].rename(columns={"馬場区分": "馬場コンディション"})

        return result_df

    def create_draw_bias_risk_summary(self, df: pd.DataFrame) -> pd.DataFrame:
        """4. 【枠番バイアス対応】枠番傾向＆包まれリスク・サマリー"""
        data = df.copy()
        if "枠番" not in data.columns or "着順" not in data.columns:
            return pd.DataFrame(columns=["枠順カテゴリ", "出走数", "平均着順", "勝利数", "勝率", "連対数", "複勝率"])

        data["着順"] = pd.to_numeric(data["着順"], errors="coerce")
        data["枠番_num"] = pd.to_numeric(data["枠番"], errors="coerce")

        def categorize_draw(w):
            if pd.isna(w):
                return "不明"
            if w in [1, 2]:
                return "内枠 (1〜2枠)"
            elif w in [3, 4, 5, 6]:
                return "中枠 (3〜6枠)"
            elif w in [7, 8]:
                return "外枠 (7〜8枠)"
            return "不明"

        data["枠順カテゴリ"] = data["枠番_num"].apply(categorize_draw)

        data["is_win"] = (data["着順"] == 1).astype(int)
        data["is_top2"] = (data["着順"] <= 2).astype(int)
        data["is_top3"] = (data["着順"] <= 3).astype(int)

        grouped = (
            data.groupby("枠順カテゴリ")
            .agg(
                出走数=("着順", "count"),
                平均着順=("着順", "mean"),
                勝利数=("is_win", "sum"),
                連対数=("is_top2", "sum"),
                複勝数=("is_top3", "sum"),
            )
            .reset_index()
        )

        grouped["平均着順"] = grouped["平均着順"].round(1)
        grouped["勝率"] = (grouped["勝利数"] / grouped["出走数"] * 100).round(1).astype(str) + "%"
        grouped["連対率"] = (grouped["連対数"] / grouped["出走数"] * 100).round(1).astype(str) + "%"
        grouped["複勝率"] = (grouped["複勝数"] / grouped["出走数"] * 100).round(1).astype(str) + "%"

        category_order = ["内枠 (1〜2枠)", "中枠 (3〜6枠)", "外枠 (7〜8枠)", "不明"]
        grouped["sort_key"] = grouped["枠順カテゴリ"].apply(lambda x: category_order.index(x) if x in category_order else 99)
        grouped = grouped.sort_values("sort_key").drop(columns=["sort_key"]).reset_index(drop=True)

        result_df = grouped[[
            "枠順カテゴリ",
            "出走数",
            "平均着順",
            "勝利数",
            "勝率",
            "連対数",
            "連対率",
            "複勝率",
        ]]

        return result_df

    def create_recent_class_form_summary(self, df: pd.DataFrame, n: int = 5) -> pd.DataFrame:
        """5. 【近走クラス＆着差信頼度】直近N走の着差・人気信頼度サマリー"""
        data = df.copy()

        required_cols = ["日付", "レース名", "着順", "人気"]
        for col in required_cols:
            if col not in data.columns:
                return pd.DataFrame(columns=["指標", "直近5走パフォーマンス"])

        data["着順_num"] = pd.to_numeric(data["着順"], errors="coerce")
        data["人気_num"] = pd.to_numeric(data["人気"], errors="coerce")

        if "日付" in data.columns:
            data["日付_dt"] = pd.to_datetime(data["日付"], errors="coerce")
            data = data.sort_values(by="日付_dt", ascending=False)

        recent = data.head(n)

        if recent.empty:
            return pd.DataFrame(columns=["指標", "直近5走パフォーマンス"])

        valid_ranks = recent["着順_num"].dropna()
        avg_rank = round(valid_ranks.mean(), 1) if not valid_ranks.empty else "データなし"

        valid_pops = recent["人気_num"].dropna()
        avg_pop = round(valid_pops.mean(), 1) if not valid_pops.empty else "データなし"

        top3_count = (recent["着順_num"] <= 3).sum()
        top3_rate = f"{round(top3_count / len(recent) * 100, 1)}%"

        diff_col = "着差" if "着差" in recent.columns else ("勝ち馬(2着馬)" if "勝ち馬(2着馬)" in recent.columns else None)
        diff_str = "データなし"
        if diff_col and diff_col in recent.columns:
            diffs = recent[diff_col].dropna().tolist()
            if diffs:
                diff_str = " / ".join([str(d) for d in diffs[:3]])

        summary_data = [
            {"指標": f"直近{len(recent)}走 平均着順", "直近5走パフォーマンス": f"{avg_rank}着"},
            {"指標": f"直近{len(recent)}走 平均人気", "直近5走パフォーマンス": f"{avg_pop}人気"},
            {"指標": f"直近{len(recent)}走 複勝率", "直近5走パフォーマンス": top3_rate},
            {"指標": "直近3走 着差/相手", "直近5走パフォーマンス": diff_str},
        ]

        return pd.DataFrame(summary_data)

    def normalized_hist(self, df: pd.DataFrame) -> pd.DataFrame:
        """過去戦績のDataFrameを日付順にソートし、数値型を適切にキャストする"""
        data = safe_normalize_dataframe(df)

        if "着順" in data.columns:
            data["着順"] = pd.to_numeric(data["着順"], errors="coerce")
        if "R" in data.columns:
            data["R"] = pd.to_numeric(data["R"], errors="coerce")
        if "日付" in data.columns:
            data["日付"] = pd.to_datetime(data["日付"], errors="coerce")

        return data

    def _prepare_flat_dataframe(self, all_races_data) -> pd.DataFrame:
        """内部共通関数への委譲"""
        return prepare_flat_dataframe(all_races_data)

    # -------------------------------------------------------------
    # レポート生成系メソッド（NkReportAnalyzer への委譲により後方互換性を保持）
    # -------------------------------------------------------------
    def generate_daily_bias_markdown(
        self,
        target_date: str,
        all_races_data,
        race_date_str: str = "",
        venue_str: str = "",
    ) -> str:
        return self._report_analyzer.generate_daily_bias_markdown(
            target_date, all_races_data, race_date_str, venue_str
        )

    def generate_jockey_style_aptitude_markdown(self, all_history_data: list[dict]) -> str:
        return self._report_analyzer.generate_jockey_style_aptitude_markdown(all_history_data)

    def generate_trainer_venue_aptitude_markdown(self, all_history_data: list[dict]) -> str:
        return self._report_analyzer.generate_trainer_venue_aptitude_markdown(all_history_data)
