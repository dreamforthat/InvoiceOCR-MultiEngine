"""
发票OCR提取脚本 - DeepSeek-OCR 文字提取 + Python 正则解析
使用方法:
  1. ollama pull DeepSeek-OCR
  2. python deepseek_invoice_ocr.py
"""
import fitz
import os
import sys
import io
from cache_utils import load_cached_results, save_cached_results
import json
import base64
import requests
import re
import csv
import time
import warnings
warnings.filterwarnings("ignore")

sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding='utf-8')

# ============ 配置 ============
OLLAMA_URL = "http://localhost:11434/api/generate"
MODEL = "DeepSeek-OCR:latest"
SCRIPT_DIR = os.path.dirname(os.path.abspath(__file__))
PDF_FOLDER = os.path.join(SCRIPT_DIR, '原始发票')
OUTPUT_FOLDER = os.path.join(SCRIPT_DIR, '输出结果', '发票')
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


def pdf_page_to_image(pdf_path, page_num=0):
    doc = fitz.open(pdf_path)
    page = doc[page_num]
    pix = page.get_pixmap(matrix=fitz.Matrix(1, 1))
    img_bytes = pix.tobytes("png")
    doc.close()
    return base64.b64encode(img_bytes).decode('utf-8')


def call_ollama(image_b64, prompt, retries=3):
    for attempt in range(retries):
        try:
            response = requests.post(OLLAMA_URL, json={
                "model": MODEL,
                "prompt": prompt,
                "images": [image_b64],
                "stream": False,
                "options": {"temperature": 0, "num_predict": 2048}
            }, timeout=180)
            response.raise_for_status()
            return response.json().get("response", "")
        except Exception as e:
            if attempt < retries - 1:
                time.sleep(2)
    return ""


def parse_invoice_text(text, filename=''):
    info = {
        '文件名': filename,
        '发票类型': '',
        '发票代码': '',
        '发票号码': '',
        '开票日期': '',
        '购买方名称': '',
        '购买方纳税识别号': '',
        '销售方名称': '',
        '销售方纳税识别号': '',
        '商品名称': '',
        '金额(不含税)': '',
        '税率': '',
        '税额': '',
        '价税合计': '',
    }

    text_norm = re.sub(r'\n{3,}', '\n\n', text)

    # 发票类型
    if '电子发票（普通发票）' in text:
        info['发票类型'] = '电子发票（普通发票）'
    elif '浙江通用' in text:
        info['发票类型'] = '浙江通用（电子）发票'
    else:
        info['发票类型'] = '增值税电子普通发票'

    # 发票代码
    m = re.search(r'发票代码[：:]\s*(\d{10,12})', text)
    if m: info['发票代码'] = m.group(1)

    # 发票号码
    m = re.search(r'发票号码[：:]\s*(\d{8,20})', text)
    if m: info['发票号码'] = m.group(1)

    # 开票日期
    m = re.search(r'开票日期[：:]\s*(\d{4})\s*年\s*(\d{2})\s*月\s*(\d{2})\s*日', text)
    if m: info['开票日期'] = f'{m.group(1)}-{m.group(2)}-{m.group(3)}'

    # 名称提取 - 新旧两种格式
    name_matches = list(re.finditer(r'称[：:]\s*(.+)', text_norm))

    if '购买方信息' in text:
        # 新格式: 购买方信息 ... 名称：XXX
        for m in name_matches:
            line = m.group(1).split('\n')[0].strip()
            if '纳税' in line or '识别' in line or '代码' in line:
                continue
            pos = m.start()
            before = text_norm[:pos]
            if before.rfind('销售方信息') > before.rfind('购买方信息'):
                if not info['销售方名称']:
                    info['销售方名称'] = line
            else:
                if not info['购买方名称']:
                    info['购买方名称'] = line
    else:
        # 旧格式: 购...名...称：XXX
        names = []
        for m in name_matches:
            line = m.group(1).split('\n')[0].strip()
            line = re.sub(r'纳税人.*', '', line).strip()
            line = re.sub(r'地址.*', '', line).strip()
            if line and '纳税' not in line and '识别' not in line:
                names.append(line)
        if len(names) >= 2:
            info['购买方名称'] = names[0]
            info['销售方名称'] = names[1]
        elif len(names) == 1:
            info['购买方名称'] = names[0]

    # 纳税人识别号
    tax_ids = re.findall(r'(?:纳税人识别号|统一社会信用代码)[/／]?(?:纳税人识别号)?[：:]\s*([A-Za-z0-9]+)', text)
    if len(tax_ids) >= 2:
        info['购买方纳税识别号'] = tax_ids[0]
        info['销售方纳税识别号'] = tax_ids[1]
    elif len(tax_ids) == 1:
        info['购买方纳税识别号'] = tax_ids[0]

    # 商品名称
    items = re.findall(r'\*([^*\n]+)\*([^\n*]+)', text)
    if items:
        info['商品名称'] = '; '.join([f'{cat}{name}' for cat, name in items])

    # 金额
    amounts = re.findall(r'[¥￥]\s*([\d,]+\.?\d*)', text)
    if len(amounts) >= 3:
        info['金额(不含税)'] = amounts[0].replace(',', '')
        info['税额'] = amounts[1].replace(',', '')
        info['价税合计'] = amounts[2].replace(',', '')
    elif len(amounts) == 2:
        info['金额(不含税)'] = amounts[0].replace(',', '')
        info['价税合计'] = amounts[1].replace(',', '')

    # 税率
    tax_rates = set()
    for m in re.finditer(r'(\d+)%', text):
        tax_rates.add(m.group(1))
    info['税率'] = '/'.join(sorted(tax_rates)) + '%' if tax_rates else '免税'

    return info


