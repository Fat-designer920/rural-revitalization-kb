"""
migrate_v220_bf5.py - 新增source_files.doc_origin字段
路径：scripts/migrate_v220_bf5.py
版本：v2.2.0 bugfix-5

变更说明：
  - source_files表新增doc_origin字段（self=我的经验文档, external=外部文献）
  - 默认值external，已有记录全部设为external
"""
import sqlite3, json, os, sys
from pathlib import Path

PROJECT_ROOT = Path(__file__).parent.parent
sys.path.insert(0, str(PROJECT_ROOT))

def run_migration():
    config_path = PROJECT_ROOT / "config" / "settings.json"
    if not config_path.exists():
        print("  [SKIP] 未找到配置文件")
        return False

    with open(config_path, "r", encoding="utf-8") as f:
        config = json.load(f)
    db_path = config.get("database_path", str(PROJECT_ROOT / "data" / "database" / "knowledge_base.db"))

    if not os.path.exists(db_path):
        print("  [SKIP] 数据库文件不存在")
        return False

    conn = sqlite3.connect(db_path)
    conn.row_factory = sqlite3.Row
    c = conn.cursor()

    # 检查doc_origin字段是否已存在
    c.execute("PRAGMA table_info(source_files)")
    columns = [row[1] for row in c.fetchall()]

    if "doc_origin" not in columns:
        print("  添加 source_files.doc_origin 字段...")
        c.execute("ALTER TABLE source_files ADD COLUMN doc_origin TEXT DEFAULT 'external'")
        conn.commit()
        print("  [OK] doc_origin 字段已添加")
    else:
        print("  [SKIP] doc_origin 字段已存在")

    conn.close()
    return True

if __name__ == "__main__":
    print("=" * 50)
    print("  v2.2.0 bugfix-5 数据库迁移")
    print("=" * 50)
    run_migration()
    print("  迁移完成")
    input("\n按回车键退出...")
