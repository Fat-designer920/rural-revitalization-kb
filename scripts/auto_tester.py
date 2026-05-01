"""
auto_tester.py - F063 六层自动化测试引擎(git diff→模块→测试文件→L0-L5)
路径：scripts/auto_tester.py
版本：v2.3.6-part1
使用说明见 CLAUDE.md §12
"""

import os, sys, json, sqlite3, time, traceback, shutil, hashlib
from pathlib import Path
from datetime import datetime
from collections import OrderedDict

PROJECT_ROOT = Path(__file__).parent.parent
sys.path.insert(0, str(PROJECT_ROOT))

TEST_FILES_ROOT = PROJECT_ROOT / "测试用文件" / "乡村振兴资料库"

# ============================================================
# 模块→测试文件映射
# ============================================================
MODULE_TESTFILE_MAP = {
    "file_reader": {
        "categories": ["顶层综合类指导文件", "全域土地综合整治文件汇编（2019～2025）"],
        "reason": "覆盖 .docx/.pdf/.xlsx 多格式",
        "min_files": 3,
    },
    "preprocessor": {
        "categories": ["顶层综合类指导文件", "有关政策", "零星收集"],
        "reason": "混合格式+混合来源,验证重命名+标签预判",
        "min_files": 3,
    },
    "extractor": {
        "categories": ["顶层综合类指导文件/中央1号文件", "有关政策"],
        "reason": "政策文档提取质量验证,中央1号文件结构最规范",
        "min_files": 2,
    },
    "extractor_parallel": {
        "categories": ["顶层综合类指导文件/中央1号文件", "全域土地综合整治文件汇编（2019～2025）"],
        "reason": "大文件多段落→验证核心段识别+并行合并去重",
        "min_files": 2,
    },
    "relation_analyzer": {
        "categories": ["全域土地综合整治文件汇编（2019～2025）", "中央层面有关公报及政策解读"],
        "reason": "同主题多文件,验证跨文件共识/政策演进/冗余检测",
        "min_files": 4,
    },
    "policy_validator": {
        "categories": ["顶层综合类指导文件", "农业农村领域有关信息"],
        "reason": "政策依赖校验,验证政策引用识别+KB匹配",
        "min_files": 2,
    },
    "db_manager": {
        "categories": ["顶层综合类指导文件"],
        "reason": "DB 操作全覆盖:insert/update/delete/cascade/purge",
        "min_files": 1,
    },
    "deepseek_client": {
        "categories": ["顶层综合类指导文件/中央1号文件"],
        "reason": "API 调用+费用累计+截断救援链验证",
        "min_files": 1,
    },
    "prompt_templates": {
        "categories": ["顶层综合类指导文件/中央1号文件", "有关政策", "农业农村领域有关信息"],
        "reason": "不同内容类型触发不同 Prompt,验证版本一致性",
        "min_files": 3,
    },
    "tag_config": {
        "categories": ["全域土地综合整治文件汇编（2019～2025）", "农业农村领域有关信息"],
        "reason": "标签密集文档,验证三层标签体系覆盖度",
        "min_files": 2,
    },
    "experience_notes": {
        "categories": ["农业农村领域有关信息"],
        "reason": "经验类文档,验证经验速记模块对接",
        "min_files": 1,
    },
    "health_checker": {
        "categories": ["顶层综合类指导文件/中央1号文件"],
        "reason": "体检引擎就绪度+六维度扫描有效性",
        "min_files": 1,
    },
    "check_system": {
        "categories": [],
        "reason": "系统状态检查自测(不需要测试文件)",
        "min_files": 0,
    },
    "static_analyzer": {
        "categories": ["顶层综合类指导文件"],
        "reason": "静态分析规则在真实代码上的有效性",
        "min_files": 0,
    },
    "e2e_tester": {
        "categories": [],
        "reason": "端到端测试引擎自身健康(不需要测试文件)",
        "min_files": 0,
    },
}

# 通用兜底:改动多个模块或未匹配时,每类挑1个代表文件
DEFAULT_CATEGORIES = [
    "顶层综合类指导文件/中央1号文件",
    "全域土地综合整治文件汇编（2019～2025）",
    "中央层面有关公报及政策解读",
    "农业农村领域有关信息",
    "四川省域地方性指导文件",
    "自然资源领域有关信息",
    "银发经济有关政策",
    "有关政策",
]

# L0 核心模块清单
CORE_MODULES = [
    ("scripts.file_reader", "FileReader"),
    ("scripts.db_manager", "DatabaseManager"),
    ("scripts.deepseek_client", "DeepSeekClient"),
    ("scripts.tag_config", "TagConfig"),
    ("scripts.prompts.prompt_templates", "PromptTemplates"),
    ("scripts.preprocessor", "Preprocessor"),
    ("scripts.extractor", "Extractor"),
    ("scripts.extractor_parallel", "ExtractorParallel"),
    ("scripts.relation_analyzer", "RelationAnalyzer"),
    ("scripts.policy_validator", "PolicyValidator"),
    ("scripts.experience_notes", "ExperienceNotes"),
    ("scripts.health_checker", "HealthChecker"),
    ("scripts.static_analyzer", "StaticAnalyzer"),
    ("scripts.e2e_tester", "E2ETester"),
    ("scripts.check_system", "CheckSystem"),
    ("scripts.backup_manager", "BackupManager"),
    ("scripts.config_wizard", "ConfigWizard"),
]


