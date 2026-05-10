"""
增量更新发票识别缓存 — 重跑 DeepSeek 和 Qwen 有缺失字段的文件
"""
import os
import sys
import io
import json
import re
import base64
import fitz
import requests
import time
import warnings
warnings.filterwarnings("ignore")

sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding='utf-8')

SCRIPT_DIR = os.path.dirname(os.path.abspath(__file__))
PDF_FOLDER = os.path.join(SCRIPT_DIR, '原始发票')
OUTPUT_FOLDER = os.path.join(SCRIPT_DIR, '输出结果', '发票')

OLLAMA_URL = "http://localhost:11434/api/generate"
DEEPSEEK_MODEL = "DeepSeek-OCR:latest"
QWEN_MODEL = "lukey03/qwen3.5-9b-abliterated-vision:latest"

INVOICE_PROMPT = """请仔细识别这张发票图片，提取以下信息并以JSON格式输出。
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


def pdf_to_image_b64(pdf_path, dpi=200):
    doc = fitz.open(pdf_path)
    page = doc[0]
    zoom = dpi / 72
    pix = page.get_pixmap(matrix=fitz.Matrix(zoom, zoom))
    img_bytes = pix.tobytes("png")
    doc.close()
    return base64.b64encode(img_bytes).decode('utf-8')


def img_to_image_b64(img_path):
    with open(img_path, 'rb') as f:
        return base64.b64encode(f.read()).decode('utf-8')


def call_ollama(image_b64, prompt, model, retries=3):
    for attempt in range(retries):
        try:
            response = requests.post(OLLAMA_URL, json={
                "model": model,
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


def parse_json_response(text):
    m = re.search(r'```(?:json)?\s*\n?(.*?)\n?```', text, re.DOTALL)
    if m:
        try: return json.loads(m.group(1))
        except: pass
    m = re.search(r'\{[^{}]*(?:\{[^{}]*\}[^{}]*)*\}', text, re.DOTALL)
    if m:
        try: return json.loads(m.group(0))
        except: pass
    try: return json.loads(text)
    except: return None


def parse_invoice_text(text, filename=''):
    """DeepSeek 专用正则解析"""
    info = {
        '文件名': filename, '发票类型': '', '发票代码': '', '发票号码': '',
        '开票日期': '', '购买方名称': '', '购买方纳税识别号': '',
        '销售方名称': '', '销售方纳税识别号': '', '商品名称': '',
        '金额(不含税)': '', '税率': '', '税额': '', '价税合计': '',
    }
    text_norm = re.sub(r'\n{3,}', '\n\n', text)

    if '电子发票（普通发票）' in text:
        info['发票类型'] = '电子发票（普通发票）'
    elif '浙江通用' in text:
        info['发票类型'] = '浙江通用（电子）发票'
    else:
        info['发票类型'] = '增值税电子普通发票'

    m = re.search(r'发票代码[：:]\s*(\d{10,12})', text)
    if m: info['发票代码'] = m.group(1)
    m = re.search(r'发票号码[：:]\s*(\d{8,20})', text)
    if m: info['发票号码'] = m.group(1)
    m = re.search(r'开票日期[：:]\s*(\d{4})\s*年\s*(\d{2})\s*月\s*(\d{2})\s*日', text)
    if m: info['开票日期'] = f'{m.group(1)}-{m.group(2)}-{m.group(3)}'

    name_matches = list(re.finditer(r'称[：:]\s*(.+)', text_norm))
    if '购买方信息' in text:
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

    tax_ids = re.findall(r'(?:纳税人识别号|统一社会信用代码)[/／]?(?:纳税人识别号)?[：:]\s*([A-Za-z0-9]+)', text)
    if len(tax_ids) >= 2:
        info['购买方纳税识别号'] = tax_ids[0]
        info['销售方纳税识别号'] = tax_ids[1]
    elif len(tax_ids) == 1:
        info['购买方纳税识别号'] = tax_ids[0]

    items = re.findall(r'\*([^*\n]+)\*([^\n*]+)', text)
    if items:
        info['商品名称'] = '; '.join([f'{cat}{name}' for cat, name in items])

    amounts = re.findall(r'[¥￥]\s*([\d,]+\.?\d*)', text)
    if len(amounts) >= 3:
        info['金额(不含税)'] = amounts[0].replace(',', '')
        info['税额'] = amounts[1].replace(',', '')
        info['价税合计'] = amounts[2].replace(',', '')
    elif len(amounts) == 2:
        info['金额(不含税)'] = amounts[0].replace(',', '')
        info['价税合计'] = amounts[1].replace(',', '')

    tax_rates = set()
    for m in re.finditer(r'(\d+)%', text):
        tax_rates.add(m.group(1))
    info['税率'] = '/'.join(sorted(tax_rates)) + '%' if tax_rates else '免税'

    return info


def main():
    os.makedirs(OUTPUT_FOLDER, exist_ok=True)

    # 检查 Qwen 缓存
    qw_path = os.path.join(OUTPUT_FOLDER, '发票_模型识别.json')
    with open(qw_path, 'r', encoding='utf-8') as f:
        qw_data = json.load(f)

    qw_by_fn = {r['文件名']: r for r in qw_data}
    all_pdf = sorted([f for f in os.listdir(PDF_FOLDER) if f.lower().endswith('.pdf')])

    # Qwen: 找缺失字段的文件
    qw_need = []
    for fn in all_pdf:
        r = qw_by_fn.get(fn, {})
        missing = [f for f in ['发票号码', '开票日期', '购买方名称', '销售方名称', '金额(不含税)', '税额', '价税合计'] if not r.get(f)]
        if missing:
            qw_need.append((fn, r, missing))

    # DeepSeek 缓存
    ds_path = os.path.join(OUTPUT_FOLDER, '发票_deepseek混合.json')
    with open(ds_path, 'r', encoding='utf-8') as f:
        ds_data = json.load(f)
    ds_by_fn = {r['文件名']: r for r in ds_data}

    ds_need = []
    for fn in all_pdf:
        r = ds_by_fn.get(fn, {})
        missing = [f for f in ['发票号码', '开票日期', '购买方名称', '销售方名称', '金额(不含税)', '税额', '价税合计'] if not r.get(f)]
        if missing:
            ds_need.append((fn, r, missing))

    print(f"Qwen 需重跑: {len(qw_need)} 个文件")
    print(f"DeepSeek 需重跑: {len(ds_need)} 个文件\n")

    # 重跑 Qwen
    if qw_need:
        print("=== 重跑 Qwen ===")
        for i, (fn, old_r, missing) in enumerate(qw_need, 1):
            src = os.path.join(PDF_FOLDER, fn)
            print(f"[{i}/{len(qw_need)}] {fn} (缺: {missing})...", end=" ", flush=True)

            if fn.lower().endswith('.pdf'):
                img_b64 = pdf_to_image_b64(src)
            else:
                img_b64 = img_to_image_b64(src)

            resp = call_ollama(img_b64, INVOICE_PROMPT, QWEN_MODEL)
            if resp:
                info = parse_json_response(resp)
                if info:
                    updated = False
                    for field in missing:
                        if info.get(field):
                            old_r[field] = info[field]
                            updated = True
                    if updated:
                        print(f"OK")
                    else:
                        print("无新数据")
                else:
                    print("JSON解析失败")
            else:
                print("Qwen无响应")

        with open(qw_path, 'w', encoding='utf-8') as f:
            json.dump(qw_data, f, ensure_ascii=False, indent=2)
        print(f"已保存 Qwen 缓存\n")

    # 重跑 DeepSeek
    if ds_need:
        print("=== 重跑 DeepSeek ===")
        for i, (fn, old_r, missing) in enumerate(ds_need, 1):
            src = os.path.join(PDF_FOLDER, fn)
            print(f"[{i}/{len(ds_need)}] {fn} (缺: {missing})...", end=" ", flush=True)

            img_b64 = pdf_to_image_b64(src)
            resp = call_ollama(img_b64, 'Extract the text in the image.', DEEPSEEK_MODEL)
            if resp:
                info = parse_invoice_text(resp, fn)
                updated = False
                for field in missing:
                    if info.get(field):
                        old_r[field] = info[field]
                        updated = True
                if updated:
                    print(f"OK")
                else:
                    print("无新数据")
            else:
                print("DeepSeek无响应")

        with open(ds_path, 'w', encoding='utf-8') as f:
            json.dump(ds_data, f, ensure_ascii=False, indent=2)
        print(f"已保存 DeepSeek 缓存\n")

    print("完成！")


if __name__ == '__main__':
    main()
