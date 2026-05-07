"""
brand_redlines.py - 品牌红线清单(所有对外内容必须通过的合规检查)
路径：agents/brand_redlines.py
版本：v2.3.7-part7
品牌把关人执法依据, 含DFA关键词+语义级安全检查.
"""
import json
import os
import re


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
    "敏感词检测": [
        {"id": "S1", "rule": "敏感词检测 — 自动DFA匹配,一票否决(>10命中或政治/色情/暴力类命中)", "reason": "内容安全红线,自动扫描,零容忍"},
    ],
    "语义安全红线": [
        {"id": "R1", "rule": "不得使用'保证100%获批''包过''绝对没问题'等夸大承诺表述", "reason": "乡村振兴项目无100%获批,夸大承诺=法律风险+信誉崩塌"},
        {"id": "R2", "rule": "涉及医疗/食品安全的内容必须标注'仅供参考,具体请咨询专业机构'", "reason": "无资质提供医疗/食安建议=法律红线"},
        {"id": "R3", "rule": "涉及投资/融资/理财建议必须标注'不构成投资建议,投资有风险'", "reason": "无牌照提供投资建议=被认定为非法金融活动"},
        {"id": "R4", "rule": "不得点名贬低/攻击特定政府部门、官员或审批流程", "reason": "合规风险,可能被认定为诽谤或寻衅滋事"},
        {"id": "R5", "rule": "不得包含未经授权的个人隐私数据(手机号、身份证号、银行卡号、具体住址)", "reason": "隐私泄露=严重法律后果+品牌自杀"},
    ],
}

# 触发一票否决的关键类别(命中任一=直接拦截)
CRITICAL_CATEGORIES = {"政治敏感", "色情内容", "暴力恐怖", "毒品管制"}


class DFAMatcher(object):
    """DFA敏感词匹配器。基于Trie树的单遍扫描,O(n)时间复杂度。

    用法:
        matcher = DFAMatcher()
        hits = matcher.search("这是一段测试文本")
        # hits: [(word, category, position), ...]
    """

    def __init__(self, word_file=None):
        """构建DFA匹配器。word_file为None时使用默认词库路径。"""
        self.trie = {}  # 根节点,每个节点: {char: child_node}, 叶子有 'END': category_name
        self.empty = True
        if word_file is None:
            word_file = os.path.join(
                os.path.dirname(os.path.dirname(os.path.abspath(__file__))),
                "data", "safety", "sensitive_words.txt"
            )
        self.word_file = word_file
        self._loaded = False
        if os.path.exists(word_file):
            self._load_and_build()

    def _load_and_build(self):
        """从文件加载敏感词并构建Trie。"""
        try:
            with open(self.word_file, "r", encoding="utf-8") as f:
                lines = f.readlines()
        except (IOError, UnicodeDecodeError):
            return

        current_category = "未分类"
        word_count = 0
        for line in lines:
            line = line.strip()
            if not line:
                continue
            if line.startswith("#"):
                # 提取类别名: "# 1. 政治敏感" -> "政治敏感"
                if line.startswith("# ") and "." in line[:12]:
                    parts = line.split(".", 1)
                    if len(parts) == 2:
                        name_with_desc = parts[1].strip()
                        # 去掉 em-dash 后的描述文本
                        for dash in ("—", "―", " —", " ―"):
                            if dash in name_with_desc:
                                current_category = name_with_desc.split(dash, 1)[0].strip()
                                break
                        else:
                            current_category = name_with_desc
                continue
            # 敏感词行
            self._add_word(line, current_category)
            word_count += 1
        if word_count > 0:
            self.empty = False
            self._loaded = True

    def _add_word(self, word, category):
        """向Trie中添加一个敏感词和其类别。"""
        node = self.trie
        for ch in word:
            if ch not in node:
                node[ch] = {}
            node = node[ch]
        # 标记词尾,存储类别(一个词可能属于多个类别,用列表)
        if "END" not in node:
            node["END"] = []
        node["END"].append(category)

    def search(self, text):
        """单遍扫描,返回所有命中: [(word, category, position), ...]。

        算法: 维护所有活跃的Trie路径,每读一个字符:
        1) 从根节点出发,建立从此字符开始的新路径
        2) 推进上一轮建立的路径(不含本轮新建),命中词尾则记录
        时间复杂度: O(n * W), n=文本长度, W=最大活跃路径数(上限300)
        """
        if self.empty or not isinstance(text, str):
            return []
        results = []
        walkers = []  # [(trie_node, start_pos), ...] 上一轮幸存路径
        for pos, ch in enumerate(text):
            new_starts = []  # 本轮新建路径,不在本轮推进
            if ch in self.trie:
                node = self.trie[ch]
                new_starts.append((node, pos))
                if "END" in node:
                    for cat in node["END"]:
                        results.append((text[pos:pos + 1], cat, pos))
            # 推进上一轮路径(不含本轮新建)
            survivors = []
            for node, start in walkers:
                if ch in node:
                    node = node[ch]
                    survivors.append((node, start))
                    if "END" in node:
                        for cat in node["END"]:
                            results.append((text[start:pos + 1], cat, start))
            walkers = survivors + new_starts
        return results

    def is_loaded(self):
        """词库是否成功加载。"""
        return self._loaded


