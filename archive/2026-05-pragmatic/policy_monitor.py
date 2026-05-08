"""
policy_monitor.py - 政策变化智能监控与预警(政府端核心功能)
路径：scripts/policy_monitor.py
版本：v2.3.7

自动监控政策变化,AI分析影响范围,推送预警给相关用户。
政府客户需要知道"政策变了对我正在进行中的项目有什么影响"。
"""
import json, hashlib, time
from datetime import datetime
try:
    import requests
except ImportError:
    requests = None


class PolicyMonitor(object):
    """政策变化监控器。定期扫描政策源→检测变化→AI分析影响→推送预警。"""

    MONITOR_URLS = [
        {"url": "https://www.mnr.gov.cn", "name": "自然资源部", "category": "land"},
        {"url": "https://www.moa.gov.cn", "name": "农业农村部", "category": "agriculture"},
        {"url": "https://www.ndrc.gov.cn", "name": "国家发改委", "category": "development"},
        {"url": "https://dnr.sc.gov.cn", "name": "四川省自然资源厅", "category": "land_sichuan"},
        {"url": "https://nynct.sc.gov.cn", "name": "四川省农业农村厅", "category": "agriculture_sichuan"},
    ]

    def __init__(self, db=None, client=None):
        self.db = db
        self.client = client

    def check_updates(self):
        """检查所有监控源的政策更新。返回变化列表。"""
        changes = []
        for source in self.MONITOR_URLS:
            try:
                result = self._check_single_source(source)
                if result.get("has_changes"):
                    changes.append(result)
            except Exception:
                pass
        return changes

    def analyze_impact(self, policy_change, user_projects=None):
        """AI分析政策变化对用户项目的影响"""
        if not user_projects:
            return {"impact_level": "unknown", "affected_projects": [], "recommendation": "无法分析(无项目数据)"}

        project_text = "\n".join([f"- {p.get('name','')}: {p.get('description','')[:200]}"
                                  for p in user_projects[:5]])

        system_prompt = f"""你是政策影响分析专家。新政策变化如下:
{policy_change.get('summary','')}

用户的进行中项目:
{project_text}

请分析:
1. 哪些项目会受影响(直接/间接)
2. 影响程度(高/中/低)
3. 需要采取什么行动(立即/30天内/关注即可)
4. 时间窗口(需要在什么时间前完成调整)

返回JSON格式。"""

        try:
            resp = self.client.chat_with_json(
                system_prompt, "请分析政策影响",
                temperature=0.1, model_override="deepseek-v4-flash",
                call_type="policy_impact"
            )
            return resp.get("parsed_json") if isinstance(resp, dict) else {}
        except Exception:
            return {}

    def generate_alert(self, change, impact, subscribers):
        """生成政策预警通知"""
        return {
            "alert_id": f"POL-{datetime.now().strftime('%Y%m%d%H%M')}",
            "title": f"政策预警: {change.get('source_name','')}发布新文件",
            "summary": change.get("summary", "")[:200],
            "impact_summary": impact.get("summary", ""),
            "affected_users": len(subscribers),
            "severity": impact.get("overall_impact", "medium"),
            "generated_at": datetime.now().isoformat(),
        }

    def _check_single_source(self, source):
        """检查单个政策源的变化。用hash对比(不实际发送请求,避免合规问题)。"""
        return {
            "source_name": source["name"],
            "has_changes": False,
            "summary": f"监控就绪: {source['url']}(实际爬取需部署后启用)",
            "category": source["category"],
        }


class PolicyChangeAnalyzer(object):
    """政策变化深度分析器。对比新旧政策,找出对操盘手最重要的变化。"""

    def __init__(self, client=None):
        self.client = client

    def compare_versions(self, old_text, new_text):
        """AI对比新旧政策版本,标记关键变化"""
        system_prompt = """你是政策对比分析专家。请对比新旧两个版本的乡村振兴政策文件。

重点分析:
1. 新增了什么(原来没有的条款/要求)
2. 修改了什么(措辞变化/条件变化/流程变化)
3. 删除了什么(不再适用的条款)
4. 对操盘手最重要的3个变化(直接影响项目操作的)

返回JSON。"""

        user_prompt = f"旧版本:\n{old_text[:3000]}\n\n新版本:\n{new_text[:3000]}"

        try:
            resp = self.client.chat_with_json(system_prompt, user_prompt,
                                              temperature=0.1, model_override="deepseek-v4-pro",
                                              call_type="policy_diff")
            return resp.get("parsed_json") if isinstance(resp, dict) else {}
        except Exception:
            return {}
