"""
source_verifier.py - 信源核验器(所有非老唐提供的信息必须能找到官方出处)
路径：agents/source_verifier.py
版本：v2.3.7-part2

铁律: 除老唐主动喂入的内容外, 所有KP入库前必须通过信源核验。
- .gov.cn 域名 → 自动通过
- 其他域名 → 标记为待核验, 禁止进入confirmed状态
- 老唐喂入(doc_origin='laotang_experience') → 豁免核验
"""
import re
from pathlib import Path

PROJECT_ROOT = Path(__file__).parent.parent

# ================================================================
# 信源白名单(四川全省 .gov.cn + 中央级聚合平台)
# ================================================================
SICHUAN_GOV_DOMAINS = [
    # 省级
    "sc.gov.cn", "dnr.sc.gov.cn", "nynct.sc.gov.cn",
    "fgw.sc.gov.cn", "czt.sc.gov.cn", "sthjt.sc.gov.cn",
    "zfcxjs.sc.gov.cn", "jtyst.sc.gov.cn", "swt.sc.gov.cn",
    "wlt.sc.gov.cn", "wsjkw.sc.gov.cn", "mzt.sc.gov.cn",
    # 21市州
    "chengdu.gov.cn", "zigong.gov.cn", "panzhihua.gov.cn",
    "luzhou.gov.cn", "deyang.gov.cn", "mianyang.gov.cn",
    "guangyuan.gov.cn", "suining.gov.cn", "neijiang.gov.cn",
    "leshan.gov.cn", "nanchong.gov.cn", "yibin.gov.cn",
    "guangan.gov.cn", "dazhou.gov.cn", "bazhong.gov.cn",
    "yaan.gov.cn", "ms.gov.cn", "ziyang.gov.cn",
    "abazhou.gov.cn", "ganzi.gov.cn", "liangshan.gov.cn",
    # 四川省公共资源交易/采购平台
    "scggzy.gov.cn", "ccgp-sichuan.gov.cn",
    "ggzyjy.sc.gov.cn", "ggzyjy.chengdu.gov.cn",
]
NATIONAL_GOV_DOMAINS = [
    "www.gov.cn", "mnr.gov.cn", "ndrc.gov.cn",
    "mof.gov.cn", "mohurd.gov.cn", "mee.gov.cn",
    "mwr.gov.cn", "mfa.gov.cn", "mofcom.gov.cn",
    "stats.gov.cn", "samr.gov.cn", "nlc.gov.cn",
    "ndrclaw.gov.cn", "pkulaw.gov.cn",
]
OFFICIAL_MEDIA = [
    "xinhuanet.com", "people.com.cn", "cctv.com",
    "chinanews.com", "sc.xinhuanet.com", "sc.people.com.cn",
    "sichuan.scol.com.cn", "scdaily.cn",
]


