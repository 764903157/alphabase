# AlphaBase Web 版量化工作台 - 实现计划

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** 在浏览器内实现类聚宽的量化研究体验：Notebook Cell 执行 → 回测 → 结果内嵌渲染

**Architecture:** FastAPI 后端提供 REST API，前端 React + Ant Design SPA。后端复用 alphaBase 现有 engine 层，前端类 Jupyter Notebook 交互。

**Tech Stack:** FastAPI + Uvicorn / React 18 + Vite + Ant Design 5 + Axios

---

## 文件结构

```
alphabase/
├── backend/                         # FastAPI 后端（新建）
│   ├── __init__.py
│   ├── main.py                      # FastAPI 入口，路由注册
│   ├── config.py                    # pydantic 适配现有 settings
│   ├── deps.py                      # 依赖注入（DB 连接等）
│   └── api/
│       ├── __init__.py
│       ├── notebook.py               # /api/notebook/* 代码执行
│       ├── backtest.py              # /api/backtest/* 回测触发
│       ├── data.py                  # /api/data/* 行情数据查询
│       └── factors.py               # /api/factors/* 因子
├── frontend/                        # React 前端（新建）
│   ├── package.json
│   ├── vite.config.ts
│   ├── src/
│   │   ├── main.tsx
│   │   ├── App.tsx
│   │   ├── api/                    # Axios API 调用
│   │   │   ├── notebook.ts
│   │   │   ├── backtest.ts
│   │   │   └── data.ts
│   │   ├── pages/
│   │   │   ├── Research.tsx        # Notebook 研究页（核心）
│   │   │   ├── BacktestReport.tsx  # 回测报告页
│   │   │   ├── Data.tsx            # 数据管理页
│   │   │   └── Settings.tsx        # 设置页
│   │   └── components/
│   │       └── BacktestChart.tsx   # 回测图表组件
│   └── index.html
├── engine/                          # 复用（不修改核心逻辑）
│   ├── backtest.py                  # 仅加一行 to_dict() 序列化
│   ├── datahub.py                   # 仅增加 notebook_sessions 表
│   └── providers.py                # 不改
└── config/settings.py               # 不改
```

---

## Task 1: FastAPI 后端骨架

**Files:**
- Create: `backend/__init__.py`
- Create: `backend/main.py`
- Create: `backend/config.py`
- Create: `backend/deps.py`
- Create: `backend/api/__init__.py`

- [ ] **Step 1: 创建 backend 目录和 __init__.py**

```python
# backend/__init__.py
```

- [ ] **Step 2: 创建 backend/config.py（pydantic 适配现有 settings）**

```python
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
```

- [ ] **Step 3: 创建 backend/deps.py（依赖注入）**

```python
"""
依赖注入：DB 连接等
"""
from engine.datahub import MarketDB


_db: MarketDB | None = None


def get_db() -> MarketDB:
    global _db
    if _db is None:
        _db = MarketDB()
    return _db
```

- [ ] **Step 4: 创建 backend/main.py**

```python
"""
AlphaBase Web API 入口
"""
from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from backend.api import notebook, backtest, data, factors

app = FastAPI(title="AlphaBase API", version="0.1.0")

app.add_middleware(
    CORSMiddleware,
    allow_origins=["http://localhost:5173", "http://localhost:3000"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

app.include_router(notebook.router, prefix="/api/notebook", tags=["notebook"])
app.include_router(backtest.router, prefix="/api/backtest", tags=["backtest"])
app.include_router(data.router, prefix="/api/data", tags=["data"])
app.include_router(factors.router, prefix="/api/factors", tags=["factors"])


@app.get("/api/health")
def health():
    return {"status": "ok"}
```

- [ ] **Step 5: 创建 backend/api/__init__.py**

```python
```

- [ ] **Step 6: 验证后端骨架可启动**

Run: `cd /home/echo/alphabase && python -c "from backend.main import app; print('OK')"`
Expected: `OK`

---

## Task 2: /api/data 行情数据 API

**Files:**
- Create: `backend/api/data.py`

- [ ] **Step 1: 创建 backend/api/data.py**

```python
"""
行情数据 API
GET /api/data/kline?code=600000.SH&freq=day&start=20240101&end=20250501
GET /api/data/stocks
POST /api/data/kline/save
"""
from fastapi import APIRouter, Query, HTTPException
from pydantic import BaseModel
from typing import Optional
import pandas as pd
import sys
sys.path.insert(0, str(__file__).rsplit("/", 3)[0])
from engine.providers import get_provider
from engine.datahub import MarketDB
from backend.deps import get_db

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
):
    provider = get_provider("auto")
    df = provider.fetch_kline(code, freq=freq, start=start, end=end)
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
    df = provider.fetch_stock_list()
    if df.empty:
        return {"data": []}
    return {"data": df.head(500).to_dict(orient="records")}


@router.post("/kline/save")
def save_kline(req: KLineSaveRequest):
    provider = get_provider("auto")
    df = provider.fetch_kline(
        req.code, freq=req.freq, start=req.start, end=req.end, adjust=req.adjust
    )
    if df.empty:
        raise HTTPException(status_code=400, detail="No data fetched")
    db = get_db()
    db.save_kline(df, freq=req.freq)
    return {"saved": len(df), "code": req.code, "freq": req.freq}
```

- [ ] **Step 2: 测试 data API**

