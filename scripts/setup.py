"""
setup.py - 系统初始化（完整建库 + 存量升级,双用脚本）
路径：scripts/setup.py
版本：v2.3.4-hotfix1

功能：
  1. 创建目录结构（9个目录）
  2. 初始化数据库（25张表,全部字段,一次建成）
  3. 写入27条默认分类 + 标签定义
  4. 插入虚拟source_file记录(id=0, 经验速记入口)
  5. [v2.3.1/v2.3.2/v2.3.3-mvp/v2.3.4-hotfix1 新增] 追齐存量库 schema（幂等,新库空跑）
  6. 创建桌面快捷方式
  7. 验证核心文件完整性

注意：本脚本替代了所有 migrate_*.py 迁移脚本。
      新用户首次安装 → init_tables() 一步到位拿最新 schema。
      存量用户(老库)→ init_tables() 幂等 + 追齐步骤 ALTER TABLE ADD COLUMN。
      同一个脚本同时支持"首次安装"和"老库升级",scripts 文件夹不再堆积一次性脚本。

v2.3.4-hotfix1 变更：
  - 截断零提取多模型兜底(L1 Kimi-K2.6 + L2 R1 跨厂商镜像)
  - knowledge_points 表加 extracted_by_model 字段(默认 'r1' 兼容老库)
  - 新增索引 idx_kp_model 走 _upgrade Step 9/10(立规则 60:依赖新字段的索引必须在字段建好后建)
  - _V234_NEW_COLUMNS / _V234_NEW_INDEXES 独立常量,db 表数量不变(25 张)

v2.3.3-mvp-part1a 变更：
  - 双客户端架构 part1a 后端基础设施(part1b qa_public.html / part1c review.html 改造)
  - F063 朋友试用配额管理 (新表 friend_quota_daily) 限速 20 次/天/IP
  - qa_history 加 friend_tag 字段(URL ?u=张三 朋友身份识别,精准反馈分析)
  - 新表 friend_quota_daily(ip + date 复合主键 + count 自增)
  - 1 个新索引: idx_qa_history_friend_tag
  - 数据库表数量: 24 → 25 张
  - _V233_NEW_COLUMNS / _V233_NEW_TABLES_SQL_LIST / _V233_NEW_INDEXES 独立常量
  - _upgrade_schema_to_current 加 Step 6/7/8 处理 v2.3.3-mvp schema
  - 立规则 55 第 4 次落地:不再单独提供 migrate 脚本,合并入本脚本
  - 立规则 9 第 10 次应验:文件验证清单本版补 qa_assistant.py(v2.3.2 注释说加但实际清单遗漏)

v2.3.2 变更：
  - F055 本地问答助手 schema 加入(立规则 55 第 3 次落地,继续合并入本脚本)
  - 新表 qa_history(问答留痕 + 4 板块审计)
  - 新表 qa_feedback(朋友试用 👍/👎/💬 反馈闭环)
  - 4 个新索引: idx_qa_history_created / idx_qa_history_mode /
    idx_qa_history_test / idx_qa_feedback_history
  - knowledge_points 7 字段无新增(v2.3.1 已预埋 used_count/last_used_at/used_for)
  - 核心文件校验清单追加 1 项: qa_assistant.py
  - 数据库表数量: 22 → 24 张
  - 立规则 9 第 9 次应验:Claude 在 setup.py 写表数量"19→21"靠记忆,
    实际 grep init_tables 真相是 22→24。每次写数字都必须 grep 源代码,不靠记。
  - _V232_NEW_TABLES_SQL_LIST + _V232_NEW_INDEXES 独立常量(保留 v2.3.1 常量不动,
    版本可追溯)

v2.3.1 变更：
  - 合并 migrate_v2_3_1.py 核心逻辑为 _upgrade_schema_to_current() 函数
    (立规则第 9 条应验 + 老唐立规则"scripts 不留一次性脚本")
  - knowledge_points 表 7 字段新增: premium_client / premium_rfp /
    premium_tier / used_count / last_used_at / used_for /
    premium_freshness_status
  - 新表 premium_ai_cache(v2.3.1 F2 AI 双视角判定缓存)
  - 3 个新索引: idx_kp_premium_client / idx_kp_premium_rfp /
    idx_premium_cache_kp_view
  - 核心文件校验清单追加 2 项: premium_judge.py / premium_exporter.py
  - 数据库表数量: 18 → 19 张

v2.3.0-part3 变更（对话 B 防护层）：
  - get_version() 兜底字符串 "2.3.0-part2.1" → "2.3.0-part3"
  - 核心文件校验清单追加 2 项（老唐决策锁定）：
      scripts/health_checker.py     (F048 六维度扫描引擎,对话 A 字段契约修复后)
      scripts/db_health_check.py    (数据层只读体检脚本,v1.1 扩 F048 契约一致性)
  - 数据库表数量保持 18 张（无 schema 变更）

v2.3.0-part2.1 变更：
  - init_tables() 已吸收 v2.2.3 / v2.3.0-part2 所有 schema 变更
  - scripts/migrate_v223.py 和 scripts/migrate_v230_part2.py 已退役（删除）
  - 数据库表数量：15张 → 18张（新增 operation_events / health_reports / polish_suggestions）
"""
import os, sys, json, sqlite3
from pathlib import Path

