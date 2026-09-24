# スキーマ構造リファレンス（自動生成）

このファイルは `generate_schema_docs.py` が
[初期migration](../../backend/migrations/versions/0001_initial_postgresql.py) から生成します。
**直接編集しないでください。**

列の意味・由来・運用ルールは [`schema-data-dictionary.md`](schema-data-dictionary.md)、
論理層の設計方針は [`design-principles.md`](design-principles.md) を参照してください。

## テーブル一覧

| テーブル | 列数 | 主キー |
|---|---|---|
| `strategy` | 7 | `strategy_id` |
| `theme` | 8 | `theme_id` |
| `investment_target` | 9 | `target_id` |
| `data_source` | 8 | `source_id` |
| `ingestion_run` | 16 | `ingestion_run_id` |
| `ingestion_error` | 9 | `error_id` |
| `investment_target_identifier` | 10 | `investment_target_identifier_id` |
| `theme_investment_target` | 7 | `theme_id`, `target_id` |
| `market_price_observation` | 14 | `log_id` |
| `financial_disclosure` | 18 | `disclosure_id` |
| `financial_summary` | 31 | `disclosure_id` |

## テーブル定義

### `strategy`

| 列 | 型 | NULL | 既定値 | 列挙値 |
|---|---|---|---|---|
| `strategy_id` | BIGINT | NO | `AS` | - |
| `strategy_key` | TEXT | NO | - | - |
| `strategy_name` | TEXT | NO | - | - |
| `description` | TEXT | YES | - | - |
| `is_active` | BOOLEAN | NO | `TRUE` | - |
| `created_at` | TIMESTAMPTZ | NO | `CURRENT_TIMESTAMP` | - |
| `updated_at` | TIMESTAMPTZ | NO | `CURRENT_TIMESTAMP` | - |

- 主キー: `strategy_id`

### `theme`

| 列 | 型 | NULL | 既定値 | 列挙値 |
|---|---|---|---|---|
| `theme_id` | BIGINT | NO | `AS` | - |
| `theme_key` | TEXT | NO | - | - |
| `theme_name` | TEXT | NO | - | - |
| `strategy_id` | BIGINT | NO | - | - |
| `description` | TEXT | YES | - | - |
| `is_active` | BOOLEAN | NO | `TRUE` | - |
| `created_at` | TIMESTAMPTZ | NO | `CURRENT_TIMESTAMP` | - |
| `updated_at` | TIMESTAMPTZ | NO | `CURRENT_TIMESTAMP` | - |

- 主キー: `theme_id`
- 外部キー: `strategy_id` → `strategy`(`strategy_id`)

### `investment_target`

| 列 | 型 | NULL | 既定値 | 列挙値 |
|---|---|---|---|---|
| `target_id` | BIGINT | NO | `AS` | - |
| `target_key` | TEXT | NO | - | - |
| `target_name` | TEXT | NO | - | - |
| `target_type` | TEXT | YES | - | `individual_stock`, `etf`, `mutual_fund`, `reit`, `bond`, `index`, `commodity` |
| `market` | TEXT | YES | - | - |
| `currency` | TEXT | YES | - | - |
| `is_active` | BOOLEAN | NO | `TRUE` | - |
| `created_at` | TIMESTAMPTZ | NO | `CURRENT_TIMESTAMP` | - |
| `updated_at` | TIMESTAMPTZ | NO | `CURRENT_TIMESTAMP` | - |

- 主キー: `target_id`

### `data_source`

| 列 | 型 | NULL | 既定値 | 列挙値 |
|---|---|---|---|---|
| `source_id` | BIGINT | NO | `AS` | - |
| `source_key` | TEXT | NO | - | - |
| `source_name` | TEXT | NO | - | - |
| `base_url` | TEXT | YES | - | - |
| `terms_url` | TEXT | YES | - | - |
| `is_active` | BOOLEAN | NO | `TRUE` | - |
| `created_at` | TIMESTAMPTZ | NO | `CURRENT_TIMESTAMP` | - |
| `updated_at` | TIMESTAMPTZ | NO | `CURRENT_TIMESTAMP` | - |

- 主キー: `source_id`

### `ingestion_run`

| 列 | 型 | NULL | 既定値 | 列挙値 |
|---|---|---|---|---|
| `ingestion_run_id` | BIGINT | NO | `AS` | - |
| `job_type` | TEXT | NO | - | - |
| `git_commit_sha` | TEXT | YES | - | - |
| `source_id` | BIGINT | NO | - | - |
| `status` | TEXT | NO | - | `running`, `succeeded`, `partial`, `failed` |
| `requested_from` | DATE | YES | - | - |
| `requested_to` | DATE | YES | - | - |
| `target_count` | INTEGER | NO | `0` | - |
| `fetched_count` | INTEGER | NO | `0` | - |
| `loaded_count` | INTEGER | NO | `0` | - |
| `skipped_count` | INTEGER | NO | `0` | - |
| `failed_count` | INTEGER | NO | `0` | - |
| `raw_path` | TEXT | YES | - | - |
| `error_message` | TEXT | YES | - | - |
| `started_at` | TIMESTAMPTZ | NO | `CURRENT_TIMESTAMP` | - |
| `finished_at` | TIMESTAMPTZ | YES | - | - |

