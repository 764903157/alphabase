"""
AlphaBase 数据源适配层
统一接口：fetch_kline(code, freq, start, end) -> pd.DataFrame
"""

import pandas as pd
import numpy as np
from abc import ABC, abstractmethod
from typing import Optional
from config.settings import get_config

# 全局数据源实例缓存
_providers = {}


def get_provider(name: str = "auto") -> "DataProvider":
    """获取数据源实例，自动选择可用源"""
    global _providers
    if name in _providers:
        return _providers[name]

    if name == "auto":
        cfg = get_config()
        ds = cfg.data_source
        if ds.tushare_token:
            _providers["auto"] = TushareProvider(ds.tushare_token)
        else:
            _providers["auto"] = AkShareProvider()
        return _providers["auto"]
    elif name == "akshare":
        _providers["akshare"] = AkShareProvider()
        return _providers["akshare"]
    elif name == "tushare":
        cfg = get_config()
        _providers["tushare"] = TushareProvider(cfg.data_source.tushare_token)
        return _providers["tushare"]
    elif name == "tdx":
        cfg = get_config()
        _providers["tdx"] = TDXProvider(cfg.data_source.tdx_dir)
        return _providers["tdx"]
    raise ValueError(f"Unknown provider: {name}")


class DataProvider(ABC):
    """数据源抽象基类"""

    @abstractmethod
    def fetch_kline(self, code: str, freq: str = "day",
                    start: Optional[str] = None, end: Optional[str] = None,
                    adjust: str = "qfq") -> pd.DataFrame:
        """获取 K 线数据，返回 DataFrame 列：[code, name, ts, open, high, low, close, volume, turnover]"""
        pass

    @abstractmethod
    def fetch_stock_list(self, market: str = "A股") -> pd.DataFrame:
        """获取股票列表"""
        pass

    def close(self):
        pass


class AkShareProvider(DataProvider):
    """AkShare 数据源（免费，无需 token）"""

    def __init__(self):
        import akshare as ak
        self.ak = ak

    def _to_today(self):
        from datetime import date
        return date.today().strftime("%Y%m%d")

    def _normalize_code(self, code: str) -> tuple:
        """标准化股票代码为 tushare 格式，如 600000.SH"""
        code = code.strip().upper()
        if code.endswith(".SH") or code.endswith(".SZ"):
            return code
        if code.startswith("6"):
            return f"{code}.SH"
        else:
            return f"{code}.SZ"

    def fetch_kline(self, code: str, freq: str = "day",
                    start: Optional[str] = None, end: Optional[str] = None,
                    adjust: str = "qfq") -> pd.DataFrame:
        c = self._normalize_code(code)
        freq_map = {
            "day": "daily",
            "1min": "1min",
            "5min": "5min",
            "15min": "15min",
            "30min": "30min",
            "60min": "60min",
        }
        ak_freq = freq_map.get(freq, "daily")
        adj_map = {"qfq": "qfq", "hfq": "hfq", "none": ""}
        adj = adj_map.get(adjust, "qfq")

        try:
            df = self.ak.stock_zh_a_hist(
                symbol=c.split(".")[0],
                period=ak_freq,
                start_date=start or "20100101",
                end_date=end or self._to_today(),
                adjust=adj
            )
            if df is None or df.empty:
                return pd.DataFrame()

            # 标准化列名
            rename = {}
            for col in df.columns:
                cl = col.lower()
                if "日期" in col:
                    rename[col] = "ts"
                elif "开盘" in col or "open" in cl:
                    rename[col] = "open"
                elif "最高" in col or "high" in cl:
                    rename[col] = "high"
                elif "最低" in col or "low" in cl:
                    rename[col] = "low"
                elif "收盘" in col or "close" in cl:
                    rename[col] = "close"
                elif "成交量" in col or "volume" in cl:
                    rename[col] = "volume"
                elif "成交额" in col or "turnover" in cl or "amount" in cl:
                    rename[col] = "turnover"

            df = df.rename(columns=rename)
            if "ts" in df.columns:
                df["ts"] = pd.to_datetime(df["ts"])
                df["code"] = c
                if "name" not in df.columns:
                    df["name"] = c.split(".")[0]
            cols = ["code", "name", "ts", "open", "high", "low", "close", "volume", "turnover"]
            return df[[c for c in cols if c in df.columns]]

        except Exception as e:
            print(f"[AkShare] fetch_kline error {code}: {e}")
            return pd.DataFrame()

    def fetch_stock_list(self, market: str = "A股") -> pd.DataFrame:
        try:
            df = self.ak.stock_info_a_code_name()
            return df.rename(columns={"symbol": "code", "name": "name"})
        except Exception:
            return pd.DataFrame()


