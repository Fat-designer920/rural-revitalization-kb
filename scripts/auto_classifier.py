"""
auto_classifier.py - 三级自动分级引擎(绿/黄/红标)
路径：scripts/auto_classifier.py
版本：v2.3.7
"""


class AutoClassifier(object):
    """三级自动分级:绿标(高置信自动入库)/黄标(中置信待审)/红标(低置信存档)。"""

    THRESHOLDS = {
        "green_min_qa": 4.0,
        "green_min_authority": "official",
        "yellow_min_qa": 2.5,
    }

    def __init__(self, db=None):
        self.db = db

    def classify(self, kp_data):
        """对单条知识点分级。kp_data 需含 qa_score/source_authority/source_type。返回 tier + reason"""
        qa = float(kp_data.get("qa_score") or 0)
        authority = kp_data.get("source_authority", "")
        source = kp_data.get("source_type", "extracted")

        if qa >= self.THRESHOLDS["green_min_qa"] and authority == self.THRESHOLDS["green_min_authority"]:
            return {"tier": "green", "action": "auto_confirm", "reason": "高置信度+权威来源"}
        elif qa >= self.THRESHOLDS["yellow_min_qa"]:
            return {"tier": "yellow", "action": "pending_review", "reason": "中等置信度,需人工审核"}
        else:
            return {"tier": "red", "action": "archive_only", "reason": "低置信度或不可靠来源,仅存档"}

    def batch_classify(self, kp_list):
        """批量分级,返回按 tier 分组的 dict"""
        result = {"green": [], "yellow": [], "red": []}
        for kp in kp_list:
            r = self.classify(kp)
            result[r["tier"]].append({**kp, "auto_tier": r["tier"], "auto_reason": r["reason"]})
        return result
