from fastapi import APIRouter, Depends

from app.core.security import require_token
from app.services.reports import build_dashboard_metrics, build_investor_view, build_report

router = APIRouter(tags=["dashboard"])


@router.get("/dashboard")
def dashboard_route(user=Depends(require_token)):
    return {
        "user": {
            "id": user["id"],
            "email": user["email"],
            "full_name": user["full_name"],
            "plan": user["plan"],
            "active": bool(user["active"]),
        },
        "metrics": build_dashboard_metrics(user["id"]),
    }


@router.get("/reports/{period}")
def report_route(period: str, user=Depends(require_token)):
    period = period.lower()
    if period not in {"weekly", "monthly"}:
        period = "weekly"
    return build_report(user["id"], period)


@router.get("/investor/overview")
def investor_overview_route(user=Depends(require_token)):
    return build_investor_view(user["id"])\n