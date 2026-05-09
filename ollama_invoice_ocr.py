"""
发票OCR提取脚本 - 基于 Ollama 视觉语言模型
使用方法:
  1. 安装并启动 Ollama: https://ollama.com/download
  2. 下载模型: ollama pull minicpm-v
  3. 运行: python ollama_invoice_ocr.py
"""
import fitz  # PyMuPDF
import os
import sys
from cache_utils import load_cached_results, save_cached_results
import io
import json
import base64
import requests
import re
import csv
import time
import warnings
warnings.filterwarnings("ignore")
from pathlib import Path

sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding='utf-8')

# ============ 配置 ============
OLLAMA_URL = "http://localhost:11434/api/generate"
MODEL = "lukey03/qwen3.5-9b-abliterated-vision:latest"
SCRIPT_DIR = os.path.dirname(os.path.abspath(__file__))
PDF_FOLDER = os.path.join(SCRIPT_DIR, '原始发票')
OUTPUT_FOLDER = os.path.join(SCRIPT_DIR, '输出结果', '发票')
# 兼容：如果原始发票文件夹为空，回退到上级目录
if not os.listdir(PDF_FOLDER):
    PDF_FOLDER = os.path.dirname(SCRIPT_DIR)


def print_progress(current, total, suffix="", bar_len=30):
    pct = current / total if total > 0 else 0
    filled = int(bar_len * pct)
    bar = "#" * filled + "-" * (bar_len - filled)
    name = suffix[:25] if len(suffix) > 25 else suffix
    line = f"  [{bar}] {current}/{total}  {name}"
    sys.stdout.write(f"\r{line:<70}")
    sys.stdout.flush()
    if current == total:
        print()
DPI = 200  # PDF转图片分辨率，越高越清晰但越慢

PROMPT = """请仔细识别这张发票图片，提取以下信息并以JSON格式输出。
如果某个字段无法识别，请填空字符串。

{
  "发票类型": "发票的类型名称",
  "发票代码": "发票代码（如果有）",
  "发票号码": "发票号码",
  "开票日期": "YYYY-MM-DD格式",
  "购买方名称": "购买方/购方名称",
  "购买方纳税识别号": "购买方纳税人识别号/统一社会信用代码",
  "销售方名称": "销售方/销方名称",
  "销售方纳税识别号": "销售方纳税人识别号/统一社会信用代码",
  "商品名称": "所有商品名称，用分号分隔",
  "金额(不含税)": "不含税金额合计（纯数字）",
  "税率": "税率（如13%、1%等，免税写免税）",
  "税额": "税额合计（纯数字）",
  "价税合计": "价税合计金额（纯数字）"
}

注意：
- 金额、税额、价税合计只输出数字，不要带¥符号
- 商品名称请提取完整名称，包括*分类*具体名称
- 只输出JSON，不要其他文字"""


def pdf_page_to_image(pdf_path, page_num=0, dpi=200):
    """将PDF指定页转为base64编码的PNG图片"""
    doc = fitz.open(pdf_path)
    page = doc[page_num]
    zoom = dpi / 72
    mat = fitz.Matrix(zoom, zoom)
    pix = page.get_pixmap(matrix=mat)
    img_bytes = pix.tobytes("png")
    doc.close()
    return base64.b64encode(img_bytes).decode('utf-8')


def image_file_to_base64(img_path):
    """读取图片文件转为base64"""
    with open(img_path, 'rb') as f:
        return base64.b64encode(f.read()).decode('utf-8')


def call_ollama_vision(image_b64, prompt, model=MODEL, retries=3):
    """调用Ollama视觉模型"""
    for attempt in range(retries):
        try:
            response = requests.post(OLLAMA_URL, json={
                "model": model,
                "prompt": prompt,
                "images": [image_b64],
                "stream": False,
                "options": {
                    "temperature": 0,
                    "num_predict": 1024,
                }
            }, timeout=120)
            response.raise_for_status()
            result = response.json()
            return result.get("response", "")
        except requests.exceptions.Timeout:
            print(f"  超时，重试 ({attempt+1}/{retries})...")
            time.sleep(2)
        except Exception as e:
            print(f"  错误: {e}，重试 ({attempt+1}/{retries})...")
            time.sleep(2)
    return ""


def parse_json_response(text):
    """从模型响应中提取JSON"""
    # Try to find JSON in the response
    # Method 1: find JSON block in markdown code fence
    m = re.search(r'```(?:json)?\s*\n?(.*?)\n?```', text, re.DOTALL)
    if m:
        try:
            return json.loads(m.group(1))
        except json.JSONDecodeError:
            pass

    # Method 2: find raw JSON object
    m = re.search(r'\{[^{}]*(?:\{[^{}]*\}[^{}]*)*\}', text, re.DOTALL)
    if m:
        try:
            return json.loads(m.group(0))
        except json.JSONDecodeError:
            pass

    # Method 3: try the whole text
    try:
        return json.loads(text)
    except json.JSONDecodeError:
        pass

    return None


