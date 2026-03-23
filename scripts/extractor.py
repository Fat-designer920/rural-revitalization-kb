"""
extractor.py - 知识点提取引擎
路径：scripts/extractor.py
版本：v2.0.0 - 三层标签打标 + 元数据建议 + AI分类建议适配

变更说明（v2.0.0 vs v1.1.0）：
  - 解析AI返回的三层标签字段(suggested_category_tags/suggested_attribute_tags/suggested_keywords)
  - 解析元数据建议(suggested_readiness/suggested_authority)
  - 写入db_manager的新字段，不再填旧的suggested_tags
  - AI分类建议prompt更新为感知三层标签体系
  - 新增_sanitize_tags()对AI返回的标签做基本校验
  - 保留全部v1.1.0功能：R1/V3双模型、MD5去重、分段/截断修复、失败隔离、AI分类建议
"""
import os, sys, json, shutil, hashlib
from pathlib import Path
from datetime import datetime

PROJECT_ROOT = Path(__file__).parent.parent
sys.path.insert(0, str(PROJECT_ROOT))

from scripts.file_reader import FileReader
from scripts.deepseek_client import DeepSeekClient, CostLimitExceeded
from scripts.db_manager import DatabaseManager
from scripts.prompts.prompt_templates import get_extraction_prompt
from scripts.tag_config import get_layer1_tag_names, CONTENT_READINESS, SOURCE_AUTHORITY


