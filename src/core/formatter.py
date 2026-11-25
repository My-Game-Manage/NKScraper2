"""競馬データのテキスト／Markdownフォーマット変換モジュール

パースされた出馬表、レース結果、馬プロフィール、戦績データを
LLM（Gemini等）が誤読しにくい構造化Markdownテキストやファイル名に変換します。
"""

import logging
from typing import Any, Dict, List, Union
import pandas as pd

logger = logging.getLogger(__name__)


def history_nested_list_to_bullet_list(history: List[List[Any]]) -> str:
    """list[list] 形式の戦績データ（[0]がヘッダー行）を箇条書きMarkdownテキストに変換する関数"""
    if not history or len(history) <= 1:
        return "- 戦績データなし\n\n"

    headers = history[0]
    data_rows = history[1:]

    lines = []
    for row in data_rows:
        items = []
        for col, val in zip(headers, row):
            if (
                pd.isna(val)
                or val is None
                or str(val).strip() == ""
                or str(val).lower() == "nan"
            ):
                continue

            col_clean = str(col).strip()
            val_clean = str(val).strip()

            if "タイム指数" in col_clean:
                continue

            items.append(f"{col_clean}: {val_clean}")

        if items:
            lines.append("- " + " | ".join(items))

    return "\n".join(lines) + "\n\n" if lines else "- 戦績データなし\n\n"


def history_list_to_bullet_list(history_list: List[Dict[str, Any]]) -> str:
    """list[dict] 形式の戦績データを箇条書きMarkdownテキストに変換する関数"""
    if not history_list:
        return "- 戦績データなし\n\n"

    lines = []
    for row in history_list:
        if not isinstance(row, dict):
            continue

        items = []
        for col, val in row.items():
            if (
                pd.isna(val)
                or val is None
                or str(val).strip() == ""
                or str(val).lower() == "nan"
            ):
                continue

            col_clean = str(col).strip()
            val_clean = str(val).strip()

            if "タイム指数" in col_clean:
                continue

            items.append(f"{col_clean}: {val_clean}")

        if items:
            lines.append("- " + " | ".join(items))

    return "\n".join(lines) + "\n\n" if lines else "- 戦績データなし\n\n"


