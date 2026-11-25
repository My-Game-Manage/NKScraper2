"""
date_utils.py
競馬スクレイピング・分析エンジン用 日付処理ユーティリティモジュール

スクレイパー（scraper.py）やファイルライター（writer.py）などに散在していた
日付取得・正規化・フォーマット変換処理を集約した共通モジュールです。
"""

from datetime import datetime, timedelta, timezone
from typing import Optional, Tuple, Any

# 日本時間（JST: UTC+9）のタイムゾーン定義
JST = timezone(timedelta(hours=9), 'JST')


def get_today_jst() -> str:
    """
    現在の日本時間（JST）における日付を 'YYYYMMDD' 形式（8桁文字列）で取得します。
    
    Returns:
        str: 'YYYYMMDD' 形式の文字列（例: '20261125'）
    """
    return datetime.now(JST).strftime('%Y%m%d')


def get_yesterday_date() -> str:
    """
    現在の日本時間（JST）における昨日の日付を 'YYYYMMDD' 形式（8桁文字列）で取得します。
    
    Returns:
        str: 'YYYYMMDD' 形式の文字列
    """
    return (datetime.now(JST) - timedelta(days=1)).strftime('%Y%m%d')


def normalize_date_format(date_val: Any) -> str:
    """
    入力された日付（datetimeオブジェクト、ハイフン/スラッシュ区切り文字列、8桁数字文字列など）を
    統一的な 8桁文字列 'YYYYMMDD' に正規化します。

    Args:
        date_val: 日付を表す入力値 (str, datetime, etc.)

    Returns:
        str: 'YYYYMMDD' 形式の文字列。入力が無効・空の場合は空文字列。
    """
    if not date_val:
        return ""

    if isinstance(date_val, datetime):
        return date_val.strftime('%Y%m%d')

    date_str = str(date_val).strip()
    
    # 既に 8桁の数値文字列の場合
    if len(date_str) == 8 and date_str.isdigit():
        return date_str

    # ハイフンやスラッシュ等の記号を除去して数字列を抽出
    digits_only = "".join(filter(str.isdigit, date_str))
    if len(digits_only) >= 8:
        return digits_only[:8]

    return digits_only


def determine_target_date(input_date: Optional[Any] = None) -> str:
    """
    処理対象の日付を決定します。
    指定がある場合は正規化して返し、指定がない場合は本日のJST日付を返します。

    Args:
        input_date: 指定日付（省略時またはNone/空文字列の場合は本日日付）

    Returns:
        str: 'YYYYMMDD' 形式の文字列
    """
    if input_date:
        normalized = normalize_date_format(input_date)
        if normalized:
            return normalized
    return get_today_jst()


# 元コードにあったタイポ関数名（determinate_target_date）との後方互換性エイリアス
determinate_target_date = determine_target_date


def extract_year_month(date_val: Any) -> Tuple[str, str]:
    """
    日付表現から (年: 'YYYY', 月: 'MM') のタプルを抽出します。
    保存ディレクトリ階層（例: data/results/2026/05/）の構築等に使用します。

    Args:
        date_val: 日付を表す入力値 (例: "2026-05-04", "20260504", datetimeオブジェクト)

    Returns:
        Tuple[str, str]: ('YYYY', 'MM') のタプル。解析不能な場合は ('', '')
    """
    normalized = normalize_date_format(date_val)
    if len(normalized) >= 6:
        return normalized[:4], normalized[4:6]
    return "", ""
