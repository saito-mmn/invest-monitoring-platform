-- ============================================
-- マスターテーブル
-- ============================================

CREATE TABLE IF NOT EXISTS strategy (
    strategy_id   INTEGER PRIMARY KEY AUTOINCREMENT,
    strategy_key  TEXT    NOT NULL UNIQUE,
    strategy_name TEXT    NOT NULL,
    description   TEXT,
    is_active     INTEGER NOT NULL DEFAULT 1,
    created_at    TEXT    NOT NULL DEFAULT (datetime('now')),
    updated_at    TEXT    NOT NULL DEFAULT (datetime('now'))
);

INSERT OR IGNORE INTO strategy (strategy_key, strategy_name, description)
VALUES
    ('core', 'Core', '中核となる長期保有戦略'),
    ('satellite', 'Satellite', '成長機会を取り込む補完戦略'),
    ('alternatives', 'Alternatives', '伝統資産以外の分散戦略');

CREATE TABLE IF NOT EXISTS theme (
    theme_id      INTEGER PRIMARY KEY AUTOINCREMENT,
    theme_key     TEXT    NOT NULL UNIQUE,
    theme_name    TEXT    NOT NULL,
    strategy_id   INTEGER NOT NULL,
    description   TEXT,
    is_active     INTEGER NOT NULL DEFAULT 1,
    created_at    TEXT    NOT NULL DEFAULT (datetime('now')),
    updated_at    TEXT    NOT NULL DEFAULT (datetime('now')),
    FOREIGN KEY (strategy_id) REFERENCES strategy(strategy_id)
);

CREATE TABLE IF NOT EXISTS investment_target (
    target_id    INTEGER PRIMARY KEY AUTOINCREMENT,
    target_key   TEXT    NOT NULL UNIQUE,  -- ticker+market (例: '^VIX', '466A.T')
    target_name  TEXT    NOT NULL,
    target_type  TEXT    CHECK(target_type IN (
        'individual_stock','etf','mutual_fund','reit','bond','index','commodity'
    )),
    market      TEXT,
    currency    TEXT,
    is_active   INTEGER NOT NULL DEFAULT 1,
    created_at  TEXT    NOT NULL DEFAULT (datetime('now')),
    updated_at  TEXT    NOT NULL DEFAULT (datetime('now'))
);

-- ============================================
-- データ取得・外部識別子
-- ============================================

CREATE TABLE IF NOT EXISTS data_source (
    source_id    INTEGER PRIMARY KEY AUTOINCREMENT,
    source_key   TEXT    NOT NULL UNIQUE,
    source_name  TEXT    NOT NULL,
    base_url     TEXT,
    terms_url    TEXT,
    is_active    INTEGER NOT NULL DEFAULT 1,
    created_at   TEXT    NOT NULL DEFAULT (datetime('now')),
    updated_at   TEXT    NOT NULL DEFAULT (datetime('now'))
);

CREATE TABLE IF NOT EXISTS ingestion_run (
    ingestion_run_id INTEGER PRIMARY KEY AUTOINCREMENT,
    job_type         TEXT    NOT NULL,
    git_commit_sha   TEXT,
    source_id        INTEGER NOT NULL,
    status           TEXT    NOT NULL
                     CHECK(status IN ('running','succeeded','partial','failed')),
    requested_from   TEXT,
    requested_to     TEXT,
    target_count     INTEGER NOT NULL DEFAULT 0 CHECK(target_count >= 0),
    fetched_count    INTEGER NOT NULL DEFAULT 0 CHECK(fetched_count >= 0),
    loaded_count     INTEGER NOT NULL DEFAULT 0 CHECK(loaded_count >= 0),
    skipped_count    INTEGER NOT NULL DEFAULT 0 CHECK(skipped_count >= 0),
    failed_count     INTEGER NOT NULL DEFAULT 0 CHECK(failed_count >= 0),
    raw_path         TEXT,
    error_message    TEXT,
    started_at       TEXT    NOT NULL DEFAULT (datetime('now')),
    finished_at      TEXT,
    FOREIGN KEY (source_id) REFERENCES data_source(source_id)
);

