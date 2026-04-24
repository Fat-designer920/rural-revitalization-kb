# -*- coding: utf-8 -*-
"""
e2e_diagnosis_exporter.py — F062 端到端测试诊断包导出引擎

v2.3.0-part3.8(2026-04-24) - 第三段按文件维度可视化白名单覆盖范围
  配套 e2e_tester.py v2.3.0-part3.8 新增的 WHITELIST_COVERAGE 常量,
  第三段从"单一的失效自检警告"升级为"按文件分类展示":
    ✅ 白名单覆盖内但命中 X 条(可能漂移)  — 需要重扫对齐
    ⚪ 未覆盖范围(需独立治理)           — 需要扩展白名单或治理代码
  好处: 老唐看报告时能一眼看出"这个文件之前就没在白名单",不会再被"白
        名单已失效"笼统警告误导(part3.6 的警告机制是真漂移 + 死角都说漂移,
        part3.8 把两者区分开)。
  版本号同步: _render_section_version_context 里的版本表对齐 part3.8

v2.3.0-part3.7(2026-04-24) - hotfix: 第三段白名单自检口径与第四段对齐
  Bug 4 - 第三段 dim4 140 vs 第四段 dim4 109 口径错配:
    根因: 第三段取 dims["dim4"]["issues"] 的 len(白名单过滤后 raw,但
          upsert_e2e_issue signature 去重前);第四段从 e2e_issues 表读
          (upsert 后入库)。两边分别是 raw 口径和入库口径,raw 会因同
          signature 重复实例多出 20-30%。
    修复: _render_section_whitelist 签名加 issues 参数,dim4/dim6 count
          从传入的入库 issues 按 dim_code 前缀 filter 数,和第四段同源。
    影响: 第三段警告里的数字不再和第四段"总计 XXX 条"相互掐架。老签名
          (lines, report) 仍兼容(issues 参数默认 None 退化到旧口径)。

v2.3.0-part3.6(2026-04-24) - hotfix: 修复 part3.5 首版诊断包三个显示 bug
  Bug 1 - 六维度权重全 0(读取侧兜底):
    根因: full_report 漏写 dim_weights 字段(part3.6 e2e_tester 已补写)
    兜底: 新报告从 fr["dim_weights"] 读;历史报告按 fr["scan_depth"] fallback 到常量
    好处: 老唐已存在的历史报告(比如 report_id=9)不用重跑也能正确渲染
  Bug 2 - 白名单过滤显示"无过滤项":
    根因: e2e_tester.py DIM4/DIM6 白名单行号跟 db_manager.py v2.3.0-part3.4 完全对不上
    修复: 第三段改为显式自检输出,告诉 Claude"可能白名单已失效"而不是装没事
    长期: 白名单重扫对齐 v2.3.0-part3.4 真实行号留待单独 hotfix
  Bug 3 - 近 7 天事件日志永远显示"无事件":
    根因: SQL 字段名拼错 created_at/payload 应为 event_time/payload_json
    修复: 查询 SQL + 渲染读取两处字段名全部修正

v2.3.0-part3.5(2026-04-24) - feature 首版:
  F062 配套功能:把 E2E 测试报告和 issue 列表格式化为 Markdown 诊断包,
  用于发给 Claude/工程师做异地诊断。

对外接口(唯一):
  build_e2e_diagnosis_markdown(db, report_id) -> (markdown_text, filename)
    report_id 不存在时抛 ValueError。

设计原则:
  - 纯读:不写 DB、不调 AI、无副作用
  - 聚合优先:相同 (rule_id + 文件 + dim_code) 的 issue 合并展示,
             避免 Markdown 冗长 + 防止 Claude 对同一模式重复诊断
  - payload 双格式兜底:既兼容 {rule_id, file, line, snippet, msg} 顶层扁平,
                        也兼容 {rule_id, detail:{file,line,snippet,msg}} 嵌套
    —— 对齐立规则第 9 条"不靠记忆,写兜底"精神
  - 事件日志抽样:按 event_type 分桶,每类最多 5 条,总上限 150 条
  - 时间锚点:事件日志以报告 created_at 为锚点往前 7 天,反映报告那一刻的系统状态
  - 文本截断:snippet 最多 6 行,msg/payload 最多 300 字符,防单条爆炸
  - 权重双源(part3.6):新版 full_report 写 dim_weights;读不到时按 scan_depth
    fallback 到 e2e_tester.DIM_WEIGHTS_DEEP/QUICK 常量,历史报告不丢信息

立规则对齐:
  - 第 5 条 JSON 字段自动反序列化(payload_json → dict)
  - 第 14 条 severity 严格三态(info/warning/error)
  - 第 20 条 业务逻辑放独立模块,api_server 只做路由
  - 第 49 条(part3.6 新立) 大文件修改用拷贝+局部替换,别重出整文件
"""

import json
from collections import OrderedDict
from datetime import datetime, timedelta

# part3.8: 尝试引入 e2e_tester 的 WHITELIST_COVERAGE 常量(按文件维度覆盖范围)
# 兜底: 若 e2e_tester 升级前老版本跑这个 exporter,fallback 到空 set(第三段
# 按文件维度分类逻辑自动降级为不区分 "覆盖内 vs 覆盖外")
try:
    from scripts.e2e_tester import WHITELIST_COVERAGE as _WHITELIST_COVERAGE
except Exception:
    try:
        from e2e_tester import WHITELIST_COVERAGE as _WHITELIST_COVERAGE
    except Exception:
        _WHITELIST_COVERAGE = set()


# ============================================================
# 常量
# ============================================================

