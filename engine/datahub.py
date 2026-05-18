"""
AlphaBase 数据层 - DuckDB 统一存储
支持多数据源：AkShare / Tushare / TDX / QMT
"""

import duckdb
import pandas as pd
import numpy as np
from pathlib import Path
from datetime import datetime, date
from typing import Optional, List, Literal
from config.settings import get_config


class MarketDB:
    """DuckDB 市场数据库，统一存储 K 线 / 因子 / 信号"""

    def __init__(self, path: Optional[str] = None):
        cfg = get_config()
        self.path = path or cfg.duckdb_path
        Path(self.path).parent.mkdir(parents=True, exist_ok=True)
        self.conn = duckdb.connect(self.path, read_only=False)
        self._init_schema()

    def _init_schema(self):
        """初始化表结构"""
        self.conn.execute("""
            CREATE SEQUENCE IF NOT EXISTS trade_id_seq;
            CREATE SEQUENCE IF NOT EXISTS signal_id_seq;
        """)
        self.conn.execute("""
            CREATE TABLE IF NOT EXISTS kline (
                id          BIGINT DEFAULT nextval('trade_id_seq') PRIMARY KEY,
                code        VARCHAR(12) NOT NULL,
                name        VARCHAR(32),
                freq        VARCHAR(8)  NOT NULL,   -- 1min/5min/15min/30min/60min/day
                ts          TIMESTAMP   NOT NULL,
                open        DOUBLE,
                high        DOUBLE,
                low         DOUBLE,
                close       DOUBLE,
                volume      DOUBLE,
                turnover    DOUBLE,
                UNIQUE (code, freq, ts)
            );
        """)
        self.conn.execute("""
            CREATE TABLE IF NOT EXISTS factors (
                id          BIGINT DEFAULT nextval('trade_id_seq') PRIMARY KEY,
                code        VARCHAR(12) NOT NULL,
                name        VARCHAR(64) NOT NULL,
                value       DOUBLE,
                ts          TIMESTAMP   NOT NULL,
                UNIQUE (code, name, ts)
            );
        """)
        self.conn.execute("""
            CREATE TABLE IF NOT EXISTS signals (
                id          BIGINT DEFAULT nextval('signal_id_seq') PRIMARY KEY,
                code        VARCHAR(12) NOT NULL,
                signal_time TIMESTAMP   NOT NULL,
                direction   VARCHAR(4)  NOT NULL,   -- buy/sell/short/cover
                price       DOUBLE,
                strength    DOUBLE,
                strategy    VARCHAR(64),
                freq        VARCHAR(8),
                UNIQUE (code, signal_time, strategy)
            );
        """)
        self.conn.execute("""
            CREATE TABLE IF NOT EXISTS positions (
                id          BIGINT DEFAULT nextval('trade_id_seq') PRIMARY KEY,
                code        VARCHAR(12) NOT NULL,
                name        VARCHAR(32),
                direction   VARCHAR(4),
                qty         BIGINT,
                avg_cost    DOUBLE,
                open_time   TIMESTAMP,
                update_time TIMESTAMP DEFAULT now()
            );
        """)
        # 索引
        self.conn.execute("CREATE INDEX IF NOT EXISTS idx_kline_code ON kline(code)")
        self.conn.execute("CREATE INDEX IF NOT EXISTS idx_kline_freq  ON kline(freq)")
        self.conn.execute("CREATE INDEX IF NOT EXISTS idx_kline_ts   ON kline(ts)")

    # ──────────────────────────────────────────────
    # K线读写
    # ──────────────────────────────────────────────

    def save_kline(self, df: pd.DataFrame, freq: str = "day"):
        """批量写入 K 线数据"""
        if df.empty:
            return
        df = df.copy()
        if "code" not in df.columns:
            return
        df["freq"] = freq
        if "ts" not in df.columns:
            if "datetime" in df.columns:
                df["ts"] = pd.to_datetime(df["datetime"])
            elif "date" in df.columns:
                df["ts"] = pd.to_datetime(df["date"])
        cols = ["code", "name", "freq", "ts", "open", "high", "low", "close", "volume", "turnover"]
        cols = [c for c in cols if c in df.columns]
        self.conn.execute("DELETE FROM kline WHERE code = ? AND freq = ?",
                          [df["code"].iloc[0], freq])
        self.conn.execute(f"""
            INSERT INTO kline ({','.join(cols)}) VALUES ({','.join(['?']*len(cols))})
        """, df[cols].values.tolist())

    def get_kline(self, code: str, freq: str = "day",
                   start: Optional[str] = None, end: Optional[str] = None,
                   limit: int = 0) -> pd.DataFrame:
        """
        获取 K 线数据
        - 支持 Vectorized 回测（直接用 DuckDB SQL）
        """
        sql = "SELECT * FROM kline WHERE code = ? AND freq = ?"
        params = [code, freq]
        if start:
            sql += " AND ts >= ?"
            params.append(start)
        if end:
            sql += " AND ts <= ?"
            params.append(end)
        sql += " ORDER BY ts"
        if limit > 0:
            sql += f" LIMIT {limit}"
        df = self.conn.execute(sql, params).fetchdf()
        return df

    def get_kline_range(self, codes: List[str], freq: str = "day",
                        start: Optional[str] = None, end: Optional[str] = None) -> pd.DataFrame:
        """批量获取多只股票的 K 线（向量化回测用）"""
        if not codes:
            return pd.DataFrame()
        placeholders = ",".join([f"'{c}'" for c in codes])
        sql = f"SELECT * FROM kline WHERE code IN ({placeholders}) AND freq = ?"
        params = [freq]
        if start:
            sql += " AND ts >= ?"
            params.append(start)
        if end:
            sql += " AND ts <= ?"
            params.append(end)
        sql += " ORDER BY code, ts"
        return self.conn.execute(sql, params).fetchdf()

    # ──────────────────────────────────────────────
    # 因子读写（SQL 定义存入 DuckDB）
    # ──────────────────────────────────────────────

    def save_factors(self, df: pd.DataFrame):
        """批量写入因子值"""
        if df.empty:
            return
        cols = ["code", "name", "value", "ts"]
        self.conn.execute(f"""
            INSERT INTO factors ({','.join(cols)}) VALUES ({','.join(['?']*len(cols))})
        """, df[cols].values.tolist())

    def get_factors(self, code: str, name: str,
                    start: Optional[str] = None, end: Optional[str] = None) -> pd.DataFrame:
        sql = "SELECT ts, value FROM factors WHERE code = ? AND name = ?"
        params = [code, name]
        if start:
            sql += " AND ts >= ?"
            params.append(start)
        if end:
            sql += " AND ts <= ?"
            params.append(end)
        sql += " ORDER BY ts"
        return self.conn.execute(sql, params).fetchdf()

    # ──────────────────────────────────────────────
    # 信号读写
    # ──────────────────────────────────────────────

    def save_signal(self, code: str, signal_time: str, direction: str,
                    price: float, strength: float = 1.0, strategy: str = "", freq: str = "day"):
        self.conn.execute("""
            INSERT INTO signals (code, signal_time, direction, price, strength, strategy, freq)
            VALUES (?, ?, ?, ?, ?, ?, ?)
        """, [code, signal_time, direction, price, strength, strategy, freq])

    def get_signals(self, code: Optional[str] = None,
                    strategy: Optional[str] = None,
                    start: Optional[str] = None,
                    end: Optional[str] = None) -> pd.DataFrame:
        sql = "SELECT * FROM signals WHERE 1=1"
        params = []
        if code:
            sql += " AND code = ?"
            params.append(code)
        if strategy:
            sql += " AND strategy = ?"
            params.append(strategy)
        if start:
            sql += " AND signal_time >= ?"
            params.append(start)
        if end:
            sql += " AND signal_time <= ?"
            params.append(end)
        sql += " ORDER BY signal_time"
        return self.conn.execute(sql, params).fetchdf()

    # ──────────────────────────────────────────────
    # 持仓
    # ──────────────────────────────────────────────

    def save_position(self, code: str, name: str, direction: str, qty: int,
                      avg_cost: float, open_time: Optional[str] = None):
        self.conn.execute("""
            DELETE FROM positions WHERE code = ?
        """, [code])
        self.conn.execute("""
            INSERT INTO positions (code, name, direction, qty, avg_cost, open_time)
            VALUES (?, ?, ?, ?, ?, ?)
        """, [code, name, direction, qty, avg_cost, open_time])

    def get_positions(self) -> pd.DataFrame:
        return self.conn.execute("SELECT * FROM positions").fetchdf()

    def close(self):
        self.conn.close()

    def __enter__(self):
        return self

    def __exit__(self, *args):
        self.close()