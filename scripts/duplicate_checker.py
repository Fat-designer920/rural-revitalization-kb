"""
duplicate_checker.py - 重复知识点检测模块
路径：scripts/duplicate_checker.py
版本：v2.3.0-part3.8 - 删除 main 冗余 migrate import（立规则 52 条）

v2.3.0-part3.8 变更：
  - 删除 main 内 migrate_v211_dup import 整段（5 行）
    根因：api_server.py 启动 Step 2 已统一调过此迁移，duplicate_checker
    作为 CLI 独立运行时走 DatabaseManager 初始化亦已覆盖，再调是重复
  - 对应 E2E 诊断包 v2.3.0-part3.7 报告的 duplicate_checker.py:512 warning 消失

v2.3.0-part1 变更：
  - 新增 scan_recent(days=7) 方法：扫最近 N 天 created_at 的知识点 → 转调 scan_incremental
    用途：工具箱"智能重复检测"三选一之"最近一周"模式
    实现：只查 created_at 在窗口内的 id 列表，让复用的 scan_incremental 走本地粗筛+V3精判

功能：
  - 本地粗筛：标题相似度(SequenceMatcher) + 关键词重叠(Jaccard)
  - V3精判：判断关系类型(重复/版本更替/互补/冲突/无关)
  - v2.2.2: 无client不建组(防假阳性), 互补类型不建组, 阈值收紧
  - v2.2.2: reset_and_rescan清理重扫功能
  - v2.3.0-part1: scan_recent 支持"最近一周"场景
  - 支持全库扫描、增量扫描(提取后自动)、最近窗口扫描
  - 结果存入duplicate_groups表供审核界面处理
"""
import os, sys, json, re
from pathlib import Path
from difflib import SequenceMatcher
from datetime import datetime

PROJECT_ROOT = Path(__file__).parent.parent
sys.path.insert(0, str(PROJECT_ROOT))

from scripts.db_manager import DatabaseManager
from scripts.prompts.prompt_templates import DUPLICATE_JUDGE_PROMPT

# === 阈值配置 ===
TITLE_SIM_THRESHOLD = 0.65    # 标题相似度阈值(v2.2.2上调,政策文件术语重叠大)
KEYWORD_JACCARD_THRESHOLD = 0.50  # 关键词Jaccard系数阈值
COMBINED_THRESHOLD = 0.65    # 综合得分阈值 (title*0.7 + keyword*0.3)
MAX_GROUP_SIZE_FOR_V3 = 6    # 发送给V3的最大组大小


