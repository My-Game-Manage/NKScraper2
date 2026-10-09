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

def classify_tactics(passing_str, total_horses):
    """通過順文字列と頭数から脚質（戦術）を判定する関数"""
    if pd.isna(passing_str) or not isinstance(passing_str, str):
        return "不明"

    # "1-1-1-1" -> [1, 1, 1, 1] に変換
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

    # 1. 自在の判定：道中の順位変動が激しい（例: 4番手→5番手→2番手→5番手など上下動が大きい）
    if len(positions) >= 3 and pos_range >= 3 and first_pos != 1:
        # 途中で大きく押し上げたり後退したりした場合
        return "自在"

    # 2. 逃げの判定：最初のコーナーが1番手、またはほぼ先頭キープ
    if first_pos == 1:
        return "逃げ"

    # 3. 頭数に対する相対位置の算出（割合）
    relative_pos = first_pos / total_horses

    # 4. 前半の位置取りによる分類
    if relative_pos <= 0.30:
        return "先行"
    elif relative_pos <= 0.65:
        return "差し"
    else:
        return "追込"


class NkAnalyzer:

    def analyze_horse_history(self, history: list[dict]) -> dict:
        """
        過去レースデータを分析し、必要な項目に集計、計算する
        """
        # DataFrame変換
        df = pd.DataFrame(history[1:], columns=history[0])

        # 数値等に変換
        #norm_df = self.normalized_hist(df)
        norm_df = safe_normalize_dataframe(df)

        # タイム別
        time_df = self.create_yearly_stats_summary(norm_df)
        # 条件別勝利
        win_df = self.create_yearly_venue_dist_track_performance(norm_df)
        # 戦術別
        tac_df, tac_rate_df = self.analyze_tactics_performance(norm_df)

        # マークダウン変換
        time_md = time_df.to_markdown()
        win_md = win_df.to_markdown()
        tac_md = tac_df.to_markdown()
        tac_rate_md = tac_rate_df.to_markdown()

        result = []

        # 整形
        result.append(f"#### タイム分析\n\n")
        result.append(time_md + "\n\n")
        result.append(f"#### 勝利分析\n\n")
        result.append(win_md + "\n\n")
        result.append(f"#### 脚質分析\n\n")
        result.append(tac_md + "\n\n")
        result.append(f"#### 脚質割合\n\n")
        result.append(tac_rate_md + "\n\n")
        # 統合
        return "".join(result)

    def create_yearly_stats_summary(self, df: pd.DataFrame) -> pd.DataFrame:
        # コピーを作成して前処理
        data = df.copy()

        # 日付から「年」を抽出
        data["日付"] = pd.to_datetime(data["日付"], format="mixed", errors="coerce")
        data["年"] = data["日付"].dt.year

        # 「距離」列（例: "ダ1900"）から種別と距離を抽出して結合（例: "ダート1900m"）
        data["種別"] = (
            data["距離"].str.extract(r"([芝ダ])").replace({"ダ": "ダート", "芝": "芝"})
        )
        data["距離_数値"] = data["距離"].str.extract(r"(\d+)").astype(int).astype(str)
        # 「馬場」状態を結合して「ダート1600m不」のような条件文字列を作成
        track_condition = data["馬場"].fillna("")  # 欠損値対策
        data["条件"] = data["種別"] + data["距離_数値"] + "m" + track_condition

        # 計算用カラム作成
        data["タイム_秒"] = data["タイム"].apply(time_to_seconds)
        data["上り"] = pd.to_numeric(data["上り"], errors="coerce")

        # 年・開催・条件でグループ化して一括集計
        # ※ タイムは秒数が小さい方が「最速」、大きい方が「最低（ワースト）」
        grouped = (
            data.groupby(["年", "開催", "条件"])
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

        # 秒数を表示用のタイムフォーマットに整形
        grouped["最速タイム"] = grouped["タイム最速_秒"].apply(seconds_to_time)
        grouped["平均タイム"] = grouped["タイム平均_秒"].apply(seconds_to_time)
        grouped["最低タイム"] = grouped["タイム最低_秒"].apply(seconds_to_time)

        # 上り平均の小数点を1桁に丸める
        grouped["上り平均"] = grouped["上り平均"].round(1)

        # 必要なカラム順に整理
        summary_df = grouped[[
            "年",
            "開催",
            "条件",
            "出走数",
            "最速タイム",
            "平均タイム",
            "最低タイム",
            "上り最速",
            "上り平均",
            "上り最低",
        ]]

        return summary_df

    def create_yearly_venue_dist_track_performance(self, df: pd.DataFrame) -> pd.DataFrame:
        """年・開催場所・条件（種別＆距離＋馬場状態）ごとに着順実績と各種割合を集計する"""
        data = df.copy()

        # 1. 前処理：日付から「年」を抽出し、着順を数値型に変換
        data["日付"] = pd.to_datetime(data["日付"])
        data["年"] = data["日付"].dt.year
        data["着順"] = pd.to_numeric(data["着順"], errors="coerce")

        # 「距離」列（例: "ダ1900"）から種別と距離を抽出
        data["種別"] = (
            data["距離"].str.extract(r"([芝ダ])").replace({"ダ": "ダート", "芝": "芝"})
        )
        data["距離_数値"] = data["距離"].str.extract(r"(\d+)").astype(int).astype(str)

        # 「馬場」状態を結合して「ダート1600m不」のような条件文字列を作成
        track_condition = data["馬場"].fillna("")  # 欠損値対策
        data["条件"] = data["種別"] + data["距離_数値"] + "m" + track_condition

        # 2. 条件判定フラグの作成
        data["is_win"] = (data["着順"] == 1).astype(int)  # 1着
        data["is_top2"] = (data["着順"] <= 2).astype(int)  # 2着以内
        data["is_top3"] = (data["着順"] <= 3).astype(int)  # 3着以内
        data["is_top5"] = (data["着順"] <= 5).astype(int)  # 5着以内（掲示板）

        # 3. 年・開催・条件（馬場含む）でグループ化して集計
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

        # 4. 各到達率（%）の計算
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

        return summary

    def analyze_tactics_performance(self, df: pd.DataFrame):
        data = df.copy()

        # 前処理：数値型への変換
        data["頭数"] = pd.to_numeric(data["頭数"], errors="coerce")
        data["着順"] = pd.to_numeric(data["着順"], errors="coerce")

        # 各レースの脚質を判定
        data["脚質"] = data.apply(
            lambda row: classify_tactics(row["通過"], row["頭数"]), axis=1
        )

        # 着順フラグ
        data["is_win"] = (data["着順"] == 1).astype(int)  # 1着
        data["is_top2"] = (data["着順"] <= 2).astype(int)  # 2着以内（連対）
        data["is_top3"] = (data["着順"] <= 3).astype(int)  # 3着以内（複勝圏内）

        # --- 1. レースごとの結果一覧表 ---
        race_list = data[["日付", "開催", "レース名", "頭数", "通過", "脚質", "着順"]]

        # --- 2. 脚質ごとの戦術割合・成績サマリー集計 ---
        total_races = len(data)
        summary = (
            data.groupby("脚質")
            .agg(
                出走数=("着順", "count"),
                勝利数=("is_win", "sum"),
                連対数=("is_top2", "sum"),
                複勝数=("is_top3", "sum"),
            )
            .reset_index()
        )

        # 戦術割合および各率の計算
        summary["戦術割合"] = (
            (summary["出走数"] / total_races * 100).round(1).astype(str) + "%"
        )
        summary["勝率"] = (
            (summary["勝利数"] / summary["出走数"] * 100).round(1).astype(str) + "%"
        )
        summary["連対率"] = (
            (summary["連対数"] / summary["出走数"] * 100).round(1).astype(str) + "%"
        )
        summary["複勝率"] = (
            (summary["複勝数"] / summary["出走数"] * 100).round(1).astype(str) + "%"
        )

        # カラム順序の整理
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

    def normalized_hist(self, df: pd.DataFrame) -> pd.DataFrame:
        """必要な部分を数値や日付型に変換"""
        # 1. 列名（カラム名）からすべての空白（半角 ' ' / 全角 ' ' / タブ等）を除去
        df.columns = df.columns.str.replace(r'[\s\u3000]', '', regex=True)
        # 2. (任意) 文字列型（object型）のデータ値に含まれる前後の余計な空白も除去
        for col in df.select_dtypes(include=['object']).columns:
            df[col] = df[col].astype(str).str.strip()
        
        # 着順やRなどを数値型に変換（変換できない文字が入っている場合はNaNにする coerce を指定）
        df["着順"] = pd.to_numeric(df["着順"], errors="coerce")
        df["R"] = pd.to_numeric(df["R"], errors="coerce")

        # 日付文字列を datetime 型に変換
        df["日付"] = pd.to_datetime(df["日付"])

        return df

def safe_normalize_dataframe(df: pd.DataFrame) -> pd.DataFrame:
    data = df.copy()

    # 1. 列名を文字列型に変換してから空白を除去（原因1の対策）
    data.columns = (
        data.columns.astype(str).str.replace(r'[\s\u3000]', '', regex=True)
    )

    # 2. 文字列型（object型）の列のみを対象にして前後の空白を除去（原因2の対策）
    for col in data.select_dtypes(include=['object']).columns:
        data[col] = data[col].astype(str).str.strip()

    # 3. 開催の余分な数字を消す
    data["開催"] = data["開催"].astype(str).str.replace(r"\d+", "", regex=True)

    return data
