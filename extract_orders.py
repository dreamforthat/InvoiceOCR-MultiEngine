"""
淘宝/天猫订单截图信息提取 - 基于 EasyOCR
使用方法: python extract_orders.py
"""
import os
from cache_utils import load_cached_results, save_cached_results
import sys
import io
import re
import json
import csv
import warnings
warnings.filterwarnings("ignore")
os.environ["TF_CPP_MIN_LOG_LEVEL"] = "3"
os.environ["TORCH_CPP_LOG_LEVEL"] = "ERROR"
import easyocr
from PIL import Image

sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding='utf-8')

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
    # 只显示文件名，截断过长部分
    name = suffix[:25] if len(suffix) > 25 else suffix
    line = f"  [{bar}] {current}/{total}  {name}"
    sys.stdout.write(f"\r{line:<70}")
    sys.stdout.flush()
    if current == total:
        print()


def extract_text_from_image(img_path, reader):
    """使用easyocr提取图片中的所有文字及其位置"""
    import numpy as np
    # 用PIL读取避免OpenCV中文路径问题
    img = Image.open(img_path)
    img_array = np.array(img)
    result = reader.readtext(img_array, detail=1)
    # result: list of (bbox, text, confidence)
    texts = []
    for bbox, text, conf in result:
        # bbox is [[x1,y1],[x2,y2],[x3,y3],[x4,y4]]
        y_center = (bbox[0][1] + bbox[2][1]) / 2
        x_center = (bbox[0][0] + bbox[2][0]) / 2
        texts.append({
            'text': text.strip(),
            'y': y_center,
            'x': x_center,
            'conf': conf
        })
    # Sort by y position (top to bottom)
    texts.sort(key=lambda t: t['y'])
    return texts


def find_text_near(texts, keyword, x_min=0, x_max=9999, y_range=None):
    """查找包含关键词的文本，返回其右侧的文本"""
    for i, item in enumerate(texts):
        if keyword in item['text'] and x_min <= item['x'] <= x_max:
            if y_range and not (y_range[0] <= item['y'] <= y_range[1]):
                continue
            # 找同一行右侧的文本
            for j in range(i+1, len(texts)):
                next_item = texts[j]
                if abs(next_item['y'] - item['y']) < 30 and next_item['x'] > item['x']:
                    return next_item['text']
            # 如果右侧没有，返回关键词后面的文本（同行合并）
            return item['text'].replace(keyword, '').strip()
    return ''


def find_amount_after_discount(texts):
    """找到实付款金额"""
    for i, item in enumerate(texts):
        if '实付款' in item['text']:
            shifu_y = item['y']
            shifu_x = item['x']
            # 找y接近且x远大于实付款位置的文本（金额在右侧）
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


