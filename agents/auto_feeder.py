"""
auto_feeder.py - 批量喂料器(全量文件+双模型+进度+断点续传+质检)
路径：agents/auto_feeder.py
版本：v2.3.7-part2
"""
import json, os, shutil, time, hashlib
from pathlib import Path
from datetime import datetime

PROJECT_ROOT = Path(__file__).parent.parent


class AutoFeeder(object):
    """批量喂料器。拷贝测试文件→预处理→提取(并行双模型)→质检,全自动管道。"""

    def __init__(self, db=None, client=None, progress_callback=None):
        self.db = db
        self.client = client
        self.progress_callback = progress_callback
        self._cancel = False

    # ================================================================
    # 文件盘点
    # ================================================================
    def inventory_test_files(self):
        """盘点测试目录所有可提取文件。返回 [{rel_path, name, ext, size, subdir}]"""
        test_root = PROJECT_ROOT / "测试用文件" / "乡村振兴资料库"
        if not test_root.exists():
            return []
        files = []
        for ext in [".docx", ".pdf", ".txt"]:
            for f in test_root.rglob(f"*{ext}"):
                if f.name.startswith("~") or f.name.startswith("."):
                    continue
                if f.stat().st_size < 500:
                    continue
                rel = f.relative_to(test_root)
                files.append({
                    "path": str(f),
                    "name": f.name,
                    "subdir": str(rel.parent) if str(rel.parent) != "." else "root",
                    "ext": f.suffix.lower(),
                    "size": f.stat().st_size,
                    "hash": hashlib.md5(str(f.stat().st_size).encode()).hexdigest()[:8],
                })
        return sorted(files, key=lambda x: (x["subdir"], x["name"]))

    def get_already_processed(self):
        """查询已入库(有KPs)的文件名集合。"""
        if not self.db:
            return set()
        try:
            conn = self.db.get_connection()
            c = conn.cursor()
            c.execute("""SELECT DISTINCT sf.renamed_filename, sf.original_filename
                         FROM source_files sf
                         INNER JOIN knowledge_points kp ON kp.source_file_id = sf.id""")
            rows = c.fetchall()
            conn.close()
            names = set()
            for r in rows:
                names.add(r[0] or "")
                names.add(r[1] or "")
            return names
        except Exception:
            return set()

    # ================================================================
    # 批量喂料(主入口)
    # ================================================================
    def feed_all(self, model_key="1", max_files=0, skip_existing=True):
        """全量喂料:盘点→拷贝→预处理→提取→质检。
        model_key: "1"=V4-Pro深度, "2"=V4-Flash快速, "parallel"=并行双模型(推荐)
        max_files: 0=全量, >0=限制数量
        skip_existing: 跳过已有confirmed KPs的文件
        返回 {files_total, files_copied, files_preprocessed, files_extracted,
               total_kps, ok, fail, skip, elapsed_sec, cost_estimate}
        """
        t0 = time.time()
        test_root = PROJECT_ROOT / "测试用文件" / "乡村振兴资料库"
        pending_dir = PROJECT_ROOT / "data" / "pending"
        os.makedirs(pending_dir, exist_ok=True)

        inventory = self.inventory_test_files()
        if not inventory:
            return {"success": False, "error": f"测试目录无文件: {test_root}"}

        already = self.get_already_processed() if skip_existing else set()
        pending = []
        skipped = 0
        for fi in inventory:
            if skip_existing and (fi["name"] in already):
                skipped += 1
                continue
            pending.append(fi)

        if max_files > 0:
            pending = pending[:max_files]

        if not pending:
            return {"success": True, "files_total": len(inventory), "files_skipped": skipped,
                    "files_copied": 0, "total_kps": 0, "message": "所有文件已处理完毕"}

        self._emit_progress("inventory", 0, len(pending),
                           f"盘点: {len(inventory)}个文件, {skipped}个已处理跳过, {len(pending)}个待提取")

        # Step 1: 拷贝到pending/ (子目录前缀防重名)
        copied = 0
        for fi in pending:
            dest_name = fi["name"]
            dest = pending_dir / dest_name
            if dest.exists():
                copied += 1  # 已存在
                continue
            try:
                shutil.copy2(fi["path"], str(dest))
                copied += 1
            except Exception as e:
                self._emit_progress("copy_error", copied, len(pending),
                                   f"拷贝失败: {fi['name']} - {e}")

        self._emit_progress("copy", copied, len(pending),
                           f"拷贝完成: {copied}/{len(pending)}")

        # Step 2: 预处理
        from scripts.preprocessor import Preprocessor
        pp = Preprocessor()
        all_files = pp.scan()
        preprocessed = 0
        for fi in all_files[:len(pending)]:
            if self._cancel:
                break
            try:
                rr = pp.preprocess_file(fi)
                if rr.get("success"):
                    preprocessed += 1
            except Exception:
                pass

        self._emit_progress("preprocess", preprocessed, len(pending),
                           f"预处理完成: {preprocessed}/{len(pending)}")

        # Step 3: 提取(支持并行双模型)
        from scripts.extractor import Extractor
        ext = Extractor(progress_callback=self._extract_progress)
        if model_key == "parallel":
            ext.set_model("1")  # 主模型V4-Pro,并行双模型在extract_from_file内部启用
            ext._use_parallel_dual = True
        else:
            ext.set_model(model_key)
            ext._use_parallel_dual = False

        result = ext.run_headless(model_key=model_key if model_key != "parallel" else "1")

        # Step 4: 质检新入库的KPs
        qc_result = self._run_qc_on_new()

        elapsed = time.time() - t0
        cost_est = self._estimate_cost(result.get("total_kps", 0), model_key)

        return {
            "success": True,
            "files_total": len(inventory),
            "files_skipped": skipped,
            "files_copied": copied,
            "files_preprocessed": preprocessed,
            "files_extracted": result.get("ok", 0),
            "total_kps": result.get("total_kps", 0),
            "ok": result.get("ok", 0),
            "fail": result.get("fail", 0),
            "skip": result.get("skip", 0),
            "qc_processed": qc_result.get("processed", 0),
            "elapsed_sec": round(elapsed, 1),
            "cost_estimate_cny": cost_est,
        }

    # ================================================================
    # 分批持续喂料
    # ================================================================
    def feed_batches(self, batch_size=10, total_batches=0, model_key="parallel"):
        """分批喂料,适合长时间运行。
        total_batches=0 表示直到文件耗尽。
        """
        results = []
        batch = 0
        while True:
            if self._cancel:
                break
            batch += 1
            if total_batches > 0 and batch > total_batches:
                break

            remaining = self._count_remaining()
            if remaining == 0:
                break

            actual = min(batch_size, remaining)
            r = self.feed_all(model_key=model_key, max_files=actual, skip_existing=True)
            results.append(r)

            self._emit_progress("batch_done", batch, total_batches or 999,
                               f"第{batch}批完成: +{r.get('total_kps',0)}KPs, "
                               f"累计{sum(x.get('total_kps',0) for x in results)}KPs, "
                               f"耗时{r.get('elapsed_sec',0)}秒, 估算¥{r.get('cost_estimate_cny',0)}")

            if r.get("total_kps", 0) == 0 and batch > 2:
                break
            if remaining <= 0:
                break

            time.sleep(10)  # 批次间冷却

        total_kps = sum(x.get("total_kps", 0) for x in results)
        total_cost = sum(x.get("cost_estimate_cny", 0) for x in results)
        return {
            "batches_completed": len(results),
            "total_kps": total_kps,
            "total_cost_estimate_cny": round(total_cost, 2),
            "results": results,
        }

    def cancel(self):
        self._cancel = True

    # ================================================================
    # 内部方法
    # ================================================================
    def _count_remaining(self):
        inv = self.inventory_test_files()
        already = self.get_already_processed()
        return sum(1 for f in inv if f["name"] not in already)

    def _run_qc_on_new(self):
        """对新增KPs跑质检"""
        if not self.db:
            return {"processed": 0}
        try:
            from scripts.extractor import Extractor
            ext = Extractor()
            conn = self.db.get_connection()
            c = conn.cursor()
            c.execute("""SELECT kp.id, kp.title, kp.original_excerpt, kp.final_category_id,
                                sf.renamed_filename, sf.original_filename
                         FROM knowledge_points kp
                         LEFT JOIN source_files sf ON kp.source_file_id = sf.id
                         WHERE kp.qa_score IS NULL OR kp.qa_score = 0.0
                         LIMIT 500""")
            rows = c.fetchall()
            conn.close()
            if not rows:
                return {"processed": 0}

            kps_info = [{"kp_id": r[0], "title": r[1]} for r in rows]
            ext._quality_check(
                filename="batch_qc",
                content_summary="",
                kps=rows,
                kps_info=kps_info,
                source_content="",
            )
            return {"processed": len(rows)}
        except Exception as e:
            return {"processed": 0, "error": str(e)[:200]}

    def _estimate_cost(self, total_kps, model_key):
        """估算费用(V4-Pro ¥1.05/M in, ¥12.5/M out; V4-Flash ¥1/M in, ¥2/M out)"""
        avg_tokens_per_kp = 800
        if model_key in ("1", "parallel"):
            price_per_m = 12.5
        else:
            price_per_m = 2.0
        return round(total_kps * avg_tokens_per_kp * price_per_m / 1000000, 2)

    def _emit_progress(self, stage, current, total, message):
        if self.progress_callback:
            try:
                self.progress_callback({
                    "stage": stage, "current": current, "total": total,
                    "message": str(message)[:300],
                })
            except Exception:
                pass

    def _extract_progress(self, data):
        """包装extractor进度→统一格式"""
        self._emit_progress(
            "extract",
            data.get("current_file", 0),
            data.get("total_files", 0),
            f"{data.get('current_filename','')} - {data.get('current_step','')} "
            f"已提取{data.get('total_extracted',0)}条",
        )

    # ================================================================
    # 一键全管道(喂料+提取+质检+关系)
    # ================================================================
    def run_full_pipeline(self, model_key="parallel", run_relations=True):
        """一键全管道: 喂料→提取→质检→关系扫描→就绪度联动。
        这是CEO调度知识管道的统一入口。
        """
        report = {
            "started_at": datetime.now().isoformat(),
            "stages": {},
        }

        # Stage 1: 喂料+提取+质检
        self._emit_progress("pipeline", 1, 5, "Stage 1/5: 批量喂料+提取+质检")
        feed_result = self.feed_all(model_key=model_key)
        report["stages"]["feed"] = feed_result

        if not feed_result.get("success"):
            report["error"] = "喂料阶段失败: " + feed_result.get("error", "?")
            return report

        # Stage 2: 质检补跑(全库)
        self._emit_progress("pipeline", 2, 5, "Stage 2/5: 全库质检补跑")
        qc_result = self._run_full_qc()
        report["stages"]["qc"] = qc_result

        # Stage 3: 就绪度联动
        self._emit_progress("pipeline", 3, 5, "Stage 3/5: 就绪度联动(draft→quotable)")
        readiness = self._run_readiness_promote()
        report["stages"]["readiness"] = readiness

        # Stage 4: 关系全量扫描(可选,耗时较长)
        if run_relations and self.db:
            self._emit_progress("pipeline", 4, 5, "Stage 4/5: 知识关系全量扫描(六态判别)")
            rel_result = self._run_full_relations()
            report["stages"]["relations"] = rel_result
        else:
            report["stages"]["relations"] = {"skipped": True}

        # Stage 5: 汇总
        self._emit_progress("pipeline", 5, 5, "Stage 5/5: 管道完成,汇总报告")
        total_kps = self._get_kp_count()
        report["stages"]["summary"] = {
            "total_kps": total_kps,
            "confirmed_kps": self._get_confirmed_count(),
            "premium_kps": self._get_premium_count(),
            "relation_edges": self._get_relation_count(),
        }
        report["completed_at"] = datetime.now().isoformat()

        self._emit_progress("pipeline_done", 5, 5,
                           f"全管道完成: {total_kps}条KP, 详情见report")
        return report

    def _run_full_qc(self):
        if not self.db:
            return {"error": "db未连接"}
        try:
            conn = self.db.get_connection(); c = conn.cursor()
            c.execute("SELECT COUNT(*) FROM knowledge_points WHERE qa_score IS NULL OR qa_score = 0.0")
            need_qc = c.fetchone()[0]
            conn.close()
            if need_qc == 0:
                return {"processed": 0, "message": "所有KP已质检"}
            from scripts.extractor import Extractor
            ext = Extractor()
            conn = self.db.get_connection(); c = conn.cursor()
            c.execute("""SELECT kp.id, kp.title, kp.original_excerpt,
                                sf.renamed_filename, sf.original_filename
                         FROM knowledge_points kp
                         LEFT JOIN source_files sf ON kp.source_file_id = sf.id
                         WHERE kp.qa_score IS NULL OR kp.qa_score = 0.0""")
            rows = c.fetchall()
            conn.close()
            for i in range(0, len(rows), 300):
                batch = rows[i:i+300]
                kps_info = [{"kp_id": r[0], "title": r[1]} for r in batch]
                try:
                    ext._quality_check("batch_qc", "", batch, kps_info, source_content="")
                except Exception:
                    pass
            return {"processed": len(rows)}
        except Exception as e:
            return {"error": str(e)[:200]}

    def _run_readiness_promote(self):
        if not self.db:
            return {"error": "db未连接"}
        try:
            result = self.db.promote_readiness_by_qa_score()
            return result
        except Exception as e:
            return {"error": str(e)[:200]}

    def _run_full_relations(self):
        if not self.db:
            return {"error": "db未连接"}
        try:
            from scripts.relation_analyzer import RelationAnalyzer
            ra = RelationAnalyzer(db=self.db, client=self.client)
            result = ra.scan_full()
            return {"relations_found": result.get("total_relations", 0) if isinstance(result, dict) else 0}
        except Exception as e:
            return {"error": str(e)[:200]}

    def _get_kp_count(self):
        try:
            conn = self.db.get_connection(); c = conn.cursor()
            c.execute("SELECT COUNT(*) FROM knowledge_points")
            v = c.fetchone()[0]; conn.close(); return v
        except Exception:
            return -1

    def _get_confirmed_count(self):
        try:
            conn = self.db.get_connection(); c = conn.cursor()
            c.execute("SELECT COUNT(*) FROM knowledge_points WHERE review_status='confirmed'")
            v = c.fetchone()[0]; conn.close(); return v
        except Exception:
            return -1

    def _get_premium_count(self):
        try:
            conn = self.db.get_connection(); c = conn.cursor()
            c.execute("SELECT COUNT(*) FROM knowledge_points WHERE content_readiness='premium'")
            v = c.fetchone()[0]; conn.close(); return v
        except Exception:
            return -1

    def _get_relation_count(self):
        try:
            conn = self.db.get_connection(); c = conn.cursor()
            c.execute("SELECT COUNT(*) FROM kp_relations")
            v = c.fetchone()[0]; conn.close(); return v
        except Exception:
            return -1