- 主キー: `ingestion_run_id`
- 外部キー: `source_id` → `data_source`(`source_id`)
- インデックス `idx_ingestion_run_status`: `status`, `started_at`

### `ingestion_error`

| 列 | 型 | NULL | 既定値 | 列挙値 |
|---|---|---|---|---|
| `error_id` | BIGINT | NO | `AS` | - |
| `ingestion_run_id` | BIGINT | NO | - | - |
| `entity_type` | TEXT | YES | - | - |
| `entity_key` | TEXT | YES | - | - |
| `stage` | TEXT | NO | - | - |
| `error_type` | TEXT | YES | - | - |
| `error_message` | TEXT | NO | - | - |
| `retryable` | BOOLEAN | NO | `FALSE` | - |
| `created_at` | TIMESTAMPTZ | NO | `CURRENT_TIMESTAMP` | - |

- 主キー: `error_id`
- 外部キー: `ingestion_run_id` → `ingestion_run`(`ingestion_run_id`)
- インデックス `idx_ingestion_error_run`: `ingestion_run_id`

### `investment_target_identifier`

| 列 | 型 | NULL | 既定値 | 列挙値 |
|---|---|---|---|---|
| `investment_target_identifier_id` | BIGINT | NO | `AS` | - |
| `target_id` | BIGINT | NO | - | - |
| `source_id` | BIGINT | NO | - | - |
| `identifier_type` | TEXT | NO | - | - |
| `identifier` | TEXT | NO | - | - |
| `valid_from` | DATE | NO | `DATE` | - |
| `valid_to` | DATE | YES | - | - |
| `is_primary` | BOOLEAN | NO | `FALSE` | - |
| `created_at` | TIMESTAMPTZ | NO | `CURRENT_TIMESTAMP` | - |
| `updated_at` | TIMESTAMPTZ | NO | `CURRENT_TIMESTAMP` | - |

- 主キー: `investment_target_identifier_id`
- 一意キー: `source_id`, `identifier_type`, `identifier`, `valid_from`
- 外部キー: `target_id` → `investment_target`(`target_id`)
- 外部キー: `source_id` → `data_source`(`source_id`)
- テーブルCHECK: `valid_to IS NULL OR valid_to >= valid_from`
- インデックス `idx_investment_target_identifier_target`: `target_id`
- インデックス `idx_investment_target_identifier_lookup`: `source_id`, `identifier_type`, `identifier`

### `theme_investment_target`

| 列 | 型 | NULL | 既定値 | 列挙値 |
|---|---|---|---|---|
| `theme_id` | BIGINT | NO | - | - |
| `target_id` | BIGINT | NO | - | - |
| `basket_weight` | DOUBLE PRECISION | YES | `1.0` | - |
| `rationale` | TEXT | YES | - | - |
| `is_active` | BOOLEAN | NO | `TRUE` | - |
| `created_at` | TIMESTAMPTZ | NO | `CURRENT_TIMESTAMP` | - |
| `updated_at` | TIMESTAMPTZ | NO | `CURRENT_TIMESTAMP` | - |

- 主キー: `theme_id`, `target_id`
- 外部キー: `theme_id` → `theme`(`theme_id`)
- 外部キー: `target_id` → `investment_target`(`target_id`)

### `market_price_observation`

| 列 | 型 | NULL | 既定値 | 列挙値 |
|---|---|---|---|---|
| `log_id` | BIGINT | NO | `AS` | - |
| `target_id` | BIGINT | NO | - | - |
| `source_id` | BIGINT | NO | - | - |
| `ingestion_run_id` | BIGINT | YES | - | - |
| `obs_date` | DATE | NO | - | - |
| `open_price` | DOUBLE PRECISION | YES | - | - |
| `high_price` | DOUBLE PRECISION | YES | - | - |
| `low_price` | DOUBLE PRECISION | YES | - | - |
| `close_price` | DOUBLE PRECISION | YES | - | - |
| `volume` | DOUBLE PRECISION | YES | - | - |
| `price_basis` | TEXT | NO | `'unknown'` | `adjusted`, `unadjusted`, `unknown` |
| `fetched_at` | TIMESTAMPTZ | NO | `CURRENT_TIMESTAMP` | - |
| `note` | TEXT | YES | - | - |
| `created_at` | TIMESTAMPTZ | NO | `CURRENT_TIMESTAMP` | - |

