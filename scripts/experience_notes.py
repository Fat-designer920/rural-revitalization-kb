"""
experience_notes.py - 经验速记模块
路径：scripts/experience_notes.py
版本：v2.2.0 F045
功能：接收老唐的速记内容 → 调用V3自动结构化 → 写入knowledge_points待审核

使用方式：
  from scripts.experience_notes import ExperienceNotes
  en = ExperienceNotes()  # 自动初始化db和client
  kp_id = en.structure_and_save(title, content, content_type, keywords)
"""
import json, traceback
from datetime import datetime

# 预设注解标签（也供api_server.py引用）
ANNOTATION_TAGS = [
    "老唐实战验证",
    "有实战案例佐证",
    "需要现场确认",
    "已过时需更新",
    "四川特有经验",
    "可直接用于培训",
    "可用于投标方案",
    "需要补充政策依据",
    "客户常问的问题",
    "反常识但正确",
]

# 内容类型映射
CONTENT_TYPE_MAP = {
    "policy": "政策库",
    "case": "案例库",
    "experience": "经验库",
    "tool": "工具库",
    "data": "数据库",
}


class ExperienceNotes:
    def __init__(self, db=None, client=None):
        """
        db: DatabaseManager实例（可选，不传则自动创建）
        client: DeepSeekClient实例（可选，不传则自动创建）
        """
        if db is None:
            from scripts.db_manager import DatabaseManager
            db = DatabaseManager()
        self.db = db

        self.client = client
        if self.client is None:
            try:
                from scripts.deepseek_client import DeepSeekClient
                self.client = DeepSeekClient()
            except Exception as e:
                print("  [WARN] DeepSeek客户端初始化失败: %s" % e)
                self.client = None

    def structure_and_save(self, title, content, content_type="experience",
                           keywords=None, skip_ai=False):
        """
        将速记内容结构化并保存到知识库。

        参数:
            title: 标题（必填）
            content: 内容正文（必填）
            content_type: 内容类型 policy/case/experience/tool/data
            keywords: 用户手动输入的关键词列表（可选）
            skip_ai: 跳过AI结构化（测试用）

        返回:
            kp_id: 新建知识点ID，失败返回None
        """
        if not title or not content:
            print("  [ERROR] 标题和内容不能为空")
            return None

        if content_type not in CONTENT_TYPE_MAP:
            content_type = "experience"

        # 默认值
        ai_content = {
            "core_strategy": content,
            "detailed_method": "",
            "applicable_conditions": "",
            "risk_warning": "",
        }
        suggested_category_tags = []
        suggested_attribute_tags = {}
        suggested_keywords = keywords or []
        content_readiness = "draft"

        # 调用V3结构化
        if not skip_ai and self.client:
            try:
                ai_result = self._call_v3_structure(title, content, content_type)
                if ai_result:
                    ai_content = ai_result.get("ai_extracted_content", ai_content)
                    suggested_category_tags = ai_result.get("suggested_category_tags", [])
                    suggested_attribute_tags = ai_result.get("suggested_attribute_tags", {})
                    ai_keywords = ai_result.get("suggested_keywords", [])
                    # 合并用户关键词和AI关键词（用户优先）
                    if keywords:
                        merged = list(keywords)
                        for kw in ai_keywords:
                            if kw not in merged:
                                merged.append(kw)
                        suggested_keywords = merged[:15]
                    else:
                        suggested_keywords = ai_keywords[:15]
                    content_readiness = ai_result.get("content_readiness", "draft")
            except Exception as e:
                print("  [WARN] V3结构化失败，使用原始内容入库: %s" % e)
                traceback.print_exc()

        # 获取Prompt版本
        prompt_version = ""
        try:
            from scripts.prompts.prompt_templates import get_prompt_version
            prompt_version = get_prompt_version()
        except:
            try:
                from prompts.prompt_templates import get_prompt_version
                prompt_version = get_prompt_version()
            except:
                prompt_version = "v2.2.0"

        # 写入knowledge_points
        try:
            kp_id = self.db.add_knowledge_point(
                source_file_id=0,  # 虚拟source_file记录
                title=title,
                content_type=content_type,
                original_excerpt=content,  # 原始速记内容保存在original_excerpt
                ai_extracted_content=ai_content,
                suggested_category_tags=suggested_category_tags,
                suggested_attribute_tags=suggested_attribute_tags,
                suggested_keywords=suggested_keywords,
                content_readiness=content_readiness,
                source_authority="firsthand",  # 老唐一手经验
                prompt_version=prompt_version,
                source_type="manual",
            )
            print("  [OK] 经验速记已保存: #%d %s" % (kp_id, title))
            # 记录操作日志
            self.db.log_operation("quicknote_create", "knowledge_points", kp_id,
                                  {"title": title, "content_type": content_type})
            return kp_id
        except Exception as e:
            print("  [ERROR] 保存失败: %s" % e)
            traceback.print_exc()
            return None

    def _call_v3_structure(self, title, content, content_type):
        """调用V3将速记内容结构化"""
        try:
            from scripts.prompts.prompt_templates import EXPERIENCE_STRUCTURE_PROMPT
        except ImportError:
            from prompts.prompt_templates import EXPERIENCE_STRUCTURE_PROMPT

        type_cn = CONTENT_TYPE_MAP.get(content_type, "经验库")
        user_msg = "标题: %s\n分类: %s\n内容:\n%s" % (title, type_cn, content)

        response = self.client.chat(
            system_prompt=EXPERIENCE_STRUCTURE_PROMPT,
            user_message=user_msg,
            model_override="deepseek-chat",
            temperature=0.1,
            timeout=60,
        )

        if not response:
            return None

        # 解析JSON
        text = response.strip()
        # 去除可能的markdown代码块
        if text.startswith("```"):
            lines = text.split("\n")
            text = "\n".join(lines[1:-1]) if len(lines) > 2 else text
        if text.startswith("```json"):
            text = text[7:]
        if text.endswith("```"):
            text = text[:-3]
        text = text.strip()

        try:
            result = json.loads(text)
            return result
        except json.JSONDecodeError as e:
            print("  [WARN] V3返回JSON解析失败: %s" % e)
            print("  [DEBUG] V3原始返回: %s" % text[:500])
            return None
