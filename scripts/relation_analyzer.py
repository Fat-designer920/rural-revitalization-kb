"""
relation_analyzer.py - 知识点关系分析模块(替代 duplicate_checker.py)
路径：scripts/relation_analyzer.py
版本：v2.3.5-part2 - chat_with_json kwarg 修复(F4) + V4-Pro 思考型识别

v2.3.5-part2 修复(hotfix, 2026-04-30):
  - F4 P0 BUG:_judge_one_group 调 chat_with_json 用了不存在的 model= 关键字
    真实签名是 model_override=(deepseek_client.py:512),老唐 0429 实测 7 组关系判别
    全部 TypeError 失败 → v2.3.5-part1 主功能瘫痪
    立规则 9 第 22 次应验 — 凭记忆写 kwarg,不 grep 真实签名
  - 同时把"reasoner not in model"这种历史思考型判定升级为支持 V4-Pro
    (v4-pro / r1 / reasoner / thinking 任一关键字命中即跳过 temperature)

v2.3.5-part1 重设计(feature, 2026-04-28):
  - 替代 duplicate_checker.py(改名+重写,旧文件删除)
  - 旧:二态判别(duplicate / not_duplicate)→ 写 duplicate_groups 表
  - 新:六态判别(cross_file_consensus / policy_evolution / hierarchical_refinement /
            same_file_redundancy / conflicting / complementary / unrelated)
        → 写 kp_relations + consensus_clusters + cluster_members 三表
  - AI 主链:V3 主判 + R1 兜底(V3 confidence < 70 或失败时升级)
  - AI 不确定 fallback_action='human_review' 时,关系状态置 'pending_human_review'
    UI 红色边框单独高亮,老唐手动选关系类型
  - 旧 duplicate_groups 表保留向下兼容(物理保留,不再写入)
  - 旧 /api/tools/duplicate_unified / duplicate-scan / duplicate-reset-rescan 路由保留
    内部不再调用 DuplicateChecker(已删),改调 RelationAnalyzer

关键架构:
  - 第一阶段本地粗筛:标题相似度(SequenceMatcher) + 关键词重叠(Jaccard) — 沿用旧逻辑
  - 第二阶段 V3 六态判别 → 命中 same_file_redundancy / cross_file_consensus / 等
    → 写 kp_relations(单边或多边)+ 自动建 consensus_clusters(若 cluster_suggestion.should_cluster=True)
    + 同步写 cluster_members
  - confidence < 70 时升级 R1 重判一次(覆盖 V3 输出,标 source='r1_fallback')
  - confidence 仍 < 70 或 fallback_action='human_review' → 关系标 'pending_human_review'

立规则#3 推广应用:
  - 删除关系组 → 走 db.purge_cluster_record() 封装(级联清 cluster_members + kp_relations.cluster_id 置空)
  - 删除 kp → 走 db.delete_knowledge_point() 已挂钩 cascade(包含 kp_relations / cluster_members)

公共入口(沿用旧三个名字以兼容 api_server 调度):
  - scan_full()          -- 全库重扫(工具箱按钮"重扫全库关系")
  - scan_recent(days=7)  -- 最近 N 天 created_at 的 kp 增量扫描
  - scan_incremental(kp_ids) -- 提取后传入新 kp id 列表的增量扫描
"""
import os, sys, json, re
from pathlib import Path
from difflib import SequenceMatcher
from datetime import datetime

PROJECT_ROOT = Path(__file__).parent.parent
sys.path.insert(0, str(PROJECT_ROOT))

from scripts.db_manager import DatabaseManager
from scripts.prompts.prompt_templates import RELATION_JUDGE_PROMPT

# === 阈值配置 ===
TITLE_SIM_THRESHOLD = 0.65       # 标题相似度阈值(沿用旧值,政策文件术语重叠大)
KEYWORD_JACCARD_THRESHOLD = 0.50 # 关键词Jaccard系数阈值
COMBINED_THRESHOLD = 0.65        # 综合得分阈值(title*0.7 + keyword*0.3)
MAX_GROUP_SIZE_FOR_AI = 6        # 发送给 AI 判别的最大组大小

# v2.3.5-part1: V3 主链 + R1 兜底
CONFIDENCE_UPGRADE_THRESHOLD = 70  # confidence < 此值时升级 R1 重判


