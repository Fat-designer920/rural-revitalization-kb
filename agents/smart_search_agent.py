"""
smart_search_agent.py - AI驱动智能搜索Agent(聚合平台搜索+信源验证+自动入库)
路径：agents/smart_search_agent.py
版本：v2.3.7-part2

职责: 从课程体系知识缺口倒推搜索词→在政府聚合平台搜索→验证信源→提取入库。
区县级政策大多没有独立网站, 聚合平台(省政府/市州政府/公共资源交易平台)是主要来源。
"""

import re
import time
from datetime import datetime
from pathlib import Path

PROJECT_ROOT = Path(__file__).parent.parent

# ================================================================
# 四川全省聚合平台搜索入口(区县级政策的真实来源)
# ================================================================
SEARCH_TARGETS = [
    # 省级聚合平台
    {
        "name": "四川省政府信息公开",
        "search_url": "https://www.sc.gov.cn/search/",
        "pattern": "sc.gov.cn",
        "category": "policy",
    },
    {
        "name": "四川省自然资源厅政策文件",
        "search_url": "https://dnr.sc.gov.cn/search/",
        "pattern": "dnr.sc.gov.cn",
        "category": "policy",
    },
    {
        "name": "四川省农业农村厅",
        "search_url": "https://nynct.sc.gov.cn/search/",
        "pattern": "nynct.sc.gov.cn",
        "category": "policy",
    },
    {
        "name": "四川省发改委",
        "search_url": "https://fgw.sc.gov.cn/search/",
        "pattern": "fgw.sc.gov.cn",
        "category": "policy",
    },
    {
        "name": "四川省财政厅",
        "search_url": "https://czt.sc.gov.cn/search/",
        "pattern": "czt.sc.gov.cn",
        "category": "policy",
    },
    {
        "name": "四川省公共资源交易平台",
        "search_url": "https://ggzyjy.sc.gov.cn/",
        "pattern": "ggzyjy.sc.gov.cn",
        "category": "project",
    },
    {
        "name": "中国政府采购网四川分站",
        "search_url": "https://www.ccgp-sichuan.gov.cn/",
        "pattern": "ccgp-sichuan.gov.cn",
        "category": "project",
    },
    # 重点市州聚合门户(含区县信息)
    {
        "name": "成都市政府信息公开",
        "search_url": "https://www.chengdu.gov.cn/search/",
        "pattern": "chengdu.gov.cn",
        "category": "policy",
    },
    {
        "name": "绵阳市政府",
        "search_url": "https://www.mianyang.gov.cn/search/",
        "pattern": "mianyang.gov.cn",
        "category": "policy",
    },
    {
        "name": "宜宾市政府",
        "search_url": "https://www.yibin.gov.cn/search/",
        "pattern": "yibin.gov.cn",
        "category": "policy",
    },
    {
        "name": "德阳市政府",
        "search_url": "https://www.deyang.gov.cn/search/",
        "pattern": "deyang.gov.cn",
        "category": "policy",
    },
    {
        "name": "南充市政府",
        "search_url": "https://www.nanchong.gov.cn/search/",
        "pattern": "nanchong.gov.cn",
        "category": "policy",
    },
    {
        "name": "泸州市政府",
        "search_url": "https://www.luzhou.gov.cn/search/",
        "pattern": "luzhou.gov.cn",
        "category": "policy",
    },
    {
        "name": "自贡市政府",
        "search_url": "https://www.zigong.gov.cn/search/",
        "pattern": "zigong.gov.cn",
        "category": "policy",
    },
    {
        "name": "乐山市政府",
        "search_url": "https://www.leshan.gov.cn/search/",
        "pattern": "leshan.gov.cn",
        "category": "policy",
    },
    {
        "name": "达州市政府",
        "search_url": "https://www.dazhou.gov.cn/search/",
        "pattern": "dazhou.gov.cn",
        "category": "policy",
    },
    {
        "name": "广安市政府",
        "search_url": "https://www.guangan.gov.cn/search/",
        "pattern": "guangan.gov.cn",
        "category": "policy",
    },
    {
        "name": "眉山市政府",
        "search_url": "https://www.ms.gov.cn/search/",
        "pattern": "ms.gov.cn",
        "category": "policy",
    },
    {
        "name": "遂宁市政府",
        "search_url": "https://www.suining.gov.cn/search/",
        "pattern": "suining.gov.cn",
        "category": "policy",
    },
    {
        "name": "内江市政府",
        "search_url": "https://www.neijiang.gov.cn/search/",
        "pattern": "neijiang.gov.cn",
        "category": "policy",
    },
]