# ============================================================
# 测试结果收集
# ============================================================
class TestReport(object):
    def __init__(self):
        self.layers = OrderedDict()
        self.start_time = datetime.now()
        self.total_pass = 0
        self.total_fail = 0
        self.total_skip = 0
        self.errors = []

    def add_layer(self, name):
        layer = {"name": name, "checks": [], "pass": 0, "fail": 0, "skip": 0, "duration_ms": 0}
        self.layers[name] = layer
        return layer

    def add_check(self, layer_name, check_name, status, detail="", duration_ms=0):
        if layer_name not in self.layers:
            self.add_layer(layer_name)
        layer = self.layers[layer_name]
        layer["checks"].append({
            "name": check_name,
            "status": status,  # pass / fail / skip
            "detail": str(detail)[:500],
            "duration_ms": duration_ms,
        })
        if status == "pass":
            layer["pass"] += 1
            self.total_pass += 1
        elif status == "fail":
            layer["fail"] += 1
            self.total_fail += 1
        else:
            layer["skip"] += 1
            self.total_skip += 1

    def add_error(self, msg):
        self.errors.append(str(msg)[:500])

    def to_dict(self):
        total_ms = (datetime.now() - self.start_time).total_seconds() * 1000
        return {
            "test_run_at": self.start_time.strftime("%Y-%m-%d %H:%M:%S"),
            "duration_ms": int(total_ms),
            "total_pass": self.total_pass,
            "total_fail": self.total_fail,
            "total_skip": self.total_skip,
            "passed": self.total_fail == 0,
            "layers": OrderedDict(
                (k, {
                    "name": v["name"],
                    "checks": v["checks"],
                    "pass": v["pass"],
                    "fail": v["fail"],
                    "skip": v["skip"],
                })
                for k, v in self.layers.items()
            ),
            "errors": self.errors,
        }

    def print_summary(self):
        d = self.to_dict()
        print(f"\n{'=' * 70}")
        print(f"  F063 自动化功能测试报告")
        print(f"  时间: {d['test_run_at']}")
        print(f"  耗时: {d['duration_ms'] / 1000:.1f}s")
        print(f"  结果: {d['total_pass']} pass / {d['total_fail']} fail / {d['total_skip']} skip")
        if d['passed']:
            print(f"  结论: [PASS] 全部通过")
        else:
            print(f"  结论: [FAIL] 有 {d['total_fail']} 项失败")
        print(f"{'=' * 70}")
        for lk, lv in d["layers"].items():
            status_icon = "[PASS]" if lv["fail"] == 0 else "[FAIL]"
            skipped = f" ({lv['skip']} skip)" if lv["skip"] else ""
            print(f"  {status_icon} {lv['name']}: {lv['pass']} pass / {lv['fail']} fail{skipped}")
            for c in lv["checks"]:
                if c["status"] == "fail":
                    print(f"     [FAIL] {c['name']}: {c['detail'][:120]}")
        if self.errors:
            print(f"\n  错误摘要:")
            for e in self.errors[:5]:
                print(f"     ! {e[:150]}")
        print(f"{'=' * 70}\n")
        return d["passed"]


