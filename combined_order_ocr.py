"""
截图订单提取 - EasyOCR + Qwen 模型合并方案
先跑 EasyOCR，再跑 Qwen 模型，合并取最优结果
"""
import os
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
os.environ["TF_CPP_MIN_LOG_LEVEL"] = "3"
os.environ["TORCH_CPP_LOG_LEVEL"] = "ERROR"
import easyocr
from PIL import Image
import numpy as np

sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding='utf-8')

SCRIPT_DIR = os.path.dirname(os.path.abspath(__file__))
IMG_FOLDER = os.path.join(SCRIPT_DIR, '原始截图')
OUTPUT_FOLDER = os.path.join(SCRIPT_DIR, '输出结果', '截图')
if not os.listdir(IMG_FOLDER):
    IMG_FOLDER = os.path.dirname(SCRIPT_DIR)

# ============ Qwen Config ============
OLLAMA_URL = "http://localhost:11434/api/generate"
QWEN_MODEL = "lukey03/qwen3.5-9b-abliterated-vision:latest"

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

Output ONLY the JSON, no other text."""


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


# ============ EasyOCR Part ============

def extract_text_from_image(img_path, reader):
    img = Image.open(img_path)
    img_array = np.array(img)
    result = reader.readtext(img_array, detail=1)
    texts = []
    for bbox, text, conf in result:
        y_center = (bbox[0][1] + bbox[2][1]) / 2
        x_center = (bbox[0][0] + bbox[2][0]) / 2
        texts.append({'text': text.strip(), 'y': y_center, 'x': x_center, 'conf': conf})
    texts.sort(key=lambda t: t['y'])
    return texts


def find_amount_after_discount(texts):
    for i, item in enumerate(texts):
        if '实付款' in item['text']:
            shifu_y = item['y']
            shifu_x = item['x']
            best = None
            for t in texts:
                if t is item:
                    continue
                if abs(t['y'] - shifu_y) < 60 and t['x'] > shifu_x + 400:
                    m = re.search(r'[\¥￥半]?\s*(\d+\.?\d+)', t['text'])
                    if m:
                        val = float(m.group(1))
                        if val > 1:
                            if best is None or t['x'] > best[0]:
                                best = (t['x'], m.group(1))
            if best:
                return best[1]
    return ''


def parse_order_easyocr(filename, texts):
    info = {'文件名': filename, '店铺名称': '', '交易日期': '', '交易唯一编号': '', '优惠后金额': ''}

    # 1. 店铺名称
    for i, item in enumerate(texts):
        if '进店' in item['text'] and '逛' in item['text']:
            candidates = []
            for j in range(i-1, -1, -1):
                prev = texts[j]
                if abs(prev['y'] - item['y']) < 40 and prev['x'] < item['x']:
                    name = prev['text'].strip()
                    name = re.sub(r'\s*>.*', '', name).strip()
                    if (len(name) > 1
                        and name not in ('天猫', '淘宝', '天猫超市')
                        and '地址' not in name and '洪' not in name
                        and '86-' not in name and '迎宾' not in name):
                        candidates.append(name)
            if candidates:
                info['店铺名称'] = candidates[-1]
            break

    # 2. 交易日期
    for item in texts:
        m = re.search(r'订单信息\s*(\d{4}[-/]\d{2}[-/]\d{2})', item['text'])
        if m:
            info['交易日期'] = m.group(1)
            break
        if '订单信息' in item['text']:
            m = re.search(r'(\d{4}[-/]\d{2}[-/]\d{2})', item['text'])
            if m:
                info['交易日期'] = m.group(1)
                break

    # 3. 交易唯一编号 (多策略)
    for i, item in enumerate(texts):
        if '订单编号' in item['text'] or '订单号' in item['text']:
            m = re.search(r'订单编号?\s*(\d{10,})', item['text'])
            if m:
                info['交易唯一编号'] = m.group(1)
                break
            order_y = item['y']
            best = None
            for j, next_item in enumerate(texts):
                if j == i: continue
                if abs(next_item['y'] - order_y) < 40 and next_item['x'] > item['x']:
                    m = re.search(r'(\d{10,})', next_item['text'])
                    if m:
                        dist = next_item['x'] - item['x']
                        if best is None or dist < best[0]:
                            best = (dist, m.group(1))
            if best:
                info['交易唯一编号'] = best[1]
                break
            for next_item in texts:
                if abs(next_item['y'] - order_y) < 20:
                    m = re.search(r'(\d{15,})', next_item['text'])
                    if m:
                        info['交易唯一编号'] = m.group(1)
                        break
            if info['交易唯一编号']:
                break

    if not info['交易唯一编号']:
        for i, item in enumerate(texts):
            if '订单信息' in item['text'] or '订单编号' in item['text']:
                order_y = item['y']
                for j in range(max(0, i-3), min(len(texts), i+10)):
                    t = texts[j]
                    if abs(t['y'] - order_y) < 150:
                        m = re.search(r'(\d{15,})', t['text'])
                        if m:
                            info['交易唯一编号'] = m.group(1)
                            break
                if info['交易唯一编号']:
                    break

    if not info['交易唯一编号']:
        for i, item in enumerate(texts):
            if '订单' in item['text']:
                order_y = item['y']
                for j, t in enumerate(texts):
                    if j == i: continue
                    if abs(t['y'] - order_y) < 50:
                        m = re.search(r'(\d{15,})', t['text'])
                        if m:
                            info['交易唯一编号'] = m.group(1)
                            break
                if info['交易唯一编号']:
                    break

    # 4. 优惠后金额
    info['优惠后金额'] = find_amount_after_discount(texts)

    return info


# ============ Qwen Part ============

def image_to_base64(img_path):
    with open(img_path, 'rb') as f:
        return base64.b64encode(f.read()).decode('utf-8')


def call_qwen(image_b64, prompt, retries=3):
    for attempt in range(retries):
        try:
            resp = requests.post(OLLAMA_URL, json={
                "model": QWEN_MODEL, "prompt": prompt, "images": [image_b64],
                "stream": False, "options": {"temperature": 0, "num_predict": 512}
            }, timeout=120)
            resp.raise_for_status()
            return resp.json().get("response", "")
        except Exception as e:
            if attempt < retries - 1:
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


def parse_order_qwen(filename, img_path):
    img_b64 = image_to_base64(img_path)
    resp = call_qwen(img_b64, PROMPT)
    if resp:
        info = parse_json(resp)
        if info:
            info['文件名'] = filename
            return info
    return {'文件名': filename, '店铺名称': '', '交易日期': '', '交易唯一编号': '', '优惠后金额': ''}


# ============ Merge ============

def sv(v):
    return str(v).strip() if v is not None else ''


def merge_results(easyocr_result, qwen_result):
    """合并策略：各字段取最优来源
    - 店铺名称：Qwen 优先（复杂店名识别更强）
    - 交易日期：EasyOCR 优先（Qwen 容易混淆订单日期和成交时间）
    - 交易唯一编号：EasyOCR 优先（已优化，准确率高）
    - 优惠后金额：取并集（EasyOCR 为主，Qwen 补缺失）
    """
    merged = {'文件名': easyocr_result.get('文件名', qwen_result.get('文件名', ''))}

    # 店铺名称：Qwen 优先，EasyOCR 补缺
    qwen_store = sv(qwen_result.get('店铺名称', ''))
    easyocr_store = sv(easyocr_result.get('店铺名称', ''))
    merged['店铺名称'] = qwen_store if qwen_store else easyocr_store

    # 交易日期：EasyOCR 优先，Qwen 补缺
    merged['交易日期'] = sv(easyocr_result.get('交易日期', '')) or sv(qwen_result.get('交易日期', ''))

    # 交易唯一编号：EasyOCR 优先，Qwen 补缺
    merged['交易唯一编号'] = sv(easyocr_result.get('交易唯一编号', '')) or sv(qwen_result.get('交易唯一编号', ''))

    # 优惠后金额：EasyOCR 优先，Qwen 补缺
    merged['优惠后金额'] = sv(easyocr_result.get('优惠后金额', '')) or sv(qwen_result.get('优惠后金额', ''))

    return merged


# ============ Main ============

from cache_utils import load_cached_results, save_cached_results

# 合并时去掉哈希字段，不参与合并逻辑
def strip_hash(result):
    return {k: v for k, v in result.items() if k != '_hash'}


def save_results(results, suffix):
    """保存结果到 JSON/CSV/MD"""
    json_path = os.path.join(OUTPUT_FOLDER, f'截图_{suffix}.json')
    with open(json_path, 'w', encoding='utf-8') as f:
        json.dump(results, f, ensure_ascii=False, indent=2)
    print(f"Saved JSON: {json_path}")

    csv_path = os.path.join(OUTPUT_FOLDER, f'截图_{suffix}.csv')
    keys = ['文件名', '店铺名称', '交易日期', '交易唯一编号', '优惠后金额']
    with open(csv_path, 'w', encoding='utf-8-sig', newline='') as f:
        writer = csv.DictWriter(f, fieldnames=keys, extrasaction='ignore')
        writer.writeheader()
        writer.writerows(results)
    print(f"Saved CSV:  {csv_path}")

    md_path = os.path.join(OUTPUT_FOLDER, f'截图_{suffix}.md')
    lines = [f'# 截图订单提取结果（合并方案）\n']
    lines.append(f'共提取 **{len(results)}** 条记录\n')
    lines.append('| 序号 | 文件名 | 店铺名称 | 交易日期 | 交易唯一编号 | 优惠后金额 |')
    lines.append('|------|--------|----------|----------|-------------|------------|')
    total_amt = 0
    for i, r in enumerate(results, 1):
        amt = r.get('优惠后金额', '')
        try: total_amt += float(str(amt).replace(',', ''))
        except: pass
        lines.append(f'| {i} | {r.get("文件名","")[:25]} | {r.get("店铺名称","")} | {r.get("交易日期","")} | {r.get("交易唯一编号","")} | ¥{r.get("优惠后金额","")} |')
    lines.append(f'\n**优惠后金额总计: ¥{total_amt:.2f}**\n')
    with open(md_path, 'w', encoding='utf-8') as f:
        f.write('\n'.join(lines))
    print(f"Saved MD:   {md_path}")


def main():
    os.makedirs(OUTPUT_FOLDER, exist_ok=True)

    img_files = sorted([f for f in os.listdir(IMG_FOLDER)
                        if f.lower().endswith(('.jpg', '.jpeg', '.png', '.bmp'))])
    total_files = len(img_files)
    print(f"Found {total_files} screenshots\n")

    # ====== Step 1: 检查已有结果 ======
    IMG_EXT = ('.jpg', '.jpeg', '.png', '.bmp')
    local_cache = load_cached_results(
        os.path.join(OUTPUT_FOLDER, '截图_本地识别.json'), IMG_FOLDER, IMG_EXT)
    qwen_cache = load_cached_results(
        os.path.join(OUTPUT_FOLDER, '截图_模型识别.json'), IMG_FOLDER, IMG_EXT)

    local_count = len([f for f in img_files if f in local_cache])
    qwen_count = len([f for f in img_files if f in qwen_cache])
    print(f"Cached results: EasyOCR={local_count}/{total_files}, Qwen={qwen_count}/{total_files}")

    # 需要跑 EasyOCR 的文件
    need_easyocr = [f for f in img_files if f not in local_cache]
    # 需要跑 Qwen 的文件（本地有缺失字段的）
    need_qwen = []
    for f in img_files:
        if f in qwen_cache:
            continue
        if f in local_cache:
            lr = local_cache[f]
            if any(not sv(lr.get(field)) for field in ['店铺名称', '交易唯一编号', '优惠后金额']):
                need_qwen.append(f)
        else:
            need_qwen.append(f)

    print(f"Need to run: EasyOCR={len(need_easyocr)}, Qwen={len(need_qwen)}\n")

    # ====== Step 2: 批量跑 EasyOCR ======
    if need_easyocr:
        print(f"[EasyOCR] Running on {len(need_easyocr)} files...")
        import gc
        try:
            import torch
            if torch.cuda.is_available():
                torch.cuda.empty_cache()
                gc.collect()
        except: pass

        reader = easyocr.Reader(['ch_sim', 'en'], gpu=True, verbose=False)
        for i, f in enumerate(need_easyocr, 1):
            print_progress(i, len(need_easyocr), suffix=f)
            path = os.path.join(IMG_FOLDER, f)
            try:
                texts = extract_text_from_image(path, reader)
                local_cache[f] = parse_order_easyocr(f, texts)
            except:
                local_cache[f] = {'文件名': f, '店铺名称': '', '交易日期': '', '交易唯一编号': '', '优惠后金额': ''}
        print()

        # 保存 EasyOCR 结果（带哈希）
        local_list = [strip_hash(local_cache[f]) for f in img_files if f in local_cache]
        save_cached_results(local_list, os.path.join(OUTPUT_FOLDER, '截图_本地识别.json'), IMG_FOLDER)
        print()

        # 释放 EasyOCR 显存
        del reader
        try:
            import torch
            if torch.cuda.is_available():
                torch.cuda.empty_cache()
                gc.collect()
        except: pass

        # 重新计算需要 Qwen 的文件（EasyOCR 跑完后可能有新缺失）
        need_qwen = []
        for f in img_files:
            if f in qwen_cache:
                continue
            lr = local_cache.get(f, {})
            if any(not sv(lr.get(field)) for field in ['店铺名称', '交易唯一编号', '优惠后金额']):
                need_qwen.append(f)
        print(f"After EasyOCR: need Qwen={len(need_qwen)}\n")

    # ====== Step 3: 批量跑 Qwen ======
    if need_qwen:
        print(f"[Qwen] Running on {len(need_qwen)} files...")

        # 检查 Ollama
        qwen_ok = False
        try:
            resp = requests.get("http://localhost:11434/api/tags", timeout=5)
            models = [m['name'] for m in resp.json().get('models', [])]
            if any(QWEN_MODEL in m for m in models):
                qwen_ok = True
            else:
                print(f"Warning: Qwen model not found")
        except Exception:
            print(f"Warning: Ollama not running")

        if qwen_ok:
            for i, f in enumerate(need_qwen, 1):
                print_progress(i, len(need_qwen), suffix=f)
                path = os.path.join(IMG_FOLDER, f)
                try:
                    qwen_cache[f] = parse_order_qwen(f, path)
                except:
                    qwen_cache[f] = {'文件名': f, '店铺名称': '', '交易日期': '', '交易唯一编号': '', '优惠后金额': ''}
            print()

            # 保存 Qwen 结果（带哈希）
            qwen_list = [strip_hash(qwen_cache[f]) for f in img_files if f in qwen_cache]
            save_cached_results(qwen_list, os.path.join(OUTPUT_FOLDER, '截图_模型识别.json'), IMG_FOLDER)
            print()

    # ====== Step 4: 合并结果 ======
    print("[Merge] Combining results...")
    results = []
    for f in img_files:
        lr = local_cache.get(f, {'文件名': f, '店铺名称': '', '交易日期': '', '交易唯一编号': '', '优惠后金额': ''})
        qr = qwen_cache.get(f, {'文件名': f, '店铺名称': '', '交易日期': '', '交易唯一编号': '', '优惠后金额': ''})
        merged = merge_results(lr, qr)
        results.append(merged)

    # 保存合并结果
    save_results(results, '合并识别')

    # 统计
    complete = sum(1 for r in results if all(sv(r.get(f)) for f in ['店铺名称', '交易日期', '交易唯一编号', '优惠后金额']))
    print(f"\nComplete: {complete}/{len(results)} ({complete*100//len(results)}%)")

    # Save Markdown
    md_path = os.path.join(OUTPUT_FOLDER, '截图_合并识别.md')
    lines = ['# 截图订单提取结果（EasyOCR + Qwen 合并）\n']
    lines.append(f'共提取 **{len(results)}** 条记录\n')
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
    with open(md_path, 'w', encoding='utf-8') as f:
        f.write('\n'.join(lines))
    print(f"Saved MD:   {md_path}")

    # Print stats
    complete = sum(1 for r in results if all(sv(r.get(f)) for f in ['店铺名称', '交易日期', '交易唯一编号', '优惠后金额']))
    print(f"\nComplete: {complete}/{len(results)} ({complete*100//len(results)}%)")


if __name__ == '__main__':
    main()
