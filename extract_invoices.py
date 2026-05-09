import fitz
import os
import re
import json
import csv
import sys
import warnings
warnings.filterwarnings("ignore")
from cache_utils import load_cached_results, save_cached_results

SCRIPT_DIR = os.path.dirname(os.path.abspath(__file__))
FOLDER = os.path.join(SCRIPT_DIR, '原始发票')
OUTPUT_FOLDER = os.path.join(SCRIPT_DIR, '输出结果', '发票')
# 兼容：如果原始发票文件夹为空，回退到上级目录
if not os.listdir(FOLDER):
    FOLDER = os.path.dirname(SCRIPT_DIR)


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


def get_text_blocks(pdf_path):
    """Extract text blocks with position info."""
    doc = fitz.open(pdf_path)
    items = []
    for page in doc:
        blocks = page.get_text('dict')['blocks']
        for b in blocks:
            if 'lines' not in b:
                continue
            for line in b['lines']:
                text = ''.join([span['text'] for span in line['spans']])
                x, y = line['bbox'][0], line['bbox'][1]
                items.append((x, y, text.strip()))
    doc.close()
    return items


def get_plain_text(pdf_path):
    doc = fitz.open(pdf_path)
    text = ''
    for page in doc:
        text += page.get_text()
    doc.close()
    return text


def find_text_right_of_label(items, label_parts, y_center, x_min=0, x_max=999, y_tol=10):
    """Find text to the right of a label that may be split across blocks."""
    # First try exact match
    for lx, ly, lt in items:
        if label_parts in lt and abs(ly - y_center) < y_tol:
            candidates = []
            for ix, iy, it in items:
                if it and it != lt and abs(iy - ly) < y_tol and ix > lx and x_min <= ix <= x_max:
                    candidates.append((ix - lx, it))
            if candidates:
                candidates.sort()
                return candidates[0][1]
    # Try partial match (for split labels like "名" "称：")
    for lx, ly, lt in items:
        if any(p in lt for p in label_parts) and abs(ly - y_center) < y_tol:
            candidates = []
            for ix, iy, it in items:
                if it and it != lt and abs(iy - ly) < y_tol and ix > lx + 5 and x_min <= ix <= x_max:
                    candidates.append((ix - lx, it))
            if candidates:
                candidates.sort()
                return candidates[0][1]
    return ''


def find_amount_near_y(items, y_center, y_tol=8, min_x=400):
    """Find ¥ amounts near a specific y position."""
    amounts = []
    for x, y, t in items:
        if abs(y - y_center) < y_tol and x >= min_x:
            m = re.findall(r'[¥￥]?\s*([\d,]+\.?\d*)', t)
            for a in m:
                val = a.replace(',', '')
                if val and float(val) > 0:
                    amounts.append(val)
    return amounts


