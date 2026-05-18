"""
回测 API
POST /api/backtest/run  ← 运行回测
"""
from fastapi import APIRouter, HTTPException
from pydantic import BaseModel
from typing import Optional, Any, Callable
import sys
sys.path.insert(0, str(__file__).rsplit("/", 3)[0])
from engine.backtest import BacktestEngine, BacktestResult
from backend.deps import get_db

router = APIRouter()


class BacktestRunRequest(BaseModel):
    code: str
    strategy_code: str  # 用户写的策略函数代码
    start_date: str
    end_date: str
    initial_capital: float = 1_000_000.0
    strategy_name: str = "策略"
    freq: str = "day"
    adjust: str = "qfq"


def _build_strategy_fn(code: str) -> Callable:
    """将策略代码字符串编译为可调用函数"""
    ns = {}
    exec(compile(code, "<strategy>", "exec"), ns)
    if "signal_fn" in ns:
        return ns["signal_fn"]
    if "signal" in ns:
        raise ValueError("策略代码必须定义 signal_fn(df) 函数，不能只定义 signal 列")
    raise ValueError("策略代码必须定义 signal_fn(df) 函数")


@router.post("/run")
def run_backtest(req: BacktestRunRequest):
    try:
        strategy_fn = _build_strategy_fn(req.strategy_code)
    except Exception as e:
        raise HTTPException(status_code=400, detail=f"策略编译错误: {e}")

    db = get_db()
    engine = BacktestEngine(db=db)

    try:
        result = engine.run(
            code=req.code,
            strategy_fn=strategy_fn,
            start_date=req.start_date,
            end_date=req.end_date,
            initial_capital=req.initial_capital,
            strategy_name=req.strategy_name,
            freq=req.freq,
            adjust=req.adjust,
        )
        return result.to_dict()
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"回测运行错误: {e}")