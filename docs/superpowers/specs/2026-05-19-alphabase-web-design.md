# AlphaBase Web 版量化工作台 - 设计规格书

**日期：** 2026-05-19
**版本：** v0.1

---

## 1. 项目目标

打造类聚宽（JoinQuant）本地量化研究平台。用户在浏览器内完成数据获取 → 因子研究 → 回测分析的全流程，无需云端，数据全本地存储。

---

## 2. 技术选型

| 层级 | 技术栈 | 说明 |
|------|--------|------|
| 前端 | React 18 + Ant Design 5 | 组件丰富，图表生态好 |
| 后端 | FastAPI + Python 3.11+ | 高性能异步 API |
| 研究内核 | 自研 Notebook 引擎（类 Jupyter） | 代码执行 + 结果渲染 |
| 数据存储 | DuckDB | 列存储，OLAP 查询快，部署零依赖 |
| 数据源 | AkShare / Tushare / TDX | 复用 alphaBase 现有 providers |
| 回测引擎 | 复用 alphaBase `BacktestEngine` | 向量化回测，支持 T+1 |

---

## 3. 系统架构

```
┌──────────────────────────────────────────────────────────┐
│                     浏览器 (React SPA)                     │
└──────────────────────────┬───────────────────────────────┘
                           │ HTTP / WebSocket
┌──────────────────────────▼───────────────────────────────┐
│                   FastAPI 后端服务                         │
│  ┌──────────────┐  ┌──────────────┐  ┌──────────────┐  │
│  │ /api/notebook│  │ /api/backtest│  │  /api/data   │  │
│  │  Notebook    │  │   回测引擎   │  │  数据查询    │  │
│  │  执行引擎    │  │              │  │              │  │
│  └──────────────┘  └──────────────┘  └──────────────┘  │
│  ┌──────────────┐                                        │
│  │ /api/factors │  因子框架                              │
│  └──────────────┘                                        │
└──────────────────────────┬───────────────────────────────┘
                           │
┌──────────────────────────▼───────────────────────────────┐
│                  DuckDB (本地数据存储)                      │
│  kline | factors | signals | positions | notebook_sessions│
└──────────────────────────┬───────────────────────────────┘
                           │
┌──────────────────────────▼───────────────────────────────┐
│            AkShare / Tushare / TDX (数据源)                │
└──────────────────────────────────────────────────────────┘
```

---

## 4. 核心模块设计

### 4.1 Notebook 研究环境

**定位：** 核心工作区，类似聚宽 Jupyter 研究环境。

**交互模型：**
- 研究笔记由多个 Cell 组成
- 每个 Cell 输入 Python 代码，后端执行后返回结果
- 结果支持：DataFrame（表格渲染）、Matplotlib 图表（图片）、纯文本
- Cell 可自由拖拽排序、增删

**支持的魔法命令：**

| 魔法命令 | 功能 |
|---------|------|
| `%save_factor name` | 将当前 DataFrame 保存为因子 |
| `%backtest` | 使用当前数据运行回测，结果内嵌渲染 |
| `%data stock_code start end` | 加载行情数据到当前 Cell 变量 `df` |
| `%factors` | 列出已保存的因子库 |

**后端执行流程：**
```
用户提交代码
    ↓
FastAPI /api/notebook/execute
    ↓
代码在独立 Python 进程中执行（沙箱隔离）
    ↓
捕获 stdout / last_expr 结果
    ↓
DataFrame → 序列化为 JSON（限制前 1000 行）
    ↓
图表 → 保存为 PNG，返回 URL
    ↓
前端渲染 Cell 结果
```

**持久化：**
- 每次 Cell 执行自动保存当前 Notebook 状态到 DuckDB
- 支持创建/重命名/删除研究笔记，存储在 `notebook_sessions` 表

### 4.2 因子框架

**因子基类：**

```python
class Factor(ABC):
    name: str                           # 因子名称
    description: str                    # 因子描述

    @abstractmethod
    def compute(self, data: pd.DataFrame) -> pd.Series:
        """输入行情数据，返回因子值（index = ts）"""
        pass
```