Run: `cd /home/echo/alphabase && uvicorn backend.main:app --port 8000 &`
Wait 3 seconds
Run: `curl "http://localhost:8000/api/data/kline?code=600000.SH&freq=day&start=20240101&end=20240501"`
Expected: JSON with kline data

---

## Task 3: /api/notebook 代码执行引擎

**Files:**
- Create: `backend/api/notebook.py`

- [ ] **Step 1: 创建 backend/api/notebook.py**

```python
"""
Notebook 执行引擎 API
POST /api/notebook/execute  ← 执行一段代码，返回结果
GET  /api/notebook/sessions ← 获取笔记列表
POST /api/notebook/sessions ← 创建新笔记
GET  /api/notebook/sessions/{id} ← 获取指定笔记
PUT  /api/notebook/sessions/{id} ← 保存笔记
DELETE /api/notebook/sessions/{id}
"""
from fastapi import APIRouter, HTTPException
from pydantic import BaseModel
from typing import Optional, Any
import pandas as pd
import io
import sys
import traceback
import json
from datetime import datetime

sys.path.insert(0, str(__file__).rsplit("/", 3)[0])
from backend.deps import get_db


router = APIRouter()


class ExecuteRequest(BaseModel):
    code: str
    session_id: Optional[int] = None


class CellResult(BaseModel):
    type: str  # dataframe | text | error | chart
    data: Any
    shape: Optional[tuple[int, int]] = None
    columns: Optional[list] = None
    stdout: str = ""


def _execute_code(code: str) -> CellResult:
    """在当前进程执行代码，返回结果（生产环境应隔离进程）"""
    # 捕获 stdout
    old_stdout = sys.stdout
    sys.stdout = buffer = io.StringIO()

    # 预设变量：pd, np, get_data
    ns: dict = {
        "pd": pd,
        "np": __import__("numpy"),
        "get_data": _make_get_data(),
    }

    try:
        compiled = compile(code, "<cell>", "exec")
        exec(compiled, ns)
        output = buffer.getvalue()
        sys.stdout = old_stdout

        # 取最后一个表达式结果
        # 从 AST 找最后一个表达式
        import ast
        tree = ast.parse(code)
        last_expr = None
        for node in ast.walk(tree):
            if isinstance(node, ast.Expr):
                last_expr = node.value

        result_data = None
        result_type = "text"
        shape = None
        columns = None

        if last_expr:
            val = eval(compile(ast.Expression(), "<expr>", "eval"), ns)
            if isinstance(val, pd.DataFrame):
                result_type = "dataframe"
                # 最多 1000 行
                display_df = val.head(1000)
                result_data = display_df.to_dict(orient="records")
                shape = (len(display_df), len(display_df.columns))
                columns = list(display_df.columns)
            elif hasattr(val, "__array__"):
                # matplotlib figure
                import matplotlib
                matplotlib.use("Agg")
                import matplotlib.pyplot as plt
                buf = io.BytesIO()
                plt.savefig(buf, format="png", bbox_inches="tight", dpi=100)
                buf.seek(0)
                import base64
                img_b64 = base64.b64encode(buf.read()).decode()
                plt.close()
                result_type = "chart"
                result_data = f"data:image/png;base64,{img_b64}"
            else:
                result_data = str(val)
        elif output:
            result_data = output

        return CellResult(type=result_type, data=result_data,
                         shape=shape, columns=columns, stdout=output)

    except Exception as e:
        sys.stdout = old_stdout
        return CellResult(
            type="error",
            data=f"{traceback.format_exc()}",
            stdout=buffer.getvalue(),
        )


def _make_get_data():
    """创建 get_data 函数"""
    from engine.providers import get_provider
    def get_data(code: str, start: str = "", end: str = "",
                 freq: str = "day", adjust: str = "qfq") -> pd.DataFrame:
        provider = get_provider("auto")
        df = provider.fetch_kline(code, freq=freq, start=start, end=end, adjust=adjust)
        return df
    return get_data


@router.post("/execute", response_model=CellResult)
def execute_cell(req: ExecuteRequest):
    return _execute_code(req.code)


@router.get("/sessions")
def list_sessions():
    db = get_db()
    try:
        result = db.conn.execute(
            "SELECT id, name, created_at, updated_at FROM notebook_sessions ORDER BY updated_at DESC"
        ).fetchall()
        return {"data": [{"id": r[0], "name": r[1], "created_at": str(r[2]), "updated_at": str(r[3])} for r in result]}
    except Exception:
        return {"data": []}


@router.post("/sessions")
def create_session(name: str = "未命名笔记"):
    db = get_db()
    db.conn.execute(
        "INSERT INTO notebook_sessions (name, cells) VALUES (?, ?)",
        [name, json.dumps([])]
    )
    sessions = db.conn.execute("SELECT last_insert_rowid()").fetchone()
    return {"id": sessions[0], "name": name}


@router.get("/sessions/{session_id}")
def get_session(session_id: int):
    db = get_db()
    row = db.conn.execute(
        "SELECT id, name, cells FROM notebook_sessions WHERE id = ?", [session_id]
    ).fetchone()
    if not row:
        raise HTTPException(status_code=404, detail="Session not found")
    return {"id": row[0], "name": row[1], "cells": json.loads(row[2])}


@router.put("/sessions/{session_id}")
def save_session(session_id: int, name: str = None, cells: list = None):
    db = get_db()
    updates = []
    params = []
    if name is not None:
        updates.append("name = ?")
        params.append(name)
    if cells is not None:
        updates.append("cells = ?")
        params.append(json.dumps(cells))
    updates.append("updated_at = ?")
    params.append(datetime.now().isoformat())
    params.append(session_id)
    db.conn.execute(
        f"UPDATE notebook_sessions SET {','.join(updates)} WHERE id = ?",
        params
    )
    return {"ok": True}


@router.delete("/sessions/{session_id}")
def delete_session(session_id: int):
    db = get_db()
    db.conn.execute("DELETE FROM notebook_sessions WHERE id = ?", [session_id])
    return {"ok": True}
```

