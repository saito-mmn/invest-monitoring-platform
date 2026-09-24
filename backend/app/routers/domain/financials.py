"""財務開示 API — 開示履歴と最新サマリー"""

from fastapi import APIRouter, Depends, HTTPException, Query

from app.database import Connection, get_db
from app.models.financial import FinancialDisclosureRead, LatestFinancialRead
from app.repositories.financial_repository import FinancialRepository
from app.repositories.investment_target_repository import InvestmentTargetRepository

router = APIRouter(prefix="/investment-targets", tags=["financials"])


def _repo(conn: Connection = Depends(get_db)) -> FinancialRepository:
    return FinancialRepository(conn)


def _require_target(conn: Connection, target_id: int) -> None:
    if not InvestmentTargetRepository(conn).find_by_id(target_id):
        raise HTTPException(status_code=404, detail="InvestmentTarget not found")


@router.get("/{target_id}/financial-disclosures", response_model=list[FinancialDisclosureRead])
def financial_disclosures(
    target_id: int,
    limit: int = Query(default=50, ge=1, le=500),
    conn: Connection = Depends(get_db),
):
    """開示履歴を新しい順に返す。訂正開示は元の開示と別レコードとして含む。"""
    _require_target(conn, target_id)
    return FinancialRepository(conn).find_disclosures(target_id, limit=limit)


@router.get(
    "/{target_id}/forecast-history",
    response_model=list[FinancialDisclosureRead],
)
def forecast_history(
    target_id: int,
    limit: int = Query(default=50, ge=1, le=500),
    conn: Connection = Depends(get_db),
):
    """会社予想の改訂履歴を新しい順に返す。

    決算短信と業績予想の修正の両方を含む。予想を持たない開示は除く。
    """
    _require_target(conn, target_id)
    return FinancialRepository(conn).find_forecast_history(target_id, limit=limit)


@router.get("/{target_id}/financial-summary/latest", response_model=LatestFinancialRead)
def latest_financial_summary(target_id: int, conn: Connection = Depends(get_db)):
    """最新の実績と、今期・翌期の予想を返す。

    最新の開示が今期予想を持たない場合があるため、予想はそれぞれ値を持つ最新の開示から
    取得し、出所の開示ごと返す。
    """
    _require_target(conn, target_id)
    latest = FinancialRepository(conn).find_latest(target_id)
    if latest is None:
        raise HTTPException(status_code=404, detail="No financial disclosure found")
    return latest