class RelationAnalyzer:
    """知识点关系分析器(替代 DuplicateChecker)"""

    def __init__(self, db=None, client=None):
        self.db = db or DatabaseManager()
        self.client = client  # DeepSeekClient, 可选(无client时只做本地粗筛不建关系)

    # ================================================================
    # 公开接口(三入口)
    # ================================================================
    def scan_full(self):
        """全库扫描:检测所有未忽略知识点之间的疑似关系"""
        print(f"\n  [关系分析] 全库扫描开始...")
        kps = self._load_all_kps()
        if len(kps) < 2:
            print(f"  知识点不足2条,无需检测")
            return 0
        print(f"  加载{len(kps)}条知识点")
        return self._run_pipeline(kps)

    def scan_recent(self, days=7):
        """扫描最近N天created_at的知识点"""
        print(f"\n  [关系分析] 最近{days}天扫描开始...")
        from datetime import timedelta
        cutoff = (datetime.now() - timedelta(days=days)).strftime("%Y-%m-%d %H:%M:%S")
        conn = self.db.get_connection(); c = conn.cursor()
        c.execute("""SELECT id FROM knowledge_points
                     WHERE review_status != 'ignored'
                       AND created_at >= ?""", (cutoff,))
        recent_ids = [r[0] for r in c.fetchall()]
        conn.close()
        if not recent_ids:
            print(f"  最近{days}天内无新知识点")
            return 0
        print(f"  最近{days}天: {len(recent_ids)}条新知识点")
        return self.scan_incremental(recent_ids)

    def scan_incremental(self, new_kp_ids):
        """增量扫描:对一批新kp与全库其他kp做关系检测"""
        if not new_kp_ids:
            return 0
        print(f"\n  [关系分析] 增量扫描 {len(new_kp_ids)} 条新知识点...")
        # 加载全部 + 标记新 kp
        all_kps = self._load_all_kps()
        if len(all_kps) < 2:
            return 0
        new_set = set(new_kp_ids)
        # 粗筛仅保留"新 vs 全部"的对(不做"全部 vs 全部"避免重扫历史)
        candidate_pairs = self._local_prefilter(all_kps, restrict_left_set=new_set)
        if not candidate_pairs:
            print(f"  未发现疑似关系")
            return 0
        candidate_pairs = self._filter_known_pairs(candidate_pairs)
        if not candidate_pairs:
            print(f"  所有疑似关系已在处理列表中")
            return 0
        groups = self._aggregate_groups(candidate_pairs, all_kps)
        print(f"  粗筛: {len(candidate_pairs)}对疑似 -> {len(groups)}组")
        return self._ai_judge_groups(groups, all_kps)

    # ================================================================
    # 第一阶段:加载 + 本地粗筛
    # ================================================================
    def _load_all_kps(self):
        """加载全库 review_status != 'ignored' 的 kp,带必要字段"""
        conn = self.db.get_connection(); c = conn.cursor()
        c.execute("""
            SELECT kp.id, kp.title, kp.content_type, kp.ai_extracted_content,
                   kp.original_excerpt, kp.created_at,
                   sf.original_filename, sf.renamed_filename
            FROM knowledge_points kp
            LEFT JOIN source_files sf ON kp.source_file_id = sf.id
            WHERE kp.review_status != 'ignored'
        """)
        rows = [dict(r) for r in c.fetchall()]
        conn.close()
        # 解析 ai_extracted_content 提关键词 + 摘要
        for kp in rows:
            ai = kp.get("ai_extracted_content")
            if isinstance(ai, str):
                try:
                    ai = json.loads(ai)
                except Exception:
                    ai = {}
            if not isinstance(ai, dict):
                ai = {}
            kws = ai.get("suggested_keywords") or ai.get("keywords") or []
            if isinstance(kws, str):
                kws = [k.strip() for k in re.split(r"[,，;；\s]+", kws) if k.strip()]
            kp["_keywords"] = set(str(k).lower() for k in kws if k)
            kp["_summary"] = (ai.get("description") or ai.get("policy_content")
                              or ai.get("core_conclusion") or "")[:300]
            kp["_source_file"] = kp.get("renamed_filename") or kp.get("original_filename") or ""
        return rows

    def _local_prefilter(self, kps, restrict_left_set=None):
        """本地粗筛:返回 [(id_a, id_b, score), ...]
        restrict_left_set 不为空时,只看 id_a 在 set 内的对(增量场景)"""
        pairs = []
        n = len(kps)
        for i in range(n):
            kp_i = kps[i]
            id_i = kp_i["id"]
            if restrict_left_set is not None and id_i not in restrict_left_set:
                continue
            t_i = kp_i.get("title", "") or ""
            kw_i = kp_i["_keywords"]
            for j in range(i + 1, n):
                kp_j = kps[j]
                id_j = kp_j["id"]
                # 增量模式:i 必须在 set,j 不限(覆盖"新 vs 历史"和"新 vs 新")
                t_j = kp_j.get("title", "") or ""
                kw_j = kp_j["_keywords"]
                # 标题相似度
                t_sim = SequenceMatcher(None, t_i, t_j).ratio() if (t_i and t_j) else 0
                # 关键词 Jaccard
                if kw_i and kw_j:
                    inter = len(kw_i & kw_j)
                    union = len(kw_i | kw_j)
                    kw_jac = inter / union if union > 0 else 0
                else:
                    kw_jac = 0
                # 综合得分
                score = t_sim * 0.7 + kw_jac * 0.3
                if t_sim >= TITLE_SIM_THRESHOLD or kw_jac >= KEYWORD_JACCARD_THRESHOLD or score >= COMBINED_THRESHOLD:
                    pairs.append((id_i, id_j, round(score, 3)))
        return pairs

    def _filter_known_pairs(self, pairs):
        """过滤已在 kp_relations 表中(任意 status)出现的对"""
        if not pairs:
            return []
        conn = self.db.get_connection(); c = conn.cursor()
        # 收集涉及的所有 kp id
        all_ids = set()
        for a, b, _ in pairs:
            all_ids.add(a); all_ids.add(b)
        if not all_ids:
            return pairs
        qmarks = ",".join("?" * len(all_ids))
        c.execute(f"""SELECT source_kp_id, target_kp_id FROM kp_relations
                      WHERE source_kp_id IN ({qmarks})
                         OR target_kp_id IN ({qmarks})""",
                  list(all_ids) + list(all_ids))
        existing = set()
        for row in c.fetchall():
            sid, tid = row[0], row[1]
            existing.add((min(sid, tid), max(sid, tid)))
        conn.close()
        # 过滤
        return [(a, b, s) for a, b, s in pairs if (min(a, b), max(a, b)) not in existing]

    def _aggregate_groups(self, pairs, kps):
        """用 union-find 把成对关系聚合为组"""
        parent = {}

        def find(x):
            while parent.get(x, x) != x:
                parent[x] = parent.get(parent[x], parent[x])
                x = parent[x]
            return x

        def union(x, y):
            rx, ry = find(x), find(y)
            if rx != ry:
                parent[rx] = ry

        pair_scores = {}
        for id_a, id_b, score in pairs:
            union(id_a, id_b)
            pair_scores[(min(id_a, id_b), max(id_a, id_b))] = score

        group_map = {}
        all_ids = set()
        for id_a, id_b, _ in pairs:
            all_ids.add(id_a); all_ids.add(id_b)
        for kid in all_ids:
            root = find(kid)
            if root not in group_map:
                group_map[root] = set()
            group_map[root].add(kid)

        groups = []
        for root, members in group_map.items():
            member_list = sorted(members)
            max_score = 0
            for i in range(len(member_list)):
                for j in range(i + 1, len(member_list)):
                    key = (member_list[i], member_list[j])
                    max_score = max(max_score, pair_scores.get(key, 0))
            groups.append({"members": member_list, "max_score": max_score})
        groups.sort(key=lambda g: -g["max_score"])
        return groups

    # ================================================================
    # 第二阶段:AI 六态判别(V3 主 + R1 兜底)
    # ================================================================
    def _ai_judge_groups(self, groups, kps):
        """对每组候选调用 AI 判别六态关系"""
        kp_map = {kp["id"]: kp for kp in kps}
        created = 0
        if not self.client:
            print(f"  [WARN] 无AI客户端,跳过AI判别(不创建关系)")
            return 0

        for idx, group in enumerate(groups, 1):
            members = group["members"][:MAX_GROUP_SIZE_FOR_AI]
            max_score = group["max_score"]
            print(f"  [{idx}/{len(groups)}] 判别组 (members={members}, score={max_score:.2f})")
            judgment = self._call_ai_judge(members, kp_map, model="deepseek-chat")
            if not judgment:
                continue
            confidence = judgment.get("confidence", 0)
            # confidence 低 → 升级 R1
            if confidence < CONFIDENCE_UPGRADE_THRESHOLD:
                print(f"     V3 confidence={confidence} < {CONFIDENCE_UPGRADE_THRESHOLD}, 升级 R1...")
                r1_judgment = self._call_ai_judge(members, kp_map, model="deepseek-reasoner")
                if r1_judgment:
                    r1_judgment["_source_model"] = "r1_fallback"
                    judgment = r1_judgment
                    confidence = judgment.get("confidence", 0)
            else:
                judgment["_source_model"] = "v3_main"

            relation_type = judgment.get("relation_type", "unrelated")
            # unrelated → 不建关系
            if relation_type == "unrelated":
                print(f"     unrelated, 跳过建组")
                continue

            # 写关系 + 可能建簇
            self._persist_judgment(members, max_score, judgment, kp_map)
            created += 1

        return created

    def _call_ai_judge(self, member_ids, kp_map, model="deepseek-chat"):
        """调 AI 判别一组关系,返回规范化 dict 或 None"""
        try:
            kp_descriptions = []
            for idx, kid in enumerate(member_ids, 1):
                kp = kp_map.get(kid)
                if not kp:
                    continue
                kws = list(kp.get("_keywords", set()))[:5]
                excerpt = (kp.get("original_excerpt") or "")[:300]
                summary = kp.get("_summary", "")[:200]
                src = kp.get("_source_file") or "未知"
                created = kp.get("created_at") or ""
                desc = (
                    f"【知识点{idx}】kp_id={kid}\n"
                    f"  标题: {kp['title']}\n"
                    f"  类型: {kp.get('content_type','未知')}\n"
                    f"  来源文件: {src}\n"
                    f"  入库时间: {created}\n"
                    f"  关键词: {', '.join(kws) if kws else '无'}\n"
                    f"  内容摘要: {summary if summary else '无'}\n"
                    f"  原文摘录: {excerpt if excerpt else '无'}"
                )
                kp_descriptions.append(desc)

            if len(kp_descriptions) < 2:
                return None

            user_content = (
                f"以下{len(kp_descriptions)}条知识点疑似相关,请按六态体系判别它们的关系:\n\n"
                + "\n\n".join(kp_descriptions)
            )

            # R1/V4-Pro 思考型不传 temperature(立规则 15)
            # v2.3.5-part2 修复:chat_with_json 真实签名是 model_override=,不是 model=
            # (立规则 9 第 22 次应验 — relation_analyzer 凭记忆写错 kwarg,7 组关系判别全失败)
            kwargs = {
                "system_prompt": RELATION_JUDGE_PROMPT["system_prompt"],
                "user_prompt": user_content,
                "model_override": model,
                "call_type": "relation_judge",
            }
            # 思考型(reasoner / r1 / thinking / v4-pro)不传 temperature
            m_lower = str(model).lower()
            is_thinking = ("reasoner" in m_lower or "r1" in m_lower
                           or "thinking" in m_lower or "v4-pro" in m_lower)
            if not is_thinking:
                kwargs["temperature"] = 0.1

            result = self.client.chat_with_json(**kwargs)
            parsed = result.get("parsed_json") if isinstance(result, dict) else None
            if not parsed or not isinstance(parsed, dict):
                return None
            # 规范化字段(防字段缺失)
            parsed.setdefault("relation_type", "unrelated")
            parsed.setdefault("confidence", 0)
            parsed.setdefault("topic", "")
            parsed.setdefault("reason", "")
            parsed.setdefault("evidence_signals", {})
            parsed.setdefault("cluster_suggestion", {"should_cluster": False})
            parsed.setdefault("fallback_action", "human_review")
            parsed.setdefault("human_review_reason", "")
            return parsed
        except Exception as e:
            print(f"     [AI判别失败] {type(e).__name__}: {e}")
            return None

    def _persist_judgment(self, member_ids, max_score, judgment, kp_map):
        """根据 AI 判定结果写库:
            1. fallback_action='human_review' 或 confidence 仍 < 阈值 → 关系标 pending_human_review
            2. 其他 → 关系标 pending(等老唐 UI 处理)
            3. cluster_suggestion.should_cluster=True → 同步建 cluster + members
        """
        relation_type = judgment.get("relation_type")
        confidence = judgment.get("confidence", 0)
        fallback = judgment.get("fallback_action", "human_review")
        ai_judgment_json = json.dumps(judgment, ensure_ascii=False)

        # 决定 status
        if fallback == "human_review" or confidence < CONFIDENCE_UPGRADE_THRESHOLD:
            relation_status = "pending_human_review"
        else:
            relation_status = "pending"

        # 是否建簇(决策3:human_review 不预建簇,等老唐裁决)
        cluster_id = None
        cs = judgment.get("cluster_suggestion") or {}
        if cs.get("should_cluster") and relation_status == "pending":
            cluster_type = self._map_relation_to_cluster_type(relation_type)
            if cluster_type:
                topic = (judgment.get("topic") or "")[:60]
                # 收集涉及文件名
                docs = list({kp_map[kid].get("_source_file", "")
                             for kid in member_ids if kid in kp_map})
                docs = [d for d in docs if d]
                cluster_id = self.db.create_consensus_cluster(
                    cluster_type=cluster_type,
                    topic=topic,
                    member_count=len(member_ids),
                    source_documents=docs,
                    strength_score=self._calc_strength_score(docs, member_ids),
                )
                # 写 members
                role_list = (cs.get("member_roles") or [])
                role_map = {r.get("kp_id"): r for r in role_list if isinstance(r, dict)}
                for kid in member_ids:
                    rrec = role_map.get(kid) or {}
                    role = rrec.get("role", "branch")
                    seq = int(rrec.get("sequence_order") or 0)
                    self.db.add_cluster_member(cluster_id, kid, role=role, sequence_order=seq)

        # 写关系边(成员两两全连接;关系类型一致)
        for i in range(len(member_ids)):
            for j in range(i + 1, len(member_ids)):
                a, b = member_ids[i], member_ids[j]
                self.db.add_kp_relation(
                    source_kp_id=a, target_kp_id=b,
                    relation_type=relation_type,
                    similarity_score=max_score,
                    ai_judgment=ai_judgment_json,
                    cluster_id=cluster_id,
                    status=relation_status,
                    created_by="ai",
                )
        # 更新 kp.relation_count(增量+N)
        for kid in member_ids:
            self.db.bump_kp_relation_count(kid, len(member_ids) - 1)

    def _map_relation_to_cluster_type(self, relation_type):
        """关系类型 → 聚类类型"""
        mp = {
            "cross_file_consensus": "consensus",
            "policy_evolution": "evolution_chain",
            "hierarchical_refinement": "refinement_tree",
        }
        return mp.get(relation_type)  # 同源冗余/冲突/互补 不建簇

    def _calc_strength_score(self, source_documents, member_ids):
        """计算共识强度 0-100
        简单线性: 文件数 * 20(封顶 100), 成员数 * 5 调节
        """
        doc_count = len(set(source_documents))
        member_count = len(member_ids)
        score = min(100, doc_count * 20 + min(20, member_count * 5))
        return float(score)


def main():
    """CLI 独立运行: 全库扫描"""
    try:
        import json
        cfg_path = PROJECT_ROOT / "config" / "settings.json"
        cfg = {}
        if cfg_path.exists():
            with open(cfg_path, "r", encoding="utf-8") as f:
                cfg = json.load(f)
        client = None
        try:
            from scripts.deepseek_client import DeepSeekClient
            client = DeepSeekClient(cfg)
        except Exception as e:
            print(f"  [WARN] 无法初始化 DeepSeekClient: {e}, 仅做本地粗筛")
        analyzer = RelationAnalyzer(client=client)
        n = analyzer.scan_full()
        print(f"\n  扫描完成,新建关系组: {n}")
    except Exception as e:
        print(f"\n  [ERROR] {type(e).__name__}: {e}")
        import traceback
        traceback.print_exc()
    input("\n按回车键退出...")


if __name__ == "__main__":
    main()
