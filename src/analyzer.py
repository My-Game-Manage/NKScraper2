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

def extract_last_corner_pos(passing_str):
    """通過順文字列（例: "5-3-2", "4-4-5-3"）から4角（最終コーナー）通過順を抽出"""
    if pd.isna(passing_str) or not isinstance(passing_str, str):
        return None
    positions = [int(p) for p in passing_str.split("-") if p.isdigit()]
    if not positions:
        return None
    return positions[-1]  # 最後の数字が最終コーナー通過順

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

    def generate_daily_bias_markdown(self, target_date: str, all_races_data, race_date_str: str = "", venue_str: str = "") -> str:
        """
        全レース分のデータをまとめたものから当該日バイアスを解析し、Markdownを生成する（ID主体管理）
        """
        if not all_races_data:
            return "# 当該日レース傾向・馬場バイアス分析データ\n\nデータが存在しません。"

        # 辞書型（レース名ごとなど）で渡された場合を考慮し、フラットなリストに変換
        if isinstance(all_races_data, dict):
            flat_data = []
            for race_key, race_list in all_races_data.items():
                if isinstance(race_list, list):
                    flat_data.extend(race_list)
        else:
            flat_data = all_races_data

        if not flat_data:
            return "# 当該日レース傾向・馬場バイアス分析データ\n\n有効なデータが存在しません。"

        df = pd.DataFrame(flat_data)

        # 列名のクレンジング
        df.columns = df.columns.astype(str).str.replace(r'[\s\u3000]', '', regex=True)

        # 英語キーから日本語キーへのマッピング変換
        column_mapping = {
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
        df = df.rename(columns=column_mapping)

        # データのクレンジングと型変換
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
        df["is_win"] = (df["着順"] == 1).fillna(0).astype(int)
        df["is_top2"] = (df["着順"].le(2)).fillna(0).astype(int)
        df["is_top3"] = (df["着順"].le(3)).fillna(0).astype(int)

        # -------------------------------------------------------------
        # 1. 枠番・馬番別のバイアス集計
        # -------------------------------------------------------------
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

        # -------------------------------------------------------------
        # 2. 脚質・4角ポジション別の残存率集計
        # -------------------------------------------------------------
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

        # -------------------------------------------------------------
        # 3. 当日騎手・厩舎トレンド集計（ID主体管理）
        # -------------------------------------------------------------
        jockey_summary_df = pd.DataFrame()
        if "騎手ID" in df.columns:
            # 騎手IDでグループ化し、表記揺れ対策として騎手名は最頻値を取得
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
            # テーブル項目に「騎手ID」を含めて出力
            jockey_summary_df = jockey_grouped[["騎手ID", "騎手", "騎乗数", "勝利数", "勝率", "連対数", "複勝数", "複勝率"]].head(10)

        trainer_summary_df = pd.DataFrame()
        if "厩舎ID" in df.columns:
            # 厩舎IDでグループ化し、厩舎名は最頻値を取得
            trainer_grouped = df.groupby("厩舎ID").agg(
                厩舎=("厩舎", lambda x: x.mode()[0] if not x.mode().empty else "不明"),
                出走数=("着順", "count"),
                勝利数=("is_win", "sum"),
                複勝数=("is_top3", "sum"),
            ).reset_index()

            trainer_grouped["勝率"] = (trainer_grouped["勝利数"] / trainer_grouped["出走数"] * 100).round(1).astype(str) + "%"
            trainer_grouped["複勝率"] = (trainer_grouped["複勝数"] / trainer_grouped["出走数"] * 100).round(1).astype(str) + "%"
            trainer_grouped = trainer_grouped.sort_values(by=["勝利数", "複勝数", "出走数"], ascending=[False, False, False]).reset_index(drop=True)
            # テーブル項目に「厩舎ID」を含めて出力
            trainer_summary_df = trainer_grouped[["厩舎ID", "厩舎", "出走数", "勝利数", "勝率", "複勝数", "複勝率"]].head(10)

        # -------------------------------------------------------------
        # Markdownの組み立て
        # -------------------------------------------------------------
        year = target_date[:4] if len(target_date) >= 8 else ""
        month = target_date[4:6] if len(target_date) >= 8 else ""
        day = target_date[6:8] if len(target_date) >= 8 else ""
        
        title_header = f"# {year}-{month}-{day}日傾向・馬場バイアス解析レポート"
        if race_date_str or venue_str:
            title_header += f" ({venue_str} {race_date_str})"

        md_output = [f"{title_header}\n"]

        md_output.append("## 1. 枠番別バイアス分析\n")
        md_output.append(dataframe_to_markdown_table(draw_summary_df))

        md_output.append("## 2. 4角ポジション別残存率分析\n")
        md_output.append(dataframe_to_markdown_table(corner_summary_df))

        md_output.append("## 3. 当該日騎手・厩舎トレンド分析 (ID主体)\n")
        md_output.append("### 【騎手成績】")
        md_output.append(dataframe_to_markdown_table(jockey_summary_df))
        md_output.append("### 【厩舎成績】")
        md_output.append(dataframe_to_markdown_table(trainer_summary_df))

        return "\n".join(md_output)
    
    def generate_jockey_style_aptitude_markdown(self, all_history_data: list[dict]) -> str:
        """
        蓄積されたレース結果データから「騎手IDベース」で得意脚質・芝/ダート別得意距離を分析する
        """
        df = self._prepare_flat_dataframe(all_history_data)
        if df.empty or "騎手ID" not in df.columns:
            return "# 騎手特性・得意スタイル分析プロファイル\n\nデータが存在しません。"

        # 数値前処理
        df["着順_num"] = pd.to_numeric(df["着順"], errors="coerce")
        df["人気_num"] = pd.to_numeric(df["人気"], errors="coerce")
        
        # フラグ作成
        df["is_win"] = (df["着順_num"] == 1).fillna(0).astype(int)
        df["is_top3"] = (df["着順_num"] <= 3).fillna(0).astype(int)

        # タイプ（芝・ダート）の正規化関数（不明・空欄・障などは「不明」として弾く）
        def normalize_track_type(t):
            if pd.isna(t):
                return "不明"
            t_str = str(t).strip()
            if "芝" in t_str:
                return "芝"
            elif "ダ" in t_str or "ダート" in t_str:
                return "ダート"
            else:
                return "不明"

        df["タイプ_norm"] = df["タイプ"].apply(normalize_track_type) if "タイプ" in df.columns else "不明"

        # 4角通過順位から脚質判定
        def get_tactics(passing_str):
            if pd.isna(passing_str) or not isinstance(passing_str, str):
                return "不明"
            pos = [int(p) for p in passing_str.split("-") if p.isdigit()]
            if not pos: return "不明"
            last_pos = pos[-1]
            if last_pos == 1: return "逃げ"
            elif last_pos <= 4: return "先行"
            elif last_pos <= 8: return "差し"
            else: return "追込"

        df["展開脚質"] = df["通過"].apply(get_tactics)

        # 1. 騎手ID × 脚質別の集計
        jockey_tactics = df.groupby(["騎手ID", "展開脚質"]).agg(
            騎乗数=("着順_num", "count"),
            複勝数=("is_top3", "sum")
        ).reset_index()
        jockey_tactics["複勝率_num"] = (jockey_tactics["複勝数"] / jockey_tactics["騎乗数"] * 100).round(1)

        # 2. 騎手ID × タイプ × 距離別の集計（芝・ダート別）
        jockey_dist_type = pd.DataFrame()
        if "距離" in df.columns:
            df_filtered = df[df["タイプ_norm"].isin(["芝", "ダート"])]
            if not df_filtered.empty:
                jockey_dist_type = df_filtered.groupby(["騎手ID", "タイプ_norm", "距離"]).agg(
                    騎乗数=("着順_num", "count"),
                    複勝数=("is_top3", "sum")
                ).reset_index()
                jockey_dist_type["複勝率_num"] = (jockey_dist_type["複勝数"] / jockey_dist_type["騎乗数"] * 100).round(1)

        results = []
        for j_id, group in df.groupby("騎手ID"):
            total_mounts = len(group)
            if total_mounts < 1:  
                continue
            
            jockey_name = group["騎手"].mode()[0] if "騎手" in group.columns and not group["騎手"].mode().empty else str(j_id)

            total_wins = group["is_win"].sum()
            total_top3 = group["is_top3"].sum()
            overall_top3_rate = f"{round(total_top3 / total_mounts * 100, 1)}%"

            # --- 脚質の集計（安全ガード付き） ---
            best_style, worst_style = "データ不足", "データ不足"
            tactic_group = jockey_tactics[jockey_tactics["騎手ID"] == j_id]
            if not tactic_group.empty:
                tactic_valid = tactic_group.dropna(subset=["複勝率_num"])
                if not tactic_valid.empty:
                    best_row = tactic_valid.loc[tactic_valid["複勝率_num"].idxmax()]
                    best_style = f"{best_row['展開脚質']} (複勝率:{best_row['複勝率_num']}%)"
                    worst_row = tactic_valid.loc[tactic_valid["複勝率_num"].idxmin()]
                    worst_style = f"{worst_row['展開脚質']} (複勝率:{worst_row['複勝率_num']}%)"

            # --- 芝・ダート別の得意・苦手距離の特定（安全ガード付き） ---
            best_turf_dist, worst_turf_dist = "データなし", "データなし"
            best_dirt_dist, worst_dirt_dist = "データなし", "データなし"

            if not jockey_dist_type.empty:
                # 芝の距離適性
                turf_group = jockey_dist_type[(jockey_dist_type["騎手ID"] == j_id) & (jockey_dist_type["タイプ_norm"] == "芝")]
                if not turf_group.empty:
                    turf_valid = turf_group.dropna(subset=["複勝率_num"])
                    if not turf_valid.empty:
                        b_row = turf_valid.loc[turf_valid["複勝率_num"].idxmax()]
                        best_turf_dist = f"{b_row['距離']} (複勝率:{b_row['複勝率_num']}%)"
                        w_row = turf_valid.loc[turf_valid["複勝率_num"].idxmin()]
                        worst_turf_dist = f"{w_row['距離']} (複勝率:{w_row['複勝率_num']}%)"

                # ダートの距離適性
                dirt_group = jockey_dist_type[(jockey_dist_type["騎手ID"] == j_id) & (jockey_dist_type["タイプ_norm"] == "ダート")]
                if not dirt_group.empty:
                    dirt_valid = dirt_group.dropna(subset=["複勝率_num"])
                    if not dirt_valid.empty:
                        b_row = dirt_valid.loc[dirt_valid["複勝率_num"].idxmax()]
                        best_dirt_dist = f"{b_row['距離']} (複勝率:{b_row['複勝率_num']}%)"
                        w_row = dirt_valid.loc[dirt_valid["複勝率_num"].idxmin()]
                        worst_dirt_dist = f"{w_row['距離']} (複勝率:{w_row['複勝率_num']}%)"

            results.append({
                "騎手ID": j_id,
                "騎手名": jockey_name,
                "総騎乗数": total_mounts,
                "通算勝率": f"{round(total_wins / total_mounts * 100, 1)}%",
                "通算複勝率": overall_top3_rate,
                "得意脚質スタイル": best_style,
                "苦手脚質スタイル": worst_style,
                "芝・得意距離": best_turf_dist,
                "芝・苦手距離": worst_turf_dist,
                "ダート・得意距離": best_dirt_dist,
                "ダート・苦手距離": worst_dirt_dist,
            })

        res_df = pd.DataFrame(results)
        if res_df.empty:
            return "# 騎手特性・得意スタイル分析プロファイル\n\n条件に合うデータがありません。"

        res_df = res_df.sort_values(by="総騎乗数", ascending=False).reset_index(drop=True)
        table_text = dataframe_to_markdown_table(res_df)

        return f"# 騎手特性・得意スタイル分析プロファイル\n\n{table_text}"

    def generate_trainer_venue_aptitude_markdown(self, all_history_data: list[dict]) -> str:
        """
        蓄積されたレース結果データから「厩舎IDベース」で会場別適性を分析する
        """
        df = self._prepare_flat_dataframe(all_history_data)
        if df.empty or "厩舎ID" not in df.columns:
            return "# 厩舎バイタル・会場適性分析プロファイル\n\nデータが存在しません。"

        if "開催" not in df.columns:
            df["開催"] = "当日開催"

        df["着順_num"] = pd.to_numeric(df["着順"], errors="coerce")
        df["is_win"] = (df["着順_num"] == 1).fillna(0).astype(int)
        df["is_top3"] = (df["着順_num"] <= 3).fillna(0).astype(int)

        # 厩舎ID × 開催場ごと集計
        trainer_venue = df.groupby(["厩舎ID", "開催"]).agg(
            出走数=("着順_num", "count"),
            勝利数=("is_win", "sum"),
            複勝数=("is_top3", "sum"),
        ).reset_index()

        trainer_venue["複勝率_num"] = (trainer_venue["複勝数"] / trainer_venue["出走数"] * 100).round(1)

        results = []
        for t_id, group in trainer_venue.groupby("厩舎ID"):
            total_runs = group["出走数"].sum()
            if total_runs < 1: continue

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

    def _prepare_flat_dataframe(self, all_races_data) -> pd.DataFrame:
        """入力データをフラットなDataFrameに正規化し、英語キーを日本語キーにマッピングする内部関数"""
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

        column_mapping = {
            "race_track": "開催",
            "rank": "着順", "bracket_num": "枠番", "horse_num": "馬番",
            "horse_name": "馬名", "horse_age": "性齢", "weight_carried": "斤量",
            "jockey": "騎手", "jockey_id": "騎手ID", "jockey_url": "騎手URL",
            "stable": "厩舎", "stable_id": "厩舎ID",
            "time": "タイム", "margin": "着差",
            "popularity": "人気", "odds": "オッズ", "last3f": "上り",
            "passing_order": "通過", "horse_weight": "馬体重",
            "weight_diff": "馬体重増減",
            "race_type": "タイプ", "race_distance": "距離",
        }
        df = df.rename(columns=column_mapping)
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