- [ ] **Step 2: 初始化 notebook_sessions 表（修改 datahub.py）**

Modify: `engine/datahub.py` — 在 `_init_schema()` 末尾添加：

```python
self.conn.execute("""
    CREATE TABLE IF NOT EXISTS notebook_sessions (
        id         INTEGER PRIMARY KEY,
        name       VARCHAR(128),
        cells      JSON,
        created_at TIMESTAMP DEFAULT (datetime('now')),
        updated_at TIMESTAMP DEFAULT (datetime('now'))
    )
""")
```

- [ ] **Step 3: 测试 execute API**

Run: `curl -X POST http://localhost:8000/api/notebook/execute \
  -H "Content-Type: application/json" \
  -d '{"code": "pd.Series([1,2,3]).sum()"}'`
Expected: `{"type":"text","data":"6",...}`

Run: `curl -X POST http://localhost:8000/api/notebook/execute \
  -H "Content-Type: application/json" \
  -d '{"code": "get_data(\"600000.SH\", \"20240101\", \"20240501\")"}'`
Expected: `{"type":"dataframe","data":[...],"shape":[...],"columns":[...]}`

---

## Task 4: /api/backtest 回测 API

**Files:**
- Create: `backend/api/backtest.py`

- [ ] **Step 1: 创建 backend/api/backtest.py**

```python
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
        fn = ns["signal"]
        return lambda df: df  # fallback
    raise ValueError("策略代码必须定义 signal_fn(df) 函数")


@router.post("/run")
def run_backtest(req: BacktestRunRequest):
    try:
        strategy_fn = _build_strategy_fn(req.strategy_code)
    except Exception as e:
        raise HTTPException(status_code=400, detail=f"策略编译错误: {e}")

    db = get_db()
    engine = BacktestEngine(db=db)

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
```

- [ ] **Step 2: 测试 backtest API**

Run: `curl -X POST http://localhost:8000/api/backtest/run \
  -H "Content-Type: application/json" \
  -d '{
    "code": "600000.SH",
    "strategy_code": "def signal_fn(df):\n    df[\"ma5\"] = df[\"close\"].rolling(5).mean()\n    df[\"ma20\"] = df[\"close\"].rolling(20).mean()\n    df[\"signal\"] = 0\n    df.loc[df[\"ma5\"] > df[\"ma20\"], \"signal\"] = 1\n    df.loc[df[\"ma5\"] < df[\"ma20\"], \"signal\"] = -1\n    return df",
    "start_date": "20240101",
    "end_date": "20250501",
    "strategy_name": "MA Cross"
  }'`
Expected: JSON with backtest result keys (total_return, sharpe_ratio, equity_curve, ...)

---

## Task 5: React 前端脚手架

**Files:**
- Create: `frontend/package.json`
- Create: `frontend/vite.config.ts`
- Create: `frontend/index.html`
- Create: `frontend/src/main.tsx`
- Create: `frontend/src/App.tsx`

- [ ] **Step 1: 创建 frontend/package.json**

```json
{
  "name": "alphabase-web",
  "version": "0.1.0",
  "private": true,
  "type": "module",
  "scripts": {
    "dev": "vite",
    "build": "tsc && vite build",
    "preview": "vite preview"
  },
  "dependencies": {
    "react": "^18.3.1",
    "react-dom": "^18.3.1",
    "react-router-dom": "^6.28.0",
    "antd": "^5.22.0",
    "axios": "^1.7.0",
    "@ant-design/icons": "^5.5.0",
    "echarts": "^5.5.0",
    "echarts-for-react": "^3.0.2"
  },
  "devDependencies": {
    "@types/react": "^18.3.0",
    "@types/react-dom": "^18.3.0",
    "@vitejs/plugin-react": "^4.3.0",
    "typescript": "^5.6.0",
    "vite": "^5.4.0"
  }
}
```

- [ ] **Step 2: 创建 frontend/vite.config.ts**

```typescript
import { defineConfig } from "vite";
import react from "@vitejs/plugin-react";

export default defineConfig({
  plugins: [react()],
  server: {
    port: 5173,
    proxy: {
      "/api": {
        target: "http://localhost:8000",
        changeOrigin: true,
      },
    },
  },
});
```

- [ ] **Step 3: 创建 frontend/index.html**

```html
<!DOCTYPE html>
<html lang="zh-CN">
  <head>
    <meta charset="UTF-8" />
    <title>AlphaBase Web</title>
  </head>
  <body>
    <div id="root"></div>
    <script type="module" src="/src/main.tsx"></script>
  </body>
</html>
```

- [ ] **Step 4: 创建 frontend/src/main.tsx**

