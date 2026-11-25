"""
競馬スクレイピング・分析エンジン - テキスト・数値変換・パース用ユーティリティ (text_utils.py)
"""

from typing import Any, List, Optional
import re
import pandas as pd


def extract_id_from_url(url: str) -> str:
    """URLの末尾パスまたはクエリパラメータからIDを抽出する

    例:
        - "https://db.netkeiba.com/horse/2020101234/" -> "2020101234"
        - "/race/shutuba.html?race_id=202654032801" -> "202654032801"
    """
    if not url:
        return ""
    match = re.search(r"race_id=(\d+)", url)
    if match:
        return match.group(1)

    clean_url = url.split("?")[0].rstrip("/")
    return clean_url.split("/")[-1]


def time_to_seconds(t_str: Any) -> Optional[float]:
    """タイム文字列（例: "2:05.6"）を秒数（float）に変換する"""
    if pd.isna(t_str) or not isinstance(t_str, str):
        return None
    try:
        parts = t_str.strip().split(":")
        if len(parts) == 2:
            return float(parts[0]) * 60 + float(parts[1])
        return float(parts[0])
    except (ValueError, TypeError):
        return None


def seconds_to_time(sec: Any) -> Optional[str]:
    """秒数（数値）を "分:秒.厘"（例: "2:04.4"）形式の文字列に戻す"""
    if pd.isna(sec) or sec is None:
        return None
    try:
        sec_float = float(sec)
        m = int(sec_float // 60)
        s = sec_float % 60
        return f"{m}:{s:04.1f}"
    except (ValueError, TypeError):
        return None


def extract_passing_positions(passing_str: Any) -> List[int]:
    """通過順文字列（例: "5-3-2", "4-4-5-3"）から各コーナーの通過順位のリストを抽出する"""
    if pd.isna(passing_str) or not isinstance(passing_str, str):
        return []
    return [int(p) for p in passing_str.split("-") if p.isdigit()]


def extract_last_corner_pos(passing_str: Any) -> Optional[int]:
    """通過順文字列から4角（最終コーナー）通過順位を抽出する"""
    positions = extract_passing_positions(passing_str)
    return positions[-1] if positions else None


def categorize_4th_corner(pos: Any) -> str:
    """4角通過順位を位置帯（逃げ・先行・中団前・中団後）に分類する"""
    if pd.isna(pos) or pos is None:
        return "不明"
    try:
        p = int(pos)
        if p == 1:
            return "1番手 (逃げ)"
        elif p <= 3:
            return "2〜3番手 (好位・先行)"
        elif p <= 5:
            return "4〜5番手 (中団前)"
        else:
            return "6番手以降 (中団後・追込)"
    except (ValueError, TypeError):
        return "不明"


def get_tactics(passing_str: Any) -> str:
    """通過順文字列から展開脚質（逃げ、先行、差し、追込）を判定する"""
    last_pos = extract_last_corner_pos(passing_str)
    if last_pos is None:
        return "不明"
    if last_pos == 1:
        return "逃げ"
    elif last_pos <= 4:
        return "先行"
    elif last_pos <= 8:
        return "差し"
    else:
        return "追込"


def simplify_track_condition(track_str: Any) -> str:
    """馬場状態（良, 稍重, 重, 不良など）を簡略化分類（良稍 / 重不）する"""
    if pd.isna(track_str) or not track_str:
        return ""
    t = str(track_str).strip()
    if t in ["良", "稍", "稍重"]:
        return "良稍"
    elif t in ["重", "不", "不良"]:
        return "重不"
    return t


def normalize_track_type(track_type: Any) -> str:
    """コースタイプ文字列から「芝」または「ダート」に正規化する"""
    if pd.isna(track_type) or not track_type:
        return "不明"
    t_str = str(track_type).strip()
    if "芝" in t_str:
        return "芝"
    elif "ダ" in t_str or "ダート" in t_str:
        return "ダート"
    elif "障" in t_str or "障害" in t_str:
        return "障害"
    return "不明"


def get_race_num_from_id(race_id: Any) -> str:
    """レースIDから末尾2桁のレース番号を取得する"""
    if not race_id:
        return ""
    return str(race_id)[-2:]


def get_course_code_from_id(race_id: Any) -> str:
    """レースIDから5-6桁目の会場コードを取得する"""
    r_str = str(race_id).strip()
    if len(r_str) < 6:
        return ""
    return r_str[4:6]


def is_nar_race_id(race_id: Any, jra_max_course_code: int = 10) -> bool:
    """レースIDから地方競馬（NAR）か中央競馬（JRA）か判定する"""
    code_str = get_course_code_from_id(race_id)
    if not code_str or not code_str.isdigit():
        return False
    return int(code_str) > jra_max_course_code


def dataframe_to_markdown_table(df: pd.DataFrame, constraint_notice: bool = True) -> str:
    """DataFrameをAIが誤認しにくい厳格なMarkdownテーブルに変換し、ハルシネーション防止用テキストを付与する"""
    header_notice = (
        "> **【制約事項】**\n"
        "> 以下の表に記載されているデータがすべての情報です。表に存在しない事項や数値について、推測・補完して回答してはなりません。\n\n"
    )

    if df is None or df.empty:
        empty_table = "| データなし |\n|:---|\n| データなし |\n\n"
        return (header_notice + empty_table) if constraint_notice else empty_table

    clean_df = df.copy().astype(str)
    clean_df = clean_df.replace(r"^(nan|None|NaN|<NA>|\s*)$", "データなし", regex=True)
    clean_df = clean_df.fillna("データなし")

    columns = list(clean_df.columns)
    header = "| " + " | ".join(columns) + " |"
    separator = "| " + " | ".join([":---" for _ in columns]) + " |"

    rows = []
    for _, row in clean_df.iterrows():
        row_vals = [str(val).strip() if str(val).strip() != "" else "データなし" for val in row]
        rows.append("| " + " | ".join(row_vals) + " |")

    table_str = "\n".join([header, separator] + rows)

    if constraint_notice:
        return f"{header_notice}{table_str}\n\n"
    return f"{table_str}\n\n"
