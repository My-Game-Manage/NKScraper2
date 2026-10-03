import os
import re
import shutil
import urllib
from urllib.parse import parse_qs, urlparse
from bs4 import BeautifulSoup
import requests

# parser.txt の SELECTOR_TAG を流用した定義[cite: 1]
SELECTORS = {
    "RACE_NAME": ".RaceName",
    "RACE_DATA": ".RaceData01",
    "RACE_DATA_02": ".RaceData02",  # 日付や開催場所が含まれるエリア
    "BRACKET_NUM": "td[class*='Waku']",
    "HORSE_NUM": "td[class*='Umaban']",
    "WEIGHT_CARRIED": "td:nth-of-type(6)",
    "JOCKEY": ".Jockey a",
    "STABLE": ".Trainer",
    "HORSE_NAME": ".HorseName a",
    "AGE_NAR": ".Age",  # 地方競馬用[cite: 1]
    "AGE": ".Barei",
    "HORSE_WEIGHT": ".Weight",
}


def clean_filename(name):
    """ファイル名やフォルダ名に使用できない特殊文字を除去・置換する"""
    return re.sub(r'[\\/:*?"<>|]', "", name).strip()


def scrape_netkeiba_race(race_url):
    headers = {
        "User-Agent": (
            "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36"
            " (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36"
        )
    }

    response = requests.get(race_url, headers=headers)
    response.encoding = response.apparent_encoding
    soup = BeautifulSoup(
        response.content, "html.parser", from_encoding=response.encoding
    )

    # --- レース基本情報の取得[cite: 1] ---
    race_name = (
        soup.select_one(SELECTORS["RACE_NAME"]).get_text(strip=True)
        if soup.select_one(SELECTORS["RACE_NAME"])
        else "Race_Name_Not_Found"
    )
    race_data = (
        soup.select_one(SELECTORS["RACE_DATA"]).get_text(strip=True)
        if soup.select_one(SELECTORS["RACE_DATA"])
        else ""
    )

    # 地方競馬(NAR)判定と年齢セレクタの切り替え[cite: 1]
    is_nar = "nar.netkeiba.com" in race_url
    age_selector = SELECTORS["AGE_NAR"] if is_nar else SELECTORS["AGE"]

    # --- 1. レース番号の取得 ---
    parsed_url = urlparse(race_url)
    query_params = parse_qs(parsed_url.query)
    race_id_list = query_params.get("race_id")

    if race_id_list:
        race_id = race_id_list[0]
        race_num = race_id[-2:] + "R"  # 例: 12R
    else:
        race_num = "00R"

    # --- 2. 日付・会場名の取得 ---
    race_data_02 = (
        soup.select_one(SELECTORS["RACE_DATA_02"]).get_text(strip=True)
        if soup.select_one(SELECTORS["RACE_DATA_02"])
        else ""
    )

    # 日付の抽出 (例: 2026年07月24日 または 2026/07/24 や 7月24日(金) などのパターンに対応)
    date_match = re.search(r"(\d{4})[年/-](\d{1,2})[月/-](\d{1,2})", race_data_02)
    if date_match:
        year, month, day = date_match.groups()
        race_date = f"{year}{int(month):02d}{int(day):02d}"  # YYYYMMDD形式
    else:
        # URLのrace_id(先頭4桁+..)等から補完を試みるか、デフォルト値
        race_date = race_id[:4] if race_id_list and len(race_id) >= 4 else "Date_Unknown"

    # 会場名の抽出 (例: 園田、大井、東京 など)
    venue_match = re.search(r"\d+回([^\d\s]+)\d+日", race_data_02)
    if venue_match:
        venue_name = venue_match.group(1)
    else:
        # マッチしない場合はRaceData02の文字列から安全に抽出
        venue_name = "Venue_Unknown"

    # --- 3. 保存フォルダの作成 (日付-会場名-レース番号) ---
    folder_name = clean_filename(f"{race_id}-{venue_name}-{race_num}")
    os.makedirs(folder_name, exist_ok=True)
    print(f"保存先フォルダを作成しました: {folder_name}")

    # 出馬表テーブルの解析（tr.HorseList 行を対象とする）[cite: 1]
    rows = soup.select("tr.HorseList")
    if not rows:
        print("※出馬表テーブルの解析に失敗したか、構造が異なります。")
        return

    # データの抽出
    results = []
    for row in rows[0:-2]:
        data = {
            "枠番": (
                row.select_one(SELECTORS["BRACKET_NUM"]).get_text(strip=True)
                if row.select_one(SELECTORS["BRACKET_NUM"])
                else ""
            ),
            "馬番": (
                row.select_one(SELECTORS["HORSE_NUM"]).get_text(strip=True)
                if row.select_one(SELECTORS["HORSE_NUM"])
                else ""
            ),
            "馬名": (
                row.select_one(SELECTORS["HORSE_NAME"]).get_text(strip=True)
                if row.select_one(SELECTORS["HORSE_NAME"])
                else ""
            ),
            "性齢": (
                row.select_one(age_selector).get_text(strip=True)
                if row.select_one(age_selector)
                else ""
            ),
            "斤量": (
                row.select_one(SELECTORS["WEIGHT_CARRIED"]).get_text(
                    strip=True
                )
                if row.select_one(SELECTORS["WEIGHT_CARRIED"])
                else ""
            ),
            "騎手": (
                row.select_one(SELECTORS["JOCKEY"]).get_text(strip=True)
                if row.select_one(SELECTORS["JOCKEY"])
                else ""
            ),
            "厩舎": (
                row.select_one(SELECTORS["STABLE"]).get_text(strip=True)
                if row.select_one(SELECTORS["STABLE"])
                else ""
            ),
            "馬体重": (
                row.select_one(SELECTORS["HORSE_WEIGHT"]).get_text(strip=True)
                if row.select_one(SELECTORS["HORSE_WEIGHT"])
                else ""
            ),
        }
        results.append(data)

    # --- Markdown 形式での保存機能 ---
    md_lines = []
    md_lines.append(f"# {race_name}")
    md_lines.append(f"**詳細**: {race_data}\n")
    # ヘッダー作成
    md_lines.append(
        "| 枠番 | 馬番 | 馬名 | 性齢 | 斤量 | 騎手 | 厩舎 | 馬体重 |"
    )
    md_lines.append(
        "| :--- | :--- | :--- | :--- | :--- | :--- | :--- | :--- |"
    )
    # データ行作成
    for r in results:
        line = f"| {r['枠番']} | {r['馬番']} | {r['馬名']} | {r['性齢']} | {r['斤量']} | {r['騎手']} | {r['厩舎']} | {r['馬体重']} |"
        md_lines.append(line)

    # ファイル書き出し (作成したフォルダ内に保存)
    output_filename = clean_filename(f"race_shutuba_{race_num}.md")
    filepath_md = os.path.join(folder_name, output_filename)

    with open(filepath_md, "w", encoding="utf-8") as f:
        f.write("\n".join(md_lines))

    print(f"「{filepath_md}」にMarkdown出馬表を保存しました。")

    # リンク先リスト取得
    horses, jockeys = get_horses_jockeys_links(soup, race_url)

    # テキストファイルに出力 (フォルダ内に保存)
    save_to_txt(os.path.join(folder_name, "horses.txt"), horses)
    save_to_txt(os.path.join(folder_name, "jockeys.txt"), jockeys)

    # --- 4. フォルダをZIP圧縮 ---
    zip_path = zip_folder(folder_name)

    print("\nすべての処理が完了しました。")
    return zip_path


