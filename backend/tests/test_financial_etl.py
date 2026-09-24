"""財務Observed基盤（J-Quants /fins/summary）のETLを検証する。"""

import sqlite3

import pytest

from app.etl.loaders import ensure_data_source, upsert_financial_disclosures
from app.etl.normalizers import normalize_jquants_financial, parse_document_type

BASE_ROW = {
    "Code": "86970",
    "DiscNo": "20260510001",
    "DiscDate": "2026-05-10",
    "DiscTime": "15:00:00",
    "DocType": "FYFinancialStatements_Consolidated_IFRS",
    "CurPerType": "FY",
    "CurPerSt": "2025-04-01",
    "CurPerEn": "2026-03-31",
    "CurFYSt": "2025-04-01",
    "CurFYEn": "2026-03-31",
    "Sales": "142000000000",
    "OP": "78000000000",
    "OdP": "79000000000",
    "NP": "52000000000",
    "EPS": "98.45",
    "TA": "1200000000000",
    "Eq": "300000000000",
    "BPS": "560.25",
    "CFO": "60000000000",
    "CFI": "-20000000000",
    "CFF": "-15000000000",
    "CashEq": "180000000000",
    "FSales": "150000000000",
    "FOP": "80000000000",
    "FNP": "55000000000",
    "ShOutFY": "540000000",
    "TrShFY": "12000000",
    "AvgSh": "528000000",
}


@pytest.fixture
def jquants_db(db: sqlite3.Connection) -> sqlite3.Connection:
    """J-Quants取得元と、jpx_code対応済みの銘柄を用意する。"""
    source_id = ensure_data_source(db, "jquants", "J-Quants")
    target_id = db.execute(
        "INSERT INTO investment_target (target_key, target_name, target_type) "
        "VALUES ('8697.T', 'JPX', 'individual_stock')"
    ).lastrowid
    db.execute(
        "INSERT INTO investment_target_identifier "
        "(target_id, source_id, identifier_type, identifier, is_primary) "
        "VALUES (?, ?, 'jpx_code', '86970', TRUE)",
        (target_id, source_id),
    )
    db.commit()
    return db


def _load(db, *rows):
    """正規化して保存する。取得元はDBから引く。"""
    source_id = db.execute(
        "SELECT source_id FROM data_source WHERE source_key = 'jquants'"
    ).fetchone()[0]
    records = [normalize_jquants_financial(row) for row in rows]
    return upsert_financial_disclosures(db, source_id, records, ingestion_run_id=None)


def test_summary_values_are_typed_and_linked_to_the_disclosure(jquants_db):
    """金額はINTEGER、EPS・BPSはREALとして開示に紐づけて保存する。"""
    loaded, issues = _load(jquants_db, BASE_ROW)

    row = jquants_db.execute(
        "SELECT d.disclosure_number, d.disclosed_date, s.revenue, s.eps, s.bps, s.reporting_scope "
        "FROM financial_disclosure d JOIN financial_summary s USING (disclosure_id)"
    ).fetchone()
    assert (loaded, issues) == (1, [])
    assert row["disclosure_number"] == "20260510001"
    assert row["revenue"] == 142000000000
    assert isinstance(row["revenue"], int)
    assert row["eps"] == pytest.approx(98.45)
    assert row["reporting_scope"] == "consolidated"


def test_missing_values_become_null_without_zero_filling(jquants_db):
    """空文字・欠損はNULLとして保存し、ゼロで補completeしない。"""
    row = {**BASE_ROW, "CFO": "", "CashEq": None}
    del row["TrShFY"]

    _load(jquants_db, row)

    stored = jquants_db.execute(
        "SELECT operating_cash_flow, cash_equivalents, treasury_shares FROM financial_summary"
    ).fetchone()
    assert (
        stored["operating_cash_flow"],
        stored["cash_equivalents"],
        stored["treasury_shares"],
    ) == (None, None, None)