def parse_order_from_texts(filename, texts):
    """从已提取的文字解析订单信息"""
    info = {
        '文件名': filename,
        '店铺名称': '',
        '交易日期': '',
        '交易唯一编号': '',
        '优惠后金额': '',
    }

    # 1. 店铺名称 - 找"进店逛逛"左侧，排除平台名（天猫/淘宝）和收货人
    for i, item in enumerate(texts):
        if '进店' in item['text'] and '逛' in item['text']:
            # 从右往左找同一行的文本
            candidates = []
            for j in range(i-1, -1, -1):
                prev = texts[j]
                if abs(prev['y'] - item['y']) < 40 and prev['x'] < item['x']:
                    name = prev['text'].strip()
                    # 清理尾部多余字符
                    name = re.sub(r'\s*>.*', '', name).strip()
                    # 排除非店铺名
                    if (len(name) > 1
                        and name not in ('天猫', '淘宝', '天猫超市')
                        and '地址' not in name and '洪' not in name
                        and '86-' not in name and '迎宾' not in name):
                        candidates.append(name)
            if candidates:
                info['店铺名称'] = candidates[-1]
            break

    # 2. 交易日期 - "订单信息 YYYY-MM-DD"
    for item in texts:
        m = re.search(r'订单信息\s*(\d{4}[-/]\d{2}[-/]\d{2})', item['text'])
        if m:
            info['交易日期'] = m.group(1)
            break
        # 也匹配 "订单信息" 后面同行的日期
        if '订单信息' in item['text']:
            # 日期可能在同一文本中
            m = re.search(r'(\d{4}[-/]\d{2}[-/]\d{2})', item['text'])
            if m:
                info['交易日期'] = m.group(1)
                break

    # 3. 交易唯一编号 - "订单编号" 后面的数字
    for i, item in enumerate(texts):
        if '订单编号' in item['text'] or '订单号' in item['text']:
            # 方案a: 编号在同一文本中
            m = re.search(r'订单编号?\s*(\d{10,})', item['text'])
            if m:
                info['交易唯一编号'] = m.group(1)
                break
            # 方案b: 编号在右侧同一行（扩大搜索范围）
            order_y = item['y']
            best = None
            for j, next_item in enumerate(texts):
                if j == i:
                    continue
                dy = abs(next_item['y'] - order_y)
                if dy < 40 and next_item['x'] > item['x']:
                    m = re.search(r'(\d{10,})', next_item['text'])
                    if m:
                        # 优先取最靠近的
                        dist = next_item['x'] - item['x']
                        if best is None or dist < best[0]:
                            best = (dist, m.group(1))
            if best:
                info['交易唯一编号'] = best[1]
                break
            # 方案c: 编号在附近任意位置（同一行区域）
            for next_item in texts:
                if abs(next_item['y'] - order_y) < 20:
                    m = re.search(r'(\d{15,})', next_item['text'])
                    if m:
                        info['交易唯一编号'] = m.group(1)
                        break
            if info['交易唯一编号']:
                break

    # 方案d: 找"订单信息"附近的长数字串（编号可能在"订单信息"旁边而非"订单编号"旁）
    if not info['交易唯一编号']:
        for i, item in enumerate(texts):
            if '订单信息' in item['text'] or '订单编号' in item['text']:
                order_y = item['y']
                # 在当前行和下方找长数字（编号可能在下方100+像素处）
                for j in range(max(0, i-3), min(len(texts), i+10)):
                    t = texts[j]
                    if abs(t['y'] - order_y) < 150:
                        m = re.search(r'(\d{15,})', t['text'])
                        if m:
                            info['交易唯一编号'] = m.group(1)
                            break
                if info['交易唯一编号']:
                    break

    # 方案e: 全局兜底 - 找任何包含"订单"的文本附近的长数字
    if not info['交易唯一编号']:
        for i, item in enumerate(texts):
            if '订单' in item['text']:
                order_y = item['y']
                # 在同行和附近几行找长数字
                for j, t in enumerate(texts):
                    if j == i:
                        continue
                    if abs(t['y'] - order_y) < 50:
                        m = re.search(r'(\d{15,})', t['text'])
                        if m:
                            info['交易唯一编号'] = m.group(1)
                            break
                if info['交易唯一编号']:
                    break

    # 4. 优惠后金额 - "实付款" 附近的¥金额
    info['优惠后金额'] = find_amount_after_discount(texts)

    return info


def parse_order(img_path, reader):
    """解析单张订单截图（兼容旧接口）"""
    filename = os.path.basename(img_path)
    texts = extract_text_from_image(img_path, reader)
    return parse_order_from_texts(filename, texts)