def process_pdf(pdf_path):
    """处理单个PDF文件"""
    filename = os.path.basename(pdf_path)
    doc = fitz.open(pdf_path)
    num_pages = len(doc)
    doc.close()

    all_results = []
    for page_num in range(num_pages):
        img_b64 = pdf_page_to_image(pdf_path, page_num, dpi=DPI)
        response_text = call_ollama_vision(img_b64, PROMPT)

        if response_text:
            info = parse_json_response(response_text)
            if info:
                info['文件名'] = filename
                info['页码'] = page_num + 1
                all_results.append(info)
            else:
                all_results.append({
                    '文件名': filename,
                    '页码': page_num + 1,
                    '发票类型': '解析失败',
                    '原始响应': response_text[:500]
                })
        else:
            print(f"  模型无响应")
            all_results.append({
                '文件名': filename,
                '页码': page_num + 1,
                '发票类型': '无响应'
            })

    return all_results


def process_image(img_path):
    """处理单个图片文件"""
    filename = os.path.basename(img_path)
    img_b64 = image_file_to_base64(img_path)
    response_text = call_ollama_vision(img_b64, PROMPT)

    if response_text:
        info = parse_json_response(response_text)
        if info:
            info['文件名'] = filename
            info['页码'] = 1
            return info
    return {'文件名': filename, '发票类型': '', '发票代码': '', '发票号码': '', '开票日期': '',
            '购买方名称': '', '购买方纳税识别号': '', '销售方名称': '', '销售方纳税识别号': '',
            '商品名称': '', '金额(不含税)': '', '税率': '', '税额': '', '价税合计': ''}


def generate_markdown(results):
    """生成Markdown报告"""
    lines = []
    lines.append('# 发票OCR提取结果（Ollama视觉模型）\n')
    lines.append(f'模型: {MODEL} | 共提取 **{len(results)}** 条记录\n')

    # Summary table
    lines.append('## 汇总表\n')
    lines.append('| 序号 | 文件名 | 发票号码 | 开票日期 | 购买方 | 销售方 | 金额 | 税率 | 税额 | 价税合计 |')
    lines.append('|------|--------|----------|----------|--------|--------|------|------|------|----------|')

    total = 0
    for i, r in enumerate(results, 1):
        amt = r.get('价税合计', '')
        try:
            total += float(amt)
        except (ValueError, TypeError):
            pass
        fname = r.get('文件名', '')[:25]
        lines.append(f'| {i} | {fname} | {r.get("发票号码","")} | {r.get("开票日期","")} | {r.get("购买方名称","")[:12]} | {r.get("销售方名称","")[:12]} | {r.get("金额(不含税)","")} | {r.get("税率","")} | {r.get("税额","")} | {r.get("价税合计","")} |')

    lines.append(f'\n**价税合计总金额: ¥{total:.2f}**\n')

    # Detailed info
    lines.append('## 详细信息\n')
    for i, r in enumerate(results, 1):
        lines.append(f'### {i}. {r.get("文件名", "")}')
        lines.append('')
        for key in ['发票类型', '发票代码', '发票号码', '开票日期',
                     '购买方名称', '购买方纳税识别号',
                     '销售方名称', '销售方纳税识别号',
                     '商品名称', '金额(不含税)', '税率', '税额', '价税合计']:
            lines.append(f'- **{key}**: {r.get(key, "")}')
        lines.append('')

    return '\n'.join(lines)


