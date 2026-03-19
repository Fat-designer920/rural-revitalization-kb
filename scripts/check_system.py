"""
check_system.py - 系统状态检查
路径：scripts/check_system.py
"""
import os,sys,json,sqlite3,shutil
from pathlib import Path
from datetime import datetime
PROJECT_ROOT = Path(__file__).parent.parent
sys.path.insert(0, str(PROJECT_ROOT))

def get_version():
    p = PROJECT_ROOT/"VERSION"
    return p.read_text(encoding="utf-8").strip() if p.exists() else "unknown"

def check_python():
    print("\n[1] Python环境")
    print(f"    版本: {sys.version}")
    ok = sys.version_info >= (3,8)
    print(f"    {'OK' if ok else 'FAIL'} (需>=3.8)")
    return ok

def check_deps():
    print("\n[2] 依赖库")
    mods = {"flask":"Flask","flask_cors":"Flask-CORS","docx":"python-docx","openpyxl":"openpyxl",
            "PyPDF2":"PyPDF2","pdfplumber":"pdfplumber","PIL":"Pillow","requests":"requests",
            "cryptography":"cryptography","chardet":"chardet","jieba":"jieba"}
    ok = True
    for m,n in mods.items():
        try: __import__(m); print(f"    OK {n}")
        except: print(f"    FAIL {n}"); ok=False
    return ok

def check_config():
    print("\n[3] 配置文件")
    p = PROJECT_ROOT/"config"/"settings.json"
    if not p.exists(): print("    FAIL 不存在"); return False
    try:
        with open(p,"r",encoding="utf-8") as f: c = json.load(f)
        for k,n in [("deepseek_api_key_encrypted","API Key"),("knowledge_base_path","知识库路径"),("database_path","数据库路径")]:
            print(f"    {'OK' if c.get(k) else 'FAIL'} {n}")
        print(f"    费用上限: {c.get('daily_cost_limit','未设置')}元")
        return bool(c.get("deepseek_api_key_encrypted") and c.get("database_path"))
    except: print("    FAIL 格式错误"); return False

def check_db():
    print("\n[4] 数据库")
    p = PROJECT_ROOT/"config"/"settings.json"
    if not p.exists(): print("    跳过"); return False
    with open(p,"r",encoding="utf-8") as f: c = json.load(f)
    dp = c.get("database_path", str(PROJECT_ROOT/"data"/"database"/"knowledge_base.db"))
    if not os.path.exists(dp): print(f"    FAIL 不存在: {dp}"); return False
    try:
        conn = sqlite3.connect(dp); cur = conn.cursor()
        cur.execute("SELECT name FROM sqlite_master WHERE type='table'")
        tables = [r[0] for r in cur.fetchall()]
        for t in ["categories","source_files","knowledge_points","operation_logs","api_call_logs"]:
            if t in tables:
                cur.execute(f"SELECT COUNT(*) FROM {t}"); cnt=cur.fetchone()[0]
                print(f"    OK {t} ({cnt}条)")
            else: print(f"    FAIL {t} 缺失")
        print(f"    大小: {os.path.getsize(dp)/(1024*1024):.2f}MB")
        conn.close(); return True
    except Exception as e: print(f"    FAIL {e}"); return False

def check_dirs():
    print("\n[5] 文件夹")
    p = PROJECT_ROOT/"config"/"settings.json"
    base = PROJECT_ROOT
    if p.exists():
        with open(p,"r",encoding="utf-8") as f: base = Path(json.load(f).get("knowledge_base_path",str(PROJECT_ROOT)))
    ok = True
    for d,desc in [("data/pending","待分析"),("data/processing","处理中"),("data/completed","已处理"),
                    ("data/database","数据库"),("scripts","脚本"),("web/templates","网页")]:
        exists = (base/d).exists()
        print(f"    {'OK' if exists else 'FAIL'} {d}/ ({desc})")
        if not exists: ok=False
    return ok

def check_disk():
    print("\n[6] 磁盘空间")
    try:
        t,u,f = shutil.disk_usage(str(PROJECT_ROOT))
        fg = f/(1024**3)
        print(f"    剩余: {fg:.1f}GB")
        if fg < 1: print("    WARN 不足1GB"); return False
        print(f"    OK"); return True
    except: return True

def main():
    print("="*60)
    print(f"  系统状态检查  v{get_version()}  {datetime.now().strftime('%Y-%m-%d %H:%M')}")
    print("="*60)
    results = [("Python",check_python()), ("依赖库",check_deps()), ("配置",check_config()),
               ("数据库",check_db()), ("文件夹",check_dirs()), ("磁盘",check_disk())]

    print("\n"+"-"*40)
    ans = input("是否测试API连通性? (会消耗少量费用) [y/N]: ").strip().lower()
    if ans == "y":
        print("\n[7] API连通性")
        try:
            from scripts.deepseek_client import DeepSeekClient
            cl = DeepSeekClient()
            u = cl.get_today_usage()
            print(f"    今日: {u['today_cost']}元/{u['daily_limit']}元")
            r = cl.chat("你是助手。","请只回复:正常", max_tokens=10, call_type="health_check")
            print(f"    OK ({r['content'].strip()})"); results.append(("API",True))
        except Exception as e: print(f"    FAIL {e}"); results.append(("API",False))

    print(f"\n{'='*60}")
    ok = sum(1 for _,v in results if v)
    for n,v in results: print(f"  {'OK' if v else 'FAIL'}  {n}")
    print(f"\n  {ok}/{len(results)} 项通过")
    if ok==len(results): print("  系统状态正常!")
    else: print(f"  有{len(results)-ok}项需处理")
    print("="*60)
    input("\n按回车退出...")

if __name__=="__main__": main()
