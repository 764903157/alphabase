"""
AlphaBase 主窗口
看海量化风格深色主题，扩展：
- 策略管理面板（可增删改）
- 一键回测运行
- 数据源状态指示
- AI 研究助手面板
"""

import sys
import os
import logging

logging.getLogger("matplotlib").setLevel(logging.ERROR)

import matplotlib
matplotlib.use("Qt5Agg")

from PyQt5.QtWidgets import (
    QMainWindow, QWidget, QVBoxLayout, QHBoxLayout, QGridLayout,
    QLabel, QPushButton, QTextEdit, QComboBox, QLineEdit,
    QSpinBox, QGroupBox, QSplitter, QTableWidget, QTableWidgetItem,
    QHeaderView, QTabWidget, QMessageBox, QFileDialog, QCheckBox,
    QProgressBar, QStatusBar, QMenuBar, QMenu, QAction, QDialog,
    QFormLayout, QDialogButtonBox, QListWidget, QListWidgetItem,
    QAbstractItemView, QScrollArea
)
from PyQt5.QtCore import Qt, QThread, pyqtSignal, QTimer, QSettings
from PyQt5.QtGui import QIcon, QFont, QColor, QPalette

from engine.backtest import BacktestEngine, BacktestResult
from engine.datahub import MarketDB
from engine.providers import get_provider
from config.settings import get_config, AppConfig, reload_config
from ui.backtest_result_view import BacktestResultWindow
import json
from datetime import datetime, timedelta

# 暗色主题设置
plt_style = """
QMainWindow, QWidget {
    background-color: #1a1a1a;
    color: #e0e0e0;
    font-family: "Microsoft YaHei", "SimHei", sans-serif;
    font-size: 14px;
}
QGroupBox {
    background-color: #252525;
    border: 1px solid #3a3a3a;
    border-radius: 6px;
    margin-top: 8px;
    padding: 8px;
    font-weight: bold;
}
QGroupBox::title { subcontrol-origin: margin; left: 10px; padding: 0 6px; }
QPushButton {
    background-color: #2a4a7a; color: #fff;
    border: none; border-radius: 4px; padding: 8px 20px;
    font-weight: bold;
}
QPushButton:hover { background-color: #3a6aaa; }
QPushButton:pressed { background-color: #1a3a6a; }
QPushButton:disabled { background-color: #333; color: #666; }
QLineEdit, QComboBox, QSpinBox {
    background-color: #2a2a2a; color: #e0e0e0;
    border: 1px solid #3a3a3a; border-radius: 3px; padding: 5px;
}
QComboBox::drop-down { border: none; }
QTableWidget {
    background-color: #222222; alternate-background-color: #282828;
    border: 1px solid #3a3a3a; color: #e0e0e0;
    gridline-color: #333;
}
QHeaderView::section {
    background-color: #2d2d2d; color: #ccc; padding: 6px;
    border: none; border-right: 1px solid #444; border-bottom: 1px solid #444;
    font-weight: bold;
}
QTabWidget::pane { border: 1px solid #3a3a3a; background-color: #1e1e1e; }
QTabBar::tab {
    background-color: #2a2a2a; color: #aaa; padding: 8px 18px;
    border-top-left-radius: 4px; border-top-right-radius: 4px;
}
QTabBar::tab:selected { background-color: #1e1e1e; border-bottom: 2px solid #4a9eff; color: #fff; }
QTabBar::tab:hover { background-color: #323232; }
QTextEdit, QListWidget {
    background-color: #1e1e1e; color: #d0d0d0; border: 1px solid #3a3a3a;
}
QStatusBar { background-color: #151515; color: #888; }
QProgressBar {
    background-color: #2a2a2a; border: none; border-radius: 4px;
    text-align: center; color: #fff;
}
QProgressBar::chunk { background-color: #4a9eff; border-radius: 4px; }
"""


