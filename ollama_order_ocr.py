"""
淘宝/天猫订单截图信息提取 - 基于 Ollama 视觉语言模型
使用方法:
  1. ollama pull minicpm-v
  2. python ollama_order_ocr.py
"""
import os
from cache_utils import load_cached_results, save_cached_results
import sys
import io
import json
import re
import csv
import base64
import requests
import time
import warnings
warnings.filterwarnings("ignore")

sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding='utf-8')

# ============ 配置 ============
OLLAMA_URL = "http://localhost:11434/api/generate"
MODEL = "lukey03/qwen3.5-9b-abliterated-vision:latest"
SCRIPT_DIR = os.path.dirname(os.path.abspath(__file__))
IMG_FOLDER = os.path.join(SCRIPT_DIR, '原始截图')
OUTPUT_FOLDER = os.path.join(SCRIPT_DIR, '输出结果', '截图')
# 兼容：如果原始截图文件夹为空，回退到上级目录
if not os.listdir(IMG_FOLDER):
    IMG_FOLDER = os.path.dirname(SCRIPT_DIR)


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


def get_vram_info():
    """通过nvidia-smi获取真实GPU显存信息"""
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
            return gpu_name, total_mb, used_mb, free_mb
    except Exception:
        pass
    return None, 0, 0, 0

PROMPT = """Extract the following information from this Taobao/Tmall order screenshot and output as JSON.
If a field cannot be identified, use an empty string.

{
  "店铺名称": "store name",
  "交易日期": "date from 订单信息, YYYY-MM-DD format",
  "交易唯一编号": "order number from 订单编号 (digits only)",
  "优惠后金额": "actual payment amount (number only, no ¥ symbol)"
}

CRITICAL amount extraction rules:
1. Find the "实付款" line
2. This line has TWO numbers: left side is "共减¥X" (discount), right side is "¥Y" (actual payment)
3. You MUST extract the RIGHT side number Y, NOT the left side X
4. Examples:
   - "实付款 共减¥10.5  ¥31.3" → amount = 31.3 (NOT 10.5)
   - "实付款 共减¥1.93  ¥39.47" → amount = 39.47 (NOT 1.93)
   - "实付款 共减¥2.04  ¥65.16" → amount = 65.16 (NOT 2.04)

Output ONLY the JSON, no other text."""


def image_to_base64(img_path):
    with open(img_path, 'rb') as f:
        return base64.b64encode(f.read()).decode('utf-8')


def call_ollama(image_b64, prompt, model=MODEL, retries=3):
    for attempt in range(retries):
        try:
            resp = requests.post(OLLAMA_URL, json={
                "model": model,
                "prompt": prompt,
                "images": [image_b64],
                "stream": False,
                "options": {"temperature": 0, "num_predict": 512}
            }, timeout=120)
            resp.raise_for_status()
            return resp.json().get("response", "")
        except Exception as e:
            print(f"  重试 ({attempt+1}/{retries}): {e}")
            time.sleep(2)
    return ""


def parse_json(text):
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


def process_image(img_path):
    filename = os.path.basename(img_path)
    img_b64 = image_to_base64(img_path)
    resp = call_ollama(img_b64, PROMPT)

    if resp:
        info = parse_json(resp)
        if info:
            info['文件名'] = filename
            return info
    return {'文件名': filename, '店铺名称': '', '交易日期': '', '交易唯一编号': '', '优惠后金额': ''}


def generate_markdown(results):
    lines = []
    lines.append('# 订单截图信息提取结果（Ollama视觉模型）\n')
    lines.append(f'模型: {MODEL} | 共提取 **{len(results)}** 条订单记录\n')

    lines.append('## 汇总表\n')
    lines.append('| 序号 | 文件名 | 店铺名称 | 交易日期 | 交易唯一编号 | 优惠后金额 |')
    lines.append('|------|--------|----------|----------|-------------|------------|')

    total = 0
    for i, r in enumerate(results, 1):
        amt = r.get('优惠后金额', '')
        try: total += float(amt.replace(',', ''))
        except: pass
        lines.append(f'| {i} | {r.get("文件名","")[:25]} | {r.get("店铺名称","")} | {r.get("交易日期","")} | {r.get("交易唯一编号","")} | ¥{r.get("优惠后金额","")} |')

    lines.append(f'\n**优惠后金额总计: ¥{total:.2f}**\n')

    lines.append('## 详细信息\n')
    for i, r in enumerate(results, 1):
        lines.append(f'### {i}. {r.get("文件名","")}')
        lines.append('')
        for key in ['店铺名称', '交易日期', '交易唯一编号', '优惠后金额']:
            val = r.get(key, '')
            if key == '优惠后金额' and val: val = f'¥{val}'
            lines.append(f'- **{key}**: {val}')
        lines.append('')

    return '\n'.join(lines)


