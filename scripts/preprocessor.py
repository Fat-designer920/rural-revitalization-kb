"""
preprocessor.py - 智能预处理(文件重命名+AI标签建议+质量评分)
路径：scripts/preprocessor.py
版本：v2.3.7-part8 - 集成doc_structure地域检测+质量评分
"""
import os,sys,json,shutil
from pathlib import Path
PROJECT_ROOT = Path(__file__).parent.parent
sys.path.insert(0, str(PROJECT_ROOT))

from scripts.file_reader import FileReader
from scripts.deepseek_client import DeepSeekClient, CostLimitExceeded
from scripts.db_manager import DatabaseManager
from scripts.prompts.prompt_templates import FILE_RENAME_PROMPT
from scripts.doc_structure import ChineseDocAnalyzer

class Preprocessor:
    def __init__(self):
        p = PROJECT_ROOT/"config"/"settings.json"
        if not p.exists(): raise FileNotFoundError("未找到配置文件")
        with open(p,"r",encoding="utf-8") as f: self.config = json.load(f)
        self.reader = FileReader(self.config)
        self.client = DeepSeekClient(self.config)
        self.db = DatabaseManager()
        self.pending = Path(self.config.get("pending_path", PROJECT_ROOT/"data"/"pending"))
        self.processing = Path(self.config.get("processing_path", PROJECT_ROOT/"data"/"processing"))
        self.completed = Path(self.config.get("completed_path", PROJECT_ROOT/"data"/"completed"))

    def scan(self):
        files = self.reader.scan_directory(str(self.pending))
        return [f for f in files if not f["name"].startswith("请将")]

    def _sanitize(self, name):
        for c in '<>:"/\\|?*': name = name.replace(c,"_")
        return name[:60].strip()

    def _clean_completed_file(self, ename):
        """清理completed目录中的旧文件及.md伴侣文件"""
        old_file = self.completed / ename
        if old_file.exists():
            try:
                old_file.unlink()
                print(f"     已清理completed旧文件: {ename}")
            except Exception as e:
                print(f"     ! 清理旧文件失败: {e}")
        # 清理.md伴侣文件
        old_md = self.completed / (Path(ename).stem + ".md")
        if old_md.exists():
            try:
                old_md.unlink()
                print(f"     已清理completed旧缓存: {old_md.name}")
            except Exception as e:
                print(f"     ! 清理旧缓存失败: {e}")

    def preprocess_file(self, fi, doc_origin="external", force_reprocess=False):
        result = {"success":False,"file_id":None,"renamed":"","content_type":"","content":"","error":""}
        try:
            print(f"\n  >> 正在处理: {fi['name']}")
            print(f"     读取文件...")
            rr = self.reader.read_file(fi["path"])
            if not rr["success"]: result["error"]=rr["error"]; return result
            content = rr["content"]
            if rr.get("metadata",{}).get("needs_ocr"):
                if fi["type"] == "pdf":
                    print(f"     扫描件PDF，调用硅基流动OCR...")
                else:
                    print(f"     图片文件，调用硅基流动OCR...")
                ocr_result = self.client.ocr_image(fi["path"])
                content = ocr_result["content"]
                print(f"     OCR费用: ~{ocr_result.get('estimated_cost', 0):.4f}元")
            if not content or len(content.strip())<20:
                result["error"]="内容过少(OCR识别失败或文件为空)"; return result
            result["content"] = content

            # ── 规则级文档分析(MinerU启发: AI调用前先做零成本结构扫描) ──
            quality_score = 0
            doc_region = None
            try:
                quality_score, q_reasons = ChineseDocAnalyzer.score_document_quality(content)
                doc_region = ChineseDocAnalyzer.detect_region(content)
                doc_meta = ChineseDocAnalyzer.extract_metadata(content)
                doc_hierarchy = ChineseDocAnalyzer.detect_hierarchy(content)
                if quality_score >= 20:
                    print(f"     文档质量: {quality_score}/100")
                    if doc_meta.get("document_number"):
                        print(f"     发文字号: {doc_meta['document_number']}")
                    if doc_region:
                        print(f"     检测地域: {doc_region}")
                if doc_hierarchy:
                    print(f"     层级节点: {len(doc_hierarchy)}个" f"({'/'.join(h['level'] for h in doc_hierarchy[:8])}" +
                          ("..." if len(doc_hierarchy) > 8 else ")"))
                result["quality_score"] = quality_score
                result["detected_region"] = doc_region
                result["doc_structure"] = {
                    "meta": {k: v for k, v in doc_meta.items() if v},
                    "hierarchy_count": len(doc_hierarchy),
                    "doc_type": ChineseDocAnalyzer.classify_doc_type(content),
                    "key_sections": list(ChineseDocAnalyzer.extract_key_sections(content).keys()),
                }
            except (ValueError, TypeError, AttributeError, KeyError):
                pass  # 非公文体文本跳过

            # 文件级去重: 检查hash是否已存在
            fhash = rr.get("file_hash")
            if fhash:
                existing = self.db.check_file_hash_exists(fhash)
                if existing:
                    e_status = existing.get("process_status", "")
                    ename = existing.get("renamed_filename") or existing.get("original_filename") or "?"
                    e_id = existing["id"]
                    # 已完成提取的文件
                    if e_status == "completed":
                        if force_reprocess:
                            # 强制重新处理: 删旧知识点+注解+source_file记录+completed旧文件
                            print(f"     [强制重处理] 删除旧数据(#{e_id} {ename})...")
                            deleted_count = self.db.delete_kps_by_source_file(e_id)
                            print(f"     已删除 {deleted_count} 条旧知识点")
                            # v2.3.4-hotfix2: 用 purge 级联清 operation_events + 事务安全
                            try:
                                sf_del, ev_del = self.db.purge_source_file_record(e_id)
                                if ev_del:
                                    print(f"     已级联清理 operation_events {ev_del} 条")
                            except Exception as de:
                                print(f"     ! 清理source_files记录失败: {de}")
                            self._clean_completed_file(ename)
                            # 不return，继续走正常预处理流程
                        else:
                            print(f"     [跳过] 文件已存在(#{e_id} {ename}, 状态:{e_status})")
                            result["error"] = "重复文件(已存在#%d %s)" % (e_id, ename)
                            return result
                    # processing/failed状态:检查物理文件是否还在
                    elif e_status in ("processing", "failed"):
                        e_file = self.processing / ename
                        if e_file.exists():
                            print(f"     [跳过] 文件已在处理中(#{e_id} {ename})")
                            result["error"] = "重复文件(已存在#%d %s)" % (e_id, ename)
                            return result
                        # 物理文件已不存在,清理旧记录,允许重新处理
                        print(f"     旧记录#{e_id}物理文件已不存在,清理后重新处理")
                        # v2.3.4-hotfix2: 用 purge 级联清 operation_events + 事务安全
                        try:
                            sf_del, ev_del = self.db.purge_source_file_record(e_id)
                            if ev_del:
                                print(f"     已级联清理 operation_events {ev_del} 条")
                        except Exception as de:
                            print(f"     ! 清理旧记录失败: {de}")
                    else:
                        # 其他未知状态,也清理旧记录
                        print(f"     旧记录#{e_id}状态异常({e_status}),清理后重新处理")
                        # v2.3.4-hotfix2: 用 purge 级联清 operation_events + 事务安全
                        try:
                            sf_del, ev_del = self.db.purge_source_file_record(e_id)
                            if ev_del:
                                print(f"     已级联清理 operation_events {ev_del} 条")
                        except Exception as de:
                            print(f"     ! 清理旧记录失败: {de}")

            print(f"     AI分析中...")
            up = FILE_RENAME_PROMPT["user_prompt_template"].format(
                original_filename=fi["name"], file_type=fi["type"], content_preview=content[:3000])
            ai = self.client.chat_with_json(FILE_RENAME_PROMPT["system_prompt"], up, temperature=0.2, call_type="preprocess")
            parsed = ai.get("parsed_json") or {"renamed_filename":Path(fi["name"]).stem,"content_type":"policy","domain_tags":[],"region_tag":"","policy_level":"","brief_summary":""}

            ext = Path(fi["name"]).suffix
            renamed = self._sanitize(parsed.get("renamed_filename", Path(fi["name"]).stem))
            fid = self.db.add_source_file(fi["name"], fi["path"], fi["type"],
                int(fi["size_mb"]*1024*1024), rr.get("file_hash"), doc_origin=doc_origin)
            self.db.update_source_file(fid, renamed_filename=renamed+ext,
                domain_tags=json.dumps(parsed.get("domain_tags",[]),ensure_ascii=False),
                region_tag=parsed.get("region_tag",""), policy_level=parsed.get("policy_level",""),
                process_status="processing")

            dest = self.processing/(renamed+ext)
            cnt = 1
            while dest.exists(): dest = self.processing/f"{renamed}_{cnt}{ext}"; cnt+=1
            shutil.copy2(fi["path"], str(dest))

            # 保存提取内容为markdown文件(避免提取时重复读取/OCR)
            md_name = dest.stem + ".md"
            md_path = self.processing / md_name
            with open(str(md_path), "w", encoding="utf-8") as mf:
                mf.write(f"# {fi['name']}\n\n")
                # 写入公文结构元数据(MinerU启发: 保留文档层次, 辅助后续提取)
                ds = result.get("doc_structure", {})
                dmeta = ds.get("meta", {})
                if dmeta.get("document_number"):
                    mf.write(f"> 发文字号: {dmeta['document_number']}\n")
                if dmeta.get("title"):
                    mf.write(f"> 标题: {dmeta['title']}\n")
                if dmeta.get("issuing_agency"):
                    mf.write(f"> 发文机关: {dmeta['issuing_agency']}\n")
                if dmeta.get("date"):
                    mf.write(f"> 日期: {dmeta['date']}\n")
                if result.get("detected_region"):
                    mf.write(f"> 地域: {result['detected_region']}\n")
                if result.get("quality_score"):
                    mf.write(f"> 质量评分: {result['quality_score']}/100 | 类型: {ds.get('doc_type', '未知')}\n")
                if ds.get("key_sections"):
                    mf.write(f"> 关键章节: {' / '.join(ds['key_sections'])}\n")
                if dmeta:
                    mf.write("\n")
                mf.write(content)
            print(f"     已保存预处理内容: {md_name}")

            result.update({"success":True,"file_id":fid,"renamed":dest.name,"content_type":parsed.get("content_type","policy")})
            print(f"     [OK] -> {dest.name} [{result['content_type']}]")
            print(f"     费用: ~{ai['estimated_cost']}元")
        except CostLimitExceeded as e: result["error"]=str(e); print(f"\n     !! {e}")
        except Exception as e: result["error"]=f"{type(e).__name__}:{e}"; print(f"     [FAIL] {result['error']}")
        return result

    def run(self, doc_origin="external", force_reprocess=False):
        print("="*60)
        print("  稻也 - 文件预处理")
        print("="*60)
        if force_reprocess:
            print("  [!] 强制重新处理模式: 已完成文件将删除旧知识点后重新处理")
        usage = self.client.get_today_usage()
        print(f"\n  今日API: {usage['today_cost']}元/{usage['daily_limit']}元 ({usage['usage_percent']}%)")
        files = self.scan()
        if not files:
            print(f"\n  待处理目录为空: {self.pending}")
            print("  请将文件放入该文件夹后重试。"); return []
        print(f"\n  发现 {len(files)} 个文件:")
        for f in files: print(f"    {f['name']}  [{f['type']}]  {f['size_mb']}MB")
        print(f"\n{'-'*50}\n开始预处理...")
        results, ok, fail = [], 0, 0
        for i, fi in enumerate(files,1):
            print(f"\n[{i}/{len(files)}]", end="")
            r = self.preprocess_file(fi, doc_origin=doc_origin, force_reprocess=force_reprocess); results.append(r)
            if r["success"]: ok+=1
            else:
                fail+=1
                if "费用上限" in r.get("error",""): print("\n  !! 已达费用上限,停止"); break
        print(f"\n{'='*60}")
        print(f"  预处理完成! 成功:{ok} 失败:{fail}")
        print(f"{'='*60}")
        return results

def main():
    try:
        proc = Preprocessor()
        results = proc.run()
        ok = [r for r in results if r["success"]]
        if ok:
            print(f"\n  进入知识点提取阶段...")
            from scripts.extractor import Extractor
            Extractor().run()
        else: print("\n  无成功预处理文件,跳过提取。")
    except Exception as e: print(f"\n  [ERROR] {e}")
    input("\n按回车键退出...")

if __name__=="__main__": main()
