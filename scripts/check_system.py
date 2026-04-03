"""
check_system.py - 系统状态检查
路径：scripts/check_system.py
版本：v2.3（v2.1.1 F038升级）
升级内容：
  - 保留v2.2全部14项检查
  - 数据库迁移检查新增practical_insights/insight_reliability字段(v2.1.1)
"""
import os, sys, json, sqlite3, shutil
from pathlib import Path
from datetime import datetime

PROJECT_ROOT = Path(__file__).parent.parent
sys.path.insert(0, str(PROJECT_ROOT))

def get_version():
    p = PROJECT_ROOT / "VERSION"
    return p.read_text(encoding="utf-8").strip() if p.exists() else "unknown"

def _load_config():
    """加载配置文件，返回dict或None"""
    p = PROJECT_ROOT / "config" / "settings.json"
    if not p.exists():
        return None
    try:
        with open(p, "r", encoding="utf-8") as f:
            return json.load(f)
    except:
        return None

def _get_db_path(config):
    """从配置获取数据库路径"""
    if config:
        return config.get("database_path",
            str(PROJECT_ROOT / "data" / "database" / "knowledge_base.db"))
    return str(PROJECT_ROOT / "data" / "database" / "knowledge_base.db")

# ================================================================
# 原有基础检查（保留，微调格式）
# ================================================================
def check_python():
    print(f"\n[1] Python环境")
    print(f"    版本: {sys.version.split()[0]}")
    ok = sys.version_info >= (3, 8)
    print(f"    {'OK' if ok else 'FAIL'} (需>=3.8)")
    return ok

def check_deps():
    print(f"\n[2] 依赖库")
    mods = {
        "flask": "Flask", "flask_cors": "Flask-CORS", "docx": "python-docx",
        "openpyxl": "openpyxl", "PyPDF2": "PyPDF2", "pdfplumber": "pdfplumber",
        "PIL": "Pillow", "requests": "requests", "cryptography": "cryptography",
        "chardet": "chardet", "jieba": "jieba"
    }
    ok = True
    for m, n in mods.items():
        try:
            __import__(m)
            print(f"    OK {n}")
        except:
            print(f"    FAIL {n}")
            ok = False
    return ok

def check_config():
    print(f"\n[3] 配置文件")
    config = _load_config()
    if not config:
        print(f"    FAIL 配置文件不存在或格式错误")
        return False
    checks = [
        ("deepseek_api_key_encrypted", "API Key"),
        ("knowledge_base_path", "知识库路径"),
        ("database_path", "数据库路径"),
    ]
    ok = True
    for k, n in checks:
        has = bool(config.get(k))
        print(f"    {'OK' if has else 'FAIL'} {n}")
        if not has and k in ("deepseek_api_key_encrypted", "database_path"):
            ok = False
    limit = config.get("daily_cost_limit", "未设置")
    print(f"    费用上限: {limit}元")
    return ok

def check_db_basic():
    print(f"\n[4] 数据库基础")
    config = _load_config()
    dp = _get_db_path(config)
    if not os.path.exists(dp):
        print(f"    FAIL 数据库文件不存在: {dp}")
        return False
    try:
        conn = sqlite3.connect(dp)
        cur = conn.cursor()
        cur.execute("SELECT name FROM sqlite_master WHERE type='table'")
        tables = [r[0] for r in cur.fetchall()]
        expected_core = [
            "categories", "source_files", "knowledge_points",
            "operation_logs", "api_call_logs", "edit_history",
            "architecture_suggestions",
        ]
        expected_v2 = [
            "tag_definitions", "knowledge_relations",
            "knowledge_usage_log", "tag_statistics",
        ]
        all_ok = True
        for t in expected_core:
            if t in tables:
                cur.execute(f"SELECT COUNT(*) FROM {t}")
                cnt = cur.fetchone()[0]
                print(f"    OK {t} ({cnt}条)")
            else:
                print(f"    FAIL {t} 缺失")
                all_ok = False
        for t in expected_v2:
            if t in tables:
                print(f"    OK {t}")
            else:
                print(f"    WARN {t} 缺失(v2.0.0表)")
        size_mb = os.path.getsize(dp) / (1024 * 1024)
        print(f"    大小: {size_mb:.2f}MB")
        conn.close()
        return all_ok
    except Exception as e:
        print(f"    FAIL {e}")
        return False

