"""
content_extractor.py - 政府网站正文智能提取+元数据识别
路径：scripts/content_extractor.py
版本：v2.3.8
"""
import re

# gov.cn常见正文容器class/id模式
GOV_CONTENT_PATTERNS = [
    r'<div[^>]*(?:class|id)\s*=\s*["\'][^"\']*?(?:TRS_Editor|UCAP-CONTENT|pages_content|con_main'
    r'|xxgk_content|zwgk_content|zhengce_content|info_content|detail_content'
    r'|NewsContent|ArticleContent|MainContent|Content|article_content'
    r'|zoom|text_content|body_content|content_body)[^"\']*["\'][^>]*>(.*?)</div>',
    r'<article[^>]*>(.*?)</article>',
    r'<main[^>]*>(.*?)</main>',
    r'<td[^>]*(?:class|id)\s*=\s*["\'][^"\']*?(?:content|article|main)[^"\']*["\'][^>]*>(.*?)</td>',
]

# 四川乡村振兴12领域核心白名单(必须命中≥3个词才合格)
RURAL_CORE_KEYWORDS = [
    '土地','耕地','用地','基本农田','农田','指标','占补','增减挂钩',
    '空间规划','国土','生态修复','复垦','整理','开发','保护',
    '农村','农业','农民','乡村','产业','畜牧','水产','种植','养殖',
    '高标准农田','补贴','补助','人居环境','厕所革命','垃圾治理','污水',
    '水利','灌区','防洪','供水','饮水','河湖','水域','水土保持',
    '村庄','农房','危房','传统村落','建设','规划','安置','搬迁',
    '公路','道路','交通','物流','运输','快递','客运',
    '项目','投资','资金','专项债','债券','融资','PPP','社会资本',
    '财政','税收','转移支付','以工代赈','绩效','预算',
    '旅游','民宿','农家乐','非遗','文化','遗产','传统','红色',
    '林权','林下','碳汇','造林','草原','湿地','退耕','还林',
    '振兴','脱贫','巩固','帮扶','攻坚','贫困','和美','宜居',
    '田园','川西','林盘','大院','古村','古镇','示范','试点',
    '整治','实施方案','管理办法','意见','通知','规定','标准',
]

# 政策类型检测
POLICY_TYPE_PATTERNS = [
    ("法律", [r"中华人民共和国\w+法", r"主席令\s*第\s*\d+号", r"全国人民代表大会"]),
    ("行政法规", [r"国务院令\s*第\s*\d+号", r"中华人民共和国\w+条例"]),
    ("部门规章", [r"(自然资源部|农业农村部|财政部|国家发展改革委|住房和城乡建设部|生态环境部|水利部)\s*令", r"部令\s*第\s*\d+号"]),
    ("地方性法规", [r"四川省\w+条例", r"四川省人民代表大会常务委员会"]),
    ("规范性文件", [r"关于印发[\w\s]+的通知", r"实施意见", r"指导意见", r"实施办法", r"暂行办法", r"若干措施"]),
    ("通知公告", [r"关于\w+的通知\s*$", r"公告", r"公示", r"通告"]),
]

# 发文字号 regex
DOC_NUMBER_RE = re.compile(
    r'([一-鿿]+发|[一-鿿]+办发|[一-鿿]+函|[一-鿿]+规'
    r'|[一-鿿]+字|[一-鿿]+令)'
    r'[〈《\[\(【〔]?(\d{4})[〉》\]\)】〕]?\s*(\d+)\s*号'
)

DATE_PATTERNS = [
    re.compile(r'(\d{4})\s*年\s*(\d{1,2})\s*月\s*(\d{1,2})\s*日'),
    re.compile(r'(\d{4})[-/](\d{1,2})[-/](\d{1,2})'),
]

ISSUING_BODY_RE = re.compile(
    r'(国务院|四川省人民政府|四川省自然资源厅|四川省农业农村厅|四川省财政厅'
    r'|四川省发展和改革委员会|四川省住房和城乡建设厅|自然资源部|农业农村部'
    r'|财政部|国家发展和改革委员会|成都市人民政府|成都市规划和自然资源局'
    r'|四川省生态环境厅|生态环境部|四川省水利厅|水利部'
    r'|四川省乡村振兴局|国家乡村振兴局)'
)

