"""pricing_validator.py - 定价验证器(用真实客户反馈替代理论定价)。路径:agents/pricing_validator.py。版本:v2.3.7-part5。"""
import sqlite3

# 五档定价(待验证,不假设正确)
TIERS = {
    "basic":      {"price":19.9,  "label":"基础版","qpm":50,  "target":"township_cadre"},
    "pro":        {"price":99,    "label":"专业版","qpm":200, "target":"planner"},
    "expert":     {"price":199,   "label":"专家版","qpm":400, "target":"consultant"},
    "team":       {"price":999,   "label":"团队版","qpm":1000,"target":"pm"},
    "government": {"price":20000, "label":"县级版","qpm":2000,"target":"investor"},
}
TYPE_TO_TIER = {"township_cadre":"basic","pm":"team","planner":"pro","consultant":"expert","investor":"government"}

# DeepSeek V4 API 成本(硅基流动, 2026Q2)
IN_COST, OUT_COST = 1.00, 4.00  # 元/百万token
IN_TOK, OUT_TOK = 2500, 600      # 每查询平均token数(system+KP / 回答)

PERSONAS = {
    "township_cadre": ("村支书/乡镇干部","政策变化看不懂,项目申报没门路","自费¥20-50/月"),
    "pm":             ("项目经理/平台公司","合规风险大,指标测算不准","公司报销¥200-1000/月"),
    "planner":        ("规划院/咨询师","方案编制缺四川本地政策数据","项目经费¥100-500/月"),
    "consultant":     ("独立顾问/投资人","需快速判断项目可行性","自费¥100-300/月"),
    "investor":       ("县局/政府客户","全域推进缺决策支撑工具","财政¥1-3万/年"),
}


