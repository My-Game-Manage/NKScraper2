import asyncio
from playwright.async_api import async_playwright

async def save_dynamic_html():
    url = "https://db.netkeiba.com/horse/2021100642/"
    
    async with async_playwright() as p:
        browser = await p.chromium.launch(headless=True)
        page = await browser.new_page()
        
        print("ページにアクセスしています...")
        # networkidle から domcontentloaded に変更し、タイムアウトも 60秒に延長
        await page.goto(url, wait_until="domcontentloaded", timeout=60000)
        
        # もし特定の要素（出馬表のテーブルなど）が完全に表示されるまで待ちたい場合は以下を追加
        # await page.wait_for_selector(".RaceTable01", timeout=10000)
        
        # 動的に生成されたHTMLを取得
        html_content = await page.content()
        
        # ファイルとして保存
        output_file = "samples/netkeiba_horse.html"
        with open(output_file, "w", encoding="utf-8") as f:
            f.write(html_content)
            
        print(f"成功: HTMLを '{output_file}' に保存しました。")
        
        await browser.close()

if __name__ == "__main__":
    asyncio.run(save_dynamic_html())