class SourceVerifier(object):
    """信源核验器。验证知识来源是否可追溯到官方出处。"""

    def __init__(self, db=None):
        self.db = db
        self._gov_pattern = re.compile(r'\.gov\.cn$|\.gov\.cn/')

    def seed_whitelist(self):
        """初始化信源白名单(幂等)。"""
        if not self.db:
            return {"error": "db未连接"}
        domains = []
        for d in SICHUAN_GOV_DOMAINS:
            domains.append((d, "government", "四川省政府部门"))
        for d in NATIONAL_GOV_DOMAINS:
            domains.append((d, "government", "中央政府部门"))
        for d in OFFICIAL_MEDIA:
            domains.append((d, "official_media", "官方媒体"))
        count = 0
        try:
            conn = self.db.get_connection(); c = conn.cursor()
            for domain, cat, desc in domains:
                c.execute("""INSERT OR IGNORE INTO source_whitelist (domain, category, description)
                             VALUES (?,?,?)""", (domain, cat, desc))
                if c.rowcount > 0:
                    count += 1
            conn.commit(); conn.close()
        except Exception:
            pass
        return {"seeded": count, "total_domains": len(domains)}

    def verify(self, source_url, doc_origin=""):
        """核验单个URL。返回 {ok, reason, domain_category}。
        doc_origin='laotang_experience' → 豁免核验。
        """
        if doc_origin == "laotang_experience":
            return {"ok": True, "reason": "老唐本人提供,豁免核验", "domain_category": "laotang"}

        if not source_url:
            return {"ok": False, "reason": "无来源URL", "domain_category": "unknown"}

        # 快速路径: .gov.cn 自动通过
        if self._gov_pattern.search(source_url):
            return {"ok": True, "reason": ".gov.cn官方域名", "domain_category": "government"}

        # 数据库白名单查证
        domain = self._extract_domain(source_url)
        if self.db and domain:
            try:
                conn = self.db.get_connection(); c = conn.cursor()
                c.execute("""SELECT category FROM source_whitelist
                             WHERE domain=? AND is_active=1""", (domain,))
                row = c.fetchone(); conn.close()
                if row:
                    return {"ok": True, "reason": f"白名单({row[0]})", "domain_category": row[0]}
            except Exception:
                pass

        return {"ok": False, "reason": f"域名不在白名单: {domain}", "domain_category": "unverified"}

    def verify_batch(self, kps, doc_origin=""):
        """批量核验KP列表。返回 {pass_count, fail_count, results}。"""
        results = []
        ok_count = 0
        for kp in kps:
            url = kp.get("source_url", "") if isinstance(kp, dict) else ""
            r = self.verify(url, doc_origin=doc_origin)
            results.append(r)
            if r["ok"]:
                ok_count += 1
        return {"pass_count": ok_count, "fail_count": len(results) - ok_count,
                "results": results}

    def _extract_domain(self, url):
        """从URL提取域名。"""
        m = re.search(r'https?://([^/]+)', url)
        if m:
            return m.group(1)
        return url.split("/")[0] if "/" in url else url

    def get_whitelist_status(self):
        """查询白名单状态。"""
        if not self.db:
            return {"total": 0, "active": 0}
        try:
            conn = self.db.get_connection(); c = conn.cursor()
            c.execute("SELECT COUNT(*) FROM source_whitelist")
            total = c.fetchone()[0]
            c.execute("SELECT COUNT(*) FROM source_whitelist WHERE is_active=1")
            active = c.fetchone()[0]
            conn.close()
            return {"total": total, "active": active}
        except Exception:
            return {"total": 0, "active": 0}

    # ================================================================
    # 四川21市州区划
    # ================================================================
    SICHUAN_PREFECTURES = {
        "成都": "chengdu", "自贡": "zigong", "攀枝花": "panzhihua",
        "泸州": "luzhou", "德阳": "deyang", "绵阳": "mianyang",
        "广元": "guangyuan", "遂宁": "suining", "内江": "neijiang",
        "乐山": "leshan", "南充": "nanchong", "宜宾": "yibin",
        "广安": "guangan", "达州": "dazhou", "巴中": "bazhong",
        "雅安": "yaan", "眉山": "meishan", "资阳": "ziyang",
        "阿坝": "aba", "甘孜": "ganzi", "凉山": "liangshan",
    }

    def detect_prefecture(self, text, filename=""):
        """从文本中检测涉及的四川市州。返回市州名列表。"""
        found = []
        source = text + " " + filename
        for name_en, name_cn in [(v, k) for k, v in self.SICHUAN_PREFECTURES.items()]:
            pass
        for name_cn in self.SICHUAN_PREFECTURES:
            if name_cn in source:
                found.append(name_cn)
        # 简称匹配
        shortcuts = {"蓉": "成都", "绵": "绵阳", "宜": "宜宾", "泸": "泸州",
                     "德": "德阳", "南": "南充", "达": "达州", "乐": "乐山"}
        for short, full in shortcuts.items():
            if short in source and full not in found:
                found.append(full)
        return found[:5]