```typescript
import React from "react";
import ReactDOM from "react-dom/client";
import { BrowserRouter } from "react-router-dom";
import { ConfigProvider } from "antd";
import zhCN from "antd/locale/zh_CN";
import App from "./App";

ReactDOM.createRoot(document.getElementById("root")!).render(
  <React.StrictMode>
    <ConfigProvider locale={zhCN}>
      <BrowserRouter>
        <App />
      </BrowserRouter>
    </ConfigProvider>
  </React.StrictMode>
);
```

- [ ] **Step 5: 创建 frontend/src/App.tsx（路由框架）**

```typescript
import { Routes, Route, Navigate } from "react-router-dom";
import { Layout, Menu } from "antd";
import { useNavigate, useLocation } from "react-router-dom";
import Research from "./pages/Research";
import BacktestReport from "./pages/BacktestReport";
import Data from "./pages/Data";
import Settings from "./pages/Settings";

const { Header, Sider, Content } = Layout;

function App() {
  const navigate = useNavigate();
  const location = useLocation();

  const menuItems = [
    { key: "/research", label: "研究" },
    { key: "/backtest", label: "回测报告" },
    { key: "/data", label: "数据" },
    { key: "/settings", label: "设置" },
  ];

  return (
    <Layout style={{ minHeight: "100vh" }}>
      <Header style={{ color: "white", fontSize: 18, paddingLeft: 16 }}>
        AlphaBase Web
      </Header>
      <Layout>
        <Sider width={180}>
          <Menu
            mode="inline"
            selectedKeys={[location.pathname]}
            items={menuItems}
            onClick={({ key }) => navigate(key)}
            style={{ height: "100%" }}
          />
        </Sider>
        <Content style={{ padding: 16 }}>
          <Routes>
            <Route path="/" element={<Navigate to="/research" replace />} />
            <Route path="/research" element={<Research />} />
            <Route path="/backtest" element={<BacktestReport />} />
            <Route path="/data" element={<Data />} />
            <Route path="/settings" element={<Settings />} />
          </Routes>
        </Content>
      </Layout>
    </Layout>
  );
}

export default App;
```

- [ ] **Step 6: 创建前端页面占位文件（4个空页面）**

Create: `frontend/src/pages/Research.tsx`
```typescript
export default function Research() { return <div>研究页面</div>; }
```

Create: `frontend/src/pages/BacktestReport.tsx`
```typescript
export default function BacktestReport() { return <div>回测报告</div>; }
```

Create: `frontend/src/pages/Data.tsx`
```typescript
export default function Data() { return <div>数据管理</div>; }
```

Create: `frontend/src/pages/Settings.tsx`
```typescript
export default function Settings() { return <div>设置</div>; }
```

- [ ] **Step 7: 安装依赖并验证前端可运行**

Run: `cd /home/echo/alphabase/frontend && npm install`
Run: `npm run dev` (run in background, check it starts without error)

---

## Task 6: API 调用层

**Files:**
- Create: `frontend/src/api/notebook.ts`
- Create: `frontend/src/api/backtest.ts`
- Create: `frontend/src/api/data.ts`
- Create: `frontend/src/api/factors.ts`

- [ ] **Step 1: 创建 frontend/src/api/notebook.ts**

```typescript
import axios from "axios";

const client = axios.create({ baseURL: "/api/notebook" });

export interface CellResult {
  type: "dataframe" | "text" | "error" | "chart";
  data: any;
  shape?: [number, number];
  columns?: string[];
  stdout: string;
}

export interface Session {
  id: number;
  name: string;
  cells: CellData[];
  created_at: string;
  updated_at: string;
}

export interface CellData {
  id: string;
  type: "code";
  code: string;
  result?: CellResult;
}

export const notebookApi = {
  execute: (code: string) =>
    client.post<CellResult>("/execute", { code }),

  listSessions: () =>
    client.get<{ data: Session[] }>("/sessions"),

  createSession: (name: string) =>
    client.post<{ id: number; name: string }>("/sessions", null, {
      params: { name },
    }),

  getSession: (id: number) =>
    client.get<Session>(`/sessions/${id}`),

  saveSession: (id: number, data: { name?: string; cells?: CellData[] }) =>
    client.put(`/sessions/${id}`, null, { params: data }),

  deleteSession: (id: number) =>
    client.delete(`/sessions/${id}`),
};
```

- [ ] **Step 2: 创建 frontend/src/api/backtest.ts**

```typescript
import axios from "axios";

const client = axios.create({ baseURL: "/api/backtest" });

export interface BacktestResult {
  strategy_name: string;
  code: string;
  start_date: string;
  end_date: string;
  initial_capital: number;
  final_capital: number;
  total_return: number;
  annual_return: number;
  benchmark_return: number;
  alpha: number;
  max_drawdown: number;
  max_drawdown_pct: number;
  sharpe_ratio: number;
  sortino_ratio: number;
  calmar_ratio: number;
  beta: number;
  total_trades: number;
  win_rate: number;
  profit_loss_ratio: number;
  equity_curve: { ts: string; capital: number }[];
  trades: any[];
  monthly_returns: { year: string; month: string; ret: number }[];
}

export const backtestApi = {
  run: (params: {
    code: string;
    strategy_code: string;
    start_date: string;
    end_date: string;
    initial_capital?: number;
    strategy_name?: string;
    freq?: string;
  }) => client.post<BacktestResult>("/run", params),
};
```

- [ ] **Step 3: 创建 frontend/src/api/data.ts**