def parse_old_invoice(pdf_path):
    """Parse 增值税电子普通发票 (old format) using spatial layout."""
    items = get_text_blocks(pdf_path)
    filename = os.path.basename(pdf_path)
    info = {
        '文件名': filename,
        '发票类型': '增值税电子普通发票',
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

    # Invoice code and number - top right area
    for x, y, t in items:
        if re.match(r'^\d{10,12}$', t) and x > 400 and y < 60:
            if not info['发票代码']:
                info['发票代码'] = t
        elif re.match(r'^\d{8}$', t) and x > 400 and y < 60:
            if not info['发票号码']:
                info['发票号码'] = t

    # Date
    for x, y, t in items:
        m = re.match(r'^(\d{4})\s+(\d{2})\s+(\d{2})$', t)
        if m and x > 400 and y < 60:
            info['开票日期'] = f'{m.group(1)}-{m.group(2)}-{m.group(3)}'
            break
        m = re.search(r'(\d{4})年(\d{2})月(\d{2})日', t)
        if m and x > 400:
            info['开票日期'] = f'{m.group(1)}-{m.group(2)}-{m.group(3)}'
            break

    # Buyer: find "名" or "称：" near y~90, x<200
    buyer_y = None
    for x, y, t in items:
        if ('名' in t or '称' in t) and y < 150 and x < 200:
            buyer_y = y
            break

    if buyer_y is not None:
        info['购买方名称'] = find_text_right_of_label(items, '称', buyer_y, x_min=80, x_max=340)
        if not info['购买方名称']:
            info['购买方名称'] = find_text_right_of_label(items, '名', buyer_y, x_min=80, x_max=340)

    # Buyer tax ID
    for x, y, t in items:
        if '纳税人识别号' in t and y < 150:
            info['购买方纳税识别号'] = find_text_right_of_label(items, '纳税人识别号', y, x_min=80, x_max=340)
            break

    # Seller: find "名" or "称：" near y>280, x<200
    seller_y = None
    for x, y, t in items:
        if ('名' in t or '称' in t) and y > 250 and x < 200:
            seller_y = y
            break

    if seller_y is not None:
        info['销售方名称'] = find_text_right_of_label(items, '称', seller_y, x_min=80, x_max=340)
        if not info['销售方名称']:
            info['销售方名称'] = find_text_right_of_label(items, '名', seller_y, x_min=80, x_max=340)

    # Seller tax ID
    for x, y, t in items:
        if '纳税人识别号' in t and y > 250:
            info['销售方纳税识别号'] = find_text_right_of_label(items, '纳税人识别号', y, x_min=80, x_max=340)
            break

    # Items: lines starting with * at y ~150-250
    items_list = []
    for x, y, t in items:
        if t.startswith('*') and 150 < y < 260:
            m = re.match(r'\*([^*]+)\*(.+)', t)
            if m:
                items_list.append(f'{m.group(1)}{m.group(2)}')
    info['商品名称'] = '; '.join(items_list)

    # Amounts: find 合计 row and 价税合计 row
    heji_y = None
    xiaoxie_y = None
    for x, y, t in items:
        if '合' in t and '计' in t and 250 < y < 290:
            heji_y = y
        if '小写' in t and 270 < y < 300:
            xiaoxie_y = y

    if heji_y is not None:
        heji_amounts = find_amount_near_y(items, heji_y, y_tol=8, min_x=400)
        if len(heji_amounts) >= 2:
            info['金额(不含税)'] = heji_amounts[0]
            info['税额'] = heji_amounts[1]

    if xiaoxie_y is not None:
        xx_amounts = find_amount_near_y(items, xiaoxie_y, y_tol=8, min_x=400)
        if xx_amounts:
            info['价税合计'] = xx_amounts[0]

    # Fallback: if still no 价税合计, find ¥ signs
    if not info['价税合计']:
        for x, y, t in items:
            m = re.findall(r'[¥￥]\s*([\d,]+\.?\d*)', t)
            if m:
                info['价税合计'] = m[-1].replace(',', '')
                break

    # If still no amounts, look for amounts near y~260-280
    if not info['金额(不含税)']:
        all_amounts = []
        for x, y, t in items:
            if 255 < y < 285 and x > 400:
                m = re.findall(r'[¥￥]?\s*([\d,]+\.?\d*)', t)
                for a in m:
                    val = a.replace(',', '')
                    if val and float(val) > 0:
                        all_amounts.append(val)
        if len(all_amounts) >= 2:
            info['金额(不含税)'] = all_amounts[0]
            info['税额'] = all_amounts[1]
        elif len(all_amounts) == 1:
            info['金额(不含税)'] = all_amounts[0]

    # Tax rates
    tax_rates = set()
    for x, y, t in items:
        if 150 < y < 260:
            m = re.findall(r'(\d+)%', t)
            tax_rates.update(m)
    info['税率'] = '/'.join(sorted(tax_rates)) + '%' if tax_rates else '免税'

    return info


def parse_new_invoice(pdf_path):
    """Parse 电子发票（普通发票）(new format) using spatial layout."""
    items = get_text_blocks(pdf_path)
    filename = os.path.basename(pdf_path)
    info = {
        '文件名': filename,
        '发票类型': '电子发票（普通发票）',
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

    # Invoice number: 20-digit number
    for x, y, t in items:
        if re.match(r'^\d{20}$', t):
            info['发票号码'] = t
            break

    # Date: YYYY年MM月DD日
    for x, y, t in items:
        m = re.search(r'(\d{4})年(\d{2})月(\d{2})日', t)
        if m:
            info['开票日期'] = f'{m.group(1)}-{m.group(2)}-{m.group(3)}'
            break

    # Buyer name: text right of "名称：" in left half (x < 300)
    for lx, ly, lt in items:
        if '名称' in lt and lx < 300:
            candidates = []
            for ix, iy, it in items:
                if it and it != lt and abs(iy - ly) < 8 and ix > lx and ix < 300:
                    candidates.append((ix - lx, it))
            if candidates:
                candidates.sort()
                info['购买方名称'] = candidates[0][1]
            break

    # Buyer tax ID
    for lx, ly, lt in items:
        if '统一社会信用代码' in lt and lx < 300:
            candidates = []
            for ix, iy, it in items:
                if it and it != lt and abs(iy - ly) < 8 and ix > lx and ix < 300:
                    if re.match(r'^[A-Za-z0-9]+$', it):
                        candidates.append((ix - lx, it))
            if candidates:
                candidates.sort()
                info['购买方纳税识别号'] = candidates[0][1]
            break

    # Seller name: text right of "名称：" in right half (x > 300)
    for lx, ly, lt in items:
        if '名称' in lt and lx > 300:
            candidates = []
            for ix, iy, it in items:
                if it and it != lt and abs(iy - ly) < 8 and ix > lx:
                    candidates.append((ix - lx, it))
            if candidates:
                candidates.sort()
                info['销售方名称'] = candidates[0][1]
            break

    # Seller tax ID
    for lx, ly, lt in items:
        if '统一社会信用代码' in lt and lx > 300:
            candidates = []
            for ix, iy, it in items:
                if it and it != lt and abs(iy - ly) < 8 and ix > lx:
                    if re.match(r'^[A-Za-z0-9]+$', it):
                        candidates.append((ix - lx, it))
            if candidates:
                candidates.sort()
                info['销售方纳税识别号'] = candidates[0][1]
            break

    # Items
    items_list = []
    for x, y, t in items:
        if t.startswith('*') and 100 < y < 400:
            m = re.match(r'\*([^*]+)\*(.+)', t)
            if m:
                items_list.append(f'{m.group(1)}{m.group(2)}')
    info['商品名称'] = '; '.join(items_list)

    # Amounts
    amounts = []
    for x, y, t in items:
        m = re.findall(r'[¥￥]\s*([\d,]+\.?\d*)', t)
        amounts.extend(m)

    if len(amounts) >= 3:
        info['金额(不含税)'] = amounts[0].replace(',', '')
        info['税额'] = amounts[1].replace(',', '')
        info['价税合计'] = amounts[2].replace(',', '')
    elif len(amounts) == 2:
        info['金额(不含税)'] = amounts[0].replace(',', '')
        info['价税合计'] = amounts[1].replace(',', '')

    # Tax rates
    tax_rates = set()
    for x, y, t in items:
        m = re.findall(r'(\d+)%', t)
        tax_rates.update(m)
    info['税率'] = '/'.join(sorted(tax_rates)) + '%' if tax_rates else '免税'

    return info


def parse_zhejiang_invoice(pdf_path):
    """Parse 浙江通用（电子）发票 format."""
    items = get_text_blocks(pdf_path)
    filename = os.path.basename(pdf_path)
    info = {
        '文件名': filename,
        '发票类型': '浙江通用（电子）发票',
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

    # Invoice code: "发票代码：XXXXX"
    for x, y, t in items:
        m = re.search(r'发票代码[：:]\s*(\d{10,12})', t)
        if m:
            info['发票代码'] = m.group(1)
        m = re.search(r'发票号码[：:]\s*(\d{8})', t)
        if m:
            info['发票号码'] = m.group(1)

    # Date: find year/month/day numbers near 开票日期
    for x, y, t in items:
        if '开票日期' in t:
            # Find nearby numbers
            nearby = []
            for ix, iy, it in items:
                if abs(iy - y) < 8 and ix > x and re.match(r'^\d{4}$', it):
                    nearby.append(it)
                elif abs(iy - y) < 8 and ix > x and re.match(r'^\d{2}$', it):
                    nearby.append(it)
            if len(nearby) >= 3:
                info['开票日期'] = f'{nearby[0]}-{nearby[1]}-{nearby[2]}'
            break

    # Buyer name
    for lx, ly, lt in items:
        if '称' in lt and '：' in lt and ly < 200:
            candidates = []
            for ix, iy, it in items:
                if it and it != lt and abs(iy - ly) < 8 and ix > lx:
                    candidates.append((ix - lx, it))
            if candidates:
                candidates.sort()
                info['购买方名称'] = candidates[0][1]
            break

    # Buyer tax ID
    for lx, ly, lt in items:
        if '纳税人识别号' in lt and ly < 200:
            candidates = []
            for ix, iy, it in items:
                if it and it != lt and abs(iy - ly) < 8 and ix > lx:
                    if re.match(r'^[A-Za-z0-9]+$', it):
                        candidates.append((ix - lx, it))
            if candidates:
                candidates.sort()
                info['购买方纳税识别号'] = candidates[0][1]
            break

    # Seller name
    for lx, ly, lt in items:
        if '称' in lt and '：' in lt and ly > 250:
            candidates = []
            for ix, iy, it in items:
                if it and it != lt and abs(iy - ly) < 8 and ix > lx:
                    candidates.append((ix - lx, it))
            if candidates:
                candidates.sort()
                info['销售方名称'] = candidates[0][1]
            break

    # Seller tax ID
    for lx, ly, lt in items:
        if '纳税人识别号' in lt and ly > 250:
            candidates = []
            for ix, iy, it in items:
                if it and it != lt and abs(iy - ly) < 8 and ix > lx:
                    if re.match(r'^[A-Za-z0-9]+$', it):
                        candidates.append((ix - lx, it))
            if candidates:
                candidates.sort()
                info['销售方纳税识别号'] = candidates[0][1]
            break

    # Items
    items_list = []
    for x, y, t in items:
        if t.startswith('*') and 130 < y < 250:
            m = re.match(r'\*([^*]+)\*(.+)', t)
            if m:
                items_list.append(f'{m.group(1)}{m.group(2)}')
    info['商品名称'] = '; '.join(items_list)

    # Amounts - look for numbers near y~250-280
    for x, y, t in items:
        if '价税合计' in t and '小写' in t:
            # Find number to the right
            for ix, iy, it in items:
                if abs(iy - y) < 8 and ix > x:
                    m = re.search(r'[\¥￥]?\s*([\d,]+\.?\d*)', it)
                    if m:
                        info['价税合计'] = m.group(1).replace(',', '')
                        break
            break

    # 合计 amounts
    for x, y, t in items:
        if '合' in t and '计' in t and 240 < y < 270:
            heji_amounts = find_amount_near_y(items, y, y_tol=8, min_x=400)
            if len(heji_amounts) >= 2:
                info['金额(不含税)'] = heji_amounts[0]
                info['税额'] = heji_amounts[1]
            elif len(heji_amounts) == 1:
                info['金额(不含税)'] = heji_amounts[0]
            break

    # Tax rates
    tax_rates = set()
    for x, y, t in items:
        if 130 < y < 250:
            m = re.findall(r'(\d+)%', t)
            tax_rates.update(m)
    info['税率'] = '/'.join(sorted(tax_rates)) + '%' if tax_rates else '免税'

    return info


def parse_invoice(pdf_path):
    text = get_plain_text(pdf_path)

    if '电子发票（普通发票）' in text:
        return parse_new_invoice(pdf_path)
    elif '浙江通用' in text:
        return parse_zhejiang_invoice(pdf_path)
    elif '增值税电子普通发票' in text or '发票代码' in text:
        return parse_old_invoice(pdf_path)
    else:
        return parse_old_invoice(pdf_path)


def generate_markdown(results):
    """Generate markdown output."""
    lines = []
    lines.append('# 发票信息提取结果\n')
    lines.append(f'共提取 **{len(results)}** 张发票\n')

    # Summary table
    lines.append('## 汇总表\n')
    lines.append('| 序号 | 文件名 | 发票类型 | 发票号码 | 开票日期 | 购买方 | 销售方 | 金额(不含税) | 税率 | 税额 | 价税合计 |')
    lines.append('|------|--------|----------|----------|----------|--------|--------|-------------|------|------|----------|')

    total_amount = 0
    for i, r in enumerate(results, 1):
        amt = r.get('价税合计', '')
        try:
            total_amount += float(amt)
        except (ValueError, TypeError):
            pass
        lines.append(f'| {i} | {r["文件名"][:30]} | {r["发票类型"][:10]} | {r["发票号码"]} | {r["开票日期"]} | {r["购买方名称"][:15]} | {r["销售方名称"][:15]} | {r["金额(不含税)"]} | {r["税率"]} | {r["税额"]} | {r["价税合计"]} |')

    lines.append(f'\n**价税合计总金额: ¥{total_amount:.2f}**\n')

    # Detailed info for each invoice
    lines.append('## 详细信息\n')
    for i, r in enumerate(results, 1):
        lines.append(f'### {i}. {r["文件名"]}\n')
        lines.append(f'- **发票类型**: {r["发票类型"]}')
        lines.append(f'- **发票代码**: {r["发票代码"]}')
        lines.append(f'- **发票号码**: {r["发票号码"]}')
        lines.append(f'- **开票日期**: {r["开票日期"]}')
        lines.append(f'- **购买方名称**: {r["购买方名称"]}')
        lines.append(f'- **购买方纳税识别号**: {r["购买方纳税识别号"]}')
        lines.append(f'- **销售方名称**: {r["销售方名称"]}')
        lines.append(f'- **销售方纳税识别号**: {r["销售方纳税识别号"]}')
        lines.append(f'- **商品名称**: {r["商品名称"]}')
        lines.append(f'- **金额(不含税)**: {r["金额(不含税)"]}')
        lines.append(f'- **税率**: {r["税率"]}')
        lines.append(f'- **税额**: {r["税额"]}')
        lines.append(f'- **价税合计**: {r["价税合计"]}')
        lines.append('')

    return '\n'.join(lines)


def main():
    os.makedirs(OUTPUT_FOLDER, exist_ok=True)

    # 检查已有结果（含哈希过期检测）
    json_path = os.path.join(OUTPUT_FOLDER, '发票_本地识别.json')
    cached = load_cached_results(json_path, FOLDER, ('.pdf',))
    all_files = sorted([f for f in os.listdir(FOLDER) if f.lower().endswith('.pdf')])
    missing = [f for f in all_files if f not in cached]
    if cached and not missing:
        print(f"已有结果 ({len(cached)} 条)，全部覆盖，跳过。")
        return
    if cached:
        print(f"已有 {len(cached)} 条，{len(missing)} 个新文件需处理")

    pdf_files = sorted([f for f in os.listdir(FOLDER) if f.lower().endswith('.pdf')])
    total_files = len(pdf_files)
    print(f'Found {total_files} PDF files\n')

    results = []
    for i, f in enumerate(pdf_files, 1):
        print_progress(i, total_files, suffix=f)
        path = os.path.join(FOLDER, f)
        try:
            info = parse_invoice(path)
            results.append(info)
        except Exception as e:
            results.append({'文件名': f, '发票类型': f'ERROR: {e}',
                '发票代码': '', '发票号码': '', '开票日期': '',
                '购买方名称': '', '购买方纳税识别号': '',
                '销售方名称': '', '销售方纳税识别号': '',
                '商品名称': '', '金额(不含税)': '', '税率': '', '税额': '', '价税合计': ''})

    # Save JSON (with hashes)
    json_path = os.path.join(OUTPUT_FOLDER, '发票_本地识别.json')
    save_cached_results(results, json_path, FOLDER)
    print(f'Saved JSON: {json_path}')

    # Save CSV
    csv_path = os.path.join(OUTPUT_FOLDER, '发票_本地识别.csv')
    if results:
        keys = results[0].keys()
        with open(csv_path, 'w', encoding='utf-8-sig', newline='') as f:
            writer = csv.DictWriter(f, fieldnames=keys)
            writer.writeheader()
            writer.writerows(results)
        print(f'Saved CSV:  {csv_path}')

    # Save Markdown
    md_path = os.path.join(OUTPUT_FOLDER, '发票_本地识别.md')
    md_content = generate_markdown(results)
    with open(md_path, 'w', encoding='utf-8') as f:
        f.write(md_content)
    print(f'Saved MD:   {md_path}')

    # Print summary
    for r in results:
        amt = r['价税合计']
        print(f'{r["文件名"][:40]:<42} {r["发票号码"]:<12} {r["购买方名称"][:10]:<12} {r["销售方名称"][:15]:<17} {amt}')


if __name__ == '__main__':
    main()
