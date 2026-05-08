"""
search_bypass.py - 搜索引擎旁路: 绕过WAF,通过搜索引擎获取政策文章链接
路径：agents/search_bypass.py
版本：v2.3.8

WAF保护的是列表页(高频访问),但搜索引擎已经帮我们爬过了全文。
策略: site:domain keyword → 拿搜索结果中的文章URL → 直连文章页(单页WAF弱)
→ 正文提取 → 质量门禁 → 合格入库。
"""
import re, time, hashlib
from pathlib import Path
from datetime import datetime
from urllib.parse import quote, urlparse, urljoin

try:
    import requests
except ImportError:
    requests = None

PROJECT_ROOT = Path(__file__).parent.parent

# 搜索引擎端点
SEARCH_ENGINES = [
    {
        "name": "Bing",
        "url": "https://www.bing.com/search?q={query}&setlang=zh-cn&cc=cn",
        "link_pattern": r'<a[^>]*href\s*=\s*["\'](https?://[^"\']+?)["\']',
        "result_selector": r'<li\s+class="b_algo"[^>]*>.*?</li>',
    },
]

# 针对WAF域名的搜索关键词(乡村振兴核心政策)
SEARCH_KEYWORDS = [
    "乡村振兴 政策 通知",
    "土地整治 实施方案",
    "高标准农田 建设",
    "农村 产业 发展 意见",
    "耕地保护 措施",
    "人居环境 整治 方案",
    "农村公路 建设",
    "乡村旅游 发展",
    "农业补贴 办法",
    "农村金融 政策",
    "增减挂钩 指标",
    "宅基地 管理 办法",
]


