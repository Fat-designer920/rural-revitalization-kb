"""
reader_tagger.py - V3 自动读者定位打标器(15角色×5场景×4深度)
路径：agents/reader_tagger.py
版本：v2.3.7
"""

import json
import time

from scripts.deepseek_client import CostLimitExceeded, DeepSeekClient
from scripts.prompts.prompt_templates import READER_TAGGING_PROMPT

READER_ROLES = [
    "township_cadre",
    "county_land",
    "county_agri",
    "dev_reform",
    "finance_bureau",
    "platform_pm",
    "planning_institute",
    "consulting_firm",
    "construction_pm",
    "industry_operator",
    "social_capital",
    "village_secretary",
    "cooperative_head",
    "legal_counsel",
    "bank_credit",
]

READER_SCENARIOS = ["policy", "funding", "land", "approval", "execution"]
KNOWLEDGE_DEPTHS = ["入门级", "操作级", "判断级", "证据级"]


class ReaderAutoTagger(object):
    """读者自动定位打标器。V3 单次调用,同时输出 10 个读者定位字段。"""

    def __init__(self, client=None, db=None):
        self.client = client or DeepSeekClient()
        self.db = db

    def tag_single(self, kp_dict):
        """对单条知识点打标。kp_dict: {title, content_type, excerpt, category_tags}。返回 reader_tags dict"""
        try:
            title = kp_dict.get("title", "")[:200]
            ctype = kp_dict.get("content_type", "policy")
            excerpt = (kp_dict.get("original_excerpt") or kp_dict.get("excerpt") or "")[
                :800
            ]
            tags = (
                kp_dict.get("suggested_category_tags")
                or kp_dict.get("category_tags")
                or []
            )

            user_prompt = READER_TAGGING_PROMPT["user_prompt_template"].format(
                title=title,
                content_type=ctype,
                excerpt=excerpt,
                category_tags=json.dumps(tags, ensure_ascii=False),
            )
            resp = self.client.chat_with_json(
                READER_TAGGING_PROMPT["system_prompt"],
                user_prompt,
                temperature=0.1,
                model_override="deepseek-v4-flash",
                call_type="reader_tagger",
            )
            raw = resp.get("parsed_json") if isinstance(resp, dict) else None
            if not raw or not isinstance(raw, dict):
                return self._default_tags()
            return self._sanitize_reader_tags(raw)
        except CostLimitExceeded:
            return self._default_tags()
        except Exception:
            return self._default_tags()

    def tag_batch(self, kp_list, batch_size=50, progress_callback=None):
        """批量打标。kp_list: [{kp_id, title, content_type, excerpt, category_tags}, ...]。返回 [(kp_id, reader_tags), ...]"""
        results = []
        total = len(kp_list)
        for i, kp in enumerate(kp_list):
            tags = self.tag_single(kp)
            kp_id = kp.get("kp_id") or kp.get("id")
            results.append((kp_id, tags))
            if progress_callback:
                progress_callback(
                    {
                        "current": i + 1,
                        "total": total,
                        "message": f"读者打标 {i+1}/{total}",
                    }
                )
        return results

    def _sanitize_reader_tags(self, raw):
        """校验枚举白名单,清洗非法值,返回标准化 dict"""
        target_reader = raw.get("target_reader") or raw.get("target_reader_roles") or []
        if isinstance(target_reader, str):
            target_reader = [r.strip() for r in target_reader.split(",") if r.strip()]
        target_reader = [r for r in target_reader if r in READER_ROLES]
        if not target_reader:
            target_reader = ["township_cadre"]

        scenario = raw.get("reader_scenario", "")
        if scenario not in READER_SCENARIOS:
            scenario = "policy"

        depth = raw.get("knowledge_depth", "")
        if depth not in KNOWLEDGE_DEPTHS:
            depth = "入门级"

        search_kw = raw.get("search_keywords") or []
        if isinstance(search_kw, str):
            search_kw = [k.strip() for k in search_kw.split(",") if k.strip()]
        search_kw = [k for k in search_kw if 2 <= len(k) <= 30][:10]

        questions = raw.get("question_examples") or []
        if isinstance(questions, str):
            questions = [q.strip() for q in questions.split("\n") if q.strip()]
        questions = [q for q in questions if len(q) >= 5][:5]

        quality = raw.get("quality_score") or raw.get("quality_score_json") or {}
        if not isinstance(quality, dict):
            quality = {}
        for dim in ("accuracy", "practicality", "timeliness", "uniqueness"):
            val = quality.get(dim, 3)
            try:
                val = int(val)
            except (TypeError, ValueError):
                val = 3
            quality[dim] = max(1, min(5, val))

        return {
            "target_reader": target_reader,
            "reader_scenario": scenario,
            "reader_need": str(raw.get("reader_need", ""))[:200],
            "knowledge_depth": depth,
            "depth_reason": str(raw.get("depth_reason", ""))[:200],
            "knowledge_chain": str(raw.get("knowledge_chain", ""))[:200],
            "search_keywords": search_kw,
            "question_examples": questions,
            "answer_template": str(raw.get("answer_template", ""))[:500],
            "quality_score": quality,
        }

    def _default_tags(self):
        return {
            "target_reader": [],
            "reader_scenario": "",
            "reader_need": "",
            "knowledge_depth": "",
            "depth_reason": "",
            "knowledge_chain": "",
            "search_keywords": [],
            "question_examples": [],
            "answer_template": "",
            "quality_score": {
                "accuracy": 3,
                "practicality": 3,
                "timeliness": 3,
                "uniqueness": 3,
            },
        }


def run_reader_backfill(db, client, progress_callback=None, batch_size=50):
    """回填全库缺失的读者定位字段。供 api_server 异步任务调用。"""
    tagger = ReaderAutoTagger(client=client, db=db)
    kps = db.get_kps_missing_reader_fields(limit=500)
    if not kps:
        return {
            "success": True,
            "message": "无缺失读者字段的知识点",
            "total": 0,
            "tagged": 0,
        }

    total = len(kps)
    tagged = 0
    for i, kp in enumerate(kps):
        tags = tagger.tag_single(kp)
        if tags.get("target_reader"):
            db.batch_update_reader_fields(kp["id"], tags)
            tagged += 1
        if progress_callback:
            progress_callback(
                {"current": i + 1, "total": total, "message": f"读者回填 {i+1}/{total}"}
            )
        if (i + 1) % 10 == 0:
            time.sleep(0.1)
    return {"success": True, "total": total, "tagged": tagged}