def main():
    os.makedirs(OUTPUT_FOLDER, exist_ok=True)

    # 检查已有结果（含哈希过期检测）
    IMG_EXT = ('.jpg', '.jpeg', '.png', '.bmp')
    json_path = os.path.join(OUTPUT_FOLDER, '截图_模型识别.json')
    cached = load_cached_results(json_path, IMG_FOLDER, IMG_EXT)
    all_files = sorted([f for f in os.listdir(IMG_FOLDER) if f.lower().endswith(IMG_EXT)])
    missing = [f for f in all_files if f not in cached]
    if cached and not missing:
        print(f"已有结果 ({len(cached)} 条)，全部覆盖，跳过。")
        return
    if cached:
        print(f"已有 {len(cached)} 条，{len(missing)} 个新文件需处理")

    # Check Ollama
    try:
        resp = requests.get("http://localhost:11434/api/tags", timeout=5)
        models = [m['name'] for m in resp.json().get('models', [])]
        print(f'Ollama 运行中，可用模型: {", ".join(models)}')
        if not any(MODEL in m for m in models):
            print(f'\n模型 "{MODEL}" 未找到！请运行: ollama pull {MODEL}\n')
            return
    except Exception as e:
        print(f'无法连接Ollama: {e}')
        return

    img_files = sorted([f for f in os.listdir(IMG_FOLDER)
                        if f.lower().endswith(('.jpg', '.jpeg', '.png', '.bmp'))])
    total_files = len(img_files)
    print(f'\n找到 {total_files} 张截图\n')

    if not img_files:
        print('没有找到图片文件，请将截图放入 原始截图 文件夹')
        return

    # 检测GPU
    gpu_name, total_mb, used_mb, free_mb = get_vram_info()
    if gpu_name:
        print(f'GPU: {gpu_name} ({total_mb//1024}GB) 显存: {used_mb}MB/{total_mb}MB')
    num_workers = 4 if total_mb >= 12000 else (3 if total_mb >= 8000 else 2)
    print(f'并发数: {num_workers}\n')

    from concurrent.futures import ThreadPoolExecutor, as_completed

    def process_one(args):
        f, path = args
        try:
            info = process_image(path)
        except Exception as e:
            info = {'文件名': f, '店铺名称': '', '交易日期': '', '交易唯一编号': '', '优惠后金额': ''}
        return info

    results = [None] * total_files
    done_count = [0]

    with ThreadPoolExecutor(max_workers=num_workers) as executor:
        tasks = [(f, os.path.join(IMG_FOLDER, f)) for f in img_files]
        futures = {executor.submit(process_one, t): i for i, t in enumerate(tasks)}
        for future in as_completed(futures):
            idx = futures[future]
            results[idx] = future.result()
            done_count[0] += 1
            print_progress(done_count[0], total_files, suffix=results[idx].get('文件名', ''))

    if results:
        json_path = os.path.join(OUTPUT_FOLDER, '截图_模型识别.json')
        save_cached_results(results, json_path, IMG_FOLDER)
        print(f'Saved JSON: {json_path}')

        csv_path = os.path.join(OUTPUT_FOLDER, '截图_模型识别.csv')
        keys = ['文件名', '店铺名称', '交易日期', '交易唯一编号', '优惠后金额']
        with open(csv_path, 'w', encoding='utf-8-sig', newline='') as f:
            writer = csv.DictWriter(f, fieldnames=keys, extrasaction='ignore')
            writer.writeheader()
            writer.writerows(results)
        print(f'Saved CSV:  {csv_path}')

        md_path = os.path.join(OUTPUT_FOLDER, '截图_模型识别.md')
        with open(md_path, 'w', encoding='utf-8') as f:
            f.write(generate_markdown(results))
        print(f'Saved MD:   {md_path}')

    print(f'\n完成！共 {len(results)} 条记录')


if __name__ == '__main__':
    main()
