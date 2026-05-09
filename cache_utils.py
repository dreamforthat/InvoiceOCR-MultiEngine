"""缓存工具 - 基于文件内容哈希的缓存失效检测"""
import hashlib
import os
import json


def file_hash(filepath):
    """计算文件内容的 MD5 哈希"""
    h = hashlib.md5()
    with open(filepath, 'rb') as f:
        for chunk in iter(lambda: f.read(8192), b''):
            h.update(chunk)
    return h.hexdigest()


def load_cached_results(json_path, src_folder, valid_extensions):
    """加载缓存结果，自动清除内容变化的过期条目

    Returns:
        dict: {filename: result_dict} 只包含有效的缓存条目
    """
    if not os.path.exists(json_path):
        return {}

    with open(json_path, 'r', encoding='utf-8') as f:
        data = json.load(f)

    # 检查缓存是否有哈希信息（旧格式缓存没有）
    has_hash = any('_hash' in r for r in data)

    if not has_hash:
        # 旧格式缓存，无法验证，全部视为有效
        return {r['文件名']: r for r in data}

    cache = {}
    invalidated = 0
    for r in data:
        fn = r['文件名']
        src_path = os.path.join(src_folder, fn)

        if not os.path.exists(src_path):
            continue

        # 检查文件扩展名
        ext = os.path.splitext(fn)[1].lower()
        if ext not in valid_extensions:
            continue

        # 对比哈希
        current_hash = file_hash(src_path)
        if current_hash != r.get('_hash', ''):
            invalidated += 1
            continue

        cache[fn] = r

    if invalidated:
        print(f"  检测到 {invalidated} 个源文件内容变化，已清除过期缓存")

    return cache


def save_cached_results(results, json_path, src_folder):
    """保存结果并附带源文件哈希"""
    # 给每条结果添加哈希
    enriched = []
    for r in results:
        r_copy = dict(r)
        fn = r_copy.get('文件名', '')
        src_path = os.path.join(src_folder, fn)
        if os.path.exists(src_path):
            r_copy['_hash'] = file_hash(src_path)
        enriched.append(r_copy)

    with open(json_path, 'w', encoding='utf-8') as f:
        json.dump(enriched, f, ensure_ascii=False, indent=2)
