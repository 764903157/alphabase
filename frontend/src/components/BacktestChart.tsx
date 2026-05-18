import ReactECharts from "echarts-for-react";
import { Table, Typography } from "antd";

const { Text } = Typography;

export interface EquityItem { ts: string; capital: number; }
export interface TradeItem { date: string; direction: string; price: number; qty: number; pnl: number; pnl_pct?: number; amount?: number; commission?: number; }

export interface BacktestResult {
  strategy_name: string;
  code: string;
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
  equity_curve: EquityItem[];
  trades: TradeItem[];
}

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
      type: "value",
      axisLine: { lineStyle: { color: "#444" } },
      axisLabel: { color: "#888" },
      splitLine: { lineStyle: { color: "#2a2a2a" } },
    },
    series: [{
      data: data.map(d => d.capital),
      type: "line", smooth: true,
      lineStyle: { color: "#4a9eff", width: 1.5 },
      areaStyle: {
        color: {
          type: "linear", x: 0, y: 0, x2: 0, y2: 1,
          colorStops: [
            { offset: 0, color: "#4a9eff44" },
            { offset: 1, color: "#4a9eff00" },
          ],
        },
      },
      symbol: "none",
    }],
  };
  return <ReactECharts option={option} style={{ height: 240 }} />;
}

export function TradeMarkers({ trades }: { trades: TradeItem[] }) {
  const buyTimes = trades.filter(t => t.direction === "buy").map(t => [t.date, null]);
  const sellTimes = trades.filter(t => t.direction === "sell").map(t => [t.date, null]);

  const allDates = Array.from(new Set(trades.map(t => t.date))).sort();
  const option = {
    backgroundColor: "#1e1e1e",
    title: { text: "买卖标记", textStyle: { color: "#e0e0e0", fontSize: 14 } },
    tooltip: { trigger: "axis" },
    grid: { left: 50, right: 16, top: 40, bottom: 30 },
    xAxis: { type: "category", data: allDates,
      axisLine: { lineStyle: { color: "#444" } },
      axisLabel: { color: "#888", fontSize: 10 } },
    yAxis: { type: "value", axisLine: { lineStyle: { color: "#444" } },
      axisLabel: { color: "#888" }, splitLine: { lineStyle: { color: "#2a2a2a" } } },
    series: [
      { name: "买入", data: buyTimes, type: "scatter", symbolSize: 10,
        itemStyle: { color: "#51cf66" } },
      { name: "卖出", data: sellTimes, type: "scatter", symbolSize: 10,
        itemStyle: { color: "#ff6b6b" } },
    ],
  };
  return <ReactECharts option={option} style={{ height: 160 }} />;
}

export function BacktestMetrics({ result }: { result: BacktestResult }) {
  const metrics = [
    ["总收益", `${(result.total_return ?? 0).toFixed(2)}%`],
    ["年化收益", `${(result.annual_return ?? 0).toFixed(2)}%`],
    ["夏普比率", (result.sharpe_ratio ?? 0).toFixed(2)],
    ["最大回撤", `${(result.max_drawdown_pct ?? 0).toFixed(2)}%`],
    ["胜率", `${(result.win_rate ?? 0).toFixed(1)}%`],
    ["交易次数", String(result.total_trades ?? 0)],
    ["盈亏比", (result.profit_loss_ratio ?? 0).toFixed(2)],
    ["卡玛比率", (result.calmar_ratio ?? 0).toFixed(2)],
  ];

  return (
    <div style={{ display: "grid", gridTemplateColumns: "repeat(4, 1fr)", gap: 8 }}>
      {metrics.map(([label, val]) => (
        <div key={label} style={{ background: "#1e1e1e", padding: "8px 12px", borderRadius: 4, border: "1px solid #333" }}>
          <div style={{ fontSize: 11, color: "#888", marginBottom: 4 }}>{label}</div>
          <div style={{ fontSize: 15, color: "#4a9eff" }}>{val}</div>
        </div>
      ))}
    </div>
  );
}

export function TradeTable({ trades }: { trades: TradeItem[] }) {
  const columns = [
    { title: "日期", dataIndex: "date", width: 100 },
    { title: "方向", dataIndex: "direction", width: 60,
      render: (d: string) => (
        <span style={{ color: d === "buy" ? "#51cf66" : "#ff6b6b" }}>
          {d === "buy" ? "买入" : "卖出"}
        </span>
      )
    },
    { title: "价格", dataIndex: "price", width: 80 },
    { title: "数量", dataIndex: "qty", width: 80 },
    { title: "盈亏", dataIndex: "pnl", width: 80,
      render: (v: number) => (
        <span style={{ color: (v ?? 0) >= 0 ? "#51cf66" : "#ff6b6b" }}>
          {v?.toFixed(2)}
        </span>
      )
    },
  ];
  const data = trades.map((t, i) => ({ key: i, ...t }));
  return <Table size="small" columns={columns} dataSource={data} pagination={{ pageSize: 10 }} />;
}