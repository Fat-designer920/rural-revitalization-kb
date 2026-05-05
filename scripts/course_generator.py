"""
course_generator.py - AI 自动课程生成器(大纲→课文→练习→评估)
路径：scripts/course_generator.py
版本：v2.3.7
"""
import json
from datetime import datetime


class CourseGenerator(object):
    """AI 驱动课程生成器。从知识库中自动提取知识链,生成结构化课程。"""

    def __init__(self, db=None, client=None):
        self.db = db
        self.client = client

    def generate_course_outline(self, topic, target_reader="township_cadre", depth="操作级"):
        """生成课程大纲:基于知识库中与topic相关的知识点,AI构建课程结构"""
        kps = self._fetch_related_kps(topic, limit=30)
        if not kps:
            return {"success": False, "error": f"知识库中无'{topic}'相关内容"}

        outline = self._ai_build_outline(topic, kps, target_reader, depth)
        return {"success": True, "topic": topic, "outline": outline,
                "kp_count": len(kps), "generated_at": datetime.now().isoformat()}

    def generate_lesson(self, outline_item, kp_ids=None):
        """生成单课内容:AI根据大纲条目和知识点生成完整课文"""
        kps = self._fetch_kps_by_ids(kp_ids) if kp_ids else []
        lesson = self._ai_write_lesson(outline_item, kps)
        return {"success": True, "lesson": lesson}

    def generate_exercises(self, lesson_content, count=5):
        """生成课后练习:选择题+简答题+案例分析"""
        return self._ai_generate_exercises(lesson_content, count)

    def generate_full_course(self, topic, target_reader="township_cadre"):
        """一键生成完整课程:大纲→章节→练习→评估"""
        outline_result = self.generate_course_outline(topic, target_reader)
        if not outline_result.get("success"):
            return outline_result

        lessons = []
        for item in outline_result.get("outline", {}).get("chapters", [])[:5]:
            lesson_result = self.generate_lesson(item, item.get("kp_ids", []))
            if lesson_result.get("success"):
                lessons.append(lesson_result["lesson"])

        return {
            "success": True,
            "topic": topic,
            "outline": outline_result["outline"],
            "lessons": lessons,
            "lesson_count": len(lessons),
            "generated_at": datetime.now().isoformat(),
        }

    def _fetch_related_kps(self, topic, limit=30):
        """从知识库获取与主题相关的知识点"""
        try:
            conn = self.db.get_connection(); c = conn.cursor()
            c.execute("""SELECT id, title, content_type, original_excerpt, ai_extracted_content,
                         qa_score, knowledge_depth, target_reader
                         FROM knowledge_points
                         WHERE review_status='confirmed'
                           AND (title LIKE ? OR original_excerpt LIKE ?
                                OR suggested_category_tags LIKE ?)
                         ORDER BY qa_score DESC LIMIT ?""",
                      (f"%{topic}%", f"%{topic}%", f"%{topic}%", limit))
            rows = [dict(r) for r in c.fetchall()]
            conn.close()
            return rows
        except Exception:
            return []

    def _fetch_kps_by_ids(self, kp_ids):
        if not kp_ids:
            return []
        try:
            conn = self.db.get_connection(); c = conn.cursor()
            placeholders = ",".join("?" * len(kp_ids))
            c.execute(f"""SELECT * FROM knowledge_points WHERE id IN ({placeholders})""", kp_ids)
            rows = [dict(r) for r in c.fetchall()]
            conn.close()
            return rows
        except Exception:
            return []

    def _ai_build_outline(self, topic, kps, target_reader, depth):
        """AI 构建课程大纲"""
        kp_summaries = "\n".join([f"- {kp['title'][:80]}" for kp in kps[:20]])

        system_prompt = f"""你是乡村振兴领域的课程设计师。你为{target_reader}设计一门关于'{topic}'的课程。
目标读者知识水平:{depth}
可用知识点摘要:\n{kp_summaries}

你需要设计课程大纲,包含:
- course_title: 课程标题
- course_description: 课程简介(≤200字)
- target_audience: 目标学员
- total_hours: 预估总学时
- chapters: 章节列表(每章含 title/description/kp_count/estimated_minutes)

返回 JSON。"""

        user_prompt = f"请为'{topic}'设计课程大纲,面向{target_reader},深度{depth}。"

        try:
            resp = self.client.chat_with_json(system_prompt, user_prompt,
                                                  temperature=0.3, model_override="deepseek-v4-pro",
                                                  call_type="course_outline")
            return resp.get("parsed_json") if isinstance(resp, dict) else {}
        except Exception:
            return {"chapters": []}

    def _ai_write_lesson(self, outline_item, kps):
        """AI 撰写单课内容"""
        title = outline_item.get("title", "")
        kp_text = "\n".join([f"- {kp.get('title','')}: {(kp.get('original_excerpt') or '')[:200]}"
                            for kp in kps[:5]])

        system_prompt = f"""你是乡村振兴培训讲师。请为课程章节'{title}'撰写课文。
参考知识点:\n{kp_text}

课文要求:
1. 语言通俗,像老师在讲课不是写论文
2. 有具体案例和数据支撑
3. 有操作步骤和注意事项
4. 长度800-1500字
5. 结尾有本节要点总结

返回 JSON: {{"title": "...", "content": "...", "key_points": [...], "case_study": "...", "estimated_reading_minutes": 数字}}"""

        try:
            resp = self.client.chat_with_json(system_prompt,
                                                  f"请撰写'{title}'的课程内容",
                                                  temperature=0.5, model_override="deepseek-v4-pro",
                                                  call_type="course_lesson")
            return resp.get("parsed_json") if isinstance(resp, dict) else {}
        except Exception:
            return {}

    def _ai_generate_exercises(self, lesson_content, count=5):
        """AI 生成课后练习"""
        try:
            resp = self.client.chat_with_json(
                f"请为以下课程内容设计{count}道练习题(选择题+简答题混合):\n{str(lesson_content)[:1500]}",
                "请生成练习题",
                temperature=0.3, model_override="deepseek-v4-flash",
                call_type="course_exercises")
            return resp.get("parsed_json") if isinstance(resp, dict) else {"exercises": []}
        except Exception:
            return {"exercises": []}