# severity 排序权重(error 最严重,排最前)
_SEVERITY_ORDER = {"error": 0, "warning": 1, "info": 2}

# 维度中文名映射(展示用)
_DIM_LABELS = {
    "dim1": "① 路由自省",
    "dim2": "② 启动就绪性",
    "dim3": "③ Prompt 一致性",
    "dim4": "④ 字段契约",
    "dim5": "⑤ 事件语义",
    "dim6": "⑥ 代码异味",
}

# 事件日志抽样参数
_EVENT_SAMPLE_PER_TYPE = 5
_EVENT_TOTAL_CAP = 150
_EVENT_LOOKBACK_DAYS = 7

# 文本截断上限
_PAYLOAD_MAX_CHARS = 300
_SNIPPET_MAX_LINES = 6
_SNIPPET_MAX_CHARS = 400


# ============================================================
# 对外唯一入口
# ============================================================

def build_e2e_diagnosis_markdown(db, report_id):
    """构造 E2E 诊断包 Markdown。

    Args:
        db: DatabaseManager 实例
        report_id: int, E2E 报告 ID

    Returns:
        (markdown_text: str, filename: str)

    Raises:
        ValueError: report_id 不存在
    """
    # Step 1: 取报告本体
    report = db.get_e2e_test_report_detail(report_id)
    if not report:
        raise ValueError("report not found: " + str(report_id))

    # Step 2: 取该报告的所有 issue(四态全部,按 severity 排序)
    issues = _load_issues_by_report(db, report_id)

    # Step 3: 按 (rule_id + 文件 + dim_code) 聚合
    groups = _aggregate_issues(issues)

    # Step 4: 取近 7 天 warn/error 事件(以报告创建时间为锚点)
    events_by_type = _load_recent_events(db, report.get("created_at"))

    # Step 5: 组装 Markdown
    md = _render_markdown(report, issues, groups, events_by_type)

    # Step 6: 文件名
    filename = "e2e_diagnosis_{}_{}.md".format(report_id, _now_stamp())
    return md, filename


# ============================================================
# 数据加载
# ============================================================

def _load_issues_by_report(db, report_id):
    """取某份报告的所有 issue(含四态),按 severity 升序(error 最前)。"""
    try:
        conn = db.get_connection()
        c = conn.cursor()
        c.execute(
            """SELECT issue_id, report_id, dim_code, endpoint, severity,
                      signature, status, first_seen_at, last_seen_at,
                      occurrence_count, resolved_at, payload_json
               FROM e2e_issues
               WHERE report_id = ?
               ORDER BY CASE severity
                   WHEN 'error' THEN 0
                   WHEN 'warning' THEN 1
                   WHEN 'info' THEN 2
                   ELSE 9
               END, dim_code, signature""",
            (report_id,),
        )
        rows = c.fetchall()
        cols = [d[0] for d in c.description]
        items = []
        for r in rows:
            row = dict(zip(cols, r))
            raw = row.pop("payload_json") or "{}"
            try:
                row["payload"] = json.loads(raw) if isinstance(raw, str) else (raw or {})
            except Exception:
                row["payload"] = {}
            items.append(row)
        conn.close()
        return items
    except Exception:
        # 查询失败返回空,不中断主流程(单维度异常隔离精神)
        return []


def _load_recent_events(db, anchor_time):
    """取报告 created_at 往前 7 天的 warn/error 事件,按 event_type 分桶抽样。

    Returns:
        OrderedDict: {event_type: {"total": N, "samples": [event_dict, ...]}}
        按 total 降序。
    """
    # 计算时间窗口(锚点是报告创建时刻,不是"现在")
    try:
        anchor = _parse_iso_time(anchor_time) if anchor_time else datetime.now()
    except Exception:
        anchor = datetime.now()
    start_time = anchor - timedelta(days=_EVENT_LOOKBACK_DAYS)

    try:
        conn = db.get_connection()
        c = conn.cursor()
        # part3.6 修复: operation_events 真实字段名是 event_time / payload_json,
        # 不是 created_at / payload。老 SQL 抛 no such column 被 except 静默接住,
        # 导致诊断包"近 7 天事件"永远空。详见 db_manager.py 第 363-376 行表定义。
        c.execute(
            """SELECT event_type, module, severity, event_time, payload_json
               FROM operation_events
               WHERE severity IN ('warning', 'error')
                 AND datetime(event_time) >= datetime(?)
                 AND datetime(event_time) <= datetime(?)
               ORDER BY event_time DESC""",
            (
                start_time.strftime("%Y-%m-%d %H:%M:%S"),
                anchor.strftime("%Y-%m-%d %H:%M:%S"),
            ),
        )
        rows = c.fetchall()
        cols = [d[0] for d in c.description]
        conn.close()
    except Exception:
        return OrderedDict()

    # 按 event_type 分桶
    buckets = {}
    for r in rows:
        row = dict(zip(cols, r))
        etype = row.get("event_type") or "unknown"
        if etype not in buckets:
            buckets[etype] = {"total": 0, "samples": []}
        buckets[etype]["total"] += 1
        if len(buckets[etype]["samples"]) < _EVENT_SAMPLE_PER_TYPE:
            buckets[etype]["samples"].append(row)

    # 按 total 降序;套总样本上限(防单类刷屏)
    sorted_buckets = sorted(buckets.items(), key=lambda x: -x[1]["total"])
    result = OrderedDict()
    total_samples = 0
    for etype, info in sorted_buckets:
        if total_samples >= _EVENT_TOTAL_CAP:
            break
        remain = _EVENT_TOTAL_CAP - total_samples
        samples = info["samples"][:remain]
        result[etype] = {"total": info["total"], "samples": samples}
        total_samples += len(samples)
    return result


