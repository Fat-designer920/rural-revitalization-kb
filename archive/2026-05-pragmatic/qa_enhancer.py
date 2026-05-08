"""
qa_enhancer.py - QA增强模块(ThinkRAG + MiniRAG + FlashRAG 思路集成)
路径：scripts/qa_enhancer.py
版本：v2.3.7-part7

为现有 QaAssistantEngine 提供插入式增强: 查询增强→重排优化→质量评分→反馈闭环。
不打乱现有管道, 每个增强点独立开关, 可单独启用/禁用。
"""
import json
import re
import time
from datetime import datetime, timedelta
from typing import Dict, List, Optional, Tuple, Any


# ==============================================================
# 1. Query Enhancement (借鉴 ThinkRAG: 中文优化查询理解)
#    ThinkRAG uses bge-large-zh-v1.5 + Spacy Chinese tokenizer.
#    Landed: jieba 中文分词 + 领域同义词扩展 + 查询类型检测。
# ==============================================================

# 查询类型模式特征 (ThinkRAG key insight: pre-classify queries to
# bias retrieval toward the right document type, rather than treating
# every query as a generic keyword search.)
_QUERY_TYPE_PATTERNS = {
    'policy_lookup': [
        r'政策.*规定|文件.*条款|.*政策.*依据|哪.*文件|什么.*政策',
        r'标准|规范|规程|条例|办法|通知|意见|方案',
        r'指标|目标|任务|考核|约束',
    ],
    'operational_howto': [
        r'怎么[做搞弄办]|如何.*操作|流程|步骤|方法|技巧|经验',
        r'怎么申报|怎么申请|怎么审批|怎么验收',
        r'避坑|注意|陷阱|教训|踩坑',
    ],
    'compliance_check': [
        r'合规|合法|违规|红线|禁止|不允许|可以吗|行不行',
        r'符合.*要求|满足.*条件|达到.*标准',
        r'违法|责任|处罚|后果|风险',
    ],
    'case_study': [
        r'案例|实例|成功.*经验|失败.*教训|哪个.*案例',
        r'某.*项目|某.*县|某.*镇|哪个[乡村]',
        r'典型|标杆|示范|试点',
    ],
    'funding_finance': [
        r'钱|资金|融资|贷款|补贴|补助|拨款|专项债|债券',
        r'预算|费用|成本|多少钱|金额|额度|利率',
    ],
}


def detect_query_type(query: str) -> Tuple[str, float]:
    """检测查询类型 + 置信度.

    借鉴 ThinkRAG: 查询意图分类改善检索精度。
    ThinkRAG 用 bge-reranker 做分类; 我们用领域正则模式实现零成本分类。

    返回 (type_label, confidence 0-1)。
    type_label: policy_lookup / operational_howto / compliance_check /
                case_study / funding_finance / general
    """
    if not query or not str(query).strip():
        return 'general', 1.0
    q = str(query).strip()
    scores = {}
    for qtype, pattern_list in _QUERY_TYPE_PATTERNS.items():
        hits = 0
        for pat in pattern_list:
            if re.search(pat, q):
                hits += 1
        if hits > 0:
            scores[qtype] = min(1.0, hits / max(len(pattern_list), 1))
    if not scores:
        return 'general', 1.0
    best = max(scores, key=scores.get)
    return best, scores[best]


# 查询扩展 (扩充 npu_engine._QUERY_SYNONYMS 的功能，
# 增加领域词典的查询-侧增强: 从查询中检测关键词，返回检索权重偏置)
# 借鉴 MiniRAG: 用轻量图索引标注文档类型 + 查询侧类型偏置改善检索。

# 查询内容日志关键词映射(用于事后审计)
_CONTENT_SIGNAL_PATTERNS = {
    'reinforcement_heavy': r'最重要|最关键|最核心|务必|必须|严格|强制|红线|底线',
    'novice_oriented': r'新手|入门|初学|第一步|基础|小白|不懂|请问|想问',
    'expert_oriented': r'深化|进阶|高级|复杂|精细|精细化管理|创新模式',
}


