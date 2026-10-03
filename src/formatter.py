# ロガー設定
import logging
logger = logging.getLogger(__name__)



class NkFormatter:

    def conv_race_info_to_markdown(self, target_date: str, race_info: list[dict]) -> str:
        """
        レース情報をマークダウンに変換する
        """
        """レース情報の辞書をGeminiが見やすいMarkdown形式のテキストに変換する"""
        md_text = f"""# {target_date} - 【{race_info.get('race_course', '')}】第race_{race_info.get('race_num', '')}R: {race_info.get('race_name', '')}

## 1. レース基本情報
- **レースID**: `{race_info.get('race_id', '')}`
- **発走時刻**: {race_info.get('start_time', '')}
- **グレード**: {race_info.get('race_grade', '')}
- **条件**: {race_info.get('race_class', '')} （{race_info.get('horses_num', '')}）
- **コース**: {race_info.get('race_course', '')} {race_info.get('distance', '')} {race_info.get('course', '')} / {race_info.get('race_type', '')}
- **馬場・天候**: 天候: {race_info.get('weather', '')} / 馬場状態: {race_info.get('condition', '')}
- **開催スケジュール**: {race_info.get('race_kai', '')} {race_info.get('race_course', '')} {race_info.get('race_days', '')}
"""
        return md_text

    def conv_shutuba_to_markdown(self, data_list: list[dict]) -> str:
        """出馬表の辞書リストをMarkdown形式のテーブル文字列に変換する"""
        # ヘッダーと区切り線
        md_lines = [
            "## 2. 出馬表\n\n",
            "| 枠 | 馬番 | 馬名 | 性齢 | 斤量 | 騎手 | 厩舎 | 馬ID |",
            "|---|---|---|---|---|---|---|---|",
        ]

        for item in data_list:
            # 馬名にURLのハイパーリンクを設定（Markdown形式: [馬名](URL)）
            horse_link = f"[{item['horse_name']}]({item['horse_url']})"

            # 行の生成
            row = f"| {item['bracket_num']} | {item['horse_num']} | {horse_link} | {item['horse_age']} | {item['weight_carried']} | {item['jockey']} | {item['stable']} | {item['horse_id']} |"
            md_lines.append(row)

        return "\n".join(md_lines)

    def conv_race_result_to_markdown(self, data_list: list[dict]) -> str:
        """レース結果の辞書リストをMarkdown形式のテーブル文字列に変換する"""
        # ヘッダーと区切り線
        md_lines = [
            "## 2. レース結果（着順）\n\n",
            "| 着順 | 枠 | 馬番 | 馬名 | 性齢 | 斤量 | 騎手 | タイム | 着差 | 人気 | オッズ | 上り | 通過 | 馬体重 | 厩舎 |",
            "|---|---|---|---|---|---|---|---|---|---|---|---|---|---|---|",
        ]

        for item in data_list:
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
                f"{item['passing_order']} | {weight_str} | {item['stable']} |"
            )
            md_lines.append(row)

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
            "#### 基本情報",
            f"- **名前 / 英名** {name} ({eng_name})",
            f"- **性齢 / 毛色**: {data.get('horse_age', '')} / {data.get('horse_type', '')}",
            f"- **生年月日**: {data.get('生年月日', '')}",
            f"- **調教師**: {data.get('調教師', '')}",
            f"- **馬主**: {data.get('馬主', '')}",
            f"- **生産者 / 産地**: {data.get('生産者', '')}（{data.get('産地', '')}）",
            f"- **募集情報**: {data.get('募集情報', '')}",
            f"- **セリ取引価格**: {data.get('セリ取引価格', '')}",
            "",
            "#### 成績・獲得賞金",
            f"- **通算成績**: {data.get('通算成績', '')}",
            f"- **獲得賞金**: 地方 {data.get('獲得賞金 (地方)', '0万円')} / 中央 {data.get('獲得賞金 (中央)', '0万円')}",
            f"- **主な勝鞍**: {data.get('主な勝鞍', '')}",
            f"- **近親馬**: {data.get('近親馬', '')}",
            "",
            "#### 血統表（3代血統）",
            "| 父 | 母父 |",
            "|---|---|",
            f"| **{make_ped_link(data.get('sire'))}** | **{make_ped_link(data.get('dam_sire'))}** |",
            f"| 父父: {make_ped_link(data.get('sire_sire'))} | 母母: {make_ped_link(data.get('dam_dam'))} |",
            f"| 父母: {make_ped_link(data.get('sire_dam'))} | 母: **{make_ped_link(data.get('dam'))}** |",
        ]

        return "\n".join(md)

    def conv_history_to_markdown(data_list: list[list]) -> str:
        """
        先頭行(data_list[0])がヘッダーとなっている2次元リストを
        Markdown形式のテーブル文字列に変換する
        """
        if not data_list:
            return ""

        # セル内のパイプ記号(|)や改行をエスケープ・整形するヘルパー関数
        def format_cell(value) -> str:
            if value is None:
                return ""
            s = str(value).replace("\n", " ").replace("|", "\\|")
            return s.strip()

        header = data_list[0]
        rows = data_list[1:]

        # 1. ヘッダー行と区切り線の生成
        header_line = "| " + " | ".join(format_cell(h) for h in header) + " |"
        separator_line = "| " + " | ".join(["---"] * len(header)) + " |"

        # 2. 各データ行の生成
        md_lines = [header_line, separator_line]
        for row in rows:
            row_line = "| " + " | ".join(format_cell(cell) for cell in row) + " |"
            md_lines.append(row_line)

        return "\n".join(md_lines)

    def get_filename_from_race_info(self, race_info: list[dict]) -> str:
        return ""
