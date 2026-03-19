"""
extractor.py - 知识点提取引擎
路径：scripts/extractor.py
版本：v1.0.1 - R1模型提取 + MD5去重 + failed隔离 + 进度增强
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

    # 使用R1模型做知识提取（更深度的推理分析）
    EXTRACTION_MODEL = "deepseek-reasoner"

    def __init__(self):
        p = PROJECT_ROOT / "config" / "settings.json"
        with open(p, "r", encoding="utf-8") as f:
            self.config = json.load(f)
        self.reader = FileReader(self.config)
        self.client = DeepSeekClient(self.config)
        self.db = DatabaseManager()
        self.processing = Path(self.config.get("processing_path", PROJECT_ROOT / "data" / "processing"))
        self.completed = Path(self.config.get("completed_path", PROJECT_ROOT / "data" / "completed"))
        self.failed_dir = Path(self.config.get("failed_path", PROJECT_ROOT / "data" / "failed"))
        # 确保文件夹存在
        self.completed.mkdir(parents=True, exist_ok=True)
        self.failed_dir.mkdir(parents=True, exist_ok=True)

    # === 文件指纹（MD5）===
    @staticmethod
    def calculate_file_hash(file_path):
        """计算文件MD5指纹，就像文件的身份证号"""
        h = hashlib.md5()
        with open(file_path, "rb") as f:
            while True:
                chunk = f.read(8192)
                if not chunk:
                    break
                h.update(chunk)
        return h.hexdigest()

    def check_duplicate(self, file_path, filename):
        """检查文件是否已处理过（通过MD5指纹判断）"""
        file_hash = self.calculate_file_hash(file_path)
        existing = self.db.check_file_hash_exists(file_hash)
        if existing:
            exist_name = existing.get("renamed_filename") or existing.get("original_filename")
            exist_status = existing.get("process_status")
            print(f"     [跳过] 文件已处理过(指纹相同)")
            print(f"            原记录: {exist_name} (状态:{exist_status})")
            return True, file_hash
        return False, file_hash

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

    def _split(self, content, max_len=12000):
        """
        长文档分段。R1模型支持更长上下文，阈值从6000提高到12000字。
        尽量在自然段落边界分割，保持语义完整。
        """
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
        """调用R1模型提取单段内容的知识点"""
        up = prompt["user_prompt_template"].format(filename=filename, full_content=content)
        ai = self.client.chat_with_json(
            prompt["system_prompt"], up,
            temperature=0.2, max_tokens=8192,
            call_type=f"extract_{ctype}",
            model_override=self.EXTRACTION_MODEL
        )
        parsed = ai.get("parsed_json")
        cost_info = f"(花费约{ai.get('estimated_cost', 0):.4f}元)"

        if parsed and isinstance(parsed, dict):
            kps = parsed.get("knowledge_points", [])
            notes = parsed.get("extraction_notes", "")
            if notes:
                print(f"       AI说明: {notes[:80]}")
            print(f"       本段提取{len(kps)}个知识点 {cost_info}")
            return kps
        if parsed and isinstance(parsed, list):
            print(f"       本段提取{len(parsed)}个知识点 {cost_info}")
            return parsed

        # JSON解析失败
        err = ai.get("json_parse_error", "未知错误")
        print(f"       ! JSON解析失败: {err} {cost_info}")
        return []

    def _move_to_completed(self, fp, fn):
        """将处理完成的文件移动到completed文件夹"""
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
                print(f"     文件已移至: completed/{dest.name}")
        except Exception as e:
            print(f"     ! 文件移动失败: {e}")

    def _move_to_failed(self, fp, fn):
        """将处理失败的文件移动到failed文件夹隔离"""
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
        fp = None

        try:
            print(f"\n  >> 开始提取: {fn}")

            # 定位文件
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

            # === 重复文件检测 ===
            is_dup, file_hash = self.check_duplicate(fp, fn)
            if is_dup:
                self.db.update_source_file(fid, process_status="completed",
                                           process_message="重复文件,已自动跳过",
                                           file_hash=file_hash)
                self._move_to_completed(fp, fn)
                result["error"] = "重复文件已跳过"
                return result

            # 更新文件指纹到数据库
            self.db.update_source_file(fid, file_hash=file_hash)

            # === 读取文件内容 ===
            rr = self.reader.read_file(fp)
            if not rr["success"]:
                result["error"] = rr["error"]
                print(f"     [FAIL] 文件读取失败: {result['error']}")
                self._move_to_failed(fp, fn)
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
            print(f"     提取模型: {self.EXTRACTION_MODEL} (R1深度推理)")
            print(f"     AI提取中（R1模型思考较慢,请耐心等待）...")

            # === AI提取知识点 ===
            if len(content) > 12000:
                segs = self._split(content)
                print(f"     长文档,分{len(segs)}段处理")
                kps = []
                for i, seg in enumerate(segs, 1):
                    print(f"\n     --- 第{i}/{len(segs)}段 ({len(seg)}字) ---")
                    seg_kps = self._extract_single(seg, f"{fn}(第{i}/{len(segs)}段)", prompt, ctype)
                    kps.extend(seg_kps)
            else:
                kps = self._extract_single(content, fn, prompt, ctype)

            if not kps:
                self.db.update_source_file(fid, process_status="completed",
                                           process_message="未提取到知识点")
                self._move_to_completed(fp, fn)
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

            # === 移动文件到completed ===
            self._move_to_completed(fp, fn)

            self.db.update_source_file(fid, process_status="completed",
                                       process_message=f"R1提取{cnt}个知识点")
            result.update({"success": True, "knowledge_count": cnt})
            print(f"     [OK] {cnt}个知识点已存入待审核队列")

        except CostLimitExceeded as e:
            result["error"] = str(e)
            print(f"\n     !! 费用超限: {e}")
        except Exception as e:
            result["error"] = f"{type(e).__name__}:{e}"
            print(f"     [FAIL] {result['error']}")
            # 失败的文件隔离到failed文件夹
            if fp and os.path.exists(fp):
                self._move_to_failed(fp, fn)
            self.db.update_source_file(fid, process_status="failed", process_message=result["error"])
        return result

    def run(self):
        print(f"\n{'=' * 60}")
        print(f"  乡村振兴知识库 - 知识点提取引擎 v1.0.1")
        print(f"  提取模型: {self.EXTRACTION_MODEL} (R1深度推理)")
        print(f"  启动时间: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}")
        print(f"{'=' * 60}")

        # 显示今日费用
        usage = self.client.get_today_usage()
        print(f"\n  今日API费用: {usage['today_cost']:.2f}元 / {usage['daily_limit']:.0f}元上限"
              f" (已用{usage['usage_percent']:.0f}%)")

        files = self.get_processing_files()
        if not files:
            print(f"\n  无待提取文件。请先将文件放入 data/pending/ 文件夹并运行预处理。")
            return
        print(f"\n  共{len(files)}个文件待提取")
        print(f"  提示: R1模型思考较深入,每个文件约需1-5分钟,请耐心等待")
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

        # 最终汇总
        usage = self.client.get_today_usage()
        print(f"\n{'=' * 60}")
        print(f"  提取完成!")
        print(f"  文件统计: {ok}个成功 / {skip}个跳过(重复) / {fail}个失败")
        print(f"  知识点数: 共提取{total_kps}个，等待人工审核")
        print(f"  今日费用: {usage['today_cost']:.2f}元 (剩余{usage['remaining']:.2f}元)")
        print(f"{'-' * 60}")
        print(f"  下一步: 运行[启动审核界面.bat]审核知识点")
        print(f"{'=' * 60}")


def main():
    try:
        Extractor().run()
    except Exception as e:
        print(f"\n  [ERROR] {e}")
    input("\n按回车键退出...")


if __name__ == "__main__":
    main()
