# -*- coding: utf-8 -*-
"""
v2.3.1 F6 精品导出引擎
=======================

职责:把已封神的精品条目导出为 Markdown 或 JSON,供老唐在
    咨询场景 / 投标场景 / 写文章场景直接使用。

设计决策(Phase 2 冻结档案 §7.4):
  - 两种输出格式:Markdown(阅读友好) / JSON(结构化,v2.3.2 F056 预埋)
  - 四种范围:all_premium / client_only / rfp_only / by_category
  - 成色过滤:可选 verified/trusted/candidate 勾选
  - 文件命名:"精品导出_<scope标签>_YYYY-MM-DD.<ext>"
  - 纯读无副作用(失败走 operation_events 埋点 premium_export_success/failed)

立规则对齐:
  第 4 条:关键操作记事件(premium_export_success/failed)
  第 20 条:api_server 只做路由,导出格式化放独立模块
  第 50 条:跨模块 import 双路径兜底
"""

import json
from datetime import datetime
from typing import Dict, List, Optional, Tuple


# ================================================================
# 主入口
# ================================================================
def build_premium_export(db,
                          scope: str = "all_premium",
                          format: str = "markdown",
                          tier_filter: Optional[List[str]] = None,
                          category_id: Optional[int] = None) -> Tuple[str, str, str]:
    """生成精品导出内容.

    参数:
      scope: 'all_premium' | 'client_only' | 'rfp_only' | 'by_category'
      format: 'markdown' | 'json'
      tier_filter: 成色过滤列表,如 ['verified','trusted'],None 表示不过滤
      category_id: scope='by_category' 时必填

    返回: (content_text, filename, mime_type)
      content_text: 文件正文字符串
      filename:     建议文件名(老唐保存时看到)
      mime_type:    Content-Type(供 Flask Response 用)

    埋点: 成功走 premium_export_success,失败走 premium_export_failed
         调用方(api_server)负责 db.log_operation_event 打点,
         本模块只负责格式化,不直接记事件(避免重复埋点)
    """
    # 参数校验
    if scope not in ("all_premium", "client_only", "rfp_only", "by_category"):
        raise ValueError("scope 非法: " + str(scope))
    if format not in ("markdown", "json"):
        raise ValueError("format 必须是 'markdown' 或 'json', got: " + str(format))
    if scope == "by_category" and category_id is None:
        raise ValueError("scope='by_category' 时 category_id 必填")

    # 从 db 取数据
    rows = db.get_premium_export_data(
        scope=scope,
        tier_filter=tier_filter,
        category_id=category_id,
    )

    # 格式化
    if format == "markdown":
        content = _build_markdown(rows, scope, tier_filter, category_id)
        ext = "md"
        mime = "text/markdown; charset=utf-8"
    else:
        content = _build_json(rows, scope, tier_filter, category_id)
        ext = "json"
        mime = "application/json; charset=utf-8"

    # 文件名
    filename = _build_filename(scope, ext)
    return content, filename, mime


# ================================================================
# Markdown 格式化
# ================================================================
def _build_markdown(rows: List[Dict],
                     scope: str,
                     tier_filter: Optional[List[str]],
                     category_id: Optional[int]) -> str:
    """生成 Markdown 文档."""
    lines = []
    lines.append("# 精品知识点导出")
    lines.append("")
    lines.append("- **导出时间**:%s" % datetime.now().strftime("%Y-%m-%d %H:%M:%S"))
    lines.append("- **范围**:%s" % _scope_label(scope))
    if tier_filter:
        lines.append("- **成色过滤**:%s" % " / ".join(tier_filter))
    if scope == "by_category":
        lines.append("- **分类 ID**:%s" % category_id)
    lines.append("- **条目总数**:%d" % len(rows))
    lines.append("")
    lines.append("---")
    lines.append("")

    if not rows:
        lines.append("*(当前条件下无精品条目)*")
        return "\n".join(lines)

    # 按分类分组
    grouped: Dict[str, List[Dict]] = {}
    for r in rows:
        cat = r.get("category") or "未分类"
        subcat = r.get("subcategory") or ""
        key = (cat + " / " + subcat) if subcat else cat
        grouped.setdefault(key, []).append(r)

    for cat_path, items in grouped.items():
        lines.append("## %s(%d 条)" % (cat_path, len(items)))
        lines.append("")
        for r in items:
            lines.extend(_format_one_kp_md(r))
            lines.append("---")
            lines.append("")

    return "\n".join(lines)


