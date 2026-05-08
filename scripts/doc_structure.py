"""
doc_structure.py - 中国公文结构分析器(发文字号/层级/类型/关键章节)
路径：scripts/doc_structure.py
版本：v2.3.7-part8
参考 GB/T 9704-2012 党政机关公文格式标准
"""
import re
from typing import Dict, List, Optional, Tuple

# ── 发文字号正则（GB/T 9704-2012: 机关代字〔年份〕序号号）──
_DOC_NUM_RE = re.compile(
    r'(?P<agency>[一-鿿a-zA-Z]+?发[一-鿿]{0,12})'
    r'[〔\[]\s*(?P<year>\d{4})\s*[〕\]]\s*'
    r'(?:第)?(?P<seq>\d{1,6})\s*号'
)

# ── 密级检测 ──
_MIJI_RE = re.compile(r'(绝密|机密|秘密)\s*(?:★\s*(\d+)年)?')

# ── 公文标题: X关于Y的Z ──
_TITLE_RE = re.compile(
    r'(?P<issuer>[一-龥]{2,30})关于'
    r'(?P<subject>.+?)的'
    r'(?P<doc_type>[一-龥]{2,6})\s*$'
)

# ── 成文日期 ──
_DATE_RE = re.compile(r'(\d{4})\s*年\s*(\d{1,2})\s*月\s*(\d{1,2})\s*日')

# ── 层级标记（篇/章/节/条/款/项）──
_HIERARCHY_PATTERNS = [
    (re.compile(r'第([一二三四五六七八九十百千]+)篇'), '篇'),
    (re.compile(r'第([一二三四五六七八九十百千]+)章'), '章'),
    (re.compile(r'第([一二三四五六七八九十百千]+)节'), '节'),
    (re.compile(r'第([一二三四五六七八九十百千]+)条'), '条'),
    (re.compile(r'^[（(]([一二三四五六七八九十]+)[）)]'), '款'),
    (re.compile(r'^(\d+)[\.、]'), '项'),
]

# ── 常见公文类型关键词 ──
_DOC_TYPE_PATTERNS = {
    '法律': re.compile(r'第.*条.*款|法律|法(第|\s*\d+\s*号|令)'),
    '行政法规': re.compile(r'中华人民共和国.*条例|国务院令'),
    '部门规章': re.compile(r'(自然资源部|农业农村部|财政部|生态环境部|住建部).*办法|规定'),
    '地方性法规': re.compile(r'(省|自治区|市).*条例|管理办法.*审议通过'),
    '规范性文件': re.compile(r'(意见|通知|方案|规划|指导意见|若干意见)\s*$|关于印发'),
    '通知公告': re.compile(r'^关于.*的通知$|公告$|通告$'),
    '批复': re.compile(r'^关于.*的批复$|^批复'),
    '函': re.compile(r'^关于.*的函$|^.*函$'),
}

# ── 关键章节标题模式 ──
_KEY_SECTION_PATTERNS = {
    '总体要求': re.compile(r'(总体要求|指导思想|基本原则|工作目标|目标任务)'),
    '重点任务': re.compile(r'(重点任务|主要任务|工作任务|重点.*工作|行动措施)'),
    '保障措施': re.compile(r'(保障措施|组织保障|政策保障|资金保障|工作要求)'),
    '组织领导': re.compile(r'(组织领导|责任分工|部门职责|工作机制)'),
    '实施步骤': re.compile(r'(实施步骤|时间安排|进度安排|阶段.*目标)'),
    '监督管理': re.compile(r'(监督管理|考核评估|督查检查|绩效评价)'),
}

# ── 四川地名（从 knowledge_graph.py 同步）──
_SICHUAN_PLACES = [
    '成都', '绵阳', '德阳', '宜宾', '南充', '泸州', '达州', '乐山',
    '凉山', '内江', '自贡', '眉山', '遂宁', '广安', '攀枝花', '广元',
    '资阳', '巴中', '雅安', '阿坝', '甘孜',
]
# ── 全国省级行政区 ──
_PROVINCES = [
    '北京', '天津', '上海', '重庆', '河北', '山西', '辽宁', '吉林',
    '黑龙江', '江苏', '浙江', '安徽', '福建', '江西', '山东', '河南',
    '湖北', '湖南', '广东', '广西', '海南', '四川', '贵州', '云南',
    '西藏', '陕西', '甘肃', '青海', '宁夏', '新疆', '内蒙古',
]

