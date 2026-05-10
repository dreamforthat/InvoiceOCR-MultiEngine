"""
发票OCR交叉投票合并 — 3引擎结果投票 + 后处理校验
读取 PyMuPDF / Qwen / DeepSeek 的已有输出，按字段投票取最优值，再用校验规则修正。

使用方法:
  1. 先分别运行 3 个引擎（extract_invoices.py / ollama_invoice_ocr.py / deepseek_invoice_ocr.py）
  2. python merge_invoice_ocr.py
"""
import os
import sys
import io
import json
import csv
import re
from collections import Counter

sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding='utf-8')

SCRIPT_DIR = os.path.dirname(os.path.abspath(__file__))
OUTPUT_FOLDER = os.path.join(SCRIPT_DIR, '输出结果', '发票')

# 3 个引擎的 JSON 输出路径
ENGINE_PATHS = {
    'PyMuPDF': os.path.join(OUTPUT_FOLDER, '发票_本地识别.json'),
    'Qwen': os.path.join(OUTPUT_FOLDER, '发票_模型识别.json'),
    'DeepSeek': os.path.join(OUTPUT_FOLDER, '发票_deepseek混合.json'),
}

# 字段优先级：当无共识时，按此顺序取值（排在前面的优先级更高）
FIELD_PRIORITY = {
    '发票号码': ['DeepSeek', 'PyMuPDF', 'Qwen'],
    '开票日期': ['PyMuPDF', 'DeepSeek', 'Qwen'],
    '购买方名称': ['Qwen', 'DeepSeek', 'PyMuPDF'],
    '销售方名称': ['Qwen', 'PyMuPDF', 'DeepSeek'],
    '金额(不含税)': ['Qwen', 'DeepSeek', 'PyMuPDF'],
    '税额': ['Qwen', 'DeepSeek', 'PyMuPDF'],
    '价税合计': ['DeepSeek', 'PyMuPDF', 'Qwen'],
    '发票类型': ['DeepSeek', 'Qwen', 'PyMuPDF'],
    '发票代码': ['DeepSeek', 'PyMuPDF', 'Qwen'],
    '购买方纳税识别号': ['PyMuPDF', 'DeepSeek', 'Qwen'],
    '销售方纳税识别号': ['PyMuPDF', 'DeepSeek', 'Qwen'],
    '商品名称': ['PyMuPDF', 'DeepSeek', 'Qwen'],  # PyMuPDF 直接提取 PDF 文本最可靠
    '税率': ['PyMuPDF', 'DeepSeek', 'Qwen'],
}


def load_engine_results():
    """加载所有引擎结果，返回 {引擎名: {文件名: result}}"""
    engines = {}
    for name, path in ENGINE_PATHS.items():
        if not os.path.exists(path):
            print(f"[!] {name} 结果不存在: {path}")
            continue
        with open(path, 'r', encoding='utf-8') as f:
            data = json.load(f)
        # Qwen 输出可能有页码字段，按文件名合并（取最后一页，即主要发票页）
        by_file = {}
        for r in data:
            fn = r.get('文件名', '')
            if not fn:
                continue
            # 去掉 _hash 字段
            r_clean = {k: v for k, v in r.items() if k != '_hash'}
            by_file[fn] = r_clean
        engines[name] = by_file
        print(f"[OK] {name}: {len(by_file)} 条结果")
    return engines


def clean_amount(val):
    """清理金额字段，去除 ¥、逗号、空格等"""
    if val is None:
        return ''
    s = str(val).strip()
    s = re.sub(r'[¥￥,\s]', '', s)
    # 尝试转 float 再格式化，去除尾部多余零
    try:
        v = float(s)
        if v < 0:
            return ''
        return f'{v:.2f}'
    except (ValueError, TypeError):
        return ''


