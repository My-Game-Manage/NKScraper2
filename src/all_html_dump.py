from playwright.async_api import async_playwright


async def fetch_horse_html(url):
  """指定したURL（馬情報ページなど）からJavaScript実行後のHTMLを非同期で取得する"""
  async with async_playwright() as p:
    # ブラウザの起動
    browser = await p.chromium.launch(headless=True)
    page = await browser.new_page()

    print(f"ページにアクセス中: {url}")
    # ページへ移動（コンテンツの読み込み完了まで待機）
    await page.goto(url, wait_until="domcontentloaded")

    # レンダリング済みのHTMLを取得
    html_content = await page.content()

    await browser.close()
    print("HTMLの取得が完了しました。")
    return html_content
