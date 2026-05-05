"""
course_generator.py - AI课程自动生成引擎(大纲→脚本→老唐视角→审核)
路径：agents/course_generator.py
版本：v2.3.7

乡村振兴知识产品的核心变现引擎。从知识库自动生成结构化课程。
流程: 选题分析→大纲生成→逐节脚本→老唐视角注入→配图建议→品牌审核→输出

产品形态对标: 洋葱学园(AI动画微课)+天津大学模式(理论+实操+案例)+得到(音频+文稿)
差异化: 老唐20年实战视角=不可复制的IP
"""
import json, time
from datetime import datetime


class CourseGenerator(object):
    """AI课程自动生成引擎。知识库→课程产品。"""

    def __init__(self, client=None, db=None):
        self.client = client
        self.db = db
        self.agent_code = "course_generator"
        self.agent_name = "课程生成引擎"

    # ================================================================
    # 主流程：从选题到成品课程
    # ================================================================
    def generate_course(self, topic, target_audience="乡镇干部+平台公司项目经理",
                        course_level="中级", lesson_count=8):
        """生成一门完整课程。返回结构化课程包。"""
        if not self.client:
            return {"error": "AI客户端未连接,无法生成课程"}

        result = {
            "topic": topic,
            "target_audience": target_audience,
            "course_level": course_level,
            "generated_at": datetime.now().isoformat(),
            "stages": {},
        }

        # Stage 1: 选题分析与定价
        analysis = self._stage_analyze_topic(topic, target_audience, course_level)
        result["stages"]["topic_analysis"] = analysis
        if not analysis.get("viable"):
            result["error"] = "选题不可行: " + analysis.get("reason", "")
            return result

        # Stage 2: 知识检索(从知识库拉相关KP)
        kps = self._stage_retrieve_knowledge(topic, analysis)
        result["stages"]["knowledge_retrieval"] = {"kp_count": len(kps)}
        if len(kps) < 5:
            result["error"] = f"知识库相关KP不足({len(kps)}条),需要先喂料"
            return result

        # Stage 3: 课程大纲生成
        outline = self._stage_generate_outline(topic, target_audience, course_level,
                                               lesson_count, analysis, kps)
        result["stages"]["outline"] = outline

        # Stage 4: 逐节脚本生成
        lessons = self._stage_generate_lessons(outline, kps, analysis)
        result["stages"]["lessons"] = lessons

        # Stage 5: 老唐视角注入
        enriched = self._stage_inject_laotang_perspective(lessons, topic)
        result["stages"]["laotang_enrichment"] = enriched

        # Stage 6: 配图与视觉建议
        visuals = self._stage_visual_suggestions(outline, lessons)
        result["stages"]["visual_suggestions"] = visuals

        # Stage 7: 课程包组装
        package = self._assemble_course_package(topic, target_audience, course_level,
                                                analysis, outline, lessons, visuals)
        result["course_package"] = package
        result["status"] = "ready_for_review"

        return result

    # ================================================================
    # Stage 1: 选题分析
    # ================================================================
    def _stage_analyze_topic(self, topic, audience, level):
        system_prompt = f"""你是乡村振兴知识付费产品经理。请分析以下课程选题的可行性。

选题: {topic}
目标学员: {audience}
难度: {level}

分析维度:
1. 市场需求: 有多少人需要学这个? 是刚需还是nice-to-have?
2. 竞争分析: 市场上有没有类似课程? 我们的差异化是什么?
3. 定价建议: 这个选题的合理定价区间(参考: 天天学农99-999元, 得到9.9-199元)
4. 预期销量: 保守估计第一年能卖多少份?
5. 老唐优势: 这个选题能不能发挥老唐20年实战经验?

返回JSON:
{{"viable":true/false,"reason":"≤100字","market_size":"大/中/小",
 "competition_level":"高/中/低","differentiation":"≤100字我们的独特优势",
 "suggested_price":"99-499元区间","estimated_sales_year":"保守估计份数",
 "laotang_advantage":"≤100字老唐在这个选题上的独特价值",
 "keywords":["关键词1","关键词2","关键词3"]}}"""

        try:
            resp = self.client.chat_with_json(
                system_prompt, f"请分析选题: {topic}",
                temperature=0.3, model_override="deepseek-v4-flash",
                call_type="course_analyze")
            return resp.get("parsed_json", {}) if isinstance(resp, dict) else {}
        except Exception:
            return {"viable": True, "reason": "AI分析暂不可用,默认通过"}

    # ================================================================
    # Stage 2: 知识检索
    # ================================================================
    def _stage_retrieve_knowledge(self, topic, analysis):
        keywords = analysis.get("keywords", [topic])
        kps = []
        if self.db:
            try:
                conn = self.db.get_connection(); c = conn.cursor()
                for kw in keywords[:5]:
                    c.execute("""SELECT id,title,original_excerpt,content_type,
                                 qa_score,source_authority
                                 FROM knowledge_points
                                 WHERE (title LIKE ? OR original_excerpt LIKE ?)
                                 AND review_status='confirmed'
                                 AND qa_score >= 3
                                 LIMIT 20""",
                              (f"%{kw}%", f"%{kw}%"))
                    for row in c.fetchall():
                        kps.append(dict(row))
                conn.close()
            except Exception:
                pass
        return kps[:50]

    # ================================================================
    # Stage 3: 大纲生成
    # ================================================================
    def _stage_generate_outline(self, topic, audience, level, lesson_count, analysis, kps):
        kp_titles = [kp.get("title", "")[:100] for kp in kps[:20]]
        kp_text = "\n".join(f"- {t}" for t in kp_titles[:15])

        system_prompt = f"""你是乡村振兴课程设计师。请为以下选题设计课程大纲。

选题: {topic}
学员: {audience}
难度: {level}
课时数: {lesson_count}节(每节10-15分钟)
可用知识点(来自知识库):
{kp_text}

设计原则:
1. 结构: 为什么(Why)→是什么(What)→怎么做(How)→避坑(Don't)→案例(Show)
2. 每节课有明确的学习目标(学完能做什么)
3. 每节课有"老唐说"环节(老唐20年实战经验的实战判断)
4. 每节课有课后练习(实操题,不是选择题)
5. 课程难度递进(第1节入门→最后1节高阶)

返回JSON:
{{"course_title":"≤20字课程标题","course_subtitle":"≤40字副标题",
 "learning_objectives":["目标1","目标2","目标3"],
 "lessons":[{{"lesson_number":1,"title":"≤15字","duration":"10-15分钟",
   "learning_goal":"≤30字","key_points":["要点1","要点2"],
   "laotang_hook":"这节课老唐会讲什么独家经验≤30字",
   "exercise":"课后实操题≤50字"}}],
 "estimated_total_duration":"总时长",
 "pricing_tier":"99/199/499/799/999"}}"""

        try:
            resp = self.client.chat_with_json(
                system_prompt, f"设计课程大纲: {topic}",
                temperature=0.4, model_override="deepseek-v4-flash",
                call_type="course_outline")
            return resp.get("parsed_json", {}) if isinstance(resp, dict) else {}
        except Exception:
            return {"course_title": topic, "lessons": []}

    # ================================================================
    # Stage 4: 逐节脚本生成
    # ================================================================
    def _stage_generate_lessons(self, outline, kps, analysis):
        lessons = outline.get("lessons", [])
        if not lessons:
            return []

        scripts = []
        for lesson in lessons[:3]:  # 首先生成前3节(控制API成本)
            script = self._generate_single_lesson(lesson, outline, kps)
            scripts.append(script)
            time.sleep(1)

        return scripts

    def _generate_single_lesson(self, lesson, outline, kps):
        lesson_num = lesson.get("lesson_number", 1)
        title = lesson.get("title", "")
        hook = lesson.get("laotang_hook", "")

        kp_context = json.dumps([{
            "title": kp.get("title", "")[:100],
            "excerpt": (kp.get("original_excerpt") or "")[:200],
        } for kp in kps[:10]], ensure_ascii=False)

        system_prompt = f"""你是乡村振兴课程脚本撰写专家。请撰写第{lesson_num}节课程脚本。

课程: {outline.get('course_title','')}
本节标题: {title}
学习目标: {lesson.get('learning_goal','')}
老唐要讲的独家经验: {hook}

## 脚本结构(严格按此顺序)
1. 开场钩子(30秒): 用一个真实痛点或反常识问题抓住学员
2. 核心内容(8-10分钟): 讲清楚本节的核心知识和方法
3. 老唐说(2-3分钟): 老唐20年实战的独家判断、踩过的坑、反常识洞察
4. 案例拆解(2-3分钟): 一个真实项目的实操案例
5. 本节小结(30秒): 3个关键takeaway
6. 课后实操: 学员要动手做的事

## 参考知识点
{kp_context}

## 语言风格
- 不是讲课,是"老师傅带徒弟"
- 用大白话,不用学术术语(除非必须用,用时要解释)
- 敢于说"我当年在这个坑里摔过"
- 敢于说"这个做法在四川行得通,在别的地方不一定"

返回JSON:
{{"lesson_number":{lesson_num},"title":"{title}",
 "script_sections":[
   {{"section":"开场钩子","content":"≤200字脚本","duration":"30秒"}},
   {{"section":"核心内容","content":"≤1500字脚本","duration":"8-10分钟"}},
   {{"section":"老唐说","content":"≤500字脚本(必须用老唐第一人称'我')","duration":"2-3分钟"}},
   {{"section":"案例拆解","content":"≤400字脚本","duration":"2-3分钟"}},
   {{"section":"本节小结","content":"≤100字: 3个关键takeaway","duration":"30秒"}}
 ],
 "exercise":"≤100字课后实操任务",
 "visual_cues":["需要展示的图表/流程图/对比表建议"]}}"""

        try:
            resp = self.client.chat_with_json(
                system_prompt, f"撰写第{lesson_num}节脚本: {title}",
                temperature=0.5, model_override="deepseek-v4-pro",
                call_type="course_script")
            return resp.get("parsed_json", {}) if isinstance(resp, dict) else {}
        except Exception:
            return {"lesson_number": lesson_num, "title": title, "error": "生成失败"}

    # ================================================================
    # Stage 5: 老唐视角注入
    # ================================================================
    def _stage_inject_laotang_perspective(self, lessons, topic):
        """为每节课注入老唐独家视角。这是课程的核心差异化。"""
        enriched = []
        for lesson in lessons:
            laotang_notes = {
                "lesson_number": lesson.get("lesson_number"),
                "title": lesson.get("title"),
                "injections": [],
            }

            # 检查每节课是否有"老唐说"环节
            sections = lesson.get("script_sections", [])
            for s in sections:
                if s.get("section") == "老唐说":
                    # AI生成的老唐视角需要通过品牌审核
                    laotang_notes["injections"].append({
                        "type": "laotang_perspective",
                        "content": s.get("content", "")[:300],
                        "needs_human_review": True,
                        "review_note": "老唐本人需确认: 这些经验描述是否准确? 有没有遗漏关键细节?",
                    })

            enriched.append(laotang_notes)

        return {"lessons_enriched": len(enriched),
                "review_required": True,
                "reviewer": "老唐本人 + 品牌把关人",
                "notes": enriched}

    # ================================================================
    # Stage 6: 视觉建议
    # ================================================================
    def _stage_visual_suggestions(self, outline, lessons):
        system_prompt = f"""你是教育产品视觉设计师。请为以下课程建议配图和视觉元素。

课程: {outline.get('course_title','')}
节数: {len(lessons)}

请逐一建议每节课需要什么样的视觉辅助:
- 流程图(什么流程?)
- 对比表(什么对比?)
- 数据图(什么数据?)
- 案例示意图(什么场景?)
- 检查清单(什么清单?)

返回JSON:
{{"suggestions":[{{"lesson_number":1,"visual_type":"流程图/对比表/...",
  "description":"≤50字描述","data_source":"从哪里获取数据"}}]}}"""

        try:
            resp = self.client.chat_with_json(
                system_prompt, "请建议视觉元素",
                temperature=0.3, model_override="deepseek-v4-flash",
                call_type="course_visuals")
            return resp.get("parsed_json", {}) if isinstance(resp, dict) else {}
        except Exception:
            return {"suggestions": []}

    # ================================================================
    # Stage 7: 课程包组装
    # ================================================================
    def _assemble_course_package(self, topic, audience, level, analysis, outline, lessons, visuals):
        return {
            "meta": {
                "course_title": outline.get("course_title", topic),
                "course_subtitle": outline.get("course_subtitle", ""),
                "target_audience": audience,
                "level": level,
                "total_lessons": len(lessons),
                "estimated_duration": outline.get("estimated_total_duration", ""),
                "suggested_price": analysis.get("suggested_price", "99-499"),
                "generated_at": datetime.now().isoformat(),
                "version": "v1.0-draft",
            },
            "outline": outline,
            "lessons": lessons,
            "visual_suggestions": visuals,
            "review_checklist": [
                "老唐本人审核: 所有'老唐说'内容是否准确",
                "品牌把关人审核: 事实、逻辑、合规",
                "UI设计师: 配图/动画方案",
                "测试: 3个目标学员试听评分≥4分",
            ],
            "next_steps": [
                "老唐审核通过后→录制音频/视频",
                "UI设计师制作配图和动画",
                "上传到课程平台(小鹅通/知识星球/自建)",
                "定价→预售→正式上线",
            ],
        }

    # ================================================================
    # 批量生成: 根据课程线自动生成多门课程
    # ================================================================
    def generate_course_line(self, course_line_name, topics, audience, level="中级"):
        """生成一条课程线(多门课程)。如'专项债系列'含3门课。"""
        results = []
        for topic in topics:
            r = self.generate_course(topic, audience, level)
            results.append(r)
            time.sleep(2)
        return {
            "course_line": course_line_name,
            "total_courses": len(results),
            "completed": sum(1 for r in results if r.get("status") == "ready_for_review"),
            "courses": results,
        }

    def to_dict(self):
        return {
            "agent_code": self.agent_code,
            "agent_name": self.agent_name,
            "agent_type": "production",
            "identity_text": "我是课程生成引擎。我自动从知识库生成结构化课程: 选题分析→大纲→脚本→老唐视角→配图→成品。我的输出不是最终产品——必须经过老唐审核和品牌把关。",
            "core_questions": ["知识库是否有足够的素材支撑一门课","课程大纲是否逻辑递进","每节课是否有老唐独家视角","课程定价是否合理"],
            "quality_standards": ["课程大纲逻辑完整","每节课有老唐视角(差异化)","脚本可读性强","视觉建议可行"],
            "scoring_dimensions": ["选题市场价值","大纲逻辑性","老唐视角深度","脚本可用度"],
        }
