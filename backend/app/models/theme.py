"""Pydantic スキーマ — theme"""

from datetime import datetime

from pydantic import BaseModel


class ThemeBase(BaseModel):
    theme_key: str
    theme_name: str
    strategy_id: int
    description: str | None = None


class ThemeCreate(ThemeBase):
    pass


class ThemeUpdate(BaseModel):
    theme_name: str | None = None
    strategy_id: int | None = None
    description: str | None = None
    is_active: bool | None = None


class ThemeRead(ThemeBase):
    theme_id: int
    is_active: bool
    created_at: datetime
    updated_at: datetime

    model_config = {"from_attributes": True}


class ThemeDetailRead(ThemeRead):
    """テーマ1件。所属strategyは `strategy_id` の解決が呼び出し側に必要にならないよう、
    キーと表示名を含めて返す。"""

    strategy_key: str
    strategy_name: str


class ThemeSummaryRead(BaseModel):
    """テーマ一覧の集計行。strategyと構成銘柄数を添える。"""

    theme_id: int
    theme_key: str
    theme_name: str
    strategy_id: int
    strategy_key: str
    strategy_name: str
    target_count: int
    is_active: bool

    model_config = {"from_attributes": True}


class StrategyBase(BaseModel):
    strategy_key: str
    strategy_name: str
    description: str | None = None


class StrategyCreate(StrategyBase):
    pass


class StrategyRead(StrategyBase):
    strategy_id: int
    is_active: bool
    created_at: datetime
    updated_at: datetime

    model_config = {"from_attributes": True}
