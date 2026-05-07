"""
qa_assistant.py - 问答助手模块
路径：scripts/qa_assistant.py
版本：v2.3.7-part5
A2升级: NPU混合检索 + policy_basis来源追溯 + 低分I don't know + auto_score自动反馈
"""
import json
import re
import time
from typing import Optional, Callable, Dict, List, Any

try:
    from scripts.prompts.prompt_templates import (
        QA_RETRIEVAL_RANK_PROMPT,
        QA_ANSWER_GEN_PROMPT,
        QA_FOLLOWUP_GEN_PROMPT,
    )
except ImportError:
    from prompts.prompt_templates import (  # noqa: F401
        QA_RETRIEVAL_RANK_PROMPT,
        QA_ANSWER_GEN_PROMPT,
        QA_FOLLOWUP_GEN_PROMPT,
    )

try:
    from scripts.npu_engine import NPUEngine
except ImportError:
    NPUEngine = None  # type: ignore


QA_RETRIEVAL_LIMIT = 30          # 关键词召回上限(db 层 LIMIT)
QA_TOP_N_AFTER_RANK = 5          # V3 重排后取 Top N 喂生成
QA_RERANK_THRESHOLD = 6          # 候选 ≥ 此阈值才走 V3 重排,否则跳过省钱
QA_TIMEOUT_V3 = 60               # V3 单次调用超时
QA_TIMEOUT_R1 = 300              # R1 单次调用超时(立规则 15)
V3_TEMPERATURE = 0.3             # 与 premium_judge 一致

# composite_score 加权(决策冻结档案 §3 Step 3)
WEIGHT_PREMIUM = 50              # premium_client=1 OR premium_rfp=1 → +50
WEIGHT_ANNOTATION = 20           # has_annotation → +20
WEIGHT_QA_FACTOR = 5             # qa_score × 5(0-25)
_AUTHORITY_BOOST = {
    'official': 25,
    'authoritative': 18,
    'firsthand': 12,
    'informal': 5,
}

# 简易停用词(中文)
_STOP_WORDS = set([
    '的', '了', '和', '是', '在', '有', '也', '就', '都', '与', '及', '或',
    '我', '你', '他', '她', '它', '这', '那', '这个', '那个', '哪些', '什么',
    '怎么', '怎样', '如何', '为什么', '怎么办', '可以', '应该', '需要',
    '吗', '呢', '啊', '嘛', '一', '二', '三', '一些',
    '请问', '想问', '请', '麻烦', '帮我', '我想', '想要', '能否', '能不能',
    '?', '?', '、', '/',
])


def _parse_json_loose(text: str) -> Optional[Dict]:
    """容错 JSON 解析:剥离 ``` 包裹 + 提取第一个 {...} 块.

    本函数与 premium_judge._parse_json_loose 写法对齐.
    """
    if not text:
        return None
    s = text.strip()
    # 剥离 ```json 或 ``` 代码块
    m = re.search(r'```(?:json)?\s*([\s\S]*?)```', s)
    if m:
        s = m.group(1).strip()
    # 提取第一个完整 {...} 块
    first = s.find('{')
    last = s.rfind('}')
    if first >= 0 and last > first:
        s = s[first:last + 1]
    try:
        return json.loads(s)
    except (json.JSONDecodeError, ValueError):
        return None


def _tokenize_query(query: str) -> List[str]:
    """中文分词 + 停用词过滤.

    优先 jieba(精确模式),fallback 标点切.
    """
    if not query or not str(query).strip():
        return []
    q = str(query).strip()

    words: List[str]
    try:
        import jieba
        words = list(jieba.cut(q, cut_all=False))
    except ImportError:
        # fallback: 标点 + 空格切
        words = re.split(
            r'[\s,,;;。!?!?、/()()【】\[\]"\'""\u2018\u2019《》<>]+',
            q,
        )

    out: List[str] = []
    seen = set()
    for w in words:
        w = w.strip()
        if not w or w in _STOP_WORDS:
            continue
        # 单字过滤(纯数字保留)
        if len(w) < 2 and not w.isdigit():
            continue
        if w in seen:
            continue
        seen.add(w)
        out.append(w)
    return out


