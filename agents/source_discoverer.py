"""
source_discoverer.py - 信源探测器: URL模式暴力探测政府网站政策列表页
路径：agents/source_discoverer.py
版本：v2.3.8

中国政府网站结构高度标准化(国务院办公厅强制规范),与其解析首页HTML,
不如用URL模式直接探测。对每个候选URL发HEAD→200就GET→数文章链接→达标就收录。
"""

import re
import time
from concurrent.futures import ThreadPoolExecutor, as_completed
from urllib.parse import urljoin, urlparse

try:
    import requests
except ImportError:
    requests = None

FETCH_TIMEOUT = 15
MIN_ARTICLE_LINKS = 5
MAX_WORKERS = 5


class SourceDiscoverer(object):
    """信源探测器。URL模式暴力探测→验证列表页→返回发现结果。"""

    # 中国政府网站标准化URL路径模式(国务院办公厅规范,各级网站通用)
    # 格式: (路径片段列表, 栏目名称)
    PATH_PATTERNS = [
        # === 一级路径(大概率是列表页) ===
        (["zwgk"], "政务公开"),
        (["xxgk"], "信息公开"),
        (["zhengce"], "政策"),
        (["tzgg"], "通知公告"),
        (["zcjd"], "政策解读"),
        (["gongkai"], "公开"),
        (["govinfo"], "政府信息"),
        (["zcfg"], "政策法规"),
        (["flfg"], "法律法规"),
        # === 二级路径(更精确的政策列表页) ===
        (["zwgk", "zc"], "政策文件"),
        (["zwgk", "zcfg"], "政策法规"),
        (["zwgk", "tzgg"], "通知公告"),
        (["zwgk", "zcjd"], "政策解读"),
        (["zwgk", "zhengce"], "政策"),
        (["zwgk", "flfg"], "法律法规"),
        (["zwgk", "gfxwj"], "规范性文件"),
        (["zwgk", "xxgk"], "信息公开"),
        (["xxgk", "zc"], "政策文件"),
        (["xxgk", "zcfg"], "政策法规"),
        (["xxgk", "tzgg"], "通知公告"),
        (["xxgk", "zcjd"], "政策解读"),
        (["xxgk", "gfxwj"], "规范性文件"),
        (["zhengce", "zcjd"], "政策解读"),
        (["zhengce", "zcfg"], "政策法规"),
        (["zhengce", "tzgg"], "通知公告"),
        # === 带index/列表页后缀 ===
        (["zwgk", "zc", "index"], "政策文件"),
        (["xxgk", "tzgg", "index"], "通知公告"),
        (["zhengce", "zcjd", "index"], "政策解读"),
        # === 市州常见变体 ===
        (["zw", "zcwjs", "zcfg"], "政策法规"),
        (["zw", "zcwjs", "zcjd"], "政策解读"),
        (["zw", "zcwjs", "tzgg"], "通知公告"),
        (["zwgk", "zfxxgk", "zcjd"], "政策解读"),
        (["xxgk", "zfxxgk", "zcfg"], "政策法规"),
    ]

    # 文章页URL特征(用于计数)
    ARTICLE_PATTERNS = [
        r"/content/",
        r"/article/",
        r"/info/",
        r"/detail/",
        r"/20\d{2}[/-]\d{1,2}[/-]\d{1,2}",  # 含日期的路径
        r"[a-f0-9]{16,}",  # 长ID
        r"\.s?html$",  # .html/.shtml结尾
        r"/t\d{8}_\d+",  # 常见文章ID格式
    ]

    def __init__(self):
        self._session = None

    # ================================================================
    # 主入口
    # ================================================================
    def discover(self, domain, max_listings=10):
        """探测单个域名的政策列表页(URL模式暴力探测)。
        返回 {domain, discovered: [{url, title, article_count}], stats}
        """
        if not requests:
            return {"domain": domain, "discovered": [], "error": "requests未安装"}

        self._init_session()
        discovered = []
        stats = {"candidates_tried": 0, "http_ok": 0, "verified": 0}

        # 生成候选URL并去重
        candidates = self._generate_candidates(domain)
        seen = set()
        unique_candidates = []
        for url, name in candidates:
            key = url.rstrip("/")
            if key not in seen:
                seen.add(key)
                unique_candidates.append((url, name))
        stats["candidates_total"] = len(unique_candidates)

        # 并发验证候选URL
        with ThreadPoolExecutor(max_workers=MAX_WORKERS) as executor:
            futures = {
                executor.submit(self._verify_listing, url, name): (url, name)
                for url, name in unique_candidates
            }
            for future in as_completed(futures):
                if len(discovered) >= max_listings:
                    break
                stats["candidates_tried"] += 1
                result = future.result()
                if result:
                    stats["http_ok"] += 1
                    if result.get("verified"):
                        stats["verified"] += 1
                        discovered.append(result)
                        # 发现一个后,尝试同级目录的其他常见子路径
                        self._probe_siblings(
                            result["url"], domain, discovered, max_listings, stats
                        )

        # 按文章数降序排列(文章越多=列表页越靠谱)
        discovered.sort(key=lambda x: x.get("article_count", 0), reverse=True)

        # 去重(同一个URL去index.html后缀后可能重复)
        seen_urls = set()
        deduped = []
        for d in discovered:
            key = (
                d["url"]
                .rstrip("/")
                .replace("/index.html", "")
                .replace("/index.shtml", "")
                .replace("/index.htm", "")
            )
            if key not in seen_urls:
                seen_urls.add(key)
                deduped.append(d)
        discovered = deduped

        return {
            "domain": domain,
            "discovered": discovered[:max_listings],
            "stats": stats,
        }

    def discover_batch(self, domains, max_listings_per_domain=10):
        """批量探测多个域名。"""
        results = []
        for domain in domains:
            r = self.discover(domain, max_listings=max_listings_per_domain)
            results.append(r)
            time.sleep(1)
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
    # 候选URL生成
    # ================================================================
    def _generate_candidates(self, domain):
        """生成一个域名的所有候选政策列表页URL。"""
        candidates = []
        for path_parts, name in self.PATH_PATTERNS:
            path = "/".join(path_parts)
            # 尝试带/不带尾部斜杠
            for suffix in ["/", ""]:
                url = f"https://{domain}/{path}{suffix}"
                candidates.append((url, name))
            # 尝试 .shtml .html index.shtml
            for idx in ["index.shtml", "index.html", "index.htm"]:
                url = f"https://{domain}/{path}/{idx}"
                candidates.append((url, name))
        return candidates

    def _probe_siblings(self, found_url, domain, discovered, max_listings, stats):
        """发现一个列表页后,探测同级目录下的其他常见子路径。"""
        path = urlparse(found_url).path.rstrip("/")
        # 去掉尾部index.*
        path = re.sub(r"/index\.(s?html|htm)$", "", path)
        # 取父目录
        parts = [p for p in path.split("/") if p]
        if len(parts) < 1:
            return
        parent = "/".join(parts[:-1]) if len(parts) > 1 else ""

        sibling_names = ["zcjd", "zcfg", "tzgg", "zc", "flfg", "gfxwj", "zhengce"]
        seen_urls = {d["url"].rstrip("/") for d in discovered}
        for sib in sibling_names:
            if len(discovered) >= max_listings:
                return
            if parent:
                sibling_url = f"https://{domain}/{parent}/{sib}/"
            else:
                sibling_url = f"https://{domain}/{sib}/"
            if sibling_url.rstrip("/") in seen_urls:
                continue
            seen_urls.add(sibling_url.rstrip("/"))
            stats["candidates_tried"] += 1
            result = self._verify_listing(sibling_url, f"同级:{sib}")
            if result and result.get("verified"):
                # 跳过重定向到根目录的
                result_path = urlparse(result["url"]).path.rstrip("/")
                if len(result_path) < 2:
                    continue
                stats["verified"] += 1
                discovered.append(result)

    # ================================================================
    # 列表页验证
    # ================================================================
    def _verify_listing(self, url, name):
        """验证一个URL是否是真的政策列表页(GET→检查HTTP 200→数文章链接)。
        大多数中国政府网站不支持HEAD请求,直接GET。"""
        try:
            resp = self._session.get(
                url, timeout=FETCH_TIMEOUT, allow_redirects=True, stream=True
            )  # stream=True先读headers
            if resp.status_code >= 400:
                resp.close()
                return None
            content_type = resp.headers.get("Content-Type", "")
            if (
                "text/html" not in content_type
                and "application/xhtml" not in content_type
            ):
                resp.close()
                return None

            # 读body(限制大小避免下载大文件)
            raw = b""
            for chunk in resp.iter_content(chunk_size=8192):
                raw += chunk
                if len(raw) > 200000:  # 200KB足够判断
                    break
            resp.close()

            if len(raw) < 1000:
                return None

            html = self._decode(raw)
            if not html:
                return None

            # 提取标题
            title_m = re.search(r"<title[^>]*>(.*?)</title>", html, re.IGNORECASE)
            page_title = title_m.group(1).strip() if title_m else name

            # 跳过明显的错误页/跳转页
            skip_titles = ["404", "500", "错误", "不存在", "跳转", "redirect", "error"]
            if any(s in page_title.lower() for s in skip_titles):
                return None

            # 数文章链接
            domain = urlparse(url).netloc
            article_count = self._count_article_links(html, url, domain)
            verified = article_count >= MIN_ARTICLE_LINKS

            return {
                "url": resp.url,
                "title": page_title[:80],
                "article_count": article_count,
                "verified": verified,
                "content_len": len(raw),
            }
        except Exception:
            return None

    def _count_article_links(self, html, base_url, domain):
        """计算页面中文章链接的数量。"""
        link_pattern = re.compile(
            r'<a[^>]*href\s*=\s*["\']([^"\']+)["\']', re.IGNORECASE
        )
        count = 0
        seen = set()
        base_domain = domain.replace("www.", "")

        for match in link_pattern.finditer(html):
            href = match.group(1).strip()
            if not href or href.startswith("#") or href.startswith("javascript:"):
                continue

            full_url = urljoin(base_url, href)
            if "#" in full_url:
                full_url = full_url.split("#")[0]

            # 同域
            try:
                if base_domain not in urlparse(full_url).netloc:
                    continue
            except Exception:
                continue

            if full_url in seen:
                continue
            seen.add(full_url)

            path = urlparse(full_url).path.lower()
            # 匹配文章页特征
            if any(re.search(p, path) for p in self.ARTICLE_PATTERNS):
                count += 1
            # 深度路径也很可能是文章
            elif len([p for p in path.split("/") if p]) >= 4:
                count += 1

        return count

    # ================================================================
    # 工具方法
    # ================================================================
    def _init_session(self):
        self._session = requests.Session()
        self._session.headers.update(
            {
                "User-Agent": "RuralRevitalizationKB/2.3.8 (source-discovery)",
                "Accept-Language": "zh-CN,zh;q=0.9",
                "Accept": "text/html,application/xhtml+xml",
            }
        )

    def _decode(self, raw_bytes):
        """智能解码(meta→UTF-8→GBK)"""
        head = raw_bytes[:2000]
        meta_enc = None
        m = re.search(rb'charset[="\s]+([a-zA-Z0-9_-]+)', head, re.IGNORECASE)
        if m:
            try:
                meta_enc = m.group(1).decode("ascii").lower()
            except Exception:
                pass
        for enc in ([meta_enc] if meta_enc else []) + ["utf-8", "gbk", "gb18030"]:
            try:
                text = raw_bytes.decode(enc, errors="strict")
                if sum(1 for c in text[:2000] if "一" <= c <= "鿿") > 10:
                    return text
            except (UnicodeDecodeError, LookupError):
                continue
        return raw_bytes.decode("utf-8", errors="replace")
