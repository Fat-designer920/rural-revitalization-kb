"""
tier_manager.py - 会员等级与功能权限管理(五档定价后端)
路径：scripts/tier_manager.py
版本：v2.3.7

支持五档会员: basic(¥19.9)/pro(¥99)/expert(¥199)/team(¥999)/gov(¥20K/年)
按等级控制: 问答次数、领域数量、功能开关、API配额
"""
import json
from datetime import datetime, timedelta


class TierManager(object):
    """会员等级管理器。定义五档的权限和限制。"""

    TIERS = {
        "basic": {
            "name": "基础版",
            "price_monthly": 19.9,
            "qa_limit_monthly": 50,       # 每月50次问答
            "domain_count": 1,             # 1个业务领域
            "features": ["qa", "policy_lookup", "daily_lesson"],
            "report_limit_monthly": 0,     # 无合规报告
            "api_access": False,
            "offline_access": False,
            "priority_support": False,
        },
        "pro": {
            "name": "专业版",
            "price_monthly": 99,
            "qa_limit_monthly": 500,
            "domain_count": 5,
            "features": ["qa", "policy_lookup", "daily_lesson", "policy_compare",
                        "case_library", "compliance_self_check"],
            "report_limit_monthly": 3,
            "api_access": False,
            "offline_access": False,
            "priority_support": False,
        },
        "expert": {
            "name": "专家版",
            "price_monthly": 199,
            "qa_limit_monthly": -1,        # 无限
            "domain_count": 15,
            "features": ["qa", "policy_lookup", "daily_lesson", "policy_compare",
                        "case_library", "compliance_self_check", "compliance_report",
                        "metric_calculator", "policy_alert", "peer_benchmark"],
            "report_limit_monthly": 20,
            "api_access": True,
            "offline_access": True,
            "priority_support": False,
        },
        "team": {
            "name": "团队版",
            "price_monthly": 999,
            "qa_limit_monthly": -1,
            "domain_count": 15,
            "seat_count": 5,
            "features": ["qa", "policy_lookup", "daily_lesson", "policy_compare",
                        "case_library", "compliance_self_check", "compliance_report",
                        "metric_calculator", "policy_alert", "peer_benchmark",
                        "team_collab", "project_mgmt", "custom_kb"],
            "report_limit_monthly": 100,
            "api_access": True,
            "offline_access": True,
            "priority_support": True,
        },
        "gov": {
            "name": "县级政府版",
            "price_yearly": 20000,
            "qa_limit_monthly": -1,
            "domain_count": 15,
            "seat_count": 10,
            "features": ["qa", "policy_lookup", "daily_lesson", "policy_compare",
                        "case_library", "compliance_self_check", "compliance_report",
                        "metric_calculator", "policy_alert", "peer_benchmark",
                        "team_collab", "project_mgmt", "custom_kb",
                        "offline_pack", "training_included", "dedicated_support"],
            "report_limit_monthly": -1,
            "api_access": True,
            "offline_access": True,
            "priority_support": True,
            "dedicated_support": True,
            "training_sessions_yearly": 2,
        },
    }

    def __init__(self, db=None):
        self.db = db

    def get_tier(self, tier_name):
        """获取指定等级的配置"""
        return self.TIERS.get(tier_name)

    def check_access(self, tier_name, feature, usage_count=None):
        """检查用户是否有权限使用某功能。返回 (allowed, reason)。"""
        tier = self.TIERS.get(tier_name)
        if not tier:
            return (False, "无效的会员等级")

        if feature == "qa" and usage_count is not None:
            limit = tier.get("qa_limit_monthly", 50)
            if limit > 0 and usage_count >= limit:
                return (False, f"本月问答次数已用完({limit}次/月),请升级会员")
            return (True, "ok")

        if feature == "compliance_report" and usage_count is not None:
            limit = tier.get("report_limit_monthly", 0)
            if limit <= 0:
                return (False, "当前等级不支持合规报告功能,请升级到专业版及以上")
            if usage_count >= limit:
                return (False, f"本月报告次数已用完({limit}次/月)")
            return (True, "ok")

        features = tier.get("features", [])
        if feature in features:
            return (True, "ok")
        return (False, f"当前等级({tier['name']})不支持此功能,请升级")

    def get_upgrade_suggestions(self, current_tier, blocked_feature):
        """当功能被阻止时,建议升级到哪个等级"""
        suggestions = []
        for tier_name, tier in self.TIERS.items():
            if blocked_feature in tier.get("features", []):
                if tier_name != current_tier:
                    price = tier.get("price_monthly", tier.get("price_yearly", 0) / 12)
                    suggestions.append({
                        "tier": tier_name,
                        "name": tier["name"],
                        "price_monthly": price,
                        "unlocks": blocked_feature,
                    })
        return suggestions[:3]

    def calculate_monthly_revenue(self, user_counts):
        """根据各等级用户数计算月收入"""
        revenue = 0
        for tier_name, count in user_counts.items():
            tier = self.TIERS.get(tier_name, {})
            monthly = tier.get("price_monthly", 0)
            if monthly == 0:
                yearly = tier.get("price_yearly", 0)
                monthly = yearly / 12
            revenue += monthly * count
        return round(revenue, 2)
