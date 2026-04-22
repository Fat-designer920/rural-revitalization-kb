"""
setup.py - 系统初始化（完整建库）
路径：scripts/setup.py
版本：v2.3.0-part2.2

功能：
  1. 创建目录结构（9个目录）
  2. 初始化数据库（18张表，全部字段，一次建成）
  3. 写入27条默认分类 + 标签定义
  4. 插入虚拟source_file记录(id=0, 经验速记入口)
  5. 创建桌面快捷方式
  6. 验证核心文件完整性（v2.3.0-part2.2 新增 health_checker.py / db_health_check.py）

注意：本脚本替代了所有 migrate_*.py 迁移脚本。
      新用户首次安装直接获得最新完整表结构，无需逐版本迁移。

v2.3.0-part2.2 变更（对话 B 防护层）：
  - get_version() 兜底字符串 "2.3.0-part2.1" → "2.3.0-part2.2"
  - 核心文件校验清单追加 2 项（老唐决策锁定）：
      scripts/health_checker.py     (F048 六维度扫描引擎,对话 A 字段契约修复后)
      scripts/db_health_check.py    (数据层只读体检脚本,v1.1 扩 F048 契约一致性)
  - 数据库表数量保持 18 张（无 schema 变更）

v2.3.0-part2.1 变更：
  - init_tables() 已吸收 v2.2.3 / v2.3.0-part2 所有 schema 变更
  - scripts/migrate_v223.py 和 scripts/migrate_v230_part2.py 已退役（删除）
  - 数据库表数量：15张 → 18张（新增 operation_events / health_reports / polish_suggestions）
"""
import os, sys, json
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
    return p.read_text(encoding="utf-8").strip() if p.exists() else "2.3.0-part2.2"


def main():
    print("=" * 60)
    print("  乡村振兴知识库 - 系统初始化  v%s" % get_version())
    print("=" * 60)

    config = get_config()
    if not config:
        input("\n按回车退出...")
        return

    base = Path(config.get("knowledge_base_path", str(PROJECT_ROOT)))

    # ── [1/5] 创建目录结构 ──────────────────────────
    print("\n[1/5] 创建文件夹...")
    dirs = [
        "data/pending", "data/processing", "data/completed",
        "data/database", "data/exports",
        "config", "logs",
        "backups", "backups/snapshots"
    ]
    for d in dirs:
        (base / d).mkdir(parents=True, exist_ok=True)
        print("    OK %s/" % d)

    readme = base / "data" / "pending" / "请将待处理文件放在此文件夹中.txt"
    if not readme.exists():
        with open(readme, "w", encoding="utf-8") as f:
            f.write("请将需要AI处理的文件放在此文件夹中。\n"
                    "支持: PDF, Word(.docx), Excel(.xlsx/.csv), "
                    "图片(JPG/PNG), 纯文本(.txt/.md)\n")

    # ── [2/5] 初始化数据库 ──────────────────────────
    print("\n[2/5] 初始化数据库...")
    db_path = config.get("database_path",
                         str(base / "data" / "database" / "knowledge_base.db"))
    db = DatabaseManager(db_path)
    db.init_tables()
    print("    OK 18张表已创建（全部字段，无需迁移）")

    # ── [3/5] 写入默认分类 ──────────────────────────
    print("\n[3/5] 写入默认分类...")
    db.init_default_categories()
    print("    OK 27条分类已写入")

    # ── [4/5] 写入标签定义 ──────────────────────────
    print("\n[4/5] 写入标签定义...")
    try:
        db.init_tag_definitions()
        print("    OK 标签定义已写入")
    except Exception as e:
        print("    跳过 (%s)" % e)

    # ── [5/5] 插入虚拟source_file(id=0) ─────────────
    print("\n[5/5] 初始化系统记录...")
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
        "scripts/health_checker.py",     # v2.3.0-part2.2 新增（F048 六维度扫描引擎）
        "scripts/db_health_check.py",    # v2.3.0-part2.2 新增（数据层只读体检脚本）
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