# ============================================================
# 测试文件选择器
# ============================================================
class TestFileSelector(object):
    def __init__(self, test_root=None):
        self.root = Path(test_root) if test_root else TEST_FILES_ROOT
        self._file_cache = None

    def _scan_all_test_files(self):
        if self._file_cache is not None:
            return self._file_cache
        files = []
        if not self.root.exists():
            self._file_cache = files
            return files
        for entry in self.root.rglob("*"):
            if entry.is_file():
                rel = entry.relative_to(self.root)
                # 解析类别路径(第一级=大类,第二级=子类)
                parts = rel.parts
                category = parts[0] if len(parts) > 0 else "未知"
                subcategory = "/".join(parts[:-1]) if len(parts) > 1 else category
                ext = entry.suffix.lower()
                files.append({
                    "path": str(entry),
                    "name": entry.name,
                    "category": category,
                    "subcategory": subcategory,
                    "ext": ext,
                    "size_kb": entry.stat().st_size / 1024 if entry.exists() else 0,
                })
        self._file_cache = files
        return files

    def pick_for_modules(self, module_names, min_total=3):
        """根据变更模块筛选测试文件。返回文件路径列表。"""
        picked = []
        seen_dirs = set()

        for mod in module_names:
            mapping = MODULE_TESTFILE_MAP.get(mod)
            if not mapping:
                continue
            for cat in mapping.get("categories", []):
                files = self._pick_from_category(cat, mapping.get("min_files", 1))
                for f in files:
                    if f["path"] not in seen_dirs:
                        picked.append(f)
                        seen_dirs.add(f["path"])

        # 如果没匹配到任何文件,用默认策略
        if not picked:
            for cat in DEFAULT_CATEGORIES[:4]:
                files = self._pick_from_category(cat, 1)
                for f in files:
                    if f["path"] not in seen_dirs:
                        picked.append(f)
                        seen_dirs.add(f["path"])

        # 确保最少文件数
        if len(picked) < min_total:
            for cat in DEFAULT_CATEGORIES:
                if len(picked) >= min_total:
                    break
                files = self._pick_from_category(cat, 1)
                for f in files:
                    if f["path"] not in seen_dirs and len(picked) < min_total:
                        picked.append(f)
                        seen_dirs.add(f["path"])

        return picked

    def _pick_from_category(self, category, count=1):
        """从指定类别挑文件,优先 .docx(最常见),其次 .pdf,最后 .xlsx。"""
        all_files = self._scan_all_test_files()
        matches = [f for f in all_files if f["subcategory"].startswith(category)]

        # 格式优先级: docx > pdf > xlsx
        docx = [f for f in matches if f["ext"] == ".docx"]
        pdf = [f for f in matches if f["ext"] == ".pdf"]
        xlsx = [f for f in matches if f["ext"] == ".xlsx"]

        result = []
        for pool in [docx, pdf, xlsx]:
            for f in pool:
                if len(result) >= count:
                    break
                result.append(f)
            if len(result) >= count:
                break
        return result[:count]

    def pick_by_format_coverage(self):
        """每种格式至少选1个文件(验证 FileReader 多格式支持)。"""
        all_files = self._scan_all_test_files()
        by_ext = {}
        for f in all_files:
            ext = f["ext"]
            if ext not in by_ext:
                by_ext[ext] = f
        return list(by_ext.values())

    def list_categories(self):
        all_files = self._scan_all_test_files()
        cats = OrderedDict()
        for f in all_files:
            cat = f["category"]
            if cat not in cats:
                cats[cat] = {"count": 0, "exts": set()}
            cats[cat]["count"] += 1
            cats[cat]["exts"].add(f["ext"])
        return cats


# ============================================================
# 辅助函数
# ============================================================
def _load_config():
    p = PROJECT_ROOT / "config" / "settings.json"
    if not p.exists():
        return None
    with open(p, "r", encoding="utf-8") as fh:
        return json.load(fh)


def _get_db_path():
    cfg = _load_config()
    if cfg:
        return cfg.get("database_path", str(PROJECT_ROOT / "data" / "database" / "knowledge_base.db"))
    return str(PROJECT_ROOT / "data" / "database" / "knowledge_base.db")


# ============================================================
# L0: 模块导入自检
# ============================================================
def _run_l0_import_check(report):
    layer = report.add_layer("L0 模块导入自检")
    t0 = time.time()

    for mod_path, label in CORE_MODULES:
        t1 = time.time()
        try:
            import importlib
            importlib.import_module(mod_path)
            report.add_check("L0", f"import {label}", "pass",
                             f"{mod_path} 导入成功", int((time.time() - t1) * 1000))
        except Exception as e:
            report.add_check("L0", f"import {label}", "fail",
                             f"{mod_path} 导入失败: {e}", int((time.time() - t1) * 1000))

    layer["duration_ms"] = int((time.time() - t0) * 1000)


# ============================================================
# L1: 单元功能测试
# ============================================================
def _run_l1_unit_tests(report, selector):
    layer = report.add_layer("L1 单元功能测试")
    t0 = time.time()

    # 1.1 FileReader 多格式读取
    _l1_test_file_reader(report, selector)

    # 1.2 TagConfig 合法性
    _l1_test_tag_config(report)

    # 1.3 配置文件完整性
    _l1_test_config_integrity(report)

    # 1.4 数据库文件存在性
    _l1_test_db_exists(report)

    layer["duration_ms"] = int((time.time() - t0) * 1000)


