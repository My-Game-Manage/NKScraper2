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

class GradeSelector:
    GRADE_G1 = ".Icon_GradeType1"
    GRADE_G2 = ".Icon_GradeType2"
    GRADE_G3 = ".Icon_GradeType3"
    GRADE_MAJOR = ".Icon_GradeType4"
    GRADE_OP = ".Icon_GradeType5"
    GRADE_L = ".Icon_GradeType15"
    GRADE_3W = ".Icon_GradeType16"
    GRADE_2W = ".Icon_GradeType17"
    GRADE_1W = ".Icon_GradeType18"
    GRADE_JPN1 = ".Icon_GradeType19"
    GRADE_JPN2 = ".Icon_GradeType20"
    GRADE_JPN3 = ".Icon_GradeType21"

    @classmethod
    def to_japanese(cls, selector: str) -> str:
        """セレクタ文字列から対応する日本語・表示名へ変換する"""
        mapping = {
            cls.GRADE_G1: "G1",
            cls.GRADE_G2: "G2",
            cls.GRADE_G3: "G3",
            cls.GRADE_MAJOR: "重賞",
            cls.GRADE_OP: "オープン",
            cls.GRADE_L: "L",
            cls.GRADE_3W: "3勝クラス",
            cls.GRADE_2W: "2勝クラス",
            cls.GRADE_1W: "1勝クラス",
            cls.GRADE_JPN1: "Jpn1",
            cls.GRADE_JPN2: "Jpn2",
            cls.GRADE_JPN3: "Jpn3",
        }
        return mapping.get(selector, "不明")

    @classmethod
    def get_selectors(cls) -> list:
        return [
            cls.GRADE_G1,
            cls.GRADE_G2,
            cls.GRADE_G3,
            cls.GRADE_MAJOR,
            cls.GRADE_OP,
            cls.GRADE_L,
            cls.GRADE_3W,
            cls.GRADE_2W,
            cls.GRADE_1W,
            cls.GRADE_JPN1,
            cls.GRADE_JPN2,
            cls.GRADE_JPN3,
        ]

class ResultSelector:
    RACE_NAME = ".RaceName"
    RACE_DATA = ".RaceData01"
    RACE_DATA02 = ".RaceData02"     # 日付や開催場所が含まれるエリア
    BRACKET_NUM = "td[class*='Waku']"
    HORSE_NUM = "td[class='Num Txt_C']"
    HORSE_NUM_NAR = "td[class='Num Waku']"
    WEIGHT_CARRIED = "td:nth-of-type(6)"
    JOCKEY = ".Jockey a"
    STABLE = ".Trainer"
    HORSE_NAME = ".Horse_Name"
    AGE = ".Horse_Info_Detail"      # 中央・地方共通
    HORSE_WEIGHT = ".Weight"
    HORSE_LIST = "tr.HorseList"     # 出馬表テーブル
    RANK = ".Rank"
    ODDS = "td[class='Odds Txt_R']"
    LAST_3F = "td:nth-of-type(12)"
    POPULARITY = ".OddsPeople"
    PASSING_ORDER = ".PassageRate"  # 中央競馬のみ
    MARGIN = "td:nth-of-type(9)"
    TIME = ".Time"
    LAST3F_1ST = ".BgYellow"        # 上がり1番
    LAST3F_2ND = ".BgBlue"          # 上がり2番
    LAST3F_3RD = ".BgOrange"        # 上がり3番
    WEIGHT_DIFF = ".WeightDiff"

class HorseDBSelector:
    LAST3F_1ST = ".rank_1"
    LAST3F_2ND = ".rank_2"
    LAST3F_3RD = ".rank_3"

JYO_NAME_MAP = {
    '01': '札幌', '02': '函館', '03': '福島', '04': '新潟',
    '05': '東京', '06': '中山', '07': '中京', '08': '京都',
    '09': '阪神', '10': '小倉',
    '30': '門別', '35': '盛岡',
    '36': '水沢', '42': '浦和', '43': '船橋', '44': '大井',
    '45': '川崎', '46': '金沢', '47': '笠松', '48': '名古屋',
    '50': '園田', '51': '姫路', '54': '高知', '55': '佐賀',
    '65': '帯広',
}

# 地方競馬(NAR)か中央競馬(JRA)かを判定する境界
JRA_MAX_COURSE_CODE = 10

# 除外する場所名
EXCLUDE_COURSES = {
    '帯広', '不明',
}