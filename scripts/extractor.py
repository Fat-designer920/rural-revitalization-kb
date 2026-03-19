"""
extractor.py - 知识点提取引擎
路径：scripts/extractor.py
版本：v1.0.1 - 模型可选R1/V3 + 重复文件询问 + 智能分段 + 截断自动拆分
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


class Extractor:
    TYPE_NAMES = {
        "policy": "政策文件", "case": "项目案例", "experience": "操盘经验",
        "tool": "实操工具", "data": "数据资料"
    }

    # 可选模型配置
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

        # 运行时选择的模型（由 select_model 设置）
        self.extraction_model = None
        self.extraction_model_name = None
        self.segment_max_len = 4000

    def select_model(self):
        """启动时让用户选择提取模型"""
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

    # === 文件指纹（MD5）===
    @staticmethod
    def calculate_file_hash(file_path):
        h = hashlib.md5()
        with open(file_path, "rb") as f:
            while True:
                chunk = f.read(8192)
                if not chunk:
                    break
                h.update(chunk)
        return h.hexdigest()

    def check_duplicate(self, file_path, filename):
        """
        检查文件是否已处理过。
        如果已成功提取过知识点,询问用户是否要重新分析。
        """
        file_hash = self.calculate_file_hash(file_path)
        existing = self.db.check_file_hash_exists(file_hash)
        if existing:
            exist_name = existing.get("renamed_filename") or existing.get("original_filename")
            exist_status = existing.get("process_status", "")
            exist_msg = existing.get("process_message", "")

            # 已成功提取过知识点的文件：询问用户
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

            # 之前失败或没提取到知识点：自动重新处理，不用问
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
        conn = self.db.get_connection()
        c = conn.cursor()
        c.execute("SELECT * FROM source_files WHERE process_status='processing' ORDER BY created_at")
        rows = [dict(r) for r in c.fetchall()]
        conn.close()
        return rows

    def _determine_type(self, rec, content):
        fn = (rec.get("renamed_filename") or rec["original_filename"]).lower()
        if any(k in fn for k in ["政策", "通知", "办法", "规定", "意见", "规划", "zc"]):
            return "policy"
        if any(k in fn for k in ["案例", "项目", "al"]):
            return "case"
        if any(k in fn for k in ["经验", "心得", "复盘", "jy"]):
            return "experience"
        if any(k in fn for k in ["模板", "工具", "合同", "gj"]):
            return "tool"
        if any(k in fn for k in ["数据", "统计", "测算", "sj"]):
            return "data"
        preview = content[:1000]
        if sum(1 for kw in ["发布", "施行", "通知", "各省", "第一条", "本办法"] if kw in preview) >= 2:
            return "policy"
        return "policy"

    def _split(self, content, max_len=None):
        if max_len is None:
            max_len = self.segment_max_len
        if len(content) <= max_len:
            return [content]
        segs, cur = [], ""
        for para in content.split("\n\n"):
            if len(cur) + len(para) > max_len and cur:
                segs.append(cur)
                cur = para
            else:
                cur = cur + "\n\n" + para if cur else para
        if cur:
            segs.append(cur)
        return segs

    def _extract_single(self, content, filename, prompt, ctype):
        up = prompt["user_prompt_template"].format(filename=filename, full_content=content)
        ai = self.client.chat_with_json(
            prompt["system_prompt"], up,
            temperature=0.2,
            call_type=f"extract_{ctype}",
            model_override=self.extraction_model
        )
        parsed = ai.get("parsed_json")
        was_truncated = ai.get("was_truncated", False)
        cost_info = f"(花费约{ai.get('estimated_cost', 0):.4f}元)"

        if was_truncated and parsed is None:
            print(f"       ! 输出被截断且无法抢救 {cost_info}")
            return "TRUNCATED"

        if parsed and isinstance(parsed, dict):
            kps = parsed.get("knowledge_points", [])
            notes = parsed.get("extraction_notes", "")
            if notes:
                print(f"       AI说明: {notes[:80]}")
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
        if current_max_len is None:
            current_max_len = self.segment_max_len

        result = self._extract_single(content, filename, prompt, ctype)

        if result == "TRUNCATED":
            new_max = current_max_len // 2
            if new_max < 500:
                print(f"       ! 内容过短仍被截断,跳过该段")
                return []
            print(f"       自动拆分为更小段(每段{new_max}字)重新提取...")
            sub_segs = self._split(content, max_len=new_max)
            all_kps = []
            for j, sub_seg in enumerate(sub_segs, 1):
                print(f"         子段{j}/{len(sub_segs)} ({len(sub_seg)}字)...")
                sub_kps = self._extract_with_auto_split(sub_seg, f"{filename}(子段{j})", prompt, ctype, new_max)
                all_kps.extend(sub_kps)
            return all_kps

        if isinstance(result, list):
            return result
        return []

    def _move_to_completed(self, fp, fn):
        try:
            dest = self.completed / fn
            c = 1
            while dest.exists():
                stem = Path(fn).stem
                ext = Path(fn).suffix
                dest = self.completed / f"{stem}_{c}{ext}"
                c += 1
            if os.path.exists(fp):
                shutil.copy2(fp, str(dest))
                if str(self.processing) in str(fp):
                    os.remove(fp)
                print(f"     文件已归档至: completed/{dest.name}")
        except Exception as e:
            print(f"     ! 文件归档失败: {e}")

    def _move_to_failed(self, fp, fn):
        try:
            dest = self.failed_dir / fn
            c = 1
            while dest.exists():
                stem = Path(fn).stem
                ext = Path(fn).suffix
                dest = self.failed_dir / f"{stem}_{c}{ext}"
                c += 1
            if os.path.exists(fp):
                shutil.copy2(fp, str(dest))
                if str(self.processing) in str(fp):
                    os.remove(fp)
                print(f"     文件已隔离至: failed/{dest.name}")
        except Exception as e:
            print(f"     ! 文件隔离失败: {e}")

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
                    fp = str(f)
                    break
            if not fp:
                fp = rec["file_path"]
            if not os.path.exists(fp):
                result["error"] = f"文件不存在:{fp}"
                print(f"     [FAIL] {result['error']}")
                return result

            # === 重复文件检测（会询问用户） ===
            is_dup, file_hash = self.check_duplicate(fp, fn)
            if is_dup:
                self.db.update_source_file(fid, process_status="completed",
                                           process_message="重复文件,用户选择跳过",
                                           file_hash=file_hash)
                self._move_to_completed(fp, fn)
                self._clean_pending(original_fn)
                result["error"] = "重复文件已跳过"
                return result

            self.db.update_source_file(fid, file_hash=file_hash)

            # === 读取文件内容 ===
            rr = self.reader.read_file(fp)
            if not rr["success"]:
                result["error"] = rr["error"]
                print(f"     [FAIL] 文件读取失败: {result['error']}")
                self._move_to_failed(fp, fn)
                self._clean_pending(original_fn)
                self.db.update_source_file(fid, process_status="failed", process_message=result["error"])
                return result
            content = rr["content"]
            if rr.get("metadata", {}).get("needs_ocr"):
                print(f"     图片文件,先进行OCR识别...")
                content = self.client.ocr_image(fp)["content"]

            # === 判断文件类型 ===
            ctype = self._determine_type(rec, content)
            prompt = get_extraction_prompt(ctype)
            print(f"     文件类型: {self.TYPE_NAMES.get(ctype, ctype)}")
            print(f"     内容长度: {len(content)}字")
            print(f"     提取模型: {self.extraction_model} ({self.extraction_model_name})")

            # === AI提取知识点 ===
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
                    seg,
                    f"{fn}(第{i}/{len(segs)}段)" if len(segs) > 1 else fn,
                    prompt, ctype
                )
                kps.extend(seg_kps)

            if not kps:
                self.db.update_source_file(fid, process_status="completed",
                                           process_message="未提取到知识点")
                self._move_to_completed(fp, fn)
                self._clean_pending(original_fn)
                result["error"] = "未提取到知识点"
                print(f"     [注意] 未提取到知识点")
                return result

            # === 写入数据库 ===
            print(f"\n     写入{len(kps)}个知识点到数据库...")
            cnt = 0
            for kp in kps:
                try:
                    cat_code = kp.get("suggested_category_code", "")
                    cat = self.db.find_category_by_code(cat_code)
                    self.db.add_knowledge_point(
                        source_file_id=fid,
                        title=kp.get("title", "未命名"),
                        content_type=ctype,
                        original_excerpt=kp.get("original_excerpt", ""),
                        ai_extracted_content=kp,
                        suggested_category_id=cat["id"] if cat else None,
                        suggested_tags=kp.get("suggested_tags", []),
                        source_page=str(kp.get("source_page", "")),
                        source_keyword=kp.get("source_keyword", "")
                    )
                    cnt += 1
                except Exception as e:
                    print(f"     ! 第{cnt + 1}个知识点入库失败: {e}")

            self._move_to_completed(fp, fn)
            self._clean_pending(original_fn)

            model_tag = "R1" if "reasoner" in self.extraction_model else "V3"
            self.db.update_source_file(fid, process_status="completed",
                                       process_message=f"{model_tag}提取{cnt}个知识点")
            result.update({"success": True, "knowledge_count": cnt})
            print(f"     [OK] {cnt}个知识点已存入待审核队列")

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
        print(f"  乡村振兴知识库 - 知识点提取引擎 v1.0.1")
        print(f"  启动时间: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}")
        print(f"{'=' * 60}")

        # 显示今日费用
        usage = self.client.get_today_usage()
        print(f"\n  今日API费用: {usage['today_cost']:.2f}元 / {usage['daily_limit']:.0f}元上限"
              f" (已用{usage['usage_percent']:.0f}%)")

        # 让用户选择模型
        self.select_model()

        files = self.get_processing_files()
        if not files:
            print(f"\n  无待提取文件。请先将文件放入 data/pending/ 文件夹并运行预处理。")
            return
        print(f"\n  共{len(files)}个文件待提取")
        print(f"  使用模型: {self.extraction_model_name} ({self.extraction_model})")
        print(f"  分段策略: 每段{self.segment_max_len}字")
        print(f"{'-' * 60}")

        total_kps, ok, fail, skip = 0, 0, 0, 0
        for i, rec in enumerate(files, 1):
            fn = rec.get("renamed_filename") or rec["original_filename"]
            print(f"\n[{i}/{len(files)}] {fn}")
            r = self.extract_from_file(rec)
            if r["success"]:
                ok += 1
                total_kps += r["knowledge_count"]
            elif "重复" in r.get("error", "") or "跳过" in r.get("error", ""):
                skip += 1
            else:
                fail += 1
                if "费用上限" in r.get("error", ""):
                    print(f"\n  !! 费用达到上限，剩余{len(files) - i}个文件下次再处理")
                    break

        usage = self.client.get_today_usage()
        print(f"\n{'=' * 60}")
        print(f"  提取完成!")
        print(f"  使用模型: {self.extraction_model_name}")
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
