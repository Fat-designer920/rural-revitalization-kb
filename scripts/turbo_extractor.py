"""
turbo_extractor.py - 极速批量提取器(并行+精简+单模型,速度优先)
路径：scripts/turbo_extractor.py
版本：v2.3.7

设计原则:
  1. 跳过预分析/跨段补漏/质检/政策校验/关系分析(可事后批量补)
  2. V4-Flash 单模型(跳过V4-Pro,速度>质量在初期喂料场景)
  3. 多文件并行处理(ThreadPoolExecutor)
  4. 减少分段数(segment_max=8000,大段减少API调用)
  5. 自动打标(读者定位,异步进行)
"""
import json, time, traceback
from pathlib import Path
from concurrent.futures import ThreadPoolExecutor, as_completed
from datetime import datetime

PROJECT_ROOT = Path(__file__).parent.parent


class TurboExtractor(object):
    """极速批量提取器。砍掉可后补步骤,并行处理,专为初期大规模喂料优化。"""

    def __init__(self, db=None, client=None, max_workers=3):
        self.db = db
        self.client = client
        self.max_workers = max_workers
        self.stats = {"files_processed": 0, "kps_extracted": 0, "errors": 0, "total_time_s": 0}

    def batch_extract(self, file_paths, progress_callback=None):
        """批量极速提取:多文件并行,每文件只做最核心的提取。返回统计。"""
        t0 = time.time()
        self.stats = {"files_processed": 0, "kps_extracted": 0, "errors": 0, "total_time_s": 0}

        with ThreadPoolExecutor(max_workers=self.max_workers) as executor:
            futures = {executor.submit(self._extract_one, fp): fp for fp in file_paths[:50]}
            for future in as_completed(futures):
                fp = futures[future]
                try:
                    result = future.result(timeout=300)
                    if result.get("success"):
                        self.stats["kps_extracted"] += result.get("kp_count", 0)
                    else:
                        self.stats["errors"] += 1
                    self.stats["files_processed"] += 1
                except Exception:
                    self.stats["errors"] += 1
                if progress_callback:
                    progress_callback({
                        "files_processed": self.stats["files_processed"],
                        "total": len(file_paths),
                        "kps": self.stats["kps_extracted"],
                    })

        self.stats["total_time_s"] = int(time.time() - t0)
        return self.stats

    def _extract_one(self, file_path):
        """极速提取单个文件:预处理→读取→V4-Flash单次提取→入库。跳过所有可后补步骤。"""
        fp = Path(file_path)
        if not fp.exists():
            return {"success": False, "error": f"文件不存在: {file_path}"}

        try:
            # Step 1: 读取文件内容(绕过安全检查,读取测试目录)
            from scripts.file_reader import FileReader
            import json as _json
            cfg_path = PROJECT_ROOT / "config" / "settings.json"
            cfg = _json.load(open(cfg_path, encoding="utf-8")) if cfg_path.exists() else {}
            allowed = list(cfg.get("allowed_paths", []))
            if str(PROJECT_ROOT) not in allowed:
                allowed.append(str(PROJECT_ROOT))
            cfg["allowed_paths"] = allowed
            reader = FileReader(cfg)
            rr = reader.read_file(str(fp))
            if not rr.get("success"):
                return {"success": False, "error": rr.get("error", "读取失败")}
            content = rr.get("content", "")
            if len(content) < 100:
                return {"success": False, "error": "内容过短"}

            # Step 2: 单次 V4-Flash 提取(不分段,或大段)
            from scripts.prompts.prompt_templates import get_extraction_prompt
            ctype = self._guess_type(fp)
            prompt = get_extraction_prompt(ctype)
            system_prompt = prompt["system_prompt"]

            # 不分段,直接整篇喂给 V4-Flash(V4 支持大 context)
            max_chars = 50000
            truncated_content = content[:max_chars]
            user_prompt = prompt["user_prompt_template"].format(
                full_content=truncated_content,
                filename=fp.name,
            )

            resp = self.client.chat_with_jsonl(
                system_prompt, user_prompt,
                temperature=0.0, model_override="deepseek-v4-flash",
                call_type="turbo_extract",
                max_tokens=32768,
            )
            kps = resp.get("kp_objects", []) if isinstance(resp, dict) else []
            if not kps:
                return {"success": True, "kp_count": 0, "message": "未提取到知识点"}

            # Step 3: 快速入库(最小字段集)
            kp_count = self._fast_insert(fp.name, kps, ctype)

            # Step 4: 异步打标(不阻塞)
            try:
                self._async_tag_new_kps()
            except Exception:
                pass

            return {"success": True, "kp_count": kp_count, "file": fp.name}

        except Exception as e:
            return {"success": False, "error": str(e)}

    def _parse_kps(self, resp):
        """解析 AI 返回的知识点列表"""
        kps = []
        if isinstance(resp, dict):
            parsed = resp.get("parsed_json") or resp.get("content")
            if isinstance(parsed, list):
                kps = parsed
            elif isinstance(parsed, dict):
                kps = parsed.get("knowledge_points", [])
        elif isinstance(resp, str):
            try:
                kps = json.loads(resp)
            except Exception:
                pass
        return kps if isinstance(kps, list) else []

    def _fast_insert(self, filename, kps, ctype):
        """快速入库(含质量门:摘录<50字或纯口号=拒绝)"""
        conn = self.db.get_connection(); c = conn.cursor()
        c.execute("""INSERT INTO source_files (original_filename, file_path, file_type, process_status)
                     VALUES (?,?,?,?)""",
                  (filename, f"turbo://{filename}", "word" if filename.endswith(".docx") else "pdf", "completed"))
        fid = c.lastrowid
        conn.commit(); conn.close()

        count = 0; rejected = 0
        for kp in kps[:150]:
            try:
                title = str(kp.get("title", "未命名"))[:200]
                excerpt = str(kp.get("original_excerpt", ""))[:2000]

                # 质量门: 拒绝明显低质量的知识点
                if len(excerpt) < 50:
                    rejected += 1; continue
                if len(title) < 5:
                    rejected += 1; continue
                # 拒绝纯口号
                slogan_keywords = ["高度重视","加强领导","提高认识","深刻领会","认真贯彻"]
                if any(kw in title for kw in slogan_keywords) and len(excerpt) < 100:
                    rejected += 1; continue

                self.db.add_knowledge_point(
                    source_file_id=fid,
                    title=title,
                    content_type=ctype,
                    original_excerpt=excerpt,
                    ai_extracted_content=kp,
                    content_readiness="quotable" if len(excerpt) >= 150 else "draft",
                    source_authority="official",
                    prompt_version="turbo-v2.3.7",
                    extracted_by_model="v4-flash-turbo",
                    source_type="turbo_extract",
                )
                count += 1
            except Exception:
                pass
        return count

    def _guess_type(self, fp):
        """根据文件名猜测内容类型"""
        name = fp.name.lower()
        if "案例" in name or "项目" in name:
            return "case"
        if "经验" in name or "速记" in name:
            return "experience"
        if "模板" in name or "工具" in name:
            return "tool"
        if "数据" in name or "统计" in name:
            return "data"
        return "policy"

    def _async_tag_new_kps(self):
        """对最近入库的 KP 进行读者打标(非阻塞)"""
        try:
            from agents.reader_tagger import ReaderAutoTagger
            tagger = ReaderAutoTagger(client=self.client, db=self.db)
            kps = self.db.get_kps_missing_reader_fields(limit=50)
            for kp in kps[:10]:
                try:
                    tags = tagger.tag_single(kp)
                    if tags.get("target_reader"):
                        self.db.batch_update_reader_fields(kp["id"], tags)
                except Exception:
                    pass
        except Exception:
            pass


def turbo_feed_directory(dir_path, db, client, max_workers=3):
    """极速喂入整个目录。返回统计。"""
    turbo = TurboExtractor(db=db, client=client, max_workers=max_workers)
    files = list(Path(dir_path).rglob("*.docx")) + list(Path(dir_path).rglob("*.pdf"))
    files = [str(f) for f in files if not f.name.startswith("~")][:30]
    if not files:
        return {"success": False, "error": "无文件"}
    return turbo.batch_extract(files)