```typescript
import axios from "axios";

const client = axios.create({ baseURL: "/api/data" });

export const dataApi = {
  getKline: (params: {
    code: string;
    freq?: string;
    start?: string;
    end?: string;
    limit?: number;
  }) => client.get<{ code: string; data: any[]; total: number }>("/kline", { params }),

  getStocks: () =>
    client.get<{ data: { code: string; name: string }[] }>("/stocks"),

  saveKline: (params: {
    code: string;
    freq?: string;
    start?: string;
    end?: string;
    adjust?: string;
  }) => client.post("/kline/save", params),
};
```

- [ ] **Step 4: 创建 frontend/src/api/factors.ts**

```typescript
import axios from "axios";

const client = axios.create({ baseURL: "/api/factors" });

export const factorsApi = {
  list: () => client.get("/list"),
  compute: (params: { code: string; factor_name: string; freq?: string }) =>
    client.post("/compute", params),
  delete: (id: number) => client.delete(`/${id}`),
};
```

- [ ] **Step 5: 创建 frontend/tsconfig.json**

```json
{
  "compilerOptions": {
    "target": "ES2020",
    "useDefineForClassFields": true,
    "lib": ["ES2020", "DOM", "DOM.Iterable"],
    "module": "ESNext",
    "skipLibCheck": true,
    "moduleResolution": "bundler",
    "allowImportingTsExtensions": true,
    "resolveJsonModule": true,
    "isolatedModules": true,
    "noEmit": true,
    "jsx": "react-jsx",
    "strict": false,
    "noUnusedLocals": false,
    "noUnusedParameters": false
  },
  "include": ["src"]
}
```

---

## Task 7: Notebook 研究页面（核心 UI）

**Files:**
- Modify: `frontend/src/pages/Research.tsx`

- [ ] **Step 1: 创建完整的 Research.tsx**