def _sample_strategies():
    """内置示例策略（展示策略格式）"""
    return [
        {
            "id": "ma_cross",
            "name": "MA金叉死叉",
            "desc": "5日均线与20日均线交叉信号",
            "params": {"fast": 5, "slow": 20, "stop_loss": 0.05},
            "code": """
def signal_fn(df):
    df = df.copy()
    df['ma5'] = df['close'].rolling(5).mean()
    df['ma20'] = df['close'].rolling(20).mean()
    df['signal'] = 0
    df.loc[df['ma5'] > df['ma20'], 'signal'] = 1
    # 死叉：ma5下穿ma20时次日卖出（简化）
    df.loc[df['ma5'] < df['ma20'], 'signal'] = -1
    # 只在有持仓时卖出（避免频繁空卖）
    return df
            """.strip()
        },
        {
            "id": "rsi_oversold",
            "name": "RSI超卖",
            "desc": "RSI<30买入，RSI>70卖出",
            "params": {"rsi_period": 14, "oversold": 30, "overbought": 70, "stop_loss": 0.03},
            "code": """
def signal_fn(df):
    delta = df['close'].diff()
    gain = delta.where(delta > 0, 0).rolling(14).mean()
    loss = (-delta.where(delta < 0, 0)).rolling(14).mean()
    rs = gain / loss.replace(0, 1e-10)
    df['rsi'] = 100 - (100 / (1 + rs))
    df['signal'] = 0
    df.loc[df['rsi'] < 30, 'signal'] = 1
    df.loc[df['rsi'] > 70, 'signal'] = -1
    return df
            """.strip()
        },
        {
            "id": "boll_break",
            "name": "布林带突破",
            "desc": "收盘价突破布林带上轨买入，跌破下轨卖出",
            "params": {"period": 20, "std": 2, "stop_loss": 0.05},
            "code": """
def signal_fn(df):
    df = df.copy()
    df['mid'] = df['close'].rolling(20).mean()
    df['std'] = df['close'].rolling(20).std()
    df['upper'] = df['mid'] + 2 * df['std']
    df['lower'] = df['mid'] - 2 * df['std']
    df['signal'] = 0
    df.loc[df['close'] > df['upper'], 'signal'] = 1
    df.loc[df['close'] < df['lower'], 'signal'] = -1
    return df
            """.strip()
        },
        {
            "id": "macd_cross",
            "name": "MACD金叉死叉",
            "desc": "DIF与DEA交叉信号",
            "params": {"fast": 12, "slow": 26, "signal": 9, "stop_loss": 0.04},
            "code": """
def signal_fn(df):
    df = df.copy()
    ema12 = df['close'].ewm(span=12, adjust=False).mean()
    ema26 = df['close'].ewm(span=26, adjust=False).mean()
    df['dif'] = ema12 - ema26
    df['dea'] = df['dif'].ewm(span=9, adjust=False).mean()
    df['macd_hist'] = (df['dif'] - df['dea']) * 2
    df['signal'] = 0
    # 金叉
    df.loc[(df['dif'] > df['dea']) & (df['dif'].shift(1) <= df['dea'].shift(1)), 'signal'] = 1
    # 死叉
    df.loc[(df['dif'] < df['dea']) & (df['dif'].shift(1) >= df['dea'].shift(1)), 'signal'] = -1
    return df
            """.strip()
        },
    ]


class BacktestThread(QThread):
    """后台回测线程，避免 UI 冻结"""
    finished = pyqtSignal(object)
    progress = pyqtSignal(str, int)

    def __init__(self, engine: BacktestEngine, code: str, strategy_fn, start: str, end: str,
                 capital: float, name: str, freq: str):
        super().__init__()
        self.engine = engine
        self.code = code
        self.strategy_fn = strategy_fn
        self.start = start
        self.end = end
        self.capital = capital
        self.name = name
        self.freq = freq

    def run(self):
        try:
            self.progress.emit("加载数据...", 10)
            result = self.engine.run(
                code=self.code,
                strategy_fn=self.strategy_fn,
                start_date=self.start,
                end_date=self.end,
                initial_capital=self.capital,
                strategy_name=self.name,
                freq=self.freq,
            )
            self.progress.emit("计算完成", 100)
            self.finished.emit(result)
        except Exception as e:
            self.finished.emit(e)


