"""
all_html_dump.py - Playwrightブラウザ自動化・HTMLダンプ取得モジュール
"""

import logging
import threading
from typing import Optional, List
from playwright.sync_api import sync_playwright

logger = logging.getLogger(__name__)


class NkPlaywrightClient:
    """
    Playwrightブラウザインスタンスを常駐・再利用し、
    スクレイピング毎のブラウザ起動/停止オーバーヘッドを防止するクライアントクラス
    """

    def __init__(self, headless: bool = True):
        self.headless = headless
        self._playwright = None
        self._browser = None
        self._context = None

    def start(self):
        """ブラウザインスタンスを一回だけ起動して常駐させる"""
        if not self._playwright:
            self._playwright = sync_playwright().start()
            self._browser = self._playwright.chromium.launch(headless=self.headless)
            self._context = self._browser.new_context()
            logger.info("🚀 Playwrightブラウザインスタンスを常駐開始しました。")

    def fetch_js_html(self, url: str, selector: str = "") -> str:
        """起動済みのブラウザから新しいタブ(Page)のみを開閉してHTMLを取得"""
        if not self._browser:
            self.start()

        page = self._context.new_page()
        try:
            logger.info(f"ページにアクセス中: {url}")
            page.goto(url, wait_until="domcontentloaded")

            if selector:
                try:
                    page.wait_for_selector(selector, timeout=10000)
                    logger.info(f"指定要素 ({selector}) の読み込みを確認しました。")
                except Exception as e:
                    logger.warning(f"指定要素の読み込みを待機タイムアウトしました ({selector}): {e}")

            return page.content()
        finally:
            page.close()  # タブ(Page)のみを閉じ、ブラウザプロセス自体は維持

    def close(self):
        """全スクレイピング完了時に一括でブラウザを終了破棄"""
        if self._browser:
            try:
                self._browser.close()
            except Exception:
                pass
            self._browser = None
        if self._playwright:
            try:
                self._playwright.stop()
            except Exception:
                pass
            self._playwright = None
        logger.info("🛑 Playwrightブラウザインスタンスを終了しました。")


class NkPlaywrightClientManager:
    """
    マルチスレッド対応 Playwright クライアントマネージャー
    スレッドごとに独立した Playwright ブラウザを隔離管理し、全スレッド終了時に安全に一括破棄する
    """

    def __init__(self, headless: bool = True):
        self.headless = headless
        self._clients: List[NkPlaywrightClient] = []
        self._lock = threading.Lock()
        self._thread_local = threading.local()

    def get_client(self) -> NkPlaywrightClient:
        """現在のスレッド専用の Playwright クライアントを取得（無ければ作成）"""
        if not hasattr(self._thread_local, "client") or self._thread_local.client is None:
            client = NkPlaywrightClient(headless=self.headless)
            client.start()
            self._thread_local.client = client
            with self._lock:
                self._clients.append(client)
        return self._thread_local.client

    def close_all(self):
        """管理下の全スレッドの Playwright ブラウザを安全に解放・破棄"""
        with self._lock:
            for client in self._clients:
                try:
                    client.close()
                except Exception as e:
                    logger.debug(f"Playwright クライアント破棄中ログ: {e}")
            self._clients.clear()
            if hasattr(self._thread_local, "client"):
                self._thread_local.client = None


# 単発呼び出し用フォールバック関数
def fetch_js_html(url: str, selector: str = "") -> str:
    """単発実行用のフォールバック関数（1回限りの起動/停止）"""
    client = NkPlaywrightClient(headless=True)
    try:
        return client.fetch_js_html(url, selector)
    finally:
        client.close()