def vote_field(engines, filename, field):
    """对单个字段进行投票
    Returns: (value, source, method)
      method: 'consensus' | 'priority' | 'longest' | 'empty'
    """
    values = {}
    for name, results in engines.items():
        if filename in results:
            v = str(results[filename].get(field, '')).strip()
            if v and v != '0' and v != 'FAILED' and v != 'ERROR':
                values[name] = v

    if not values:
        return '', '', 'empty'

    # 1. 去重，取 unique values
    unique_vals = list(set(values.keys()))
    if len(unique_vals) == 1:
        # 所有引擎结果一致
        src = unique_vals[0]
        return values[src], src, 'consensus'

    # 统计每个值出现的次数
    val_to_engines = {}
    for eng, val in values.items():
        val_to_engines.setdefault(val, []).append(eng)

    # 2. 多数共识（2票及以上一致）
    for val, eng_list in val_to_engines.items():
        if len(eng_list) >= 2:
            return val, '/'.join(eng_list), 'consensus'

    # 3. 无共识，按字段优先级取值
    priority = FIELD_PRIORITY.get(field, list(engines.keys()))
    for eng in priority:
        if eng in values:
            return values[eng], eng, 'priority'

    # 不应走到这里
    first_eng = next(iter(values))
    return values[first_eng], first_eng, 'priority'


def is_garbled(text):
    """检测文本是否含有乱码（大量非常见字符）"""
    if not text:
        return True
    # 计算正常字符比例（中文、字母、数字、常见标点）
    total = len(text)
    normal = len(re.findall(r'[一-鿿A-Za-z0-9\s;、，。%\*\-]', text))
    return normal / total < 0.5 if total > 0 else True


def vote_longest_clean(engines, filename, field):
    """取最长的有效值，跳过乱码文本"""
    values = {}
    for name, results in engines.items():
        if filename in results:
            v = str(results[filename].get(field, '')).strip()
            if v and not is_garbled(v):
                values[name] = v
    if not values:
        # 所有值都是乱码，取最长的
        all_vals = {}
        for name, results in engines.items():
            if filename in results:
                v = str(results[filename].get(field, '')).strip()
                if v:
                    all_vals[name] = v
        if all_vals:
            best_eng = max(all_vals, key=lambda e: len(all_vals[e]))
            return all_vals[best_eng], best_eng, 'longest(garbled)'
        return '', '', 'empty'
    # 有多个正常值时，取共识或最长
    val_to_engines = {}
    for eng, val in values.items():
        val_to_engines.setdefault(val, []).append(eng)
    for val, eng_list in val_to_engines.items():
        if len(eng_list) >= 2:
            return val, '/'.join(eng_list), 'consensus'
    best_eng = max(values, key=lambda e: len(values[e]))
    return values[best_eng], best_eng, 'longest'


def merge_invoice_number(engines, filename):
    """发票号码专用投票：防止 Qwen 截断问题"""
    values = {}
    for name, results in engines.items():
        if filename in results:
            v = str(results[filename].get('发票号码', '')).strip()
            if v and re.match(r'^\d+$', v):
                values[name] = v

    if not values:
        return '', '', 'empty'

    # 多数共识
    val_to_engines = {}
    for eng, val in values.items():
        val_to_engines.setdefault(val, []).append(eng)
    for val, eng_list in val_to_engines.items():
        if len(eng_list) >= 2:
            return val, '/'.join(eng_list), 'consensus'

    # 无共识：取最长的（8位或20位才是有效的）
    valid = {e: v for e, v in values.items() if len(v) in (8, 20)}
    if valid:
        best_eng = max(valid, key=lambda e: len(valid[e]))
        return valid[best_eng], best_eng, 'longest'

    # 无法得到有效长度，取最长值
    best_eng = max(values, key=lambda e: len(values[e]))
    return values[best_eng], best_eng, 'longest'


