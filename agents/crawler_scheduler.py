"""
crawler_scheduler.py - 爬虫调度器(URL管理+去重+变化检测+限速+编码修复)
路径：agents/crawler_scheduler.py
版本：v2.3.7-part3

CEO爬取规则(v2.3.7-part3):
  爬什么: 政策文件/通知公告/解读文章(不含首页/导航/纯链接页)
  怎么爬: 原始编码检测→UTF-8清洗→提取正文≥500字→CEO审核→入库
  文件命名: 来源域名_页面标题_日期.txt(可读,非机器码)
  质量门槛: 正文<500字=低质量,标记待重爬; 乱码=直接丢弃
  限速: 每URL间隔2秒,每轮最多5个URL
"""
import json, time, hashlib, os, re
from pathlib import Path
from datetime import datetime
try:
    import requests
except ImportError:
    requests = None
try:
    import chardet
except ImportError:
    chardet = None

PROJECT_ROOT = Path(__file__).parent.parent

# === CEO爬取质量规则 ===
MIN_CONTENT_CHARS = 500          # 正文最低字数,低于此值标记为低质量
MAX_CONTENT_CHARS = 80000        # 单文件最大字数
CRAWL_INTERVAL_SEC = 2           # URL间隔秒数
MAX_URLS_PER_RUN = 5             # 每轮最多抓取数
REVIEW_DIR_NAME = "data/crawled"  # CEO审核目录(爬取后先放这里)

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
        """按计划爬取: 抓取→编码检测→正文提取→保存到data/crawled/(CEO审核目录)
        返回 {fetched, new, skipped, errors, details, ceo_review_path}"""
        if not requests:
            return {"success": False, "error": "requests库未安装,无法爬取"}

        # CEO审核目录(爬取后先放这里,CEO确认后才移到pending/)
        review_dir = PROJECT_ROOT / REVIEW_DIR_NAME
        os.makedirs(review_dir, exist_ok=True)

        results = {"fetched": 0, "new": 0, "low_quality": 0,
                    "skipped": 0, "errors": 0, "details": [],
                    "ceo_review_path": str(review_dir)}
        targets = [t for t in self._targets if t["schedule"] in (schedule, "daily", "weekly")
                   or (schedule == "weekly" and t["schedule"] in ("daily", "weekly"))]

        for t in targets[:MAX_URLS_PER_RUN]:
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

                # 乱码检测
                html_content = fetched.get("content", "")
                if not self._clean_text_for_save(html_content):
                    results["low_quality"] += 1
                    results["details"].append({
                        "url": url, "status": "garbled",
                        "encoding": fetched.get("encoding", "?"),
                        "action": "乱码,建议检查原始编码后重爬"
                    })
                    continue

                # 提取正文并评估质量
                extracted = self._extract_text(
                    html_content, url=url,
                    category=t.get("category", "policy"),
                    page_title=fetched.get("title", "")
                )
                text_content = extracted["text"]

                # 生成可读文件名: 域名_页面标题_日期.txt
                safe_name = self._safe_filename(url, fetched.get("title", ""))
                timestamp = datetime.now().strftime('%Y%m%d_%H%M')
                filename = f"{safe_name}_{timestamp}.txt"
                save_path = review_dir / filename

                with open(save_path, "w", encoding="utf-8") as f:
                    f.write(text_content[:MAX_CONTENT_CHARS])

                # 质量分流
                if extracted["quality"] == "low":
                    results["low_quality"] += 1
                    results["details"].append({
                        "url": url, "saved": str(save_path),
                        "quality": "low", "chars": extracted["char_count"],
                        "action": "低质量,CEO决定:重爬/手动补充/丢弃",
                        "reason": extracted["reason"],
                    })
                else:
                    results["new"] += 1
                    results["details"].append({
                        "url": url, "saved": str(save_path),
                        "quality": "good", "chars": extracted["char_count"],
                        "title": fetched.get("title", "")[:60],
                        "filename": filename,
                    })

                self._record_crawl(url, content_hash, str(save_path))
                time.sleep(CRAWL_INTERVAL_SEC)
            except Exception as e:
                results["errors"] += 1
                results["details"].append({"url": url, "error": str(e)[:200]})

        return {"success": True, **results}

    def approve_to_pipeline(self, file_path):
        """CEO审核通过: 将爬取文件从crawled/移动到pending/触发管道"""
        src = Path(file_path)
        if not src.exists():
            return {"ok": False, "error": "文件不存在"}
        pending_dir = PROJECT_ROOT / "data" / "pending"
        os.makedirs(pending_dir, exist_ok=True)
        dst = pending_dir / src.name
        import shutil
        shutil.move(str(src), str(dst))
        return {"ok": True, "moved_to": str(dst)}

    def _fetch_url(self, url, timeout=30):
        """抓取单个URL,智能编码检测。返回 {success, content, title, encoding, ...}"""
        if not self._session:
            self._session = requests.Session()
            self._session.headers.update({
                "User-Agent": "RuralRevitalizationKB/2.3.7 (knowledge-base-bot; contact@example.com)"
            })
        try:
            resp = self._session.get(url, timeout=timeout, allow_redirects=True)
            resp.raise_for_status()
            raw_bytes = resp.content  # 用原始字节,不用resp.text(避免错误解码)

            # 编码检测: 优先HTML meta标签,其次chardet,最后UTF-8
            encoding = None
            # 先尝试从HTML meta中提取charset
            head_sample = raw_bytes[:2000]
            meta_match = re.search(rb'charset[="\s]+([a-zA-Z0-9_-]+)', head_sample, re.IGNORECASE)
            if meta_match:
                try:
                    encoding = meta_match.group(1).decode('ascii').lower()
                except Exception:
                    pass
            # chardet兜底
            if not encoding and chardet:
                detected = chardet.detect(raw_bytes[:10000])
                if detected and detected.get('confidence', 0) > 0.7:
                    encoding = detected.get('encoding', 'utf-8')
            if not encoding:
                encoding = 'utf-8'

            # 解码
            try:
                content = raw_bytes.decode(encoding, errors='replace')
            except Exception:
                content = raw_bytes.decode('utf-8', errors='replace')

            # 提取页面标题
            title_match = re.search(r'<title[^>]*>(.*?)</title>', content, re.IGNORECASE | re.DOTALL)
            page_title = title_match.group(1).strip() if title_match else ''

            return {
                "success": True,
                "content": content,
                "title": page_title,
                "encoding": encoding,
                "content_hash": hashlib.md5(raw_bytes).hexdigest(),
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
    def _extract_text(self, html, url="", category="policy", page_title=""):
        """从HTML提取高质量正文。
        步骤: 去噪音标签→提正文区→去HTML→去空行→质量评分
        返回: {text, quality, char_count, reason}
        """
        if not html:
            return {"text": "", "quality": "empty", "char_count": 0, "reason": "无内容"}

        text = html
        # 1. 去除噪音标签(script/style/head/nav/footer/header)
        for tag in ['script', 'style', 'head', 'nav', 'footer', 'header', 'aside',
                     'noscript', 'iframe', 'svg', 'form']:
            text = re.sub(rf'<{tag}[^>]*>.*?</{tag}>', ' ', text, flags=re.DOTALL | re.IGNORECASE)
        # 2. 去除HTML注释
        text = re.sub(r'<!--.*?-->', ' ', text, flags=re.DOTALL)
        # 3. 去除HTML标签(保留文字)
        text = re.sub(r'<[^>]+>', ' ', text)
        # 4. 解码HTML实体
        text = text.replace('&nbsp;', ' ').replace('&lt;', '<').replace('&gt;', '>')
        text = text.replace('&amp;', '&').replace('&quot;', '"').replace('&apos;', "'")
        text = re.sub(r'&[a-z]+;', ' ', text)
        text = re.sub(r'&#\d+;', ' ', text)
        # 5. 去除URL和长数字串
        text = re.sub(r'https?://\S+', ' ', text)
        # 6. 按行清理: 保留有意义的行(>10个中文字符或>20个英文字符)
        lines = []
        for line in text.split('\n'):
            stripped = line.strip()
            if not stripped:
                continue
            # 计算中文字符数
            chinese_chars = len(re.findall(r'[一-鿿]', stripped))
            total_chars = len(stripped)
            # 保留有意义的内容行
            if chinese_chars >= 5 or (total_chars > 30 and chinese_chars > 0):
                lines.append(stripped)
        text = '\n'.join(lines)
        # 7. 压缩连续空白行
        text = re.sub(r'\n{3,}', '\n\n', text)
        text = text.strip()

        # 8. 质量评估
        char_count = len(text)
        chinese_count = len(re.findall(r'[一-鿿]', text))
        if char_count < MIN_CONTENT_CHARS:
            quality = "low"
            reason = f"正文仅{char_count}字,低于{MIN_CONTENT_CHARS}字门槛,建议重爬或手动补充"
        elif chinese_count < 50:
            quality = "low"
            reason = f"中文字符仅{chinese_count}个,可能为非中文页面或提取失败"
        else:
            quality = "good"
            reason = f"正文{char_count}字,中文{chinese_count}字,质量合格"

        # 9. 加元数据头
        header = (
            f"# 来源: {url}\n"
            f"# 标题: {page_title}\n"
            f"# 抓取时间: {datetime.now().strftime('%Y-%m-%d %H:%M')}\n"
            f"# 类别: {category}\n"
            f"# 质量: {quality} | {reason}\n"
            f"{'='*50}\n\n"
        )
        return {
            "text": header + text,
            "quality": quality,
            "char_count": char_count,
            "chinese_count": chinese_count,
            "reason": reason,
        }

    def _safe_filename(self, url, page_title=''):
        """从URL和页面标题生成可读文件名。
        格式: 来源域名_页面标题_日期.txt
        例: mnr_gov_cn_全域土地综合整治试点工作通知_20260506.txt
        """
        # 提取域名核心部分
        domain = url.replace("https://", "").replace("http://", "").split("/")[0]
        domain_short = domain.replace("www.", "").replace(".gov.cn", "").replace(".", "_")[:30]

        # 清洗页面标题
        if page_title:
            # 去掉常见网站后缀和分隔符
            title = page_title
            for sep in ['_', '-', '|', '—', '–']:
                if sep in title:
                    # 取第一个有意义的部分
                    parts = [p.strip() for p in title.split(sep) if len(p.strip()) > 3]
                    if parts:
                        title = parts[0]
                        break
            # 去掉"四川省""中国政府网"等通用前缀
            title = re.sub(r'^(四川省|中国政府网|中华人民共和国|国务院)', '', title)
            # 保留中文、字母、数字,其余替换为_
            title = re.sub(r'[^\w一-鿿]+', '_', title)
            title = title.strip('_')[:50]  # 标题不超过50字符
        else:
            title = 'untitled'

        return f"{domain_short}_{title}"

    def _clean_text_for_save(self, content):
        """检查是否含乱码: 如果UTF-8字节序列出现大量无效序列→乱码。
        简单检测: 解码后的文本含大量替换字符(U+FFFD)→乱码。"""
        if not content:
            return False
        replacement_count = content.count('�')
        if len(content) > 0 and replacement_count / max(len(content), 1) > 0.05:
            return False  # >5%替换字符=乱码
        return True

    # ================================================================
    # 爬取+自动喂入提取管道
    # ================================================================
    def crawl_and_feed(self, schedule="weekly", max_urls=5):
        """爬取→CEO审核→手动批准→入库。
        v2.3.7-part3变更: 爬取文件先放data/crawled/等待CEO审核,
        CEO调用approve_to_pipeline()确认后才进入提取管道。
        返回 {crawl_result}
        """
        crawl_result = self.run_scheduled(schedule=schedule)
        good_count = crawl_result.get("new", 0)
        low_count = crawl_result.get("low_quality", 0)

        return {
            "success": True,
            "crawl": crawl_result,
            "message": (
                f"爬取完成: 合格{good_count}个, 低质量{low_count}个。"
                f"文件已保存到{REVIEW_DIR_NAME}/。"
                f"请CEO审核后决定: 批准→入库 / 拒绝→重爬 / 低质量→手动补充。"
            ),
            "ceo_action": "请打开 data/crawled/ 查看爬取文件",
        }