# 无关内容排除关键词(采矿业/人事/党建/招标/信访等与乡村振兴无关)
EXCLUDE_KEYWORDS = [
    '采矿权','探矿权','勘查方案','矿产资源','煤矿','铁矿','铜矿','铝土矿',
    '人事任免','干部任命','同志职务','任职决定','免去','任前公示','换届选举',
    '党建','党课','主题党日','民主生活会','组织生活会','中心组学习',
    '招标公告','中标公示','采购公告','询价公告','竞争性磋商','流标',
    '信访','上访','举报','投诉处理','行政复议',
    '疫情防控','核酸检测','疫苗接种','健康码',
    '资质认定','资质审批','执业资格','注册考试',
    '会计','审计','税务','税法','汇率','利率',
]


class GovContentExtractor(object):
    """政府网站正文智能提取器。识别正文区→提取文本→元数据→质量评分。"""

    def __init__(self):
        self._session = None

    def extract(self, html, url="", page_title=""):
        """从政府网页HTML中提取正文+元数据。
        返回: {text, char_count, chinese_count, metadata, quality, reason}
        """
        if not html:
            return self._empty_result("无内容")

        # 1. 去噪音标签
        cleaned = self._strip_noise_tags(html)

        # 2. 定位正文区
        content_area = self._locate_content_area(cleaned)
        if not content_area:
            content_area = cleaned

        # 3. 提取纯文本
        text = self._html_to_text(content_area)

        # 4. 清理空行
        text = self._clean_lines(text)

        # 5. 提取元数据
        metadata = self._extract_metadata(text, page_title, url)

        # 6. 质量评估
        char_count = len(text)
        chinese_count = len(re.findall(r'[一-鿿]', text))
        quality, reason = self._assess_quality(text, char_count, chinese_count, url)

        return {
            "text": text,
            "char_count": char_count,
            "chinese_count": chinese_count,
            "metadata": metadata,
            "quality": quality,
            "reason": reason,
        }

    def _strip_noise_tags(self, html):
        """去除噪音标签: script/style/nav/footer/header/aside/form等"""
        noise_tags = ['script', 'style', 'head', 'nav', 'footer', 'header', 'aside',
                      'noscript', 'iframe', 'svg', 'form', 'select', 'button',
                      'input', 'textarea', 'link', 'meta', 'base', 'map', 'canvas',
                      'video', 'audio', 'source', 'track', 'embed', 'object']
        for tag in noise_tags:
            html = re.sub(rf'<{tag}[^>]*>.*?</{tag}>', ' ', html,
                         flags=re.DOTALL | re.IGNORECASE)
            html = re.sub(rf'<{tag}[^>]*/?>', ' ', html, flags=re.IGNORECASE)
        html = re.sub(r'<!--.*?-->', ' ', html, flags=re.DOTALL)
        return html

    def _locate_content_area(self, html):
        """定位正文容器。返回匹配到的HTML片段或空字符串。"""
        for pat in GOV_CONTENT_PATTERNS:
            m = re.search(pat, html, re.IGNORECASE | re.DOTALL)
            if m:
                content = m.group(1)
                # 正文容器至少200字符才算有效
                text_len = len(re.sub(r'<[^>]+>', '', content).strip())
                if text_len >= 200:
                    return content
        return ""

    def _html_to_text(self, html):
        """HTML标签→纯文本。保留换行结构。"""
        text = html
        # 块级元素换行
        for tag in ['p', 'div', 'li', 'tr', 'h1', 'h2', 'h3', 'h4', 'h5', 'h6',
                     'br', 'hr', 'section', 'article']:
            text = re.sub(rf'<{tag}[^>]*>', '\n', text, flags=re.IGNORECASE)
            text = re.sub(rf'</{tag}>', '\n', text, flags=re.IGNORECASE)
        # 去掉所有HTML标签
        text = re.sub(r'<[^>]+>', ' ', text)
        # 解码HTML实体
        text = text.replace('&nbsp;', ' ').replace('&lt;', '<').replace('&gt;', '>')
        text = text.replace('&amp;', '&').replace('&quot;', '"').replace('&apos;', "'")
        text = re.sub(r'&[a-z]+;', ' ', text)
        text = re.sub(r'&#\d+;', ' ', text)
        # 去掉URL
        text = re.sub(r'https?://\S+', ' ', text)
        return text

    def _clean_lines(self, text):
        """按行清理: 去空白行、去纯标点行、去短导航行"""
        lines = []
        for line in text.split('\n'):
            stripped = line.strip()
            if not stripped:
                continue
            # 跳过纯数字/符号行(导航/页码)
            if re.match(r'^[\s\d\-\.,;:|\/\\]+$', stripped):
                continue
            # 跳过太短的行(非中文)
            if len(stripped) < 8:
                continue
            chinese_chars = len(re.findall(r'[一-鿿]', stripped))
            if chinese_chars >= 5 or (len(stripped) > 30 and chinese_chars > 0):
                lines.append(stripped)
        text = '\n'.join(lines)
        text = re.sub(r'\n{3,}', '\n\n', text)
        return text.strip()

    def _extract_metadata(self, text, page_title, url):
        """提取政策文档元数据: 发文字号/发布日期/发文机关/生效日期"""
        metadata = {}
        combined = (page_title + " " + text[:5000]).replace("\n", " ")

        # 发文字号
        doc_match = DOC_NUMBER_RE.search(combined)
        if doc_match:
            metadata["doc_number"] = doc_match.group(0)

        # 发布日期
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

        # 发文机关
        body_matches = ISSUING_BODY_RE.findall(combined)
        if body_matches:
            seen = set()
            bodies = []
            for b in body_matches:
                if b not in seen:
                    seen.add(b)
                    bodies.append(b)
            metadata["issuing_body"] = "、".join(bodies[:3])

        # 生效日期
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

    def _assess_quality(self, text, char_count, chinese_count, url):
        """四级质量评估。返回 (quality, reason)"""
        # Level 0: 乱码
        if char_count > 0 and chinese_count / char_count < 0.05:
            return "garbled", f"中文字符仅{chinese_count}个({chinese_count/char_count*100:.1f}%)<5%"

        # Level 1: 排除关键词(采矿/人事/党建/招标/信访等)
        for kw in EXCLUDE_KEYWORDS:
            if kw in text[:2000]:
                return "excluded", f"含排除关键词'{kw}',与乡村振兴无关"

        # Level 2: 正文长度
        if char_count < 500:
            return "low_quality", f"正文仅{char_count}字,低于500字门槛"

        # Level 3: 乡村振兴相关性
        rural_count = sum(1 for kw in RURAL_CORE_KEYWORDS if kw in text)
        if rural_count < 3:
            return "irrelevant", f"乡村振兴相关度不足(仅{rural_count}个核心词,需>=3)"

        return "good", f"正文{char_count}字,中文{chinese_count}字,核心词{rural_count}个,合格"

    def classify_policy(self, text, page_title=""):
        """识别政策文档类型。返回 {policy_type, confidence}"""
        combined = (page_title + " " + text[:3000]).replace("\n", " ")
        for ptype, patterns in POLICY_TYPE_PATTERNS:
            matches = sum(1 for pat in patterns if re.search(pat, combined))
            if matches >= 2:
                return {"policy_type": ptype, "confidence": 0.8}
            elif matches == 1:
                return {"policy_type": ptype, "confidence": 0.5}
        return {"policy_type": "通知公告", "confidence": 0.2}

    def _empty_result(self, reason):
        return {"text": "", "char_count": 0, "chinese_count": 0,
                "metadata": {}, "quality": "empty", "reason": reason}


