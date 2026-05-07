"""
brand_redlines.py - 品牌红线清单(所有对外内容必须通过的合规检查)
路径：agents/brand_redlines.py
版本：v2.3.7-part6

品牌把关人的执法依据。所有对外发布内容(文章/视频/课程/图文)必须通过此清单。
一票否决制 — 任何一条红线触发=内容不得发布。
"""
import json
import os


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

        # B. 跑原有18条规则关键词检查
        for category, rules in REDLINES.items():
            if category == "敏感词检测":
                continue  # 已由DFA处理
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
        }

        for keyword in triggers.get(rule_id, []):
            if keyword in content_lower:
                return True
        return False

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