# ============================================================
# 聚合
# ============================================================

def _aggregate_issues(issues):
    """按 (dim_code, rule_id, 文件或端点) 三元组聚合 issue。

    Returns:
        list[dict]:按 severity 升序 + count 降序 + file 字母序排。
        每个 group 含:
          - severity (组内最严重)
          - dim_code / rule_id / file / endpoint
          - count (命中数)
          - lines (去重排序的行号列表)
          - status_dist ({pending:N, fixed:M, ...})
          - first_seen / last_seen (组内最早 / 最晚)
          - representative_snippet / representative_msg (组内第一条有值的)
          - sample_items (前 5 条完整 item,展示多行代表)
    """
    buckets = OrderedDict()
    for it in issues:
        rule_id, file_path, line, _snippet, _msg = _extract_payload_fields(
            it.get("payload") or {}
        )
        # rule_id 兜底:从 signature 解(dim_code|file:line|rule_id)
        if not rule_id:
            rule_id = _extract_rule_from_signature(it.get("signature") or "")
        loc = file_path or it.get("endpoint") or "-"
        key = (it.get("dim_code") or "-", rule_id or "-", loc)
        if key not in buckets:
            buckets[key] = {
                "dim_code": it.get("dim_code"),
                "rule_id": rule_id,
                "file": file_path,
                "endpoint": it.get("endpoint"),
                "severities": [],
                "count": 0,
                "lines": set(),
                "status_dist": {},
                "first_seen": None,
                "last_seen": None,
                "items": [],
            }
        b = buckets[key]
        b["severities"].append(it.get("severity") or "info")
        b["count"] += 1
        if line is not None:
            b["lines"].add(line)
        st = it.get("status") or "pending"
        b["status_dist"][st] = b["status_dist"].get(st, 0) + 1
        first = it.get("first_seen_at")
        last = it.get("last_seen_at")
        if first and (not b["first_seen"] or first < b["first_seen"]):
            b["first_seen"] = first
        if last and (not b["last_seen"] or last > b["last_seen"]):
            b["last_seen"] = last
        b["items"].append(it)

    # 整理输出
    groups = []
    for _, b in buckets.items():
        # 取组内最严重 severity(error < warning < info)
        sev_weights = [_SEVERITY_ORDER.get(s, 9) for s in b["severities"]]
        worst_severity = b["severities"][sev_weights.index(min(sev_weights))]

        # 典型片段:取组内第一条有值的 snippet / msg
        rep_snippet = ""
        rep_msg = ""
        for it in b["items"]:
            _, _, _, sn, mg = _extract_payload_fields(it.get("payload") or {})
            if sn and not rep_snippet:
                rep_snippet = sn
            if mg and not rep_msg:
                rep_msg = mg
            if rep_snippet and rep_msg:
                break

        groups.append({
            "dim_code": b["dim_code"],
            "rule_id": b["rule_id"],
            "file": b["file"],
            "endpoint": b["endpoint"],
            "severity": worst_severity,
            "count": b["count"],
            "lines": sorted(b["lines"]),
            "status_dist": b["status_dist"],
            "first_seen": b["first_seen"],
            "last_seen": b["last_seen"],
            "representative_snippet": rep_snippet,
            "representative_msg": rep_msg,
            "sample_items": b["items"][:5],
        })

    # 排序:severity 升序(error 最前),count 降序,file 字母序
    groups.sort(key=lambda g: (
        _SEVERITY_ORDER.get(g["severity"], 9),
        -g["count"],
        g.get("file") or g.get("endpoint") or "zzz",
    ))
    return groups


def _extract_payload_fields(payload):
    """从 payload 取 (rule_id, file, line, snippet, msg) 五元组,兼容两种存储格式:
       A) 顶层扁平: {"rule_id":..., "file":..., "line":..., "snippet":..., "msg":...}
       B) detail 嵌套: {"rule_id":..., "detail":{"file":..., "line":..., "snippet":..., "msg":...}}

    未来 payload 结构再变也可扩展此函数,保持调用方无感。
    """
    if not isinstance(payload, dict):
        return None, None, None, None, None

    rule_id = payload.get("rule_id")
    # 先取顶层
    file_path = payload.get("file")
    line = payload.get("line")
    snippet = payload.get("snippet")
    msg = payload.get("msg") or payload.get("message")

    # 顶层没有则下探 detail 子字典
    detail = payload.get("detail")
    if isinstance(detail, dict):
        if not file_path:
            file_path = detail.get("file")
        if line is None:
            line = detail.get("line")
        if not snippet:
            snippet = detail.get("snippet")
        if not msg:
            msg = detail.get("msg") or detail.get("message")

    # line 强转 int(容忍字符串 "300")
    try:
        if line is not None:
            line = int(line)
    except (TypeError, ValueError):
        line = None

    return rule_id, file_path, line, snippet, msg


def _extract_rule_from_signature(signature):
    """从 signature 'dim_code|file:line|rule_id' 里提取最后一段 rule_id。"""
    if not signature:
        return ""
    parts = signature.split("|")
    return parts[-1] if len(parts) >= 3 else ""


# ============================================================
# Markdown 渲染(7 段)
# ============================================================

