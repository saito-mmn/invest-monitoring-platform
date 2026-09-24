"""財務開示APIの検証。"""

import pytest

from app.etl.loaders import ensure_data_source, upsert_financial_disclosures
from app.etl.normalizers import normalize_jquants_financial

QUARTER_ROW = {
    "Code": "86970", "DiscNo": "q3", "DiscDate": "2026-01-29", "DiscTime": "15:00:00",
    "DocType": "3QFinancialStatements_Consolidated_IFRS", "CurPerType": "3Q",
    "Sales": "139626000000", "EPS": "53.33",
    # 四半期短信は今期予想を持つ
    "FSales": "176000000000", "FEPS": "63.09", "FDivAnn": "50.0",
}
FY_ROW = {
    "Code": "86970", "DiscNo": "fy", "DiscDate": "2026-04-28", "DiscTime": "15:00:00",
    "DocType": "FYFinancialStatements_Consolidated_IFRS", "CurPerType": "FY",
    "Sales": "198735000000", "EPS": "76.81", "DivAnn": "61.0",
    # FY短信は今期予想を持たず、翌期予想を持つ
    "NxFSales": "205000000000", "NxFEPS": "75.39",
}


@pytest.fixture
def target_with_financials(db, client):
    """開示2件（四半期・FY）を登録した銘柄を用意する。"""
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
    records = [normalize_jquants_financial(row) for row in (QUARTER_ROW, FY_ROW)]
    upsert_financial_disclosures(db, source_id, records)
    db.commit()
    return target_id


def test_disclosures_are_returned_newest_first(client, target_with_financials):
    """開示履歴は新しい順に返る。"""
    response = client.get(f"/api/investment-targets/{target_with_financials}/financial-disclosures")

    assert response.status_code == 200
    body = response.json()
    assert [d["disclosed_date"] for d in body] == ["2026-04-28", "2026-01-29"]
    assert body[0]["accounting_standard"] == "IFRS"
    assert body[0]["revenue"] == 198735000000


def test_latest_assembles_forecasts_from_different_disclosures(client, target_with_financials):
    """最新の開示が今期予想を持たない場合、前の開示から補って返す。"""
    response = client.get(
        f"/api/investment-targets/{target_with_financials}/financial-summary/latest"
    )

    assert response.status_code == 200
    body = response.json()
    # 実績は最新のFY開示
    assert body["latest_disclosure"]["disclosed_date"] == "2026-04-28"
    assert body["latest_disclosure"]["forecast_revenue"] is None
    # 今期予想はFY開示に無いため、四半期開示から取る
    assert body["current_forecast"]["disclosed_date"] == "2026-01-29"
    assert body["current_forecast"]["forecast_revenue"] == 176000000000
    # 翌期予想はFY開示から取る
    assert body["next_forecast"]["disclosed_date"] == "2026-04-28"
    assert body["next_forecast"]["next_forecast_revenue"] == 205000000000


def test_latest_returns_null_forecasts_when_company_does_not_disclose(client, db):
    """業績予想を開示しない企業では、予想が null で返る。"""
    source_id = ensure_data_source(db, "jquants", "J-Quants")
    target_id = db.execute(
        "INSERT INTO investment_target (target_key, target_name, target_type) "
        "VALUES ('9984.T', 'SBG', 'individual_stock')"
    ).lastrowid
    db.execute(
        "INSERT INTO investment_target_identifier "
        "(target_id, source_id, identifier_type, identifier, is_primary) "
        "VALUES (?, ?, 'jpx_code', '99840', TRUE)",
        (target_id, source_id),
    )
    no_forecast = {k: v for k, v in FY_ROW.items() if not k.startswith(("F", "NxF"))}
    upsert_financial_disclosures(
        db, source_id, [normalize_jquants_financial({**no_forecast, "Code": "99840"})]
    )
    db.commit()

    body = client.get(f"/api/investment-targets/{target_id}/financial-summary/latest").json()

    assert body["latest_disclosure"]["revenue"] == 198735000000
    assert body["current_forecast"] is None
    assert body["next_forecast"] is None
    assert body["dividend_forecast"] is None


def test_unknown_target_returns_404(client):
    assert client.get("/api/investment-targets/9999/financial-disclosures").status_code == 404
    assert client.get("/api/investment-targets/9999/financial-summary/latest").status_code == 404


def test_target_without_disclosures_returns_404_for_latest(client, db):
    """開示がまだ無い銘柄は404を返す。"""
    target_id = db.execute(
        "INSERT INTO investment_target (target_key, target_name, target_type) "
        "VALUES ('408A.T', 'ETF', 'etf')"
    ).lastrowid
    db.commit()

    assert client.get(f"/api/investment-targets/{target_id}/financial-summary/latest").status_code == 404
    assert client.get(f"/api/investment-targets/{target_id}/financial-disclosures").json() == []