class MainWindow(QMainWindow):
    """AlphaBase 主窗口"""

    def __init__(self):
        super().__init__()
        self.cfg = get_config()
        self.db = None
        self.strategies = _sample_strategies()
        self.backtest_thread: BacktestThread = None
        self.result_window: BacktestResultWindow = None

        self.setWindowTitle("AlphaBase - A股量化研究与执行工作站")
        self.setStyleSheet(plt_style)
        self._detect_screen()

        self._init_ui()
        self._init_menu()
        self._check_data_status()

    def _detect_screen(self):
        from PyQt5.QtWidgets import QApplication
        screen = QApplication.desktop().screenGeometry()
        w = screen.width()
        if w >= 3840:
            fs = 1.8
        elif w >= 2560:
            fs = 1.4
        elif w >= 1920:
            fs = 1.0
        else:
            fs = 0.8
        base_w, base_h = 1600, 1000
        self.resize(int(base_w * fs), int(base_h * fs))

    def _init_ui(self):
        # ── 状态栏 ──
        self.status_bar = QStatusBar()
        self.setStatusBar(self.status_bar)
        self.status_label = QLabel("就绪")
        self.ds_label = QLabel("数据源: AkShare")
        self.ds_label.setStyleSheet("color: #51cf66;")
        self.cap_label = QLabel("初始资金: ¥1,000,000")
        self.status_bar.addWidget(self.status_label, 1)
        self.status_bar.addPermanentWidget(self.ds_label)
        self.status_bar.addPermanentWidget(self.cap_label)

        # ── 主 widget ──
        central = QWidget()
        self.setCentralWidget(central)
        layout = QVBoxLayout()
        layout.setSpacing(6)
        layout.setContentsMargins(8, 8, 8, 8)
        central.setLayout(layout)

        # ── 顶部工具栏 ──
        toolbar = self._build_toolbar()
        layout.addLayout(toolbar)

        # ── 主内容分割 ──
        splitter = QSplitter(Qt.Horizontal)
        splitter.setHandleWidth(2)

        # 左侧面板
        left_panel = self._build_left_panel()
        splitter.addWidget(left_panel)

        # 右侧：策略编辑 + 回测控制
        right_panel = self._build_right_panel()
        splitter.addWidget(right_panel)

        splitter.setSizes([400, 1200])
        layout.addWidget(splitter, 1)

        # ── 底部日志 ──
        self.log_edit = QTextEdit()
        self.log_edit.setMaximumHeight(120)
        self.log_edit.setReadOnly(True)
        self.log_edit.setFont(QFont("Consolas", 10))
        layout.addWidget(self.log_edit)

    def _build_toolbar(self) -> QHBoxLayout:
        layout = QHBoxLayout()
        layout.setSpacing(8)

        self.settings_btn = QPushButton("⚙ 配置")
        self.settings_btn.clicked.connect(self._open_settings)
        self.refresh_btn = QPushButton("↻ 刷新数据")
        self.refresh_btn.clicked.connect(self._refresh_data)
        self.ai_btn = QPushButton("🤖 AI 研究")
        self.ai_btn.clicked.connect(self._open_ai_panel)

        layout.addWidget(self.settings_btn)
        layout.addWidget(self.refresh_btn)
        layout.addStretch()
        layout.addWidget(self.ai_btn)
        return layout

    def _build_left_panel(self) -> QWidget:
        widget = QWidget()
        vbox = QVBoxLayout()
        vbox.setSpacing(6)

        # ── 策略列表 ──
        strategy_group = QGroupBox("策略管理")
        strategy_layout = QVBoxLayout()

        self.strategy_list = QListWidget()
        self.strategy_list.setAlternatingRowColors(True)
        for s in self.strategies:
            item = QListWidgetItem(f"[{s['id']}] {s['name']}")
            item.setData(Qt.UserRole, s)
            self.strategy_list.addItem(item)
        self.strategy_list.currentItemChanged.connect(self._on_strategy_selected)
        strategy_layout.addWidget(self.strategy_list)

        btn_row = QHBoxLayout()
        self.add_strategy_btn = QPushButton("+ 新增")
        self.add_strategy_btn.clicked.connect(self._add_strategy)
        self.edit_strategy_btn = QPushButton("编辑")
        self.edit_strategy_btn.clicked.connect(self._edit_strategy)
        self.del_strategy_btn = QPushButton("删除")
        self.del_strategy_btn.clicked.connect(self._del_strategy)
        btn_row.addWidget(self.add_strategy_btn)
        btn_row.addWidget(self.edit_strategy_btn)
        btn_row.addWidget(self.del_strategy_btn)
        strategy_layout.addLayout(btn_row)
        strategy_group.setLayout(strategy_layout)
        vbox.addWidget(strategy_group)

        # ── 回测参数 ──
        params_group = QGroupBox("回测参数")
        params_grid = QFormLayout()
        params_grid.setSpacing(6)

        self.code_input = QLineEdit("600000.SH")
        self.code_input.setPlaceholderText("如 600000.SH 或 000001.SZ")
        params_grid.addRow("股票代码:", self.code_input)

        self.start_date_input = QLineEdit("20240101")
        self.start_date_input.setPlaceholderText("YYYYMMDD")
        params_grid.addRow("开始日期:", self.start_date_input)

        self.end_date_input = QLineEdit("20250501")
        self.end_date_input.setPlaceholderText("YYYYMMDD")
        params_grid.addRow("结束日期:", self.end_date_input)

        self.capital_spin = QSpinBox()
        self.capital_spin.setRange(10000, 100000000)
        self.capital_spin.setSingleStep(100000)
        self.capital_spin.setValue(1000000)
        self.capital_spin.setSuffix(" 元")
        params_grid.addRow("初始资金:", self.capital_spin)

        self.freq_combo = QComboBox()
        self.freq_combo.addItems(["day", "1min", "5min", "15min", "30min", "60min"])
        params_grid.addRow("数据频率:", self.freq_combo)

        params_group.setLayout(params_grid)
        vbox.addWidget(params_group)

        widget.setLayout(vbox)
        return widget

    def _build_right_panel(self) -> QWidget:
        widget = QWidget()
        vbox = QVBoxLayout()
        vbox.setSpacing(6)

        # ── 策略预览 ──
        preview_group = QGroupBox("策略代码")
        preview_layout = QVBoxLayout()
        self.strategy_preview = QTextEdit()
        self.strategy_preview.setFont(QFont("Consolas", 11))
        self.strategy_preview.setTabStopDistance(40)
        preview_layout.addWidget(self.strategy_preview)
        preview_group.setLayout(preview_layout)
        vbox.addWidget(preview_group, 1)

        # ── 回测控制 ──
        control_group = QGroupBox("回测控制")
        control_layout = QHBoxLayout()

        self.run_backtest_btn = QPushButton("▶ 运行回测")
        self.run_backtest_btn.setStyleSheet("""
            QPushButton { background-color: #2d6a4f; padding: 10px 30px; font-size: 15px; }
            QPushButton:hover { background-color: #3d8a6f; }
        """)
        self.run_backtest_btn.clicked.connect(self._run_backtest)

        self.batch_btn = QPushButton("📊 批量回测")
        self.batch_btn.clicked.connect(self._run_batch)

        self.progress_bar = QProgressBar()
        self.progress_bar.setMaximumWidth(300)
        self.progress_bar.setVisible(False)

        control_layout.addWidget(self.run_backtest_btn)
        control_layout.addWidget(self.batch_btn)
        control_layout.addWidget(self.progress_bar)
        control_layout.addStretch()
        control_group.setLayout(control_layout)
        vbox.addWidget(control_group)

        # ── 结果摘要 ──
        result_group = QGroupBox("回测结果摘要")
        result_grid = QGridLayout()
        result_grid.setSpacing(6)

        self.result_labels = {}
        summary_items = [
            ("总收益率", "total_return"), ("年化收益率", "annual_return"),
            ("最大回撤", "max_drawdown"), ("夏普比率", "sharpe"),
            ("胜率", "win_rate"), ("总交易次数", "trades"),
            ("盈亏比", "pl_ratio"), ("最终资金", "final_capital"),
        ]
        for i, (label, key) in enumerate(summary_items):
            row, col = i // 4, (i % 4) * 2
            lbl = QLabel(label + ":")
            lbl.setStyleSheet("color: #888; font-weight: bold;")
            val_lbl = QLabel("--")
            val_lbl.setStyleSheet("color: #e0e0e0; font-family: Consolas;")
            result_grid.addWidget(lbl, row, col)
            result_grid.addWidget(val_lbl, row, col + 1)
            self.result_labels[key] = val_lbl

        result_group.setLayout(result_grid)
        vbox.addWidget(result_group)

        # ── 打开详细结果按钮 ──
        self.open_result_btn = QPushButton("📈 打开详细结果窗口")
        self.open_result_btn.clicked.connect(self._open_result_window)
        self.open_result_btn.hide()
        vbox.addWidget(self.open_result_btn)

        widget.setLayout(vbox)
        return widget

    def _init_menu(self):
        menubar = self.menuBar()
        file_menu = menubar.addMenu("文件")
        file_menu.addAction("保存策略配置", self._save_strategies)
        file_menu.addAction("加载策略配置", self._load_strategies)
        file_menu.addSeparator()
        file_menu.addAction("退出", self.close)

        data_menu = menubar.addMenu("数据")
        data_menu.addAction("同步日线数据", self._sync_daily)
        data_menu.addAction("数据源设置", self._open_settings)

        ai_menu = menubar.addMenu("AI")
        ai_menu.addAction("市场分析", self._open_ai_panel)
        ai_menu.addAction("策略生成", self._generate_strategy)

        help_menu = menubar.addMenu("帮助")
        help_menu.addAction("关于", self._about)

    def _check_data_status(self):
        try:
            self.db = MarketDB()
            count = self.db.conn.execute("SELECT COUNT(*) FROM kline").fetchone()[0]
            self.ds_label.setText(f"数据源: AkShare | DuckDB记录: {count:,}")
        except Exception as e:
            self._log(f"[初始化] DuckDB 连接异常: {e}")

    def _log(self, msg: str):
        ts = datetime.now().strftime("%H:%M:%S")
        self.log_edit.append(f"[{ts}] {msg}")

    def _on_strategy_selected(self, item: QListWidgetItem):
        if item:
            s = item.data(Qt.UserRole)
            self.strategy_preview.setPlainText(s.get("code", ""))

    def _add_strategy(self):
        dlg = StrategyDialog(self)
        if dlg.exec_() == QDialog.Accepted:
            s = dlg.get_strategy()
            self.strategies.append(s)
            item = QListWidgetItem(f"[{s['id']}] {s['name']}")
            item.setData(Qt.UserRole, s)
            self.strategy_list.addItem(item)
            self._log(f"[策略] 新增策略: {s['name']}")

    def _edit_strategy(self):
        item = self.strategy_list.currentItem()
        if not item:
            return
        s = item.data(Qt.UserRole)
        dlg = StrategyDialog(self, s)
        if dlg.exec_() == QDialog.Accepted:
            new_s = dlg.get_strategy()
            # 更新列表
            for i in range(self.strategy_list.count()):
                it = self.strategy_list.item(i)
                if it.data(Qt.UserRole)["id"] == s["id"]:
                    it.setData(Qt.UserRole, new_s)
                    it.setText(f"[{new_s['id']}] {new_s['name']}")
                    break
            self._log(f"[策略] 更新策略: {new_s['name']}")

    def _del_strategy(self):
        row = self.strategy_list.currentRow()
        if row >= 0:
            item = self.strategy_list.item(row)
            s = item.data(Qt.UserRole)
            self.strategy_list.takeItem(row)
            self._log(f"[策略] 删除策略: {s['name']}")

    def _run_backtest(self):
        item = self.strategy_list.currentItem()
        if not item:
            QMessageBox.warning(self, "提示", "请先选择一个策略")
            return

        code = self.code_input.text().strip()
        if not code:
            QMessageBox.warning(self, "提示", "请输入股票代码")
            return

        strategy_data = item.data(Qt.UserRole)
        strategy_name = strategy_data["name"]

        # 构造策略函数
        try:
            exec_globals = {}
            exec(strategy_data["code"], exec_globals)
            signal_fn = exec_globals.get("signal_fn")
            if not signal_fn:
                raise ValueError("策略代码中未定义 signal_fn 函数")
        except Exception as e:
            QMessageBox.critical(self, "策略错误", f"策略代码执行失败:\n{e}")
            return

        start = self.start_date_input.text().strip()
        end = self.end_date_input.text().strip()
        capital = self.capital_spin.value()
        freq = self.freq_combo.currentText()

        self.progress_bar.setVisible(True)
        self.progress_bar.setValue(5)
        self.run_backtest_btn.setEnabled(False)
        self.status_label.setText("回测中...")

        self.engine = BacktestEngine()
        self.backtest_thread = BacktestThread(
            self.engine, code, signal_fn, start, end, capital, strategy_name, freq
        )
        self.backtest_thread.finished.connect(self._on_backtest_finished)
        self.backtest_thread.progress.connect(self._on_backtest_progress)
        self.backtest_thread.start()

    def _on_backtest_progress(self, msg: str, value: int):
        self.status_label.setText(msg)
        self.progress_bar.setValue(value)

    def _on_backtest_finished(self, result):
        self.progress_bar.setVisible(False)
        self.run_backtest_btn.setEnabled(True)

        if isinstance(result, Exception):
            QMessageBox.critical(self, "回测失败", str(result))
            self.status_label.setText("回测失败")
            self._log(f"[回测] 失败: {result}")
            return

        self._log(f"[回测] ✅ {result.strategy_name} 完成 | 总收益: {result.total_return:+.2f}%")
        self.status_label.setText("回测完成")

        # 更新摘要
        labels_map = {
            "total_return": f"{result.total_return:+.2f}%",
            "annual_return": f"{result.annual_return:+.2f}%",
            "max_drawdown": f"{result.max_drawdown_pct:.2f}%",
            "sharpe": f"{result.sharpe_ratio:.2f}",
            "win_rate": f"{result.win_rate:.1f}%",
            "trades": str(result.total_trades),
            "pl_ratio": f"{result.profit_loss_ratio:.2f}",
            "final_capital": f"¥{result.final_capital:,.0f}",
        }
        for key, val in labels_map.items():
            self.result_labels[key].setText(val)
            # 着色
            color = "#51cf66" if ("return" in key and result.total_return > 0) or \
                             (key == "max_drawdown" and result.max_drawdown_pct < 5) else "#e0e0e0"
            self.result_labels[key].setStyleSheet(f"color: {color}; font-family: Consolas;")

        self.current_result = result
        self.open_result_btn.show()

    def _open_result_window(self):
        if hasattr(self, "current_result") and self.current_result:
            win = BacktestResultWindow(self.current_result)
            win.show()
            self._log("[窗口] 打开回测结果详情窗口")

    def _run_batch(self):
        QMessageBox.information(self, "批量回测", "批量回测功能开发中，可先使用单票回测验证策略。")

    def _open_settings(self):
        dlg = SettingsDialog(self)
        dlg.exec_()
        reload_config()
        self.cfg = get_config()

    def _refresh_data(self):
        self.status_label.setText("同步数据...")
        QMessageBox.information(self, "数据同步", "数据同步功能开发中，请通过配置设置 Tushare Token。")

    def _open_ai_panel(self):
        dlg = AIPanelDialog(self)
        dlg.exec_()

    def _generate_strategy(self):
        QMessageBox.information(self, "策略生成", "AI 策略生成功能开发中。")

    def _sync_daily(self):
        QMessageBox.information(self, "数据同步", "日线数据同步功能开发中。")

    def _save_strategies(self):
        path, _ = QFileDialog.getSaveFileName(self, "保存策略", "strategies.json", "JSON Files (*.json)")
        if path:
            with open(path, "w", encoding="utf-8") as f:
                json.dump(self.strategies, f, indent=2, ensure_ascii=False)
            self._log(f"[文件] 策略已保存: {path}")

    def _load_strategies(self):
        path, _ = QFileDialog.getOpenFileName(self, "加载策略", "", "JSON Files (*.json)")
        if path:
            with open(path, "r", encoding="utf-8") as f:
                self.strategies = json.load(f)
            self.strategy_list.clear()
            for s in self.strategies:
                item = QListWidgetItem(f"[{s['id']}] {s['name']}")
                item.setData(Qt.UserRole, s)
                self.strategy_list.addItem(item)
            self._log(f"[文件] 策略已加载: {path}")

    def _about(self):
        QMessageBox.about(self, "关于 AlphaBase",
            "AlphaBase - A股量化研究与执行工作站\n\n"
            "融合多个优秀开源项目优点:\n"
            "• QuantDinger - AI 多智能体研究\n"
            "• 看海量化 - 专业 PyQt5 交互\n"
            "• 金策智算 - 多数据源 + DuckDB\n\n"
            "版本: 0.1.0\nLicense: Apache 2.0"
        )