def _render_markdown(report, issues, groups, events_by_type):
    lines = []

    report_id = report.get("report_id") or "--"
    created_at = report.get("created_at") or ""
    scan_depth = (report.get("scan_depth") or "").upper()

    # 标题 + 摘要
    lines.append("# E2E 端到端测试诊断包")
    lines.append("")
    lines.append("> 报告 ID: **{}**  |  报告时间: {}  |  导出时间: {}".format(
        report_id, created_at, _now_display()))
    lines.append("> 扫描深度: **{}**  |  Issue 总数: **{}**  |  聚合组数: **{}**".format(
        scan_depth or "未知", len(issues), len(groups)))
    lines.append("")

    _render_section_metadata(lines, report)
    _render_section_dimensions(lines, report)
    _render_section_whitelist(lines, report, issues)
    _render_section_issues(lines, groups, issues)
    _render_section_events(lines, events_by_type)
    _render_section_instructions(lines)
    _render_section_version_context(lines)

    return "\n".join(lines) + "\n"


def _render_section_metadata(lines, report):
    lines.append("## 一、报告元数据")
    lines.append("")
    lines.append("| 字段 | 值 |")
    lines.append("|---|---|")
    lines.append("| 报告 ID | {} |".format(report.get("report_id") or "--"))
    lines.append("| 创建时间 | {} |".format(report.get("created_at") or "--"))
    lines.append("| 触发方式 | {} |".format(report.get("trigger_type") or "--"))
    lines.append("| 扫描深度 | {} |".format(report.get("scan_depth") or "--"))
    lines.append("| 端点总数 | {} |".format(report.get("total_endpoints") or 0))
    lines.append("| passed | {} |".format(report.get("passed_count") or 0))
    lines.append("| warning | {} |".format(report.get("warning_count") or 0))
    lines.append("| failed | {} |".format(report.get("failed_count") or 0))
    lines.append("| V3 调用 | {} 次 |".format(report.get("v3_call_count") or 0))
    try:
        cost = float(report.get("cost_estimate") or 0)
        lines.append("| 估算成本 | {:.6f} 元 |".format(cost))
    except Exception:
        lines.append("| 估算成本 | -- |")

    fr = _get_full_report(report)
    total_score = fr.get("total_score")
    if total_score is not None:
        lines.append("| **总分** | **{}** |".format(total_score))
    dur = fr.get("duration_seconds")
    if dur is not None:
        try:
            dur_f = float(dur)
            disp = "<1s" if dur_f <= 0 else "{}s".format(int(dur_f))
            lines.append("| 扫描耗时 | {} |".format(disp))
        except Exception:
            pass
    lines.append("")


def _resolve_dim_weights(fr):
    """part3.6 新增:读取侧权重兜底。

    新报告从 fr["dim_weights"] 读(e2e_tester.py v2.3.0-part3.6 起已落库);
    历史报告 fr 里没这个字段,按 fr["scan_depth"] fallback 到 e2e_tester 常量。
    import 失败也不崩,返回空字典让上层渲染"--"。
    """
    weights = fr.get("dim_weights")
    if isinstance(weights, dict) and weights:
        return weights
    # fallback: 历史报告走这里
    scan_depth = (fr.get("scan_depth") or "deep").lower()
    try:
        from scripts.e2e_tester import DIM_WEIGHTS_DEEP, DIM_WEIGHTS_QUICK
    except Exception:
        try:
            from e2e_tester import DIM_WEIGHTS_DEEP, DIM_WEIGHTS_QUICK
        except Exception:
            return {}
    return dict(DIM_WEIGHTS_DEEP) if scan_depth == "deep" else dict(DIM_WEIGHTS_QUICK)


def _render_section_dimensions(lines, report):
    lines.append("## 二、六维度得分")
    lines.append("")

    fr = _get_full_report(report)
    dims = fr.get("dims") or {}
    weights = _resolve_dim_weights(fr)

    lines.append("| 维度 | 得分 | 权重 | 加权贡献 | 状态 |")
    lines.append("|---|---|---|---|---|")

    for k in ("dim1", "dim2", "dim3", "dim4", "dim5", "dim6"):
        d = dims.get(k) or {}
        score = d.get("score")
        skipped = d.get("skipped") is True
        weight = weights.get(k, 0)
        if skipped:
            score_disp = "skipped"
            contrib = "--"
            status = "跳过"
        elif score is None:
            score_disp = "--"
            contrib = "--"
            status = "无数据"
        else:
            try:
                score_f = float(score)
                score_disp = "{}".format(score)
                contrib = "{:.2f}".format(score_f * float(weight or 0))
                if score_f >= 85:
                    status = "良好"
                elif score_f >= 60:
                    status = "一般"
                else:
                    status = "差"
            except Exception:
                score_disp = str(score)
                contrib = "--"
                status = "解析错误"
        try:
            weight_disp = "{:.2f}".format(float(weight or 0))
        except Exception:
            weight_disp = "--"
        lines.append("| {} | {} | {} | {} | {} |".format(
            _DIM_LABELS[k], score_disp, weight_disp, contrib, status,
        ))
    lines.append("")