PROJECT_ROOT = Path(__file__).parent.parent
sys.path.insert(0, str(PROJECT_ROOT))
from scripts.db_manager import DatabaseManager


def get_config():
    p = PROJECT_ROOT / "config" / "settings.json"
    if not p.exists():
        print("  未找到配置文件，请先运行配置向导。")
        return None
    with open(p, "r", encoding="utf-8") as f:
        return json.load(f)


def get_version():
    p = PROJECT_ROOT / "VERSION"
    return p.read_text(encoding="utf-8").strip() if p.exists() else "2.3.3-mvp-part1a"


# ================================================================
# v2.3.1 追齐存量库 schema(合并自原 migrate_v2_3_1.py,老唐立规则)
# ----------------------------------------------------------------
# 设计原则:
#   - 新库:init_tables() 已建全,本函数全跳过(PRAGMA table_info 检查)
#   - 老库:ALTER TABLE ADD COLUMN / CREATE TABLE IF NOT EXISTS /
#          CREATE INDEX IF NOT EXISTS 幂等追加
#   - 任意次数运行无副作用(立规则第 8 条)
# ================================================================
_V231_NEW_COLUMNS = [
    ("premium_client", "INTEGER DEFAULT 0"),
    ("premium_rfp", "INTEGER DEFAULT 0"),
    ("premium_tier", "TEXT DEFAULT NULL"),
    ("used_count", "INTEGER DEFAULT 0"),
    ("last_used_at", "TEXT DEFAULT NULL"),
    ("used_for", "TEXT DEFAULT NULL"),
    ("premium_freshness_status", "TEXT DEFAULT NULL"),
]

_V231_NEW_TABLE_SQL = """
CREATE TABLE IF NOT EXISTS premium_ai_cache (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    kp_id INTEGER NOT NULL,
    view TEXT NOT NULL CHECK(view IN ('client','rfp')),
    recommendation TEXT CHECK(recommendation IN ('strong','optional','not')),
    reason TEXT,
    score REAL DEFAULT 0.0,
    source TEXT DEFAULT 'ai' CHECK(source IN ('ai','rule_fallback')),
    generated_at TEXT DEFAULT CURRENT_TIMESTAMP,
    UNIQUE(kp_id, view)
)
"""

_V231_NEW_INDEXES = [
    "CREATE INDEX IF NOT EXISTS idx_kp_premium_client ON knowledge_points(premium_client)",
    "CREATE INDEX IF NOT EXISTS idx_kp_premium_rfp ON knowledge_points(premium_rfp)",
    "CREATE INDEX IF NOT EXISTS idx_premium_cache_kp_view ON premium_ai_cache(kp_id, view)",
]


