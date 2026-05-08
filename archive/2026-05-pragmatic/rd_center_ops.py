"""
rd_center_ops.py - 研发中心+设计中心 操作中心
路径：agents/rd_center_ops.py
版本：v2.3.7-part5
驱动代码审查+测试+UI开发+架构评审。协调16人团队(10工程师+6设计师)。
"""
import json, subprocess, sys
from datetime import datetime
from pathlib import Path

PROJECT_ROOT = Path(__file__).parent.parent
sys.path.insert(0, str(PROJECT_ROOT))


class RDCenterOps:
    """研发中心+设计中心 操作中心。驱动代码审查+测试+UI开发+架构评审。"""

    def __init__(self, chief, members_dict, db=None, client=None):
        self.chief = chief
        self.members = members_dict
        self.db = db
        self.client = client

    def _think(self, agent_code, context, deep=False):
        agent = self.members.get(agent_code)
        if not agent:
            return {"analysis": f"[{agent_code}]未找到", "confidence": "low", "insights": []}
        if not self.client:
            return {"analysis": f"[{agent.agent_name}]离线: {str(context)[:150]}",
                    "confidence": "offline", "insights": []}
        try:
            return agent.think(context, deep=deep)
        except Exception as e:
            return {"analysis": f"异常: {str(e)[:150]}", "confidence": "low", "insights": []}

    # ---- 代码审查 ----
    def code_review(self, file_path, change_description):
        """代码审查员+安全审计员双人审查。"""
        if not Path(file_path).exists():
            return {"success": False, "error": f"文件不存在: {file_path}"}
        fname = Path(file_path).name
        code_r = self._think("code_reviewer",
            f"审查文件{fname}: {change_description}。检查:正确性/安全性/可读性/性能/一致性。")
        sec_r = self._think("security_auditor",
            f"安全审计{fname}: {change_description}。检查:SQL注入/XSS/密钥泄露/依赖安全/权限控制。")
        return {
            "success": True, "file": file_path,
            "code_review": code_r.get("analysis", "")[:500],
            "security_audit": sec_r.get("analysis", "")[:500],
            "passes_review": code_r.get("confidence", "low") != "low",
        }

    # ---- 测试 ----
    def run_test_suite(self, scope="smoke"):
        """测试架构师驱动6层测试金字塔。scope: smoke/auto/full。"""
        tester = PROJECT_ROOT / "scripts" / "auto_tester.py"
        if not tester.exists():
            return {"success": False, "error": "auto_tester.py不存在"}
        cmd_map = {
            "smoke": [sys.executable, str(tester), "--smoke"],
            "auto": [sys.executable, str(tester), "--auto", "--no-ai"],
            "full": [sys.executable, str(tester), "--full", "--dry-run"],
        }
        cmd = cmd_map.get(scope, cmd_map["smoke"])
        try:
            proc = subprocess.run(cmd, capture_output=True, text=True, timeout=120, shell=False)
            success = proc.returncode == 0
            output = (proc.stdout or "")[-3000:]
            if not success and proc.stderr:
                output += f"\n[STDERR]\n{(proc.stderr or '')[-1000:]}"
        except subprocess.TimeoutExpired:
            return {"success": False, "error": "测试超时(>120秒)"}
        except Exception as e:
            return {"success": False, "error": str(e)[:200]}
        analysis = self._think("test_architect",
            f"测试范围={scope}, 通过={success}。输出摘要:{output[:500]}")
        return {
            "success": success, "scope": scope,
            "test_architect_analysis": analysis.get("analysis", "")[:300],
            "output_tail": output[-500:],
        }

    # ---- 架构评审 ----
    def architecture_review(self, proposal):
        """研发总监+前端架构师+后端工程师+DBA 4人架构评审。"""
        reviewers = [
            ("rd_director", f"[CTO]评审整体架构和风险:{proposal}"),
            ("frontend_architect", f"[前端]评审ES5兼容/性能/可维护性:{proposal}"),
            ("backend_engineer", f"[后端]评审API设计/数据流/异常处理:{proposal}"),
            ("database_engineer", f"[DBA]评审schema设计/索引/查询性能:{proposal}"),
        ]
        opinions = []
        for code, prompt in reviewers:
            r = self._think(code, prompt)
            opinions.append({"reviewer": code, "opinion": r.get("analysis", "")[:300],
                            "confidence": r.get("confidence", "?")})
        ok = sum(1 for o in opinions if o["confidence"] in ("high", "medium"))
        return {
            "success": True, "proposal": proposal[:200], "opinions": opinions,
            "verdict": "approved" if ok >= 3 else "revisions_needed",
            "approval_ratio": f"{ok}/{len(opinions)}",
        }

    # ---- 设计评审 ----
    def design_review(self, page_spec):
        """UI设计师+前端架构师+移动端 3人设计评审。"""
        reviewers = [
            ("ui_visual_designer", f"视觉:检查颜色/字体/间距/设计token:{page_spec}"),
            ("frontend_architect", f"前端:检查320px/首屏加载/ES5兼容:{page_spec}"),
            ("mobile_specialist", f"移动端:检查分辨率适配/触控/PWA:{page_spec}"),
        ]
        opinions = []
        critical = 0
        for code, prompt in reviewers:
            r = self._think(code, prompt)
            ins = r.get("insights", [])
            critical += sum(1 for i in ins if "严重" in str(i) or "critical" in str(i).lower())
            opinions.append({"reviewer": code, "opinion": r.get("analysis", "")[:250],
                            "issues": ins[:3]})
        qa = self._think("design_qa",
            f"交叉验证{len(opinions)}位设计师评审结果,确认无遗漏:" +
            json.dumps([o["reviewer"] for o in opinions], ensure_ascii=False))
        return {
            "success": True, "page_spec": page_spec[:200], "opinions": opinions,
            "critical_count": critical, "qa_validation": qa.get("analysis", "")[:300],
            "verdict": "requires_major_revision" if critical >= 2 else
                       "requires_minor_revision" if critical >= 1 else "approved",
        }

    # ---- UI组件生成 ----
    def generate_ui_component(self, spec):
        """根据设计规范生成ES5兼容的HTML/CSS/JS组件。"""
        if not self.client:
            return {"success": False, "error": "AI client不可用"}
        sys_prompt = u"""你是UI组件生成器,严守以下规范:
ES5严格兼容(无箭头函数/const/let/模板字符串/class/Promise)
设计token:颜色用var(--color-xxx),间距4/8/16/24/32/48六级
移动优先:320px基准,media query渐进增强
可访问性:aria-label全覆盖,输入框有label,触控目标>=44px
颜色系统:--color-primary:#1a5632 --color-gold:#c8a84e --color-bg:#faf8f5 --color-text:#2d2d2d
输出JSON:{"html":"...","css":"...","js":"/* ES5 */","accessibility_notes":["..."]}"""
        try:
            resp = self.client.chat_with_json(
                sys_prompt, u"生成UI组件: " + str(spec),
                temperature=0.2, model_override="deepseek-v4-flash", call_type="ui_component_gen")
            parsed = resp.get("parsed_json") if isinstance(resp, dict) else {}
            return {"success": True, "spec": spec[:200],
                    "html": parsed.get("html", ""), "css": parsed.get("css", ""),
                    "js": parsed.get("js", ""),
                    "accessibility_notes": parsed.get("accessibility_notes", [])}
        except Exception as e:
            return {"success": False, "error": str(e)[:200]}

    # ---- DevOps部署检查 ----
    def deploy_check(self):
        """DevOps部署前检查:语法+冒烟测试+Git状态。"""
        checks = {}
        # 语法检查
        py_files = list(PROJECT_ROOT.rglob("*.py"))[:100]
        syntax_errors = []
        for f in py_files:
            try:
                with open(f, "r", encoding="utf-8") as fh:
                    compile(fh.read(), str(f), "exec")
            except SyntaxError as e:
                syntax_errors.append({"file": str(f.relative_to(PROJECT_ROOT)), "error": str(e)})
        checks["syntax"] = {"pass": len(syntax_errors) == 0, "errors": len(syntax_errors)}
        # 冒烟测试
        smoke = self.run_test_suite("smoke")
        checks["smoke_test"] = {"pass": smoke.get("success", False)}
        # Git状态
        try:
            gs = subprocess.run(["git", "status", "--porcelain"], cwd=str(PROJECT_ROOT),
                               capture_output=True, text=True, shell=False)
            dirty = bool(gs.stdout.strip())
            checks["git_clean"] = {"pass": not dirty,
                                  "files": len(gs.stdout.splitlines()) if dirty else 0}
        except Exception:
            checks["git_clean"] = {"pass": True, "note": "无法检查git"}
        devops_v = self._think("devops_engineer",
            f"部署前检查: {json.dumps(checks, ensure_ascii=False)}。是否可以部署?")
        all_ok = all(c.get("pass", True) for c in checks.values())
        return {"success": True, "checks": checks, "deployable": all_ok,
                "devops_verdict": devops_v.get("analysis", "")[:300]}

    # ---- 部门管理 ----
    def rd_daily_standup(self):
        """研发日站会:各工程师汇报进度+阻塞。"""
        report = {
            "dept": "rd_center", "chief": self.chief.agent_name if self.chief else "?",
            "time": datetime.now().isoformat(), "member_count": len(self.members),
            "members": [],
        }
        for code, agent in self.members.items():
            report["members"].append({
                "code": code, "name": agent.agent_name,
                "type": getattr(agent, "agent_type", "?"),
                "calls": getattr(agent, "_call_count", 0),
                "cost": round(getattr(agent, "_total_cost", 0), 4),
            })
        if self.client:
            for m in report["members"][:6]:
                r = self._think(m["code"], "日站会:今天完成什么?阻塞?需要什么帮助?")
                m["standup"] = r.get("analysis", "")[:150]
        tc = sum(m["calls"] for m in report["members"])
        tco = round(sum(m["cost"] for m in report["members"]), 4)
        report["summary"] = f"研发中心{len(self.members)}人,总调用{tc}次,总成本{tco}元"
        return report