def _render_section_whitelist(lines, report, issues=None):
    """part3.7:新增 issues 参数,用于第三段 dim4/dim6 count 与第四段聚合
    清单(=入库 e2e_issues 口径)对齐。老签名 (lines, report) 仍兼容。
    """
    lines.append("## 三、白名单过滤统计")
    lines.append("")

    fr = _get_full_report(report)
    dims = fr.get("dims") or {}
    f4 = (dims.get("dim4") or {}).get("filtered_out") or []
    f6 = (dims.get("dim6") or {}).get("filtered_out") or []
    total = len(f4) + len(f6)

    if total == 0:
        # part3.6 修复: 不再一句"无白名单过滤项"就收工,加失效自检。
        # 白名单一条都没命中通常意味着行号已漂移(db_manager.py 改动后没重扫)。
        # 诊断包自己告诉 Claude 自己可能在骗他,避免 Claude 照单全收"0 条过滤"。
        #
        # part3.7 口径修复: 原本取 dims["dim4"]["issues"] 的 len(过滤后 raw,
        # upsert 前),与第四段聚合清单(e2e_issues 表 upsert 后入库)口径不一致,
        # 导致第三段说"dim4 140"、第四段合计只有 109 条。改为从传入的 issues
        # (入库后,与第四段同源)按 dim_code 前缀 filter 数。
        if issues is not None:
            dim4_issue_count = sum(
                1 for iss in issues
                if (iss.get("dim_code") or "").startswith("4_")
            )
            dim6_issue_count = sum(
                1 for iss in issues
                if (iss.get("dim_code") or "").startswith("6_")
            )
        else:
            # 兼容老签名(不传 issues 时退回到 dims.issues 的 raw 口径)
            dim4_issue_count = len((dims.get("dim4") or {}).get("issues") or [])
            dim6_issue_count = len((dims.get("dim6") or {}).get("issues") or [])
        lines.append("**⚠️ 本次扫描未过滤任何已知合理项**。两种可能:")
        lines.append("")
        lines.append("- **(a) 白名单确无命中**:dim4/dim6 真的干净,本库当前状态无\"已知合理项\"")
        lines.append(
            "- **(b) 白名单已失效**(行号漂移):`e2e_tester.py` 的 "
            "DIM4/DIM6_KNOWN_FALSE_POSITIVES 基准行号跟当前 `db_manager.py` 对不上"
        )
        lines.append("")
        if dim4_issue_count + dim6_issue_count >= 20:
            lines.append(
                "**当前 dim4/dim6 共命中 {} 条 issue(dim4 {} / dim6 {})**,"
                "若远高于历史基线,**99% 是情况 (b) 白名单已失效**,"
                "建议对照附录 issue 清单二次人工判断已知合理项。".format(
                    dim4_issue_count + dim6_issue_count,
                    dim4_issue_count,
                    dim6_issue_count,
                )
            )
        else:
            lines.append(
                "当前 dim4/dim6 共命中 {} 条 issue,数量不高,"
                "情况 (a) 或 (b) 都可能,建议扫 issue 清单粗判。".format(
                    dim4_issue_count + dim6_issue_count
                )
            )
        lines.append("")
        # part3.8: 失效警告后也要按文件维度展示(区分"漂移" vs "未覆盖")
        _render_whitelist_coverage_breakdown(lines, issues)
        return

    lines.append(
        "**共过滤 {} 条已知合理项**(DIM4 字段契约 {} 条 + DIM6 代码异味 {} 条)。".format(
            total, len(f4), len(f6)
        )
    )
    lines.append(
        "这些 signature 已在 `scripts/e2e_tester.py` 白名单内,"
        "**诊断时请跳过,不视为问题**。"
    )
    lines.append("")

    # 前 5+5 条示例
    show = list(f4[:5]) + list(f6[:5])
    if show:
        lines.append("**示例(前 {} 条)**:".format(len(show)))
        lines.append("")
        for it in show:
            sig = _md_escape(it.get("signature") or "")
            reason = it.get("_filter_reason") or ""
            suffix = "  -- {}".format(reason) if reason else ""
            lines.append("- `{}`{}".format(sig, suffix))
        lines.append("")

    # ==========================================================
    # part3.8: 按文件维度分类展示(覆盖内 vs 覆盖外)
    # ==========================================================
    _render_whitelist_coverage_breakdown(lines, issues)


def _render_whitelist_coverage_breakdown(lines, issues):
    """part3.8 新增:按文件维度展示"白名单覆盖内 vs 覆盖外"。

    输入: 入库 issues 列表(dim4 + dim6 的真正 pending)
    逻辑:
      - 从 WHITELIST_COVERAGE 常量拿覆盖文件集合
      - 对每个 dim4/dim6 issue 抽取 file,按是否在覆盖内分两栏:
        ✅ 覆盖内但命中 X 条 → 提示"行号可能已漂移,建议重扫白名单"
        ⚪ 覆盖外有 X 条 → 提示"新文件未进白名单,需要独立治理"
      - 老版本 e2e_tester(没有 WHITELIST_COVERAGE 常量)时 _WHITELIST_COVERAGE 为空,
        降级为单一列表展示,不分"覆盖内/外"

    为什么加这个视图:
      part3.6 加的"白名单已失效"警告是笼统的 —— 真正漂移 vs 文件从未进白名单
      两种情况混在一起。part3.8 WHITELIST_COVERAGE 把两者区分开,让老唐看报告时
      不再被"失效"笼统警告误导。
    """
    if not issues:
        return
    # 从 issues 里分 dim4/dim6 并按 file 聚合
    file_stats = {}  # file -> {"dim4": count, "dim6": count}
    for iss in issues:
        dim = iss.get("dim_code") or ""
        if not (dim.startswith("4_") or dim.startswith("6_")):
            continue
        detail = iss.get("detail") or {}
        if isinstance(detail, str):
            try:
                detail = json.loads(detail)
            except Exception:
                detail = {}
        file_path = detail.get("file") or ""
        if not file_path:
            # 从 signature 反解: dim|file:line|rule_id
            sig = iss.get("signature") or ""
            parts = sig.split("|")
            if len(parts) >= 2 and ":" in parts[1]:
                file_path = parts[1].rsplit(":", 1)[0]
        if not file_path:
            continue
        if file_path not in file_stats:
            file_stats[file_path] = {"dim4": 0, "dim6": 0}
        if dim.startswith("4_"):
            file_stats[file_path]["dim4"] += 1
        else:
            file_stats[file_path]["dim6"] += 1

    if not file_stats:
        return

    lines.append("### 3.1 白名单覆盖范围分布(按文件维度,part3.8 视图)")
    lines.append("")
    lines.append("**说明**:")
    lines.append(
        "- ✅ 覆盖内但命中 X 条 = 该文件在白名单范围内,但仍有 X 条漏网。"
        "通常是 db_manager 等文件重构后行号漂移,**建议重扫对齐**"
    )
    lines.append(
        "- ⚪ 未覆盖范围 = 该文件从未进白名单。通常是新文件首次被 E2E 扫到,"
        "**需要独立治理**(加入 WHITELIST_COVERAGE 并逐条判断新白名单)"
    )
    lines.append("")

    covered = []
    uncovered = []
    for file_path, st in sorted(file_stats.items()):
        total_file = st["dim4"] + st["dim6"]
        if file_path in _WHITELIST_COVERAGE:
            covered.append((file_path, st, total_file))
        else:
            uncovered.append((file_path, st, total_file))

    if covered:
        lines.append("**✅ 覆盖内命中(可能行号漂移)**:")
        lines.append("")
        lines.append("| 文件 | dim4 | dim6 | 合计 |")
        lines.append("|---|---|---|---|")
        for file_path, st, total_file in covered:
            lines.append("| `{}` | {} | {} | {} |".format(
                file_path, st["dim4"], st["dim6"], total_file))
        lines.append("")

    if uncovered:
        lines.append("**⚪ 未覆盖范围(需独立治理)**:")
        lines.append("")
        lines.append("| 文件 | dim4 | dim6 | 合计 |")
        lines.append("|---|---|---|---|")
        for file_path, st, total_file in uncovered:
            lines.append("| `{}` | {} | {} | {} |".format(
                file_path, st["dim4"], st["dim6"], total_file))
        lines.append("")
        lines.append(
            "**处置建议**:把上述文件加入 `scripts/e2e_tester.py` 的 "
            "`WHITELIST_COVERAGE` 常量,然后逐条判断新白名单 signature。"
        )
        lines.append("")


