"""
AlphaBase 配置层
- 数据源配置（用户可自定义 token / API key）
- 数据库路径配置
- LLM API 配置
"""

import os
import json
from pathlib import Path
from typing import Optional
from dataclasses import dataclass, field, asdict

BASE_DIR = Path(__file__).parent.parent.resolve()
DATA_DIR = BASE_DIR / "data"
DATA_DIR.mkdir(exist_ok=True)

DEFAULT_CONFIG_PATH = BASE_DIR / "config" / "config.json"


@dataclass
class DataSourceConfig:
    """数据源配置"""
    # AkShare（免费，无需 token）
    akshare_enabled: bool = True

    # Tushare（需要 token）
    tushare_token: str = ""

    # 通达信本地数据（目录配置）
    tdx_dir: str = ""

    # MiniQMT（需要经纪商账户）
    qmt_account: str = ""
    qmt_password: str = ""
    qmt_server: str = ""

    # 自定义 HTTP API
    api_url: str = ""
    api_key: str = ""


@dataclass
class LLMConfig:
    """LLM 配置"""
    provider: str = "siliconflow"  # siliconflow | deepseek | ollama | openai
    api_key: str = ""
    base_url: str = "https://api.siliconflow.cn/v1"
    model: str = "Qwen/Qwen3-30B-A3B"
    timeout: int = 120


@dataclass
class BacktestConfig:
    """回测配置"""
    initial_capital: float = 1_000_000.0
    commission: float = 0.00025  # 万2.5
    stamp_duty: float = 0.001    # 千1（仅卖方）
    slippage: float = 0.001      # 滑点


@dataclass
class AppConfig:
    """全局配置"""
    data_source: DataSourceConfig = field(default_factory=DataSourceConfig)
    llm: LLMConfig = field(default_factory=LLMConfig)
    backtest: BacktestConfig = field(default_factory=BacktestConfig)

    # DuckDB 本地存储路径
    duckdb_path: str = str(DATA_DIR / "market.duckdb")

    # 无风险收益率（计算夏普比率用）
    risk_free_rate: float = 0.03

    def save(self, path: Optional[Path] = None):
        p = path or DEFAULT_CONFIG_PATH
        p.parent.mkdir(parents=True, exist_ok=True)
        with open(p, "w", encoding="utf-8") as f:
            json.dump(asdict(self), f, indent=2, ensure_ascii=False)

    @classmethod
    def load(cls, path: Optional[Path] = None) -> "AppConfig":
        p = path or DEFAULT_CONFIG_PATH
        if p.exists():
            with open(p, "r", encoding="utf-8") as f:
                data = json.load(f)
            return cls(**{
                "data_source": DataSourceConfig(**data.get("data_source", {})),
                "llm": LLMConfig(**data.get("llm", {})),
                "backtest": BacktestConfig(**data.get("backtest", {})),
                "duckdb_path": data.get("duckdb_path", str(DATA_DIR / "market.duckdb")),
                "risk_free_rate": data.get("risk_free_rate", 0.03),
            })
        return cls()

    @classmethod
    def from_env(cls) -> "AppConfig":
        """从环境变量加载配置（用于 Docker / 服务器部署）"""
        cfg = cls()
        ds = cfg.data_source
        ds.tushare_token = os.environ.get("TUSHARE_TOKEN", "")
        ds.api_key = os.environ.get("DATA_API_KEY", "")
        ds.api_url = os.environ.get("DATA_API_URL", "")
        cfg.llm.api_key = os.environ.get("LLM_API_KEY", "")
        cfg.llm.base_url = os.environ.get("LLM_BASE_URL", "https://api.siliconflow.cn/v1")
        cfg.llm.model = os.environ.get("LLM_MODEL", "Qwen/Qwen3-30B-A3B")
        ds.qmt_account = os.environ.get("QMT_ACCOUNT", "")
        ds.qmt_password = os.environ.get("QMT_PASSWORD", "")
        ds.qmt_server = os.environ.get("QMT_SERVER", "")
        return cfg


# 全局单例
_config: Optional[AppConfig] = None


def get_config() -> AppConfig:
    global _config
    if _config is None:
        _config = AppConfig.load()
    return _config


def reload_config():
    global _config
    _config = AppConfig.load()