"""
migrate_v220.py - v2.2.0 数据库迁移脚本
路径：scripts/migrate_v220.py
功能：
  1. 创建 annotations 表（第15张表）
  2. 插入虚拟 source_file 记录（id=0，代表手动录入）
  3. knowledge_points 表新增 source_type 字段
  4. 新增 annotation_count 索引优化
全部操作幂等，可重复运行。
"""
import sqlite3, json, os
from pathlib import Path

def run_migration(db_path=None):
    if db_path is None:
        project_root = Path(__file__).parent.parent
        config_path = project_root / "config" / "settings.json"
        if config_path.exists():
            with open(config_path, "r", encoding="utf-8") as f:
                db_path = json.load(f).get("database_path", "")
        if not db_path:
            db_path = str(project_root / "data" / "database" / "knowledge_base.db")

    if not os.path.exists(db_path):
        print("  [SKIP] 数据库文件不存在: %s" % db_path)
        return False

    conn = sqlite3.connect(db_path)
    conn.row_factory = sqlite3.Row
    c = conn.cursor()
    changes = []

    # --- 1. 创建 annotations 表 ---
    c.execute("SELECT name FROM sqlite_master WHERE type='table' AND name='annotations'")
    if not c.fetchone():
        c.execute("""CREATE TABLE annotations (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            knowledge_point_id INTEGER NOT NULL,
            annotation_type TEXT NOT NULL
                CHECK(annotation_type IN ('agree','disagree','supplement','correction','experience')),
            content TEXT DEFAULT '',
            tags TEXT DEFAULT '[]',
            created_at TEXT DEFAULT (datetime('now','localtime')),
            FOREIGN KEY (knowledge_point_id) REFERENCES knowledge_points(id)
        )""")
        c.execute("CREATE INDEX IF NOT EXISTS idx_ann_kpid ON annotations(knowledge_point_id)")
        changes.append("创建 annotations 表")
    else:
        print("  [OK] annotations 表已存在")

    # --- 2. 插入虚拟 source_file 记录（id=0） ---
    c.execute("SELECT id FROM source_files WHERE id=0")
    if not c.fetchone():
        # 需要显式指定 id=0
        c.execute("""INSERT INTO source_files (id, original_filename, file_path, file_type,
                     process_status, process_message)
                     VALUES (0, '[手动录入]', 'manual_entry', 'manual', 'completed',
                     '经验速记入口(v2.2.0)')""")
        changes.append("插入虚拟 source_file 记录 (id=0)")
    else:
        print("  [OK] 虚拟 source_file (id=0) 已存在")

    # --- 3. knowledge_points 新增 source_type 字段 ---
    c.execute("PRAGMA table_info(knowledge_points)")
    cols = [row[1] for row in c.fetchall()]
    if "source_type" not in cols:
        c.execute("ALTER TABLE knowledge_points ADD COLUMN source_type TEXT DEFAULT 'extracted'")
        changes.append("knowledge_points 新增 source_type 字段")
    else:
        print("  [OK] source_type 字段已存在")

    conn.commit()
    conn.close()

    if changes:
        print("  [MIGRATE] v2.2.0 迁移完成:")
        for ch in changes:
            print("    - %s" % ch)
    else:
        print("  [OK] v2.2.0 迁移：无需变更")
    return True


if __name__ == "__main__":
    print("=" * 50)
    print("  v2.2.0 数据库迁移")
    print("=" * 50)
    run_migration()
    print("  完成。")