CREATE TABLE IF NOT EXISTS ingestion_error (
    error_id          INTEGER PRIMARY KEY AUTOINCREMENT,
    ingestion_run_id  INTEGER NOT NULL,
    entity_type       TEXT,
    entity_key        TEXT,
    stage             TEXT    NOT NULL,
    error_type        TEXT,
    error_message     TEXT    NOT NULL,
    retryable         INTEGER NOT NULL DEFAULT 0 CHECK(retryable IN (0, 1)),
    created_at        TEXT    NOT NULL DEFAULT (datetime('now')),
    FOREIGN KEY (ingestion_run_id) REFERENCES ingestion_run(ingestion_run_id)
);

CREATE TABLE IF NOT EXISTS investment_target_identifier (
    investment_target_identifier_id INTEGER PRIMARY KEY AUTOINCREMENT,
    target_id            INTEGER NOT NULL,
    source_id           INTEGER NOT NULL,
    identifier_type     TEXT    NOT NULL,
    identifier          TEXT    NOT NULL,
    valid_from          TEXT    NOT NULL DEFAULT '0001-01-01',
    valid_to            TEXT,
    is_primary          INTEGER NOT NULL DEFAULT 0 CHECK(is_primary IN (0, 1)),
    created_at          TEXT    NOT NULL DEFAULT (datetime('now')),
    updated_at          TEXT    NOT NULL DEFAULT (datetime('now')),
    UNIQUE(source_id, identifier_type, identifier, valid_from),
    FOREIGN KEY (target_id) REFERENCES investment_target(target_id),
    FOREIGN KEY (source_id) REFERENCES data_source(source_id),
    CHECK(valid_to IS NULL OR valid_from IS NULL OR valid_to >= valid_from)
);

-- ============================================
-- 判定設定・中間テーブル
-- ============================================

CREATE TABLE IF NOT EXISTS theme_investment_target (
    theme_id       INTEGER NOT NULL,
    target_id       INTEGER NOT NULL,
    basket_weight  REAL    DEFAULT 1.0,
    rationale      TEXT,
    is_active      INTEGER NOT NULL DEFAULT 1,
    created_at     TEXT    NOT NULL DEFAULT (datetime('now')),
    updated_at     TEXT    NOT NULL DEFAULT (datetime('now')),
    PRIMARY KEY (theme_id, target_id),
    FOREIGN KEY (theme_id) REFERENCES theme(theme_id),
    FOREIGN KEY (target_id) REFERENCES investment_target(target_id)
);

-- ============================================
-- ログテーブル（時系列データ）
-- ============================================

CREATE TABLE IF NOT EXISTS market_price_observation (
    log_id      INTEGER PRIMARY KEY AUTOINCREMENT,
    target_id    INTEGER NOT NULL,
    source_id   INTEGER NOT NULL,
    ingestion_run_id INTEGER,
    obs_date    TEXT    NOT NULL,
    open_price  REAL,
    high_price  REAL,
    low_price   REAL,
    close_price REAL,
    volume      REAL,
    price_basis TEXT    NOT NULL DEFAULT 'unknown'
                        CHECK(price_basis IN ('adjusted','unadjusted','unknown')),
    fetched_at  TEXT    NOT NULL DEFAULT (datetime('now')),
    note        TEXT,
    created_at  TEXT    NOT NULL DEFAULT (datetime('now')),
    UNIQUE(target_id, source_id, obs_date),
    FOREIGN KEY (target_id) REFERENCES investment_target(target_id),
    FOREIGN KEY (source_id) REFERENCES data_source(source_id),
    FOREIGN KEY (ingestion_run_id) REFERENCES ingestion_run(ingestion_run_id)
);

-- ============================================
-- 財務サマリー（J-Quants /fins/summary）
-- ============================================