```tsx
import { useState, useEffect, useRef, useCallback } from "react";
import {
  Button, Input, Table, Space, message, Card, Typography, Divider,
  List, Modal, Tooltip, Tag
} from "antd";
import {
  PlayCircleOutlined, PlusOutlined, DeleteOutlined,
  SaveOutlined, FolderOutlined, RightOutlined
} from "@ant-design/icons";
import { notebookApi, CellResult, Session, CellData } from "../api/notebook";

const { Text, Title } = Typography;
const { TextArea } = Input;

// 生成唯一 ID
const uid = () => Math.random().toString(36).slice(2);

export default function Research() {
  const [sessions, setSessions] = useState<Session[]>([]);
  const [activeId, setActiveId] = useState<number | null>(null);
  const [cells, setCells] = useState<CellData[]>([]);
  const [sessionName, setSessionName] = useState("未命名笔记");
  const [loading, setLoading] = useState(false);
  const [executingId, setExecutingId] = useState<string | null>(null);
  const bottomRef = useRef<HTMLDivElement>(null);

  // 加载笔记列表
  const loadSessions = useCallback(async () => {
    const r = await notebookApi.listSessions();
    setSessions(r.data.data);
  }, []);

  useEffect(() => { loadSessions(); }, [loadSessions]);

  // 加载指定笔记
  const loadSession = async (id: number) => {
    const r = await notebookApi.getSession(id);
    setActiveId(id);
    setCells(r.data.cells?.length ? r.data.cells : []);
    setSessionName(r.data.name);
  };

  // 新建笔记
  const createSession = async () => {
    const r = await notebookApi.createSession("新笔记 " + new Date().toLocaleTimeString());
    await loadSessions();
    loadSession(r.data.id);
  };

  // 保存笔记
  const saveSession = async () => {
    if (!activeId) return;
    await notebookApi.saveSession(activeId, { name: sessionName, cells });
    message.success("已保存");
  };

  // 执行单个 Cell
  const executeCell = async (cellId: string, code: string) => {
    setExecutingId(cellId);
    try {
      const r = await notebookApi.execute(code);
      setCells(prev =>
        prev.map(c => c.id === cellId ? { ...c, result: r.data } : c)
      );
    } catch (e: any) {
      setCells(prev =>
        prev.map(c => c.id === cellId
          ? { ...c, result: { type: "error", data: e.message, stdout: "" } as CellResult }
          : c
        )
      );
    } finally {
      setExecutingId(null);
      setTimeout(() => bottomRef.current?.scrollIntoView({ behavior: "smooth" }), 100);
    }
  };

  // 添加新 Cell
  const addCell = (afterId?: string, code = "") => {
    const cell: CellData = { id: uid(), type: "code", code };
    setCells(prev => {
      if (!afterId) return [...prev, cell];
      const idx = prev.findIndex(c => c.id === afterId);
      return [...prev.slice(0, idx + 1), cell, ...prev.slice(idx + 1)];
    });
  };

  // 删除 Cell
  const deleteCell = (cellId: string) => {
    setCells(prev => prev.filter(c => c.id !== cellId));
  };

  // 更新 Cell 代码
  const updateCellCode = (cellId: string, code: string) => {
    setCells(prev => prev.map(c => c.id === cellId ? { ...c, code } : c));
  };

  // 渲染结果
  const renderResult = (result?: CellResult) => {
    if (!result) return null;
    if (result.type === "dataframe") {
      const cols = (result.columns || []).map((k: string) => ({
        title: k, dataIndex: k, key: k, width: 120,
        ellipsis: true,
        render: (v: any) => String(v ?? ""),
      }));
      const data = (result.data as any[]).map((row, i) => ({ key: i, ...row }));
      return (
        <div>
          <Space style={{ marginBottom: 4 }}>
            <Text type="secondary" style={{ fontSize: 12 }}>
              {result.shape && `(${result.shape[0]} rows × ${result.shape[1]} cols)`}
            </Text>
          </Space>
          <Table size="small" columns={cols} dataSource={data}
            pagination={{ pageSize: 10 }} scroll={{ x: true }}
            style={{ maxHeight: 300, overflow: "auto" }} />
        </div>
      );
    }
    if (result.type === "chart") {
      return <img src={result.data} style={{ maxWidth: "100%" }} />;
    }
    if (result.type === "error") {
      return <pre style={{ color: "#ff6b6b", fontSize: 12 }}>{result.data}</pre>;
    }
    return <pre style={{ fontSize: 13, color: "#e0e0e0" }}>{result.data}</pre>;
  };

  return (
    <div style={{ display: "flex", height: "calc(100vh - 100px)" }}>
      {/* 左侧：笔记列表 */}
      <div style={{ width: 200, borderRight: "1px solid #333", padding: 8 }}>
        <Button icon={<PlusOutlined />} onClick={createSession} block style={{ marginBottom: 8 }}>
          新建笔记
        </Button>
        <List
          size="small"
          dataSource={sessions}
          rowKey="id"
          renderItem={(s) => (
            <List.Item
              style={{ cursor: "pointer", padding: "4px 8px" }}
              onClick={() => loadSession(s.id)}
            >
              <Text ellipsis style={{ fontSize: 12 }}>{s.name}</Text>
            </List.Item>
          )}
        />
      </div>

      {/* 右侧：Notebook 编辑区 */}
      <div style={{ flex: 1, overflow: "auto", padding: "0 16px" }}>
        {/* 工具栏 */}
        <div style={{ display: "flex", alignItems: "center", gap: 8, padding: "8px 0", borderBottom: "1px solid #333", marginBottom: 16 }}>
          <Input
            value={sessionName}
            onChange={e => setSessionName(e.target.value)}
            style={{ width: 240 }}
            size="small"
          />
          <Button size="small" icon={<SaveOutlined />} onClick={saveSession}>保存</Button>
          <Button size="small" icon={<PlusOutlined />} onClick={() => addCell()}>+ Cell</Button>
        </div>

        {/* Cells */}
        {cells.map((cell, idx) => (
          <Card
            key={cell.id}
            size="small"
            style={{ marginBottom: 12, background: "#1e1e1e", border: "1px solid #333" }}
            bodyStyle={{ padding: 0 }}
          >
            <div style={{ display: "flex", alignItems: "flex-start" }}>
              {/* 行号区 */}
              <div style={{ width: 32, padding: "8px 4px", textAlign: "right", color: "#666", fontSize: 12, userSelect: "none" }}>
                {idx + 1}
              </div>
              {/* 代码区 */}
              <TextArea
                value={cell.code}
                onChange={e => updateCellCode(cell.id, e.target.value)}
                onPressEnter={e => {
                  if (e.ctrlKey || e.metaKey) executeCell(cell.id, cell.code);
                }}
                style={{
                  flex: 1, background: "transparent", border: "none",
                  color: "#e0e0e0", fontFamily: "Consolas, monospace", fontSize: 13,
                  resize: "none", minHeight: 60, padding: "8px",
                }}
                autoSize={{ minRows: 2, maxRows: 10 }}
              />
              {/* 操作按钮 */}
              <div style={{ padding: "4px 8px", display: "flex", flexDirection: "column", gap: 4 }}>
                <Tooltip title="执行 (Ctrl+Enter)">
                  <Button
                    size="small" type="text" icon={<PlayCircleOutlined />}
                    loading={executingId === cell.id}
                    onClick={() => executeCell(cell.id, cell.code)}
                  />
                </Tooltip>
                <Tooltip title="下方添加 Cell">
                  <Button size="small" type="text" icon={<PlusOutlined />}
                    onClick={() => addCell(cell.id)} />
                </Tooltip>
                <Tooltip title="删除">
                  <Button size="small" type="text" icon={<DeleteOutlined />}
                    onClick={() => deleteCell(cell.id)} danger />
                </Tooltip>
              </div>
            </div>
            {/* 结果区 */}
            {cell.result && (
              <div style={{ borderTop: "1px solid #333", padding: "8px 12px", background: "#111" }}>
                {renderResult(cell.result)}
              </div>
            )}
          </Card>
        ))}

        {/* 底部添加 Cell */}
        {cells.length === 0 && (
          <Button icon={<PlusOutlined />} onClick={() => addCell()}>
            添加第一个 Cell
          </Button>
        )}
        <div ref={bottomRef} />
      </div>
    </div>
  );
}
```

- [ ] **Step 2: 更新 App.tsx 添加全局样式**

Modify: `frontend/src/App.tsx` — 在文件顶部添加 CSS：

```typescript
// 在 import 后添加：
// 全局暗色主题
const darkTheme: React.CSSProperties = {
  backgroundColor: "#141414",
  color: "#e0e0e0",
};
```

在 App 组件 return 的最外层 div 添加 `style={{ minHeight: "100vh", backgroundColor: "#141414", color: "#e0e0e0" }}`：

