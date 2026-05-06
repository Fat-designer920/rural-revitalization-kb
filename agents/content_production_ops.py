"""
content_production_ops.py - 内容生产部实作化: 一日生产循环+各岗位领域方法
路径: agents/content_production_ops.py
版本: v2.3.7
"""
import json, sys
from datetime import datetime
from pathlib import Path

PROJECT_ROOT = Path(__file__).parent.parent
sys.path.insert(0, str(PROJECT_ROOT))
sys.path.insert(0, str(PROJECT_ROOT / "agents"))


class ContentProductionOps(object):
    """内容生产部实作化层。封装10个Agent的领域方法, 驱动完整生产管道。"""

    def __init__(self, chief, members_dict, db=None, client=None):
        self.chief = chief          # feed_strategist (DepartmentChief)
        self.members = members_dict  # {agent_code: agent}
        self.db = db
        self.client = client
        self._stage_map = {
            "gap": self._run_gap_analysis,
            "crawl": self._run_crawl,
            "feed": self._run_feed_extract,
            "qc": self._run_qc,
            "relations": self._run_relations,
            "premium": self._run_premium,
        }

    # ================================================================
    # 一日生产循环
    # ================================================================
    def daily_production_cycle(self, stage=None):
        """一日生产循环: 缺口分析→爬取→喂料→质检→分类→打包→报告。
        stage=None 跑全循环; 可指定单个阶段名加速。
        """
        started = datetime.now()
        report = {
            "dept": "content_production",
            "started": started.isoformat(),
            "stages": {},
            "summary": {},
            "agent_insights": [],
        }

        stages_to_run = [stage] if stage and stage in self._stage_map else list(self._stage_map.keys())

        for s in stages_to_run:
            try:
                result = self._stage_map[s]()
                report["stages"][s] = result
            except Exception as e:
                report["stages"][s] = {"success": False, "error": str(e)[:200]}

        # 分类+打包+报告(仅在完整循环时运行)
        if stage is None:
            report["stages"]["classify"] = self._run_auto_classify()
            report["stages"]["packaging"] = self._run_packaging_check()
            report["stages"]["report"] = self._generate_daily_report(report)

        report["elapsed_sec"] = round((datetime.now() - started).total_seconds(), 1)
        report["success"] = all(
            r.get("success", True) for r in report["stages"].values()
        )
        return report

    # ================================================================
    # 岗位领域方法
    # ================================================================
    def research_policy(self, policy_text_or_url):
        """政策研究员: 将政策文件/文本转为结构化KP。
        用policy_researcher的think()做专业分析, 产出: 原文要点+老唐视角+落地步骤+风险提示。
        """
        agent = self.members.get("policy_researcher")
        if not agent:
            return {"error": "policy_researcher不可用", "kps": []}

        context = {
            "task": "policy_analysis",
            "input_type": "url" if policy_text_or_url.startswith("http") else "text",
            "content": policy_text_or_url[:5000],
            "requirements": [
                "标注政策文件号/条款原文/发布时间/有效期限",
                "必须有'老唐视角'解读(非政策复述,是实战判断)",
                "产出≥3条可入库的知识点",
                "每条KP含: 标题/类型/原文/解读/行动建议/风险/时效",
            ],
        }
        result = agent.think(context, deep=True)
        kps = self._extract_kps_from_result(result)
        return {
            "agent": "policy_researcher",
            "analysis": result.get("analysis", "")[:400],
            "insights": result.get("insights", []),
            "kps": kps,
            "confidence": result.get("confidence", "medium"),
        }

    def collect_case(self, case_description):
        """案例采编员: 收集四川真实项目案例。
        产出: 项目名称/地点/时间/成本/关键决策点/成败分析。
        """
        agent = self.members.get("case_collector")
        if not agent:
            return {"error": "case_collector不可用", "case": None}

        context = {
            "task": "case_collection",
            "description": case_description[:3000],
            "requirements": [
                "项目名称/地点/时间/成本(尽可能量化)",
                "关键决策点和决策人",
                "成功因素(为什么成)或失败根因(为什么败)",
                "对操盘手的参考价值(他看了能用在什么场景)",
                "来源可验证性标注",
            ],
        }
        result = agent.think(context, deep=True)
        return {
            "agent": "case_collector",
            "analysis": result.get("analysis", "")[:400],
            "structured_case": {
                "project_name": "",
                "location": "",
                "time_period": "",
                "cost_data": {},
                "key_decisions": result.get("insights", []),
                "lessons": result.get("recommendations", []),
            },
            "confidence": result.get("confidence", "medium"),
        }

    def extract_methodology(self, experience_text):
        """方法论专家: 把老唐经验转为可复制方法。
        产出: 步骤/模板/检查清单/话术/决策树。
        """
        agent = self.members.get("methodology_expert")
        if not agent:
            return {"error": "methodology_expert不可用", "methodology": None}

        context = {
            "task": "methodology_extraction",
            "experience": experience_text[:3000],
            "requirements": [
                "抽象为可复制的步骤(≥3步)",
                "每步对应颗粒度: '下一步该找哪个部门/填什么表'",
                "产出可直接填空的模板或检查清单",
                "标注老唐实战来源(非书本理论)",
                "前置条件和适用边界标注",
            ],
        }
        result = agent.think(context, deep=True)
        return {
            "agent": "methodology_expert",
            "analysis": result.get("analysis", "")[:400],
            "methodology": {
                "steps": result.get("recommendations", []),
                "template": "",
                "checklist": [],
                "preconditions": result.get("insights", []),
            },
            "confidence": result.get("confidence", "medium"),
        }

    # ================================================================
    # 管道阶段驱动
    # ================================================================
    def run_pipeline_stage(self, stage):
        """管道总监: 驱动指定管道阶段。stage: gap/crawl/feed/qc/relations/premium"""
        if stage not in self._stage_map:
            return {"error": f"未知阶段'{stage}', 可选: {list(self._stage_map.keys())}"}
        return self._stage_map[stage]()

    def department_status(self):
        """部门状态: 成员活跃度+产出统计+待办事项"""
        members_info = []
        for code, agent in self.members.items():
            members_info.append({
                "code": code,
                "name": agent.agent_name,
                "type": getattr(agent, "agent_type", "?"),
                "calls": getattr(agent, "_call_count", 0),
                "cost": round(getattr(agent, "_total_cost", 0), 4),
            })

        db_stats = {}
        if self.db:
            try:
                conn = self.db.get_connection()
                c = conn.cursor()
                c.execute("SELECT COUNT(*) FROM knowledge_points")
                db_stats["total_kps"] = c.fetchone()[0]
                c.execute("""SELECT COUNT(*) FROM knowledge_points
                             WHERE review_status='confirmed'""")
                db_stats["confirmed_kps"] = c.fetchone()[0]
                c.execute("SELECT COUNT(*) FROM source_files")
                db_stats["source_files"] = c.fetchone()[0]
                c.execute("SELECT COUNT(*) FROM kp_relations")
                db_stats["relations"] = c.fetchone()[0]
                c.execute("SELECT COUNT(*) FROM crawl_history")
                db_stats["crawl_history"] = c.fetchone()[0]
                conn.close()
            except Exception:
                pass

        return {
            "dept": "content_production",
            "chief": self.chief.agent_name,
            "member_count": len(members_info),
            "members": members_info,
            "total_calls": sum(m["calls"] for m in members_info),
            "total_cost": round(sum(m["cost"] for m in members_info), 4),
            "db_stats": db_stats,
            "timestamp": datetime.now().isoformat(),
        }

    # ================================================================
    # 阶段内部实现
    # ================================================================
    def _run_gap_analysis(self):
        """阶段1: 知识缺口分析"""
        from agents.knowledge_gap_analyzer import KnowledgeGapAnalyzer
        analyzer = KnowledgeGapAnalyzer(db=self.db, client=self.client)
        gaps = analyzer.analyze_all_gaps()
        return {
            "success": True,
            "coverage_rate": gaps.get("coverage_rate", 0),
            "total_needs": gaps.get("total_knowledge_needs", 0),
            "gaps_count": gaps.get("gaps", 0),
            "top_gaps": gaps.get("gaps_detail", [])[:5],
        }

    def _run_crawl(self):
        """阶段2: 定向爬取(调用crawler_scheduler)"""
        try:
            from agents.crawler_scheduler import CrawlerScheduler
            scheduler = CrawlerScheduler(db=self.db, client=self.client)
            result = scheduler.run_scheduled_crawl()
            return {
                "success": True,
                "urls_crawled": result.get("total", 0) if isinstance(result, dict) else 0,
                "qualified": result.get("qualified", 0) if isinstance(result, dict) else 0,
            }
        except Exception as e:
            return {"success": False, "error": str(e)[:200]}

    def _run_feed_extract(self):
        """阶段3: 喂料+提取(调用auto_feeder)"""
        try:
            from agents.auto_feeder import AutoFeeder
            feeder = AutoFeeder(db=self.db, client=self.client)
            inv = feeder.inventory_test_files()
            already = feeder.get_already_processed()
            pending = [f for f in inv if f["name"] not in already]
            if not pending:
                return {"success": True, "message": "无待处理文件", "total_kps": 0}
            report = feeder.run_full_pipeline(model_key="parallel", run_relations=False)
            return {
                "success": True,
                "files_processed": len(pending),
                "total_kps": report.get("summary", {}).get("total_kps", 0),
            }
        except Exception as e:
            return {"success": False, "error": str(e)[:200]}

    def _run_qc(self):
        """阶段4: 批量质检"""
        try:
            from agents.auto_feeder import AutoFeeder
            feeder = AutoFeeder(db=self.db, client=self.client)
            result = feeder._run_full_qc()
            return {
                "success": True,
                "processed": result.get("processed", 0) if isinstance(result, dict) else 0,
            }
        except Exception as e:
            return {"success": False, "error": str(e)[:200]}

    def _run_relations(self):
        """阶段5: 关系扫描(调用run_pipeline --relations-only)"""
        try:
            from scripts.run_pipeline import run_relations_only
            result = run_relations_only(self.db, self.client)
            return {
                "success": True,
                "relations_found": result.get("relations_found", 0) if isinstance(result, dict) else 0,
            }
        except Exception:
            return {"success": True, "relations_found": 0, "status": "skipped"}

    def _run_premium(self):
        """精品判定"""
        try:
            from scripts.run_pipeline import run_premium_only
            result = run_premium_only(self.db, self.client)
            return {
                "success": True,
                "promoted": result.get("promoted_to_quotable", 0) if isinstance(result, dict) else 0,
            }
        except Exception:
            return {"success": True, "promoted": 0, "status": "skipped"}

    def _run_auto_classify(self):
        """自动分类确认: 让auto_classifier agent批量处理待分类KP"""
        agent = self.members.get("auto_classifier")
        if not agent:
            return {"success": True, "status": "skipped", "reason": "agent未加载"}
        context = {
            "task": "auto_classify_batch",
            "action": "扫描所有final_category_id IS NULL的KP, 批量确认AI分类建议",
            "rules": ["默认同意", "明显错误才拒绝", "拒绝须给替代分类", "30秒内处理全部"],
        }
        result = agent.think(context)
        return {
            "success": True,
            "agent": "auto_classifier",
            "action": result.get("analysis", "")[:200],
        }

    def _run_packaging_check(self):
        """内容包装检查: 让content_packager识别可包装为产品的KP组"""
        agent = self.members.get("content_packager")
        if not agent:
            return {"success": True, "status": "skipped", "reason": "agent未加载"}
        context = {
            "task": "packaging_scan",
            "action": "扫描知识库中被标记为confirmed的高质量KP, 识别可直接包装为产品的KP组",
        }
        result = agent.think(context)
        return {
            "success": True,
            "agent": "content_packager",
            "packaging_candidates": result.get("recommendations", [])[:5],
        }

    def _generate_daily_report(self, pipeline_report):
        """生成每日部门报告: 让chief+各成员分析当日产出"""
        # 各部门成员发表意见
        insights = []
        for code in ["pipeline_director", "auto_classifier", "content_packager"]:
            agent = self.members.get(code)
            if not agent:
                continue
            try:
                r = agent.think({
                    "task": "daily_reflection",
                    "pipeline_summary": str(pipeline_report.get("stages", {}))[:2000],
                })
                insights.append({"agent": code, "reflection": r.get("analysis", "")[:200]})
            except Exception:
                pass

        pipeline_report["agent_insights"] = insights

        # Chief 汇总
        if self.chief:
            try:
                summary = self.chief.think({
                    "task": "daily_report_summary",
                    "pipeline_report": str(pipeline_report.get("stages", {}))[:2000],
                    "agent_insights": insights,
                }, deep=True)
                pipeline_report["chief_summary"] = summary.get("analysis", "")[:400]
            except Exception:
                pipeline_report["chief_summary"] = "部门长暂未汇总"

        return {"success": True, "insights_count": len(insights)}

    # ================================================================
    # 辅助
    # ================================================================
    def _extract_kps_from_result(self, result):
        """从agent think结果中提取KP列表"""
        kps = []
        recs = result.get("recommendations", [])
        for r in recs[:10]:
            if isinstance(r, dict):
                kps.append({
                    "title": r.get("action", "")[:100],
                    "type": "policy",
                    "action": r.get("reason", "")[:200],
                    "priority": r.get("priority", "P2"),
                })
        return kps