# 中央级聚合平台(含全国区县政策)
NATIONAL_AGGREGATORS = [
    {
        "name": "自然资源部政策法规库",
        "search_url": "https://www.mnr.gov.cn/search/",
        "pattern": "mnr.gov.cn",
        "category": "policy",
    },
    {
        "name": "中国政府网政策库",
        "search_url": "https://www.gov.cn/search/",
        "pattern": "www.gov.cn",
        "category": "policy",
    },
    {
        "name": "全国公共资源交易平台",
        "search_url": "https://www.ggzy.gov.cn/",
        "pattern": "ggzy.gov.cn",
        "category": "project",
    },
]


class SmartSearchAgent(object):
    """AI驱动智能搜索Agent。从知识缺口→搜索→验证→入库。"""

    def __init__(self, db=None, client=None, progress_callback=None):
        self.db = db
        self.client = client
        self.progress_callback = progress_callback
        self._cancel = False

    # ================================================================
    # 主入口: 从课程需求出发搜索
    # ================================================================
    def search_by_knowledge_needs(self, needs_list, max_per_need=3):
        """根据知识需求列表搜索。needs_list=[{knowledge, lesson_count, priority}, ...]
        返回 {total_searches, urls_found, urls_verified, content_saved}
        """
        results = {
            "total_searches": 0,
            "urls_found": 0,
            "urls_verified": 0,
            "content_saved": 0,
            "details": [],
        }

        for need in needs_list[:20]:  # 每轮最多处理20个需求
            knowledge = need.get("knowledge", need) if isinstance(need, dict) else need
            priority = need.get("priority", "P2") if isinstance(need, dict) else "P2"

            # 生成搜索查询
            queries = self._generate_queries(knowledge)
            need_result = {"knowledge": knowledge, "queries": queries, "found": []}

            for query in queries[:2]:  # 每个需求最多2个查询变体
                if self._cancel:
                    break
                urls = self._search_targets(query, max_results=3)
                results["total_searches"] += 1
                for url_info in urls:
                    verified = self._verify_and_save(url_info, knowledge, query)
                    if verified.get("ok"):
                        results["urls_verified"] += 1
                        results["content_saved"] += 1
                        need_result["found"].append(url_info["url"])
                    results["urls_found"] += 1
                time.sleep(1)  # 限速

            results["details"].append(need_result)
            self._emit_progress(
                "search",
                len(results["details"]),
                len(needs_list),
                f"已搜索: {knowledge[:40]}... 找到{len(need_result['found'])}个",
            )

        return results

    # ================================================================
    # 搜索查询生成(AI驱动)
    # ================================================================
    def _generate_queries(self, knowledge):
        """从知识需求生成搜索查询。使用规则+AI混合。"""
        queries = []
        # 规则: 加四川/政策/文件/通知等后缀
        suffixes = [" 政策 文件", " 通知 意见", " site:gov.cn", " 四川 实施方案"]
        for suffix in suffixes[:2]:
            q = knowledge + suffix
            if len(q) <= 100:
                queries.append(q)
        # 规则: 加市州前缀
        for pref in ["四川省", "成都市"]:
            q = pref + " " + knowledge
            if len(q) <= 100 and q not in queries:
                queries.append(q)
        return queries[:3]

    # ================================================================
    # 搜索执行
    # ================================================================
    def _search_targets(self, query, max_results=3):
        """在聚合平台搜索。当前使用直接URL构造+爬取。"""
        found = []
        import requests as req

        # 策略: 构造目标平台的搜索URL, 抓取搜索结果页面
        for target in SEARCH_TARGETS[:10]:  # 每轮最多10个平台
            if len(found) >= max_results:
                break
            try:
                search_url = target["search_url"]
                # 尝试带查询参数的搜索
                resp = req.get(
                    search_url,
                    params={"q": query, "keyword": query},
                    timeout=15,
                    headers={"User-Agent": "RuralKB-SmartSearch/2.3.7"},
                )
                if resp.status_code == 200:
                    content = resp.text
                    # 提取搜索结果中的.gov.cn链接
                    gov_urls = set(
                        re.findall(
                            r'https?://[a-zA-Z0-9.-]+\.gov\.cn[^\s"\'<>]*', content
                        )
                    )
                    for url in list(gov_urls)[:max_results]:
                        if url not in [f["url"] for f in found]:
                            found.append(
                                {
                                    "url": url,
                                    "platform": target["name"],
                                    "query": query,
                                    "category": target["category"],
                                }
                            )
            except Exception:
                continue
            time.sleep(0.5)  # 限速

        return found[:max_results]

    # ================================================================
    # 验证+保存
    # ================================================================
    def _verify_and_save(self, url_info, knowledge, query):
        """验证URL信源并保存到pending/。"""
        from agents.source_verifier import SourceVerifier

        sv = SourceVerifier(db=self.db)

        # 信源验证
        verification = sv.verify(url_info["url"])
        if not verification["ok"]:
            return {"ok": False, "reason": verification["reason"]}

        # 抓取内容页
        import requests as req

        try:
            resp = req.get(
                url_info["url"], timeout=30, headers={"User-Agent": "RuralKB/2.3.7"}
            )
            if resp.status_code != 200:
                return {"ok": False, "reason": f"HTTP {resp.status_code}"}
            html = resp.text
        except Exception as e:
            return {"ok": False, "reason": str(e)[:100]}

        # 提取正文(复用crawler的逻辑)
        text = self._extract_text(html, url_info["url"])

        # 保存到pending/
        safe_name = re.sub(
            r'[<>:"|?*]', "_", url_info["url"].split("/")[-1] or "search_result"
        )[:50]
        fname = f"search_{safe_name}_{datetime.now().strftime('%Y%m%d_%H%M%S')}.txt"
        pending_dir = PROJECT_ROOT / "data" / "pending"
        pending_dir.mkdir(parents=True, exist_ok=True)
        save_path = pending_dir / fname
        header = (
            f"来源URL: {url_info['url']}\n搜索平台: {url_info['platform']}\n"
            f"知识需求: {knowledge}\n搜索查询: {query}\n"
            f"抓取时间: {datetime.now().isoformat()}\n"
            f"信源验证: {verification['reason']}\n\n"
        )
        with open(save_path, "w", encoding="utf-8") as f:
            f.write(header + text[:80000])

        return {"ok": True, "saved_path": str(save_path), "source_url": url_info["url"]}

    def _extract_text(self, html, url=""):
        """HTML→正文提取(同crawler逻辑)。"""
        if not html:
            return ""
        text = re.sub(
            r"<script[^>]*>.*?</script>", " ", html, flags=re.DOTALL | re.IGNORECASE
        )
        text = re.sub(
            r"<style[^>]*>.*?</style>", " ", text, flags=re.DOTALL | re.IGNORECASE
        )
        text = re.sub(
            r"<head[^>]*>.*?</head>", " ", text, flags=re.DOTALL | re.IGNORECASE
        )
        text = re.sub(r"<[^>]+>", " ", text)
        text = re.sub(r"&[a-z]+;", " ", text)
        text = re.sub(r"&#\d+;", " ", text)
        text = re.sub(r"\s+", " ", text).strip()
        lines = [l.strip() for l in text.split("。") if len(l.strip()) > 15]
        return "。\n".join(lines)

    def cancel(self):
        self._cancel = True

    def _emit_progress(self, stage, current, total, message):
        if self.progress_callback:
            try:
                self.progress_callback(
                    {
                        "stage": stage,
                        "current": current,
                        "total": total,
                        "message": str(message)[:300],
                    }
                )
            except Exception:
                pass

    def to_dict(self):
        return {
            "agent_code": "smart_search_agent",
            "agent_name": "智能搜索Agent",
            "agent_type": "role",
            "identity_text": "我是智能搜索Agent。从知识缺口倒推搜索词,在政府聚合平台搜索,验证.gov.cn信源,自动入库。区县级政策通过市州政府门户的聚合功能获取。",
        }
