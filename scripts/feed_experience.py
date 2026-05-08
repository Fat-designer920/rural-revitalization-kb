"""
feed_experience.py - 经验喂入: 读 inbox/*.md → 写入 knowledge_points
路径：scripts/feed_experience.py
版本：v2.3.8
用法：python scripts/feed_experience.py [--dry-run]
"""
import os, sys, re, shutil
from pathlib import Path

PROJECT_ROOT = Path(__file__).parent.parent
sys.path.insert(0, str(PROJECT_ROOT))

INBOX = PROJECT_ROOT / "data" / "experience_inbox"
DONE = INBOX / "done"


def parse_md(filepath):
    """解析 .md 文件: 返回 {title, body, tags, subcategory}"""
    with open(filepath, "r", encoding="utf-8") as f:
        text = f.read()

    title = None
    body = text
    tags = []
    subcategory = None

    # 提取第一行 # 标题
    m = re.match(r"^#\s+(.+)$", text, re.MULTILINE)
    if m:
        title = m.group(1).strip()
        body = text[m.end():].strip()

    # 去掉末尾的 --- 元数据块
    sep = body.rfind("\n---\n")
    if sep >= 0:
        meta_block = body[sep + 4:].strip()
        body = body[:sep].strip()
        for line in meta_block.split("\n"):
            line = line.strip()
            if line.startswith("tags:") or line.startswith("tag:"):
                raw = line.split(":", 1)[1].strip()
                tags = [t.strip() for t in raw.split(",") if t.strip()]
            elif line.startswith("subcategory:"):
                subcategory = line.split(":", 1)[1].strip()

    if not title:
        title = Path(filepath).stem

    return {"title": title, "body": body, "tags": tags, "subcategory": subcategory}


def _ensure_source_file(db):
    """确保存在 'manual_experience' 虚拟源文件记录,返回 source_file_id。"""
    conn = db.get_connection()
    c = conn.cursor()
    c.execute("SELECT id FROM source_files WHERE original_filename='手动经验录入'")
    row = c.fetchone()
    if row:
        conn.close()
        return row[0]
    c.execute(
        "INSERT INTO source_files (file_path, original_filename, file_type, file_size, process_status) "
        "VALUES ('manual_experience', '手动经验录入', 'markdown', 0, 'completed')"
    )
    sf_id = c.lastrowid
    conn.commit()
    conn.close()
    return sf_id


def feed_one(db, sf_id, parsed):
    """写入一条经验到 knowledge_points。"""
    import json
    cat_tags = json.dumps(parsed["tags"], ensure_ascii=False) if parsed["tags"] else "[]"
    db.add_knowledge_point(
        source_file_id=sf_id,
        title=parsed["title"],
        content_type="experience",
        original_excerpt=parsed["body"],
        suggested_category_tags=parsed["tags"],
        source_keyword="老唐经验",
        source_type="manual",
        source_authority="firsthand",
        content_readiness="draft",
    )


def main():
    dry_run = "--dry-run" in sys.argv
    from scripts.db_manager import DatabaseManager
    db = DatabaseManager()

    os.makedirs(DONE, exist_ok=True)
    files = sorted(INBOX.glob("*.md"))
    files = [f for f in files if f.name != "_README.md"]

    if not files:
        print("没有待喂入的经验文件。把 .md 放到 data/experience_inbox/ 后再运行。")
        return

    sf_id = _ensure_source_file(db) if not dry_run else 0
    count = 0
    for fp in files:
        parsed = parse_md(str(fp))
        print(f"{'[DRY-RUN]' if dry_run else '[FEED]'} {parsed['title'][:60]}")
        if not dry_run:
            try:
                feed_one(db, sf_id, parsed)
                shutil.move(str(fp), str(DONE / fp.name))
                count += 1
            except Exception as e:
                print(f"  失败: {e}")
        else:
            print(f"  tags={parsed['tags']} subcategory={parsed.get('subcategory','')}")
            count += 1

    print(f"\n完成: {count} 条经验{' (dry-run)' if dry_run else ' 已入库'}")


if __name__ == "__main__":
    main()