def validate_and_fix(merged):
    """后处理校验与修正，返回 (fixed, warnings)"""
    warnings = []

    # 1. 金额清理
    for field in ['金额(不含税)', '税额', '价税合计']:
        original = merged.get(field, '')
        cleaned = clean_amount(original)
        if cleaned != original and original:
            warnings.append(f'{field}: 清理 "{original}" → "{cleaned}"')
            merged[field] = cleaned

    # 2. 金额校验: 金额 + 税额 ≈ 价税合计
    amt = merged.get('金额(不含税)', '')
    tax = merged.get('税额', '')
    total = merged.get('价税合计', '')

    try:
        amt_f = float(amt) if amt else None
        tax_f = float(tax) if tax else None
        total_f = float(total) if total else None

        known = sum(x is not None for x in [amt_f, tax_f, total_f])

        if known == 3:
            expected = round(amt_f + tax_f, 2)
            if abs(expected - total_f) > 0.02:
                warnings.append(f'金额校验不通过: {amt} + {tax} = {expected} ≠ {total}')
                # 用已知的两个值推算第三个
                if amt_f and tax_f:
                    merged['价税合计'] = f'{expected:.2f}'
                elif amt_f and total_f:
                    merged['税额'] = f'{round(total_f - amt_f, 2):.2f}'
                elif tax_f and total_f:
                    merged['金额(不含税)'] = f'{round(total_f - tax_f, 2):.2f}'
        elif known == 2:
            if amt_f is not None and tax_f is not None and not total:
                merged['价税合计'] = f'{round(amt_f + tax_f, 2):.2f}'
                warnings.append(f'价税合计由校验补充: {amt} + {tax} = {merged["价税合计"]}')
            elif amt_f is not None and total_f is not None and not tax:
                merged['税额'] = f'{round(total_f - amt_f, 2):.2f}'
                warnings.append(f'税额由校验补充: {total} - {amt} = {merged["税额"]}')
            elif tax_f is not None and total_f is not None and not amt:
                merged['金额(不含税)'] = f'{round(total_f - tax_f, 2):.2f}'
                warnings.append(f'金额由校验补充: {total} - {tax} = {merged["金额(不含税)"]}')
    except (ValueError, TypeError):
        pass

    # 3. 发票号码校验
    inv_num = merged.get('发票号码', '')
    if inv_num and len(inv_num) not in (8, 20):
        warnings.append(f'发票号码长度异常: {inv_num} ({len(inv_num)}位)')

    # 4. 纳税识别号校验
    for field in ['购买方纳税识别号', '销售方纳税识别号']:
        tax_id = merged.get(field, '')
        if tax_id and len(tax_id) != 18:
            warnings.append(f'{field}长度异常: {tax_id} ({len(tax_id)}位)')

    # 5. 日期校验
    date_str = merged.get('开票日期', '')
    if date_str:
        m = re.match(r'^(\d{4})-(\d{2})-(\d{2})$', date_str)
        if m:
            month, day = int(m.group(2)), int(m.group(3))
            if month < 1 or month > 12:
                warnings.append(f'开票日期月份异常: {date_str}')
            if day < 1 or day > 31:
                warnings.append(f'开票日期日期异常: {date_str}')
        elif date_str:
            warnings.append(f'开票日期格式异常: {date_str}')

    # 6. 异常金额过滤
    for field in ['金额(不含税)', '税额', '价税合计']:
        val = merged.get(field, '')
        if val:
            try:
                if float(val) <= 0:
                    warnings.append(f'{field} 值为零或负数: {val}')
            except ValueError:
                pass

    return merged, warnings


def generate_markdown(results, all_warnings):
    """生成 Markdown 报告"""
    lines = []
    lines.append('# 发票OCR交叉投票合并结果\n')
    lines.append(f'共合并 **{len(results)}** 张发票（PyMuPDF + Qwen + DeepSeek 三引擎投票）\n')

    # 统计
    total_warnings = sum(len(w) for w in all_warnings.values())
    lines.append(f'**校验警告: {total_warnings} 条**\n')

    # 汇总表
    lines.append('## 汇总表\n')
    lines.append('| 序号 | 文件名 | 发票号码 | 开票日期 | 购买方 | 销售方 | 金额 | 税额 | 价税合计 |')
    lines.append('|------|--------|----------|----------|--------|--------|------|------|----------|')

    total_amount = 0
    for i, r in enumerate(results, 1):
        amt = r.get('价税合计', '')
        try:
            total_amount += float(amt)
        except (ValueError, TypeError):
            pass
        fname = r.get('文件名', '')[:25]
        lines.append(f'| {i} | {fname} | {r.get("发票号码","")} | {r.get("开票日期","")} | {r.get("购买方名称","")[:12]} | {r.get("销售方名称","")[:12]} | {r.get("金额(不含税)","")} | {r.get("税额","")} | {r.get("价税合计","")} |')

    lines.append(f'\n**价税合计总金额: ¥{total_amount:.2f}**\n')

    # 投票来源表
    lines.append('## 各字段来源\n')
    lines.append('| 序号 | 文件名 | 发票号码 | 开票日期 | 购买方 | 销售方 | 金额 | 税额 | 价税合计 |')
    lines.append('|------|--------|----------|----------|--------|--------|------|------|----------|')
    for i, r in enumerate(results, 1):
        fname = r.get('文件名', '')[:25]
        lines.append(f'| {i} | {fname} | {r.get("_source_发票号码","")} | {r.get("_source_开票日期","")} | {r.get("_source_购买方名称","")} | {r.get("_source_销售方名称","")} | {r.get("_source_金额(不含税)","")} | {r.get("_source_税额","")} | {r.get("_source_价税合计","")} |')

    # 校验警告
    if total_warnings > 0:
        lines.append('\n## 校验警告\n')
        for fn, warns in all_warnings.items():
            if warns:
                lines.append(f'### {fn}\n')
                for w in warns:
                    lines.append(f'- {w}')
                lines.append('')

    # 详细信息
    lines.append('## 详细信息\n')
    for i, r in enumerate(results, 1):
        lines.append(f'### {i}. {r.get("文件名", "")}\n')
        for key in ['发票类型', '发票代码', '发票号码', '开票日期',
                     '购买方名称', '购买方纳税识别号',
                     '销售方名称', '销售方纳税识别号',
                     '商品名称', '金额(不含税)', '税率', '税额', '价税合计']:
            lines.append(f'- **{key}**: {r.get(key, "")}')
        lines.append('')

    return '\n'.join(lines)


