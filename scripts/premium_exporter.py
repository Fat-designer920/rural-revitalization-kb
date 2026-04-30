# -*- coding: utf-8 -*-
"""
premium_exporter.py - 精品导出引擎
=======================

版本: v2.3.5-part2-hotfix1.1 - 版本统一(Claude Code 系统修复)

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
            a_content = a.get("content") or ""
            header = "- **%s**" % a_type if a_type else "-"
            out.append(header)
            if a_content:
                # 二级缩进
                for ln in a_content.strip().split("\n"):
                    out.append("  " + ln)
        out.append("")

    return out


# ================================================================
# JSON 格式化(F056 v1.0 发布标准)
# ================================================================
def _build_json(rows: List[Dict],
                scope: str,
                tier_filter: Optional[List[str]],
                category_id: Optional[int]) -> str:
    """生成 F056 v1.0 发布 JSON.

    schema_version = "f056-v1.0"
    顶层 6 字段:schema_version / publish_id / published_at / scope / count / items
    KP 13 字段:见 _build_kp_payload_v1_0

    设计决策(F056 第 2 轮冻结档案 §第 1 轮已锁的 5 件事):
      1. excerpt 限长 1200 字、按句号截断;content_type='data' 放宽 2000 字
      2. kp_id 命名 `kp-{本地 id}` 字符串前缀
      3. practical_insights[].confidence 公开(high/medium/low)
      4. annotations 全发(含 disagree/correction)
      5. 8 维属性标签 v1.0 不强制 enum,本地灵活发布严格双层(v1.1 锁死)

    tier_filter / category_id 不再写入顶层(scope 已含 by_category 语义).
    """
    items = [_build_kp_payload_v1_0(r) for r in rows]

    payload = {
        "schema_version": "f056-v1.0",
        "publish_id": _generate_publish_id(),
        "published_at": _utcnow_iso(),
        "scope": scope,
        "count": len(items),
        "items": items,
    }
    return json.dumps(payload, ensure_ascii=False, indent=2)


def _build_kp_payload_v1_0(r: Dict) -> Dict:
    """单条 KnowledgePoint 13 字段构建.

    字段映射(立规则 9 真名锚点):
      kp_id              <- "kp-" + str(r["kp_id"])  # SQL AS 别名,实际是 kp.id
      title              <- r["title"]
      content_type       <- r["content_type"]
      category           <- {level1_name: r["category"], level2_name: r["subcategory"]}
      excerpt            <- _truncate_excerpt(r["original_excerpt"], r["content_type"])
      extracted_content  <- r["ai_extracted_content"](object,不锁内层)
      practical_insights <- _normalize_insights(r["practical_insights"])
      tags.category      <- r["final_category_tags"]
      tags.attributes    <- r["final_attribute_tags"]
      tags.keywords      <- r["final_keywords"]
      quality.qa_score   <- r["qa_score"]
      quality.authority  <- r["source_authority"]      # 立规则 9 第 5 次应验:这是真名
      quality.access_level <- r["access_level"]
      premium.client     <- bool(r["premium_client"])  # 0/1 -> bool
      premium.rfp        <- bool(r["premium_rfp"])
      premium.tier       <- r["premium_tier"]          # 可 null
      premium.freshness_status <- r["premium_freshness_status"]
      source.display_filename  <- renamed_filename or original_filename or null
      source.document_id <- _extract_document_id(aic)  # 从 ai_extracted_content 提取
      annotations        <- _normalize_annotations(r["annotations"])  # 无 title
      timestamps.confirmed_at <- r["confirmed_at"]
      timestamps.freshness_checked_at <- r["freshness_checked_at"]
    """
    kp_id_int = r.get("kp_id")
    aic = r.get("ai_extracted_content") or {}
    if not isinstance(aic, dict):
        aic = {}

    return {
        "kp_id": ("kp-%d" % int(kp_id_int)) if kp_id_int is not None else None,
        "title": r.get("title") or "",
        "content_type": r.get("content_type"),
        "category": {
            "level1_name": r.get("category"),
            "level2_name": r.get("subcategory"),
        },
        "excerpt": _truncate_excerpt(r.get("original_excerpt") or "", r.get("content_type")),
        "extracted_content": aic,
        "practical_insights": _normalize_insights(r.get("practical_insights")),
        "tags": {
            "category": _ensure_list(r.get("final_category_tags")),
            "attributes": _ensure_dict(r.get("final_attribute_tags")),
            "keywords": _ensure_list(r.get("final_keywords")),
        },
        "quality": {
            "qa_score": float(r.get("qa_score") or 0.0),
            "authority": r.get("source_authority") or "informal",
            "access_level": r.get("access_level") or "open",
        },
        "premium": {
            "client": bool(r.get("premium_client")),
            "rfp": bool(r.get("premium_rfp")),
            "tier": r.get("premium_tier"),  # 可 null
            "freshness_status": r.get("premium_freshness_status"),  # 可 null
        },
        "source": {
            "display_filename": r.get("renamed_filename") or r.get("original_filename") or None,
            "document_id": _extract_document_id(aic),
        },
        "annotations": _normalize_annotations(r.get("annotations") or []),
        "timestamps": {
            "confirmed_at": r.get("confirmed_at"),
            "freshness_checked_at": r.get("freshness_checked_at"),
        },
    }


# ================================================================
# F056 v1.0 字段构建辅助
# ================================================================
def _truncate_excerpt(text: str, content_type: Optional[str]) -> str:
    """按句号截断 excerpt.

    冻结档案 §第 1 轮已锁第 1 件:content_type='data' 限 2000 字,其他 1200 字.
    截断策略:在限长内寻找最后一个句号(中英文标点,中文优先);
              至少保留 70% 内容,否则硬截断防止过短.
    """
    if not text:
        return ""
    limit = 2000 if content_type == "data" else 1200
    if len(text) <= limit:
        return text
    truncated = text[:limit]
    # 中文标点优先(老唐场景中文为主)
    for punct in ("。", "!", "?", ";", ".", "!", "?"):
        idx = truncated.rfind(punct)
        if idx >= int(limit * 0.7):
            return truncated[:idx + 1]
    # 没找到合适断点,硬截断
    return truncated


def _normalize_insights(insights):
    """规范化 practical_insights,确保 {insight, basis, confidence} 三字段齐全.

    冻结档案 §第 1 轮已锁第 3 件:confidence 公开 high/medium/low.
    缺失 confidence 时默认 medium(不假装 high 也不全标 low,中性).
    """
    if not insights or not isinstance(insights, list):
        return []
    out = []
    for ins in insights:
        if isinstance(ins, dict):
            out.append({
                "insight": ins.get("insight") or ins.get("text") or ins.get("content") or "",
                "basis": ins.get("basis") or "",
                "confidence": ins.get("confidence") or "medium",
            })
        elif isinstance(ins, str):
            out.append({
                "insight": ins,
                "basis": "",
                "confidence": "medium",
            })
    return out


def _normalize_annotations(annotations):
    """规范化 annotations.

    F056 v1.0 字段:type / content / tags / created_at(无 title).
    冻结档案 §第 1 轮已锁第 4 件:全发(含 disagree/correction).
    """
    if not annotations:
        return []
    out = []
    for a in annotations:
        if not isinstance(a, dict):
            continue
        tags = a.get("tags")
        if isinstance(tags, str):
            try:
                tags = json.loads(tags)
            except Exception:
                tags = []
        if not isinstance(tags, list):
            tags = []
        out.append({
            "type": a.get("annotation_type") or "experience",
            "content": a.get("content") or "",
            "tags": tags,
            "created_at": a.get("created_at") or "",
        })
    return out


def _extract_document_id(aic: Dict) -> Optional[str]:
    """从 ai_extracted_content 提取规范化文号字符串.

    F056 v1.0 source.document_id 承重墙(冻结档案 §第 2 轮 §字段清单 顶层).
    用途:B 端投标项目经理 + C4 学生 + C5 自学者 三类客户必需,
          学术引用 / 投标文件回溯 / 用户用错时反查源头(法律闭环第 4 项).
    取值规则:遍历常见 key 模式,first match wins;无则返回 None.
    """
    if not isinstance(aic, dict):
        return None
    # 顶层常见 key
    for key in ("document_id", "doc_no", "policy_no", "文号", "发文字号", "doc_number"):
        v = aic.get(key)
        if v and isinstance(v, str) and v.strip():
            return v.strip()
    # source 子字典常见 key
    src = aic.get("source")
    if isinstance(src, dict):
        for key in ("document_id", "doc_no", "policy_no", "文号", "发文字号"):
            v = src.get(key)
            if v and isinstance(v, str) and v.strip():
                return v.strip()
    # metadata 子字典
    meta = aic.get("metadata")
    if isinstance(meta, dict):
        for key in ("document_id", "doc_no", "文号"):
            v = meta.get(key)
            if v and isinstance(v, str) and v.strip():
                return v.strip()
    return None


def _ensure_list(v) -> List:
    """JSON 字段防御:db_manager 一般已 json.loads 过,但兜底."""
    if isinstance(v, list):
        return v
    if isinstance(v, str):
        try:
            parsed = json.loads(v)
            return parsed if isinstance(parsed, list) else []
        except Exception:
            return []
    return []


def _ensure_dict(v) -> Dict:
    """JSON 字段防御:db_manager 一般已 json.loads 过,但兜底."""
    if isinstance(v, dict):
        return v
    if isinstance(v, str):
        try:
            parsed = json.loads(v)
            return parsed if isinstance(parsed, dict) else {}
        except Exception:
            return {}
    return {}


def _utcnow_iso() -> str:
    """生成 UTC ISO 8601 时间戳(末尾带 Z),format='%Y-%m-%dT%H:%M:%SZ'."""
    from datetime import timezone
    return datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")


def _generate_publish_id() -> str:
    """生成 pub-{16位 hex} 唯一 id.

    幂等 key:云端入库时按此识别重复发布(同 publish_id 视为重试).
    种子:os.urandom(16) + 当前时间字符串,SHA256 取前 16 位.
    """
    import hashlib
    import os
    seed = os.urandom(16) + str(datetime.now()).encode("utf-8")
    h = hashlib.sha256(seed).hexdigest()[:16]
    return "pub-" + h


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


# ================================================================
# F056 v1.0 校验函数(立规则 55:合并不新建,不开 f056_validator.py)
# ================================================================
import re as _re_for_validator


def validate_publish_json(json_str: str) -> Tuple[bool, List[str]]:
    """F056 v1.0 发布 JSON 校验.

    入参:
      json_str: 待校验的 JSON 字符串(_build_json 输出 / 外部传入)

    返回:
      (ok, errors):
        ok=True 时 errors=[];
        ok=False 时 errors 列出所有违规项,每项前缀 [E001]/[E002]/...

    职责:
      - 结构校验(json.loads + 七层契约)
      - 业务规则校验(限长 / 关系一致 / 字段 cross-check)
      - 不修复数据,只判定;修复由调用方决定

    错误码定位:
      E001-E002  JSON 结构损坏(阻断)
      E003-E009  顶层契约违反(阻断)
      E010-E013  KP 基础契约(阻断)
      E014       excerpt 超长(可降级)
      E020-E029  KP 嵌套字段(category/quality/premium/source/tags/annotations/timestamps)

    立规则:
      - 立规则 55:合并进 premium_exporter,不独立文件
      - 不调 V3、不调 db、纯文本入纯 list 出
    """
    errors: List[str] = []

    # ============ L0: JSON 解析 ============
    try:
        doc = json.loads(json_str)
    except Exception as e:
        return False, ["[E001] JSON 解析失败: " + str(e)]

    if not isinstance(doc, dict):
        return False, ["[E002] 顶层必须是 object,实际是 " + type(doc).__name__]

    # ============ L1: 顶层必填字段 ============
    REQUIRED_TOP = ("schema_version", "publish_id", "published_at",
                    "scope", "count", "items")
    for k in REQUIRED_TOP:
        if k not in doc:
            errors.append("[E003] 顶层缺必填字段: " + k)
    if errors:
        return False, errors

    # ============ L2: 顶层值约束 ============
    if doc["schema_version"] != "f056-v1.0":
        errors.append("[E004] schema_version 必须 'f056-v1.0',实际: " + repr(doc["schema_version"]))

    if not isinstance(doc["publish_id"], str) or not _re_for_validator.match(r"^pub-[0-9a-f]{16}$", doc["publish_id"]):
        errors.append("[E005] publish_id 不符 'pub-{16hex}' 模式,实际: " + repr(doc["publish_id"]))

    pub_at = doc["published_at"]
    if not isinstance(pub_at, str):
        errors.append("[E006] published_at 必须是字符串")
    else:
        # ISO 8601 接受 Z 后缀(通过替换为 +00:00 解析) 或 +HH:MM
        try:
            datetime.fromisoformat(pub_at.replace("Z", "+00:00"))
        except Exception:
            errors.append("[E006] published_at 不是合法 ISO 8601: " + pub_at)

    if doc["scope"] not in ("all_premium", "client_only", "rfp_only", "by_category"):
        errors.append("[E007] scope 非法: " + repr(doc["scope"]))

    if not isinstance(doc["items"], list):
        errors.append("[E008] items 必须是数组")
        return False, errors

    if not isinstance(doc["count"], int):
        errors.append("[E009] count 必须是整数")
    elif doc["count"] != len(doc["items"]):
        errors.append("[E009] count(%d) 与 len(items)(%d) 不一致" %
                      (doc["count"], len(doc["items"])))

    # ============ L3: KnowledgePoint 逐条校验 ============
    for i, kp in enumerate(doc["items"]):
        prefix = "items[%d]: " % i
        errors.extend(_validate_kp_v1_0(kp, prefix))

    return (len(errors) == 0), errors


def _validate_kp_v1_0(kp, prefix: str) -> List[str]:
    """单条 KnowledgePoint 校验.返回 errors 列表(可空)."""
    errs: List[str] = []
    if not isinstance(kp, dict):
        return [prefix + "[E010] 必须是 object"]

    REQUIRED_KP = ("kp_id", "title", "content_type", "category", "excerpt",
                   "extracted_content", "tags", "quality", "premium",
                   "source", "timestamps")
    for k in REQUIRED_KP:
        if k not in kp:
            errs.append(prefix + "[E011] 缺必填字段: " + k)
    if errs:
        return errs

    # kp_id 模式
    if not isinstance(kp["kp_id"], str) or not _re_for_validator.match(r"^kp-\d+$", kp["kp_id"]):
        errs.append(prefix + "[E012] kp_id 不符 'kp-{int}' 模式: " + repr(kp["kp_id"]))

    # content_type 枚举
    if kp["content_type"] not in ("policy", "case", "experience", "tool", "data"):
        errs.append(prefix + "[E013] content_type 非法: " + repr(kp["content_type"]))

    # title 非空
    if not isinstance(kp["title"], str) or not kp["title"].strip():
        errs.append(prefix + "[E013] title 不能为空")

    # excerpt 限长(已锁 §1)
    excerpt = kp.get("excerpt") or ""
    if not isinstance(excerpt, str):
        errs.append(prefix + "[E014] excerpt 必须是字符串")
    else:
        limit = 2000 if kp["content_type"] == "data" else 1200
        if len(excerpt) > limit:
            errs.append(prefix + "[E014] excerpt 超长 %d/%d (content_type=%s)" %
                        (len(excerpt), limit, kp["content_type"]))

    # 嵌套对象校验
    errs.extend(_validate_category(kp.get("category"), prefix))
    errs.extend(_validate_quality(kp.get("quality"), prefix))
    errs.extend(_validate_premium(kp.get("premium"), prefix))
    errs.extend(_validate_source(kp.get("source"), prefix))
    errs.extend(_validate_tags(kp.get("tags"), prefix))
    errs.extend(_validate_timestamps(kp.get("timestamps"), prefix))
    errs.extend(_validate_annotations_v1_0(kp.get("annotations"), prefix))
    errs.extend(_validate_insights(kp.get("practical_insights"), prefix))

    return errs


def _validate_category(cat, prefix: str) -> List[str]:
    if not isinstance(cat, dict):
        return [prefix + "[E020] category 必须是 object"]
    errs = []
    for k in ("level1_name", "level2_name"):
        if k not in cat:
            errs.append(prefix + "[E020] category 缺字段: " + k)
        elif cat[k] is not None and not isinstance(cat[k], str):
            errs.append(prefix + "[E020] category.%s 必须是 string 或 null" % k)
    return errs


def _validate_quality(q, prefix: str) -> List[str]:
    if not isinstance(q, dict):
        return [prefix + "[E021] quality 必须是 object"]
    errs = []
    for k in ("qa_score", "authority", "access_level"):
        if k not in q:
            errs.append(prefix + "[E021] quality 缺字段: " + k)
    if "qa_score" in q:
        s = q["qa_score"]
        if not isinstance(s, (int, float)) or s < 0 or s > 5:
            errs.append(prefix + "[E021] quality.qa_score 必须 0-5: " + repr(s))
    if "authority" in q and q["authority"] not in ("official", "authoritative", "firsthand", "informal"):
        errs.append(prefix + "[E021] quality.authority 非法: " + repr(q["authority"]))
    if "access_level" in q and q["access_level"] not in ("open", "standard", "premium"):
        errs.append(prefix + "[E021] quality.access_level 非法: " + repr(q["access_level"]))
    return errs


def _validate_premium(p, prefix: str) -> List[str]:
    if not isinstance(p, dict):
        return [prefix + "[E022] premium 必须是 object"]
    errs = []
    for k in ("client", "rfp", "tier", "freshness_status"):
        if k not in p:
            errs.append(prefix + "[E022] premium 缺字段: " + k)
    if "client" in p and not isinstance(p["client"], bool):
        errs.append(prefix + "[E022] premium.client 必须是 bool")
    if "rfp" in p and not isinstance(p["rfp"], bool):
        errs.append(prefix + "[E022] premium.rfp 必须是 bool")
    if "tier" in p and p["tier"] is not None and p["tier"] not in ("verified", "trusted", "candidate"):
        errs.append(prefix + "[E022] premium.tier 非法: " + repr(p["tier"]))
    if "freshness_status" in p and p["freshness_status"] is not None \
            and p["freshness_status"] not in ("fresh", "warning", "expired"):
        errs.append(prefix + "[E022] premium.freshness_status 非法: " + repr(p["freshness_status"]))
    return errs


def _validate_source(s, prefix: str) -> List[str]:
    if not isinstance(s, dict):
        return [prefix + "[E023] source 必须是 object"]
    errs = []
    for k in ("display_filename", "document_id"):
        if k not in s:
            errs.append(prefix + "[E023] source 缺字段: " + k)
        elif s[k] is not None and not isinstance(s[k], str):
            errs.append(prefix + "[E023] source.%s 必须是 string 或 null" % k)
    return errs


def _validate_tags(t, prefix: str) -> List[str]:
    if not isinstance(t, dict):
        return [prefix + "[E024] tags 必须是 object"]
    errs = []
    for k in ("category", "attributes", "keywords"):
        if k not in t:
            errs.append(prefix + "[E024] tags 缺字段: " + k)
    if "category" in t and not isinstance(t["category"], list):
        errs.append(prefix + "[E024] tags.category 必须是 array")
    if "attributes" in t and not isinstance(t["attributes"], dict):
        errs.append(prefix + "[E024] tags.attributes 必须是 object")
    if "keywords" in t and not isinstance(t["keywords"], list):
        errs.append(prefix + "[E024] tags.keywords 必须是 array")
    return errs


def _validate_timestamps(ts, prefix: str) -> List[str]:
    if not isinstance(ts, dict):
        return [prefix + "[E025] timestamps 必须是 object"]
    errs = []
    for k in ("confirmed_at", "freshness_checked_at"):
        if k not in ts:
            errs.append(prefix + "[E025] timestamps 缺字段: " + k)
        elif ts[k] is not None and not isinstance(ts[k], str):
            errs.append(prefix + "[E025] timestamps.%s 必须是 string 或 null" % k)
    return errs


def _validate_annotations_v1_0(annos, prefix: str) -> List[str]:
    """annotations 可空可 null;非空时每项 type ∈ 5 enum + content 必填(无 title)."""
    if annos is None or annos == []:
        return []
    if not isinstance(annos, list):
        return [prefix + "[E026] annotations 必须是 array 或 null"]
    errs = []
    for j, a in enumerate(annos):
        ap = prefix + ("annotations[%d]: " % j)
        if not isinstance(a, dict):
            errs.append(ap + "[E026] 必须是 object")
            continue
        if "type" not in a:
            errs.append(ap + "[E026] 缺字段 type")
        elif a["type"] not in ("agree", "disagree", "supplement", "correction", "experience"):
            errs.append(ap + "[E026] type 非法: " + repr(a["type"]))
        if "content" not in a:
            errs.append(ap + "[E026] 缺字段 content")
        # title 字段不应出现(冻结档案 §潜伏 bug 修复后对齐)
        if "title" in a:
            errs.append(ap + "[E026] 不应包含 title 字段(F056 v1.0 已删除)")
    return errs


def _validate_insights(ins, prefix: str) -> List[str]:
    if ins is None or ins == []:
        return []
    if not isinstance(ins, list):
        return [prefix + "[E027] practical_insights 必须是 array 或 null"]
    errs = []
    for j, item in enumerate(ins):
        ip = prefix + ("practical_insights[%d]: " % j)
        if not isinstance(item, dict):
            errs.append(ip + "[E027] 必须是 object")
            continue
        if "insight" not in item or not isinstance(item.get("insight"), str):
            errs.append(ip + "[E027] insight 必须是 string")
        if "confidence" in item and item["confidence"] not in ("high", "medium", "low"):
            errs.append(ip + "[E027] confidence 必须是 high/medium/low: " + repr(item.get("confidence")))
    return errs