# ──────────────────────────────────────────────
# 子对话框
# ──────────────────────────────────────────────

class StrategyDialog(QDialog):
    """策略编辑对话框"""

    def __init__(self, parent=None, strategy: dict = None):
        super().__init__(parent)
        self.strategy = strategy or {}
        self.setWindowTitle("编辑策略" if strategy else "新增策略")
        self.setMinimumSize(600, 500)
        self.setStyleSheet(parent.styleSheet())

        layout = QVBoxLayout()
        form = QFormLayout()
        form.setSpacing(6)

        self.id_edit = QLineEdit(self.strategy.get("id", ""))
        self.name_edit = QLineEdit(self.strategy.get("name", ""))
        self.desc_edit = QLineEdit(self.strategy.get("desc", ""))
        self.params_edit = QLineEdit(json.dumps(self.strategy.get("params", {}), ensure_ascii=False))
        self.code_edit = QTextEdit(self.strategy.get("code",
            "def signal_fn(df):\n    df = df.copy()\n    df['signal'] = 0\n    return df"
        ))
        self.code_edit.setFont(QFont("Consolas", 11))
        self.code_edit.setTabStopDistance(40)

        form.addRow("策略ID:", self.id_edit)
        form.addRow("名称:", self.name_edit)
        form.addRow("描述:", self.desc_edit)
        form.addRow("参数(JSON):", self.params_edit)

        layout.addLayout(form)
        layout.addWidget(QLabel("策略代码:"))
        layout.addWidget(self.code_edit, 1)

        btns = QDialogButtonBox(QDialogButtonBox.Ok | QDialogButtonBox.Cancel)
        btns.accepted.connect(self.accept)
        btns.rejected.connect(self.reject)
        layout.addWidget(btns)

        self.setLayout(layout)

    def get_strategy(self) -> dict:
        params = {}
        try:
            params = json.loads(self.params_edit.text())
        except Exception:
            pass
        return {
            "id": self.id_edit.text().strip(),
            "name": self.name_edit.text().strip(),
            "desc": self.desc_edit.text().strip(),
            "params": params,
            "code": self.code_edit.toPlainText(),
        }


