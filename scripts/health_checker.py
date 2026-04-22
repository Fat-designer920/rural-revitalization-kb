# -*- coding: utf-8 -*-
"""
health_checker.py - 知识库体检 Agent 引擎层（F048）

版本: v2.3.0-part2-alpha2
所属: 乡村振兴知识管理系统

职责:
    六维度扫描知识库健康度,生成 health_report + polish_suggestions
    维度①健康度  维度②结构分布  维度③加工深度
    维度④关联密度(孤岛精判)  维度⑤低分打磨(三层降级链)  维度⑥变现匹配度

核心约定:
    - 所有 AI 调用走 deepseek_client,V3 传 model_override='deepseek-chat'+temperature=0.1
    - R1 不传 temperature,超时 300s,分段 <=3000 字
    - JSON 字段入 db.save_polish_suggestion() 直接传 dict,db 层自动序列化
    - 所有 log_operation_event 调用走 _safe_log_event 包装
    - 采纳事务(备份->更新kp->标记applied)由 api_server 层做,本模块只管生成 suggestion

打磨三层降级链:
    L1 主链: HEALTH_DIAGNOSIS(V3) -> HEALTH_POLISH(R1) -> HEALTH_POLISH_VERIFY(V3)
    L2 降级: HEALTH_POLISH_CONSERVATIVE(V3)
    L3 兜底: 规则标记 manual_review_needed, suggested_content=NULL

降级触发条件:
    诊断阶段: recommend_manual_review=true / polish_difficulty=impossible -> L3
              polish_direction=drop -> 生成 drop 建议(仍算 L1)
    主链校验: verify_pass=false / re_score<原分 / confidence=low / R1 截断 -> L2
    L2 失败: -> L3
"""

import json
import re
import time
import traceback
from datetime import datetime, timezone
from typing import Any, Callable, Dict, List, Optional, Tuple


# ============================================================
# 模块级可选导入 (失败时 HealthChecker 构造参数也可显式传入)
# ============================================================
try:
    from scripts.db_manager import DatabaseManager  # type: ignore
except Exception:
    DatabaseManager = None  # noqa: N816

try:
    from scripts.deepseek_client import DeepSeekClient  # type: ignore
except Exception:
    DeepSeekClient = None  # noqa: N816

try:
    from scripts.prompts.prompt_templates import (
        HEALTH_DIAGNOSIS_PROMPT,
        HEALTH_POLISH_PROMPT,
        HEALTH_POLISH_VERIFY_PROMPT,
        HEALTH_POLISH_CONSERVATIVE_PROMPT,
        HEALTH_ISLAND_JUDGE_PROMPT,
        HEALTH_MONETIZE_REPORT_PROMPT,
    )
except Exception as _e:  # 允许单测时不依赖 prompt_templates
    HEALTH_DIAGNOSIS_PROMPT = None
    HEALTH_POLISH_PROMPT = None
    HEALTH_POLISH_VERIFY_PROMPT = None
    HEALTH_POLISH_CONSERVATIVE_PROMPT = None
    HEALTH_ISLAND_JUDGE_PROMPT = None
    HEALTH_MONETIZE_REPORT_PROMPT = None


# ============================================================
# 常量
# ============================================================
# 六大类(00_项目全景)
TOP_CATEGORIES = ['政策库', '案例库', '经验库', '工具库', '数据库']
# 27 个二级分类(02_知识体系)
SUB_CATEGORIES = [
    '1.1全域土地综合整治政策', '1.2增减挂钩与占补平衡', '1.3集体经营性建设用地入市',
    '1.4专项债与资金政策', '1.5川西林盘保护政策', '1.6乡村振兴综合政策',
    '1.7自然资源与规划政策',
    '2.1全域土地综合整治项目', '2.2增减挂钩项目', '2.3川西林盘修复运营项目',
    '2.4资金整合与融资创新案例', '2.5乡村产业与运营案例', '2.6失败与风险案例',
    '3.1策略判断类', '3.2操盘方法类', '3.3反常识洞察', '3.4踩坑记录',
    '3.5客户沟通与汇报经验',
    '4.1方案模板', '4.2合同模板', '4.3评审意见模板', '4.4招标文件模板',
    '4.5汇报材料模板', '4.6申报材料模板',
    '5.1资金测算数据', '5.2指标数据', '5.3地方政策对比', '5.4项目规模与成效数据',
    '5.5行业基准数据',
]