# ----------------------------------------------------------------
# v2.3.2 追齐存量库 schema(F055 本地问答助手)
# 与 v2.3.1 常量并列, 不合并不重命名(立规则 55: 版本可追溯)
# ----------------------------------------------------------------
_V232_NEW_TABLES_SQL_LIST = [
    ("qa_history", """
CREATE TABLE IF NOT EXISTS qa_history (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    query TEXT NOT NULL,
    answer_json TEXT,
    retrieved_kp_ids TEXT,
    mode TEXT DEFAULT 'self' CHECK(mode IN ('self','friend')),
    source TEXT DEFAULT 'main'
        CHECK(source IN ('main','l1_retry','r1_fallback','rule_fallback')),
    is_test_query INTEGER DEFAULT 0,
    latency_ms INTEGER DEFAULT 0,
    created_at TEXT DEFAULT (datetime('now','localtime'))
)
"""),
    ("qa_feedback", """
CREATE TABLE IF NOT EXISTS qa_feedback (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    qa_history_id INTEGER NOT NULL,
    feedback_type TEXT NOT NULL
        CHECK(feedback_type IN ('helpful','not_helpful','comment')),
    comment TEXT DEFAULT '',
    created_at TEXT DEFAULT (datetime('now','localtime')),
    FOREIGN KEY (qa_history_id) REFERENCES qa_history(id)
)
"""),
]

_V232_NEW_INDEXES = [
    "CREATE INDEX IF NOT EXISTS idx_qa_history_created ON qa_history(created_at DESC)",
    "CREATE INDEX IF NOT EXISTS idx_qa_history_mode ON qa_history(mode, created_at DESC)",
    "CREATE INDEX IF NOT EXISTS idx_qa_history_test ON qa_history(is_test_query, created_at DESC)",
    "CREATE INDEX IF NOT EXISTS idx_qa_feedback_history ON qa_feedback(qa_history_id)",
]


# ================================================================
# v2.3.3-mvp-part1a 追齐:朋友试用配额管理 + 朋友身份识别
# ----------------------------------------------------------------
# 双客户端架构 part1a 后端基础设施:
#   - qa_history 加 friend_tag 字段(URL ?u=张三, 朋友身份精准识别)
#   - 新表 friend_quota_daily(IP 限速 20 次/天)
#   - 1 个索引:idx_qa_history_friend_tag(便于按朋友筛选历史)
# ================================================================
_V233_NEW_COLUMNS = [
    ("friend_tag", "TEXT DEFAULT NULL"),  # 朋友身份(URL ?u=张三),仅 mode=friend 有值
]

_V233_NEW_TABLES_SQL_LIST = [
    ("friend_quota_daily", """
CREATE TABLE IF NOT EXISTS friend_quota_daily (
    ip TEXT NOT NULL,
    date TEXT NOT NULL,
    count INTEGER DEFAULT 0,
    last_at TEXT DEFAULT (datetime('now','localtime')),
    PRIMARY KEY (ip, date)
)
"""),
]

_V233_NEW_INDEXES = [
    "CREATE INDEX IF NOT EXISTS idx_qa_history_friend_tag ON qa_history(friend_tag, created_at DESC)",
]

# v2.3.4-hotfix1: 提取来源模型字段 + 索引
# 立规则 60 落地:索引依赖新字段,必须先 ALTER 加字段(Step 9)再 CREATE INDEX(Step 10),
# 不能放 db_manager.init_tables 的统一 indexes 列表里(老库走 IF NOT EXISTS 跳过 CREATE TABLE,
# extracted_by_model 字段不存在,index 创建会崩 — 与 v2.3.3 idx_qa_history_friend_tag 同模式)
_V234_NEW_COLUMNS = [
    ("extracted_by_model", "TEXT DEFAULT 'r1'"),  # L0=r1 / L1=kimi / L2=r1_mirror / L3=f057_recovery
]

_V234_NEW_INDEXES = [
    "CREATE INDEX IF NOT EXISTS idx_kp_model ON knowledge_points(extracted_by_model)",
]


