"""デモデータ生成が、実データと同じ開示の規則を再現し、実データを壊さないことを確認する。

デモDBは公開されるため、生成規則が崩れると画面の説明と食い違う。また、この投入は
TRUNCATEを伴うので、実データの入ったDBへ向いたときに止まることが最も重要な性質である。
"""

import pytest

from scripts import seed_demo


def _company(key: str) -> seed_demo.Company:
    return next(c for c in seed_demo.COMPANIES if c.key == key)


@pytest.fixture
def demo_db(db, monkeypatch):
    """テスト用DBを、この検査に限りデモ用DBとして扱う。

    本番を守っているのはDB名の一致そのものなので、名前を偽装するのはテスト内だけに閉じる。
    """
    name = db.execute("SELECT current_database() AS name").fetchone()["name"]
    monkeypatch.setattr(
        seed_demo, "DEMO_DATABASE_NAMES", frozenset({*seed_demo.DEMO_DATABASE_NAMES, name})
    )
    return db


def test_seed_refuses_database_that_is_not_the_demo_one(db):
    """デモ用DB以外は対象にしない。本番DBへ到達させないための一次防御。"""
    with pytest.raises(SystemExit) as excinfo:
        seed_demo.seed(db, replace=True)

    assert "デモ用DB" in str(excinfo.value)


def test_force_cannot_override_the_database_name_check(db):
    """--force でもDB名の条件は越えられない。突破口を1つも残さない。"""
    with pytest.raises(SystemExit):
        seed_demo.seed(db, replace=True, force=True)


def test_seed_aborts_when_real_sources_exist(demo_db):
    """デモ用DBでも、実データ由来の取得元が混ざっていれば中断する。"""
    demo_db.execute(
        "INSERT INTO data_source (source_key, source_name) VALUES (?, ?)",
        ("jquants", "J-Quants"),
    )

    with pytest.raises(SystemExit) as excinfo:
        seed_demo.seed(demo_db, replace=True)

    assert "jquants" in str(excinfo.value)


def test_seed_proceeds_on_empty_demo_database(demo_db):
    """デモ用の空DBには投入できる。"""
    counts = seed_demo.seed(demo_db, replace=True)

    assert counts["targets"] == len(seed_demo.COMPANIES)
    assert counts["prices"] > 0
    assert counts["disclosures"] > 0


def test_production_database_names_are_not_allowed():
    """本番とローカル開発のDB名が許可集合に入っていないことを固定する。"""
    assert "neondb" not in seed_demo.DEMO_DATABASE_NAMES
    assert "invest" not in seed_demo.DEMO_DATABASE_NAMES


def test_quarterly_disclosure_carries_current_forecast_not_next():
    """四半期開示には今期予想が入り、翌期予想は入らない。"""
    values = seed_demo._summary_values(_company("ALPHA.DEMO"), "2Q", 2026)

    assert values["forecast_revenue"] is not None
    assert "next_forecast_revenue" not in values


def test_full_year_disclosure_carries_next_forecast_not_current():
    """FY開示では今期が実績になるため、会社の見通しは翌期ぶんに入る。"""
    values = seed_demo._summary_values(_company("ALPHA.DEMO"), "FY", 2026)

    assert "forecast_revenue" not in values
    assert values["next_forecast_revenue"] is not None
    assert values["annual_dividend_per_share"] is not None


def test_revision_changes_the_forecast():
    """業績予想の修正は、四半期開示の予想と異なる値になる。同値では改訂が画面に出ない。"""
    company = _company("ALPHA.DEMO")

    before = seed_demo._summary_values(company, "3Q", seed_demo.REVISION_FISCAL_YEAR)
    after = seed_demo._summary_values(
        company, "3Q", seed_demo.REVISION_FISCAL_YEAR, company.revision
    )

    assert after["forecast_revenue"] > before["forecast_revenue"]


def test_actual_lands_at_the_revised_level():
    """改訂年度の通期実績は改訂後の予想に整合する。上方修正して未達では系列が破綻する。"""
    company = _company("ALPHA.DEMO")

    revised = seed_demo._summary_values(
        company, "3Q", seed_demo.REVISION_FISCAL_YEAR, company.revision
    )
    actual = seed_demo._summary_values(company, "FY", seed_demo.REVISION_FISCAL_YEAR)

    assert actual["revenue"] == revised["forecast_revenue"]


def test_downward_revision_exists():
    """上方修正だけのデモにしない。下方修正する企業も用意する。"""
    assert any(c.revision < 1.0 for c in seed_demo.COMPANIES)
    assert any(c.revision > 1.0 for c in seed_demo.COMPANIES)
