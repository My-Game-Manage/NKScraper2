from playwright.async_api import async_playwright

# ロガー設定
import logging
logger = logging.getLogger(__name__)


async def fetch_horse_html(url):
  """指定したURL（馬情報ページなど）からJavaScript実行後のHTMLを非同期で取得する"""
  async with async_playwright() as p:
    # ブラウザの起動
    browser = await p.chromium.launch(headless=True)
    page = await browser.new_page()

    logger.info(f"ページにアクセス中: {url}")
    await page.goto(url, wait_until="domcontentloaded")

    # 【ポイント】戦績テーブルや特定の要素が読み込まれるまで最大10秒待機する
    # ※実際のページのテーブルのclass名やIDに合わせて調整してください（例: "table.db_h_race_results" など）
    try:
        await page.wait_for_selector(
            "table.db_h_race_results", timeout=10000
        )  # 例
        print("戦績テーブルの読み込みを確認しました。")
    except Exception as e:
        logger.error(
            "指定したテーブルの読み込みを待機タイムアウトしました（またはセレクタが違います）: "
            f"{e}"
        )

    # 描画完了後のHTMLを取得
    html_content = await page.content()
    await browser.close()
    return html_content