def _upgrade_schema_to_current(db_path):
    """追齐存量库 schema 到 v2.3.3-mvp-part1a.

    返回 dict 描述本次实际追加的内容(供 setup 主流程打印汇总).
    新库场景下会全部跳过,返回全零值.

    本函数同时处理 v2.3.1 (premium 系列) / v2.3.2 (qa 系列) /
    v2.3.3-mvp (朋友试用配额 + 朋友身份识别) 三批 schema,
    版本常量分组保留, 升级时只看"做了几件"不看"哪个版本做的".
    """
    summary = {
        "columns_added": [], "columns_skipped": [],
        "tables_created": [], "tables_skipped": [],
        "indexes_created": [], "indexes_skipped": [],
    }
    conn = sqlite3.connect(db_path)
    c = conn.cursor()
    try:
        # Step 1: knowledge_points 7 字段幂等追加 (v2.3.1)
        c.execute("PRAGMA table_info(knowledge_points)")
        existing_cols = {r[1] for r in c.fetchall()}
        for col_name, col_def in _V231_NEW_COLUMNS:
            if col_name in existing_cols:
                summary["columns_skipped"].append(col_name)
            else:
                c.execute("ALTER TABLE knowledge_points ADD COLUMN %s %s"
                          % (col_name, col_def))
                summary["columns_added"].append(col_name)

        # Step 2: premium_ai_cache 新表 (v2.3.1, CREATE TABLE IF NOT EXISTS)
        c.execute("SELECT name FROM sqlite_master WHERE type='table' "
                  "AND name='premium_ai_cache'")
        if c.fetchone():
            summary["tables_skipped"].append("premium_ai_cache")
        else:
            c.execute(_V231_NEW_TABLE_SQL)
            summary["tables_created"].append("premium_ai_cache")

        # Step 3: 3 个新索引 (v2.3.1, CREATE INDEX IF NOT EXISTS)
        for idx_sql in _V231_NEW_INDEXES:
            idx_name = idx_sql.split("IF NOT EXISTS")[1].split("ON")[0].strip()
            c.execute("SELECT name FROM sqlite_master WHERE type='index' "
                      "AND name=?", (idx_name,))
            if c.fetchone():
                summary["indexes_skipped"].append(idx_name)
            else:
                c.execute(idx_sql)
                summary["indexes_created"].append(idx_name)

        # Step 4: qa_history / qa_feedback 新表 (v2.3.2)
        for tbl_name, tbl_sql in _V232_NEW_TABLES_SQL_LIST:
            c.execute("SELECT name FROM sqlite_master WHERE type='table' "
                      "AND name=?", (tbl_name,))
            if c.fetchone():
                summary["tables_skipped"].append(tbl_name)
            else:
                c.execute(tbl_sql)
                summary["tables_created"].append(tbl_name)

        # Step 5: 4 个新索引 (v2.3.2, CREATE INDEX IF NOT EXISTS)
        for idx_sql in _V232_NEW_INDEXES:
            idx_name = idx_sql.split("IF NOT EXISTS")[1].split("ON")[0].strip()
            c.execute("SELECT name FROM sqlite_master WHERE type='index' "
                      "AND name=?", (idx_name,))
            if c.fetchone():
                summary["indexes_skipped"].append(idx_name)
            else:
                c.execute(idx_sql)
                summary["indexes_created"].append(idx_name)

        # Step 6: qa_history 加 friend_tag 字段 (v2.3.3-mvp)
        c.execute("PRAGMA table_info(qa_history)")
        qa_existing_cols = {r[1] for r in c.fetchall()}
        for col_name, col_def in _V233_NEW_COLUMNS:
            if col_name in qa_existing_cols:
                summary["columns_skipped"].append(col_name)
            else:
                c.execute("ALTER TABLE qa_history ADD COLUMN %s %s"
                          % (col_name, col_def))
                summary["columns_added"].append(col_name)

        # Step 7: friend_quota_daily 新表 (v2.3.3-mvp)
        for tbl_name, tbl_sql in _V233_NEW_TABLES_SQL_LIST:
            c.execute("SELECT name FROM sqlite_master WHERE type='table' "
                      "AND name=?", (tbl_name,))
            if c.fetchone():
                summary["tables_skipped"].append(tbl_name)
            else:
                c.execute(tbl_sql)
                summary["tables_created"].append(tbl_name)

        # Step 8: 1 个新索引 (v2.3.3-mvp, CREATE INDEX IF NOT EXISTS)
        for idx_sql in _V233_NEW_INDEXES:
            idx_name = idx_sql.split("IF NOT EXISTS")[1].split("ON")[0].strip()
            c.execute("SELECT name FROM sqlite_master WHERE type='index' "
                      "AND name=?", (idx_name,))
            if c.fetchone():
                summary["indexes_skipped"].append(idx_name)
            else:
                c.execute(idx_sql)
                summary["indexes_created"].append(idx_name)

        # Step 9: knowledge_points 加 extracted_by_model 字段 (v2.3.4-hotfix1)
        c.execute("PRAGMA table_info(knowledge_points)")
        kp_existing_cols = {r[1] for r in c.fetchall()}
        for col_name, col_def in _V234_NEW_COLUMNS:
            if col_name in kp_existing_cols:
                summary["columns_skipped"].append(col_name)
            else:
                c.execute("ALTER TABLE knowledge_points ADD COLUMN %s %s"
                          % (col_name, col_def))
                summary["columns_added"].append(col_name)

        # Step 10: idx_kp_model 索引 (v2.3.4-hotfix1, 必须在 Step 9 后)
        for idx_sql in _V234_NEW_INDEXES:
            idx_name = idx_sql.split("IF NOT EXISTS")[1].split("ON")[0].strip()
            c.execute("SELECT name FROM sqlite_master WHERE type='index' "
                      "AND name=?", (idx_name,))
            if c.fetchone():
                summary["indexes_skipped"].append(idx_name)
            else:
                c.execute(idx_sql)
                summary["indexes_created"].append(idx_name)

        conn.commit()
    finally:
        conn.close()
    return summary