**内置因子库（第一批）：**

| 因子 | 描述 |
|------|------|
| MA | 简单移动平均 |
| EMA | 指数移动平均 |
| RSI | 相对强弱指标 |
| MACD | 指数平滑异同移动平均线 |
| BOLL | 布林带 |
| VolumeRatio | 量比 |

**因子存储（DuckDB）：**
```sql
CREATE TABLE factors (
    id          INTEGER PRIMARY KEY,
    name        VARCHAR,
    codes       VARCHAR[],           -- 覆盖的股票列表
    freq        VARCHAR,              -- 频率：day / 1min / 5min ...
    value       JSON,                -- {ts: value} 序列化
    computed_at TIMESTAMP,
    created_at  TIMESTAMP DEFAULT now()
);
```

**因子分析：**
- IC（信息系数）分析：`IC = corr(factor, forward_return)`
- 分组回测收益分析：按因子值分组，统计各组未来收益差异
- 内置可视化：IC 时序图、分组收益热力图

### 4.3 回测引擎

**接口：**

```python
# Notebook 内调用示例
result = backtest(
    data=df,
    signal_fn=my_strategy,
    initial_capital=1_000_000,
    commission=0.00025,
    stamp_duty=0.001,
    slippage=0.001,
)
# result 直接内嵌渲染
```

**结果结构：**
```python
@dataclass
class BacktestResult:
    strategy_name: str
    period: tuple[str, str]
    initial_capital: float
    final_capital: float
    total_return: float
    annual_return: float
    benchmark_return: float
    alpha: float
    max_drawdown: float
    sharpe_ratio: float
    sortino_ratio: float
    calmar_ratio: float
    annual_volatility: float
    beta: float
    total_trades: int
    win_rate: float
    profit_loss_ratio: float
    equity_curve: list[dict]   # [{date, nav, position_value, cash, daily_return}]
    trades: list[dict]         # [{date, code, direction, price, qty, amount, fee, pnl}]
    monthly_returns: list[dict]
```

**前端渲染：** 回测结果内嵌在 Cell 输出区域，包含权益曲线图、交易标记图、绩效指标。

### 4.4 数据层

**复用 alphaBase 现有模块：**
- `engine/providers.py` → `DataProvider` 抽象 + `AkShare`/`Tushare`/`TDX` 实现
- `engine/datahub.py` → `MarketDB` DuckDB 封装

**数据库 Schema：**

```sql
-- K 线数据
CREATE TABLE kline (
    code   VARCHAR,
    freq   VARCHAR,
    ts     TIMESTAMP,
    open   DOUBLE, high  DOUBLE, low   DOUBLE, close  DOUBLE,
    volume BIGINT, turnover DOUBLE,
    PRIMARY KEY (code, freq, ts)
);

-- 因子表
CREATE TABLE factors (... 同上 ...);

-- 信号表
CREATE TABLE signals (
    code VARCHAR, signal_time TIMESTAMP, direction VARCHAR,
    price DOUBLE, strength DOUBLE, strategy VARCHAR, freq VARCHAR
);

-- 持仓表
CREATE TABLE positions (
    code VARCHAR, direction VARCHAR, qty INTEGER,
    avg_cost DOUBLE, open_time TIMESTAMP
);

-- 研究笔记
CREATE TABLE notebook_sessions (
    id INTEGER PRIMARY KEY,
    name VARCHAR,
    cells JSON,          -- [{type, code, result}]
    created_at TIMESTAMP DEFAULT now(),
    updated_at TIMESTAMP DEFAULT now()
);
```

**分区策略（中等规模）：**
- K 线表按 `freq` 分区（day / 1min / 5min 分开存储）
- 近期数据（近 1 年）单独一个子表，查询优先扫描

---

## 5. 前端页面结构

