"""
extractor.py - 知识点提取引擎
路径：scripts/extractor.py
"""
import os,sys,json,shutil
from pathlib import Path
PROJECT_ROOT = Path(__file__).parent.parent
sys.path.insert(0, str(PROJECT_ROOT))

from scripts.file_reader import FileReader
from scripts.deepseek_client import DeepSeekClient, CostLimitExceeded
from scripts.db_manager import DatabaseManager
from scripts.prompts.prompt_templates import get_extraction_prompt

class Extractor:
    TYPE_NAMES = {"policy":"政策文件","case":"项目案例","experience":"操盘经验","tool":"实操工具","data":"数据资料"}

    def __init__(self):
        p = PROJECT_ROOT/"config"/"settings.json"
        with open(p,"r",encoding="utf-8") as f: self.config = json.load(f)
        self.reader = FileReader(self.config)
        self.client = DeepSeekClient(self.config)
        self.db = DatabaseManager()
        self.processing = Path(self.config.get("processing_path", PROJECT_ROOT/"data"/"processing"))
        self.completed = Path(self.config.get("completed_path", PROJECT_ROOT/"data"/"completed"))

    def get_processing_files(self):
        conn = self.db.get_connection(); c = conn.cursor()
        c.execute("SELECT * FROM source_files WHERE process_status='processing' ORDER BY created_at")
        rows = [dict(r) for r in c.fetchall()]; conn.close(); return rows

    def _determine_type(self, rec, content):
        fn = (rec.get("renamed_filename") or rec["original_filename"]).lower()
        if any(k in fn for k in ["政策","通知","办法","规定","意见","规划","zc"]): return "policy"
        if any(k in fn for k in ["案例","项目","al"]): return "case"
        if any(k in fn for k in ["经验","心得","复盘","jy"]): return "experience"
        if any(k in fn for k in ["模板","工具","合同","gj"]): return "tool"
        if any(k in fn for k in ["数据","统计","测算","sj"]): return "data"
        preview = content[:1000]
        if sum(1 for kw in ["发布","施行","通知","各省","第一条","本办法"] if kw in preview) >= 2: return "policy"
        return "policy"

    def _split(self, content, max_len=6000):
        if len(content) <= max_len: return [content]
        segs, cur = [], ""
        for para in content.split("\n\n"):
            if len(cur)+len(para) > max_len and cur: segs.append(cur); cur = para
            else: cur = cur+"\n\n"+para if cur else para
        if cur: segs.append(cur)
        return segs

    def _extract_single(self, content, filename, prompt, ctype):
        up = prompt["user_prompt_template"].format(filename=filename, full_content=content)
        ai = self.client.chat_with_json(prompt["system_prompt"], up, temperature=0.2, max_tokens=4096, call_type=f"extract_{ctype}")
        parsed = ai.get("parsed_json")
        if parsed and isinstance(parsed, dict): return parsed.get("knowledge_points", [])
        if parsed and isinstance(parsed, list): return parsed
        return []

    def extract_from_file(self, rec):
        result = {"success":False, "knowledge_count":0, "error":""}
        fid = rec["id"]; fn = rec.get("renamed_filename") or rec["original_filename"]
        try:
            print(f"\n  >> 提取: {fn}")
            fp = None
            for f in self.processing.iterdir():
                if f.name == fn or f.name == rec["original_filename"]: fp=str(f); break
            if not fp: fp = rec["file_path"]
            if not os.path.exists(fp): result["error"]=f"文件不存在:{fp}"; return result

            rr = self.reader.read_file(fp)
            if not rr["success"]: result["error"]=rr["error"]; return result
            content = rr["content"]
            if rr.get("metadata",{}).get("needs_ocr"):
                content = self.client.ocr_image(fp)["content"]

            ctype = self._determine_type(rec, content)
            prompt = get_extraction_prompt(ctype)
            print(f"     类型: {self.TYPE_NAMES.get(ctype,ctype)}")
            print(f"     AI提取中...")

            if len(content) > 8000:
                segs = self._split(content)
                print(f"     长文档({len(content)}字), 分{len(segs)}段")
                kps = []
                for i,seg in enumerate(segs,1):
                    print(f"     提取第{i}/{len(segs)}段...")
                    kps.extend(self._extract_single(seg, f"{fn}(第{i}段)", prompt, ctype))
            else:
                kps = self._extract_single(content, fn, prompt, ctype)

            if not kps:
                self.db.update_source_file(fid, process_status="completed", process_message="未提取到知识点")
                result["error"]="未提取到知识点"; return result

            print(f"     写入{len(kps)}个知识点...")
            cnt = 0
            for kp in kps:
                try:
                    cat_code = kp.get("suggested_category_code","")
                    cat = self.db.find_category_by_code(cat_code)
                    self.db.add_knowledge_point(
                        source_file_id=fid, title=kp.get("title","未命名"),
                        content_type=ctype, original_excerpt=kp.get("original_excerpt",""),
                        ai_extracted_content=kp,
                        suggested_category_id=cat["id"] if cat else None,
                        suggested_tags=kp.get("suggested_tags",[]),
                        source_page=str(kp.get("source_page","")),
                        source_keyword=kp.get("source_keyword",""))
                    cnt += 1
                except Exception as e: print(f"     ! 入库失败: {e}")

            try:
                dest = self.completed/fn; c=1
                while dest.exists(): stem=Path(fn).stem; ext=Path(fn).suffix; dest=self.completed/f"{stem}_{c}{ext}"; c+=1
                if os.path.exists(fp):
                    shutil.copy2(fp, str(dest))
                    if str(self.processing) in fp: os.remove(fp)
            except: pass

            self.db.update_source_file(fid, process_status="completed", process_message=f"提取{cnt}个知识点")
            result.update({"success":True, "knowledge_count":cnt})
            print(f"     [OK] {cnt}个知识点已存入待审核队列")
        except CostLimitExceeded as e: result["error"]=str(e); print(f"\n     !! {e}")
        except Exception as e:
            result["error"]=f"{type(e).__name__}:{e}"; print(f"     [FAIL] {result['error']}")
            self.db.update_source_file(fid, process_status="failed", process_message=result["error"])
        return result

    def run(self):
        print(f"\n{'-'*50}")
        print("  知识点提取阶段")
        print(f"{'-'*50}")
        files = self.get_processing_files()
        if not files: print("\n  无待提取文件。"); return
        print(f"\n  共{len(files)}个文件待提取")
        total_kps, ok, fail = 0, 0, 0
        for i,rec in enumerate(files,1):
            print(f"\n[{i}/{len(files)}]", end="")
            r = self.extract_from_file(rec)
            if r["success"]: ok+=1; total_kps+=r["knowledge_count"]
            else:
                fail+=1
                if "费用上限" in r.get("error",""): break
        print(f"\n{'='*60}")
        print(f"  提取完成! 文件:{ok}成功/{fail}失败, 知识点:共{total_kps}个")
        print(f"  请运行[启动审核界面.bat]审核知识点")
        print(f"{'='*60}")

def main():
    try: Extractor().run()
    except Exception as e: print(f"\n  [ERROR] {e}")
    input("\n按回车键退出...")

if __name__=="__main__": main()