def characterise_query(query: str) -> Dict[str, Any]:
    """查询特征画像: 类型+信号+建议检索偏置.

    借鉴 FlashRAG: 查询分析模块(query_analysis)提供检索策略偏置。
    FlashRAG 提供完整的 RAG 管道框架, 含 query_analysis/judger/retriever/
    generator 标准接口(https://github.com/RUC-NLPIR/FlashRAG)。

    返回可传给检索层的查询画像 dict。
    """
    qtype, qtype_conf = detect_query_type(query)
    profile = {
        'qtype': qtype,
        'qtype_confidence': round(qtype_conf, 2),
        'signals': [],
        'retrieval_bias': {},
    }
    # 内容信号检测
    for sig_name, pat in _CONTENT_SIGNAL_PATTERNS.items():
        if re.search(pat, query):
            profile['signals'].append(sig_name)
    # 检索偏置: 按查询类型设置类别权重
    _QTYPE_CATEGORY_BIAS = {
        'policy_lookup': {'政策性文件': 1.5, '政策解读': 1.3,
                          '标准规范': 1.4, '通知公告': 1.2},
        'operational_howto': {'实操指南': 1.6, '案例研究': 1.3,
                              '经验分享': 1.4, '工具模板': 1.2},
        'compliance_check': {'政策解读': 1.5, '合规管控': 1.7,
                             '标准规范': 1.3, '风险预警': 1.4},
        'case_study': {'案例研究': 1.8, '示范试点': 1.5,
                       '经验分享': 1.3, '数据报告': 1.2},
        'funding_finance': {'资金管理': 1.6, '政策性文件': 1.4,
                            '申报指南': 1.5, '案例研究': 1.2},
    }
    profile['retrieval_bias'] = _QTYPE_CATEGORY_BIAS.get(qtype, {})
    return profile


# ==============================================================
# 2. Retrieval Re-ranking (借鉴 FlashRAG: 完整管道工具集)
#    FlashRAG 提供 re-ranker 抽象接口 + 多种实现。
#    Landed: 启发式多因子打分(零 AI 调用)替代 cross-encoder 模型重排。
#    对 NPU 召回的 top-50 做二次精排, 不调用外部模型。
# ==============================================================

# 来源权威分级(与 qa_assistant._AUTHORITY_BOOST 对齐)
_AUTHORITY_SCORE = {
    'official': 1.0,
    'authoritative': 0.7,
    'firsthand': 0.45,
    'informal': 0.2,
}


