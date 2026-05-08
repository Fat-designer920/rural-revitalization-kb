"""
global_task_registry.py - 全局任务注册表(CEO系统性思考基础设施)
路径：agents/global_task_registry.py
版本：v2.3.7-part5

解决CEO缺乏系统性、全局性、主动性思考的问题。
每项任务: 注册→执行→验证→纠偏→闭环。不盲跑。
"""
import json, time
from datetime import datetime


class GlobalTaskRegistry(object):
    """全局任务注册表。CEO的系统性思考基础设施——所有任务在此注册、追踪、验证、闭环。"""

    PRIORITY_ORDER = {"P0": 0, "P1": 1, "P2": 2, "P3": 3}
    STATUS_FLOW = ["pending", "running", "completed", "validated", "failed", "corrected"]

    def __init__(self):
        self._tasks = {}       # {task_id: task_dict}
        self._history = []     # 已完成任务历史
        self._counter = 0

    def register(self, name, priority, department, action, validator=None, depends_on=None):
        """注册新任务。每个任务必须有验证器和依赖声明。
        validator: 函数,接收result返回(ok, reason)
        depends_on: [task_ids], 前置依赖任务
        """
        self._counter += 1
        tid = f"T{self._counter:04d}"
        task = {
            "id": tid, "name": name, "priority": priority,
            "department": department, "action": action,
            "status": "pending", "validator": validator,
            "depends_on": depends_on or [],
            "created_at": datetime.now().isoformat(),
            "started_at": None, "completed_at": None,
            "result": None, "validation": None,
            "retries": 0, "max_retries": 3,
        }
        # 检查依赖: 如果依赖的任务都已完成,可以直接启动
        if depends_on:
            all_deps_done = all(
                self._tasks.get(d, {}).get("status") in ("validated", "completed")
                for d in depends_on if d in self._tasks)
            if not all_deps_done:
                task["status"] = "blocked"
        self._tasks[tid] = task
        return tid

    def get_ready_tasks(self):
        """获取所有就绪任务(无依赖或依赖已满足)"""
        ready = []
        for tid, t in self._tasks.items():
            if t["status"] in ("pending",):
                blocked = False
                for dep in t.get("depends_on", []):
                    if dep in self._tasks:
                        dep_status = self._tasks[dep]["status"]
                        if dep_status not in ("validated", "completed"):
                            blocked = True
                            break
                if not blocked:
                    ready.append(t)
        # 按优先级排序
        ready.sort(key=lambda t: self.PRIORITY_ORDER.get(t["priority"], 99))
        return ready

    def mark_running(self, task_id):
        if task_id in self._tasks:
            self._tasks[task_id]["status"] = "running"
            self._tasks[task_id]["started_at"] = datetime.now().isoformat()

    def mark_completed(self, task_id, result):
        if task_id in self._tasks:
            self._tasks[task_id]["status"] = "completed"
            self._tasks[task_id]["completed_at"] = datetime.now().isoformat()
            self._tasks[task_id]["result"] = result

    def validate(self, task_id, validator_func=None):
        """验证任务结果。每个任务必须有验证步骤。"""
        if task_id not in self._tasks:
            return False, "task not found"
        task = self._tasks[task_id]
        if task["status"] not in ("completed",):
            return False, f"task status is {task['status']}, not completed"

        vf = validator_func or task.get("validator")
        if vf is None:
            # 默认验证: 结果非空且无error
            result = task.get("result", {})
            if isinstance(result, dict):
                ok = result.get("success", True) and not result.get("error")
                return ok, "default check: " + ("OK" if ok else "has error")
            return True, "no validator, assuming OK"

        try:
            ok, reason = vf(task.get("result"))
            task["validation"] = {"ok": ok, "reason": reason, "time": datetime.now().isoformat()}
            task["status"] = "validated" if ok else "failed"
            if not ok and task["retries"] < task["max_retries"]:
                task["status"] = "pending"  # 回退到pending,等待重试
                task["retries"] += 1
            return ok, reason
        except Exception as e:
            task["validation"] = {"ok": False, "reason": str(e)[:200]}
            task["status"] = "failed"
            return False, str(e)[:200]

    def correct(self, task_id, correction_action):
        """纠偏: 任务失败后采取纠正措施"""
        if task_id in self._tasks:
            self._tasks[task_id]["status"] = "corrected"
            self._tasks[task_id]["correction"] = correction_action
            self._history.append(self._tasks.pop(task_id))
            # 重新注册修正后的任务
            old = self._history[-1]
            return self.register(
                f"{old['name']}(纠偏)", old["priority"],
                old["department"], correction_action,
                validator=old.get("validator"),
            )

    def get_global_view(self):
        """全局视图: CEO系统性决策的基础"""
        by_status = {}
        for t in self._tasks.values():
            s = t["status"]
            by_status.setdefault(s, []).append(t["name"])

        by_dept = {}
        for t in self._tasks.values():
            by_dept.setdefault(t["department"], []).append(f"[{t['priority']}] {t['name']}")

        by_priority = {"P0": [], "P1": [], "P2": [], "P3": []}
        for t in self._tasks.values():
            by_priority.setdefault(t["priority"], []).append(t["name"])

        return {
            "total": len(self._tasks),
            "by_status": {k: len(v) for k, v in by_status.items()},
            "by_department": {k: len(v) for k, v in by_dept.items()},
            "by_priority": {k: len(v) for k, v in by_priority.items()},
            "ready_to_run": len(self.get_ready_tasks()),
            "pending_validation": len([t for t in self._tasks.values() if t["status"] == "completed"]),
            "failed_need_correction": len([t for t in self._tasks.values() if t["status"] == "failed"]),
            "blocked_by_dependency": len([t for t in self._tasks.values() if t["status"] == "blocked"]),
        }

    def get_missing_domains(self):
        """CEO主动性: 检测哪些领域没有活跃任务"""
        all_domains = {
            "content_production": "内容生产",
            "crawler": "爬虫采集",
            "ui_overhaul": "UI改造",
            "deep_learning": "深度学习升级",
            "quality_audit": "质量审计",
            "safety_scan": "安全扫描",
            "agent_evolution": "Agent进化",
            "relation_network": "关系网络",
            "premium_judge": "精品判定",
            "code_review": "代码审查",
            "npu_optimization": "NPU优化",
            "qa_improvement": "QA改进",
            "revenue_analysis": "变现分析",
            "skill_integration": "Skill整合",
            "freshness_scan": "保鲜扫描",
            "memory_monitor": "内存监控",
            "git_sync": "Git同步",
        }
        active_domains = set()
        for t in self._tasks.values():
            active_domains.add(t.get("department", ""))
        missing = {k: v for k, v in all_domains.items() if k not in active_domains}
        return missing


# 全局单例
_registry = None


def get_registry():
    global _registry
    if _registry is None:
        _registry = GlobalTaskRegistry()
    return _registry


def reset_registry():
    global _registry
    _registry = GlobalTaskRegistry()
    return _registry
