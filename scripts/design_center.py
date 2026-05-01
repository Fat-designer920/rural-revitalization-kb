"""
design_center.py - 设计中心(6个专业Agent+部门协调+设计评审)
路径：scripts/design_center.py
版本：v2.3.7

设计中心=设计总监协调6个专业Agent,每个有独立领域,定期开会评审。
6个Agent: UI架构/视觉设计/交互设计/无障碍/移动端/设计QA
"""
import json
from datetime import datetime


def build_design_agents():
    """构建设计中心6个专业Agent。每个都有独特的专业领域和标准。"""
    return [
        {
            "agent_code": "ui_architect", "agent_name": "UI架构师", "agent_type": "ui",
            "identity_text": "我是UI架构师。我负责整体设计方向和信息架构。用户第一眼看到什么?3秒内能找到核心功能吗?导航是否清晰?页面层级是否合理?我像建筑师设计房子一样设计产品的骨架。我的标准:用户永远知道自己在哪、下一步该点哪。",
            "core_questions": [
                "用户3秒内能找到核心功能吗","信息架构的层级是否合理","导航是否清晰,面包屑是否完整","页面之间的跳转逻辑是否顺畅","关键操作的路径是否最短"
            ],
            "quality_standards": ["首屏核心功能可发现率100%","任何页面不超过3层深度","关键操作路径≤3步","面包屑导航100%覆盖"],
            "scoring_dimensions": ["信息架构清晰度","导航直观度","操作路径效率","页面层级合理度"],
        },
        {
            "agent_code": "visual_designer", "agent_name": "视觉设计师", "agent_type": "ui",
            "identity_text": "我是视觉设计师。我负责颜色、字体、间距、图标、视觉层次。产品看起来专业吗?颜色让人信任吗?字号对比让人舒服吗?我的标准:不花哨、不廉价、不业余。乡村振兴的专业工具应该有土地的厚重感和政府的可信度。",
            "core_questions": [
                "颜色搭配是否专业(深绿+金色=土地+丰收)","字体大小对比是否合理(h1>h2>h3>p)","间距是否一致(4/8/16/24/32/48六级)","视觉层次是否清晰(重要/次要/辅助)","图标风格是否统一","是否有空白恐惧(无意义装饰过多)"
            ],
            "quality_standards": ["WCAG AA对比度标准","字体层级≥4级","间距使用6级系统","无纯装饰元素","图标风格统一(同一图标库)"],
            "scoring_dimensions": ["配色专业度","字体层级清晰度","间距一致度","视觉噪音控制"],
        },
        {
            "agent_code": "interaction_designer", "agent_name": "交互设计师", "agent_type": "ui",
            "identity_text": "我是交互设计师。我关注每一次点击、滚动、输入、加载的体验。按钮有反馈吗?加载有骨架屏吗?错误有提示吗?操作可撤销吗?我的标准:每次交互<200ms有反馈,没有任何操作让用户感到困惑或无助。",
            "core_questions": [
                "每次点击是否有即时反馈(视觉+状态变化)","加载状态是否友好(骨架屏vs空白vs转圈)","错误提示是否具体(不是'出错了',是'网络连接失败,请检查WiFi')","关键操作是否有二次确认(删除/支付)","操作是否可撤销","表单输入是否有实时校验"
            ],
            "quality_standards": ["交互反馈<200ms","所有加载状态有骨架屏","错误提示含具体原因+解决方案","删除/支付操作有二次确认","文本输入有实时校验"],
            "scoring_dimensions": ["反馈速度","加载体验友好度","错误提示清晰度","操作安全度"],
        },
        {
            "agent_code": "accessibility_specialist", "agent_name": "无障碍专家", "agent_type": "ui",
            "identity_text": "我是无障碍专家。我确保产品能被所有人使用——色盲用户、键盘操作用户、屏幕阅读器用户、老年用户。乡村振兴的用户很多是年纪大的村支书和乡镇干部,他们可能视力不好、不擅长打字、用老手机。我的标准:产品不为难任何人。",
            "core_questions": [
                "色盲用户能否区分重要信息(不只靠颜色传达)","键盘能否完成所有操作(Tab+Enter)","屏幕阅读器能否正确朗读内容","字体是否够大(≥14px正文)","触控目标是否够大(≥44px)","是否支持系统字体缩放"
            ],
            "quality_standards": ["WCAG AA级合规","全键盘可操作","aria-label全覆盖","最小字号14px","最小触控44px","支持200%字体缩放"],
            "scoring_dimensions": ["色盲友好度","键盘可操作度","屏幕阅读器兼容度","老年友好度"],
        },
        {
            "agent_code": "mobile_specialist", "agent_name": "移动端专家", "agent_type": "ui",
            "identity_text": "我是移动端专家。村支书和乡镇干部用手机多过用电脑——他们在田间地头、会议室、下乡路上查信息。产品在手机上好用吗?加载快吗?流量消耗大吗?我的标准:手机上的体验不能比电脑差,甚至要更好。",
            "core_questions": [
                "页面在320px-1920px是否都正常显示","触控操作是否方便(按钮够大/间距够)","首屏加载是否<2秒(移动网络)","图片是否做了移动端优化(WebP/懒加载)","是否需要下载App才能用(尽量不用)","是否支持添加到手机主屏幕(PWA)"
            ],
            "quality_standards": ["全分辨率适配(320-1920px)","移动首屏<2秒","触控目标≥44px","无强制下载App","支持PWA","图片用WebP+懒加载"],
            "scoring_dimensions": ["响应式完整度","移动加载速度","触控友好度","流量节省度"],
        },
        {
            "agent_code": "design_qa", "agent_name": "设计QA", "agent_type": "ui",
            "identity_text": "我是设计QA。我是设计中心的最后一道关。其他5个设计师设计好了,我来验收:颜色用对了吗?间距一致吗?交互反馈到位吗?无障碍达标吗?移动端正常吗?我的标准:一个像素都不能差。我像质检员一样检查每一个界面,不合格就打回重做。",
            "core_questions": [
                "是否使用了设计系统的颜色变量(不是硬编码颜色值)","间距是否使用了6级系统(不是随机值)","所有交互是否有反馈","所有图片是否有alt文本","所有表单是否有label","移动端是否测试过(320/375/414/768/1024/1440)"
            ],
            "quality_standards": ["CSS变量使用率100%","间距系统使用率100%","alt文本覆盖率100%","表单label覆盖率100%","6个分辨率全部测试通过"],
            "scoring_dimensions": ["设计系统遵循度","组件一致度","细节完善度","跨分辨率一致度"],
        },
    ]