def heuristic_rerank(
    candidates: List[Dict],
    query: str,
    query_keywords: Optional[List[str]] = None,
    query_profile: Optional[Dict] = None,
    top_k: int = 10,
) -> List[Dict]:
    """多因子启发式重排(零AI成本).

    借鉴 FlashRAG re-ranker: 在 RAG 管道中对检索结果做二次精排。
    FlashRAG 支持 bge-reranker/cross-encoder 等模型重排;
    我们用轻量多因子打分实现零成本重排。

    评分维度:
      - keyword_overlap: 查询关键词在 KP 标题+摘要中的命中率
      - category_match: KP 类别与查询类型偏置的匹配度
      - recency: 新鲜度(最近更新的知识衰减慢)
      - authority: 来源权威性
      - nps: NPU 语义相似度(如果有 _npu_score)

    返回重排后的 candidates, 含 _enhancer_score 字段。
    """
    if not candidates:
        return []
    if not query_keywords:
        query_keywords = _extract_keywords(query)

    now = datetime.now()
    for kp in candidates:
        score = 0.0

        # 因子1: keyword_overlap (0-1 归一化)
        kw_overlap = _calc_keyword_overlap(kp, query_keywords)
        score += kw_overlap * 0.25

        # 因子2: category_match (查询类型偏置, 0-1)
        cat_bonus = 0.0
        if query_profile and query_profile.get('retrieval_bias'):
            raw_cat = str(kp.get('category') or '')
            sub_cat = str(kp.get('subcategory') or '')
            bias_map = query_profile['retrieval_bias']
            for cat_pattern, weight in bias_map.items():
                if cat_pattern in raw_cat or cat_pattern in sub_cat:
                    cat_bonus = max(cat_bonus, weight / 2.0)
        score += cat_bonus * 0.15

        # 因子3: recency (基于 freshness_status 和 last_used_at)
        recency = 0.5
        freshness = str(kp.get('premium_freshness_status') or '')
        if freshness == 'fresh':
            recency = 1.0
        elif freshness == 'stale':
            recency = 0.3
        last_used = kp.get('last_used_at')
        if last_used:
            try:
                if isinstance(last_used, str):
                    lu = datetime.fromisoformat(last_used.replace('Z', ''))
                    days_since = (now - lu).days
                    if days_since < 30:
                        recency = max(recency, 0.9)
                    elif days_since < 90:
                        recency = max(recency, 0.6)
            except (ValueError, TypeError):
                pass
        score += recency * 0.15

        # 因子4: authority
        auth_raw = str(kp.get('source_authority') or '')
        auth_score = _AUTHORITY_SCORE.get(auth_raw, 0.3)
        score += auth_score * 0.15

        # 因子5: NPU 语义相似度(如果有的话)
        npu_s = kp.get('_npu_score')
        if npu_s is not None:
            try:
                score += float(npu_s) * 0.30
            except (ValueError, TypeError):
                score += 0.0
        else:
            # 无 NPU 分数时, keyword_overlap 权重提升
            score += kw_overlap * 0.20

        kp['_enhancer_score'] = round(score, 4)

    candidates.sort(key=lambda x: x.get('_enhancer_score', 0), reverse=True)
    return candidates[:top_k]


def _extract_keywords(text: str) -> List[str]:
    """简易关键词提取: 2+ 字中文词组."""
    if not text:
        return []
    tokens = []
    # 先找中文连续片段
    cn_segs = re.findall(r'[一-鿿]{2,}', str(text))
    # 再补充数字+单位组合
    num_units = re.findall(r'\d+[万亿千百十]?[元吨亩平方米公里]?', str(text))
    tokens = cn_segs + num_units
    # 去重 + 限长
    seen = set()
    out = []
    for t in tokens:
        if t not in seen and 2 <= len(t) <= 15:
            seen.add(t)
            out.append(t)
    return out[:20]


def _calc_keyword_overlap(kp: Dict, query_keywords: List[str]) -> float:
    """计算 KP 标题 + 摘要的关键词命中率."""
    if not query_keywords:
        return 0.0
    title = str(kp.get('title') or '')
    excerpt = str(kp.get('original_excerpt') or '')
    combined = title + ' ' + excerpt
    hits = sum(1 for kw in query_keywords if kw in combined)
    return min(1.0, hits / max(len(query_keywords), 1))


# ==============================================================
# 3. Answer Quality Scoring (借鉴 MiniRAG: 轻量质量反馈闭环)
#    MiniRAG 用图索引存储检索质量评分, 驱动持续改进。
#    Landed: 4 维度启发式评分 + 可追踪的分数历史。
# ==============================================================

