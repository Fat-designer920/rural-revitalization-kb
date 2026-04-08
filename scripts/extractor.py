"""
extractor.py - 知识点提取引擎
路径：scripts/extractor.py
版本：v2.1.2 F044+bugfix - 基于v2.1.1 F039，新增进度回调+headless运行模式+headless input跳过

变更说明（v2.1.1 F039）：
  - 新增Step 8: 提取完成后增量重复检测(本地粗筛+V3精判)
  - 导入并初始化DuplicateChecker
  - 自动调用migrate_v211_dup迁移脚本
  - 保留全部v2.1.1 F038功能不变
"""
import os, sys, json, re, shutil, hashlib
from pathlib import Path
from datetime import datetime

PROJECT_ROOT = Path(__file__).parent.parent
sys.path.insert(0, str(PROJECT_ROOT))

from scripts.file_reader import FileReader
from scripts.deepseek_client import DeepSeekClient, CostLimitExceeded
from scripts.db_manager import DatabaseManager
from scripts.prompts.prompt_templates import (
    get_extraction_prompt, get_prompt_version,
    CONTEXT_RELAY_TEMPLATE, PRE_ANALYSIS_PROMPT,
    SEGMENT_SUMMARY_PROMPT, CROSS_SEGMENT_CHECK_PROMPT,
    QC_CHECK_PROMPT
)
from scripts.tag_config import get_layer1_tag_names, CONTENT_READINESS, SOURCE_AUTHORITY
from scripts.policy_validator import PolicyValidator
from scripts.duplicate_checker import DuplicateChecker


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
            "segment_max": 3000  # v2.1.0-d: 从4000降到3000,减少截断
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

    def __init__(self, progress_callback=None):
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
        self.segment_max_len = 3000  # v2.1.0-d: 默认值也改为3000
        self.policy_validator = PolicyValidator(db=self.db, client=self.client)
        self.duplicate_checker = DuplicateChecker(db=self.db, client=self.client)
        self._progress_callback = progress_callback
        self._headless = False  # v2.1.2 bugfix: headless模式跳过所有input()

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

    def set_model(self, model_key="1"):
        """非交互式模型选择，供API调用"""
        opt = self.MODEL_OPTIONS.get(model_key, self.MODEL_OPTIONS["1"])
        self.extraction_model = opt["model"]
        self.extraction_model_name = opt["name"]
        self.segment_max_len = opt["segment_max"]
        self._headless = True  # API调用时启用headless模式

    def _report_progress(self, **kw):
        """向进度回调报告当前状态"""
        if self._progress_callback:
            try:
                self._progress_callback(kw)
            except:
                pass

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
                print(f"       原记录: {exist_name} | {exist_msg}")
                if self._headless:
                    print(f"     [headless] 自动重新分析")
                    return False, file_hash
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

    def _extract_single(self, content, filename, prompt, ctype, relay_prefix=""):
        up = prompt["user_prompt_template"].format(filename=filename, full_content=content)
        if relay_prefix:
            up = relay_prefix + "\n\n" + up
        ai = self.client.chat_with_json(
            prompt["system_prompt"], up, temperature=0.2,
            call_type=f"extract_{ctype}", model_override=self.extraction_model)
        parsed = ai.get("parsed_json")
        was_truncated = ai.get("was_truncated", False)
        cost_info = f"(花费约{ai.get('estimated_cost', 0):.4f}元)"

        if was_truncated and parsed is None:
            print(f"     ! 输出被截断且无法抢救 {cost_info}")
            return "TRUNCATED"

        if parsed and isinstance(parsed, dict):
            kps = parsed.get("knowledge_points", [])
            notes = parsed.get("extraction_notes", "")
            if notes: print(f"     AI说明: {notes[:80]}")
            if was_truncated:
                # v2.1.0-d: 截断提示增强，明确说明影响
                print(f"     [注意] R1输出被截断(达到模型输出上限),尝试抢救...")
                print(f"     [截断修复] 从不完整输出中抢救出{len(kps)}个完整知识点")
                print(f"     本段提取{len(kps)}个知识点(部分截断已修复) {cost_info}")
            else:
                print(f"     本段提取{len(kps)}个知识点 {cost_info}")
            return kps
        if parsed and isinstance(parsed, list):
            print(f"     本段提取{len(parsed)}个知识点 {cost_info}")
            return parsed
        err = ai.get("json_parse_error", "未知错误")
        print(f"     ! JSON解析失败: {err} {cost_info}")
        return []

    def _extract_with_auto_split(self, content, filename, prompt, ctype, current_max_len=None, relay_prefix=""):
        if current_max_len is None: current_max_len = self.segment_max_len
        result = self._extract_single(content, filename, prompt, ctype, relay_prefix=relay_prefix)
        if result == "TRUNCATED":
            new_max = current_max_len // 2
            if new_max < 500:
                print(f"     ! 内容过短仍被截断,跳过该段"); return []
            print(f"     自动拆分为更小段(每段{new_max}字)重新提取...")
            sub_segs = self._split(content, max_len=new_max)
            all_kps = []
            for j, sub_seg in enumerate(sub_segs, 1):
                print(f"       子段{j}/{len(sub_segs)} ({len(sub_seg)}字)...")
                sub_kps = self._extract_with_auto_split(sub_seg, f"{filename}(子段{j})", prompt, ctype, new_max, relay_prefix=relay_prefix)
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
                print(f"     [标签校验] 过滤了{len(removed)}个不在清单中的分类标签: {', '.join(list(removed)[:3])}")

        # --- 第二层：属性标签 ---
        raw_attr_tags = kp.get("suggested_attribute_tags", {})
        if not isinstance(raw_attr_tags, dict):
            raw_attr_tags = {}
        clean_attr_tags = {}
        for dim_key, dim_val in raw_attr_tags.items():
            if isinstance(dim_key, str) and dim_val:
                if isinstance(dim_val, list):
                    dim_val = "、".join(str(v) for v in dim_val)
                clean_attr_tags[dim_key] = str(dim_val)

        # --- 第三层：关键词 ---
        raw_keywords = kp.get("suggested_keywords", [])
        if not isinstance(raw_keywords, list):
            raw_keywords = []
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
    # v2.1.0-c 新增：V3预分析
    # ================================================================
    def _pre_analyze(self, content, filename):
        """V3预分析：质量评估+分类建议+结构识别。失败时暂停让用户选择。"""
        preview = content[:2000]
        char_count = len(content)
        prompt = PRE_ANALYSIS_PROMPT
        up = prompt["user_prompt_template"].format(
            filename=filename, char_count=char_count, content_preview=preview)

        for attempt in range(1, 4):
            try:
                ai = self.client.chat_with_json(
                    prompt["system_prompt"], up, temperature=0.2,
                    call_type="pre_analysis", model_override="deepseek-chat")
                parsed = ai.get("parsed_json")
                if parsed and isinstance(parsed, dict):
                    cost = ai.get("estimated_cost", 0)
                    print(f"     预分析完成(花费{cost:.4f}元)")
                    return parsed
                print(f"     预分析返回格式异常(第{attempt}次)")
            except CostLimitExceeded:
                raise
            except Exception as e:
                print(f"     预分析出错(第{attempt}次): {e}")

        # 3次失败，暂停让用户选择
        print(f"\n     [预分析未能完成] 可能是网络问题")
        if self._headless:
            print(f"     [headless] 自动跳过预分析，使用文件名推断分类")
            return None
        while True:
            choice = input("     [1]重试 [2]跳过预分析直接提取 [3]跳过该文件: ").strip()
            if choice == "1":
                return self._pre_analyze(content, filename)  # 递归重试
            elif choice == "2":
                print("     跳过预分析，使用文件名推断分类")
                return None
            elif choice == "3":
                return "SKIP_FILE"
            else:
                print("     请输入 1/2/3")

    # ================================================================
    # v2.1.0-c 新增：V3结构摘要
    # ================================================================
    def _get_structure_summary(self, content, filename):
        """V3分析文件结构，返回分段建议。失败返回None。"""
        char_count = len(content)
        prompt = SEGMENT_SUMMARY_PROMPT
        up = prompt["user_prompt_template"].format(
            filename=filename, char_count=char_count, full_content=content[:8000])
        try:
            ai = self.client.chat_with_json(
                prompt["system_prompt"], up, temperature=0.2,
                call_type="segment_summary", model_override="deepseek-chat")
            parsed = ai.get("parsed_json")
            if parsed and isinstance(parsed, dict):
                cost = ai.get("estimated_cost", 0)
                print(f"     结构摘要完成(花费{cost:.4f}元)")
                return parsed
        except CostLimitExceeded:
            raise
        except Exception as e:
            print(f"     结构摘要失败: {e}")
        return None

    # ================================================================
    # v2.1.0-c 新增：三级智能分段
    # ================================================================
    def _smart_segment(self, content, pre_result, filename):
        """三级分段策略，绝不回退到机械切割。
        返回 (segments_list, file_structure_text)"""
        if len(content) <= self.segment_max_len:
            return [content], ""

        # v2.1.0-d: 过大段阈值动态计算，跟随模型设置
        oversized_threshold = int(self.segment_max_len * 1.5)

        # --- 第一级：V3结构摘要分段 ---
        structure_result = self._get_structure_summary(content, filename)
        if structure_result:
            suggested_segs = structure_result.get("suggested_segments", [])
            if suggested_segs and len(suggested_segs) >= 2:
                segs = self._apply_v3_segments(content, suggested_segs, oversized_threshold)
                if segs:
                    # 构建结构摘要文本
                    doc_structure = structure_result.get("document_structure", [])
                    struct_text = self._format_structure_text(doc_structure)
                    notes = structure_result.get("notes", "")
                    if notes:
                        print(f"     分段提示: {notes[:60]}")
                    # 保存分段方案
                    try:
                        self.db.update_source_file(
                            self._current_file_id,
                            segment_plan=json.dumps(structure_result, ensure_ascii=False))
                    except:
                        pass
                    return segs, struct_text
            print(f"     V3分段建议不可用,切换到本地规则分段")
        else:
            print(f"     V3结构摘要不可用,切换到本地规则分段")

        # --- 第二级：本地规则分段 ---
        segs = self._local_rule_segment(content, oversized_threshold)
        if segs and len(segs) >= 2:
            print(f"     使用本地规则分段(按章节标记)")
            # 从预分析中提取结构信息
            struct_text = ""
            if pre_result and isinstance(pre_result, dict):
                overview = pre_result.get("content_overview", "")
                struct_text = overview
            return segs, struct_text

        # --- 第三级：段落边界分段 ---
        print(f"     使用段落边界分段")
        segs = self._paragraph_segment(content)
        struct_text = ""
        if pre_result and isinstance(pre_result, dict):
            struct_text = pre_result.get("content_overview", "")
        return segs, struct_text

    def _apply_v3_segments(self, content, suggested_segs, oversized_threshold=None):
        """根据V3建议的分段方案切割内容"""
        # v2.1.0-d: 使用传入的动态阈值
        if oversized_threshold is None:
            oversized_threshold = int(self.segment_max_len * 1.5)

        segments = []
        content_lower = content
        for seg_info in suggested_segs:
            start_kw = seg_info.get("start_keyword", "")
            if not start_kw:
                continue
            # 找到起始位置
            pos = content_lower.find(start_kw)
            if pos < 0:
                # 尝试模糊匹配（取前10个字）
                short_kw = start_kw[:10]
                pos = content_lower.find(short_kw)
            if pos >= 0:
                segments.append(pos)

        if len(segments) < 2:
            return None

        # 按位置排序并切割
        segments.sort()
        result = []
        for i in range(len(segments)):
            start = segments[i]
            end = segments[i + 1] if i + 1 < len(segments) else len(content)
            seg_text = content[start:end].strip()
            if seg_text:
                result.append(seg_text)

        # 如果第一段之前有内容，加到第一段前面
        if segments[0] > 0:
            prefix = content[:segments[0]].strip()
            if prefix and result:
                result[0] = prefix + "\n\n" + result[0]

        # v2.1.0-d: 过大段拆分使用动态阈值
        final = []
        for seg in result:
            if len(seg) > oversized_threshold:
                sub_segs = self._paragraph_segment(seg, max_len=self.segment_max_len)
                final.extend(sub_segs)
            else:
                final.append(seg)

        return final if len(final) >= 1 else None

    def _local_rule_segment(self, content, oversized_threshold=None):
        """按章节标记分段：识别中文文档常见的结构标记"""
        # v2.1.0-d: 使用动态阈值
        if oversized_threshold is None:
            oversized_threshold = int(self.segment_max_len * 1.5)

        # 常见章节标记模式
        patterns = [
            r'\n(第[一二三四五六七八九十百]+[章编篇])',    # 第一章、第一编
            r'\n(第[一二三四五六七八九十\d]+条[\s\u3000])',  # 第一条 （政策文件）
            r'\n([一二三四五六七八九十]+、)',              # 一、二、三、
            r'\n(附[则件录表]\s)',                        # 附则、附件
        ]

        # 尝试每种模式，选择最佳（切出2-15段的）
        for pattern in patterns:
            positions = []
            for m in re.finditer(pattern, content):
                positions.append(m.start())

            if len(positions) >= 2:
                # 切割
                segments = []
                for i in range(len(positions)):
                    start = positions[i]
                    end = positions[i + 1] if i + 1 < len(positions) else len(content)
                    seg = content[start:end].strip()
                    if seg:
                        segments.append(seg)

                # 第一段之前的内容加到第一段
                if positions[0] > 0:
                    prefix = content[:positions[0]].strip()
                    if prefix and segments:
                        segments[0] = prefix + "\n\n" + segments[0]

                # 合并过小的段（小于500字的与后一段合并）
                merged = []
                buf = ""
                for seg in segments:
                    if buf:
                        buf = buf + "\n\n" + seg
                    else:
                        buf = seg
                    if len(buf) >= 500:
                        merged.append(buf)
                        buf = ""
                if buf:
                    if merged:
                        merged[-1] = merged[-1] + "\n\n" + buf
                    else:
                        merged.append(buf)

                # v2.1.0-d: 拆分过大的段（使用动态阈值）
                final = []
                for seg in merged:
                    if len(seg) > oversized_threshold:
                        sub = self._paragraph_segment(seg, max_len=self.segment_max_len)
                        final.extend(sub)
                    else:
                        final.append(seg)

                if 2 <= len(final) <= 20:
                    return final

        return None  # 没有找到合适的章节标记

    def _paragraph_segment(self, content, max_len=None):
        """按段落边界分段，保证不在段落中间切断"""
        if max_len is None:
            max_len = self.segment_max_len
        if len(content) <= max_len:
            return [content]
        paragraphs = content.split("\n\n")
        segments = []
        current = ""
        for para in paragraphs:
            # 如果当前段加上新段落会超限，且当前段非空，先保存当前段
            if len(current) + len(para) + 2 > max_len and current:
                segments.append(current.strip())
                current = para
            else:
                current = current + "\n\n" + para if current else para
        if current.strip():
            segments.append(current.strip())
        # 如果只产生了一段（整个内容没有段落分隔），按换行分
        if len(segments) <= 1 and len(content) > max_len:
            lines = content.split("\n")
            segments = []
            current = ""
            for line in lines:
                if len(current) + len(line) + 1 > max_len and current:
                    segments.append(current.strip())
                    current = line
                else:
                    current = current + "\n" + line if current else line
            if current.strip():
                segments.append(current.strip())
        return segments if segments else [content]

    def _format_structure_text(self, doc_structure):
        """将V3返回的文档结构格式化为文本"""
        if not doc_structure:
            return ""
        lines = []
        for item in doc_structure:
            level = item.get("level", 1)
            title = item.get("title", "")
            indent = "  " * (level - 1)
            lines.append(f"{indent}- {title}")
        return "\n".join(lines)

    # ================================================================
    # v2.1.0-c 新增：上下文接力信息构建
    # ================================================================
    def _build_context_relay(self, seg_idx, total_segs, file_structure, prev_kps):
        """构建分段提取的上下文接力信息。单段文件返回空字符串。"""
        if total_segs <= 1:
            return ""
        # 前段已提取的知识点标题
        if prev_kps:
            titles = [kp.get("title", "") for kp in prev_kps]
            titles_text = "\n".join(f"  {i+1}. {t}" for i, t in enumerate(titles))
        else:
            titles_text = "  (这是第一段，暂无)"
        return CONTEXT_RELAY_TEMPLATE.format(
            total_segments=total_segs,
            current_segment=seg_idx,
            file_structure_summary=file_structure or "(结构摘要不可用)",
            previous_titles=titles_text
        )

    # ================================================================
    # v2.1.0-c 新增：跨段补漏检查
    # ================================================================
    def _cross_segment_check(self, filename, file_structure, all_kps):
        """V3检查分段提取是否有遗漏。返回遗漏信息dict或None。"""
        if not file_structure:
            print(f"     无结构摘要,跳过补漏检查")
            return None

        all_titles = "\n".join(f"  {i+1}. {kp.get('title', '')}" for i, kp in enumerate(all_kps))
        prompt = CROSS_SEGMENT_CHECK_PROMPT
        up = prompt["user_prompt_template"].format(
            filename=filename,
            document_structure=file_structure,
            all_kp_titles=all_titles)

        try:
            ai = self.client.chat_with_json(
                prompt["system_prompt"], up, temperature=0.2,
                call_type="cross_segment_check", model_override="deepseek-chat")
            parsed = ai.get("parsed_json")
            if parsed and isinstance(parsed, dict):
                cost = ai.get("estimated_cost", 0)
                missed = parsed.get("missed_sections", [])
                coverage = parsed.get("overall_coverage", "未知")
                dupes = parsed.get("duplicate_suspects", [])
                print(f"     补漏检查完成(花费{cost:.4f}元)")
                print(f"     覆盖评估: {coverage}")
                if missed:
                    important_missed = [m for m in missed if m.get("importance") in ("高", "中")]
                    if important_missed:
                        print(f"     [注意] 发现{len(important_missed)}个可能遗漏的章节:")
                        for m in important_missed[:3]:
                            print(f"       - {m.get('section_title', '')} (重要性:{m.get('importance', '')})")
                        print(f"     建议在审核时重点关注相关知识点的完整性")
                if dupes:
                    print(f"     [提示] 发现{len(dupes)}组疑似重复知识点")
                return parsed
        except CostLimitExceeded:
            print(f"     费用已达上限,跳过补漏检查")
        except Exception as e:
            print(f"     补漏检查失败: {e}")
        return None

    # ================================================================
    # v2.1.0-c 新增：费用预估
    # ================================================================
    def _estimate_extraction_cost(self, segments):
        """估算R1提取费用（粗略估算，给用户一个量级参考）"""
        # R1定价：输入4元/百万token，输出16元/百万token
        # 粗估：1000中文字 ≈ 800 token
        total_chars = sum(len(s) for s in segments)
        est_input_tokens = int(total_chars * 0.8)  # 输入（含system prompt约3000字）
        est_input_tokens += len(segments) * 3000 * 0.8  # 每段的system prompt
        est_output_tokens = len(segments) * 1500  # 每段估算输出1500 token
        cost = (est_input_tokens / 1e6) * 4.0 + (est_output_tokens / 1e6) * 16.0
        return round(cost, 2)

    # ================================================================
    # v2.1.0-c 第3批新增：V3质检（5维度评分）
    # ================================================================
    def _quality_check(self, filename, content_summary, kps, kps_info):
        """V3质检：对同一文件的所有知识点进行6维度评分（v2.1.1: 含举一反三可靠性）。
        kps: 原始AI提取的知识点列表（含完整内容）
        kps_info: 写入DB后的info列表（含kp_id和practical_insights）
        返回成功质检的数量。"""
        if not kps or not kps_info:
            return 0

        # 构建知识点JSON（与QC_CHECK_PROMPT模板的{knowledge_points_json}对应）
        kp_for_qc = []
        for i, kp in enumerate(kps):
            qc_item = {
                "index": i,
                "title": kp.get("title", "未命名"),
                "original_excerpt": (kp.get("original_excerpt") or "")[:200],
                "suggested_category_tags": kp.get("suggested_category_tags", []),
                "suggested_keywords": kp.get("suggested_keywords", [])[:5]
            }
            # v2.1.1 F038: 传递practical_insights供V3评估可靠性
            if i < len(kps_info):
                insights = kps_info[i].get("practical_insights", [])
                if insights:
                    qc_item["practical_insights"] = insights
            kp_for_qc.append(qc_item)

        knowledge_points_json = json.dumps(kp_for_qc, ensure_ascii=False, indent=2)
        prompt = QC_CHECK_PROMPT
        up = prompt["user_prompt_template"].format(
            filename=filename,
            file_summary=content_summary or "(无摘要)",
            kp_count=len(kps),
            knowledge_points_json=knowledge_points_json
        )

        try:
            ai = self.client.chat_with_json(
                prompt["system_prompt"], up, temperature=0.2,
                call_type="qc_check", model_override="deepseek-chat")
            parsed = ai.get("parsed_json")
            cost = ai.get("estimated_cost", 0)

            if not parsed or not isinstance(parsed, dict):
                print(f"     质检返回格式异常(花费{cost:.4f}元)")
                return 0

            # QC_CHECK_PROMPT返回的数组字段名是qa_results
            results = parsed.get("qa_results", [])
            if not results:
                print(f"     质检无结果(花费{cost:.4f}元)")
                return 0

            print(f"     质检完成: {len(results)}条评分(花费{cost:.4f}元)")

            # 统计分数分布
            scores = []
            checked = 0
            for qr in results:
                # QC_CHECK_PROMPT返回kp_index（0开始）
                idx = qr.get("kp_index", -1)
                score = qr.get("qa_score", 0)
                flags = qr.get("qa_flags", [])
                if not isinstance(flags, list):
                    flags = []

                # 标准化flags为英文标记，方便前端翻译
                normalized_flags = []
                FLAG_MAP = {
                    "缺上下文": "independence", "独立性不足": "independence",
                    "信息空泛": "density", "信息密度低": "density",
                    "颗粒度过粗": "granularity_coarse", "过粗": "granularity_coarse",
                    "颗粒度过细": "granularity_fine", "过细": "granularity_fine",
                    "标签不符": "tag_mismatch", "标签不匹配": "tag_mismatch",
                    "疑似重复": "duplicate_suspect", "重复": "duplicate_suspect",
                    "启示无依据": "insight_no_basis", "举一反三无依据": "insight_no_basis",
                }
                for f in flags:
                    if isinstance(f, str):
                        mapped = FLAG_MAP.get(f)
                        if mapped:
                            normalized_flags.append(mapped)
                        elif f in FLAG_MAP.values():
                            normalized_flags.append(f)
                        else:
                            # 保留原始中文标记
                            normalized_flags.append(f)

                # v2.1.1 F038: 解析insight_reliability
                insight_rel = qr.get("insight_reliability", None)
                valid_rel = ("reliable", "uncertain", "unreliable", "no_insights")
                if insight_rel not in valid_rel:
                    insight_rel = None

                scores.append(score)
                # 找到对应的kp_id
                if 0 <= idx < len(kps_info):
                    kp_id = kps_info[idx].get("kp_id")
                    if kp_id:
                        try:
                            update_kw = {
                                "qa_score": score,
                                "qa_flags": json.dumps(normalized_flags, ensure_ascii=False)
                            }
                            if insight_rel:
                                update_kw["insight_reliability"] = insight_rel
                            self.db.update_knowledge_point(kp_id, **update_kw)
                            checked += 1
                        except Exception as e:
                            print(f"     ! 质检分数写入失败(ID={kp_id}): {e}")

            # 打印分数分布
            if scores:
                avg = sum(scores) / len(scores)
                low = sum(1 for s in scores if s <= 2)
                mid = sum(1 for s in scores if s == 3)
                high = sum(1 for s in scores if s >= 4)
                print(f"     质检评分: 平均{avg:.1f}分 (优{high} / 中{mid} / 差{low})")
                if low > 0:
                    print(f"     [注意] {low}条知识点评分较低,建议审核时重点关注")

            return checked

        except CostLimitExceeded:
            print(f"     费用已达上限,跳过质检")
            return 0
        except Exception as e:
            print(f"     质检失败: {e}")
            return 0

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
        self._current_file_id = fid  # 供_smart_segment保存分段方案
        fn = rec.get("renamed_filename") or rec["original_filename"]
        original_fn = rec["original_filename"]
        fp = None
        try:
            print(f"\n     >> 开始提取: {fn}")
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

            # === Step 1: V3预分析 ===
            pre_result = None
            print(f"     [Step 1] V3预分析...")
            self._report_progress(current_step="Step 1/8 V3预分析")
            pre_result = self._pre_analyze(content, fn)
            if pre_result == "SKIP_FILE":
                self.db.update_source_file(fid, process_status="processing",
                                           process_message="预分析失败,用户选择跳过")
                result["error"] = "用户跳过(预分析失败)"; return result

            if pre_result and isinstance(pre_result, dict):
                # 更新分类建议
                suggested_type = pre_result.get("content_type", "")
                if suggested_type and suggested_type in self.TYPE_NAMES:
                    if suggested_type != ctype:
                        print(f"     V3建议分类: {self.TYPE_NAMES[suggested_type]}(原判断:{self.TYPE_NAMES.get(ctype, ctype)})")
                        ctype = suggested_type
                # 质量评估
                q_score = pre_result.get("quality_score", 5)
                q_reason = pre_result.get("quality_reason", "")
                est_count = pre_result.get("estimated_knowledge_count", "?")
                print(f"     质量评分: {q_score}/5 ({q_reason})")
                print(f"     预估知识点: {est_count}条")
                # 低价值文件提醒
                if q_score <= 2:
                    warnings = pre_result.get("warnings", [])
                    if warnings:
                        for w in warnings:
                            print(f"     [提醒] {w}")
                    if self._headless:
                        print(f"     [headless] 低价值文件(评分{q_score}/5)，自动继续提取")
                    else:
                        while True:
                            answer = input(f"     该文件价值较低(评分{q_score}/5), 继续提取? (Y=继续 / N=跳过): ").strip().upper()
                            if answer == "Y":
                                print(f"     好的,继续提取"); break
                            elif answer == "N":
                                self.db.update_source_file(fid, process_status="completed",
                                                           process_message=f"V3预分析评分{q_score}/5,用户选择跳过")
                                self._move_to_completed(fp, fn); self._clean_pending(original_fn)
                                result["error"] = "低价值文件已跳过"; return result
                            else: print(f"     请输入 Y 或 N")
                # 保存预分析结果
                self.db.update_source_file(fid,
                    pre_analysis_result=json.dumps(pre_result, ensure_ascii=False),
                    suggested_content_type=ctype)

            prompt = get_extraction_prompt(ctype)
            print(f"     文件类型: {self.TYPE_NAMES.get(ctype, ctype)}")
            print(f"     内容长度: {len(content)}字")
            print(f"     提取模型: {self.extraction_model} ({self.extraction_model_name})")
            print(f"     Prompt版本: {get_prompt_version()}")

            # === Step 2: 智能分段 ===
            print(f"     [Step 2] 智能分段...")
            self._report_progress(current_step="Step 2/8 智能分段")
            segs, file_structure = self._smart_segment(content, pre_result, fn)
            if len(segs) > 1:
                seg_lens = [len(s) for s in segs]
                print(f"     分{len(segs)}段提取(段长: {min(seg_lens)}-{max(seg_lens)}字)")
            else:
                print(f"     整段提取({len(segs[0])}字)")

            # === Step 3: 费用预估(大文件) ===
            if len(segs) >= 3:
                est_cost = self._estimate_extraction_cost(segs)
                print(f"     预估费用: R1提取约{est_cost:.2f}元 + V3辅助<0.2元")
                if est_cost > 5.0:
                    if self._headless:
                        print(f"     [headless] 费用较高({est_cost:.1f}元)，自动继续")
                    else:
                        while True:
                            answer = input(f"     预估费用较高({est_cost:.1f}元), 继续? (Y/N): ").strip().upper()
                            if answer == "Y": break
                            elif answer == "N":
                                self.db.update_source_file(fid, process_status="processing",
                                                           process_message=f"费用预估{est_cost:.1f}元,用户暂缓")
                                result["error"] = "用户暂缓(费用)"; return result
                            else: print(f"     请输入 Y 或 N")

            # === Step 4: R1逐段提取(带上下文接力) ===
            print(f"     [Step 4] AI提取中,请耐心等待...")
            self._report_progress(current_step="Step 4/8 AI提取")
            kps = []
            for i, seg in enumerate(segs, 1):
                if len(segs) > 1:
                    print(f"\n     --- 第{i}/{len(segs)}段 ({len(seg)}字) ---")
                # 构建上下文接力信息
                relay_prefix = self._build_context_relay(i, len(segs), file_structure, kps)
                seg_kps = self._extract_with_auto_split(
                    seg, f"{fn}(第{i}/{len(segs)}段)" if len(segs) > 1 else fn,
                    prompt, ctype, relay_prefix=relay_prefix)
                kps.extend(seg_kps)

            if not kps:
                self.db.update_source_file(fid, process_status="completed", process_message="未提取到知识点")
                self._move_to_completed(fp, fn); self._clean_pending(original_fn)
                result["error"] = "未提取到知识点"
                print(f"     [注意] 未提取到知识点"); return result

            # === Step 5: 跨段补漏检查(多段文件) ===
            extraction_notes = ""
            if len(segs) > 1:
                print(f"\n     [Step 5] 跨段补漏检查...")
                self._report_progress(current_step="Step 5/8 跨段补漏")
                missed = self._cross_segment_check(fn, file_structure, kps)
                if missed:
                    extraction_notes = json.dumps(missed, ensure_ascii=False)

            # === 写入数据库（v2.1.1: 三层标签 + 元数据 + prompt_version + practical_insights） ===
            print(f"\n     写入{len(kps)}个知识点到数据库...")
            current_prompt_version = get_prompt_version()
            cnt = 0
            kps_info = []
            for kp in kps:
                try:
                    cat_code = kp.get("suggested_category_code", "")
                    cat = self.db.find_category_by_code(cat_code)
                    tags = self._sanitize_tags(kp)

                    # v2.1.1 F038: 解析practical_insights
                    raw_insights = kp.get("practical_insights", [])
                    if not isinstance(raw_insights, list):
                        raw_insights = []
                    clean_insights = []
                    for ins in raw_insights:
                        if isinstance(ins, dict) and ins.get("insight"):
                            clean_insights.append({
                                "insight": str(ins.get("insight", "")),
                                "basis": str(ins.get("basis", "")),
                                "confidence": ins.get("confidence", "medium") if ins.get("confidence") in ("high", "medium", "low") else "medium"
                            })

                    kid = self.db.add_knowledge_point(
                        source_file_id=fid,
                        title=kp.get("title", "未命名"),
                        content_type=ctype,
                        original_excerpt=kp.get("original_excerpt", ""),
                        ai_extracted_content=kp,
                        suggested_category_id=cat["id"] if cat else None,
                        suggested_category_tags=tags["category_tags"],
                        suggested_attribute_tags=tags["attribute_tags"],
                        suggested_keywords=tags["keywords"],
                        content_readiness=tags["readiness"],
                        source_authority=tags["authority"],
                        source_page=str(kp.get("source_page", "")),
                        source_keyword=kp.get("source_keyword", ""),
                        prompt_version=current_prompt_version,
                        practical_insights=clean_insights)
                    cnt += 1
                    kps_info.append({
                        "kp_id": kid,
                        "title": kp.get("title", ""),
                        "suggested_code": cat_code,
                        "category_matched": cat is not None,
                        "category_tags": tags["category_tags"],
                        "practical_insights": clean_insights,
                    })
                except Exception as e:
                    print(f"     ! 第{cnt + 1}个知识点入库失败: {e}")

            self._move_to_completed(fp, fn)
            self._clean_pending(original_fn)

            # === Step 6: V3质检（5维度评分） ===
            qc_count = 0
            if cnt > 0:
                print(f"\n     [Step 6] V3质检({cnt}条知识点)...")
                self._report_progress(current_step="Step 6/8 V3质检")
                content_summary = ""
                if pre_result and isinstance(pre_result, dict):
                    content_summary = pre_result.get("content_overview", "")
                qc_count = self._quality_check(fn, content_summary, kps, kps_info)

            # === Step 7: 政策依赖校验（V3扫描+KB匹配） ===
            pv_count = 0
            if cnt > 0:
                print(f"\n     [Step 7] 政策依赖校验({cnt}条知识点)...")
                self._report_progress(current_step="Step 7/8 政策校验")
                try:
                    pv_count = self.policy_validator.validate_batch(kps, kps_info, ctype)
                except CostLimitExceeded:
                    print(f"     费用已达上限,跳过政策校验")
                except Exception as e:
                    print(f"     政策校验出错: {e}")

            # === Step 8: 增量重复检测（本地粗筛+V3精判） ===
            dup_count = 0
            if cnt > 0 and kps:
                self._report_progress(current_step="Step 8/8 重复检测")
                try:
                    new_ids = [info["id"] for info in kps_info if info.get("id")]
                    if new_ids:
                        dup_count = self.duplicate_checker.scan_incremental(new_ids)
                except CostLimitExceeded:
                    print(f"     费用已达上限,跳过重复检测")
                except Exception as e:
                    print(f"     重复检测出错: {e}")

            model_tag = "R1" if "reasoner" in self.extraction_model else "V3"
            msg = f"{model_tag}提取{cnt}个知识点(v2.1.1)"
            if qc_count > 0:
                msg += f" [已质检{qc_count}条]"
            if pv_count > 0:
                msg += f" [已政策校验{pv_count}条]"
            if dup_count > 0:
                msg += f" [发现{dup_count}组疑似重复]"
            if extraction_notes:
                msg += " [有补漏建议]"
            self.db.update_source_file(fid, process_status="completed", process_message=msg)
            result.update({"success": True, "knowledge_count": cnt, "kps_info": kps_info})
            print(f"     [OK] {cnt}个知识点已存入待审核队列(Prompt:{get_prompt_version()})")

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
        print(f"  乡村振兴知识库 - 知识点提取引擎 v2.1.1")
        print(f"  产品导向提取 | Prompt:{get_prompt_version()}")
        print(f"  启动时间: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}")
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
        print(f"  分段策略: 三级智能分段(V3结构摘要 > 本地规则 > 段落边界)")
        print(f"  标签体系: 三层标签(6组41个分类标签 + 8维度属性 + 自由关键词)")
        print(f"  新增功能: V3预分析+上下文接力+跨段补漏+V3质检+政策校验+举一反三+重复检测")
        print(f"{'-' * 60}")

        total_kps, ok, fail, skip = 0, 0, 0, 0
        all_kps_info = []
        self._report_progress(total_files=len(files), current_file=0, current_filename="",
                              current_step="准备开始", total_extracted=0, message="开始提取")
        for i, rec in enumerate(files, 1):
            fn = rec.get("renamed_filename") or rec["original_filename"]
            print(f"\n[{i}/{len(files)}] {fn}")
            self._report_progress(total_files=len(files), current_file=i, current_filename=fn,
                                  current_step="开始处理", total_extracted=total_kps, message="")
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
        print(f"  Prompt版本: {get_prompt_version()}")
        print(f"  文件统计: {ok}个成功 / {skip}个跳过 / {fail}个失败")
        print(f"  知识点数: 共提取{total_kps}个，已V3质检(含举一反三)+政策校验+重复检测，等待人工审核")
        print(f"  今日费用: {usage['today_cost']:.2f}元 (剩余{usage['remaining']:.2f}元)")
        print(f"{'-' * 60}")
        print(f"  下一步: 运行[启动审核界面.bat]审核知识点")
        print(f"{'=' * 60}")

    def run_headless(self, model_key="1"):
        """非交互式运行，供管理后台API调用。返回结果字典。"""
        self.set_model(model_key)
        # 自动执行迁移
        try:
            from scripts.migrate_v210c import migrate; migrate()
        except ImportError: pass
        try:
            from scripts.migrate_v210d_f028 import migrate as m2; m2()
        except ImportError: pass
        try:
            from scripts.migrate_v211 import migrate as m3; m3()
        except ImportError: pass
        try:
            from scripts.migrate_v211_dup import migrate as m4; m4()
        except ImportError: pass

        files = self.get_processing_files()
        if not files:
            self._report_progress(message="无待提取文件", total_files=0, current_file=0,
                                  current_step="完成", total_extracted=0)
            return {"success": True, "ok": 0, "fail": 0, "skip": 0, "total_kps": 0, "message": "无待提取文件"}

        total_kps, ok, fail, skip = 0, 0, 0, 0
        all_kps_info = []
        self._report_progress(total_files=len(files), current_file=0, current_filename="",
                              current_step="准备开始", total_extracted=0, message="开始提取")
        for i, rec in enumerate(files, 1):
            fn = rec.get("renamed_filename") or rec["original_filename"]
            self._report_progress(total_files=len(files), current_file=i, current_filename=fn,
                                  current_step="开始处理", total_extracted=total_kps)
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
                    break

        if all_kps_info:
            self._check_category_suggestions(all_kps_info)

        self._report_progress(total_files=len(files), current_file=len(files),
                              current_step="完成", total_extracted=total_kps,
                              message="提取完成: %d成功/%d跳过/%d失败, 共%d条知识点" % (ok, skip, fail, total_kps))
        return {"success": True, "ok": ok, "fail": fail, "skip": skip, "total_kps": total_kps,
                "message": "提取完成"}


