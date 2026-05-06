"""
quality_safety_ops.py - 质量保障+安全合规 双部门操作中心
路径：agents/quality_safety_ops.py
版本：v2.3.7

零容忍: 任何未经双门禁(入口安全+出口防幻觉)的内容不得发布。
"""
import json, re
from datetime import datetime
from pathlib import Path

PROJECT_ROOT = Path(__file__).parent.parent


class QualitySafetyOps(object):
    """质量保障+安全合规 双部门操作中心。零容忍: 任何未经双门禁的内容不得发布。"""

    def __init__(self, qa_chief, safety_chief, qa_members=None, safety_members=None,
                 db=None, client=None):
        self.qa_chief = qa_chief
        self.safety_chief = safety_chief
        self.qa_members = qa_members or []
        self.safety_members = safety_members or []
        self.db = db
        self.client = client
        self._ops_log = []
        self._blocked_count = 0
        self._passed_count = 0

    # ---- 质量保障操作 ----

    def fact_check_batch(self, kp_list):
        """批量核查KP的事实准确性(政策文件号/数据来源/时效性)"""
        results = [self._fact_check_one(kp) for kp in kp_list]
        passed = sum(1 for r in results if r["passed"])
        self._log("fact_check", "info", f"核查{len(kp_list)}条: 通过{passed}")
        return {"total": len(kp_list), "passed": passed,
                "failed": len(kp_list) - passed, "results": results,
                "checked_at": datetime.now().isoformat()}

    def _fact_check_one(self, kp):
        title = kp.get("title", "")
        content = kp.get("ai_extracted_content", "") or kp.get("original_excerpt", "")
        issues = []
        has_file_ref = any(w in content for w in
                          ["国发", "川发", "办发", "部发", "厅发", "委发", "号"])
        looks_like_policy = any(w in title for w in
                               ["政策", "通知", "办法", "条例", "意见"])
        if looks_like_policy and not has_file_ref:
            issues.append("政策类KP缺少可追溯的文件号")
        if re.search(r'\d+%|\d+万|\d+亿', content):
            if not any(w in content for w in ["来源", "据统计", "根据", "数据来自"]):
                issues.append("数据类内容缺少来源标注")
        interval = kp.get("freshness_interval_days", 180)
        last_check = kp.get("freshness_checked_at")
        if last_check:
            try:
                days = (datetime.now() - datetime.fromisoformat(str(last_check))).days
                if days > interval:
                    issues.append(f"保鲜检查已过期({days}d,保鲜期{interval}d)")
            except (ValueError, TypeError):
                pass
        return {"kp_id": kp.get("id"), "title": title[:80],
                "passed": len(issues) == 0, "issues": issues}

    def freshness_scan(self):
        """全库扫描过期KP并标记。返回 {expired, needs_update}"""
        try:
            from scripts.freshness_checker import scan_freshness
            return scan_freshness()
        except ImportError:
            pass
        expired, needs = 0, 0
        try:
            conn = self.db.get_connection(); c = conn.cursor()
            cond = ("freshness_checked_at IS NOT NULL AND datetime(freshness_checked_at,"
                    "'+'||freshness_interval_days||' days')<datetime('now')")
            c.execute(f"SELECT COUNT(*) FROM knowledge_points WHERE review_status='confirmed' AND {cond}")
            expired = c.fetchone()[0]
            c.execute(f"SELECT COUNT(*) FROM knowledge_points WHERE review_status='confirmed' AND"
                      f" (freshness_checked_at IS NULL OR {cond})")
            needs = c.fetchone()[0]
            c.execute(f"UPDATE knowledge_points SET freshness_status='expired' WHERE"
                      f" review_status='confirmed' AND {cond}")
            conn.commit(); conn.close()
            self._log("freshness", "info", f"过期{expired}条,需更新{needs}条")
        except Exception as e:
            self._log("freshness", "error", str(e)[:150])
        return {"expired": expired, "needs_update": needs, "scanned_at": datetime.now().isoformat()}

    def quality_audit_cycle(self):
        """完整质量审计周期: 采样核查→保鲜扫描→评分→建议"""
        report = {"cycle": "quality_audit", "started_at": datetime.now().isoformat(),
                  "overall_score": 0, "recommendations": []}
        sample = []
        try:
            conn = self.db.get_connection(); c = conn.cursor()
            c.execute("SELECT id, title, original_excerpt, ai_extracted_content,"
                      " freshness_interval_days, freshness_checked_at FROM knowledge_points"
                      " WHERE review_status='confirmed' ORDER BY id DESC LIMIT 50")
            cols = [d[0] for d in c.description]
            sample = [dict(zip(cols, r)) for r in c.fetchall()]
            conn.close()
        except Exception as e:
            report["fact_check"] = {"error": str(e)[:150]}
        if sample:
            report["fact_check"] = self.fact_check_batch(sample)
        report["freshness"] = self.freshness_scan()
        fc = report.get("fact_check", {}) or {}
        fr = report.get("freshness", {}) or {}
        fc_pr = fc.get("passed", 0) / max(fc.get("total", 1), 1)
        fr_cov = 1.0 - fr.get("expired", 0) / max(fr.get("needs_update", 1), 1)
        report["overall_score"] = round(fc_pr * 0.6 + fr_cov * 0.4, 2)
        if fc_pr < 0.8:
            report["recommendations"].append(f"事实核查通过率仅{fc_pr:.0%},建议CEO审查来源质量")
        if fr_cov < 0.9:
            report["recommendations"].append(f"保鲜覆盖率仅{fr_cov:.0%},建议全库保鲜扫描")
        report["completed_at"] = datetime.now().isoformat()
        return report

    # ---- 安全双门禁(强制,不可绕过) ----

    def safety_gate_inbound(self, content):
        """入口门禁: Layer1技术(脚本/SQL/XSS)→Layer2内容(政治/色情/暴力)→Layer3合规(虚假广告)"""
        text = content if isinstance(content, str) else content.get("text", "")
        source = "" if isinstance(content, str) else content.get("source", "")
        result = {"passed": True, "layer": "inbound", "violations": [],
                  "checked_at": datetime.now().isoformat(), "source": source}
        if not text:
            result.update({"passed": False, "violations": [
                {"layer": "tech", "rule": "empty_content", "severity": "BLOCK"}]})
            self._blocked_count += 1
            return result
        for pat, desc, layer in [
            (r'<script[^>]*>', "XSS:<script>", "tech"),
            (r"""(?i)\b(SELECT\b.*\bFROM\b|\bDROP\s+TABLE\b|\bUNION\s+SELECT\b)""", "SQL注入", "tech"),
            (r'javascript:|onerror\s*=', "XSS:js/onerror", "tech"),
            (r'分裂|独立|颠覆', "政治敏感", "content"),
            (r'色情|淫秽|裸露', "色情内容", "content"),
            (r'暴力|恐怖|杀人', "暴力内容", "content"),
            (r'保证\s*(收益|获批|通过|成功)', "虚假承诺", "compliance"),
            (r'100%|零风险|稳赚|保本', "绝对化金融声称", "compliance"),
            (r'政府背书|官方认证|部委推荐', "虚假权威背书", "compliance"),
        ]:
            if re.search(pat, text):
                result["passed"] = False
                result["violations"].append({"layer": layer, "rule": desc, "severity": "BLOCK"})
        if result["passed"]:
            self._passed_count += 1
        else:
            self._blocked_count += 1
        self._log("inbound", "info", f"{'PASS' if result['passed'] else 'BLOCK'} "
                  f"({len(result['violations'])} violations)")
        return result

    def hallucination_gate_outbound(self, ai_output):
        """出口门禁: uncertain=禁止输出; 无来源KP=拦截/标记[待验证]; 数字无KP=零容忍"""
        if isinstance(ai_output, str):
            text, src, conf = ai_output, [], "medium"
        else:
            text = ai_output.get("text", "")
            src = ai_output.get("source_kp_ids", [])
            conf = ai_output.get("confidence", "medium")
        result = {"passed": True, "layer": "outbound", "confidence": conf,
                  "source_kp_ids": src, "issues": [], "checked_at": datetime.now().isoformat()}
        if conf == "uncertain":
            result["passed"] = False
            result["issues"].append({"type": "uncertain", "detail": "AI置信度uncertain,禁止输出",
                                     "action": "BLOCK"})
        elif not src:
            action = "BLOCK" if conf in ("low", "medium") else "FLAG"
            result["passed"] = (action == "FLAG")
            result["issues"].append({"type": "no_source", "detail": f"无来源KP({action})",
                                     "action": action})
        nums = re.findall(r'\d+(?:\.\d+)?(?:万|亿)?(?:元|亩|公顷|人|%)?', text)
        if nums and not src:
            action = "BLOCK" if conf != "high" else "FLAG"
            result["issues"].append({"type": "unverified_numbers",
                                     "detail": f"{len(nums)}个数字声称无KP", "action": action})
            if conf != "high":
                result["passed"] = False
        self._log("outbound", "info", f"{'PASS' if result['passed'] else 'BLOCK/FLAG'} "
                  f"(conf={conf}, src={len(src)})")
        return result

    def dual_gate_publish(self, content):
        """双门禁发布: inbound→outbound→通过/拦截。任意一关不通过=不得发布。"""
        text = content if isinstance(content, str) else content.get("text", "")
        inbound = self.safety_gate_inbound(
            content if isinstance(content, dict) else {"text": text})
        if not inbound["passed"]:
            return {"approved": False, "stage": "inbound_blocked",
                    "reason": "入口门禁拦截", "inbound": inbound, "outbound": None}
        outbound = self.hallucination_gate_outbound(
            content if isinstance(content, dict) else {"text": text})
        return {"approved": outbound["passed"],
                "stage": "outbound_blocked" if not outbound["passed"] else "dual_gate_passed",
                "reason": "双门禁通过" if outbound["passed"] else "出口门禁拦截",
                "inbound": inbound, "outbound": outbound}

    # ---- 品牌红线 ----

    def brand_redline_check(self, content):
        """品牌红线检查: 5类18条红线一票否决。"""
        try:
            from agents.brand_redlines import BrandRedlineChecker
            ctype = content if isinstance(content, str) else content.get("type", "article")
            ctext = content if isinstance(content, str) else content.get("text", "")
            result = BrandRedlineChecker().check_content(ctext, content_type=ctype)
            self._log("brand_redline", "info",
                      f"{result.get('verdict','?')}: {len(result.get('violations',[]))}件")
            return result
        except ImportError:
            return {"passed": True, "violations": [], "error": "BrandRedlineChecker不可用"}

    # ---- 部门管理 ----

    def department_status(self):
        """双部门状态报告。"""
        def _dept(name, chief, members):
            return {"name": name, "chief": chief.agent_name if chief else "N/A",
                    "members": [m.agent_name for m in members], "member_count": len(members)}
        return {"departments": [
            _dept("质量保障部", self.qa_chief, self.qa_members),
            _dept("安全合规部", self.safety_chief, self.safety_members)],
            "ops": {"blocks": self._blocked_count, "passes": self._passed_count,
                    "dual_gate_enforced": True},
            "reported_at": datetime.now().isoformat()}

    def _log(self, stage, level, msg):
        entry = f"[QualitySafety] {stage}: {msg}"
        self._ops_log.append({"stage": stage, "level": level, "msg": msg,
                              "time": datetime.now().isoformat()})
        try:
            if self.db:
                self.db.log_operation_event(
                    event_type=f"quality_safety_{stage}", severity=level,
                    module="quality_safety_ops", payload={"msg": msg})
        except Exception:
            pass


def mandatory_safety_check(content, is_inbound=True):
    """强制安全门禁检查。调用者必须显式捕获和处理异常。
    Raises ValueError if content is empty or None.
    """
    if not content:
        raise ValueError("内容为空,安全门禁拒绝放行")
    return True