def score_answer_quality(
    answer: Optional[Dict],
    query: str,
    retrieved_kps: List[Dict],
    source: str = 'unknown',
) -> Dict[str, Any]:
    """4 维度答案质量评分(启发式规则, 零 AI 成本).

    借鉴 MiniRAG: 在 RAG 管道中嵌入轻量质量度量, 将评分存储在图索引中
    用于追踪改进趋势。MiniRAG 的核心理念是"存储越少、索引越精", 质量评分
    作为索引修剪依据(低质量 KP 降权)。

    4 维度:
      - source_grounding (0-5): 答案是否有据可查
      - completeness (0-5): 回答是否涵盖查询的主要方面
      - actionability (0-5): 操盘手看完能否直接行动
      - specificity (0-5): 是否含具体数据/地名/条款号

    返回评分 dict 含各维度分数 + overall + 改进建议。
    """
    default_scores = {
        'source_grounding': 1, 'completeness': 1,
        'actionability': 1, 'specificity': 1, 'overall': 1.0,
        'flags': [], 'suggestions': [],
    }
    if not answer or not isinstance(answer, dict):
        default_scores['flags'].append('empty_answer')
        default_scores['suggestions'].append('检查生成链是否全部降级到L3')
        return default_scores

    direct = str(answer.get('direct_answer') or '')
    ev_ids = answer.get('evidence_kp_ids') or []
    fups = answer.get('followup_questions') or []
    gap = str(answer.get('coverage_gap') or '')
    policy_basis = answer.get('policy_basis') or []

    # ---- source_grounding (0-5) ----
    grounding = 1
    if ev_ids:
        grounding = min(5, 2 + min(len(ev_ids), 3))
    if policy_basis and len(policy_basis) >= 2:
        grounding = min(5, grounding + 1)
    if source == 'rule_fallback':
        grounding = max(1, grounding - 2)

    # ---- completeness (0-5) ----
    completeness = 1
    if len(direct) >= 80:
        completeness += 1
    if len(direct) >= 300:
        completeness += 1
    if fups and len(fups) >= 2:
        completeness += 1
    if '无法充分覆盖' in gap or '未检索到' in gap:
        completeness = max(1, completeness - 2)
    elif gap:
        completeness = max(1, completeness - 1)
    completeness = min(5, max(1, completeness))

    # ---- actionability (0-5) ----
    actionability = 1
    if re.search(r'\d+[万亿千百]?元', direct):
        actionability += 1
    if re.search(r'[一-鿿]{2,}[市县乡村镇]', direct):
        actionability += 1
    if re.search(r'步骤|流程|方法|路径|第一步|第二步', direct):
        actionability += 1
    if len(direct) >= 150:
        actionability += 1
    actionability = min(5, max(1, actionability))

    # ---- specificity (0-5) ----
    specificity = 1
    # 条款号检测
    if re.search(r'第[一二三四五六七八九十\d]+[条款章节]', direct):
        specificity += 1
    # 百分比/具体数字
    if re.search(r'\d+[\.％%]', direct):
        specificity += 1
    # 文件名或政策名
    if re.search(r'《[^》]+》', direct) or re.search(r'[\d]{4}[年]', direct):
        specificity += 1
    # 机构名
    if re.search(r'(自然资源|农业农村|住建|发改|财政|生态环境)部|厅|局', direct):
        specificity += 1
    specificity = min(5, max(1, specificity))

    overall = round((grounding + completeness + actionability + specificity) / 4, 1)

    # 诊断 flags + 建议
    flags = []
    suggestions = []
    if grounding <= 2:
        flags.append('low_grounding')
        suggestions.append('补充引用来源: 检索到的KP中选最相关的3条作为证据写入evidence_kp_ids')
    if completeness <= 2:
        flags.append('low_completeness')
        suggestions.append('覆盖不足: 检查知识库是否缺少该主题的精品KP, 或查询是否需要拆分')
    if actionability <= 2:
        flags.append('low_actionability')
        suggestions.append('增强可操作性: 补充具体步骤、数据、地名或金额')
    if specificity <= 2:
        flags.append('low_specificity')
        suggestions.append('增强具体性: 引用具体政策文件名、条款号、百分比、机构名')

    return {
        'source_grounding': grounding,
        'completeness': completeness,
        'actionability': actionability,
        'specificity': specificity,
        'overall': overall,
        'flags': flags,
        'suggestions': suggestions,
        'auto_generated': True,
        'scored_at': datetime.now().isoformat(),
    }


# ==============================================================
# 4. Feedback Loop Integration (借鉴 MiniRAG: 质量驱动知识缺口检测)
#    MiniRAG 将低质量检索结果反馈到索引层, 触发重新索引或知识补充。
#    Landed: 低分答案 → 缺口记录 → knowledge_gap_analyzer 对接。
# ==============================================================