def main():
    os.makedirs(OUTPUT_FOLDER, exist_ok=True)

    # 检查已有结果（含哈希过期检测）
    json_path = os.path.join(OUTPUT_FOLDER, '发票_模型识别.json')
    cached = load_cached_results(json_path, PDF_FOLDER, ('.pdf',))
    all_files = sorted([f for f in os.listdir(PDF_FOLDER) if f.lower().endswith('.pdf')])
    missing = [f for f in all_files if f not in cached]
    if cached and not missing:
        print(f"已有结果 ({len(cached)} 条)，全部覆盖，跳过。")
        return
    if cached:
        print(f"已有 {len(cached)} 条，{len(missing)} 个新文件需处理")

    # Check Ollama is running
    try:
        resp = requests.get("http://localhost:11434/api/tags", timeout=5)
        models = [m['name'] for m in resp.json().get('models', [])]
        print(f"Ollama 运行中，可用模型: {', '.join(models)}")
        if not any(MODEL in m for m in models):
            print(f"\n警告: 模型 '{MODEL}' 未找到！")
            print(f"请运行: ollama pull {MODEL}")
            print(f"或修改脚本中的 MODEL 变量为已有模型\n")
            # Check if any vision model is available
            vision_models = [m for m in models if any(v in m.lower() for v in ['vision', 'minicpm', 'llava', 'moondream'])]
            if vision_models:
                print(f"检测到视觉模型: {', '.join(vision_models)}")
                print(f"可将 MODEL 改为: {vision_models[0]}")
            return
    except Exception as e:
        print(f"无法连接Ollama: {e}")
        print("请确保Ollama已启动: ollama serve")
        return

    # Collect files
    pdf_files = sorted([f for f in os.listdir(PDF_FOLDER) if f.lower().endswith('.pdf')])
    img_files = sorted([f for f in os.listdir(PDF_FOLDER)
                        if f.lower().endswith(('.jpg', '.jpeg', '.png', '.bmp'))])
    total_files = len(pdf_files) + len(img_files)
    print(f"\n找到 {len(pdf_files)} 个PDF, {len(img_files)} 个图片, 共 {total_files} 个文件\n")

    # 检测GPU显存
    import subprocess
    try:
        result = subprocess.run(
            ['nvidia-smi', '--query-gpu=name,memory.total,memory.used,memory.free', '--format=csv,noheader,nounits'],
            capture_output=True, text=True, timeout=5
        )
        if result.returncode == 0:
            parts = result.stdout.strip().split(',')
            gpu_name = parts[0].strip()
            total_mb = int(parts[1].strip())
            used_mb = int(parts[2].strip())
            free_mb = int(parts[3].strip())
            print(f"GPU: {gpu_name} ({total_mb//1024}GB)")
            print(f"显存: {used_mb}MB/{total_mb}MB 可用:{free_mb}MB")
        else:
            total_mb = 0
    except:
        total_mb = 0

    num_workers = 4 if total_mb >= 12000 else (3 if total_mb >= 8000 else 2)
    print(f"并发数: {num_workers}\n")

    from concurrent.futures import ThreadPoolExecutor, as_completed

    def process_one_pdf(args):
        f, path = args
        try:
            return process_pdf(path)
        except:
            return [{'文件名': f, '发票类型': ''}]

    def process_one_img(args):
        f, path = args
        try:
            return process_image(path)
        except:
            return {'文件名': f, '发票类型': ''}

    results = []
    done_count = [0]

    # PDF处理
    with ThreadPoolExecutor(max_workers=num_workers) as executor:
        futures = {executor.submit(process_one_pdf, (f, os.path.join(PDF_FOLDER, f))): f
                   for f in pdf_files}
        for future in as_completed(futures):
            f = futures[future]
            done_count[0] += 1
            print_progress(done_count[0], total_files, suffix=f)
            results.extend(future.result())

    # 图片处理
    with ThreadPoolExecutor(max_workers=num_workers) as executor:
        futures = {executor.submit(process_one_img, (f, os.path.join(PDF_FOLDER, f))): f
                   for f in img_files}
        for future in as_completed(futures):
            f = futures[future]
            done_count[0] += 1
            print_progress(done_count[0], total_files, suffix=f)
            results.append(future.result())

    # Save results
    if results:
        # JSON (with hashes)
        json_path = os.path.join(OUTPUT_FOLDER, '发票_模型识别.json')
        save_cached_results(results, json_path, PDF_FOLDER)
        print(f"Saved JSON: {json_path}")

        # CSV
        csv_path = os.path.join(OUTPUT_FOLDER, '发票_模型识别.csv')
        keys = ['文件名', '发票类型', '发票代码', '发票号码', '开票日期',
                '购买方名称', '购买方纳税识别号', '销售方名称', '销售方纳税识别号',
                '商品名称', '金额(不含税)', '税率', '税额', '价税合计']
        with open(csv_path, 'w', encoding='utf-8-sig', newline='') as f:
            writer = csv.DictWriter(f, fieldnames=keys, extrasaction='ignore')
            writer.writeheader()
            writer.writerows(results)
        print(f"Saved CSV:  {csv_path}")

        # Markdown
        md_path = os.path.join(OUTPUT_FOLDER, '发票_模型识别.md')
        md_content = generate_markdown(results)
        with open(md_path, 'w', encoding='utf-8') as f:
            f.write(md_content)
        print(f"Saved MD:   {md_path}")

    print(f"\n完成！共处理 {len(results)} 条记录")


if __name__ == '__main__':
    main()
