"""
增量更新截图识别缓存 — 只重跑有问题的文件（店铺名/金额为空）
重跑 Qwen 模型，更新截图_模型识别.json 中的空字段
"""
import os
import sys
import io
import json
import re
import base64
import requests
import time
import warnings
warnings.filterwarnings("ignore")

sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding='utf-8')

SCRIPT_DIR = os.path.dirname(os.path.abspath(__file__))
IMG_FOLDER = os.path.join(SCRIPT_DIR, '原始截图')
OUTPUT_FOLDER = os.path.join(SCRIPT_DIR, '输出结果', '截图')

OLLAMA_URL = "http://localhost:11434/api/generate"
QWEN_MODEL = "lukey03/qwen3.5-9b-abliterated-vision:latest"

PROMPT = """Extract the following information from this Taobao/Tmall/JD order screenshot and output as JSON.
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


def call_qwen(img_path, retries=3):
    with open(img_path, 'rb') as f:
        img_b64 = base64.b64encode(f.read()).decode('utf-8')
    for attempt in range(retries):
        try:
            resp = requests.post(OLLAMA_URL, json={
                "model": QWEN_MODEL, "prompt": PROMPT, "images": [img_b64],
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


def main():
    # 加载现有缓存
    qwen_path = os.path.join(OUTPUT_FOLDER, '截图_模型识别.json')
    with open(qwen_path, 'r', encoding='utf-8') as f:
        qwen_data = json.load(f)

    # 找出需要重跑的文件
    need_rerun = []
    for r in qwen_data:
        fn = r.get('文件名', '')
        if not r.get('店铺名称') or not r.get('优惠后金额'):
            src = os.path.join(IMG_FOLDER, fn)
            if os.path.exists(src):
                need_rerun.append((fn, r))

    if not need_rerun:
        print("所有文件的店铺名和金额都已提取，无需更新。")
        return

    print(f"需要重跑 Qwen: {len(need_rerun)} 个文件\n")

    # 逐个重跑
    fixed_count = 0
    for i, (fn, old_r) in enumerate(need_rerun, 1):
        src = os.path.join(IMG_FOLDER, fn)
        print(f"[{i}/{len(need_rerun)}] {fn}...", end=" ", flush=True)

        resp = call_qwen(src)
        if resp:
            info = parse_json(resp)
            if info:
                # 只更新空字段
                updated = False
                for field in ['店铺名称', '交易日期', '交易唯一编号', '优惠后金额']:
                    if not old_r.get(field) and info.get(field):
                        old_r[field] = info[field]
                        updated = True
                if updated:
                    fixed_count += 1
                    print(f"OK 店铺=\"{old_r.get('店铺名称', '')}\" 金额=\"{old_r.get('优惠后金额', '')}\"")
                else:
                    print("无新数据")
            else:
                print("JSON解析失败")
        else:
            print("Qwen无响应")

    # 保存更新后的缓存
    with open(qwen_path, 'w', encoding='utf-8') as f:
        json.dump(qwen_data, f, ensure_ascii=False, indent=2)
    print(f"\n完成！更新了 {fixed_count} 个文件，已保存到 {qwen_path}")


if __name__ == '__main__':
    main()
