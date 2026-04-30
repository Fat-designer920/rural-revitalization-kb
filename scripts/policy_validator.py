"""
policy_validator.py - 政策依赖校验模块
路径：scripts/policy_validator.py
版本：v2.3.5-part2-hotfix1.1 - 版本统一(Claude Code 系统修复)

功能：
  - 扫描非政策类知识点中的政策引用（V3模型）
  - 将识别出的政策引用与知识库中已有政策知识点匹配
  - 未匹配的政策引用 → 锁定就绪度为草稿级 + 提供查找指引
  - 政策类知识点自动标记为"不涉及政策依赖"

设计原则：
  - 纯操盘技巧类经验不受政策校验限制（AI判断）
  - AI不确定"是否涉及政策"时 → 标记待确认，不自行决定
  - 政策查找建议用固定指引模板（按层级匹配官网），不接搜索API
"""

import json, sys
from pathlib import Path

PROJECT_ROOT = Path(__file__).parent.parent
sys.path.insert(0, str(PROJECT_ROOT))

from scripts.deepseek_client import DeepSeekClient, CostLimitExceeded
from scripts.db_manager import DatabaseManager
from scripts.prompts.prompt_templates import POLICY_SCAN_PROMPT
from scripts.tag_config import POLICY_LOOKUP_GUIDE


