"""Pydantic スキーマ — theme_investment_target"""

from pydantic import BaseModel

from app.models.investment_target import InvestmentTargetRead


class ThemeInvestmentTargetBase(BaseModel):
    basket_weight: float = 1.0
    rationale: str | None = None


class ThemeInvestmentTargetCreate(ThemeInvestmentTargetBase):
    """テーマへの銘柄追加・更新。

    `theme_id` はURLのパスで指定するため、bodyには含めない。両方で受け取ると
    食い違った場合の扱いが曖昧になる。
    """

    target_id: int


class ThemeInvestmentTargetUpdate(BaseModel):
    basket_weight: float | None = None
    rationale: str | None = None
    is_active: bool | None = None


class ThemeInvestmentTargetRead(ThemeInvestmentTargetBase):
    theme_id: int
    target_id: int
    is_active: bool
    created_at: str

    model_config = {"from_attributes": True}


class ThemeConstituentRead(InvestmentTargetRead):
    """テーマの構成銘柄。銘柄そのものの属性に、テーマ内での位置づけを添える。

    `theme_rationale` はこのテーマにその銘柄を含めた理由で、投資仮説の記録にあたる。
    銘柄マスタ側の属性ではないため、列名を分けている。
    """

    basket_weight: float | None = None
    theme_rationale: str | None = None
    relation_is_active: bool
