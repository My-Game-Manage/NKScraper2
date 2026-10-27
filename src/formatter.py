# ロガー設定
import logging
logger = logging.getLogger(__name__)
import pandas as pd

def history_nested_list_to_bullet_list(history: list[list]) -> str:
    """list[list] 形式のデータ（[0]がヘッダー行）を、

    LLMが誤読しにくい箇条書きテキストに変換する関数
    """
    if not history or len(history) <= 1:
        return "- 戦績データなし\n"

    headers = history[0]
    data_rows = history[1:]

    lines = []
    for row in data_rows:
        items = []
        for col, val in zip(headers, row):
            # 欠損値や空文字、意味のない記号・nanはスキップ
            if (
                pd.isna(val)
                or val is None
                or str(val).strip() == ""
                or str(val).lower() == "nan"
            ):
                continue

            col_clean = str(col).strip()
            val_clean = str(val).strip()

            # ノイズになりやすい項目を除外したい場合のフィルター（例: タイム指数）
            if "タイム指数" in col_clean:
                continue

            items.append(f"{col_clean}: {val_clean}")

        if items:
            lines.append("- " + " | ".join(items))

    return "\n".join(lines) + "\n\n"

def history_list_to_bullet_list(history_list: list[dict]) -> str:
    """戦績の list[dict] 形式データを、LLM（Gemini等）が誤読しにくい

    箇条書きテキスト（キー: 値 | ...）に変換する関数
    """
    if not history_list or len(history_list) <= 1:
        return "- 戦績データなし\n"

    # 先頭がヘッダーやカラム名、2番目以降がデータの場合の安全な抽出
    # もし単純な dict のリストであればそのままループします
    headers = history_list[0]
    data_rows = history_list[1:]

    lines = []
    for row in data_rows:
        items = []
        for col, val in row.items():
            # 欠損値や空文字、意味のない記号列はスキップ
            if (
                pd.isna(val)
                or val is None
                or str(val).strip() == ""
                or str(val).lower() == "nan"
            ):
                continue

            # 余分な空白を除去
            col_clean = str(col).strip()
            val_clean = str(val).strip()

            # 指数系や長すぎる項目、今回は不要な項目を間引きたい場合はここでフィルタリング可能
            # 例: "ﾀｲﾑ指数" などノイズになりやすいものを除外する場合
            if "タイム指数" in col_clean:
                continue

            items.append(f"{col_clean}: {val_clean}")

        if items:
            lines.append("- " + " | ".join(items))

    return "\n".join(lines) + "\n\n"


