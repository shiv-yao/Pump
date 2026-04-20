from pydantic import BaseModel


class OrderRequest(BaseModel):
    asset_id: str
    side: str
    size: float
    price: float | None = None
    venue: str | None = "auto"
    strategy_id: str | None = "default"


class CancelRequest(BaseModel):
    order_id: str
    venue: str | None = "auto"