class SettingsDialog(QDialog):
    """配置对话框：用户自定义 token / plan key"""

    def __init__(self, parent=None):
        super().__init__(parent)
        self.cfg = get_config()
        self.setWindowTitle("⚙ AlphaBase 配置")
        self.setMinimumSize(650, 550)
        self.setStyleSheet(parent.styleSheet())

        tabs = QTabWidget()
        tabs.addTab(self._build_data_tab(), "数据源")
        tabs.addTab(self._build_llm_tab(), "AI / LLM")
        tabs.addTab(self._build_backtest_tab(), "回测参数")

        layout = QVBoxLayout()
        layout.addWidget(tabs)
        btns = QDialogButtonBox(QDialogButtonBox.Ok | QDialogButtonBox.Cancel)
        btns.accepted.connect(self._save)
        btns.rejected.connect(self.reject)
        layout.addWidget(btns)
        self.setLayout(layout)

    def _build_data_tab(self) -> QWidget:
        w = QWidget()
        layout = QVBoxLayout()

        info = QLabel("配置您的数据源 API（留空则使用 AkShare 免费数据）")
        info.setStyleSheet("color: #888;")
        layout.addWidget(info)

        form = QFormLayout()
        self.tushare_token = QLineEdit(self.cfg.data_source.tushare_token)
        self.tushare_token.setPlaceholderText("在 tushare.pro 注册后获取 token")
        form.addRow("Tushare Token:", self.tushare_token)

        self.tdx_dir = QLineEdit(self.cfg.data_source.tdx_dir)
        self.tdx_dir.setPlaceholderText("通达信安装目录，如 D:/tdx")
        form.addRow("通达信目录:", self.tdx_dir)

        self.api_url = QLineEdit(self.cfg.data_source.api_url)
        self.api_url.setPlaceholderText("https://your-api.com")
        form.addRow("自定义 API URL:", self.api_url)

        self.api_key = QLineEdit(self.cfg.data_source.api_key)
        self.api_key.setEchoMode(QLineEdit.Password)
        form.addRow("自定义 API Key:", self.api_key)

        self.qmt_account = QLineEdit(self.cfg.data_source.qmt_account)
        form.addRow("QMT 账户:", self.qmt_account)
        self.qmt_password = QLineEdit(self.cfg.data_source.qmt_password)
        self.qmt_password.setEchoMode(QLineEdit.Password)
        form.addRow("QMT 密码:", self.qmt_password)

        layout.addLayout(form)
        layout.addStretch()
        w.setLayout(layout)
        return w

    def _build_llm_tab(self) -> QWidget:
        w = QWidget()
        layout = QVBoxLayout()
        form = QFormLayout()

        self.llm_provider = QComboBox()
        self.llm_provider.addItems(["siliconflow", "deepseek", "ollama", "openai"])
        self.llm_provider.setCurrentText(self.cfg.llm.provider)
        form.addRow("LLM Provider:", self.llm_provider)

        self.llm_api_key = QLineEdit(self.cfg.llm.api_key)
        self.llm_api_key.setEchoMode(QLineEdit.Password)
        self.llm_api_key.setPlaceholderText("API Key（用于 AI 分析和策略生成）")
        form.addRow("API Key:", self.llm_api_key)

        self.llm_base_url = QLineEdit(self.cfg.llm.base_url)
        form.addRow("Base URL:", self.llm_base_url)

        self.llm_model = QLineEdit(self.cfg.llm.model)
        form.addRow("Model:", self.llm_model)

        layout.addLayout(form)
        layout.addStretch()
        w.setLayout(layout)
        return w

    def _build_backtest_tab(self) -> QWidget:
        w = QWidget()
        layout = QVBoxLayout()
        form = QFormLayout()

        self.initial_capital = QSpinBox()
        self.initial_capital.setRange(10000, 100000000)
        self.initial_capital.setSingleStep(100000)
        self.initial_capital.setValue(int(self.cfg.backtest.initial_capital))
        form.addRow("初始资金:", self.initial_capital)

        self.commission = QSpinBox()
        self.commission.setRange(0, 100)
        self.commission.setValue(int(self.cfg.backtest.commission * 10000))
        self.commission.setSuffix(" bp")
        form.addRow("佣金 (bp):", self.commission)

        self.stamp_duty = QSpinBox()
        self.stamp_duty.setRange(0, 100)
        self.stamp_duty.setValue(int(self.cfg.backtest.stamp_duty * 1000))
        self.stamp_duty.setSuffix(" ‰")
        form.addRow("印花税 (‰):", self.stamp_duty)

        self.slippage = QSpinBox()
        self.slippage.setRange(0, 100)
        self.slippage.setValue(int(self.cfg.backtest.slippage * 1000))
        self.slippage.setSuffix(" ‰")
        form.addRow("滑点 (‰):", self.slippage)

        self.risk_free_rate = QSpinBox()
        self.risk_free_rate.setRange(0, 50)
        self.risk_free_rate.setValue(int(self.cfg.risk_free_rate * 100))
        self.risk_free_rate.setSuffix(" %")
        form.addRow("无风险收益率:", self.risk_free_rate)

        layout.addLayout(form)
        layout.addStretch()
        w.setLayout(layout)
        return w

    def _save(self):
        ds = self.cfg.data_source
        ds.tushare_token = self.tushare_token.text().strip()
        ds.tdx_dir = self.tdx_dir.text().strip()
        ds.api_url = self.api_url.text().strip()
        ds.api_key = self.api_key.text().strip()
        ds.qmt_account = self.qmt_account.text().strip()
        ds.qmt_password = self.qmt_password.text().strip()

        llm = self.cfg.llm
        llm.provider = self.llm_provider.currentText()
        llm.api_key = self.llm_api_key.text().strip()
        llm.base_url = self.llm_base_url.text().strip()
        llm.model = self.llm_model.text().strip()

        bt = self.cfg.backtest
        bt.initial_capital = float(self.initial_capital.value())
        bt.commission = self.commission.value() / 10000
        bt.stamp_duty = self.stamp_duty.value() / 1000
        bt.slippage = self.slippage.value() / 1000
        self.cfg.risk_free_rate = self.risk_free_rate.value() / 100

        self.cfg.save()
        self.accept()
        QMessageBox.information(self, "保存成功", "配置已保存，重启后生效。")