def test_dividend_forecast_is_separate_from_earnings_forecast(client, db):
    """業績予想を出さず配当予想だけ出す企業を、正しく区別して返す。"""
    source_id = ensure_data_source(db, "jquants", "J-Quants")
    target_id = db.execute(
        "INSERT INTO investment_target (target_key, target_name, target_type) "
        "VALUES ('9984.T', 'SBG', 'individual_stock')"
    ).lastrowid
    db.execute(
        "INSERT INTO investment_target_identifier "
        "(target_id, source_id, identifier_type, identifier, is_primary) "
        "VALUES (?, ?, 'jpx_code', '99840', TRUE)",
        (target_id, source_id),
    )
    dividend_only = {
        "Code": "99840", "DiscNo": "q1", "DiscDate": "2025-08-07", "DiscTime": "15:00:00",
        "DocType": "1QFinancialStatements_Consolidated_IFRS", "CurPerType": "1Q",
        "Sales": "1000", "FDivAnn": "44.0",
    }
    upsert_financial_disclosures(db, source_id, [normalize_jquants_financial(dividend_only)])
    db.commit()

    body = client.get(f"/api/investment-targets/{target_id}/financial-summary/latest").json()

    assert body["current_forecast"] is None
    assert body["dividend_forecast"]["forecast_annual_dividend_per_share"] == 44.0


# 配当修正だけの開示。実績も業績予想も持たない。
DIVIDEND_REVISION_ROW = {
    "Code": "86970", "DiscNo": "divrev", "DiscDate": "2026-06-10", "DiscTime": "15:00:00",
    "DocType": "DivForecastRevision", "CurPerType": "FY",
    "FDivAnn": "65.0",
}


def test_latest_actual_skips_disclosures_without_actuals(client, db, target_with_financials):
    """実績を持たない開示が最新でも、実績は直近の決算開示から返す。

    配当修正や業績予想の修正は実績値を含まない。最新の開示をそのまま実績として扱うと、
    画面の実績欄が空になる。
    """
    source_id = db.execute(
        "SELECT source_id FROM data_source WHERE source_key = 'jquants'"
    ).fetchone()[0]
    upsert_financial_disclosures(
        db, source_id, [normalize_jquants_financial(DIVIDEND_REVISION_ROW)]
    )
    db.commit()

    body = client.get(
        f"/api/investment-targets/{target_with_financials}/financial-summary/latest"
    ).json()

    # 最新の開示は配当修正だが、実績はFY短信から取る
    assert body["latest_disclosure"]["disclosure_number"] == "divrev"
    assert body["latest_disclosure"]["revenue"] is None
    assert body["latest_actual"]["disclosure_number"] == "fy"
    assert body["latest_actual"]["revenue"] == 198735000000


def test_latest_actual_is_null_when_no_disclosure_has_actuals(client, db):
    """実績を含む開示が1件も無ければ `latest_actual` は null になる。"""
    source_id = ensure_data_source(db, "jquants", "J-Quants")
    target_id = db.execute(
        "INSERT INTO investment_target (target_key, target_name, target_type) "
        "VALUES ('9999.T', '予想のみ', 'individual_stock')"
    ).lastrowid
    db.execute(
        "INSERT INTO investment_target_identifier "
        "(target_id, source_id, identifier_type, identifier, is_primary) "
        "VALUES (?, ?, 'jpx_code', '99990', TRUE)",
        (target_id, source_id),
    )
    upsert_financial_disclosures(
        db, source_id,
        [normalize_jquants_financial({**DIVIDEND_REVISION_ROW, "Code": "99990"})],
    )
    db.commit()

    body = client.get(f"/api/investment-targets/{target_id}/financial-summary/latest").json()

    assert body["latest_actual"] is None
    assert body["dividend_forecast"]["forecast_annual_dividend_per_share"] == 65.0


def test_forecast_history_includes_revisions_and_excludes_actual_only(client, db, target_with_financials):
    """予想を含む開示だけを新しい順に返す。

    予想は決算短信だけでなく業績予想の修正でも更新されるため、実績の有無ではなく
    予想の有無で抽出する。
    """
    source_id = db.execute(
        "SELECT source_id FROM data_source WHERE source_key = 'jquants'"
    ).fetchone()[0]
    # 業績予想の修正（実績を持たない）
    revision = {
        "Code": "86970", "DiscNo": "rev", "DiscDate": "2026-02-10", "DiscTime": "15:00:00",
        "DocType": "EarnForecastRevision", "CurPerType": "FY",
        "FSales": "180000000000", "FEPS": "65.00",
    }
    # 実績だけで予想を持たない開示
    actual_only = {
        "Code": "86970", "DiscNo": "actual-only", "DiscDate": "2026-02-20",
        "DiscTime": "15:00:00", "DocType": "FYFinancialStatements_Consolidated_IFRS",
        "CurPerType": "FY", "Sales": "1", "EPS": "0.1",
    }
    upsert_financial_disclosures(
        db, source_id, [normalize_jquants_financial(r) for r in (revision, actual_only)]
    )
    db.commit()

    body = client.get(
        f"/api/investment-targets/{target_with_financials}/forecast-history"
    ).json()

    numbers = [row["disclosure_number"] for row in body]
    assert "rev" in numbers          # 予想の修正は含む
    assert "q3" in numbers           # 予想を持つ四半期短信も含む
    assert "actual-only" not in numbers  # 予想の無い開示は除く
    # 新しい順
    assert numbers == sorted(
        numbers, key=lambda n: [row["disclosed_date"] for row in body][numbers.index(n)], reverse=True
    )


def test_forecast_history_for_unknown_target_returns_404(client):
    assert client.get("/api/investment-targets/9999/forecast-history").status_code == 404