def check_dirs():
    print(f"\n[5] 文件夹")
    config = _load_config()
    base = PROJECT_ROOT
    if config:
        base = Path(config.get("knowledge_base_path", str(PROJECT_ROOT)))
    ok = True
    for d, desc in [
        ("data/pending", "待分析"), ("data/processing", "处理中"),
        ("data/completed", "已处理"), ("data/failed", "失败隔离"),
        ("data/database", "数据库"), ("data/backups", "备份"),
        ("scripts", "脚本"), ("scripts/prompts", "Prompt模板"),
        ("web/templates", "网页"),
    ]:
        exists = (base / d).exists()
        print(f"    {'OK' if exists else 'WARN'} {d}/ ({desc})")
        if not exists and d in ("data/database", "scripts"):
            ok = False
    return ok

def check_disk():
    print(f"\n[6] 磁盘空间")
    try:
        t, u, f = shutil.disk_usage(str(PROJECT_ROOT))
        fg = f / (1024 ** 3)
        print(f"    剩余: {fg:.1f}GB")
        if fg < 1:
            print(f"    WARN 不足1GB")
            return False
        print(f"    OK")
        return True
    except:
        return True

# ================================================================
# v2.0 新增：数据库字段完整性
# ================================================================
def check_db_migration():
    print(f"\n[7] 数据库迁移状态(v2.1.1 F038)")
    config = _load_config()
    dp = _get_db_path(config)
    if not os.path.exists(dp):
        print(f"    跳过(数据库不存在)")
        return True
    try:
        conn = sqlite3.connect(dp)
        conn.row_factory = sqlite3.Row
        cur = conn.cursor()
        # 检查source_files新增字段(v2.1.0-c)
        cur.execute("PRAGMA table_info(source_files)")
        sf_cols = {r[1] for r in cur.fetchall()}
        sf_new = ["pre_analysis_result", "suggested_content_type", "segment_plan"]
        sf_ok = True
        for col in sf_new:
            if col in sf_cols:
                print(f"    OK source_files.{col}")
            else:
                print(f"    FAIL source_files.{col} 缺失")
                sf_ok = False
        # 检查knowledge_points新增字段(v2.1.0-c + v2.1.0-d)
        cur.execute("PRAGMA table_info(knowledge_points)")
        kp_cols = {r[1] for r in cur.fetchall()}
        kp_new_c = ["prompt_version", "qa_score", "qa_flags"]
        kp_new_d = ["freshness_note", "policy_dependencies", "policy_validated"]
        kp_new_v211 = ["practical_insights", "insight_reliability"]
        kp_ok = True
        for col in kp_new_c:
            if col in kp_cols:
                print(f"    OK knowledge_points.{col}")
            else:
                print(f"    FAIL knowledge_points.{col} 缺失")
                kp_ok = False
        for col in kp_new_d:
            if col in kp_cols:
                print(f"    OK knowledge_points.{col}")
            else:
                print(f"    WARN knowledge_points.{col} 缺失(v2.1.0-d)")
                print(f"       => 请运行[一键提取.bat]或[保鲜检查.bat]或[政策补跑.bat]触发自动迁移")
        for col in kp_new_v211:
            if col in kp_cols:
                print(f"    OK knowledge_points.{col}")
            else:
                print(f"    WARN knowledge_points.{col} 缺失(v2.1.1)")
                print(f"       => 请运行[一键提取.bat]触发自动迁移")
        conn.close()
        if not sf_ok or not kp_ok:
            print(f"    => 请运行[一键提取.bat]触发自动迁移，或手动运行 migrate_v210c.py")
            return False
        return True
    except Exception as e:
        print(f"    FAIL {e}")
        return False