class DuplicateChecker:
    """重复知识点检测器"""

    def __init__(self, db=None, client=None):
        self.db = db or DatabaseManager()
        self.client = client  # DeepSeekClient, 可选(无client时只做本地粗筛)

    # ================================================================
    # 公开接口
    # ================================================================
    def scan_full(self):
        """全库扫描：检测所有未忽略知识点之间的疑似重复"""
        print(f"\n  [重复检测] 全库扫描开始...")
        kps = self._load_all_kps()
        if len(kps) < 2:
            print(f"  知识点不足2条，无需检测")
            return 0

        print(f"  加载{len(kps)}条知识点")

        # 第一阶段：本地粗筛
        candidate_pairs = self._local_prefilter(kps)
        if not candidate_pairs:
            print(f"  未发现疑似重复")
            return 0

        # 过滤已知的重复组
        candidate_pairs = self._filter_known_pairs(candidate_pairs)
        if not candidate_pairs:
            print(f"  所有疑似重复已在处理列表中")
            return 0

        # 聚合为组
        groups = self._aggregate_groups(candidate_pairs, kps)
        print(f"  粗筛结果: {len(candidate_pairs)}对疑似重复 -> {len(groups)}组")

        # 第二阶段：V3精判
        created = self._v3_judge_groups(groups, kps)
        print(f"  [重复检测] 完成, 新建{created}组重复记录")
        return created

    def scan_incremental(self, new_kp_ids):
        """增量扫描：新提取的知识点与全库对比"""
        if not new_kp_ids:
            return 0

        kps = self._load_all_kps()
        new_ids_set = set(new_kp_ids)
        if len(kps) < 2:
            return 0

        print(f"\n     [Step 8] 重复检测(增量: {len(new_ids_set)}条新知识点 vs 全库{len(kps)}条)...")

        # 只计算涉及新知识点的配对
        candidate_pairs = self._local_prefilter(kps, only_involving=new_ids_set)
        if not candidate_pairs:
            print(f"     未发现疑似重复")
            return 0

        candidate_pairs = self._filter_known_pairs(candidate_pairs)
        if not candidate_pairs:
            return 0

        groups = self._aggregate_groups(candidate_pairs, kps)
        print(f"     粗筛: {len(candidate_pairs)}对 -> {len(groups)}组")

        created = self._v3_judge_groups(groups, kps)
        if created > 0:
            print(f"     发现{created}组疑似重复，请在审核界面处理")
        return created

    def scan_recent(self, days=7):
        """
        v2.3.0-part1: 最近 N 天窗口扫描
        扫 knowledge_points.created_at 在最近 days 天内的 kp，作为"新知识点"
        与全库对比（内部转调 scan_incremental 复用 V3 精判流程）。
        参数：
          days=7 表示最近一周（默认），可传 1/7/30 等
        返回值：创建的疑似重复组数量
        """
        if days is None or days <= 0:
            print(f"  [重复检测] days 参数无效: {days}")
            return 0

        conn = self.db.get_connection()
        c = conn.cursor()
        c.execute("""SELECT id FROM knowledge_points
                     WHERE review_status IN ('pending','confirmed')
                       AND (is_outdated IS NULL OR is_outdated=0)
                       AND created_at >= datetime('now','localtime',?)
                     ORDER BY id""",
                  (f'-{int(days)} days',))
        recent_ids = [r[0] for r in c.fetchall()]
        conn.close()

        print(f"\n  [重复检测] 最近 {days} 天窗口：查到 {len(recent_ids)} 条新知识点")
        if not recent_ids:
            return 0

        # 复用 scan_incremental 的全流程（本地粗筛+V3精判+写 duplicate_groups）
        return self.scan_incremental(recent_ids)

    def reset_and_rescan(self):
        """v2.2.2: 清理所有pending假阳性后重新全库扫描(含V3精判)"""
        # 第一步: 清理现有pending组
        dismissed = self.db.dismiss_all_pending_duplicates()
        print(f"\n  [重复检测] 已清理{dismissed}组旧的待处理结果")

        # 第二步: 全库重新扫描(V3精判)
        if not self.client:
            print(f"  [ERROR] 清理重扫需要AI客户端,请检查API配置")
            return 0

        return self.scan_full()

    # ================================================================
    # 第一阶段：本地粗筛
    # ================================================================
    def _load_all_kps(self):
        """加载所有有效知识点(非忽略、非过时)"""
        conn = self.db.get_connection()
        c = conn.cursor()
        c.execute("""SELECT id, title, content_type, source_file_id,
                     suggested_keywords, final_keywords,
                     original_excerpt, ai_extracted_content
                     FROM knowledge_points
                     WHERE review_status IN ('pending','confirmed')
                       AND (is_outdated IS NULL OR is_outdated=0)
                     ORDER BY id""")
        rows = [dict(r) for r in c.fetchall()]
        conn.close()

        # 预处理关键词
        for kp in rows:
            kws = set()
            for field in ["final_keywords", "suggested_keywords"]:
                raw = kp.get(field)
                if raw:
                    try:
                        items = json.loads(raw) if isinstance(raw, str) else raw
                        if isinstance(items, list):
                            for k in items:
                                if isinstance(k, str) and k.strip():
                                    kws.add(k.strip())
                    except:
                        pass
            kp["_keywords"] = kws
            # 提取内容摘要(前200字)
            kp["_summary"] = self._get_summary(kp)
        return rows

    def _get_summary(self, kp):
        """提取知识点内容摘要"""
        # 优先用ai_extracted_content
        raw = kp.get("ai_extracted_content")
        if raw:
            try:
                obj = json.loads(raw) if isinstance(raw, str) else raw
                if isinstance(obj, dict):
                    for key in ["scope", "core_content", "key_requirements",
                                "background", "summary", "content"]:
                        v = obj.get(key)
                        if v and isinstance(v, str) and len(v) > 20:
                            return v[:200]
            except:
                pass
        # 退而求其次用original_excerpt
        excerpt = kp.get("original_excerpt", "")
        if excerpt and len(excerpt) > 20:
            return excerpt[:200]
        return ""

    def _local_prefilter(self, kps, only_involving=None):
        """本地粗筛：标题相似度+关键词重叠"""
        pairs = []
        n = len(kps)
        for i in range(n):
            for j in range(i + 1, n):
                a, b = kps[i], kps[j]

                # 如果是增量模式，至少一条要是新的
                if only_involving:
                    if a["id"] not in only_involving and b["id"] not in only_involving:
                        continue

                # 标题相似度
                title_sim = SequenceMatcher(None, a["title"], b["title"]).ratio()

                # 关键词Jaccard
                kw_a, kw_b = a["_keywords"], b["_keywords"]
                if kw_a and kw_b:
                    intersection = len(kw_a & kw_b)
                    union = len(kw_a | kw_b)
                    kw_jaccard = intersection / union if union > 0 else 0
                else:
                    kw_jaccard = 0

                # 综合得分
                combined = title_sim * 0.7 + kw_jaccard * 0.3

                # 任一通道达标即为候选
                if (title_sim >= TITLE_SIM_THRESHOLD or
                    kw_jaccard >= KEYWORD_JACCARD_THRESHOLD or
                    combined >= COMBINED_THRESHOLD):
                    pairs.append((a["id"], b["id"], round(combined, 3)))

        return pairs

    def _filter_known_pairs(self, pairs):
        """排除已在duplicate_groups中的配对"""
        existing = self.db.get_duplicate_groups(status=None)  # 获取所有状态
        known_pairs = set()
        for g in existing:
            try:
                members = json.loads(g["member_ids"]) if isinstance(g["member_ids"], str) else g["member_ids"]
                for i in range(len(members)):
                    for j in range(i + 1, len(members)):
                        pair = tuple(sorted([members[i], members[j]]))
                        known_pairs.add(pair)
            except:
                pass

        filtered = []
        for id_a, id_b, score in pairs:
            pair = tuple(sorted([id_a, id_b]))
            if pair not in known_pairs:
                filtered.append((id_a, id_b, score))
        return filtered

    # ================================================================
    # 聚合为组（Union-Find）
    # ================================================================
    def _aggregate_groups(self, pairs, kps):
        """将配对聚合为组（Union-Find算法）"""
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

        # 记录每对的分数
        pair_scores = {}
        for id_a, id_b, score in pairs:
            union(id_a, id_b)
            pair_scores[(min(id_a, id_b), max(id_a, id_b))] = score

        # 聚合
        group_map = {}
        all_ids = set()
        for id_a, id_b, _ in pairs:
            all_ids.add(id_a)
            all_ids.add(id_b)
        for kid in all_ids:
            root = find(kid)
            if root not in group_map:
                group_map[root] = set()
            group_map[root].add(kid)

        # 构建组列表
        groups = []
        for root, members in group_map.items():
            member_list = sorted(members)
            # 取组内最高相似度
            max_score = 0
            for i in range(len(member_list)):
                for j in range(i + 1, len(member_list)):
                    key = (member_list[i], member_list[j])
                    max_score = max(max_score, pair_scores.get(key, 0))
            groups.append({
                "members": member_list,
                "max_score": max_score
            })

        # 按相似度降序
        groups.sort(key=lambda g: -g["max_score"])
        return groups

    # ================================================================
    # 第二阶段：V3精判
    # ================================================================
    def _v3_judge_groups(self, groups, kps):
        """对每组候选调用V3判断关系类型"""
        kp_map = {kp["id"]: kp for kp in kps}
        created = 0

        # v2.2.2: 无client时不建组(避免大量假阳性)
        if not self.client:
            print(f"  [WARN] 无AI客户端,跳过V3精判(不创建重复组)")
            return 0

        for group in groups:
            members = group["members"]
            max_score = group["max_score"]

            # 限制发送给V3的组大小
            if len(members) > MAX_GROUP_SIZE_FOR_V3:
                members = members[:MAX_GROUP_SIZE_FOR_V3]

            judgment = self._call_v3_judge(members, kp_map)
            relation_type = judgment.get("relation_type", "duplicate")

            # v2.2.2: 无关和互补都不建组(互补知识点各有价值不需要去重)
            if relation_type in ("unrelated", "complementary"):
                continue

            self.db.add_duplicate_group(
                member_ids=members,
                relation_type=relation_type,
                ai_judgment=judgment,
                similarity_score=max_score
            )
            created += 1

        return created

    def _call_v3_judge(self, member_ids, kp_map):
        """调用V3判断一组知识点的关系"""
        try:
            # 构建每条知识点的摘要信息
            kp_descriptions = []
            for idx, kid in enumerate(member_ids, 1):
                kp = kp_map.get(kid)
                if not kp:
                    continue
                kws = list(kp.get("_keywords", set()))[:5]
                # v2.2.2: 加入原文摘录让V3看到更完整的上下文
                excerpt = (kp.get("original_excerpt") or "")[:300]
                summary = kp.get("_summary", "")[:200]
                desc = (
                    f"【知识点{idx}】ID={kid}\n"
                    f"  标题: {kp['title']}\n"
                    f"  类型: {kp.get('content_type','未知')}\n"
                    f"  关键词: {', '.join(kws) if kws else '无'}\n"
                    f"  内容摘要: {summary if summary else '无'}\n"
                    f"  原文摘录: {excerpt if excerpt else '无'}"
                )
                kp_descriptions.append(desc)

            if len(kp_descriptions) < 2:
                return {"relation_type": "unrelated", "reason": "知识点不足"}

            user_content = (
                f"以下{len(kp_descriptions)}条知识点疑似重复或高度相关，请分析它们的关系:\n\n"
                + "\n\n".join(kp_descriptions)
            )

            result = self.client.chat_with_json(
                system_prompt=DUPLICATE_JUDGE_PROMPT["system"],
                user_prompt=user_content,
                temperature=0.1,
                max_tokens=1024,
                call_type="duplicate_judge",
                model_override="deepseek-chat"  # V3模型
            )

            parsed = result.get("parsed_json")
            if parsed and isinstance(parsed, dict):
                # 校验relation_type合法性
                valid_types = {"duplicate", "superseded", "complementary", "conflicting", "unrelated"}
                rt = parsed.get("relation_type", "")
                if rt not in valid_types:
                    parsed["relation_type"] = "duplicate"
                # 确保suggested_keep_id是组内有效ID
                ski = parsed.get("suggested_keep_id")
                if ski and ski not in member_ids:
                    parsed["suggested_keep_id"] = member_ids[0]
                return parsed
            else:
                return {
                    "relation_type": "duplicate",
                    "reason": "V3判断失败,默认为重复",
                    "suggested_keep_id": member_ids[0],
                    "merge_note": ""
                }

        except Exception as e:
            print(f"       V3判断出错: {e}")
            return {
                "relation_type": "duplicate",
                "reason": f"V3调用异常({e}),默认为重复",
                "suggested_keep_id": member_ids[0],
                "merge_note": ""
            }

    # ================================================================
    # 生成报告（bat调用时显示）
    # ================================================================
    def print_report(self):
        """打印重复检测报告"""
        summary = self.db.get_duplicate_summary()
        pending = summary.get("pending", 0)
        resolved = summary.get("resolved", 0)
        dismissed = summary.get("dismissed", 0)
        total = pending + resolved + dismissed

        print(f"\n{'=' * 50}")
        print(f"  重复检测报告")
        print(f"{'=' * 50}")
        print(f"  总计: {total}组")
        if pending > 0:
            print(f"  待处理: {pending}组")
        if resolved > 0:
            print(f"  已处理: {resolved}组")
        if dismissed > 0:
            print(f"  已排除: {dismissed}组")

        if pending > 0:
            groups = self.db.get_duplicate_groups(status="pending")
            # 关系类型名称
            rtn = {"duplicate": "重复", "superseded": "版本更替",
                   "complementary": "互补", "conflicting": "冲突"}
            print(f"\n  --- 待处理详情 ---")
            for g in groups[:20]:  # 最多显示20组
                members = json.loads(g["member_ids"]) if isinstance(g["member_ids"], str) else g["member_ids"]
                rt = g.get("relation_type", "unknown")
                rt_name = rtn.get(rt, rt)
                score = g.get("similarity_score", 0)
                judgment = {}
                try:
                    judgment = json.loads(g["ai_judgment"]) if isinstance(g["ai_judgment"], str) else g.get("ai_judgment", {})
                except:
                    pass
                reason = judgment.get("reason", "")

                print(f"\n  组#{g['id']} [{rt_name}] 相似度:{score:.2f}")
                if reason:
                    print(f"    AI判断: {reason[:80]}")
                # 显示成员标题
                conn = self.db.get_connection()
                cur = conn.cursor()
                for mid in members:
                    cur.execute("SELECT title, content_type FROM knowledge_points WHERE id=?", (mid,))
                    row = cur.fetchone()
                    if row:
                        print(f"    - #{mid} [{row['content_type']}] {row['title'][:50]}")
                    else:
                        print(f"    - #{mid} (已删除)")
                conn.close()

            if pending > 20:
                print(f"\n  ... 还有{pending - 20}组未显示")

            print(f"\n  => 请在审核界面处理待处理的重复组")
        else:
            print(f"\n  当前无待处理的疑似重复")
        print(f"{'=' * 50}")