def main():
    try:
        # v2.1.0-c: 自动检查数据库迁移
        try:
            from scripts.migrate_v210c import migrate
            migrate()
        except ImportError:
            try:
                from migrate_v210c import migrate
                migrate()
            except ImportError:
                pass  # 迁移脚本不存在，跳过
        # v2.1.0-d F028: 政策依赖校验字段迁移
        try:
            from scripts.migrate_v210d_f028 import migrate as migrate_f028
            migrate_f028()
        except ImportError:
            try:
                from migrate_v210d_f028 import migrate as migrate_f028
                migrate_f028()
            except ImportError:
                pass
        # v2.1.1 F038: 举一反三字段迁移
        try:
            from scripts.migrate_v211 import migrate as migrate_v211
            migrate_v211()
        except ImportError:
            try:
                from migrate_v211 import migrate as migrate_v211
                migrate_v211()
            except ImportError:
                pass
        # v2.1.1 F039: 重复检测表迁移
        try:
            from scripts.migrate_v211_dup import migrate as migrate_dup
            migrate_dup()
        except ImportError:
            try:
                from migrate_v211_dup import migrate as migrate_dup
                migrate_dup()
            except ImportError:
                pass
        Extractor().run()
    except KeyboardInterrupt:
        print(f"\n\n  已取消操作。")
    except Exception as e:
        print(f"\n  [ERROR] {e}")
    input("\n按回车键退出...")


if __name__ == "__main__":
    main()
