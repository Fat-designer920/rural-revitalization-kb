# -*- coding: utf-8 -*-
"""
并行双模型提取辅助模块 (v2.3.6-part1)
提供 V4-Flash 快速全覆盖 + V4-Pro 深度核心段的并行提取逻辑
"""
import json
from typing import List, Dict, Tuple, Any


def identify_core_segments(file_structure: Dict, segs: List[str]) -> List[Tuple[int, str]]:
    """
    识别核心段落(需要 V4-Pro 深度提取的段落)

    策略:
    - 一级标题段落 → 核心段
    - 包含"重点"/"关键"/"核心"等关键词的段落 → 核心段
    - 其他段落 → 非核心段(仅 V4-Flash 覆盖)

    返回: [(段索引, 段内容), ...]
    """
    core_indices = set()

    # 从 file_structure 提取一级标题位置
    sections = file_structure.get("sections", [])
    for sec in sections:
        if sec.get("level") == 1:
            # 找到对应的段索引(简化:按标题文本匹配)
            title = sec.get("title", "")
            for i, seg in enumerate(segs):
                if title in seg[:200]:  # 标题通常在段首200字内
                    core_indices.add(i)
                    break

    # 关键词匹配
    keywords = ["重点", "关键", "核心", "主要", "重要", "必须", "应当"]
    for i, seg in enumerate(segs):
        if any(kw in seg[:500] for kw in keywords):
            core_indices.add(i)

    # 如果没有识别出核心段,默认取前30%段落
    if not core_indices and segs:
        core_count = max(1, len(segs) // 3)
        core_indices = set(range(core_count))

    return [(i, segs[i]) for i in sorted(core_indices)]


def merge_and_deduplicate(flash_kps: List[Dict], pro_kps: List[Dict]) -> Tuple[List[Dict], int]:
    """
    合并两个模型的提取结果并去重

    去重策略:
    1. 完全相同的 title → 保留 V4-Pro 版本(质量更高)
    2. title 相似度 > 85% → 保留更详细的版本(excerpt 更长)
    3. 其他 → 都保留

    返回: (合并后的 kps, 去重数量)
    """
    # 先按来源标记
    for kp in flash_kps:
        kp["_source"] = "flash"
    for kp in pro_kps:
        kp["_source"] = "pro"

    # 构建 title → kp 映射
    title_map = {}
    duplicates = 0

    # 先处理 flash
    for kp in flash_kps:
        title = (kp.get("title") or "").strip()
        if not title:
            continue
        title_map[title] = kp

    # 再处理 pro,遇到重复时保留 pro
    for kp in pro_kps:
        title = (kp.get("title") or "").strip()
        if not title:
            continue

        if title in title_map:
            # 完全相同的 title → 保留 pro
            duplicates += 1
            title_map[title] = kp
        else:
            # 检查相似 title
            found_similar = False
            for existing_title in list(title_map.keys()):
                if _title_similarity(title, existing_title) > 0.85:
                    # 保留更详细的版本
                    existing_kp = title_map[existing_title]
                    existing_len = len(existing_kp.get("original_excerpt", ""))
                    new_len = len(kp.get("original_excerpt", ""))

                    if new_len > existing_len:
                        del title_map[existing_title]
                        title_map[title] = kp
                    duplicates += 1
                    found_similar = True
                    break

            if not found_similar:
                title_map[title] = kp

    # 清理临时标记
    merged = list(title_map.values())
    for kp in merged:
        kp.pop("_source", None)

    return merged, duplicates


def _title_similarity(t1: str, t2: str) -> float:
    """
    计算两个标题的相似度(简化版 Jaccard)
    """
    if not t1 or not t2:
        return 0.0

    # 字符级 bigram
    def get_bigrams(s):
        return set(s[i:i+2] for i in range(len(s)-1))

    b1 = get_bigrams(t1)
    b2 = get_bigrams(t2)

    if not b1 or not b2:
        return 1.0 if t1 == t2 else 0.0

    intersection = len(b1 & b2)
    union = len(b1 | b2)

    return intersection / union if union > 0 else 0.0
