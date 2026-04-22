"""
db_manager.py - SQLite数据库管理模块
路径：scripts/db_manager.py
版本：v2.3.0-part3-alpha1 - F062 端到端健康测试 Agent 基础层（对话 1/3）

v2.3.0-part3-alpha1 新增（F062 基础层 / 对话 1/3）：
  - 3 张新表（init_tables 内建，对齐 v2.3.0-part2.1 立规则"schema 单一来源"）：
    * api_endpoint_registry：接口登记表（endpoint PK + methods + first_seen_at
                                           + last_tested_at + test_template_json）
    * e2e_test_reports：E2E 测试整体报告（六维度汇总 + 新增接口清单 + 完整 JSON）
    * e2e_issues：四态 issue 跟踪（pending/fixed/intermittent/ignored + signature
                                    去重键 + occurrence_count + 偶发升级逻辑）
  - 3 条 F062 索引：idx_e2e_report_created / idx_e2e_issue_status /
                    idx_e2e_issue_signature
  - 8 个新方法（严格按对话 1 Phase 2 锁定契约）：
      路由自省(3)：register_endpoint / get_endpoint_registry /
                   update_endpoint_last_tested
      报告读写(3)：save_e2e_test_report / get_latest_e2e_test_report /
                   get_e2e_test_report_detail
      issue 四态(2)：upsert_e2e_issue（含偶发升级）/ set_e2e_issue_status
  - 所有 JSON 字段（test_template_json / new_endpoints_json / full_report_json /
    payload_json）传入支持 dict/list 自动 json.dumps，读取自动 json.loads
  - severity 取值严格对齐 operation_events 的 CHECK：info / warning / error
    （禁用 "warn" 简写，对话 A 立规则）
  - e2e_issues.status 用 CHECK 约束锁死四态白名单
  - 数据库表总数：18 → 21

v2.3.0-part2.2 修复（hotfix 对话 B）：
  - F048 维度②结构分布=0 根因修复：三个扫描查询（get_kp_for_health_scan /
    get_polish_candidates / get_island_candidates）追加 LEFT JOIN categories
    并 AS 出两个业务分类字符串字段：
      c.level1_name AS category     -- 5 大类名（政策库/案例库/经验库/工具库/数据库）
      c.level2_name AS subcategory  -- 27 子类名（如 "1.1全域土地综合整治政策"）
  - JOIN 条件：c.id = kp.final_category_id（kp 表真实外键列名是 final_category_id，
    不是 category_id；对话 A 的 01 工程手册锚点口径已在对话 B 同步纠正）
  - 历史库中 final_category_id IS NULL 的未分类 kp，LEFT JOIN 后 category/subcategory
    返回 None，health_checker 的 set 操作天然忽略 None，不崩但会让维度②略低
  - 字段契约兑现后，health_checker.py 的 _dim2_structure_score / _build_library_summary /
    _build_nearby_summary / _kp_to_judge_payload / _kp_to_full_payload 全部天然恢复，
    代码零改动（这是对话 A/B 三对话拆分的精妙点：修 db 层兑现契约 > 改 health_checker 硬编码）

v2.3.0-part2.1 修复（hotfix）：
  - init_tables() 追加 health_reports / polish_suggestions 两张表建表 SQL
    + 3 个 F048 索引（idx_health_created / idx_polish_report / idx_polish_status）
  - 修复新电脑首次部署缺两表导致体检功能炸的 bug
  - 建表单一来源原则：init_tables 必须是唯一的建表真相，schema 变更先改这里
  - 配套删除 scripts/migrate_v223.py、scripts/migrate_v230_part2.py（历史使命完成）

v2.3.0-part2 新增（F048 体检 Agent 基础层）：
  - 新表 health_reports：六维度体检报告（status/total_score/6 维分/full_report_json/API调用统计）
  - 新表 polish_suggestions：低分打磨建议（tier/diagnosis/original/suggested/status）
  - 12 个新方法（严格按 01 工程手册锁定契约）：
      健康报告读写(5)：save/update/get_latest/get_list/get_detail_health_report
      打磨建议读写(4)：save/get_by_report/apply/reject_polish_suggestion
      扫描候选查询(3)：get_kp_for_health_scan/get_polish_candidates/get_island_candidates
  - 【重要】apply_polish_suggestion 仅标 status=applied，不在此方法内调 update_knowledge_point
      事务边界由 api_server 层保持三步清晰：备份 → 更新 kp → 标记 suggestion applied
  - 字段别名映射（SQL AS）：kp.id → kp_id / review_status → status / source_authority → authority_level / access_level → monetize_tier
    + v2.3.0-part2.2 追加 c.level1_name → category / c.level2_name → subcategory

v2.3.0-part1 新增（工具箱+批量重跑）：
  - get_all_knowledge_points 签名补齐 qa_source_filter（v2.2.3 遗留bug：api层已在传，db层签名却没有）
    和 layer1_tag（A组业务领域/C组知识形态/D组客户视角 穿透跳转用）
  - 新方法 get_tag_distribution(group_code)：按标签组聚合已确认知识点数量（仪表盘卡片数据源）
  - 新方法 delete_extracted_kps_by_source_file(file_id)：仅删 review_status='pending' 的知识点
    （批量重跑 F059 用，保留已 confirmed 的审核成果；级联风格与 delete_kps_by_source_file 对齐）
  - 新方法 get_batch_rerun_candidate_files()：扫 source_files 表 + LEFT JOIN kp 聚合，
    返回 [{id, filename, kp_total, kp_pending, kp_confirmed, kp_ignored, has_annotations}] 供前端批量勾选

v2.2.3 新增（hotfix）：
  - source_files 表: truncation_count / recovery_runs / last_recovery_at
  - knowledge_points 表: qa_source（batch/small_batch/single/rule_fallback）
  - 新表 operation_events: 结构化事件日志（截断/降级/兜底/备份）
  - 新方法 log_operation_event / get_qc_rerun_candidates
  - update_knowledge_point 白名单追加 qa_source

数据库表（21张，v2.3.0-part3-alpha1 新增 api_endpoint_registry / e2e_test_reports / e2e_issues）：
  categories - 知识库分类体系（5大类27+子类）
  source_files - 原始文件记录（v2.2.3新增3字段用于截断补救追溯）
  knowledge_points - 知识点（核心表，v2.2.3新增qa_source字段）
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
  annotations - 专家注解（v2.2.0 F029新增）
  operation_events - 结构化事件日志（v2.2.3 F057/F058/F060新增）
  health_reports - 体检报告（v2.3.0-part2 F048新增，v2.3.0-part2.1 起由 init_tables 直接建）
  polish_suggestions - 打磨建议（v2.3.0-part2 F048新增，v2.3.0-part2.1 起由 init_tables 直接建）
  api_endpoint_registry - 接口登记表（v2.3.0-part3-alpha1 F062新增，路由自省用）
  e2e_test_reports - E2E 测试报告（v2.3.0-part3-alpha1 F062新增）
  e2e_issues - E2E issue 四态跟踪（v2.3.0-part3-alpha1 F062新增）
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
            -- v2.1.0-c: 预分析结果
            pre_analysis_result TEXT DEFAULT '',
            suggested_content_type TEXT DEFAULT '',
            segment_plan TEXT DEFAULT '',
            -- v2.2.0: 文档来源属性
            doc_origin TEXT DEFAULT 'external',
            -- v2.2.3 F057: 截断补救追溯
            truncation_count INTEGER DEFAULT 0,
            recovery_runs INTEGER DEFAULT 0,
            last_recovery_at TEXT DEFAULT NULL,
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
            -- v2.1.0: 提取与质检
            prompt_version TEXT DEFAULT '',
            qa_score REAL DEFAULT 0.0,
            qa_flags TEXT DEFAULT '[]',
            -- v2.2.3 F058: 质检来源追溯（batch/small_batch/single/rule_fallback）
            qa_source TEXT DEFAULT 'batch',
            freshness_note TEXT DEFAULT '',
            -- v2.1.0: 政策依赖校验
            policy_dependencies TEXT DEFAULT '[]',
            policy_validated INTEGER DEFAULT 0,
            -- v2.1.1: 举一反三
            practical_insights TEXT DEFAULT '[]',
            insight_reliability TEXT DEFAULT NULL,
            -- v2.2.0: 来源类型
            source_type TEXT DEFAULT 'extracted',
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
        # --- v2.2.0 专家注解 ---
        c.execute("""CREATE TABLE IF NOT EXISTS annotations (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            knowledge_point_id INTEGER NOT NULL,
            annotation_type TEXT NOT NULL
                CHECK(annotation_type IN ('agree','disagree','supplement','correction','experience')),
            content TEXT DEFAULT '',
            tags TEXT DEFAULT '[]',
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
        # --- v2.2.3 F057/F058/F060 结构化事件日志 ---
        # event_type: truncation_recovery / qc_downgrade / rule_fallback / backup_trigger / backup_failed
        # module: extractor / qc / backup
        # severity: info / warning / error
        c.execute("""CREATE TABLE IF NOT EXISTS operation_events (
            event_id INTEGER PRIMARY KEY AUTOINCREMENT,
            event_time TEXT NOT NULL DEFAULT (datetime('now','localtime')),
            event_type TEXT NOT NULL,
            module TEXT NOT NULL,
            severity TEXT NOT NULL DEFAULT 'info'
                CHECK(severity IN ('info','warning','error')),
            related_file_id INTEGER,
            related_kp_id INTEGER,
            payload_json TEXT DEFAULT '{}',
            FOREIGN KEY (related_file_id) REFERENCES source_files(id),
            FOREIGN KEY (related_kp_id) REFERENCES knowledge_points(id)
        )""")
        # --- v2.3.0-part2 F048 知识库体检报告 ---
        c.execute("""CREATE TABLE IF NOT EXISTS health_reports (
            report_id INTEGER PRIMARY KEY AUTOINCREMENT,
            created_at TEXT NOT NULL,
            status TEXT NOT NULL,
            total_score REAL,
            dim1_health_score REAL,
            dim2_structure_score REAL,
            dim3_processing_score REAL,
            dim4_relation_score REAL,
            dim5_polish_score REAL,
            dim6_monetize_score REAL,
            full_report_json TEXT,
            scanned_kp_count INTEGER,
            v3_call_count INTEGER,
            r1_call_count INTEGER,
            cost_estimate REAL,
            error_message TEXT
        )""")
        # --- v2.3.0-part2 F048 低分打磨建议 ---
        c.execute("""CREATE TABLE IF NOT EXISTS polish_suggestions (
            suggestion_id INTEGER PRIMARY KEY AUTOINCREMENT,
            report_id INTEGER NOT NULL,
            kp_id INTEGER NOT NULL,
            diagnosis TEXT,
            suggestion_type TEXT,
            tier TEXT,
            original_content TEXT,
            suggested_content TEXT,
            status TEXT DEFAULT 'pending',
            applied_at TEXT,
            created_at TEXT NOT NULL,
            FOREIGN KEY (report_id) REFERENCES health_reports(report_id)
        )""")
        # --- v2.3.0-part3-alpha1 F062 接口登记表（路由自省用） ---
        # endpoint 作为 PRIMARY KEY,同一 endpoint 多 methods 合成逗号分隔("GET,POST")
        c.execute("""CREATE TABLE IF NOT EXISTS api_endpoint_registry (
            endpoint TEXT PRIMARY KEY,
            methods TEXT NOT NULL,
            first_seen_at TEXT NOT NULL,
            last_tested_at TEXT,
            test_template_json TEXT
        )""")
        # --- v2.3.0-part3-alpha1 F062 E2E 测试整体报告 ---
        c.execute("""CREATE TABLE IF NOT EXISTS e2e_test_reports (
            report_id INTEGER PRIMARY KEY AUTOINCREMENT,
            created_at TEXT NOT NULL,
            trigger_type TEXT NOT NULL,
            scan_depth TEXT NOT NULL DEFAULT 'quick',
            total_endpoints INTEGER,
            passed_count INTEGER,
            failed_count INTEGER,
            warning_count INTEGER,
            new_endpoints_json TEXT,
            full_report_json TEXT,
            v3_call_count INTEGER DEFAULT 0,
            cost_estimate REAL DEFAULT 0.0
        )""")
        # --- v2.3.0-part3-alpha1 F062 E2E issue 四态跟踪 ---
        # status 四态白名单: pending(待修) / fixed(已修复) / intermittent(偶发) / ignored(忽略)
        # severity 对齐 operation_events CHECK: info / warning / error (禁"warn"简写)
        # signature 作为去重键: "{dim_code}|{endpoint}|{rule_id}" 单字段,不加 UNIQUE 约束,
        #   允许跨 report 多次出现,upsert 时按 signature 查最新 pending/intermittent 记录更新
        c.execute("""CREATE TABLE IF NOT EXISTS e2e_issues (
            issue_id INTEGER PRIMARY KEY AUTOINCREMENT,
            report_id INTEGER NOT NULL,
            dim_code TEXT NOT NULL,
            endpoint TEXT,
            severity TEXT NOT NULL DEFAULT 'warning'
                CHECK(severity IN ('info','warning','error')),
            signature TEXT NOT NULL,
            status TEXT NOT NULL DEFAULT 'pending'
                CHECK(status IN ('pending','fixed','intermittent','ignored')),
            first_seen_at TEXT NOT NULL,
            last_seen_at TEXT NOT NULL,
            occurrence_count INTEGER NOT NULL DEFAULT 1,
            resolved_at TEXT,
            payload_json TEXT DEFAULT '{}',
            FOREIGN KEY (report_id) REFERENCES e2e_test_reports(report_id)
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
            "CREATE INDEX IF NOT EXISTS idx_ann_kpid ON annotations(knowledge_point_id)",
            # v2.2.3 operation_events 索引
            "CREATE INDEX IF NOT EXISTS idx_events_time ON operation_events(event_time)",
            "CREATE INDEX IF NOT EXISTS idx_events_type ON operation_events(event_type)",
            "CREATE INDEX IF NOT EXISTS idx_events_file ON operation_events(related_file_id)",
            # v2.3.0-part2 F048 体检报告/打磨建议索引
            "CREATE INDEX IF NOT EXISTS idx_health_created ON health_reports(created_at DESC)",
            "CREATE INDEX IF NOT EXISTS idx_polish_report ON polish_suggestions(report_id)",
            "CREATE INDEX IF NOT EXISTS idx_polish_status ON polish_suggestions(status)",
            # v2.3.0-part3-alpha1 F062 E2E 测试报告/issue 索引
            "CREATE INDEX IF NOT EXISTS idx_e2e_report_created ON e2e_test_reports(created_at DESC)",
            "CREATE INDEX IF NOT EXISTS idx_e2e_issue_status ON e2e_issues(status, dim_code)",
            "CREATE INDEX IF NOT EXISTS idx_e2e_issue_signature ON e2e_issues(signature)",
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
    def add_source_file(self, original_filename, file_path, file_type, file_size=0, file_hash=None, doc_origin="external"):
        conn = self.get_connection(); c = conn.cursor()
        c.execute("INSERT INTO source_files (original_filename,file_path,file_type,file_size,file_hash,doc_origin) VALUES (?,?,?,?,?,?)",
                  (original_filename, file_path, file_type, file_size, file_hash, doc_origin))
        fid = c.lastrowid; conn.commit(); conn.close(); return fid

    def update_source_file(self, file_id, **kw):
        conn = self.get_connection(); c = conn.cursor()
        allowed = ["renamed_filename","domain_tags","region_tag","policy_level","process_status","process_message","file_hash",
                    "pre_analysis_result","suggested_content_type","segment_plan","doc_origin"]
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
                            practical_insights=None,
                            source_type="extracted"):
        conn = self.get_connection(); c = conn.cursor()
        c.execute("""INSERT INTO knowledge_points
            (source_file_id, title, content_type, original_excerpt, ai_extracted_content,
             suggested_category_id, suggested_category_tags, suggested_attribute_tags,
             suggested_keywords, suggested_tags, source_page, source_keyword,
             content_readiness, source_authority, prompt_version, practical_insights,
             source_type)
            VALUES (?,?,?,?,?, ?,?,?,?,?, ?,?,?,?,?, ?,?)""",
            (source_file_id, title, content_type, original_excerpt,
             json.dumps(ai_extracted_content or {}, ensure_ascii=False),
             suggested_category_id,
             json.dumps(suggested_category_tags or [], ensure_ascii=False),
             json.dumps(suggested_attribute_tags or {}, ensure_ascii=False),
             json.dumps(suggested_keywords or [], ensure_ascii=False),
             json.dumps(suggested_tags or [], ensure_ascii=False),
             source_page, source_keyword,
             content_readiness, source_authority, prompt_version,
             json.dumps(practical_insights or [], ensure_ascii=False),
             source_type))
        kid = c.lastrowid; conn.commit(); conn.close(); return kid

    def get_all_knowledge_points(self, review_status=None, content_type=None,
                                 category_id=None, level1_code=None,
                                 search_query=None, content_readiness=None,
                                 freshness_filter=None, policy_filter=None,
                                 source_type_filter=None, qa_score_filter=None,
                                 qa_source_filter=None, layer1_tag=None,
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
            # 支持按ID精确查找(如从重复检测跳转)
            try:
                kid = int(search_query)
                where.append("""(kp.id = ? OR kp.title LIKE ? OR kp.original_excerpt LIKE ? OR kp.ai_extracted_content LIKE ?
                            OR kp.suggested_keywords LIKE ? OR kp.final_keywords LIKE ?
                            OR kp.suggested_category_tags LIKE ? OR kp.final_category_tags LIKE ?
                            OR kp.suggested_tags LIKE ? OR kp.final_tags LIKE ?)""")
                params.extend([kid] + [sq]*9)
            except ValueError:
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
        # v2.2.0: 来源类型筛选
        if source_type_filter:
            if source_type_filter == "extracted":
                where.append("(kp.source_type='extracted' OR kp.source_type IS NULL)")
            elif source_type_filter == "experience_note":
                where.append("kp.source_type='experience_note'")
            elif source_type_filter == "manual":
                where.append("kp.source_type='manual'")
        # v2.2.2: 质检分数筛选
        if qa_score_filter:
            if qa_score_filter == "unscored":
                where.append("(kp.qa_score IS NULL)")
            else:
                try:
                    qs = int(qa_score_filter)
                    where.append("CAST(kp.qa_score AS INTEGER)=?")
                    params.append(qs)
                except ValueError:
                    pass
        # v2.3.0-part1: 质检来源筛选（v2.2.3 遗留bug补齐，api_server.py 已在传此参数）
        if qa_source_filter:
            where.append("kp.qa_source=?"); params.append(qa_source_filter)
        # v2.3.0-part1 F049: 一层标签穿透跳转（A组/C组/D组仪表盘卡片点击用）
        # 匹配 suggested_category_tags 或 final_category_tags 中的 tag_code
        # 用 '%"CODE"%' 格式避免子串误匹配（例如 "指标交易" 不会误匹配 "指标交易与定价"）
        if layer1_tag:
            pattern = f'%"{layer1_tag}"%'
            where.append("(kp.suggested_category_tags LIKE ? OR kp.final_category_tags LIKE ?)")
            params.extend([pattern, pattern])
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
                    "prompt_version","qa_score","qa_flags","qa_source",
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
        c.execute("DELETE FROM annotations WHERE knowledge_point_id=?", (kp_id,))
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
            c.execute("DELETE FROM annotations WHERE knowledge_point_id=?", (kp_id,))
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
    # v2.3.0-part1 F059: 批量重跑仅删 pending，保留 confirmed 审核成果
    # ================================================================
    def delete_extracted_kps_by_source_file(self, source_file_id):
        """
        仅删除指定源文件下 review_status='pending' 的知识点及其关联数据。
        已 confirmed 或 ignored 的条目（包括带注解/经验速记关联）保留，
        与 delete_kps_by_source_file 保持同样的级联风格（annotations/edit_history/
        knowledge_relations/knowledge_usage_log 逐一清理）。
        返回实际删除数量。
        """
        conn = self.get_connection(); c = conn.cursor()
        c.execute("""SELECT id FROM knowledge_points
                     WHERE source_file_id=? AND review_status='pending'""", (source_file_id,))
        kp_ids = [r[0] for r in c.fetchall()]
        for kp_id in kp_ids:
            c.execute("DELETE FROM annotations WHERE knowledge_point_id=?", (kp_id,))
            c.execute("DELETE FROM edit_history WHERE knowledge_point_id=?", (kp_id,))
            c.execute("DELETE FROM knowledge_relations WHERE source_kp_id=? OR target_kp_id=?", (kp_id, kp_id))
            c.execute("DELETE FROM knowledge_usage_log WHERE knowledge_point_id=?", (kp_id,))
        if kp_ids:
            qmarks = ",".join("?" * len(kp_ids))
            c.execute(f"DELETE FROM knowledge_points WHERE id IN ({qmarks})", kp_ids)
        conn.commit(); conn.close()
        if kp_ids:
            self.log_operation("batch_rerun_delete_pending", "knowledge_points", source_file_id,
                               {"deleted_count": len(kp_ids), "kp_ids": kp_ids})
        return len(kp_ids)

    # ================================================================
    # v2.3.0-part1 F049: 标签分布统计（仪表盘A/C/D组卡片数据源）
    # ================================================================
    def get_tag_distribution(self, group_code):
        """
        按标签组 group_code (如 'A','C','D') 聚合 review_status='confirmed' 知识点数量。
        统计口径：
          - 只统计已确认知识点（pending/ignored 不计入）
          - 同时扫描 final_category_tags 和 suggested_category_tags（final 优先，为空时回退 suggested）
          - 用 LIKE '%"CODE"%' 避免子串误匹配
        返回 [{tag_code, tag_name, count}] 按 count 降序。
        """
        conn = self.get_connection(); c = conn.cursor()
        # 1. 从 tag_definitions 取该组的所有一层标签
        c.execute("""SELECT tag_code, tag_name FROM tag_definitions
                     WHERE layer='layer1' AND group_code=? AND is_active=1
                     ORDER BY sort_order""", (group_code,))
        tags = [(r["tag_code"], r["tag_name"]) for r in c.fetchall()]
        result = []
        for tag_code, tag_name in tags:
            pattern = f'%"{tag_code}"%'
            c.execute("""SELECT COUNT(*) AS cnt FROM knowledge_points
                         WHERE review_status='confirmed'
                           AND (
                             (final_category_tags LIKE ? AND final_category_tags IS NOT NULL
                                AND final_category_tags != '' AND final_category_tags != '[]')
                             OR (
                               (final_category_tags IS NULL OR final_category_tags=''
                                OR final_category_tags='[]')
                               AND suggested_category_tags LIKE ?
                             )
                           )""", (pattern, pattern))
            cnt = c.fetchone()["cnt"]
            result.append({"tag_code": tag_code, "tag_name": tag_name, "count": cnt})
        conn.close()
        # 按 count 降序返回（便于前端直接渲染排序后的卡片）
        result.sort(key=lambda x: x["count"], reverse=True)
        return result

    # ================================================================
    # v2.3.0-part1 F059: 批量重跑候选文件扫描
    # ================================================================
    def get_batch_rerun_candidate_files(self):
        """
        扫 source_files 表，左连接 knowledge_points/annotations 聚合：
          - kp_total / kp_pending / kp_confirmed / kp_ignored
          - has_annotations（用于前端警示：含注解则全量重跑会清空）
        只返回 process_status='completed' 的文件（已完成提取的才有重跑意义）。
        返回列表按 created_at 倒序。
        """
        conn = self.get_connection(); c = conn.cursor()
        c.execute("""
            SELECT sf.id, sf.original_filename, sf.renamed_filename, sf.file_path,
                   sf.process_status, sf.process_message, sf.created_at,
                   sf.truncation_count, sf.recovery_runs, sf.last_recovery_at,
                   COUNT(kp.id) AS kp_total,
                   SUM(CASE WHEN kp.review_status='pending' THEN 1 ELSE 0 END) AS kp_pending,
                   SUM(CASE WHEN kp.review_status='confirmed' THEN 1 ELSE 0 END) AS kp_confirmed,
                   SUM(CASE WHEN kp.review_status='ignored' THEN 1 ELSE 0 END) AS kp_ignored
              FROM source_files sf
              LEFT JOIN knowledge_points kp ON kp.source_file_id = sf.id
             WHERE sf.process_status='completed'
             GROUP BY sf.id
             ORDER BY sf.created_at DESC
        """)
        rows = [dict(r) for r in c.fetchall()]
        # 再查每个文件下是否有 annotations（警示用）
        for row in rows:
            c.execute("""SELECT COUNT(*) AS cnt FROM annotations a
                         JOIN knowledge_points kp ON a.knowledge_point_id=kp.id
                         WHERE kp.source_file_id=?""", (row["id"],))
            row["has_annotations"] = (c.fetchone()["cnt"] or 0) > 0
            # 规范化数值字段（SUM 结果可能是 None）
            for k in ("kp_total", "kp_pending", "kp_confirmed", "kp_ignored"):
                row[k] = int(row.get(k) or 0)
        conn.close()
        return rows

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

    def dismiss_all_pending_duplicates(self):
        """清理所有pending重复组(标记为dismissed)"""
        conn = self.get_connection(); c = conn.cursor()
        try:
            c.execute("""UPDATE duplicate_groups
                         SET status='dismissed',
                             resolved_at=datetime('now','localtime'),
                             resolved_action='v2.2.2批量清理假阳性'
                         WHERE status='pending'""")
            count = c.rowcount
            conn.commit()
        except:
            count = 0
        conn.close()
        if count > 0:
            self.log_operation("dismiss_all_pending_duplicates", "duplicate_groups",
                               details={"dismissed_count": count})
        return count

    # ================================================================
    # v2.2.0 F029: 专家注解
    # ================================================================
    def add_annotation(self, kp_id, annotation_type, content="", tags=None):
        """添加一条专家注解"""
        conn = self.get_connection(); c = conn.cursor()
        c.execute("""INSERT INTO annotations (knowledge_point_id, annotation_type, content, tags)
                     VALUES (?, ?, ?, ?)""",
                  (kp_id, annotation_type, content,
                   json.dumps(tags or [], ensure_ascii=False)))
        aid = c.lastrowid
        conn.commit(); conn.close()
        self.log_operation("add_annotation", "annotations", aid,
                           {"kp_id": kp_id, "type": annotation_type})
        return aid

    def get_annotations_by_kp(self, kp_id):
        """获取某知识点的全部注解"""
        conn = self.get_connection(); c = conn.cursor()
        c.execute("""SELECT * FROM annotations WHERE knowledge_point_id=?
                     ORDER BY created_at ASC""", (kp_id,))
        rows = [dict(r) for r in c.fetchall()]
        conn.close()
        for r in rows:
            if isinstance(r.get("tags"), str):
                try:
                    r["tags"] = json.loads(r["tags"])
                except:
                    r["tags"] = []
        return rows

    def delete_annotation(self, annotation_id):
        """删除一条注解"""
        conn = self.get_connection(); c = conn.cursor()
        c.execute("DELETE FROM annotations WHERE id=?", (annotation_id,))
        conn.commit(); conn.close()
        self.log_operation("delete_annotation", "annotations", annotation_id)

    def get_annotation_count_by_kp(self, kp_id):
        """获取某知识点的注解数量"""
        conn = self.get_connection(); c = conn.cursor()
        c.execute("SELECT COUNT(*) FROM annotations WHERE knowledge_point_id=?", (kp_id,))
        n = c.fetchone()[0]; conn.close(); return n

    def get_annotation_summary(self):
        """注解统计摘要"""
        conn = self.get_connection(); c = conn.cursor()
        summary = {"annotated_kps": 0, "total_annotations": 0, "by_type": {}}
        try:
            c.execute("SELECT COUNT(DISTINCT knowledge_point_id) FROM annotations")
            summary["annotated_kps"] = c.fetchone()[0]
            c.execute("SELECT COUNT(*) FROM annotations")
            summary["total_annotations"] = c.fetchone()[0]
            c.execute("SELECT annotation_type, COUNT(*) FROM annotations GROUP BY annotation_type")
            for row in c.fetchall():
                summary["by_type"][row[0]] = row[1]
        except:
            pass
        conn.close()
        return summary

    # ================================================================
    # v2.2.3 F057/F058/F060: 结构化事件日志 + 质检补跑候选
    # ================================================================
    def log_operation_event(self, event_type, module, severity="info",
                            file_id=None, kp_id=None, payload=None):
        """
        写入结构化事件日志（供F062端到端测试Agent审计）

        event_type: truncation_recovery / qc_downgrade / rule_fallback /
                    backup_trigger / backup_failed 等
        module: extractor / qc / backup
        severity: info / warning / error
        file_id: 关联source_files.id（可选）
        kp_id: 关联knowledge_points.id（可选）
        payload: dict或任意可json序列化对象，写入payload_json字段
        """
        if severity not in ("info", "warning", "error"):
            severity = "info"
        if payload is None:
            payload_str = "{}"
        elif isinstance(payload, (dict, list)):
            try:
                payload_str = json.dumps(payload, ensure_ascii=False, default=str)
            except Exception:
                payload_str = json.dumps({"_raw": str(payload)}, ensure_ascii=False)
        else:
            payload_str = json.dumps({"_raw": str(payload)}, ensure_ascii=False)

        try:
            conn = self.get_connection(); c = conn.cursor()
            c.execute("""INSERT INTO operation_events
                (event_time, event_type, module, severity,
                 related_file_id, related_kp_id, payload_json)
                VALUES (datetime('now','localtime'), ?, ?, ?, ?, ?, ?)""",
                (event_type, module, severity, file_id, kp_id, payload_str))
            event_id = c.lastrowid
            conn.commit(); conn.close()
            return event_id
        except Exception as e:
            # 事件日志写入失败不应打断主流程，降级为stdout
            print("[log_operation_event 失败] event_type={} module={} err={}".format(
                event_type, module, e))
            return None

    def get_operation_events(self, event_type=None, severity=None,
                             module=None, file_id=None, limit=500):
        """读取事件日志（供前端报告页 / F062审计员用）"""
        conn = self.get_connection(); c = conn.cursor()
        where, vals = [], []
        if event_type:
            where.append("event_type=?"); vals.append(event_type)
        if severity:
            where.append("severity=?"); vals.append(severity)
        if module:
            where.append("module=?"); vals.append(module)
        if file_id is not None:
            where.append("related_file_id=?"); vals.append(file_id)
        sql = "SELECT * FROM operation_events"
        if where:
            sql += " WHERE " + " AND ".join(where)
        sql += " ORDER BY event_id DESC LIMIT ?"
        vals.append(int(limit))
        c.execute(sql, vals)
        rows = [dict(r) for r in c.fetchall()]
        conn.close()
        return rows

    def get_qc_rerun_candidates(self):
        """
        F061 质检补跑：扫描需要重跑质检的知识点
        命中条件（任一即可）：
          1. qa_score IS NULL（从未质检过）
          2. qa_flags 包含 "格式异常"（V3返回格式错误导致质检失败）
        返回知识点dict列表（含source_file_id/title/qa_source等）
        """
        conn = self.get_connection(); c = conn.cursor()
        c.execute("""
            SELECT kp.id, kp.source_file_id, kp.title, kp.content_type,
                   kp.qa_score, kp.qa_flags, kp.qa_source, kp.review_status,
                   kp.original_excerpt, kp.ai_extracted_content,
                   kp.practical_insights,
                   sf.original_filename, sf.renamed_filename
            FROM knowledge_points kp
            LEFT JOIN source_files sf ON kp.source_file_id=sf.id
            WHERE (kp.qa_score IS NULL OR kp.qa_score = 0.0)
               OR kp.qa_flags LIKE '%格式异常%'
            ORDER BY kp.source_file_id, kp.id
        """)
        rows = [dict(r) for r in c.fetchall()]
        conn.close()
        return rows

    def get_qc_rerun_summary(self):
        """F061 质检补跑候选摘要（前端按钮边显示数量用）"""
        conn = self.get_connection(); c = conn.cursor()
        c.execute("""
            SELECT COUNT(*) as total,
                   SUM(CASE WHEN qa_score IS NULL OR qa_score=0.0 THEN 1 ELSE 0 END) as unscored,
                   SUM(CASE WHEN qa_flags LIKE '%格式异常%' THEN 1 ELSE 0 END) as format_err
            FROM knowledge_points
            WHERE (qa_score IS NULL OR qa_score = 0.0)
               OR qa_flags LIKE '%格式异常%'
        """)
        r = c.fetchone()
        conn.close()
        return {
            "total": r[0] or 0,
            "unscored": r[1] or 0,
            "format_err": r[2] or 0
        }

    # ================================================================
    # v2.3.0-part2 F048 知识库体检 Agent 基础层（对话1/3 交付）
    # 两张表 health_reports / polish_suggestions 由 init_tables() 建（v2.3.0-part2.1 起）
    # 本模块只负责 CRUD，引擎逻辑在 health_checker.py（对话2）
    # ================================================================

    # ---- 常量：字段白名单（防止任意字段 UPDATE/INSERT） ----
    _HEALTH_REPORT_INSERT_FIELDS = (
        "created_at", "status", "total_score",
        "dim1_health_score", "dim2_structure_score", "dim3_processing_score",
        "dim4_relation_score", "dim5_polish_score", "dim6_monetize_score",
        "full_report_json", "scanned_kp_count",
        "v3_call_count", "r1_call_count", "cost_estimate", "error_message",
    )
    _HEALTH_REPORT_UPDATE_FIELDS = (
        "status", "total_score",
        "dim1_health_score", "dim2_structure_score", "dim3_processing_score",
        "dim4_relation_score", "dim5_polish_score", "dim6_monetize_score",
        "full_report_json", "scanned_kp_count",
        "v3_call_count", "r1_call_count", "cost_estimate", "error_message",
    )
    _POLISH_SUGGESTION_INSERT_FIELDS = (
        "report_id", "kp_id", "diagnosis", "suggestion_type", "tier",
        "original_content", "suggested_content", "status",
        "applied_at", "created_at",
    )

    # ==================================================
    # 健康报告读写（5 个）
    # ==================================================

    def save_health_report(self, report_data):
        """
        F048: 插入 health_reports，返回 report_id
        status='running' 时数字字段可为 None，完成后 update_health_report 覆写
        只写白名单字段，防污染
        """
        now = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
        data = dict(report_data or {})
        if "created_at" not in data or not data["created_at"]:
            data["created_at"] = now
        if "status" not in data or not data["status"]:
            data["status"] = "running"

        # JSON 字段如果是 dict/list 自动序列化
        if "full_report_json" in data and not isinstance(data["full_report_json"], (str, type(None))):
            data["full_report_json"] = json.dumps(data["full_report_json"], ensure_ascii=False)

        fields = [f for f in self._HEALTH_REPORT_INSERT_FIELDS if f in data]
        if not fields:
            raise ValueError("save_health_report: 至少需要一个有效字段")
        placeholders = ", ".join("?" for _ in fields)
        sql = "INSERT INTO health_reports ({}) VALUES ({})".format(
            ", ".join(fields), placeholders
        )
        values = [data[f] for f in fields]

        conn = self.get_connection(); c = conn.cursor()
        c.execute(sql, values)
        report_id = c.lastrowid
        conn.commit(); conn.close()
        return report_id

    def update_health_report(self, report_id, patch):
        """
        F048: 更新 health_reports 字段（白名单校验）
        返回 True=成功有更新行 / False=无效字段或 report_id 不存在
        """
        if not patch:
            return False
        data = dict(patch)
        # JSON 字段自动序列化
        if "full_report_json" in data and not isinstance(data["full_report_json"], (str, type(None))):
            data["full_report_json"] = json.dumps(data["full_report_json"], ensure_ascii=False)

        fields = [f for f in self._HEALTH_REPORT_UPDATE_FIELDS if f in data]
        if not fields:
            return False
        set_clause = ", ".join("{}=?".format(f) for f in fields)
        sql = "UPDATE health_reports SET {} WHERE report_id=?".format(set_clause)
        values = [data[f] for f in fields] + [report_id]

        conn = self.get_connection(); c = conn.cursor()
        c.execute(sql, values)
        changed = c.rowcount > 0
        conn.commit(); conn.close()
        return changed

    def get_latest_health_report(self):
        """
        F048: 取最新一份 status='completed' 的报告，供趋势对比
        full_report_json 自动解析为 dict/list
        返回 dict 或 None
        """
        conn = self.get_connection(); c = conn.cursor()
        c.execute("""
            SELECT * FROM health_reports
            WHERE status='completed'
            ORDER BY created_at DESC, report_id DESC
            LIMIT 1
        """)
        row = c.fetchone()
        conn.close()
        if not row:
            return None
        r = dict(row)
        r["full_report_json"] = self._safe_json_parse(r.get("full_report_json"), default=None)
        return r

    def get_health_report_list(self, limit=20):
        """
        F048: 历史报告列表，created_at DESC
        不解析 full_report_json（省带宽，详情用 get_health_report_detail）
        """
        try:
            limit = max(1, min(int(limit), 200))
        except (TypeError, ValueError):
            limit = 20
        conn = self.get_connection(); c = conn.cursor()
        c.execute("""
            SELECT report_id, created_at, status, total_score,
                   dim1_health_score, dim2_structure_score, dim3_processing_score,
                   dim4_relation_score, dim5_polish_score, dim6_monetize_score,
                   scanned_kp_count, v3_call_count, r1_call_count, cost_estimate,
                   error_message
              FROM health_reports
             ORDER BY created_at DESC, report_id DESC
             LIMIT ?
        """, (limit,))
        rows = [dict(r) for r in c.fetchall()]
        conn.close()
        return rows

    def get_health_report_detail(self, report_id):
        """
        F048: 单份报告完整数据（含 full_report_json 解析）
        """
        conn = self.get_connection(); c = conn.cursor()
        c.execute("SELECT * FROM health_reports WHERE report_id=?", (report_id,))
        row = c.fetchone()
        conn.close()
        if not row:
            return None
        r = dict(row)
        r["full_report_json"] = self._safe_json_parse(r.get("full_report_json"), default=None)
        return r

    # ==================================================
    # 打磨建议读写（4 个）
    # ==================================================

    def save_polish_suggestion(self, suggestion_data):
        """
        F048: 插入 polish_suggestions，返回 suggestion_id
        只写白名单字段，original_content / suggested_content 自动序列化
        """
        now = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
        data = dict(suggestion_data or {})
        if "created_at" not in data or not data["created_at"]:
            data["created_at"] = now
        if "status" not in data or not data["status"]:
            data["status"] = "pending"

        # 两个 JSON 字段自动序列化
        for f in ("original_content", "suggested_content"):
            if f in data and not isinstance(data[f], (str, type(None))):
                data[f] = json.dumps(data[f], ensure_ascii=False)

        fields = [f for f in self._POLISH_SUGGESTION_INSERT_FIELDS if f in data]
        if "report_id" not in fields or "kp_id" not in fields:
            raise ValueError("save_polish_suggestion: report_id 和 kp_id 必填")
        placeholders = ", ".join("?" for _ in fields)
        sql = "INSERT INTO polish_suggestions ({}) VALUES ({})".format(
            ", ".join(fields), placeholders
        )
        values = [data[f] for f in fields]

        conn = self.get_connection(); c = conn.cursor()
        c.execute(sql, values)
        sid = c.lastrowid
        conn.commit(); conn.close()
        return sid

    def get_polish_suggestions_by_report(self, report_id, status=None):
        """
        F048: 拉取某份报告的打磨建议，可按 status 过滤
        original_content / suggested_content 自动解析为 dict/list
        返回列表按 created_at ASC（先生成的先处理）
        """
        conn = self.get_connection(); c = conn.cursor()
        if status:
            c.execute("""
                SELECT * FROM polish_suggestions
                WHERE report_id=? AND status=?
                ORDER BY created_at ASC, suggestion_id ASC
            """, (report_id, status))
        else:
            c.execute("""
                SELECT * FROM polish_suggestions
                WHERE report_id=?
                ORDER BY created_at ASC, suggestion_id ASC
            """, (report_id,))
        rows = [dict(r) for r in c.fetchall()]
        conn.close()
        for r in rows:
            r["original_content"] = self._safe_json_parse(r.get("original_content"), default=None)
            r["suggested_content"] = self._safe_json_parse(r.get("suggested_content"), default=None)
        return rows

    def apply_polish_suggestion(self, suggestion_id):
        """
        F048: 仅标 status='applied' + applied_at（不动 knowledge_points）
        【事务边界】kp 更新由 api_server 层在本方法前完成，
        保持"备份 → 更新 kp → 标记 suggestion applied"三步清晰
        """
        now = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
        conn = self.get_connection(); c = conn.cursor()
        c.execute("""
            UPDATE polish_suggestions
               SET status='applied', applied_at=?
             WHERE suggestion_id=?
               AND status IN ('pending','manual_review_needed')
        """, (now, suggestion_id))
        changed = c.rowcount > 0
        conn.commit(); conn.close()
        return changed

    def reject_polish_suggestion(self, suggestion_id, reason=""):
        """
        F048: 标 status='rejected'
        reason 参数保留签名（schema 未设 reject_reason 字段），仅 print 日志
        """
        if reason:
            try:
                print("[reject_polish_suggestion] id={} reason={}".format(
                    suggestion_id, reason))
            except Exception:
                pass
        conn = self.get_connection(); c = conn.cursor()
        c.execute("""
            UPDATE polish_suggestions
               SET status='rejected'
             WHERE suggestion_id=?
               AND status IN ('pending','manual_review_needed')
        """, (suggestion_id,))
        changed = c.rowcount > 0
        conn.commit(); conn.close()
        return changed

    # ==================================================
    # 扫描候选查询（3 个）
    # ==================================================

    def get_kp_for_health_scan(self, include_annotations=True):
        """
        F048 维度①②③⑤⑥ 数据源：全量拉取用于扫描的 kp
        SQLite 本地单用户不加 LIMIT，全量加载到内存做分布统计

        字段 AS 映射（对齐 01 工程手册契约）：
          id → kp_id / review_status → status
          source_authority → authority_level / access_level → monetize_tier
          ai_extracted_content 保留原名（供健康检查读提炼内容）
          三层标签字段原名保留（final_category_tags / final_attribute_tags / final_keywords）
          v2.3.0-part2.2 追加：LEFT JOIN categories 后
            c.level1_name → category   （5 大类名，NULL=未分类）
            c.level2_name → subcategory（27 子类名，NULL=未分类）
        annotations_count 通过 LEFT JOIN 聚合
        """
        conn = self.get_connection(); c = conn.cursor()
        if include_annotations:
            sql = """
                SELECT kp.id AS kp_id,
                       kp.source_file_id,
                       kp.title,
                       kp.content_type,
                       kp.final_category_id AS category_id,
                       kp.suggested_category_id,
                       c.level1_name AS category,
                       c.level2_name AS subcategory,
                       kp.final_category_tags,
                       kp.final_attribute_tags,
                       kp.final_keywords,
                       kp.suggested_category_tags,
                       kp.suggested_attribute_tags,
                       kp.suggested_keywords,
                       kp.qa_score,
                       kp.qa_source,
                       kp.qa_flags,
                       kp.original_excerpt,
                       kp.ai_extracted_content,
                       kp.practical_insights,
                       kp.insight_reliability,
                       kp.source_authority AS authority_level,
                       kp.access_level    AS monetize_tier,
                       kp.content_readiness,
                       kp.review_status   AS status,
                       kp.prompt_version,
                       kp.created_at,
                       kp.updated_at,
                       (SELECT COUNT(*) FROM annotations a WHERE a.knowledge_point_id=kp.id)
                           AS annotations_count
                  FROM knowledge_points kp
                  LEFT JOIN categories c ON c.id = kp.final_category_id
                 ORDER BY kp.id ASC
            """
        else:
            sql = """
                SELECT kp.id AS kp_id,
                       kp.source_file_id,
                       kp.title,
                       kp.content_type,
                       kp.final_category_id AS category_id,
                       kp.suggested_category_id,
                       c.level1_name AS category,
                       c.level2_name AS subcategory,
                       kp.final_category_tags,
                       kp.final_attribute_tags,
                       kp.final_keywords,
                       kp.suggested_category_tags,
                       kp.suggested_attribute_tags,
                       kp.suggested_keywords,
                       kp.qa_score,
                       kp.qa_source,
                       kp.qa_flags,
                       kp.original_excerpt,
                       kp.ai_extracted_content,
                       kp.practical_insights,
                       kp.insight_reliability,
                       kp.source_authority AS authority_level,
                       kp.access_level    AS monetize_tier,
                       kp.content_readiness,
                       kp.review_status   AS status,
                       kp.prompt_version,
                       kp.created_at,
                       kp.updated_at
                  FROM knowledge_points kp
                  LEFT JOIN categories c ON c.id = kp.final_category_id
                 ORDER BY kp.id ASC
            """
        c.execute(sql)
        rows = [dict(r) for r in c.fetchall()]
        conn.close()
        # 标签字段自动解析为 list/dict
        for r in rows:
            r["final_category_tags"] = self._safe_json_parse(r.get("final_category_tags"), default=[])
            r["final_attribute_tags"] = self._safe_json_parse(r.get("final_attribute_tags"), default={})
            r["final_keywords"] = self._safe_json_parse(r.get("final_keywords"), default=[])
            r["suggested_category_tags"] = self._safe_json_parse(r.get("suggested_category_tags"), default=[])
            r["suggested_attribute_tags"] = self._safe_json_parse(r.get("suggested_attribute_tags"), default={})
            r["suggested_keywords"] = self._safe_json_parse(r.get("suggested_keywords"), default=[])
            r["qa_flags"] = self._safe_json_parse(r.get("qa_flags"), default=[])
            r["practical_insights"] = self._safe_json_parse(r.get("practical_insights"), default=[])
            r["ai_extracted_content"] = self._safe_json_parse(r.get("ai_extracted_content"), default={})
        return rows

    def get_polish_candidates(self):
        """
        F048 维度⑤低分打磨数据源：
        WHERE (qa_score>0 AND qa_score<=2) OR qa_source='rule_fallback'
          AND review_status NOT IN ('ignored','confirmed','merged')
          AND NOT EXISTS (pending polish_suggestion on same kp)

        关键：qa_score>0 过滤掉"未质检"的 kp（默认值 0.0）
        未质检的应先走 F061 质检补跑，不应进入打磨候选池

        字段契约（v2.3.0-part2.2 新增）：
          LEFT JOIN categories → c.level1_name AS category / c.level2_name AS subcategory
          health_checker._kp_to_full_payload 读这两个字段做 V3 诊断上下文
        """
        conn = self.get_connection(); c = conn.cursor()
        c.execute("""
            SELECT kp.id AS kp_id,
                   kp.source_file_id,
                   kp.title,
                   kp.content_type,
                   kp.final_category_id AS category_id,
                   cat.level1_name AS category,
                   cat.level2_name AS subcategory,
                   kp.final_category_tags,
                   kp.final_attribute_tags,
                   kp.final_keywords,
                   kp.suggested_category_tags,
                   kp.suggested_attribute_tags,
                   kp.suggested_keywords,
                   kp.qa_score,
                   kp.qa_source,
                   kp.qa_flags,
                   kp.original_excerpt,
                   kp.ai_extracted_content,
                   kp.practical_insights,
                   kp.insight_reliability,
                   kp.source_authority AS authority_level,
                   kp.access_level    AS monetize_tier,
                   kp.content_readiness,
                   kp.review_status   AS status,
                   kp.prompt_version,
                   sf.original_filename,
                   sf.renamed_filename
              FROM knowledge_points kp
              LEFT JOIN source_files sf ON kp.source_file_id=sf.id
              LEFT JOIN categories cat ON cat.id = kp.final_category_id
             WHERE (
                     (kp.qa_score > 0 AND kp.qa_score <= 2)
                     OR kp.qa_source = 'rule_fallback'
                   )
               AND kp.review_status NOT IN ('ignored','confirmed','merged')
               AND NOT EXISTS (
                     SELECT 1 FROM polish_suggestions ps
                      WHERE ps.kp_id = kp.id
                        AND ps.status IN ('pending','manual_review_needed')
                   )
             ORDER BY kp.qa_score ASC, kp.id ASC
        """)
        rows = [dict(r) for r in c.fetchall()]
        conn.close()
        for r in rows:
            r["final_category_tags"] = self._safe_json_parse(r.get("final_category_tags"), default=[])
            r["final_attribute_tags"] = self._safe_json_parse(r.get("final_attribute_tags"), default={})
            r["final_keywords"] = self._safe_json_parse(r.get("final_keywords"), default=[])
            r["suggested_category_tags"] = self._safe_json_parse(r.get("suggested_category_tags"), default=[])
            r["suggested_attribute_tags"] = self._safe_json_parse(r.get("suggested_attribute_tags"), default={})
            r["suggested_keywords"] = self._safe_json_parse(r.get("suggested_keywords"), default=[])
            r["qa_flags"] = self._safe_json_parse(r.get("qa_flags"), default=[])
            r["practical_insights"] = self._safe_json_parse(r.get("practical_insights"), default=[])
            r["ai_extracted_content"] = self._safe_json_parse(r.get("ai_extracted_content"), default={})
        return rows

    def get_island_candidates(self):
        """
        F048 维度④关联密度粗筛：
        本地规则：
          - 无 duplicate_groups 关联（未出现在任一 member_ids）
          - 无 annotations
          - 三层标签合并数量 < 3

        返回列表后由 health_checker 调 V3 HEALTH_ISLAND_JUDGE_PROMPT 精判
        避免把"本就稀缺但有价值的独家经验"（niche_topic）误判为孤岛

        字段契约（v2.3.0-part2.2 新增）：
          LEFT JOIN categories → cat.level1_name AS category / cat.level2_name AS subcategory
          health_checker._kp_to_judge_payload 读这两个字段做 V3 孤岛精判上下文
        """
        conn = self.get_connection(); c = conn.cursor()
        c.execute("""
            SELECT kp.id AS kp_id,
                   kp.source_file_id,
                   kp.title,
                   kp.content_type,
                   kp.final_category_id AS category_id,
                   cat.level1_name AS category,
                   cat.level2_name AS subcategory,
                   kp.final_category_tags,
                   kp.final_attribute_tags,
                   kp.final_keywords,
                   kp.suggested_category_tags,
                   kp.suggested_attribute_tags,
                   kp.suggested_keywords,
                   kp.qa_score,
                   kp.original_excerpt,
                   kp.ai_extracted_content,
                   kp.practical_insights,
                   kp.source_authority AS authority_level,
                   kp.access_level    AS monetize_tier,
                   kp.review_status   AS status,
                   (SELECT COUNT(*) FROM annotations a WHERE a.knowledge_point_id=kp.id)
                       AS annotations_count
              FROM knowledge_points kp
              LEFT JOIN categories cat ON cat.id = kp.final_category_id
             WHERE kp.review_status NOT IN ('ignored','merged')
               AND NOT EXISTS (
                     SELECT 1 FROM duplicate_groups dg
                      WHERE dg.member_ids LIKE '%' || kp.id || '%'
                   )
             ORDER BY kp.id ASC
        """)
        raw_rows = [dict(r) for r in c.fetchall()]
        conn.close()

        # Python 侧过滤：annotation_count=0 + tags 总数 <3
        result = []
        for r in raw_rows:
            if (r.get("annotations_count") or 0) > 0:
                continue
            # 合并三层标签计数：优先 final，空则 suggested
            final_tags_list = self._safe_json_parse(r.get("final_category_tags"), default=[]) or []
            final_attr = self._safe_json_parse(r.get("final_attribute_tags"), default={}) or {}
            final_kw = self._safe_json_parse(r.get("final_keywords"), default=[]) or []
            use_final = bool(final_tags_list) or bool(final_attr) or bool(final_kw)
            if use_final:
                tags_total = len(final_tags_list) + len(final_attr) + len(final_kw)
            else:
                sug_tags = self._safe_json_parse(r.get("suggested_category_tags"), default=[]) or []
                sug_attr = self._safe_json_parse(r.get("suggested_attribute_tags"), default={}) or {}
                sug_kw = self._safe_json_parse(r.get("suggested_keywords"), default=[]) or []
                tags_total = len(sug_tags) + len(sug_attr) + len(sug_kw)
            if tags_total >= 3:
                continue
            # 字段规范化（供 health_checker 直接喂给 V3）
            r["final_category_tags"] = final_tags_list
            r["final_attribute_tags"] = final_attr
            r["final_keywords"] = final_kw
            r["suggested_category_tags"] = self._safe_json_parse(r.get("suggested_category_tags"), default=[])
            r["suggested_attribute_tags"] = self._safe_json_parse(r.get("suggested_attribute_tags"), default={})
            r["suggested_keywords"] = self._safe_json_parse(r.get("suggested_keywords"), default=[])
            r["practical_insights"] = self._safe_json_parse(r.get("practical_insights"), default=[])
            r["ai_extracted_content"] = self._safe_json_parse(r.get("ai_extracted_content"), default={})
            r["tags_total_count"] = tags_total
            result.append(r)
        return result

    # ---- JSON 字段安全解析辅助（本模块私有） ----
    @staticmethod
    def _safe_json_parse(s, default=None):
        """
        把 DB 存的 JSON 字符串安全 parse 回 Python 对象
        空/None/非法 JSON 一律返回 default
        """
        if s is None or s == "" or s == "null":
            return default
        if not isinstance(s, str):
            return s  # 已经是 dict/list
        try:
            return json.loads(s)
        except (ValueError, TypeError):
            return default

    def increment_truncation_count(self, file_id):
        """F057: 触发截断补救时+1"""
        conn = self.get_connection(); c = conn.cursor()
        c.execute("""UPDATE source_files
            SET truncation_count = COALESCE(truncation_count, 0) + 1,
                recovery_runs = COALESCE(recovery_runs, 0) + 1,
                last_recovery_at = datetime('now','localtime')
            WHERE id=?""", (file_id,))
        conn.commit(); conn.close()

    def get_truncation_summary(self):
        """F057: 截断统计摘要（供仪表盘/报告用）"""
        conn = self.get_connection(); c = conn.cursor()
        c.execute("""SELECT COUNT(*) FROM source_files
            WHERE COALESCE(truncation_count, 0) > 0""")
        affected_files = c.fetchone()[0] or 0
        c.execute("""SELECT COALESCE(SUM(truncation_count), 0),
                            COALESCE(SUM(recovery_runs), 0)
                     FROM source_files""")
        r = c.fetchone()
        total_truncations = r[0] or 0
        total_recovery_runs = r[1] or 0
        conn.close()
        return {
            "affected_files": affected_files,
            "total_truncations": total_truncations,
            "total_recovery_runs": total_recovery_runs
        }

    # ==================================================
    # v2.3.0-part3-alpha1 F062 端到端健康测试 Agent
    # 8 个新方法：路由自省 3 + 报告读写 3 + issue 四态 2
    # 严格遵守对话 1 Phase 2 锁定契约
    # ==================================================

    # -------- 路由自省（3 个） --------

    def register_endpoint(self, endpoint, methods, test_template=None):
        """登记或更新 Flask 路由。

        endpoint: TEXT 路由路径（PRIMARY KEY），如 "/api/tools/health/start"
        methods:  list[str] 或 str，多方法合成逗号分隔（如 ["GET","POST"] → "GET,POST"）
        test_template: dict 可选，手动定义的测试模板（入参样例/期望响应等），内部 json.dumps

        返回: dict {endpoint, methods, first_seen_at, last_tested_at, test_template_json(已parse)}

        UPSERT 语义：
          - 首次登记：插入 first_seen_at = 当前时间，last_tested_at = NULL
          - 已存在：仅更新 methods（如果 methods 变化时）和 test_template_json（如果非 None）
          - 不改 first_seen_at（"新增端点发现"靠 first_seen_at vs 上份报告 created_at 对比识别）
        """
        if isinstance(methods, (list, tuple, set)):
            methods_str = ",".join(sorted(set(str(m).upper() for m in methods if m)))
        else:
            methods_str = str(methods or "").upper()
        if not methods_str:
            methods_str = "GET"

        tmpl_str = None
        if test_template is not None:
            if isinstance(test_template, (dict, list)):
                try:
                    tmpl_str = json.dumps(test_template, ensure_ascii=False, default=str)
                except Exception:
                    tmpl_str = json.dumps({"_raw": str(test_template)}, ensure_ascii=False)
            elif isinstance(test_template, str):
                tmpl_str = test_template
            else:
                tmpl_str = json.dumps({"_raw": str(test_template)}, ensure_ascii=False)

        now = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
        conn = self.get_connection(); c = conn.cursor()
        c.execute("SELECT * FROM api_endpoint_registry WHERE endpoint=?", (endpoint,))
        row = c.fetchone()
        if row is None:
            c.execute("""INSERT INTO api_endpoint_registry
                (endpoint, methods, first_seen_at, last_tested_at, test_template_json)
                VALUES (?, ?, ?, NULL, ?)""",
                (endpoint, methods_str, now, tmpl_str))
        else:
            # 只更新 methods 和 test_template_json；first_seen_at 保留
            if tmpl_str is not None:
                c.execute("""UPDATE api_endpoint_registry
                    SET methods=?, test_template_json=?
                    WHERE endpoint=?""", (methods_str, tmpl_str, endpoint))
            else:
                c.execute("""UPDATE api_endpoint_registry
                    SET methods=?
                    WHERE endpoint=?""", (methods_str, endpoint))
        conn.commit()
        c.execute("SELECT * FROM api_endpoint_registry WHERE endpoint=?", (endpoint,))
        r = dict(c.fetchone())
        conn.close()
        # 自动 parse test_template_json
        r["test_template_json"] = self._safe_json_parse(r.get("test_template_json"), default=None)
        return r

    def get_endpoint_registry(self):
        """读全量路由登记表。返回 list[dict]，test_template_json 已 parse。"""
        conn = self.get_connection(); c = conn.cursor()
        c.execute("""SELECT endpoint, methods, first_seen_at, last_tested_at,
                            test_template_json
                     FROM api_endpoint_registry
                     ORDER BY first_seen_at ASC, endpoint ASC""")
        rows = [dict(r) for r in c.fetchall()]
        conn.close()
        for r in rows:
            r["test_template_json"] = self._safe_json_parse(
                r.get("test_template_json"), default=None)
        return rows

    def update_endpoint_last_tested(self, endpoint, tested_at=None):
        """标记某条端点的 last_tested_at 时间戳。

        tested_at: ISO 字符串；None 则用当前时间。
        返回: True 成功（行数=1）/ False 未找到端点。
        """
        if tested_at is None:
            tested_at = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
        conn = self.get_connection(); c = conn.cursor()
        c.execute("""UPDATE api_endpoint_registry
                     SET last_tested_at=?
                     WHERE endpoint=?""", (tested_at, endpoint))
        affected = c.rowcount
        conn.commit(); conn.close()
        return affected > 0

    # -------- E2E 测试报告（3 个） --------

    def save_e2e_test_report(self, report_data):
        """保存 E2E 测试整体报告。

        入参 report_data: dict，允许字段（白名单，未列出的字段自动忽略）：
          trigger_type    str  "manual" / "scheduled" / "post_upgrade"
          scan_depth      str  "quick" / "deep" （默认 quick）
          total_endpoints int
          passed_count    int
          failed_count    int
          warning_count   int
          new_endpoints_json   list/dict  (自动 json.dumps)
          full_report_json     list/dict  (自动 json.dumps)
          v3_call_count   int  (默认 0)
          cost_estimate   float (默认 0.0)
          created_at      str  (可选，未传则用当前时间)

        返回: 新插入的 report_id
        """
        whitelist = {
            "trigger_type", "scan_depth", "total_endpoints",
            "passed_count", "failed_count", "warning_count",
            "new_endpoints_json", "full_report_json",
            "v3_call_count", "cost_estimate", "created_at"
        }
        data = {k: v for k, v in (report_data or {}).items() if k in whitelist}
        # created_at 默认当前
        data.setdefault("created_at",
                        datetime.now().strftime("%Y-%m-%d %H:%M:%S"))
        data.setdefault("trigger_type", "manual")
        data.setdefault("scan_depth", "quick")
        data.setdefault("v3_call_count", 0)
        data.setdefault("cost_estimate", 0.0)
        # JSON 字段自动序列化
        for jf in ("new_endpoints_json", "full_report_json"):
            v = data.get(jf)
            if v is None:
                continue
            if isinstance(v, (dict, list)):
                try:
                    data[jf] = json.dumps(v, ensure_ascii=False, default=str)
                except Exception:
                    data[jf] = json.dumps({"_raw": str(v)}, ensure_ascii=False)
            elif not isinstance(v, str):
                data[jf] = json.dumps({"_raw": str(v)}, ensure_ascii=False)

        cols = list(data.keys())
        placeholders = ",".join("?" for _ in cols)
        sql = ("INSERT INTO e2e_test_reports (" + ",".join(cols) +
               ") VALUES (" + placeholders + ")")
        conn = self.get_connection(); c = conn.cursor()
        c.execute(sql, [data[k] for k in cols])
        report_id = c.lastrowid
        conn.commit(); conn.close()
        return report_id

    def get_latest_e2e_test_report(self):
        """取最新一份 E2E 报告的瘦身摘要（不含 full_report_json 省带宽）。
        无数据返回 None。
        new_endpoints_json 自动 parse；full_report_json 不返回。
        """
        conn = self.get_connection(); c = conn.cursor()
        c.execute("""SELECT report_id, created_at, trigger_type, scan_depth,
                            total_endpoints, passed_count, failed_count,
                            warning_count, new_endpoints_json,
                            v3_call_count, cost_estimate
                     FROM e2e_test_reports
                     ORDER BY report_id DESC LIMIT 1""")
        row = c.fetchone()
        conn.close()
        if row is None:
            return None
        r = dict(row)
        r["new_endpoints_json"] = self._safe_json_parse(
            r.get("new_endpoints_json"), default=[])
        return r

    def get_e2e_test_report_detail(self, report_id):
        """取某份 E2E 报告完整内容（含 full_report_json 自动 parse）。"""
        conn = self.get_connection(); c = conn.cursor()
        c.execute("SELECT * FROM e2e_test_reports WHERE report_id=?",
                  (int(report_id),))
        row = c.fetchone()
        conn.close()
        if row is None:
            return None
        r = dict(row)
        r["new_endpoints_json"] = self._safe_json_parse(
            r.get("new_endpoints_json"), default=[])
        r["full_report_json"] = self._safe_json_parse(
            r.get("full_report_json"), default={})
        return r

    # -------- E2E issue 四态跟踪（2 个） --------

    # 偶发升级阈值（类级常量，方便对话 2 引擎层联调时覆盖）
    E2E_INTERMITTENT_WINDOW_DAYS = 7
    E2E_INTERMITTENT_UPGRADE_THRESHOLD = 5

    def upsert_e2e_issue(self, report_id, dim_code, endpoint, severity,
                        signature, payload=None):
        """四态 issue 去重写入 + 偶发升级判定。

        语义：
          - 按 signature 查库
          - 不存在：INSERT,status=pending,occurrence_count=1,first_seen_at=last_seen_at=now
          - 存在且 status in (fixed, ignored)：不动老记录,INSERT 一条新的 pending(允许回归再被关注)
          - 存在且 status in (pending, intermittent)：
                UPDATE 老记录 last_seen_at=now, occurrence_count+=1,
                report_id 刷新为当前 report_id（便于按最新报告定位）
                如果老记录是 intermittent 且 近 EE2E_INTERMITTENT_WINDOW_DAYS 天
                  累计 occurrence_count > E2E_INTERMITTENT_UPGRADE_THRESHOLD
                  → 自动降级升级回 pending（"偶发升级为待修"）

        入参：
          report_id: int 当前 E2E 报告 id（关联到最新报告）
          dim_code:  str  "1_route"/"2_readiness"/"3_prompt_call"/"4_field_contract"/"5_event"/"6_code_smell"
          endpoint:  str|None（维度 3/4/6 可为 None，静态代码规则不挂接口）
          severity:  "info"/"warning"/"error"
          signature: str 去重键（建议 "{dim_code}|{endpoint或'-'}|{rule_id}"）
          payload:   dict/list 详细信息，自动 json.dumps

        返回: issue_id（新插入或被更新的 id）
        """
        if severity not in ("info", "warning", "error"):
            severity = "warning"
        if payload is None:
            payload_str = "{}"
        elif isinstance(payload, (dict, list)):
            try:
                payload_str = json.dumps(payload, ensure_ascii=False, default=str)
            except Exception:
                payload_str = json.dumps({"_raw": str(payload)}, ensure_ascii=False)
        else:
            payload_str = json.dumps({"_raw": str(payload)}, ensure_ascii=False)

        now = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
        conn = self.get_connection(); c = conn.cursor()
        # 找最新一条同 signature 的 pending/intermittent（这两个状态需要合并）
        c.execute("""SELECT issue_id, status, occurrence_count, first_seen_at
                     FROM e2e_issues
                     WHERE signature=? AND status IN ('pending','intermittent')
                     ORDER BY issue_id DESC LIMIT 1""", (signature,))
        existing = c.fetchone()
        if existing is None:
            # 全新：INSERT
            c.execute("""INSERT INTO e2e_issues
                (report_id, dim_code, endpoint, severity, signature,
                 status, first_seen_at, last_seen_at, occurrence_count,
                 resolved_at, payload_json)
                VALUES (?, ?, ?, ?, ?, 'pending', ?, ?, 1, NULL, ?)""",
                (int(report_id), dim_code, endpoint, severity, signature,
                 now, now, payload_str))
            issue_id = c.lastrowid
            conn.commit(); conn.close()
            return issue_id

        # 已存在 pending/intermittent：UPDATE 合并
        issue_id = existing["issue_id"]
        old_status = existing["status"]
        new_count = (existing["occurrence_count"] or 0) + 1
        first_seen = existing["first_seen_at"]

        # 偶发升级判定：仅对 intermittent 判定
        # 条件：近 WINDOW_DAYS 天内累计 > THRESHOLD → 升级回 pending
        new_status = old_status
        if old_status == "intermittent":
            try:
                from datetime import datetime as _dt, timedelta as _td
                first_dt = _dt.strptime(first_seen, "%Y-%m-%d %H:%M:%S")
                now_dt = _dt.strptime(now, "%Y-%m-%d %H:%M:%S")
                within_window = (now_dt - first_dt).days <= self.E2E_INTERMITTENT_WINDOW_DAYS
                if within_window and new_count > self.E2E_INTERMITTENT_UPGRADE_THRESHOLD:
                    new_status = "pending"
            except Exception:
                pass  # 时间解析失败不阻断主流程

        c.execute("""UPDATE e2e_issues
                     SET report_id=?, severity=?, last_seen_at=?,
                         occurrence_count=?, status=?, payload_json=?
                     WHERE issue_id=?""",
                  (int(report_id), severity, now, new_count,
                   new_status, payload_str, issue_id))
        conn.commit(); conn.close()
        return issue_id

    def set_e2e_issue_status(self, issue_id, status, resolved_at=None):
        """手动更新 issue 四态（前端"已修复/忽略"按钮用，对话 3 界面层接入）。

        status: pending / fixed / intermittent / ignored
        resolved_at: fixed/ignored 时自动落当前时间戳（除非显式传）
                     pending/intermittent 时清空 resolved_at
        返回: True 成功 / False 未找到。
        """
        if status not in ("pending", "fixed", "intermittent", "ignored"):
            return False
        if status in ("fixed", "ignored"):
            if resolved_at is None:
                resolved_at = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
        else:
            resolved_at = None
        conn = self.get_connection(); c = conn.cursor()
        c.execute("""UPDATE e2e_issues
                     SET status=?, resolved_at=?
                     WHERE issue_id=?""",
                  (status, resolved_at, int(issue_id)))
        affected = c.rowcount
        conn.commit(); conn.close()
        return affected > 0

