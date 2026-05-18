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
    adjust?: string;
  }) => client.post<BacktestResult>("/run", params),
};