class NkFormatter:

    def conv_race_info_to_markdown(self, target_date: str, race_info: dict) -> str:
        """
        レース情報をマークダウンに変換する
        """
        """レース情報の辞書をGeminiが見やすいMarkdown形式のテキストに変換する"""
        md_text = f"""# {target_date} - 【{race_info.get('race_track', '')}】第{race_info.get('race_num', '')}R: {race_info.get('race_name', '')}

## 1. レース基本情報
- **レースID**: `{race_info.get('race_id', '')}`
- **発走時刻**: {race_info.get('start_time', '')}
- **グレード**: {race_info.get('race_grade', '')}
- **条件**: {race_info.get('race_class', '')} （{race_info.get('horses_num', '')}）
- **コース**: {race_info.get('race_course', '')} {race_info.get('race_distance', '')} {race_info.get('course', '')} / {race_info.get('race_type', '')}
- **馬場・天候**: 天候: {race_info.get('weather', '')} / 馬場状態: {race_info.get('condition', '')}
- **開催スケジュール**: {race_info.get('race_kai', '')} {race_info.get('race_track', '')} {race_info.get('race_days', '')}
"""
        return md_text

    def conv_shutuba_to_markdown(self, data_list: list[dict]) -> str:
        """出馬表の辞書リストをMarkdown形式のテーブル文字列に変換する"""
        # ヘッダーと区切り線
        md_lines = [
            "## 2. 出馬表\n\n",
            "| 枠 | 馬番 | 馬名 | 性齢 | 斤量 | 騎手 | 厩舎 | 馬ID | 騎手ID | 厩舎ID |",
            "|---|---|---|---|---|---|---|---|---|---|",
        ]

        for item in data_list:
            # 馬名にURLのハイパーリンクを設定（Markdown形式: [馬名](URL)）
            horse_link = f"[{item['horse_name']}]({item['horse_url']})"

            # 行の生成
            row = f"| {item['bracket_num']} | {item['horse_num']} | {horse_link} | {item['horse_age']} | {item['weight_carried']} | {item['jockey']} | {item['stable']} | {item['horse_id']} | {item['jockey_id']} | {item['stable_id']} |"
            md_lines.append(row)

        return "\n".join(md_lines)

    def conv_race_result_to_markdown(self, target_date: str, data_list: list[dict]) -> str:
        """レース結果の辞書リストをMarkdown形式のテーブル文字列に変換する"""
        # 1. レース情報部分の処理
        race_info = data_list[0]

        race_info_txt = self.conv_race_info_to_markdown(target_date, race_info)

        # 2. レース払い戻し
        payouts_info = data_list[1]
        payouts_txt = self.payout_dict_to_markdown(payouts_info)

        # ヘッダーと区切り線
        md_lines = [
            f"{race_info_txt}\n\n",
            "## 2. レース結果（着順）\n\n",
            "| 着順 | 枠 | 馬番 | 馬名 | 性齢 | 斤量 | 騎手 | タイム | 着差 | 人気 | オッズ | 上り | 通過 | 馬体重 | 厩舎 | 騎手ID | 厩舎ID |",
            "|---|---|---|---|---|---|---|---|---|---|---|---|---|---|---|---|---|",
        ]

        for item in data_list[2:]:
            # 馬名にURLのハイパーリンクを設定
            horse_link = f"[{item['horse_name']}]({item['horse_url']})"

            # 馬体重と増減を整形（例: 464(+4) または 454(0)）
            weight_diff = item["weight_diff"]
            if weight_diff and not weight_diff.startswith(("-", "+")):
                # 増減が "0" などの場合は符号なしのまま
                weight_str = f"{item['horse_weight']}({weight_diff})"
            elif weight_diff:
                weight_str = f"{item['horse_weight']}({weight_diff})"
            else:
                weight_str = item["horse_weight"]

            # 行の生成
            row = (
                f"| {item['rank']} | {item['bracket_num']} | {item['horse_num']} | "
                f"{horse_link} | {item['horse_age']} | {item['weight_carried']} | "
                f"{item['jockey']} | {item['time']} | {item['margin']} | "
                f"{item['popularity']} | {item['odds']} | {item['last3f']} | "
                f"{item['passing_order']} | {weight_str} | {item['stable']} | {item['jockey_id']} | {item['stable_id']} |"
            )
            md_lines.append(row)

        md_lines.append("## 3. レース払い戻し\n\n")
        md_lines.append(f"{payouts_txt}\n\n")

        return "\n".join(md_lines)

    def conv_horse_profile_to_markdown(self, data: dict) -> str:
        """馬のプロフィール辞書データをMarkdown形式に変換する"""

        # 血統リンク生成用ヘルパー関数
        def make_ped_link(ped_dict: dict) -> str:
            if isinstance(ped_dict, dict) and "name" in ped_dict and "url" in ped_dict:
                return f"[{ped_dict['name']}]({ped_dict['url']})"
            return str(ped_dict) if ped_dict else "-"

        # 1. 基本プロフィール部
        name = data.get("horse_name", "")
        eng_name = data.get("horse_eng_name", "")

        md = [
            "##### 基本情報",
            f"- **名前 / 英名** {name} ({eng_name})",
            f"- **性齢 / 毛色**: {data.get('horse_age', '')} / {data.get('horse_type', '')}",
            f"- **生年月日**: {data.get('生年月日', '')}",
            f"- **調教師**: {data.get('調教師', '')}",
            f"- **馬主**: {data.get('馬主', '')}",
            f"- **生産者 / 産地**: {data.get('生産者', '')}（{data.get('産地', '')}）",
            f"- **募集情報**: {data.get('募集情報', '')}",
            f"- **セリ取引価格**: {data.get('セリ取引価格', '')}",
            "",
            "##### 成績・獲得賞金",
            f"- **通算成績**: {data.get('通算成績', '')}",
            f"- **獲得賞金**: 地方 {data.get('獲得賞金 (地方)', '0万円')} / 中央 {data.get('獲得賞金 (中央)', '0万円')}",
            f"- **主な勝鞍**: {data.get('主な勝鞍', '')}",
            f"- **近親馬**: {data.get('近親馬', '')}",
            "",
            "##### 血統表（3代血統）",
            "| 父 | 母父 |",
            "|---|---|",
            f"| **{make_ped_link(data.get('sire'))}** | **{make_ped_link(data.get('dam_sire'))}** |",
            f"| 父父: {make_ped_link(data.get('sire_sire'))} | 母母: {make_ped_link(data.get('dam_dam'))} |",
            f"| 父母: {make_ped_link(data.get('sire_dam'))} | 母: **{make_ped_link(data.get('dam'))}** |",
        ]

        return "\n".join(md)

    def conv_history_to_markdown(self, data_list: list[list]) -> str:
        """
        先頭行(data_list[0])がヘッダーとなっている2次元リストを
        Markdown形式のテーブル文字列に変換する
        """
        if not data_list or len(data_list) < 10:
            return ""

        md = history_nested_list_to_bullet_list(data_list)

        return md

    def get_filename_from_race_info(self, race_info: list[dict]) -> str:
        if not "race_info" in race_info:
            logger.error(f"race_info key が見つかりません：{info}")
            return "no-name.md"
        
        info = race_info["race_info"]

        return f"{info.get('race_id', '')}-{info.get('race_track','')}{info.get('race_num','')}R.md"

    def get_filename_from_id_track_num(self, race_id: str, race_track: str, race_num: str) -> str:
        return f"{race_id}-{race_track}{race_num}R.md"

    def get_filename_prefix_from_id_track_num(self, race_id: str, race_track: str, race_num: str) -> str:
        return f"{race_id}-{race_track}{race_num}"

    def get_filename_from_race_result(self, race_id: str, race_track: str, race_num: str) -> str:
        return f"{race_id}-result-{race_track}{race_num}R.md"

    def payout_dict_to_markdown(self, payout_data: dict) -> str:
        """
        パースした払い戻し辞書データ（payout_data）を、
        見やすいMarkdownの表形式（文字列）に変換する関数
        """
        if not payout_data:
            return "> **【払戻情報】**\n> 払い戻しデータはありません。\n"

        rows = []
        for bet_type, info in payout_data.items():
            results = info.get("results", [])
            payouts = info.get("payouts", [])
            ninkis = info.get("popularity", [])

            # 賭式に応じて馬番・組合せの表示形式を整える
            formatted_results = ""
            if bet_type in ["ワイド", "馬連", "馬単", "枠連"]:
                # 2頭（枠）ずつのペアに結合する（例: 13-16）
                pairs = [f"{results[i]}-{results[i+1]}" for i in range(0, len(results) - 1, 2)] if len(results) >= 2 else results
                formatted_results = "<br>".join(pairs)
            elif bet_type == "3連複":
                # 3頭ずつの組み合わせにする（例: 11-13-16）
                triplets = [f"{results[i]}-{results[i+1]}-{results[i+2]}" for i in range(0, len(results) - 2, 3)] if len(results) >= 3 else results
                formatted_results = "<br>".join(triplets)
            elif bet_type == "3連単":
                # 3頭ずつの着順通りにする（例: 16→13→11）
                triplets = [f"{results[i]}→{results[i+1]}→{results[i+2]}" for i in range(0, len(results) - 2, 3)] if len(results) >= 3 else results
                formatted_results = "<br>".join(triplets)
            else:
                # 単勝・複勝など
                formatted_results = "<br>".join(results)

            # 払戻金と人気も複数ある場合は改行で繋ぐ
            payout_str = "<br>".join(payouts) if payouts else "データなし"
            ninki_str = "<br>".join(ninkis) if ninkis else "データなし"

            rows.append(f"| {bet_type} | {formatted_results} | {payout_str} | {ninki_str} |")

        # Markdownテーブルのヘッダーとボディの構築
        table_header = "| 賭式 | 組合せ | 払戻金 | 人気 |\n|:---:|:---:|:---:|:---:|"
        table_body = "\n".join(rows)

        markdown_output = (
            f"### 払い戻し情報\n\n"
            f"{table_header}\n"
            f"{table_body}\n"
        )

        return markdown_output