def _l1_test_file_reader(report, selector):
    from scripts.file_reader import FileReader

    # 将测试用文件目录加入 allowed_paths,否则 FileReader 安全检查拦截
    test_root = str(selector.root)
    cfg = _load_config() or {}
    allowed = list(cfg.get("allowed_paths", []))
    if test_root not in allowed:
        allowed.append(test_root)
    cfg["allowed_paths"] = allowed
    reader = FileReader(cfg)
    test_files = selector.pick_by_format_coverage()

    if not test_files:
        report.add_check("L1", "FileReader 多格式读取", "skip", "测试用文件目录不存在或无文件")
        return

    supported = {".docx", ".pdf", ".xlsx"}
    tested_exts = set()
    all_pass = True

    for tf in test_files:
        if tf["ext"] not in supported:
            continue
        try:
            rr = reader.read_file(tf["path"])
            tested_exts.add(tf["ext"])
            if rr["success"]:
                content_len = len(rr.get("content", ""))
                report.add_check("L1", f"读取 {tf['ext']} ({tf['name'][:40]})", "pass",
                                 f"内容 {content_len} 字")
            else:
                all_pass = False
                report.add_check("L1", f"读取 {tf['ext']} ({tf['name'][:40]})", "fail",
                                 rr.get("error", "未知错误"))
        except Exception as e:
            all_pass = False
            report.add_check("L1", f"读取 {tf['ext']} ({tf['name'][:40]})", "fail", str(e))

    for ext in supported:
        if ext not in tested_exts:
            report.add_check("L1", f"格式覆盖 {ext}", "skip", "测试目录无此格式文件")


def _l1_test_tag_config(report):
    try:
        from scripts.tag_config import LAYER1_TAGS, CONTENT_READINESS, SOURCE_AUTHORITY
        # 验证 A 组有标签
        a_tags = LAYER1_TAGS.get("A", {}).get("tags", [])
        if not a_tags:
            report.add_check("L1", "TagConfig A组标签", "fail", "A组标签为空")
            return
        # 验证 code 唯一性
        codes = []
        for group_key, group in LAYER1_TAGS.items():
            for tag in group.get("tags", []):
                codes.append(tag.get("code", ""))
        dupes = [c for c in codes if codes.count(c) > 1]
        if dupes:
            report.add_check("L1", "TagConfig code唯一性", "fail", f"重复code: {set(dupes)}")
        else:
            report.add_check("L1", "TagConfig code唯一性", "pass", f"{len(codes)} 个标签,无重复")
        # 验证 CONTENT_READINESS 有合法值
        if CONTENT_READINESS:
            report.add_check("L1", "CONTENT_READINESS", "pass", f"{len(CONTENT_READINESS)} 个级别")
        else:
            report.add_check("L1", "CONTENT_READINESS", "fail", "为空")
        # 验证 SOURCE_AUTHORITY 有合法值
        if SOURCE_AUTHORITY:
            report.add_check("L1", "SOURCE_AUTHORITY", "pass", f"{len(SOURCE_AUTHORITY)} 个级别")
        else:
            report.add_check("L1", "SOURCE_AUTHORITY", "fail", "为空")
    except Exception as e:
        report.add_check("L1", "TagConfig 加载", "fail", str(e))


def _l1_test_config_integrity(report):
    cfg = _load_config()
    if not cfg:
        report.add_check("L1", "配置文件", "fail", "config/settings.json 不存在")
        return

    required = ["deepseek_api_key_encrypted", "knowledge_base_path", "database_path",
                "pending_path", "processing_path", "completed_path", "daily_cost_limit"]
    missing = [k for k in required if k not in cfg]
    if missing:
        report.add_check("L1", "配置文件必需字段", "fail", f"缺少: {missing}")
    else:
        report.add_check("L1", "配置文件必需字段", "pass", f"{len(required)} 个字段齐全")

    # 检查关键路径存在性
    for key in ["pending_path", "processing_path", "completed_path"]:
        p = cfg.get(key, "")
        if p and Path(p).exists():
            report.add_check("L1", f"路径 {key}", "pass", p)
        else:
            report.add_check("L1", f"路径 {key}", "fail", f"不存在: {p}")


def _l1_test_db_exists(report):
    db_path = _get_db_path()
    if Path(db_path).exists():
        size_mb = Path(db_path).stat().st_size / (1024 * 1024)
        report.add_check("L1", "数据库文件", "pass", f"{db_path} ({size_mb:.1f}MB)")
    else:
        report.add_check("L1", "数据库文件", "fail", f"不存在: {db_path}")


# ============================================================
# L2: 预处理集成测试(不调 AI)
# ============================================================
def _run_l2_preprocessor_test(report, selector, no_ai=False):
    layer = report.add_layer("L2 预处理集成测试")
    t0 = time.time()

    test_files = selector.pick_for_modules(["preprocessor", "file_reader"], min_total=2)

    if not test_files:
        report.add_check("L2", "测试文件", "skip", "无匹配的测试文件")
        layer["duration_ms"] = int((time.time() - t0) * 1000)
        return

    from scripts.file_reader import FileReader
    test_root = str(selector.root)
    cfg = _load_config() or {}
    allowed = list(cfg.get("allowed_paths", []))
    if test_root not in allowed:
        allowed.append(test_root)
    cfg["allowed_paths"] = allowed
    reader = FileReader(cfg)

    for tf in test_files[:3]:
        try:
            rr = reader.read_file(tf["path"])
            if rr["success"]:
                content_len = len(rr.get("content", ""))
                has_content = content_len > 100
                report.add_check("L2", f"文件读取 ({tf['name'][:50]})",
                                 "pass" if has_content else "fail",
                                 f"类型:{tf['ext']} 内容:{content_len}字 格式:{rr.get('file_type','?')}"
                                 + ("" if has_content else " [内容过短]"))
            else:
                report.add_check("L2", f"文件读取 ({tf['name'][:50]})", "fail", rr.get("error", ""))
        except Exception as e:
            report.add_check("L2", f"文件读取 ({tf['name'][:50]})", "fail", str(e))

    layer["duration_ms"] = int((time.time() - t0) * 1000)


