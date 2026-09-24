# ER Diagram

投資判断プラットフォームの現行 DB スキーマを表す ER 図です。

スキーマ定義の正本は [Alembic migration](../../backend/migrations/versions/) です。

## ER 図

<!-- generated:er-diagram start -->
```mermaid
erDiagram
    strategy ||--o{ theme : strategy_id
    data_source ||--o{ ingestion_run : source_id
    ingestion_run ||--o{ ingestion_error : ingestion_run_id
    investment_target ||--o{ investment_target_identifier : target_id
    data_source ||--o{ investment_target_identifier : source_id
    theme ||--o{ theme_investment_target : theme_id
    investment_target ||--o{ theme_investment_target : target_id
    investment_target ||--o{ market_price_observation : target_id
    data_source ||--o{ market_price_observation : source_id
    ingestion_run ||--o{ market_price_observation : ingestion_run_id
    investment_target ||--o{ financial_disclosure : target_id
    data_source ||--o{ financial_disclosure : source_id
    ingestion_run ||--o{ financial_disclosure : ingestion_run_id
    financial_disclosure ||--o| financial_summary : disclosure_id
```
<!-- generated:er-diagram end -->

## テーブル一覧

| テーブル | 説明 |
|---|---|
| `strategy` | 投資戦略マスタ |
| `theme` | 投資テーマ。`strategy_id`で戦略に所属 |
| `investment_target` | 投資対象マスタ（個別株・ETF・投資信託・REIT・債券・指数・商品） |
| `data_source` | J-Quants、FRED等のデータ取得先 |
| `investment_target_identifier` | 内部銘柄とJ-Quants Code、ticker等の対応 |
| `ingestion_run` | データ取得・ETLの実行履歴と件数 |
| `ingestion_error` | 実行中の部分失敗と再試行可否 |
| `theme_investment_target` | テーマ×銘柄（basket_weight） |
| `market_price_observation` | 銘柄・取得元・取引日単位のOHLCV価格観測と来歴 |
| `financial_disclosure` | 開示番号ごとの決算開示履歴 |
| `financial_summary` | 開示に対応する実績・会社予想・配当サマリー |

## 役割別構成

```mermaid
flowchart TB
    subgraph Master[Master / Dimension-like]
        strategy
        theme
        investment_target
        data_source
    end

    subgraph Relationship[Relationship]
        theme_investment_target
        investment_target_identifier
    end

    subgraph Observed[Observed Facts]
        market_price_observation
        financial_disclosure
        financial_summary
    end

    subgraph Provenance[Ingestion Provenance]
        ingestion_run
        ingestion_error
    end

    strategy --> theme
    theme --> theme_investment_target
    investment_target --> theme_investment_target
    investment_target --> investment_target_identifier
    data_source --> investment_target_identifier
    investment_target --> market_price_observation
    data_source --> market_price_observation
    ingestion_run --> market_price_observation
    investment_target --> financial_disclosure
    data_source --> financial_disclosure
    ingestion_run --> financial_disclosure
    financial_disclosure --> financial_summary
    data_source --> ingestion_run
    ingestion_run --> ingestion_error
```