def generate_markdown(results):
    """生成Markdown报告"""
    lines = []
    lines.append('# 订单截图信息提取结果（EasyOCR）\n')
    lines.append(f'共提取 **{len(results)}** 条订单记录\n')

    lines.append('## 汇总表\n')
    lines.append('| 序号 | 文件名 | 店铺名称 | 交易日期 | 交易唯一编号 | 优惠后金额 |')
    lines.append('|------|--------|----------|----------|-------------|------------|')

    total = 0
    for i, r in enumerate(results, 1):
        amt = r.get('优惠后金额', '')
        try:
            total += float(amt.replace(',', ''))
        except (ValueError, TypeError):
            pass
        lines.append(f'| {i} | {r["文件名"][:25]} | {r["店铺名称"]} | {r["交易日期"]} | {r["交易唯一编号"]} | ¥{r["优惠后金额"]} |')

    lines.append(f'\n**优惠后金额总计: ¥{total:.2f}**\n')

    lines.append('## 详细信息\n')
    for i, r in enumerate(results, 1):
        lines.append(f'### {i}. {r["文件名"]}')
        lines.append('')
        for key in ['店铺名称', '交易日期', '交易唯一编号', '优惠后金额']:
            val = r.get(key, '')
            if key == '优惠后金额' and val:
                val = f'¥{val}'
            lines.append(f'- **{key}**: {val}')
        lines.append('')

    return '\n'.join(lines)


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


def wait_for_vram(min_free_mb=1500):
    """等待显存释放到可用空间"""
    import time
    while True:
        _, total, used, free = get_vram_info()
        if free >= min_free_mb or total == 0:
            return
        time.sleep(0.5)


def main():
    os.makedirs(OUTPUT_FOLDER, exist_ok=True)

    # 检查已有结果（含哈希过期检测）
    IMG_EXT = ('.jpg', '.jpeg', '.png', '.bmp')
    json_path = os.path.join(OUTPUT_FOLDER, '截图_本地识别.json')
    cached = load_cached_results(json_path, IMG_FOLDER, IMG_EXT)
    all_files = sorted([f for f in os.listdir(IMG_FOLDER) if f.lower().endswith(IMG_EXT)])
    missing = [f for f in all_files if f not in cached]
    if cached and not missing:
        print(f"已有结果 ({len(cached)} 条)，全部覆盖，跳过。")
        return
    if cached:
        print(f"已有 {len(cached)} 条，{len(missing)} 个新文件需处理")

    img_files = sorted([f for f in os.listdir(IMG_FOLDER)
                        if f.lower().endswith(('.jpg', '.jpeg', '.png', '.bmp'))])
    total_files = len(img_files)
    print(f'找到 {total_files} 张截图\n')

    if not img_files:
        print('没有找到图片文件，请将截图放入 原始截图 文件夹')
        return

    # 检测GPU
    gpu_name, total_mb, used_mb, free_mb = get_vram_info()
    if gpu_name:
        print(f'GPU: {gpu_name} ({total_mb//1024}GB) 显存: {used_mb}MB/{total_mb}MB 可用:{free_mb}MB')
    else:
        print('未检测到GPU')

    print('加载 EasyOCR 模型...')
    reader = easyocr.Reader(['ch_sim', 'en'], gpu=True, verbose=False)
    print('模型加载完成\n')

    results = []
    for i, f in enumerate(img_files, 1):
        print_progress(i, total_files, suffix=f)
        path = os.path.join(IMG_FOLDER, f)
        try:
            info = parse_order(path, reader)
            results.append(info)
        except Exception as e:
            results.append({'文件名': f, '店铺名称': '', '交易日期': '', '交易唯一编号': '', '优惠后金额': ''})

    # Save JSON (with hashes)
    json_path = os.path.join(OUTPUT_FOLDER, '截图_本地识别.json')
    save_cached_results(results, json_path, IMG_FOLDER)
    print(f'\nSaved JSON: {json_path}')

    # Save CSV
    csv_path = os.path.join(OUTPUT_FOLDER, '截图_本地识别.csv')
    keys = ['文件名', '店铺名称', '交易日期', '交易唯一编号', '优惠后金额']
    with open(csv_path, 'w', encoding='utf-8-sig', newline='') as f:
        writer = csv.DictWriter(f, fieldnames=keys)
        writer.writeheader()
        writer.writerows(results)
    print(f'Saved CSV:  {csv_path}')

    # Save Markdown
    md_path = os.path.join(OUTPUT_FOLDER, '截图_本地识别.md')
    with open(md_path, 'w', encoding='utf-8') as f:
        f.write(generate_markdown(results))
    print(f'Saved MD:   {md_path}')


if __name__ == '__main__':
    main()
