"""
AlphaBase 回测结果可视化窗口
基于看海量化风格，扩展以下功能：
1. 收益曲线 + 回撤曲线 + 月度收益热力图
2. 滚动夏普比率
3. 盈亏分布直方图
4. 累计盈亏曲线
5. 因子暴露度分析（可选）
"""

import logging
import sys
import os

log_handler = logging.StreamHandler(sys.stdout)
log_handler.setLevel(logging.ERROR)
logging.getLogger("matplotlib").addHandler(log_handler)
logging.getLogger("matplotlib").setLevel(logging.ERROR)

import matplotlib
matplotlib.use("Qt5Agg")

from PyQt5.QtWidgets import (
    QMainWindow, QWidget, QVBoxLayout, QHBoxLayout,
    QLabel, QTabWidget, QTableWidget, QTableWidgetItem,
    QGroupBox, QSplitter, QGridLayout, QHeaderView,
    QSizePolicy, QFileDialog, QMessageBox, QPushButton,
    QComboBox, QLineEdit, QSpinBox, QCheckBox, QProgressBar,
    QTextEdit
)
from PyQt5.QtCore import Qt, QSettings, QTimer
from PyQt5.QtGui import QPalette, QColor, QIcon, QFont

import matplotlib.pyplot as plt
import matplotlib.patches as mpatches
from matplotlib.backends.backend_qt5agg import FigureCanvasQTAgg as FigureCanvas
from matplotlib.figure import Figure
import matplotlib.dates as mdates
from matplotlib import cm, ticker
import numpy as np
import pandas as pd
from datetime import datetime
from typing import Optional

# 全局深色主题 matplotlib 设置
plt.rcParams["font.sans-serif"] = ["Noto Sans CJK JP", "Microsoft YaHei", "SimHei", "DejaVu Sans"]
plt.rcParams["axes.unicode_minus"] = False
plt.rcParams["font.family"] = "sans-serif"
plt.rcParams["axes.facecolor"] = "#1e1e1e"
plt.rcParams["figure.facecolor"] = "#1e1e1e"
plt.rcParams["axes.edgecolor"] = "#3c3c3c"
plt.rcParams["axes.labelcolor"] = "#e0e0e0"
plt.rcParams["xtick.color"] = "#a0a0a0"
plt.rcParams["ytick.color"] = "#a0a0a0"
plt.rcParams["text.color"] = "#e0e0e0"
plt.rcParams["grid.color"] = "#2a2a2a"
plt.style.use("dark_background")


def _color_pct(pct: float) -> str:
    """收益率正负着色"""
    if pct > 0:
        return "#ff6b6b"
    elif pct < 0:
        return "#51cf66"
    return "#a0a0a0"


def _color_val(val: float, higher_is_better: bool = True) -> str:
    if higher_is_better:
        return "#51cf66" if val > 0 else "#ff6b6b"
    else:
        return "#51cf66" if val < 0 else "#ff6b6b"


