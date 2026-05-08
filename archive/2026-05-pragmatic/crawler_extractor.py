"""
crawler_extractor.py - 爬取内容→结构化知识点管道
路径：scripts/crawler_extractor.py
版本：v2.3.8

v2.3.8: 从空壳重写为真实管道。
  输入: data/crawled/ 中CEO已批准的文件
  输出: 结构化的 knowledge_points (复用现有 Extractor 提取管道)
"""
import json, os, shutil
from pathlib import Path
from datetime import datetime

PROJECT_ROOT = Path(__file__).parent.parent


class CrawlerExtractor(object):
    """爬取内容加工管道: 爬取文件→提取→打标→入库。
    复用现有 Extractor 管道,不做独立提取。
    """

    def __init__(self, db=None, client=None):
        self.db = db
        self.client = client

    def batch_approve_and_process(self, filenames=None):
        """批量批准+处理: 将 crawled/ 中的文件移动到 pending/ 并触发提取。
        参数:
          filenames: 指定文件名列表, None=全部
        返回: {approved, errors}
        """
        review_dir = PROJECT_ROOT / "data" / "crawled"
        pending_dir = PROJECT_ROOT / "data" / "pending"
        os.makedirs(pending_dir, exist_ok=True)

        approved = []
        errors = []

        if filenames:
            files = [review_dir / f for f in filenames]
        else:
            files = sorted(review_dir.glob("*.txt"))
            files = [f for f in files if not f.name.startswith("crawl_report")]

        for fp in files:
            if not fp.exists():
                errors.append({"file": str(fp), "error": "文件不存在"})
                continue
            try:
                dst = pending_dir / fp.name
                shutil.move(str(fp), str(dst))
                approved.append({"from": str(fp), "to": str(dst)})
            except Exception as e:
                errors.append({"file": str(fp), "error": str(e)})

        return {
            "approved": approved,
            "errors": errors,
            "message": f"批准{len(approved)}个文件移至pending/, 错误{len(errors)}个。"
                       f"请执行 --feed-only 启动提取管道。"
        }

    def get_crawled_stats(self):
        """查看 crawled/ 目录统计"""
        review_dir = PROJECT_ROOT / "data" / "crawled"
        if not review_dir.exists():
            return {"total": 0, "files": []}

        files = sorted(review_dir.glob("*.txt"))
        files = [f for f in files if not f.name.startswith("crawl_report")]
        total_size = sum(f.stat().st_size for f in files)

        return {
            "total": len(files),
            "total_size_kb": round(total_size / 1024, 1),
            "files": [{
                "filename": f.name,
                "size": f.stat().st_size,
                "created": datetime.fromtimestamp(f.stat().st_ctime).isoformat(),
            } for f in files],
        }
