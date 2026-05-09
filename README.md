# SmartInvoice

> 中文发票 & 电商订单多引擎 OCR 提取工具 — 6 种方案自由切换，DeepSeek + Qwen + EasyOCR 智能融合，发票识别准确率 96.7%，智能缓存 + 批量处理，双击即用。

[![License: MIT](https://img.shields.io/badge/License-MIT-yellow.svg)](https://opensource.org/licenses/MIT)
[![Python 3.10+](https://img.shields.io/badge/python-3.10+-blue.svg)](https://www.python.org/downloads/)

[English](#english) | [中文](#中文说明)

---

## 为什么选择 SmartInvoice？

- **多引擎融合** — 不依赖单一模型，6 种方案互补，覆盖率最高
- **开箱即用** — 双击 `run_all.bat` 即可使用，无需命令行经验
- **智能缓存** — MD5 哈希检测，源文件变化才重跑，节省时间
- **本地运行** — 数据不出本机，保护隐私安全
- **多格式输出** — JSON、CSV、Markdown 报告，满足不同需求

---

## 效果展示

### 发票识别

| 方案 | 准确率 | 最强项 |
|------|--------|--------|
| **DeepSeek-OCR + 正则** | **96.7%** | 发票号码/日期/购买方 100% |
| Qwen 视觉模型 | 95.7% | 金额/税额/销售方 100% |
| 本地 PyMuPDF | 91.9% | 发票号码/日期 100% |

### 订单截图识别

| 方案 | 成功率 | 说明 |
|------|--------|------|
| **EasyOCR + Qwen 合并** | **83%** | 互补效果最佳 |
| EasyOCR（已优化） | 66% | 速度快，编号提取 99% |
| Qwen 视觉模型 | 62% | 复杂店名识别更强 |

### 合并策略（方式 6）

| 字段 | 优先来源 | 原因 |
|------|---------|------|
| 店铺名称 | Qwen | 复杂/乱码店名识别更强 |
| 交易日期 | EasyOCR | Qwen 容易混淆订单日期和成交时间 |
| 交易唯一编号 | EasyOCR | 优化后准确率 99% |
| 优惠后金额 | EasyOCR | 覆盖 92%，Qwen 补缺 |

---

## 功能特性

- **6 种识别方式** — PyMuPDF、DeepSeek-OCR、Qwen Vision、EasyOCR 自由选择
- **智能缓存** — 基于 MD5 哈希的缓存失效检测，源文件变化时自动重跑
- **结果合并** — EasyOCR + Qwen 视觉模型互补，截图成功率从 66% 提升至 83%
- **批量处理** — 逐模型运行，合理管理 GPU 显存
- **多格式输出** — JSON、CSV、Markdown 报告
- **菜单界面** — 无需命令行知识，双击即用

---

## 环境要求

- **Python** 3.10+
- **NVIDIA GPU** + CUDA（推荐，CPU 也可运行）
- **Ollama**（使用视觉模型时需要，[下载地址](https://ollama.com/download)）

---

## 快速开始

### 1. 克隆仓库

```bash
git clone https://github.com/dreamforthat/InvoiceOCR-MultiEngine.git
cd InvoiceOCR-MultiEngine
```

### 2. 安装依赖

```bash
pip install -r requirements.txt
```

或 Windows 用户双击 `setup.bat`

### 3. 下载模型（可选）

```bash
# Qwen 视觉模型（方式 2/5/6）
ollama pull lukey03/qwen3.5-9b-abliterated-vision:latest

# DeepSeek OCR（方式 3）
ollama pull DeepSeek-OCR:latest
```

### 4. 开始使用

**Windows 用户：** 双击 `run_all.bat`，从菜单选择：

```
--- 发票识别 ---
[1] 本地 PyMuPDF          [2] Qwen 视觉模型    [3] DeepSeek-OCR + 正则

--- 截图识别 ---
[4] 本地 EasyOCR          [5] Qwen 视觉模型    [6] EasyOCR + Qwen 合并

--- 批量运行 ---
[7] 全部运行              [8] 仅发票           [9] 仅截图
```

**命令行用户：**

```bash
# 发票识别（选其一）
python extract_invoices.py        # 方式 1: 本地 PyMuPDF
python ollama_invoice_ocr.py      # 方式 2: Qwen 视觉模型
python deepseek_invoice_ocr.py    # 方式 3: DeepSeek-OCR + 正则

# 截图识别（选其一）
python extract_orders.py          # 方式 4: EasyOCR（已优化）
python ollama_order_ocr.py        # 方式 5: Qwen 视觉模型
python combined_order_ocr.py      # 方式 6: EasyOCR + Qwen 合并
```

---

## 输入 / 输出

### 输入

将文件放入对应目录：

```
原始发票/          # 放入发票 PDF
├── invoice_001.pdf
└── invoice_002.pdf

原始截图/          # 放入订单截图
├── screenshot_001.jpg
└── screenshot_002.png
```

### 输出

结果保存到 `输出结果/`：

```
输出结果/
├── 发票/
│   ├── 发票_本地识别.json/csv/md
│   ├── 发票_模型识别.json/csv/md
│   └── 发票_deepseek混合.json/csv/md
└── 截图/
    ├── 截图_本地识别.json/csv/md
    ├── 截图_模型识别.json/csv/md
    └── 截图_合并识别.json/csv/md
```

---

## 项目结构

```
InvoiceOCR-MultiEngine/
├── extract_invoices.py          # 方式 1: 本地 PyMuPDF
├── ollama_invoice_ocr.py        # 方式 2: Qwen 视觉模型
├── deepseek_invoice_ocr.py      # 方式 3: DeepSeek-OCR + 正则
├── extract_orders.py            # 方式 4: EasyOCR（已优化）
├── ollama_order_ocr.py          # 方式 5: Qwen 视觉模型
├── combined_order_ocr.py        # 方式 6: EasyOCR + Qwen 合并
├── cache_utils.py               # MD5 哈希缓存管理
├── run_all.bat                  # 菜单运行器（Windows）
├── setup.bat                    # 环境安装（Windows）
├── requirements.txt             # Python 依赖
├── OCR对比报告.md               # 详细对比报告
├── 原始发票/                    # 输入：发票 PDF
├── 原始截图/                    # 输入：订单截图
└── 输出结果/                    # 输出：识别结果
```

---

## 缓存机制

所有脚本使用 MD5 哈希缓存：

- 保存结果时自动附带源文件哈希
- 再次运行时对比哈希，内容变化的文件自动重跑
- 换了源文件无需手动清缓存
- 旧缓存（无哈希）兼容处理，不会强制重跑

---

## 配置

### 模型选择

修改 Ollama 脚本中的 `MODEL` 变量：

```python
# ollama_invoice_ocr.py / ollama_order_ocr.py
MODEL = "lukey03/qwen3.5-9b-abliterated-vision:latest"

# deepseek_invoice_ocr.py
MODEL = "DeepSeek-OCR:latest"
```

### EasyOCR GPU

EasyOCR 自动检测 GPU。强制使用 CPU：

```python
reader = easyocr.Reader(['ch_sim', 'en'], gpu=False)
```

---

## 常见问题

### Q: 没有 GPU 能用吗？

A: 可以。方式 1/4（PyMuPDF、EasyOCR）支持 CPU 运行，速度较慢但可用。方式 2/3/5/6 需要 Ollama，建议有 GPU。

### Q: 识别准确率怎么提高？

A: 
- 发票推荐使用方式 3（DeepSeek-OCR + 正则），准确率 96.7%
- 截图推荐使用方式 6（EasyOCR + Qwen 合并），成功率 83%
- 确保图片清晰、无遮挡

### Q: 支持哪些文件格式？

A: 
- 发票：PDF
- 截图：JPG、PNG

### Q: 如何更新模型？

A: 运行 `ollama pull` 命令即可更新到最新版本。

---

## 许可证

MIT License - 详见 [LICENSE](LICENSE)

---

# English

## SmartInvoice

> Multi-engine OCR toolkit for Chinese invoices & e-commerce orders. 6 extraction methods with DeepSeek + Qwen + EasyOCR fusion. Invoice accuracy up to 96.7%, smart caching, batch processing — just double-click to run.

### Why SmartInvoice?

- **Multi-engine fusion** — 6 methods for maximum coverage
- **Easy to use** — Double-click `run_all.bat`, no CLI knowledge needed
- **Smart caching** — MD5 hash-based, only re-process changed files
- **Local execution** — Your data stays on your machine
- **Multiple outputs** — JSON, CSV, and Markdown reports

### Quick Start

```bash
# Clone
git clone https://github.com/dreamforthat/InvoiceOCR-MultiEngine.git
cd InvoiceOCR-MultiEngine

# Install
pip install -r requirements.txt

# Run (Windows)
double-click run_all.bat
```

### Requirements

- Python 3.10+
- NVIDIA GPU + CUDA (recommended)
- [Ollama](https://ollama.com/download) (for vision models)

### License

MIT License