# ================================================================
# v2.0 新增：知识库健康度概览
# ================================================================
def check_knowledge_health():
    print(f"\n[8] 知识库健康度")
    config = _load_config()
    dp = _get_db_path(config)
    if not os.path.exists(dp):
        print(f"    跳过")
        return True
    try:
        conn = sqlite3.connect(dp)
        cur = conn.cursor()
        cur.execute("SELECT COUNT(*) FROM knowledge_points")
        total = cur.fetchone()[0]
        if total == 0:
            print(f"    知识点: 0条 (知识库为空，请先提取文件)")
            conn.close()
            return True
        cur.execute("""
            SELECT review_status, COUNT(*) FROM knowledge_points
            GROUP BY review_status ORDER BY COUNT(*) DESC
        """)
        status_map = {"pending": "待审核", "confirmed": "已确认", "ignored": "已忽略"}
        status_parts = []
        for row in cur.fetchall():
            label = status_map.get(row[0], row[0] or "未知")
            status_parts.append(f"{label}{row[1]}")
        print(f"    知识点: {total}条 ({' / '.join(status_parts)})")
        cur.execute("""
            SELECT content_type, COUNT(*) FROM knowledge_points
            GROUP BY content_type ORDER BY COUNT(*) DESC
        """)
        type_map = {
            "policy": "政策", "case": "案例", "experience": "经验",
            "tool": "工具", "data": "数据"
        }
        type_parts = []
        for row in cur.fetchall():
            label = type_map.get(row[0], row[0] or "未知")
            type_parts.append(f"{label}{row[1]}")
        print(f"    类型: {' / '.join(type_parts)}")
        cur.execute("""
            SELECT content_readiness, COUNT(*) FROM knowledge_points
            WHERE review_status='confirmed'
            GROUP BY content_readiness
        """)
        rd_map = {"draft": "草稿级", "quotable": "可引用级", "premium": "精品级"}
        rd_parts = []
        for row in cur.fetchall():
            label = rd_map.get(row[0], row[0] or "未设")
            rd_parts.append(f"{label}{row[1]}")
        if rd_parts:
            print(f"    就绪度(已确认): {' / '.join(rd_parts)}")
        cur.execute("SELECT COUNT(*) FROM source_files")
        total_files = cur.fetchone()[0]
        cur.execute("SELECT COUNT(*) FROM source_files WHERE process_status='completed'")
        done_files = cur.fetchone()[0]
        cur.execute("SELECT COUNT(*) FROM source_files WHERE process_status='failed'")
        fail_files = cur.fetchone()[0]
        print(f"    源文件: {total_files}个 (完成{done_files} / 失败{fail_files})")
        conn.close()
        return True
    except Exception as e:
        print(f"    FAIL {e}")
        return False

# ================================================================
# v2.0 新增：Prompt版本检查
# ================================================================
def check_prompt_version():
    print(f"\n[9] Prompt版本")
    try:
        from scripts.prompts.prompt_templates import get_prompt_version
        current = get_prompt_version()
    except:
        try:
            from prompts.prompt_templates import get_prompt_version
            current = get_prompt_version()
        except:
            print(f"    WARN 无法加载prompt_templates")
            return True
    print(f"    当前版本: {current}")
    config = _load_config()
    dp = _get_db_path(config)
    if not os.path.exists(dp):
        return True
    try:
        conn = sqlite3.connect(dp)
        cur = conn.cursor()
        cur.execute("SELECT COUNT(*) FROM knowledge_points WHERE prompt_version IS NOT NULL AND prompt_version != ''")
        has_version = cur.fetchone()[0]
        cur.execute("SELECT COUNT(*) FROM knowledge_points WHERE prompt_version IS NULL OR prompt_version = ''")
        no_version = cur.fetchone()[0]
        if has_version == 0 and no_version == 0:
            print(f"    (暂无知识点)")
            conn.close()
            return True
        if no_version > 0:
            print(f"    {no_version}条知识点无版本标记(迁移前提取)")
        cur.execute("""
            SELECT prompt_version, COUNT(*) FROM knowledge_points
            WHERE prompt_version IS NOT NULL AND prompt_version != ''
            GROUP BY prompt_version ORDER BY prompt_version
        """)
        versions = cur.fetchall()
        old_count = 0
        for row in versions:
            ver = row[0]
            cnt = row[1]
            marker = "" if ver == current else " (旧版本)"
            print(f"    {ver}: {cnt}条{marker}")
            if ver != current:
                old_count += cnt
        if old_count > 0:
            print(f"    => {old_count}条旧版本知识点，可运行[一键知识库升级.bat]批量重提取")
        conn.close()
        return True
    except Exception as e:
        print(f"    WARN {e}")
        return True