def test_ifrs_disclosure_without_ordinary_income_is_accepted(jquants_db):
    """IFRS等で経常利益が無い開示も、他の項目を保存して受け入れる。"""
    _load(jquants_db, {**BASE_ROW, "OdP": ""})

    stored = jquants_db.execute(
        "SELECT ordinary_income, operating_income FROM financial_summary"
    ).fetchone()
    assert stored["ordinary_income"] is None
    assert stored["operating_income"] == 78000000000


def test_correction_disclosure_is_kept_as_a_separate_record(jquants_db):
    """訂正開示は開示番号が異なるため、元の開示を上書きせず別レコードとして残る。"""
    correction = {**BASE_ROW, "DiscNo": "20260612001", "Sales": "141000000000"}

    _load(jquants_db, BASE_ROW, correction)

    rows = jquants_db.execute(
        "SELECT d.disclosure_number, s.revenue FROM financial_disclosure d "
        "JOIN financial_summary s USING (disclosure_id) ORDER BY d.disclosure_number"
    ).fetchall()
    assert [(r["disclosure_number"], r["revenue"]) for r in rows] == [
        ("20260510001", 142000000000),
        ("20260612001", 141000000000),
    ]


def test_rerunning_the_same_disclosure_is_idempotent(jquants_db):
    """同じ開示番号を取り直しても行は増えず、値が更新される。"""
    _load(jquants_db, BASE_ROW)
    _load(jquants_db, {**BASE_ROW, "Sales": "143000000000"})

    count = jquants_db.execute("SELECT count(*) FROM financial_disclosure").fetchone()[0]
    revenue = jquants_db.execute("SELECT revenue FROM financial_summary").fetchone()[0]
    assert count == 1
    assert revenue == 143000000000


def test_source_record_hash_detects_content_change(jquants_db):
    """原レコードが変われば source_record_hash も変わる。"""
    first = normalize_jquants_financial(BASE_ROW).source_record_hash
    same = normalize_jquants_financial(dict(reversed(list(BASE_ROW.items())))).source_record_hash
    changed = normalize_jquants_financial({**BASE_ROW, "Sales": "1"}).source_record_hash

    assert first == same  # キー順には依存しない
    assert first != changed


def test_unknown_jpx_code_is_reported_without_stopping(jquants_db):
    """対応の無い銘柄はエラーとして記録し、他の開示の保存は続ける。"""
    unknown = {**BASE_ROW, "Code": "99999", "DiscNo": "x"}

    loaded, issues = _load(jquants_db, unknown, BASE_ROW)

    assert loaded == 1
    assert [i.error_type for i in issues] == ["unknown_investment_target"]


@pytest.mark.parametrize(
    "document_type, expected",
    [
        ("1QFinancialStatements_Consolidated_IFRS", ("IFRS", "consolidated")),
        ("FYFinancialStatements_Consolidated_JP", ("JP", "consolidated")),
        ("FYFinancialStatements_NonConsolidated_JP", ("JP", "non_consolidated")),
        # 業績予想の修正には会計基準も連結範囲も含まれない
        ("EarnForecastRevision", (None, None)),
    ],
)
def test_document_type_carries_standard_and_scope(document_type, expected):
    """会計基準と連結範囲は専用項目ではなく DocType から判定する。"""
    assert parse_document_type(document_type) == expected


def test_non_consolidated_disclosure_uses_nc_fields(jquants_db):
    """非連結の開示では NC 系の項目を採用する。"""
    row = {
        **BASE_ROW,
        "DocType": "FYFinancialStatements_NonConsolidated_JP",
        "NCSales": "62933000000",
        "NCEPS": "53.01",
    }

    _load(jquants_db, row)

    stored = jquants_db.execute(
        "SELECT d.accounting_standard, s.reporting_scope, s.revenue, s.eps "
        "FROM financial_disclosure d JOIN financial_summary s USING (disclosure_id)"
    ).fetchone()
    assert stored["accounting_standard"] == "JP"
    assert stored["reporting_scope"] == "non_consolidated"
    # 連結の Sales / EPS ではなく NC 側が入る
    assert stored["revenue"] == 62933000000
    assert stored["eps"] == pytest.approx(53.01)


