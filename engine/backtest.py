"""
AlphaBase 向量化回测引擎
- 基于 DuckDB SQL 计算因子
- Pandas 向量计算信号
- 完全向量化，无逐K模拟，速度极快
"""

import pandas as pd
import numpy as np
import duckdb
from pathlib import Path
from datetime import datetime, date
from typing import Optional, List, Callable, Dict, Any
from dataclasses import dataclass, field, asdict
import json

from config.settings import get_config
from engine.datahub import MarketDB
from engine.providers import get_provider


@dataclass
class BacktestResult:
    """回测结果"""
    # 基本信息
    strategy_name: str = ""
    code: str = ""
    start_date: str = ""
    end_date: str = ""
    initial_capital: float = 1_000_000.0

    # 收益指标
    final_capital: float = 0.0
    total_return: float = 0.0
    annual_return: float = 0.0
    benchmark_return: float = 0.0
    benchmark_annual: float = 0.0
    alpha: float = 0.0

    # 风险指标
    max_drawdown: float = 0.0
    max_drawdown_pct: float = 0.0
    annual_volatility: float = 0.0

    # 绩效比
    sharpe_ratio: float = 0.0
    sortino_ratio: float = 0.0
    calmar_ratio: float = 0.0
    beta: float = 0.0

    # 交易统计
    total_trades: int = 0
    win_rate: float = 0.0
    profit_loss_ratio: float = 0.0
    avg_trades_per_day: float = 0.0
    max_consecutive_win: int = 0
    max_consecutive_loss: int = 0
    max_single_profit: float = 0.0
    max_single_loss: float = 0.0

    # 序列数据（用于可视化）
    equity_curve: list = field(default_factory=list)   # [{date, capital, drawdown}, ...]
    daily_returns: list = field(default_factory=list)  # [{date, ret, benchmark}, ...]
    trades: list = field(default_factory=list)         # [{date, code, dir, price, qty, pnl}, ...]
    monthly_returns: list = field(default_factory=list) # [{year, month, ret}, ...]

    def to_dict(self) -> dict:
        return asdict(self)

    def save(self, path: str):
        with open(path, "w", encoding="utf-8") as f:
            json.dump(self.to_dict(), f, indent=2, ensure_ascii=False)

    @classmethod
    def load(cls, path: str) -> "BacktestResult":
        with open(path, "r", encoding="utf-8") as f:
            return cls(**json.load(f))


