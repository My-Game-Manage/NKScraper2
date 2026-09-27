from bs4 import BeautifulSoup
import json
import re
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

def scrape_netkeiba_race_info(url):
  # 1. サイトへのアクセス
  headers = {
      'User-Agent': (
          'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML,'
          ' like Gecko) Chrome/115.0.0.0 Safari/537.36'
      )
  }

  try:
    response = requests.get(url, headers=headers)
    response.raise_for_status()
  except requests.exceptions.RequestException as e:
    print(f'ページの取得に失敗しました: {e}')
    return None

  # netkeibaはEUC-JPの場合が多いので自動判定を利用
  response.encoding = response.apparent_encoding

  # 2. BeautifulSoupでHTMLを解析
  soup = BeautifulSoup(response.text, 'html.parser')

  race_data = {}

  try:
    # --- ① レース名の取得 ---
    # 例: <dl class="racedata"> や <div class="race_title"> 内の <h1> など
    #race_name_elem = soup.find('h1', class_=['race_name', 'RaceName'])
    race_name = (
        soup.select_one(SELECTORS["RACE_NAME"]).get_text(strip=True)
        if soup.select_one(SELECTORS["RACE_NAME"])
        else "Race_Name_Not_Found"
    )
    race_data['レース名'] = race_name

    #if not race_name_elem:
    #  # 見つからない場合は一般的なh1を探索
    #  race_name_elem = soup.find('h1')
    #race_data['レース名'] = (
    #    race_name_elem.get_text(strip=True) if race_name_elem else '不明'
    #)

    # --- ② メタ情報（開催日、回数、会場、距離、馬場、天候など）の取得 ---
    # netkeibaでは、これらの情報が小さなテキストや特定のclass（例: 'race_data01', 'race_data02' など）にまとまっています。
    # ここでは該当しうる要素を結合してテキストとして取得し、正規表現で各項目を分解して抽出します。

    meta_text = ''
    # よくあるメタ情報の格納クラスを複数探索
    for class_name in ['race_data01', 'race_data02', 'RaceData02', 'racedata', 'RaceData']:
      elem = soup.find(class_=class_name)
      if elem:
        meta_text += ' ' + elem.get_text(separator=' ', strip=True)

    # もし見つからなければ、ページ全体からそれらしい部分を補完、あるいはテキスト全体を対象にする
    if not meta_text:
      meta_text = soup.get_text()

    # --- 各項目の正規表現による抽出ロジック ---

    # A. 開催回・日目 & 開催会場の抽出 (例: "8回高知2日目" や "東京2回5日" など)
    race_data1 = (
        soup.select_one(SELECTORS["RACE_DATA"]).get_text(strip=True)
        if soup.select_one(SELECTORS["RACE_DATA"])
        else "Race_Name_Not_Found"
    )
    race_data2 = (
        soup.select_one(SELECTORS["RACE_DATA_02"]).get_text(strip=True)
        if soup.select_one(SELECTORS["RACE_DATA_02"])
        else "Race_Name_Not_Found"
    )

    #kai_match = re.search(r'(\d+回)?([^\d\s]+)?(\d+日目)', meta_text)
    #if kai_match:
    #  race_data['開催回・日目'] = kai_match.group(0)
    #  if kai_match.group(2):
    #    race_data['開催会場'] = kai_match.group(2).replace('回', '').strip()
    #  else:
    #    race_data['開催会場'] = '不明'
    #else:
    #  race_data['開催回・日目'] = '不明'
    #  race_data['開催会場'] = '不明'
    race_data['開催回・日目'] = race_data1
    race_data['開催会場'] = race_data2

    # B. レース番号の抽出 (例: "7R", "第7レース" など)
    r_num_match = re.search(r'(\d+R|第\d+レース)', meta_text)
    race_data['レース番号'] = r_num_match.group(1) if r_num_match else '不明'

    # C. レースグレードの抽出 (例: 重賞, G1, G2, OP など)
    grade_match = re.search(r'(G[1-3]|重賞|オープン|OP|L)', meta_text)
    race_data['レースグレード'] = (
        grade_match.group(1) if grade_match else '一般/その他'
    )

    # D. 発走時刻の抽出 (例: "18:15", "発走 15:35" など)
    time_match = re.search(r'(\d{1,2}:\d{2})', meta_text)
    race_data['発走時刻'] = time_match.group(1) if time_match else '不明'

    # E. レース種別（ダート・芝・障害）の抽出
    if 'ダ' in meta_text or 'ダート' in meta_text:
      race_data['レース種別'] = 'ダート'
    elif '芝' in meta_text:
      race_data['レース種別'] = '芝'
    elif '障害' in meta_text:
      race_data['レース種別'] = '障害'
    else:
      race_data['レース種別'] = '不明'

    # F. レース距離の抽出 (例: "1900m", "芝1600m" など)
    dist_match = re.search(r'(\d{3,4}m)', meta_text)
    race_data['レース距離'] = dist_match.group(1) if dist_match else '不明'

    # G. 天候・馬場の抽出 (例: "天候:雨", "馬場:不" など)
    weather_match = re.search(r'天候[:：]?\s*([^\s/]+)', meta_text)
    condition_match = re.search(r'馬場[:：]?\s*([^\s/]+)', meta_text)

    weather_str = (
        f'天候:{weather_match.group(1)}' if weather_match else '天候:不明'
    )
    cond_str = f'馬場:{condition_match.group(1)}' if condition_match else '馬場:不明'
    race_data['天候・馬場'] = f'{weather_str} / {cond_str}'

  except Exception as e:
    print(f'データ抽出中にエラーが発生しました: {e}')

  return race_data


# --- 実行部分 ---
if __name__ == '__main__':
  # サンプル用のURL（実際のnetkeibaのレース詳細URLに変更してください）
  target_url = 'https://db.netkeiba.com/race/202334090507/'

  print('データを抽出中...')
  extracted_info = scrape_netkeiba_race_info(target_url)

  if extracted_info:
    # 抽出した項目データのみをJSONファイルとして保存
    output_filename = 'race_info_summary.json'
    with open(output_filename, 'w', encoding='utf-8') as f:
      json.dump(extracted_info, f, ensure_ascii=False, indent=4)

    print(f'\n【保存完了】以下のレース情報を {output_filename} に保存しました：')
    for key, value in extracted_info.items():
      print(f'- {key}: {value}')