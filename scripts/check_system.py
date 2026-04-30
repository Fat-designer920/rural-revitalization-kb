"""
check_system.py - 系统状态检查
路径：scripts/check_system.py
版本：v2.3.5-part2-hotfix1.1 - 版本统一(Claude Code 系统修复)

v2.3.0-part2.2 变更（对话 B 防护层扩展）：
v2.3.0-part3 变更（F062 对话 3/3 界面层收尾）：
  - 命令行版 [4] 数据库基础 expected 清单扩到 12 张（+api_endpoint_registry +e2e_test_reports +e2e_issues）
  - JSON 版 [4] 同扩（决策 Q1：F062 是核心业务,老库没升级该早暴露）
  - 命令行版新增 [19] F062 端到端测试就绪度（4 小项:Prompt + static_analyzer + e2e_tester + 9 db 方法）
  - JSON 版新增 "F062 就绪度" 项，汇总时纳入 ok_count 统计

v2.3.0-part2.2 变更（F048 对话 B/C 防护层收尾）：
  - 命令行版新增第 17 项 check_f048_readiness()：F048 体检功能就绪度
      [17.1] 6 个 F048 Prompt 顶层可 import
      [17.2] 6 个 Prompt dict 含非空 system_prompt / user_prompt_template（对话 A 缺陷 4）
      [17.3] health_reports / polish_suggestions 两表存在
      [17.4] 近 2 小时无 status='running' 僵尸任务
  - JSON 版 run_checks_json() 顺手扩 2 处：
      [4] 数据库基础的 expected 表清单追加 health_reports / polish_suggestions（老唐决策Q1）
      末尾追加 [18] F048 就绪度（同命令行第 17 项 4 小项聚合）
  - 主流程 results 追加 "F048 就绪度" 项，汇总时纳入 ok_count 统计

v2.5 - v2.2.0 F029+F045升级：
  - 保留v2.4全部15项检查
  - 新增第16项: 专家注解与经验速记状态检查(F029+F045)
  - 数据库迁移检查新增annotations表+source_type字段
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
    except Exception:
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
        except Exception:
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
            # v2.3.0-part2 F048 两表
            "health_reports", "polish_suggestions",
            # v2.3.0-part3 F062 三表(对话 3 决策 Q1:扩到 12 张)
            "api_endpoint_registry", "e2e_test_reports", "e2e_issues",
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
    except Exception:
        return True

# ================================================================
# v2.0 新增：数据库字段完整性
# ================================================================
def check_db_migration():
    print(f"\n[7] 数据库迁移状态(v2.2.0 F029+F045)")
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
        # v2.2.0 F045: 检查source_type字段
        kp_new_v220 = ["source_type"]
        for col in kp_new_v220:
            if col in kp_cols:
                print(f"    OK knowledge_points.{col}")
            else:
                print(f"    WARN knowledge_points.{col} 缺失(v2.2.0)")
                print(f"       => 请运行迁移脚本 migrate_v220.py")
        # v2.1.1 F039: 检查duplicate_groups表
        cur.execute("SELECT name FROM sqlite_master WHERE type='table' AND name='duplicate_groups'")
        if cur.fetchone():
            print(f"    OK duplicate_groups表")
        else:
            print(f"    WARN duplicate_groups表缺失(v2.1.1 F039)")
            print(f"       => 请运行[重复检测.bat]或[一键提取.bat]触发自动创建")
        # v2.2.0 F029: 检查annotations表
        cur.execute("SELECT name FROM sqlite_master WHERE type='table' AND name='annotations'")
        if cur.fetchone():
            print(f"    OK annotations表")
        else:
            print(f"    WARN annotations表缺失(v2.2.0 F029)")
            print(f"       => 请运行迁移脚本 migrate_v220.py")
        # v2.2.0 F045: 检查source_type字段
        if "source_type" in kp_cols:
            print(f"    OK knowledge_points.source_type")
        else:
            print(f"    WARN knowledge_points.source_type 缺失(v2.2.0)")
            print(f"       => 请运行迁移脚本 migrate_v220.py")
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
    except ImportError:
        try:
            from prompts.prompt_templates import get_prompt_version
            current = get_prompt_version()
        except Exception:
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
    except ImportError:
        try:
            from backup_manager import BackupManager
            bm = BackupManager()
            status = bm.get_backup_status()
        except Exception:
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
# v2.4 新增：重复检测状态检查（F039）
# ================================================================
def check_duplicate_status():
    print(f"\n[15] 重复检测状态(F039)")
    config = _load_config()
    dp = _get_db_path(config)
    if not os.path.exists(dp):
        print(f"    跳过")
        return True
    try:
        conn = sqlite3.connect(dp)
        cur = conn.cursor()
        # 检查表是否存在
        cur.execute("SELECT name FROM sqlite_master WHERE type='table' AND name='duplicate_groups'")
        if not cur.fetchone():
            print(f"    (表不存在,需先运行[重复检测.bat])")
            conn.close()
            return True

        cur.execute("SELECT status, COUNT(*) as cnt FROM duplicate_groups GROUP BY status")
        parts = []
        pending_count = 0
        conflict_count = 0
        for row in cur.fetchall():
            status = row[0]
            cnt = row[1]
            label = {"pending": "待处理", "resolved": "已处理", "dismissed": "已排除"}.get(status, status)
            parts.append(f"{label}{cnt}")
            if status == "pending":
                pending_count = cnt

        if not parts:
            print(f"    (无重复检测记录)")
            conn.close()
            return True

        print(f"    重复组: {' / '.join(parts)}")

        # 统计冲突类
        if pending_count > 0:
            cur.execute("""SELECT COUNT(*) FROM duplicate_groups
                          WHERE status='pending' AND relation_type='conflicting'""")
            conflict_count = cur.fetchone()[0]
            if conflict_count > 0:
                print(f"    => {conflict_count}组知识冲突，建议优先处理!")
            else:
                print(f"    => {pending_count}组待处理，建议在审核界面处理")

        conn.close()
        return pending_count == 0
    except Exception as e:
        print(f"    WARN {e}")
        return True

# ================================================================
# v2.5 新增：专家注解与经验速记状态检查（F029+F045）
# ================================================================
def check_annotation_status():
    print(f"\n[16] 专家注解与经验速记(F029+F045)")
    config = _load_config()
    dp = _get_db_path(config)
    if not os.path.exists(dp):
        print(f"    跳过")
        return True
    try:
        conn = sqlite3.connect(dp)
        cur = conn.cursor()
        cur.execute("SELECT name FROM sqlite_master WHERE type='table' AND name='annotations'")
        if not cur.fetchone():
            print(f"    (annotations表不存在,需运行migrate_v220.py)")
            conn.close()
            return True
        cur.execute("SELECT COUNT(*) FROM annotations")
        total_ann = cur.fetchone()[0]
        if total_ann == 0:
            print(f"    注解: 0条 (尚未添加注解)")
        else:
            cur.execute("SELECT annotation_type, COUNT(*) FROM annotations GROUP BY annotation_type")
            ann_parts = []
            for row in cur.fetchall():
                at_name = {"agree":"实战验证","disagree":"不同意","supplement":"补充",
                           "correction":"纠错","experience":"经验补充"}.get(row[0], row[0])
                ann_parts.append(f"{at_name}{row[1]}")
            print(f"    注解: {total_ann}条 ({' / '.join(ann_parts)})")
            cur.execute("SELECT COUNT(DISTINCT knowledge_point_id) FROM annotations")
            annotated_kps = cur.fetchone()[0]
            print(f"    已注解知识点: {annotated_kps}条")
        cur.execute("PRAGMA table_info(knowledge_points)")
        kp_cols2 = {r[1] for r in cur.fetchall()}
        if "source_type" in kp_cols2:
            cur.execute("SELECT COUNT(*) FROM knowledge_points WHERE source_type='experience_note'")
            exp_count = cur.fetchone()[0]
            print(f"    经验速记入库: {exp_count}条")
        else:
            print(f"    (source_type字段未迁移)")
        conn.close()
        return True
    except Exception as e:
        print(f"    WARN {e}")
        return True

# ================================================================
# v2.5.1 新增：F048 体检功能就绪度检查（v2.3.0-part2.2 对话 B）
# ================================================================
def check_f048_readiness():
    print(f"\n[17] F048 体检功能就绪度(v2.3.0-part2.2)")

    # [17.1] 6 个 F048 Prompt 顶层可 import
    required_prompts = [
        "HEALTH_DIAGNOSIS_PROMPT", "HEALTH_POLISH_PROMPT",
        "HEALTH_POLISH_VERIFY_PROMPT", "HEALTH_POLISH_CONSERVATIVE_PROMPT",
        "HEALTH_ISLAND_JUDGE_PROMPT", "HEALTH_MONETIZE_REPORT_PROMPT",
    ]
    try:
        from scripts.prompts import prompt_templates as pt
    except Exception as e:
        print(f"    FAIL prompt_templates 模块 import 失败: {e}")
        return False
    missing = []
    non_dict = []
    bad_key = []
    for name in required_prompts:
        obj = getattr(pt, name, None)
        if obj is None:
            missing.append(name)
            continue
        if not isinstance(obj, dict):
            non_dict.append(name + "(" + type(obj).__name__ + ")")
            continue
        # [17.2] dict 含非空 system_prompt / user_prompt_template
        if not obj.get("system_prompt"):
            bad_key.append(name + ".system_prompt")
        if not obj.get("user_prompt_template"):
            bad_key.append(name + ".user_prompt_template")

    if missing:
        print(f"    FAIL [17.1] Prompt 未定义或为 None: {', '.join(missing)}")
        print(f"         (对话 A 缺陷 1/2：Prompt 未落地 或 import 静默降级)")
        return False
    if non_dict:
        print(f"    FAIL [17.2] Prompt 非 dict 类型: {', '.join(non_dict)}")
        return False
    if bad_key:
        print(f"    FAIL [17.2] Prompt dict 缺非空 key: {', '.join(bad_key)}")
        print(f"         (对话 A 缺陷 4：key 错配 ['system']→['system_prompt'])")
        return False
    print(f"    OK [17.1/17.2] 6 个 F048 Prompt 全部就绪（name+dict+key 三关通过）")

    # [17.3] health_reports / polish_suggestions 两表存在
    config = _load_config()
    dp = _get_db_path(config)
    if not os.path.exists(dp):
        print(f"    跳过 [17.3] 数据库不存在")
        return True
    try:
        conn = sqlite3.connect(dp)
        cur = conn.cursor()
        cur.execute("SELECT name FROM sqlite_master WHERE type='table' AND name IN ('health_reports','polish_suggestions')")
        f048_tables = {r[0] for r in cur.fetchall()}
        missing_t = []
        for t in ("health_reports", "polish_suggestions"):
            if t not in f048_tables:
                missing_t.append(t)
        if missing_t:
            print(f"    FAIL [17.3] F048 表缺失: {', '.join(missing_t)}")
            print(f"         => 请重跑 setup.py 或检查 init_tables() 是否含两表")
            conn.close()
            return False
        print(f"    OK [17.3] health_reports / polish_suggestions 两表存在")

        # [17.4] 近 2 小时无僵尸任务
        cur.execute("""
            SELECT COUNT(*) FROM health_reports
             WHERE status='running'
               AND julianday('now') - julianday(created_at) > 0.0833
        """)
        zombie = cur.fetchone()[0]
        conn.close()
        if zombie > 0:
            print(f"    WARN [17.4] {zombie} 条 running 超 2 小时（僵尸任务）")
            print(f"         建议用 SQL 手动清理：UPDATE health_reports SET status='failed', error_message='僵尸任务清理' WHERE status='running' AND julianday('now')-julianday(created_at)>0.0833")
        else:
            print(f"    OK [17.4] 无僵尸任务（status=running 超 2 小时）")
        return True
    except Exception as e:
        print(f"    WARN {e}")
        return True

# ================================================================
# v2.1.2 新增：供API调用的JSON版检查（不print，返回结构化数据）
# ================================================================
def run_checks_json():
    """
    执行所有系统检查，返回结构化JSON结果。
    供api_server.py的/api/tools/system-check端点调用。
    不调用print，不调用input，不影响命令行版本。
    """
    results = []
    config = _load_config()
    dp = _get_db_path(config)

    # [1] Python环境
    py_ver = sys.version.split()[0]
    py_ok = sys.version_info >= (3, 8)
    results.append({"name": "Python环境", "ok": py_ok, "detail": "版本 " + py_ver})

    # [2] 依赖库
    mods = {
        "flask": "Flask", "flask_cors": "Flask-CORS", "docx": "python-docx",
        "openpyxl": "openpyxl", "PyPDF2": "PyPDF2", "pdfplumber": "pdfplumber",
        "PIL": "Pillow", "requests": "requests", "cryptography": "cryptography",
        "chardet": "chardet", "jieba": "jieba"
    }
    missing = []
    for m, n in mods.items():
        try:
            __import__(m)
        except Exception:
            missing.append(n)
    results.append({
        "name": "依赖库",
        "ok": len(missing) == 0,
        "detail": "全部就绪" if not missing else "缺失: " + ", ".join(missing)
    })

    # [3] 配置文件
    cfg_ok = config is not None and bool(config.get("deepseek_api_key_encrypted"))
    results.append({
        "name": "配置文件",
        "ok": cfg_ok,
        "detail": "正常" if cfg_ok else "配置缺失或API Key未设置"
    })

    # [4] 数据库基础
    db_exists = os.path.exists(dp) if dp else False
    db_detail = ""
    if db_exists:
        try:
            conn = sqlite3.connect(dp)
            cur = conn.cursor()
            cur.execute("SELECT name FROM sqlite_master WHERE type='table'")
            tables = [r[0] for r in cur.fetchall()]
            # v2.3.0-part3 扩清单：原 7 张核心表 + F048 两表 + F062 三表（对话 3 决策 Q1）
            expected = ["categories", "source_files", "knowledge_points",
                        "operation_logs", "api_call_logs", "edit_history", "architecture_suggestions",
                        "health_reports", "polish_suggestions",
                        "api_endpoint_registry", "e2e_test_reports", "e2e_issues"]
            missing_t = [t for t in expected if t not in tables]
            size_mb = os.path.getsize(dp) / (1024 * 1024)
            db_detail = "%d张表, %.2fMB" % (len(tables), size_mb)
            if missing_t:
                db_detail += ", 缺失: " + ",".join(missing_t)
            conn.close()
        except Exception as e:
            db_detail = str(e)
            missing_t = ["error"]
    else:
        missing_t = ["数据库不存在"]
        db_detail = "数据库文件不存在"
    results.append({"name": "数据库基础", "ok": db_exists and len(missing_t) == 0, "detail": db_detail})

    # [5] 磁盘空间
    try:
        _, _, f = shutil.disk_usage(str(PROJECT_ROOT))
        fg = f / (1024 ** 3)
        results.append({"name": "磁盘空间", "ok": fg >= 1, "detail": "%.1fGB剩余" % fg})
    except Exception:
        results.append({"name": "磁盘空间", "ok": True, "detail": "无法检测"})

    # [6-15] 数据库相关检查（需要数据库存在）
    if not db_exists:
        for name in ["数据库迁移", "知识库健康度", "Prompt版本", "V3质检覆盖",
                      "备份状态", "文件管线", "保鲜状态", "政策校验", "重复检测", "注解与速记"]:
            results.append({"name": name, "ok": True, "detail": "跳过(数据库不存在)"})
        return {"version": "v2.4", "system_version": get_version(),
                "checked_at": datetime.now().strftime("%Y-%m-%d %H:%M:%S"),
                "results": results,
                "ok_count": sum(1 for r in results if r["ok"]),
                "total": len(results)}

    try:
        conn = sqlite3.connect(dp)
        cur = conn.cursor()

        # [6] 数据库迁移
        cur.execute("PRAGMA table_info(knowledge_points)")
        kp_cols = {r[1] for r in cur.fetchall()}
        needed_cols = ["prompt_version", "qa_score", "qa_flags", "freshness_note",
                       "policy_dependencies", "policy_validated", "practical_insights", "insight_reliability",
                       "source_type"]
        missing_cols = [c for c in needed_cols if c not in kp_cols]
        cur.execute("SELECT name FROM sqlite_master WHERE type='table' AND name='duplicate_groups'")
        has_dup_table = cur.fetchone() is not None
        cur.execute("SELECT name FROM sqlite_master WHERE type='table' AND name='annotations'")
        has_ann_table = cur.fetchone() is not None
        mig_detail = "字段完整" if not missing_cols else "缺失: " + ",".join(missing_cols)
        if not has_dup_table:
            mig_detail += "; duplicate_groups表缺失"
        if not has_ann_table:
            mig_detail += "; annotations表缺失"
        results.append({"name": "数据库迁移", "ok": len(missing_cols) == 0 and has_dup_table and has_ann_table, "detail": mig_detail})

        # [7] 知识库健康度
        cur.execute("SELECT COUNT(*) FROM knowledge_points")
        total_kp = cur.fetchone()[0]
        if total_kp == 0:
            results.append({"name": "知识库健康度", "ok": True, "detail": "空库"})
        else:
            cur.execute("SELECT review_status, COUNT(*) FROM knowledge_points GROUP BY review_status")
            st_map = {r[0]: r[1] for r in cur.fetchall()}
            cur.execute("SELECT content_type, COUNT(*) FROM knowledge_points GROUP BY content_type")
            tp_map = {r[0]: r[1] for r in cur.fetchall()}
            tn = {"policy":"政策","case":"案例","experience":"经验","tool":"工具","data":"数据"}
            type_str = " / ".join(["%s%d" % (tn.get(k, k), v) for k, v in tp_map.items()])
            detail = "共%d条 (待审核%d/已确认%d/已忽略%d) | %s" % (
                total_kp, st_map.get("pending", 0), st_map.get("confirmed", 0),
                st_map.get("ignored", 0), type_str)
            results.append({"name": "知识库健康度", "ok": True, "detail": detail})

        # [8] Prompt版本
        try:
            from scripts.prompts.prompt_templates import get_prompt_version
            current_pv = get_prompt_version()
        except ImportError:
            try:
                from prompts.prompt_templates import get_prompt_version
                current_pv = get_prompt_version()
            except Exception:
                current_pv = None
        if current_pv and total_kp > 0:
            cur.execute("SELECT COUNT(*) FROM knowledge_points WHERE prompt_version IS NOT NULL AND prompt_version != ? AND prompt_version != ''", (current_pv,))
            old_count = cur.fetchone()[0]
            results.append({"name": "Prompt版本", "ok": True,
                            "detail": "当前%s, %d条旧版本" % (current_pv, old_count)})
        else:
            results.append({"name": "Prompt版本", "ok": True, "detail": current_pv or "未加载"})

        # [9] V3质检覆盖
        if total_kp > 0:
            cur.execute("SELECT COUNT(*) FROM knowledge_points WHERE qa_score IS NOT NULL")
            checked = cur.fetchone()[0]
            pct = (checked * 100 // total_kp) if total_kp > 0 else 0
            avg_s = 0
            low = 0
            if checked > 0:
                cur.execute("SELECT AVG(qa_score) FROM knowledge_points WHERE qa_score IS NOT NULL")
                avg_s = cur.fetchone()[0] or 0
                cur.execute("SELECT COUNT(*) FROM knowledge_points WHERE qa_score IS NOT NULL AND qa_score <= 2")
                low = cur.fetchone()[0]
            results.append({"name": "V3质检覆盖", "ok": True,
                            "detail": "已质检%d/%d(%d%%), 平均%.1f分, 低分%d条" % (checked, total_kp, pct, avg_s, low)})
        else:
            results.append({"name": "V3质检覆盖", "ok": True, "detail": "空库"})

        # [10] 备份状态
        try:
            from scripts.backup_manager import BackupManager
            bm = BackupManager()
            bs = bm.get_backup_status()
            bcount = bs.get("count", 0) if bs else 0
            blatest = bs.get("latest", "无") if bs else "无"
            results.append({"name": "备份状态", "ok": bcount > 0,
                            "detail": "%d个备份, 最近: %s" % (bcount, blatest)})
        except Exception:
            backup_dir = PROJECT_ROOT / "data" / "backups"
            bcount = len(list(backup_dir.glob("*.db"))) if backup_dir.exists() else 0
            results.append({"name": "备份状态", "ok": bcount > 0,
                            "detail": "%d个备份文件" % bcount})

        # [11] 文件管线
        base = PROJECT_ROOT
        if config:
            base = Path(config.get("knowledge_base_path", str(PROJECT_ROOT)))
        pipeline = {}
        for d in ["pending", "processing", "completed", "failed"]:
            dd = base / "data" / d
            if dd.exists():
                pipeline[d] = len([f for f in dd.iterdir() if f.is_file() and not f.name.startswith(".")])
            else:
                pipeline[d] = 0
        has_stuck = pipeline.get("processing", 0) > 0
        results.append({"name": "文件管线", "ok": not has_stuck,
                        "detail": "待分析%d/处理中%d/已完成%d/失败%d" % (
                            pipeline.get("pending", 0), pipeline.get("processing", 0),
                            pipeline.get("completed", 0), pipeline.get("failed", 0))})

        # [12] 保鲜状态
        if "freshness_checked_at" in kp_cols:
            cur.execute("""SELECT COUNT(*) FROM knowledge_points
                           WHERE review_status='confirmed' AND (is_outdated IS NULL OR is_outdated=0)
                             AND freshness_interval_days > 0 AND freshness_checked_at IS NOT NULL
                             AND julianday('now') - julianday(freshness_checked_at) > freshness_interval_days""")
            expired = cur.fetchone()[0]
            results.append({"name": "保鲜状态", "ok": expired == 0,
                            "detail": "%d条已过期" % expired if expired > 0 else "全部新鲜"})
        else:
            results.append({"name": "保鲜状态", "ok": True, "detail": "字段未迁移"})

        # [13] 政策校验
        if "policy_validated" in kp_cols:
            cur.execute("""SELECT COUNT(*) FROM knowledge_points
                           WHERE review_status IN ('pending','confirmed') AND policy_validated=2""")
            pending_pv = cur.fetchone()[0]
            results.append({"name": "政策校验", "ok": pending_pv == 0,
                            "detail": "%d条待验证" % pending_pv if pending_pv > 0 else "全部通过"})
        else:
            results.append({"name": "政策校验", "ok": True, "detail": "字段未迁移"})

        # [14] 重复检测
        if has_dup_table:
            cur.execute("SELECT COUNT(*) FROM duplicate_groups WHERE status='pending'")
            pending_dup = cur.fetchone()[0]
            cur.execute("SELECT COUNT(*) FROM duplicate_groups WHERE status='pending' AND relation_type='conflicting'")
            conflict = cur.fetchone()[0]
            detail = "%d组待处理" % pending_dup if pending_dup > 0 else "无待处理"
            if conflict > 0:
                detail += ", %d组冲突!" % conflict
            results.append({"name": "重复检测", "ok": pending_dup == 0, "detail": detail})
        else:
            results.append({"name": "重复检测", "ok": True, "detail": "表未创建"})

        # [15] 专家注解与经验速记(v2.2.0)
        if has_ann_table:
            cur2 = conn.cursor()
            cur2.execute("SELECT COUNT(*) FROM annotations")
            total_ann = cur2.fetchone()[0]
            cur2.execute("SELECT COUNT(DISTINCT knowledge_point_id) FROM annotations")
            annotated_kps = cur2.fetchone()[0]
            ann_detail = "%d条注解, %d个知识点已注解" % (total_ann, annotated_kps)
            if "source_type" in kp_cols:
                cur2.execute("SELECT COUNT(*) FROM knowledge_points WHERE source_type='experience_note'")
                exp_cnt = cur2.fetchone()[0]
                ann_detail += ", %d条经验速记" % exp_cnt
            results.append({"name": "注解与速记", "ok": True, "detail": ann_detail})
        else:
            results.append({"name": "注解与速记", "ok": True, "detail": "表未创建(需运行migrate_v220.py)"})

        conn.close()
    except Exception as e:
        results.append({"name": "数据库检查", "ok": False, "detail": str(e)})

    # v2.5.1 新增 [18] F048 就绪度
    f048_ok = True
    f048_detail_parts = []
    required_prompts = [
        "HEALTH_DIAGNOSIS_PROMPT", "HEALTH_POLISH_PROMPT",
        "HEALTH_POLISH_VERIFY_PROMPT", "HEALTH_POLISH_CONSERVATIVE_PROMPT",
        "HEALTH_ISLAND_JUDGE_PROMPT", "HEALTH_MONETIZE_REPORT_PROMPT",
    ]
    try:
        from scripts.prompts import prompt_templates as pt
        prompt_bad = []
        for name in required_prompts:
            obj = getattr(pt, name, None)
            if obj is None or not isinstance(obj, dict):
                prompt_bad.append(name)
                continue
            if not obj.get("system_prompt") or not obj.get("user_prompt_template"):
                prompt_bad.append(name + "(key)")
        if prompt_bad:
            f048_ok = False
            f048_detail_parts.append("Prompt 异常: " + ",".join(prompt_bad))
        else:
            f048_detail_parts.append("6 Prompt就绪")
    except Exception as e:
        f048_ok = False
        f048_detail_parts.append("prompt_templates import 失败: " + str(e))

    # 两表 + 僵尸任务
    if db_exists:
        try:
            conn = sqlite3.connect(dp)
            cur = conn.cursor()
            cur.execute("SELECT name FROM sqlite_master WHERE type='table' AND name IN ('health_reports','polish_suggestions')")
            got = {r[0] for r in cur.fetchall()}
            miss = [t for t in ("health_reports", "polish_suggestions") if t not in got]
            if miss:
                f048_ok = False
                f048_detail_parts.append("表缺失: " + ",".join(miss))
            else:
                cur.execute("SELECT COUNT(*) FROM health_reports WHERE status='running' AND julianday('now')-julianday(created_at)>0.0833")
                zombie = cur.fetchone()[0]
                if zombie > 0:
                    f048_detail_parts.append("僵尸任务" + str(zombie) + "条")
                else:
                    f048_detail_parts.append("两表OK/无僵尸")
            conn.close()
        except Exception as e:
            f048_detail_parts.append("两表检查失败: " + str(e))
    results.append({"name": "F048 就绪度", "ok": f048_ok,
                    "detail": " | ".join(f048_detail_parts)})

    # v2.3.0-part3 新增 [19] F062 端到端测试就绪度
    f062_ok = True
    f062_detail_parts = []
    # [19.1] E2E_RESPONSE_JUDGE_PROMPT import + 双 key
    try:
        from scripts.prompts import prompt_templates as pt_e2e
        p = getattr(pt_e2e, "E2E_RESPONSE_JUDGE_PROMPT", None)
        if p is None or not isinstance(p, dict):
            f062_ok = False
            f062_detail_parts.append("E2E_RESPONSE_JUDGE_PROMPT 缺失或类型错")
        elif not p.get("system_prompt") or not p.get("user_prompt_template"):
            f062_ok = False
            f062_detail_parts.append("Prompt 双 key 不全")
        else:
            f062_detail_parts.append("Prompt OK")
    except Exception as e:
        f062_ok = False
        f062_detail_parts.append("Prompt import 失败: " + str(e))
    # [19.2] static_analyzer + e2e_tester import
    try:
        from scripts import static_analyzer as sa
        for m in ("scan_prompt_call_consistency", "scan_field_contract",
                  "scan_code_smells", "run_static_scan"):
            if not hasattr(sa, m):
                f062_ok = False
                f062_detail_parts.append("static_analyzer 缺 " + m)
                break
        else:
            f062_detail_parts.append("static_analyzer OK")
    except Exception as e:
        f062_ok = False
        f062_detail_parts.append("static_analyzer import 失败: " + str(e))
    try:
        from scripts import e2e_tester as et
        if not hasattr(et, "E2ETester") or not hasattr(et, "run_e2e_scan"):
            f062_ok = False
            f062_detail_parts.append("e2e_tester 缺类或便捷函数")
        else:
            f062_detail_parts.append("e2e_tester OK")
    except Exception as e:
        f062_ok = False
        f062_detail_parts.append("e2e_tester import 失败: " + str(e))
    # [19.3] 三表 + 9 db 方法
    if db_exists:
        try:
            conn = sqlite3.connect(dp)
            cur = conn.cursor()
            cur.execute("SELECT name FROM sqlite_master WHERE type='table' AND name IN ('api_endpoint_registry','e2e_test_reports','e2e_issues')")
            got = {r[0] for r in cur.fetchall()}
            miss = [t for t in ("api_endpoint_registry", "e2e_test_reports", "e2e_issues") if t not in got]
            if miss:
                f062_ok = False
                f062_detail_parts.append("F062 表缺失: " + ",".join(miss))
            else:
                f062_detail_parts.append("三表OK")
            conn.close()
        except Exception as e:
            f062_detail_parts.append("表检查异常: " + str(e))
    # 9 个 db 方法
    try:
        from scripts.db_manager import DatabaseManager
        required_methods = [
            "register_endpoint", "get_endpoint_registry", "update_endpoint_last_tested",
            "save_e2e_test_report", "get_latest_e2e_test_report",
            "get_e2e_test_report_detail", "get_e2e_test_report_list",
            "upsert_e2e_issue", "set_e2e_issue_status",
        ]
        miss_m = [m for m in required_methods if not hasattr(DatabaseManager, m)]
        if miss_m:
            f062_ok = False
            f062_detail_parts.append("db 方法缺: " + ",".join(miss_m[:3]))
        else:
            f062_detail_parts.append("9 db方法OK")
    except Exception as e:
        f062_ok = False
        f062_detail_parts.append("DB 类检查失败: " + str(e))
    results.append({"name": "F062 就绪度", "ok": f062_ok,
                    "detail": " | ".join(f062_detail_parts)})

    return {
        "version": "v2.5.2",
        "system_version": get_version(),
        "checked_at": datetime.now().strftime("%Y-%m-%d %H:%M:%S"),
        "results": results,
        "ok_count": sum(1 for r in results if r["ok"]),
        "total": len(results)
    }


# ================================================================
# 主流程
# ================================================================
def check_f062_readiness():
    """v2.3.0-part3 新增：F062 端到端测试就绪度 4 小项
       [19.1] E2E_RESPONSE_JUDGE_PROMPT 双 key
       [19.2] static_analyzer + e2e_tester 可 import
       [19.3] 三张 F062 表存在
       [19.4] 9 个 db F062 方法齐全
    """
    print(f"\n[19] F062 端到端测试就绪度(v2.3.0-part3)")
    ok_all = True
    # [19.1] Prompt
    try:
        from scripts.prompts import prompt_templates as pt_e2e
        p = getattr(pt_e2e, "E2E_RESPONSE_JUDGE_PROMPT", None)
        if p is None or not isinstance(p, dict):
            print(f"    FAIL [19.1] E2E_RESPONSE_JUDGE_PROMPT 未定义或类型错")
            ok_all = False
        elif not p.get("system_prompt") or not p.get("user_prompt_template"):
            print(f"    FAIL [19.1] E2E_RESPONSE_JUDGE_PROMPT 缺 system_prompt 或 user_prompt_template")
            ok_all = False
        else:
            print(f"    OK [19.1] E2E_RESPONSE_JUDGE_PROMPT 双 key 就绪")
    except Exception as e:
        print(f"    FAIL [19.1] Prompt import 异常: {e}")
        ok_all = False
    # [19.2] static_analyzer + e2e_tester
    try:
        from scripts import static_analyzer as sa
        miss = [m for m in ("scan_prompt_call_consistency", "scan_field_contract",
                            "scan_code_smells", "run_static_scan") if not hasattr(sa, m)]
        if miss:
            print(f"    FAIL [19.2a] static_analyzer 缺方法: {','.join(miss)}")
            ok_all = False
        else:
            print(f"    OK [19.2a] static_analyzer 4 方法齐全")
    except Exception as e:
        print(f"    FAIL [19.2a] static_analyzer import 异常: {e}")
        ok_all = False
    try:
        from scripts import e2e_tester as et
        if not hasattr(et, "E2ETester") or not hasattr(et, "run_e2e_scan"):
            print(f"    FAIL [19.2b] e2e_tester 缺 E2ETester 或 run_e2e_scan")
            ok_all = False
        else:
            print(f"    OK [19.2b] e2e_tester 类与便捷函数齐全")
    except Exception as e:
        print(f"    FAIL [19.2b] e2e_tester import 异常: {e}")
        ok_all = False
    # [19.3] 三张 F062 表
    config = _load_config()
    dp = _get_db_path(config) if config else None
    if dp and os.path.exists(dp):
        try:
            conn = sqlite3.connect(dp)
            cur = conn.cursor()
            cur.execute("SELECT name FROM sqlite_master WHERE type='table' AND name IN ('api_endpoint_registry','e2e_test_reports','e2e_issues')")
            got = {r[0] for r in cur.fetchall()}
            miss = [t for t in ("api_endpoint_registry", "e2e_test_reports", "e2e_issues") if t not in got]
            if miss:
                print(f"    FAIL [19.3] F062 表缺失: {','.join(miss)}")
                ok_all = False
            else:
                print(f"    OK [19.3] F062 三表齐全")
            conn.close()
        except Exception as e:
            print(f"    FAIL [19.3] 表检查异常: {e}")
            ok_all = False
    # [19.4] 9 个 db 方法
    try:
        from scripts.db_manager import DatabaseManager
        required = [
            "register_endpoint", "get_endpoint_registry", "update_endpoint_last_tested",
            "save_e2e_test_report", "get_latest_e2e_test_report",
            "get_e2e_test_report_detail", "get_e2e_test_report_list",
            "upsert_e2e_issue", "set_e2e_issue_status",
        ]
        miss = [m for m in required if not hasattr(DatabaseManager, m)]
        if miss:
            print(f"    FAIL [19.4] db 缺 F062 方法: {','.join(miss)}")
            ok_all = False
        else:
            print(f"    OK [19.4] 9 db F062 方法齐全")
    except Exception as e:
        print(f"    FAIL [19.4] DatabaseManager 类检查失败: {e}")
        ok_all = False
    return ok_all


def main():
    print("=" * 60)
    print(f"  系统状态检查 v2.5.2")
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
    results.append(("重复检测", check_duplicate_status()))
    results.append(("注解与速记", check_annotation_status()))
    results.append(("F048 就绪度", check_f048_readiness()))
    results.append(("F062 就绪度", check_f062_readiness()))

    # 第三部分：API连通性（可选）
    print(f"\n{'─' * 40}")
    ans = input("  是否测试API连通性? (会消耗少量费用) [y/N]: ").strip().lower()
    if ans == "y":
        print(f"\n[16] API连通性")
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