-- 1回の開示を1レコードとして保持する。
-- 同じ決算期の訂正開示も disclosure_number が異なる限り別履歴となる。
CREATE TABLE IF NOT EXISTS financial_disclosure (
    disclosure_id       INTEGER PRIMARY KEY AUTOINCREMENT,
    target_id            INTEGER NOT NULL,
    source_id           INTEGER NOT NULL,
    disclosure_number   TEXT    NOT NULL,
    disclosed_date      TEXT    NOT NULL,
    disclosed_time      TEXT,
    document_type       TEXT    NOT NULL,
    fiscal_period_type  TEXT,
    period_start        TEXT,
    period_end          TEXT,
    fiscal_year_start   TEXT,
    fiscal_year_end     TEXT,
    accounting_standard TEXT,
    ingestion_run_id    INTEGER,
    source_record_hash  TEXT,
    fetched_at          TEXT    NOT NULL,
    created_at          TEXT    NOT NULL DEFAULT (datetime('now')),
    updated_at          TEXT    NOT NULL DEFAULT (datetime('now')),
    UNIQUE(source_id, disclosure_number),
    FOREIGN KEY (target_id) REFERENCES investment_target(target_id),
    FOREIGN KEY (source_id) REFERENCES data_source(source_id),
    FOREIGN KEY (ingestion_run_id) REFERENCES ingestion_run(ingestion_run_id),
    CHECK(period_end IS NULL OR period_start IS NULL OR period_end >= period_start),
    CHECK(fiscal_year_end IS NULL OR fiscal_year_start IS NULL OR fiscal_year_end >= fiscal_year_start)
);

-- APIの全フィールドではなく、Phase 1で使う標準化項目のみ保持する。
-- 金額・株式数は INTEGER、EPS/BPS/一株配当は REAL、欠損は NULL とする。
CREATE TABLE IF NOT EXISTS financial_summary (
    disclosure_id            INTEGER PRIMARY KEY,
    reporting_scope          TEXT NOT NULL
                             CHECK(reporting_scope IN ('consolidated','non_consolidated')),
    revenue                  INTEGER,
    operating_income         INTEGER,
    ordinary_income          INTEGER,
    net_income               INTEGER,
    eps                      REAL,
    total_assets             INTEGER,
    equity                   INTEGER,
    bps                      REAL,
    operating_cash_flow      INTEGER,
    investing_cash_flow      INTEGER,
    financing_cash_flow      INTEGER,
    cash_equivalents         INTEGER,
    forecast_revenue         INTEGER,
    forecast_operating_income INTEGER,
    forecast_ordinary_income INTEGER,
    forecast_net_income      INTEGER,
    forecast_eps             REAL,
    next_forecast_revenue    INTEGER,
    next_forecast_operating_income INTEGER,
    next_forecast_ordinary_income INTEGER,
    next_forecast_net_income INTEGER,
    next_forecast_eps        REAL,
    annual_dividend_per_share REAL,
    forecast_annual_dividend_per_share REAL,
    shares_outstanding       INTEGER,
    treasury_shares          INTEGER,
    average_shares           INTEGER,
    created_at               TEXT NOT NULL DEFAULT (datetime('now')),
    updated_at               TEXT NOT NULL DEFAULT (datetime('now')),
    FOREIGN KEY (disclosure_id) REFERENCES financial_disclosure(disclosure_id) ON DELETE CASCADE
);

-- ============================================
-- インデックス
-- ============================================

CREATE INDEX IF NOT EXISTS idx_market_price_date ON market_price_observation(target_id, obs_date);
CREATE INDEX IF NOT EXISTS idx_investment_target_identifier_target ON investment_target_identifier(target_id);
CREATE INDEX IF NOT EXISTS idx_investment_target_identifier_lookup ON investment_target_identifier(source_id, identifier_type, identifier);
CREATE INDEX IF NOT EXISTS idx_ingestion_run_status ON ingestion_run(status, started_at);
CREATE INDEX IF NOT EXISTS idx_ingestion_error_run ON ingestion_error(ingestion_run_id);
CREATE INDEX IF NOT EXISTS idx_financial_disclosure_target_date ON financial_disclosure(target_id, disclosed_date);
CREATE INDEX IF NOT EXISTS idx_financial_disclosure_period ON financial_disclosure(target_id, fiscal_year_end, fiscal_period_type);