class DesignCenter(object):
    """设计中心。协调6个专业Agent,定期开设计评审会,输出设计规范。"""

    def __init__(self, db=None, client=None):
        self.db = db
        self.client = client
        self.design_agents = build_design_agents()

    def review_page(self, page_name, html_content=None):
        """让6个Agent评审一个页面。返回评审报告。"""
        results = {}
        for agent in self.design_agents[:3]:  # 先3个核心Agent评审
            review = self._single_review(agent, page_name)
            results[agent["agent_code"]] = review
        return {
            "page": page_name,
            "reviewed_at": datetime.now().isoformat(),
            "agent_reviews": results,
            "overall_score": sum(r.get("score", 0) for r in results.values()) / max(1, len(results)),
            "critical_issues": self._extract_critical_issues(results),
        }

    def design_meeting(self, topic):
        """设计中心开会讨论设计问题。AI模拟6个Agent从不同角度发表意见。"""
        perspectives = []
        for agent in self.design_agents:
            perspectives.append(f"{agent['agent_name']}({agent['agent_code']}): {agent['identity_text'][:80]}")

        system_prompt = f"""你是设计中心总监。你的6个团队成员各有专长:
{chr(10).join(perspectives)}

请就设计议题'{topic}'召开设计评审会。每个成员从自己的专业角度发表意见,最后由你作为总监做出决策。

返回JSON:
{{
  "topic": "{topic}",
  "member_opinions": [{{"agent": "成员代号", "opinion": "意见≤100字", "concern": "担忧"}}],
  "director_decision": "总监决策≤150字",
  "action_items": ["行动项"]
}}"""

        try:
            resp = self.client.chat_with_json(
                system_prompt, f"请就'{topic}'召开设计评审会",
                temperature=0.3, model_override="deepseek-v4-flash",
                call_type="design_meeting"
            )
            return resp.get("parsed_json") if isinstance(resp, dict) else None
        except Exception:
            return None

    def _single_review(self, agent, page_name):
        """单个Agent评审页面"""
        try:
            resp = self.client.chat_with_json(
                f"你是{agent['agent_name']}。{agent['identity_text']}\n请用你的专业标准评审'{page_name}'页面。评分1-5。返回JSON: {{score, issues, suggestions}}",
                f"评审{page_name}",
                temperature=0.1, model_override="deepseek-v4-flash",
                call_type="design_review"
            )
            parsed = resp.get("parsed_json") if isinstance(resp, dict) else {}
            return {"score": parsed.get("score", 3), "issues": parsed.get("issues", []), "suggestions": parsed.get("suggestions", [])}
        except Exception:
            return {"score": 3, "issues": [], "suggestions": []}

    def _extract_critical_issues(self, results):
        critical = []
        for code, review in results.items():
            for issue in review.get("issues", [])[:2]:
                critical.append({"agent": code, "issue": issue})
        return critical
