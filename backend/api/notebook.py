"""
Notebook 执行引擎 API
POST /api/notebook/execute  ← 执行一段代码，返回结果
GET  /api/notebook/sessions ← 获取笔记列表
POST /api/notebook/sessions ← 创建新笔记
GET  /api/notebook/sessions/{session_id} ← 获取指定笔记
PUT  /api/notebook/sessions/{session_id} ← 保存笔记
DELETE /api/notebook/sessions/{session_id}
"""
from fastapi import APIRouter, HTTPException, Query
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
            val = eval(compile(ast.Expression(body=last_expr), "<expr>", "eval"), ns)
            if isinstance(val, pd.DataFrame):
                result_type = "dataframe"
                # 最多 1000 行
                display_df = val.head(1000)
                result_data = display_df.to_dict(orient="records")
                shape = (len(display_df), len(display_df.columns))
                columns = list(display_df.columns)
            elif isinstance(val, (int, float, str, bool, type(None))):
                result_data = str(val)
            elif isinstance(val, pd.Series):
                # numpy array-like but not a figure
                result_data = str(val)
            elif hasattr(val, "__array__"):
                # matplotlib figure or numpy array - check if it's a Figure
                import matplotlib.figure
                if isinstance(val, matplotlib.figure.Figure):
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
        captured = buffer.getvalue()
        sys.stdout = old_stdout
        return CellResult(
            type="error",
            data=f"{traceback.format_exc()}",
            stdout=captured,
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
def create_session(name: str = Query("未命名笔记")):
    db = get_db()
    result = db.conn.execute(
        "INSERT INTO notebook_sessions (name, cells) VALUES (?, ?) RETURNING id",
        [name, json.dumps([])]
    ).fetchone()
    return {"id": result[0], "name": name}


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
def save_session(session_id: int, name: Optional[str] = Query(None), cells: Optional[list] = Query(None)):
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