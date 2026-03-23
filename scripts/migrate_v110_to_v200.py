"""
migrate_v110_to_v200.py - 数据库迁移脚本
从 v1.1.0 升级到 v2.0.0
新增：三层标签字段、4张新表、5个元数据字段
旧标签自动分流到新字段
路径：scripts/migrate_v110_to_v200.py
"""
import sqlite3, os, json, sys
from pathlib import Path

PROJECT_ROOT = Path(__file__).parent.parent
sys.path.insert(0, str(PROJECT_ROOT))


def get_db_path():
    config_path = PROJECT_ROOT / "config" / "settings.json"
    if config_path.exists():
        with open(config_path, "r", encoding="utf-8") as f:
            config = json.load(f)
        db_path = config.get("database_path", "")
        if db_path: return db_path
    return str(PROJECT_ROOT / "data" / "database" / "knowledge_base.db")


def get_existing_columns(c, table_name):
    c.execute(f"PRAGMA table_info({table_name})")
    return [row[1] for row in c.fetchall()]


def migrate():
    db_path = get_db_path()
    if not os.path.exists(db_path):
        print(f"  [ERROR] 数据库文件不存在: {db_path}")
        return False

    print(f"  数据库路径: {db_path}")
    conn = sqlite3.connect(db_path)
    c = conn.cursor()

    existing_cols = get_existing_columns(c, "knowledge_points")

    # === 1. knowledge_points 新增字段 ===
    new_columns = [
        ("suggested_category_tags", "TEXT DEFAULT '[]'"),
        ("final_category_tags", "TEXT DEFAULT '[]'"),
        ("suggested_attribute_tags", "TEXT DEFAULT '{}'"),
        ("final_attribute_tags", "TEXT DEFAULT '{}'"),
        ("suggested_keywords", "TEXT DEFAULT '[]'"),
        ("final_keywords", "TEXT DEFAULT '[]'"),
        ("content_readiness", "TEXT DEFAULT 'draft'"),
        ("source_authority", "TEXT DEFAULT 'firsthand'"),
        ("access_level", "TEXT DEFAULT 'open'"),
        ("freshness_checked_at", "TEXT DEFAULT NULL"),
        ("freshness_interval_days", "INTEGER DEFAULT 180"),
    ]
    for col_name, col_def in new_columns:
        if col_name not in existing_cols:
            print(f"  新增字段: knowledge_points.{col_name}")
            c.execute(f"ALTER TABLE knowledge_points ADD COLUMN {col_name} {col_def}")
        else:
            print(f"  [OK] {col_name} 已存在")

    # === 2. 新建 tag_definitions 表 ===
    c.execute("SELECT name FROM sqlite_master WHERE type='table' AND name='tag_definitions'")
    if not c.fetchone():
        print(f"  创建表: tag_definitions")
        c.execute("""CREATE TABLE tag_definitions (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            layer TEXT NOT NULL CHECK(layer IN ('layer1','layer2')),
            group_code TEXT NOT NULL, group_name TEXT NOT NULL,
            tag_code TEXT NOT NULL, tag_name TEXT NOT NULL,
            tag_definition TEXT DEFAULT '', is_active INTEGER DEFAULT 1,
            sort_order INTEGER DEFAULT 0,
            created_at TEXT DEFAULT (datetime('now','localtime')))""")
        c.execute("CREATE INDEX IF NOT EXISTS idx_td_layer ON tag_definitions(layer, group_code)")
    else:
        print(f"  [OK] tag_definitions 已存在")

    # === 3. 新建 knowledge_relations 表 ===
    c.execute("SELECT name FROM sqlite_master WHERE type='table' AND name='knowledge_relations'")
    if not c.fetchone():
        print(f"  创建表: knowledge_relations")
        c.execute("""CREATE TABLE knowledge_relations (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            source_kp_id INTEGER NOT NULL, target_kp_id INTEGER NOT NULL,
            relation_type TEXT NOT NULL
                CHECK(relation_type IN ('supports','contradicts','same_source','prerequisite','updated_by','related')),
            created_by TEXT DEFAULT 'manual' CHECK(created_by IN ('ai','manual')),
            created_at TEXT DEFAULT (datetime('now','localtime')),
            FOREIGN KEY (source_kp_id) REFERENCES knowledge_points(id),
            FOREIGN KEY (target_kp_id) REFERENCES knowledge_points(id))""")
        c.execute("CREATE INDEX IF NOT EXISTS idx_kr_source ON knowledge_relations(source_kp_id)")
        c.execute("CREATE INDEX IF NOT EXISTS idx_kr_target ON knowledge_relations(target_kp_id)")
    else:
        print(f"  [OK] knowledge_relations 已存在")

    # === 4. 新建 knowledge_usage_log 表 ===
    c.execute("SELECT name FROM sqlite_master WHERE type='table' AND name='knowledge_usage_log'")
    if not c.fetchone():
        print(f"  创建表: knowledge_usage_log")
        c.execute("""CREATE TABLE knowledge_usage_log (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            knowledge_point_id INTEGER NOT NULL,
            usage_type TEXT NOT NULL CHECK(usage_type IN ('article','course','qa','proposal','export','other')),
            usage_context TEXT DEFAULT '',
            created_at TEXT DEFAULT (datetime('now','localtime')),
            FOREIGN KEY (knowledge_point_id) REFERENCES knowledge_points(id))""")
        c.execute("CREATE INDEX IF NOT EXISTS idx_kul_kpid ON knowledge_usage_log(knowledge_point_id)")
    else:
        print(f"  [OK] knowledge_usage_log 已存在")

    # === 5. 新建 tag_statistics 表 ===
    c.execute("SELECT name FROM sqlite_master WHERE type='table' AND name='tag_statistics'")
    if not c.fetchone():
        print(f"  创建表: tag_statistics")
        c.execute("""CREATE TABLE tag_statistics (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            tag_name TEXT NOT NULL, layer TEXT NOT NULL,
            usage_count INTEGER DEFAULT 0,
            last_updated TEXT DEFAULT (datetime('now','localtime')))""")
    else:
        print(f"  [OK] tag_statistics 已存在")

    # === 6. 补充索引 ===
    for idx_sql in [
        "CREATE INDEX IF NOT EXISTS idx_kp_readiness ON knowledge_points(content_readiness)",
        "CREATE INDEX IF NOT EXISTS idx_kp_access ON knowledge_points(access_level)",
    ]:
        c.execute(idx_sql)

    # === 7. 确保 edit_history 和 architecture_suggestions 存在 ===
    c.execute("SELECT name FROM sqlite_master WHERE type='table' AND name='edit_history'")
    if not c.fetchone():
        print(f"  创建表: edit_history")
        c.execute("""CREATE TABLE edit_history (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            knowledge_point_id INTEGER NOT NULL,
            edited_fields TEXT NOT NULL DEFAULT '{}', edit_summary TEXT DEFAULT '',
            created_at TEXT DEFAULT (datetime('now','localtime')),
            FOREIGN KEY (knowledge_point_id) REFERENCES knowledge_points(id))""")
        c.execute("CREATE INDEX IF NOT EXISTS idx_eh_kpid ON edit_history(knowledge_point_id)")

    as_cols = get_existing_columns(c, "architecture_suggestions")
    if "suggestion_type" not in as_cols:
        print(f"  补充字段: architecture_suggestions.suggestion_type")
        c.execute("ALTER TABLE architecture_suggestions ADD COLUMN suggestion_type TEXT DEFAULT 'add_level2'")

    conn.commit()

    # === 8. 旧标签数据迁移：suggested_tags -> suggested_keywords ===
    print(f"\n  正在迁移旧标签数据到新字段...")
    c.execute("SELECT id, suggested_tags, final_tags FROM knowledge_points")
    rows = c.fetchall()
    migrated = 0
    for row in rows:
        kp_id, st, ft = row[0], row[1], row[2]
        # 旧的suggested_tags -> suggested_keywords（如果新字段为空）
        c.execute("SELECT suggested_keywords FROM knowledge_points WHERE id=?", (kp_id,))
        current_kw = c.fetchone()[0]
        if (not current_kw or current_kw == "[]") and st and st != "[]":
            c.execute("UPDATE knowledge_points SET suggested_keywords=? WHERE id=?", (st, kp_id))
            migrated += 1
        # 旧的final_tags -> final_keywords
        c.execute("SELECT final_keywords FROM knowledge_points WHERE id=?", (kp_id,))
        current_fkw = c.fetchone()[0]
        if (not current_fkw or current_fkw == "[]") and ft and ft != "[]":
            c.execute("UPDATE knowledge_points SET final_keywords=? WHERE id=?", (ft, kp_id))

    conn.commit()
    print(f"  迁移了 {migrated} 条知识点的旧标签到关键词字段")

    # === 9. 初始化标签定义表 ===
    c.execute("SELECT COUNT(*) FROM tag_definitions")
    if c.fetchone()[0] == 0:
        print(f"\n  正在初始化标签定义表...")
        try:
            from scripts.tag_config import LAYER1_TAGS, LAYER2_DIMENSIONS
        except ImportError:
            try:
                from tag_config import LAYER1_TAGS, LAYER2_DIMENSIONS
            except ImportError:
                print(f"  [WARN] 找不到 tag_config.py，跳过标签定义初始化")
                print(f"         请确保 scripts/tag_config.py 存在后重新运行迁移")
                LAYER1_TAGS, LAYER2_DIMENSIONS = None, None

        if LAYER1_TAGS:
            sort = 0
            for group_code, group in LAYER1_TAGS.items():
                for tag in group["tags"]:
                    sort += 1
                    c.execute("""INSERT INTO tag_definitions (layer,group_code,group_name,tag_code,tag_name,tag_definition,sort_order)
                        VALUES (?,?,?,?,?,?,?)""",
                        ("layer1", group_code, group["group_name"], tag["code"], tag["name"], tag["definition"], sort))
            if LAYER2_DIMENSIONS:
                for dim_code, dim in LAYER2_DIMENSIONS.items():
                    for val in dim.get("values", []):
                        sort += 1
                        c.execute("""INSERT INTO tag_definitions (layer,group_code,group_name,tag_code,tag_name,tag_definition,sort_order)
                            VALUES (?,?,?,?,?,?,?)""",
                            ("layer2", dim_code, dim["name"], dim_code, val, "", sort))
            conn.commit()
            print(f"  [OK] 标签定义初始化完成")
    else:
        print(f"  [OK] 标签定义表已有数据")

    conn.close()
    print(f"\n{'=' * 50}")
    print(f"  迁移完成! 数据库已升级到 v2.0.0 结构")
    print(f"  - 知识点表新增11个字段（三层标签+元数据）")
    print(f"  - 新建4张表（标签定义/知识关联/使用追踪/标签统计）")
    print(f"  - 旧标签已迁移到关键词字段")
    print(f"{'=' * 50}")
    return True


if __name__ == "__main__":
    print(f"{'=' * 60}")
    print(f"  乡村振兴知识库 - 数据库迁移 v1.1.0 -> v2.0.0")
    print(f"  !!! 请确保已备份数据库 !!!")
    print(f"{'=' * 60}")
    if migrate():
        print(f"\n  迁移成功!")
    else:
        print(f"\n  迁移失败,请检查上面的错误信息")
    input("\n按回车键退出...")