def _render_section_issues(lines, groups, issues):
    lines.append("## 四、Issue 聚合清单")
    lines.append("")

    if not issues:
        lines.append(
            "**本报告无 issue**(或 issue 落库失败,请查第五段事件日志摘要中的 `e2e_issue_upsert_failed`)。"
        )
        lines.append("")
        return

    # 汇总统计
    status_total = {"pending": 0, "intermittent": 0, "fixed": 0, "ignored": 0}
    sev_total = {"error": 0, "warning": 0, "info": 0}
    for it in issues:
        st = it.get("status") or "pending"
        sv = it.get("severity") or "info"
        if st in status_total:
            status_total[st] += 1
        if sv in sev_total:
            sev_total[sv] += 1

    lines.append("**总计**:{} 条 issue,聚合为 {} 组。".format(len(issues), len(groups)))
    lines.append("")
    lines.append("**严重程度分布**:error `{}` / warning `{}` / info `{}`".format(
        sev_total["error"], sev_total["warning"], sev_total["info"]))
    lines.append("**状态分布**:pending `{}` / intermittent `{}` / fixed `{}` / ignored `{}`".format(
        status_total["pending"], status_total["intermittent"],
        status_total["fixed"], status_total["ignored"]))
    lines.append("")

    # 4.1 诊断概览表
    lines.append("### 4.1 诊断概览表(按 severity 降序)")
    lines.append("")
    lines.append("| # | severity | dim_code | rule_id | 文件/端点 | 命中 | 状态分布 |")
    lines.append("|---|---|---|---|---|---|---|")
    for i, g in enumerate(groups, 1):
        loc = g.get("file") or g.get("endpoint") or "-"
        status_parts = []
        for st in ("pending", "intermittent", "fixed", "ignored"):
            n = g["status_dist"].get(st, 0)
            if n > 0:
                status_parts.append("{}:{}".format(st, n))
        status_disp = " ".join(status_parts) or "-"
        lines.append("| {} | {} | {} | `{}` | `{}` | {} | {} |".format(
            i,
            g["severity"],
            g["dim_code"] or "-",
            _md_escape(g["rule_id"] or "-"),
            _md_escape(loc),
            g["count"],
            status_disp,
        ))
    lines.append("")

    # 4.2 详细聚合(按 severity 分区)
    lines.append("### 4.2 详细聚合(error → warning → info)")
    lines.append("")

    for sev_key, sev_label in (
        ("error", "error(必修)"),
        ("warning", "warning(重点关注)"),
        ("info", "info(代码质量建议)"),
    ):
        sub = [g for g in groups if g["severity"] == sev_key]
        if not sub:
            continue
        lines.append("#### {} · 共 {} 组".format(sev_label, len(sub)))
        lines.append("")
        for i, g in enumerate(sub, 1):
            _render_one_group(lines, g, sev_key[0].upper(), i)


