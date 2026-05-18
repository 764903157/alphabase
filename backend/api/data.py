"""
行情数据 API
GET /api/data/kline?code=600000.SH&freq=day&start=20240101&end=20250501
GET /api/data/stocks
POST /api/data/kline/save
"""
from fastapi import APIRouter, Depends, Query, HTTPException
from pydantic import BaseModel
from typing import Optional
import logging
import sys

sys.path.insert(0, str(__file__).rsplit("/", 3)[0])
from engine.providers import get_provider
from engine.datahub import MarketDB
from backend.deps import get_db

logger = logging.getLogger(__name__)

router = APIRouter()


class KLineSaveRequest(BaseModel):
    code: str
    freq: str = "day"
    start: Optional[str] = None
    end: Optional[str] = None
    adjust: str = "qfq"


@router.get("/kline")
def get_kline(
    code: str = Query(..., description="股票代码，如 600000.SH"),
    freq: str = Query("day", description="频率：day/1min/5min..."),
    start: Optional[str] = Query(None, description="开始日期 YYYYMMDD"),
    end: Optional[str] = Query(None, description="结束日期 YYYYMMDD"),
    limit: int = Query(0, description="限制返回条数，0=不限"),
    adjust: str = Query("qfq", description="复权类型：qfq/hfq/none"),
):
    provider = get_provider("auto")
    try:
        df = provider.fetch_kline(code, freq=freq, start=start, end=end, adjust=adjust)
    except Exception as e:
        logger.exception("fetch_kline failed")
        raise HTTPException(status_code=502, detail=f"Data provider error: {e}")
    if df.empty:
        return {"code": code, "data": [], "total": 0}

    if limit > 0:
        df = df.tail(limit)

    # 序列化为 dict（限制前 2000 行用于展示）
    data = df.head(2000).to_dict(orient="records")
    # 转换 datetime 为字符串
    for row in data:
        if "ts" in row and hasattr(row["ts"], "isoformat"):
            row["ts"] = row["ts"].isoformat()

    return {"code": code, "data": data, "total": len(df)}


@router.get("/stocks")
def get_stock_list():
    provider = get_provider("auto")
    try:
        df = provider.fetch_stock_list()
    except Exception as e:
        logger.exception("fetch_stock_list failed")
        raise HTTPException(status_code=502, detail=f"Data provider error: {e}")
    if df.empty:
        return {"data": []}
    return {"data": df.head(500).to_dict(orient="records")}


@router.post("/kline/save")
def save_kline(req: KLineSaveRequest, db: MarketDB = Depends(get_db)):
    provider = get_provider("auto")
    try:
        df = provider.fetch_kline(
            req.code, freq=req.freq, start=req.start, end=req.end, adjust=req.adjust
        )
    except Exception as e:
        logger.exception("fetch_kline failed")
        raise HTTPException(status_code=502, detail=f"Data provider error: {e}")
    if df.empty:
        raise HTTPException(status_code=400, detail="No data fetched")
    db.save_kline(df, freq=req.freq)
    return {"saved": len(df), "code": req.code, "freq": req.freq}