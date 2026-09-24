# 投資データ基盤の目標アーキテクチャ

## 位置づけ

この文書は現在と将来に共通する論理データ層の境界を定めます。物理スキーマの正本は
[Alembic migration](../../backend/migrations/versions/)、列定義の正本は
[`schema-data-dictionary.md`](schema-data-dictionary.md)です。



## 設計原則

データを次の責務に分離します。

1. **Master** — 何を観測・分類・投資するか
2. **Observed** — 外部から取得し、内部形式へ正規化した一次観測
3. **Derived** — Observedから再計算可能な特徴量、リターン、リスク指標、ファクター
4. **Assessment** — 閾値・モデル・ルールによるバージョン付きの評価・解釈
5. **Decision** — Assessmentを踏まえた人またはシステムの意思決定
6. **Outcome** — 注文、約定、入出金、手数料など実際に発生した取引事実

外部提供者が加工した値でも、この基盤が外部入力として取得したものはObservedとします。
自基盤内で生成した値だけをDerivedとします。

## 現行スキーマとの対応

| 論理層 | 現在の物理テーブル・状態 |
|---|---|
| Master | `investment_target`, `theme`, `strategy`, `data_source`, `investment_target_identifier` |
| Observed | `market_price_observation`, `financial_disclosure`, `financial_summary` |
| Derived | 未実装。分析要件が確定してからmart等で追加 |
| Assessment | 未実装。独立した評価領域として追加 |
| Decision | 未実装。Assessmentとは分離して追加 |
| Outcome | 未実装。注文・約定等のFactとして追加 |

関連指標、閾値、状態、構造判定、テーマとの意味的な関係は現在の物理スキーマに持たせません。
必要になった場合も、関連指標のObservedと、判断の定義・結果・Evidenceを別の責務として設計します。

## ファクト基盤と判断領域の境界

Master、Observed、Derivedは、同じ入力と計算定義から同じ結果を再現できるデータ基盤として
堅牢に設計します。取得元、利用可能時点、取込実行、計算定義を追跡し、一次観測は原則として
上書きせず履歴を保持します。

AssessmentとDecisionは唯一の正解を表すFactではありません。同じ銘柄・評価日でも、戦略、
ルール、モデル、パラメータが異なれば複数の評価と判断が成立します。そのため、評価結果を
`investment_target`や`theme`へ直接保存せず、次を満たす独立した領域として扱います。

- ルール、モデル、プロンプト、パラメータをバージョン管理する
- `as_of_date`を保持し、その時点で利用可能だったデータだけを入力にする
- 結果を実行単位で追記し、過去の解釈を上書きしない
- 結果から入力Factと特徴量へ遡れるEvidenceを保存する
- Assessmentと、最終的な採用・却下・上書きであるDecisionを分離する
- FastAPIのRouterへ判定ロジックを持たせず、PipelineまたはServiceへ委譲する

Outcomeは判断領域から分離します。注文、約定、数量、価格、入出金、手数料は実際に発生した
取引Factとして、Observedと同様に堅牢な履歴として扱います。保有は約定から導出する状態または
スナップショット、実現・未実現損益は計算方式に依存するDerivedとして分離します。
AssessmentがBUYでもDecisionがHOLDになる場合があるため、Assessment、Decision、Outcomeの
差分も分析可能にします。

```text
Master / Observed / Derived
        ↓ 読み取り
Assessment Pipeline
        ↓ バージョン付き評価とEvidence
Decision Layer
        ↓ 採用・却下・上書き
Outcome
        ↓ 約定・損益というFact
分析基盤へ還流
```

### 将来の論理テーブル候補

物理スキーマはAssessment Pipelineの要件確定後に決めますが、責務境界は次を基準とします。

| 論理テーブル | 責務 |
|---|---|
| `assessment_definition` | 評価方法、ルール・モデル・パラメータ・コードのバージョン |
| `assessment_run` | 評価実行、評価時点、`as_of_date`、実行状態 |
| `assessment_result` | テーマまたは投資対象に対するスコア、ラベル、確信度、説明 |
| `assessment_evidence` | 結果に利用したFact、特徴量、値への参照 |
| `decision` | 評価を踏まえた行動、決定者、理由、採否 |
| `order` / `execution` | 発注・約定というOutcome Fact |

これらの物理テーブルと判断Serviceは先行実装しません。要件確定後はAssessment Pipelineが結果を
永続化し、APIは保存済みの最新結果と履歴を読み取る構成を目標とします。

## 時間と来歴

時系列データでは、可能な範囲で次を区別します。

- `obs_date` / reference period — 値が表す対象日・対象期間
- `available_at` / disclosed time — 利用可能になった時点
- `fetched_at` — 基盤が取得した時点
- `ingestion_run_id` — 取得・変換・検証を実行した処理
- `source_id` — 取得元
- value type — actual、company forecast、consensus等

「過去・現在・未来」は固定属性として保存せず、評価時点と対象期間から導出します。

## 将来の加算的拡張

必要性が確認された場合に限り、次を別テーブルまたは分析martとして追加します。

- Event factと対象への影響
- リターン、ボラティリティ、β等のDerivedデータ
- Factor master、model、value、target exposure
- Assessment、signal、decision、outcomeの履歴
- 投資信託・REIT・債券・商品へのデータ取得拡張

`theme`は投資仮説・分類、`investment_target`は価格を持つ投資可能商品として分離し、
両者の対応は`theme_investment_target`で表現します。
また、OHLCや財務値を汎用的な`metric_id/value`形式へ統合せず、型と制約を持つ専用Factを使います。