def _render_one_group(lines, g, sev_prefix, idx):
    loc = g.get("file") or g.get("endpoint") or "-"
    lines.append("##### 【{}{}】{} · `{}` · `{}` ({} 条)".format(
        sev_prefix, idx,
        g["dim_code"] or "-",
        _md_escape(g["rule_id"] or "-"),
        _md_escape(loc),
        g["count"],
    ))
    lines.append("")

    # 命中行号(折叠成一行,便于目测"密集度")
    if g["lines"]:
        if len(g["lines"]) <= 40:
            lines_str = ", ".join(str(l) for l in g["lines"])
        else:
            head = ", ".join(str(l) for l in g["lines"][:20])
            tail = ", ".join(str(l) for l in g["lines"][-10:])
            lines_str = head + ",  ...  ," + tail + "(共 {} 行)".format(len(g["lines"]))
        lines.append("- **命中行号**: {}".format(lines_str))
    elif g.get("endpoint"):
        lines.append("- **端点**: `{}`".format(_md_escape(g["endpoint"])))

    # 状态分布
    status_parts = []
    for st in ("pending", "intermittent", "fixed", "ignored"):
        n = g["status_dist"].get(st, 0)
        if n > 0:
            status_parts.append("{} {}".format(st, n))
    if status_parts:
        lines.append("- **状态分布**: {}".format(" / ".join(status_parts)))

    # 时间范围
    if g["first_seen"] or g["last_seen"]:
        lines.append("- **时间范围**: 首次 {}  /  最近 {}".format(
            g["first_seen"] or "-", g["last_seen"] or "-"))
    lines.append("")

    # msg
    if g["representative_msg"]:
        lines.append("**msg**:{}".format(
            _truncate(g["representative_msg"], _PAYLOAD_MAX_CHARS)))
        lines.append("")

    # 典型代码片段
    if g["representative_snippet"]:
        lines.append("**典型代码片段**:")
        lines.append("")
        lines.append("```python")
        lines.append(_truncate_snippet(g["representative_snippet"]))
        lines.append("```")
        lines.append("")

    # 其他代表行(如果有 snippet 差异,列前 3 条单行)
    if len(g["sample_items"]) > 1 and g["representative_snippet"]:
        other_samples = []
        rep_norm = (g["representative_snippet"] or "").strip()
        for it in g["sample_items"][1:]:
            _, _, ln, sn, _ = _extract_payload_fields(it.get("payload") or {})
            if sn and sn.strip() != rep_norm:
                first_line = sn.split("\n")[0].strip()
                if first_line and len(first_line) <= 120:
                    other_samples.append((ln, first_line))
        if other_samples:
            lines.append("**其他代表行(片段首行)**:")
            for ln, snip in other_samples[:3]:
                lines.append("- 行 {}: `{}`".format(
                    ln if ln is not None else "-", _md_escape(snip)))
            lines.append("")

    lines.append("")


def _render_section_events(lines, events_by_type):
    lines.append("## 五、近 7 天 warn/error 事件日志摘要")
    lines.append("")

    if not events_by_type:
        lines.append("**近 7 天内无 warn/error 事件**(或 operation_events 表查询失败)。")
        lines.append("")
        return

    total_events = sum(v["total"] for v in events_by_type.values())
    lines.append(
        "**共 {} 条事件,按 event_type 分桶,每类最多 {} 条代表**(总样本上限 {} 条):".format(
            total_events, _EVENT_SAMPLE_PER_TYPE, _EVENT_TOTAL_CAP
        )
    )
    lines.append("")

    for etype, info in events_by_type.items():
        lines.append("### `{}` (共 {} 条,示例 {} 条)".format(
            etype, info["total"], len(info["samples"])))
        lines.append("")
        for ev in info["samples"]:
            # part3.6 修复: 真实字段 event_time / payload_json,不是 created_at / payload
            ts = ev.get("event_time") or "-"
            module = ev.get("module") or "-"
            sev = ev.get("severity") or "-"
            payload_disp = _truncate(
                _flatten_payload(ev.get("payload_json") or ""),
                _PAYLOAD_MAX_CHARS,
            )
            lines.append("- **{}** [{} · {}] {}".format(
                ts, module, sev, payload_disp))
        lines.append("")


def _render_section_instructions(lines):
    lines.append("## 六、诊断使用说明(给 Claude 看)")
    lines.append("")
    lines.append("1. **优先级**:error → warning → info。error 必修,info 是代码质量建议,可按实际工作量选修")
    lines.append("2. **聚合语义**:本报告按 `(dim_code + rule_id + 文件)` 三元组聚合")
    lines.append("   - 某组命中行号多(如 ×47)通常是**模块级模式问题**,建议给整体重构建议而非逐行修")
    lines.append("   - 某组命中行号少(1-3 条)通常是**个别点位**,针对性修")
    lines.append("3. **白名单**:第三段已列出的 signature 已在 `scripts/e2e_tester.py` 白名单内,**不要重复诊断**;"
                 "若第三段显示**\"白名单已失效\"**警告,请对全部 issue 二次判断是否为已知合理项")
    lines.append("4. **状态语义**:")
    lines.append("   - `pending`:待修,本次重点")
    lines.append("   - `intermittent`:7 天内 >5 次触发的偶发问题,值得重视")
    lines.append("   - `fixed`:历史已修,仅供上下文参考")
    lines.append("   - `ignored`:老唐已判定合理,不需重评")
    lines.append("5. **时间语义**:第五段事件日志以报告 `created_at` 为锚点往前 7 天,反映报告那一刻的系统状态")
    lines.append("6. **规则实现源**:")
    lines.append("   - `scripts/static_analyzer.py` (~645 行,dim3/4/6 AST 规则库)")
    lines.append("   - `scripts/e2e_tester.py` (引擎层 + 白名单 + V3 事件语义)")
    lines.append("")