def process_pdf(pdf_path):
    filename = os.path.basename(pdf_path)
    img_b64 = pdf_page_to_image(pdf_path)
    text = call_ollama(img_b64, 'Extract the text in the image.')
    if text:
        return parse_invoice_text(text, filename)
    return {'文件名': filename, '发票类型': 'FAILED'}


def generate_markdown(results):
    lines = []
    lines.append('# 发票OCR提取结果（DeepSeek-OCR + 正则解析）\n')
    lines.append(f'模型: {MODEL} | 共提取 **{len(results)}** 条记录\n')

    lines.append('## 汇总表\n')
    lines.append('| 序号 | 文件名 | 发票类型 | 发票号码 | 开票日期 | 购买方 | 销售方 | 金额 | 税率 | 税额 | 价税合计 |')
    lines.append('|------|--------|----------|----------|----------|--------|--------|------|------|------|----------|')

    total = 0
    for i, r in enumerate(results, 1):
        amt = r.get('价税合计', '')
        try:
            total += float(amt)
        except (ValueError, TypeError):
            pass
        fname = r.get('文件名', '')[:25]
        lines.append(f'| {i} | {fname} | {r.get("发票类型","")[:10]} | {r.get("发票号码","")} | {r.get("开票日期","")} | {r.get("购买方名称","")[:12]} | {r.get("销售方名称","")[:12]} | {r.get("金额(不含税)","")} | {r.get("税率","")} | {r.get("税额","")} | {r.get("价税合计","")} |')

    lines.append(f'\n**价税合计总金额: ¥{total:.2f}**\n')

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
    json_path = os.path.join(OUTPUT_FOLDER, '发票_deepseek混合.json')
    cached = load_cached_results(json_path, PDF_FOLDER, ('.pdf',))
    all_files = sorted([f for f in os.listdir(PDF_FOLDER) if f.lower().endswith('.pdf')])
    missing = [f for f in all_files if f not in cached]
    if cached and not missing:
        print(f"Cached result found ({len(cached)} records), all files covered. Skipping.")
        return
    if cached:
        print(f"Cached: {len(cached)} valid + {len(missing)} new files to process")
    results = list(cached.values())
    pdf_files = missing

    # Check Ollama
    try:
        resp = requests.get("http://localhost:11434/api/tags", timeout=5)
        models = [m['name'] for m in resp.json().get('models', [])]
        print(f"Ollama: {', '.join(models)}")
        if not any(MODEL in m for m in models):
            print(f"\nModel '{MODEL}' not found! Run: ollama pull {MODEL}")
            return
    except Exception as e:
        print(f"Cannot connect to Ollama: {e}")
        return
    total_files = len(pdf_files)
    print(f"\nFound {total_files} PDF files\n")

    results = []
    for i, f in enumerate(pdf_files, 1):
        print_progress(i, total_files, suffix=f)
        path = os.path.join(PDF_FOLDER, f)
        try:
            info = process_pdf(path)
            results.append(info)
        except Exception as e:
            results.append({'文件名': f, '发票类型': f'ERROR: {e}',
                '发票代码': '', '发票号码': '', '开票日期': '',
                '购买方名称': '', '购买方纳税识别号': '',
                '销售方名称': '', '销售方纳税识别号': '',
                '商品名称': '', '金额(不含税)': '', '税率': '', '税额': '', '价税合计': ''})

    # Save JSON (with hashes)
    json_path = os.path.join(OUTPUT_FOLDER, '发票_deepseek混合.json')
    save_cached_results(results, json_path, PDF_FOLDER)
    print(f'\nSaved JSON: {json_path}')

    # Save CSV
    csv_path = os.path.join(OUTPUT_FOLDER, '发票_deepseek混合.csv')
    keys = ['文件名', '发票类型', '发票代码', '发票号码', '开票日期',
            '购买方名称', '购买方纳税识别号', '销售方名称', '销售方纳税识别号',
            '商品名称', '金额(不含税)', '税率', '税额', '价税合计']
    with open(csv_path, 'w', encoding='utf-8-sig', newline='') as f:
        writer = csv.DictWriter(f, fieldnames=keys, extrasaction='ignore')
        writer.writeheader()
        writer.writerows(results)
    print(f'Saved CSV:  {csv_path}')

    # Save Markdown
    md_path = os.path.join(OUTPUT_FOLDER, '发票_deepseek混合.md')
    with open(md_path, 'w', encoding='utf-8') as f:
        f.write(generate_markdown(results))
    print(f'Saved MD:   {md_path}')

    print(f"\nDone! {len(results)} records")


if __name__ == '__main__':
    main()