- 主キー: `log_id`
- 一意キー: `target_id`, `source_id`, `obs_date`
- 外部キー: `target_id` → `investment_target`(`target_id`)
- 外部キー: `source_id` → `data_source`(`source_id`)
- 外部キー: `ingestion_run_id` → `ingestion_run`(`ingestion_run_id`)
- インデックス `idx_market_price_date`: `target_id`, `obs_date`

### `financial_disclosure`

| 列 | 型 | NULL | 既定値 | 列挙値 |
|---|---|---|---|---|
| `disclosure_id` | BIGINT | NO | `AS` | - |
| `target_id` | BIGINT | NO | - | - |
| `source_id` | BIGINT | NO | - | - |
| `disclosure_number` | TEXT | NO | - | - |
| `disclosed_date` | DATE | NO | - | - |
| `disclosed_time` | TIME | YES | - | - |
| `document_type` | TEXT | NO | - | - |
| `fiscal_period_type` | TEXT | YES | - | - |
| `period_start` | DATE | YES | - | - |
| `period_end` | DATE | YES | - | - |
| `fiscal_year_start` | DATE | YES | - | - |
| `fiscal_year_end` | DATE | YES | - | - |
| `accounting_standard` | TEXT | YES | - | - |
| `ingestion_run_id` | BIGINT | YES | - | - |
| `source_record_hash` | TEXT | YES | - | - |
| `fetched_at` | TIMESTAMPTZ | NO | - | - |
| `created_at` | TIMESTAMPTZ | NO | `CURRENT_TIMESTAMP` | - |
| `updated_at` | TIMESTAMPTZ | NO | `CURRENT_TIMESTAMP` | - |

- 主キー: `disclosure_id`
- 一意キー: `source_id`, `disclosure_number`
- 外部キー: `target_id` → `investment_target`(`target_id`)
- 外部キー: `source_id` → `data_source`(`source_id`)
- 外部キー: `ingestion_run_id` → `ingestion_run`(`ingestion_run_id`)
- テーブルCHECK: `period_end IS NULL OR period_start IS NULL OR period_end >= period_start`
- テーブルCHECK: `fiscal_year_end IS NULL OR fiscal_year_start IS NULL OR fiscal_year_end >= fiscal_year_start`
- インデックス `idx_financial_disclosure_target_date`: `target_id`, `disclosed_date`
- インデックス `idx_financial_disclosure_period`: `target_id`, `fiscal_year_end`, `fiscal_period_type`

### `financial_summary`

| 列 | 型 | NULL | 既定値 | 列挙値 |
|---|---|---|---|---|
| `disclosure_id` | BIGINT | NO | - | - |
| `reporting_scope` | TEXT | NO | - | `consolidated`, `non_consolidated` |
| `revenue` | BIGINT | YES | - | - |
| `operating_income` | BIGINT | YES | - | - |
| `ordinary_income` | BIGINT | YES | - | - |
| `net_income` | BIGINT | YES | - | - |
| `eps` | DOUBLE PRECISION | YES | - | - |
| `total_assets` | BIGINT | YES | - | - |
| `equity` | BIGINT | YES | - | - |
| `bps` | DOUBLE PRECISION | YES | - | - |
| `operating_cash_flow` | BIGINT | YES | - | - |
| `investing_cash_flow` | BIGINT | YES | - | - |
| `financing_cash_flow` | BIGINT | YES | - | - |
| `cash_equivalents` | BIGINT | YES | - | - |
| `forecast_revenue` | BIGINT | YES | - | - |
| `forecast_operating_income` | BIGINT | YES | - | - |
| `forecast_ordinary_income` | BIGINT | YES | - | - |
| `forecast_net_income` | BIGINT | YES | - | - |
| `forecast_eps` | DOUBLE PRECISION | YES | - | - |
| `next_forecast_revenue` | BIGINT | YES | - | - |
| `next_forecast_operating_income` | BIGINT | YES | - | - |
| `next_forecast_ordinary_income` | BIGINT | YES | - | - |
| `next_forecast_net_income` | BIGINT | YES | - | - |
| `next_forecast_eps` | DOUBLE PRECISION | YES | - | - |
| `annual_dividend_per_share` | DOUBLE PRECISION | YES | - | - |
| `forecast_annual_dividend_per_share` | DOUBLE PRECISION | YES | - | - |
| `shares_outstanding` | BIGINT | YES | - | - |
| `treasury_shares` | BIGINT | YES | - | - |
| `average_shares` | BIGINT | YES | - | - |
| `created_at` | TIMESTAMPTZ | NO | `CURRENT_TIMESTAMP` | - |
| `updated_at` | TIMESTAMPTZ | NO | `CURRENT_TIMESTAMP` | - |

- 主キー: `disclosure_id`
- 外部キー: `disclosure_id` → `financial_disclosure`(`disclosure_id`)（ON DELETE CASCADE）
