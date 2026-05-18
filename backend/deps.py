"""
依赖注入：DB 连接等，支持 FastAPI lifespan 生命周期
"""
from contextlib import asynccontextmanager
from fastapi import FastAPI
from engine.datahub import MarketDB

_db: MarketDB | None = None


def get_db() -> MarketDB:
    global _db
    if _db is None:
        _db = MarketDB()
    return _db


def close_db():
    global _db
    if _db is not None:
        _db.close()
        _db = None


@asynccontextmanager
async def lifespan(app: FastAPI):
    # 启动：什么都不做，get_db() 懒加载
    yield
    # 关闭：清理 DB 连接
    close_db()