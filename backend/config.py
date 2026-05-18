"""
FastAPI 层配置：适配现有 config/settings.py
"""
from pydantic import BaseModel
from config.settings import get_config


class DataSourceConfigAPI(BaseModel):
    tushare_token: str = ""
    akshare_enabled: bool = True


class BacktestConfigAPI(BaseModel):
    initial_capital: float = 1_000_000.0
    commission: float = 0.00025
    stamp_duty: float = 0.001
    slippage: float = 0.001


class AppConfigAPI(BaseModel):
    data_source: DataSourceConfigAPI
    backtest: BacktestConfigAPI
    duckdb_path: str
    risk_free_rate: float = 0.03

    @classmethod
    def from_app_config(cls) -> "AppConfigAPI":
        cfg = get_config()
        return cls(
            data_source=DataSourceConfigAPI(
                tushare_token=cfg.data_source.tushare_token,
                akshare_enabled=cfg.data_source.akshare_enabled,
            ),
            backtest=BacktestConfigAPI(
                initial_capital=cfg.backtest.initial_capital,
                commission=cfg.backtest.commission,
                stamp_duty=cfg.backtest.stamp_duty,
                slippage=cfg.backtest.slippage,
            ),
            duckdb_path=cfg.duckdb_path,
            risk_free_rate=cfg.risk_free_rate,
        )