```
AlphaBase Web
├── 研究 (/research)
│   ├── 左侧：笔记列表
│   ├── 中间：Notebook 编辑区（Cell 序列）
│   └── 右侧：变量检查器（当前 Cell 执行后的变量）
│
├── 因子 (/factors)
│   ├── 因子列表（已保存的因子）
│   ├── 因子分析（IC / 分组收益）
│   └── 新建因子（代码编辑）
│
├── 回测 (/backtest)
│   ├── 回测报告（独立页面）
│   ├── 绩效摘要 / 权益曲线 / 交易记录 / 月度分析
│   └── 导出报告（PDF）
│
├── 数据 (/data)
│   ├── 股票列表
│   ├── 数据下载（按代码/日期范围）
│   └── 数据状态（已缓存 vs 待下载）
│
└── 设置 (/settings)
    ├── 数据源配置（Token / 目录路径）
    ├── 回测参数（手续费 / 滑点 / 初始资金）
    └── LLM 配置（AI 研究助手）
```

**Notebook 界面布局：**
```
┌─────────────────────────────────────────────────────┐
│ [新建 Cell] [保存笔记 ▾]  笔记名称：_________         │
├──────────────────────────┬──────────────────────────┤
│  [+] Cell 1: 代码         │  变量：                   │
│  %data 600000.SH ...     │  df: DataFrame (243 rows)│
│                          │  ma5: Series (243)        │
│  [执行] [上移] [下移] [×] │                          │
├──────────────────────────┤                          │
│  Cell 1 结果:            │                          │
│  ┌──────────────────┐   │                          │
│  │ DataFrame 表格   │   │                          │
│  └──────────────────┘   │                          │
├──────────────────────────┤                          │
│  [+] Cell 2: 代码        │                          │
│  df['signal'] = ...      │                          │
│                          │                          │
│  [执行]                  │                          │
└──────────────────────────┴──────────────────────────┘
```

---

## 6. 部署方式

**单机器部署（个人用户）：**
```bash
# 启动后端
uvicorn main:app --reload --port 8000

# 前端开发
cd frontend && npm run dev

# 生产构建
cd frontend && npm run build
# Nginx 反向代理 /api 到 :8000，静态文件 serve build/
```

**环境要求：**
- Python 3.11+
- Node.js 18+
- 8GB+ RAM（中等规模数据处理）
- 50GB+ 本地存储

---

## 7. MVP 优先级

**第一阶段（MVP）：**
1. FastAPI 骨架 + React 脚手架
2. Notebook Cell 执行（代码 → 返回 DataFrame 表格 + 图表）
3. 行情数据获取（AkShare）
4. 复用 alphaBase 回测引擎，Notebook 内嵌调用
5. 基本回测结果渲染（绩效指标 + 权益曲线）
6. 研究笔记持久化

**第二阶段：**
1. 因子框架（基类 + 内置因子）
2. IC 分析 + 分组收益分析
3. 因子库管理（保存 / 加载）
4. Notebook 魔法命令完善

**第三阶段：**
1. 完整因子分析看板
2. 批量回测（多策略对比）
3. 数据管理界面
4. 模拟 / 实盘对接预留接口

---

## 8. 与现有 alphaBase 的关系

| 现有模块 | 处理方式 |
|---------|---------|
| `engine/providers.py` | 直接复用 |
| `engine/datahub.py` | 直接复用，增加 notebook_sessions 表 |
| `engine/backtest.py` | 直接复用，JSON 序列化输出 |
| `config/settings.py` | 适配 FastAPI 配置加载（pydantic-settings） |
| `ui/` | 废弃（逐步迁移到 React） |
| `strategies/` | 用户策略放置目录，Notebook 动态导入 |

---

## 9. 成功标准

- [ ] 在浏览器中执行 `df = get_data("600000.SH", "20240101", "20250501")` 并渲染 DataFrame
- [ ] 定义 `signal_fn` 并调用 `%backtest` 魔法命令，内嵌渲染绩效报告
- [ ] 研究笔记保存后刷新页面不丢失
- [ ] 全市场 5 年日线数据可正常存储和查询
- [ ] IC 分析图表正确渲染