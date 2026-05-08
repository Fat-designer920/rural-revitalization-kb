"""
crawler_scheduler.py - 爬虫调度器(定向搜索+三层去重+四级质量门禁+合规)
路径：agents/crawler_scheduler.py
版本：v2.3.8

v2.3.8 重构:
  - 从"首页扫链接"翻转为"定向搜索" (gov.cn检索API + 站内搜索)
  - 三层去重: URL指纹→内容哈希→发文字号
  - GovContentExtractor 智能正文提取(替代正则去标签)
  - robots.txt 合规检查 + Crawl-Delay
  - 手动触发(不自动化) + 四川21市州+省级+国家级
"""
import json, time, hashlib, os, re
from pathlib import Path
from datetime import datetime
from urllib.parse import urljoin, urlparse

try:
    import requests
except ImportError:
    requests = None
try:
    import chardet
except ImportError:
    chardet = None

PROJECT_ROOT = Path(__file__).parent.parent
sys_path = str(PROJECT_ROOT)

# 导入正文提取器
import sys as _sys
_sys.path.insert(0, sys_path)
from scripts.content_extractor import GovContentExtractor, check_robots_txt, EXCLUDE_KEYWORDS

# === 政策列表页(四川乡村振兴定向信源) ===
# 直接命中政府网站的政策列表页(server-rendered HTML)，不依赖JS搜索
POLICY_LISTING_SOURCES = [
    # 四川省省级
    {"domain": "www.sc.gov.cn", "name": "四川省人民政府",
     "list_urls": [
         "https://www.sc.gov.cn/10462/10778/10876/index.shtml",  # 政策文件
         "https://www.sc.gov.cn/10462/10778/10877/index.shtml",  # 政策解读
     ]},
    # 成都市
    {"domain": "www.chengdu.gov.cn", "name": "成都市人民政府",
     "list_urls": [
         "https://www.chengdu.gov.cn/chengdu/zfxx/zwgk_index.shtml",
     ]},
    # 绵阳市
    {"domain": "www.mianyang.gov.cn", "name": "绵阳市人民政府",
     "list_urls": [
         "https://www.mianyang.gov.cn/zwgk/zfxxgk/zcjd/index.html",
     ]},
    # 宜宾市
    {"domain": "www.yibin.gov.cn", "name": "宜宾市人民政府",
     "list_urls": [
         "https://www.yibin.gov.cn/zwgk/zc/zcfg/index.html",
     ]},
    # 德阳市
    {"domain": "www.deyang.gov.cn", "name": "德阳市人民政府",
     "list_urls": [
         "https://www.deyang.gov.cn/zwgk/zcfg/index.html",
     ]},
]

# === 列表页链接发现关键词(用于筛选相关链接) ===
LISTING_LINK_KEYWORDS = [
    '土地','耕地','农田','指标','占补','增减挂钩','空间规划','国土',
    '农村','农业','乡村','产业','振兴','整治','建设','用地','入市',
    '专项债','资金','补贴','补助','水利','生态修复','高标准农田',
    '村庄','农房','人居','环境','厕所','垃圾','污水',
    '公路','道路','交通','物流','旅游','民宿','非遗','文化',
    '林权','碳汇','造林','草原','湿地','退耕','还林',
    '脱贫','帮扶','巩固','和美','宜居','示范','试点',
    '通知','意见','办法','方案','规划','公告','公示',
]

# === 质量门禁常量 ===
MIN_CONTENT_CHARS = 500
MAX_CONTENT_CHARS = 80000
MAX_URLS_PER_SEARCH = 10       # 每个关键词取前N条结果
MAX_ARTICLES_PER_RUN = 50      # 单次最多保存N篇文章
CRAWL_DELAY_DEFAULT = 5        # 默认请求间隔(秒)


