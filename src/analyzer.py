# ロガー設定
import logging
logger = logging.getLogger(__name__)

import pandas as pd


def time_to_seconds(t_str):
    """ タイム文字列（例: "2:05.6"）を「秒数（数値）」に変換する関数"""
    if pd.isna(t_str) or not isinstance(t_str, str):
        return None
    try:
        parts = t_str.split(":")
        if len(parts) == 2:
            return float(parts[0]) * 60 + float(parts[1])  # 分 * 60 + 秒
        return float(parts[0])
    except ValueError:
        return None

def seconds_to_time(sec):
    """秒数（数値）を "分:秒.厘"（例: "2:04.4"）に戻す関数"""
    if pd.isna(sec):
        return None
    m = int(sec // 60)
    s = sec % 60
    return f"{m}:{s:04.1f}"

def dataframe_to_markdown_table(df: pd.DataFrame) -> str:
    """DataFrameをAIが誤認しにくい厳格なMarkdownテーブルに変換し、ハルシネーション防止用の制約テキストを付与する関数"""
    if df.empty:
        return (
            "> **【制約事項】**\n"
            "> 以下の表に記載されているデータがすべての情報です。表に存在しない事項や数値について、推測・補完して回答してはなりません。\n\n"
            "| データなし |\n"
            "|:---|\n"
            "| データなし |\n\n"
        )

    # 1. コピーを作成し、先に文字列型に変換してから欠損値の置換を行う（Int64型のエラーを防ぐため）
    clean_df = df.copy().astype(str)
    # 文字列としての 'nan', 'None', '<NA>', 空白のみのセルも「データなし」に統一
    clean_df = clean_df.replace(r'^(nan|None|NaN|<NA>|\s*)$', 'データなし', regex=True)
    clean_df = clean_df.fillna("データなし")

    # 2. Markdownテーブルのヘッダーとアラインメント行の作成
    columns = list(clean_df.columns)
    header = "| " + " | ".join(columns) + " |"
    separator = "| " + " | ".join([":---" for _ in columns]) + " |"

    # 3. 各行の構築
    rows = []
    for _, row in clean_df.iterrows():
        row_vals = [str(val).strip() if str(val).strip() != "" else "データなし" for val in row]
        rows.append("| " + " | ".join(row_vals) + " |")

    table_str = "\n".join([header, separator] + rows)

    # 4. 上下に強力なネガティブ制約（境界の明示）を付与
    boxed_text = (
        f"> **【制約事項】**\n"
        f"> 以下の表に記載されているデータがすべての情報です。表に存在しない事項や数値について、推測・補完して回答してはなりません。\n\n"
        f"{table_str}\n\n"
    )
    return boxed_text

def simplify_track_condition(track_str):
    if pd.isna(track_str):
        return ""
    track_str = str(track_str).strip()
    if track_str in ["良", "稍"]:
        return "良稍"
    elif track_str in ["重", "不"]:
        return "重不"
    return track_str


class NkAnalyzer:

    def refine_data_horse_history(self, history: list[dict]) -> str:
        """
        過去戦績から余計な項目を除去し、ハルシネーション防止策を施したテーブル形式で返す
        """
        if not history:
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

    def analyze_horse_history(self, history: list[dict]) -> dict:
        """
        過去レースデータを分析し、予想ロジックに特化した5大サマリーのマークダウンを生成する
        """
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
        data["タイム_秒"] = data["タイム"].apply(time_to_seconds)

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
        ]]
        result_df = result_df.rename(columns={"場・距離": "競馬場・距離"})

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
            return pd.DataFrame(columns=["枠番傾向", "出走数", "平均着順", "勝利数", "勝率", "連対数", "連対率", "複勝数", "複勝率"])

        data["着順"] = pd.to_numeric(data["着順"], errors="coerce")
        data["枠番_数値"] = pd.to_numeric(data["枠番"], errors="coerce")

        def categorize_draw(w):
            if pd.isna(w):
                return "不明"
            if w <= 2:
                return "内枠 (1〜2枠)"
            elif w <= 5:
                return "中枠 (3〜5枠)"
            else:
                return "外枠 (6〜8枠)"

        data["枠番カテゴリ"] = data["枠番_数値"].apply(categorize_draw)

        data["is_win"] = (data["着順"] == 1).astype(int)
        data["is_top2"] = (data["着順"] <= 2).astype(int)
        data["is_top3"] = (data["着順"] <= 3).astype(int)

        grouped = (
            data.groupby("枠番カテゴリ")
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
            "枠番カテゴリ",
            "出走数",
            "平均着順",
            "勝利数",
            "勝率",
            "連対数",
            "連対率",
            "複勝数",
            "複勝率",
        ]].rename(columns={"枠番カテゴリ": "枠番傾向"})

        return result_df

    def create_recent_class_form_summary(self, df: pd.DataFrame, n: int = 5) -> pd.DataFrame:
        """5. 【近走格付け】近走クラス・勝ち馬との着差＆人気信頼度サマリー"""
        data = df.copy()

        if "日付" in data.columns:
            data["日付_dt"] = pd.to_datetime(data["日付"], errors="coerce")
            data = data.sort_values(by="日付_dt", ascending=False).reset_index(drop=True)

        target_cols = ["日付", "開催", "レース名", "頭数", "人気", "着順", "着差", "勝ち馬(2着馬)"]
        available_cols = [col for col in target_cols if col in data.columns]
        
        recent_df = data[available_cols].head(n).copy()

        non_numeric_tokens = ["取", "除", "中", "失", "取消", "除外", "中止", "失格", "データなし", ""]

        if "着順" in recent_df.columns:
            recent_df["着順"] = recent_df["着順"].replace(non_numeric_tokens, pd.NA)
            recent_df["着順"] = pd.to_numeric(recent_df["着順"], errors="coerce").astype("Int64")
        if "人気" in recent_df.columns:
            recent_df["人気"] = recent_df["人気"].replace(non_numeric_tokens, pd.NA)
            recent_df["人気"] = pd.to_numeric(recent_df["人気"], errors="coerce").astype("Int64")

        return recent_df

    def normalized_hist(self, df: pd.DataFrame) -> pd.DataFrame:
        df.columns = df.columns.str.replace(r'[\s\u3000]', '', regex=True)
        for col in df.select_dtypes(include=['object']).columns:
            df[col] = df[col].astype(str).str.strip()
        
        df["着順"] = pd.to_numeric(df["着順"], errors="coerce")
        df["R"] = pd.to_numeric(df["R"], errors="coerce")
        df["日付"] = pd.to_datetime(df["日付"])

        return df

def safe_normalize_dataframe(df: pd.DataFrame) -> pd.DataFrame:
    data = df.copy()

    data.columns = (
        data.columns.astype(str).str.replace(r'[\s\u3000]', '', regex=True)
    )

    for col in data.select_dtypes(include=['object']).columns:
        data[col] = data[col].astype(str).str.strip()

    data["開催"] = data["開催"].astype(str).str.replace(r"\d+", "", regex=True)

    return data