class SearchBypass(object):
    """搜索引擎旁路: 用搜索引擎获取WAF域名的政策文章。"""

    def __init__(self, extractor=None, db=None):
        self._session = None
        self._extractor = extractor
        self._db = db
        self._content_hashes = set()

    def discover_articles(self, domain, max_articles=20):
        """对单个WAF域名,通过搜索引擎发现政策文章。
        返回 {domain, articles: [{url, title, snippet, source}], stats}
        """
        if not requests:
            return {"domain": domain, "articles": [], "error": "requests未安装"}

        self._init_session()
        all_articles = []
        stats = {"searches": 0, "urls_found": 0, "fetched": 0, "errors": 0}

        for kw in SEARCH_KEYWORDS:
            if len(all_articles) >= max_articles:
                break
            query = f"site:{domain} {kw}"
            stats["searches"] += 1

            urls = self._search_urls(query, domain, max_per_search=10)
            stats["urls_found"] += len(urls)

            for url in urls:
                if len(all_articles) >= max_articles:
                    break
                if any(a["url"] == url for a in all_articles):
                    continue

                article = self._fetch_article(url, domain)
                stats["fetched"] += 1
                if article:
                    all_articles.append(article)
                else:
                    stats["errors"] += 1

            time.sleep(2)  # 搜索间隔,避免被封

        return {
            "domain": domain,
            "articles": all_articles,
            "stats": stats,
        }

    def bypass_and_crawl(self, domain, max_articles=20):
        """搜索引擎旁路→抓取文章→正文提取→质量门禁→保存。
        完整流程,产出可直接进入CEO审核的爬取文件。
        返回 {domain, qualified: [{url, title, filepath, ...}], stats}
        """
        from scripts.content_extractor import GovContentExtractor
        if not self._extractor:
            self._extractor = GovContentExtractor()
        if self._db:
            self._load_hashes()

        result = self.discover_articles(domain, max_articles=max_articles)
        review_dir = PROJECT_ROOT / "data" / "crawled"
        review_dir.mkdir(parents=True, exist_ok=True)

        qualified = []
        rejected = []
        stats = dict(result.get("stats", {}))
        stats["qualified"] = 0
        stats["rejected"] = 0
        stats["duplicates"] = 0

        for art in result.get("articles", []):
            html = art.get("html", "")
            if not html:
                stats["errors"] += 1
                continue

            # 正文提取+质量门禁
            extracted = self._extractor.extract(
                html, url=art["url"], page_title=art.get("title", "")
            )

            if extracted["quality"] == "good":
                content_hash = hashlib.md5(extracted["text"].encode('utf-8')).hexdigest()
                if content_hash in self._content_hashes:
                    stats["duplicates"] += 1
                    continue
                self._content_hashes.add(content_hash)

                # 保存文件
                safe_name = self._safe_filename(art["url"], art.get("title", ""))
                timestamp = datetime.now().strftime('%Y%m%d_%H%M%S')
                filename = f"{safe_name}_{timestamp}.txt"
                save_path = review_dir / filename

                meta = extracted.get("metadata", {})
                header = (
                    f"# 来源: {art['url']}\n"
                    f"# 标题: {art.get('title', '')}\n"
                    f"# 抓取方式: 搜索引擎旁路(WAF绕过)\n"
                    f"# 抓取时间: {datetime.now().strftime('%Y-%m-%d %H:%M')}\n"
                )
                if meta.get("doc_number"):
                    header += f"# 发文字号: {meta['doc_number']}\n"
                if meta.get("publish_date"):
                    header += f"# 发布日期: {meta['publish_date']}\n"
                if meta.get("issuing_body"):
                    header += f"# 发文机关: {meta['issuing_body']}\n"
                header += f"{'='*50}\n\n"

                with open(save_path, "w", encoding="utf-8") as f:
                    f.write(header + extracted["text"][:80000])

                self._record_crawl(art["url"], content_hash, str(save_path),
                                  doc_number=meta.get("doc_number", ""),
                                  source_domain=domain,
                                  method="search_bypass")

                qualified.append({
                    "url": art["url"],
                    "title": art.get("title", "")[:120],
                    "char_count": extracted["char_count"],
                    "filepath": str(save_path),
                    "filename": filename,
                    "metadata": meta,
                })
                stats["qualified"] += 1
            else:
                rejected.append({
                    "url": art["url"][:100],
                    "quality": extracted["quality"],
                    "reason": extracted["reason"][:120],
                })
                stats["rejected"] += 1

        return {
            "domain": domain,
            "qualified": qualified,
            "rejected": rejected[:20],
            "stats": stats,
        }

    # ================================================================
    # 内部方法
    # ================================================================
    def _search_urls(self, query, domain, max_per_search=10):
        """执行搜索引擎查询,提取结果中的文章URL。"""
        urls = []
        engine = SEARCH_ENGINES[0]
        search_url = engine["url"].format(query=quote(query))

        try:
            resp = self._session.get(search_url, timeout=20, allow_redirects=True)
            if resp.status_code != 200:
                return urls

            # 提取含目标域名的URL
            link_pattern = re.compile(
                r'<a[^>]*href\s*=\s*["\'](https?://[^"\']*' +
                re.escape(domain.replace("www.", "")) +
                r'[^"\']*)["\']',
                re.IGNORECASE
            )
            seen = set()
            for match in link_pattern.finditer(resp.text):
                url = match.group(1)
                # 清理URL
                url = url.split('#')[0]
                # 跳过静态资源
                if any(url.lower().endswith(ext) for ext in
                       ('.jpg', '.jpeg', '.png', '.gif', '.css', '.js',
                        '.pdf', '.doc', '.docx', '.xls', '.xlsx', '.zip')):
                    continue
                # 跳过首页/根URL(太短)
                path = urlparse(url).path
                if len(path) < 5:
                    continue
                if url in seen:
                    continue
                seen.add(url)
                urls.append(url)
                if len(urls) >= max_per_search:
                    break

        except Exception:
            pass

        return urls

    def _fetch_article(self, url, domain):
        """直连文章页(绕过WAF)。文章页WAF通常比列表页弱。"""
        try:
            resp = self._session.get(url, timeout=20, allow_redirects=True)
            if resp.status_code >= 400:
                # 重试: 部分政府网站首次访问会302到验证页,第二次正常
                time.sleep(1)
                resp = self._session.get(url, timeout=20, allow_redirects=True)
                if resp.status_code >= 400:
                    return None

            html = self._decode(resp.content)
            if not html or len(html) < 500:
                return None

            # 提取标题
            title_m = re.search(r'<title[^>]*>(.*?)</title>', html, re.IGNORECASE)
            title = title_m.group(1).strip() if title_m else ""

            return {
                "url": url,
                "title": title,
                "html": html,
                "content_len": len(html),
            }
        except Exception:
            return None

    def _decode(self, raw_bytes):
        """智能编码检测"""
        head = raw_bytes[:2000]
        meta_enc = None
        m = re.search(rb'charset[="\s]+([a-zA-Z0-9_-]+)', head, re.IGNORECASE)
        if m:
            try:
                meta_enc = m.group(1).decode('ascii').lower()
            except Exception:
                pass
        for enc in ([meta_enc] if meta_enc else []) + ['utf-8', 'gbk', 'gb18030']:
            try:
                text = raw_bytes.decode(enc, errors='strict')
                if sum(1 for c in text[:2000] if '一' <= c <= '鿿') > 10:
                    return text
            except (UnicodeDecodeError, LookupError):
                continue
        return raw_bytes.decode('utf-8', errors='replace')

    def _load_hashes(self):
        """加载已有内容哈希用于去重"""
        if not self._db:
            return
        try:
            conn = self._db.get_connection()
            c = conn.cursor()
            c.execute("SELECT content_hash FROM crawl_history WHERE content_hash != ''")
            for (h,) in c.fetchall():
                self._content_hashes.add(h)
            conn.close()
        except Exception:
            pass

    def _record_crawl(self, url, content_hash, saved_path, doc_number="",
                      source_domain="", method="search_bypass"):
        """记录到crawl_history"""
        if not self._db:
            return
        try:
            conn = self._db.get_connection()
            c = conn.cursor()
            c.execute("""INSERT INTO crawl_history
                         (url, content_hash, saved_path, doc_number, source_domain, notes, fetched_at)
                         VALUES (?,?,?,?,?,?,datetime('now','localtime'))""",
                      (url, content_hash, saved_path, doc_number,
                       source_domain, f"method={method}"))
            conn.commit()
            conn.close()
        except Exception:
            pass

    def _safe_filename(self, url, page_title=''):
        domain = url.replace("https://", "").replace("http://", "").split("/")[0]
        short = domain.replace("www.", "").replace(".gov.cn", "").replace(".", "_")[:25]
        if page_title:
            title = re.sub(r'[^\w一-鿿]+', '_', page_title)[:50]
        else:
            title = 'untitled'
        return f"{short}_{title}"

    def _init_session(self):
        self._session = requests.Session()
        self._session.headers.update({
            "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36",
            "Accept-Language": "zh-CN,zh;q=0.9",
            "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,*/*;q=0.8",
        })
