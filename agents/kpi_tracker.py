"""
kpi_tracker.py - KPI度量系统,测量所有部门的关键绩效指标
路径：agents/kpi_tracker.py
版本：v2.3.7-part5
"""

import json
import os
import sqlite3
from datetime import datetime, timedelta
from pathlib import Path

PROJECT_ROOT = Path(__file__).parent.parent
DB_PATH = str(PROJECT_ROOT / "data" / "database" / "knowledge_base.db")

WORLD_CLASS = {
    "factual_error_rate": 0.001,
    "audit_coverage": 0.10,
    "freshness_rate": 0.95,
    "csat": 0.92,
    "agent_zombie_ratio": 0.05,
    "red_flag_rate": 0.05,
}


class KPITracker:
    """KPI度量系统。测量所有部门的关键绩效指标。先测量,再优化。"""

    def __init__(self, db=None):
        if db is None:
            self._db_path, self._ext_db = DB_PATH, None
        elif hasattr(db, "get_connection"):
            self._ext_db, self._db_path = db, getattr(db, "db_path", DB_PATH)
        else:
            self._db_path, self._ext_db = str(db), None
        self._snapshots = []

    def _conn(self):
        if self._ext_db:
            return self._ext_db.get_connection()
        conn = sqlite3.connect(self._db_path)
        conn.row_factory = sqlite3.Row
        return conn

    def snapshot(self):
        """采集当前全部KPI快照。返回完整仪表盘数据。"""
        snap = {
            "ts": datetime.now().isoformat(),
            "quality": self.quality_metrics(),
            "production": self.production_metrics(),
            "agents": self.agent_metrics(),
            "infrastructure": self.infrastructure_metrics(),
        }
        self._snapshots.append(snap)
        if len(self._snapshots) > 30:
            self._snapshots = self._snapshots[-30:]
        return snap

    def quality_metrics(self):
        """质量指标: 审计覆盖率、红标率、保鲜率、客户满意度"""
        m = {}
        conn = self._conn()
        try:
            c = conn.cursor()
            m["confirmed"] = (
                c.execute(
                    "SELECT COUNT(*) FROM knowledge_points WHERE review_status='confirmed'"
                ).fetchone()[0]
                or 0
            )
            scored = (
                c.execute(
                    "SELECT COUNT(*) FROM knowledge_points WHERE qa_score > 0"
                ).fetchone()[0]
                or 0
            )
            r = c.execute(
                "SELECT AVG(qa_score) FROM knowledge_points WHERE qa_score > 0"
            ).fetchone()
            m["avg_qa"] = round(r[0], 2) if r and r[0] else 0
            m["red_flag"] = (
                c.execute(
                    "SELECT COUNT(*) FROM knowledge_points WHERE qa_score > 0 AND qa_score < 3.0"
                ).fetchone()[0]
                or 0
            )
            m["red_flag_rate"] = round(m["red_flag"] / scored, 4) if scored else 0
            fresh = (
                c.execute(
                    "SELECT COUNT(*) FROM knowledge_points WHERE review_status='confirmed'"
                    " AND is_outdated=0"
                ).fetchone()[0]
                or 0
            )
            m["freshness_rate"] = (
                round(fresh / m["confirmed"], 4) if m["confirmed"] else 1.0
            )
            m["outdated"] = (
                c.execute(
                    "SELECT COUNT(*) FROM knowledge_points WHERE is_outdated=1"
                ).fetchone()[0]
                or 0
            )
            ar = c.execute(
                "SELECT kp_sample_ids FROM audit_cycles ORDER BY created_at DESC LIMIT 1"
            ).fetchone()
            m["audit_cov"] = 0
            if ar and ar[0] and m["confirmed"]:
                try:
                    ids = json.loads(ar[0]) if isinstance(ar[0], str) else ar[0]
                    m["audit_cov"] = round(len(ids) / m["confirmed"], 4)
                except (json.JSONDecodeError, TypeError, AttributeError):
                    pass
            cx = (
                c.execute(
                    "SELECT COUNT(*) FROM qa_feedback WHERE feedback_type='helpful'"
                ).fetchone()[0]
                or 0
            )
            cn = (
                c.execute(
                    "SELECT COUNT(*) FROM qa_feedback WHERE feedback_type='not_helpful'"
                ).fetchone()[0]
                or 0
            )
            m["satisf_n"] = cx + cn
            m["satisf_rate"] = round(cx / m["satisf_n"], 4) if m["satisf_n"] else 0
        finally:
            conn.close()
        return m

    def production_metrics(self):
        """生产指标: KP产量、精品率、内容类型分布"""
        m = {}
        conn = self._conn()
        try:
            c = conn.cursor()
            m["total"] = (
                c.execute("SELECT COUNT(*) FROM knowledge_points").fetchone()[0] or 0
            )
            m["confirmed"] = (
                c.execute(
                    "SELECT COUNT(*) FROM knowledge_points WHERE review_status='confirmed'"
                ).fetchone()[0]
                or 0
            )
            m["pending"] = (
                c.execute(
                    "SELECT COUNT(*) FROM knowledge_points WHERE review_status='pending'"
                ).fetchone()[0]
                or 0
            )
            month_ago = (datetime.now() - timedelta(days=30)).isoformat()
            m["monthly"] = (
                c.execute(
                    "SELECT COUNT(*) FROM knowledge_points WHERE created_at >= ?",
                    (month_ago,),
                ).fetchone()[0]
                or 0
            )
            r = c.execute(
                "SELECT AVG(quality_score) FROM knowledge_points WHERE quality_score > 0"
            ).fetchone()
            m["avg_quality"] = round(r[0], 2) if r and r[0] else 0
            m["premium"] = (
                c.execute(
                    "SELECT COUNT(*) FROM knowledge_points WHERE premium_tier IS NOT NULL"
                ).fetchone()[0]
                or 0
            )
            tagged = (
                c.execute(
                    "SELECT COUNT(*) FROM knowledge_points WHERE review_status='confirmed'"
                    " AND target_reader IS NOT NULL AND target_reader!='[]' AND target_reader!=''"
                ).fetchone()[0]
                or 0
            )
            m["reader_tag_rate"] = (
                round(tagged / m["confirmed"], 4) if m["confirmed"] else 0
            )
            types = {}
            for row in c.execute(
                "SELECT content_type, COUNT(*) FROM knowledge_points"
                " WHERE review_status='confirmed' GROUP BY content_type"
            ).fetchall():
                types[row[0]] = row[1]
            m["content_types"] = types
        finally:
            conn.close()
        return m

    def agent_metrics(self):
        """Agent指标: 活跃度、调用次数、成本、僵尸Agent比例"""
        m = {}
        conn = self._conn()
        try:
            c = conn.cursor()
            m["total"] = (
                c.execute("SELECT COUNT(*) FROM agent_definitions").fetchone()[0] or 0
            )
            m["active"] = (
                c.execute(
                    "SELECT COUNT(*) FROM agent_definitions WHERE is_active=1"
                ).fetchone()[0]
                or 0
            )
            m["zombie"] = m["total"] - m["active"]
            m["zombie_rate"] = round(m["zombie"] / m["total"], 4) if m["total"] else 0
            month_ago = (datetime.now() - timedelta(days=30)).strftime("%Y-%m-%d")
            r = c.execute(
                "SELECT COUNT(*), COALESCE(SUM(estimated_cost),0) FROM api_call_logs"
                " WHERE call_date >= ?",
                (month_ago,),
            ).fetchone()
            m["api_calls_30d"] = r[0] or 0 if r else 0
            m["api_cost_30d"] = round(r[1], 4) if r else 0
            r = c.execute(
                "SELECT AVG(latency_ms) FROM qa_history"
                " WHERE latency_ms>0 AND created_at>=datetime('now','-30 days')"
            ).fetchone()
            m["avg_latency_ms"] = round(r[0], 0) if r and r[0] else 0
        finally:
            conn.close()
        return m

    def infrastructure_metrics(self):
        """基础设施指标: 健康评分、DB大小、待处理文件、系统错误"""
        m = {
            "db_mb": 0,
            "pending_files": 0,
            "health_score": 0,
            "err_7d": 0,
            "warn_7d": 0,
        }
        try:
            if os.path.exists(self._db_path):
                m["db_mb"] = round(os.path.getsize(self._db_path) / (1024 * 1024), 2)
            pd = PROJECT_ROOT / "data" / "pending"
            if pd.exists():
                m["pending_files"] = len(list(pd.glob("*")))
        except OSError:
            pass
        conn = self._conn()
        try:
            c = conn.cursor()
            r = c.execute(
                "SELECT total_score FROM health_reports ORDER BY created_at DESC LIMIT 1"
            ).fetchone()
            if r and r[0]:
                m["health_score"] = round(r[0], 2)
            m["err_7d"] = (
                c.execute(
                    "SELECT COUNT(*) FROM operation_events"
                    " WHERE severity='error' AND event_time>=datetime('now','-7 days')"
                ).fetchone()[0]
                or 0
            )
            m["warn_7d"] = (
                c.execute(
                    "SELECT COUNT(*) FROM operation_events"
                    " WHERE severity='warning' AND event_time>=datetime('now','-7 days')"
                ).fetchone()[0]
                or 0
            )
        finally:
            conn.close()
        return m

    def gap_vs_world_class(self):
        """对标世界级水平的差距报告"""
        q, a, wc = self.quality_metrics(), self.agent_metrics(), WORLD_CLASS
        gaps = {}
        for key, cur in [
            ("factual_error_rate", q.get("red_flag_rate", 0)),
            ("audit_coverage", q.get("audit_cov", 0)),
            ("freshness_rate", q.get("freshness_rate", 0)),
            ("csat", q.get("satisf_rate", 0)),
            ("agent_zombie_ratio", a.get("zombie_rate", 0)),
            ("red_flag_rate", q.get("red_flag_rate", 0)),
        ]:
            gap_val = round(cur - wc[key], 4)
            status = (
                "OK" if gap_val <= 0 else ("WARN" if gap_val < 0.10 else "CRITICAL")
            )
            gaps[key] = {
                "current": cur,
                "target": wc[key],
                "gap": gap_val,
                "status": status,
            }
        return gaps

    def report(self):
        """生成KPI报告(Markdown格式,可存入文件或发给CEO)。"""
        snap = self.snapshot()
        q, p, a, inf = (
            snap["quality"],
            snap["production"],
            snap["agents"],
            snap["infrastructure"],
        )
        gaps, ts = self.gap_vs_world_class(), datetime.now().strftime("%Y-%m-%d %H:%M")
        lines = [
            f"# KPI仪表盘 {ts}",
            "",
            "## 质量",
            f"- 审计覆盖率: {q.get('audit_cov',0):.1%} | QA均分: {q.get('avg_qa',0)}"
            f" | 红标率: {q.get('red_flag_rate',0):.1%} ({q.get('red_flag',0)}条)",
            f"- 保鲜率: {q.get('freshness_rate',0):.1%} | 过期KP: {q.get('outdated',0)}"
            f" | 满意度: {q.get('satisf_rate',0):.1%} (n={q.get('satisf_n',0)})",
            "",
            "## 生产",
            f"- KP: 总{p.get('total',0)}/确认{p.get('confirmed',0)}/待审{p.get('pending',0)}"
            f" | 月增: {p.get('monthly',0)} | 精品: {p.get('premium',0)}",
            f"- 平均质量分: {p.get('avg_quality',0)}"
            f" | 读者标签: {p.get('reader_tag_rate',0):.1%}"
            f" | 类型: {p.get('content_types',{})}",
            "",
            "## Agent",
            f"- 活跃/总计: {a.get('active',0)}/{a.get('total',0)}"
            f" | 僵死率: {a.get('zombie_rate',0):.1%} ({a.get('zombie',0)}个)",
            f"- 30天API: {a.get('api_calls_30d',0)}次/Y{a.get('api_cost_30d',0):.4f}"
            f" | 平均延迟: {a.get('avg_latency_ms',0):.0f}ms",
            "",
            "## 基础设施",
            f"- 健康分: {inf.get('health_score',0)} | DB: {inf.get('db_mb',0)}MB"
            f" | 待处理: {inf.get('pending_files',0)}",
            f"- 7天事件: {inf.get('err_7d',0)}错误/{inf.get('warn_7d',0)}警告",
            "",
            "## 对标世界级",
        ]
        for name, g in gaps.items():
            icon = (
                "OK"
                if g["status"] == "OK"
                else ("WARN" if g["status"] == "WARN" else "!!")
            )
            lines.append(
                f"- [{icon}] {name}: {g['current']:.1%} vs {g['target']:.1%}"
                f" (gap: {g['gap']:+.1%})"
            )
        if len(self._snapshots) >= 2:
            lines.append("\n## 趋势\n" + self._trends(snap, self._snapshots[-2]))
        return "\n".join(lines)

    def _trends(self, cur, prev):
        out = []
        for sec, label in [
            ("quality", "质量"),
            ("production", "生产"),
            ("agents", "Agent"),
        ]:
            for k, v in cur.get(sec, {}).items():
                if not isinstance(v, (int, float)):
                    continue
                pv = prev.get(sec, {}).get(k, v)
                if pv != v:
                    d = v - pv
                    out.append(
                        f"- {label}.{k}: {pv} -> {v} ({'+' if d>=0 else ''}{d:+.2f})"
                    )
        return "\n".join(out[:20])
