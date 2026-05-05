"""
auto_feeder.py - 自动批量喂料器(使用现有成熟管道)
路径：agents/auto_feeder.py
版本：v2.3.7
"""
import json, os, shutil, time
from pathlib import Path

PROJECT_ROOT = Path(__file__).parent.parent


class AutoFeeder(object):
    """自动批量喂料器。使用现有 Preprocessor + Extractor 成熟管道。"""

    def __init__(self, db=None, client=None):
        self.db = db
        self.client = client

    def feed_test_files(self, max_files=10):
        """批量喂入测试用文件:拷贝到pending/→预处理→提取(headless)"""
        test_root = PROJECT_ROOT / "测试用文件" / "乡村振兴资料库"
        pending_dir = PROJECT_ROOT / "data" / "pending"
        os.makedirs(pending_dir, exist_ok=True)

        if not test_root.exists():
            return {"success": False, "error": f"测试目录不存在: {test_root}"}

        # 收集文件
        test_files = []
        for ext in [".docx", ".pdf"]:
            for f in test_root.rglob(f"*{ext}"):
                if not f.name.startswith("~") and not f.name.startswith("."):
                    test_files.append(f)
        test_files = test_files[:max_files]

        # 拷贝到pending/
        copied = 0
        for tf in test_files:
            dest = pending_dir / tf.name
            if not dest.exists():
                shutil.copy2(str(tf), str(dest))
                copied += 1
        if copied == 0:
            return {"success": True, "files_processed": 0, "kps_extracted": 0,
                    "message": "文件均已存在pending目录"}

        # 运行预处理
        from scripts.preprocessor import Preprocessor
        pp = Preprocessor()
        files = pp.scan()
        preprocessed = 0
        for fi in files[:max_files]:
            try:
                rr = pp.preprocess_file(fi)
                if rr.get("success"):
                    preprocessed += 1
            except Exception:
                pass

        # 运行提取
        from scripts.extractor import Extractor
        ext = Extractor()
        ext.set_model("2")  # V4-Flash快速模式
        result = ext.run_headless(model_key="2")

        return {
            "success": True,
            "files_copied": copied,
            "files_preprocessed": preprocessed,
            "kps_extracted": result.get("total_kps", 0),
            "ok": result.get("ok", 0),
            "fail": result.get("fail", 0),
        }

    def feed_batch_continuous(self, batch_size=5, total_batches=10):
        """持续批量喂料:每批处理batch_size个文件,直到完成total_batches批或文件用完"""
        results = []
        for batch in range(total_batches):
            remaining = self._count_remaining_test_files()
            if remaining == 0:
                break
            actual_size = min(batch_size, remaining)
            r = self.feed_test_files(max_files=actual_size)
            results.append(r)
            if r.get("kps_extracted", 0) == 0 and batch > 2:
                break
            time.sleep(5)  # 冷却
        return {"batches_completed": len(results), "results": results}

    def _count_remaining_test_files(self):
        test_root = PROJECT_ROOT / "测试用文件" / "乡村振兴资料库"
        if not test_root.exists():
            return 0
        pending_dir = PROJECT_ROOT / "data" / "pending"
        pending_names = set(f.name for f in pending_dir.glob("*")) if pending_dir.exists() else set()
        count = 0
        for ext in [".docx", ".pdf"]:
            for f in test_root.rglob(f"*{ext}"):
                if not f.name.startswith("~") and f.name not in pending_names:
                    count += 1
        return count