# ================================================================
# v2.0 新增：V3质检覆盖率
# ================================================================
def check_qa_coverage():
    print(f"\n[10] V3质检覆盖率")
    config = _load_config()
    dp = _get_db_path(config)
    if not os.path.exists(dp):
        print(f"    跳过")
        return True
    try:
        conn = sqlite3.connect(dp)
        cur = conn.cursor()
        cur.execute("SELECT COUNT(*) FROM knowledge_points")
        total = cur.fetchone()[0]
        if total == 0:
            print(f"    (暂无知识点)")
            conn.close()
            return True
        cur.execute("SELECT COUNT(*) FROM knowledge_points WHERE qa_score IS NOT NULL")
        checked = cur.fetchone()[0]
        unchecked = total - checked
        pct = (checked / total * 100) if total > 0 else 0
        print(f"    已质检: {checked}条 / 总{total}条 ({pct:.0f}%)")
        if unchecked > 0:
            print(f"    未质检: {unchecked}条")
        if checked > 0:
            cur.execute("SELECT AVG(qa_score) FROM knowledge_points WHERE qa_score IS NOT NULL")
            avg = cur.fetchone()[0] or 0
            cur.execute("SELECT COUNT(*) FROM knowledge_points WHERE qa_score IS NOT NULL AND qa_score <= 2")
            low = cur.fetchone()[0]
            cur.execute("SELECT COUNT(*) FROM knowledge_points WHERE qa_score IS NOT NULL AND qa_score >= 4")
            high = cur.fetchone()[0]
            print(f"    平均分: {avg:.1f} (优{high} / 差{low})")
            if low > 0:
                print(f"    => {low}条低分知识点，建议在审核界面使用[质检排序]优先处理")
        conn.close()
        return True
    except Exception as e:
        print(f"    WARN {e}")
        return True

# ================================================================
# v2.0 新增：备份状态
# ================================================================
def check_backup_status():
    print(f"\n[11] 备份状态")
    try:
        from scripts.backup_manager import BackupManager
        bm = BackupManager()
        status = bm.get_backup_status()
    except:
        try:
            from backup_manager import BackupManager
            bm = BackupManager()
            status = bm.get_backup_status()
        except:
            backup_dir = PROJECT_ROOT / "data" / "backups"
            if backup_dir.exists():
                backups = list(backup_dir.glob("*.db"))
                print(f"    备份目录: {len(backups)}个备份文件")
                if not backups:
                    print(f"    => 建议运行[一键备份.bat]创建首个备份")
            else:
                print(f"    备份目录不存在")
                print(f"    => 建议运行[一键备份.bat]")
            return True
    if status:
        count = status.get("backup_count", 0)
        latest = status.get("latest_backup", "无")
        print(f"    备份数量: {count}个")
        print(f"    最近备份: {latest}")
        if count == 0:
            print(f"    => 强烈建议运行[一键备份.bat]创建备份!")
    else:
        print(f"    未获取到备份信息")
    return True

# ================================================================
# v2.0 新增：文件管线状态
# ================================================================
def check_file_pipeline():
    print(f"\n[12] 文件管线")
    config = _load_config()
    base = PROJECT_ROOT
    if config:
        base = Path(config.get("knowledge_base_path", str(PROJECT_ROOT)))
    dirs = {
        "pending": "待分析",
        "processing": "处理中",
        "completed": "已完成",
        "failed": "失败隔离",
    }
    has_stuck = False
    for d, desc in dirs.items():
        dp = base / "data" / d
        if dp.exists():
            files = [f for f in dp.iterdir() if f.is_file() and not f.name.startswith(".")]
            cnt = len(files)
            extra = ""
            if d == "pending" and cnt > 0:
                extra = " => 请运行[处理新文件.bat]"
            elif d == "processing" and cnt > 0:
                extra = " => 请运行[一键提取.bat]"
                has_stuck = True
            elif d == "failed" and cnt > 0:
                extra = " (可手动检查后移回pending重试)"
            print(f"    {desc}: {cnt}个文件{extra}")
        else:
            print(f"    {desc}: 目录不存在")
    return not has_stuck