# ── 发文机关常见结尾词 ──
_ISSUER_SUFFIX = re.compile(
    r'[一-龥]{4,40}(?:人民政府|办公厅|办公室|委员会|领导小组|指挥部|局|厅|部|委)$'
)


class ChineseDocAnalyzer:
    """中国公文结构分析器，不依赖AI，纯规则驱动。"""

    @classmethod
    def extract_metadata(cls, text: str) -> Dict:
        """提取公文元数据：发文字号/发文机关/标题/密级/成文日期/主送机关。"""
        if not text or len(text.strip()) < 20:
            return {"is_govt_doc": False}
        result = {"is_govt_doc": False, "document_number": None, "issuing_agency": None,
                  "title": None, "date": None, "security_level": None, "recipient": None}
        # 发文字号
        m = _DOC_NUM_RE.search(text)
        if m:
            result["document_number"] = m.group()
            result["is_govt_doc"] = True
        # 密级
        m = _MIJI_RE.search(text[:500])
        if m:
            result["security_level"] = m.group()
        # 标题
        for line in text.split('\n')[:30]:
            line = line.strip()
            if not line or len(line) < 6 or len(line) > 120:
                continue
            m = _TITLE_RE.match(line)
            if m:
                result["title"] = line
                result["issuing_agency"] = m.group("issuer")
                result["is_govt_doc"] = True
                break
        # 成文日期
        m = _DATE_RE.search(text[-500:] if len(text) > 500 else text)
        if m:
            result["date"] = m.group()
        # 主送机关（标题后的冒号分隔名单）
        result["recipient"] = cls._detect_recipient(text)
        return result

    @classmethod
    def detect_hierarchy(cls, text: str) -> List[Dict]:
        """检测文档层级结构：篇/章/节/条/款/项。模拟MinerU的文档树概念。"""
        if not text:
            return []
        nodes = []
        for i, line in enumerate(text.split('\n'), 1):
            line = line.strip()
            if not line or len(line) > 200:
                continue
            for pat, level in _HIERARCHY_PATTERNS:
                m = pat.match(line)
                if m:
                    nodes.append({"line": i, "level": level, "text": line[:120]})
                    break
        return nodes

    @classmethod
    def classify_doc_type(cls, text: str) -> str:
        """分类公文类型：行政法规/部门规章/规范性文件/通知公告/批复/函/非公文。"""
        if not text or len(text) < 20:
            return '非公文'
        # 从标题行优先推断
        title = cls._get_title_line(text)
        for dtype, pat in _DOC_TYPE_PATTERNS.items():
            if pat.search(title):
                return dtype
        # 全文兜底
        for dtype, pat in _DOC_TYPE_PATTERNS.items():
            if pat.search(text[:2000]):
                return dtype
        return '非公文'

    @classmethod
    def extract_key_sections(cls, text: str) -> Dict[str, str]:
        """提取关键章节起始位置：总体要求/重点任务/保障措施等。"""
        if not text:
            return {}
        sections = {}
        lines = text.split('\n')
        for i, line in enumerate(lines):
            line = line.strip()
            for sec_name, pat in _KEY_SECTION_PATTERNS.items():
                if sec_name not in sections and pat.search(line):
                    sections[sec_name] = {"line": i + 1, "title": line[:100]}
        return sections

    @classmethod
    def score_document_quality(cls, text: str, metadata: Optional[Dict] = None) -> Tuple[int, List[str]]:
        """文档质量评分(0-100)及理由。高分=规范公文，可用于KP提取。"""
        score = 0
        reasons = []
        if not text or len(text.strip()) < 100:
            return 0, ["内容过短(<100字符)"]
        if metadata is None:
            metadata = cls.extract_metadata(text)
        # 发文字号(强信号)
        if metadata.get("document_number"):
            score += 25
            reasons.append("有发文字号 +25")
        # 标题规范
        if metadata.get("title"):
            score += 15
            reasons.append("标题规范(X关于Y的Z) +15")
        # 层级结构
        hierarchy = cls.detect_hierarchy(text)
        if len(hierarchy) >= 3:
            score += min(len(hierarchy), 8) * 2
            reasons.append(f"层级结构({len(hierarchy)}个节点) +{min(len(hierarchy),8)*2}")
        elif len(hierarchy) > 0:
            score += len(hierarchy)
            reasons.append(f"有层级标记({len(hierarchy)}个) +{len(hierarchy)}")
        # 关键章节
        key_sections = cls.extract_key_sections(text)
        if key_sections:
            score += min(len(key_sections), 5) * 3
            reasons.append(f"关键章节({list(key_sections.keys())}) +{min(len(key_sections),5)*3}")
        # 日期
        if metadata.get("date"):
            score += 5
            reasons.append("有日期 +5")
        # 长度
        length = len(text.strip())
        if length > 5000:
            score += 10
            reasons.append("长文本(>5000字) +10")
        elif length > 1000:
            score += 5
            reasons.append("中等长度(>1000字) +5")
        elif length > 300:
            score += 3
            reasons.append("较短(>300字) +3")
        # 政策关键词密度
        kw_count = cls._count_policy_keywords(text)
        if kw_count > 20:
            score += 10
            reasons.append(f"政策关键词密集({kw_count}次) +10")
        elif kw_count > 5:
            score += 5
            reasons.append(f"有政策关键词({kw_count}次) +5")
        return min(score, 100), reasons

    @classmethod
    def detect_region(cls, text: str) -> Optional[str]:
        """检测文档涉及的地域（省份/城市），优先四川。"""
        if not text:
            return None
        # 四川优先
        for city in _SICHUAN_PLACES:
            if city in text[:3000]:
                return f"四川-{city}"
        # 其他省份
        for prov in _PROVINCES:
            if prov in text[:3000]:
                return f"{prov}"
        # 发文字号中的机关代字推断（川=四川）
        m = _DOC_NUM_RE.search(text)
        if m:
            agency = m.group("agency")
            if agency.startswith('川'):
                return '四川'
        return None

    # ── 内部辅助 ──

    @staticmethod
    def _get_title_line(text: str) -> str:
        for line in text.split('\n')[:20]:
            line = line.strip()
            if 6 <= len(line) <= 120:
                return line
        return text[:120]

    @staticmethod
    def _detect_recipient(text: str) -> Optional[str]:
        """检测主送机关：标题下方、冒号收尾的连续组织名。"""
        lines = text.split('\n')
        found_title = False
        for i, line in enumerate(lines[:30]):
            line = line.strip()
            if not line:
                continue
            # 跳过标题行
            if _TITLE_RE.match(line):
                found_title = True
                continue
            if found_title and line.endswith('：') and len(line) < 200:
                # 可能是主送机关
                if re.search(r'(政府|局|厅|部|委|办|院|会|军区|部队|集团|公司)', line):
                    return line.rstrip('：').rstrip(':')
            found_title = True  # 表格类标题之外的第一个实义行也可能是主送
        return None

    @staticmethod
    def _count_policy_keywords(text: str) -> int:
        """统计政策相关关键词出现次数(乡村振兴领域)。"""
        keywords = [
            '乡村振兴', '农业农村', '耕地保护', '生态修复', '高标准农田',
            '建设用地', '宅基地', '土地整治', '增减挂钩', '占补平衡',
            '林盘', '人居环境', '乡村产业', '集体经济', '国土空间',
            '村庄规划', '碳汇', '可持续发展', '新型城镇化', '城乡融合',
            '确权登记', '经营权', '承包地', '永久基本农田', '非农化',
            '非粮化', '三区三线', '项目申报', '资金筹措', 'EPC',
            '招标投标', '竣工验收', '指标交易', '收益分配', '管护',
        ]
        count = 0
        for kw in keywords:
            count += text.count(kw)
        return count
