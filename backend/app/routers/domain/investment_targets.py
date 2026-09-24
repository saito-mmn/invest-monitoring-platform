"""
銘柄 (InvestmentTarget) CRUD + 価格履歴 API
"""
from fastapi import APIRouter, Depends, HTTPException, Query
from psycopg.errors import UniqueViolation

from app.database import Connection, get_db
from app.models.investment_target import (
    InvestmentTargetCreate,
    InvestmentTargetRead,
    InvestmentTargetUpdate,
    LatestMarketPriceRead,
    MarketPriceRead,
)
from app.repositories.investment_target_repository import InvestmentTargetRepository

router = APIRouter(prefix="/investment-targets", tags=["investment-targets"])


def _repo(conn: Connection = Depends(get_db)) -> InvestmentTargetRepository:
    return InvestmentTargetRepository(conn)


@router.get("/", response_model=list[InvestmentTargetRead])
def list_investment_targets(is_active: bool | None = None, repo: InvestmentTargetRepository = Depends(_repo)):
    return repo.find_all(is_active=is_active)


@router.get("/latest-prices", response_model=list[LatestMarketPriceRead])
def latest_prices(repo: InvestmentTargetRepository = Depends(_repo)):
    return repo.get_all_latest_prices()


@router.get("/{target_id}", response_model=InvestmentTargetRead)
def get_investment_target(target_id: int, repo: InvestmentTargetRepository = Depends(_repo)):
    investment_target = repo.find_by_id(target_id)
    if not investment_target:
        raise HTTPException(status_code=404, detail="InvestmentTarget not found")
    return investment_target


@router.get("/{target_id}/prices", response_model=list[MarketPriceRead])
def investment_target_prices(
    target_id: int,
    days: int = Query(default=30, ge=1, le=3650),
    repo: InvestmentTargetRepository = Depends(_repo),
):
    if not repo.find_by_id(target_id):
        raise HTTPException(status_code=404, detail="InvestmentTarget not found")
    return repo.get_price_history(target_id, days=days)


@router.post("/", response_model=InvestmentTargetRead, status_code=201)
def create_investment_target(body: InvestmentTargetCreate, repo: InvestmentTargetRepository = Depends(_repo)):
    try:
        new_id = repo.create(body.model_dump())
    except UniqueViolation as exc:
        raise HTTPException(status_code=409, detail="target_key already exists") from exc
    return repo.find_by_id(new_id)


@router.patch("/{target_id}", response_model=InvestmentTargetRead)
def update_investment_target(
    target_id: int, body: InvestmentTargetUpdate, repo: InvestmentTargetRepository = Depends(_repo)
):
    if not repo.find_by_id(target_id):
        raise HTTPException(status_code=404, detail="InvestmentTarget not found")
    repo.update(target_id, body.model_dump(exclude_none=True))
    return repo.find_by_id(target_id)


@router.delete("/{target_id}", status_code=204)
def delete_investment_target(target_id: int, repo: InvestmentTargetRepository = Depends(_repo)):
    if not repo.find_by_id(target_id):
        raise HTTPException(status_code=404, detail="InvestmentTarget not found")
    repo.update(target_id, {"is_active": False})
