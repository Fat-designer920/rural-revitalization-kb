"""
crawler_scheduler.py - 爬虫调度器(深度爬取+政策搜索+自动分类+变化检测+质量门禁)
路径：agents/crawler_scheduler.py
版本：v2.3.7-part7

深度爬取: 不从仅首页HTML→改为进入文章页→提取正文→质量门禁→CEO审核。
立规则77强制: <500字=丢弃, 乱码=丢弃, 无政策关键词=丢弃。
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

# === Gov.cn 政策搜索关键词组(四川乡村振兴5大核心领域) ===
GOV_SEARCH_KEYWORD_GROUPS = {
    "全域土地综合整治": [
        "全域土地综合整治", "国土综合整治", "田水路林村", "土地整治试点",
        "村庄规划", "农用地整理", "建设用地整理"
    ],
    "增减挂钩+占补平衡": [
        "增减挂钩", "占补平衡", "城乡建设用地增减挂钩", "耕地占补平衡",
        "指标交易", "节余指标流转", "建设用地指标"
    ],
    "集体经营性建设用地入市": [
        "集体经营性建设用地入市", "农村集体建设用地", "同权同价",
        "入市收益分配", "集体土地入市", "农村土地制度改革"
    ],
    "高标准农田建设": [
        "高标准农田建设", "高标准农田", "农田建设补助", "耕地质量提升",
        "粮食安全", "永久基本农田", "高标准农田管护"
    ],
    "乡村振兴专项债": [
        "乡村振兴专项债", "地方政府专项债", "涉农资金整合", "乡村振兴基金",
        "政策性金融", "农村金融", "乡村振兴债券"
    ],
}

# Gov.cn 搜索端点(Sichuan-specific policy search)
GOV_SEARCH_ENDPOINTS = [
    {"domain": "www.gov.cn", "search_url": "https://sousuo.www.gov.cn/sousuo/search.shtml?searchWord={keyword}&searchType=all"},
    {"domain": "www.sc.gov.cn", "search_url": "https://www.sc.gov.cn/search?keyword={keyword}"},
    {"domain": "dnr.sc.gov.cn", "search_url": "https://dnr.sc.gov.cn/search?keyword={keyword}"},
    {"domain": "nynct.sc.gov.cn", "search_url": "https://nynct.sc.gov.cn/search?keyword={keyword}"},
    {"domain": "fgw.sc.gov.cn", "search_url": "https://fgw.sc.gov.cn/search?keyword={keyword}"},
]

# 政策类型检测模式 (法律/行政法规/部门规章/地方性法规/规范性文件/通知公告)
POLICY_TYPE_PATTERNS = [
    ("法律", [r"中华人民共和国\w+法", r"主席令\s*第\s*\d+号", r"全国人民代表大会"]),
    ("行政法规", [r"国务院令\s*第\s*\d+号", r"中华人民共和国\w+条例", r"国务院.*公布"]),
    ("部门规章", [r"(自然资源部|农业农村部|财政部|国家发展改革委|住房和城乡建设部|生态环境部|水利部)\s*令", r"部令\s*第\s*\d+号"]),
    ("地方性法规", [r"四川省\w+条例", r"四川省人民代表大会常务委员会", r"成都市\w+条例"]),
    ("规范性文件", [r"关于印发[\w\s]+的通知", r"实施意见", r"指导意见", r"实施办法", r"暂行办法", r"若干措施"]),
    ("通知公告", [r"关于\w+的通知\s*$", r"公告", r"公示", r"通告"]),
]

# 发文字号 regex: 匹配 国发〔2024〕1号 / 川府发〔2023〕15号 / 自然资发〔2024〕10号
DOC_NUMBER_RE = re.compile(
    r'([一-鿿]+发|[一-鿿]+办发|[一-鿿]+函|[一-鿿]+规'
    r'|[一-鿿]+字|[一-鿿]+令)'
    r'[〈《\[\(【〔]?(\d{4})[〉》\]\)】〕]?\s*(\d+)\s*号'
)

# 日期匹配模式(中国政府公文格式)
DATE_PATTERNS = [
    re.compile(r'(\d{4})\s*年\s*(\d{1,2})\s*月\s*(\d{1,2})\s*日'),
    re.compile(r'(\d{4})[-/](\d{1,2})[-/](\d{1,2})'),
]

# 发文机关匹配(四川省乡村振兴相关常见发文主体)
ISSUING_BODY_RE = re.compile(
    r'(国务院|四川省人民政府|四川省自然资源厅|四川省农业农村厅|四川省财政厅'
    r'|四川省发展和改革委员会|四川省住房和城乡建设厅|自然资源部|农业农村部'
    r'|财政部|国家发展和改革委员会|成都市人民政府|成都市规划和自然资源局'
    r'|四川省生态环境厅|生态环境部|四川省水利厅|水利部'
    r'|四川省乡村振兴局|国家乡村振兴局)'
)


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
    # 深度爬取: 从首页/列表页提取文章链接→跟进→提取正文
    # ================================================================
    def _extract_article_links(self, html, base_url, max_links=50):
        """从任意gov页面HTML中提取政策/文章链接。
        优先级: 政策频道URL模式 > 含政策关键词的链接文本 > 长文本链接。
        返回 [{url, title, link_type}] 唯一列表。
        """
        if not html:
            return []

        # 政策频道URL模式(政府网站常见)
        policy_url_patterns = [
            r'/zwgk/', r'/zhengce/', r'/xxgk/', r'/content/', r'/article/',
            r'/govinfo/', r'/gongbao/', r'/zcfg/', r'/flfg/', r'/zfxxgk/',
            r'/信息公开/', r'/政策/', r'/通知/', r'/意见/', r'/政策解读/',
            r'/tdzl/', r'/nync/', r'/fgw/', r'/czt/', r'/zrzy/',
        ]

        # 政策文章标题关键词
        policy_title_keywords = [
            '通知', '意见', '办法', '规定', '方案', '标准', '公告', '公示',
            '政策', '解读', '措施', '规划', '条例', '指南', '规程',
            '耕地', '土地', '农村', '农业', '乡村振兴', '农田', '粮食',
            '整治', '挂钩', '占补', '入市', '建设',
        ]

        links = []
        seen_urls = set()
        parsed_base = urlparse(base_url)

        link_pattern = re.compile(
            r'<a[^>]*href\s*=\s*["\']([^"\']+)["\'][^>]*>(.*?)</a>',
            re.IGNORECASE | re.DOTALL
        )

        scored_links = []
        for match in link_pattern.finditer(html):
            href = match.group(1).strip()
            title_raw = re.sub(r'<[^>]+>', '', match.group(2)).strip()
            title_raw = re.sub(r'\s+', ' ', title_raw)

            if not href or href.startswith('#') or href.startswith('javascript:'):
                continue

            # 构建绝对URL
            full_url = urljoin(base_url, href)

            # 只保留同域链接(避免跨站跳转)
            try:
                parsed_link = urlparse(full_url)
                if parsed_link.netloc != parsed_base.netloc:
                    continue
            except Exception:
                continue

            # 去.html/.htm/.shtml后缀, 去首页/锚点
            path = parsed_link.path.lower()
            if path in ('', '/', '/index.html', '/index.htm', '/index.shtml'):
                continue
            if '#' in full_url:
                full_url = full_url.split('#')[0]

            if full_url in seen_urls:
                continue
            seen_urls.add(full_url)

            # 过滤静态资源
            skip_exts = ('.jpg', '.jpeg', '.png', '.gif', '.pdf', '.doc', '.docx',
                         '.xls', '.xlsx', '.ppt', '.pptx', '.zip', '.rar', '.css', '.js')
            if any(full_url.lower().endswith(ext) for ext in skip_exts):
                continue

            # 评分: URL模式匹配 + 标题关键词匹配
            score = 0
            match_reason = []
            for pat in policy_url_patterns:
                if pat in path:
                    score += 3
                    match_reason.append(f'URL:{pat}')
                    break

            if title_raw:
                title_len = len(title_raw)
                if title_len > 10:
                    score += 1  # 长标题更可能是文章
                if title_len > 20:
                    score += 1
                for kw in policy_title_keywords:
                    if kw in title_raw:
                        score += 2
                        match_reason.append(f'标题:{kw}')
                        break
                # 中文字符占比
                chinese = sum(1 for c in title_raw if '一' <= c <= '鿿')
                if len(title_raw) > 0 and chinese / len(title_raw) > 0.3:
                    score += 1

            if score >= 2:  # 至少有一定相关性
                scored_links.append((score, full_url, title_raw, match_reason))

        scored_links.sort(key=lambda x: x[0], reverse=True)
        for score, url, title, reason in scored_links[:max_links]:
            links.append({
                "url": url,
                "title": title[:120] if title else '',
                "link_type": '|'.join(reason[:2]),
                "score": score,
            })

        return links

    def _deep_fetch(self, url, max_depth=2, max_articles=20, timeout=30):
        """深度爬取: 首页→提取文章链接→跟进文章页→提取正文→质量门禁。
        不是只抓首页HTML,而是真正进入政策文章页面提取全文。
        返回 {articles: [{url, title, text, char_count, quality, filepath}], stats}
        """
        all_articles = []
        visited_urls = set()
        article_queue = [(url, 0)]  # (url, depth)
        stats = {"pages_fetched": 0, "links_found": 0, "articles_extracted": 0,
                 "quality_fail": 0}

        while article_queue and len(all_articles) < max_articles:
            current_url, depth = article_queue.pop(0)
            if current_url in visited_urls:
                continue
            visited_urls.add(current_url)

            fetched = self._fetch_url(current_url, timeout=timeout)
            stats["pages_fetched"] += 1

            if not fetched.get("success"):
                continue

            html_content = fetched.get("content", "")

            # 乱码检测
            if not self._clean_text_for_save(html_content):
                continue

            # 在首页/列表页(depth=0)提取文章链接
            if depth < max_depth:
                links = self._extract_article_links(html_content, current_url)
                stats["links_found"] += len(links)
                for link in links:
                    link_url = link["url"]
                    if link_url not in visited_urls:
                        article_queue.append((link_url, depth + 1))

            # 对文章页(depth>=1)提取正文内容
            if depth >= 1:
                main_content = self._extract_main_content(html_content)
                if main_content:
                    char_count = len(main_content)
                    page_title = fetched.get("title", "")
                    article = {
                        "url": current_url,
                        "title": page_title[:120] if page_title else "",
                        "text": main_content,
                        "char_count": char_count,
                        "quality": "unknown",
                        "filepath": None,
                    }
                    all_articles.append(article)
                    stats["articles_extracted"] += 1

            time.sleep(CRAWL_INTERVAL_SEC)

        # 对每篇文章保存并跑质量门禁
        review_dir = PROJECT_ROOT / REVIEW_DIR_NAME
        os.makedirs(review_dir, exist_ok=True)
        qualified = []

        for article in all_articles:
            safe_name = self._safe_filename(article["url"], article["title"])
            timestamp = datetime.now().strftime('%Y%m%d_%H%M%S')
            filename = f"{safe_name}_{timestamp}.txt"
            save_path = review_dir / filename

            # 加元数据头
            header = (
                f"# 来源: {article['url']}\n"
                f"# 标题: {article['title']}\n"
                f"# 抓取时间: {datetime.now().strftime('%Y-%m-%d %H:%M')}\n"
                f"# 深度爬取: depth≥1文章页正文提取\n"
                f"{'='*50}\n\n"
            )
            full_text = header + article["text"]

            with open(save_path, "w", encoding="utf-8") as f:
                f.write(full_text[:MAX_CONTENT_CHARS])

            article["filepath"] = str(save_path)

            # 立规则77质量门禁
            passed, reason_code, reason_detail = self._quality_gate(str(save_path))
            if passed:
                article["quality"] = "good"
                qualified.append(article)
            else:
                article["quality"] = reason_code
                article["quality_reason"] = reason_detail
                stats["quality_fail"] += 1
                # 不合格立即删除(立规则77: 乱码=直接丢弃)
                try:
                    os.remove(save_path)
                    article["filepath"] = None
                except Exception:
                    pass

        stats["qualified_count"] = len(qualified)
        return {"articles": qualified, "stats": stats}

    def _extract_main_content(self, html):
        """从文章页HTML提取正文内容(剔除导航/侧栏/页脚等噪音)。
        返回纯文本字符串,失败返回空字符串。
        """
        if not html:
            return ""

        # 1. 去除噪音标签(script/style/head/nav/footer/header/aside/form/noscript)
        for tag in ('script', 'style', 'head', 'nav', 'footer', 'header', 'aside',
                     'noscript', 'iframe', 'svg', 'form', 'select', 'button',
                     'input', 'textarea', 'link', 'meta', 'base', 'map', 'canvas'):
            html = re.sub(rf'<{tag}[^>]*>.*?</{tag}>', ' ', html,
                         flags=re.DOTALL | re.IGNORECASE)
            html = re.sub(rf'<{tag}[^>]*/?>', ' ', html, flags=re.IGNORECASE)

        # 2. 去除HTML注释
        html = re.sub(r'<!--.*?-->', ' ', html, flags=re.DOTALL)

        # 3. 尝试定位正文容器(优先匹配gov.cn常见正文区)
        content_area = ""
        main_patterns = [
            r'<div[^>]*(?:class|id)\s*=\s*["\'][^"\']*?(?:content|article|main|text|body|TRS_Editor|zoom|pages_content|con_main|xxgk_content|zwgk_content|zhengce_content|info_content|detail_content|UCAP-CONTENT|Content|MainContent|ArticleContent|NewsContent)[^"\']*["\'][^>]*>(.*?)</div>',
            r'<article[^>]*>(.*?)</article>',
            r'<main[^>]*>(.*?)</main>',
            r'<div[^>]*(?:id|class)\s*=\s*["\'][^"\']*?(?:content|article|main|text|body)[^"\']*["\'][^>]*>(.*?)</div>',
        ]
        for pat in main_patterns:
            m = re.search(pat, html, re.IGNORECASE | re.DOTALL)
            if m:
                content_area = m.group(1)
                break

        # 没有找到明确的正文容器,回退到全页处理
        if not content_area or len(content_area) < 200:
            content_area = html

        # 4. 去除所有HTML标签
        text = re.sub(r'<[^>]+>', ' ', content_area)

        # 5. 解码HTML实体
        text = text.replace('&nbsp;', ' ').replace('&lt;', '<').replace('&gt;', '>')
        text = text.replace('&amp;', '&').replace('&quot;', '"').replace('&apos;', "'")
        text = re.sub(r'&[a-z]+;', ' ', text)
        text = re.sub(r'&#\d+;', ' ', text)

        # 6. 去除URL和长数字串
        text = re.sub(r'https?://\S+', ' ', text)

        # 7. 按行保留有意义的内容
        lines = []
        for line in text.split('\n'):
            stripped = line.strip()
            if not stripped:
                continue
            # 跳过短导航行(纯链接、纯数字、纯日期)
            if re.match(r'^[\s\d\-\.,;:|\/\\]+$', stripped):
                continue
            if len(stripped) < 8:
                continue
            chinese_chars = len(re.findall(r'[一-鿿]', stripped))
            # 保留含中文的行或足够长的文本行
            if chinese_chars >= 5 or (len(stripped) > 30 and chinese_chars > 0):
                lines.append(stripped)

        text = '\n'.join(lines)

        # 8. 压缩连续空白行
        text = re.sub(r'\n{3,}', '\n\n', text)
        text = text.strip()

        return text

    def _quality_gate(self, filepath):
        """立规则77强制质量门禁: 检查爬取文件是否合格。
        四条红线(任一不通过=直接丢弃):
          0. 乡村振兴相关性不足(采矿/人事/招标等不相关内容排除)
          1. 正文<500字(低质量)
          2. 中文字符<5%(乱码)
          3. 不含任何政策关键词(非政策内容)
        返回 (passed: bool, reason_code: str, detail: str)
        """
        if not os.path.exists(filepath):
            return False, "file_missing", "文件不存在"

        try:
            with open(filepath, 'r', encoding='utf-8') as f:
                content = f.read()
        except Exception as e:
            return False, "read_error", str(e)

        # 切掉元数据头(从第一个'='分隔线后取正文)
        text = content
        separator_idx = content.find('\n\n')
        if separator_idx > 0:
            text = content[separator_idx:]

        text = text.strip()

        # 红线0: 乡村振兴相关性(排除采矿/人事/招标等无关内容)
        exclude_keywords = [
            # 采矿/矿业(不相关)
            '采矿权','探矿权','煤矿','出让收益','评估结果','评估项目','矿业权',
            # 人事/行政(不相关)
            '招聘','任免','人事','天气预报','放假安排','信访',
            '干部','述职','考核','表彰','培训','讲座','学习','会议纪要',
            # 招标/采购(不相关)
            '招标公告','中标','成交公告','招租','招商','拍卖','竞价',
            # 其他不相关
            '领导','调研','慰问','工作动态','简报','周报','月报','公示',
            '听证','复议','仲裁','举报','投诉','信访',
        ]
        for kw in exclude_keywords:
            if kw in text:
                return False, "irrelevant", f"不相关内容(含'{kw}'),与乡村振兴无关"
        # 至少包含2个乡村振兴关键词
        rural_keywords = ['土地','耕地','农村','农业','乡村','农田','宅基地',
                         '振兴','整治','规划','建设','保护','生态','水利',
                         '交通','补偿','补贴','补助','资金','项目','政策',
                         '指标','审批','登记','管理办法','实施方案','意见','通知']
        rural_count = sum(1 for kw in rural_keywords if kw in text)
        if rural_count < 2:
            return False, "irrelevant", f"乡村振兴相关度不足(仅{rural_count}个关键词)"

        # 红线1: 长度检查(<500字=低质量)
        if len(text) < MIN_CONTENT_CHARS:
            return False, "low_quality", f"正文{len(text)}字<{MIN_CONTENT_CHARS}字门槛"

        # 红线2: 乱码检查(<5%中文字符=疑似乱码/非中文页)
        if len(text) > 0:
            chinese_chars = sum(1 for c in text if '一' <= c <= '鿿')
            if chinese_chars / len(text) < 0.05:
                return False, "garbled", f"中文字符{chinese_chars}个({chinese_chars/len(text)*100:.1f}%)<5%"

        # 红线3: 政策关键词检查
        policy_keywords = [
            '政策', '通知', '意见', '办法', '规定', '方案', '标准',
            '耕地', '土地', '农村', '农业', '乡村振兴', '农田', '粮食',
            '整治', '挂钩', '占补', '入市', '建设', '规划', '管理',
            '项目', '资金', '补贴', '补助', '审批', '督察', '考核',
            '申报', '示范', '试点', '补贴',
        ]
        has_policy = any(kw in text for kw in policy_keywords)
        if not has_policy:
            return False, "no_policy_content", "无政策关键词"

        return True, "good", f"正文{len(text)}字,合格"

    # ================================================================
    # Gov.cn政策搜索(借鉴China-Central-Policy-MCP的gov.cn全文检索思路)
    # ================================================================
    def search_gov_policy(self, keyword_group=None, keywords=None, max_results=10):
        """搜索gov.cn政策文档。支持按关键字组或自定义关键字搜索。
        返回 {success, results: [{title, url, snippet, source_domain}]}
        """
        if keyword_group and keyword_group in GOV_SEARCH_KEYWORD_GROUPS:
            kw_list = GOV_SEARCH_KEYWORD_GROUPS[keyword_group]
        elif keywords:
            kw_list = keywords if isinstance(keywords, list) else [keywords]
        else:
            kw_list = []
            for v in GOV_SEARCH_KEYWORD_GROUPS.values():
                kw_list.extend(v[:2])

        all_results = []
        for endpoint in GOV_SEARCH_ENDPOINTS[:3]:
            for kw in kw_list[:3]:
                try:
                    search_url = endpoint["search_url"].format(keyword=kw)
                    fetched = self._fetch_url(search_url, timeout=25)
                    if not fetched.get("success"):
                        continue
                    links = self._extract_policy_links(
                        fetched.get("content", ""),
                        base_domain=endpoint["domain"]
                    )
                    for link in links[:max_results]:
                        if not any(r["url"] == link["url"] for r in all_results):
                            all_results.append(link)
                    time.sleep(1)
                except Exception:
                    continue

        return {"success": True, "keyword_group": keyword_group,
                "keywords_used": kw_list[:9], "total_found": len(all_results),
                "results": all_results[:max_results]}

    def _extract_policy_links(self, html, base_domain):
        """从gov.cn搜索结果页提取政策文档链接。"""
        links = []
        link_pattern = re.compile(
            r'<a[^>]*href="([^"]*(?:zhengce|zwgk|xxgk|content|article'
            r'|govinfo|gongbao|zcfg|flfg)[^"]*)"[^>]*>(.*?)</a>',
            re.IGNORECASE | re.DOTALL
        )
        for match in link_pattern.finditer(html):
            href = match.group(1)
            title_raw = re.sub(r'<[^>]+>', '', match.group(2)).strip()
            if not title_raw or len(title_raw) < 6:
                continue
            if href.startswith("http"):
                full_url = href
            elif href.startswith("//"):
                full_url = "https:" + href
            elif href.startswith("/"):
                full_url = "https://{}{}".format(base_domain, href)
            else:
                continue
            links.append({
                "url": full_url,
                "title": title_raw[:120],
                "snippet": title_raw[:200],
                "source_domain": base_domain,
            })
        return links

    # ================================================================
    # 爬取文档自动分类
    # ================================================================
    def classify_policy_doc(self, text, url="", page_title=""):
        """对新爬取的政策文档自动分类。
        返回 {policy_type, doc_number, publish_date, issuing_body,
               effective_date, matched_categories, confidence}
        """
        if not text:
            return {"policy_type": "未知", "matched_categories": [], "confidence": 0}

        policy_type, type_confidence = self._detect_policy_type(text, url, page_title)
        metadata = self._extract_doc_metadata(text, page_title)
        matched_categories = self._match_keyword_categories(text, page_title)

        confidence = type_confidence
        if metadata.get("doc_number"):
            confidence += 0.15
        if metadata.get("publish_date"):
            confidence += 0.10
        if matched_categories:
            confidence += 0.15
        confidence = min(confidence, 1.0)

        return {
            "policy_type": policy_type,
            "doc_number": metadata.get("doc_number", ""),
            "publish_date": metadata.get("publish_date", ""),
            "issuing_body": metadata.get("issuing_body", ""),
            "effective_date": metadata.get("effective_date", ""),
            "matched_categories": matched_categories,
            "confidence": round(confidence, 2),
        }

    def _detect_policy_type(self, text, url="", page_title=""):
        """检测政策文档类型。返回 (type_name, confidence)。"""
        combined = (page_title + " " + text[:3000]).replace("\n", " ")

        for ptype, patterns in POLICY_TYPE_PATTERNS:
            matches = 0
            for pat in patterns:
                if re.search(pat, combined):
                    matches += 1
            if matches >= 2:
                return ptype, 0.8
            elif matches == 1:
                return ptype, 0.5

        if "zhengce" in url or "zwgk" in url:
            if "content" in url:
                return "规范性文件", 0.4
            return "通知公告", 0.3

        return "通知公告", 0.2

    def _extract_doc_metadata(self, text, page_title=""):
        """提取文档元数据: 发文字号、发布日期、发文机关、生效日期。"""
        metadata = {}
        combined = (page_title + " " + text[:5000]).replace("\n", " ")

        doc_match = DOC_NUMBER_RE.search(combined)
        if doc_match:
            metadata["doc_number"] = doc_match.group(0)

        for date_pat in DATE_PATTERNS:
            date_match = date_pat.search(combined)
            if date_match:
                try:
                    y, m, d = int(date_match.group(1)), int(date_match.group(2)), int(date_match.group(3))
                    if 2000 <= y <= 2030 and 1 <= m <= 12 and 1 <= d <= 31:
                        metadata["publish_date"] = "{:04d}-{:02d}-{:02d}".format(y, m, d)
                        break
                except (ValueError, IndexError):
                    pass

        body_matches = ISSUING_BODY_RE.findall(combined)
        if body_matches:
            seen = set()
            bodies = []
            for b in body_matches:
                if b not in seen:
                    seen.add(b)
                    bodies.append(b)
            metadata["issuing_body"] = "、".join(bodies[:3])

        effective_patterns = [
            r'自\s*(\d{4})\s*年\s*(\d{1,2})\s*月\s*(\d{1,2})\s*日\s*起\s*(?:施行|生效)',
            r'施行日期[：:]\s*(\d{4})\s*年\s*(\d{1,2})\s*月\s*(\d{1,2})\s*日',
            r'自\s*(\d{4})[-/](\d{1,2})[-/](\d{1,2})\s*起\s*(?:施行|生效)',
        ]
        for eff_pat in effective_patterns:
            eff_match = re.search(eff_pat, combined)
            if eff_match:
                try:
                    y, m, d = int(eff_match.group(1)), int(eff_match.group(2)), int(eff_match.group(3))
                    if 2000 <= y <= 2030 and 1 <= m <= 12 and 1 <= d <= 31:
                        metadata["effective_date"] = "{:04d}-{:02d}-{:02d}".format(y, m, d)
                        break
                except (ValueError, IndexError):
                    pass

        return metadata

    def _match_keyword_categories(self, text, page_title=""):
        """将文档匹配到5大四川乡村振兴关键词组。返回匹配到的组名列表。"""
        combined = (page_title + " " + text[:2000])
        matched = []
        for group_name, keywords in GOV_SEARCH_KEYWORD_GROUPS.items():
            score = 0
            for kw in keywords:
                if kw in combined:
                    score += 1
            if score >= 2 or (keywords[0] in combined and score >= 1):
                matched.append(group_name)
        return matched

    # ================================================================
    # 政策变化检测(借鉴MCP的全文对比思路→轻量版:标题语义匹配)
    # ================================================================
    def detect_policy_changes(self, doc_title, doc_url=""):
        """检测新爬取文档是否更新/替代已有政策。
        策略: 提取标题核心名词→查KP库→标题语义匹配→标记"政策更新"。
        返回 {is_update, matched_kps: [{kp_id, title, match_reason}], action}
        """
        if not self.db or not doc_title:
            return {"is_update": False, "matched_kps": [], "action": "new"}

        core_title = doc_title
        for wrapper in [
            r'关于印发[〈《]\s*', r'[〉》]\s*的通知$', r'^关于',
            r'的通知$', r'的批复$', r'的函$', r'的公告$',
        ]:
            core_title = re.sub(wrapper, '', core_title).strip()

        if len(core_title) < 4:
            return {"is_update": False, "matched_kps": [], "action": "new"}

        matched_kps = []
        try:
            conn = self.db.get_connection()
            c = conn.cursor()
            c.execute("""SELECT kp.id, kp.title, kp.review_status,
                                c.level1_name as category
                         FROM knowledge_points kp
                         LEFT JOIN categories c ON c.id = kp.final_category_id
                         WHERE kp.title LIKE ? AND kp.review_status = 'confirmed'
                         LIMIT 10""", ('%' + core_title[:20] + '%',))
            rows = c.fetchall()

            c.execute("""SELECT kp.id, kp.title, kp.review_status,
                                c.level1_name as category
                         FROM knowledge_points kp
                         LEFT JOIN categories c ON c.id = kp.final_category_id
                         WHERE kp.ai_extracted_content LIKE ?
                           AND kp.review_status = 'confirmed'
                         LIMIT 10""", ('%' + core_title[:30] + '%',))
            rows2 = c.fetchall()
            conn.close()

            seen_ids = set()
            all_rows = []
            for row in (rows or []) + (rows2 or []):
                kp_id = row[0]
                if kp_id not in seen_ids:
                    seen_ids.add(kp_id)
                    all_rows.append(row)

            for row in all_rows:
                kp_id, title, status, category = row[0], row[1], row[2], row[3]
                match_reason = self._analyze_update_relationship(doc_title, title)
                if match_reason:
                    matched_kps.append({
                        "kp_id": kp_id, "title": title[:80],
                        "category": category or "", "match_reason": match_reason,
                    })
        except Exception:
            pass

        if matched_kps:
            return {
                "is_update": True,
                "matched_kps": matched_kps,
                "action": "policy_update",
                "warning": "以下已有KP可能被此文档更新/替代,建议人工确认"
            }
        return {"is_update": False, "matched_kps": [], "action": "new"}

    def _analyze_update_relationship(self, new_title, old_title):
        """分析新旧标题之间的更新关系。返回 match_reason 或空字符串。"""
        common_words = set()
        for word in ['办法', '条例', '规定', '意见', '方案', '规划', '标准', '指南']:
            if word in new_title and word in old_title:
                common_words.add(word)

        if not common_words:
            return ""

        update_signals = ['修订', '修正', '修改', '废止', '替代', '更新', '新版', '试行']
        for sig in update_signals:
            if sig in new_title:
                return u"新文档标题含'{}'信号词,可能更新/替代已有同名政策".format(sig)

        simplified_new = re.sub(r'[〈〉《》（）\s]', '', new_title)
        simplified_old = re.sub(r'[〈〉《》（）\s]', '', old_title)

        common = sum(1 for c in simplified_new if c in simplified_old)
        max_len = max(len(simplified_new), len(simplified_old))
        if max_len > 0 and common / max_len > 0.5:
            return u"标题核心词高度相似({:.0%}),可能是同名政策的不同版本".format(common / max_len)

        return ""

    # ================================================================
    # 爬取+自动喂入提取管道
    # ================================================================
    def crawl_and_feed(self, schedule="weekly", max_urls=30, max_articles=200):
        """深度爬取→质量门禁→CEO审核→手动批准→入库。
        v2.3.7-part7: 深度爬取——max_depth=3,每源最多200篇文章,每篇产出一个文件。
        不是首页HTML→进入文章页提取正文。四级红线质量门禁。
        返回 {crawl_result, quality_report, ceo_action}
        """
        review_dir = PROJECT_ROOT / REVIEW_DIR_NAME
        os.makedirs(review_dir, exist_ok=True)

        targets = [t for t in self._targets if t["schedule"] in (schedule, "daily", "weekly")
                   or (schedule == "weekly" and t["schedule"] in ("daily", "weekly"))]

        all_articles = []
        total_stats = {
            "targets_processed": 0,
            "pages_fetched": 0,
            "links_found": 0,
            "articles_extracted": 0,
            "quality_fail": 0,
            "qualified": 0,
            "errors": 0,
        }
        crawl_details = []
        quality_report = {"qualified": 0, "low_quality": 0, "garbled": 0, "no_policy": 0,
                         "details": []}

        for t in targets[:max_urls]:
            url = t["url"]
            category = t.get("category", "policy")
            try:
                result = self._deep_fetch(url, max_depth=2, max_articles=max_articles)
                total_stats["pages_fetched"] += result["stats"]["pages_fetched"]
                total_stats["links_found"] += result["stats"]["links_found"]
                total_stats["articles_extracted"] += result["stats"]["articles_extracted"]
                total_stats["quality_fail"] += result["stats"]["quality_fail"]
                total_stats["targets_processed"] += 1

                for article in result["articles"]:
                    if article["quality"] == "good":
                        total_stats["qualified"] += 1
                        quality_report["qualified"] += 1
                        crawl_details.append({
                            "url": article["url"],
                            "saved": article.get("filepath", ""),
                            "quality": "good",
                            "chars": article["char_count"],
                            "title": article["title"][:60],
                            "source_domain": url,
                            "category": category,
                        })
                        # 记录爬取历史
                        content_hash = hashlib.md5(article["text"].encode('utf-8')).hexdigest()
                        self._record_crawl(article["url"], content_hash, article.get("filepath", ""))
                    else:
                        qr = article.get("quality", "low_quality")
                        quality_report[qr] = quality_report.get(qr, 0) + 1
                        quality_report["details"].append({
                            "url": article["url"],
                            "title": article["title"][:60],
                            "quality": qr,
                            "reason": article.get("quality_reason", "?"),
                        })
            except Exception as e:
                total_stats["errors"] += 1
                crawl_details.append({"url": url, "error": str(e)[:200]})

        return {
            "success": True,
            "crawl_stats": total_stats,
            "quality_report": quality_report,
            "details": crawl_details,
            "message": (
                f"深度爬取完成: 处理{total_stats['targets_processed']}个源站, "
                f"抓取{total_stats['pages_fetched']}页, "
                f"发现{total_stats['links_found']}个链接, "
                f"提取{total_stats['articles_extracted']}篇文章, "
                f"合格{total_stats['qualified']}个, "
                f"丢弃{total_stats['quality_fail']}个(低质量/乱码/非政策)。"
                f"文件已保存到{REVIEW_DIR_NAME}/。"
                f"请CEO审核后决定: 批准→入库 / 拒绝→重爬。"
            ),
            "ceo_action": f"请打开 {REVIEW_DIR_NAME}/ 查看{total_stats['qualified']}个合格爬取文件",
        }

    # ================================================================
    # 全自动管道: 爬取→分类→变化检测→提取就绪
    # ================================================================
    def crawl_classify_extract_chain(self, schedule="weekly", keyword_groups=None):
        """全自动管道: 爬取→自动分类→变化检测→提取就绪→日志完整链。
        返回 {crawl, classify, policy_changes, chain_summary}
        """
        results = {
            "crawl": None, "classify": [], "policy_changes": [],
            "pending_copies": [], "chain_summary": {},
        }

        crawl_result = self.run_scheduled(schedule=schedule)
        results["crawl"] = crawl_result

        if not crawl_result.get("success"):
            results["chain_summary"] = {"status": "crawl_failed",
                                         "error": crawl_result.get("error", "?")}
            return results

        review_dir = PROJECT_ROOT / REVIEW_DIR_NAME
        classified_count = 0
        update_flags = 0

        for detail in crawl_result.get("details", []):
            saved_path = detail.get("saved")
            if not saved_path or detail.get("status") == "unchanged":
                continue

            spath = Path(saved_path)
            if not spath.exists():
                continue

            try:
                with open(spath, "r", encoding="utf-8") as f:
                    content = f.read()
            except Exception:
                continue

            classification = self.classify_policy_doc(
                content, url=detail.get("url", ""),
                page_title=detail.get("title", "")
            )
            results["classify"].append({
                "file": spath.name,
                "url": detail.get("url", ""),
                "policy_type": classification.get("policy_type", ""),
                "doc_number": classification.get("doc_number", ""),
                "publish_date": classification.get("publish_date", ""),
                "issuing_body": classification.get("issuing_body", ""),
                "matched_categories": classification.get("matched_categories", []),
                "confidence": classification.get("confidence", 0),
            })
            classified_count += 1

            page_title = detail.get("title", "")
            if page_title:
                changes = self.detect_policy_changes(page_title, detail.get("url", ""))
                if changes.get("is_update"):
                    results["policy_changes"].append({
                        "file": spath.name,
                        "matched_kps": changes.get("matched_kps", []),
                        "action": changes.get("action", ""),
                        "warning": changes.get("warning", ""),
                    })
                    update_flags += 1

            self._update_crawl_classification(
                detail.get("url", ""), saved_path, classification
            )

        chain_log = {
            "timestamp": datetime.now().strftime('%Y-%m-%d %H:%M:%S'),
            "total_fetched": crawl_result.get("fetched", 0),
            "new_files": crawl_result.get("new", 0),
            "low_quality": crawl_result.get("low_quality", 0),
            "classified": classified_count,
            "policy_updates_flagged": update_flags,
            "errors": crawl_result.get("errors", 0),
        }
        results["chain_summary"] = {
            "status": "completed",
            "pipeline": "crawl->classify->detect->ready",
            "log": chain_log,
            "message": (
                u"管道完成: 爬取{}→分类{}→变化检测{}。"
                u"文件位于{}/,待CEO审核后批准入库。"
            ).format(
                crawl_result.get("fetched", 0),
                classified_count,
                update_flags,
                REVIEW_DIR_NAME,
            ),
        }

        return results

    def _update_crawl_classification(self, url, saved_path, classification):
        """更新crawl_history的notes字段,记录分类元数据。"""
        if not self.db or not url:
            return
        try:
            import json as _json
            conn = self.db.get_connection()
            c = conn.cursor()
            notes = _json.dumps({
                "policy_type": classification.get("policy_type", ""),
                "doc_number": classification.get("doc_number", ""),
                "publish_date": classification.get("publish_date", ""),
                "issuing_body": classification.get("issuing_body", ""),
                "matched_categories": classification.get("matched_categories", []),
                "confidence": classification.get("confidence", 0),
            }, ensure_ascii=False)
            c.execute("""UPDATE crawl_history SET notes=?
                         WHERE url=? AND saved_path=? AND notes=''""",
                      (notes, url, saved_path))
            conn.commit()
            conn.close()
        except Exception:
            pass

    def get_pipeline_report(self):
        """获取管道运行报告: 最近爬取+分类统计+变化检测概览。"""
        report = {"recent_crawls": [], "classification_stats": {}, "policy_updates": []}
        if not self.db:
            return report
        try:
            conn = self.db.get_connection()
            c = conn.cursor()
            c.execute("""SELECT url, status, category, fetched_at, notes
                         FROM crawl_history
                         ORDER BY fetched_at DESC LIMIT 20""")
            for row in c.fetchall():
                entry = {"url": row[0], "status": row[1], "category": row[2],
                         "fetched_at": row[3]}
                if row[4]:
                    try:
                        entry["classification"] = json.loads(row[4])
                    except Exception:
                        pass
                report["recent_crawls"].append(entry)

            c.execute("""SELECT notes FROM crawl_history
                         WHERE notes != '' AND fetched_at >= date('now','-7 days')""")
            type_counts = {}
            cat_counts = {}
            for (notes,) in c.fetchall():
                try:
                    cls = json.loads(notes)
                    pt = cls.get("policy_type", u"未知")
                    type_counts[pt] = type_counts.get(pt, 0) + 1
                    for cat in cls.get("matched_categories", []):
                        cat_counts[cat] = cat_counts.get(cat, 0) + 1
                except Exception:
                    pass
            report["classification_stats"] = {
                "by_policy_type": type_counts,
                "by_category": cat_counts,
                "period": u"最近7天",
            }

            conn.close()
        except Exception:
            pass
        return report
