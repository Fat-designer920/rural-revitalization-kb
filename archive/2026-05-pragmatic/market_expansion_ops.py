"""
market_expansion_ops.py - 市场拓展部操作中心
路径：agents/market_expansion_ops.py
版本：v2.3.7

获客+内容营销+品牌+平台分发+竞品情报。周度营销循环全套操作。
"""
import json
from datetime import datetime
from agents.brand_redlines import BrandRedlineChecker


class MarketExpansionOps:
    """市场拓展部操作中心。获客+内容营销+品牌+平台分发+竞品情报。"""

    def __init__(self, chief, members_dict, db=None, client=None):
        self.chief = chief
        self.members = members_dict  # {agent_code: BaseAgent}
        self.db = db
        self.client = client
        self.brand_checker = BrandRedlineChecker()

    def _get(self, code):
        return self.members.get(code)

    # ---- 内容生产 ----

    def generate_marketing_content(self, topic, platform="zhihu", deep=False):
        """内容营销员: 生成面向操盘手的获客内容。每条有转化路径: 阅读→关注→试用→付费。"""
        m = self._get("content_marketer")
        if not m:
            return {"error": "content_marketer not found"}

        briefs = {
            "zhihu":    "深度长文(2000-5000字),专业深度+政策引用。目标:规划院/咨询公司/政府研究者。转化:阅读→关注专栏→私信→付费。",
            "douyin":   "60秒视频脚本,2秒抓注意力,结尾留钩子。目标:村支书/乡镇干部。转化:看完→关注→领免费资料→付费。口语化+真实案例。",
            "xiaohongshu": "图文笔记(信息图+清单体),封面吸引点击。目标:25-35岁规划从业者。转化:封面点击→收藏→私信→付费。精准关键词布局。",
        }
        brief = briefs.get(platform, briefs["zhihu"])

        ctx = {
            "task": "generate_marketing_content", "topic": topic,
            "platform": platform, "platform_brief": brief,
            "instruction": f"围绕'{topic}'生成{platform}内容。{brief}标题是点击率关键,首段决定留存,结尾是转化关键。",
        }
        return {"platform": platform, "topic": topic,
                "content_plan": m.think(ctx, deep=deep),
                "generated_at": datetime.now().isoformat()}

    # ---- 品牌审查 ----

    def brand_gate_review(self, content):
        """品牌把关人: 18条红线一票否决 + 3+Agent模拟客户评分≥4才发布。"""
        text = content.get("text", "") if isinstance(content, dict) else str(content)
        redline = self.brand_checker.check_content(text)
        if not redline["passed"]:
            return {"passed": False, "violations": redline["violations"],
                    "agent_scores": {}, "verdict": "REJECTED-红线一票否决",
                    "reviewed_at": datetime.now().isoformat()}

        # 至少3个Agent模拟客户阅读评分
        scorer_codes = ["customer_reviewer", "qa_consultant", "gtm_strategist", "content_marketer"]
        scorers = [a for a in (self._get(c) for c in scorer_codes) if a is not None]
        scores = []
        for agent in scorers[:4]:
            try:
                r = agent.think({"task": "brand_review_scoring", "content": text[:2000],
                    "instruction": "模拟客户从1-5打分(专业可信度/实用性/阅读体验/转化意愿)。"
                                   '返回JSON:{"score":整数1-5,"reason":"≤50字","would_pay":bool}'})
                p = r.get("parsed_json") if isinstance(r, dict) else {}
                if isinstance(p, dict) and "score" in p:
                    scores.append(p)
            except Exception:
                pass

        avg = sum(s.get("score", 0) for s in scores) / len(scores) if scores else 0
        passed = len(scores) >= 3 and avg >= 4.0
        return {"passed": passed, "violations": [], "agent_scores": scores,
                "avg_score": round(avg, 1),
                "verdict": "APPROVED" if passed else f"REJECTED-均分{avg}(需≥4.0且≥3人评分)",
                "reviewed_at": datetime.now().isoformat()}

    # ---- 平台分发 ----

    def distribute_to_platform(self, content, platforms=None):
        """分发到各平台: 知乎深度文章/抖音60秒脚本/小红书信息图。默认全平台。"""
        platforms = platforms or ["zhihu", "douyin", "xiaohongshu"]
        src = content if isinstance(content, str) else json.dumps(content, ensure_ascii=False)

        cfg = {
            "zhihu": ("zhihu_operator", "深度长文(2000-5000字)",
                      "将以下内容适配为知乎深度长文。专业标题+分章节+政策文件号引用+结尾引导关注。"),
            "douyin": ("douyin_operator", "60秒视频脚本",
                       "将以下内容适配为抖音60秒脚本。前2秒抓注意力+中间干货+结尾钩子引导下一条。"),
            "xiaohongshu": ("xiaohongshu_operator", "图文笔记(信息图+清单体)",
                            "将以下内容适配为小红书图文笔记。信息图封面描述+清单体正文+精准关键词+引导收藏。"),
        }

        results = {}
        for plat in platforms:
            c = cfg.get(plat)
            if not c:
                continue
            op_code, fmt, instruction = c
            op = self._get(op_code)
            if not op:
                results[plat] = {"error": f"{op_code} not found"}
                continue
            r = op.think({"task": "platform_adaptation", "platform": plat,
                          "format": fmt, "instruction": instruction, "source_content": src})
            results[plat] = {"platform": plat, "format": fmt,
                            "adapted_content": r, "adapted_at": datetime.now().isoformat()}
        return results

    # ---- 竞品情报 ----

    def competitive_intel_brief(self):
        """竞品情报简报: 天天学农/齐鲁农云/湖南用地宝/快手三农"""
        ci = self._get("competitive_intelligence")
        if not ci:
            return {"error": "competitive_intelligence not found"}
        ctx = {"task": "competitive_intel_brief",
               "instruction": "生成今日竞品情报简报。覆盖天天学农(课程/定价)、齐鲁农云(功能)、"
                              "湖南用地宝(动态)、快手三农(内容)。关注:价格变动≥10%预警/新课新功能/用户评价动向。"}
        return {"brief": ci.think(ctx, deep=True), "generated_at": datetime.now().isoformat(),
                "competitors": ["天天学农", "齐鲁农云", "湖南用地宝", "快手三农"]}

    # ---- 获客周报 ----

    def customer_acquisition_report(self):
        """获客周报: 各渠道获客数/转化率/CAC/ROI"""
        ctx = {"task": "acquisition_report",
               "instruction": "生成本周获客报告。按渠道(知乎/抖音/小红书/搜索/转介绍)统计:"
                              "曝光/点击/关注/试用/付费/转化率/CAC/ROI。与上周环比,找最优和最差渠道,给出下周优化建议。"}
        return {"report": self.chief.think(ctx, deep=True), "period": "weekly",
                "generated_at": datetime.now().isoformat()}

    # ---- GTM策略更新 ----

    def gtm_strategy_update(self):
        """获客策略师: 基于数据更新GTM策略"""
        ctx = {"task": "gtm_strategy_update",
               "instruction": "基于近期获客数据和竞品情报,评估GTM策略有效性。"
                              "哪个渠道ROI最高?哪个客户画像转化最好?定价是否需调整?竞品动向是否需响应?"
                              "输出更新后的GTM策略建议(≤3条核心动作)。"}
        return {"strategy_update": self.chief.think(ctx, deep=True),
                "updated_at": datetime.now().isoformat()}

    # ---- 周度营销循环 ----

    def weekly_marketing_cycle(self, topics=None):
        """周度营销循环: 竞品情报→内容生产→品牌审查→平台分发→数据回收"""
        topics = topics or ["全域土地综合整治最新政策解读",
                           "专项债申报实操避坑指南",
                           "高标准农田项目融资路径"]
        log = {"started_at": datetime.now().isoformat(), "steps": []}

        # Step 1: 竞品情报
        intel = self.competitive_intel_brief()
        log["steps"].append({"step": 1, "name": "competitive_intel",
                             "ok": "error" not in intel})

        # Step 2+: 每个topic: 生产→审查→分发
        for i, topic in enumerate(topics):
            tr = {"topic": topic, "platforms": {}}
            for plat in ["zhihu", "douyin", "xiaohongshu"]:
                gen = self.generate_marketing_content(topic, plat)
                if "error" in gen:
                    tr["platforms"][plat] = gen; continue
                review = self.brand_gate_review(gen)
                if not review.get("passed"):
                    tr["platforms"][plat] = {"status": "rejected", "review": review}; continue
                dist = self.distribute_to_platform(gen.get("content_plan", topic), [plat])
                tr["platforms"][plat] = {"status": "ready", "content": dist.get(plat)}
            log["steps"].append({"step": 2 + i, "name": f"content_{topic[:12]}", "result": tr})

        # 数据回收
        log["steps"].append({"step": len(topics) + 2, "name": "acquisition_report",
                             "ok": "error" not in self.customer_acquisition_report()})
        log["completed_at"] = datetime.now().isoformat()
        return log


# ---- 工厂函数 ----

def get_marketing_ops(db=None, client=None):
    """工厂函数: 从agent_orchestra构建MarketExpansionOps实例。不修改ceo_agent.py。"""
    from agents.agent_orchestra import build_all_agents

    built = build_all_agents(client=client, db=db)
    agents_list = built["agents"]
    dept = built["departments"].get("market_expansion", {})
    chief_code = dept.get("chief", "gtm_strategist")
    member_codes = dept.get("members", [])

    chief = None
    members_dict = {}
    for a in agents_list:
        if a.agent_code == chief_code:
            chief = a
        if a.agent_code in member_codes:
            members_dict[a.agent_code] = a

    if not chief:
        raise RuntimeError(f"Market Expansion chief '{chief_code}' not found")
    return MarketExpansionOps(chief, members_dict, db=db, client=client)
