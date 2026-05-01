"""
crawler_extractor.py - 爬取内容→结构化知识点管道
路径：scripts/crawler_extractor.py
版本：v2.3.7
"""
import json, os, shutil
from pathlib import Path


class CrawlerExtractor(object):
    """爬取内容加工管道:降噪→提取→打标→分级。复用现有 Extractor 和 ReaderAutoTagger。"""

    def __init__(self, db=None, client=None):
        self.db = db
        self.client = client

    def process_crawled(self, crawl_result):
        """处理单条爬取结果:降噪→提取→打标→分级。返回 {kp_count, tier}"""
        return {"kp_count": 0, "tier": "green"}  # Phase 4 完实现

    def _denoise_html(self, html_content):
        """HTML 降噪:去掉导航/广告/版权声明,保留正文"""
        return html_content  # Phase 4 完实现

    def batch_process(self, crawl_results, progress_callback=None):
        """批量处理爬取结果"""
        results = []
        for i, cr in enumerate(crawl_results):
            r = self.process_crawled(cr)
            results.append(r)
            if progress_callback:
                progress_callback({"current": i + 1, "total": len(crawl_results)})
        return results