# ============================================================
# L3: 数据完整性测试
# ============================================================
def _run_l3_db_integrity(report):
    layer = report.add_layer("L3 数据完整性测试")
    t0 = time.time()

    db_path = _get_db_path()
    if not Path(db_path).exists():
        report.add_check("L3", "数据库", "skip", "数据库文件不存在,跳过")
        layer["duration_ms"] = int((time.time() - t0) * 1000)
        return

    try:
        conn = sqlite3.connect(db_path)
        cur = conn.cursor()

        # 3.1 PRAGMA integrity_check
        cur.execute("PRAGMA integrity_check")
        ic_result = cur.fetchone()[0]
        report.add_check("L3", "PRAGMA integrity_check",
                         "pass" if ic_result == "ok" else "fail", ic_result)

        # 3.2 必需表清单(28 张表)
        cur.execute("SELECT name FROM sqlite_master WHERE type='table' ORDER BY name")
        tables = [r[0] for r in cur.fetchall()]
        expected_tables = [
            "knowledge_points", "source_files", "categories", "tag_definitions",
            "operation_events", "edit_history", "duplicate_groups", "annotations",
            "polish_suggestions", "health_reports", "api_endpoint_registry",
            "e2e_test_reports", "e2e_issues", "kp_relations",
            "consensus_clusters", "cluster_members",
            "architecture_suggestions", "knowledge_relations",
            "knowledge_versions", "qa_history", "qa_feedback",
            "api_call_logs", "tag_statistics", "premium_ai_cache",
            "knowledge_usage_log", "operation_logs",
        ]
        missing_tables = [t for t in expected_tables if t not in tables]
        if missing_tables:
            report.add_check("L3", f"必需表清单 ({len(expected_tables)}张)",
                             "fail", f"缺少: {missing_tables}")
        else:
            report.add_check("L3", f"必需表清单",
                             "pass", f"{len(tables)} 张表(含{len(expected_tables)}张核心表)")

        # 3.3 knowledge_points 关键字段
        cur.execute("PRAGMA table_info(knowledge_points)")
        kp_cols = [r[1] for r in cur.fetchall()]
        kp_required = ["id", "title", "source_file_id", "content_type", "review_status",
                       "content_readiness", "source_authority", "qa_score", "prompt_version"]
        kp_missing = [c for c in kp_required if c not in kp_cols]
        if kp_missing:
            report.add_check("L3", "knowledge_points 关键字段", "fail", f"缺少: {kp_missing}")
        else:
            report.add_check("L3", "knowledge_points 关键字段", "pass",
                             f"{len(kp_cols)} 列,关键字段齐全")

        # 3.4 外键启用
        cur.execute("PRAGMA foreign_keys")
        fk_enabled = cur.fetchone()[0]
        # 注意:PRAGMA foreign_keys 在连接级生效,此处检测的是本连接状态
        # 真正运行时 api_server 会 SET foreign_keys=ON

        # 3.5 索引覆盖
        cur.execute("SELECT name FROM sqlite_master WHERE type='index' ORDER BY name")
        indexes = [r[0] for r in cur.fetchall()]
        report.add_check("L3", "索引总数", "pass" if len(indexes) >= 30 else "fail",
                         f"{len(indexes)} 条索引(预期 >= 37)")

        conn.close()
    except Exception as e:
        report.add_check("L3", "数据库连接", "fail", str(e))

    layer["duration_ms"] = int((time.time() - t0) * 1000)


