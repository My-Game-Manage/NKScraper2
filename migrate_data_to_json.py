"""
migrate_data_to_json.py - 過去の出馬表・馬データMarkdownを構造化JSONへ一括移行するスクリプト

1. data/ 配下の出馬表Markdown (00_race_overview.md 等) を全自動探索
2. RacePredictor.parse_shutuba_markdown でパースし、data/shutuba/YYYY/MM/*.json へ保存
3. data/ 配下の馬データMarkdown (horse_*.md 等) を探索・パースし、data/horses/{horse_id}.json へ保存
"""

import os
import json
import re
import logging
from pathlib import Path
from typing import Dict, List, Any, Optional

logging.basicConfig(level=logging.INFO, format="%(asctime)s [%(levelname)s] %(message)s")
logger = logging.getLogger("Migrator")


def extract_year_month(date_str: str) -> tuple[str, str]:
    """YYYYMMDD 文字列から (YYYY, MM) を抽出"""
    digits = "".join(filter(str.isdigit, str(date_str)))
    if len(digits) >= 6:
        return digits[:4], digits[4:6]
    return "unknown", "unknown"


def parse_shutuba_markdown(md_path: Path) -> Optional[Dict[str, Any]]:
    """出馬表Markdownファイルをパースして辞書化"""
    try:
        with open(md_path, "r", encoding="utf-8") as f:
            content = f.read()

        lines = content.splitlines()
        target_date = ""
        race_track = ""
        race_num = ""
        race_name = ""
        race_type = ""
        race_id = ""

        horses = []
        in_table = False

        for line in lines:
            line_str = line.strip()
            if "第" in line_str and "R:" in line_str:
                match = re.search(r"#+\s*(\d+)\s*-\s*【([^】]+)】第(\d+)R:\s*(.*)", line_str)
                if match:
                    target_date = match.group(1)
                    race_track = match.group(2)
                    race_num = str(int(match.group(3)))
                    race_name = match.group(4)
            elif "レースID" in line_str:
                race_id = re.sub(r"[^\d]", "", line_str)
            elif "コース" in line_str:
                race_type = re.sub(r"[\*\-\s\*]*\*\*コース\*\*\s*:\s*", "", line_str).strip()
            elif line_str.startswith("| 枠 | 馬番 |") or line_str.startswith("|枠|馬番|"):
                in_table = True
                continue
            elif in_table and (line_str.startswith("| ---") or line_str.startswith("|---")):
                continue
            elif in_table and line_str.startswith("|"):
                cols = [c.strip() for c in line_str.split("|")[1:-1]]
                if len(cols) >= 7:
                    b_num = cols[0]
                    h_num = cols[1]
                    h_name_raw = cols[2]
                    h_name = re.sub(r"\[(.*?)\]\(.*?\)", r"\1", h_name_raw)
                    h_name = re.sub(r"<[^>]+>", "", h_name).replace("<br>", "").replace("<br/>", "").strip()
                    age = cols[3]
                    weight = cols[4]
                    jockey = cols[5]
                    stable = cols[6]
                    h_id = cols[7] if len(cols) > 7 else ""

                    horses.append({
                        "bracket_num": b_num,
                        "horse_num": h_num,
                        "horse_name": h_name,
                        "horse_age": age,
                        "weight_carried": weight,
                        "jockey": jockey,
                        "stable": stable,
                        "horse_id": h_id
                    })

        if not horses:
            return None

        return {
            "race_id": race_id,
            "race_track": race_track,
            "race_num": race_num,
            "target_date": target_date,
            "race_name": race_name,
            "race_grade": "",
            "race_type": race_type,
            "race_distance": "",
            "weather": "",
            "condition": "",
            "race_class": "",
            "shutuba_horses": horses,
            "results": horses
        }
    except Exception as e:
        logger.error(f"出馬表Markdownパース失敗 ({md_path}): {e}")
        return None


def parse_horse_markdown(md_path: Path) -> Optional[Dict[str, Any]]:
    """馬データMarkdownファイルをパースして辞書化"""
    try:
        with open(md_path, "r", encoding="utf-8") as f:
            content = f.read()

        # ヘッダーから 馬ID と 馬名 を抽出
        # 例: # 馬番：01（馬ID：2021104567）／馬名：グランアプレ
        match_header = re.search(r"馬ID：(\d+)[\）\)]?／馬名：([^\n\r]+)", content)
        if not match_header:
            match_header = re.search(r"馬ID：(\d+)", content)
            if not match_header:
                return None
            horse_id = match_header.group(1)
            horse_name = ""
        else:
            horse_id = match_header.group(1)
            horse_name = match_header.group(2).strip()

        # 日付フォルダから日付推測 (例: data/20261126/...)
        target_date = ""
        date_match = re.search(r"(\d{8})", str(md_path))
        if date_match:
            target_date = date_match.group(1)

        # セクション分解
        prof_text = ""
        history_text = ""
        analyzed_text = ""

        if "## プロフィール" in content:
            parts = content.split("## プロフィール")
            if len(parts) > 1:
                sub = parts[1]
                if "## 過去戦績" in sub:
                    prof_text, sub2 = sub.split("## 過去戦績", 1)
                    if "## データ分析" in sub2:
                        history_text, analyzed_text = sub2.split("## データ分析", 1)
                    else:
                        history_text = sub2
                else:
                    prof_text = sub

        return {
            "horse_id": horse_id,
            "horse_name": horse_name,
            "updated_at": target_date,
            "horse_prof_raw": prof_text.strip(),
            "horse_history_raw": history_text.strip(),
            "analyzed_data_raw": analyzed_text.strip()
        }
    except Exception as e:
        logger.error(f"馬データMarkdownパース失敗 ({md_path}): {e}")
        return None