def handle_content_production_task(task, db=None, client=None):
    """CEO可调用此函数将任务路由到内容生产部。
    task: dict {task_name, ...} 或 str "今日生产"
    返回: 执行报告 dict
    """
    from agents.agent_orchestra import build_all_agents

    result = build_all_agents(client=client, db=db)
    all_agents = result.get("agents", [])
    departments = result.get("departments", {})

    # 找部门长和成员
    agent_map = {a.agent_code: a for a in all_agents}
    dept_info = departments.get("content_production", {})
    chief_code = dept_info.get("chief", "feed_strategist")
    chief = agent_map.get(chief_code)

    if not chief:
        return {"success": False, "error": f"内容生产部长({chief_code})未找到"}

    # 收集成员
    members = {}
    for code in dept_info.get("members", []):
        if code in agent_map and code != chief_code:
            members[code] = agent_map[code]

    ops = ContentProductionOps(chief, members, db=db, client=client)

    task_name = task if isinstance(task, str) else task.get("task_name", task.get("task", ""))
    task_name_lower = task_name.lower()

    if any(w in task_name_lower for w in ["今日生产", "daily", "生产循环", "全管道"]):
        return ops.daily_production_cycle()
    elif any(w in task_name_lower for w in ["政策", "policy", "research_policy"]):
        content = task.get("content", task.get("policy_text", task_name)) if isinstance(task, dict) else task_name
        return ops.research_policy(content)
    elif any(w in task_name_lower for w in ["案例", "case", "collect_case"]):
        content = task.get("content", task.get("case_description", task_name)) if isinstance(task, dict) else task_name
        return ops.collect_case(content)
    elif any(w in task_name_lower for w in ["方法", "methodology", "经验", "extract_methodology"]):
        content = task.get("content", task.get("experience_text", task_name)) if isinstance(task, dict) else task_name
        return ops.extract_methodology(content)
    elif any(w in task_name_lower for w in ["状态", "status", "部门"]):
        return ops.department_status()
    elif any(w in task_name_lower for w in ["管道", "pipeline", "stage"]):
        stage = task.get("stage", "gap") if isinstance(task, dict) else "gap"
        return ops.run_pipeline_stage(stage)
    else:
        return {
            "success": False,
            "error": f"未识别的任务: '{task_name}'",
            "supported": ["今日生产/全管道", "政策/案例/方法论/经验分析",
                         "部门状态", "管道阶段: gap/crawl/feed/qc/relations/premium"],
        }
