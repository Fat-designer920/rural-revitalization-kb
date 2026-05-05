"""
crawler_scheduler.py - 爬虫调度器(URL管理+去重+变化检测+限速)
路径：agents/crawler_scheduler.py
版本：v2.3.7
"""
import json, time, hashlib, os
from pathlib import Path
from datetime import datetime
try:
    import requests
except ImportError:
    requests = None

PROJECT_ROOT = Path(__file__).parent.parent

DEFAULT_TARGETS = [
    {"url": "https://www.mnr.gov.cn", "category": "policy", "schedule": "weekly"},
    {"url": "https://dnr.sc.gov.cn", "category": "policy", "schedule": "weekly"},
    {"url": "https://nynct.sc.gov.cn", "category": "policy", "schedule": "weekly"},
]


class CrawlerScheduler(object):
    """爬虫调度器。管理抓取源清单、限速、去重、变化检测。"""

    def __init__(self, db=None):
        self.db = db
        self._session = None
        self._targets = list(DEFAULT_TARGETS)  # 内存中持源清单

    def add_target(self, url, category="policy", schedule="daily"):
        """添加爬虫目标。返回 {added: true/false}"""
        for t in self._targets:
            if t["url"] == url:
                return {"added": False, "reason": "URL已存在"}
        self._targets.append({"url": url, "category": category, "schedule": schedule})
        return {"added": True, "url": url}

    def list_targets(self):
        return {"total": len(self._targets), "targets": self._targets}

    def run_scheduled(self, schedule="daily"):
        """按计划执行爬取: 遍历匹配 schedule 的目标→抓取→保存到 pending/
        返回 {fetched, new, skipped, errors, details}"""
        if not requests:
            return {"success": False, "error": "requests库未安装,无法爬取"}

        pending_dir = PROJECT_ROOT / "data" / "pending"
        os.makedirs(pending_dir, exist_ok=True)

        results = {"fetched": 0, "new": 0, "skipped": 0, "errors": 0, "details": []}
        targets = [t for t in self._targets if t["schedule"] in (schedule, "daily", "weekly")
                   or (schedule == "weekly" and t["schedule"] in ("daily", "weekly"))]

        for t in targets[:5]:  # 每轮最多5个URL,限速保护
            url = t["url"]
            try:
                fetched = self._fetch_url(url, timeout=30)
                results["fetched"] += 1
                if not fetched.get("success"):
                    results["errors"] += 1
                    results["details"].append({"url": url, "error": fetched.get("error", "?")})
                    continue

                content_hash = fetched.get("content_hash", "")
                if not self._check_changed(url, content_hash):
                    results["skipped"] += 1
                    results["details"].append({"url": url, "status": "unchanged"})
                    continue

                # 保存到 pending/ (仅保存前50KB,避免超大文件)
                safe_name = url.replace("https://", "").replace("http://", "").replace("/", "_")[:60]
                save_path = pending_dir / f"crawl_{safe_name}_{datetime.now().strftime('%Y%m%d_%H%M%S')}.html"
                content = fetched.get("content", "")[:50000]
                with open(save_path, "w", encoding="utf-8") as f:
                    f.write(content)
                results["new"] += 1
                results["details"].append({"url": url, "saved": str(save_path), "bytes": len(content)})

                # 记录到 crawl_history
                self._record_crawl(url, content_hash, str(save_path))
                time.sleep(2)  # 限速: 每URL间隔2秒
            except Exception as e:
                results["errors"] += 1
                results["details"].append({"url": url, "error": str(e)[:200]})

        return {"success": True, **results}

    def _fetch_url(self, url, timeout=30):
        """抓取单个URL"""
        if not self._session:
            self._session = requests.Session()
            self._session.headers.update({
                "User-Agent": "RuralRevitalizationKB/2.3.7 (knowledge-base-bot; contact@example.com)"
            })
        try:
            resp = self._session.get(url, timeout=timeout)
            resp.raise_for_status()
            content = resp.text
            return {
                "success": True,
                "content": content,
                "content_hash": hashlib.md5(content.encode("utf-8")).hexdigest(),
                "status_code": resp.status_code,
                "url": url,
            }
        except Exception as e:
            return {"success": False, "error": str(e), "url": url}

    def _check_changed(self, url, new_hash):
        """检查内容是否变化。True=已变化或新URL"""
        if not self.db:
            return True
        try:
            conn = self.db.get_connection()
            c = conn.cursor()
            c.execute("""SELECT content_hash FROM crawl_history
                         WHERE url=? ORDER BY fetched_at DESC LIMIT 1""", (url,))
            row = c.fetchone()
            conn.close()
            if row:
                return row[0] != new_hash
            return True  # 新URL
        except Exception:
            return True

    def _record_crawl(self, url, content_hash, saved_path):
        """记录爬取历史"""
        if not self.db:
            return
        try:
            conn = self.db.get_connection()
            c = conn.cursor()
            c.execute("""INSERT INTO crawl_history (url, content_hash, saved_path, fetched_at)
                         VALUES (?,?,?,datetime('now','localtime'))""",
                      (url, content_hash, saved_path))
            conn.commit()
            conn.close()
        except Exception:
            pass

    def get_status(self):
        """获取爬虫当前状态"""
        status = {"status": "idle", "targets": len(self._targets), "last_run": None}
        if self.db:
            try:
                conn = self.db.get_connection()
                c = conn.cursor()
                c.execute("SELECT COUNT(*) FROM crawl_history")
                status["total_crawls"] = c.fetchone()[0]
                c.execute("SELECT MAX(fetched_at) FROM crawl_history")
                last = c.fetchone()
                status["last_run"] = last[0] if last and last[0] else None
                conn.close()
            except Exception:
                pass
        return status
