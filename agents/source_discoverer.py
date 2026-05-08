"""
source_discoverer.py - 信源探测器: 自动发现政府网站政策列表页
路径：agents/source_discoverer.py
版本：v2.3.8

思路: 给定域名→抓首页→提取所有链接→按政策相关性评分→识别列表页→返回发现结果。
中国政府网站结构高度同质化, /zwgk/ /zhengce/ /xxgk/ /tzgg/ 等路径模式几乎通用。
"""
import re, time
from urllib.parse import urljoin, urlparse

try:
    import requests
except ImportError:
    requests = None

MIN_ARTICLE_LINKS = 5       # 至少含5个文章链接才算列表页
MAX_PAGES_TO_CHECK = 15     # 每个域名最多探测15个候选页
FETCH_TIMEOUT = 20


class SourceDiscoverer(object):
    """信源自动探测器。输入域名,输出发现的政策列表页URL列表。"""

    def __init__(self):
        self._session = None

    # ================================================================
    # 主入口: 探测单个域名的政策信源
    # ================================================================
    def discover(self, domain, max_listings=5):
        """探测单个域名的政策列表页。
        参数:
          domain: 如 'www.mianyang.gov.cn'
          max_listings: 最多返回N个列表页
        返回: {domain, discovered: [{url, title, article_count, score}], stats}
        """
        if not requests:
            return {"domain": domain, "discovered": [], "error": "requests未安装"}

        self._init_session()
        base = f"https://{domain}"
        discovered = []
        visited = set()
        stats = {"pages_checked": 0, "links_total": 0}

        # 1. 抓首页,提取所有内部链接
        homepage_links = self._fetch_and_extract_links(base, domain)
        stats["links_total"] = len(homepage_links)
        stats["pages_checked"] = 1

        # 2. 对链接按政策相关性评分排序
        scored = self._score_and_rank(homepage_links)
        candidates = [(url, title, score) for url, title, score in scored
                      if url not in visited]

        # 3. 对Top-N候选页,检查是否是列表页(含多个文章链接)
        for url, title, score in candidates[:MAX_PAGES_TO_CHECK]:
            if len(discovered) >= max_listings:
                break
            if url in visited:
                continue
            visited.add(url)

            # 只检查看起来像列表页的URL(路径短/含频道关键词)
            if not self._looks_like_listing(url):
                continue

            full_url = urljoin(base, url) if not url.startswith('http') else url
            sub_links = self._fetch_and_extract_links(full_url, domain)
            stats["pages_checked"] += 1

            article_count = self._count_article_links(sub_links)
            if article_count >= MIN_ARTICLE_LINKS:
                discovered.append({
                    "url": full_url,
                    "title": title[:80],
                    "article_count": article_count,
                    "score": score,
                })
                # 继续钻取: 检查此列表页的子链接,发现更多列表页
                for sub_url, sub_title in sub_links:
                    if len(discovered) >= max_listings:
                        break
                    if sub_url in visited:
                        continue
                    if self._looks_like_listing(sub_url):
                        visited.add(sub_url)
                        sub_full = urljoin(full_url, sub_url) if not sub_url.startswith('http') else sub_url
                        sub_sub_links = self._fetch_and_extract_links(sub_full, domain)
                        stats["pages_checked"] += 1
                        sub_article_count = self._count_article_links(sub_sub_links)
                        if sub_article_count >= MIN_ARTICLE_LINKS:
                            discovered.append({
                                "url": sub_full,
                                "title": sub_title[:80],
                                "article_count": sub_article_count,
                                "score": 1,  # 二级发现,默认低分
                            })

            time.sleep(1)

        return {
            "domain": domain,
            "discovered": discovered,
            "stats": stats,
        }

    # ================================================================
    # 批量探测
    # ================================================================
    def discover_batch(self, domains, max_listings_per_domain=3):
        """批量探测多个域名。返回 {results: [...], summary}"""
        results = []
        for domain in domains:
            r = self.discover(domain, max_listings=max_listings_per_domain)
            results.append(r)
            time.sleep(2)
        total = sum(len(r["discovered"]) for r in results)
        return {
            "results": results,
            "summary": {
                "domains_scanned": len(domains),
                "total_discovered": total,
                "domains_with_sources": sum(1 for r in results if r["discovered"]),
            },
        }

    # ================================================================
    # 内部方法
    # ================================================================
    def _init_session(self):
        self._session = requests.Session()
        self._session.headers.update({
            "User-Agent": "RuralRevitalizationKB/2.3.8 (source-discovery; Sichuan-rural-research)",
            "Accept-Language": "zh-CN,zh;q=0.9",
        })

    def _fetch_and_extract_links(self, url, domain):
        """抓取页面并提取同域链接。返回 [(url, title, full_url)]"""
        links = []
        try:
            resp = self._session.get(url, timeout=FETCH_TIMEOUT, allow_redirects=True)
            resp.raise_for_status()
            html = self._decode(resp.content)
            if not html:
                return links

            link_pattern = re.compile(
                r'<a[^>]*href\s*=\s*["\']([^"\']+)["\'][^>]*>(.*?)</a>',
                re.IGNORECASE | re.DOTALL
            )
            seen = set()
            base_domain = domain.replace("www.", "")

            for match in link_pattern.finditer(html):
                href = match.group(1).strip()
                title_raw = re.sub(r'<[^>]+>', '', match.group(2)).strip()
                title_raw = re.sub(r'\s+', ' ', title_raw)

                if not href or href.startswith('#') or href.startswith('javascript:'):
                    continue
                if len(title_raw) < 4:
                    continue

                full_url = urljoin(url, href)
                if '#' in full_url:
                    full_url = full_url.split('#')[0]

                # 只保留同域链接
                try:
                    if base_domain not in urlparse(full_url).netloc:
                        continue
                except Exception:
                    continue

                # 过滤静态资源
                if any(full_url.lower().endswith(ext) for ext in
                       ('.jpg', '.jpeg', '.png', '.gif', '.pdf', '.doc', '.docx',
                        '.xls', '.xlsx', '.ppt', '.zip', '.rar', '.css', '.js')):
                    continue

                if full_url in seen:
                    continue
                seen.add(full_url)
                links.append((full_url, title_raw))

        except Exception:
            pass

        return links

    def _decode(self, raw_bytes):
        """智能解码(meta→UTF-8→GBK)"""
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

    def _score_and_rank(self, links):
        """对链接按政策相关性评分排序。返回 [(url, title, score)]"""
        policy_path_keywords = [
            'zwgk', 'zhengce', 'xxgk', 'tzgg', 'zcfg', 'zcjd',
            'gongkai', 'gongbao', 'flfg', 'zfxxgk',
            '通知', '公告', '政策', '政务', '信息', '法规',
        ]
        policy_title_keywords = [
            '政务公开', '政策文件', '通知公告', '政策解读', '法规文件',
            '信息公开', '政府公报', '政策法规', '规范性文件', '公示公告',
            '规划计划', '人事信息', '财政信息', '统计信息', '应急管理',
        ]
        article_url_patterns = [
            '/content/', '/article/', '/info/', '/detail/',
            r'/20\d{2}[/-]\d{1,2}[/-]\d{1,2}',
            r'[a-f0-9]{16,}',
        ]

        scored = []
        for url, title in links:
            score = 0
            path = urlparse(url).path.lower()

            # URL含政策频道关键词
            for kw in policy_path_keywords:
                if kw in path:
                    score += 3
                    break

            # URL是文章页→降低分数(我们要找列表页,不是文章页)
            is_article = any(re.search(p, path) for p in article_url_patterns)
            if is_article:
                score -= 1

            # 路径深度(列表页通常1-3级)
            parts = [p for p in path.split('/') if p]
            if 1 <= len(parts) <= 3:
                score += 1
            elif len(parts) >= 5:
                score -= 1  # 太深=可能是文章页

            # 标题匹配
            for kw in policy_title_keywords:
                if kw in title:
                    score += 2
                    break

            # 标题长度合理(列表页标题通常10-30字)
            if 8 <= len(title) <= 40:
                score += 1

            if score >= 3:
                scored.append((url, title, score))

        scored.sort(key=lambda x: x[2], reverse=True)
        return scored

    def _looks_like_listing(self, url):
        """判断URL是否看起来像列表页(非文章页)"""
        path = urlparse(url).path.lower()
        # 文章页特征→不是列表页
        article_indicators = [
            r'/content/', r'/article/', r'/info/', r'/detail/',
            r'/20\d{2}[/-]\d{1,2}[/-]\d{1,2}',
            r'[a-f0-9]{16,}',
            r'\.s?html$',  # .html/.shtml 可能是文章页也可能是列表页
        ]
        # 列表页特征
        listing_indicators = [
            '/zwgk/', '/zhengce/', '/xxgk/', '/tzgg/', '/zcfg/',
            '/zcjd/', '/gongkai/', 'index', 'list', 'default',
        ]

        listing_score = sum(1 for p in listing_indicators if p in path)
        article_score = sum(1 for p in article_indicators if re.search(p, path))

        return listing_score > article_score

    def _count_article_links(self, links):
        """统计一个页面中看起来像文章链接的数量(判断是否为列表页)"""
        article_patterns = [
            r'/content/', r'/article/', r'/info/', r'/detail/',
            r'/20\d{2}[/-]\d{1,2}[/-]\d{1,2}',
            r'[a-f0-9]{16,}',
        ]
        count = 0
        for url, _ in links:
            path = urlparse(url).path.lower()
            if any(re.search(p, path) for p in article_patterns):
                count += 1
            elif len(path.split('/')) >= 4:  # 深路径=可能是文章
                count += 1
        return count
