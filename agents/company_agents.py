"""
company_agents.py - 公司级Agent(已被v2.3.7六部门架构吸收)
路径：agents/company_agents.py
版本：v2.3.7

v2.3.7部门化重构: 原6个公司Agent的功能已分配到6个部门:
  市场战略师 → 市场拓展部(获客策略师)
  渠道运营经理 → 市场拓展部(内容营销员)
  定价策略师 → CEO办公室(财务分析师)
  上线就绪审查官 → 客户交付部(方案汇编师)
  客户成功经理 → 客户交付部(问答顾问)
  内容营销专家 → 市场拓展部(内容营销员)

本文件保留向后兼容接口,不再创建独立Agent。
"""
from agents.base_agent import BaseAgent


def build_company_agents(client=None, db=None):
    """向后兼容: 返回空列表(Agent已吸收到agent_orchestra的六部门中)"""
    return []


def build_company_agent_dicts():
    """向后兼容: 返回空列表"""
    return []