# ============================================================
# HealthChecker 主类
# ============================================================
class HealthChecker:
    """知识库体检 Agent 引擎层

    使用示例:
        hc = HealthChecker(db=db, client=client, progress_callback=cb)
        result = hc.run_full_check(polish_max=50)
        # result = {'success': True, 'report_id': 12, 'total_score': 78.5, 'summary': {...}}
    """

    # ===== 六维度权重(总和 1.0) =====
    DIMENSION_WEIGHTS = {
        'dim1_health': 0.25,
        'dim2_structure': 0.10,
        'dim3_processing': 0.20,
        'dim4_relation': 0.10,
        'dim5_polish': 0.20,
        'dim6_monetize': 0.15,
    }

    # ===== 打磨档位白名单 =====
    POLISH_MAX_OPTIONS = [30, 50, 100, 200, None]  # None 表示不限
    POLISH_MAX_DEFAULT = 50

    # ===== 孤岛精判上限(内部常量) =====
    ISLAND_JUDGE_MAX_COUNT = 50

    # ===== R1/V3 调用约束 =====
    R1_SEGMENT_LIMIT = 3000       # 输入分段上限(字符)
    R1_TIMEOUT = 300
    V3_TIMEOUT = 60
    V3_TEMPERATURE = 0.1

    # ===== 变现场景(对照 03_Prompt 手册) =====
    MONETIZE_SCENARIOS = ['咨询答疑', '方案撰写', '政策解读', '汇报话术', '投标辅助']

    # ===== 成本估算(USD/千 token, 粗估值,仅供报告参考) =====
    V3_INPUT_PER_1K = 0.001
    V3_OUTPUT_PER_1K = 0.002
    R1_INPUT_PER_1K = 0.002
    R1_OUTPUT_PER_1K = 0.008

    # ------------------------------------------------------------
    # 构造
    # ------------------------------------------------------------
    def __init__(
        self,
        db=None,
        client=None,
        progress_callback: Optional[Callable[[Dict[str, Any]], None]] = None,
    ):
        """
        Args:
            db: DatabaseManager 实例;None 时自动创建
            client: DeepSeekClient 实例;None 时自动创建(需在 headless 模式)
            progress_callback: 进度回调 fn(payload_dict);payload={stage,current,total,message}
        """
        if db is None:
            if DatabaseManager is None:
                raise RuntimeError('db_manager 未能导入,无法体检')
            db = DatabaseManager()
        self.db = db

        if client is None:
            if DeepSeekClient is None:
                raise RuntimeError('deepseek_client 未能导入,无法体检')
            client = DeepSeekClient()
        self.client = client

        self.progress_callback = progress_callback

        # 本次运行累计
        self._v3_call_count = 0
        self._r1_call_count = 0
        self._cost_estimate = 0.0
        self._current_report_id: Optional[int] = None

    # ============================================================
    # 主入口
    # ============================================================
    def run_full_check(
        self,
        polish_max: Optional[int] = POLISH_MAX_DEFAULT,
        island_max: Optional[int] = None,
    ) -> Dict[str, Any]:
        """一键启动全库体检

        Args:
            polish_max: 单次打磨上限 (30/50/100/200/None);非白名单值自动兜底 50
            island_max: 孤岛精判上限,默认走 ISLAND_JUDGE_MAX_COUNT

        Returns:
            成功: {'success': True, 'report_id': N, 'total_score': 82.5, 'summary': dict}
            失败: {'success': False, 'error': str, 'report_id': N or None}
        """
        # --- 参数校验与兜底 ---
        if polish_max not in self.POLISH_MAX_OPTIONS:
            self._safe_log_event(
                'health_check_param_invalid', 'warn',
                {'param': 'polish_max', 'got': polish_max, 'fallback': self.POLISH_MAX_DEFAULT},
            )
            polish_max = self.POLISH_MAX_DEFAULT

        if island_max is None:
            island_max = self.ISLAND_JUDGE_MAX_COUNT

        # --- 建 running 行 ---
        started_at = self._now_iso()
        try:
            report_id = self.db.save_health_report({
                'created_at': started_at,
                'status': 'running',
            })
            self._current_report_id = report_id
        except Exception as e:
            return {'success': False, 'error': f'创建报告失败: {e}', 'report_id': None}

        self._safe_log_event('health_check_start', 'info', {
            'report_id': report_id,
            'polish_max': polish_max,
            'island_max': island_max,
        })

        # 重置累计器
        self._v3_call_count = 0
        self._r1_call_count = 0
        self._cost_estimate = 0.0

        try:
            return self._run_pipeline(report_id, polish_max, island_max)
        except Exception as e:
            tb = traceback.format_exc()
            self._safe_log_event('health_check_failed', 'error', {
                'report_id': report_id, 'error': str(e), 'traceback': tb[:1000],
            })
            try:
                self.db.update_health_report(report_id, {
                    'status': 'failed',
                    'error_message': str(e)[:500],
                    'v3_call_count': self._v3_call_count,
                    'r1_call_count': self._r1_call_count,
                    'cost_estimate': round(self._cost_estimate, 4),
                })
            except Exception:
                pass
            self._emit_progress('failed', 0, 0, f'体检失败: {e}')
            return {'success': False, 'error': str(e), 'report_id': report_id}

    # ------------------------------------------------------------
    # 流水线(内部)
    # ------------------------------------------------------------
    def _run_pipeline(
        self, report_id: int, polish_max: Optional[int], island_max: int,
    ) -> Dict[str, Any]:
        # Stage 0: 加载数据
        self._emit_progress('init', 0, 0, '初始化: 加载全库知识点')
        kps = self._safe_call(
            lambda: self.db.get_kp_for_health_scan(include_annotations=True), default=[],
        )
        total_kp = len(kps)

        tag_dist = {
            'A': self._safe_call(lambda: self.db.get_tag_distribution('A'), default=[]),
            'C': self._safe_call(lambda: self.db.get_tag_distribution('C'), default=[]),
            'D': self._safe_call(lambda: self.db.get_tag_distribution('D'), default=[]),
        }

        dimensions: Dict[str, Any] = {}

        # Stage 1: 健康度
        self._emit_progress('dim1', 0, 0, '维度 1/6: 健康度分析')
        dimensions['dim1_health'] = self._safe_dim('dim1_health',
            lambda: self._dim1_health_score(kps))

        # Stage 2: 结构分布
        self._emit_progress('dim2', 0, 0, '维度 2/6: 结构分布分析')
        dimensions['dim2_structure'] = self._safe_dim('dim2_structure',
            lambda: self._dim2_structure_score(kps, tag_dist))

        # Stage 3: 加工深度
        self._emit_progress('dim3', 0, 0, '维度 3/6: 加工深度分析')
        dimensions['dim3_processing'] = self._safe_dim('dim3_processing',
            lambda: self._dim3_processing_score(kps))

        # Stage 4: 关联密度(含孤岛精判)
        self._emit_progress('dim4_island', 0, 0, '维度 4/6: 关联密度分析(本地粗筛中)')
        dimensions['dim4_relation'] = self._safe_dim('dim4_relation',
            lambda: self._dim4_relation_score(total_kp, island_max))

        # Stage 5: 低分打磨
        self._emit_progress('dim5_polish', 0, 0, '维度 5/6: 低分打磨准备')
        dimensions['dim5_polish'] = self._safe_dim('dim5_polish',
            lambda: self._dim5_polish(report_id, total_kp, polish_max))

        # Stage 6: 变现匹配度
        self._emit_progress('dim6_monetize', 0, 0, '维度 6/6: 变现匹配度分析')
        lib_summary = self._build_library_summary(kps, tag_dist)
        dimensions['dim6_monetize'] = self._safe_dim('dim6_monetize',
            lambda: self._dim6_monetize_score(lib_summary))

        # 聚合总分
        total_score = self._compute_total_score(dimensions)
        polish_skipped = dimensions.get('dim5_polish', {}).get('detail', {}).get('skipped_due_to_max', 0)

        full_report = {
            'scanned_at': self._now_iso(),
            'total_kp_count': total_kp,
            'polish_max_used': polish_max,
            'island_max_used': island_max,
            'dimensions': dimensions,
            'polish_skipped_count': polish_skipped,
            'v3_call_count': self._v3_call_count,
            'r1_call_count': self._r1_call_count,
            'cost_estimate': round(self._cost_estimate, 4),
        }

        # 落盘
        self.db.update_health_report(report_id, {
            'status': 'completed',
            'total_score': total_score,
            'dim1_health_score': dimensions.get('dim1_health', {}).get('score'),
            'dim2_structure_score': dimensions.get('dim2_structure', {}).get('score'),
            'dim3_processing_score': dimensions.get('dim3_processing', {}).get('score'),
            'dim4_relation_score': dimensions.get('dim4_relation', {}).get('score'),
            'dim5_polish_score': dimensions.get('dim5_polish', {}).get('score'),
            'dim6_monetize_score': dimensions.get('dim6_monetize', {}).get('score'),
            'full_report_json': full_report,
            'scanned_kp_count': total_kp,
            'v3_call_count': self._v3_call_count,
            'r1_call_count': self._r1_call_count,
            'cost_estimate': round(self._cost_estimate, 4),
        })

        self._safe_log_event('health_check_done', 'info', {
            'report_id': report_id,
            'total_score': total_score,
            'v3_calls': self._v3_call_count,
            'r1_calls': self._r1_call_count,
            'cost': round(self._cost_estimate, 4),
        })
        self._emit_progress('done', total_kp, total_kp, f'体检完成: 总分 {total_score}')

        return {
            'success': True,
            'report_id': report_id,
            'total_score': total_score,
            'summary': {
                'total_kp_count': total_kp,
                'dimension_scores': {k: v.get('score') for k, v in dimensions.items()},
                'polish_stats': dimensions.get('dim5_polish', {}).get('detail', {}).get('polish_stats'),
                'polish_skipped_count': polish_skipped,
            },
        }

    # ============================================================
    # 维度 ①健康度
    # ============================================================
    def _dim1_health_score(self, kps: List[Dict]) -> Dict[str, Any]:
        total = len(kps)
        if total == 0:
            return {'score': 0, 'detail': {'note': '空库'}}

        high_count = sum(1 for k in kps if (k.get('qa_score') or 0) >= 4)
        fallback_count = sum(1 for k in kps if k.get('qa_source') == 'rule_fallback')
        unchecked_count = sum(1 for k in kps if (k.get('qa_score') or 0) == 0)

        # 分布
        dist = {'0': 0, '1': 0, '2': 0, '3': 0, '4': 0, '5': 0}
        for k in kps:
            s = int(k.get('qa_score') or 0)
            if s < 0:
                s = 0
            if s > 5:
                s = 5
            dist[str(s)] += 1

        high_rate = high_count / total
        fallback_rate = fallback_count / total
        unchecked_rate = unchecked_count / total

        score = high_rate * 50 + (1 - fallback_rate) * 30 + (1 - unchecked_rate) * 20
        score = round(max(0.0, min(100.0, score)), 2)

        return {
            'score': score,
            'detail': {
                'total_kp': total,
                'high_score_count': high_count,
                'high_score_rate': round(high_rate, 4),
                'fallback_count': fallback_count,
                'fallback_rate': round(fallback_rate, 4),
                'unchecked_count': unchecked_count,
                'unchecked_rate': round(unchecked_rate, 4),
                'qa_score_distribution': dist,
            },
        }

    # ============================================================
    # 维度 ②结构分布
    # ============================================================
    def _dim2_structure_score(self, kps: List[Dict], tag_dist: Dict[str, List]) -> Dict[str, Any]:
        total = len(kps)
        if total == 0:
            return {'score': 0, 'detail': {'note': '空库'}}

        # 大类命中
        l1_set = set()
        l2_set = set()
        for k in kps:
            cat = (k.get('category') or '').strip()
            subcat = (k.get('subcategory') or '').strip()
            # 粗匹配大类(前缀或包含)
            for tc in TOP_CATEGORIES:
                if tc and (cat == tc or (cat and cat.startswith(tc[:2]))):
                    l1_set.add(tc)
                    break
            if subcat:
                l2_set.add(subcat)

        l1_hit = len(l1_set)
        l2_hit = len(l2_set & set(SUB_CATEGORIES))
        l1_rate = l1_hit / len(TOP_CATEGORIES)
        l2_rate = l2_hit / len(SUB_CATEGORIES)

        # 三层标签均衡度 = 1 - 归一化标准差
        variance = self._tag_balance_score(tag_dist)

        score = l1_rate * 30 + l2_rate * 40 + variance * 30
        score = round(max(0.0, min(100.0, score)), 2)

        return {
            'score': score,
            'detail': {
                'l1_hit': l1_hit,
                'l1_total': len(TOP_CATEGORIES),
                'l1_rate': round(l1_rate, 4),
                'l2_hit': l2_hit,
                'l2_total': len(SUB_CATEGORIES),
                'l2_rate': round(l2_rate, 4),
                'tag_balance': round(variance, 4),
                'tag_balance_explain': '1=完全均衡, 0=严重失衡',
            },
        }

    def _tag_balance_score(self, tag_dist: Dict[str, List]) -> float:
        """三层标签均衡度: 1 - 归一化标准差
        tag_dist 每组格式: [{'name':'XXX','count':N}, ...] 或 {'tag'/'label':'XXX','n':N}
        """
        all_counts = []
        for group in ('A', 'C', 'D'):
            for item in tag_dist.get(group, []) or []:
                c = item.get('count') if item.get('count') is not None else item.get('n')
                if c is not None:
                    try:
                        all_counts.append(int(c))
                    except Exception:
                        continue
        if not all_counts:
            return 0.0
        mean = sum(all_counts) / len(all_counts)
        if mean == 0:
            return 0.0
        var = sum((c - mean) ** 2 for c in all_counts) / len(all_counts)
        std = var ** 0.5
        cv = std / mean  # 变异系数
        return max(0.0, 1.0 - min(cv, 1.0))

    # ============================================================
    # 维度 ③加工深度
    # ============================================================
    def _dim3_processing_score(self, kps: List[Dict]) -> Dict[str, Any]:
        total = len(kps)
        if total == 0:
            return {'score': 0, 'detail': {'note': '空库'}}

        annotated = 0
        with_insights = 0
        premium_authority = 0
        premium_monetize = 0

        for k in kps:
            # 注解覆盖率
            ac = k.get('annotations_count') or 0
            try:
                if int(ac) > 0:
                    annotated += 1
            except Exception:
                pass
            # 举一反三填充率
            insights = k.get('practical_insights')
            if isinstance(insights, list) and len(insights) > 0:
                with_insights += 1
            elif isinstance(insights, str) and insights.strip() and insights.strip() != '[]':
                with_insights += 1
            # 权威度
            auth = (k.get('authority_level') or '').lower()
            if auth in ('official', 'authoritative'):
                premium_authority += 1
            # 变现分级
            tier = (k.get('monetize_tier') or '').lower()
            if tier == 'premium':
                premium_monetize += 1

        anno_rate = annotated / total
        insight_rate = with_insights / total
        pa_rate = premium_authority / total
        pm_rate = premium_monetize / total

        score = anno_rate * 40 + insight_rate * 30 + pa_rate * 15 + pm_rate * 15
        score = round(max(0.0, min(100.0, score)), 2)

        return {
            'score': score,
            'detail': {
                'total_kp': total,
                'annotated_count': annotated,
                'annotation_rate': round(anno_rate, 4),
                'insights_filled_count': with_insights,
                'insights_fill_rate': round(insight_rate, 4),
                'premium_authority_count': premium_authority,
                'premium_authority_rate': round(pa_rate, 4),
                'premium_monetize_count': premium_monetize,
                'premium_monetize_rate': round(pm_rate, 4),
            },
        }

    # ============================================================
    # 维度 ④关联密度(本地粗筛 + V3 精判)
    # ============================================================
    def _dim4_relation_score(self, total_kp: int, island_max: int) -> Dict[str, Any]:
        if total_kp == 0:
            return {'score': 0, 'detail': {'note': '空库'}}

        candidates = self._safe_call(
            lambda: self.db.get_island_candidates(), default=[],
        )
        candidate_count = len(candidates)
        if candidate_count == 0:
            return {
                'score': 100.0,
                'detail': {'island_candidates': 0, 'note': '无孤岛候选'},
            }

        # 限量精判
        sampled = candidates[:island_max] if island_max else candidates
        sampled_count = len(sampled)

        all_kps_lite = None  # 延迟构建 nearby summary
        judged_island = 0
        judged_detail = []

        for idx, kp in enumerate(sampled, 1):
            self._emit_progress('dim4_island', idx, sampled_count,
                                f'孤岛精判 {idx}/{sampled_count}')
            if all_kps_lite is None:
                # 构建轻量邻近摘要源(题+分类)
                all_kps_lite = self._safe_call(
                    lambda: self.db.get_kp_for_health_scan(include_annotations=False),
                    default=[],
                )
            nearby = self._build_nearby_summary(kp, all_kps_lite, max_items=8)
            judgment = self._judge_island(kp, nearby)
            if judgment and judgment.get('is_island'):
                it = (judgment.get('island_type') or '').strip()
                if it in ('true_island', 'structural_isolated'):
                    judged_island += 1
                    judged_detail.append({
                        'kp_id': kp.get('kp_id'),
                        'island_type': it,
                        'relation_suggestion': judgment.get('relation_suggestion', ''),
                    })

        # 按抽样比例外推
        if sampled_count > 0 and candidate_count > sampled_count:
            estimated_islands = judged_island / sampled_count * candidate_count
        else:
            estimated_islands = judged_island

        island_rate = estimated_islands / total_kp if total_kp else 0
        score = max(0.0, 100.0 - island_rate * 100)
        score = round(score, 2)

        return {
            'score': score,
            'detail': {
                'total_kp': total_kp,
                'island_candidates': candidate_count,
                'sampled_count': sampled_count,
                'judged_island_count': judged_island,
                'estimated_island_rate': round(island_rate, 4),
                'island_examples': judged_detail[:10],
            },
        }

    def _build_nearby_summary(
        self, target_kp: Dict, all_kps: List[Dict], max_items: int = 8,
    ) -> str:
        """组装相似分类/标签的简要摘要给 V3 判断"""
        target_cat = target_kp.get('category') or ''
        target_sub = target_kp.get('subcategory') or ''
        target_id = target_kp.get('kp_id')
        # 同分类优先
        same_sub = [k for k in all_kps
                    if k.get('kp_id') != target_id
                    and (k.get('subcategory') or '') == target_sub]
        same_cat = [k for k in all_kps
                    if k.get('kp_id') != target_id
                    and (k.get('category') or '') == target_cat
                    and (k.get('subcategory') or '') != target_sub]
        picks = (same_sub + same_cat)[:max_items]
        lines = []
        for k in picks:
            t = (k.get('title') or '')[:50]
            c = (k.get('category') or '')
            s = (k.get('subcategory') or '')
            lines.append(f"- [{c}/{s}] {t}")
        if not lines:
            return '(无同分类邻近知识点)'
        return '\n'.join(lines)

    def _judge_island(self, kp: Dict, nearby_summary: str) -> Optional[Dict]:
        """调 V3 HEALTH_ISLAND_JUDGE_PROMPT 判定是否孤岛"""
        if not HEALTH_ISLAND_JUDGE_PROMPT:
            return None
        try:
            sys_p = HEALTH_ISLAND_JUDGE_PROMPT['system']
            user_tpl = HEALTH_ISLAND_JUDGE_PROMPT['user']
            kp_json = json.dumps(self._kp_to_judge_payload(kp), ensure_ascii=False)
            user_p = user_tpl.format(
                knowledge_point_json=kp_json,
                nearby_kp_summary=nearby_summary,
            )
            resp = self._call_v3(sys_p, user_p, timeout=self.V3_TIMEOUT)
            return self._safe_parse_json(resp)
        except Exception as e:
            self._safe_log_event('health_ai_call_failed', 'warn', {
                'stage': 'island_judge', 'kp_id': kp.get('kp_id'), 'error': str(e)[:300],
            })
            return None

    def _kp_to_judge_payload(self, kp: Dict) -> Dict:
        """抽取用于孤岛判定的精简字段"""
        return {
            'kp_id': kp.get('kp_id'),
            'title': kp.get('title'),
            'category': kp.get('category'),
            'subcategory': kp.get('subcategory'),
            'description': (kp.get('description') or kp.get('content') or '')[:500],
            'tags': {
                'layer1': kp.get('layer1_tags') or kp.get('tags_layer1'),
                'layer2': kp.get('layer2_tags') or kp.get('tags_layer2'),
                'layer3': kp.get('layer3_tags') or kp.get('tags_layer3'),
            },
        }

    # ============================================================
    # 维度 ⑤低分打磨(三层降级链)
    # ============================================================
    def _dim5_polish(
        self, report_id: int, total_kp: int, polish_max: Optional[int],
    ) -> Dict[str, Any]:
        if total_kp == 0:
            return {'score': 0, 'detail': {'note': '空库'}}

        candidates = self._safe_call(
            lambda: self.db.get_polish_candidates(), default=[],
        )
        low_score_count = len(candidates)

        # 排序: qa_score 升序 (0被过滤掉了) -> created_at 降序
        def _sort_key(k):
            qs = k.get('qa_score') or 0
            ca = k.get('created_at') or ''
            return (qs, -self._ts_of(ca))

        candidates.sort(key=_sort_key)

        if polish_max is None:
            to_polish = candidates
        else:
            to_polish = candidates[:polish_max]
        to_count = len(to_polish)
        skipped = max(0, low_score_count - to_count)

        # 得分公式: 100 - 低分占比*100 (不依赖打磨执行情况)
        low_rate = low_score_count / total_kp if total_kp else 0
        base_score = max(0.0, 100.0 - low_rate * 100)

        stats = {'attempted': to_count, 'l1': 0, 'l2': 0, 'l3': 0, 'drop': 0, 'error': 0}

        for idx, kp in enumerate(to_polish, 1):
            self._emit_progress('dim5_polish', idx, to_count,
                                f"打磨 {idx}/{to_count}: kp#{kp.get('kp_id')}")
            try:
                tier, sugg_type = self._polish_one_kp(kp, report_id)
                if tier == 'L1_r1_polish':
                    if sugg_type == 'drop':
                        stats['drop'] += 1
                    else:
                        stats['l1'] += 1
                elif tier == 'L2_v3_conservative':
                    stats['l2'] += 1
                elif tier == 'L3_manual':
                    stats['l3'] += 1
                else:
                    stats['error'] += 1
            except Exception as e:
                stats['error'] += 1
                self._safe_log_event('health_polish_fallback', 'warn', {
                    'kp_id': kp.get('kp_id'), 'tier': 'exception', 'error': str(e)[:300],
                })

        return {
            'score': round(base_score, 2),
            'detail': {
                'total_kp': total_kp,
                'low_score_count': low_score_count,
                'low_score_rate': round(low_rate, 4),
                'polish_max_used': polish_max,
                'skipped_due_to_max': skipped,
                'polish_stats': stats,
            },
        }

    # ------------------------------------------------------------
    # 单条打磨(降级链)
    # ------------------------------------------------------------
    def _polish_one_kp(self, kp: Dict, report_id: int) -> Tuple[str, str]:
        """单条 kp 走三层降级链,返回 (tier, suggestion_type)"""
        kp_id = kp.get('kp_id')

        # --- Step 1: V3 诊断 ---
        diag = self._diagnose_polish_candidate(kp)
        if not diag:
            self._mark_manual_review(kp, report_id, None, '诊断失败(V3 返回无效)')
            self._safe_log_event('health_polish_l3_manual', 'info',
                                 {'kp_id': kp_id, 'reason': 'diagnose_failed'})
            return ('L3_manual', 'manual_review')

        # --- Step 2: 诊断后分支 ---
        if diag.get('recommend_manual_review') or diag.get('polish_difficulty') == 'impossible':
            self._mark_manual_review(kp, report_id, diag, '诊断建议人工介入')
            self._safe_log_event('health_polish_l3_manual', 'info',
                                 {'kp_id': kp_id, 'reason': 'diagnose_hint_manual'})
            return ('L3_manual', 'manual_review')

        if diag.get('polish_direction') == 'drop':
            self._save_suggestion(kp, report_id, 'L1_r1_polish', diag, None, 'drop')
            return ('L1_r1_polish', 'drop')

        # --- Step 3: L1 主链 R1 打磨 + V3 校验 ---
        polished = self._polish_with_r1(kp, diag)
        if polished is not None:
            verify = self._verify_polish(diag, kp, polished)
            if self._verify_is_acceptable(verify, kp):
                sugg_type = 'split' if (isinstance(polished, list) and len(polished) > 1) \
                            else diag.get('polish_direction', 'improve')
                self._save_suggestion(kp, report_id, 'L1_r1_polish', diag, polished, sugg_type)
                return ('L1_r1_polish', sugg_type)
            self._safe_log_event('health_polish_fallback', 'info', {
                'kp_id': kp_id, 'from': 'L1', 'to': 'L2',
                'reason': 'verify_failed_or_low_score',
                'verify': verify,
            })
        else:
            self._safe_log_event('health_polish_fallback', 'info', {
                'kp_id': kp_id, 'from': 'L1', 'to': 'L2', 'reason': 'r1_no_output',
            })

        # --- Step 4: L2 V3 保守打磨 ---
        conservative = self._polish_conservative(kp, diag)
        if conservative:
            self._save_suggestion(kp, report_id, 'L2_v3_conservative', diag, conservative, 'improve')
            return ('L2_v3_conservative', 'improve')

        # --- Step 5: L3 兜底 ---
        self._mark_manual_review(kp, report_id, diag, 'L1/L2 均失败')
        self._safe_log_event('health_polish_l3_manual', 'info',
                             {'kp_id': kp_id, 'reason': 'L1_L2_all_failed'})
        return ('L3_manual', 'manual_review')

    # ------------------------------------------------------------
    # 诊断 / 打磨 / 校验 / 保守打磨
    # ------------------------------------------------------------
    def _diagnose_polish_candidate(self, kp: Dict) -> Optional[Dict]:
        if not HEALTH_DIAGNOSIS_PROMPT:
            return None
        try:
            sys_p = HEALTH_DIAGNOSIS_PROMPT['system']
            user_tpl = HEALTH_DIAGNOSIS_PROMPT['user']
            kp_json = json.dumps(self._kp_to_full_payload(kp), ensure_ascii=False)
            filename = kp.get('source_file_name') or kp.get('source_file') or 'unknown'
            user_p = user_tpl.format(
                filename=filename,
                knowledge_point_json=kp_json,
            )
            resp = self._call_v3(sys_p, user_p, timeout=self.V3_TIMEOUT)
            return self._safe_parse_json(resp)
        except Exception as e:
            self._safe_log_event('health_ai_call_failed', 'warn', {
                'stage': 'diagnose', 'kp_id': kp.get('kp_id'), 'error': str(e)[:300],
            })
            return None

    def _polish_with_r1(self, kp: Dict, diag: Dict) -> Optional[Any]:
        """R1 创造性打磨,返回 list(split 可能多条) 或 None"""
        if not HEALTH_POLISH_PROMPT:
            return None
        try:
            sys_p = HEALTH_POLISH_PROMPT['system']
            user_tpl = HEALTH_POLISH_PROMPT['user']
            kp_payload = self._kp_to_full_payload(kp)
            # 控制输入长度
            kp_json = json.dumps(kp_payload, ensure_ascii=False)
            if len(kp_json) > self.R1_SEGMENT_LIMIT:
                # 截断 description 保证输入不炸
                if 'description' in kp_payload and isinstance(kp_payload['description'], str):
                    kp_payload['description'] = kp_payload['description'][:2000] + '...[截断]'
                    kp_json = json.dumps(kp_payload, ensure_ascii=False)

            filename = kp.get('source_file_name') or kp.get('source_file') or 'unknown'
            diag_str = json.dumps({
                'diagnosis': diag.get('diagnosis', ''),
                'root_cause_type': diag.get('root_cause_type', ''),
                'polish_difficulty': diag.get('polish_difficulty', ''),
            }, ensure_ascii=False)
            polish_dir = diag.get('polish_direction', 'improve')

            user_p = user_tpl.format(
                filename=filename,
                knowledge_point_json=kp_json,
                diagnosis=diag_str,
                polish_direction=polish_dir,
            )
            resp = self._call_r1(sys_p, user_p, timeout=self.R1_TIMEOUT)

            # 截断检测: R1 完成的响应应该以完整 JSON 结尾
            parsed = self._safe_parse_json(resp)
            if parsed is None:
                return None

            # 规范化: 单对象也包成数组方便下游处理
            if isinstance(parsed, dict):
                parsed = [parsed]
            if not isinstance(parsed, list) or len(parsed) == 0:
                return None

            # 基本字段校验
            for item in parsed:
                if not isinstance(item, dict):
                    return None
                if not item.get('title') or not item.get('description'):
                    return None
            return parsed
        except Exception as e:
            self._safe_log_event('health_ai_call_failed', 'warn', {
                'stage': 'polish_r1', 'kp_id': kp.get('kp_id'), 'error': str(e)[:300],
            })
            return None

    def _verify_polish(self, diag: Dict, original_kp: Dict, polished: Any) -> Optional[Dict]:
        """V3 校验 R1 打磨结果"""
        if not HEALTH_POLISH_VERIFY_PROMPT:
            return None
        try:
            sys_p = HEALTH_POLISH_VERIFY_PROMPT['system']
            user_tpl = HEALTH_POLISH_VERIFY_PROMPT['user']
            original_json = json.dumps(self._kp_to_full_payload(original_kp), ensure_ascii=False)
            polished_json = json.dumps(polished, ensure_ascii=False)
            diag_str = json.dumps({
                'diagnosis': diag.get('diagnosis', ''),
                'polish_direction': diag.get('polish_direction', ''),
            }, ensure_ascii=False)
            user_p = user_tpl.format(
                diagnosis=diag_str,
                original_json=original_json,
                polished_json=polished_json,
            )
            resp = self._call_v3(sys_p, user_p, timeout=self.V3_TIMEOUT)
            return self._safe_parse_json(resp)
        except Exception as e:
            self._safe_log_event('health_ai_call_failed', 'warn', {
                'stage': 'verify', 'kp_id': original_kp.get('kp_id'), 'error': str(e)[:300],
            })
            return None

    def _verify_is_acceptable(self, verify: Optional[Dict], original_kp: Dict) -> bool:
        if not verify:
            return False
        if not verify.get('verify_pass'):
            return False
        if (verify.get('confidence') or '').lower() == 'low':
            return False
        try:
            re_score = float(verify.get('re_score') or 0)
            orig_score = float(original_kp.get('qa_score') or 0)
            if re_score < orig_score:
                return False
        except Exception:
            return False
        return True

    def _polish_conservative(self, kp: Dict, diag: Dict) -> Optional[Dict]:
        """L2 V3 保守打磨"""
        if not HEALTH_POLISH_CONSERVATIVE_PROMPT:
            return None
        try:
            sys_p = HEALTH_POLISH_CONSERVATIVE_PROMPT['system']
            user_tpl = HEALTH_POLISH_CONSERVATIVE_PROMPT['user']
            original_json = json.dumps(self._kp_to_full_payload(kp), ensure_ascii=False)
            diag_str = json.dumps({
                'diagnosis': diag.get('diagnosis', ''),
                'root_cause_type': diag.get('root_cause_type', ''),
            }, ensure_ascii=False)
            user_p = user_tpl.format(
                diagnosis=diag_str,
                original_json=original_json,
            )
            resp = self._call_v3(sys_p, user_p, timeout=self.V3_TIMEOUT)
            parsed = self._safe_parse_json(resp)
            if not parsed:
                return None
            # 保守打磨应返回单对象
            if isinstance(parsed, list):
                parsed = parsed[0] if parsed else None
            if not isinstance(parsed, dict):
                return None
            if not parsed.get('title') or not parsed.get('description'):
                return None
            return parsed
        except Exception as e:
            self._safe_log_event('health_ai_call_failed', 'warn', {
                'stage': 'polish_conservative', 'kp_id': kp.get('kp_id'), 'error': str(e)[:300],
            })
            return None

    # ------------------------------------------------------------
    # 建议落盘
    # ------------------------------------------------------------
    def _save_suggestion(
        self,
        kp: Dict,
        report_id: int,
        tier: str,
        diagnosis: Optional[Dict],
        suggested_content: Any,
        suggestion_type: str,
    ) -> Optional[int]:
        """保存一条 polish_suggestion。suggested_content 传 dict/list,db 层自动序列化。"""
        try:
            diagnosis_text = ''
            if diagnosis:
                diagnosis_text = diagnosis.get('diagnosis', '') or ''

            payload = {
                'report_id': report_id,
                'kp_id': kp.get('kp_id'),
                'diagnosis': diagnosis_text,
                'suggestion_type': suggestion_type,
                'tier': tier,
                'original_content': self._kp_to_full_payload(kp),
                'suggested_content': suggested_content,  # None 也允许(drop/manual)
                'status': 'pending',
                'created_at': self._now_iso(),
            }
            return self.db.save_polish_suggestion(payload)
        except Exception as e:
            self._safe_log_event('health_polish_save_failed', 'error', {
                'kp_id': kp.get('kp_id'), 'tier': tier, 'error': str(e)[:300],
            })
            return None

    def _mark_manual_review(
        self, kp: Dict, report_id: int, diagnosis: Optional[Dict], reason: str,
    ) -> Optional[int]:
        """L3 兜底: 标记 manual_review_needed, suggested_content=None"""
        diagnosis_text = f'[建议人工介入] {reason}'
        if diagnosis and diagnosis.get('diagnosis'):
            diagnosis_text = f'{diagnosis_text} | 诊断: {diagnosis.get("diagnosis")}'
        try:
            payload = {
                'report_id': report_id,
                'kp_id': kp.get('kp_id'),
                'diagnosis': diagnosis_text[:500],
                'suggestion_type': 'manual_review',
                'tier': 'L3_manual',
                'original_content': self._kp_to_full_payload(kp),
                'suggested_content': None,
                'status': 'manual_review_needed',
                'created_at': self._now_iso(),
            }
            return self.db.save_polish_suggestion(payload)
        except Exception as e:
            self._safe_log_event('health_polish_save_failed', 'error', {
                'kp_id': kp.get('kp_id'), 'tier': 'L3_manual', 'error': str(e)[:300],
            })
            return None

    # ============================================================
    # 维度 ⑥变现匹配度
    # ============================================================
    def _dim6_monetize_score(self, lib_summary: Dict) -> Dict[str, Any]:
        if not HEALTH_MONETIZE_REPORT_PROMPT:
            return {'score': 0, 'detail': {'note': 'Prompt 未就绪'}}
        try:
            sys_p = HEALTH_MONETIZE_REPORT_PROMPT['system']
            user_tpl = HEALTH_MONETIZE_REPORT_PROMPT['user']
            summary_json = json.dumps(lib_summary, ensure_ascii=False)
            user_p = user_tpl.format(library_summary_json=summary_json)
            resp = self._call_v3(sys_p, user_p, timeout=self.V3_TIMEOUT)
            parsed = self._safe_parse_json(resp) or {}
            score = float(parsed.get('overall_monetize_score') or 0)
            score = round(max(0.0, min(100.0, score)), 2)
            return {
                'score': score,
                'detail': {
                    'scenario_scores': parsed.get('scenario_scores', {}),
                    'feed_direction': parsed.get('feed_direction', []),
                    'monetize_readiness': parsed.get('monetize_readiness', ''),
                    'library_summary': lib_summary,
                },
            }
        except Exception as e:
            self._safe_log_event('health_ai_call_failed', 'warn', {
                'stage': 'monetize', 'error': str(e)[:300],
            })
            return {'score': 0, 'detail': {'error': str(e)[:200]}}

    def _build_library_summary(self, kps: List[Dict], tag_dist: Dict[str, List]) -> Dict:
        """构建整库统计摘要供变现报告使用"""
        total = len(kps)
        if total == 0:
            return {'total_kp': 0}

        cat_count = {}
        sub_count = {}
        auth_count = {}
        tier_count = {}
        qa_dist = {'0': 0, '1': 0, '2': 0, '3': 0, '4': 0, '5': 0}
        high_quality_count = 0

        for k in kps:
            c = k.get('category') or '未分类'
            cat_count[c] = cat_count.get(c, 0) + 1
            s = k.get('subcategory') or '未分类'
            sub_count[s] = sub_count.get(s, 0) + 1
            a = k.get('authority_level') or 'unknown'
            auth_count[a] = auth_count.get(a, 0) + 1
            t = k.get('monetize_tier') or 'unknown'
            tier_count[t] = tier_count.get(t, 0) + 1
            qs = int(k.get('qa_score') or 0)
            if qs < 0:
                qs = 0
            if qs > 5:
                qs = 5
            qa_dist[str(qs)] += 1
            if qs >= 4:
                high_quality_count += 1

        return {
            'total_kp': total,
            'high_quality_count': high_quality_count,
            'category_distribution': cat_count,
            'subcategory_distribution': sub_count,
            'authority_distribution': auth_count,
            'monetize_tier_distribution': tier_count,
            'qa_score_distribution': qa_dist,
            'tag_distribution': {
                'A': tag_dist.get('A', []),
                'C': tag_dist.get('C', []),
                'D': tag_dist.get('D', []),
            },
        }

    # ============================================================
    # AI 调用封装
    # ============================================================
    def _call_v3(self, system_prompt: str, user_prompt: str, timeout: int = 60) -> Optional[str]:
        """V3 调用统一入口: model_override='deepseek-chat' + temperature=0.1"""
        try:
            content, usage = self._do_call(
                system_prompt=system_prompt,
                user_prompt=user_prompt,
                model_override='deepseek-chat',
                temperature=self.V3_TEMPERATURE,
                timeout=timeout,
            )
            self._v3_call_count += 1
            if usage:
                self._accumulate_cost('v3', usage)
            return content
        except Exception as e:
            self._safe_log_event('health_ai_call_failed', 'warn', {
                'model': 'v3', 'error': str(e)[:300],
            })
            return None

    def _call_r1(self, system_prompt: str, user_prompt: str, timeout: int = 300) -> Optional[str]:
        """R1 调用统一入口: 不传 temperature"""
        try:
            content, usage = self._do_call(
                system_prompt=system_prompt,
                user_prompt=user_prompt,
                model_override=None,  # 默认 R1
                temperature=None,     # R1 不支持
                timeout=timeout,
            )
            self._r1_call_count += 1
            if usage:
                self._accumulate_cost('r1', usage)
            return content
        except Exception as e:
            self._safe_log_event('health_ai_call_failed', 'warn', {
                'model': 'r1', 'error': str(e)[:300],
            })
            return None

    def _do_call(
        self,
        system_prompt: str,
        user_prompt: str,
        model_override: Optional[str],
        temperature: Optional[float],
        timeout: int,
    ) -> Tuple[Optional[str], Optional[Dict]]:
        """统一适配 deepseek_client 各种可能的接口签名,返回 (content, usage)"""
        client = self.client
        kwargs = {}
        if model_override is not None:
            kwargs['model_override'] = model_override
        if temperature is not None:
            kwargs['temperature'] = temperature

        # 优先尝试 call_chat(messages=..., timeout=...)
        messages = [
            {'role': 'system', 'content': system_prompt},
            {'role': 'user', 'content': user_prompt},
        ]

        # 候选方法名逐个尝试(兼容项目中的不同接口)
        for method_name in ('call_chat', 'chat', 'complete', 'call', 'generate'):
            fn = getattr(client, method_name, None)
            if not fn:
                continue
            try:
                # 尝试传 messages
                try:
                    res = fn(messages=messages, timeout=timeout, **kwargs)
                except TypeError:
                    # 退化: 传 system+user 两个分开参数
                    try:
                        res = fn(system_prompt=system_prompt, user_prompt=user_prompt,
                                 timeout=timeout, **kwargs)
                    except TypeError:
                        res = fn(system_prompt, user_prompt, **kwargs)
                return self._unpack_response(res)
            except Exception:
                continue
        raise RuntimeError('deepseek_client 没有可用的 chat 接口')

    def _unpack_response(self, res: Any) -> Tuple[Optional[str], Optional[Dict]]:
        """解析不同客户端返回值结构, 返回 (content, usage)"""
        if res is None:
            return None, None
        if isinstance(res, str):
            return res, None
        if isinstance(res, dict):
            content = (res.get('content') or res.get('text')
                       or res.get('message') or res.get('response'))
            usage = res.get('usage') or res.get('token_usage')
            if isinstance(content, dict):
                content = content.get('content') or content.get('text')
            return content, usage
        if isinstance(res, tuple) and len(res) >= 1:
            content = res[0]
            usage = res[1] if len(res) > 1 else None
            return content, usage
        # 退化: 任何对象 str() 一下
        return str(res), None

    def _accumulate_cost(self, model: str, usage: Dict):
        try:
            pt = int(usage.get('prompt_tokens') or usage.get('input_tokens') or 0)
            ct = int(usage.get('completion_tokens') or usage.get('output_tokens') or 0)
            if model == 'v3':
                cost = pt / 1000 * self.V3_INPUT_PER_1K + ct / 1000 * self.V3_OUTPUT_PER_1K
            else:
                cost = pt / 1000 * self.R1_INPUT_PER_1K + ct / 1000 * self.R1_OUTPUT_PER_1K
            self._cost_estimate += cost
        except Exception:
            pass

    # ============================================================
    # 工具方法
    # ============================================================
    def _kp_to_full_payload(self, kp: Dict) -> Dict:
        """抽取送入 AI 的 kp 完整字段快照"""
        return {
            'kp_id': kp.get('kp_id'),
            'title': kp.get('title'),
            'description': kp.get('description') or kp.get('content') or '',
            'category': kp.get('category'),
            'subcategory': kp.get('subcategory'),
            'qa_score': kp.get('qa_score'),
            'qa_flags': kp.get('qa_flags'),
            'qa_source': kp.get('qa_source'),
            'authority_level': kp.get('authority_level'),
            'monetize_tier': kp.get('monetize_tier'),
            'tags': {
                'layer1': kp.get('layer1_tags') or kp.get('tags_layer1'),
                'layer2': kp.get('layer2_tags') or kp.get('tags_layer2'),
                'layer3': kp.get('layer3_tags') or kp.get('tags_layer3'),
            },
            'practical_insights': kp.get('practical_insights'),
            'source_file_name': kp.get('source_file_name') or kp.get('source_file'),
            'excerpt': kp.get('excerpt'),
        }

    def _safe_parse_json(self, text: Optional[str]) -> Any:
        """稳健 JSON 解析: 剥 ```json 围栏 / 首尾清洗 / 兜底找第一个 { 或 ["""
        if not text:
            return None
        if not isinstance(text, str):
            return text  # 已是结构化

        s = text.strip()
        # 去 BOM
        if s.startswith('\ufeff'):
            s = s[1:]
        # 去 markdown 围栏
        if s.startswith('```'):
            # 去除首行 ```json 或 ```
            s = re.sub(r'^```[a-zA-Z]*\s*', '', s)
            if s.endswith('```'):
                s = s[:-3]
            s = s.strip()

        try:
            return json.loads(s)
        except Exception:
            pass

        # 兜底: 截取第一个 {...} 或 [...] 块
        for left, right in (('{', '}'), ('[', ']')):
            lp = s.find(left)
            rp = s.rfind(right)
            if lp != -1 and rp != -1 and rp > lp:
                candidate = s[lp:rp + 1]
                try:
                    return json.loads(candidate)
                except Exception:
                    continue
        return None

    def _safe_log_event(self, event_type: str, severity: str, payload: Dict):
        """包装 log_operation_event, 日志失败只打 print 不 raise"""
        try:
            if self._current_report_id is not None:
                payload = dict(payload)
                payload.setdefault('report_id', self._current_report_id)
            if hasattr(self.db, 'log_operation_event'):
                self.db.log_operation_event(
                    event_type=event_type,
                    severity=severity,
                    module='health_checker',
                    payload=payload,
                )
        except Exception as e:
            try:
                print(f'[health_checker] log_event failed: {event_type} / {e}')
            except Exception:
                pass

    def _emit_progress(self, stage: str, current: int, total: int, message: str):
        if not self.progress_callback:
            return
        try:
            self.progress_callback({
                'stage': stage,
                'current': current,
                'total': total,
                'message': message,
            })
        except Exception:
            pass

    def _safe_call(self, fn: Callable, default=None):
        try:
            return fn()
        except Exception as e:
            self._safe_log_event('health_internal_call_failed', 'warn', {
                'error': str(e)[:300],
            })
            return default

    def _safe_dim(self, dim_name: str, fn: Callable) -> Dict[str, Any]:
        """单维度异常隔离: 失败返回 score=0"""
        try:
            result = fn() or {}
            if 'score' not in result:
                result['score'] = 0
            return result
        except Exception as e:
            tb = traceback.format_exc()
            self._safe_log_event('health_dim_failed', 'warn', {
                'dim': dim_name, 'error': str(e)[:300], 'traceback': tb[:800],
            })
            return {'score': 0, 'detail': {'error': str(e)[:200]}}

    def _compute_total_score(self, dimensions: Dict[str, Dict]) -> float:
        total = 0.0
        for key, weight in self.DIMENSION_WEIGHTS.items():
            s = dimensions.get(key, {}).get('score') or 0
            try:
                total += float(s) * weight
            except Exception:
                continue
        return round(max(0.0, min(100.0, total)), 2)

    def _now_iso(self) -> str:
        return datetime.now(timezone.utc).astimezone().isoformat(timespec='seconds')

    def _ts_of(self, iso_str: str) -> float:
        try:
            return datetime.fromisoformat(iso_str).timestamp()
        except Exception:
            return 0.0


# ============================================================
# 模块级便捷入口(方便 api_server 简短调用)
# ============================================================
def run_health_check(
    db=None,
    client=None,
    progress_callback: Optional[Callable] = None,
    polish_max: Optional[int] = HealthChecker.POLISH_MAX_DEFAULT,
) -> Dict[str, Any]:
    """模块级便捷入口

    api_server 可直接:
        from scripts.health_checker import run_health_check
        result = run_health_check(db=db, client=client,
                                  progress_callback=cb, polish_max=50)
    """
    hc = HealthChecker(db=db, client=client, progress_callback=progress_callback)
    return hc.run_full_check(polish_max=polish_max)


if __name__ == '__main__':
    # 命令行自测(需配置好 db 和 api key)
    import sys
    try:
        result = run_health_check(polish_max=5)
        print(json.dumps(result, ensure_ascii=False, indent=2))
    except Exception as ex:
        print(f'[health_checker] 自测失败: {ex}', file=sys.stderr)
        sys.exit(1)