class TushareProvider(DataProvider):
    """Tushare 数据源（需要 token）"""

    def __init__(self, token: str = ""):
        import tushare as ts
        if token:
            ts.set_token(token)
        self.ts = ts
        # pro_api() returns a DataApi instance (lazy, no __call__)
        self.pro_api = ts.pro_api()

    def fetch_kline(self, code: str, freq: str = "day",
                    start: Optional[str] = None, end: Optional[str] = None,
                    adjust: str = "qfq") -> pd.DataFrame:
        # tushare 代码格式: 600000.SH
        c = code.strip().upper()
        adj_map = {"qfq": "qfq", "hfq": "hfq", "none": "None"}
        adj = adj_map.get(adjust, "qfq")

        try:
            # pro_bar needs only basic permissions, returns df with columns:
            # ts_code, trade_date, open, high, low, close, vol, amount
            df = self.ts.pro_bar(
                ts_code=c,
                freq="D",         # D=日线
                start_date=start or "",
                end_date=end or ""
            )
            if df is None or df.empty:
                return pd.DataFrame()
            df["ts"] = pd.to_datetime(df["trade_date"])
            df["code"] = c
            df = df.rename(columns={"vol": "volume", "amount": "turnover"})
            cols = ["code", "ts", "open", "high", "low", "close", "volume"]
            return df[[c for c in cols if c in df.columns]]
        except Exception as e:
            print(f"[Tushare] fetch_kline error {code}: {e}")
            return pd.DataFrame()

    def fetch_stock_list(self, market: str = "A股") -> pd.DataFrame:
        try:
            df = self.pro.stock_basic(exchange="", list_status="L",
                                     fields="ts_code,symbol,name,area,industry,market")
            return df.rename(columns={"ts_code": "code"})
        except Exception:
            return pd.DataFrame()


class TDXProvider(DataProvider):
    """通达信本地数据源（读取本地目录数据）"""

    def __init__(self, tdx_dir: str = ""):
        self.tdx_dir = tdx_dir

    def fetch_kline(self, code: str, freq: str = "day",
                    start: Optional[str] = None, end: Optional[str] = None,
                    adjust: str = "qfq") -> pd.DataFrame:
        # 通达信数据格式读取，需要 pytdx
        try:
            from pytdx.config import TdxConfig
            from pytdx.hq import TdxHq_API
            api = TdxHq_API(heartbeat=True)
            api.connect()

            market = 1 if code.startswith("6") or code.startswith("9") else 0
            date_format = "%Y-%m-%d" if freq == "day" else "%Y-%m-%d %H:%M"

            if freq == "day":
                data = api.get_security_bars(
                    category=9, market=market, code=code,
                    start=0, count=800
                )
            else:
                cat_map = {"1min": 8, "5min": 0, "15min": 1,
                           "30min": 2, "60min": 3}
                cat = cat_map.get(freq, 8)
                data = api.get_security_bars(
                    category=cat, market=market, code=code,
                    start=0, count=800
                )

            api.disconnect()
            if not data:
                return pd.DataFrame()

            df = pd.DataFrame(data)
            df["ts"] = pd.to_datetime(df["datetime"])
            df["code"] = code
            cols = ["code", "ts", "open", "high", "low", "close", "volume"]
            return df[[c for c in cols if c in df.columns]]
        except Exception as e:
            print(f"[TDX] fetch_kline error {code}: {e}")
            return pd.DataFrame()

    def fetch_stock_list(self, market: str = "A股") -> pd.DataFrame:
        return pd.DataFrame()