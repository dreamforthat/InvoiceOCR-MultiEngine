# SmartInvoice

> 中文发票 & 电商订单多引擎 OCR 提取工具 — 6 种方案自由切换，DeepSeek + Qwen + EasyOCR 智能融合，发票识别准确率 100%，截图识别率 92%+，智能缓存 + 批量处理，双击即用。

[![License: MIT](https://img.shields.io/badge/License-MIT-yellow.svg)](https://opensource.org/licenses/MIT)
[![Python 3.10+](https://img.shields.io/badge/python-3.10+-blue.svg)](https://www.python.org/downloads/)

[English](#english) | [中文](#中文说明)

---

## 为什么选择 SmartInvoice？

- **多引擎融合** — 不依赖单一模型，6 种方案互补，覆盖率最高
- **交叉投票** — 发票三引擎投票合并，字段级共识机制，准确率 100%
- **智能缓存** — MD5 哈希检测，源文件变化才重跑，节省时间
- **增量更新** — 只重跑有问题的文件，不重复处理全部数据
- **本地运行** — 数据不出本机，保护隐私安全
- **多格式输出** — JSON、CSV、Markdown 报告，满足不同需求

---

## 效果展示

### 发票识别（31 张，交叉投票合并后）

| 字段 | 准确率 | 说明 |
|------|--------|------|
| 发票号码 | **100%** | 三引擎投票，修复 Qwen 截断问题 |
| 开票日期 | **100%** | 三引擎投票 |
| 购买方名称 | **100%** | 三引擎投票 |
| 销售方名称 | **100%** | 三引擎投票 |
| 金额(不含税) | **100%** | 含金额校验修正（金额+税额=价税合计） |
| 税额 | **100%** | 免税发票自动识别 |
| 价税合计 | **100%** | 含金额校验修正 |

### 截图识别（218 张，EasyOCR + Qwen 合并后）

| 字段 | 准确率 | 说明 |
|------|--------|------|
| 交易日期 | **100%** | EasyOCR 优先，全覆盖 |
| 优惠后金额 | **100%** | 双引擎互补，含小数点金额全覆盖 |
| 交易唯一编号 | **99.1%** | 2 个订单编号被折叠无法提取 |
| 店铺名称 | **92.2%** | 17 个截图店铺名被滚出画面 |

---

## 功能特性

- **6 种识别方式** — PyMuPDF、DeepSeek-OCR、Qwen Vision、EasyOCR 自由选择
- **发票交叉投票** — 三引擎按字段投票，多数共识 + 优先级裁决
- **后处理校验** — 金额加法校验、发票号码长度校验、纳税识别号格式校验
- **智能缓存** — 基于 MD5 哈希的缓存失效检测，源文件变化时自动重跑
- **增量更新** — 只重跑有缺失字段的文件，不重复处理
- **结果合并** — EasyOCR + Qwen 视觉模型互补，截图成功率从 66% 提升至 92%
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
--- Invoice ---
[1] Local (PyMuPDF)              [2] Qwen Vision Model
[3] DeepSeek-OCR + Regex

--- Order Screenshot ---
[4] Local (EasyOCR)              [5] Qwen Vision Model
[6] EasyOCR + Qwen Merge

--- Merge ---
[10] Invoice Cross-Vote Merge (3 engines)

--- Batch ---
[7] Run ALL                      [8] Run Invoice Only (all 3 methods)
[9] Run Order Only (all 3 methods)
```

**菜单选项说明：**

| 选项 | 功能 | 调用脚本 | 说明 |
|------|------|---------|------|
| [1] | 发票 - 本地 PyMuPDF | `extract_invoices.py` | 用 PyMuPDF 直接解析 PDF 文本，不需要模型，速度快 |
| [2] | 发票 - Qwen 视觉模型 | `ollama_invoice_ocr.py` | 调用 Ollama 上的 Qwen 视觉模型识别发票图片 |
| [3] | 发票 - DeepSeek-OCR | `deepseek_invoice_ocr.py` | 调用 DeepSeek-OCR 模型 + 正则表达式提取发票字段 |
| [4] | 截图 - EasyOCR | `extract_orders.py` | 用 EasyOCR 本地识别订单截图，支持 CPU/GPU |
| [5] | 截图 - Qwen 视觉模型 | `ollama_order_ocr.py` | 调用 Qwen 视觉模型识别订单截图 |
| [6] | 截图 - 双引擎合并 | `combined_order_ocr.py` | 先跑 EasyOCR，再跑 Qwen，合并两者结果（成功率最高） |
| [10] | 发票三引擎投票合并 | `merge_invoice_ocr.py` | 把方式 1/2/3 的结果按字段投票，取多数共识。**需先跑过至少 2 个发票引擎** |
| [7] | 全部运行 | 依次执行 1→6 | 首次全量处理推荐 |
| [8] | 只跑发票 | 依次执行 1→3 | 三种发票识别全部执行 |
| [9] | 只跑截图 | 依次执行 4→6 | 三种截图识别全部执行 |

**命令行用户：**

```bash
# 发票识别（选其一）
python extract_invoices.py        # 方式 1: 本地 PyMuPDF
python ollama_invoice_ocr.py      # 方式 2: Qwen 视觉模型
python deepseek_invoice_ocr.py    # 方式 3: DeepSeek-OCR + 正则

# 发票交叉投票合并（推荐，需先运行至少 2 个引擎）
python merge_invoice_ocr.py       # 方式 10: 三引擎投票合并

# 截图识别（选其一）
python extract_orders.py          # 方式 4: EasyOCR（已优化）
python ollama_order_ocr.py        # 方式 5: Qwen 视觉模型
python combined_order_ocr.py      # 方式 6: EasyOCR + Qwen 合并

# 增量更新缓存（可选，修复空字段）
python update_screenshot_cache.py # 重跑有缺失字段的截图
python update_invoice_cache.py    # 重跑有缺失字段的发票
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
│   ├── 发票_本地识别.json/csv/md        # PyMuPDF 结果
│   ├── 发票_模型识别.json/csv/md        # Qwen 视觉模型结果
│   ├── 发票_deepseek混合.json/csv/md    # DeepSeek-OCR 结果
│   └── 发票_投票合并.json/csv/md        # 三引擎投票合并（推荐）
└── 截图/
    ├── 截图_本地识别.json/csv/md        # EasyOCR 结果
    ├── 截图_模型识别.json/csv/md        # Qwen 视觉模型结果
    └── 截图_合并识别.json/csv/md        # EasyOCR + Qwen 合并（推荐）
```

---

## 项目结构

```
InvoiceOCR-MultiEngine/
├── extract_invoices.py              # 方式 1: 本地 PyMuPDF 发票提取
├── ollama_invoice_ocr.py            # 方式 2: Qwen 视觉模型发票提取
├── deepseek_invoice_ocr.py          # 方式 3: DeepSeek-OCR + 正则发票提取
├── merge_invoice_ocr.py             # 方式 10: 发票三引擎交叉投票合并
├── extract_orders.py                # 方式 4: EasyOCR 截图提取（已优化）
├── ollama_order_ocr.py              # 方式 5: Qwen 视觉模型截图提取
├── combined_order_ocr.py            # 方式 6: EasyOCR + Qwen 合并截图提取
├── update_screenshot_cache.py       # 截图缓存增量更新
├── update_invoice_cache.py          # 发票缓存增量更新
├── cache_utils.py                   # MD5 哈希缓存管理
├── run_all.bat                      # 菜单运行器（Windows）
├── setup.bat                        # 环境安装（Windows）
├── requirements.txt                 # Python 依赖
├── OCR对比报告.md                   # 详细对比报告
├── 原始发票/                        # 输入：发票 PDF
├── 原始截图/                        # 输入：订单截图
└── 输出结果/                        # 输出：识别结果
```

---

## 缓存机制

### 基础缓存

所有脚本使用 MD5 哈希缓存：

- 保存结果时自动附带源文件哈希
- 再次运行时对比哈希，内容变化的文件自动重跑
- 换了源文件无需手动清缓存
- 旧缓存（无哈希）兼容处理，不会强制重跑

### 增量更新

`update_screenshot_cache.py` 和 `update_invoice_cache.py` 提供增量更新：

- 扫描现有缓存，找出有缺失字段的文件
- 只对这些文件重新调用模型
- 更新后的结果合并回缓存
- 适用于模型升级后重新提取、修复空字段等场景

---

## 发票交叉投票机制

`merge_invoice_ocr.py` 实现了三引擎交叉投票：

### 投票规则

1. **多数共识** — 2 个及以上引擎结果一致 → 取共识值
2. **优先级裁决** — 无共识时，按字段级历史准确率排序取值
3. **特殊处理** — 发票号码取最长值防截断，商品名称跳过乱码文本

### 字段优先级

| 字段 | 优先级（高→低） | 原因 |
|------|-----------------|------|
| 发票号码 | DeepSeek → PyMuPDF → Qwen | Qwen 易截断 20 位号码 |
| 开票日期 | PyMuPDF → DeepSeek → Qwen | 三者均 100%，PyMuPDF 最稳定 |
| 购买方名称 | Qwen → DeepSeek → PyMuPDF | Qwen 语义理解最强 |
| 销售方名称 | Qwen → PyMuPDF → DeepSeek | Qwen 准确率最高 |
| 金额(不含税) | Qwen → DeepSeek → PyMuPDF | Qwen 金额提取最准 |
| 税额 | Qwen → DeepSeek → PyMuPDF | Qwen 税额提取最准 |
| 价税合计 | DeepSeek → PyMuPDF → Qwen | Qwen 易混淆价税合计 |

### 后处理校验

- **金额校验**：`金额 + 税额 ≈ 价税合计`（允许 0.02 误差）
- **发票号码**：8 位或 20 位纯数字
- **纳税识别号**：18 位字母数字
- **日期格式**：YYYY-MM-DD，月份 01-12，日期 01-31

---

## 截图多策略店铺名识别

`extract_orders.py` 和 `combined_order_ocr.py` 使用 3 种策略识别店铺名：

| 策略 | 匹配模式 | 适用场景 |
|------|---------|---------|
| 策略 1 | "进店逛逛" 左侧文本 | 标准淘宝/天猫订单 |
| 策略 2 | "天猫/淘宝 XXX旗舰店" 前缀 | 天猫店铺无"进店逛逛"按钮 |
| 策略 3 | 收货信息与商品之间的独立文本 | 兜底策略 |

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
- 发票推荐使用方式 10（交叉投票合并），准确率 100%
- 截图推荐使用方式 6（EasyOCR + Qwen 合并），成功率 92%
- 确保图片清晰、无遮挡
- 如果缓存结果有空字段，运行 `update_screenshot_cache.py` 或 `update_invoice_cache.py` 增量更新

### Q: 支持哪些文件格式？

A:
- 发票：PDF
- 截图：JPG、PNG、BMP

### Q: 如何更新模型？

A: 运行 `ollama pull` 命令即可更新到最新版本。更新后建议运行增量更新脚本重新提取。

### Q: 缓存机制是怎样的？

A: 每个脚本保存结果时自动附带源文件的 MD5 哈希。再次运行时对比哈希，只有源文件内容变化的文件才会重新处理。增量更新脚本可以只重跑有缺失字段的文件。

### Q: 为什么有些截图提取不到店铺名？

A: 如果截图在截取时已经滚动过了店铺名区域（即店铺名不在画面内），则无法提取。这是数据本身的限制，不是代码问题。

---

## 许可证

MIT License - 详见 [LICENSE](LICENSE)

---

# English

## SmartInvoice

> Multi-engine OCR toolkit for Chinese invoices & e-commerce orders. 6 extraction methods with DeepSeek + Qwen + EasyOCR fusion. Invoice accuracy 100% via cross-voting, screenshot accuracy 92%+, smart caching, batch processing — just double-click to run.

### Why SmartInvoice?

- **Multi-engine fusion** — 6 methods for maximum coverage
- **Cross-voting** — 3-engine field-level consensus for invoices
- **Post-validation** — Amount arithmetic check, invoice number length check
- **Smart caching** — MD5 hash-based, only re-process changed files
- **Incremental update** — Only re-run files with missing fields
- **Local execution** — Your data stays on your machine
- **Multiple outputs** — JSON, CSV, and Markdown reports

### Quick Start

#### 1. Clone

```bash
git clone https://github.com/dreamforthat/InvoiceOCR-MultiEngine.git
cd InvoiceOCR-MultiEngine
```

#### 2. Install

```bash
pip install -r requirements.txt
```

Or double-click `setup.bat` on Windows.

#### 3. Download Models (Optional)

```bash
# Qwen Vision Model (Methods 2/5/6)
ollama pull lukey03/qwen3.5-9b-abliterated-vision:latest

# DeepSeek OCR (Method 3)
ollama pull DeepSeek-OCR:latest
```

#### 4. Start

**Windows:** Double-click `run_all.bat` and select from menu:

**Menu Options:**

| Option | Function | Script | Description |
|--------|----------|--------|-------------|
| [1] | Invoice - Local PyMuPDF | `extract_invoices.py` | Parse PDF text directly with PyMuPDF, no model needed, fast |
| [2] | Invoice - Qwen Vision | `ollama_invoice_ocr.py` | Use Qwen vision model via Ollama to recognize invoice images |
| [3] | Invoice - DeepSeek-OCR | `deepseek_invoice_ocr.py` | Use DeepSeek-OCR model + regex to extract invoice fields |
| [4] | Screenshot - EasyOCR | `extract_orders.py` | Use EasyOCR to recognize order screenshots locally, CPU/GPU supported |
| [5] | Screenshot - Qwen Vision | `ollama_order_ocr.py` | Use Qwen vision model to recognize order screenshots |
| [6] | Screenshot - Dual Merge | `combined_order_ocr.py` | Run EasyOCR then Qwen, merge results (highest success rate) |
| [10] | Invoice Cross-Vote Merge | `merge_invoice_ocr.py` | Vote across 3 engines by field, take majority consensus. **Requires at least 2 invoice engines run first** |
| [7] | Run ALL | Run 1→6 sequentially | Recommended for first-time full processing |
| [8] | Invoice Only | Run 1→3 sequentially | Run all 3 invoice methods |
| [9] | Order Only | Run 4→6 sequentially | Run all 3 screenshot methods |

**CLI Users:**

```bash
# Invoice (pick one)
python extract_invoices.py        # Method 1: Local PyMuPDF
python ollama_invoice_ocr.py      # Method 2: Qwen Vision
python deepseek_invoice_ocr.py    # Method 3: DeepSeek-OCR + Regex

# Invoice cross-vote merge (recommended, run at least 2 engines first)
python merge_invoice_ocr.py       # Method 10: 3-engine voting merge

# Screenshot (pick one)
python extract_orders.py          # Method 4: EasyOCR (optimized)
python ollama_order_ocr.py        # Method 5: Qwen Vision
python combined_order_ocr.py      # Method 6: EasyOCR + Qwen merge

# Incremental cache update (optional, fix empty fields)
python update_screenshot_cache.py # Re-run screenshots with missing fields
python update_invoice_cache.py    # Re-run invoices with missing fields
```

### Results

#### Invoice Recognition (31 invoices, after cross-vote merge)

| Field | Accuracy | Notes |
|-------|----------|-------|
| Invoice Number | **100%** | 3-engine voting, fixes Qwen truncation issue |
| Invoice Date | **100%** | 3-engine voting |
| Buyer Name | **100%** | 3-engine voting |
| Seller Name | **100%** | 3-engine voting |
| Amount (excl. tax) | **100%** | With amount validation (amount + tax = total) |
| Tax Amount | **100%** | Auto-detect tax-exempt invoices |
| Total Amount | **100%** | With amount validation |

#### Screenshot Recognition (218 screenshots, after EasyOCR + Qwen merge)

| Field | Accuracy | Notes |
|-------|----------|-------|
| Transaction Date | **100%** | EasyOCR priority, full coverage |
| Amount After Discount | **100%** | Dual-engine complement, covers decimal amounts |
| Transaction ID | **99.1%** | 2 order IDs folded and unextractable |
| Store Name | **92.2%** | 17 screenshots had store name scrolled out of frame |

---

### Features

- **6 extraction methods** — PyMuPDF, DeepSeek-OCR, Qwen Vision, EasyOCR freely selectable
- **Invoice cross-voting** — 3-engine field-level voting, majority consensus + priority arbitration
- **Post-validation** — Amount arithmetic check, invoice number length check, tax ID format check
- **Smart caching** — MD5 hash-based cache invalidation, auto re-run when source changes
- **Incremental update** — Only re-run files with missing fields
- **Result merging** — EasyOCR + Qwen vision complement, screenshot success rate from 66% to 92%
- **Batch processing** — Run models sequentially, manage GPU memory efficiently
- **Multiple outputs** — JSON, CSV, and Markdown reports
- **Menu interface** — No CLI knowledge needed, double-click to run

---

### Input / Output

#### Input

Place files in corresponding directories:

```
原始发票/          # Place invoice PDFs
├── invoice_001.pdf
└── invoice_002.pdf

原始截图/          # Place order screenshots
├── screenshot_001.jpg
└── screenshot_002.png
```

#### Output

Results saved to `输出结果/`:

```
输出结果/
├── 发票/
│   ├── 发票_本地识别.json/csv/md        # PyMuPDF results
│   ├── 发票_模型识别.json/csv/md        # Qwen vision results
│   ├── 发票_deepseek混合.json/csv/md    # DeepSeek-OCR results
│   └── 发票_投票合并.json/csv/md        # 3-engine voting merge (recommended)
└── 截图/
    ├── 截图_本地识别.json/csv/md        # EasyOCR results
    ├── 截图_模型识别.json/csv/md        # Qwen vision results
    └── 截图_合并识别.json/csv/md        # EasyOCR + Qwen merge (recommended)
```

---

### Project Structure

```
InvoiceOCR-MultiEngine/
├── extract_invoices.py              # Method 1: Local PyMuPDF invoice extraction
├── ollama_invoice_ocr.py            # Method 2: Qwen vision invoice extraction
├── deepseek_invoice_ocr.py          # Method 3: DeepSeek-OCR + regex invoice extraction
├── merge_invoice_ocr.py             # Method 10: Invoice 3-engine cross-vote merge
├── extract_orders.py                # Method 4: EasyOCR screenshot extraction (optimized)
├── ollama_order_ocr.py              # Method 5: Qwen vision screenshot extraction
├── combined_order_ocr.py            # Method 6: EasyOCR + Qwen merge screenshot extraction
├── update_screenshot_cache.py       # Screenshot cache incremental update
├── update_invoice_cache.py          # Invoice cache incremental update
├── cache_utils.py                   # MD5 hash cache management
├── run_all.bat                      # Menu runner (Windows)
├── setup.bat                        # Environment setup (Windows)
├── requirements.txt                 # Python dependencies
├── OCR对比报告.md                   # Detailed comparison report
├── 原始发票/                        # Input: Invoice PDFs
├── 原始截图/                        # Input: Order screenshots
└── 输出结果/                        # Output: Recognition results
```

---

### Caching

#### Basic Caching

All scripts use MD5 hash caching:

- Automatically attach source file hash when saving results
- Compare hashes on re-run, only re-process changed files
- No manual cache clearing needed when source files change
- Legacy cache (without hash) handled compatibly, no forced re-run

#### Incremental Update

`update_screenshot_cache.py` and `update_invoice_cache.py` provide incremental updates:

- Scan existing cache, find files with missing fields
- Only re-invoke models for these files
- Merge updated results back into cache
- Useful for model upgrades, fixing empty fields, etc.

---

### Invoice Cross-Vote Mechanism

`merge_invoice_ocr.py` implements 3-engine cross-voting:

#### Voting Rules

1. **Majority consensus** — 2+ engines agree → take consensus value
2. **Priority arbitration** — No consensus → sort by field-level historical accuracy
3. **Special handling** — Invoice number takes longest value to prevent truncation, product name skips garbled text

#### Field Priority

| Field | Priority (High→Low) | Reason |
|-------|---------------------|--------|
| Invoice Number | DeepSeek → PyMuPDF → Qwen | Qwen tends to truncate 20-digit numbers |
| Invoice Date | PyMuPDF → DeepSeek → Qwen | All 100%, PyMuPDF most stable |
| Buyer Name | Qwen → DeepSeek → PyMuPDF | Qwen has strongest semantic understanding |
| Seller Name | Qwen → PyMuPDF → DeepSeek | Qwen has highest accuracy |
| Amount (excl. tax) | Qwen → DeepSeek → PyMuPDF | Qwen extracts amounts most accurately |
| Tax Amount | Qwen → DeepSeek → PyMuPDF | Qwen extracts tax most accurately |
| Total Amount | DeepSeek → PyMuPDF → Qwen | Qwen tends to confuse total amount |

#### Post-Validation

- **Amount check**: `Amount + Tax ≈ Total` (0.02 tolerance)
- **Invoice number**: 8 or 20 digit pure numbers
- **Tax ID**: 18 digit alphanumeric
- **Date format**: YYYY-MM-DD, month 01-12, day 01-31

---

### Screenshot Multi-Strategy Store Name Recognition

`extract_orders.py` and `combined_order_ocr.py` use 3 strategies to recognize store names:

| Strategy | Matching Pattern | Use Case |
|----------|------------------|----------|
| Strategy 1 | Text left of "进店逛逛" | Standard Taobao/Tmall orders |
| Strategy 2 | "天猫/淘宝 XXX旗舰店" prefix | Tmall stores without "进店逛逛" button |
| Strategy 3 | Standalone text between shipping info and product | Fallback strategy |

---

### Configuration

#### Model Selection

Modify `MODEL` variable in Ollama scripts:

```python
# ollama_invoice_ocr.py / ollama_order_ocr.py
MODEL = "lukey03/qwen3.5-9b-abliterated-vision:latest"

# deepseek_invoice_ocr.py
MODEL = "DeepSeek-OCR:latest"
```

#### EasyOCR GPU

EasyOCR auto-detects GPU. Force CPU:

```python
reader = easyocr.Reader(['ch_sim', 'en'], gpu=False)
```

---

### FAQ

#### Q: Can I use it without a GPU?

A: Yes. Methods 1/4 (PyMuPDF, EasyOCR) support CPU, slower but functional. Methods 2/3/5/6 require Ollama, GPU recommended.

#### Q: How to improve recognition accuracy?

A:
- Invoices: Use method 10 (cross-vote merge), accuracy 100%
- Screenshots: Use method 6 (EasyOCR + Qwen merge), success rate 92%
- Ensure images are clear and unobstructed
- If cache has empty fields, run `update_screenshot_cache.py` or `update_invoice_cache.py`

#### Q: What file formats are supported?

A:
- Invoices: PDF
- Screenshots: JPG, PNG, BMP

#### Q: How to update models?

A: Run `ollama pull` to update to latest version. After updating, run incremental update scripts to re-extract.

#### Q: How does the caching work?

A: Each script automatically attaches the source file's MD5 hash when saving results. On re-run, hashes are compared—only files with changed content are re-processed. Incremental update scripts can re-run only files with missing fields.

#### Q: Why can't some screenshots extract store names?

A: If the screenshot was taken after scrolling past the store name area (i.e., store name not in frame), it cannot be extracted. This is a data limitation, not a code issue.

---

### Requirements

- Python 3.10+
- NVIDIA GPU + CUDA (recommended)
- [Ollama](https://ollama.com/download) (for vision models)

### License

MIT License
