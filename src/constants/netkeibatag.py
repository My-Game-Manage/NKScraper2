# netkeibaのページのクラス名等

class ShutubaSelector:
    RACE_NAME = ".RaceName"
    RACE_DATA = ".RaceData01"
    RACE_DATA02 = ".RaceData02"     # 日付や開催場所が含まれるエリア
    BRACKET_NUM = "td[class*='Waku']"
    HORSE_NUM = "td[class*='Umaban']"
    WEIGHT_CARRIED = "td:nth-of-type(6)"
    JOCKEY = ".Jockey a"
    STABLE = ".Trainer"
    HORSE_NAME = ".HorseName a"
    AGE_NAR = ".Age"                # 地方競馬用
    AGE = ".Barei"                  # 中央競馬用
    HORSE_WEIGHT = ".Weight"
    HORSE_LIST = "tr.HorseList"     # 出馬表テーブル