# ================================================================
# v2.1 新增：保鲜状态检查
# ================================================================
def check_freshness_status():
    print(f"\n[13] 保鲜状态")
    config = _load_config()
    dp = _get_db_path(config)
    if not os.path.exists(dp):
        print(f"    跳过")
        return True
    try:
        conn = sqlite3.connect(dp)
        cur = conn.cursor()
        # 只检查已确认且未过时的知识点
        cur.execute("""
            SELECT COUNT(*) FROM knowledge_points
            WHERE review_status='confirmed' AND (is_outdated IS NULL OR is_outdated=0)
        """)
        confirmed = cur.fetchone()[0]
        if confirmed == 0:
            print(f"    (无已确认知识点)")
            conn.close()
            return True

        # 统计未设保鲜周期的
        cur.execute("""
            SELECT COUNT(*) FROM knowledge_points
            WHERE review_status='confirmed' AND (is_outdated IS NULL OR is_outdated=0)
              AND (freshness_interval_days IS NULL OR freshness_interval_days=0)
        """)
        no_interval = cur.fetchone()[0]

        # 统计已过期的
        cur.execute("""
            SELECT COUNT(*) FROM knowledge_points
            WHERE review_status='confirmed' AND (is_outdated IS NULL OR is_outdated=0)
              AND freshness_interval_days > 0
              AND freshness_checked_at IS NOT NULL
              AND julianday('now') - julianday(freshness_checked_at) > freshness_interval_days
        """)
        expired = cur.fetchone()[0]

        # 统计即将到期的（7天内）
        cur.execute("""
            SELECT COUNT(*) FROM knowledge_points
            WHERE review_status='confirmed' AND (is_outdated IS NULL OR is_outdated=0)
              AND freshness_interval_days > 0
              AND freshness_checked_at IS NOT NULL
              AND julianday('now') - julianday(freshness_checked_at) > freshness_interval_days - 7
              AND julianday('now') - julianday(freshness_checked_at) <= freshness_interval_days
        """)
        expiring = cur.fetchone()[0]

        # 统计已过时的
        cur.execute("""
            SELECT COUNT(*) FROM knowledge_points
            WHERE review_status='confirmed' AND is_outdated=1
        """)
        outdated = cur.fetchone()[0]

        fresh = confirmed - expired - expiring
        if fresh < 0:
            fresh = 0

        print(f"    已确认: {confirmed}条 (新鲜{fresh} / 即将到期{expiring} / 已过期{expired})")

        if outdated > 0:
            print(f"    已过时: {outdated}条")

        if no_interval > 0:
            print(f"    未设保鲜周期: {no_interval}条")
            print(f"    => 运行[保鲜检查.bat]可自动补充默认周期")

        if expired > 0:
            print(f"    => {expired}条已过期，建议在审核界面筛选[保鲜状态-待检查]优先处理")

        conn.close()
        return expired == 0
    except Exception as e:
        print(f"    WARN {e}")
        return True