class NkFormatter:
    """競馬データの各オブジェクトをMarkdownフォーマット文字列に変換するクラス"""

    def conv_race_info_to_markdown(self, target_date: str, race_info: Dict[str, Any]) -> str:
        """レース情報の辞書をGeminiが見やすいMarkdown形式のテキストに変換する"""
        if not race_info:
            return ""

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

    def conv_shutuba_to_markdown(self, data_list: List[Dict[str, Any]]) -> str:
        """出馬表の辞書リストをMarkdown形式のテーブル文字列に変換する"""
        if not data_list:
            return "## 2. 出馬表\n\nデータなし\n"

        md_lines = [
            "## 2. 出馬表\n\n",
            "| 枠 | 馬番 | 馬名 | 性齢 | 斤量 | 騎手 | 厩舎 | 馬ID | 騎手ID | 厩舎ID |",
            "|---|---|---|---|---|---|---|---|---|---|",
        ]

        for item in data_list:
            horse_link = f"[{item.get('horse_name', '')}]({item.get('horse_url', '')})"
            row = (
                f"| {item.get('bracket_num', '')} | {item.get('horse_num', '')} | "
                f"{horse_link} | {item.get('horse_age', '')} | {item.get('weight_carried', '')} | "
                f"{item.get('jockey', '')} | {item.get('stable', '')} | {item.get('horse_id', '')} | "
                f"{item.get('jockey_id', '')} | {item.get('stable_id', '')} |"
            )
            md_lines.append(row)

        return "\n".join(md_lines)

    def conv_race_result_to_markdown(self, target_date: str, data_list: List[Any]) -> str:
        """レース結果のデータリスト（[0]=race_info, [1]=payouts, [2:]=着順データ）をMarkdown形式に変換する"""
        if not data_list or len(data_list) < 2:
            return ""

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
            if not isinstance(item, dict):
                continue

            horse_link = f"[{item.get('horse_name', '')}]({item.get('horse_url', '')})"

            # 馬体重と増減を整形（例: 464(+4) または 454(0)）
            weight_diff = item.get("weight_diff", "")
            horse_weight = item.get("horse_weight", "")
            if weight_diff:
                weight_str = f"{horse_weight}({weight_diff})"
            else:
                weight_str = horse_weight

            row = (
                f"| {item.get('rank', '')} | {item.get('bracket_num', '')} | {item.get('horse_num', '')} | "
                f"{horse_link} | {item.get('horse_age', '')} | {item.get('weight_carried', '')} | "
                f"{item.get('jockey', '')} | {item.get('time', '')} | {item.get('margin', '')} | "
                f"{item.get('popularity', '')} | {item.get('odds', '')} | {item.get('last3f', '')} | "
                f"{item.get('passing_order', '')} | {weight_str} | {item.get('stable', '')} | "
                f"{item.get('jockey_id', '')} | {item.get('stable_id', '')} |"
            )
            md_lines.append(row)

        md_lines.append("\n## 3. レース払い戻し\n")
        md_lines.append(f"{payouts_txt}\n")

        return "\n".join(md_lines)

    def conv_horse_profile_to_markdown(self, data: Dict[str, Any]) -> str:
        """馬のプロフィール辞書データをMarkdown形式に変換する"""
        if not data:
            return ""

        def make_ped_link(ped_dict: Any) -> str:
            if isinstance(ped_dict, dict) and "name" in ped_dict and "url" in ped_dict:
                return f"[{ped_dict['name']}]({ped_dict['url']})"
            return str(ped_dict) if ped_dict else "-"

        name = data.get("horse_name", "")
        eng_name = data.get("horse_eng_name", "")

        md = [
            "##### 基本情報",
            f"- **名前 / 英名**: {name} ({eng_name})",
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

    def conv_history_to_markdown(self, data_list: Union[List[List[Any]], List[Dict[str, Any]]]) -> str:
        """戦績データ（2次元リストまたは辞書リスト）をMarkdown形式に変換する"""
        if not data_list:
            return ""

        if isinstance(data_list[0], list):
            return history_nested_list_to_bullet_list(data_list)
        elif isinstance(data_list[0], dict):
            return history_list_to_bullet_list(data_list)
        return ""

    def get_filename_prefix_from_id_track_num(self, race_id: str, race_track: str, race_num: str) -> str:
        """ファイル名の接頭辞 (例: '202654032801-中山11') を生成する"""
        return f"{race_id}-{race_track}{race_num}"

    def get_filename_from_id_track_num(self, race_id: str, race_track: str, race_num: str) -> str:
        """出馬表ファイル名 (例: '202654032801-中山11R.md') を生成する"""
        prefix = self.get_filename_prefix_from_id_track_num(race_id, race_track, race_num)
        return f"{prefix}R.md"

    def get_filename_from_race_info(self, race_info: Union[Dict[str, Any], List[Dict[str, Any]]]) -> str:
        """レース情報オブジェクトから標準ファイル名を生成する"""
        if isinstance(race_info, list) and race_info:
            target = race_info[0]
        elif isinstance(race_info, dict):
            target = race_info.get("race_info", race_info)
        else:
            logger.error(f"不正な race_info 形式: {race_info}")
            return "no-name.md"

        race_id = target.get("race_id", "")
        race_track = target.get("race_track", "")
        race_num = target.get("race_num", "")
        return self.get_filename_from_id_track_num(race_id, race_track, race_num)

    def get_filename_from_race_result(self, race_id: str, race_track: str, race_num: str) -> str:
        """レース結果ファイル名 (例: '202654032801-result-中山11R.md') を生成する"""
        return f"{race_id}-result-{race_track}{race_num}R.md"

    def payout_dict_to_markdown(self, payout_data: Dict[str, Any]) -> str:
        """パースされた払い戻し辞書データ（payout_data）をMarkdown表形式に変換する"""
        if not payout_data:
            return "> **【払戻情報】**\n> 払い戻しデータはありません。\n"

        rows = []
        for bet_type, info in payout_data.items():
            results = info.get("results", [])
            payouts = info.get("payouts", [])
            ninkis = info.get("popularity", [])

            if bet_type in ["ワイド", "馬連", "馬単", "枠連"]:
                pairs = [f"{results[i]}-{results[i+1]}" for i in range(0, len(results) - 1, 2)] if len(results) >= 2 else results
                formatted_results = "<br>".join(pairs)
            elif bet_type == "3連複":
                triplets = [f"{results[i]}-{results[i+1]}-{results[i+2]}" for i in range(0, len(results) - 2, 3)] if len(results) >= 3 else results
                formatted_results = "<br>".join(triplets)
            elif bet_type == "3连単" or bet_type == "3連単":
                triplets = [f"{results[i]}→{results[i+1]}→{results[i+2]}" for i in range(0, len(results) - 2, 3)] if len(results) >= 3 else results
                formatted_results = "<br>".join(triplets)
            else:
                formatted_results = "<br>".join(results)

            payout_str = "<br>".join(payouts) if payouts else "データなし"
            ninki_str = "<br>".join(ninkis) if ninkis else "データなし"

            rows.append(f"| {bet_type} | {formatted_results} | {payout_str} | {ninki_str} |")

        table_header = "| 賭式 | 組合せ | 払戻金 | 人気 |\n|:---:|:---:|:---:|:---:|"
        table_body = "\n".join(rows)

        markdown_output = (
            f"### 払い戻し情報\n\n"
            f"{table_header}\n"
            f"{table_body}\n"
        )

        return markdown_output