class PolicyValidator:
    """政策依赖校验器：扫描知识点中的政策引用，匹配知识库，标记校验状态。

    policy_validated 状态码：
      0 = 未检查
      1 = 已验证通过（所有引用政策均在库中）
      2 = 待验证（有未匹配的政策引用）
      3 = 人工豁免（审核时人工标记为不需要政策校验）
      4 = 不涉及政策（纯操盘技巧/政策类知识点本身）
    """

    def __init__(self, db=None, client=None):
        if db is None:
            self.db = DatabaseManager()
        else:
            self.db = db

        if client is None:
            config_path = PROJECT_ROOT / "config" / "settings.json"
            with open(config_path, "r", encoding="utf-8") as f:
                config = json.load(f)
            self.client = DeepSeekClient(config)
        else:
            self.client = client

    # ================================================================
    # 主入口：批量校验一个文件提取出的所有知识点
    # ================================================================

    def validate_batch(self, kps, kps_info, content_type):
        """对一批知识点进行政策依赖校验。

        Args:
            kps: 原始AI提取的知识点列表（含完整内容）
            kps_info: 写入DB后的info列表（含kp_id）
            content_type: 文件内容类型（policy/case/experience/tool/data）

        Returns:
            validated_count: 成功校验的数量
        """
        if not kps or not kps_info:
            return 0

        # === 政策类知识点：自动标记为"不涉及政策依赖" ===
        if content_type == "policy":
            count = self._mark_policy_type(kps_info)
            print(f"     政策类知识点{count}条,自动标记为不涉及政策依赖")
            return count

        # === 非政策类：调用V3扫描政策引用 ===
        scan_results = self._scan_policy_references(kps, kps_info)
        if not scan_results:
            return 0

        # === 逐条匹配知识库中的政策 ===
        validated_count = 0
        unmatched_total = 0

        for item in scan_results:
            idx = item.get("kp_index", -1)
            involves_policy = item.get("involves_policy", "uncertain")
            referenced = item.get("referenced_policies", [])

            if idx < 0 or idx >= len(kps_info):
                continue

            kp_id = kps_info[idx].get("kp_id")
            if not kp_id:
                continue

            # --- 不涉及政策 ---
            if involves_policy == "no":
                ok = self._update_kp(kp_id, [], 4)
                if ok:
                    validated_count += 1
                continue

            # --- AI不确定 ---
            if involves_policy == "uncertain":
                deps_json = self._build_uncertain_deps(referenced)
                ok = self._update_kp(kp_id, deps_json, 0)
                if ok:
                    validated_count += 1
                continue

            # --- 涉及政策：逐条匹配 ---
            matched_deps, has_unmatched = self._match_policies(referenced)
            if has_unmatched:
                unmatched_total += sum(1 for d in matched_deps if not d.get("matched"))

            status = 2 if has_unmatched else 1  # 2=待验证, 1=已验证
            ok = self._update_kp(kp_id, matched_deps, status, lock_draft=has_unmatched)
            if ok:
                validated_count += 1

        # === 汇总输出 ===
        if unmatched_total > 0:
            print(f"     [注意] {unmatched_total}个政策引用未在知识库中找到对应政策")
            print(f"     建议: 先导入相关政策文件,再审核这些知识点")

        return validated_count

    # ================================================================
    # 政策类知识点批量标记
    # ================================================================

    def _mark_policy_type(self, kps_info):
        """政策类知识点不需要政策依赖校验，直接标记。"""
        count = 0
        for info in kps_info:
            kp_id = info.get("kp_id")
            if kp_id:
                ok = self._update_kp(kp_id, [], 4)
                if ok:
                    count += 1
        return count

    # ================================================================
    # V3扫描政策引用
    # ================================================================

    def _scan_policy_references(self, kps, kps_info):
        """调用V3模型批量扫描知识点中的政策引用。"""
        # 构建批量扫描的JSON（只传必要信息，控制token）
        kp_batch = []
        for i, kp in enumerate(kps):
            # 从不同类型的知识点中提取核心内容
            core = (kp.get("core_provisions", "")
                    or kp.get("core_strategy", "")
                    or kp.get("core_conclusion", "")
                    or kp.get("detailed_method", "")
                    or "")

            kp_batch.append({
                "index": i,
                "title": kp.get("title", ""),
                "excerpt": (kp.get("original_excerpt") or "")[:300],
                "core_content": str(core)[:300]
            })

        kp_json = json.dumps(kp_batch, ensure_ascii=False, indent=2)

        prompt = POLICY_SCAN_PROMPT
        up = prompt["user_prompt_template"].format(
            kp_count=len(kp_batch),
            knowledge_points_json=kp_json
        )

        try:
            ai = self.client.chat_with_json(
                prompt["system_prompt"], up, temperature=0.2,
                call_type="policy_scan", model_override="deepseek-chat")

            parsed = ai.get("parsed_json")
            cost = ai.get("estimated_cost", 0)

            if not parsed or not isinstance(parsed, dict):
                print(f"     政策扫描返回格式异常(花费{cost:.4f}元)")
                return None

            results = parsed.get("scan_results", [])
            print(f"     政策扫描完成: {len(results)}条结果(花费{cost:.4f}元)")

            # 统计
            has_policy = sum(1 for r in results if r.get("involves_policy") == "yes")
            no_policy = sum(1 for r in results if r.get("involves_policy") == "no")
            uncertain = sum(1 for r in results if r.get("involves_policy") == "uncertain")
            print(f"     涉及政策{has_policy}条 | 不涉及{no_policy}条 | 待确认{uncertain}条")

            return results

        except CostLimitExceeded:
            print(f"     费用已达上限,跳过政策扫描")
            return None
        except Exception as e:
            print(f"     政策扫描失败: {e}")
            return None

    # ================================================================
    # 政策匹配
    # ================================================================

    def _match_policies(self, referenced_policies):
        """将V3识别出的政策引用与知识库中的政策知识点匹配。

        Returns:
            (matched_deps_list, has_unmatched)
        """
        matched_deps = []
        has_unmatched = False

        for ref in referenced_policies:
            policy_number = ref.get("policy_number", "")
            policy_name = ref.get("policy_name", "")
            policy_level = ref.get("policy_level", "")

            # 在知识库中搜索
            match = self._find_policy_in_kb(policy_number, policy_name)

            if match:
                matched_deps.append({
                    "name": policy_name or policy_number,
                    "number": policy_number,
                    "matched": True,
                    "kb_id": match["id"],
                    "kb_title": match["title"]
                })
            else:
                guide = self._get_lookup_guide(policy_level)
                matched_deps.append({
                    "name": policy_name or policy_number,
                    "number": policy_number,
                    "matched": False,
                    "policy_level": policy_level,
                    "lookup_guide": guide
                })
                has_unmatched = True

        return matched_deps, has_unmatched

    def _find_policy_in_kb(self, policy_number, policy_name):
        """在知识库中查找匹配的政策知识点。

        搜索策略：先精确匹配文号，再模糊匹配名称。
        搜索范围：content_type='policy' 且 review_status in ('pending','confirmed')
        """
        conn = self.db.get_connection()
        c = conn.cursor()

        searches = []
        if policy_number:
            searches.append(policy_number)
            # 尝试不同的括号写法（全角/半角）
            alt = policy_number.replace("〔", "[").replace("〕", "]")
            if alt != policy_number:
                searches.append(alt)
        if policy_name and len(policy_name) >= 4:
            searches.append(policy_name)

        for term in searches:
            like_term = f"%{term}%"
            c.execute("""
                SELECT id, title
                FROM knowledge_points
                WHERE content_type='policy'
                  AND review_status IN ('pending','confirmed')
                  AND (title LIKE ? OR original_excerpt LIKE ? OR ai_extracted_content LIKE ?)
                LIMIT 1
            """, (like_term, like_term, like_term))
            row = c.fetchone()
            if row:
                conn.close()
                return {"id": row["id"], "title": row["title"]}

        conn.close()
        return None

    def _get_lookup_guide(self, policy_level):
        """根据政策层级返回查找指引文本。"""
        if not policy_level:
            return POLICY_LOOKUP_GUIDE.get("default", "请查询相关政策文件")

        for key, guide in POLICY_LOOKUP_GUIDE.items():
            if key in policy_level:
                return guide

        return POLICY_LOOKUP_GUIDE.get("default", "请查询相关政策文件")

    # ================================================================
    # 不确定项处理
    # ================================================================

    def _build_uncertain_deps(self, referenced):
        """对AI不确定的政策引用，构建待确认的依赖列表。"""
        deps = []
        for ref in referenced:
            deps.append({
                "name": ref.get("policy_name", "") or ref.get("policy_number", ""),
                "number": ref.get("policy_number", ""),
                "matched": False,
                "uncertain": True,
                "policy_level": ref.get("policy_level", ""),
                "lookup_guide": "AI不确定是否涉及政策,请人工判断"
            })
        return deps

    # ================================================================
    # 数据库更新
    # ================================================================

    def _update_kp(self, kp_id, deps, status, lock_draft=False):
        """更新知识点的政策校验结果。

        Args:
            kp_id: 知识点ID
            deps: 政策依赖列表（list of dict）
            status: policy_validated状态码
            lock_draft: 是否锁定就绪度为draft

        Returns:
            True if success
        """
        try:
            update_kw = {
                "policy_dependencies": json.dumps(deps, ensure_ascii=False),
                "policy_validated": status
            }

            if lock_draft:
                kp_detail = self.db.get_knowledge_point(kp_id)
                if kp_detail and kp_detail.get("content_readiness") != "draft":
                    update_kw["content_readiness"] = "draft"
                    title = kp_detail.get("title", "")[:20]
                    print(f"     [锁定] KP#{kp_id}({title}...) 有未验证政策依赖,就绪度降为草稿级")

            self.db.update_knowledge_point(kp_id, **update_kw)
            return True

        except Exception as e:
            print(f"     ! 政策校验写入失败(ID={kp_id}): {e}")
            return False

    # ================================================================
    # 独立运行：对已入库知识点补跑政策校验
    # ================================================================

    def run_standalone(self):
        """对已入库但未做政策校验的知识点补跑校验。"""
        conn = self.db.get_connection()
        c = conn.cursor()

        c.execute("""
            SELECT id, title, content_type, original_excerpt, ai_extracted_content,
                   policy_validated
            FROM knowledge_points
            WHERE review_status IN ('pending', 'confirmed')
              AND (policy_validated IS NULL OR policy_validated = 0)
              AND content_type != 'policy'
            ORDER BY id
        """)
        rows = [dict(r) for r in c.fetchall()]
        conn.close()

        if not rows:
            print("  无需校验的知识点（所有非政策类知识点均已校验）")
            return

        print(f"  发现{len(rows)}条未校验的非政策类知识点")

        # 构建kps和kps_info结构以复用validate_batch逻辑
        kps = []
        kps_info = []
        for row in rows:
            ai_content = {}
            try:
                raw = row.get("ai_extracted_content", "{}")
                if isinstance(raw, str):
                    ai_content = json.loads(raw)
            except (json.JSONDecodeError, ValueError):
                pass

            kps.append({
                "title": row["title"],
                "original_excerpt": row.get("original_excerpt", ""),
                "core_provisions": ai_content.get("core_provisions", ""),
                "core_strategy": ai_content.get("core_strategy", ""),
                "core_conclusion": ai_content.get("core_conclusion", ""),
                "detailed_method": ai_content.get("detailed_method", ""),
            })
            kps_info.append({
                "kp_id": row["id"],
                "title": row["title"],
            })

        # 分批处理（每批最多20条，控制V3 token）
        batch_size = 20
        total_validated = 0
        for start in range(0, len(kps), batch_size):
            batch_kps = kps[start:start + batch_size]
            batch_info = kps_info[start:start + batch_size]
            # 重新编号index
            for i, kp in enumerate(batch_kps):
                kp["_batch_index"] = i

            print(f"\n  批次{start // batch_size + 1}: 校验第{start + 1}-{min(start + batch_size, len(kps))}条...")
            count = self.validate_batch(batch_kps, batch_info, "experience")  # 按非政策类处理
            total_validated += count

        print(f"\n  补跑完成: 共校验{total_validated}条知识点")


# ================================================================
# 独立运行入口（供bat文件直接调用）
# ================================================================
if __name__ == "__main__":
    print("\n  政策依赖补跑校验")
    print("  对已入库但未校验的知识点补跑政策校验")
    print("=" * 50)
    pv = PolicyValidator()
    pv.run_standalone()
