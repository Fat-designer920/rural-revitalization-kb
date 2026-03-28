"""
migrate_v210d_f028.py - v2.1.0-d F028数据库迁移
路径：scripts/migrate_v210d_f028.py
版本：v2.1.0-d

新增字段：
  - knowledge_points.policy_dependencies (TEXT) - 政策依赖列表(JSON)
  - knowledge_points.policy_validated (INTEGER) - 政策校验状态
    0=未检查, 1=已验证通过, 2=待验证(有未匹配), 3=人工豁免, 4=不涉及政策

幂等执行：自动检测已有列，重复运行不会出错
"""

import sqlite3, os, json
from pathlib import Path

PROJECT_ROOT = Path(__file__).parent.parent


def migrate():
    """执行F028数据库迁移"""
    config_path = PROJECT_ROOT / "config" / "settings.json"
    db_path = ""
    if config_path.exists():
        with open(config_path, "r", encoding="utf-8") as f:
            config = json.load(f)
        db_path = config.get("database_path", "")
    if not db_path:
        db_path = str(PROJECT_ROOT / "data" / "database" / "knowledge_base.db")

    if not os.path.exists(db_path):
        return

    conn = sqlite3.connect(db_path)
    c = conn.cursor()

    # 检查字段是否已存在
    c.execute("PRAGMA table_info(knowledge_points)")
    existing = {row[1] for row in c.fetchall()}

    added = []

    if "policy_dependencies" not in existing:
        c.execute("ALTER TABLE knowledge_points ADD COLUMN policy_dependencies TEXT DEFAULT NULL")
        added.append("policy_dependencies")

    if "policy_validated" not in existing:
        c.execute("ALTER TABLE knowledge_points ADD COLUMN policy_validated INTEGER DEFAULT 0")
        added.append("policy_validated")

    if added:
        conn.commit()
        print(f"  [迁移] F028: knowledge_points新增字段 {', '.join(added)}")

    conn.close()


if __name__ == "__main__":
    migrate()
    print("F028迁移完成")
