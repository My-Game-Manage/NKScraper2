from bs4 import BeautifulSoup
import json
import re
import requests

# ロガー設定
import logging
logger = logging.getLogger(__name__)

from src.constants.netkeibatag import ShutubaSelector
from src.netkeiba_client import NkClientSoup


class ScraperRaceInfo:
    def __init__(self):
        self.client = NkClientSoup()

    def get_shutuba_info(self, url):
        soup = self.client.get_soup(url)

        race_data = {}

        try:
            # レース名取得
            race_data["race_name"] = self._get_race_name(soup)
        except Exception as e:
            logger.info(f'データ抽出中にエラーが発生しました: {e}')
        return race_data

    def _get_race_name(self, soup):
        race_name = (
            soup.select_one(ShutubaSelector.RACE_NAME).get_text(strip=True)
            if soup.select_one(ShutubaSelector.RACE_NAME)
            else "Race_Name_Not_Found"
        )
        return race_name if race_name else "Unknown"