def detect_knowledge_gaps_from_feedback(
    db: Any,
    quality_scores: Dict,
    query: str,
    history_id: int = 0,
    retrieved_ids: Optional[List[int]] = None,
) -> List[Dict]:
    """从 QA 反馈中检测知识缺口(对接 knowledge_gap_analyzer).

    借鉴 MiniRAG: 低质量检索结果触发图索引修复和知识补充。
    MiniRAG 在检索评分 < 阈值时自动标记知识缺口, 并将缺口记录在索引层
    供后续爬虫定向抓取。

    触发条件:
      - overall < 2.5 或 source_grounding < 2 → 知识严重不足
      - 检索命中 < 3 条有效 KP → 覆盖不足

    返回缺口列表, 可直接传给 knowledge_gap_analyzer 或写日志。
    """
    gaps = []
    overall = quality_scores.get('overall', 0) if quality_scores else 0
    grounding = quality_scores.get('source_grounding', 0) if quality_scores else 0
    n_retrieved = len(retrieved_ids or [])

    if overall < 2.5 or grounding < 2:
        gaps.append({
            'severity': 'critical' if overall < 1.5 or n_retrieved == 0 else 'high',
            'query': query[:300],
            'qa_history_id': history_id,
            'overall_score': overall,
            'source_grounding': grounding,
            'n_retrieved': n_retrieved,
            'gap_type': 'severe_knowledge_gap' if n_retrieved < 3 else 'quality_gap',
            'suggested_action':
                'P0紧急喂料: 需要补充与查询主题直接相关的政策原文和实操案例',
            'detected_at': datetime.now().isoformat(),
        })
    elif overall < 3.0:
        # 中等缺口: 知识存在但不够精深
        flags = quality_scores.get('flags', []) if quality_scores else []
        gaps.append({
            'severity': 'medium',
            'query': query[:300],
            'qa_history_id': history_id,
            'overall_score': overall,
            'flags': flags,
            'n_retrieved': n_retrieved,
            'gap_type': 'knowledge_depth_insufficient',
            'suggested_action':
                '增加精品KP: 现有知识可回答但质量不足, 建议补充更深度的实操案例',
            'detected_at': datetime.now().isoformat(),
        })

    # 记录到操作日志(如果 db 可用)
    if gaps and db is not None:
        for gap in gaps:
            try:
                db.log_operation_event(
                    event_type='knowledge_gap_detected',
                    module='qa_enhancer',
                    severity='warning' if gap['severity'] != 'critical' else 'error',
                    payload=gap,
                )
            except Exception:
                pass

    return gaps


def get_recent_low_score_queries(
    db: Any,
    days: int = 7,
    min_overall: float = 2.5,
    limit: int = 20,
) -> List[Dict]:
    """获取近期低分答案列表(用于追踪改进趋势).

    解析 qa_feedback 中 comment 字段(JSON)里的 overall 分数,
    筛选低于阈值的记录。

    借鉴 MiniRAG 的存储策略: 用极少的元数据(分数摘要)做趋势追踪,
    而不是保留完整答案(节省 25% 存储)。
    """
    if not db:
        return []
    try:
        cutoff = (datetime.now() - timedelta(days=days)).strftime('%Y-%m-%d')
        results = []
        conn = db.get_connection()
        c = conn.cursor()
        c.execute("""
            SELECT qh.id, qh.query, qh.source, qh.created_at,
                   qf.comment
            FROM qa_history qh
            JOIN qa_feedback qf ON qf.qa_history_id = qh.id
            WHERE qh.created_at >= ?
              AND qf.feedback_type = 'comment'
              AND qf.comment != ''
            ORDER BY qh.created_at DESC
            LIMIT ?
        """, (cutoff, limit * 3))
        for row in c.fetchall():
            r = dict(row)
            try:
                comment_data = json.loads(r.get('comment') or '{}')
                overall = comment_data.get('overall')
                if overall is not None and float(overall) < min_overall:
                    results.append({
                        'history_id': r['id'],
                        'query': (r.get('query') or '')[:200],
                        'source': r.get('source', ''),
                        'overall': float(overall),
                        'created_at': r.get('created_at', ''),
                    })
            except (json.JSONDecodeError, ValueError, TypeError):
                continue
        conn.close()
        results.sort(key=lambda x: x.get('overall', 0))
        return results[:limit]
    except Exception:
        return []