class BrandRedlineChecker(object):
    """品牌红线检查器。一票否决,不留情面。集成了DFA敏感词自动匹配。"""

    def __init__(self, dfamatcher=None):
        self.redlines = REDLINES
        if dfamatcher is None:
            dfamatcher = DFAMatcher()
        self.dfamatcher = dfamatcher

    def check_content(self, content_text, content_type="article"):
        """检查一段内容是否触犯红线。返回 {passed: bool, violations: [], warnings: []}"""
        violations = []
        warnings = []

        # A. 先跑DFA敏感词检测(Rule S1 — 自动、零成本)
        dfa_result = self.sensitive_word_check(content_text)
        if dfa_result["blocked"]:
            violations.append({
                "category": "敏感词检测",
                "rule_id": "S1",
                "rule": "敏感词检测 — 自动DFA匹配,一票否决",
                "reason": dfa_result["block_reason"],
                "severity": "BLOCK",
                "detail": {
                    "total_hits": dfa_result["total_hits"],
                    "critical_hits": dfa_result["critical_hits"],
                    "samples": dfa_result["samples"],
                },
            })
        elif dfa_result["level"] == "warning":
            warnings.append({
                "category": "敏感词检测",
                "rule_id": "S1",
                "rule": "敏感词检测 — DFA匹配预警",
                "reason": "命中%d个敏感词(%d个为关键类别),建议人工复核" % (
                    dfa_result["total_hits"], len(dfa_result["critical_hits"])
                ),
                "detail": {
                    "total_hits": dfa_result["total_hits"],
                    "critical_hits": dfa_result["critical_hits"],
                    "samples": dfa_result["samples"],
                },
            })

        # B. 语义级安全检查(R1-R5): 超越关键词的意图分析
        semantic_result = self.semantic_check(content_text)
        if semantic_result.get("violations"):
            violations.extend(semantic_result["violations"])
        if semantic_result.get("warnings"):
            warnings.extend(semantic_result["warnings"])

        # C. 跑原有18条+新增5条规则关键词检查
        for category, rules in REDLINES.items():
            if category in ("敏感词检测", "语义安全红线"):
                continue  # S1已由DFA处理, R1-R5已由semantic_check处理
            for rule in rules:
                triggered = self._check_rule(content_text, rule)
                if triggered:
                    violations.append({
                        "category": category,
                        "rule_id": rule["id"],
                        "rule": rule["rule"],
                        "reason": rule["reason"],
                        "severity": "BLOCK",
                    })

        passed = len(violations) == 0
        return {
            "passed": passed,
            "violations": violations,
            "warnings": warnings,
            "content_type": content_type,
            "checked_at": __import__('datetime').datetime.now().isoformat(),
            "verdict": "APPROVED" if passed else "REJECTED - 必须修改后重新提交",
        }

    def sensitive_word_check(self, text):
        """DFA敏感词检测,三级评分(无AI调用,完全确定性)。

        Returns:
            {
                "level": "safe" | "warning" | "blocked",
                "total_hits": int,
                "critical_hits": [(word, category, position), ...],
                "all_hits": [...],
                "blocked": bool,
                "block_reason": str or None,
                "samples": [...],  # 最多前10条供展示
            }
        """
        hits = self.dfamatcher.search(text)
        if not hits:
            return {
                "level": "safe", "total_hits": 0,
                "critical_hits": [], "all_hits": [],
                "blocked": False, "block_reason": None,
                "samples": [],
            }

        critical_hits = [
            (w, c, p) for w, c, p in hits
            if c in CRITICAL_CATEGORIES
        ]
        total = len(hits)

        # 三级判定逻辑
        if critical_hits:
            level = "blocked"
            blocked = True
            block_reason = "命中关键敏感类别(%s),共%d条" % (
                ", ".join(sorted(set(c for _, c, _ in critical_hits))),
                len(critical_hits),
            )
        elif total > 10:
            level = "blocked"
            blocked = True
            block_reason = "敏感词命中过多(%d个),疑似恶意内容" % total
        elif total >= 3:
            level = "warning"
            blocked = False
            block_reason = None
        else:
            level = "safe"
            blocked = False
            block_reason = None

        return {
            "level": level,
            "total_hits": total,
            "critical_hits": critical_hits,
            "all_hits": hits,
            "blocked": blocked,
            "block_reason": block_reason,
            "samples": hits[:10],
        }

    def _check_rule(self, content, rule):
        """检查单条规则(简化版关键词匹配,完整版应由AI执行)"""
        rule_id = rule["id"]
        content_lower = content.lower() if isinstance(content, str) else ""

        triggers = {
            "L1": ["补偿标准", "征收补偿", "拆迁补偿"],
            "L2": ["民族", "宗教"],
            "L3": [],
            "L4": ["保证获批", "包过", "100%通过"],
            "F1": [],
            "F2": [],
            "B1": [],
            "B2": ["最好", "第一", "唯一", "100%"],
            "B3": [],
            # 语义安全红线关键词触发
            "R1": ["保证100%", "包过", "绝对没问题", "肯定能批", "一定通过",
                   "100%获批", "保证获批", "必定成功", "铁定能行"],
            "R2": ["治疗", "治愈", "特效药", "偏方治病", "药到病除",
                   "食品安全不达标", "吃了没事", "不用检测"],
            "R3": ["稳赚", "保本", "高收益", "无风险投资", "躺着赚钱",
                   "内部消息", "必涨", "荐股", "跟投"],
            "R4": [],   # 部门点名由semantic_check处理
            "R5": [],   # 隐私数据由semantic_check处理
        }

        for keyword in triggers.get(rule_id, []):
            if keyword in content_lower:
                return True
        return False

    def semantic_check(self, text):
        """语义级安全检查: 超越关键词, 检测有害INTENT。

        五维度模式分析:
          R4: 部门机构点名 — 识别涉及"XX局/XX厅/XX部"的批评性表述
          R5: 隐私数据泄露 — 识别手机号/身份证/银行卡/地址等PII模式
          R1: 夸大承诺 — 识别"100%保证/绝对/肯定"等确定性承诺上下文
          R2: 医疗食安建议 — 识别医疗/食品安全诊断性表述
          R3: 投资建议 — 识别推荐/建议具体金融产品的表述

        返回: {passed: bool, violations: [], warnings: []}
        """
        violations = []
        warnings = []

        # --- R4: 部门点名检测 ---
        # 匹配中国政府机构常见命名模式
        gov_patterns = [
            r'(省|市|县|区|镇|乡)(.{1,6})(局|厅|部|委|办|处)',
            r'(自然资源局|农业农村局|发改委|财政局|住建局|生态环境局'
            r'|水利局|交通局|林业局|市场监管局)',
        ]
        gov_mentions = []
        for pat in gov_patterns:
            gov_mentions.extend(re.findall(pat, text))
        if gov_mentions:
            # 检查附近是否有批评/贬低性词汇
            neg_window = 50
            for m in re.finditer(
                r'(腐败|不作为|乱作为|吃拿卡要|刁难|拖延|推诿'
                r'|效率低|态度差|官僚|黑幕|暗箱|关系户|走后门'
                r'|贪污|受贿|徇私|滥用|违规审批|故意卡)',
                text,
            ):
                start = max(0, m.start() - neg_window)
                end = min(len(text), m.end() + neg_window)
                near_context = text[start:end]
                for pat in gov_patterns:
                    if re.search(pat, near_context):
                        violations.append({
                            "category": "语义安全红线",
                            "rule_id": "R4",
                            "rule": self.redlines["语义安全红线"][3]["rule"],
                            "reason": self.redlines["语义安全红线"][3]["reason"],
                            "severity": "BLOCK",
                            "detail": {
                                "matched_term": m.group(0),
                                "context": near_context[:100],
                            },
                        })
                        break

        # --- R5: 隐私数据(PII)检测 ---
        pii_patterns = {
            "phone": (r'1[3-9]\d{9}', "手机号"),
            "id_card": (r'\d{6}(?:19|20)\d{2}(?:0[1-9]|1[0-2])'
                        r'(?:0[1-9]|[12]\d|3[01])\d{3}[\dXx]', "身份证号"),
            "bank_card": (r'(?:62\d{14,17}|60\d{14,17}|'
                          r'[45]\d{15,18})', "银行卡号"),
        }
        for key, (pat, label) in pii_patterns.items():
            pii_matches = [m.group(0) for m in re.finditer(pat, text)]
            if pii_matches:
                violations.append({
                    "category": "语义安全红线",
                    "rule_id": "R5",
                    "rule": self.redlines["语义安全红线"][4]["rule"],
                    "reason": self.redlines["语义安全红线"][4]["reason"],
                    "severity": "BLOCK",
                    "detail": {
                        "pii_type": label,
                        "count": len(pii_matches),
                        "samples": [m[:3] + "****" + m[-2:]
                                    for m in pii_matches[:3]],
                    },
                })

        # --- R1: 夸大承诺语义检测 ---
        # 检测"保证/绝对/100%" + 审批/通过/成功 等结果词
        r1_pairs = re.findall(
            r'(保证|绝对|100%|肯定|必定|铁定).{0,20}'
            r'(获批|通过|成功|能行|没问题|能批)',
            text,
        )
        if r1_pairs:
            violations.append({
                "category": "语义安全红线",
                "rule_id": "R1",
                "rule": self.redlines["语义安全红线"][0]["rule"],
                "reason": self.redlines["语义安全红线"][0]["reason"],
                "severity": "BLOCK",
                "detail": {
                    "pattern_type": "guarantee_result_pair",
                    "matches": [m[0] + "..." + m[1] for m in r1_pairs[:3]],
                },
            })

        # --- R2: 医疗/食安声明检测 ---
        r2_matches = re.findall(
            r'(治好|治愈|治疗|诊断|这药|这个偏方|这个方子).{0,30}'
            r'(保证|肯定|一定|绝对|没问题|放心)',
            text,
        )
        if r2_matches:
            # 检查是否有免责声明
            has_disclaimer = bool(re.search(
                r'(仅供参考|请咨询|请遵医嘱|请咨询医生'
                r'|具体请咨询|不构成医疗建议)',
                text,
            ))
            if not has_disclaimer:
                violations.append({
                    "category": "语义安全红线",
                    "rule_id": "R2",
                    "rule": self.redlines["语义安全红线"][1]["rule"],
                    "reason": self.redlines["语义安全红线"][1]["reason"],
                    "severity": "BLOCK",
                    "detail": {
                        "has_disclaimer": False,
                        "samples": list(r2_matches[:3]),
                    },
                })

        # --- R3: 投资建议检测 ---
        r3_phrases = re.findall(
            r'(推荐.{0,8}(股票|基金|投资|理财|币|项目))'
            r'|(这个(项目|投资|股票).{0,8}(肯定|绝对|一定|稳))'
            r'|((买入|卖出|持有|满仓|空仓|抄底|逃顶))',
            text,
        )
        # 展平元组
        r3_flat = [m for t in r3_phrases for m in t if m]
        if r3_flat:
            has_fin_disclaimer = bool(re.search(
                r'(不构成投资建议|投资有风险|理财有风险'
                r'|入市需谨慎|仅供参考.{0,5}投资)',
                text,
            ))
            if not has_fin_disclaimer:
                violations.append({
                    "category": "语义安全红线",
                    "rule_id": "R3",
                    "rule": self.redlines["语义安全红线"][2]["rule"],
                    "reason": self.redlines["语义安全红线"][2]["reason"],
                    "severity": "BLOCK",
                    "detail": {
                        "has_disclaimer": False,
                        "samples": r3_flat[:3],
                    },
                })

        passed = len(violations) == 0
        return {
            "passed": passed,
            "violations": violations,
            "warnings": warnings,
        }

    def get_redline_document(self):
        """获取完整的红线文档(供品牌把关人使用)"""
        return {
            "title": "乡村振兴知识集团 — 品牌红线清单",
            "version": "v2.0",
            "principle": "一票否决制。任何一条红线触发=内容不得发布。宁可不发,不可发坏。含DFA敏感词自动检测(Rule 19)。",
            "categories": REDLINES,
            "approval_flow": [
                "1. 内容创作者自检(对照红线清单)",
                "2. DFA敏感词自动扫描(零成本秒级,无AI)",
                "3. AI初审(品牌把关人Agent自动扫描)",
                "4. 模拟客户阅读(至少3个Agent评分>=4)",
                "5. 品牌把关人终审(人工/AI)",
                "6. 老唐终审(涉及老唐观点/经验的内容)",
                "7. 发布",
            ],
        }
