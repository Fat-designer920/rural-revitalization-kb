"""
migrate_v211.py - v2.1.1数据库迁移脚本
路径：scripts/migrate_v211.py
功能：knowledge_points表新增 practical_insights + insight_reliability 字段
幂等执行：已存在的列不会重复添加
"""
import sqlite3, os, json
from pathlib import Path

PROJECT_ROOT = Path(__file__).parent.parent


def migrate():
    """执行v2.1.1数据库迁移"""
    # 读取配置获取数据库路径
    config_path = PROJECT_ROOT / "config" / "settings.json"
    if config_path.exists():
        with open(config_path, "r", encoding="utf-8") as f:
            config = json.load(f)
        db_path = config.get("database_path",
                             str(PROJECT_ROOT / "data" / "database" / "knowledge_base.db"))
    else:
        db_path = str(PROJECT_ROOT / "data" / "database" / "knowledge_base.db")

    if not os.path.exists(db_path):
        return  # 数据库不存在，跳过

    conn = sqlite3.connect(db_path)
    cur = conn.cursor()

    # 获取当前列
    cur.execute("PRAGMA table_info(knowledge_points)")
    existing_cols = {row[1] for row in cur.fetchall()}

    migrations = []

    # practical_insights: JSON数组，存储AI推导的实操启示
    # 格式: [{"insight":"启示内容","basis":"推导依据","confidence":"high/medium/low"}]
    if "practical_insights" not in existing_cols:
        cur.execute("ALTER TABLE knowledge_points ADD COLUMN practical_insights TEXT DEFAULT '[]'")
        migrations.append("practical_insights")

    # insight_reliability: V3质检对举一反三的可靠性评估
    # 取值: reliable / uncertain / unreliable / no_insights / NULL(未质检)
    if "insight_reliability" not in existing_cols:
        cur.execute("ALTER TABLE knowledge_points ADD COLUMN insight_reliability TEXT DEFAULT NULL")
        migrations.append("insight_reliability")

    conn.commit()
    conn.close()

    if migrations:
        print(f"  [迁移] v2.1.1: knowledge_points 新增 {', '.join(migrations)}")
    # 无新增则静默跳过


if __name__ == "__main__":
    migrate()
    print("  v2.1.1 迁移完成")