class CrawlerScheduler(object):
    """爬虫调度器 v2.3.8。定向搜索→深度爬取→智能提取→质量门禁→CEO审核。"""

    def __init__(self, db=None):
        self.db = db
        self._session = None
        self._extractor = GovContentExtractor()
        self._url_fingerprints = set()     # L0: 内存级URL去重
        self._content_hashes = set()       # L1: 内容哈希去重
        self._crawl_history_loaded = False
        self._domain_delays = {}           # 域名→Crawl-Delay

    # ================================================================
    # 主入口: 手动触发单次爬取
    # ================================================================
    def run(self, max_articles=MAX_ARTICLES_PER_RUN, sources=None):
        """手动触发单次爬取(不自动调度)。遍历政策列表页→提取文章链接→深度爬取→质量门禁。
        参数:
          max_articles: 单次最多保存文章数
          sources: None=全部信源, 或指定域名列表如 ['www.sc.gov.cn']
        返回: {success, stats, articles, message}
        """
        if not requests:
            return {"success": False, "error": "requests库未安装,无法爬取"}

        self._load_existing_fingerprints()
        review_dir = PROJECT_ROOT / "data" / "crawled"
        os.makedirs(review_dir, exist_ok=True)

        targets = POLICY_LISTING_SOURCES
        if sources:
            targets = [s for s in targets if s["domain"] in sources]

        stats = {"pages_fetched": 0, "links_found": 0, "articles_fetched": 0,
                 "qualified": 0, "rejected": 0, "errors": 0, "duplicates": 0}
        articles = []
        reject_log = []

        for src in targets:
            if len(articles) >= max_articles:
                break

            # 合规检查
            allowed, delay = self._ensure_compliance(src["domain"])
            if not allowed:
                continue

            for list_url in src["list_urls"]:
                if len(articles) >= max_articles:
                    break

                # 抓取列表页→提取文章链接
                links = self._extract_links_from_listing(list_url, src["domain"])
                stats["pages_fetched"] += 1
                stats["links_found"] += len(links)

                # 对每个文章链接→深度爬取
                for link in links:
                    if len(articles) >= max_articles:
                        break

                    # L0: URL指纹去重
                    url_fp = self._url_fingerprint(link["url"])
                    if url_fp in self._url_fingerprints:
                        stats["duplicates"] += 1
                        continue

                    article = self._fetch_and_extract_article(
                        link, review_dir,
                        source_domain=src["domain"],
                        source_name=src["name"]
                    )
                    stats["articles_fetched"] += 1

                    if article and article.get("quality") == "good":
                        self._url_fingerprints.add(url_fp)
                        self._content_hashes.add(article["content_hash"])
                        articles.append(article)
                        stats["qualified"] += 1
                    elif article:
                        stats["rejected"] += 1
                        reject_log.append({
                            "url": link["url"][:100],
                            "quality": article.get("quality", "?"),
                            "reason": article.get("quality_reason", "?")[:120],
                        })
                    else:
                        stats["errors"] += 1

                    time.sleep(delay)

        report = self._build_report(stats, articles, reject_log, review_dir)
        report_path = review_dir / f"crawl_report_{datetime.now().strftime('%Y%m%d_%H%M')}.json"
        with open(report_path, "w", encoding="utf-8") as f:
            json.dump(report, f, ensure_ascii=False, indent=2)

        return {
            "success": True,
            "stats": stats,
            "articles": articles[:20],
            "reject_log": reject_log[:20],
            "report_path": str(report_path),
            "message": (
                f"爬取完成: 抓取{stats['pages_fetched']}个列表页, "
                f"发现{stats['links_found']}个链接, "
                f"提取{stats['articles_fetched']}篇文章, "
                f"合格{stats['qualified']}篇, "
                f"拒绝{stats['rejected']}篇(去重{stats['duplicates']}), "
                f"错误{stats['errors']}。"
                f"文件已保存到 data/crawled/。请CEO审核后批准入库。"
            ),
        }

    # ================================================================
    # 定向搜索
    # ================================================================
    def _extract_links_from_listing(self, list_url, domain):
        """从政策列表页提取文章链接。优先提含乡村振兴关键词的链接。
        返回 [{url, title, score}] 去重列表。
        """
        links = []
        try:
            html = self._fetch_url(list_url, timeout=25)
            if not html:
                return links

            link_pattern = re.compile(
                r'<a[^>]*href\s*=\s*["\']([^"\']+)["\'][^>]*>(.*?)</a>',
                re.IGNORECASE | re.DOTALL
            )

            base = f"https://{domain}"
            seen = set()
            scored = []

            for match in link_pattern.finditer(html):
                href = match.group(1).strip()
                title_raw = re.sub(r'<[^>]+>', '', match.group(2)).strip()
                title_raw = re.sub(r'\s+', ' ', title_raw)

                if not href or href.startswith('#') or href.startswith('javascript:'):
                    continue
                if len(title_raw) < 8:
                    continue

                full_url = urljoin(base, href)
                if '#' in full_url:
                    full_url = full_url.split('#')[0]

                # 同域
                try:
                    if urlparse(full_url).netloc != urlparse(base).netloc:
                        continue
                except Exception:
                    continue

                # 过滤静态资源
                skip_exts = ('.jpg', '.jpeg', '.png', '.gif', '.pdf', '.doc', '.docx',
                            '.xls', '.xlsx', '.ppt', '.zip', '.rar', '.css', '.js')
                if any(full_url.lower().endswith(ext) for ext in skip_exts):
                    continue

                if full_url in seen:
                    continue
                seen.add(full_url)

                # 快速排除: 标题含排除关键词
                if any(kw in title_raw for kw in EXCLUDE_KEYWORDS):
                    continue

                # 评分
                score = self._score_link(full_url, title_raw)
                if score >= 3:  # 至少有一定相关度
                    scored.append((score, full_url, title_raw))

            scored.sort(key=lambda x: x[0], reverse=True)
            for score, url, title in scored[:MAX_URLS_PER_SEARCH]:
                links.append({
                    "url": url,
                    "title": title[:120],
                    "score": score,
                })

        except Exception:
            pass

        return links

    def _score_link(self, url, title):
        """对列表页链接评分。"""
        score = 0
        path = urlparse(url).path.lower()

        # URL含政策频道模式
        policy_paths = ['/zwgk/', '/zhengce/', '/xxgk/', '/content/', '/article/',
                        '/govinfo/', '/gongbao/', '/zcfg/', '/flfg/', '/zfxxgk/',
                        '/zcjd/', '/zcfg/', '/tzgg/']
        for pp in policy_paths:
            if pp in path:
                score += 3
                break

        # URL含日期=更可能是文章页
        if re.search(r'/20\d{2}[/-]\d{1,2}', path):
            score += 2

        # 路径深度≥3=更可能是文章页
        path_parts = [p for p in path.split('/') if p]
        if len(path_parts) >= 4:
            score += 1

        # 标题匹配乡村振兴关键词
        kw_matches = sum(1 for kw in LISTING_LINK_KEYWORDS if kw in title)
        score += min(kw_matches, 3)

        # 标题长度(太短=导航文字)
        if len(title) > 15:
            score += 1
        if len(title) > 25:
            score += 1

        return score

    # ================================================================
    # 文章页抓取+提取
    # ================================================================
    def _fetch_and_extract_article(self, link, review_dir, source_domain="", source_name=""):
        """抓取文章页→智能提取正文→质量门禁→保存文件。"""
        url = link["url"]
        page_title = link.get("title", "")

        # 抓取文章页
        html = self._fetch_url(url, timeout=30)
        if not html:
            return None

        # 智能提取正文+元数据
        extracted = self._extractor.extract(html, url=url, page_title=page_title)

        if extracted["quality"] in ("garbled", "excluded", "empty"):
            return {
                "url": url, "title": page_title[:120],
                "quality": extracted["quality"],
                "quality_reason": extracted["reason"],
                "filepath": None, "content_hash": "",
            }

        text = extracted["text"]
        content_hash = hashlib.md5(text.encode('utf-8')).hexdigest()

        # L1: 内容哈希去重
        if content_hash in self._content_hashes:
            return {
                "url": url, "title": page_title[:120],
                "quality": "duplicate",
                "quality_reason": "内容哈希重复,已存在",
                "filepath": None, "content_hash": content_hash,
            }

        # L2: 发文字号去重(同一政策不可重复入库)
        doc_number = extracted["metadata"].get("doc_number", "")
        if doc_number and self._doc_number_exists(doc_number):
            return {
                "url": url, "title": page_title[:120],
                "quality": "duplicate",
                "quality_reason": f"发文字号{doc_number}已存在",
                "filepath": None, "content_hash": content_hash,
            }

        # 质量不合格的不保存文件
        if extracted["quality"] != "good":
            return {
                "url": url, "title": page_title[:120],
                "quality": extracted["quality"],
                "quality_reason": extracted["reason"],
                "filepath": None, "content_hash": "",
            }

        # 合格: 保存文件
        safe_name = self._safe_filename(url, page_title)
        timestamp = datetime.now().strftime('%Y%m%d_%H%M%S')
        filename = f"{safe_name}_{timestamp}.txt"
        save_path = review_dir / filename

        meta = extracted["metadata"]
        header = (
            f"# 来源: {url}\n"
            f"# 标题: {page_title}\n"
            f"# 抓取时间: {datetime.now().strftime('%Y-%m-%d %H:%M')}\n"
            f"# 源站: {source_name}({source_domain})\n"
        )
        if meta.get("doc_number"):
            header += f"# 发文字号: {meta['doc_number']}\n"
        if meta.get("publish_date"):
            header += f"# 发布日期: {meta['publish_date']}\n"
        if meta.get("issuing_body"):
            header += f"# 发文机关: {meta['issuing_body']}\n"
        header += f"{'='*50}\n\n"

        with open(save_path, "w", encoding="utf-8") as f:
            f.write(header + text[:MAX_CONTENT_CHARS])

        # 记录到crawl_history(去重依据)
        self._record_crawl(url, content_hash, str(save_path),
                          doc_number=meta.get("doc_number", ""),
                          source_domain=source_domain)

        return {
            "url": url,
            "title": page_title[:120],
            "char_count": extracted["char_count"],
            "chinese_count": extracted["chinese_count"],
            "quality": "good",
            "quality_reason": extracted["reason"],
            "filepath": str(save_path),
            "filename": filename,
            "content_hash": content_hash,
            "metadata": meta,
            "source_name": source_name,
            "source_domain": source_domain,
        }

    # ================================================================
    # 去重辅助
    # ================================================================
    def _load_existing_fingerprints(self):
        """从crawl_history加载已有URL指纹和内容哈希做去重基准。"""
        if self._crawl_history_loaded or not self.db:
            return
        try:
            conn = self.db.get_connection()
            c = conn.cursor()
            c.execute("SELECT url, content_hash FROM crawl_history")
            for row in c.fetchall():
                self._url_fingerprints.add(self._url_fingerprint(row[0]))
                if row[1]:
                    self._content_hashes.add(row[1])
            conn.close()
            self._crawl_history_loaded = True
        except Exception:
            pass

    def _url_fingerprint(self, url):
        """URL标准化指纹: 去协议+去www+去尾部斜杠+去锚点→MD5前16位"""
        u = url.lower().replace("https://", "").replace("http://", "")
        u = u.replace("www.", "").rstrip("/")
        if '#' in u:
            u = u.split('#')[0]
        return hashlib.md5(u.encode('utf-8')).hexdigest()[:16]

    def _doc_number_exists(self, doc_number):
        """检查发文字号是否已存在于crawl_history"""
        if not self.db or not doc_number:
            return False
        try:
            conn = self.db.get_connection()
            c = conn.cursor()
            c.execute("SELECT COUNT(*) FROM crawl_history WHERE doc_number=?", (doc_number,))
            count = c.fetchone()[0]
            conn.close()
            return count > 0
        except Exception:
            return False

    # ================================================================
    # 合规
    # ================================================================
    def _ensure_compliance(self, domain):
        """检查robots.txt+Crawl-Delay。返回 (allowed, delay_seconds)"""
        if domain in self._domain_delays:
            return True, self._domain_delays[domain]
        allowed, delay = check_robots_txt(domain)
        self._domain_delays[domain] = max(delay, CRAWL_DELAY_DEFAULT)
        return allowed, self._domain_delays[domain]

    # ================================================================
    # HTTP抓取
    # ================================================================
    def _fetch_url(self, url, timeout=30):
        """抓取URL,智能编码检测(meta优先→chardet→UTF-8→GBK回退)。"""
        if not self._session:
            self._session = requests.Session()
            self._session.headers.update({
                "User-Agent": "RuralRevitalizationKB/2.3.8 (knowledge-base-bot; Sichuan-rural-research)"
            })
        try:
            resp = self._session.get(url, timeout=timeout, allow_redirects=True,
                                     headers={"Accept-Language": "zh-CN,zh;q=0.9"})
            resp.raise_for_status()
            raw_bytes = resp.content

            # 尝试解码: meta→chardet→常见中文编码
            head_sample = raw_bytes[:2000]
            meta_enc = None
            meta_match = re.search(rb'charset[="\s]+([a-zA-Z0-9_-]+)', head_sample, re.IGNORECASE)
            if meta_match:
                try:
                    meta_enc = meta_match.group(1).decode('ascii').lower()
                except Exception:
                    pass

            # chardet检测
            chardet_enc = None
            if chardet:
                try:
                    detected = chardet.detect(raw_bytes[:20000])
                    if detected and detected.get('confidence', 0) > 0.6:
                        chardet_enc = detected.get('encoding', '').lower()
                except Exception:
                    pass

            # 尝试顺序: meta → chardet → UTF-8 → GBK → GB18030
            candidates = []
            if meta_enc:
                candidates.append(meta_enc)
            if chardet_enc and chardet_enc != meta_enc:
                candidates.append(chardet_enc)
            for enc in ['utf-8', 'gbk', 'gb18030', 'gb2312']:
                if enc not in candidates:
                    candidates.append(enc)

            for enc in candidates:
                try:
                    text = raw_bytes.decode(enc, errors='strict')
                    chinese = sum(1 for c in text[:2000] if '一' <= c <= '鿿')
                    if chinese > 20:  # 前2000字符至少有20个中文=编码正确
                        return text
                except (UnicodeDecodeError, LookupError):
                    continue

            # 最终兜底
            return raw_bytes.decode('utf-8', errors='replace')
        except Exception:
            return None

    def _record_crawl(self, url, content_hash, saved_path, doc_number="",
                      source_domain=""):
        """记录爬取历史到DB"""
        if not self.db:
            return
        try:
            conn = self.db.get_connection()
            c = conn.cursor()
            c.execute("""INSERT INTO crawl_history
                         (url, content_hash, saved_path, doc_number, source_domain, fetched_at)
                         VALUES (?,?,?,?,?,datetime('now','localtime'))""",
                      (url, content_hash, saved_path, doc_number, source_domain))
            conn.commit()
            conn.close()
        except Exception:
            pass

    # ================================================================
    # 辅助方法
    # ================================================================
    def _safe_filename(self, url, page_title=''):
        """生成可读文件名: 域名_标题_时间戳.txt"""
        domain = url.replace("https://", "").replace("http://", "").split("/")[0]
        domain_short = domain.replace("www.", "").replace(".gov.cn", "").replace(".", "_")[:30]

        if page_title:
            title = page_title
            for sep in ['_', '-', '|', '—', '–']:
                if sep in title:
                    parts = [p.strip() for p in title.split(sep) if len(p.strip()) > 3]
                    if parts:
                        title = parts[0]
                        break
            title = re.sub(r'^(四川省|中国政府网|中华人民共和国|国务院)', '', title)
            title = re.sub(r'[^\w一-鿿]+', '_', title)
            title = title.strip('_')[:50]
        else:
            title = 'untitled'

        return f"{domain_short}_{title}"

    def _build_report(self, stats, articles, reject_log, review_dir):
        """生成爬取报告"""
        return {
            "timestamp": datetime.now().strftime('%Y-%m-%d %H:%M:%S'),
            "version": "v2.3.8",
            "stats": stats,
            "articles": [{
                "title": a["title"],
                "url": a["url"],
                "filename": a.get("filename", ""),
                "char_count": a.get("char_count", 0),
                "group_name": a.get("group_name", ""),
                "source_domain": a.get("source_domain", ""),
                "metadata": a.get("metadata", {}),
            } for a in articles],
            "rejected": reject_log[:20],
            "ceo_action": f"请打开 {review_dir}/ 审核{stats['qualified']}篇合格文章。批准→入库 / 拒绝→删除。",
        }

    # ================================================================
    # CEO审核→入库管道
    # ================================================================
    def approve_to_pipeline(self, file_path):
        """CEO审核通过: 将爬取文件从crawled/移动到pending/触发提取管道"""
        src = Path(file_path)
        if not src.exists():
            return {"ok": False, "error": "文件不存在"}
        pending_dir = PROJECT_ROOT / "data" / "pending"
        os.makedirs(pending_dir, exist_ok=True)
        dst = pending_dir / src.name
        import shutil
        shutil.move(str(src), str(dst))
        return {"ok": True, "moved_to": str(dst)}

    def reject_file(self, file_path):
        """CEO拒绝: 删除不合格爬取文件"""
        src = Path(file_path)
        if src.exists():
            src.unlink()
            return {"ok": True, "deleted": str(src)}
        return {"ok": False, "error": "文件不存在"}

    def list_crawled(self):
        """列出crawled/中待审核文件"""
        review_dir = PROJECT_ROOT / "data" / "crawled"
        files = []
        if review_dir.exists():
            for f in sorted(review_dir.iterdir()):
                if f.suffix == '.txt' and not f.name.startswith('crawl_report'):
                    stat = f.stat()
                    files.append({
                        "filename": f.name,
                        "size": stat.st_size,
                        "created": datetime.fromtimestamp(stat.st_ctime).isoformat(),
                    })
        return {"total": len(files), "files": files}

    def get_status(self):
        """爬虫状态"""
        status = {"version": "v2.3.8", "mode": "manual", "search_endpoints": len(SEARCH_ENDPOINTS),
                  "listing_sources": len(POLICY_LISTING_SOURCES), "last_run": None}
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
