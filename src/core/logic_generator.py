"""
logic_generator.py - 会場別プロトコルおよび自動検出パッチ対応 Markdown 生成ユーティリティ

simulator.py の VenueRuleFinder / ParameterOptimizer で算出された
会場別最適化パラメータおよび統計的特例パッチ（重馬場補正、枠順リスク等）を読み込み、
Gemini Notebook が解釈可能な統合予想プロトコル Markdown (logic-{venue}-v1.8.md) を自動作成します。
"""

import logging
from pathlib import Path
from typing import Dict, List, Any, Optional, Union

try:
    from simulator import SimulationConfig
except ImportError:
    try:
        from src.core.simulator import SimulationConfig
    except ImportError:
        class SimulationConfig:
            pass

try:
    from writer import NkWriter
except ImportError:
    try:
        from src.core.writer import NkWriter
    except ImportError:
        class NkWriter:
            def save_as_markdown(self, target_date, track_name, filename, contents, is_test=False):
                path = Path("data") / target_date / track_name / filename
                path.parent.mkdir(parents=True, exist_ok=True)
                with open(path, "w", encoding="utf-8") as f:
                    f.write(contents)
                return path

logger = logging.getLogger(__name__)


class NkLogicGenerator:
    """最適化されたハイパーパラメータおよび自動検出パッチからプロトコル Markdown を生成するクラス"""

    def __init__(self, writer: Optional[NkWriter] = None):
        self.writer = writer or NkWriter()

    def generate_markdown_protocol(
        self,
        config: SimulationConfig,
        version: str = "v1.8",
        target_venue: str = "全場共通",
        backtest_stats: Optional[Dict[str, Any]] = None,
        detected_patches: Optional[List[Dict[str, Any]]] = None,
    ) -> str:
        """
        会場別の最適化パラメータおよび検出された特例パッチを埋め込んだ統合推論プロトコル Markdown を生成する
        """
        stats = backtest_stats or {}
        patches = detected_patches or []

        total_races = stats.get("total_races", 0)
        roi = stats.get("recovery_rate", 0.0)
        hit_rate = stats.get("hit_rate", 0.0)

        # 自動検出パッチのテキスト組み立て
        patch_section_lines = []
        if patches:
            for p in patches:
                patch_section_lines.append(f"### 📌 {p.get('title', '特例パッチ')}")
                patch_section_lines.append(f"- **適用条件**: {p.get('condition', '')}")
                patch_section_lines.append(f"- **補正内容**: {p.get('effect_description', '')}")
                patch_section_lines.append(f"- **スコア調整**: `{p.get('score_delta', 0.0):+0.1f}点`\n")
            patches_text = "\n".join(patch_section_lines)
        else:
            patches_text = "> 現時点で過去データから特別な統計的異常値・特例ルールは検出されていません。\n"

        md_content = f"""# 【自動生成】Gemini Notebook 競馬予想統合推論プロトコル ({target_venue}版 {version})

本プロトコルは、**【{target_venue}】** のレース出馬表・過去データサマリー・トラックバイアスレポート等を読み込み、バックテストで統計的に最適化された評価パラメータおよび自動検出された会場特例ルールに基づいて再現性の高い予想を出力するための統合運用規定です。

> **バックテスト最適化結果 ({target_venue}データ)**:
> - **対象レース数**: {total_races} 件
> - **検証回収率 (ROI)**: {roi}%
> - **検証的中率**: {hit_rate}%
> - **推奨賭式 / 選択頭数**: {getattr(config, 'bet_type', 'tansho')} / 上位 {getattr(config, 'top_n_selection', 1)} 頭
> - **軸馬購入最低スコア**: `{getattr(config, 'min_score_threshold', 40.0)} 点`

---

## 1. システム目的・データ参照プロトコル

### 1-1. 基本目的
事前取得された「レース基本情報」「出馬表」「過去戦績」「馬体重データ」を定量的に評価し、オッズ変動の影響を受けずに高精度な予想（◎○▲△☆）と回収率・的中率のバランスが取れた推奨買い目を出力します。

### 1-2. 参照データソース
1. **【レース基本情報】**: 開催場（{target_venue}）、レース番号、コース種別（芝/ダート、距離）、馬場状態、出走頭数。
2. **【出走馬分析データ】**: コーナー位置取り力（4角ポジション）、コース・距離別実績、近走タイム差・上がり3F実績、馬体重。
3. **【トラックバイアス・当日トレンド】**: 枠番別複勝率、4角ポジション別残存率、当日好調騎手・好調厩舎トレンド。

---

## 2. 【自動検出】{target_venue}固有の統計的特例パッチ

データ解析によって自動抽出された、{target_venue}特有の馬場・枠順・条件バイアスルールです。評価時に自動適用されます。

{patches_text}

---

## 3. 統合100点満点スコアリング・システム ({target_venue}最適化版)

各出走馬に対し、以下の評価軸で定量採点を行います（合計100点満点＋条件加減点）。

### ① 騎手・鞍上・厩舎評価
- **S評価騎手**: `+{getattr(config, 's_jockey_score', 20.0):.1f}点`
- **A評価騎手**: `+{getattr(config, 'a_jockey_score', 12.0):.1f}点`
- **若手・減量騎乗**: `+{getattr(config, 'young_jockey_score', 8.0):.1f}点`
- **トップ厩舎×S・A騎手 巻き返し補正**: `+{getattr(config, 'top_stable_revival_score', 10.0):.1f}点`

### ② コース・枠順・脚質・トラックバイアス適性
- **ダート外枠 (5~8枠)**: `+{getattr(config, 'dirt_outer_bracket_score', 15.0):.1f}点`
- **ダート内枠ペナルティ (1~3枠)**: `{getattr(config, 'dirt_inner_bracket_penalty', -8.0):.1f}点`
- **ダート大型馬 (480kg以上)**: `+{getattr(config, 'dirt_weight_boost', 5.0):.1f}点`
- **芝極限末脚 (上がり33.5秒以下実績)**: `+{getattr(config, 'turf_last3f_boost', 8.0):.1f}点`

### ③ 前走実績・ローテーション
- **前走同クラス 1着〜3着**: `+{getattr(config, 'prev_top3_score', 20.0):.1f}点`
- **前走同クラス 4着〜5着**: `+{getattr(config, 'prev_4_5th_score', 12.0):.1f}点`
- **前走10着以下大敗**: `{getattr(config, 'prev_blowout_penalty', -15.0):.1f}点`（※トップ厩舎×S/A騎手は `{getattr(config, 'prev_blowout_mitigated_penalty', -5.0):.1f}点` に緩和）

---

## 4. 予想印および推奨買い目出力プロトコル

### 4-1. 印の決定基準
- **◎ (本命)**: 総合スコア最高かつ `{getattr(config, 'min_score_threshold', 40.0)}点` 以上の最信頼馬。
- **○ (対抗)**: 総合スコア第2位の馬。
- **▲ (単穴)**: 総合スコア第3位の馬。
- **☆ (特注穴馬)**: 評価値が高く、特定条件（特例パッチや減量騎手外枠ブースト等）に適合する穴馬。
- **△ (連下)**: 総合スコア第4位以下の相手候補。

### 4-2. 買い目構成
- **推論賭式**: `{getattr(config, 'bet_type', 'tansho')}`
- **対象軸頭数**: 上位 `{getattr(config, 'top_n_selection', 1)}` 頭
"""
        return md_content

    def save_protocol(
        self,
        config: SimulationConfig,
        version: str = "v1.8",
        target_venue: str = "全場共通",
        backtest_stats: Optional[Dict[str, Any]] = None,
        detected_patches: Optional[List[Dict[str, Any]]] = None,
        target_date: str = "20261125",
        is_test: bool = False,
    ) -> Path:
        """Markdownプロトコルをファイルとして保存"""
        content = self.generate_markdown_protocol(config, version, target_venue, backtest_stats, detected_patches)
        filename = f"logic-{target_venue.lower()}-{version}.md"
        return self.writer.save_as_markdown(target_date, "protocols", filename, content, is_test)


if __name__ == "__main__":
    logging.basicConfig(level=logging.INFO)
    generator = NkLogicGenerator()
    dummy_config = SimulationConfig()
    dummy_patches = [
        {
            "rule_id": "BAD_TRACK_FRONT_RUNNER_BOOST",
            "title": "【自動検出パッチ】大井・重/不良馬場における前残り・ポジション倍率強化",
            "condition": "馬場状態が『重』または『不良』の開催日",
            "effect_description": "4角3番手以内の展開想定馬に対し、ポジションスコアを 1.25倍〜1.3倍（+5〜8点）へ自動増幅",
            "score_delta": 6.0
        }
    ]
    md = generator.generate_markdown_protocol(
        config=dummy_config,
        version="v1.8",
        target_venue="大井",
        backtest_stats={"total_races": 45, "recovery_rate": 118.4, "hit_rate": 31.1},
        detected_patches=dummy_patches
    )
    print("=== 生成テスト ===")
    print(md[:600])