```tsx
<div style={{ minHeight: "100vh", backgroundColor: "#141414", color: "#e0e0e0" }}>
  <Layout ...>
    ...
  </Layout>
</div>
```

- [ ] **Step 3: 验证 Research 页面**

Run: `npm run dev` → 浏览器打开 http://localhost:5173/research
Expected: 左侧笔记列表 + 右侧 Cell 编辑区，可执行代码并看到 DataFrame 渲染

---

## Task 8: 回测结果渲染组件

**Files:**
- Create: `frontend/src/components/BacktestChart.tsx`

- [ ] **Step 1: 创建 BacktestChart.tsx**

```tsx
import ReactECharts from "echarts-for-react";

export interface EquityItem { ts: string; capital: number; }
export interface TradeItem { date: string; direction: string; price: number; qty: number; pnl: number; }

export function EquityCurve({ data }: { data: EquityItem[] }) {
  const option = {
    backgroundColor: "#1e1e1e",
    title: { text: "权益曲线", textStyle: { color: "#e0e0e0", fontSize: 14 } },
    tooltip: { trigger: "axis" },
    grid: { left: 50, right: 16, top: 40, bottom: 30 },
    xAxis: {
      type: "category", data: data.map(d => d.ts),
      axisLine: { lineStyle: { color: "#444" } },
      axisLabel: { color: "#888", fontSize: 10 },
    },
    yAxis: {
      type: "value", axisLine: { lineStyle: { color: "#444" } },
      axisLabel: { color: "#888" }, splitLine: { lineStyle: { color: "#2a2a2a" } },
    },
    series: [{
      data: data.map(d => d.capital),
      type: "line", smooth: true,
      lineStyle: { color: "#4a9eff", width: 1.5 },
      areaStyle: { color: { type: "linear", x: 0, y: 0, x2: 0, y2: 1,
        colorStops: [{ offset: 0, color: "#4a9eff44" }, { offset: 1, color: "#4a9eff00" }] } },
      symbol: "none",
    }],
  };
  return <ReactECharts option={option} style={{ height: 240 }} />;
}

export function TradeMarkers({ data, prices }: { data: TradeItem[]; prices: string[] }) {
  const buyTimes = data.filter(t => t.direction === "buy").map(t => t.date);
  const sellTimes = data.filter(t => t.direction === "sell").map(t => t.date);

  const option = {
    backgroundColor: "#1e1e1e",
    title: { text: "交易标记", textStyle: { color: "#e0e0e0", fontSize: 14 } },
    tooltip: { trigger: "axis" },
    grid: { left: 50, right: 16, top: 40, bottom: 30 },
    xAxis: { type: "category", data: prices,
      axisLine: { lineStyle: { color: "#444" } },
      axisLabel: { color: "#888", fontSize: 10 } },
    yAxis: { type: "value", axisLine: { lineStyle: { color: "#444" } },
      axisLabel: { color: "#888" }, splitLine: { lineStyle: { color: "#2a2a2a" } } },
    series: [
      { data: buyTimes.map(t => [t, 0]), type: "scatter", symbolSize: 8, itemStyle: { color: "#51cf66" } },
      { data: sellTimes.map(t => [t, 0]), type: "scatter", symbolSize: 8, itemStyle: { color: "#ff6b6b" } },
    ],
  };
  return <ReactECharts option={option} style={{ height: 200 }} />;
}
```

- [ ] **Step 2: 在 Research 中集成回测内嵌结果**

Modify: `frontend/src/pages/Research.tsx` — 在 renderResult 函数中处理 backtest 类型。

在 `CellResult` 接口添加：
```typescript
export interface BacktestResult {
  strategy_name: string; total_return: number; annual_return: number;
  sharpe_ratio: number; max_drawdown_pct: number; win_rate: number;
  equity_curve: EquityItem[]; trades: TradeItem[];
}
```

添加新渲染分支：
```typescript
if (result.type === "backtest") {
  const r = result.data as BacktestResult;
  return (
    <div>
      <EquityCurve data={r.equity_curve} />
      {/* 简单绩效指标 */}
      <div style={{ display: "grid", gridTemplateColumns: "repeat(4, 1fr)", gap: 8, margin: "8px 0" }}>
        {[
          ["总收益", `${r.total_return?.toFixed(2)}%`],
          ["年化收益", `${r.annual_return?.toFixed(2)}%`],
          ["夏普比率", String(r.sharpe_ratio ?? 0)],
          ["最大回撤", `${r.max_drawdown_pct?.toFixed(2)}%`],
        ].map(([label, val]) => (
          <div key={label} style={{ background: "#252525", padding: "6px 10px", borderRadius: 4 }}>
            <div style={{ fontSize: 11, color: "#888" }}>{label}</div>
            <div style={{ fontSize: 15, color: "#4a9eff" }}>{val}</div>
          </div>
        ))}
      </div>
      {/* 交易记录 */}
      {r.trades?.length > 0 && (
        <Table
          size="small"
          dataSource={r.trades.map((t, i) => ({ key: i, ...t }))}
          columns={[
            { title: "日期", dataIndex: "date", width: 100 },
            { title: "方向", dataIndex: "direction", width: 60,
              render: d => d === "buy" ? "买入" : "卖出" },
            { title: "价格", dataIndex: "price", width: 80 },
            { title: "数量", dataIndex: "qty", width: 80 },
            { title: "盈亏", dataIndex: "pnl",
              render: v => <span style={{ color: v >= 0 ? "#51cf66" : "#ff6b6b" }}>{v}</span> },
          ]}
          pagination={{ pageSize: 5 }}
        />
      )}
    </div>
  );
}
```