class PricingValidator(object):
    """定价验证器。用真实客户反馈替代理论定价。"""

    def __init__(self, db=None):
        self.db = db
        self._test_results = []

    def generate_test_offer(self, customer_type):
        """为特定客户类型生成免费试用邀请文案,可直接发给客户。"""
        p = PERSONAS.get(customer_type)
        if not p:
            return {"error": f"Unknown type: {customer_type}", "valid": list(PERSONAS.keys())}
        title, pain, budget = p
        tier = TIERS[TYPE_TO_TIER.get(customer_type, "basic")]
        body = f"{title}你好,\n\n我们为像你这样的{title}做了一个四川乡村振兴知识工具,核心解决一个问题:「{pain}」。\n\n现在邀请你免费试用1个月({tier['label']}),无需付费、无需承诺。\n试用期间:AI问答({tier['qpm']}次/月)+政策速查+案例库。\n我们只希望试用结束后你花2分钟告诉我们:这个工具值多少钱,哪里还不够好。\n\n如果你的朋友也需要,欢迎转发——每邀请1位同行试用,再送1个月。"
        return {
            "customer_type": customer_type, "persona": title, "pain_point": pain,
            "subject": f"【内测邀请】{title},送你1个月免费试用四川乡村振兴知识库",
            "body": body, "call_to_action": "回复「试用」即可开通",
            "tier_matched": TYPE_TO_TIER.get(customer_type, "basic"), "trial_period_days": 30,
        }

    def willingness_to_pay_survey(self, features_used, satisfaction):
        """基于使用数据生成付费意愿调查问卷。"""
        qs = [
            ("willingness","choice","试用结束后,你愿意付费继续使用吗?",
             ["愿意","不愿意","不确定,看价格"]),
            ("price_point","choice","你觉得月付多少钱是「合理且愿意付」的?",
             ["¥19.9","¥49","¥99","¥199","¥299","¥499+","不付费"]),
            ("too_expensive","choice","超过多少钱你就「绝对不会付」?",
             ["¥29","¥59","¥129","¥259","¥599","¥999+"]),
            ("too_cheap","choice","低于多少钱你会「怀疑质量」?",
             ["¥9.9","¥19.9","¥49","¥99","¥199","不会怀疑"]),
            ("one_thing","text","如果只改一件事,你最希望我们加什么功能?",[]),
            ("friend_price","text","你觉得你的同行会愿意付多少钱?",[]),
        ]
        if satisfaction <= 2:
            qs.insert(0, ("dissatisfaction","text","最不好用的是哪一点?我们立刻改。",[]))
        unused = [f for f in ["合规自检","项目报告","指标测算","政策预警","案例对比"]
                  if f not in set(features_used)]
        if unused:
            qs.append(("unused_features","multichoice",
                       "以下功能你还没用过,加上觉得值更多钱吗?", unused))
        return {
            "title": "试用体验调查(2分钟)", "intro": f"你已使用{len(features_used)}项,满意度{satisfaction}/5",
            "questions": [{"id":q[0],"type":q[1],"text":q[2],"options":q[3]} for q in qs],
        }

    def analyze_pricing_feedback(self, responses):
        """分析定价反馈列表。responses: [{'willingness':'愿意','price_point':'¥99',...},...]"""
        n = len(responses)
        if n == 0:
            return {"error": "无反馈数据", "sample_size": 0}

        willing = sum(1 for r in responses if r.get("willingness") == "愿意")
        pc = {}
        for r in responses:
            pp = r.get("price_point");
            if pp: pc[pp] = pc.get(pp, 0) + 1
        ranked = sorted(pc.items(), key=lambda x: x[1], reverse=True)

        floor, ceilings = None, []
        for r in responses:
            tc = r.get("too_cheap","")
            if tc and tc != "不会怀疑":
                v = float(tc.replace("¥","").replace("+",""))
                if floor is None or v > floor: floor = v
            te = r.get("too_expensive","")
            if te: ceilings.append(float(te.replace("¥","").replace("+","")))
        avg_c = sum(ceilings)/len(ceilings) if ceilings else None

        return {
            "sample_size": n, "willingness_rate": round(willing / n, 2),
            "optimal_price_point": ranked[0][0] if ranked else "insufficient_data",
            "acceptable_range": {"floor": floor, "ceiling": avg_c,
                "interpretation": (f"低于¥{floor}怀疑质量,高于¥{avg_c:.0f}不付"
                                   if floor and avg_c else "待更多数据")},
            "verdict": self._verdict(ranked, willing / n),
        }

    def _verdict(self, ranked, wr):
        v = {"¥19.9":"基础版获客定位正确,确认API成本","¥99":"专业版价格敏感区,可试¥79",
             "¥199":"专家版价值定价,需合规报告支撑溢价","¥499+":"高付费意愿超预期,加推团队/县级",
             "不付费":"先提升产品价值感知"}
        base = v.get(ranked[0][0] if ranked else "","数据不足") if ranked else "数据不足"
        return base + (";付费意愿<50%,先提高产品价值" if wr < 0.5 else "")

    def recommend_pricing(self):
        """基于已收集的反馈推荐最优定价,连API成本毛利。"""
        if not self._test_results:
            return {"status": "no_data", "message": "先收集反馈再推荐",
                    "next_step": "找3-5位真实客户填willingness_to_pay_survey"}

        enriched = {}
        for code, t in TIERS.items():
            cost = self._cost_per_user(t["qpm"])
            enriched[code] = dict(t, api_cost=cost["total_monthly"],
                gross_margin_pct=round((t["price"]-cost["total_monthly"])/t["price"]*100, 1)
                if t["price"] > 0 else 0)
        return {"current_tiers": enriched, "data_points": len(self._test_results),
                "confidence": "low" if len(self._test_results) < 10 else "medium"}

    def unit_economics_calculator(self, monthly_queries_per_user=50):
        """单位经济学计算器。输入月查询数,输出API成本/用户+毛利+盈亏平衡。"""
        in_t = monthly_queries_per_user * IN_TOK
        out_t = monthly_queries_per_user * OUT_TOK
        cost = (in_t / 1_000_000) * IN_COST + (out_t / 1_000_000) * OUT_COST
        cost_basic = self._cost_per_user(50)
        return {
            "assumptions": {"qpm": monthly_queries_per_user, "avg_in_tok": IN_TOK,
                "avg_out_tok": OUT_TOK, "v4_in_1M": IN_COST, "v4_out_1M": OUT_COST},
            "total_monthly": round(cost, 4), "per_query": round(cost / monthly_queries_per_user, 6),
            "tier_margins": self._tier_margins(),
            "breakeven_check": (
                f"基础版成本¥{cost_basic['total_monthly']:.4f}/人/月,"
                f"定价¥19.9→毛利¥{19.9-cost_basic['total_monthly']:.4f}"
                if monthly_queries_per_user <= 50 else
                f"成本¥{cost:.4f} > 定价¥19.9→基础版亏本,需限额或提价"
            ),
        }

    def _cost_per_user(self, qpm):
        in_c = (qpm * IN_TOK) / 1_000_000 * IN_COST
        out_c = (qpm * OUT_TOK) / 1_000_000 * OUT_COST
        t = round(in_c + out_c, 4)
        return {"total_monthly": t, "per_query": round(t / qpm, 6)}

    def _tier_margins(self):
        margins = []
        for code, t in TIERS.items():
            c = self._cost_per_user(t["qpm"])
            m = t["price"] - c["total_monthly"]
            mp = round(m / t["price"] * 100, 1) if t["price"] > 0 else 0
            margins.append({"tier": t["label"], "price": t["price"],
                "api_cost": c["total_monthly"], "margin": round(m, 2),
                "margin_pct": mp, "verdict": "healthy" if mp > 70 else "ok" if mp > 40 else "thin"})
        return margins

    def get_trial_ready_customers(self, limit=20):
        """从DB的qa_history找适合邀请试用的客户(friend模式活跃用户)。"""
        if not self.db:
            return {"error": "数据库不可用", "targets": []}
        targets = []
        try:
            cur = self._resolve_cursor()
            cur.execute("""SELECT qh.friend_tag, COUNT(*) as qc, MAX(qh.created_at),
                (SELECT COUNT(*) FROM qa_feedback qf
                 WHERE qf.qa_history_id=qh.id AND qf.feedback_type='helpful') as hc
                FROM qa_history qh WHERE qh.mode='friend' AND qh.is_test_query=0
                GROUP BY qh.friend_tag HAVING qc>=3 ORDER BY qc DESC LIMIT ?""", (limit,))
            for tag, qc, last, hc in cur.fetchall():
                targets.append({"tag": tag or "未标注", "queries": qc, "last_active": last,
                    "helpful": f"{hc}/{qc}",
                    "readiness": "high" if qc>=10 and hc>=3 else "medium" if qc>=5 else "low",
                    "suggested_offer": "expert" if qc>=30 else "pro" if qc>=15 else "basic"})
        except Exception as e:
            return {"error": str(e)[:200], "targets": targets}
        return {"total": len(targets), "targets": targets,
                "method": "qa_history friend模式,查询>=3次→可邀约"}

    def _resolve_cursor(self):
        """兼容多种DB传入方式: str路径/DBManager实例/connection/raw cursor。"""
        db = self.db
        if isinstance(db, str):
            self._conn = sqlite3.connect(db)
            return self._conn.cursor()
        if hasattr(db, 'cursor'):
            return db.cursor()
        if hasattr(db, 'conn'):
            return db.conn.cursor()
        if hasattr(db, 'get_connection'):
            self._conn = db.get_connection()
            return self._conn.cursor()
        return db.cursor()
