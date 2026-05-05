"""
iteration_auditor.py - 迭代审计Agent(检查每次升级是否全系统同步,不留欠账)
路径：agents/iteration_auditor.py
版本：v2.3.7-part2

每次升级后,本Agent扫描全项目,检查:
1. CLAUDE.md的版本号/架构描述是否与代码实际状态一致
2. README.md/CHANGELOG/docs/00-03是否同步更新
3. 代码中的model ID/版本号/描述文案是否与当前版本一致
4. 是否有"TODO"/"FIXME"/"挂账"标记未处理
5. 被修改模块的关联文件是否同步修改过时引用
"""
import sys, os, re, json
from pathlib import Path
from datetime import datetime

PROJECT_ROOT = Path(__file__).parent.parent
sys.path.insert(0, str(PROJECT_ROOT / "agents"))

from base_agent import BaseAgent


class IterationAuditor(BaseAgent):
    """迭代审计Agent。每次升级后自动运行,确保全系统同步,不留技术债务。"""

    def __init__(self, client=None, db=None):
        super().__init__(
            agent_code="iteration_auditor",
            agent_name="迭代审计官",
            agent_type="quality",
            identity_text=(
                "我是迭代审计官。我的职责是确保每次系统升级都是'全系统升级'——"
                "不留下任何一个过时的版本号、任何一处未同步的文档、任何一条'以后再说'的欠账。"
                "我的信念: 每一次'以后再说'都会变成'永远不做'。"
            ),
            core_questions=[
                "CLAUDE.md描述的能力,代码是否都实现了?",
                "README.md的版本号和模型描述是否与代码一致?",
                "所有关联文件是否都同步更新了?",
            ],
            quality_standards=[
                "零过时引用 — 不能出现'以后再说'的标记",
                "全文件版本一致 — CLAUDE/README/CHANGELOG/docs 版本号必须统一",
                "代码=文档 — CLAUDE.md描述的架构必须与代码实际一致",
            ],
            client=client, db=db, model="deepseek-v4-flash",
        )

    # ================================================================
    # 全量审计
    # ================================================================
    def audit_all(self):
        """扫描全项目,生成审计报告。返回 {score, issues, fixed, recommendations}"""
        report = {
            "audit_time": datetime.now().isoformat(),
            "project_root": str(PROJECT_ROOT),
            "checks": {},
            "issues": [],
            "total_score": 100,
        }

        # Check 1: 版本号一致性
        report["checks"]["version_consistency"] = self._check_versions()

        # Check 2: 过时引用扫描
        report["checks"]["outdated_refs"] = self._scan_outdated_refs()

        # Check 3: TODO/FIXME/挂账扫描
        report["checks"]["debt_markers"] = self._scan_debt_markers()

        # Check 4: Agent真实性审计
        report["checks"]["agent_authenticity"] = self._check_agents()

        # Check 5: 文档-代码一致性
        report["checks"]["doc_code_consistency"] = self._check_doc_code_gap()

        # 汇总
        for check_name, check_result in report["checks"].items():
            issues = check_result.get("issues", [])
            report["issues"].extend(issues)
            deductions = len(issues) * 2
            report["total_score"] = max(0, report["total_score"] - deductions)

        # AI深度分析
        if self.client:
            verdict = self._ai_analyze(report)
            report["ai_analysis"] = verdict

        return report

    # ================================================================
    # 检查项
    # ================================================================
    def _check_versions(self):
        """检查所有文件的版本号是否一致。"""
        issues = []
        version_pattern = re.compile(r'v2\.\d+\.\d+[-\w]*')

        # 从CHANGELOG获取最新版本号
        changelog = PROJECT_ROOT / "CHANGELOG.md"
        latest_version = None
        if changelog.exists():
            text = changelog.read_text(encoding="utf-8")
            versions = version_pattern.findall(text)
            if versions:
                latest_version = versions[0]  # CHANGELOG最新版本在顶部

        if not latest_version:
            issues.append({"severity": "error", "file": "CHANGELOG.md",
                          "issue": "无法确定最新版本号"})
            return {"issues": issues, "latest_version": None}

        # 检查各文件
        files_to_check = {
            "README.md": PROJECT_ROOT / "README.md",
            "CLAUDE.md": PROJECT_ROOT / "CLAUDE.md",
            "scripts/config_wizard.py": PROJECT_ROOT / "scripts" / "config_wizard.py",
            "scripts/extractor.py": PROJECT_ROOT / "scripts" / "extractor.py",
        }
        for fname, fpath in files_to_check.items():
            if not fpath.exists():
                continue
            text = fpath.read_text(encoding="utf-8")
            f_versions = set(version_pattern.findall(text))
            if latest_version not in f_versions and f_versions:
                issues.append({
                    "severity": "warning",
                    "file": fname,
                    "issue": f"版本号可能过时: 找到{f_versions}, CHANGELOG最新={latest_version}",
                })

        return {"issues": issues, "latest_version": latest_version}

    def _scan_outdated_refs(self):
        """扫描代码中的过时引用。"""
        issues = []
        outdated_patterns = [
            (r'R1/V3\s*双模型', '应改为 V4-Pro/V4-Flash 双模型'),
            (r'deepseek-reasoner', 'R1已退役, 应使用deepseek-v4-pro(legacy除外)'),
            (r'R1\s*提取', '应改为 V4-Pro 提取(历史文档除外)'),
        ]
        # Only check non-CHANGELOG files
        for py_file in PROJECT_ROOT.rglob("*.py"):
            if 'migrate' in str(py_file) or '__pycache__' in str(py_file):
                continue
            try:
                text = py_file.read_text(encoding="utf-8")
                for pattern, suggestion in outdated_patterns:
                    matches = re.findall(pattern, text)
                    if matches:
                        rel_path = py_file.relative_to(PROJECT_ROOT)
                        issues.append({
                            "severity": "info",
                            "file": str(rel_path),
                            "issue": f"发现过时引用'{matches[0][:60]}': {suggestion}",
                        })
            except Exception:
                pass
        return {"issues": issues[:20]}

    def _scan_debt_markers(self):
        """扫描技术债务标记。"""
        issues = []
        debt_patterns = [
            (r'TODO|FIXME|HACK|XXX', '技术债务标记'),
            (r'挂账|暂缓|待定|以后再说|下版|远期|待修复', '未解决的挂账事项'),
            (r'# v2\.\d+\.\d+ (?:修复|新增|变更)', '代码内版本注释(应归CHANGELOG)'),
        ]
        for py_file in PROJECT_ROOT.glob("**/*.py"):
            if 'migrate' in str(py_file) or '__pycache__' in str(py_file):
                continue
            try:
                text = py_file.read_text(encoding="utf-8")
                for pattern, desc in debt_patterns:
                    for match in re.finditer(pattern, text):
                        line_no = text[:match.start()].count('\n') + 1
                        issues.append({
                            "severity": "info",
                            "file": str(py_file.relative_to(PROJECT_ROOT)),
                            "line": line_no,
                            "issue": f"{desc}: {match.group()[:80]}",
                        })
            except Exception:
                pass
        return {"issues": issues[:30]}

    def _check_agents(self):
        """检查Agent是否符合BaseAgent标准。"""
        issues = []
        agents_dir = PROJECT_ROOT / "agents"
        for py_file in agents_dir.glob("*.py"):
            if py_file.name.startswith("__"):
                continue
            try:
                text = py_file.read_text(encoding="utf-8")
                has_baseagent = "BaseAgent" in text and "class" in text
                has_think = "def think" in text
                has_identity = "identity_text" in text
                if has_baseagent and not has_think:
                    issues.append({
                        "severity": "warning",
                        "file": f"agents/{py_file.name}",
                        "issue": "继承BaseAgent但缺少think方法",
                    })
                if not has_baseagent and "class" in text and "Agent" in py_file.name:
                    has_init = "def __init__" in text
                    if has_init:
                        # It's a class but not a BaseAgent
                        pass  # Some are tools (auto_feeder, crawler), not agents
            except Exception:
                pass
        return {"issues": issues[:15]}

    def _check_doc_code_gap(self):
        """检查CLAUDE.md描述的架构与代码实际状态之间的差距。"""
        issues = []
        claude_md = PROJECT_ROOT / "CLAUDE.md"
        if not claude_md.exists():
            return {"issues": [{"severity": "error", "issue": "CLAUDE.md不存在!"}]}

        claude_text = claude_md.read_text(encoding="utf-8")

        # CLAUDE.md声称有25个Agent? 实际检查
        if "25个AI" in claude_text or "25个AI Agent" in claude_text:
            agents_dir = PROJECT_ROOT / "agents"
            agent_files = [f for f in agents_dir.glob("*.py") if not f.name.startswith("__")]
            # Count actual BaseAgent subclasses
            agent_count = 0
            for f in agent_files:
                text = f.read_text(encoding="utf-8")
                if "BaseAgent" in text and "class" in text:
                    agent_count += 1
            if agent_count < 10:
                issues.append({
                    "severity": "error",
                    "issue": f"CLAUDE.md声称25个Agent, 实际仅{agent_count}个继承BaseAgent",
                })

        # 检查"7部门"描述是否准确
        if "7部门" in claude_text or "6部门" in claude_text:
            dept_count = claude_text.count("部门")
            if dept_count < 3:
                issues.append({"severity": "warning",
                              "issue": "CLAUDE.md部门描述可能过时"})

        return {"issues": issues}

    def _ai_analyze(self, report):
        """用AI深度分析审计结果。"""
        context = {
            "audit_summary": {
                "total_issues": len(report["issues"]),
                "score": report["total_score"],
                "top_issues": report["issues"][:5],
            },
            "instruction": (
                "作为迭代审计官,分析这些审计发现。给出:\n"
                "1. 最严重的3个问题(按影响排序)\n"
                "2. 修复建议(具体到文件)\n"
                "3. 哪些是'现在必须修'vs'可以宽容'\n"
                "返回JSON: {top_3_issues, fix_suggestions, now_vs_later}"
            ),
        }
        result = self.think(context, deep=False)
        return result

    # ================================================================
    # 快速审计(模块级入口)
    # ================================================================
    def quick_audit(self):
        """快速审计(不含AI分析)。"""
        report = self.audit_all()
        report.pop("ai_analysis", None)
        return report

    def to_dict(self):
        return {
            "agent_code": self.agent_code,
            "agent_name": self.agent_name,
            "agent_type": self.agent_type,
            "identity_text": self.identity_text,
        }


def run_audit(client=None, db=None, deep=False):
    """模块级便捷入口。"""
    auditor = IterationAuditor(client=client, db=db)
    return auditor.audit_all() if deep else auditor.quick_audit()
