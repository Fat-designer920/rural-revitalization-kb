"""
db_manager.py - SQLite数据库管理模块
路径：scripts/db_manager.py
"""

import sqlite3
import os
import json
from datetime import datetime
from pathlib import Path

PROJECT_ROOT = Path(__file__).parent.parent


class DatabaseManager:

    def __init__(self, db_path=None):
        if db_path is None:
            config_path = PROJECT_ROOT / "config" / "settings.json"
            if config_path.exists():
                with open(config_path, "r", encoding="utf-8") as f:
                    config = json.load(f)
                db_path = config.get("database_path", "")
            if not db_path:
                db_path = str(PROJECT_ROOT / "data" / "database" / "knowledge_base.db")
        self.db_path = db_path
        os.makedirs(os.path.dirname(self.db_path), exist_ok=True)

    def get_connection(self):
        conn = sqlite3.connect(self.db_path)
        conn.row_factory = sqlite3.Row
        conn.execute("PRAGMA journal_mode=WAL")
        conn.execute("PRAGMA foreign_keys=ON")
        return conn

    def init_tables(self):
        conn = self.get_connection()
        c = conn.cursor()

        c.execute("""CREATE TABLE IF NOT EXISTS categories (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            level1_code TEXT NOT NULL, level1_name TEXT NOT NULL,
            level2_code TEXT NOT NULL, level2_name TEXT NOT NULL,
            level3_code TEXT DEFAULT NULL, level3_name TEXT DEFAULT NULL,
            description TEXT DEFAULT '', is_active INTEGER DEFAULT 1,
            created_at TEXT DEFAULT (datetime('now','localtime')),
            updated_at TEXT DEFAULT (datetime('now','localtime'))
        )""")

        c.execute("""CREATE TABLE IF NOT EXISTS source_files (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            original_filename TEXT NOT NULL, renamed_filename TEXT DEFAULT NULL,
            file_path TEXT NOT NULL, file_type TEXT NOT NULL,
            file_size INTEGER DEFAULT 0, file_hash TEXT DEFAULT NULL,
            domain_tags TEXT DEFAULT '[]', region_tag TEXT DEFAULT '',
            policy_level TEXT DEFAULT '',
            process_status TEXT DEFAULT 'pending'
                CHECK(process_status IN ('pending','processing','completed','failed')),
            process_message TEXT DEFAULT '',
            created_at TEXT DEFAULT (datetime('now','localtime')),
            updated_at TEXT DEFAULT (datetime('now','localtime'))
        )""")

        c.execute("""CREATE TABLE IF NOT EXISTS knowledge_points (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            source_file_id INTEGER NOT NULL,
            title TEXT NOT NULL,
            content_type TEXT NOT NULL CHECK(content_type IN ('policy','case','experience','tool','data')),
            original_excerpt TEXT DEFAULT '',
            ai_extracted_content TEXT DEFAULT '{}',
            suggested_category_id INTEGER DEFAULT NULL,
            final_category_id INTEGER DEFAULT NULL,
            suggested_tags TEXT DEFAULT '[]', final_tags TEXT DEFAULT '[]',
            source_page TEXT DEFAULT '', source_keyword TEXT DEFAULT '',
            review_status TEXT DEFAULT 'pending'
                CHECK(review_status IN ('pending','confirmed','ignored','merged')),
            reviewer_notes TEXT DEFAULT '',
            quality_score REAL DEFAULT 0.0,
            version INTEGER DEFAULT 1,
            is_outdated INTEGER DEFAULT 0, superseded_by INTEGER DEFAULT NULL,
            created_at TEXT DEFAULT (datetime('now','localtime')),
            updated_at TEXT DEFAULT (datetime('now','localtime')),
            confirmed_at TEXT DEFAULT NULL,
            FOREIGN KEY (source_file_id) REFERENCES source_files(id),
            FOREIGN KEY (suggested_category_id) REFERENCES categories(id),
            FOREIGN KEY (final_category_id) REFERENCES categories(id)
        )""")

        c.execute("""CREATE TABLE IF NOT EXISTS knowledge_versions (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            knowledge_point_id INTEGER NOT NULL, version INTEGER NOT NULL,
            content_snapshot TEXT NOT NULL, change_reason TEXT DEFAULT '',
            created_at TEXT DEFAULT (datetime('now','localtime')),
            FOREIGN KEY (knowledge_point_id) REFERENCES knowledge_points(id)
        )""")

        c.execute("""CREATE TABLE IF NOT EXISTS architecture_suggestions (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            suggested_name TEXT NOT NULL, suggested_level TEXT NOT NULL,
            parent_category_id INTEGER DEFAULT NULL,
            reason TEXT DEFAULT '', related_knowledge_ids TEXT DEFAULT '[]',
            status TEXT DEFAULT 'pending' CHECK(status IN ('pending','approved','rejected','deferred')),
            resolved_at TEXT DEFAULT NULL,
            created_at TEXT DEFAULT (datetime('now','localtime')),
            FOREIGN KEY (parent_category_id) REFERENCES categories(id)
        )""")

        c.execute("""CREATE TABLE IF NOT EXISTS operation_logs (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            operation_type TEXT NOT NULL, target_table TEXT DEFAULT '',
            target_id INTEGER DEFAULT NULL, details TEXT DEFAULT '{}',
            created_at TEXT DEFAULT (datetime('now','localtime'))
        )""")

        c.execute("""CREATE TABLE IF NOT EXISTS api_call_logs (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            call_type TEXT NOT NULL, model TEXT DEFAULT '',
            input_tokens INTEGER DEFAULT 0, output_tokens INTEGER DEFAULT 0,
            estimated_cost REAL DEFAULT 0.0,
            call_date TEXT DEFAULT (date('now','localtime')),
            created_at TEXT DEFAULT (datetime('now','localtime'))
        )""")

        c.execute("""CREATE TABLE IF NOT EXISTS notion_sync_log (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            knowledge_point_id INTEGER NOT NULL,
            notion_page_id TEXT DEFAULT NULL,
            sync_status TEXT DEFAULT 'pending' CHECK(sync_status IN ('pending','synced','failed','conflict')),
            last_synced_at TEXT DEFAULT NULL, error_message TEXT DEFAULT '',
            created_at TEXT DEFAULT (datetime('now','localtime')),
            FOREIGN KEY (knowledge_point_id) REFERENCES knowledge_points(id)
        )""")

        c.execute("CREATE INDEX IF NOT EXISTS idx_kp_status ON knowledge_points(review_status)")
        c.execute("CREATE INDEX IF NOT EXISTS idx_kp_type ON knowledge_points(content_type)")
        c.execute("CREATE INDEX IF NOT EXISTS idx_kp_source ON knowledge_points(source_file_id)")
        c.execute("CREATE INDEX IF NOT EXISTS idx_sf_status ON source_files(process_status)")
        c.execute("CREATE INDEX IF NOT EXISTS idx_api_date ON api_call_logs(call_date)")

        conn.commit()
        conn.close()
        return True

    def init_default_categories(self):
        conn = self.get_connection()
        c = conn.cursor()
        c.execute("SELECT COUNT(*) as cnt FROM categories")
        if c.fetchone()["cnt"] > 0:
            conn.close()
            return True

        cats = [
            ("1","政策库","1.1","全域土地综合整治政策","国家/省/市层面综合整治专项政策"),
            ("1","政策库","1.2","增减挂钩与占补平衡","城乡建设用地增减挂钩、耕地占补平衡相关政策"),
            ("1","政策库","1.3","集体经营性建设用地入市","入市规则、定价机制、收益分配、试点政策"),
            ("1","政策库","1.4","专项债与资金政策","地方政府专项债、涉农资金整合、EPC打捆招标等"),
            ("1","政策库","1.5","川西林盘保护政策","林盘保护修复专项政策、生态保护相关法规"),
            ("1","政策库","1.6","乡村振兴综合政策","跨领域综合政策、五年规划、考核标准等"),
            ("1","政策库","1.7","自然资源与规划政策","国土空间规划、用途管制、耕地保护等底层法规"),
            ("2","案例库","2.1","全域土地综合整治项目","完整项目案例（含背景、策略、资金、成效）"),
            ("2","案例库","2.2","增减挂钩项目","指标交易类项目案例"),
            ("2","案例库","2.3","川西林盘修复运营项目","林盘保护修复+运营类项目案例"),
            ("2","案例库","2.4","资金整合与融资创新案例","专项债申报、EPC打捆、资金拼盘等融资案例"),
            ("2","案例库","2.5","乡村产业与运营案例","民宿、农旅、集体经济运营等产业端案例"),
            ("2","案例库","2.6","失败与风险案例","踩坑项目、烂尾项目、政策风险暴露案例"),
            ("3","经验库","3.1","策略判断类","选址逻辑、项目类型选择、合作模式判断等"),
            ("3","经验库","3.2","操盘方法类","资金拼盘方法、报批流程优化、多部门协调等"),
            ("3","经验库","3.3","反常识洞察","与行业常规认知相反但经实战验证的判断"),
            ("3","经验库","3.4","踩坑记录","具体失误及教训，含当时决策背景和事后复盘"),
            ("3","经验库","3.5","客户沟通与汇报经验","面向政府领导、平台公司的汇报话术经验"),
            ("4","工具库","4.1","方案模板","可研报告、实施方案、策划方案等模板"),
            ("4","工具库","4.2","合同模板","咨询合同、EPC合同、合作框架协议等"),
            ("4","工具库","4.3","评审意见模板","方案评审、项目验收等评审意见范本"),
            ("4","工具库","4.4","招标文件模板","招标公告、评标标准、技术要求等"),
            ("4","工具库","4.5","汇报材料模板","PPT框架、汇报提纲、领导讲话稿等"),
            ("4","工具库","4.6","申报材料模板","专项债申报、试点申报、资金申请等"),
            ("5","数据库","5.1","资金测算数据","各类项目资金测算模型、单价参考、费用构成"),
            ("5","数据库","5.2","指标数据","增减挂钩指标价格、占补平衡指标、各地交易数据"),
            ("5","数据库","5.3","地方政策对比","不同省/市的政策差异对比"),
            ("5","数据库","5.4","项目规模与成效数据","各地项目面积、投资额、产出数据等"),
            ("5","数据库","5.5","行业基准数据","亩均投资、建设周期、收益率等行业参考值"),
        ]
        for cat in cats:
            c.execute("INSERT INTO categories (level1_code,level1_name,level2_code,level2_name,description) VALUES (?,?,?,?,?)", cat)
        conn.commit()
        conn.close()
        return True

    # === 文件操作 ===
    def add_source_file(self, original_filename, file_path, file_type, file_size=0, file_hash=None):
        conn = self.get_connection()
        c = conn.cursor()
        c.execute("INSERT INTO source_files (original_filename,file_path,file_type,file_size,file_hash) VALUES (?,?,?,?,?)",
                  (original_filename, file_path, file_type, file_size, file_hash))
        fid = c.lastrowid
        conn.commit(); conn.close()
        return fid

    def update_source_file(self, file_id, **kw):
        conn = self.get_connection()
        c = conn.cursor()
        allowed = ["renamed_filename","domain_tags","region_tag","policy_level","process_status","process_message"]
        sets, vals = [], []
        for k, v in kw.items():
            if k in allowed:
                sets.append(f"{k}=?"); vals.append(v)
        if sets:
            sets.append("updated_at=datetime('now','localtime')")
            vals.append(file_id)
            c.execute(f"UPDATE source_files SET {','.join(sets)} WHERE id=?", vals)
            conn.commit()
        conn.close()

    def get_source_file(self, file_id):
        conn = self.get_connection()
        c = conn.cursor()
        c.execute("SELECT * FROM source_files WHERE id=?", (file_id,))
        r = c.fetchone(); conn.close()
        return dict(r) if r else None

    # === 知识点操作 ===
    def add_knowledge_point(self, source_file_id, title, content_type, original_excerpt="",
                            ai_extracted_content=None, suggested_category_id=None,
                            suggested_tags=None, source_page="", source_keyword=""):
        conn = self.get_connection()
        c = conn.cursor()
        c.execute("""INSERT INTO knowledge_points (source_file_id,title,content_type,original_excerpt,
            ai_extracted_content,suggested_category_id,suggested_tags,source_page,source_keyword)
            VALUES (?,?,?,?,?,?,?,?,?)""",
            (source_file_id, title, content_type, original_excerpt,
             json.dumps(ai_extracted_content or {}, ensure_ascii=False),
             suggested_category_id,
             json.dumps(suggested_tags or [], ensure_ascii=False),
             source_page, source_keyword))
        kid = c.lastrowid
        conn.commit(); conn.close()
        return kid

    def get_all_knowledge_points(self, review_status=None, content_type=None, category_id=None, page=1, per_page=20):
        conn = self.get_connection()
        c = conn.cursor()
        where, params = ["1=1"], []
        if review_status:
            where.append("kp.review_status=?"); params.append(review_status)
        if content_type:
            where.append("kp.content_type=?"); params.append(content_type)
        if category_id:
            where.append("(kp.suggested_category_id=? OR kp.final_category_id=?)"); params.extend([category_id, category_id])
        w = " AND ".join(where)
        offset = (page - 1) * per_page

        c.execute(f"SELECT COUNT(*) as cnt FROM knowledge_points kp WHERE {w}", params)
        total = c.fetchone()["cnt"]

        c.execute(f"""SELECT kp.*, sf.original_filename, sf.renamed_filename, sf.file_path,
            cat.level1_name, cat.level2_name, cat.level2_code
            FROM knowledge_points kp
            LEFT JOIN source_files sf ON kp.source_file_id=sf.id
            LEFT JOIN categories cat ON COALESCE(kp.final_category_id, kp.suggested_category_id)=cat.id
            WHERE {w} ORDER BY kp.created_at DESC LIMIT ? OFFSET ?""",
            params + [per_page, offset])
        rows = [dict(r) for r in c.fetchall()]
        conn.close()
        return {"items": rows, "total": total, "page": page, "per_page": per_page}

    def get_knowledge_point(self, kp_id):
        conn = self.get_connection()
        c = conn.cursor()
        c.execute("""SELECT kp.*, sf.original_filename, sf.renamed_filename, sf.file_path,
            cat.level1_name, cat.level2_name, cat.level2_code
            FROM knowledge_points kp
            LEFT JOIN source_files sf ON kp.source_file_id=sf.id
            LEFT JOIN categories cat ON COALESCE(kp.final_category_id, kp.suggested_category_id)=cat.id
            WHERE kp.id=?""", (kp_id,))
        r = c.fetchone(); conn.close()
        return dict(r) if r else None

    def update_knowledge_point(self, kp_id, **kw):
        conn = self.get_connection()
        c = conn.cursor()
        allowed = ["title","original_excerpt","ai_extracted_content","final_category_id",
                    "final_tags","review_status","reviewer_notes","quality_score","is_outdated","superseded_by"]
        sets, vals = [], []
        for k, v in kw.items():
            if k in allowed:
                sets.append(f"{k}=?")
                if k in ("ai_extracted_content","final_tags") and isinstance(v, (dict, list)):
                    vals.append(json.dumps(v, ensure_ascii=False))
                else:
                    vals.append(v)
        if sets:
            sets.append("updated_at=datetime('now','localtime')")
            if kw.get("review_status") == "confirmed":
                sets.append("confirmed_at=datetime('now','localtime')")
            vals.append(kp_id)
            c.execute(f"UPDATE knowledge_points SET {','.join(sets)} WHERE id=?", vals)
            conn.commit()
        conn.close()

    def confirm_knowledge_point(self, kp_id, final_category_id=None, final_tags=None, reviewer_notes=""):
        kw = {"review_status": "confirmed"}
        if final_category_id is not None: kw["final_category_id"] = final_category_id
        if final_tags is not None: kw["final_tags"] = final_tags
        if reviewer_notes: kw["reviewer_notes"] = reviewer_notes
        self.update_knowledge_point(kp_id, **kw)
        self.log_operation("confirm", "knowledge_points", kp_id)

    def ignore_knowledge_point(self, kp_id, reason=""):
        self.update_knowledge_point(kp_id, review_status="ignored", reviewer_notes=reason)
        self.log_operation("ignore", "knowledge_points", kp_id)

    # === 分类 ===
    def get_all_categories(self, active_only=True):
        conn = self.get_connection()
        c = conn.cursor()
        w = "WHERE is_active=1" if active_only else ""
        c.execute(f"SELECT * FROM categories {w} ORDER BY level1_code, level2_code")
        rows = [dict(r) for r in c.fetchall()]; conn.close()
        return rows

    def get_categories_tree(self):
        cats = self.get_all_categories()
        tree = {}
        for cat in cats:
            l1 = cat["level1_name"]
            if l1 not in tree:
                tree[l1] = {"code": cat["level1_code"], "children": []}
            tree[l1]["children"].append({"id": cat["id"], "code": cat["level2_code"],
                "name": cat["level2_name"], "description": cat["description"]})
        return tree

    def find_category_by_code(self, level2_code):
        conn = self.get_connection()
        c = conn.cursor()
        c.execute("SELECT * FROM categories WHERE level2_code=? AND is_active=1", (level2_code,))
        r = c.fetchone(); conn.close()
        return dict(r) if r else None

    # === API调用记录 ===
    def log_api_call(self, call_type, model, input_tokens, output_tokens, estimated_cost):
        conn = self.get_connection()
        c = conn.cursor()
        c.execute("INSERT INTO api_call_logs (call_type,model,input_tokens,output_tokens,estimated_cost) VALUES (?,?,?,?,?)",
                  (call_type, model, input_tokens, output_tokens, estimated_cost))
        conn.commit(); conn.close()

    def get_today_api_cost(self):
        conn = self.get_connection()
        c = conn.cursor()
        today = datetime.now().strftime("%Y-%m-%d")
        c.execute("SELECT COALESCE(SUM(estimated_cost),0) as tc FROM api_call_logs WHERE call_date=?", (today,))
        r = c.fetchone(); conn.close()
        return r["tc"]

    # === 日志 ===
    def log_operation(self, op_type, target_table="", target_id=None, details=None):
        conn = self.get_connection()
        c = conn.cursor()
        c.execute("INSERT INTO operation_logs (operation_type,target_table,target_id,details) VALUES (?,?,?,?)",
                  (op_type, target_table, target_id, json.dumps(details or {}, ensure_ascii=False)))
        conn.commit(); conn.close()

    # === 统计 ===
    def get_statistics(self):
        conn = self.get_connection()
        c = conn.cursor()
        stats = {}
        c.execute("SELECT process_status, COUNT(*) as cnt FROM source_files GROUP BY process_status")
        stats["files"] = {r["process_status"]: r["cnt"] for r in c.fetchall()}
        c.execute("SELECT review_status, COUNT(*) as cnt FROM knowledge_points GROUP BY review_status")
        stats["knowledge_points"] = {r["review_status"]: r["cnt"] for r in c.fetchall()}
        c.execute("SELECT content_type, COUNT(*) as cnt FROM knowledge_points WHERE review_status='confirmed' GROUP BY content_type")
        stats["by_type"] = {r["content_type"]: r["cnt"] for r in c.fetchall()}
        stats["today_api_cost"] = self.get_today_api_cost()
        c.execute("SELECT COUNT(*) as cnt FROM knowledge_points WHERE review_status='confirmed'")
        stats["total_confirmed"] = c.fetchone()["cnt"]
        c.execute("SELECT COUNT(*) as cnt FROM knowledge_points WHERE review_status='pending'")
        stats["total_pending"] = c.fetchone()["cnt"]
        conn.close()
        return stats