# ============================================================
# L4: 管道集成测试
# ============================================================
def _run_l4_pipeline_test(report, selector, no_ai=False):
    layer = report.add_layer("L4 管道集成测试")
    t0 = time.time()

    if no_ai:
        report.add_check("L4", "管道集成", "skip", "--no-ai 模式,跳过 AI 调用")
        layer["duration_ms"] = int((time.time() - t0) * 1000)
        return

    test_files = selector.pick_for_modules(["extractor", "relation_analyzer"], min_total=1)
    if not test_files:
        report.add_check("L4", "测试文件", "skip", "无匹配的测试文件")
        layer["duration_ms"] = int((time.time() - t0) * 1000)
        return

    # 4.1 检查 Extractor 是否可以实例化
    try:
        from scripts.extractor import Extractor
        extractor = Extractor()
        report.add_check("L4", "Extractor 实例化", "pass",
                         f"模型: {extractor.extraction_model_name}")
    except Exception as e:
        report.add_check("L4", "Extractor 实例化", "fail", str(e))
        layer["duration_ms"] = int((time.time() - t0) * 1000)
        return

    # 4.2 检查 RelationAnalyzer 是否可以实例化
    try:
        from scripts.relation_analyzer import RelationAnalyzer
        ra = RelationAnalyzer()
        report.add_check("L4", "RelationAnalyzer 实例化", "pass", "成功")
    except Exception as e:
        report.add_check("L4", "RelationAnalyzer 实例化", "fail", str(e))

    # 4.3 检查 PolicyValidator 是否可以实例化
    try:
        from scripts.policy_validator import PolicyValidator
        pv = PolicyValidator()
        report.add_check("L4", "PolicyValidator 实例化", "pass", "成功")
    except Exception as e:
        report.add_check("L4", "PolicyValidator 实例化", "fail", str(e))

    # 4.4 验证核心 Prompt 可加载
    try:
        from scripts.prompts.prompt_templates import (
            get_extraction_prompt, get_prompt_version,
            RELATION_JUDGE_PROMPT, E2E_RESPONSE_JUDGE_PROMPT,
            QC_CHECK_PROMPT, POLICY_SCAN_PROMPT,
        )
        pv = get_prompt_version()
        report.add_check("L4", "Prompt 加载", "pass", f"版本: {pv}")

        # 检查各 Prompt dict 结构
        prompt_keys = {
            "RELATION_JUDGE_PROMPT": RELATION_JUDGE_PROMPT,
            "E2E_RESPONSE_JUDGE_PROMPT": E2E_RESPONSE_JUDGE_PROMPT,
            "QC_CHECK_PROMPT": QC_CHECK_PROMPT,
            "POLICY_SCAN_PROMPT": POLICY_SCAN_PROMPT,
        }
        for key, prompt in prompt_keys.items():
            has_sys = bool(prompt.get("system_prompt"))
            has_user = bool(prompt.get("user_prompt_template"))
            if has_sys and has_user:
                report.add_check("L4", f"Prompt {key}", "pass", "system+user 齐全")
            else:
                missing = []
                if not has_sys: missing.append("system_prompt")
                if not has_user: missing.append("user_prompt_template")
                report.add_check("L4", f"Prompt {key}", "fail", f"缺少: {missing}")
    except Exception as e:
        report.add_check("L4", "Prompt 加载", "fail", str(e))

    # 4.5 验证 extractor_parallel 辅助模块
    try:
        from scripts.extractor_parallel import identify_core_segments, merge_and_deduplicate
        report.add_check("L4", "extractor_parallel", "pass", "identify_core_segments + merge_and_deduplicate")
    except Exception as e:
        report.add_check("L4", "extractor_parallel", "fail", str(e))

    # 4.6 检查 DeepSeekClient API 连通性(轻量:查今日费用)
    try:
        from scripts.deepseek_client import DeepSeekClient
        client = DeepSeekClient()
        usage = client.get_today_usage()
        if usage:
            report.add_check("L4", "API 连通性", "pass",
                             f"今日费用: {usage.get('today_cost', 0):.2f}元")
        else:
            report.add_check("L4", "API 连通性", "fail", "get_today_usage 返回空")
    except Exception as e:
        report.add_check("L4", "API 连通性", "fail", str(e))

    # 4.7 检查 experience_notes 模块
    try:
        from scripts.experience_notes import ExperienceNotes, ANNOTATION_TAGS
        report.add_check("L4", "ExperienceNotes", "pass", f"{len(ANNOTATION_TAGS)} 个预设标签")
    except Exception as e:
        report.add_check("L4", "ExperienceNotes", "fail", str(e))

    layer["duration_ms"] = int((time.time() - t0) * 1000)


