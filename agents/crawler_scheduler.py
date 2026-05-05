"""
crawler_scheduler.py - 爬虫调度器(URL管理+去重+变化检测+限速)
路径：agents/crawler_scheduler.py
版本：v2.3.7
"""
import json, time, hashlib, os, re
from pathlib import Path
from datetime import datetime
try:
    import requests
except ImportError:
    requests = None

PROJECT_ROOT = Path(__file__).parent.parent

DEFAULT_TARGETS = [
    # 国家级
    {"url": "https://www.mnr.gov.cn", "category": "policy", "schedule": "weekly"},
    {"url": "https://www.gov.cn", "category": "policy", "schedule": "weekly"},
    # 四川省省级
    {"url": "https://dnr.sc.gov.cn", "category": "policy", "schedule": "weekly"},
    {"url": "https://nynct.sc.gov.cn", "category": "policy", "schedule": "weekly"},
    {"url": "https://fgw.sc.gov.cn", "category": "policy", "schedule": "weekly"},
    {"url": "https://czt.sc.gov.cn", "category": "policy", "schedule": "weekly"},
    {"url": "https://ggzyjy.sc.gov.cn", "category": "project", "schedule": "weekly"},
    {"url": "https://www.ccgp-sichuan.gov.cn", "category": "project", "schedule": "weekly"},
    # 四川21市州(按GDP排序)
    {"url": "https://www.chengdu.gov.cn", "category": "policy", "schedule": "weekly"},
    {"url": "https://www.mianyang.gov.cn", "category": "policy", "schedule": "weekly"},
    {"url": "https://www.yibin.gov.cn", "category": "policy", "schedule": "weekly"},
    {"url": "https://www.deyang.gov.cn", "category": "policy", "schedule": "weekly"},
    {"url": "https://www.nanchong.gov.cn", "category": "policy", "schedule": "weekly"},
    {"url": "https://www.luzhou.gov.cn", "category": "policy", "schedule": "weekly"},
    {"url": "https://www.dazhou.gov.cn", "category": "policy", "schedule": "weekly"},
    {"url": "https://www.leshan.gov.cn", "category": "policy", "schedule": "weekly"},
    {"url": "https://www.zigong.gov.cn", "category": "policy", "schedule": "biweekly"},
    {"url": "https://www.guangan.gov.cn", "category": "policy", "schedule": "biweekly"},
    {"url": "https://www.ms.gov.cn", "category": "policy", "schedule": "biweekly"},
    {"url": "https://www.suining.gov.cn", "category": "policy", "schedule": "biweekly"},
    {"url": "https://www.neijiang.gov.cn", "category": "policy", "schedule": "biweekly"},
    {"url": "https://www.guangyuan.gov.cn", "category": "policy", "schedule": "biweekly"},
    {"url": "https://www.bazhong.gov.cn", "category": "policy", "schedule": "biweekly"},
    {"url": "https://www.ziyang.gov.cn", "category": "policy", "schedule": "biweekly"},
    {"url": "https://www.yaan.gov.cn", "category": "policy", "schedule": "biweekly"},
    {"url": "https://www.panzhihua.gov.cn", "category": "policy", "schedule": "biweekly"},
    {"url": "https://www.abazhou.gov.cn", "category": "policy", "schedule": "monthly"},
    {"url": "https://www.ganzi.gov.cn", "category": "policy", "schedule": "monthly"},
    {"url": "https://www.liangshan.gov.cn", "category": "policy", "schedule": "monthly"},
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

                # 提取正文文本(非原始HTML),保存为.txt到pending/
                text_content = self._extract_text(fetched.get("content", ""),
                                                  url=url, category=t.get("category", "policy"))
                safe_name = self._safe_filename(url)
                save_path = pending_dir / f"crawl_{safe_name}_{datetime.now().strftime('%Y%m%d_%H%M%S')}.txt"
                with open(save_path, "w", encoding="utf-8") as f:
                    f.write(text_content[:80000])  # 最多80KB文本
                results["new"] += 1
                results["details"].append({"url": url, "saved": str(save_path),
                                           "chars": len(text_content)})

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

    # ================================================================
    # HTML→文本提取
    # ================================================================
    def _extract_text(self, html, url="", category="policy"):
        """从HTML提取正文文本。策略: 去标签→去脚本/样式→压缩空白→截取有意义的段落。"""
        if not html:
            return ""
        # 去script/style标签及其内容
        text = re.sub(r'<script[^>]*>.*?</script>', ' ', html, flags=re.DOTALL | re.IGNORECASE)
        text = re.sub(r'<style[^>]*>.*?</style>', ' ', text, flags=re.DOTALL | re.IGNORECASE)
        text = re.sub(r'<head[^>]*>.*?</head>', ' ', text, flags=re.DOTALL | re.IGNORECASE)
        # 去HTML标签
        text = re.sub(r'<[^>]+>', ' ', text)
        # 去HTML实体
        text = re.sub(r'&[a-z]+;', ' ', text)
        text = re.sub(r'&#\d+;', ' ', text)
        # 去多余空白
        text = re.sub(r'\s+', ' ', text).strip()
        # 去导航/页脚噪音(短行密集区)
        lines = [l.strip() for l in text.split('.') if len(l.strip()) > 15]
        text = '。\n'.join(lines)
        # 加来源标记
        header = f"来源: {url}\n抓取时间: {datetime.now().isoformat()}\n类别: {category}\n\n"
        return header + text

    def _safe_filename(self, url):
        """从URL生成安全文件名"""
        name = url.replace("https://", "").replace("http://", "").replace("/", "_").replace(".", "_")
        name = re.sub(r'[<>:"|?*]', '_', name)
        return name[:60]

    # ================================================================
    # 爬取+自动喂入提取管道
    # ================================================================
    def crawl_and_feed(self, schedule="weekly", max_urls=5):
        """爬取→保存.txt到pending/→自动触发提取。
        这是CEO驱动的知识管道入口: 从课程体系倒推知识需求→爬取→自动入库。
        返回 {crawl_result, extract_result}
        """
        crawl_result = self.run_scheduled(schedule=schedule)
        if crawl_result.get("new", 0) == 0:
            return {"success": True, "crawl": crawl_result,
                    "message": "无新内容,跳过提取"}

        # 自动触发预处理+提取(使用已成熟的管道)
        try:
            from scripts.preprocessor import Preprocessor
            from scripts.extractor import Extractor
            pp = Preprocessor()
            files = pp.scan()
            new_files = [f for f in files if f.get("original_filename", "").startswith("crawl_")]
            if new_files:
                for fi in new_files[:5]:
                    try:
                        pp.preprocess_file(fi)
                    except Exception:
                        pass
                ext = Extractor()
                ext.set_model("2")  # V4-Flash快速模式(爬虫内容质量较低)
                ext_result = ext.run_headless(model_key="2")
                return {"success": True, "crawl": crawl_result,
                        "extract": {"ok": ext_result.get("ok", 0),
                                   "total_kps": ext_result.get("total_kps", 0)}}
        except Exception as e:
            return {"success": True, "crawl": crawl_result,
                    "extract_error": str(e)[:200]}
        return {"success": True, "crawl": crawl_result}