def _render_section_version_context(lines):
    lines.append("## 七、版本上下文")
    lines.append("")
    lines.append("| 模块 | 最新版本 |")
    lines.append("|---|---|")
    lines.append("| api_server.py | v2.3.0-part3.8(+ 6 批量路由 errors 收集改造) |")
    lines.append("| e2e_tester.py | v2.3.0-part3.8(白名单大扩展 DIM4 75/DIM6 79 + WHITELIST_COVERAGE) |")
    lines.append("| db_manager.py | v2.3.0-part3.4(get_polish_candidates 候选池修复) |")
    lines.append("| static_analyzer.py | v2.3.0-part3.7(规则精度三连改) |")
    lines.append("| review.html | v2.3.0-part3.8(6 批量按钮 + batchResultModal) |")
    lines.append("| e2e_diagnosis_exporter.py | v2.3.0-part3.8(按文件维度覆盖范围视图) |")
    lines.append("| extractor.py | v2.3.0-part3.8(冗余迁移 import 清理 -21 行) |")
    lines.append("| duplicate_checker.py | v2.3.0-part3.8(冗余迁移 import 清理 -3 行) |")
    lines.append("")
    lines.append("**近期关键 hotfix**:")
    lines.append("- v2.3.0-part3.8:F062 白名单大扩展(7 文件 DIM6 79 条) + 6 批量路由走 errors 收集 E2 改造 + 冗余代码清理(立规则 52)")
    lines.append("- v2.3.0-part3.7:static_analyzer 规则精度三连改 + 诊断包第三段口径对齐")
    lines.append("- v2.3.0-part3.6:诊断包六维度权重/白名单自检/事件日志 SQL 三 bug 修复")
    lines.append("- v2.3.0-part3.5:E2E 诊断包 Markdown 导出 feature 首版")
    lines.append("- v2.3.0-part3.4:低分打磨候选池允许 confirmed + E2E issue 签名漂移修复")
    lines.append("- v2.3.0-part3.3:审核统计 UI 重写 + 保鲜 loading + E2E 白名单刷新")
    lines.append("")
    lines.append("**立规则**:共 52 条(数据层 10 / 代码层 13 / 交互层 8 / 流程层 21,part3.8 新增 1 条「代码审查兼做冗余清理」),详见 `01_工程手册.md §二`。")
    lines.append("")


# ============================================================
# 工具函数
# ============================================================

def _get_full_report(report):
    """安全取 full_report_json 字段(可能是 dict 或 JSON 字符串)。"""
    fr = report.get("full_report_json") or {}
    if isinstance(fr, str):
        try:
            return json.loads(fr)
        except Exception:
            return {}
    if isinstance(fr, dict):
        return fr
    return {}


def _md_escape(text):
    """Markdown 表格/代码里的 | 和换行处理。"""
    if not isinstance(text, str):
        text = str(text) if text is not None else ""
    return text.replace("|", "\\|").replace("\n", " ").strip()


def _truncate(text, max_chars):
    if not isinstance(text, str):
        text = str(text) if text is not None else ""
    if len(text) <= max_chars:
        return text
    return text[:max_chars] + "...(截断)"


def _truncate_snippet(snippet):
    """snippet 截断:最多 N 行 + 字符数上限。"""
    if not isinstance(snippet, str):
        snippet = str(snippet) if snippet is not None else ""
    line_list = snippet.split("\n")
    if len(line_list) > _SNIPPET_MAX_LINES:
        line_list = line_list[:_SNIPPET_MAX_LINES] + ["# ...(代码行数截断)"]
    result = "\n".join(line_list)
    if len(result) > _SNIPPET_MAX_CHARS:
        result = result[:_SNIPPET_MAX_CHARS] + "\n# ...(字符数截断)"
    return result


def _flatten_payload(payload):
    """把 payload(可能是 JSON 字符串、dict、list) 压成一行展示。"""
    if isinstance(payload, str):
        try:
            d = json.loads(payload)
            return json.dumps(d, ensure_ascii=False, separators=(",", ":"))
        except Exception:
            return payload.replace("\n", " ")
    if isinstance(payload, (dict, list)):
        try:
            return json.dumps(payload, ensure_ascii=False, separators=(",", ":"))
        except Exception:
            return str(payload)
    return str(payload) if payload is not None else ""


def _parse_iso_time(s):
    """兼容多种时间格式,失败返回 now。"""
    if not s:
        return datetime.now()
    s = str(s).strip().replace("T", " ")
    for fmt in ("%Y-%m-%d %H:%M:%S.%f", "%Y-%m-%d %H:%M:%S", "%Y-%m-%d"):
        try:
            return datetime.strptime(s[:len(fmt) + 7], fmt)
        except Exception:
            continue
    try:
        return datetime.strptime(s[:19], "%Y-%m-%d %H:%M:%S")
    except Exception:
        return datetime.now()


def _now_display():
    return datetime.now().strftime("%Y-%m-%d %H:%M:%S")


def _now_stamp():
    return datetime.now().strftime("%Y%m%d_%H%M%S")


# ============================================================
# CLI 自测入口(老唐可跑 python e2e_diagnosis_exporter.py <report_id>)
# ============================================================

if __name__ == "__main__":
    import sys
    import os as _os

    sys.path.insert(0, _os.path.dirname(_os.path.abspath(__file__)))
    from db_manager import DatabaseManager

    if len(sys.argv) < 2:
        print("用法:python e2e_diagnosis_exporter.py <report_id> [输出路径]")
        sys.exit(1)

    rid = int(sys.argv[1])
    out_path = sys.argv[2] if len(sys.argv) > 2 else None

    db = DatabaseManager()
    try:
        md, fn = build_e2e_diagnosis_markdown(db, rid)
    except ValueError as e:
        print("错误:{}".format(e))
        sys.exit(1)

    if out_path:
        with open(out_path, "w", encoding="utf-8") as f:
            f.write(md)
        print("已写入:{}({} 字节)".format(out_path, len(md.encode("utf-8"))))
    else:
        print("建议文件名:{}".format(fn))
        print("-" * 60)
        print(md)