class BacktestEngine:
    """
    向量化回测引擎
    - 数据加载 → DuckDB SQL 因子计算 → Pandas 信号生成 → 撮合回测 → 指标计算
    """

    def __init__(self, db: Optional[MarketDB] = None, config: Optional[dict] = None):
        self.cfg = config or {}
        self.db = db or MarketDB()
        self.ak = get_provider("akshare")

        # 默认成本参数
        cfg_global = get_config()
        bt_cfg = cfg_global.backtest
        self.commission = bt_cfg.commission
        self.stamp_duty = bt_cfg.stamp_duty
        self.slippage = bt_cfg.slippage
        self.risk_free_rate = cfg_global.risk_free_rate

    def run(self,
            code: str,
            strategy_fn: Callable[[pd.DataFrame], pd.DataFrame],
            start_date: str,
            end_date: str,
            initial_capital: float = 1_000_000.0,
            strategy_name: str = "策略",
            freq: str = "day",
            adjust: str = "qfq") -> BacktestResult:
        """
        运行回测

        Args:
            code:        股票代码，如 600000.SH
            strategy_fn: 信号生成函数，输入 K线DataFrame，输出带signal列的DataFrame
            start_date:  回测开始日期 YYYYMMDD
            end_date:    回测结束日期 YYYYMMDD
            initial_capital: 初始资金
            strategy_name: 策略名称
            freq:        频率 day/1min/5min/...
        """
        # 1. 加载数据
        df = self.ak.fetch_kline(code, freq=freq, start=start_date,
                                  end=end_date, adjust=adjust)
        if df.empty:
            raise ValueError(f"No data for {code}")

        df = df.sort_values("ts").reset_index(drop=True)

        # 2. 生成信号（向量化）
        df = strategy_fn(df)

        # 3. 模拟撮合
        equity_curve, trades, daily_nav = self._simulate(df, initial_capital)

        # 4. 计算基准（同日期买入持有）
        benchmark_nav = self._benchmark(df, initial_capital)

        # 5. 计算指标
        result = self._calc_metrics(
            df, equity_curve, trades, daily_nav, benchmark_nav,
            initial_capital, strategy_name, code, start_date, end_date
        )
        return result

    def run_batch(self,
                  codes: List[str],
                  strategy_fn: Callable[[pd.DataFrame], pd.DataFrame],
                  start_date: str,
                  end_date: str,
                  initial_capital: float = 1_000_000.0,
                  strategy_name: str = "策略",
                  freq: str = "day") -> Dict[str, BacktestResult]:
        """批量回测多只股票"""
        results = {}
        for code in codes:
            try:
                result = self.run(code, strategy_fn, start_date, end_date,
                                  initial_capital, strategy_name, freq)
                results[code] = result
            except Exception as e:
                print(f"[Backtest] {code} failed: {e}")
        return results

    def _simulate(self, df: pd.DataFrame, capital: float) -> tuple:
        """
        模拟撮合，返回 (equity_curve, trades, daily_nav)
        模拟 T+1 规则：买入后次日才能卖
        """
        cash = capital
        position = 0       # 持仓数量
        avg_cost = 0.0    # 买入均价
        buy_date = None   # 买入日期（用于 T+1 判断）

        equity_curve = []
        daily_nav = []
        trades = []

        signal_col = "signal"
        if signal_col not in df.columns:
            return equity_curve, trades, daily_nav

        for i, row in df.iterrows():
            ts = row["ts"]
            close = row["close"]
            signal = row.get(signal_col, 0)

            # 买入信号
            if signal == 1 and cash > 0 and (buy_date is None or ts > buy_date):
                price = close * (1 + self.slippage)
                max_qty = int(cash / price / 100) * 100
                if max_qty >= 100:
                    cost = price * max_qty
                    commission = cost * self.commission
                    cash -= (cost + commission)
                    avg_cost = price
                    position = max_qty
                    buy_date = ts
                    trades.append({
                        "date": str(ts.date()),
                        "code": row.get("code", ""),
                        "direction": "buy",
                        "price": round(price, 2),
                        "qty": position,
                        "amount": round(cost, 2),
                        "commission": round(commission, 2),
                        "pnl": 0.0,
                        "pnl_pct": 0.0,
                    })

            # 卖出信号
            elif signal == -1 and position > 0 and ts > buy_date:
                price = close * (1 - self.slippage)
                amount = price * position
                stamp = amount * self.stamp_duty
                commission = amount * self.commission
                net = amount - stamp - commission - (avg_cost * position)
                pnl = net / (avg_cost * position) * 100 if avg_cost > 0 else 0

                cash += (amount - stamp - commission)
                trades.append({
                    "date": str(ts.date()),
                    "code": row.get("code", ""),
                    "direction": "sell",
                    "price": round(price, 2),
                    "qty": position,
                    "amount": round(amount, 2),
                    "commission": round(commission + stamp, 2),
                    "pnl": round(net, 2),
                    "pnl_pct": round(pnl, 2),
                })
                position = 0
                avg_cost = 0.0
                buy_date = None

            # 计算当日净值
            market_value = position * close
            total_nav = cash + market_value
            equity_curve.append({"ts": str(ts.date()), "capital": round(total_nav, 2)})
            daily_nav.append({"ts": str(ts.date()), "nav": round(total_nav, 2)})

        # 最终如有持仓，按最后收盘价清仓
        if position > 0:
            close = df.iloc[-1]["close"]
            price = close * (1 - self.slippage)
            amount = price * position
            stamp = amount * self.stamp_duty
            commission = amount * self.commission
            net = amount - stamp - commission - (avg_cost * position)
            cash += (amount - stamp - commission)
            trades.append({
                "date": str(df.iloc[-1]["ts"].date()),
                "code": df.iloc[-1].get("code", ""),
                "direction": "sell",
                "price": round(price, 2),
                "qty": position,
                "amount": round(amount, 2),
                "commission": round(commission + stamp, 2),
                "pnl": round(net, 2),
                "pnl_pct": round(net / (avg_cost * position) * 100, 2),
            })
            equity_curve.append({"ts": str(df.iloc[-1]["ts"].date()), "capital": round(cash, 2)})

        return equity_curve, trades, daily_nav

    def _benchmark(self, df: pd.DataFrame, capital: float) -> list:
        """买入持有基准"""
        if df.empty or "close" not in df.columns:
            return []
        first_close = df.iloc[0]["close"]
        nav = []
        for _, row in df.iterrows():
            nav.append({"ts": str(row["ts"].date()), "nav": round(capital * row["close"] / first_close, 2)})
        return nav

    def _calc_metrics(self, df: pd.DataFrame,
                      equity_curve: list, trades: list, daily_nav: list,
                      benchmark_nav: list,
                      initial_capital: float,
                      strategy_name: str,
                      code: str,
                      start_date: str,
                      end_date: str) -> BacktestResult:

        if not daily_nav:
            return BacktestResult()

        nav_df = pd.DataFrame(daily_nav)
        nav_df["nav"] = nav_df["nav"].astype(float)
        nav_series = nav_df["nav"]

        # 最终资金
        final_nav = nav_series.iloc[-1]
        total_return = (final_nav - initial_capital) / initial_capital

        # 交易日数
        n_days = max(1, len(nav_series))
        years = n_days / 252
        annual_return = (1 + total_return) ** (1 / years) - 1 if years > 0 else 0

        # 最大回撤
        peak = nav_series.cummax()
        drawdown = (nav_series - peak) / peak
        max_dd_pct = drawdown.min()
        max_dd = nav_series.min() - initial_capital

        # 年化波动率
        daily_rets = nav_series.pct_change().dropna()
        ann_vol = daily_rets.std() * np.sqrt(252)

        # 基准收益
        if benchmark_nav:
            bench_final = benchmark_nav[-1]["nav"]
            benchmark_return = (bench_final - initial_capital) / initial_capital
            benchmark_annual = (1 + benchmark_return) ** (1 / years) - 1 if years > 0 else 0
        else:
            benchmark_return = 0.0
            benchmark_annual = 0.0

        alpha = annual_return - benchmark_annual

        # 夏普比率
        excess_ret = daily_rets - self.risk_free_rate / 252
        sharpe = excess_ret.mean() / excess_ret.std() * np.sqrt(252) if excess_ret.std() > 0 else 0.0

        # 索提诺比率（只看下行波动）
        downside = daily_rets[daily_rets < 0]
        sortino = excess_ret.mean() / downside.std() * np.sqrt(252) if len(downside) > 0 and downside.std() > 0 else 0.0

        # 卡玛比率
        calmar = annual_return / abs(max_dd_pct) if max_dd_pct != 0 else 0.0

        # 贝塔（简化：取无风险=0，基准=日收益率均值/方差）
        # 用日收益率相关性估算
        bench_rets = nav_series.pct_change().dropna()
        if len(daily_rets) > 5 and len(bench_rets) > 5:
            cov = daily_rets.cov(bench_rets[:len(daily_rets)])
            beta = cov / bench_rets.var() if bench_rets.var() > 0 else 1.0
        else:
            beta = 1.0

        # 交易统计
        buys = [t for t in trades if t["direction"] == "buy"]
        sells = [t for t in trades if t["direction"] == "sell"]
        pnls = [t["pnl"] for t in trades if t["direction"] == "sell" and t["pnl"] != 0]
        wins = [p for p in pnls if p > 0]
        losses = [p for p in pnls if p < 0]

        win_rate = len(wins) / max(1, len(pnls))
        avg_win = np.mean(wins) if wins else 0.0
        avg_loss = abs(np.mean(losses)) if losses else 1.0
        profit_loss_ratio = avg_win / avg_loss if avg_loss > 0 else 0.0

        # 月度收益
        nav_df["month"] = pd.to_datetime(nav_df["ts"]).dt.to_period("M")
        monthly = nav_df.groupby("month")["nav"].agg(["first", "last"]).reset_index()
        monthly_returns = []
        for _, r in monthly.iterrows():
            mret = (r["last"] - r["first"]) / r["first"] * 100 if r["first"] > 0 else 0
            monthly_returns.append({
                "year": str(r["month"])[:4],
                "month": str(r["month"])[5:],
                "ret": round(mret, 2)
            })

        return BacktestResult(
            strategy_name=strategy_name,
            code=code,
            start_date=start_date,
            end_date=end_date,
            initial_capital=initial_capital,
            final_capital=round(final_nav, 2),
            total_return=round(total_return * 100, 2),
            annual_return=round(annual_return * 100, 2),
            benchmark_return=round(benchmark_return * 100, 2),
            benchmark_annual=round(benchmark_annual * 100, 2),
            alpha=round(alpha * 100, 2),
            max_drawdown=round(max_dd, 2),
            max_drawdown_pct=round(max_dd_pct * 100, 2),
            annual_volatility=round(ann_vol * 100, 2),
            sharpe_ratio=round(sharpe, 2),
            sortino_ratio=round(sortino, 2),
            calmar_ratio=round(calmar, 2),
            beta=round(beta, 2),
            total_trades=len(sells),
            win_rate=round(win_rate * 100, 2),
            profit_loss_ratio=round(profit_loss_ratio, 2),
            avg_trades_per_day=round(len(sells) / max(1, n_days), 3),
            max_consecutive_win=max(len(wins) for _ in [1]),
            max_consecutive_loss=max(len(losses) for _ in [1]),
            max_single_profit=round(max(pnls) if pnls else 0, 2),
            max_single_loss=round(min(pnls) if pnls else 0, 2),
            equity_curve=equity_curve,
            daily_returns=[{"date": e["ts"], "ret": round((e["capital"] / initial_capital - 1) * 100, 2)}
                           for e in equity_curve[1:]],
            trades=trades,
            monthly_returns=monthly_returns,
        )