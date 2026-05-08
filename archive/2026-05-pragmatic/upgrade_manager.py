"""
upgrade_manager.py - 版本升级管理器
路径：scripts/upgrade_manager.py
版本：v2.3.7
"""

import os
import sys
import json
import shutil
from pathlib import Path
from datetime import datetime

PROJECT_ROOT = Path(__file__).parent.parent
sys.path.insert(0, str(PROJECT_ROOT))

from scripts.db_manager import DatabaseManager
from scripts.deepseek_client import DeepSeekClient, CostLimitExceeded
from scripts.backup_manager import BackupManager
from scripts.tag_config import (
    get_layer1_for_prompt, get_layer2_for_prompt,
    get_layer1_tag_names, CONTENT_READINESS, SOURCE_AUTHORITY
)


class UpgradeManager:

    VALID_LAYER1_NAMES = set(get_layer1_tag_names())
    VALID_READINESS = set(CONTENT_READINESS.keys())
    VALID_AUTHORITY = set(SOURCE_AUTHORITY.keys())

    def __init__(self):
        config_path = PROJECT_ROOT / "config" / "settings.json"
        with open(config_path, "r", encoding="utf-8") as f:
            self.config = json.load(f)
        self.db = DatabaseManager()
        self.client = DeepSeekClient(self.config)
        self.backup_mgr = BackupManager()
        self.completed = Path(self.config.get("completed_path",
                                               str(PROJECT_ROOT / "data" / "completed")))
        self.processing = Path(self.config.get("processing_path",
                                                str(PROJECT_ROOT / "data" / "processing")))

    # ==============================================================
    # 主流程
    # ==============================================================

    def run(self):
        print("")
        print("=" * 60)
        print("  稻也 - 架构升级迁移工具 v2.1.0-b")
        print("  启动时间: {}".format(datetime.now().strftime("%Y-%m-%d %H:%M:%S")))
        print("=" * 60)

        # --- Step 1: 自动备份 ---
        print("\n[Step 1/6] 自动备份当前数据库...")
        backup_path = self.backup_mgr.create_backup(label="before_upgrade")
        if backup_path:
            print("  备份完成, 如出问题可随时回滚")
        else:
            print("  [警告] 备份失败!")
            confirm = input("  是否仍然继续? (输入 y 继续, 其他取消): ").strip().lower()
            if confirm != "y":
                print("  已取消升级"); return

        # --- Step 2: 规则检查 ---
        print("\n[Step 2/6] 规则检查 (免费, 秒级)...")
        all_kps = self.db.get_all_knowledge_for_upgrade()
        if not all_kps:
            print("  知识库中没有知识点, 无需升级"); return

        report = self._rule_check(all_kps)

        # --- Step 3: 展示报告 ---
        self._show_report(report)

        if report["supplement_count"] == 0 and report["evaluate_count"] == 0:
            print("\n  所有知识点已符合当前架构要求, 无需升级!")
            return

        # 费用预估
        supplement_cost = report["supplement_count"] * 0.002
        evaluate_cost = report["evaluate_count"] * 0.003
        total_cost = supplement_cost + evaluate_cost

        print("\n  预估API费用: 约 {:.3f} 元 (使用V3模型, 非常便宜)".format(total_cost))
        if report["supplement_count"] > 0:
            print("    补标签: {}条 x ~0.002元 = ~{:.3f}元".format(
                report["supplement_count"], supplement_cost))
        if report["evaluate_count"] > 0:
            print("    AI评估: {}条 x ~0.003元 = ~{:.3f}元".format(
                report["evaluate_count"], evaluate_cost))

        usage = self.client.get_today_usage()
        print("  今日已用: {:.2f}元 / {:.0f}元上限".format(
            usage["today_cost"], usage["daily_limit"]))

        confirm = input("\n  是否执行升级? (输入 y 确认, 其他取消): ").strip().lower()
        if confirm != "y":
            print("  已取消升级"); return

        # --- Step 4: AI补标签 ---
        supplement_ok, supplement_fail = 0, 0
        if report["supplement_items"]:
            print("\n[Step 4/6] AI补标签 ({}条)...".format(report["supplement_count"]))
            for i, item in enumerate(report["supplement_items"], 1):
                title_short = item["title"][:30]
                print("  [{}/{}] {}...".format(i, report["supplement_count"], title_short),
                      end=" ")
                try:
                    success = self._supplement_tags(item)
                    if success:
                        supplement_ok += 1; print("OK")
                    else:
                        supplement_fail += 1; print("失败")
                except CostLimitExceeded:
                    print("\n  !! 费用达到上限, 剩余{}条下次再处理".format(
                        report["supplement_count"] - i))
                    break
                except Exception as e:
                    supplement_fail += 1; print("错误: {}".format(e))
        else:
            print("\n[Step 4/6] 无需补标签, 跳过")

        # --- Step 5: AI质量评估 ---
        need_reextract = []
        evaluate_ok = 0
        if report["evaluate_items"]:
            print("\n[Step 5/6] AI质量评估 ({}条)...".format(report["evaluate_count"]))
            for i, item in enumerate(report["evaluate_items"], 1):
                title_short = item["title"][:30]
                print("  [{}/{}] {}...".format(i, report["evaluate_count"], title_short),
                      end=" ")
                try:
                    result = self._ai_evaluate_quality(item)
                    if result == "reextract":
                        need_reextract.append(item)
                        print("-> 需重提取")
                    elif result == "supplement":
                        success = self._supplement_tags(item)
                        if success:
                            evaluate_ok += 1; print("-> 已补标签")
                        else:
                            print("-> 补标签失败")
                    else:
                        evaluate_ok += 1; print("-> 合格")
                except CostLimitExceeded:
                    print("\n  !! 费用达到上限")
                    break
                except Exception as e:
                    print("错误: {}".format(e))
        else:
            print("\n[Step 5/6] 无需AI评估, 跳过")

        # --- Step 6: 重提取调度 ---
        if need_reextract:
            print("\n[Step 6/6] 处理需重提取的知识点 ({}条)...".format(len(need_reextract)))
            self._handle_reextraction(need_reextract)
        else:
            print("\n[Step 6/6] 无需重提取, 跳过")

        # --- 最终报告 ---
        print("")
        print("=" * 60)
        print("  升级完成!")
        print("  补标签成功: {}条".format(supplement_ok))
        print("  AI评估通过: {}条".format(evaluate_ok))
        print("  需重提取:   {}条".format(len(need_reextract)))
        if supplement_fail > 0:
            print("  补标签失败: {}条".format(supplement_fail))
        if need_reextract:
            print("")
            print("  重提取文件已移至 data/processing/")
            print("  请运行 [一键提取.bat] 重新提取这些文件")
            print("  提取后在审核界面审核确认新知识点即可")
        print("=" * 60)

    # ==============================================================
    # 规则检查
    # ==============================================================

    def _rule_check(self, all_kps):
        """扫描所有知识点, 按架构要求分类"""
        ok_items = []
        supplement_items = []
        evaluate_items = []

        for kp in all_kps:
            missing = []
            reasons = []

            # 检查分类标签
            cat_tags = self._parse_json(
                kp.get("final_category_tags") or kp.get("suggested_category_tags"), [])
            if not cat_tags:
                missing.append("分类标签")

            # 检查属性标签
            attr_tags = self._parse_json(
                kp.get("final_attribute_tags") or kp.get("suggested_attribute_tags"), {})
            if not attr_tags:
                missing.append("属性标签")

            # 检查关键词
            keywords = self._parse_json(
                kp.get("final_keywords") or kp.get("suggested_keywords"), [])
            if not keywords or len(keywords) < 3:
                missing.append("关键词")

            # 检查元数据（已确认的知识点如果还是draft，说明未被AI评估过）
            if kp.get("content_readiness") == "draft" and kp.get("review_status") == "confirmed":
                missing.append("就绪度未评估")

            # 检查内容充实度（启发式：内容过短可能需要重提取）
            ai_content = self._parse_json(kp.get("ai_extracted_content"), {})
            excerpt = kp.get("original_excerpt") or ""
            content_text = json.dumps(ai_content, ensure_ascii=False) if ai_content else ""
            if len(content_text) < 100 and len(excerpt) < 50:
                reasons.append("内容过短")

            # 分类
            if reasons:
                evaluate_items.append(self._build_item(kp, missing, reasons))
            elif missing:
                supplement_items.append(self._build_item(kp, missing, []))
            else:
                ok_items.append(kp["id"])

        return {
            "total": len(all_kps),
            "ok_count": len(ok_items),
            "supplement_count": len(supplement_items),
            "evaluate_count": len(evaluate_items),
            "ok_items": ok_items,
            "supplement_items": supplement_items,
            "evaluate_items": evaluate_items,
        }

    def _build_item(self, kp, missing, reasons):
        """构造检查结果项"""
        ai_content = self._parse_json(kp.get("ai_extracted_content"), {})
        return {
            "id": kp["id"],
            "title": kp.get("title", ""),
            "content_type": kp.get("content_type", ""),
            "source_file_id": kp.get("source_file_id"),
            "ai_extracted_content": ai_content,
            "original_excerpt": kp.get("original_excerpt") or "",
            "missing": missing,
            "reasons": reasons,
            "review_status": kp.get("review_status", ""),
            "filename": kp.get("renamed_filename") or kp.get("original_filename", ""),
        }

    def _show_report(self, report):
        """打印规则检查报告"""
        print("\n[Step 3/6] 规则检查报告")
        print("  " + "=" * 50)
        print("  总知识点数: {}".format(report["total"]))
        print("  完全合格:   {} 条".format(report["ok_count"]))
        print("  可补标签:   {} 条 (缺标签/元数据, AI可直接补)".format(
            report["supplement_count"]))
        print("  需AI评估:   {} 条 (内容可能粗糙, 需AI判断)".format(
            report["evaluate_count"]))
        print("  " + "=" * 50)

        if report["supplement_items"]:
            print("\n  [可补标签] 详情 (最多显示15条):")
            for item in report["supplement_items"][:15]:
                miss_str = ", ".join(item["missing"])
                print("    - [#{}] {} | 缺: {}".format(
                    item["id"], item["title"][:35], miss_str))
            if len(report["supplement_items"]) > 15:
                print("    ... 等共{}条".format(len(report["supplement_items"])))

        if report["evaluate_items"]:
            print("\n  [需AI评估] 详情 (最多显示15条):")
            for item in report["evaluate_items"][:15]:
                reason_str = ", ".join(item["reasons"])
                print("    - [#{}] {} | 原因: {}".format(
                    item["id"], item["title"][:35], reason_str))
            if len(report["evaluate_items"]) > 15:
                print("    ... 等共{}条".format(len(report["evaluate_items"])))

    # ==============================================================
    # AI补标签
    # ==============================================================

    def _supplement_tags(self, item):
        """用V3模型为知识点补充缺失的标签和元数据"""
        title = item.get("title", "")
        content_type = item.get("content_type", "")
        excerpt = item.get("original_excerpt", "")
        ai_content = item.get("ai_extracted_content", {})

        # 拼接内容供AI分析
        content_for_ai = "标题: {}\n类型: {}\n".format(title, content_type)
        if excerpt:
            content_for_ai += "原文摘录: {}\n".format(excerpt[:2000])
        if ai_content:
            content_for_ai += "AI提取内容: {}\n".format(
                json.dumps(ai_content, ensure_ascii=False)[:3000])

        tag_ref = self._build_tag_reference()

        system_prompt = (
            "你是稻也的标签专家。根据知识点内容,补充缺失的标签和元数据。\n"
            "严格按JSON格式返回,不要有其他文字。"
        )

        user_prompt = (
            "请为以下知识点补充标签和元数据:\n\n"
            "{content}\n\n"
            "标签参考清单:\n{tag_ref}\n\n"
            '请返回JSON:\n'
            '{{\n'
            '  "category_tags": ["从第一层清单中选3-6个最相关的标签名称"],\n'
            '  "attribute_tags": {{"policy_level": "值", "fund_channel": "值"}},\n'
            '  "keywords": ["关键词1", "关键词2", "...5-15个"],\n'
            '  "content_readiness": "draft或quotable或premium",\n'
            '  "source_authority": "official或authoritative或firsthand或informal"\n'
            '}}'
        ).format(content=content_for_ai, tag_ref=tag_ref)

        ai = self.client.chat_with_json(
            system_prompt, user_prompt,
            temperature=0.2, call_type="upgrade_supplement",
            model_override="deepseek-chat"
        )
        parsed = ai.get("parsed_json")
        if not parsed or not isinstance(parsed, dict):
            return False

        update_kw = {}

        # 分类标签
        cat_tags = parsed.get("category_tags", [])
        if isinstance(cat_tags, list) and cat_tags:
            valid = [t for t in cat_tags
                     if isinstance(t, str) and t in self.VALID_LAYER1_NAMES]
            if valid:
                update_kw["final_category_tags"] = valid

        # 属性标签
        attr_tags = parsed.get("attribute_tags", {})
        if isinstance(attr_tags, dict) and attr_tags:
            clean = {}
            for k, v in attr_tags.items():
                if isinstance(k, str) and v:
                    if isinstance(v, list):
                        v = "、".join(str(x) for x in v)
                    clean[k] = str(v)
            if clean:
                update_kw["final_attribute_tags"] = clean

        # 关键词
        keywords = parsed.get("keywords", [])
        if isinstance(keywords, list) and keywords:
            clean_kw = list(dict.fromkeys(
                k for k in keywords
                if isinstance(k, str) and 2 <= len(k) <= 20
            ))
            if clean_kw:
                update_kw["final_keywords"] = clean_kw

        # 元数据
        readiness = parsed.get("content_readiness")
        if readiness in self.VALID_READINESS:
            update_kw["content_readiness"] = readiness

        authority = parsed.get("source_authority")
        if authority in self.VALID_AUTHORITY:
            update_kw["source_authority"] = authority

        if update_kw:
            self.db.update_knowledge_point(item["id"], **update_kw)
            edit_fields = {k: {"old": "", "new": str(v)} for k, v in update_kw.items()}
            self.db.add_edit_history(item["id"], edit_fields, "架构升级自动补标签")
            return True
        return False

    # ==============================================================
    # AI质量评估
    # ==============================================================

    def _ai_evaluate_quality(self, item):
        """AI评估知识点内容质量, 返回 'ok' / 'supplement' / 'reextract'"""
        title = item.get("title", "")
        excerpt = item.get("original_excerpt", "")
        ai_content = item.get("ai_extracted_content", {})

        content_for_ai = "标题: {}\n".format(title)
        if excerpt:
            content_for_ai += "原文摘录: {}\n".format(excerpt[:1500])
        if ai_content:
            content_for_ai += "AI提取内容: {}\n".format(
                json.dumps(ai_content, ensure_ascii=False)[:2000])

        system_prompt = (
            "你是知识库质量评估专家。判断知识点的内容质量是否满足\"可引用级\"标准。\n"
            "严格按JSON格式返回。"
        )

        user_prompt = (
            "请评估以下知识点的内容质量:\n\n"
            "{content}\n\n"
            "评估标准:\n"
            "- ok: 内容完整,有具体信息(数据/流程/要点),可以直接引用\n"
            "- supplement: 内容还行,但缺少标签,补上标签就可以用\n"
            "- reextract: 内容太粗糙/笼统/缺少具体信息,需要从原文件重新提取\n\n"
            '请返回JSON:\n'
            '{{"verdict": "ok或supplement或reextract", "reason": "简要说明原因(30字以内)"}}'
        ).format(content=content_for_ai)

        ai = self.client.chat_with_json(
            system_prompt, user_prompt,
            temperature=0.2, call_type="upgrade_evaluate",
            model_override="deepseek-chat"
        )
        parsed = ai.get("parsed_json")
        if parsed and isinstance(parsed, dict):
            verdict = parsed.get("verdict", "ok")
            reason = parsed.get("reason", "")
            if reason:
                print("({}) ".format(reason[:30]), end="")
            if verdict in ("ok", "supplement", "reextract"):
                return verdict
        return "ok"

    # ==============================================================
    # 重提取调度
    # ==============================================================

    def _handle_reextraction(self, items):
        """处理需要重提取的知识点: 删除旧的 + 源文件移至processing"""

        # 按源文件分组
        file_groups = {}
        for item in items:
            sfid = item.get("source_file_id")
            if sfid not in file_groups:
                file_groups[sfid] = {
                    "filename": item.get("filename", ""),
                    "kp_ids": [],
                    "kp_titles": [],
                }
            file_groups[sfid]["kp_ids"].append(item["id"])
            file_groups[sfid]["kp_titles"].append(item.get("title", ""))

        print("\n  涉及{}个源文件:".format(len(file_groups)))
        found_files = []
        missing_files = []

        for sfid, group in file_groups.items():
            fn = group["filename"]
            found_path = self._find_in_completed(fn)

            if found_path:
                found_files.append({
                    "source_file_id": sfid,
                    "filename": fn,
                    "path": found_path,
                    "kp_ids": group["kp_ids"],
                    "kp_count": len(group["kp_ids"]),
                })
                print("    [找到] {} ({}条知识点)".format(fn, len(group["kp_ids"])))
            else:
                missing_files.append(sfid)
                print("    [未找到] {} (completed/中不存在)".format(fn))

        if missing_files:
            print("\n  [警告] {}个文件在completed/中未找到, 这些知识点将保持原样".format(
                len(missing_files)))

        if not found_files:
            print("  没有可重提取的文件"); return

        total_old_kps = sum(f["kp_count"] for f in found_files)
        print("\n  将执行以下操作:")
        print("    1. 删除旧知识点 (共{}条)".format(total_old_kps))
        print("    2. 将{}个文件从 completed/ 复制到 processing/".format(len(found_files)))
        print("    3. 您稍后运行 [一键提取.bat] 重新提取")
        print("\n  [说明] 旧知识点删除前已自动备份, 如需回滚可运行 [一键恢复.bat]")

        confirm = input("\n  确认执行? (输入 y 确认, 其他取消): ").strip().lower()
        if confirm != "y":
            print("  已取消重提取操作"); return

        # 删除旧知识点
        deleted = 0
        for group in found_files:
            for kp_id in group["kp_ids"]:
                try:
                    self.db.delete_knowledge_point(kp_id)
                    deleted += 1
                except Exception as e:
                    print("    ! 删除知识点#{}失败: {}".format(kp_id, e))
        print("  已删除{}条旧知识点".format(deleted))

        # 复制文件到processing
        self.processing.mkdir(parents=True, exist_ok=True)
        moved = 0
        for group in found_files:
            src = group["path"]
            dest = self.processing / group["filename"]
            try:
                shutil.copy2(str(src), str(dest))
                moved += 1
                self.db.update_source_file(
                    group["source_file_id"],
                    process_status="processing",
                    process_message="架构升级-等待重提取")
                print("  已复制: {}".format(group["filename"]))
            except Exception as e:
                print("    ! 文件复制失败 {}: {}".format(group["filename"], e))

        print("\n  {}个文件已准备就绪, 请运行 [一键提取.bat]".format(moved))

    # ==============================================================
    # 工具方法
    # ==============================================================

    def _find_in_completed(self, filename):
        """在completed文件夹中查找文件, 返回Path或None"""
        if not self.completed.exists():
            return None
        for f in self.completed.iterdir():
            if f.name == filename:
                return f
        return None

    def _parse_json(self, value, default):
        """安全解析JSON字段"""
        if value is None:
            return default
        if isinstance(value, (dict, list)):
            return value
        if isinstance(value, str):
            try:
                return json.loads(value)
            except (json.JSONDecodeError, ValueError):
                return default
        return default

    def _build_tag_reference(self):
        """构建标签参考清单, 注入到Prompt中"""
        lines = []
        lines.append("=== 第一层: 分类标签 (从以下清单中选3-6个) ===")
        lines.append(get_layer1_for_prompt())
        lines.append("")
        lines.append("=== 第二层: 属性标签 (按维度填写) ===")
        lines.append(get_layer2_for_prompt())
        lines.append("")
        lines.append("=== 第三层: 关键词 ===")
        lines.append("自由提取5-15个关键词, 覆盖术语/实体/场景")
        lines.append("")
        lines.append("=== 元数据 ===")
        lines.append("content_readiness: draft(草稿级) / quotable(可引用级) / premium(精品级)")
        lines.append("source_authority: official(官方文件) / authoritative(行业权威) / firsthand(项目实证) / informal(业内交流)")
        return "\n".join(lines)


# ==============================================================
# 命令行入口
# ==============================================================

def main():
    print("")
    print("=" * 60)
    print("  稻也 - 架构升级迁移工具")
    print("=" * 60)

    try:
        UpgradeManager().run()
    except KeyboardInterrupt:
        print("\n\n  已取消操作。")
    except Exception as e:
        print("\n  [ERROR] {}".format(e))
        import traceback
        traceback.print_exc()
    input("\n按回车键退出...")


if __name__ == "__main__":
    main()