# ================================================================
# v2.2 新增：政策校验状态检查（F028）
# ================================================================
def check_policy_validation():
    print(f"\n[14] 政策校验状态(F028)")
    config = _load_config()
    dp = _get_db_path(config)
    if not os.path.exists(dp):
        print(f"    跳过")
        return True
    try:
        conn = sqlite3.connect(dp)
        cur = conn.cursor()
        # 检查字段是否存在
        cur.execute("PRAGMA table_info(knowledge_points)")
        cols = {r[1] for r in cur.fetchall()}
        if "policy_validated" not in cols:
            print(f"    (字段不存在,需先运行迁移)")
            conn.close()
            return True

        cur.execute("SELECT COUNT(*) FROM knowledge_points WHERE review_status IN ('pending','confirmed')")
        total = cur.fetchone()[0]
        if total == 0:
            print(f"    (无知识点)")
            conn.close()
            return True

        # 各状态统计
        status_map = {0: "未校验", 1: "已验证", 2: "待验证", 3: "已豁免", 4: "不涉及"}
        cur.execute("""
            SELECT COALESCE(policy_validated, 0) as pv, COUNT(*) as cnt
            FROM knowledge_points
            WHERE review_status IN ('pending','confirmed')
            GROUP BY pv ORDER BY pv
        """)
        parts = []
        pending_count = 0
        unvalidated_count = 0
        for row in cur.fetchall():
            pv = row[0]
            cnt = row[1]
            label = status_map.get(pv, f"状态{pv}")
            parts.append(f"{label}{cnt}")
            if pv == 2:
                pending_count = cnt
            if pv == 0 or pv is None:
                unvalidated_count = cnt

        print(f"    知识点: {total}条 ({' / '.join(parts)})")

        if pending_count > 0:
            print(f"    => {pending_count}条待验证: 有未匹配的政策引用,建议先导入相关政策文件")
            print(f"       在审核界面筛选[政策校验-待验证]查看详情")

        if unvalidated_count > 0:
            # 区分政策类和非政策类
            cur.execute("""
                SELECT COUNT(*) FROM knowledge_points
                WHERE review_status IN ('pending','confirmed')
                  AND (policy_validated IS NULL OR policy_validated=0)
                  AND content_type != 'policy'
            """)
            non_policy_unvalidated = cur.fetchone()[0]
            if non_policy_unvalidated > 0:
                print(f"    => {non_policy_unvalidated}条非政策类知识点未校验")
                print(f"       运行[政策补跑.bat]可补跑校验")

        conn.close()
        return pending_count == 0
    except Exception as e:
        print(f"    WARN {e}")
        return True

# ================================================================
# 主流程
# ================================================================
def main():
    print("=" * 60)
    print(f"  系统状态检查 v2.3")
    print(f"  系统版本: v{get_version()}")
    print(f"  检查时间: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}")
    print("=" * 60)

    # 第一部分：基础环境检查
    print(f"\n{'─' * 40}")
    print(f"  基础环境检查")
    print(f"{'─' * 40}")
    results = []
    results.append(("Python环境", check_python()))
    results.append(("依赖库", check_deps()))
    results.append(("配置文件", check_config()))
    results.append(("数据库基础", check_db_basic()))
    results.append(("文件夹", check_dirs()))
    results.append(("磁盘空间", check_disk()))
    results.append(("数据库迁移", check_db_migration()))

    # 第二部分：知识库状态
    print(f"\n{'─' * 40}")
    print(f"  知识库状态")
    print(f"{'─' * 40}")
    results.append(("知识库健康度", check_knowledge_health()))
    results.append(("Prompt版本", check_prompt_version()))
    results.append(("V3质检覆盖", check_qa_coverage()))
    results.append(("备份状态", check_backup_status()))
    results.append(("文件管线", check_file_pipeline()))
    results.append(("保鲜状态", check_freshness_status()))
    results.append(("政策校验", check_policy_validation()))

    # 第三部分：API连通性（可选）
    print(f"\n{'─' * 40}")
    ans = input("  是否测试API连通性? (会消耗少量费用) [y/N]: ").strip().lower()
    if ans == "y":
        print(f"\n[15] API连通性")
        try:
            from scripts.deepseek_client import DeepSeekClient
            cl = DeepSeekClient()
            u = cl.get_today_usage()
            print(f"    今日费用: {u['today_cost']:.2f}元 / {u['daily_limit']:.0f}元上限")
            print(f"    剩余额度: {u['remaining']:.2f}元")
            r = cl.chat("你是助手。", "请只回复:正常", max_tokens=10, call_type="health_check")
            print(f"    API响应: {r['content'].strip()}")
            print(f"    OK")
            results.append(("API连通", True))
        except Exception as e:
            print(f"    FAIL {e}")
            results.append(("API连通", False))

    # 汇总
    print(f"\n{'=' * 60}")
    print(f"  检查汇总")
    print(f"{'=' * 60}")
    ok_count = sum(1 for _, v in results if v)
    fail_count = len(results) - ok_count
    for name, passed in results:
        print(f"  {'OK' if passed else '!!'} {name}")
    print(f"\n  {ok_count}/{len(results)} 项通过", end="")
    if fail_count > 0:
        print(f"，{fail_count}项需处理")
    else:
        print(f"\n  系统状态正常!")
    print(f"{'=' * 60}")
    input("\n按回车键退出...")

if __name__ == "__main__":
    main()
