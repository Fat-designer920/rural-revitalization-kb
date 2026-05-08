"""
client_delivery_ops.py - 客户交付部操作中心,从客户问题到完整方案的全链路交付
路径：agents/client_delivery_ops.py
版本：v2.3.7
"""
import json
import re
import time
from agents.brand_redlines import BrandRedlineChecker


class ClientDeliveryOps:
    """客户交付部操作中心。从客户问题到完整方案的全链路交付。

    驱动部门: solution_architect(部门长)统领 customer_reviewer + qa_consultant
             + sales_page_gen + feedback_analyst, 完成:
    问答→审查→方案汇编→销售页面→反馈分析→全链路管道。
    """

    def __init__(self, chief, members_dict, db=None, client=None):
        self.chief = chief
        self.members = members_dict  # {agent_code: BaseAgent/DepartmentChief}
        self.db = db
        self.client = client
        self.brand_checker = BrandRedlineChecker()
        self._delivery_log = []

    def answer_customer_question(self, query, customer_profile=None):
        """问答交付: 客户提问 -> run_qa检索生成 -> customer_reviewer审查 -> 返回。

        调用 qa_assistant.run_qa() 获取4板块回答,再用客户视角审查员做质量把关。
        """
        from scripts.qa_assistant import run_qa

        qa_result = run_qa(self.db, self.client, query, mode='self')
        review = None
        reviewer = self.members.get('customer_reviewer')
        if reviewer and qa_result.get('ok'):
            review = reviewer.think({
                "task": "审查问答结果对付费客户的价值",
                "query": query,
                "answer": qa_result.get('answer', ''),
                "customer_profile": customer_profile,
            })
        return {
            "qa_result": qa_result,
            "customer_review": review,
            "delivered_at": time.time(),
        }

    def assemble_solution(self, client_needs, solution_type='策划方案'):
        """方案汇编: chief深度理解需求 -> DB调集KP -> 组织成结构化方案。

        solution_type: '策划方案'|'融资方案'|'政策解读'|'项目申报'
        方案结构: 背景->分析->方案->风险->下一步
        """
        chief = self.chief
        if not chief:
            return {"error": "方案汇编师(部门长)未就位", "solution_type": solution_type}

        analysis = chief.think({
            "task": "理解客户需求并设计解决方案框架",
            "client_needs": client_needs,
            "solution_type": solution_type,
        }, deep=True)

        keywords = self._extract_keywords(client_needs)
        kps = self._retrieve_kps_for_solution(keywords, solution_type)

        solution = {
            "solution_type": solution_type,
            "client_needs": client_needs,
            "needs_analysis": analysis,
            "retrieved_kps": kps,
            "sections": [
                "背景与需求理解",
                "关键问题分析",
                "解决方案与路径",
                "风险分析与对策",
                "下一步行动建议",
            ],
            "assembled_at": time.time(),
        }
        return solution

    def _extract_keywords(self, client_needs):
        """从客户需求文本中提取检索关键词。fallback只用原文本切词。"""
        if isinstance(client_needs, dict):
            text = ' '.join(str(v) for v in client_needs.values() if v)
        else:
            text = str(client_needs)
        parts = re.split(r'[,，、;；\s]+', text)
        return [p.strip() for p in parts if len(p.strip()) >= 2][:10]

    def _retrieve_kps_for_solution(self, keywords, solution_type):
        """从DB检索方案所需知识点。使用get_qa_retrieval_candidates批量召回。"""
        if not self.db or not keywords:
            return []
        try:
            candidates = self.db.get_qa_retrieval_candidates(keywords, limit=50)
            return candidates[:20]  # 取Top 20
        except AttributeError:
            return []

    def review_for_customer(self, content, customer_profile=None):
        """客户视角审查: 从付费客户角度评估内容质量与付费意愿。"""
        reviewer = self.members.get('customer_reviewer')
        if not reviewer:
            return {"error": "customer_reviewer 未就位", "reviews": []}
        return reviewer.think({
            "task": "从付费客户视角审查内容",
            "content": str(content)[:3000],
            "customer_profile": customer_profile,
        })

    def collect_feedback(self, qa_history_id):
        """反馈收集分析: feedback_analyst 对单次问答反馈进行结构化分析。"""
        analyst = self.members.get('feedback_analyst')
        if not analyst:
            return {"error": "feedback_analyst 未就位"}
        return analyst.think({
            "task": "分析客户反馈并输出分类与优先级",
            "qa_history_id": qa_history_id,
        })

    def generate_sales_page(self, product_info):
        """销售页面生成: sales_page_gen 生成AIDA漏斗页->品牌红线检查->返回。"""
        sales_gen = self.members.get('sales_page_gen')
        if not sales_gen:
            return {"error": "sales_page_gen 未就位"}
        page = sales_gen.think({
            "task": "生成AIDA漏斗销售页面",
            "product_info": product_info,
        })
        raw_text = json.dumps(page, ensure_ascii=False)
        brand_result = self.brand_checker.check_content(raw_text, "sales_page")
        return {
            "page_content": page,
            "brand_check": brand_result,
            "generated_at": time.time(),
        }

    def delivery_pipeline(self, customer_request):
        """全链路交付管道(6步)。

        理解需求 -> 知识检索 -> 客户审查 -> 方案组装 -> 品牌红线 -> 最终交付
        """
        query = customer_request.get('query', '')
        solution_type = customer_request.get('solution_type', '策划方案')
        customer_profile = customer_request.get('customer_profile')
        steps = []

        # 1. 理解需求
        steps.append({"step": "understand", "status": "running"})
        needs = self.chief.think({
            "task": "理解客户交付需求,确定交付策略",
            "request": customer_request,
        }, deep=True) if self.chief else {}
        steps[-1]["status"] = "done"

        # 2. 知识检索+问答
        steps.append({"step": "retrieve", "status": "running"})
        qa = self.answer_customer_question(query, customer_profile)
        steps[-1]["status"] = "done"

        # 3. 客户视角审查
        steps.append({"step": "review", "status": "running"})
        review = self.review_for_customer(qa.get('qa_result', {}), customer_profile)
        steps[-1]["status"] = "done"

        # 4. 方案组装(若需求含完整方案)
        steps.append({"step": "assemble", "status": "running"})
        solution = None
        if solution_type and query:
            solution = self.assemble_solution(customer_request, solution_type)
        steps[-1]["status"] = "done"

        # 5. 品牌红线检查
        steps.append({"step": "brand_check", "status": "running"})
        answer_text = str(qa.get('qa_result', {}).get('answer', ''))
        brand = self.brand_checker.check_content(answer_text, "solution")
        steps[-1]["status"] = "done"

        # 6. 交付
        steps.append({"step": "deliver", "status": "done"})
        delivery = {
            "query": query,
            "qa_answer": qa,
            "customer_review": review,
            "solution": solution,
            "brand_check": brand,
            "steps": steps,
            "delivered_at": time.time(),
            "status": "delivered" if brand.get('passed', True) else "brand_blocked",
        }

        self._delivery_log.append({
            "time": delivery["delivered_at"],
            "query": query[:100],
            "status": delivery["status"],
            "steps": len(steps),
        })
        return delivery

    def department_status(self):
        """部门运行状态概览。"""
        member_details = []
        for code, m in self.members.items():
            member_details.append({
                "code": code,
                "name": m.agent_name,
                "type": getattr(m, "agent_type", "?"),
                "calls": getattr(m, "_call_count", 0),
                "cost": round(getattr(m, "_total_cost", 0), 4),
            })
        return {
            "dept": "客户交付部",
            "chief": self.chief.agent_name if self.chief else "未设置",
            "chief_dept": getattr(self.chief, "_dept_key", None) if self.chief else None,
            "members": list(self.members.keys()),
            "member_details": member_details,
            "delivery_log_count": len(self._delivery_log),
            "recent_deliveries": self._delivery_log[-5:],
            "brand_checker": "active",
        }


