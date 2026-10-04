from playwright.sync_api import sync_playwright

# ロガー設定
import logging
logger = logging.getLogger(__name__)


def fetch_js_html(url: str, selector: str):
  """指定したURL（馬情報ページなど）からJavaScript実行後のHTMLを非同期で取得する"""
  with sync_playwright() as p:
    # ブラウザの起動
    browser = p.chromium.launch(headless=True)
    page = browser.new_page()

    logger.info(f"ページにアクセス中: {url}")
    page.goto(url, wait_until="domcontentloaded")

    # 【ポイント】戦績テーブルや特定の要素が読み込まれるまで最大10秒待機する
    # ※実際のページのテーブルのclass名やIDに合わせて調整してください（例: "table.db_h_race_results" など）
    try:
        page.wait_for_selector(
            selector, timeout=10000
        )  # 例
        print("戦績テーブルの読み込みを確認しました。")
    except Exception as e:
        logger.error(
            "指定したテーブルの読み込みを待機タイムアウトしました（またはセレクタが違います）: "
            f"{e}"
        )

    # 描画完了後のHTMLを取得
    html_content = page.content()
    browser.close()
    return html_content