class Extractor:
    TYPE_NAMES = {
        "policy": "政策文件", "case": "项目案例", "experience": "操盘经验",
        "tool": "实操工具", "data": "数据资料"
    }

    MODEL_OPTIONS = {
        "1": {
            "model": "deepseek-reasoner",
            "name": "R1 深度推理",
            "desc": "最精准,逐段深度分析,速度较慢,费用较高",
            "segment_max": 4000
        },
        "2": {
            "model": "deepseek-chat",
            "name": "V3 快速提取",
            "desc": "速度快,性价比高,适合批量处理",
            "segment_max": 6000
        }
    }

    # 第一层标签的合法名称清单（启动时从tag_config加载）
    VALID_LAYER1_NAMES = set(get_layer1_tag_names())
    # 元数据合法值
    VALID_READINESS = set(CONTENT_READINESS.keys())
    VALID_AUTHORITY = set(SOURCE_AUTHORITY.keys())

    def __init__(self):
        p = PROJECT_ROOT / "config" / "settings.json"
        with open(p, "r", encoding="utf-8") as f:
            self.config = json.load(f)
        self.reader = FileReader(self.config)
        self.client = DeepSeekClient(self.config)
        self.db = DatabaseManager()
        self.pending = Path(self.config.get("pending_path", PROJECT_ROOT / "data" / "pending"))
        self.processing = Path(self.config.get("processing_path", PROJECT_ROOT / "data" / "processing"))
        self.completed = Path(self.config.get("completed_path", PROJECT_ROOT / "data" / "completed"))
        self.failed_dir = Path(self.config.get("failed_path", PROJECT_ROOT / "data" / "failed"))
        self.completed.mkdir(parents=True, exist_ok=True)
        self.failed_dir.mkdir(parents=True, exist_ok=True)

        self.extraction_model = None
        self.extraction_model_name = None
        self.segment_max_len = 4000

    def select_model(self):
        print(f"\n  请选择提取模型:")
        print(f"  {'=' * 50}")
        for key, opt in self.MODEL_OPTIONS.items():
            print(f"  [{key}] {opt['name']}")
            print(f"      {opt['desc']}")
        print(f"  {'=' * 50}")
        while True:
            choice = input("  请输入选项编号 (1/2): ").strip()
            if choice in self.MODEL_OPTIONS:
                opt = self.MODEL_OPTIONS[choice]
                self.extraction_model = opt["model"]
                self.extraction_model_name = opt["name"]
                self.segment_max_len = opt["segment_max"]
                print(f"\n  已选择: {opt['name']} ({opt['model']})")
                return
            print(f"  无效输入,请输入 1 或 2")

    @staticmethod
    def calculate_file_hash(file_path):
        h = hashlib.md5()
        with open(file_path, "rb") as f:
            while True:
                chunk = f.read(8192)
                if not chunk: break
                h.update(chunk)
        return h.hexdigest()

    def check_duplicate(self, file_path, filename):
        file_hash = self.calculate_file_hash(file_path)
        existing = self.db.check_file_hash_exists(file_hash)
        if existing:
            exist_name = existing.get("renamed_filename") or existing.get("original_filename")
            exist_status = existing.get("process_status", "")
            exist_msg = existing.get("process_message", "")
            if exist_status == "completed" and "提取" in exist_msg and "知识点" in exist_msg and "未提取到" not in exist_msg:
                print(f"     [发现重复] 该文件已成功处理过(MD5指纹相同)")
                print(f"                原记录: {exist_name} | {exist_msg}")
                while True:
                    answer = input("     是否重新分析? (Y=重新分析 / N=跳过): ").strip().upper()
                    if answer == "Y":
                        print(f"     好的,将重新分析此文件")
                        return False, file_hash
                    elif answer == "N":
                        print(f"     已跳过")
                        return True, file_hash
                    else:
                        print(f"     请输入 Y 或 N")
            if exist_status == "failed":
                print(f"     [重新处理] 该文件上次处理失败,本次将重新提取")
            elif "未提取到" in exist_msg:
                print(f"     [重新处理] 该文件上次未提取到知识点,本次将重新提取")
            else:
                print(f"     [重新处理] 该文件存在旧记录(状态:{exist_status}),本次将重新提取")
            return False, file_hash
        return False, file_hash

    def _clean_pending(self, original_filename):
        try:
            for f in self.pending.iterdir():
                if f.name == original_filename:
                    os.remove(str(f))
                    print(f"     已清理pending中的原始文件: {original_filename}")
                    return
        except Exception as e:
            print(f"     ! pending文件清理失败: {e}")

    def get_processing_files(self):
        conn = self.db.get_connection(); c = conn.cursor()
        c.execute("SELECT * FROM source_files WHERE process_status='processing' ORDER BY created_at")
        rows = [dict(r) for r in c.fetchall()]; conn.close(); return rows

    def _determine_type(self, rec, content):
        fn = (rec.get("renamed_filename") or rec["original_filename"]).lower()
        if any(k in fn for k in ["政策", "通知", "办法", "规定", "意见", "规划", "zc"]): return "policy"
        if any(k in fn for k in ["案例", "项目", "al"]): return "case"
        if any(k in fn for k in ["经验", "心得", "复盘", "jy"]): return "experience"
        if any(k in fn for k in ["模板", "工具", "合同", "gj"]): return "tool"
        if any(k in fn for k in ["数据", "统计", "测算", "sj"]): return "data"
        preview = content[:1000]
        if sum(1 for kw in ["发布", "施行", "通知", "各省", "第一条", "本办法"] if kw in preview) >= 2: return "policy"
        return "policy"

    def _split(self, content, max_len=None):
        if max_len is None: max_len = self.segment_max_len
        if len(content) <= max_len: return [content]
        segs, cur = [], ""
        for para in content.split("\n\n"):
            if len(cur) + len(para) > max_len and cur:
                segs.append(cur); cur = para
            else:
                cur = cur + "\n\n" + para if cur else para
        if cur: segs.append(cur)
        return segs

    def _extract_single(self, content, filename, prompt, ctype):
        up = prompt["user_prompt_template"].format(filename=filename, full_content=content)
        ai = self.client.chat_with_json(
            prompt["system_prompt"], up, temperature=0.2,
            call_type=f"extract_{ctype}", model_override=self.extraction_model)
        parsed = ai.get("parsed_json")
        was_truncated = ai.get("was_truncated", False)
        cost_info = f"(花费约{ai.get('estimated_cost', 0):.4f}元)"
        if was_truncated and parsed is None:
            print(f"       ! 输出被截断且无法抢救 {cost_info}")
            return "TRUNCATED"
        if parsed and isinstance(parsed, dict):
            kps = parsed.get("knowledge_points", [])
            notes = parsed.get("extraction_notes", "")
            if notes: print(f"       AI说明: {notes[:80]}")
            if was_truncated:
                print(f"       本段提取{len(kps)}个知识点(部分截断已修复) {cost_info}")
            else:
                print(f"       本段提取{len(kps)}个知识点 {cost_info}")
            return kps
        if parsed and isinstance(parsed, list):
            print(f"       本段提取{len(parsed)}个知识点 {cost_info}")
            return parsed
        err = ai.get("json_parse_error", "未知错误")
        print(f"       ! JSON解析失败: {err} {cost_info}")
        return []

    def _extract_with_auto_split(self, content, filename, prompt, ctype, current_max_len=None):
        if current_max_len is None: current_max_len = self.segment_max_len
        result = self._extract_single(content, filename, prompt, ctype)
        if result == "TRUNCATED":
            new_max = current_max_len // 2
            if new_max < 500:
                print(f"       ! 内容过短仍被截断,跳过该段"); return []
            print(f"       自动拆分为更小段(每段{new_max}字)重新提取...")
            sub_segs = self._split(content, max_len=new_max)
            all_kps = []
            for j, sub_seg in enumerate(sub_segs, 1):
                print(f"         子段{j}/{len(sub_segs)} ({len(sub_seg)}字)...")
                sub_kps = self._extract_with_auto_split(sub_seg, f"{filename}(子段{j})", prompt, ctype, new_max)
                all_kps.extend(sub_kps)
            return all_kps
        if isinstance(result, list): return result
        return []

    def _move_to_completed(self, fp, fn):
        try:
            dest = self.completed / fn; c = 1
            while dest.exists():
                stem, ext = Path(fn).stem, Path(fn).suffix
                dest = self.completed / f"{stem}_{c}{ext}"; c += 1
            if os.path.exists(fp):
                shutil.copy2(fp, str(dest))
                if str(self.processing) in str(fp): os.remove(fp)
                print(f"     文件已归档至: completed/{dest.name}")
        except Exception as e: print(f"     ! 文件归档失败: {e}")

    def _move_to_failed(self, fp, fn):
        try:
            dest = self.failed_dir / fn; c = 1
            while dest.exists():
                stem, ext = Path(fn).stem, Path(fn).suffix
                dest = self.failed_dir / f"{stem}_{c}{ext}"; c += 1
            if os.path.exists(fp):
                shutil.copy2(fp, str(dest))
                if str(self.processing) in str(fp): os.remove(fp)
                print(f"     文件已隔离至: failed/{dest.name}")
        except Exception as e: print(f"     ! 文件隔离失败: {e}")

    # ================================================================
    # v2.0.0 新增：标签数据校验
    # ================================================================
    def _sanitize_tags(self, kp):
        """校验并清理AI返回的三层标签数据，确保格式正确、值合法。"""

        # --- 第一层：分类标签 ---
        raw_cat_tags = kp.get("suggested_category_tags", [])
        if not isinstance(raw_cat_tags, list):
            raw_cat_tags = []
        # 只保留在合法清单中的标签名
        clean_cat_tags = [t for t in raw_cat_tags if isinstance(t, str) and t in self.VALID_LAYER1_NAMES]
        if len(clean_cat_tags) < len(raw_cat_tags):
            removed = set(raw_cat_tags) - set(clean_cat_tags)
            if removed:
                print(f"       [标签校验] 过滤了{len(removed)}个不在清单中的分类标签: {', '.join(list(removed)[:3])}")

        # --- 第二层：属性标签 ---
        raw_attr_tags = kp.get("suggested_attribute_tags", {})
        if not isinstance(raw_attr_tags, dict):
            raw_attr_tags = {}
        # 保留所有键值对（维度名由AI填写，值可能是候选值或自由文本）
        clean_attr_tags = {}
        for dim_key, dim_val in raw_attr_tags.items():
            if isinstance(dim_key, str) and dim_val:
                # 如果值是列表（AI可能多选），转为逗号分隔字符串
                if isinstance(dim_val, list):
                    dim_val = "、".join(str(v) for v in dim_val)
                clean_attr_tags[dim_key] = str(dim_val)

        # --- 第三层：关键词 ---
        raw_keywords = kp.get("suggested_keywords", [])
        if not isinstance(raw_keywords, list):
            raw_keywords = []
        # 过滤：只保留2-20字的字符串，去重
        seen = set()
        clean_keywords = []
        for kw in raw_keywords:
            if isinstance(kw, str) and 2 <= len(kw) <= 20 and kw not in seen:
                seen.add(kw)
                clean_keywords.append(kw)

        # --- 元数据 ---
        readiness = kp.get("suggested_readiness", "draft")
        if readiness not in self.VALID_READINESS:
            readiness = "draft"

        authority = kp.get("suggested_authority", "firsthand")
        if authority not in self.VALID_AUTHORITY:
            authority = "firsthand"

        return {
            "category_tags": clean_cat_tags,
            "attribute_tags": clean_attr_tags,
            "keywords": clean_keywords,
            "readiness": readiness,
            "authority": authority,
        }

    # ================================================================
    # v1.1.0 保留：AI分类建议（v2.0.0更新prompt以感知三层标签）
    # ================================================================
    def _check_category_suggestions(self, kps_info):
        """提取完成后,分析是否需要调整分类体系。"""
        unmatched = [k for k in kps_info if not k.get("category_matched")]
        if not unmatched:
            return

        cats = self.db.get_all_categories()
        cat_tree_text = ""
        for cat in cats:
            cat_tree_text += f"  {cat['level2_code']} {cat['level2_name']}: {cat['description']}\n"

        unmatched_text = ""
        for k in unmatched[:10]:
            tags_preview = ", ".join(k.get("category_tags", [])[:4])
            unmatched_text += f"  - {k['title']} (AI建议分类编号: {k.get('suggested_code', '无')}, 分类标签: {tags_preview})\n"

        system_prompt = """你是一个知识库分类体系顾问。用户有一个乡村振兴知识库,分类体系如下。
现在有一些知识点无法匹配到现有分类,请分析是否需要调整分类体系。

注意：该知识库同时使用"分类体系"和"三层标签体系"。分类体系是档案柜（按来源类型分区），三层标签是多维标注。
你只负责分类体系的建议，不涉及标签体系。

你可以提出以下类型的建议(可以同时提多条):
1. add_level2: 在某个一级分类下新增二级分类
2. add_level1: 新增一个全新的一级分类(及其下属二级分类)
3. rename: 重命名某个分类以扩大覆盖范围
4. split: 将一个过大的分类拆分为多个
5. merge: 将多个过小的分类合并

请严格按JSON格式返回,不要有其他文字:
{"suggestions": [
  {"type": "add_level2", "name": "新分类名称", "level": "二级", "parent": "所属一级分类名称", "reason": "理由说明(50字以内)"},
  {"type": "add_level1", "name": "新一级分类名称", "level": "一级", "parent": "", "reason": "理由说明"},
  ...
]}

如果现有分类体系已经够用(只是AI分类建议不准确),请返回: {"suggestions": []}"""

        user_prompt = f"""当前分类体系:
{cat_tree_text}

以下知识点未能匹配到现有分类:
{unmatched_text}

请分析是否需要新增或调整分类。只提出真正必要的建议,不要过度拆分。"""

        try:
            print(f"\n     [AI分类建议] 分析{len(unmatched)}条未匹配知识点...")
            ai = self.client.chat_with_json(
                system_prompt, user_prompt,
                temperature=0.3, call_type="architecture_suggestion",
                model_override="deepseek-chat"
            )
            parsed = ai.get("parsed_json")
            if parsed and isinstance(parsed, dict):
                suggestions = parsed.get("suggestions", [])
                if suggestions:
                    print(f"     [AI分类建议] AI提出了{len(suggestions)}条建议:")
                    for sg in suggestions:
                        sg_type = sg.get("type", "add_level2")
                        sg_name = sg.get("name", "")
                        sg_level = sg.get("level", "二级")
                        sg_parent = sg.get("parent", "")
                        sg_reason = sg.get("reason", "")
                        print(f"       - [{sg_type}] {sg_name} ({sg_reason[:40]})")

                        parent_id = None
                        if sg_parent:
                            for cat in cats:
                                if cat["level1_name"] == sg_parent:
                                    parent_id = cat["id"]
                                    break

                        related_ids = [k.get("kp_id") for k in unmatched if k.get("kp_id")]
                        self.db.add_architecture_suggestion(
                            suggested_name=sg_name,
                            suggested_level=sg_level,
                            reason=sg_reason,
                            suggestion_type=sg_type,
                            parent_category_id=parent_id,
                            related_knowledge_ids=related_ids[:5]
                        )
                    print(f"     [AI分类建议] 已保存,请在审核界面中查看并处理")
                else:
                    print(f"     [AI分类建议] 现有分类体系够用,无需调整")
            else:
                print(f"     [AI分类建议] 解析失败,跳过")
        except CostLimitExceeded:
            print(f"     [AI分类建议] 费用已达上限,跳过分类建议")
        except Exception as e:
            print(f"     [AI分类建议] 出错: {e}")

    # ================================================================
    # 核心提取流程
    # ================================================================
    def extract_from_file(self, rec):
        result = {"success": False, "knowledge_count": 0, "error": ""}
        fid = rec["id"]
        fn = rec.get("renamed_filename") or rec["original_filename"]
        original_fn = rec["original_filename"]
        fp = None

        try:
            print(f"\n  >> 开始提取: {fn}")
            for f in self.processing.iterdir():
                if f.name == fn or f.name == rec["original_filename"]:
                    fp = str(f); break
            if not fp: fp = rec["file_path"]
            if not os.path.exists(fp):
                result["error"] = f"文件不存在:{fp}"
                print(f"     [FAIL] {result['error']}"); return result

            is_dup, file_hash = self.check_duplicate(fp, fn)
            if is_dup:
                self.db.update_source_file(fid, process_status="completed",
                                           process_message="重复文件,用户选择跳过", file_hash=file_hash)
                self._move_to_completed(fp, fn)
                self._clean_pending(original_fn)
                result["error"] = "重复文件已跳过"; return result
            self.db.update_source_file(fid, file_hash=file_hash)

            rr = self.reader.read_file(fp)
            if not rr["success"]:
                result["error"] = rr["error"]
                print(f"     [FAIL] 文件读取失败: {result['error']}")
                self._move_to_failed(fp, fn); self._clean_pending(original_fn)
                self.db.update_source_file(fid, process_status="failed", process_message=result["error"])
                return result
            content = rr["content"]
            if rr.get("metadata", {}).get("needs_ocr"):
                print(f"     图片文件,先进行OCR识别...")
                content = self.client.ocr_image(fp)["content"]

            ctype = self._determine_type(rec, content)
            prompt = get_extraction_prompt(ctype)
            print(f"     文件类型: {self.TYPE_NAMES.get(ctype, ctype)}")
            print(f"     内容长度: {len(content)}字")
            print(f"     提取模型: {self.extraction_model} ({self.extraction_model_name})")
            print(f"     标签模式: 三层标签(v2.0.0)")

            segs = self._split(content)
            if len(segs) > 1:
                print(f"     分{len(segs)}段提取(每段约{self.segment_max_len}字)")
            else:
                print(f"     整段提取")
            print(f"     AI提取中,请耐心等待...")

            kps = []
            for i, seg in enumerate(segs, 1):
                if len(segs) > 1:
                    print(f"\n     --- 第{i}/{len(segs)}段 ({len(seg)}字) ---")
                seg_kps = self._extract_with_auto_split(
                    seg, f"{fn}(第{i}/{len(segs)}段)" if len(segs) > 1 else fn,
                    prompt, ctype)
                kps.extend(seg_kps)

            if not kps:
                self.db.update_source_file(fid, process_status="completed", process_message="未提取到知识点")
                self._move_to_completed(fp, fn); self._clean_pending(original_fn)
                result["error"] = "未提取到知识点"
                print(f"     [注意] 未提取到知识点"); return result

            # === 写入数据库（v2.0.0: 三层标签 + 元数据） ===
            print(f"\n     写入{len(kps)}个知识点到数据库...")
            cnt = 0
            kps_info = []
            for kp in kps:
                try:
                    # 分类体系匹配（保持不变）
                    cat_code = kp.get("suggested_category_code", "")
                    cat = self.db.find_category_by_code(cat_code)

                    # v2.0.0: 三层标签校验
                    tags = self._sanitize_tags(kp)

                    # 写入数据库
                    kid = self.db.add_knowledge_point(
                        source_file_id=fid,
                        title=kp.get("title", "未命名"),
                        content_type=ctype,
                        original_excerpt=kp.get("original_excerpt", ""),
                        ai_extracted_content=kp,
                        suggested_category_id=cat["id"] if cat else None,
                        # v2.0.0 三层标签
                        suggested_category_tags=tags["category_tags"],
                        suggested_attribute_tags=tags["attribute_tags"],
                        suggested_keywords=tags["keywords"],
                        # v2.0.0 元数据
                        content_readiness=tags["readiness"],
                        source_authority=tags["authority"],
                        # 定位信息
                        source_page=str(kp.get("source_page", "")),
                        source_keyword=kp.get("source_keyword", ""))
                    cnt += 1
                    kps_info.append({
                        "kp_id": kid,
                        "title": kp.get("title", ""),
                        "suggested_code": cat_code,
                        "category_matched": cat is not None,
                        "category_tags": tags["category_tags"],
                    })
                except Exception as e:
                    print(f"     ! 第{cnt + 1}个知识点入库失败: {e}")

            self._move_to_completed(fp, fn)
            self._clean_pending(original_fn)

            model_tag = "R1" if "reasoner" in self.extraction_model else "V3"
            self.db.update_source_file(fid, process_status="completed",
                                       process_message=f"{model_tag}提取{cnt}个知识点(三层标签)")
            result.update({"success": True, "knowledge_count": cnt, "kps_info": kps_info})
            print(f"     [OK] {cnt}个知识点已存入待审核队列(三层标签已打标)")

        except CostLimitExceeded as e:
            result["error"] = str(e)
            print(f"\n     !! 费用超限: {e}")
        except Exception as e:
            result["error"] = f"{type(e).__name__}:{e}"
            print(f"     [FAIL] {result['error']}")
            if fp and os.path.exists(fp):
                self._move_to_failed(fp, fn)
            self._clean_pending(original_fn)
            self.db.update_source_file(fid, process_status="failed", process_message=result["error"])
        return result

    def run(self):
        print(f"\n{'=' * 60}")
        print(f"  乡村振兴知识库 - 知识点提取引擎 v2.0.0")
        print(f"  三层标签模式 | 启动时间: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}")
        print(f"{'=' * 60}")

        usage = self.client.get_today_usage()
        print(f"\n  今日API费用: {usage['today_cost']:.2f}元 / {usage['daily_limit']:.0f}元上限"
              f" (已用{usage['usage_percent']:.0f}%)")

        self.select_model()

        files = self.get_processing_files()
        if not files:
            print(f"\n  无待提取文件。请先将文件放入 data/pending/ 文件夹并运行预处理。")
            return
        print(f"\n  共{len(files)}个文件待提取")
        print(f"  使用模型: {self.extraction_model_name} ({self.extraction_model})")
        print(f"  分段策略: 每段{self.segment_max_len}字")
        print(f"  标签体系: 三层标签(6组41个分类标签 + 8维度属性 + 自由关键词)")
        print(f"{'-' * 60}")

        total_kps, ok, fail, skip = 0, 0, 0, 0
        all_kps_info = []
        for i, rec in enumerate(files, 1):
            fn = rec.get("renamed_filename") or rec["original_filename"]
            print(f"\n[{i}/{len(files)}] {fn}")
            r = self.extract_from_file(rec)
            if r["success"]:
                ok += 1
                total_kps += r["knowledge_count"]
                all_kps_info.extend(r.get("kps_info", []))
            elif "重复" in r.get("error", "") or "跳过" in r.get("error", ""):
                skip += 1
            else:
                fail += 1
                if "费用上限" in r.get("error", ""):
                    print(f"\n  !! 费用达到上限，剩余{len(files) - i}个文件下次再处理")
                    break

        # 全部提取完成后,统一分析分类建议
        if all_kps_info:
            self._check_category_suggestions(all_kps_info)

        usage = self.client.get_today_usage()
        print(f"\n{'=' * 60}")
        print(f"  提取完成!")
        print(f"  使用模型: {self.extraction_model_name}")
        print(f"  标签体系: 三层标签(v2.0.0)")
        print(f"  文件统计: {ok}个成功 / {skip}个跳过 / {fail}个失败")
        print(f"  知识点数: 共提取{total_kps}个，等待人工审核")
        print(f"  今日费用: {usage['today_cost']:.2f}元 (剩余{usage['remaining']:.2f}元)")
        print(f"{'-' * 60}")
        print(f"  下一步: 运行[启动审核界面.bat]审核知识点")
        print(f"{'=' * 60}")


def main():
    try:
        Extractor().run()
    except KeyboardInterrupt:
        print(f"\n\n  已取消操作。")
    except Exception as e:
        print(f"\n  [ERROR] {e}")
    input("\n按回车键退出...")


if __name__ == "__main__":
    main()
