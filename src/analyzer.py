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

    # 1. コピーを作成し、欠損値や空文字をすべて「データなし」に置換（AIの勝手な補完を防ぐ）
    # 修正: 先に全体を文字列型に変換してから欠損値の置換を行う（Int64型のエラーを防ぐため）
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

def sort_yearly_stats_summary(df: pd.DataFrame) -> pd.DataFrame:
    """DataFrameを以下の優先順位でソートする関数

    1. 年: 降順（新しい順）
    2. 条件（距離の数値）: 降順（距離が長い順）
    3. 条件（文字列全体）: 昇順（あるいは任意の順）
    """
    data = df.copy()

    # 1. 「条件」列から距離の数値（例: "1800m" なら 1800）を抽出して一時的な数値カラムを作成
    data["_距離数値"] = (
        data["条件"].str.extract(r"(\d+)m").astype(float).fillna(0)
    )

    # 2. 並び替えの実行
    sorted_df = data.sort_values(
        by=["年", "_距離数値", "条件"], ascending=[False, False, True]
    ).reset_index(drop=True)

    # 3. 追加した一時的な内部用カラムを削除して綺麗に戻す
    sorted_df = sorted_df.drop(columns=["_距離数値"])

    return sorted_df

def classify_tactics(passing_str, total_horses):
    """通過順文字列と頭数から脚質（戦術）を判定する関数"""
    if pd.isna(passing_str) or not isinstance(passing_str, str):
        return "不明"

    try:
        positions = [int(p) for p in passing_str.split("-") if p.isdigit()]
    except ValueError:
        return "不明"

    if not positions or pd.isna(total_horses) or total_horses <= 0:
        return "不明"

    first_pos = positions[0]  # 最初のコーナー通過順
    min_pos = min(positions)  # 最前位置
    max_pos = max(positions)  # 最悪位置
    pos_range = max_pos - min_pos  # 位置の変動幅

    if len(positions) >= 3 and pos_range >= 3 and first_pos != 1:
        return "自在"

    if first_pos == 1:
        return "逃げ"

    relative_pos = first_pos / total_horses

    if relative_pos <= 0.30:
        return "先行"
    elif relative_pos <= 0.65:
        return "差し"
    else:
        return "追込"

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

        # 共通のテーブル変換関数を使用
        return dataframe_to_markdown_table(filtered_df)

    def analyze_horse_history(self, history: list[dict]) -> dict:
        """
        過去レースデータを分析し、ハルシネーション防止策を施したテーブル形式のマークダウンを生成する
        """
        df = pd.DataFrame(history[1:], columns=history[0])
        norm_df = safe_normalize_dataframe(df)

        # 各分析データの作成
        time_df = self.create_yearly_stats_summary(norm_df)
        win_df = self.create_yearly_venue_dist_track_performance(norm_df)
        jockey_df = self.create_jockey_performance(norm_df)
        tac_df, tac_rate_df = self.analyze_tactics_performance(norm_df)
        pop_df = self.create_popularity_performance(norm_df)
        recent_df = self.create_recent_form_summary(norm_df)

        # マークダウン変換（テーブル形式 ＋ ネガティブ制約付き）
        time_text = dataframe_to_markdown_table(time_df)
        win_text = dataframe_to_markdown_table(win_df)
        jockey_text = dataframe_to_markdown_table(jockey_df)
        tac_text = dataframe_to_markdown_table(tac_df)
        tac_rate_text = dataframe_to_markdown_table(tac_rate_df)
        pop_text = dataframe_to_markdown_table(pop_df)
        recent_text = dataframe_to_markdown_table(recent_df)

        result = []

        # 整形（マークダウン文書の組み立て）
        result.append("##### タイム分析\n\n")
        result.append(time_text)

        result.append("##### 勝利分析\n\n")
        result.append(win_text)

        result.append("##### 騎手別分析\n\n")
        result.append(jockey_text)

        result.append("##### 脚質分析\n\n")
        result.append(tac_text)

        result.append("##### 脚質割合\n\n")
        result.append(tac_rate_text)

        result.append("##### 人気オッズ・信頼度分析\n\n")
        result.append(pop_text)

        result.append("##### 近走パフォーマンス分析\n\n")
        result.append(recent_text)

        return "".join(result)

    def create_yearly_stats_summary(self, df: pd.DataFrame) -> pd.DataFrame:
        data = df.copy()

        if "日付" in data.columns:
            data["日付_dt"] = pd.to_datetime(data["日付"], errors="coerce")
            data = data.sort_values(by="日付_dt", ascending=False).reset_index(drop=True)

        data["日付"] = pd.to_datetime(data["日付"], format="mixed", errors="coerce")
        data["年"] = data["日付"].dt.year

        data["種別"] = (
            data["距離"].str.extract(r"([芝ダ])").replace({"ダ": "ダート", "芝": "芝"})
        )
        data["距離_数値"] = data["距離"].str.extract(r"(\d+)").astype(int).astype(str)
        track_condition = data["馬場"].apply(simplify_track_condition)
        data["条件"] = data["種別"] + data["距離_数値"] + "m" + track_condition

        data["斤量_数値"] = pd.to_numeric(data["斤量"], errors="coerce")
        data["斤量表示"] = data["斤量_数値"].apply(lambda x: f"{x:g}kg" if pd.notna(x) else "不明")

        data["タイム_秒"] = data["タイム"].apply(time_to_seconds)
        data["上り"] = pd.to_numeric(data["上り"], errors="coerce")

        grouped = (
            data.groupby(["年", "開催", "条件", "斤量表示"])
            .agg(
                出走数=("着順", "count"),
                タイム最速_秒=("タイム_秒", "min"),
                タイム平均_秒=("タイム_秒", "mean"),
                タイム最低_秒=("タイム_秒", "max"),
                上り最速=("上り", "min"),
                上り平均=("上り", "mean"),
                上り最低=("上り", "max"),
            )
            .reset_index()
        )

        grouped["最速タイム"] = grouped["タイム最速_秒"].apply(seconds_to_time)
        grouped["平均タイム"] = grouped["タイム平均_秒"].apply(seconds_to_time)
        grouped["最低タイム"] = grouped["タイム最低_秒"].apply(seconds_to_time)
        grouped["上り平均"] = grouped["上り平均"].round(1)

        summary_df = grouped[[
            "年",
            "開催",
            "条件",
            "斤量表示",
            "出走数",
            "最速タイム",
            "平均タイム",
            "最低タイム",
            "上り最速",
            "上り平均",
            "上り最低",
        ]]

        summary_df = summary_df.rename(columns={"斤量表示": "斤量"})
        result_df = sort_yearly_stats_summary(summary_df)

        return result_df

    def create_yearly_venue_dist_track_performance(self, df: pd.DataFrame) -> pd.DataFrame:
        data = df.copy()

        if "日付" in data.columns:
            data["日付_dt"] = pd.to_datetime(data["日付"], errors="coerce")
            data = data.sort_values(by="日付_dt", ascending=False).reset_index(drop=True)

        data["日付"] = pd.to_datetime(data["日付"])
        data["年"] = data["日付"].dt.year
        data["着順"] = pd.to_numeric(data["着順"], errors="coerce")

        data["種別"] = (
            data["距離"].str.extract(r"([芝ダ])").replace({"ダ": "ダート", "芝": "芝"})
        )
        data["距離_数値"] = data["距離"].str.extract(r"(\d+)").astype(int).astype(str)

        track_condition = data["馬場"].apply(simplify_track_condition)
        data["条件"] = data["種別"] + data["距離_数値"] + "m" + track_condition

        data["is_win"] = (data["着順"] == 1).astype(int)
        data["is_top2"] = (data["着順"] <= 2).astype(int)
        data["is_top3"] = (data["着順"] <= 3).astype(int)
        data["is_top5"] = (data["着順"] <= 5).astype(int)

        summary = (
            data.groupby(["年", "開催", "条件"])
            .agg(
                出走数=("着順", "count"),
                勝利数=("is_win", "sum"),
                連対数=("is_top2", "sum"),
                複勝圏内数=("is_top3", "sum"),
                掲示板数=("is_top5", "sum"),
            )
            .reset_index()
        )

        summary["勝率"] = (
            (summary["勝利数"] / summary["出走数"] * 100).round(1).astype(str) + "%"
        )
        summary["連対率"] = (
            (summary["連対数"] / summary["出走数"] * 100).round(1).astype(str) + "%"
        )
        summary["複勝率"] = (
            (summary["複勝圏内数"] / summary["出走数"] * 100).round(1).astype(str) + "%"
        )
        summary["掲示板率"] = (
            (summary["掲示板数"] / summary["出走数"] * 100).round(1).astype(str) + "%"
        )

        result_df = sort_yearly_stats_summary(summary)

        return result_df

    def analyze_tactics_performance(self, df: pd.DataFrame):
        data = df.copy()

        data["頭数"] = pd.to_numeric(data["頭数"], errors="coerce")
        data["着順"] = pd.to_numeric(data["着順"], errors="coerce")

        data["脚質"] = data.apply(
            lambda row: classify_tactics(row["通過"], row["頭数"]), axis=1
        )

        data["is_win"] = (data["着順"] == 1).astype(int)
        data["is_top2"] = (data["着順"] <= 2).astype(int)
        data["is_top3"] = (data["着順"] <= 3).astype(int)

        race_list = data[["日付", "開催", "レース名", "頭数", "通過", "脚質", "着順"]]

        total_races = len(data)
        summary = (
            data.groupby(["脚質"])
            .agg(
                出走数=("着順", "count"),
                勝利数=("is_win", "sum"),
                連対数=("is_top2", "sum"),
                複勝数=("is_top3", "sum"),
            )
            .reset_index()
        )

        # 0除算防止
        if total_races > 0:
            summary["戦術割合"] = (
                (summary["出走数"] / total_races * 100).round(1).astype(str) + "%"
            )
        else:
            summary["戦術割合"] = "0.0%"

        summary["勝率"] = (
            (summary["勝利数"] / summary["出走数"] * 100).round(1).astype(str) + "%"
        )
        summary["連対率"] = (
            (summary["連対数"] / summary["出走数"] * 100).round(1).astype(str) + "%"
        )
        summary["複勝率"] = (
            (summary["複勝数"] / summary["出走数"] * 100).round(1).astype(str) + "%"
        )

        summary = summary[[
            "脚質",
            "出走数",
            "戦術割合",
            "勝利数",
            "勝率",
            "連対数",
            "連対率",
            "複勝数",
            "複勝率",
        ]]

        return race_list, summary

    def create_jockey_performance(self, df: pd.DataFrame) -> pd.DataFrame:
        data = df.copy()
        data["着順"] = pd.to_numeric(data["着順"], errors="coerce")

        if "騎手" not in data.columns:
            return pd.DataFrame(columns=["騎手", "騎乗数", "勝利数", "勝率", "連対率", "複勝率"])
        
        data["騎手"] = data["騎手"].fillna("不明").astype(str).str.strip()

        data["is_win"] = (data["着順"] == 1).astype(int)
        data["is_top2"] = (data["着順"] <= 2).astype(int)
        data["is_top3"] = (data["着順"] <= 3).astype(int)

        summary = (
            data.groupby(["騎手"])
            .agg(
                騎乗数=("着順", "count"),
                勝利数=("is_win", "sum"),
                連対数=("is_top2", "sum"),
                複勝数=("is_top3", "sum"),
            )
            .reset_index()
        )

        summary["勝率"] = (summary["勝利数"] / summary["騎乗数"] * 100).round(1).astype(str) + "%"
        summary["連対率"] = (summary["連対数"] / summary["騎乗数"] * 100).round(1).astype(str) + "%"
        summary["複勝率"] = (summary["複勝数"] / summary["騎乗数"] * 100).round(1).astype(str) + "%"

        summary = summary.sort_values(by="騎乗数", ascending=False).reset_index(drop=True)

        summary = summary[[
            "騎手",
            "騎乗数",
            "勝利数",
            "勝率",
            "連対数",
            "連対率",
            "複勝数",
            "複勝率",
        ]]

        return summary

    def create_popularity_performance(self, df: pd.DataFrame) -> pd.DataFrame:
        data = df.copy()

        if "人気" not in data.columns or "着順" not in data.columns:
            return pd.DataFrame(columns=["人気帯", "出走数", "平均着順", "勝利数", "勝率", "複勝率"])

        data["人気"] = pd.to_numeric(data["人気"], errors="coerce")
        data["着順"] = pd.to_numeric(data["着順"], errors="coerce")
        data = data.dropna(subset=["人気", "着順"])

        if data.empty:
            return pd.DataFrame(columns=["人気帯", "出走数", "平均着順", "勝利数", "勝率", "複勝率"])

        def categorize_popularity(p):
            if p <= 3:
                return "1〜3番人気 (上位)"
            elif p <= 6:
                return "4〜6番人気 (中位)"
            elif p <= 10:
                return "7〜10番人気 (下位)"
            else:
                return "11番人気以上 (穴)"

        data["人気帯"] = data["人気"].apply(categorize_popularity)

        data["is_win"] = (data["着順"] == 1).astype(int)
        data["is_top3"] = (data["着順"] <= 3).astype(int)

        summary = (
            data.groupby(["人気帯"])
            .agg(
                出走数=("着順", "count"),
                平均着順=("着順", "mean"),
                勝利数=("is_win", "sum"),
                複勝数=("is_top3", "sum"),
            )
            .reset_index()
        )

        summary["平均着順"] = summary["平均着順"].round(1)
        summary["勝率"] = (summary["勝利数"] / summary["出走数"] * 100).round(1).astype(str) + "%"
        summary["複勝率"] = (summary["複勝数"] / summary["出走数"] * 100).round(1).astype(str) + "%"

        summary = summary[[
            "人気帯",
            "出走数",
            "平均着順",
            "勝利数",
            "勝率",
            "複勝数",
            "複勝率",
        ]]

        return summary

    def create_recent_form_summary(self, df: pd.DataFrame, n: int = 5) -> pd.DataFrame:
        data = df.copy()

        if "日付" in data.columns:
            data["日付_dt"] = pd.to_datetime(data["日付"], errors="coerce")
            data = data.sort_values(by="日付_dt", ascending=False).reset_index(drop=True)

        target_cols = ["日付", "開催", "レース名", "頭数", "着順", "着差", "上がり", "人気", "脚質"]
        available_cols = [col for col in target_cols if col in data.columns]
        
        recent_df = data[available_cols].head(n).copy()

        # 「取消」や「除外」などの非数値文字列を事前に NaN / pd.NA に置換する
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