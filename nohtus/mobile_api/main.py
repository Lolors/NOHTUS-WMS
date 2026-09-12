"""모바일 전용 재고 조회 API.

mobile_app/(정적 프론트엔드)이 호출하는 백엔드. 기존 Streamlit 앱과
같은 SQLite DB, 같은 users 테이블/비밀번호를 사용하지만 완전히 별도
프로세스로 떠서 mobile_app/의 정적 파일을 서빙하고 JSON API를 제공한다.

실행: python -m uvicorn nohtus.mobile_api.main:app --port 8535
"""

from __future__ import annotations

from pathlib import Path

from fastapi import Depends, FastAPI, Header, HTTPException, Request
from fastapi.staticfiles import StaticFiles
from pydantic import BaseModel

from nohtus.export_app import db as export_db
from nohtus.services.export_waiting import ensure_export_waiting_tables

from nohtus.mobile_api import auth, export_queries, location_map_queries, purchase_queries, queries

app = FastAPI(title="NOHTUS 모바일 재고 API")

# 수출 현황(export_queries)이 export_app DB와 WMS 쪽 export_waiting_orders
# 브릿지 테이블을 함께 읽는다. 평소엔 스트림릿 main()이 시작할 때 이 스키마를
# 준비해두지만, mobile_api는 완전히 별도 프로세스로 뜨기 때문에 여기서도
# 한 번 보장해줘야 한다 — 안 그러면 "no such table" 에러가 난다.
export_db.init_db()
ensure_export_waiting_tables()

_PROJECT_ROOT = Path(__file__).resolve().parents[2]
_FRONTEND_DIR = _PROJECT_ROOT / "mobile_app"


class LoginRequest(BaseModel):
    username: str
    password: str


def current_user(authorization: str | None = Header(default=None)):
    token = ""
    if authorization and authorization.lower().startswith("bearer "):
        token = authorization[7:].strip()
    user = auth.resolve_token(token)
    if not user:
        raise HTTPException(status_code=401, detail="로그인이 필요합니다.")
    return user


@app.post("/api/login")
def api_login(payload: LoginRequest, request: Request):
    ip = request.client.host if request.client else ""
    try:
        result = auth.login(payload.username, payload.password, ip=ip)
    except auth.LoginLockedError as exc:
        raise HTTPException(
            status_code=429,
            detail=f"로그인 시도가 너무 많습니다. {exc.retry_after_minutes}분 후 다시 시도해주세요.",
        )
    if not result:
        raise HTTPException(status_code=401, detail="아이디 또는 비밀번호가 맞지 않습니다.")
    token, user = result
    return {"token": token, "user": user}


@app.post("/api/logout")
def api_logout(authorization: str | None = Header(default=None)):
    token = ""
    if authorization and authorization.lower().startswith("bearer "):
        token = authorization[7:].strip()
    auth.logout(token)
    return {"ok": True}


@app.get("/api/me")
def api_me(user=Depends(current_user)):
    return {"user": user}


@app.get("/api/products/search")
def api_search(
    q: str = "",
    limit: int = 20,
    exclude_material: bool = True,
    sort: str = "relevance",
    user=Depends(current_user),
):
    return {"results": queries.search_products(q, limit=limit, exclude_material=exclude_material, sort=sort)}


@app.get("/api/products/{name:path}")
def api_product_detail(name: str, user=Depends(current_user)):
    return queries.stock_detail(name)


@app.get("/api/location-map/layout")
def api_location_map_layout(user=Depends(current_user)):
    return location_map_queries.get_layout()


@app.get("/api/expiry")
def api_expiry(
    q: str = "",
    period: str = "1y",
    exclude_bidata: bool = True,
    warehouse: str = "all",
    limit: int = 100,
    user=Depends(current_user),
):
    return {
        "results": queries.search_expiry(
            q, period=period, exclude_bidata=exclude_bidata, warehouse=warehouse, limit=limit
        )
    }


@app.get("/api/expiry/{name:path}")
def api_expiry_detail(
    name: str,
    period: str = "1y",
    exclude_bidata: bool = True,
    warehouse: str = "all",
    user=Depends(current_user),
):
    return queries.expiry_detail(name, period=period, exclude_bidata=exclude_bidata, warehouse=warehouse)


@app.get("/api/purchase/search")
def api_purchase_search(q: str = "", period: str = "1y", limit: int = 20, user=Depends(current_user)):
    return {"results": purchase_queries.search_products(q, period=period, limit=limit)}


@app.get("/api/purchase/{name:path}")
def api_purchase_detail(name: str, period: str = "1y", user=Depends(current_user)):
    return purchase_queries.product_detail(name, period=period)


@app.get("/api/export/countries")
def api_export_countries(user=Depends(current_user)):
    return {"countries": export_queries.available_countries()}


@app.get("/api/export/dashboard")
def api_export_dashboard(
    country: str = "",
    transport: str = "",
    period: str = "recent",
    user=Depends(current_user),
):
    return export_queries.export_dashboard(country=country, transport=transport, period=period)


@app.get("/api/export/dashboard/year/{year}")
def api_export_year(
    year: int,
    country: str = "",
    transport: str = "",
    user=Depends(current_user),
):
    return {"cases": export_queries.export_year_cases(year, country=country, transport=transport)}


@app.get("/api/export/dashboard/month/{year}/{month}")
def api_export_month(
    year: int,
    month: int,
    country: str = "",
    transport: str = "",
    user=Depends(current_user),
):
    return {"cases": export_queries.export_month_cases(year, month, country=country, transport=transport)}


@app.get("/api/export/cases/{case_id}/items")
def api_export_case_items(case_id: int, user=Depends(current_user)):
    return {"items": export_queries.case_order_items(case_id)}


if _FRONTEND_DIR.is_dir():
    app.mount("/", StaticFiles(directory=str(_FRONTEND_DIR), html=True), name="mobile_app")