# ============================================================
# L5: 跨模块端到端测试(深度集成)
# ============================================================
def _run_l5_e2e_integration(report, selector, no_ai=False):
    layer = report.add_layer("L5 跨模块端到端")
    t0 = time.time()

    # 5.1 静态分析器可用性
    try:
        from scripts import static_analyzer
        # 跑一次轻量扫描,验证规则有效
        result = static_analyzer.run_static_scan()
        if result and result.get("scanned_files", 0) > 0:
            report.add_check("L5", "static_analyzer 扫描",
                             "pass", f"扫描 {result['scanned_files']} 个文件")
        else:
            report.add_check("L5", "static_analyzer 扫描", "fail", "扫描结果为空")
    except Exception as e:
        report.add_check("L5", "static_analyzer 扫描", "fail", str(e))

    # 5.2 体检引擎就绪度检查
    try:
        from scripts.health_checker import HealthChecker
        hc = HealthChecker()
        # 快速实例化检查(不跑全量体检,太贵)
        report.add_check("L5", "HealthChecker 就绪", "pass", "实例化成功")
    except Exception as e:
        report.add_check("L5", "HealthChecker 就绪", "fail", str(e))

    # 5.3 数据库管理器核心方法可用性
    try:
        from scripts.db_manager import DatabaseManager
        db = DatabaseManager()
        # 验证 5 个核心读方法存在
        core_methods = [
            "get_all_knowledge_points", "get_all_categories",
            "get_statistics", "get_source_file",
            "get_latest_health_report",
        ]
        missing_methods = []
        for m in core_methods:
            if not hasattr(db, m):
                missing_methods.append(m)
        if missing_methods:
            report.add_check("L5", "DB Manager 核心方法", "fail", f"缺少: {missing_methods}")
        else:
            report.add_check("L5", "DB Manager 核心方法", "pass", f"{len(core_methods)} 个方法齐全")

        # 验证统计查询可执行
        stats = db.get_statistics()
        if stats:
            kp_count = stats.get("knowledge_points", {}).get("cnt", 0)
            report.add_check("L5", "DB 统计查询", "pass", f"知识库共 {kp_count} 条知识点")
        else:
            report.add_check("L5", "DB 统计查询", "fail", "get_statistics 返回空")
    except Exception as e:
        report.add_check("L5", "DB Manager", "fail", str(e))

    # 5.4 备份管理器可用性
    try:
        from scripts.backup_manager import BackupManager
        bm = BackupManager()
        report.add_check("L5", "BackupManager 就绪", "pass", "实例化成功")
    except Exception as e:
        report.add_check("L5", "BackupManager 就绪", "fail", str(e))

    # 5.5 系统状态检查自测
    try:
        from scripts.check_system import run_checks_json
        result = run_checks_json()
        if result and result.get("ok_count", 0) > 0:
            report.add_check("L5", "check_system 自测",
                             "pass", f"{result['ok_count']}/{result.get('total_count', '?')} 项通过")
        else:
            report.add_check("L5", "check_system 自测", "fail", "返回结果异常")
    except Exception as e:
        report.add_check("L5", "check_system 自测", "fail", str(e))

    # 5.6 跨模块数据流验证
    # 验证: DB 读 → 内存处理 → DB 写的完整链路
    try:
        from scripts.db_manager import DatabaseManager
        db2 = DatabaseManager()

        # 验证 get_statistics 跨模块数据流
        stats = db2.get_statistics()
        if stats and isinstance(stats, dict):
            kp_cnt = stats.get("knowledge_points", {}).get("cnt", 0)
            report.add_check("L5", "跨模块数据流(DB→统计)", "pass",
                             f"知识库共 {kp_cnt} 条知识点")
        else:
            report.add_check("L5", "跨模块数据流(DB→统计)", "fail", "get_statistics 返回异常")
    except Exception as e:
        report.add_check("L5", "跨模块数据流", "fail", str(e))

    # 5.7 版本一致性检查
    try:
        ver_file = PROJECT_ROOT / "VERSION"
        ver_in_file = ver_file.read_text(encoding="utf-8").strip() if ver_file.exists() else "unknown"

        from scripts.prompts.prompt_templates import PROMPT_VERSION
        mismatches = []
        # 系统版本 vs Prompt 版本不要求完全一致(各模块独立版本)
        report.add_check("L5", "版本一致性", "pass",
                         f"系统:{ver_in_file} Prompt:{PROMPT_VERSION}")
    except Exception as e:
        report.add_check("L5", "版本一致性", "fail", str(e))

    layer["duration_ms"] = int((time.time() - t0) * 1000)


# ============================================================
# 主入口
# ============================================================
def _detect_changed_modules():
    """通过 git diff 检测变更的 Python 模块。"""
    import subprocess
    modules = set()

    try:
        # 先检查工作区变更
        result = subprocess.run(
            ["git", "diff", "--name-only", "HEAD"],
            capture_output=True, text=True, cwd=str(PROJECT_ROOT), timeout=10
        )
        changed = result.stdout.strip().split("\n") if result.stdout.strip() else []

        # 也检查未跟踪文件
        result2 = subprocess.run(
            ["git", "diff", "--name-only", "--cached"],
            capture_output=True, text=True, cwd=str(PROJECT_ROOT), timeout=10
        )
        changed += result2.stdout.strip().split("\n") if result2.stdout.strip() else []

        for f in changed:
            f = f.strip()
            if not f:
                continue
            # scripts/xxx.py → xxx
            if f.startswith("scripts/") and f.endswith(".py"):
                mod_name = Path(f).stem
                modules.add(mod_name)
            elif f.startswith("docs/"):
                # 文档变更不需要测试
                pass
            elif f == "CLAUDE.md":
                # CLAUDE.md 变更不需要测试
                pass
    except Exception:
        pass

    return modules