def migrate_all(data_dir: str = "data", test_mode: bool = False):
    root_dir = Path(data_dir)
    if not root_dir.exists():
        logger.warning(f"指定されたディレクトリが存在しません: {root_dir}")
        return

    logger.info(f"=== 移行処理開始 (対象: {root_dir}) ===")

    # -------------------------------------------------------------
    # 1. 出馬表Markdownの移行
    # -------------------------------------------------------------
    shutuba_count = 0
    # 00_race_overview.md または統合MDファイルを探索
    md_files = list(root_dir.glob("**/*00_race_overview.md"))
    if not md_files:
        # ディレクトリ配下の通常MDファイルを探索 (predictions, reports, protocols を除く)
        md_files = [
            p for p in root_dir.glob("**/*.md")
            if "predictions" not in p.parts
            and "reports" not in p.parts
            and "protocols" not in p.parts
            and "results" not in p.parts
            and not p.name.startswith("horse_")
            and not p.name.startswith("logic-")
            and not p.name.endswith("-bias.md")
        ]

    logger.info(f"探索された出馬表Markdownファイル数: {len(md_files)} 件")

    out_shutuba_base = Path("data_test/shutuba") if test_mode else Path("data/shutuba")

    for md_path in md_files:
        shutuba_dict = parse_shutuba_markdown(md_path)
        if not shutuba_dict:
            continue

        target_date = shutuba_dict.get("target_date", "")
        race_track = shutuba_dict.get("race_track", "")
        race_num = str(shutuba_dict.get("race_num", "")).zfill(2)
        race_id = shutuba_dict.get("race_id", "")

        year, month = extract_year_month(target_date)
        save_dir = out_shutuba_base / year / month if year != "unknown" else out_shutuba_base
        save_dir.mkdir(parents=True, exist_ok=True)

        filename = f"{target_date}-{race_track}{race_num}R.json" if target_date and race_track else f"{race_id}.json"
        save_path = save_dir / filename

        with open(save_path, "w", encoding="utf-8") as f:
            json.dump(shutuba_dict, f, ensure_ascii=False, indent=2)

        logger.info(f"✅ 出馬表JSON移行完了: {save_path}")
        shutuba_count += 1

    # -------------------------------------------------------------
    # 2. 馬データMarkdownの移行
    # -------------------------------------------------------------
    horse_count = 0
    horse_md_files = list(root_dir.glob("**/horse_*.md"))
    logger.info(f"探索された馬データMarkdownファイル数: {len(horse_md_files)} 件")

    out_horse_base = Path("data_test/horses") if test_mode else Path("data/horses")
    out_horse_base.mkdir(parents=True, exist_ok=True)

    for h_path in horse_md_files:
        h_dict = parse_horse_markdown(h_path)
        if not h_dict or not h_dict.get("horse_id"):
            continue

        h_id = h_dict["horse_id"]
        json_path = out_horse_base / f"{h_id}.json"

        # 既存JSONがあれば読み込んでマージまたは上書き確認
        if json_path.exists():
            try:
                with open(json_path, "r", encoding="utf-8") as f:
                    existing_data = json.load(f)
                # 既存データに補完
                if not existing_data.get("horse_name") and h_dict.get("horse_name"):
                    existing_data["horse_name"] = h_dict["horse_name"]
                payload = existing_data
            except Exception:
                payload = h_dict
        else:
            payload = h_dict

        with open(json_path, "w", encoding="utf-8") as f:
            json.dump(payload, f, ensure_ascii=False, indent=2)

        logger.info(f"✅ 馬データJSON移行完了: {json_path}")
        horse_count += 1

    logger.info(f"🎉 移行処理完了! [出馬表JSON: {shutuba_count} 件, 馬データJSON: {horse_count} 件]")


if __name__ == "__main__":
    import argparse
    parser = argparse.ArgumentParser(description="過去のMarkdown資産をJSON構造へ一括移行します。")
    parser.add_argument("--data_dir", type=str, default="data", help="データルートディレクトリ (デフォルト: data)")
    parser.add_argument("--test", action="store_true", help="data_test ディレクトリへ保存")
    args = parser.parse_args()

    migrate_all(data_dir=args.data_dir, test_mode=args.test)