def _format_one_kp_md(r: Dict) -> List[str]:
    """单条 kp 的 Markdown 段."""
    out = []
    title = r.get("title") or "(无标题)"
    out.append("### " + title)
    out.append("")

    # 元信息行
    meta_parts = []
    meta_parts.append("**质检分**:%.1f" % (r.get("qa_score") or 0.0))
    meta_parts.append("**权威级别**:%s" % (r.get("source_authority") or "-"))
    tier = r.get("premium_tier") or "trusted"
    tier_name = {"verified": "铁货", "trusted": "硬货", "candidate": "候选"}.get(tier, tier)
    meta_parts.append("**精品成色**:%s" % tier_name)
    # 精品视角
    views = []
    if r.get("premium_client"):
        views.append("客户型")
    if r.get("premium_rfp"):
        views.append("投标型")
    if views:
        meta_parts.append("**精品视角**:%s" % " + ".join(views))
    src = r.get("renamed_filename") or r.get("original_filename") or ""
    if src:
        meta_parts.append("**源文件**:%s" % src)
    out.append(" | ".join(meta_parts))
    out.append("")

    # 核心观点
    excerpt = r.get("original_excerpt") or ""
    if excerpt:
        out.append("**【核心观点】**")
        out.append("")
        out.append(excerpt.strip())
        out.append("")

    # 关键要点(从 ai_extracted_content 取)
    aic = r.get("ai_extracted_content") or {}
    if isinstance(aic, dict):
        key_points = aic.get("key_points") or []
        if isinstance(key_points, list) and key_points:
            out.append("**【关键要点】**")
            out.append("")
            for kp in key_points:
                if isinstance(kp, str):
                    out.append("- " + kp)
                elif isinstance(kp, dict):
                    out.append("- " + (kp.get("text") or kp.get("content") or str(kp)))
            out.append("")

    # 举一反三
    insights = r.get("practical_insights") or []
    if isinstance(insights, list) and insights:
        out.append("**【实操启示】**")
        out.append("")
        for idx, ins in enumerate(insights, 1):
            if isinstance(ins, str):
                out.append("%d. %s" % (idx, ins))
            elif isinstance(ins, dict):
                text = ins.get("insight") or ins.get("text") or str(ins)
                out.append("%d. %s" % (idx, text))
        out.append("")

    # 注解
    annotations = r.get("annotations") or []
    if annotations:
        out.append("**【专家注解】**")
        out.append("")
        for a in annotations:
            a_type = a.get("annotation_type") or ""
            a_title = a.get("title") or ""
            a_content = a.get("content") or ""
            header = "- **%s**" % a_type if a_type else "-"
            if a_title:
                header += " " + a_title
            out.append(header)
            if a_content:
                # 二级缩进
                for ln in a_content.strip().split("\n"):
                    out.append("  " + ln)
        out.append("")

    return out


# ================================================================
# JSON 格式化
# ================================================================
def _build_json(rows: List[Dict],
                scope: str,
                tier_filter: Optional[List[str]],
                category_id: Optional[int]) -> str:
    """生成 JSON 文档(v2.3.2 F056 发布 JSON 预埋格式)."""
    items = []
    for r in rows:
        item = {
            "id": r.get("kp_id"),
            "title": r.get("title"),
            "content_type": r.get("content_type"),
            "category": r.get("category"),
            "subcategory": r.get("subcategory"),
            "excerpt": r.get("original_excerpt"),
            "ai_extracted_content": r.get("ai_extracted_content"),
            "practical_insights": r.get("practical_insights"),
            "tags": {
                "category_tags": r.get("final_category_tags"),
                "attribute_tags": r.get("final_attribute_tags"),
                "keywords": r.get("final_keywords"),
            },
            "annotations": r.get("annotations"),
            "qa_score": r.get("qa_score"),
            "source_authority": r.get("source_authority"),
            "access_level": r.get("access_level"),
            "premium_meta": {
                "client": bool(r.get("premium_client")),
                "rfp": bool(r.get("premium_rfp")),
                "tier": r.get("premium_tier") or "trusted",
                "freshness_status": r.get("premium_freshness_status"),
            },
            "source_file": {
                "original_filename": r.get("original_filename"),
                "renamed_filename": r.get("renamed_filename"),
            },
            "timestamps": {
                "created_at": r.get("created_at"),
                "confirmed_at": r.get("confirmed_at"),
                "freshness_checked_at": r.get("freshness_checked_at"),
            },
        }
        items.append(item)

    doc = {
        "export_version": "v2.3.1",
        "generated_at": datetime.now().strftime("%Y-%m-%d %H:%M:%S"),
        "scope": scope,
        "tier_filter": tier_filter,
        "category_id": category_id,
        "count": len(items),
        "items": items,
    }
    return json.dumps(doc, ensure_ascii=False, indent=2)


# ================================================================
# 文件名生成
# ================================================================
def _build_filename(scope: str, ext: str) -> str:
    """按 scope 生成文件名.

    格式:精品导出_<scope 标签>_YYYY-MM-DD.<ext>
    """
    date_str = datetime.now().strftime("%Y-%m-%d")
    scope_tag = {
        "all_premium": "全部精品",
        "client_only": "客户型",
        "rfp_only": "投标型",
        "by_category": "分类",
    }.get(scope, scope)
    return "精品导出_%s_%s.%s" % (scope_tag, date_str, ext)


def _scope_label(scope: str) -> str:
    """scope 的人类可读标签."""
    return {
        "all_premium": "全部精品(客户型 + 投标型)",
        "client_only": "仅客户型精品",
        "rfp_only": "仅投标型精品",
        "by_category": "按分类筛选",
    }.get(scope, scope)