def main():
    print("=" * 60)
    print("  乡村振兴知识库 - 系统初始化  v%s" % get_version())
    print("=" * 60)

    config = get_config()
    if not config:
        input("\n按回车退出...")
        return

    base = Path(config.get("knowledge_base_path", str(PROJECT_ROOT)))

    # ── [1/6] 创建目录结构 ──────────────────────────
    # v2.3.1 立规则 9 应验修复:
    #   backup_manager.py 第 54 行硬编码 '<base>/data/backups',
    #   历史 setup.py 曾误创建根目录 'backups/' 和 'backups/snapshots/',
    #   实际无任何代码引用,纯冗余。本版已修正为真实备份路径。
    print("\n[1/6] 创建文件夹...")
    dirs = [
        "data/pending", "data/processing", "data/completed",
        "data/database", "data/exports",
        "data/backups",         # 真实备份目录(与 backup_manager.py 对齐)
        "config", "logs",
    ]
    for d in dirs:
        (base / d).mkdir(parents=True, exist_ok=True)
        print("    OK %s/" % d)

    # v2.3.1 去除 pending 占位说明文档:目录名 "pending" 已说明用途,
    #   文档对用户无增量价值,反而让"文件夹为空"的正常判断变复杂

    # ── [2/6] 初始化数据库 ──────────────────────────
    print("\n[2/6] 初始化数据库...")
    db_path = config.get("database_path",
                         str(base / "data" / "database" / "knowledge_base.db"))
    db = DatabaseManager(db_path)
    db.init_tables()
    print("    OK 25张表已创建（全部字段，无需迁移）")

    # ── [3/6] 写入默认分类 ──────────────────────────
    print("\n[3/6] 写入默认分类...")
    db.init_default_categories()
    print("    OK 27条分类已写入")

    # ── [4/6] 写入标签定义 ──────────────────────────
    print("\n[4/6] 写入标签定义...")
    try:
        db.init_tag_definitions()
        print("    OK 标签定义已写入")
    except Exception as e:
        print("    跳过 (%s)" % e)

    # ── [5/6] 插入虚拟source_file(id=0) ─────────────
    print("\n[5/6] 初始化系统记录...")
    conn = db.get_connection()
    c = conn.cursor()
    c.execute("SELECT id FROM source_files WHERE id=0")
    if not c.fetchone():
        c.execute("""INSERT INTO source_files
                     (id, original_filename, file_path, file_type,
                      process_status, process_message)
                     VALUES (0, '[手动录入]', 'manual_entry', 'manual',
                             'completed', '经验速记入口(v2.2.0)')""")
        conn.commit()
        print("    OK 虚拟source_file(id=0)已创建")
    else:
        print("    OK 虚拟source_file(id=0)已存在")
    conn.close()

    # ── [6/6] 追齐存量库 schema (v2.3.1 + v2.3.2 + v2.3.3-mvp) ────
    # 新库场景下本步骤全部跳过(init_tables 已建全)
    # 老库场景下本步骤会 ALTER TABLE ADD COLUMN / CREATE TABLE IF NOT EXISTS
    # 本函数合并自原 scripts/migrate_v2_3_1.py + v2.3.2/v2.3.3-mvp schema,
    # 立规则 55 第 4 次落地:不再单独提供 migrate 脚本
    print("\n[6/6] 追齐存量库 schema (v2.3.1 + v2.3.2 + v2.3.3-mvp)...")
    try:
        up = _upgrade_schema_to_current(db_path)
        ca = len(up["columns_added"]); cs = len(up["columns_skipped"])
        ta = len(up["tables_created"]); ts = len(up["tables_skipped"])
        ia = len(up["indexes_created"]); is_ = len(up["indexes_skipped"])
        if ca == 0 and ta == 0 and ia == 0:
            print("    OK 存量 schema 已是最新,无需追齐(跳过 %d 字段 / %d 表 / %d 索引)"
                  % (cs, ts, is_))
        else:
            print("    OK 存量库升级:追加 %d 字段 / %d 新表 / %d 新索引"
                  % (ca, ta, ia))
            if up["columns_added"]:
                print("       字段: " + ", ".join(up["columns_added"]))
            if up["tables_created"]:
                print("       新表: " + ", ".join(up["tables_created"]))
            if up["indexes_created"]:
                print("       索引: " + ", ".join(up["indexes_created"]))
    except Exception as e:
        print("    !! 追齐 schema 失败: %s" % e)
        print("       可用 sqlite3 手动查 knowledge_points / premium_ai_cache /"
              " qa_history / qa_feedback / friend_quota_daily 表")

    db.log_operation("system_init", details={"version": get_version()})

    # ── 创建桌面快捷方式 ────────────────────────────
    print("\n[+] 创建桌面快捷方式...")
    try:
        desktop = Path.home() / "Desktop"
        if not desktop.exists():
            desktop = Path.home() / "桌面"
        if desktop.exists():
            vbs = (
                'Set s=WScript.CreateObject("WScript.Shell")\n'
                'Set lnk=s.CreateShortcut("%s\\乡村振兴知识库.lnk")\n'
                'lnk.TargetPath="%s\\启动后台.bat"\n'
                'lnk.WorkingDirectory="%s"\n'
                'lnk.Save'
            ) % (desktop, PROJECT_ROOT, PROJECT_ROOT)
            vp = PROJECT_ROOT / "_tmp.vbs"
            with open(vp, "w", encoding="gbk") as f:
                f.write(vbs)
            os.system('cscript //nologo "%s"' % vp)
            os.remove(vp)
            print("    OK 桌面快捷方式已创建")
        else:
            print("    跳过 (未找到桌面)")
    except Exception as e:
        print("    跳过 (%s)" % e)

    # ── 验证核心文件 ────────────────────────────────
    print("\n[+] 验证核心文件...")
    scripts = [
        "scripts/db_manager.py",
        "scripts/config_wizard.py",
        "scripts/file_reader.py",
        "scripts/deepseek_client.py",
        "scripts/preprocessor.py",
        "scripts/extractor.py",
        "scripts/api_server.py",
        "scripts/health_checker.py",     # v2.3.0-part2.2（F048 六维度扫描引擎）
        "scripts/db_health_check.py",    # v2.3.0-part2.2（数据层只读体检脚本）
        "scripts/static_analyzer.py",    # v2.3.0-part3-alpha1 新增（F062 维度③④⑥ AST 规则库）
        "scripts/e2e_tester.py",         # v2.3.0-part3-alpha2 新增（F062 六维度扫描引擎层）
        "scripts/premium_judge.py",      # v2.3.1 新增（F2 精品候选 AI 双视角判定引擎）
        "scripts/premium_exporter.py",   # v2.3.1 新增（F6 精品导出 Markdown/JSON 格式化）
        "scripts/qa_assistant.py",       # v2.3.2 新增（F055 智能问答四级降级链 + 4 板块组装）
        "scripts/prompts/prompt_templates.py",
        "web/templates/review.html",
    ]
    ok = True
    for s in scripts:
        if (PROJECT_ROOT / s).exists():
            print("    OK %s" % s)
        else:
            print("    !! 缺失 %s" % s)
            ok = False

    print("\n" + "=" * 60)
    if ok:
        print("  系统初始化完成!")
        print("\n  接下来:")
        print("  1. 将文件放入 data/pending/")
        print("  2. 双击桌面[乡村振兴知识库]快捷方式启动管理后台")
        print("  3. 在Tab2系统管理中完成文件预处理和知识提取")
    else:
        print("  初始化完成，但有文件缺失，请检查。")
    print("=" * 60)
    input("\n按回车退出...")


if __name__ == "__main__":
    main()
