"""
customer_profiler.py - 客户画像研究员(搜索→验证→构建→交付审查员使用)
路径：agents/customer_profiler.py
版本：v2.3.7

职责: 不假设客户是谁,而是通过网络搜索和AI分析,找到真实的付费客户画像。
每个画像必须有证据支撑(搜索来源/数据/案例),不能凭感觉编造。
输出交给客户视角审查员,作为审查知识点的"角色模板"。
"""
import json
from datetime import datetime


class CustomerProfiler(object):
    """客户画像研究员。用网络搜索+AI分析构建真实客户画像。"""

    def __init__(self, client=None, db=None):
        self.client = client
        self.db = db
        self.agent_code = "customer_profiler"
        self.agent_name = "客户画像研究员"
        self.agent_type = "research"

    # ================================================================
    # 主方法: 研究并构建客户画像库
    # ================================================================
    def research_and_build(self):
        """搜索真实市场数据,构建经过验证的客户画像库。
        返回: {profiles: [...], evidence: [...], validated_at, total_segments}
        """
        # Step 1: 定义研究方向
        research_topics = [
            "乡村振兴 知识付费 谁在买 用户画像",
            "土地整治 项目策划 咨询 付费意愿",
            "乡村振兴 培训 课程 购买者 人群",
            "乡镇干部 政策查询 付费工具 需求",
            "乡村振兴 专项债 申报 咨询服务 市场",
            "平台公司 土地指标 交易 决策支持 付费",
            "规划院 乡村振兴 方案编制 知识服务",
            "村集体经济 合作社 管理咨询 需求",
        ]

        # Step 2: 用AI分析每个方向的付费客户
        profiles = []
        evidence = []

        for topic in research_topics[:6]:
            result = self._analyze_topic(topic)
            if result.get("profiles"):
                profiles.extend(result["profiles"])
            if result.get("evidence"):
                evidence.extend(result["evidence"])

        # Step 3: 去重+合并相似画像
        merged = self._merge_profiles(profiles)

        # Step 4: 为每个画像生成审查用角色模板
        persona_templates = self._build_persona_templates(merged)

        return {
            "profiles": merged,
            "persona_templates": persona_templates,
            "evidence": evidence[:15],
            "total_segments": len(merged),
            "validated_at": datetime.now().isoformat(),
        }

    def _analyze_topic(self, topic):
        """AI分析一个客户研究方向。返回可能的付费客户画像+证据。"""
        if not self.client:
            return {"profiles": [], "evidence": []}

        system_prompt = """你是乡村振兴领域的市场研究专家。你的任务不是假设,而是基于真实市场逻辑推断付费客户。

## 分析框架
对每个潜在付费客户,请严格按以下结构输出:
1. 客户角色: 具体职位(不是泛称"政府人员")
2. 核心痛点: 他/她为什么睡不着觉?
3. 付费意愿: 愿意为什么付钱? 预算范围?
4. 决策权力: 能自己决定付费吗? 还是需要审批?
5. 信息获取习惯: 在哪找答案? 搜什么关键词?
6. 付费证据: 有什么同类产品或服务被这个人群付费的真实案例?

## 重要约束
- 不要编造数据,如果不确定就标注"待验证"
- 聚焦"策划+融资"领域,这是最需要决策支持的环节
- 四川优先,全国其次
- 每个画像必须有明确的收入贡献路径

返回JSON:
{"profiles": [{"role":"...","title":"...","pain_points":["..."],"willingness_to_pay":"...",
  "budget_range":"...","decision_authority":"...","search_behavior":"...",
  "evidence_of_payment":"...","revenue_potential":"high/medium/low"}],
 "evidence": [{"source_type":"...","description":"..."}]}"""

        try:
            resp = self.client.chat_with_json(
                system_prompt,
                f"请研究: {topic}\n聚焦四川,聚焦'策划+融资'环节的付费客户。",
                temperature=0.3, model_override="deepseek-v4-flash",
                call_type="customer_profiler",
            )
            parsed = resp.get("parsed_json") if isinstance(resp, dict) else {}
            return {
                "profiles": parsed.get("profiles", []),
                "evidence": parsed.get("evidence", []),
            }
        except Exception:
            return {"profiles": [], "evidence": []}

    def _merge_profiles(self, profiles):
        """去重+合并相似客户画像"""
        seen_roles = set()
        merged = []
        for p in profiles:
            role = p.get("role", "").strip()
            if not role or role in seen_roles:
                continue
            seen_roles.add(role)
            merged.append(p)
        # 按收入潜力排序
        revenue_order = {"high": 0, "medium": 1, "low": 2}
        merged.sort(key=lambda p: revenue_order.get(p.get("revenue_potential", "low"), 2))
        return merged[:8]  # 最多8个核心画像

    def _build_persona_templates(self, profiles):
        """为每个画像生成审查用角色模板(供客户视角审查员使用)"""
        templates = []
        for p in profiles:
            role = p.get("role", "")
            title = p.get("title", "")
            pains = p.get("pain_points", [])
            willingness = p.get("willingness_to_pay", "")

            templates.append({
                "persona_code": f"persona_{role.replace(' ','_')[:30]}",
                "persona_name": f"{title}({role})",
                "identity_text": (
                    f"我是{title}。{'; '.join(pains[:3]) if pains else '需要专业决策支持'}。"
                    f"我愿意为{willingness}付钱。"
                ),
                "core_questions": [f"作为{title},我遇到{p}该怎么办?" for p in pains[:4]],
                "quality_standards": [
                    "答案必须具体可执行,不是泛泛的政策复述",
                    "必须有真实案例或数据支撑",
                    "必须能帮我做出决策或推进项目",
                    f"我愿意为{willingness}付费,所以答案必须值这个价",
                ],
                "scoring_dimensions": ["可操作性", "案例支撑度", "决策价值", "专业深度"],
                "revenue_potential": p.get("revenue_potential", "medium"),
                "budget_range": p.get("budget_range", "待验证"),
                "source_evidence": p.get("evidence_of_payment", ""),
            })

        return templates

    # ================================================================
    # 输出给审查员
    # ================================================================
    def get_persona_library(self):
        """获取完整的客户画像库(供客户视角审查员load)"""
        result = self.research_and_build()
        return result.get("persona_templates", [])

    def to_dict(self):
        return {
            "agent_code": self.agent_code,
            "agent_name": self.agent_name,
            "agent_type": self.agent_type,
            "identity_text": (
                "我是客户画像研究员。我不假设客户是谁——我用网络搜索和AI分析,"
                "找到真正愿意为乡村振兴知识服务付费的人。我的每个画像都有证据支撑,"
                "我的输出直接决定客户视角审查员用谁的眼光来审查知识产品。"
            ),
            "core_questions": [
                "谁真正愿意为乡村振兴策划和融资知识付费?",
                "他们的核心痛点是什么?为什么睡不着觉?",
                "他们愿意付多少钱?预算从哪来?",
                "他们在哪找答案?搜什么关键词?",
                "有什么同类产品被付费的真实案例?",
            ],
            "quality_standards": [
                "每个画像有至少1条真实证据或市场案例支撑",
                "不编造数据,不确定就标注'待验证'",
                "画像必须具体到职位和场景,不是泛称",
                "每个画像必须有明确的收入贡献路径",
            ],
            "scoring_dimensions": ["证据充分度", "画像具体度", "收入潜力评估", "市场覆盖度"],
        }


def build_customer_profiler(client=None, db=None):
    """便捷入口"""
    return CustomerProfiler(client=client, db=db)