def test_annual_dividend_uses_per_share_not_total(jquants_db):
    """配当は1株当たりの `DivAnn` を採用し、総額の `DivTotalAnn` は使わない。"""
    _load(jquants_db, {**BASE_ROW, "DivAnn": "61.0", "DivTotalAnn": "62938000000"})

    stored = jquants_db.execute(
        "SELECT annual_dividend_per_share FROM financial_summary"
    ).fetchone()
    assert stored["annual_dividend_per_share"] == pytest.approx(61.0)


def test_next_period_forecast_field_names(jquants_db):
    """翌期予想の純利益だけ項目名の末尾が小文字（`NxFNp`）である。"""
    _load(jquants_db, {**BASE_ROW, "NxFSales": "205000000000", "NxFNp": "77500000000"})

    stored = jquants_db.execute(
        "SELECT next_forecast_revenue, next_forecast_net_income FROM financial_summary"
    ).fetchone()
    assert stored["next_forecast_revenue"] == 205000000000
    assert stored["next_forecast_net_income"] == 77500000000


class _FakeClient:
    """`financial_summaries` の呼び出し引数を記録する代役。"""

    def __init__(self, rows):
        self.rows = rows
        self.calls = []

    def financial_summaries(self, *, code=None, date=None):
        self.calls.append({"code": code, "date": date})
        return self.rows

    base_url = "https://example.test"


def _pipeline(db, client, tmp_path):
    from app.etl.pipeline import JQuantsMarketPipeline

    return JQuantsMarketPipeline(db, client, tmp_path / "raw", tmp_path)


def test_date_mode_fetches_once_for_all_companies(jquants_db, tmp_path):
    """開示日指定では銘柄ごとにループせず、1リクエストで取得する。"""
    client = _FakeClient([BASE_ROW])
    result = _pipeline(jquants_db, client, tmp_path).sync_financials(date="2026-05-10")

    assert client.calls == [{"code": None, "date": "2026-05-10"}]
    assert result["loaded"] == 1


def test_date_mode_skips_untracked_companies_without_errors(jquants_db, tmp_path):
    """追跡していない銘柄の開示は、エラーではなく対象外として数える。"""
    untracked = {**BASE_ROW, "Code": "99999", "DiscNo": "other"}
    client = _FakeClient([BASE_ROW, untracked])

    result = _pipeline(jquants_db, client, tmp_path).sync_financials(date="2026-05-10")

    assert result["loaded"] == 1
    assert result["untracked"] == 1
    assert result["failed"] == 0
    errors = jquants_db.execute("SELECT count(*) FROM ingestion_error").fetchone()[0]
    assert errors == 0


def test_code_mode_fetches_each_code(jquants_db, tmp_path):
    """銘柄指定では指定した数だけリクエストする。"""
    client = _FakeClient([BASE_ROW])
    _pipeline(jquants_db, client, tmp_path).sync_financials(codes=["86970", "72030"])

    assert [c["code"] for c in client.calls] == ["86970", "72030"]
    assert all(c["date"] is None for c in client.calls)


def test_codes_and_date_are_mutually_exclusive(jquants_db, tmp_path):
    """codes と date の同時指定・同時省略は受け付けない。"""
    pipeline = _pipeline(jquants_db, _FakeClient([]), tmp_path)

    with pytest.raises(ValueError, match="どちらか一方"):
        pipeline.sync_financials(codes=["86970"], date="2026-05-10")
    with pytest.raises(ValueError, match="どちらか一方"):
        pipeline.sync_financials()


def test_fetcher_requires_code_or_date():
    """クライアントは code も date も無い呼び出しを拒否する。"""
    from app.etl.fetchers.jquants import JQuantsClient, JQuantsError

    client = JQuantsClient("secret", opener=lambda *_a, **_k: None)
    with pytest.raises(JQuantsError, match="requires code or date"):
        client.financial_summaries()
