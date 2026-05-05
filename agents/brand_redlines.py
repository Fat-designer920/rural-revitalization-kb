"""
brand_redlines.py - 品牌红线清单(所有对外内容必须通过的合规检查)
路径：agents/brand_redlines.py
版本：v2.3.7

品牌把关人的执法依据。所有对外发布内容(文章/视频/课程/图文)必须通过此清单。
一票否决制 — 任何一条红线触发=内容不得发布。
"""
import json


# 红线清单(五类, 18条)
REDLINES = {
    "法律红线": [
        {"id": "L1", "rule": "不得涉及土地征收补偿具体标准", "reason": "易引发社会矛盾,属于敏感信息"},
        {"id": "L2", "rule": "不得涉及民族、宗教敏感话题", "reason": "政策红线,零容忍"},
        {"id": "L3", "rule": "不得评价具体政府部门的审批效率或点名批评", "reason": "合规风险,可能被追责"},
        {"id": "L4", "rule": "不得给出'保证获批''包过'等承诺性表述", "reason": "虚假宣传,法律风险"},
    ],
    "事实红线": [
        {"id": "F1", "rule": "所有政策引用必须有文件号和可追溯来源", "reason": "错误政策引用=专业信誉崩塌"},
        {"id": "F2", "rule": "所有数据必须有来源标注(年份+出处)", "reason": "数据造假=品牌自杀"},
        {"id": "F3", "rule": "所有案例必须脱敏(隐去真实项目名/企业名/具体金额)", "reason": "保护隐私,避免纠纷"},
        {"id": "F4", "rule": "时效性标注: 政策类标注发布年份,数据类标注数据年份", "reason": "过时信息=误导客户"},
    ],
    "品牌红线": [
        {"id": "B1", "rule": "语言风格必须'像20年老师傅在说话',不能学术化/官腔/营销腔", "reason": "品牌调性=老唐IP"},
        {"id": "B2", "rule": "不能出现'最''第一''100%'等绝对化表述(除非有证据)", "reason": "广告法+可信度"},
        {"id": "B3", "rule": "不能贬低竞品(可以客观对比,但不能攻击)", "reason": "专业素养+法律风险"},
        {"id": "B4", "rule": "首次发布前必须3个以上Agent模拟客户阅读评分≥4分", "reason": "质量底线"},
    ],
    "商业红线": [
        {"id": "C1", "rule": "不能泄露老唐未公开的商业策略和定价细节", "reason": "商业秘密保护"},
        {"id": "C2", "rule": "不能透露具体客户信息和项目细节", "reason": "客户隐私+竞业限制"},
        {"id": "C3", "rule": "免费内容与付费内容边界清晰(免费给价值,付费给深度)", "reason": "不欺诈,不误导"},
    ],
    "合规红线": [
        {"id": "R1", "rule": "不提供具体投资建议(可以说方法,不能说'你应该投这个')", "reason": "避免被认定为投资顾问"},
        {"id": "R2", "rule": "不转发未经核实的政策传言或'内部消息'", "reason": "传播不实信息风险"},
        {"id": "R3", "rule": "不鼓励规避监管或打擦边球的做法", "reason": "合规底线"},
    ],
}


class BrandRedlineChecker(object):
    """品牌红线检查器。一票否决,不留情面。"""

    def __init__(self):
        self.redlines = REDLINES

    def check_content(self, content_text, content_type="article"):
        """检查一段内容是否触犯红线。返回 {passed: bool, violations: [], warnings: []}"""
        violations = []
        warnings = []

        for category, rules in REDLINES.items():
            for rule in rules:
                # 关键词检查(简化版,实际应配合AI深度审查)
                triggered = self._check_rule(content_text, rule)
                if triggered:
                    violations.append({
                        "category": category,
                        "rule_id": rule["id"],
                        "rule": rule["rule"],
                        "reason": rule["reason"],
                        "severity": "BLOCK",  # 一票否决
                    })

        return {
            "passed": len(violations) == 0,
            "violations": violations,
            "warnings": warnings,
            "content_type": content_type,
            "checked_at": __import__('datetime').datetime.now().isoformat(),
            "verdict": "APPROVED" if len(violations) == 0 else "REJECTED - 必须修改后重新提交",
        }

    def _check_rule(self, content, rule):
        """检查单条规则(简化版关键词匹配,完整版应由AI执行)"""
        rule_id = rule["id"]
        content_lower = content.lower() if isinstance(content, str) else ""

        # 简化的关键词触发
        triggers = {
            "L1": ["补偿标准", "征收补偿", "拆迁补偿"],
            "L2": ["民族", "宗教"],
            "L3": [],  # 需要AI判断
            "L4": ["保证获批", "包过", "100%通过"],
            "F1": [],  # 需要检查是否有文件号
            "F2": [],  # 需要检查数据是否有来源
            "B1": [],  # 需要AI判断语气
            "B2": ["最好", "第一", "唯一", "100%"],
            "B3": [],  # 需要AI判断
        }

        for keyword in triggers.get(rule_id, []):
            if keyword in content_lower:
                return True
        return False

    def get_redline_document(self):
        """获取完整的红线文档(供品牌把关人使用)"""
        return {
            "title": "乡村振兴知识集团 — 品牌红线清单",
            "version": "v1.0",
            "principle": "一票否决制。任何一条红线触发=内容不得发布。宁可不发,不可发坏。",
            "categories": REDLINES,
            "approval_flow": [
                "1. 内容创作者自检(对照红线清单)",
                "2. AI初审(品牌把关人Agent自动扫描)",
                "3. 模拟客户阅读(至少3个Agent评分≥4)",
                "4. 品牌把关人终审(人工/AI)",
                "5. 老唐终审(涉及老唐观点/经验的内容)",
                "6. 发布",
            ],
        }