def get_delivery_ops(db, client):
    """工厂函数。构建所有Agent,找出客户交付部成员,装配ClientDeliveryOps并返回。
    CEO可直接调用此函数获取交付操作中心: ops = get_delivery_ops(db, client)
    """
    from agents.agent_orchestra import build_all_agents
    from agents.expansion_agents import build_expansion_agents
    from agents.revenue_agents import build_revenue_agents

    result = build_all_agents(client=client, db=db)
    all_agents = result['agents']

    agent_map = {}
    for a in all_agents:
        agent_map[a.agent_code] = a

    # 补录扩编Agent(feedback_analyst来自expansion, sales_page_gen来自revenue)
    for build_fn in [build_expansion_agents, build_revenue_agents]:
        try:
            for a in build_fn(client=client, db=db):
                if a.agent_code not in agent_map:
                    agent_map[a.agent_code] = a
        except Exception:
            pass

    chief = agent_map.get('solution_architect')
    delivery_codes = ['customer_reviewer', 'qa_consultant',
                      'sales_page_gen', 'feedback_analyst']
    members_dict = {}
    for code in delivery_codes:
        if code in agent_map:
            members_dict[code] = agent_map[code]

    # 为部门长做实部门管理
    if chief and hasattr(chief, 'set_department'):
        members_list = list(members_dict.values())
        chief.set_department(
            'client_delivery',
            '直接服务付费客户:问答+方案+审查,客户满意度>=85%,续费率>=60%',
            members_list,
        )

    return ClientDeliveryOps(chief, members_dict, db, client)
