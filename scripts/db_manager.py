"""
db_manager.py - SQLite数据库管理模块
路径：scripts/db_manager.py
版本：v2.1.1 F039 - 新增duplicate_groups表+重复检测CRUD

数据库表（14张）：
  categories - 知识库分类体系（5大类27+子类）
  source_files - 原始文件记录
  knowledge_points - 知识点（核心表，v2.0.0新增多个字段）
  knowledge_versions - 知识点版本快照（预留）
  architecture_suggestions - AI分类建议
  edit_history - 编辑历史记录
  tag_definitions - 标签定义表（v2.0.0新增）
  knowledge_relations - 知识关联表（v2.0.0新增）
  knowledge_usage_log - 使用追踪表（v2.0.0新增）
  tag_statistics - 标签统计缓存（v2.0.0新增）
  operation_logs - 操作日志
  api_call_logs - API调用日志
  notion_sync_log - Notion同步日志（预留）
  duplicate_groups - 重复检测结果（v2.1.1 F039新增）
"""
import sqlite3, os, json
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

    # ================================================================
    # 建表
    # ================================================================
    def init_tables(self):
        conn = self.get_connection(); c = conn.cursor()
        # --- 分类体系 ---
        c.execute("""CREATE TABLE IF NOT EXISTS categories (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            level1_code TEXT NOT NULL, level1_name TEXT NOT NULL,
            level2_code TEXT NOT NULL, level2_name TEXT NOT NULL,
            level3_code TEXT DEFAULT NULL, level3_name TEXT DEFAULT NULL,
            description TEXT DEFAULT '', is_active INTEGER DEFAULT 1,
            created_at TEXT DEFAULT (datetime('now','localtime')),
            updated_at TEXT DEFAULT (datetime('now','localtime')))""")
        # --- 原始文件 ---
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
            updated_at TEXT DEFAULT (datetime('now','localtime')))""")
        # --- 知识点（核心表） ---
        c.execute("""CREATE TABLE IF NOT EXISTS knowledge_points (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            source_file_id INTEGER NOT NULL,
            title TEXT NOT NULL,
            content_type TEXT NOT NULL CHECK(content_type IN ('policy','case','experience','tool','data')),
            original_excerpt TEXT DEFAULT '',
            ai_extracted_content TEXT DEFAULT '{}',
            -- 分类体系（保留原有，与标签并行）
            suggested_category_id INTEGER DEFAULT NULL,
            final_category_id INTEGER DEFAULT NULL,
            -- 第一层：分类标签（从41个固定标签中选）
            suggested_category_tags TEXT DEFAULT '[]',
            final_category_tags TEXT DEFAULT '[]',
            -- 第二层：属性标签（key=维度,value=值）
            suggested_attribute_tags TEXT DEFAULT '{}',
            final_attribute_tags TEXT DEFAULT '{}',
            -- 第三层：关键词（自由提取）
            suggested_keywords TEXT DEFAULT '[]',
            final_keywords TEXT DEFAULT '[]',
            -- 旧字段保留兼容（迁移后数据会转入上面的新字段）
            suggested_tags TEXT DEFAULT '[]',
            final_tags TEXT DEFAULT '[]',
            -- 元数据
            source_page TEXT DEFAULT '',
            source_keyword TEXT DEFAULT '',
            review_status TEXT DEFAULT 'pending'
                CHECK(review_status IN ('pending','confirmed','ignored','merged')),
            reviewer_notes TEXT DEFAULT '',
            quality_score REAL DEFAULT 0.0,
            version INTEGER DEFAULT 1,
            is_outdated INTEGER DEFAULT 0,
            superseded_by INTEGER DEFAULT NULL,
            -- v2.0.0 新增字段
            content_readiness TEXT DEFAULT 'draft'
                CHECK(content_readiness IN ('draft','quotable','premium')),
            source_authority TEXT DEFAULT 'firsthand'
                CHECK(source_authority IN ('official','authoritative','firsthand','informal')),
            access_level TEXT DEFAULT 'open'
                CHECK(access_level IN ('open','standard','premium')),
            freshness_checked_at TEXT DEFAULT NULL,
            freshness_interval_days INTEGER DEFAULT 180,
            -- 时间戳
            created_at TEXT DEFAULT (datetime('now','localtime')),
            updated_at TEXT DEFAULT (datetime('now','localtime')),
            confirmed_at TEXT DEFAULT NULL,
            FOREIGN KEY (source_file_id) REFERENCES source_files(id),
            FOREIGN KEY (suggested_category_id) REFERENCES categories(id),
            FOREIGN KEY (final_category_id) REFERENCES categories(id))""")
        # --- 知识版本快照（预留） ---
        c.execute("""CREATE TABLE IF NOT EXISTS knowledge_versions (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            knowledge_point_id INTEGER NOT NULL, version INTEGER NOT NULL,
            content_snapshot TEXT NOT NULL, change_reason TEXT DEFAULT '',
            created_at TEXT DEFAULT (datetime('now','localtime')),
            FOREIGN KEY (knowledge_point_id) REFERENCES knowledge_points(id))""")
        # --- AI分类建议 ---
        c.execute("""CREATE TABLE IF NOT EXISTS architecture_suggestions (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            suggested_name TEXT NOT NULL, suggested_level TEXT NOT NULL,
            parent_category_id INTEGER DEFAULT NULL,
            suggestion_type TEXT DEFAULT 'add_level2',
            reason TEXT DEFAULT '', related_knowledge_ids TEXT DEFAULT '[]',
            status TEXT DEFAULT 'pending' CHECK(status IN ('pending','approved','rejected','deferred')),
            resolved_at TEXT DEFAULT NULL,
            created_at TEXT DEFAULT (datetime('now','localtime')),
            FOREIGN KEY (parent_category_id) REFERENCES categories(id))""")
        # --- 编辑历史 ---
        c.execute("""CREATE TABLE IF NOT EXISTS edit_history (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            knowledge_point_id INTEGER NOT NULL,
            edited_fields TEXT NOT NULL DEFAULT '{}',
            edit_summary TEXT DEFAULT '',
            created_at TEXT DEFAULT (datetime('now','localtime')),
            FOREIGN KEY (knowledge_point_id) REFERENCES knowledge_points(id))""")
        # --- v2.0.0 标签定义表 ---
        c.execute("""CREATE TABLE IF NOT EXISTS tag_definitions (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            layer TEXT NOT NULL CHECK(layer IN ('layer1','layer2')),
            group_code TEXT NOT NULL,
            group_name TEXT NOT NULL,
            tag_code TEXT NOT NULL,
            tag_name TEXT NOT NULL,
            tag_definition TEXT DEFAULT '',
            is_active INTEGER DEFAULT 1,
            sort_order INTEGER DEFAULT 0,
            created_at TEXT DEFAULT (datetime('now','localtime')))""")
        # --- v2.0.0 知识关联表 ---
        c.execute("""CREATE TABLE IF NOT EXISTS knowledge_relations (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            source_kp_id INTEGER NOT NULL,
            target_kp_id INTEGER NOT NULL,
            relation_type TEXT NOT NULL
                CHECK(relation_type IN ('supports','contradicts','same_source','prerequisite','updated_by','related')),
            created_by TEXT DEFAULT 'manual' CHECK(created_by IN ('ai','manual')),
            created_at TEXT DEFAULT (datetime('now','localtime')),
            FOREIGN KEY (source_kp_id) REFERENCES knowledge_points(id),
            FOREIGN KEY (target_kp_id) REFERENCES knowledge_points(id))""")
        # --- v2.0.0 使用追踪表 ---
        c.execute("""CREATE TABLE IF NOT EXISTS knowledge_usage_log (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            knowledge_point_id INTEGER NOT NULL,
            usage_type TEXT NOT NULL CHECK(usage_type IN ('article','course','qa','proposal','export','other')),
            usage_context TEXT DEFAULT '',
            created_at TEXT DEFAULT (datetime('now','localtime')),
            FOREIGN KEY (knowledge_point_id) REFERENCES knowledge_points(id))""")
        # --- v2.0.0 标签统计缓存 ---
        c.execute("""CREATE TABLE IF NOT EXISTS tag_statistics (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            tag_name TEXT NOT NULL,
            layer TEXT NOT NULL,
            usage_count INTEGER DEFAULT 0,
            last_updated TEXT DEFAULT (datetime('now','localtime')))""")
        # --- 操作日志 ---
        c.execute("""CREATE TABLE IF NOT EXISTS operation_logs (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            operation_type TEXT NOT NULL, target_table TEXT DEFAULT '',
            target_id INTEGER DEFAULT NULL, details TEXT DEFAULT '{}',
            created_at TEXT DEFAULT (datetime('now','localtime')))""")
        # --- API调用日志 ---
        c.execute("""CREATE TABLE IF NOT EXISTS api_call_logs (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            call_type TEXT NOT NULL, model TEXT DEFAULT '',
            input_tokens INTEGER DEFAULT 0, output_tokens INTEGER DEFAULT 0,
            estimated_cost REAL DEFAULT 0.0,
            call_date TEXT DEFAULT (date('now','localtime')),
            created_at TEXT DEFAULT (datetime('now','localtime')))""")
        # --- Notion同步日志（预留） ---
        c.execute("""CREATE TABLE IF NOT EXISTS notion_sync_log (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            knowledge_point_id INTEGER NOT NULL,
            notion_page_id TEXT DEFAULT NULL,
            sync_status TEXT DEFAULT 'pending' CHECK(sync_status IN ('pending','synced','failed','conflict')),
            last_synced_at TEXT DEFAULT NULL, error_message TEXT DEFAULT '',
            created_at TEXT DEFAULT (datetime('now','localtime')),
            FOREIGN KEY (knowledge_point_id) REFERENCES knowledge_points(id))""")
        # --- v2.1.1 F039 重复检测结果 ---
        c.execute("""CREATE TABLE IF NOT EXISTS duplicate_groups (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            member_ids TEXT NOT NULL,
            relation_type TEXT DEFAULT NULL,
            ai_judgment TEXT DEFAULT '{}',
            similarity_score REAL DEFAULT 0,
            status TEXT DEFAULT 'pending'
                CHECK(status IN ('pending','resolved','dismissed')),
            created_at TEXT DEFAULT (datetime('now','localtime')),
            resolved_at TEXT DEFAULT NULL,
            resolved_action TEXT DEFAULT ''
        )""")
        # --- 索引 ---
        for idx in [
            "CREATE INDEX IF NOT EXISTS idx_kp_status ON knowledge_points(review_status)",
            "CREATE INDEX IF NOT EXISTS idx_kp_type ON knowledge_points(content_type)",
            "CREATE INDEX IF NOT EXISTS idx_kp_source ON knowledge_points(source_file_id)",
            "CREATE INDEX IF NOT EXISTS idx_kp_readiness ON knowledge_points(content_readiness)",
            "CREATE INDEX IF NOT EXISTS idx_kp_access ON knowledge_points(access_level)",
            "CREATE INDEX IF NOT EXISTS idx_sf_status ON source_files(process_status)",
            "CREATE INDEX IF NOT EXISTS idx_sf_hash ON source_files(file_hash)",
            "CREATE INDEX IF NOT EXISTS idx_api_date ON api_call_logs(call_date)",
            "CREATE INDEX IF NOT EXISTS idx_eh_kpid ON edit_history(knowledge_point_id)",
            "CREATE INDEX IF NOT EXISTS idx_td_layer ON tag_definitions(layer, group_code)",
            "CREATE INDEX IF NOT EXISTS idx_kr_source ON knowledge_relations(source_kp_id)",
            "CREATE INDEX IF NOT EXISTS idx_kr_target ON knowledge_relations(target_kp_id)",
            "CREATE INDEX IF NOT EXISTS idx_kul_kpid ON knowledge_usage_log(knowledge_point_id)",
            "CREATE INDEX IF NOT EXISTS idx_dg_status ON duplicate_groups(status)",
        ]:
            c.execute(idx)
        conn.commit(); conn.close(); return True

    # ================================================================
    # 默认分类
    # ================================================================
    def init_default_categories(self):
        conn = self.get_connection(); c = conn.cursor()
        c.execute("SELECT COUNT(*) as cnt FROM categories")
        if c.fetchone()["cnt"] > 0: conn.close(); return True
        cats = [
            ("1","政策库","1.1","全域土地综合整治政策","国家/省/市层面综合整治专项政策"),
            ("1","政策库","1.2","增减挂钩与占补平衡","城乡建设用地增减挂钩、耕地占补平衡相关政策"),
            ("1","政策库","1.3","集体经营性建设用地入市","入市规则、定价机制、收益分配、试点政策"),
            ("1","政策库","1.4","专项债与资金政策","地方政府专项债、涉农资金整合、EPC打捆招标等"),
            ("1","政策库","1.5","川西林盘保护政策","林盘保护修复专项政策、生态保护相关法规"),
            ("1","政策库","1.6","乡村振兴综合政策","跨领域综合政策、五年规划、考核标准等"),
            ("1","政策库","1.7","自然资源与规划政策","国土空间规划、用途管制、耕地保护等底层法规"),
            ("2","案例库","2.1","全域土地综合整治项目","完整项目案例"),
            ("2","案例库","2.2","增减挂钩项目","指标交易类项目案例"),
            ("2","案例库","2.3","川西林盘修复运营项目","林盘保护修复+运营类项目案例"),
            ("2","案例库","2.4","资金整合与融资创新案例","专项债申报、EPC打捆、资金拼盘等"),
            ("2","案例库","2.5","乡村产业与运营案例","民宿、农旅、集体经济运营等"),
            ("2","案例库","2.6","失败与风险案例","踩坑项目、烂尾项目、政策风险暴露案例"),
            ("3","经验库","3.1","策略判断类","选址逻辑、项目类型选择、合作模式判断等"),
            ("3","经验库","3.2","操盘方法类","资金拼盘方法、报批流程优化、多部门协调等"),
            ("3","经验库","3.3","反常识洞察","与行业常规认知相反但经实战验证的判断"),
            ("3","经验库","3.4","踩坑记录","具体失误及教训"),
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
            ("5","数据库","5.5","行业基准数据","亩均投资、建设周期、收益率等行业参考值")]
        for cat in cats:
            c.execute("INSERT INTO categories (level1_code,level1_name,level2_code,level2_name,description) VALUES (?,?,?,?,?)", cat)
        conn.commit(); conn.close(); return True

    # ================================================================
    # 标签定义初始化（从tag_config.py同步到数据库）
    # ================================================================
    def init_tag_definitions(self):
        """将tag_config.py中的标签定义同步到tag_definitions表"""
        try:
            from scripts.tag_config import LAYER1_TAGS, LAYER2_DIMENSIONS
        except ImportError:
            from tag_config import LAYER1_TAGS, LAYER2_DIMENSIONS
        conn = self.get_connection(); c = conn.cursor()
        c.execute("SELECT COUNT(*) as cnt FROM tag_definitions")
        if c.fetchone()["cnt"] > 0:
            conn.close(); return True  # 已初始化过
        sort = 0
        for group_code, group in LAYER1_TAGS.items():
            for tag in group["tags"]:
                sort += 1
                c.execute("""INSERT INTO tag_definitions (layer,group_code,group_name,tag_code,tag_name,tag_definition,sort_order)
                    VALUES (?,?,?,?,?,?,?)""",
                    ("layer1", group_code, group["group_name"], tag["code"], tag["name"], tag["definition"], sort))
        for dim_code, dim in LAYER2_DIMENSIONS.items():
            for val in dim.get("values", []):
                sort += 1
                c.execute("""INSERT INTO tag_definitions (layer,group_code,group_name,tag_code,tag_name,tag_definition,sort_order)
                    VALUES (?,?,?,?,?,?,?)""",
                    ("layer2", dim_code, dim["name"], dim_code, val, "", sort))
        conn.commit(); conn.close(); return True

    # ================================================================
    # 文件管理
    # ================================================================
    def add_source_file(self, original_filename, file_path, file_type, file_size=0, file_hash=None):
        conn = self.get_connection(); c = conn.cursor()
        c.execute("INSERT INTO source_files (original_filename,file_path,file_type,file_size,file_hash) VALUES (?,?,?,?,?)",
                  (original_filename, file_path, file_type, file_size, file_hash))
        fid = c.lastrowid; conn.commit(); conn.close(); return fid

    def update_source_file(self, file_id, **kw):
        conn = self.get_connection(); c = conn.cursor()
        allowed = ["renamed_filename","domain_tags","region_tag","policy_level","process_status","process_message","file_hash",
                    "pre_analysis_result","suggested_content_type","segment_plan"]
        sets, vals = [], []
        for k, v in kw.items():
            if k in allowed: sets.append(f"{k}=?"); vals.append(v)
        if sets:
            sets.append("updated_at=datetime('now','localtime')"); vals.append(file_id)
            c.execute(f"UPDATE source_files SET {','.join(sets)} WHERE id=?", vals); conn.commit()
        conn.close()

    def get_source_file(self, file_id):
        conn = self.get_connection(); c = conn.cursor()
        c.execute("SELECT * FROM source_files WHERE id=?", (file_id,))
        r = c.fetchone(); conn.close(); return dict(r) if r else None

    def check_file_hash_exists(self, file_hash):
        if not file_hash: return None
        conn = self.get_connection(); c = conn.cursor()
        c.execute("SELECT id, original_filename, renamed_filename, process_status, process_message FROM source_files WHERE file_hash=? ORDER BY created_at DESC LIMIT 1", (file_hash,))
        r = c.fetchone(); conn.close(); return dict(r) if r else None

    # ================================================================
    # 知识点管理
    # ================================================================
    def add_knowledge_point(self, source_file_id, title, content_type, original_excerpt="",
                            ai_extracted_content=None, suggested_category_id=None,
                            suggested_category_tags=None, suggested_attribute_tags=None,
                            suggested_keywords=None,
                            suggested_tags=None,  # 旧字段兼容
                            source_page="", source_keyword="",
                            content_readiness="draft", source_authority="firsthand",
                            prompt_version="",
                            practical_insights=None):
        conn = self.get_connection(); c = conn.cursor()
        c.execute("""INSERT INTO knowledge_points
            (source_file_id, title, content_type, original_excerpt, ai_extracted_content,
             suggested_category_id, suggested_category_tags, suggested_attribute_tags,
             suggested_keywords, suggested_tags, source_page, source_keyword,
             content_readiness, source_authority, prompt_version, practical_insights)
            VALUES (?,?,?,?,?, ?,?,?,?,?, ?,?,?,?,?, ?)""",
            (source_file_id, title, content_type, original_excerpt,
             json.dumps(ai_extracted_content or {}, ensure_ascii=False),
             suggested_category_id,
             json.dumps(suggested_category_tags or [], ensure_ascii=False),
             json.dumps(suggested_attribute_tags or {}, ensure_ascii=False),
             json.dumps(suggested_keywords or [], ensure_ascii=False),
             json.dumps(suggested_tags or [], ensure_ascii=False),
             source_page, source_keyword,
             content_readiness, source_authority, prompt_version,
             json.dumps(practical_insights or [], ensure_ascii=False)))
        kid = c.lastrowid; conn.commit(); conn.close(); return kid

    def get_all_knowledge_points(self, review_status=None, content_type=None,
                                 category_id=None, level1_code=None,
                                 search_query=None, content_readiness=None,
                                 freshness_filter=None, policy_filter=None,
                                 page=1, per_page=20):
        conn = self.get_connection(); c = conn.cursor()
        where, params = ["1=1"], []
        if review_status: where.append("kp.review_status=?"); params.append(review_status)
        if content_type: where.append("kp.content_type=?"); params.append(content_type)
        if content_readiness: where.append("kp.content_readiness=?"); params.append(content_readiness)
        if category_id:
            where.append("(kp.suggested_category_id=? OR kp.final_category_id=?)")
            params.extend([category_id, category_id])
        elif level1_code:
            where.append("""(kp.suggested_category_id IN (SELECT id FROM categories WHERE level1_code=?)
                            OR kp.final_category_id IN (SELECT id FROM categories WHERE level1_code=?))""")
            params.extend([level1_code, level1_code])
        if search_query:
            sq = f"%{search_query}%"
            where.append("""(kp.title LIKE ? OR kp.original_excerpt LIKE ? OR kp.ai_extracted_content LIKE ?
                            OR kp.suggested_keywords LIKE ? OR kp.final_keywords LIKE ?
                            OR kp.suggested_category_tags LIKE ? OR kp.final_category_tags LIKE ?
                            OR kp.suggested_tags LIKE ? OR kp.final_tags LIKE ?)""")
            params.extend([sq]*9)
        # v2.1.0-d: 保鲜状态筛选
        if freshness_filter:
            if freshness_filter == "expired":
                # 已过期：已确认 + 非过时 + 超过保鲜周期
                where.append("""kp.review_status='confirmed' AND kp.is_outdated=0
                    AND kp.freshness_checked_at IS NOT NULL
                    AND julianday('now','localtime') - julianday(kp.freshness_checked_at) > kp.freshness_interval_days""")
            elif freshness_filter == "expiring_soon":
                # 即将到期：已确认 + 非过时 + 剩余不到30天
                where.append("""kp.review_status='confirmed' AND kp.is_outdated=0
                    AND kp.freshness_checked_at IS NOT NULL
                    AND julianday('now','localtime') - julianday(kp.freshness_checked_at) > (kp.freshness_interval_days - 30)
                    AND julianday('now','localtime') - julianday(kp.freshness_checked_at) <= kp.freshness_interval_days""")
            elif freshness_filter == "fresh":
                # 新鲜：已确认 + 非过时 + 在保鲜周期内
                where.append("""kp.review_status='confirmed' AND kp.is_outdated=0
                    AND kp.freshness_checked_at IS NOT NULL
                    AND julianday('now','localtime') - julianday(kp.freshness_checked_at) <= (kp.freshness_interval_days - 30)""")
            elif freshness_filter == "outdated":
                # 已过时
                where.append("kp.is_outdated=1")
            elif freshness_filter == "unchecked":
                # 未设保鲜时间
                where.append("kp.review_status='confirmed' AND kp.freshness_checked_at IS NULL AND kp.is_outdated=0")
        # v2.1.0-d F028: 政策校验状态筛选
        if policy_filter:
            if policy_filter == "unvalidated":
                where.append("(kp.policy_validated IS NULL OR kp.policy_validated = 0)")
            elif policy_filter == "validated":
                where.append("kp.policy_validated = 1")
            elif policy_filter == "pending_validation":
                where.append("kp.policy_validated = 2")
            elif policy_filter == "exempt":
                where.append("kp.policy_validated = 3")
            elif policy_filter == "no_policy":
                where.append("kp.policy_validated = 4")
        w = " AND ".join(where)
        offset = (page - 1) * per_page
        c.execute(f"SELECT COUNT(*) as cnt FROM knowledge_points kp WHERE {w}", params)
        total = c.fetchone()["cnt"]
        c.execute(f"""SELECT kp.*, sf.original_filename, sf.renamed_filename, sf.file_path,
                      cat.level1_name, cat.level2_name, cat.level2_code
                      FROM knowledge_points kp
                      LEFT JOIN source_files sf ON kp.source_file_id=sf.id
                      LEFT JOIN categories cat ON COALESCE(kp.final_category_id, kp.suggested_category_id)=cat.id
                      WHERE {w} ORDER BY sf.created_at DESC, kp.id ASC LIMIT ? OFFSET ?""",
                  params + [per_page, offset])
        rows = [dict(r) for r in c.fetchall()]; conn.close()
        return {"items": rows, "total": total, "page": page, "per_page": per_page}

    def get_knowledge_point(self, kp_id):
        conn = self.get_connection(); c = conn.cursor()
        c.execute("""SELECT kp.*, sf.original_filename, sf.renamed_filename, sf.file_path,
                      cat.level1_name, cat.level2_name, cat.level2_code
                      FROM knowledge_points kp
                      LEFT JOIN source_files sf ON kp.source_file_id=sf.id
                      LEFT JOIN categories cat ON COALESCE(kp.final_category_id, kp.suggested_category_id)=cat.id
                      WHERE kp.id=?""", (kp_id,))
        r = c.fetchone(); conn.close(); return dict(r) if r else None

    def update_knowledge_point(self, kp_id, **kw):
        conn = self.get_connection(); c = conn.cursor()
        allowed = ["title","original_excerpt","ai_extracted_content","final_category_id",
                    "final_tags","final_category_tags","final_attribute_tags","final_keywords",
                    "review_status","reviewer_notes","quality_score","is_outdated","superseded_by",
                    "content_readiness","source_authority","access_level",
                    "freshness_checked_at","freshness_interval_days","freshness_note",
                    "prompt_version","qa_score","qa_flags",
                    "policy_dependencies","policy_validated",
                    "practical_insights","insight_reliability"]
        sets, vals = [], []
        for k, v in kw.items():
            if k in allowed:
                sets.append(f"{k}=?")
                if k in ("ai_extracted_content","final_tags","final_category_tags",
                          "final_attribute_tags","final_keywords","qa_flags",
                          "policy_dependencies","practical_insights") and isinstance(v, (dict, list)):
                    vals.append(json.dumps(v, ensure_ascii=False))
                else: vals.append(v)
        if sets:
            sets.append("updated_at=datetime('now','localtime')")
            if kw.get("review_status") == "confirmed": sets.append("confirmed_at=datetime('now','localtime')")
            vals.append(kp_id)
            c.execute(f"UPDATE knowledge_points SET {','.join(sets)} WHERE id=?", vals); conn.commit()
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

    def restore_to_pending(self, kp_id):
        self.update_knowledge_point(kp_id, review_status="pending", reviewer_notes="")
        self.log_operation("restore_to_pending", "knowledge_points", kp_id)

    def delete_knowledge_point(self, kp_id):
        """物理删除知识点及其关联数据（不可恢复）"""
        conn = self.get_connection(); c = conn.cursor()
        c.execute("DELETE FROM edit_history WHERE knowledge_point_id=?", (kp_id,))
        c.execute("DELETE FROM knowledge_relations WHERE source_kp_id=? OR target_kp_id=?", (kp_id, kp_id))
        c.execute("DELETE FROM knowledge_usage_log WHERE knowledge_point_id=?", (kp_id,))
        c.execute("DELETE FROM knowledge_points WHERE id=?", (kp_id,))
        conn.commit(); conn.close()
        self.log_operation("physical_delete", "knowledge_points", kp_id)

    # ================================================================
    # v2.1.2 F044: 版本重提取
    # ================================================================
    def get_reextract_scan(self, current_prompt_version):
        """扫描需要重提取的知识点，按源文件分组"""
        conn = self.get_connection(); c = conn.cursor()
        c.execute("""
            SELECT sf.id as file_id, sf.original_filename, sf.renamed_filename,
                   kp.prompt_version, COUNT(kp.id) as kp_count
            FROM knowledge_points kp
            JOIN source_files sf ON kp.source_file_id = sf.id
            WHERE (kp.prompt_version IS NULL OR kp.prompt_version != ?)
              AND kp.review_status != 'ignored'
            GROUP BY sf.id, kp.prompt_version
            ORDER BY sf.original_filename
        """, (current_prompt_version,))
        rows = [dict(r) for r in c.fetchall()]
        conn.close()
        return rows

    def delete_kps_by_source_file(self, source_file_id):
        """删除指定源文件的所有知识点及关联数据，返回删除数量"""
        conn = self.get_connection(); c = conn.cursor()
        c.execute("SELECT id FROM knowledge_points WHERE source_file_id=?", (source_file_id,))
        kp_ids = [r[0] for r in c.fetchall()]
        for kp_id in kp_ids:
            c.execute("DELETE FROM edit_history WHERE knowledge_point_id=?", (kp_id,))
            c.execute("DELETE FROM knowledge_relations WHERE source_kp_id=? OR target_kp_id=?", (kp_id, kp_id))
            c.execute("DELETE FROM knowledge_usage_log WHERE knowledge_point_id=?", (kp_id,))
        c.execute("DELETE FROM knowledge_points WHERE source_file_id=?", (source_file_id,))
        conn.commit(); conn.close()
        if kp_ids:
            self.log_operation("reextract_delete", "knowledge_points", source_file_id,
                               {"deleted_count": len(kp_ids), "kp_ids": kp_ids})
        return len(kp_ids)

    # ================================================================
    # 编辑历史
    # ================================================================
    def add_edit_history(self, kp_id, edited_fields, edit_summary=""):
        conn = self.get_connection(); c = conn.cursor()
        c.execute("INSERT INTO edit_history (knowledge_point_id, edited_fields, edit_summary) VALUES (?,?,?)",
                  (kp_id, json.dumps(edited_fields, ensure_ascii=False), edit_summary))
        conn.commit(); conn.close()

    def get_edit_history(self, kp_id):
        conn = self.get_connection(); c = conn.cursor()
        c.execute("SELECT * FROM edit_history WHERE knowledge_point_id=? ORDER BY created_at DESC", (kp_id,))
        rows = [dict(r) for r in c.fetchall()]; conn.close()
        for row in rows:
            try: row["edited_fields"] = json.loads(row["edited_fields"]) if isinstance(row["edited_fields"], str) else row["edited_fields"]
            except: pass
        return rows

    def restore_from_history(self, kp_id, history_id):
        conn = self.get_connection(); c = conn.cursor()
        c.execute("SELECT * FROM edit_history WHERE id=? AND knowledge_point_id=?", (history_id, kp_id))
        h = c.fetchone(); conn.close()
        if not h: return False, "历史记录不存在"
        try: fields = json.loads(h["edited_fields"]) if isinstance(h["edited_fields"], str) else h["edited_fields"]
        except: return False, "历史记录格式错误"
        current_kp = self.get_knowledge_point(kp_id)
        if not current_kp: return False, "知识点不存在"
        restore_changes, update_kw = {}, {}
        for field_name, change in fields.items():
            old_val = change.get("old")
            restore_changes[field_name] = {"old": current_kp.get(field_name), "new": old_val}
            update_kw[field_name] = old_val
        if update_kw:
            self.update_knowledge_point(kp_id, **update_kw)
            self.add_edit_history(kp_id, restore_changes, f"回滚到历史版本#{history_id}")
            self.log_operation("restore_version", "knowledge_points", kp_id, {"history_id": history_id})
        return True, "回滚成功"

    # ================================================================
    # 分类管理
    # ================================================================
    def get_next_level1_code(self):
        conn = self.get_connection(); c = conn.cursor()
        c.execute("SELECT DISTINCT level1_code FROM categories ORDER BY level1_code DESC LIMIT 1")
        r = c.fetchone(); conn.close()
        if r: return str(int(r["level1_code"]) + 1)
        return "1"

    def get_next_level2_code(self, level1_code):
        conn = self.get_connection(); c = conn.cursor()
        c.execute("SELECT level2_code FROM categories WHERE level1_code=? ORDER BY level2_code DESC LIMIT 1", (level1_code,))
        r = c.fetchone(); conn.close()
        if r:
            parts = r["level2_code"].split(".")
            if len(parts) == 2: return f"{parts[0]}.{int(parts[1]) + 1}"
        return f"{level1_code}.1"

    def add_category(self, level1_code, level1_name, level2_name, description="", is_new_level1=False):
        if is_new_level1:
            level1_code = self.get_next_level1_code()
        level2_code = self.get_next_level2_code(level1_code)
        conn = self.get_connection(); c = conn.cursor()
        c.execute("INSERT INTO categories (level1_code,level1_name,level2_code,level2_name,description) VALUES (?,?,?,?,?)",
                  (level1_code, level1_name, level2_code, level2_name, description))
        cat_id = c.lastrowid; conn.commit(); conn.close()
        self.log_operation("add_category", "categories", cat_id, {
            "level1_code": level1_code, "level2_code": level2_code,
            "level2_name": level2_name, "is_new_level1": is_new_level1})
        return {"id": cat_id, "level1_code": level1_code, "level1_name": level1_name,
                "level2_code": level2_code, "level2_name": level2_name, "description": description}

    def get_category_stats(self):
        conn = self.get_connection(); c = conn.cursor()
        c.execute("""SELECT cat.id, cat.level1_code, cat.level1_name, cat.level2_code, cat.level2_name,
                      COUNT(kp.id) as kp_count
                      FROM categories cat
                      LEFT JOIN knowledge_points kp ON (kp.final_category_id=cat.id OR (kp.final_category_id IS NULL AND kp.suggested_category_id=cat.id))
                          AND kp.review_status='confirmed'
                      WHERE cat.is_active=1 GROUP BY cat.id ORDER BY cat.level1_code, cat.level2_code""")
        rows = [dict(r) for r in c.fetchall()]; conn.close(); return rows

    def get_all_categories(self, active_only=True):
        conn = self.get_connection(); c = conn.cursor()
        w = "WHERE is_active=1" if active_only else ""
        c.execute(f"SELECT * FROM categories {w} ORDER BY level1_code, level2_code")
        rows = [dict(r) for r in c.fetchall()]; conn.close(); return rows

    def get_categories_tree(self):
        cats = self.get_all_categories(); tree = {}
        for cat in cats:
            l1 = cat["level1_name"]
            if l1 not in tree: tree[l1] = {"code": cat["level1_code"], "children": []}
            tree[l1]["children"].append({"id": cat["id"], "code": cat["level2_code"],
                                         "name": cat["level2_name"], "description": cat["description"]})
        return tree

    def find_category_by_code(self, level2_code):
        conn = self.get_connection(); c = conn.cursor()
        c.execute("SELECT * FROM categories WHERE level2_code=? AND is_active=1", (level2_code,))
        r = c.fetchone(); conn.close(); return dict(r) if r else None

    # ================================================================
    # AI建议分类
    # ================================================================
    def add_architecture_suggestion(self, suggested_name, suggested_level, reason,
                                    suggestion_type="add_level2", parent_category_id=None,
                                    related_knowledge_ids=None):
        conn = self.get_connection(); c = conn.cursor()
        c.execute("""INSERT INTO architecture_suggestions
            (suggested_name, suggested_level, parent_category_id, suggestion_type, reason, related_knowledge_ids)
            VALUES (?,?,?,?,?,?)""",
            (suggested_name, suggested_level, parent_category_id, suggestion_type, reason,
             json.dumps(related_knowledge_ids or [], ensure_ascii=False)))
        sid = c.lastrowid; conn.commit(); conn.close(); return sid

    def get_pending_suggestions(self):
        conn = self.get_connection(); c = conn.cursor()
        c.execute("""SELECT s.*, cat.level1_name as parent_level1_name, cat.level2_name as parent_level2_name
                      FROM architecture_suggestions s
                      LEFT JOIN categories cat ON s.parent_category_id=cat.id
                      WHERE s.status='pending' ORDER BY s.created_at DESC""")
        rows = [dict(r) for r in c.fetchall()]; conn.close()
        for r in rows:
            try: r["related_knowledge_ids"] = json.loads(r["related_knowledge_ids"]) if isinstance(r["related_knowledge_ids"], str) else r["related_knowledge_ids"]
            except: r["related_knowledge_ids"] = []
        return rows

    def update_suggestion_status(self, suggestion_id, status):
        conn = self.get_connection(); c = conn.cursor()
        c.execute("UPDATE architecture_suggestions SET status=?, resolved_at=datetime('now','localtime') WHERE id=?",
                  (status, suggestion_id))
        conn.commit(); conn.close()
        self.log_operation(f"suggestion_{status}", "architecture_suggestions", suggestion_id)

    # ================================================================
    # 知识关联
    # ================================================================
    def add_knowledge_relation(self, source_kp_id, target_kp_id, relation_type, created_by="manual"):
        conn = self.get_connection(); c = conn.cursor()
        c.execute("INSERT INTO knowledge_relations (source_kp_id,target_kp_id,relation_type,created_by) VALUES (?,?,?,?)",
                  (source_kp_id, target_kp_id, relation_type, created_by))
        conn.commit(); conn.close()

    def get_knowledge_relations(self, kp_id):
        conn = self.get_connection(); c = conn.cursor()
        c.execute("""SELECT kr.*, kp.title as related_title
                      FROM knowledge_relations kr
                      JOIN knowledge_points kp ON (CASE WHEN kr.source_kp_id=? THEN kr.target_kp_id ELSE kr.source_kp_id END)=kp.id
                      WHERE kr.source_kp_id=? OR kr.target_kp_id=?
                      ORDER BY kr.created_at DESC""", (kp_id, kp_id, kp_id))
        rows = [dict(r) for r in c.fetchall()]; conn.close(); return rows

    # ================================================================
    # 使用追踪
    # ================================================================
    def log_knowledge_usage(self, kp_id, usage_type, usage_context=""):
        conn = self.get_connection(); c = conn.cursor()
        c.execute("INSERT INTO knowledge_usage_log (knowledge_point_id,usage_type,usage_context) VALUES (?,?,?)",
                  (kp_id, usage_type, usage_context))
        conn.commit(); conn.close()

    # ================================================================
    # 架构升级检查
    # ================================================================
    def get_all_knowledge_for_upgrade(self):
        """获取所有知识点用于升级检查（不分页，含源文件信息）"""
        conn = self.get_connection(); c = conn.cursor()
        c.execute("""SELECT kp.id, kp.title, kp.content_type, kp.source_file_id,
                      kp.original_excerpt, kp.ai_extracted_content,
                      kp.suggested_category_tags, kp.final_category_tags,
                      kp.suggested_attribute_tags, kp.final_attribute_tags,
                      kp.suggested_keywords, kp.final_keywords,
                      kp.content_readiness, kp.source_authority,
                      kp.review_status,
                      sf.original_filename, sf.renamed_filename, sf.file_path
                      FROM knowledge_points kp
                      LEFT JOIN source_files sf ON kp.source_file_id=sf.id
                      WHERE kp.review_status IN ('pending','confirmed')
                      ORDER BY kp.id""")
        rows = [dict(r) for r in c.fetchall()]; conn.close(); return rows

    # ================================================================
    # 内容保鲜（v2.1.0-d 新增/增强）
    # ================================================================
    def get_stale_knowledge_points(self):
        """获取需要检查时效性的知识点"""
        conn = self.get_connection(); c = conn.cursor()
        c.execute("""SELECT kp.id, kp.title, kp.content_type, kp.freshness_checked_at, kp.freshness_interval_days
                      FROM knowledge_points kp
                      WHERE kp.review_status='confirmed'
                      AND (kp.freshness_checked_at IS NULL
                           OR julianday('now','localtime') - julianday(kp.freshness_checked_at) > kp.freshness_interval_days)
                      ORDER BY kp.freshness_checked_at ASC NULLS FIRST
                      LIMIT 50""")
        rows = [dict(r) for r in c.fetchall()]; conn.close(); return rows

    def mark_freshness_checked(self, kp_id):
        conn = self.get_connection(); c = conn.cursor()
        c.execute("UPDATE knowledge_points SET freshness_checked_at=datetime('now','localtime') WHERE id=?", (kp_id,))
        conn.commit(); conn.close()

    def get_freshness_summary(self):
        """v2.1.0-d: 获取保鲜状态摘要（过期/即将到期/新鲜/已过时/未设时间）"""
        conn = self.get_connection(); c = conn.cursor()
        summary = {"expired": 0, "expiring_soon": 0, "fresh": 0, "outdated": 0, "unchecked": 0}
        # 已过时
        c.execute("SELECT COUNT(*) as cnt FROM knowledge_points WHERE review_status='confirmed' AND is_outdated=1")
        summary["outdated"] = c.fetchone()["cnt"]
        # 未设保鲜时间
        c.execute("SELECT COUNT(*) as cnt FROM knowledge_points WHERE review_status='confirmed' AND is_outdated=0 AND freshness_checked_at IS NULL")
        summary["unchecked"] = c.fetchone()["cnt"]
        # 已过期
        c.execute("""SELECT COUNT(*) as cnt FROM knowledge_points
                     WHERE review_status='confirmed' AND is_outdated=0
                     AND freshness_checked_at IS NOT NULL
                     AND julianday('now','localtime') - julianday(freshness_checked_at) > freshness_interval_days""")
        summary["expired"] = c.fetchone()["cnt"]
        # 即将到期（30天内）
        c.execute("""SELECT COUNT(*) as cnt FROM knowledge_points
                     WHERE review_status='confirmed' AND is_outdated=0
                     AND freshness_checked_at IS NOT NULL
                     AND julianday('now','localtime') - julianday(freshness_checked_at) > (freshness_interval_days - 30)
                     AND julianday('now','localtime') - julianday(freshness_checked_at) <= freshness_interval_days""")
        summary["expiring_soon"] = c.fetchone()["cnt"]
        # 新鲜
        c.execute("""SELECT COUNT(*) as cnt FROM knowledge_points
                     WHERE review_status='confirmed' AND is_outdated=0
                     AND freshness_checked_at IS NOT NULL
                     AND julianday('now','localtime') - julianday(freshness_checked_at) <= (freshness_interval_days - 30)""")
        summary["fresh"] = c.fetchone()["cnt"]
        conn.close()
        return summary

    def renew_freshness(self, kp_id, note=""):
        """v2.1.0-d: 续期保鲜（刷新检查时间，可选备注）"""
        conn = self.get_connection(); c = conn.cursor()
        if note:
            c.execute("""UPDATE knowledge_points
                         SET freshness_checked_at=datetime('now','localtime'),
                             freshness_note=?, updated_at=datetime('now','localtime')
                         WHERE id=?""", (note, kp_id))
        else:
            c.execute("""UPDATE knowledge_points
                         SET freshness_checked_at=datetime('now','localtime'),
                             updated_at=datetime('now','localtime')
                         WHERE id=?""", (kp_id,))
        conn.commit(); conn.close()
        self.log_operation("renew_freshness", "knowledge_points", kp_id, {"note": note})

    def mark_knowledge_outdated(self, kp_id, reason=""):
        """v2.1.0-d: 标记知识点为已过时"""
        conn = self.get_connection(); c = conn.cursor()
        c.execute("""UPDATE knowledge_points
                     SET is_outdated=1, freshness_note=?,
                         updated_at=datetime('now','localtime')
                     WHERE id=?""", (reason, kp_id))
        conn.commit(); conn.close()
        self.log_operation("mark_outdated", "knowledge_points", kp_id, {"reason": reason})

    # ================================================================
    # 政策依赖校验（v2.1.0-d F028 新增）
    # ================================================================
    def get_policy_validation_summary(self):
        """获取政策校验状态摘要"""
        conn = self.get_connection(); c = conn.cursor()
        summary = {"unvalidated": 0, "validated": 0, "pending": 0, "exempt": 0, "no_policy": 0}
        c.execute("""SELECT policy_validated, COUNT(*) as cnt FROM knowledge_points
                     WHERE review_status IN ('pending','confirmed')
                     GROUP BY policy_validated""")
        for row in c.fetchall():
            val = row["policy_validated"]
            cnt = row["cnt"]
            if val is None or val == 0:
                summary["unvalidated"] += cnt
            elif val == 1:
                summary["validated"] += cnt
            elif val == 2:
                summary["pending"] += cnt
            elif val == 3:
                summary["exempt"] += cnt
            elif val == 4:
                summary["no_policy"] += cnt
        conn.close()
        return summary

    # ================================================================
    # 标签定义查询
    # ================================================================
    def get_tag_definitions(self, layer=None):
        conn = self.get_connection(); c = conn.cursor()
        if layer:
            c.execute("SELECT * FROM tag_definitions WHERE layer=? AND is_active=1 ORDER BY sort_order", (layer,))
        else:
            c.execute("SELECT * FROM tag_definitions WHERE is_active=1 ORDER BY layer, sort_order")
        rows = [dict(r) for r in c.fetchall()]; conn.close(); return rows

    # ================================================================
    # 日志与统计
    # ================================================================
    def log_api_call(self, call_type, model, input_tokens, output_tokens, estimated_cost):
        conn = self.get_connection(); c = conn.cursor()
        c.execute("INSERT INTO api_call_logs (call_type,model,input_tokens,output_tokens,estimated_cost) VALUES (?,?,?,?,?)",
                  (call_type, model, input_tokens, output_tokens, estimated_cost))
        conn.commit(); conn.close()

    def get_today_api_cost(self):
        conn = self.get_connection(); c = conn.cursor()
        today = datetime.now().strftime("%Y-%m-%d")
        c.execute("SELECT COALESCE(SUM(estimated_cost),0) as tc FROM api_call_logs WHERE call_date=?", (today,))
        r = c.fetchone(); conn.close(); return r["tc"]

    def log_operation(self, op_type, target_table="", target_id=None, details=None):
        conn = self.get_connection(); c = conn.cursor()
        c.execute("INSERT INTO operation_logs (operation_type,target_table,target_id,details) VALUES (?,?,?,?)",
                  (op_type, target_table, target_id, json.dumps(details or {}, ensure_ascii=False)))
        conn.commit(); conn.close()

    def get_statistics(self):
        conn = self.get_connection(); c = conn.cursor(); stats = {}
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
        c.execute("SELECT COUNT(*) as cnt FROM architecture_suggestions WHERE status='pending'")
        stats["pending_suggestions"] = c.fetchone()["cnt"]
        # v2.0.0 新增统计
        c.execute("SELECT content_readiness, COUNT(*) as cnt FROM knowledge_points WHERE review_status='confirmed' GROUP BY content_readiness")
        stats["by_readiness"] = {r["content_readiness"]: r["cnt"] for r in c.fetchall()}
        c.execute("SELECT access_level, COUNT(*) as cnt FROM knowledge_points WHERE review_status='confirmed' GROUP BY access_level")
        stats["by_access"] = {r["access_level"]: r["cnt"] for r in c.fetchall()}
        # v2.1.1 F039: 重复检测统计
        try:
            c.execute("SELECT COUNT(*) as cnt FROM duplicate_groups WHERE status='pending'")
            stats["pending_duplicates"] = c.fetchone()["cnt"]
        except:
            stats["pending_duplicates"] = 0
        conn.close(); return stats

    # ================================================================
    # 重复检测（v2.1.1 F039 新增）
    # ================================================================
    def add_duplicate_group(self, member_ids, relation_type=None, ai_judgment=None, similarity_score=0):
        """新增一条重复检测结果"""
        conn = self.get_connection(); c = conn.cursor()
        c.execute("""INSERT INTO duplicate_groups
            (member_ids, relation_type, ai_judgment, similarity_score)
            VALUES (?,?,?,?)""",
            (json.dumps(member_ids, ensure_ascii=False),
             relation_type,
             json.dumps(ai_judgment or {}, ensure_ascii=False),
             similarity_score))
        gid = c.lastrowid; conn.commit(); conn.close()
        self.log_operation("add_duplicate_group", "duplicate_groups", gid,
                           {"member_ids": member_ids, "relation_type": relation_type})
        return gid

    def get_duplicate_groups(self, status="pending"):
        """获取重复检测结果列表"""
        conn = self.get_connection(); c = conn.cursor()
        if status:
            c.execute("SELECT * FROM duplicate_groups WHERE status=? ORDER BY similarity_score DESC, created_at DESC", (status,))
        else:
            c.execute("SELECT * FROM duplicate_groups ORDER BY status ASC, similarity_score DESC, created_at DESC")
        rows = [dict(r) for r in c.fetchall()]; conn.close()
        return rows

    def get_duplicate_group(self, group_id):
        """获取单条重复组详情"""
        conn = self.get_connection(); c = conn.cursor()
        c.execute("SELECT * FROM duplicate_groups WHERE id=?", (group_id,))
        r = c.fetchone(); conn.close()
        return dict(r) if r else None

    def update_duplicate_group(self, group_id, status, resolved_action=""):
        """更新重复组状态"""
        conn = self.get_connection(); c = conn.cursor()
        c.execute("""UPDATE duplicate_groups
                     SET status=?, resolved_at=datetime('now','localtime'), resolved_action=?
                     WHERE id=?""", (status, resolved_action, group_id))
        conn.commit(); conn.close()
        self.log_operation("resolve_duplicate", "duplicate_groups", group_id,
                           {"status": status, "action": resolved_action})

    def get_duplicate_summary(self):
        """获取重复检测状态摘要"""
        conn = self.get_connection(); c = conn.cursor()
        summary = {"pending": 0, "resolved": 0, "dismissed": 0}
        try:
            c.execute("SELECT status, COUNT(*) as cnt FROM duplicate_groups GROUP BY status")
            for row in c.fetchall():
                if row["status"] in summary:
                    summary[row["status"]] = row["cnt"]
        except:
            pass  # 表可能不存在
        conn.close()
        return summary
