"""
setup.py - 一键初始化
路径：scripts/setup.py
"""
import os,sys,json
from pathlib import Path
from datetime import datetime
PROJECT_ROOT = Path(__file__).parent.parent
sys.path.insert(0, str(PROJECT_ROOT))
from scripts.db_manager import DatabaseManager

def get_config():
    p = PROJECT_ROOT/"config"/"settings.json"
    if not p.exists(): print("  未找到配置文件,请先运行配置向导。"); return None
    with open(p,"r",encoding="utf-8") as f: return json.load(f)

def get_version():
    p = PROJECT_ROOT/"VERSION"
    return p.read_text(encoding="utf-8").strip() if p.exists() else "1.0.0"

def main():
    print("="*60)
    print(f"  乡村振兴知识库 - 系统初始化  v{get_version()}")
    print("="*60)
    config = get_config()
    if not config: input("\n按回车退出..."); return

    base = Path(config.get("knowledge_base_path", str(PROJECT_ROOT)))
    print("\n[1] 创建文件夹...")
    for d in ["data/pending","data/processing","data/completed","data/database","data/exports","config","logs","backups","backups/snapshots"]:
        (base/d).mkdir(parents=True, exist_ok=True)
        print(f"    OK {d}/")
    readme = base/"data"/"pending"/"请将待处理文件放在此文件夹中.txt"
    if not readme.exists():
        with open(readme,"w",encoding="utf-8") as f:
            f.write("请将需要AI处理的文件放在此文件夹中。\n支持: PDF, Word(.docx), Excel(.xlsx/.csv), 图片(JPG/PNG), 纯文本(.txt/.md)\n")

    print("\n[2] 初始化数据库...")
    db_path = config.get("database_path", str(base/"data"/"database"/"knowledge_base.db"))
    db = DatabaseManager(db_path)
    db.init_tables(); print("    OK 表结构已创建")
    db.init_default_categories(); print("    OK 27条分类已写入")
    db.log_operation("system_init", details={"version":get_version()})

    print("\n[3] 创建桌面快捷方式...")
    try:
        desktop = Path.home()/"Desktop"
        if not desktop.exists(): desktop = Path.home()/"桌面"
        if desktop.exists():
            vbs = f'''Set s=WScript.CreateObject("WScript.Shell")
Set lnk=s.CreateShortcut("{desktop}\\知识库审核界面.lnk")
lnk.TargetPath="{PROJECT_ROOT}\\启动审核界面.bat"
lnk.WorkingDirectory="{PROJECT_ROOT}"
lnk.Save
Set lnk2=s.CreateShortcut("{desktop}\\处理新文件.lnk")
lnk2.TargetPath="{PROJECT_ROOT}\\处理新文件.bat"
lnk2.WorkingDirectory="{PROJECT_ROOT}"
lnk2.Save'''
            vp = PROJECT_ROOT/"_tmp.vbs"
            with open(vp,"w",encoding="gbk") as f: f.write(vbs)
            os.system(f'cscript //nologo "{vp}"'); os.remove(vp)
            print("    OK 桌面快捷方式已创建")
        else: print("    跳过 (未找到桌面)")
    except Exception as e: print(f"    跳过 ({e})")

    print("\n[4] 验证...")
    scripts = ["scripts/db_manager.py","scripts/config_wizard.py","scripts/file_reader.py",
        "scripts/deepseek_client.py","scripts/preprocessor.py","scripts/extractor.py",
        "scripts/api_server.py","scripts/prompts/prompt_templates.py","web/templates/review.html"]
    ok = True
    for s in scripts:
        if (PROJECT_ROOT/s).exists(): print(f"    OK {s}")
        else: print(f"    !! 缺失 {s}"); ok=False

    print(f"\n{'='*60}")
    if ok:
        print("  系统初始化完成!")
        print("\n  接下来:")
        print("  1. 将文件放入 data/pending/")
        print("  2. 双击[处理新文件.bat]")
        print("  3. 双击[启动审核界面.bat]审核")
    else: print("  初始化完成,但有文件缺失,请检查。")
    print("="*60)
    input("\n按回车退出...")

if __name__=="__main__": main()
