"""
auto_feeder.py - 自动批量喂料器(测试文件+爬虫内容)
路径：scripts/auto_feeder.py
版本：v2.3.7
"""
import json, os, shutil, hashlib, time
from pathlib import Path

PROJECT_ROOT = Path(__file__).parent.parent


class AutoFeeder(object):
    """自动批量喂料器。将测试文件批量喂入知识库管道。"""

    def __init__(self, db=None, client=None):
        self.db = db
        self.client = client

    def feed_all_test_files(self, max_files=20):
        """批量喂入测试用文件。拷贝 max_files 个文件到 pending/ → 预处理 → 提取。返回 {files_processed, kps_extracted}"""
        test_root = PROJECT_ROOT / "测试用文件" / "乡村振兴资料库"
        if not test_root.exists():
            return {"success": False, "error": f"测试文件目录不存在: {test_root}"}

        pending_dir = PROJECT_ROOT / "data" / "pending"
        os.makedirs(pending_dir, exist_ok=True)

        # 收集测试文件(.docx/.pdf 优先)
        test_files = []
        for ext in [".docx", ".pdf"]:
            for f in test_root.rglob(f"*{ext}"):
                if not f.name.startswith("~") and not f.name.startswith("."):
                    test_files.append(f)
        test_files = test_files[:max_files]

        if not test_files:
            return {"success": False, "error": "无测试文件"}

        files_copied = 0
        for tf in test_files:
            dest = pending_dir / tf.name
            if not dest.exists():
                shutil.copy2(str(tf), str(dest))
                files_copied += 1

        if files_copied == 0:
            return {"success": True, "files_processed": 0, "kps_extracted": 0,
                    "message": f"{len(test_files)} 个文件已存在 pending 目录,跳过"}

        # 运行预处理
        kps_extracted = 0
        try:
            from scripts.preprocessor import Preprocessor
            pp = Preprocessor()
            files = pp.scan()
            for fi in files[:max_files]:
                try:
                    rr = pp.preprocess_file(fi)
                    if rr.get("success"):
                        kps_extracted += 1
                except Exception:
                    pass
        except Exception as e:
            return {"success": False, "error": f"预处理失败: {e}", "files_copied": files_copied}

        # 运行提取(headless)
        if kps_extracted > 0:
            try:
                from scripts.extractor import Extractor
                ext = Extractor()
                ext.set_model("2")  # V4-Flash 快速模式
                result = ext.run_headless(model_key="2")
                kps_extracted = result.get("total_kps", 0)
            except Exception as e:
                return {"success": True, "files_processed": files_copied,
                        "kps_extracted": kps_extracted, "extract_error": str(e)}

        return {"success": True, "files_processed": files_copied, "kps_extracted": kps_extracted}

    def feed_single_file(self, file_path):
        """喂入单个文件"""
        pending_dir = PROJECT_ROOT / "data" / "pending"
        os.makedirs(pending_dir, exist_ok=True)
        src = Path(file_path)
        if not src.exists():
            return {"success": False, "error": f"文件不存在: {file_path}"}
        dest = pending_dir / src.name
        if not dest.exists():
            shutil.copy2(str(src), str(dest))
        try:
            from scripts.preprocessor import Preprocessor
            pp = Preprocessor()
            files = pp.scan()
            for fi in files:
                if fi["name"] == src.name:
                    rr = pp.preprocess_file(fi)
                    if rr.get("success"):
                        from scripts.extractor import Extractor
                        ext = Extractor()
                        ext.set_model("2")
                        hr = ext.run_headless(model_key="2")
                        return {"success": True, "kps_extracted": hr.get("total_kps", 0)}
        except Exception as e:
            return {"success": False, "error": str(e)}
        return {"success": False, "error": "文件预处理失败"}