# ================================================================
# 独立运行入口（bat调用）
# ================================================================
def main():
    print(f"\n{'=' * 60}")
    print(f"  乡村振兴知识库 - 重复知识点检测 v2.1.1 F039")
    print(f"  检测方式: 本地粗筛 + V3 AI精判")
    print(f"  检测时间: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}")
    print(f"{'=' * 60}")

    # 自动执行迁移（由 api_server.py 启动兜底统一处理，此处不再重复调用）

    try:
        from scripts.deepseek_client import DeepSeekClient, CostLimitExceeded
        client = DeepSeekClient()
        usage = client.get_today_usage()
        print(f"\n  今日API费用: {usage['today_cost']:.2f}元 / {usage['daily_limit']:.0f}元上限")
    except Exception as e:
        print(f"\n  [WARN] 无法初始化AI客户端: {e}")
        print(f"  将仅使用本地粗筛(无V3精判)")
        client = None

    checker = DuplicateChecker(client=client)

    # 全库扫描
    try:
        created = checker.scan_full()
    except Exception as e:
        print(f"\n  [ERROR] 扫描出错: {e}")
        import traceback
        traceback.print_exc()
        created = 0

    # 显示报告
    checker.print_report()


if __name__ == "__main__":
    try:
        main()
    except KeyboardInterrupt:
        print(f"\n\n  已取消操作。")
    except Exception as e:
        print(f"\n  [ERROR] {e}")
    input("\n按回车键退出...")