# ==============================================================
# 5. 集成工具: 一站式增强包装器
# ==============================================================

class QaEnhancer:
    """QA 增强器: 为现有 QaAssistantEngine 提供插入式增强.

    设计原则(借鉴三个 RAG 项目):
      - ThinkRAG: 中文优先, 查询侧类型检测 + 扩展(不依赖大模型)
      - MiniRAG:  极致轻量, 质量评分驱动知识补充闭环(25% 存储理念)
      - FlashRAG: 模块化管道, 每个增强点独立可开关(完整工具集)

    使用方式:
        from scripts.qa_enhancer import QaEnhancer
        enhancer = QaEnhancer(db=db)
        # 增强查询
        profile = enhancer.enhance_query(query)
        # 重排检索结果
        reranked = enhancer.rerank(candidates, query, profile)
        # 评分答案质量
        scores = enhancer.score_answer(answer, query, reranked, source)
        # 检测知识缺口
        gaps = enhancer.check_gaps(scores, query, history_id, retrieved_ids)
    """

    def __init__(self, db: Any = None, enable_rerank: bool = True,
                 enable_gap_detection: bool = True):
        self.db = db
        self.enable_rerank = enable_rerank
        self.enable_gap_detection = enable_gap_detection
        self._stats = {
            'queries_enhanced': 0,
            'reranks_done': 0,
            'scores_computed': 0,
            'gaps_detected': 0,
            'created_at': datetime.now().isoformat(),
        }

    def enhance_query(self, query: str) -> Dict:
        """一站式查询增强: 类型检测 + 特征画像."""
        self._stats['queries_enhanced'] += 1
        qtype, qtype_conf = detect_query_type(query)
        profile = characterise_query(query)
        return {
            **profile,
            'query_length': len(query),
            'has_numbers': bool(re.search(r'\d', query)),
            'enhanced_at': datetime.now().isoformat(),
        }

    def rerank(self, candidates: List[Dict], query: str,
               query_profile: Optional[Dict] = None,
               top_k: int = 10) -> List[Dict]:
        """增强重排: 多因子打分 + 类型偏置."""
        if not self.enable_rerank:
            return candidates[:top_k]
        self._stats['reranks_done'] += 1
        keywords = _extract_keywords(query)
        return heuristic_rerank(
            candidates, query, query_keywords=keywords,
            query_profile=query_profile, top_k=top_k)

    def score_answer(self, answer: Optional[Dict], query: str,
                     retrieved_kps: List[Dict],
                     source: str = 'unknown') -> Dict:
        """增强质量评分: 4 维度启发式."""
        self._stats['scores_computed'] += 1
        return score_answer_quality(answer, query, retrieved_kps, source)

    def check_gaps(self, quality_scores: Dict, query: str,
                   history_id: int = 0,
                   retrieved_ids: Optional[List[int]] = None) -> List[Dict]:
        """检测知识缺口 + 写日志."""
        if not self.enable_gap_detection:
            return []
        gaps = detect_knowledge_gaps_from_feedback(
            self.db, quality_scores, query, history_id, retrieved_ids)
        self._stats['gaps_detected'] += len(gaps)
        return gaps

    def get_recent_low_scores(self, days: int = 7,
                              min_overall: float = 2.5,
                              limit: int = 20) -> List[Dict]:
        """查询近期低分记录."""
        return get_recent_low_score_queries(
            self.db, days=days, min_overall=min_overall, limit=limit)

    def get_stats(self) -> Dict:
        """获取增强器运行统计."""
        return dict(self._stats)