def get_horses_jockeys_links(soup, race_url):
    horse_urls = set()
    jockey_urls = set()

    for a_tag in soup.find_all("a", href=True):
        href = a_tag["href"]
        full_url = urllib.parse.urljoin(race_url, href)

        if "/horse/" in full_url:
            clean_url = full_url.split("?")[0]
            horse_urls.add(clean_url)

        elif "/jockey/" in full_url:
            clean_url = full_url.split("?")[0]
            jockey_urls.add(clean_url)

    return sorted(list(horse_urls)), sorted(list(jockey_urls))


def save_to_txt(filepath, url_list):
    """取得したURLリストをテキストファイルに書き込む関数"""
    try:
        with open(filepath, "w", encoding="utf-8") as f:
            for url in url_list:
                f.write(url + "\n")
        print(f"「{filepath}」に {len(url_list)} 件のURLを保存しました。")
    except Exception as e:
        print(f"ファイルの保存に失敗しました ({filepath}): {e}")

def zip_folder(folder_path):
    """指定されたフォルダをZIP圧縮する関数"""
    zip_filename = f"{folder_path}.zip"
    # shutil.make_archive を使用して指定されたフォルダをZIP化
    shutil.make_archive(
        base_name=folder_path,
        format="zip",
        root_dir=os.path.dirname(folder_path) or ".",
        base_dir=os.path.basename(folder_path),
    )
    print(f"フォルダをZIP圧縮しました: 「{zip_filename}」")
    return zip_filename

if __name__ == "__main__":
    target_url = (
        "https://nar.netkeiba.com/race/shutuba.html?race_id=202655092709"
    )
    scrape_netkeiba_race(target_url)