def main():
    os.makedirs(OUTPUT_FOLDER, exist_ok=True)

    print("=== 发票OCR交叉投票合并 ===\n")

    # 1. 加载所有引擎结果
    engines = load_engine_results()
    if len(engines) < 2:
        print(f"\n[!] 只有 {len(engines)} 个引擎结果，至少需要 2 个才能投票")
        return

    # 2. 获取所有文件名的并集
    all_files = set()
    for results in engines.values():
        all_files.update(results.keys())
    all_files = sorted(all_files)
    print(f"\n共 {len(all_files)} 个文件\n")

    # 3. 逐文件投票 + 校验
    results = []
    all_warnings = {}

    for fn in all_files:
        merged = {'文件名': fn}

        # 各字段投票
        for field in FIELD_PRIORITY:
            if field == '发票号码':
                val, source, method = merge_invoice_number(engines, fn)
            elif field == '商品名称':
                val, source, method = vote_field(engines, fn, field)
            else:
                val, source, method = vote_field(engines, fn, field)
            merged[field] = val
            merged[f'_source_{field}'] = f'{source}({method})' if source else ''

        # 后处理校验
        merged, warnings = validate_and_fix(merged)
        all_warnings[fn] = warnings

        results.append(merged)

    # 4. 保存 JSON
    json_path = os.path.join(OUTPUT_FOLDER, '发票_投票合并.json')
    # 去掉 _source_ 前缀的内部字段用于最终输出
    results_clean = []
    for r in results:
        rc = {k: v for k, v in r.items() if not k.startswith('_source_')}
        # 保留来源信息供 MD 报告使用
        rc['_sources'] = {k.replace('_source_', ''): v for k, v in r.items() if k.startswith('_source_')}
        results_clean.append(rc)

    with open(json_path, 'w', encoding='utf-8') as f:
        json.dump(results_clean, f, ensure_ascii=False, indent=2)
    print(f'Saved JSON: {json_path}')

    # 5. 保存 CSV（不含内部字段）
    csv_path = os.path.join(OUTPUT_FOLDER, '发票_投票合并.csv')
    csv_keys = ['文件名', '发票类型', '发票代码', '发票号码', '开票日期',
                '购买方名称', '购买方纳税识别号', '销售方名称', '销售方纳税识别号',
                '商品名称', '金额(不含税)', '税率', '税额', '价税合计']
    with open(csv_path, 'w', encoding='utf-8-sig', newline='') as f:
        writer = csv.DictWriter(f, fieldnames=csv_keys, extrasaction='ignore')
        writer.writeheader()
        writer.writerows(results)
    print(f'Saved CSV:  {csv_path}')

    # 6. 保存 Markdown
    md_path = os.path.join(OUTPUT_FOLDER, '发票_投票合并.md')
    md_content = generate_markdown(results, all_warnings)
    with open(md_path, 'w', encoding='utf-8') as f:
        f.write(md_content)
    print(f'Saved MD:   {md_path}')

    # 7. 打印汇总
    total_warnings = sum(len(w) for w in all_warnings.values())
    print(f"\n完成！{len(results)} 条记录，{total_warnings} 条校验警告")
    if total_warnings > 0:
        print("\n警告详情:")
        for fn, warns in all_warnings.items():
            if warns:
                print(f"  {fn}:")
                for w in warns:
                    print(f"    - {w}")


if __name__ == '__main__':
    main()
