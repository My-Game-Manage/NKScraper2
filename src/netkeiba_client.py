# netkeibaアクセス用のツール

from bs4 import BeautifulSoup
import requests

# ロガー設定
import logging
logger = logging.getLogger(__name__)


class NkClientSoup:
    def __init__(self):
        self.headers = {
            'User-Agent': (
                'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML,'
                ' like Gecko) Chrome/115.0.0.0 Safari/537.36'
            )
        }

    def get_soup(self, url):
        try:
            response = requests.get(url, headers=self.headers)
            response.raise_for_status()
        except requests.exceptions.RequestException as e:
            logger.info(f"ページの取得に失敗しました: {e}")
            return None
        
        # netkeibaはEUC-JPの場合が多いので自動判定を利用
        response.encoding = response.apparent_encoding

        # 2. BeautifulSoupでHTMLを解析
        soup = BeautifulSoup(response.text, 'html.parser')

        return soup

