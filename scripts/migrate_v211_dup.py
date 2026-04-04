"""
migrate_v211_dup.py - v2.1.1 F039 数据库迁移
路径：scripts/migrate_v211_dup.py
功能：创建duplicate_groups表（重复检测结果存储）
"""
import sqlite3, os, json
from pathlib import Path

PROJECT_ROOT = Path(__file__).parent.parent

def migrate():
    """创建duplicate_groups表（幂等执行）"""
    config_path = PROJECT_ROOT / "config" / "settings.json"
    if config_path.exists():
        with open(config_path, "r", encoding="utf-8") as f:
            config = json.load(f)
        db_path = config.get("database_path",
                             str(PROJECT_ROOT / "data" / "database" / "knowledge_base.db"))
    else:
        db_path = str(PROJECT_ROOT / "data" / "database" / "knowledge_base.db")

    if not os.path.exists(db_path):
        return

    conn = sqlite3.connect(db_path)
    cur = conn.cursor()

    # 检查表是否已存在
    cur.execute("SELECT name FROM sqlite_master WHERE type='table' AND name='duplicate_groups'")
    if cur.fetchone():
        conn.close()
        return

    print("  [迁移] 创建duplicate_groups表(F039重复检测)...")
    cur.execute("""CREATE TABLE IF NOT EXISTS duplicate_groups (
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
    cur.execute("CREATE INDEX IF NOT EXISTS idx_dg_status ON duplicate_groups(status)")

    conn.commit()
    conn.close()
    print("  [迁移] duplicate_groups表创建完成")


if __name__ == "__main__":
    migrate()
    print("迁移完成")