class QaAssistantEngine:
    """F055 问答主引擎,与 PremiumJudgeEngine 类结构对齐."""

    # NPU engine pool: reuse instance across calls to avoid repeated ONNX init
    _npu_engine_cache = None

    def __init__(
        self,
        db: Any,
        client: Any,
        progress_callback: Optional[Callable[[Dict], None]] = None,
        cancel_check: Optional[Callable[[], bool]] = None,
    ):
        self.db = db
        self.client = client
        # 立规则 21:headless 兜底
        self.progress_callback = progress_callback or (lambda x: None)
        self.cancel_check = cancel_check or (lambda: False)

        # 运行时统计
        self._ai_calls = 0
        self._cost = 0.0   # 本次问答累计成本(元)
        self._retrieval_ms = 0  # 检索耗时(ms)
        self._generation_ms = 0  # 生成耗时(ms)

    # ================================================================
    # 主入口
    # ================================================================
    def run_qa(self, query: str, mode: str = 'self',
                is_test_query: int = 0,
                model_pref: str = 'v3',
                friend_tag: Optional[str] = None) -> Dict:
        """单次问答完整流程.

        v2.3.3-mvp 新增参数:
          model_pref: 'v3' | 'r1'  主链模型偏好(自用 R1 时主链翻转)
          friend_tag: str|None     朋友身份(URL ?u=张三),仅 mode=friend 有意义

        返回 dict 字段见模块顶部 docstring.
        v2.3.3-mvp 新增返回字段: model_used = 'deepseek-chat' | 'deepseek-reasoner'
        """
        start_ts = time.time()

        # 输入校验
        if not query or not str(query).strip():
            return {
                "ok": False, "history_id": 0, "answer": None,
                "source": "rule_fallback", "latency_ms": 0,
                "retrieved_kp_ids": [], "canceled": False,
                "cost_estimate_cny": 0.0, "error": "empty query",
                "model_used": None,
            }
        query = str(query).strip()
        # mode 校验(立规则 5):未知 mode 一律落 self
        if mode not in ('self', 'friend'):
            mode = 'self'
        # model_pref 校验:未知值落 v3(自用默认 + 朋友模式由 api_server 强制)
        if model_pref not in ('v3', 'r1'):
            model_pref = 'v3'

        # 进度初始化
        self._emit_progress("tokenize", 0, "分词中")

        # ---- Stage 1: tokenize ----
        if self._is_canceled():
            return self._canceled_result(start_ts, "tokenize 前取消")
        keywords = _tokenize_query(query)

        # ---- Stage 2: retrieve ----
        self._emit_progress("retrieve", 1,
                            "检索中(关键词 %d 个)" % len(keywords))
        if self._is_canceled():
            return self._canceled_result(start_ts, "retrieve 前取消")

        retrieval_start = time.time()
        npu_used = False
        candidates = []
        if NPUEngine is not None:
            candidates = self._retrieve_via_npu(query)
            if candidates:
                npu_used = True
        if not candidates:
            candidates = self._retrieve_and_score(keywords)
        self._retrieval_ms = int((time.time() - retrieval_start) * 1000)
        if not candidates:
            # 0 召回 → 直接走 L3
            return self._handle_zero_recall(query, mode, is_test_query,
                                              start_ts, friend_tag=friend_tag)

        # NPU 低分检测: top-3 全部 < 0.10 → I don't know
        if npu_used:
            top3_scores = [kp.get('_npu_score', 0) for kp in candidates[:3]]
            if top3_scores and all(s < 0.10 for s in top3_scores):
                return self._handle_low_confidence(
                    query, mode, is_test_query, start_ts, candidates,
                    friend_tag=friend_tag)

        # ---- Stage 3: rerank ----
        self._emit_progress("rerank", 2, "重排序中(候选 %d 条)" % len(candidates))
        if self._is_canceled():
            return self._canceled_result(start_ts, "rerank 前取消")

        if len(candidates) >= QA_RERANK_THRESHOLD:
            top_n = self._rerank_with_v3(query, candidates)
        else:
            top_n = candidates[:QA_TOP_N_AFTER_RANK]

        # ---- Stage 4: generate (主链 + 三级降级) ----
        self._emit_progress("generate", 3, "生成中(主链)")
        if self._is_canceled():
            return self._canceled_result(start_ts, "generate 前取消")

        gen_start = time.time()
        answer, source, gen_err, model_used = self._generate_with_fallback_chain(
            query, top_n, model_pref=model_pref)
        self._generation_ms = int((time.time() - gen_start) * 1000)

        # followup 补救(主链/L1/R1 成功但 板块 3 空)
        if source != 'rule_fallback':
            fups = answer.get('followup_questions') or []
            if not fups:
                try:
                    fups2 = self._generate_followups(query, top_n, candidates)
                    if fups2:
                        answer['followup_questions'] = fups2
                except Exception:
                    pass

        # 注入 policy_basis(来源追溯)
        self._add_policy_basis(answer, top_n)

        # 速度日志: 分离检索时间和生成时间
        print(f"[QA] 检索{self._retrieval_ms}ms + 生成{self._generation_ms}ms = "
              f"总{int((time.time() - start_ts) * 1000)}ms "
              f"(来源: {source}, 模型: {model_used or '无'})")

        # ---- Stage 5: record ----
        self._emit_progress("record", 4, "写入历史 + 使用埋点")
        retrieved_ids = [int(kp.get('kp_id')) for kp in top_n
                         if kp.get('kp_id') is not None]
        latency_ms = int((time.time() - start_ts) * 1000)

        history_id = 0
        try:
            history_id = self.db.save_qa_history(
                query=query,
                answer_json=answer,
                retrieved_kp_ids=retrieved_ids,
                mode=mode,
                source=source,
                latency_ms=latency_ms,
                is_test_query=is_test_query,
                friend_tag=friend_tag,
            )
        except Exception as e:
            self._safe_log_event("qa_save_history_failed", "error",
                                  {"err": str(e)[:300]})

        # 老唐自测不记 used_count(防脏数据,决策档案 §11)
        if not is_test_query and source in ('main', 'l1_retry', 'r1_fallback'):
            ev_ids = answer.get('evidence_kp_ids') or retrieved_ids[:3]
            if ev_ids:
                try:
                    self.db.record_kp_used(ev_ids, history_id)
                    self._safe_log_event(
                        "qa_kp_recorded_used", "info",
                        {"kp_ids": ev_ids[:10], "qa_history_id": history_id}
                    )
                except Exception as e:
                    self._safe_log_event(
                        "qa_record_used_failed", "warning",
                        {"err": str(e)[:300], "qa_history_id": history_id}
                    )

        # 主埋点(立规则 14 严格三态)
        evt = "qa_ask_done" if source != 'rule_fallback' else "qa_ask_failed"
        sev = "info" if source == 'main' else (
            "warning" if source != 'rule_fallback' else "error")
        self._safe_log_event(evt, sev, {
            "mode": mode,
            "source": source,
            "model_pref": model_pref,
            "model_used": model_used,
            "friend_tag": friend_tag,
            "latency_ms": latency_ms,
            "retrieved_count": len(retrieved_ids),
            "history_id": history_id,
            "is_test_query": int(is_test_query),
            "ai_calls": self._ai_calls,
            "cost_cny": round(self._cost, 4),
        })

        # 自动打分(accuracy/completeness/actionability → qa_feedback)
        self._auto_score_answer(answer, query, history_id, source)

        self._emit_progress("record", 5, "完成")

        return {
            "ok": True,
            "history_id": history_id,
            "answer": answer,
            "source": source,
            "latency_ms": latency_ms,
            "retrieval_ms": self._retrieval_ms,
            "generation_ms": self._generation_ms,
            "retrieved_kp_ids": retrieved_ids,
            "canceled": False,
            "cost_estimate_cny": round(self._cost, 4),
            "error": gen_err,
            "model_used": model_used,
        }

    # ================================================================
    # Stage 实现
    # ================================================================
    def _retrieve_and_score(self, keywords: List[str]) -> List[Dict]:
        """关键词召回 + composite_score 打分(决策档案 §3 Step 3).

        关键词为空时 db 层会返回 [], 走 0 召回路径.
        """
        try:
            cands = self.db.get_qa_retrieval_candidates(
                keywords, limit=QA_RETRIEVAL_LIMIT)
        except Exception as e:
            self._safe_log_event("qa_retrieval_failed", "error",
                                  {"err": str(e)[:300]})
            return []
        if not cands:
            return []

        for kp in cands:
            score = 0.0
            # premium boost
            if (kp.get('premium_client') or 0) == 1 \
                    or (kp.get('premium_rfp') or 0) == 1:
                score += WEIGHT_PREMIUM
            # annotation boost
            if kp.get('has_annotation'):
                score += WEIGHT_ANNOTATION
            # qa_score 权重
            qa = kp.get('qa_score')
            try:
                qa_v = float(qa) if qa is not None else 0.0
            except (ValueError, TypeError):
                qa_v = 0.0
            score += qa_v * WEIGHT_QA_FACTOR
            # source_authority(立规则 §5.7 真名)
            auth = kp.get('source_authority') or ''
            score += _AUTHORITY_BOOST.get(auth, 0)
            kp['_composite_score'] = score

        cands.sort(key=lambda x: x.get('_composite_score', 0), reverse=True)
        return cands

    def _rerank_with_v3(self, query: str,
                         candidates: List[Dict]) -> List[Dict]:
        """V3 二次重排. 失败时退化为 base_score Top N."""
        # 构造摘要(精简,防 token 爆)
        cand_summary = []
        for kp in candidates[:10]:
            cand_summary.append({
                "kp_id": kp.get('kp_id'),
                "title": (kp.get('title') or '')[:80],
                "category": kp.get('category') or '',
                "subcategory": kp.get('subcategory') or '',
                "excerpt": (kp.get('original_excerpt') or '')[:200],
                "qa_score": kp.get('qa_score'),
                "has_annotation": bool(kp.get('has_annotation')),
            })

        params = {
            "user_query": query,
            "candidate_count": len(cand_summary),
            "candidates_json": json.dumps(cand_summary, ensure_ascii=False),
        }
        try:
            parsed, _, err = self._do_call_json(
                QA_RETRIEVAL_RANK_PROMPT, params, model='deepseek-chat',
                call_type="qa_retrieval_rank",
            )
            if parsed is None:
                self._safe_log_event(
                    "qa_rerank_parse_failed", "warning",
                    {"err": str(err)[:300]}
                )
                return candidates[:QA_TOP_N_AFTER_RANK]
            ranked_ids = parsed.get('ranked_kp_ids') or []
            cand_ids = {kp.get('kp_id') for kp in candidates}
            valid_ids = [int(i) for i in ranked_ids
                         if i in cand_ids][:QA_TOP_N_AFTER_RANK]
            if not valid_ids:
                return candidates[:QA_TOP_N_AFTER_RANK]
            id_to_kp = {kp.get('kp_id'): kp for kp in candidates}
            return [id_to_kp[i] for i in valid_ids if i in id_to_kp]
        except Exception as e:
            self._safe_log_event(
                "qa_rerank_failed", "warning", {"err": str(e)[:300]}
            )
            return candidates[:QA_TOP_N_AFTER_RANK]

    def _generate_with_fallback_chain(
        self, query: str, top_n: List[Dict], model_pref: str = 'v3'
    ) -> tuple:
        """主 → L1 → L2 → L3 三级降级链.

        v2.3.3-mvp: 主链根据 model_pref 翻转
          - model_pref='v3' (默认): V3 主 → V3 L1 重试 → R1 L2 跨模型兜底 → L3 规则
          - model_pref='r1':         R1 主 → R1 L1 重试 → V3 L2 跨模型兜底 → L3 规则

        source 标签语义保持向后兼容(不破坏 schema CHECK):
          - main:          主链(v3 或 r1)首发成功
          - l1_retry:      主链同模型 L1 重试成功
          - r1_fallback:   L2 跨模型兜底成功(v3 主链下=R1兜底, r1 主链下=V3兜底)
          - rule_fallback: L3 规则兜底

        返回 (answer_dict, source_label, last_error_str, model_used_str)
            model_used: 实际生成答案的模型名('deepseek-chat' / 'deepseek-reasoner' / None)
                        rule_fallback 时返回 None
        """
        last_err = None

        # 主链 / L1 同模型,L2 跨模型兜底
        if model_pref == 'r1':
            primary_model = 'deepseek-reasoner'
            l2_fallback_model = 'deepseek-chat'
        else:
            primary_model = 'deepseek-chat'
            l2_fallback_model = 'deepseek-reasoner'

        # 主链
        try:
            ans = self._generate_4_panels(query, top_n,
                                            model=primary_model)
            if ans:
                return ans, 'main', None, primary_model
        except Exception as e:
            last_err = str(e)[:300]
            self._safe_log_event("qa_ai_call_failed", "warning",
                                  {"tier": "main", "model": primary_model,
                                   "err": last_err})

        # L1 重试(同模型)
        if self._is_canceled():
            return self._l3_rule_fallback(top_n, query), 'rule_fallback', \
                "canceled before L1", None
        self._emit_progress("generate", 3,
                            "L1 重试中(%s)" % primary_model)
        try:
            ans = self._generate_4_panels(query, top_n,
                                            model=primary_model)
            if ans:
                return ans, 'l1_retry', None, primary_model
        except Exception as e:
            last_err = str(e)[:300]
            self._safe_log_event("qa_ai_call_failed", "warning",
                                  {"tier": "l1", "model": primary_model,
                                   "err": last_err})

        # L2 跨模型兜底
        if self._is_canceled():
            return self._l3_rule_fallback(top_n, query), 'rule_fallback', \
                "canceled before L2", None
        self._emit_progress("generate", 3,
                            "L2 跨模型兜底(%s)" % l2_fallback_model)
        try:
            ans = self._generate_4_panels(query, top_n,
                                            model=l2_fallback_model)
            if ans:
                return ans, 'r1_fallback', None, l2_fallback_model
        except Exception as e:
            last_err = str(e)[:300]
            self._safe_log_event("qa_ai_call_failed", "error",
                                  {"tier": "l2", "model": l2_fallback_model,
                                   "err": last_err})

        # L3 规则兜底
        return self._l3_rule_fallback(top_n, query), 'rule_fallback', last_err, None

    def _generate_4_panels(self, query: str, retrieved_kps: List[Dict],
                            model: str = 'deepseek-chat') -> Optional[Dict]:
        """V3/R1 调用生成 4 板块.

        失败时:
          - JSON 解析不出 → 返回 None(让上层走降级链)
          - AI 调用本身抛异常 → 上抛
        evidence_kp_ids 强制子集校验(防 V3 编造).
        """
        # 构造 KP 喂料
        kps_payload = []
        for kp in retrieved_kps:
            ai = kp.get('ai_extracted_content')
            if not isinstance(ai, dict):
                ai = {}
            description = (ai.get('description') or '')[:1500]
            kps_payload.append({
                "kp_id": kp.get('kp_id'),
                "title": kp.get('title') or '',
                "category": kp.get('category') or '',
                "subcategory": kp.get('subcategory') or '',
                "description": description,
                "practical_insights": kp.get('practical_insights') or [],
                "excerpt": (kp.get('original_excerpt') or '')[:500],
                "source_filename": (kp.get('renamed_filename')
                                    or kp.get('original_filename') or ''),
                "qa_score": kp.get('qa_score'),
                "source_authority": kp.get('source_authority'),
            })

        params = {
            "user_query": query,
            "kp_count": len(kps_payload),
            "retrieved_kps_json": json.dumps(kps_payload, ensure_ascii=False),
        }

        timeout = QA_TIMEOUT_R1 if 'reasoner' in model else QA_TIMEOUT_V3
        parsed, _, err = self._do_call_json(
            QA_ANSWER_GEN_PROMPT, params, model=model,
            timeout=timeout, call_type="qa_answer_gen",
        )
        if parsed is None:
            # 让上层降级
            self._safe_log_event(
                "qa_answer_parse_failed", "warning",
                {"model": model, "err": str(err)[:300]}
            )
            return None

        # evidence_kp_ids 子集校验(防编造)
        cand_ids = {kp.get('kp_id') for kp in retrieved_kps}
        raw_ev = parsed.get('evidence_kp_ids') or []
        try:
            ev = [int(i) for i in raw_ev if int(i) in cand_ids]
        except (ValueError, TypeError):
            ev = []
        # 兜底:如果 V3 一个都没给或全编造,用前 3 条
        if not ev:
            ev = [int(kp.get('kp_id')) for kp in retrieved_kps[:3]
                  if kp.get('kp_id')]
        parsed['evidence_kp_ids'] = ev

        # 兜底:必填字段(立规则 5)
        parsed.setdefault('direct_answer', '')
        parsed.setdefault('followup_questions', [])
        parsed.setdefault('coverage_gap', '')

        return parsed

    def _generate_followups(self, query: str, retrieved_kps: List[Dict],
                              all_candidates: List[Dict]) -> List[Dict]:
        """板块 3 备用补救调用. 主链生成的 followup_questions 为空时调."""
        used_titles = [kp.get('title', '') for kp in retrieved_kps[:5]
                       if kp.get('title')]
        used_ids = {kp.get('kp_id') for kp in retrieved_kps}
        nearby_titles: List[str] = []
        for kp in all_candidates:
            if kp.get('kp_id') in used_ids:
                continue
            t = kp.get('title')
            if t:
                nearby_titles.append(t)
            if len(nearby_titles) >= 8:
                break

        params = {
            "user_query": query,
            "used_kp_titles": '\n'.join('- ' + t for t in used_titles),
            "nearby_kp_titles": '\n'.join('- ' + t for t in nearby_titles),
        }
        parsed, _, _ = self._do_call_json(
            QA_FOLLOWUP_GEN_PROMPT, params, model='deepseek-chat',
            call_type="qa_followup_gen",
        )
        if parsed is None:
            return []
        return parsed.get('followups') or []

    def _l3_rule_fallback(self, retrieved_kps: List[Dict],
                            query: str) -> Dict:
        """L3 规则兜底:列 Top 3 KP 标题."""
        top3 = retrieved_kps[:3]
        if not top3:
            return {
                "direct_answer":
                    "抱歉,知识库中暂未检索到与本问题相关的内容. "
                    "建议老唐先扩充该主题的精品级知识点.",
                "evidence_kp_ids": [],
                "followup_questions": [],
                "coverage_gap":
                    "本次检索 0 条命中, 当前知识库未覆盖此主题. "
                    "建议补充该主题相关的政策原文 / 实操案例 / 投标素材.",
                "policy_basis": [],
            }
        bullets = []
        ev_ids = []
        policy_items = []
        for kp in top3:
            title = kp.get('title') or '无标题'
            src = (kp.get('renamed_filename')
                   or kp.get('original_filename') or '未知来源')
            bullets.append("- %s (来源: %s)" % (title, src))
            kid = kp.get('kp_id')
            if kid is not None:
                ev_ids.append(int(kid))
            policy_items.append({
                "kp_id": kid,
                "title": title[:80],
                "excerpt": (kp.get('original_excerpt') or '')[:200],
            })
        return {
            "direct_answer":
                "本次 AI 服务暂时不稳定, 系统列出库内最相关的 %d 条知识点供老唐自行参考:\n%s"
                % (len(top3), '\n'.join(bullets)),
            "evidence_kp_ids": ev_ids,
            "followup_questions": [],
            "coverage_gap":
                "本次因 AI 调用失败走规则兜底, 板块 3 / 板块 4 暂未生成. "
                "建议查看依据后自行判断, 或稍后重试.",
            "policy_basis": policy_items,
        }

    # ================================================================
    # 0 召回兜底(独立路径)
    # ================================================================
    def _handle_zero_recall(self, query: str, mode: str, is_test_query: int,
                              start_ts: float,
                              friend_tag: Optional[str] = None) -> Dict:
        """检索 0 命中时的标准化处理:直接 L3 + 写历史."""
        self._emit_progress("generate", 3, "0 召回, 走规则兜底")
        ans = self._l3_rule_fallback([], query)
        latency_ms = int((time.time() - start_ts) * 1000)

        history_id = 0
        try:
            history_id = self.db.save_qa_history(
                query=query, answer_json=ans, retrieved_kp_ids=[],
                mode=mode, source='rule_fallback',
                latency_ms=latency_ms, is_test_query=is_test_query,
                friend_tag=friend_tag,
            )
        except Exception as e:
            self._safe_log_event("qa_save_history_failed", "error",
                                  {"err": str(e)[:300]})

        self._safe_log_event("qa_retrieval_empty", "warning", {
            "query": query[:200], "mode": mode,
            "is_test_query": int(is_test_query),
            "friend_tag": friend_tag,
            "history_id": history_id,
        })
        self._emit_progress("record", 5, "完成(0 召回 → L3)")

        return {
            "ok": True, "history_id": history_id, "answer": ans,
            "source": "rule_fallback", "latency_ms": latency_ms,
            "retrieved_kp_ids": [], "canceled": False,
            "cost_estimate_cny": round(self._cost, 4),
            "error": None,
            "model_used": None,  # 规则兜底不调 AI
        }

    # ================================================================
    # NPU 混合检索(v2.3.7 A1)
    # ================================================================
    def _retrieve_via_npu(self, query: str, top_k: int = 50) -> List[Dict]:
        """NPU hybrid search: TF-IDF dense + BM25 re-rank.

        检索池同 get_qa_retrieval_candidates: premium + quotable + confirmed.
        返回 candidates 列表, 含 _npu_score 字段; 失败返回 [].
        """
        try:
            conn = self.db.get_connection()
            c = conn.cursor()
            c.execute("""
                SELECT kp.id AS kp_id, kp.title, kp.original_excerpt
                FROM knowledge_points kp
                WHERE kp.review_status='confirmed'
                  AND (kp.premium_client=1 OR kp.premium_rfp=1
                       OR kp.content_readiness IN ('quotable','premium'))
            """)
            pool_rows = [dict(r) for r in c.fetchall()]
            conn.close()
            if not pool_rows:
                return []

            kp_texts = [
                (str(r.get('title') or '') + ' '
                 + str(r.get('original_excerpt') or ''))[:2000]
                for r in pool_rows
            ]
            kp_id_map = {i: r['kp_id'] for i, r in enumerate(pool_rows)}

            if QaAssistantEngine._npu_engine_cache is None:
                QaAssistantEngine._npu_engine_cache = NPUEngine()
            engine = QaAssistantEngine._npu_engine_cache
            engine.build_index(kp_texts)
            results = engine.hybrid_search(
                query, top_k=min(top_k, len(kp_texts)))
            if not results:
                return []

            top_ids_with_scores = {}
            for idx, score in results:
                kid = kp_id_map.get(idx)
                if kid is not None:
                    top_ids_with_scores[kid] = score
            if not top_ids_with_scores:
                return []

            id_list = list(top_ids_with_scores.keys())
            qmarks = ','.join(['?'] * len(id_list))
            conn2 = self.db.get_connection()
            c2 = conn2.cursor()
            c2.execute(f"""
                SELECT kp.id AS kp_id,
                       kp.title,
                       kp.original_excerpt,
                       kp.ai_extracted_content,
                       kp.final_category_id,
                       kp.final_category_tags,
                       kp.final_keywords,
                       kp.practical_insights,
                       kp.qa_score,
                       kp.source_authority,
                       kp.content_readiness,
                       kp.access_level,
                       kp.premium_client,
                       kp.premium_rfp,
                       kp.premium_tier,
                       kp.premium_freshness_status,
                       kp.used_count,
                       kp.last_used_at,
                       cat.level1_name AS category,
                       cat.level2_name AS subcategory,
                       sf.original_filename,
                       sf.renamed_filename,
                       (SELECT COUNT(*) FROM annotations a
                         WHERE a.knowledge_point_id=kp.id) AS annotation_count
                FROM knowledge_points kp
                LEFT JOIN source_files sf ON kp.source_file_id=sf.id
                LEFT JOIN categories cat ON cat.id=kp.final_category_id
                WHERE kp.id IN ({qmarks})
            """, id_list)
            rows = [dict(r) for r in c2.fetchall()]
            conn2.close()

            for r in rows:
                for field in ('final_category_tags', 'final_keywords',
                              'practical_insights'):
                    val = r.get(field)
                    if isinstance(val, str):
                        try:
                            r[field] = json.loads(val)
                        except (json.JSONDecodeError, ValueError):
                            r[field] = []
                ai = r.get('ai_extracted_content')
                if isinstance(ai, str):
                    try:
                        r['ai_extracted_content'] = json.loads(ai)
                    except (json.JSONDecodeError, ValueError):
                        r['ai_extracted_content'] = {}
                r['has_annotation'] = (r.get('annotation_count') or 0) > 0
                r['_npu_score'] = top_ids_with_scores.get(r['kp_id'], 0.0)

            # composite_score(同 _retrieve_and_score 逻辑, 加 NPU 加权)
            for kp in rows:
                score = 0.0
                if ((kp.get('premium_client') or 0) == 1
                        or (kp.get('premium_rfp') or 0) == 1):
                    score += WEIGHT_PREMIUM
                if kp.get('has_annotation'):
                    score += WEIGHT_ANNOTATION
                qa = kp.get('qa_score')
                try:
                    qa_v = float(qa) if qa is not None else 0.0
                except (ValueError, TypeError):
                    qa_v = 0.0
                score += qa_v * WEIGHT_QA_FACTOR
                auth = kp.get('source_authority') or ''
                score += _AUTHORITY_BOOST.get(auth, 0)
                score += (kp.get('_npu_score') or 0.0) * 30
                kp['_composite_score'] = score

            rows.sort(key=lambda x: x.get('_composite_score', 0),
                      reverse=True)
            return rows

        except Exception as e:
            self._safe_log_event("qa_npu_retrieval_failed", "warning",
                                  {"err": str(e)[:300]})
            return []

    # ================================================================
    # policy_basis 来源追溯 / 自动打分 / 低置信度兜底
    # ================================================================
    def _add_policy_basis(self, answer: Dict, top_n: List[Dict]) -> None:
        """注入 policy_basis 字段: 每条检索 KP 的 id/title/excerpt."""
        if not answer or not isinstance(answer, dict):
            return
        basis = []
        for kp in (top_n or [])[:5]:
            excerpt = (kp.get('original_excerpt') or '')[:200]
            basis.append({
                "kp_id": kp.get('kp_id'),
                "title": (kp.get('title') or '')[:80],
                "excerpt": excerpt,
            })
        answer['policy_basis'] = basis

    def _auto_score_answer(self, answer: Dict, query: str,
                           history_id: int, source: str) -> None:
        """启发式自动打分(accuracy/completeness/actionability), 写入 qa_feedback."""
        if not history_id or not answer or not isinstance(answer, dict):
            return
        try:
            direct = str(answer.get('direct_answer') or '')
            ev_ids = answer.get('evidence_kp_ids') or []
            fups = answer.get('followup_questions') or []
            gap = str(answer.get('coverage_gap') or '')

            accuracy = 3
            if ev_ids:
                accuracy = min(5, 3 + min(len(ev_ids), 2))
            if source == 'rule_fallback':
                accuracy = max(1, accuracy - 2)

            completeness = 3
            if direct and len(direct) >= 50:
                completeness += 1
            if fups:
                completeness += 1
            if '无法充分覆盖' in gap:
                completeness = max(2, completeness - 1)
            completeness = min(5, max(1, completeness))

            actionability = 3
            if direct:
                if re.search(r'\d+', direct):
                    actionability += 1
                if re.search(r'[一-鿿]+[市县乡村镇]', direct):
                    actionability += 1
                if len(direct) >= 100:
                    actionability = min(5, actionability + 1)

            score_data = {
                "accuracy": accuracy,
                "completeness": completeness,
                "actionability": actionability,
                "overall": round((accuracy + completeness + actionability) / 3, 1),
                "auto_generated": True,
            }
            comment = json.dumps(score_data, ensure_ascii=False)
            self.db.save_qa_feedback(history_id, 'comment', comment)
            self._safe_log_event("qa_auto_scored", "info", {
                "history_id": history_id,
                "scores": score_data,
            })
        except Exception as e:
            self._safe_log_event("qa_auto_score_failed", "warning",
                                  {"err": str(e)[:300]})

    def _handle_low_confidence(self, query: str, mode: str,
                                is_test_query: int, start_ts: float,
                                candidates: List[Dict],
                                friend_tag: Optional[str] = None) -> Dict:
        """NPU top-3 全 < 0.10 时的特殊 L3 兜底: 诚实告知覆盖不足."""
        self._emit_progress("generate", 3, "检索置信度过低, 走规则兜底")
        top3 = candidates[:3]
        ev_ids = []
        policy_items = []
        for kp in top3:
            kid = kp.get('kp_id')
            if kid is not None:
                ev_ids.append(int(kid))
            policy_items.append({
                "kp_id": kid,
                "title": (kp.get('title') or '无标题')[:80],
                "excerpt": (kp.get('original_excerpt') or '')[:200],
            })
        ans = {
            "direct_answer":
                "抱歉，当前知识库中暂无与您问题高度匹配的内容。"
                "以下列出库内相对最相关的 %d 条知识点供参考，建议老唐优先补充该主题的精品级知识点。" % len(policy_items),
            "evidence_kp_ids": ev_ids,
            "followup_questions": [],
            "coverage_gap":
                "此问题当前知识库无法充分覆盖，已记录并将优先补充。"
                "建议补充该主题相关的政策原文 / 实操案例 / 投标素材。",
            "policy_basis": policy_items,
            "confidence": "uncertain",
        }
        latency_ms = int((time.time() - start_ts) * 1000)

        history_id = 0
        try:
            history_id = self.db.save_qa_history(
                query=query, answer_json=ans, retrieved_kp_ids=ev_ids,
                mode=mode, source='rule_fallback',
                latency_ms=latency_ms, is_test_query=is_test_query,
                friend_tag=friend_tag,
            )
        except Exception as e:
            self._safe_log_event("qa_save_history_failed", "error",
                                  {"err": str(e)[:300]})

        self._safe_log_event("qa_low_confidence_npu", "warning", {
            "query": query[:200], "mode": mode,
            "is_test_query": int(is_test_query),
            "friend_tag": friend_tag,
            "history_id": history_id,
            "top3_scores": [kp.get('_npu_score', 0) for kp in top3],
        })

        self._auto_score_answer(ans, query, history_id, 'rule_fallback')
        self._emit_progress("record", 5, "完成(低置信度 → L3)")

        return {
            "ok": True, "history_id": history_id, "answer": ans,
            "source": "rule_fallback", "latency_ms": latency_ms,
            "retrieved_kp_ids": ev_ids, "canceled": False,
            "cost_estimate_cny": round(self._cost, 4),
            "error": None,
            "model_used": None,
        }

    # ================================================================
    # AI 调用适配器(立规则 9 / 18)
    # ================================================================
    def _do_call_json(self, prompt_dict: Dict, params: Dict,
                       model: str = 'deepseek-chat',
                       timeout: int = QA_TIMEOUT_V3,
                       call_type: str = 'qa') -> tuple:
        """通用 JSON 调用. 返回 (parsed_dict|None, content_str, error_str|None).

        三层路径(对照 deepseek_client 真实代码 + premium_judge 容错精神):
          路径 1: client.chat_with_json — 自带 7 重 JSON 解析保险(最佳)
          路径 2: client.chat — 拿 content 后用 _parse_json_loose 解析
          路径 3: 五方法两签名适配器(终极兜底,与 premium_judge 模板对齐)
        """
        sys_p = prompt_dict.get('system_prompt', '')
        usr_p = prompt_dict.get('user_prompt_template', '').format(**params)
        is_r1 = 'reasoner' in model

        last_err: Optional[str] = None

        # ---- 路径 1: chat_with_json(最佳路径) ----
        method = getattr(self.client, 'chat_with_json', None)
        if callable(method):
            try:
                kwargs = {
                    "system_prompt": sys_p,
                    "user_prompt": usr_p,
                    "call_type": call_type,
                    "model_override": model,
                }
                if not is_r1:
                    kwargs["temperature"] = V3_TEMPERATURE
                # chat_with_json 不一定支持 timeout 参数,试加再 fallback
                try:
                    kwargs2 = dict(kwargs); kwargs2["timeout"] = timeout
                    result = method(**kwargs2)
                except TypeError:
                    result = method(**kwargs)

                content = result.get('content', '') if isinstance(result, dict) else ''
                parsed = result.get('parsed_json') if isinstance(result, dict) else None
                self._ai_calls += 1
                self._accumulate_cost(result)
                if parsed is not None:
                    return parsed, content, None
                # 失败也返回 — 不再退到路径 2(同一 client 同一调用走两次浪费)
                return None, content, str(result.get('json_parse_error', 'JSON parse failed'))[:300]
            except TypeError as e:
                last_err = str(e)[:300]
            except Exception as e:
                last_err = str(e)[:300]
                self._safe_log_event(
                    "qa_chat_with_json_failed", "warning",
                    {"err": last_err, "model": model}
                )

        # ---- 路径 2: chat() ----
        method2 = getattr(self.client, 'chat', None)
        if callable(method2):
            try:
                kwargs = {
                    "system_prompt": sys_p,
                    "user_prompt": usr_p,
                    "call_type": call_type,
                    "model_override": model,
                }
                if not is_r1:
                    kwargs["temperature"] = V3_TEMPERATURE
                try:
                    kwargs2 = dict(kwargs); kwargs2["timeout"] = timeout
                    result = method2(**kwargs2)
                except TypeError:
                    result = method2(**kwargs)

                content = result.get('content', '') if isinstance(result, dict) else str(result)
                self._ai_calls += 1
                self._accumulate_cost(result)
                parsed = _parse_json_loose(content)
                if parsed is not None:
                    return parsed, content, None
                return None, content, "JSON parse failed via chat()"
            except TypeError as e:
                last_err = str(e)[:300]
            except Exception as e:
                last_err = str(e)[:300]

        # ---- 路径 3: 五方法两签名兜底(防 client 接口异变) ----
        msgs = [
            {"role": "system", "content": sys_p},
            {"role": "user", "content": usr_p},
        ]
        for mn in ('call_chat', 'complete', 'call', 'generate'):
            m = getattr(self.client, mn, None)
            if not callable(m):
                continue
            for kw_try in (
                {"messages": msgs, "model": model, "timeout": timeout},
                {"system_prompt": sys_p, "user_prompt": usr_p,
                 "model_override": model, "timeout": timeout},
                {"system_prompt": sys_p, "user_prompt": usr_p,
                 "model_override": model},
            ):
                if not is_r1:
                    kw_try["temperature"] = V3_TEMPERATURE
                try:
                    result = m(**kw_try)
                    content = result.get('content', '') if isinstance(result, dict) else str(result)
                    self._ai_calls += 1
                    self._accumulate_cost(result)
                    parsed = _parse_json_loose(content)
                    if parsed is not None:
                        return parsed, content, None
                    return None, content, "JSON parse failed via " + mn
                except TypeError as e:
                    last_err = str(e)[:300]
                    continue
                except Exception as e:
                    last_err = str(e)[:300]
                    break

        # 所有路径都失败
        raise RuntimeError(
            "AI client all paths failed: " + (last_err or "unknown")[:200]
        )

    def _accumulate_cost(self, result: Any) -> None:
        """从 client 返回中累计成本(元).

        deepseek_client.chat 返回 dict 含 estimated_cost(已经按当前价格计算).
        """
        if not isinstance(result, dict):
            return
        c = result.get('estimated_cost')
        if c is not None:
            try:
                self._cost += float(c)
            except (ValueError, TypeError):
                pass

    # ================================================================
    # 进度 / 取消 / 日志
    # ================================================================
    def _emit_progress(self, current_step: str, processed: int,
                        message: str) -> None:
        """与 premium_judge.progress_callback 风格对齐的 dict 报告."""
        try:
            self.progress_callback({
                "current_step": current_step,
                "message": message,
                "processed_kps": processed,
                "total_kps": 5,
                "ai_calls_count": self._ai_calls,
                "cost_estimate_cny": round(self._cost, 4),
            })
        except Exception:
            pass

    def _is_canceled(self) -> bool:
        try:
            return bool(self.cancel_check())
        except Exception:
            return False

    def _canceled_result(self, start_ts: float, msg: str) -> Dict:
        latency_ms = int((time.time() - start_ts) * 1000)
        self._safe_log_event("qa_ask_canceled", "warning",
                              {"msg": msg, "latency_ms": latency_ms})
        return {
            "ok": False, "history_id": 0, "answer": None,
            "source": "rule_fallback", "latency_ms": latency_ms,
            "retrieved_kp_ids": [], "canceled": True,
            "cost_estimate_cny": round(self._cost, 4),
            "error": msg,
            "model_used": None,
        }

    def _safe_log_event(self, event_type: str, severity: str,
                          payload: Dict) -> None:
        """封装 db.log_operation_event,失败不抛(立规则 14 强制三态)."""
        if severity not in ("info", "warning", "error"):
            severity = "warning"
        try:
            self.db.log_operation_event(
                event_type=event_type,
                module="qa_assistant",
                severity=severity,
                payload=payload,
            )
        except Exception:
            pass


def run_qa(db: Any, client: Any, query: str, mode: str = 'self',
            is_test_query: int = 0,
            progress_callback: Optional[Callable[[Dict], None]] = None,
            cancel_check: Optional[Callable[[], bool]] = None,
            model_pref: str = 'v3',
            friend_tag: Optional[str] = None) -> Dict:
    """模块级便捷函数,供 api_server 调用.

    v2.3.3-mvp 新增参数:
      model_pref: 'v3' | 'r1'  主链模型偏好(自用 R1 时主链翻转)
      friend_tag: str|None     朋友身份(URL ?u=张三)

    调用方式:
        from scripts.qa_assistant import run_qa
        result = run_qa(db, client, "全域土地综合整治怎么搞",
                         mode='self', is_test_query=0,
                         progress_callback=cb,
                         cancel_check=lambda: _qa_task['cancel_requested'],
                         model_pref='v3',
                         friend_tag='张三')
    """
    engine = QaAssistantEngine(db, client, progress_callback, cancel_check)
    return engine.run_qa(query, mode=mode, is_test_query=is_test_query,
                          model_pref=model_pref, friend_tag=friend_tag)