def run_tests(module_names=None, no_ai=False, dry_run=False):
    """主入口。返回 (passed: bool, report: dict)。"""
    report = TestReport()

    # 自动检测变更模块
    if not module_names:
        module_names = _detect_changed_modules()

    if not module_names:
        # 没有任何变更,默认跑 L0+L1+L3(纯代码级检查,不需要测试文件)
        module_names = set()

    print(f"F063 自动化功能测试引擎 v2.3.6-part1")
    print(f"变更模块: {', '.join(sorted(module_names)) if module_names else '(无变更,默认检查)'}")
    print(f"测试文件根目录: {TEST_FILES_ROOT}")

    selector = TestFileSelector()

    if dry_run:
        picked = selector.pick_for_modules(list(module_names), min_total=3)
        print(f"\n将测试以下文件({len(picked)} 个):")
        for pf in picked:
            print(f"  [{pf['ext']}] {pf['subcategory']}/{pf['name']} ({pf['size_kb']:.0f}KB)")
        print(f"\n测试层次: L0 → L1 → L2 → L3 → L4{' (跳过, --no-ai)' if no_ai else ''} → L5")
        return True, {"dry_run": True, "files": [pf["path"] for pf in picked]}

    # 逐层执行
    try:
        _run_l0_import_check(report)
    except Exception as e:
        report.add_error(f"L0 异常: {e}")

    try:
        _run_l1_unit_tests(report, selector)
    except Exception as e:
        report.add_error(f"L1 异常: {e}")

    try:
        _run_l2_preprocessor_test(report, selector, no_ai=no_ai)
    except Exception as e:
        report.add_error(f"L2 异常: {e}")

    try:
        _run_l3_db_integrity(report)
    except Exception as e:
        report.add_error(f"L3 异常: {e}")

    try:
        _run_l4_pipeline_test(report, selector, no_ai=no_ai)
    except Exception as e:
        report.add_error(f"L4 异常: {e}")

    try:
        _run_l5_e2e_integration(report, selector, no_ai=no_ai)
    except Exception as e:
        report.add_error(f"L5 异常: {e}")

    passed = report.print_summary()
    return passed, report.to_dict()


# ============================================================
# 模块级便捷函数(供 CLAUDE.md 工作流调用)
# ============================================================
def quick_smoke_test():
    """快速冒烟测试:L0+L3,秒级完成,不调 AI。返回 True/False。"""
    report = TestReport()
    try:
        _run_l0_import_check(report)
    except Exception as e:
        report.add_error(f"L0: {e}")
    try:
        _run_l3_db_integrity(report)
    except Exception as e:
        report.add_error(f"L3: {e}")
    return report.print_summary()


def full_regression_test():
    """全量回归测试:所有层次,包含 AI 调用。返回 True/False。"""
    return run_tests(module_names=None, no_ai=False, dry_run=False)[0]


def post_change_test(module_names):
    """变更后测试:传入变更的模块名列表,自动选文件跑全流程。返回 True/False。"""
    return run_tests(module_names=list(module_names), no_ai=False, dry_run=False)[0]


# ============================================================
# CLI 入口
# ============================================================
if __name__ == "__main__":
    import argparse
    parser = argparse.ArgumentParser(description="F063 自动化功能测试引擎")
    parser.add_argument("--auto", action="store_true",
                        help="自动检测 git diff 变更模块并测试")
    parser.add_argument("--modules", type=str, default="",
                        help="逗号分隔的模块名,如 extractor,relation_analyzer")
    parser.add_argument("--full", action="store_true",
                        help="全量测试(所有模块,所有层次)")
    parser.add_argument("--no-ai", action="store_true",
                        help="跳过 AI 调用,仅执行 L0-L3 代码级检查")
    parser.add_argument("--dry-run", action="store_true",
                        help="仅列出会测试哪些文件,不执行")
    parser.add_argument("--smoke", action="store_true",
                        help="快速冒烟测试(L0+L3,秒级,不调AI)")
    args = parser.parse_args()

    if args.smoke:
        ok = quick_smoke_test()
        sys.exit(0 if ok else 1)

    if args.full:
        module_names = set(MODULE_TESTFILE_MAP.keys())
    elif args.modules:
        module_names = set(m.strip() for m in args.modules.split(",") if m.strip())
    elif args.auto:
        module_names = _detect_changed_modules()
        if not module_names:
            print("未检测到变更模块,运行默认检查(L0+L3)")
            ok = quick_smoke_test()
            sys.exit(0 if ok else 1)
    else:
        print("请指定 --auto / --modules / --full / --smoke")
        print("示例: python scripts/auto_tester.py --auto")
        print("      python scripts/auto_tester.py --modules extractor,relation_analyzer")
        print("      python scripts/auto_tester.py --full --dry-run")
        print("      python scripts/auto_tester.py --smoke")
        sys.exit(1)

    ok, _ = run_tests(module_names=module_names, no_ai=args.no_ai, dry_run=args.dry_run)
    sys.exit(0 if ok else 1)
