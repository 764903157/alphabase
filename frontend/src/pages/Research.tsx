import { useState, useEffect, useRef, useCallback } from "react";
import {
  Button, Input, Table, message, Card, Typography, Divider,
  List, Tooltip, Space
} from "antd";
import {
  PlayCircleOutlined, PlusOutlined, DeleteOutlined,
  SaveOutlined, LoadingOutlined
} from "@ant-design/icons";
import { notebookApi, CellResult, Session, CellData } from "../api/notebook";
import { EquityCurve, BacktestMetrics, TradeTable } from "../components/BacktestChart";
import { backtestApi } from "../api/backtest";

const { Text } = Typography;
const { TextArea } = Input;

const uid = () => Math.random().toString(36).slice(2);

export default function Research() {
  const [sessions, setSessions] = useState<Session[]>([]);
  const [activeId, setActiveId] = useState<number | null>(null);
  const [cells, setCells] = useState<CellData[]>([]);
  const [sessionName, setSessionName] = useState("未命名笔记");
  const [executingId, setExecutingId] = useState<string | null>(null);
  const [loadingSessions, setLoadingSessions] = useState(false);
  const bottomRef = useRef<HTMLDivElement>(null);

  const loadSessions = useCallback(async () => {
    setLoadingSessions(true);
    try {
      const r = await notebookApi.listSessions();
      setSessions(r.data.data || []);
    } catch {
      message.error("加载笔记列表失败");
    } finally {
      setLoadingSessions(false);
    }
  }, []);

  useEffect(() => { loadSessions(); }, [loadSessions]);

  const loadSession = async (id: number) => {
    try {
      const r = await notebookApi.getSession(id);
      setActiveId(id);
      setCells(r.data.cells?.length ? r.data.cells : []);
      setSessionName(r.data.name);
    } catch (e: any) { message.error("加载笔记失败"); }
  };

  const createSession = async () => {
    try {
      const r = await notebookApi.createSession("新笔记 " + new Date().toLocaleTimeString());
      await loadSessions();
      loadSession(r.data.id);
    } catch (e: any) { message.error("创建笔记失败"); }
  };

  const saveSession = async () => {
    if (!activeId) return;
    try {
      await notebookApi.saveSession(activeId, { name: sessionName, cells });
      message.success("已保存");
    } catch { message.error("保存失败"); }
  };

  const executeCell = async (cellId: string, code: string) => {
    if (!code.trim()) return;
    setExecutingId(cellId);
    try {
      const r = await notebookApi.execute(code);
      setCells(prev => prev.map(c => c.id === cellId ? { ...c, result: r.data } : c));
      // Auto-save session after execution
      if (activeId) {
        notebookApi.saveSession(activeId, { cells }).catch(() => {});
      }
    } catch (e: any) {
      setCells(prev => prev.map(c => c.id === cellId ? { ...c, result: { type: "error", data: String(e?.message || e), stdout: "" } as CellResult } : c));
    } finally {
      setExecutingId(null);
      setTimeout(() => bottomRef.current?.scrollIntoView({ behavior: "smooth" }), 50);
    }
  };

  const addCell = (afterId?: string, code = "") => {
    const cell: CellData = { id: uid(), type: "code", code };
    setCells(prev => {
      if (!afterId) return [...prev, cell];
      const idx = prev.findIndex(c => c.id === afterId);
      return [...prev.slice(0, idx + 1), cell, ...prev.slice(idx + 1)];
    });
  };

  const deleteCell = (cellId: string) => setCells(prev => prev.filter(c => c.id !== cellId));
  const updateCellCode = (cellId: string, code: string) => setCells(prev => prev.map(c => c.id === cellId ? { ...c, code } : c));

  const renderResult = (result?: CellResult) => {
    if (!result) return null;
    if (result.type === "dataframe") {
      const cols = (result.columns || []).map((k: string) => ({
        title: k, dataIndex: k, key: k, width: 120,
        ellipsis: true,
        render: (v: any) => String(v ?? ""),
      }));
      const data = (result.data as any[]).map((row: any, i: number) => ({ key: i, ...row }));
      return (
        <div>
          {result.shape && <Text type="secondary" style={{ fontSize: 12, display: "block", marginBottom: 4 }}>
            {result.shape[0]} rows × {result.shape[1]} cols
          </Text>}
          <Table size="small" columns={cols} dataSource={data}
            pagination={{ pageSize: 10 }} scroll={{ x: true }}
            style={{ maxHeight: 300, overflow: "auto" }} />
        </div>
      );
    }
    if (result.type === "chart") {
      return <img src={result.data} style={{ maxWidth: "100%" }} alt="chart" />;
    }
    if (result.type === "error") {
      return <pre style={{ color: "#ff6b6b", fontSize: 12, margin: 0 }}>{result.data}</pre>;
    }
    return <pre style={{ fontSize: 13, margin: 0, color: "#e0e0e0" }}>{String(result.data)}</pre>;
  };

  const sidebarWidth = 200;

  return (
    <div style={{ display: "flex", height: "calc(100vh - 120px)", gap: 0 }}>
      {/* Left sidebar */}
      <div style={{ width: sidebarWidth, borderRight: "1px solid #333", padding: "8px 8px 8px 0", flexShrink: 0, overflow: "auto" }}>
        <Button
          icon={<PlusOutlined />}
          onClick={createSession}
          block style={{ marginBottom: 8 }}
          size="small"
          loading={loadingSessions}
        >
          新建笔记
        </Button>
        <List
          size="small"
          dataSource={sessions}
          rowKey="id"
          locale={{ emptyText: "暂无笔记" }}
          loading={loadingSessions}
          renderItem={(s) => (
            <List.Item
              style={{
                cursor: "pointer", padding: "4px 8px",
                background: activeId === s.id ? "#2a2a2a" : "transparent",
                borderRadius: 4, marginBottom: 2,
              }}
              onClick={() => loadSession(s.id)}
            >
              <Text ellipsis style={{ fontSize: 12, color: activeId === s.id ? "#4a9eff" : "#aaa" }}>
                {s.name}
              </Text>
            </List.Item>
          )}
        />
      </div>

      {/* Main area */}
      <div style={{ flex: 1, overflow: "auto", padding: "0 16px" }}>
        {/* Toolbar */}
        <div style={{ display: "flex", alignItems: "center", gap: 8, padding: "8px 0", borderBottom: "1px solid #333", marginBottom: 16 }}>
          <Input
            value={sessionName}
            onChange={e => setSessionName(e.target.value)}
            style={{ width: 240 }}
            size="small"
            placeholder="笔记名称"
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
              {/* Line number */}
              <div style={{
                width: 32, padding: "8px 4px", textAlign: "right",
                color: "#555", fontSize: 12, userSelect: "none", flexShrink: 0,
                fontFamily: "Consolas, monospace",
              }}>
                {idx + 1}
              </div>
              {/* Code textarea */}
              <TextArea
                value={cell.code}
                onChange={e => updateCellCode(cell.id, e.target.value)}
                onKeyDown={e => {
                  if (e.key === "Enter" && (e.ctrlKey || e.metaKey || e.shiftKey)) {
                    e.preventDefault();
                    executeCell(cell.id, cell.code);
                  }
                }}
                style={{
                  flex: 1, background: "transparent", border: "none",
                  color: "#e0e0e0", fontFamily: "Consolas, monospace", fontSize: 13,
                  resize: "none", minHeight: 52, padding: "8px",
                  boxShadow: "none",
                }}
                autoSize={{ minRows: 2, maxRows: 12 }}
              />
              {/* Action buttons */}
              <div style={{ padding: "4px 8px", display: "flex", flexDirection: "column", gap: 2 }}>
                <Tooltip title="执行 (Ctrl+Enter)">
                  <Button
                    size="small" type="text" icon={<PlayCircleOutlined />}
                    loading={executingId === cell.id}
                    onClick={() => executeCell(cell.id, cell.code)}
                    style={{ color: "#51cf66" }}
                  />
                </Tooltip>
                <Tooltip title="下方添加 Cell">
                  <Button size="small" type="text" icon={<PlusOutlined />}
                    onClick={() => addCell(cell.id)} style={{ color: "#888" }} />
                </Tooltip>
                <Tooltip title="删除">
                  <Button size="small" type="text" icon={<DeleteOutlined />}
                    onClick={() => deleteCell(cell.id)} danger style={{ color: "#ff6b6b" }} />
                </Tooltip>
              </div>
            </div>
            {/* Result area */}
            {cell.result && (
              <div style={{ borderTop: "1px solid #2a2a2a", padding: "8px 12px", background: "#111" }}>
                {renderResult(cell.result)}
              </div>
            )}
          </Card>
        ))}

        {cells.length === 0 && activeId && (
          <Button icon={<PlusOutlined />} onClick={() => addCell()}>
            添加第一个 Cell
          </Button>
        )}
        {cells.length === 0 && !activeId && (
          <Text type="secondary">从左侧选择笔记或新建笔记开始</Text>
        )}
        <div ref={bottomRef} />
      </div>
    </div>
  );
}