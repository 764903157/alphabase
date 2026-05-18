# AlphaBase - A股量化研究与执行工作站

<div align="center">

![Python](https://img.shields.io/badge/Python-3.8+-3776AB?style=flat-square&logo=python&logoColor=white)
![PyQt5](https://img.shields.io/badge/UI-PyQt5-41CD52?style=flat-square&logo=qt&logoColor=white)
![DuckDB](https://img.shields.io/badge/Storage-DuckDB-blue?style=flat-square)
![License](https://img.shields.io/badge/License-Apache%202.0-green?style=flat-square)

</div>

---

## 三大开源项目精华融合

| 来源 | 核心优势 | 借鉴点 |
|------|---------|--------|
| **QuantDinger** | AI 多智能体研究、MCP Server | AI 研究助手 + 多 Agent 架构 |
| **看海量化** | PyQt5 专业桌面交互、低耦合设计 | 桌面 UI + 信号可视化 |
| **金策智算** | 多数据源 + DuckDB 本地存储 | DuckDB 统一存储 + 向量化回测 |

---

## 核心特性

- **多数据源**：AkShare（免费）/ Tushare / 通达信 / QMT，统一抽象层
- **DuckDB 本地存储**：列式存储 K 线、因子、信号、持仓，回测与实盘共用
- **向量化回测引擎**：基于 DuckDB SQL + Pandas 向量计算，比逐K模拟快 10-100x
- **PyQt5 专业桌面**：深色主题、绩效面板、买卖点标注、滚动夏普热力图
- **AI 研究助手**：接入 SiliconFlow / DeepSeek 等 LLM，辅助选股和策略生成
- **用户自定义 Token**：配置层支持 Tushare Token / LLM API Key / QMT 账户密码

---

## 架构

```
alphabase/
├── config/          配置层（用户自定义 token/plan key）
├── engine/
│   ├── datahub.py   DuckDB 统一存储
│   ├── providers.py 多数据源适配
│   └── backtest.py  向量化回测引擎
├── strategies/       策略文件目录
├── execution/        实盘执行（QMT/TDX）
├── ai/              AI 研究助手
├── ui/
│   ├── main_window.py          主窗口
│   └── backtest_result_view.py 回测结果可视化
└── main.py           入口
```

---

## 快速开始

```bash
# 安装依赖
pip install -r requirements.txt

# 启动
python3 main.py
```

首次启动后通过「⚙ 配置」填入你的 Token：
- **Tushare Token**：回测数据（免费注册 https://tushare.pro）
- **LLM API Key**：AI 研究助手（SiliconFlow / DeepSeek）

---

## 回测结果可视化（增强版）

在看海量化基础上新增：

- 滚动夏普比率曲线（20日）
- 累计盈亏曲线 + 买卖点标注
- 月度收益热力图（含年度汇总）
- 盈亏分布直方图
- 信号分析（收益曲线 + 盈亏柱状图）

---

## 对比同类开源项目

| 项目 | 文件数 | 数据存储 | 架构风格 |
|------|--------|---------|---------|
| 金策智算 | 99 个 | DuckDB | 过度工程化，模块冗余 |
| 看海量化 | 22 个 | 依赖 MiniQMT | 低耦合，但绑定 QMT |
| **AlphaBase** | **13 个** | **DuckDB** | **精简 + 多数据源 + AI** |

---

## License

Apache 2.0