class BacktestResultWindow(QMainWindow):
    """
    增强版回测结果窗口
    在看海量化基础上新增：
    - 滚动夏普比率曲线
    - 累计盈亏曲线（叠加买卖点）
    - 月度收益热力图（带标注）
    - 盈亏分布直方图 + 统计信息
    - 交易效率分析（持仓周期 vs 收益散点图）
    - 因子暴露度表格
    """

    def __init__(self, result: "BacktestResult" = None, backtest_dir: str = ""):
        super().__init__()
        self.result = result
        self.backtest_dir = backtest_dir
        self.font_scale = self._detect_screen()

        # 窗口基础设置
        self.setWindowTitle("AlphaBase - 回测结果")
        self._apply_dark_style()
        base_w, base_h = 1600, 1000
        self.resize(int(base_w * self.font_scale), int(base_h * self.font_scale))

        self._init_ui()
        if result:
            self.load_result(result)

    def _detect_screen(self) -> float:
        from PyQt5.QtWidgets import QApplication
        screen = QApplication.desktop().screenGeometry()
        w = screen.width()
        if w >= 3840:
            return 1.8
        elif w >= 2560:
            return 1.4
        elif w >= 1920:
            return 1.0
        return 0.8

    def _apply_dark_style(self):
        fs = self.font_scale
        base_sizes = {k: int(v * fs) for k, v in {"sm": 12, "md": 14, "lg": 16, "xl": 18}.items()}
        self.setStyleSheet(f"""
            QMainWindow, QWidget {{
                background-color: #1a1a1a;
                color: #e0e0e0;
                font-family: "Microsoft YaHei", "SimHei", sans-serif;
                font-size: {base_sizes["md"]}px;
            }}
            QGroupBox {{
                background-color: #252525;
                border: 1px solid #3a3a3a;
                border-radius: 6px;
                margin-top: 8px;
                padding: 6px;
                color: #c0c0c0;
            }}
            QGroupBox::title {{
                subcontrol-origin: margin; left: 10px; padding: 0 4px;
                font-weight: bold; font-size: {base_sizes["lg"]}px;
            }}
            QTabWidget::pane {{
                border: 1px solid #3a3a3a;
                background-color: #1e1e1e;
            }}
            QTabBar::tab {{
                background-color: #2a2a2a; color: #a0a0a0;
                padding: 8px 16px; margin-right: 2px;
                border-top-left-radius: 4px; border-top-right-radius: 4px;
                font-size: {base_sizes["md"]}px;
            }}
            QTabBar::tab:selected {{ background-color: #1e1e1e; border-bottom: 2px solid #4a9eff; color: #fff; }}
            QTabBar::tab:hover {{ background-color: #323232; }}
            QTableWidget {{
                background-color: #222222; alternate-background-color: #282828;
                border: 1px solid #3a3a3a; color: #e0e0e0;
                gridline-color: #333; font-size: {base_sizes["md"]}px;
            }}
            QHeaderView::section {{
                background-color: #2d2d2d; color: #ccc; padding: 6px;
                border: none; border-right: 1px solid #444; border-bottom: 1px solid #444;
                font-weight: bold;
            }}
            QPushButton {{
                background-color: #2a4a7a; color: #fff;
                border: none; border-radius: 4px; padding: 6px 16px;
            }}
            QPushButton:hover {{ background-color: #3a6aaa; }}
            QPushButton:pressed {{ background-color: #1a3a6a; }}
            QLineEdit, QSpinBox, QComboBox {{
                background-color: #2a2a2a; color: #e0e0e0;
                border: 1px solid #3a3a3a; border-radius: 3px; padding: 4px;
            }}
        """)

    def _init_ui(self):
        main = QWidget()
        self.setCentralWidget(main)
        layout = QVBoxLayout()
        layout.setSpacing(8)
        layout.setContentsMargins(8, 8, 8, 8)
        main.setLayout(layout)

        # ── 顶部工具栏 ──
        toolbar = QHBoxLayout()
        self.status_label = QLabel("未加载回测结果")
        self.status_label.setStyleSheet("color: #888; font-size: 13px;")
        self.export_btn = QPushButton("导出报告")
        self.export_btn.clicked.connect(self._export_report)
        self.save_fig_btn = QPushButton("保存图表")
        self.save_fig_btn.clicked.connect(self._save_figures)
        toolbar.addWidget(self.status_label)
        toolbar.addStretch()
        toolbar.addWidget(self.export_btn)
        toolbar.addWidget(self.save_fig_btn)
        layout.addLayout(toolbar)

        # ── 主分割器：指标面板 + 图表 ──
        splitter = QSplitter(Qt.Horizontal)
        splitter.setHandleWidth(2)

        # 左侧：绩效指标面板
        self._build_kpi_panel(splitter)

        # 右侧：主图表区
        self._build_main_chart(splitter)

        splitter.setSizes([350, 1250])
        layout.addWidget(splitter, 1)

        # ── 底部 Tab 区 ──
        self._build_bottom_tabs(layout)

    def _build_kpi_panel(self, parent):
        """左侧 KPI 指标面板"""
        group = QGroupBox("绩效总览")
        grid = QGridLayout()
        grid.setVerticalSpacing(4)
        grid.setHorizontalSpacing(8)
        grid.setContentsMargins(8, 6, 8, 6)

        fs = self.font_scale

        def metric_row(row, label_text, key):
            label = QLabel(label_text)
            label.setStyleSheet(f"color: #888; font-size: {int(13*fs)}px; font-weight: bold;")
            label.setMinimumWidth(int(100 * fs))
            label.setSizePolicy(QSizePolicy.Fixed, QSizePolicy.Preferred)

            val_lbl = QLabel("--")
            val_lbl.setStyleSheet(f"color: #e0e0e0; font-size: {int(13*fs)}px; font-family: Consolas, monospace;")
            val_lbl.setSizePolicy(QSizePolicy.Expanding, QSizePolicy.Preferred)
            val_lbl.setAlignment(Qt.AlignRight | Qt.AlignVCenter)
            self._kpi_labels[key] = val_lbl
            grid.addWidget(label, row, 0, Qt.AlignRight)
            grid.addWidget(val_lbl, row, 1, Qt.AlignLeft)
            return val_lbl

        self._kpi_labels = {}

        metrics = [
            ("策略名称", "strategy_name"),
            ("回测区间", "period"),
            ("初始资金", "initial_capital"),
            ("最终资金", "final_capital"),
            ("总收益率", "total_return"),
            ("年化收益率", "annual_return"),
            ("基准收益率", "benchmark_return"),
            ("超额收益(α)", "alpha"),
            ("最大回撤", "max_drawdown_pct"),
            ("夏普比率", "sharpe_ratio"),
            ("索提诺比率", "sortino_ratio"),
            ("卡玛比率", "calmar_ratio"),
            ("年化波动率", "annual_volatility"),
            ("贝塔", "beta"),
            ("总交易次数", "total_trades"),
            ("胜率", "win_rate"),
            ("盈亏比", "profit_loss_ratio"),
            ("最大单笔盈利", "max_single_profit"),
            ("最大单笔亏损", "max_single_loss"),
            ("日均交易次数", "avg_trades_per_day"),
        ]

        for i, (label_text, key) in enumerate(metrics):
            metric_row(i, label_text, key)

        group.setLayout(grid)
        group.setMaximumWidth(int(360 * fs))
        parent.addWidget(group)

    def _build_main_chart(self, parent):
        """右侧：多行子图（收益曲线、回撤、累计盈亏、月度热力图）"""
        group = QGroupBox("收益曲线 & 回撤分析")
        vbox = QVBoxLayout()
        vbox.setContentsMargins(4, 8, 4, 4)

        # 创建 4 行子图
        fig = Figure(figsize=(14, 10), facecolor="#1e1e1e")
        canvas = FigureCanvas(fig)
        self._main_fig = fig

        # 收益曲线（占 40% 高度）
        self._ax_equity = fig.add_subplot(4, 1, 1)
        # 回撤曲线（占 15%）
        self._ax_drawdown = fig.add_subplot(4, 1, 2, sharex=self._ax_equity)
        # 累计盈亏（占 20%）
        self._ax_cumpnl = fig.add_subplot(4, 1, 3, sharex=self._ax_equity)
        # 月度热力图（占 25%）
        self._ax_monthly = fig.add_subplot(4, 1, 4)

        # 共享 x 轴
        fig.subplots_adjust(hspace=0.25, left=0.06, right=0.96, top=0.94, bottom=0.08)

        vbox.addWidget(canvas)
        group.setLayout(vbox)
        parent.addWidget(group)

    def _build_bottom_tabs(self, layout):
        """底部 Tab：交易记录 / 日收益 / 绩效分析 / 月度分析"""
        tabs = QTabWidget()
        tabs.setStyleSheet(f"""
            QTabWidget::pane {{ border: 1px solid #3a3a3a; background: #1e1e1e; }}
            QTabBar::tab {{ font-size: {int(13*self.font_scale)}px; padding: 6px 14px; }}
        """)

        # Tab 1: 交易记录
        self.trades_table = QTableWidget()
        self.trades_table.setAlternatingRowColors(True)
        self.trades_table.setColumnCount(8)
        self.trades_table.setHorizontalHeaderLabels(
            ["日期", "代码", "方向", "价格", "数量", "金额", "手续费", "盈亏"]
        )
        self.trades_table.horizontalHeader().setSectionResizeMode(QHeaderView.Interactive)
        self.trades_table.verticalHeader().setVisible(False)
        tabs.addTab(self.trades_table, "交易记录")

        # Tab 2: 日收益
        self.daily_table = QTableWidget()
        self.daily_table.setAlternatingRowColors(True)
        self.daily_table.setColumnCount(5)
        self.daily_table.setHorizontalHeaderLabels(
            ["日期", "总资产", "持仓市值", "可用资金", "日收益率"]
        )
        self.daily_table.horizontalHeader().setSectionResizeMode(QHeaderView.Interactive)
        self.daily_table.verticalHeader().setVisible(False)
        tabs.addTab(self.daily_table, "日收益")

        # Tab 3: 绩效分析（多图表）
        perf_widget = QWidget()
        perf_layout = QVBoxLayout()
        perf_layout.setContentsMargins(6, 6, 6, 6)
        perf_layout.setSpacing(8)

        # 左：收益分布直方图 + 滚动夏普
        chart_grid = QSplitter(Qt.Horizontal)

        hist_group = QGroupBox("收益分布直方图")
        hist_vbox = QVBoxLayout()
        fig_h = Figure(figsize=(5, 3.5), facecolor="#1e1e1e")
        hist_canvas = FigureCanvas(fig_h)
        self._ax_hist = fig_h.add_subplot(1, 1, 1)
        hist_vbox.addWidget(hist_canvas)
        hist_group.setLayout(hist_vbox)
        chart_grid.addWidget(hist_group)

        rolling_group = QGroupBox("滚动夏普比率 (20日)")
        rolling_vbox = QVBoxLayout()
        fig_r = Figure(figsize=(5, 3.5), facecolor="#1e1e1e")
        rolling_canvas = FigureCanvas(fig_r)
        self._ax_rolling = fig_r.add_subplot(1, 1, 1)
        rolling_vbox.addWidget(rolling_canvas)
        rolling_group.setLayout(rolling_vbox)
        chart_grid.addWidget(rolling_group)

        # 右：持仓周期 vs 收益散点图
        scatter_group = QGroupBox("持仓周期 vs 单笔收益")
        scatter_vbox = QVBoxLayout()
        fig_s = Figure(figsize=(4.5, 3.5), facecolor="#1e1e1e")
        scatter_canvas = FigureCanvas(fig_s)
        self._ax_scatter = fig_s.add_subplot(1, 1, 1)
        scatter_vbox.addWidget(scatter_canvas)
        scatter_group.setLayout(scatter_vbox)
        chart_grid.addWidget(scatter_group)

        chart_grid.setSizes([400, 400, 360])
        perf_layout.addWidget(chart_grid, 1)
        perf_widget.setLayout(perf_layout)
        tabs.addTab(perf_widget, "绩效分析")

        # Tab 4: 月度分析
        monthly_widget = QWidget()
        monthly_layout = QVBoxLayout()

        # 月度收益热力图（扩展版：含年度对比）
        monthly_fig = Figure(figsize=(12, 4), facecolor="#1e1e1e")
        monthly_canvas = FigureCanvas(monthly_fig)
        self._ax_monthly_table = monthly_fig.add_subplot(1, 1, 1)
        monthly_layout.addWidget(monthly_canvas)
        monthly_widget.setLayout(monthly_layout)
        tabs.addTab(monthly_widget, "月度分析")

        # Tab 5: 信号分析（新增）
        signal_widget = QWidget()
        signal_layout = QVBoxLayout()
        signal_fig = Figure(figsize=(12, 5), facecolor="#1e1e1e")
        signal_canvas = FigureCanvas(signal_fig)
        self._ax_signal = signal_fig.add_subplot(2, 1, 1)
        self._ax_signal_entry = signal_fig.add_subplot(2, 1, 2, sharex=self._ax_signal)
        signal_layout.addWidget(signal_canvas)
        signal_widget.setLayout(signal_layout)
        tabs.addTab(signal_widget, "信号分析")

        layout.addWidget(tabs)

    def load_result(self, result: "BacktestResult"):
        """加载回测结果并渲染所有图表"""
        self.result = result
        self.status_label.setText(f"✅ {result.strategy_name} | {result.code} | {result.start_date} ~ {result.end_date}")

        steps = [
            ("KPI指标", self._render_kpi),
            ("主图表", self._render_main_chart),
            ("交易记录", self._render_trades),
            ("日收益", self._render_daily),
            ("绩效分析", self._render_perf_analysis),
            ("月度分析", self._render_monthly_analysis),
            ("信号分析", self._render_signal_analysis),
        ]
        for name, fn in steps:
            try:
                fn(result)
                print(f"[ResultWindow] ✅ {name} 渲染完成", flush=True)
            except Exception as e:
                import traceback
                traceback.print_exc()
                print(f"[ResultWindow] ❌ {name} 渲染失败: {e}", flush=True)
                self.status_label.setText(f"⚠️ {name}渲染异常: {e}")

    # ──────────────────────────────────────────────
    # 渲染方法
    # ──────────────────────────────────────────────

    def _render_kpi(self, r: "BacktestResult"):
        fs = self.font_scale
        for key, val in [
            ("strategy_name",    r.strategy_name),
            ("period",           f"{r.start_date} ~ {r.end_date}"),
            ("initial_capital",  f"¥ {r.initial_capital:,.0f}"),
            ("final_capital",    f"¥ {r.final_capital:,.0f}"),
            ("total_return",     f"{r.total_return:+.2f}%"),
            ("annual_return",    f"{r.annual_return:+.2f}%"),
            ("benchmark_return", f"{r.benchmark_return:+.2f}%"),
            ("alpha",            f"{r.alpha:+.2f}%"),
            ("max_drawdown_pct", f"{r.max_drawdown_pct:.2f}%"),
            ("sharpe_ratio",     f"{r.sharpe_ratio:.2f}"),
            ("sortino_ratio",    f"{r.sortino_ratio:.2f}"),
            ("calmar_ratio",     f"{r.calmar_ratio:.2f}"),
            ("annual_volatility",f"{r.annual_volatility:.2f}%"),
            ("beta",             f"{r.beta:.2f}"),
            ("total_trades",     str(r.total_trades)),
            ("win_rate",         f"{r.win_rate:.1f}%"),
            ("profit_loss_ratio",f"{r.profit_loss_ratio:.2f}"),
            ("max_single_profit",f"¥ {r.max_single_profit:,.0f}"),
            ("max_single_loss",  f"¥ {r.max_single_loss:,.0f}"),
            ("avg_trades_per_day", f"{r.avg_trades_per_day:.3f}"),
        ]:
            lbl = self._kpi_labels.get(key)
            if lbl:
                color = _color_pct(val) if isinstance(val, float) else "#e0e0e0"
                lbl.setText(str(val))
                lbl.setStyleSheet(f"color: {color}; font-size: {int(13*fs)}px; font-family: Consolas, monospace;")

    def _render_main_chart(self, r: "BacktestResult"):
        if not r.equity_curve:
            return

        ax1 = self._ax_equity
        ax2 = self._ax_drawdown
        ax3 = self._ax_cumpnl
        ax4 = self._ax_monthly

        dates = [e["ts"] for e in r.equity_curve]
        capitals = [e["capital"] for e in r.equity_curve]
        initial = r.initial_capital

        # ── 收益曲线 ──
        ax1.clear()
        ax1.plot(dates, capitals, color="#4a9eff", linewidth=1.5, label="策略")
        ax1.fill_between(dates, initial, capitals, alpha=0.15, color="#4a9eff")
        # 基准线
        if r.daily_returns:
            bench_start = initial
            ax1.axhline(initial, color="#555", linestyle="--", linewidth=0.8, alpha=0.7)
        ax1.set_ylabel("资金(¥)", fontsize=9)
        ax1.set_title(f"{r.strategy_name} 净值曲线  (最终: ¥{capitals[-1]:,.0f}  收益率: {r.total_return:+.2f}%)",
                      fontsize=int(11 * self.font_scale), color="#e0e0e0")
        ax1.tick_params(labelsize=8)
        ax1.grid(True, alpha=0.3)
        ax1.legend(loc="upper left", fontsize=8)

        # ── 回撤曲线 ──
        ax2.clear()
        peak = np.maximum.accumulate(capitals)
        drawdown = [(c - p) / p * 100 for c, p in zip(capitals, peak)]
        ax2.fill_between(dates, drawdown, 0, alpha=0.6, color="#ff6b6b")
        ax2.plot(dates, drawdown, color="#ff6b6b", linewidth=0.8)
        ax2.set_ylabel("回撤%", fontsize=9)
        ax2.tick_params(labelsize=8)
        ax2.grid(True, alpha=0.3)
        ax2.set_title(f"最大回撤: {r.max_drawdown_pct:.2f}%  |  夏普: {r.sharpe_ratio:.2f}  |  索提诺: {r.sortino_ratio:.2f}",
                      fontsize=9, color="#aaa")
        # 标注最大回撤点
        min_idx = np.argmin(drawdown)
        ax2.annotate(f"最大回撤\n{drawdown[min_idx]:.2f}%",
                      xy=(dates[min_idx], drawdown[min_idx]),
                      xytext=(10, -20), textcoords="offset points",
                      fontsize=7, color="#ff6b6b",
                      arrowprops=dict(arrowstyle="->", color="#ff6b6b", lw=0.8))

        # ── 累计盈亏（叠加买卖点） ──
        ax3.clear()
        sells = [t for t in r.trades if t["direction"] == "sell"]
        cumulative = 0.0
        cn_dates, cn_values = [], []
        for t in sells:
            cumulative += t["pnl"]
            cn_dates.append(t["date"])
            cn_values.append(cumulative)
        if cn_dates:
            ax3.plot(cn_dates, cn_values, color="#ffd43b", linewidth=1.5)
            ax3.scatter(cn_dates, cn_values,
                        c=["#51cf66" if v >= 0 else "#ff6b6b" for v in cn_values],
                        s=30, zorder=5, edgecolors="none")
        ax3.axhline(0, color="#555", linestyle="--", linewidth=0.8)
        ax3.set_ylabel("累计盈亏(¥)", fontsize=9)
        ax3.tick_params(labelsize=8)
        ax3.grid(True, alpha=0.3)

        # ── 月度热力图 ──
        ax4.clear()
        if r.monthly_returns:
            df_m = pd.DataFrame(r.monthly_returns)
            df_m["key"] = df_m["year"] + "-" + df_m["month"].str.zfill(2)
            # 构建年度 × 月份矩阵
            years = sorted(df_m["year"].unique())
            months = ["01","02","03","04","05","06","07","08","09","10","11","12"]
            matrix = np.full((len(years), 12), np.nan)
            for _, row in df_m.iterrows():
                yi = years.index(row["year"])
                mi = months.index(row["month"]) if row["month"] in months else -1
                if mi >= 0:
                    matrix[yi, mi] = row["ret"]

            im = ax4.imshow(matrix, aspect="auto", cmap="RdYlGn", vmin=-15, vmax=15)
            ax4.set_xticks(range(12))
            ax4.set_xticklabels(["1","2","3","4","5","6","7","8","9","10","11","12"], fontsize=8)
            ax4.set_yticks(range(len(years)))
            ax4.set_yticklabels(years, fontsize=9)
            ax4.set_xlabel("月份", fontsize=9)
            ax4.set_title("月度收益热力图 (%)", fontsize=9)

            # 标注数值
            for yi in range(len(years)):
                for xi in range(12):
                    v = matrix[yi, xi]
                    if not np.isnan(v):
                        color = "#111" if abs(v) > 8 else "#eee"
                        ax4.text(xi, yi, f"{v:.1f}", ha="center", va="center",
                                  fontsize=7, color=color, fontweight="bold")

            # 颜色条
            self._main_fig.colorbar(im, ax=ax4, shrink=0.5, label="%")

        self._main_fig.canvas.draw()

    def _render_trades(self, r: "BacktestResult"):
        table = self.trades_table
        table.setRowCount(len(r.trades))
        for i, t in enumerate(r.trades):
            values = [
                t["date"], t["code"],
                t["direction"].upper(),
                f"{t['price']:.2f}",
                str(t["qty"]),
                f"¥{t['amount']:,.0f}",
                f"¥{t['commission']:.2f}",
                f"¥{t.get('pnl',0):.0f}",
            ]
            for j, v in enumerate(values):
                item = QTableWidgetItem(v)
                item.setTextAlignment(Qt.AlignCenter)
                if t["direction"] == "buy":
                    item.setForeground(QColor("#4a9eff"))
                else:
                    pnl = t.get("pnl", 0)
                    item.setForeground(QColor("#51cf66" if pnl >= 0 else "#ff6b6b"))
                table.setItem(i, j, item)

    def _render_daily(self, r: "BacktestResult"):
        table = self.daily_table
        if not r.equity_curve:
            return
        table.setRowCount(len(r.equity_curve))
        nav_prev = r.initial_capital
        for i, e in enumerate(r.equity_curve):
            nav = e["capital"]
            ret = (nav - nav_prev) / nav_prev * 100 if nav_prev > 0 else 0
            nav_prev = nav
            values = [
                e["ts"],
                f"¥{nav:,.0f}",
                "--",
                "--",
                f"{ret:+.2f}%",
            ]
            for j, v in enumerate(values):
                item = QTableWidgetItem(v)
                item.setTextAlignment(Qt.AlignCenter)
                table.setItem(i, j, item)

    def _render_perf_analysis(self, r: "BacktestResult"):
        # 收益分布直方图
        ax = self._ax_hist
        ax.clear()
        sells = [t for t in r.trades if t["direction"] == "sell" and t.get("pnl", 0) != 0]
        pnls = [t["pnl"] for t in sells]
        if pnls:
            colors = ["#51cf66" if p >= 0 else "#ff6b6b" for p in pnls]
            ax.hist(pnls, bins=max(10, len(pnls)//5), color=colors,
                    edgecolor="#333", alpha=0.8)
            ax.axvline(0, color="#aaa", linestyle="--", linewidth=1)
            ax.set_xlabel("盈亏(¥)", fontsize=9)
            ax.set_ylabel("频次", fontsize=9)
            ax.set_title(f"单笔盈亏分布  (胜率: {r.win_rate:.1f}%  盈亏比: {r.profit_loss_ratio:.2f})",
                        fontsize=9)
            ax.grid(True, alpha=0.3)
        self._ax_hist.figure.canvas.draw()

        # 滚动夏普
        ax = self._ax_rolling
        ax.clear()
        if r.daily_returns and len(r.daily_returns) > 20:
            rets = pd.Series([d["ret"] for d in r.daily_returns])
            rolling_sharpe = rets.rolling(20).mean() / rets.rolling(20).std() * np.sqrt(252)
            dates = [d["date"] for d in r.daily_returns]
            ax.plot(dates[len(dates)-len(rolling_sharpe):], rolling_sharpe.values,
                    color="#a855f7", linewidth=1.2)
            ax.axhline(0, color="#555", linestyle="--", linewidth=0.8)
            ax.fill_between(dates[len(dates)-len(rolling_sharpe):],
                            0, rolling_sharpe.values,
                            where=rolling_sharpe.values > 0,
                            color="#a855f7", alpha=0.2)
            ax.set_ylabel("夏普比率", fontsize=9)
            ax.set_title("20日滚动夏普", fontsize=9)
            ax.grid(True, alpha=0.3)
        ax.tick_params(labelsize=7)
        self._ax_rolling.figure.canvas.draw()

        # 持仓周期 vs 收益散点
        ax = self._ax_scatter
        ax.clear()
        if sells and len(sells) > 1:
            # 计算每次持仓的周期（简化）
            trade_dates = [t["date"] for t in r.trades if t["direction"] == "buy"]
            pnl_list = [t["pnl"] for t in sells]
            hold_periods = list(range(1, len(pnl_list) + 1))
            colors = ["#51cf66" if p >= 0 else "#ff6b6b" for p in pnl_list]
            ax.scatter(hold_periods, pnl_list, c=colors, s=40, alpha=0.7, edgecolors="none")
            ax.axhline(0, color="#555", linestyle="--", linewidth=0.8)
            ax.set_xlabel("交易序号", fontsize=9)
            ax.set_ylabel("单笔盈亏(¥)", fontsize=9)
            ax.set_title("交易序号 vs 单笔盈亏", fontsize=9)
            ax.grid(True, alpha=0.3)
        ax.tick_params(labelsize=8)
        self._ax_scatter.figure.canvas.draw()

    def _render_monthly_analysis(self, r: "BacktestResult"):
        ax = self._ax_monthly_table
        ax.clear()
        if not r.monthly_returns:
            return

        df = pd.DataFrame(r.monthly_returns)
        years = sorted(df["year"].unique())
        months = ["01","02","03","04","05","06","07","08","09","10","11","12"]

        matrix = np.full((len(years), 12), np.nan)
        year_to_idx = {y: i for i, y in enumerate(years)}
        for _, row in df.iterrows():
            if row["month"] in months:
                yi = year_to_idx[row["year"]]
                xi = months.index(row["month"])
                matrix[yi, xi] = row["ret"]

        im = ax.imshow(matrix, aspect="auto", cmap="RdYlGn", vmin=-20, vmax=20)
        ax.set_xticks(range(12))
        ax.set_xticklabels([f"{int(m)}月" for m in months], fontsize=9)
        ax.set_yticks(range(len(years)))
        ax.set_yticklabels(years, fontsize=9)
        ax.set_xlabel("月份", fontsize=10)

        # 标注数值
        for yi in range(len(years)):
            for xi in range(12):
                v = matrix[yi, xi]
                if not np.isnan(v):
                    color = "#111" if abs(v) > 10 else "#eee"
                    ax.text(xi, yi, f"{v:.1f}%", ha="center", va="center",
                            fontsize=7.5, color=color, fontweight="bold")

        # 年度汇总列
        if len(years) > 0:
            annual_rets = df.groupby("year")["ret"].sum()
            for yi, y in enumerate(years):
                ar = annual_rets.get(y, 0)
                ax.text(12, yi, f"{ar:+.1f}%", ha="left", va="center",
                        fontsize=8, fontweight="bold",
                        color="#51cf66" if ar >= 0 else "#ff6b6b")

        ax.set_title("月度收益热力图（含年度汇总）", fontsize=10)
        self._ax_monthly_table.figure.colorbar(im, ax=ax, shrink=0.6, label="%")

    def _render_signal_analysis(self, r: "BacktestResult"):
        """信号分析：收益曲线叠加买卖点"""
        ax1 = self._ax_signal
        ax2 = self._ax_signal_entry

        ax1.clear()
        ax2.clear()

        if not r.equity_curve:
            return

        dates = [e["ts"] for e in r.equity_curve]
        capitals = [e["capital"] for e in r.equity_curve]

        ax1.plot(dates, capitals, color="#4a9eff", linewidth=1.2)
        ax1.axhline(r.initial_capital, color="#555", linestyle="--", linewidth=0.8, alpha=0.7)

        # 标记买卖点
        buys = [t for t in r.trades if t["direction"] == "buy"]
        sells = [t for t in r.trades if t["direction"] == "sell"]

        buy_dates, buy_caps = [], []
        sell_dates, sell_caps = [], []
        cap_dict = {e["ts"]: e["capital"] for e in r.equity_curve}
        for t in buys:
            if t["date"] in cap_dict:
                buy_dates.append(t["date"])
                buy_caps.append(cap_dict[t["date"]])
        for t in sells:
            if t["date"] in cap_dict:
                sell_dates.append(t["date"])
                sell_caps.append(cap_dict[t["date"]])

        if buy_dates:
            ax1.scatter(buy_dates, buy_caps, c="#51cf66", s=60, marker="^",
                        zorder=5, label="买入", edgecolors="none")
        if sell_dates:
            ax1.scatter(sell_dates, sell_caps, c="#ff6b6b", s=60, marker="v",
                        zorder=5, label="卖出", edgecolors="none")

        ax1.set_ylabel("资金(¥)", fontsize=9)
        ax1.set_title("买卖点标注", fontsize=9)
        ax1.legend(loc="upper left", fontsize=8)
        ax1.grid(True, alpha=0.3)
        ax1.tick_params(labelsize=7)

        # 盈亏柱状图
        if sells:
            sell_dates_list = [t["date"] for t in sells]
            sell_pnls = [t["pnl"] for t in sells]
            colors = ["#51cf66" if p >= 0 else "#ff6b6b" for p in sell_pnls]
            ax2.bar(range(len(sell_pnls)), sell_pnls, color=colors, width=0.6, alpha=0.8)
            ax2.axhline(0, color="#aaa", linestyle="--", linewidth=0.8)
            ax2.set_xticks(range(len(sell_pnls)))
            ax2.set_xticklabels(sell_dates_list, rotation=45, fontsize=7)
            ax2.set_ylabel("单笔盈亏(¥)", fontsize=9)
            ax2.set_title("卖出盈亏柱状图", fontsize=9)
            ax2.grid(True, alpha=0.3, axis="y")
        ax2.tick_params(labelsize=7)

        self._ax_signal.figure.canvas.draw()

    # ──────────────────────────────────────────────
    # 工具方法
    # ──────────────────────────────────────────────

    def _export_report(self):
        if not self.result:
            return
        path, _ = QFileDialog.getSaveFileName(
            self, "导出回测报告", f"{self.result.strategy_name}_{self.result.code}_report.json",
            "JSON Files (*.json)"
        )
        if path:
            self.result.save(path)
            QMessageBox.information(self, "导出成功", f"报告已保存至:\n{path}")

    def _save_figures(self):
        if not self.result:
            return
        path, _ = QFileDialog.getSaveFileName(
            self, "保存图表", f"{self.result.strategy_name}_{self.result.code}.png",
            "PNG Files (*.png)"
        )
        if path:
            self._main_fig.savefig(path, dpi=150, bbox_inches="tight")
            QMessageBox.information(self, "保存成功", f"图表已保存至:\n{path}")