class AIPanelDialog(QDialog):
    """AI 研究助手面板"""

    def __init__(self, parent=None):
        super().__init__(parent)
        self.cfg = get_config()
        self.setWindowTitle("🤖 AI 研究助手")
        self.setMinimumSize(800, 600)
        self.setStyleSheet(parent.styleSheet())

        layout = QVBoxLayout()

        # 系统提示
        prompt_row = QHBoxLayout()
        prompt_row.addWidget(QLabel("你想研究什么？"))
        self.prompt_input = QLineEdit()
        self.prompt_input.setPlaceholderText(
            "例如：帮我分析 600000.SH 近一年的技术形态，找出潜在买卖点"
        )
        self.ask_btn = QPushButton("询问 AI")
        self.ask_btn.clicked.connect(self._ask_ai)
        prompt_row.addWidget(self.prompt_input, 1)
        prompt_row.addWidget(self.ask_btn)
        layout.addLayout(prompt_row)

        # 模型选择
        model_row = QHBoxLayout()
        model_row.addWidget(QLabel("模型:"))
        self.model_combo = QComboBox()
        self.model_combo.addItems([
            "Qwen/Qwen3-30B-A3B (硅基流动)",
            "deepseek-ai/DeepSeek-V3",
            "Qwen/Qwen2.5-72B-Instruct",
        ])
        model_row.addWidget(self.model_combo)
        model_row.addStretch()
        layout.addLayout(model_row)

        # 输出区
        self.output = QTextEdit()
        self.output.setFont(QFont("Consolas", 11))
        self.output.setReadOnly(True)
        self.output.setPlaceholderText("AI 回复将显示在此...")
        layout.addWidget(self.output, 1)

        self.setLayout(layout)

    def _ask_ai(self):
        prompt = self.prompt_input.text().strip()
        if not prompt:
            return

        api_key = self.cfg.llm.api_key
        if not api_key:
            QMessageBox.warning(self, "未配置 API Key",
                "请先在 设置 → AI/LLM 中配置 API Key")
            return

        self.output.append(f"\n🧑 你: {prompt}\n")
        self.ask_btn.setEnabled(False)

        # 简单调用 LLM（生产环境建议用 async + proper client）
        import urllib.request, json

        try:
            base_url = self.cfg.llm.base_url or "https://api.siliconflow.cn/v1"
            model = self.cfg.llm.model or "Qwen/Qwen3-30B-A3B"

            payload = {
                "model": model,
                "messages": [{"role": "user", "content": prompt}],
                "temperature": 0.7,
                "max_tokens": 2000,
            }
            req = urllib.request.Request(
                f"{base_url}/chat/completions",
                data=json.dumps(payload).encode("utf-8"),
                headers={
                    "Content-Type": "application/json",
                    "Authorization": f"Bearer {api_key}",
                },
                method="POST"
            )
            with urllib.request.urlopen(req, timeout=60) as resp:
                data = json.loads(resp.read())

            reply = data["choices"][0]["message"]["content"]
            self.output.append(f"🤖 AI:\n{reply}\n")
        except Exception as e:
            self.output.append(f"❌ 调用失败: {e}\n")

        self.ask_btn.setEnabled(True)
        self.prompt_input.clear()