---

## Task 9: 数据管理页面

**Files:**
- Modify: `frontend/src/pages/Data.tsx`

- [ ] **Step 1: 实现 Data.tsx**

```tsx
import { useState } from "react";
import { Table, Button, Space, message, Tag, Input, Form, Modal, Select } from "antd";
import { dataApi } from "../api/data";

export default function Data() {
  const [loading, setLoading] = useState(false);
  const [stockList, setStockList] = useState<any[]>([]);
  const [selected, setSelected] = useState<string[]>([]);
  const [modalOpen, setModalOpen] = useState(false);
  const [form] = Form.useForm();

  const loadStocks = async () => {
    setLoading(true);
    try {
      const r = await dataApi.getStocks();
      setStockList(r.data.data || []);
    } finally {
      setLoading(false);
    }
  };

  const fetchAndSave = async (values: any) => {
    try {
      const r = await dataApi.saveKline({
        code: values.code,
        start: values.start,
        end: values.end,
        freq: values.freq,
      });
      message.success(`已保存 ${r.data.saved} 条数据`);
    } catch (e: any) {
      message.error("获取数据失败: " + (e.response?.data?.detail || e.message));
    }
  };

  const columns = [
    { title: "代码", dataIndex: "code", width: 100 },
    { title: "名称", dataIndex: "name", width: 120 },
  ];

  return (
    <div>
      <Space style={{ marginBottom: 16 }}>
        <Button onClick={loadStocks}>加载股票列表</Button>
        <Button type="primary" onClick={() => setModalOpen(true)}>下载数据</Button>
      </Space>

      <Table
        size="small"
        loading={loading}
        columns={columns}
        dataSource={stockList.map(s => ({ ...s, key: s.code }))}
        pagination={{ pageSize: 20 }}
        rowSelection={{
          type: "checkbox",
          onChange: (keys) => setSelected(keys as string[]),
        }}
      />

      <Modal
        title="下载行情数据"
        open={modalOpen}
        onCancel={() => setModalOpen(false)}
        onOk={() => {
          form.validateFields().then(fetchAndSave).then(() => setModalOpen(false));
        }}
      >
        <Form form={form} layout="vertical">
          <Form.Item name="code" label="股票代码" rules={[{ required: true }]}>
            <Input placeholder="如 600000.SH" />
          </Form.Item>
          <Form.Item name="freq" label="频率" initialValue="day">
            <Select options={[
              { value: "day", label: "日线" },
              { value: "1min", label: "1分钟" },
              { value: "5min", label: "5分钟" },
              { value: "60min", label: "60分钟" },
            ]} />
          </Form.Item>
          <Form.Item name="start" label="开始日期" rules={[{ required: true }]}>
            <Input placeholder="YYYYMMDD 如 20240101" />
          </Form.Item>
          <Form.Item name="end" label="结束日期">
            <Input placeholder="YYYYMMDD 如 20250501" />
          </Form.Item>
        </Form>
      </Modal>
    </div>
  );
}
```

---

## Task 10: 笔记持久化（保存时自动落库）

此任务在 Task 7 的 `saveSession` 函数中已实现，验证即可。

- [ ] **Step 1: 验证持久化**

1. 在 Research 页面创建一个新笔记
2. 添加一个 Cell，执行 `pd.Series([1,2,3])`
3. 点击"保存"
4. 刷新页面，笔记应保留

---

## Task 11: 端到端验证（验收测试）

- [ ] **Step 1: 启动后端**

Run: `cd /home/echo/alphabase && uvicorn backend.main:app --port 8000 --reload`

- [ ] **Step 2: 启动前端**

Run: `cd /home/echo/alphabase/frontend && npm run dev`

- [ ] **Step 3: 验收清单检查**

在浏览器中按顺序执行以下操作：

1. 打开 http://localhost:5173/research
   - [ ] 左侧笔记列表显示正常
   - [ ] 点击"新建笔记"，左侧出现新笔记
   - [ ] 输入代码 `pd.Series([1,2,3]).sum()`，点击执行
   - [ ] 看到结果 `6`

2. 输入 `get_data("600000.SH", "20240101", "20250501")`
   - [ ] 返回 DataFrame 并正确渲染为表格

3. 输入以下回测策略并执行：
   ```python
   def signal_fn(df):
       df["ma5"] = df["close"].rolling(5).mean()
       df["ma20"] = df["close"].rolling(20).mean()
       df["signal"] = 0
       df.loc[df["ma5"] > df["ma20"], "signal"] = 1
       df.loc[df["ma5"] < df["ma20"], "signal"] = -1
       return df
   ```
   - [ ] 看到绩效指标（总收益/夏普/回撤等）

4. 点击保存，刷新页面
   - [ ] 笔记和数据不丢失

5. 打开 http://localhost:5173/data
   - [ ] 可加载股票列表
   - [ ] 可下载指定股票数据

---

## 自检清单

- [ ] spec 中每个要求都有对应 Task 覆盖
- [ ] 无 TBD / TODO / placeholder 代码
- [ ] Task 间类型一致（如 `BacktestResult` 字段名一致）
- [ ] 前端 API 路径与后端路由匹配