def check_robots_txt(domain):
    """检查域名是否允许爬取。返回 (allowed, crawl_delay)。
    根据《网络数据安全管理条例》(2025.1.1)和robots协议。
    """
    try:
        import requests
        robots_url = f"https://{domain}/robots.txt"
        resp = requests.get(robots_url, timeout=10, headers={
            "User-Agent": "RuralRevitalizationKB/2.3.8"
        })
        if resp.status_code != 200:
            return True, 5  # 无robots.txt,默认允许但保守延迟5秒

        content = resp.text
        # 解析 Crawl-Delay
        delay_match = re.search(r'Crawl-Delay[:\s]+(\d+)', content)
        crawl_delay = int(delay_match.group(1)) if delay_match else 5

        # 检查是否被禁止
        agent_section = False
        disallowed = False
        for line in content.split('\n'):
            line = line.strip()
            if line.lower().startswith('user-agent:'):
                agent = line.split(':', 1)[1].strip()
                agent_section = (agent == '*' or 'RuralRevitalizationKB' in agent)
            elif agent_section and line.lower().startswith('disallow:'):
                path = line.split(':', 1)[1].strip()
                if path == '/' or path == '':
                    disallowed = True
                    break

        return not disallowed, max(crawl_delay, 3)
    except Exception:
        return True, 5  # 无法检查,保守允许但长延迟
