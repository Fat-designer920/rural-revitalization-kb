"""
static_analyzer.py - F062 端到端测试 Agent 静态分析模块
路径：scripts/static_analyzer.py
版本：v2.3.6-part1 - 版本统一

变更历史:
  v2.3.0-part3-alpha1  初版(宁严勿漏姿态),signal-to-noise 偏低
  v2.3.0-part3.7       规则精度重构,四项改动(part3.7):
    - 规则 ① smell_silent_except:signature + snippet 行号从 h.lineno
      改为 body[0].lineno(pass 真实行),诊断报告不再显示 `except X:`
      伪像,老 pending issue 会洗牌一次
    - 规则 ② smell_except_print_only:同上,snippet 显示 print(...) 真实行
    - 规则 ③ field_unknown:_KP_LIKE_VARS 从 {kp,k,row,r,first} 收窄
      到 {kp};下划线前缀字段跳过(_keywords/_summary 等临时挂字段);
      OR 兼容写法识别(`kp.get('a') or kp.get('b')` 两个 key 至少一个
      在白名单就不报);白名单扩 8 条 kp 相关字段
    - 规则 ④ prompt_wrong_key:error → warning;历史 key 白名单静默
      (system/user/description 兼容对话 A 之前的老 Prompt dict 定义)

定位：
  F062 六维度中 ③ Prompt 调用一致性 / ④ 字段契约 / ⑥ 代码异味
  三个维度的纯 AST 静态规则库。零 AI 调用,零 DB 写入,只读副作用。

对外接口（对话 2 e2e_tester.py 顶层 import 调用）:
  scan_prompt_call_consistency(script_paths) -> list[dict]   # 维度③
  scan_field_contract(script_paths, db_schema_snapshot) -> list[dict]  # 维度④
  scan_code_smells(script_paths) -> list[dict]               # 维度⑥
  run_static_scan(script_paths, db_schema_snapshot) -> dict  # 一次跑完三维度

返回 issue 记录统一格式（供 db.upsert_e2e_issue 消费）:
  {
    "dim_code":   "3_prompt_call" | "4_field_contract" | "6_code_smell",
    "severity":   "info" | "warning" | "error",
    "endpoint":   None（静态规则不挂路由）
    "signature":  "{dim_code}|{rel_path}:{lineno}|{rule_id}",
    "rule_id":    "prompt_wrong_key" 等（便于去重）
    "detail":     {"file": rel_path, "line": int, "snippet": str, "msg": str}
  }

设计约束:
  - 仅依赖 Python 标准库（ast / pathlib / re / json / os），不引第三方
  - 单文件扫描复杂度 O(节点数),大仓库也秒级
  - 所有 AST 访问器用 ast.NodeVisitor 子类实现,不做跨文件推理
  - 明确不扫: .html / .bat / .md / node_modules / .git / venv / __pycache__
  - 对话 A 立规则兜底: scan 过程中任何文件解析失败（如 Python 2 遗留 / 编码异常）
    记 info 级 signature,不 raise,保证单文件失败不终止全量扫描

对话 A/B 踩坑复盘的 4 类 bug 模式（本模块维度⑥的扫描对象）:
  A. try: from ... import X except: X = None      → rule_id = smell_try_except_none_import
  B. if not X: return None（import 之后的死防御）  → rule_id = smell_dead_none_guard
  C. PROMPT['system']、PROMPT['user'] 错误 key    → rule_id = prompt_wrong_key（维度③）
  D. except Exception: pass / except: pass         → rule_id = smell_silent_except
"""

import ast
import os
import re
from pathlib import Path


# ============================================================
# 常量 / 白名单
# ============================================================

# Prompt dict 合法 key 白名单（对话 A 立规则严格口径）
_VALID_PROMPT_KEYS = {"system_prompt", "user_prompt_template"}

# 历史 Prompt dict 允许的 key(对话 A 之前的老 Prompt 定义遗留)
# 规则 ④ prompt_wrong_key 对这些 key 静默不报,只对"既不在新规范也不在
# 历史白名单"的 key 报 warning。长期清理(Prompt key 统一)单独 hotfix。
# part3.7 引入。
_LEGACY_PROMPT_KEYS = {"system", "user", "description"}

# 已知 Prompt 变量后缀（用于识别 HEALTH_*_PROMPT / E2E_*_PROMPT 等 dict 引用）
_PROMPT_VAR_SUFFIXES = ("_PROMPT",)

# kp dict 合法字段白名单（对齐 db_manager 三个扫描查询 AS 别名 + 主表字段）
# 维度④字段契约扫描时用：代码里读 kp.get('xxx') / kp['xxx']
# 如果不在本白名单 + 不在 db_schema_snapshot 的列名集合,就告警
# 注：e2e_tester._build_schema_snapshot 会把 DB 真实 kp 字段动态注入,
#     这里只列 AS 别名和从代码里看到的业务上确认是 kp 属性的字段。
# part3.7 扩充:加 related_knowledge_ids / layer*_tags / tags_layer* /
#              content / description 共 8 条确认是 kp 上下文的别名。
_KP_AS_ALIAS_WHITELIST = {
    # db_manager AS 别名（对话 B 修复后）
    "kp_id", "status", "authority_level", "monetize_tier",
    "category", "subcategory",  # 对话 B LEFT JOIN categories 出的
    # 通用 JSON 字段（_safe_json_parse 后的）
    "final_category_tags", "final_attribute_tags", "final_keywords",
    "suggested_category_tags", "suggested_attribute_tags", "suggested_keywords",
    "practical_insights", "ai_extracted_content",
    # 计数字段（扫描查询聚合）
    "tags_total_count", "annotations_count",
    # part3.7 扩充:代码里明确在 kp 上下文使用的别名字段
    "related_knowledge_ids",  # practical_annotations 的,但常和 kp 一起读
    "content", "description",  # kp 表正式字段名(db_manager 里 SELECT)
    "layer1_tags", "layer2_tags", "layer3_tags",  # health_checker 用
    "tags_layer1", "tags_layer2", "tags_layer3",  # health_checker 兼容别名
}

# 扫描默认的 scripts 子目录清单（对话 2 可覆盖）
_DEFAULT_SCRIPT_FILES = [
    "api_server.py",
    "health_checker.py",
    "extractor.py",
    "duplicate_checker.py",
    "preprocessor.py",
    "experience_notes.py",
    "db_manager.py",
    "backup_manager.py",
]

# 忽略的目录
_IGNORE_DIRS = {"__pycache__", "node_modules", ".git", ".venv", "venv",
                "dist", "build", ".idea", ".vscode"}


# ============================================================
# 工具函数
# ============================================================

def _sig(dim_code, rel_path, lineno, rule_id):
    """生成 issue 去重签名。"""
    return "{}|{}:{}|{}".format(dim_code, rel_path, lineno, rule_id)


def _rel(path, base=None):
    """文件相对路径转正斜杠（signature 跨平台稳定）。"""
    try:
        if base:
            return os.path.relpath(path, base).replace(os.sep, "/")
        return str(path).replace(os.sep, "/")
    except Exception:
        return str(path)


def _snippet(src_lines, lineno, context=0):
    """取第 lineno 行的源码片段（去两端空白）。"""
    if not src_lines:
        return ""
    idx = lineno - 1
    if idx < 0 or idx >= len(src_lines):
        return ""
    return src_lines[idx].rstrip()


def _read_source(path):
    """读文件源码,失败返回 (None, None, err)。"""
    try:
        with open(path, "r", encoding="utf-8") as f:
            src = f.read()
        return src, src.splitlines(), None
    except Exception as e:
        return None, None, str(e)


def _parse_ast(src, path):
    """parse AST,失败返回 (None, err)。"""
    try:
        return ast.parse(src, filename=str(path)), None
    except Exception as e:
        return None, str(e)


def _is_prompt_var(name):
    """判断标识符是否是 Prompt 变量（如 HEALTH_DIAGNOSIS_PROMPT / E2E_RESPONSE_JUDGE_PROMPT）"""
    if not name:
        return False
    return any(name.endswith(suf) for suf in _PROMPT_VAR_SUFFIXES)


# ============================================================
# 维度③：Prompt 调用一致性（AST 访问器）
# ============================================================

class _PromptCallVisitor(ast.NodeVisitor):
    """扫描规则:
      A. import 层面: PROMPT 变量的 import 是否包在 try/except 内（静默降级）
         - try/except 内 ImportFrom PROMPT 变量 → smell_prompt_try_import（warning）
      B. 使用层面: PROMPT['system'] / PROMPT['user'] 错误 key
         - 命中白名单外的 key → prompt_wrong_key（error）
      C. None 兜底: `if not PROMPT: ...` / `PROMPT is None` / `PROMPT == None`
         - 在模块顶层或紧随 import 后的防御分支 → smell_dead_none_guard（warning）
    """

    def __init__(self, rel_path, src_lines):
        self.rel_path = rel_path
        self.src_lines = src_lines
        self.issues = []
        self._in_try = 0  # try 块深度

    # --- A: try/except 包裹 import PROMPT ---
    def visit_Try(self, node):
        self._in_try += 1
        # 检查 body 内是否有 PROMPT 变量的 import
        for stmt in node.body:
            if isinstance(stmt, (ast.ImportFrom, ast.Import)):
                names = []
                if isinstance(stmt, ast.ImportFrom):
                    names = [n.name for n in (stmt.names or [])]
                else:
                    names = [n.name for n in (stmt.names or [])]
                for n in names:
                    if _is_prompt_var(n):
                        self._add("3_prompt_call",
                                  "smell_prompt_try_import",
                                  "warning",
                                  stmt.lineno,
                                  "Prompt 变量 {} 包在 try/except 内 import,会静默降级成 None（对话 A 立规则）".format(n))
        # 检查 handlers 是否 except 吞掉 ImportError 给 Prompt 兜底
        for h in (node.handlers or []):
            for stmt in (h.body or []):
                # except 内 X = None 模式
                if isinstance(stmt, ast.Assign):
                    for tgt in stmt.targets:
                        tgt_name = getattr(tgt, "id", None)
                        if tgt_name and _is_prompt_var(tgt_name):
                            if (isinstance(stmt.value, ast.Constant)
                                    and stmt.value.value is None) or (
                                    isinstance(stmt.value, ast.NameConstant)
                                    and getattr(stmt.value, "value", None) is None):
                                self._add("3_prompt_call",
                                          "smell_prompt_except_none",
                                          "error",
                                          stmt.lineno,
                                          "Prompt 变量 {} 在 except 分支被赋值为 None（import 静默降级,对话 A 缺陷 2）".format(tgt_name))
        self.generic_visit(node)
        self._in_try -= 1

    # --- B: 错误 key 读取 ---
    def visit_Subscript(self, node):
        """匹配 PROMPT[...] 取值,若 key 字符串不在白名单 → 告警

        part3.7:
          - 严重级从 error 降为 warning(立规则第 13 条本意是"新增 Prompt
            必须用 system_prompt / user_prompt_template",不是强制历史 Prompt
            改名。历史 key 一刀切报 error 会把合法读取判成 bug。)
          - 历史 key 白名单(_LEGACY_PROMPT_KEYS = system/user/description)
            静默不报(兼容对话 A 之前的 DUPLICATE_JUDGE_PROMPT 等遗留 Prompt
            定义)。长期清理走单独 hotfix。
          - 其他任意 key → warning(仍然值得关注,可能是 typo)
        """
        # node.value 应是 Name(id='HEALTH_*_PROMPT') 之类
        val = node.value
        var_name = getattr(val, "id", None)
        if var_name and _is_prompt_var(var_name):
            # 提取 slice 的字符串常量
            key_str = self._extract_str_key(node)
            if key_str is not None:
                # 新规范 key → 合法,不报
                if key_str in _VALID_PROMPT_KEYS:
                    pass
                # 历史 key → 白名单静默(part3.7)
                elif key_str in _LEGACY_PROMPT_KEYS:
                    pass
                # 其他 key → warning(降级自 error,part3.7)
                else:
                    rule_id = "prompt_wrong_key"
                    self._add("3_prompt_call", rule_id, "warning", node.lineno,
                              "Prompt 读可疑 key: {}[{}](不在新规范 system_prompt/"
                              "user_prompt_template,也不在历史兼容 key system/user/"
                              "description,可能是 typo)".format(
                                  var_name, repr(key_str)))
        self.generic_visit(node)

    @staticmethod
    def _extract_str_key(subscript_node):
        """提取 PROMPT[...] 的字符串 key,非字符串常量返回 None。"""
        s = subscript_node.slice
        # Python 3.9+: s 直接是 ast.Constant
        if isinstance(s, ast.Constant) and isinstance(s.value, str):
            return s.value
        # Python 3.8 及以下: s 是 ast.Index 包一层
        if hasattr(ast, "Index") and isinstance(s, ast.Index):
            inner = s.value
            if isinstance(inner, ast.Constant) and isinstance(inner.value, str):
                return inner.value
            if hasattr(ast, "Str") and isinstance(inner, ast.Str):
                return inner.s
        # Python 3.8 ast.Str
        if hasattr(ast, "Str") and isinstance(s, ast.Str):
            return s.s
        return None

    # --- C: if not PROMPT: / PROMPT is None / PROMPT == None 防御分支 ---
    def visit_If(self, node):
        """扫描形如:
          if not HEALTH_*_PROMPT: ...
          if HEALTH_*_PROMPT is None: ...
          if HEALTH_*_PROMPT == None: ...
        这三种是"对话 A 立规则"禁止的死防御
        """
        test = node.test
        # 模式 1: UnaryOp(Not) Name(PROMPT)
        if isinstance(test, ast.UnaryOp) and isinstance(test.op, ast.Not):
            inner = test.operand
            name = getattr(inner, "id", None)
            if name and _is_prompt_var(name):
                self._add("3_prompt_call", "smell_dead_none_guard",
                          "warning", node.lineno,
                          "检测到 if not {}: ... 的 None 兜底死防御（对话 A 立规则:禁止 import 懒加载+None 兜底模式）".format(name))
        # 模式 2/3: Compare( Name(PROMPT), is|Eq, Constant(None) )
        if isinstance(test, ast.Compare):
            left = test.left
            name = getattr(left, "id", None)
            if name and _is_prompt_var(name):
                if test.ops and isinstance(test.ops[0], (ast.Is, ast.Eq)):
                    cmp = test.comparators[0] if test.comparators else None
                    is_none = False
                    if isinstance(cmp, ast.Constant) and cmp.value is None:
                        is_none = True
                    elif hasattr(ast, "NameConstant") and isinstance(cmp, ast.NameConstant):
                        if getattr(cmp, "value", None) is None:
                            is_none = True
                    if is_none:
                        self._add("3_prompt_call", "smell_dead_none_guard",
                                  "warning", node.lineno,
                                  "检测到 {} is/== None 的 None 兜底死防御（对话 A 立规则）".format(name))
        self.generic_visit(node)

    def _add(self, dim_code, rule_id, severity, lineno, msg):
        self.issues.append({
            "dim_code": dim_code,
            "severity": severity,
            "endpoint": None,
            "signature": _sig(dim_code, self.rel_path, lineno, rule_id),
            "rule_id": rule_id,
            "detail": {
                "file": self.rel_path,
                "line": lineno,
                "snippet": _snippet(self.src_lines, lineno),
                "msg": msg,
            },
        })


# ============================================================
# 维度④：字段契约扫描（AST 访问器）
# ============================================================

class _FieldContractVisitor(ast.NodeVisitor):
    """扫描规则:
      匹配形如:
        kp.get('xxx') / kp['xxx']
      如果字段名不在:
        1) _KP_AS_ALIAS_WHITELIST（AS 别名白名单）
        2) db_schema_snapshot 的 knowledge_points 列名集合
      两者之一,则告警 field_unknown（warning）

    part3.7 精度重构:
      - _KP_LIKE_VARS 从 {kp,k,row,r,first} 收窄到 {kp}。r / row / first
        是 Python 里通用变量名(不同表的 row / Flask 返回 dict / 工具
        函数返回),用 kp 字段白名单校验是误报来源。改后只检查明确名为
        kp 的变量。
      - 下划线前缀字段跳过:kp["_keywords"] / kp["_summary"] 等是业务
        代码自己挂的临时字段,不是 DB schema 字段,跳过不报。
      - OR 兼容写法识别:`kp.get('a') or kp.get('b')` 这种两个 key 中
        至少一个在白名单的写法,不报(_or_compatible_keys 里记录)。
        典型场景:`kp.get('layer1_tags') or kp.get('tags_layer1')`。
    """

    # part3.7:从 {"kp", "k", "row", "r", "first"} 收窄到 {"kp"}
    _KP_LIKE_VARS = {"kp"}

    def __init__(self, rel_path, src_lines, known_fields):
        self.rel_path = rel_path
        self.src_lines = src_lines
        # known_fields = _KP_AS_ALIAS_WHITELIST ∪ db_schema kp 列名
        self.known_fields = set(known_fields)
        self.issues = []
        # part3.7:记录同一 BoolOp(Or) 表达式内的 kp.get(...) 字段集合
        # 用于 OR 兼容写法识别
        self._or_compatible_keys = set()

    def visit_BoolOp(self, node):
        """识别 `kp.get('a') or kp.get('b')` 兼容写法。
        进入 Or 节点时,收集 kp.get 的所有字段;如果其中至少一个在
        known_fields,整组都不报。
        part3.7 新增。
        """
        if isinstance(node.op, ast.Or):
            collected = self._collect_kp_keys_in_boolop(node)
            if collected and any(k in self.known_fields for k in collected):
                # 至少有一个 key 在白名单,整组 OR 写法视为容错模式,不报
                # 用 _or_compatible_keys 标记,visit_Call/Subscript 会跳过
                self._or_compatible_keys.update(collected)
        self.generic_visit(node)

    def _collect_kp_keys_in_boolop(self, node):
        """递归收集 BoolOp 子表达式里 kp.get('x') / kp['x'] 的 key 字符串。"""
        keys = set()
        for child in ast.walk(node):
            # kp.get('x')
            if isinstance(child, ast.Call):
                f = child.func
                if (isinstance(f, ast.Attribute) and f.attr == "get"
                        and getattr(f.value, "id", None) in self._KP_LIKE_VARS
                        and child.args):
                    k = self._extract_first_str_arg(child.args[0])
                    if k:
                        keys.add(k)
            # kp['x']
            elif isinstance(child, ast.Subscript):
                if getattr(child.value, "id", None) in self._KP_LIKE_VARS:
                    k = _PromptCallVisitor._extract_str_key(child)
                    if k:
                        keys.add(k)
        return keys

    def visit_Call(self, node):
        """匹配 kp.get('field'[, default])"""
        f = node.func
        if isinstance(f, ast.Attribute) and f.attr == "get":
            var = getattr(f.value, "id", None)
            if var in self._KP_LIKE_VARS and node.args:
                key_str = self._extract_first_str_arg(node.args[0])
                if key_str and self._should_report(key_str):
                    self._add("4_field_contract", "field_unknown", "warning",
                              node.lineno,
                              "代码读取未声明字段 {}.get({})（维度④字段契约）".format(
                                  var, repr(key_str)))
        self.generic_visit(node)

    def visit_Subscript(self, node):
        """匹配 kp['field']"""
        var_name = getattr(node.value, "id", None)
        if var_name in self._KP_LIKE_VARS:
            key_str = _PromptCallVisitor._extract_str_key(node)
            if key_str and self._should_report(key_str):
                self._add("4_field_contract", "field_unknown", "warning",
                          node.lineno,
                          "代码读取未声明字段 {}[{}]（维度④字段契约）".format(
                              var_name, repr(key_str)))
        self.generic_visit(node)

    def _should_report(self, key_str):
        """part3.7 新增:综合判断是否要报 field_unknown。
          - 在 known_fields 白名单 → 不报
          - 下划线前缀(_xxx)临时字段 → 不报
          - 在 _or_compatible_keys(OR 兼容写法)→ 不报
          - 其他 → 报
        """
        if not key_str:
            return False
        if key_str in self.known_fields:
            return False
        if key_str.startswith("_"):
            return False
        if key_str in self._or_compatible_keys:
            return False
        return True

    @staticmethod
    def _extract_first_str_arg(node):
        if isinstance(node, ast.Constant) and isinstance(node.value, str):
            return node.value
        if hasattr(ast, "Str") and isinstance(node, ast.Str):
            return node.s
        return None

    def _add(self, dim_code, rule_id, severity, lineno, msg):
        self.issues.append({
            "dim_code": dim_code,
            "severity": severity,
            "endpoint": None,
            "signature": _sig(dim_code, self.rel_path, lineno, rule_id),
            "rule_id": rule_id,
            "detail": {
                "file": self.rel_path,
                "line": lineno,
                "snippet": _snippet(self.src_lines, lineno),
                "msg": msg,
            },
        })


# ============================================================
# 维度⑥：代码异味扫描（AST 访问器）
# ============================================================

class _CodeSmellVisitor(ast.NodeVisitor):
    """扫描 4 类 bug 模式(对话 A/B 复盘沉淀):
      A. try: from/import X except: X = None   (smell_try_except_none_import)
      B. try: ... except: pass / except Exception: pass (smell_silent_except)
      C. try: ... except: print(...)（错误吞成打印） (smell_except_print_only)
      D. 顶层 if not VAR: return None  紧随 def 之后的死防御（基础模式）
         （对话 A 特化版在维度③的 _PromptCallVisitor.visit_If 里）
    """

    def __init__(self, rel_path, src_lines):
        self.rel_path = rel_path
        self.src_lines = src_lines
        self.issues = []

    def visit_Try(self, node):
        # 模式 A: except 内赋值 X = None（非 PROMPT,通用版）
        for h in (node.handlers or []):
            body = h.body or []
            # 只扫 except 内首 1-3 条语句（典型模式）
            for stmt in body[:3]:
                if isinstance(stmt, ast.Assign):
                    # 任意目标被赋 None
                    for tgt in stmt.targets:
                        name = getattr(tgt, "id", None)
                        if name:
                            val = stmt.value
                            is_none = (isinstance(val, ast.Constant) and val.value is None)
                            if not is_none and hasattr(ast, "NameConstant"):
                                is_none = isinstance(val, ast.NameConstant) and getattr(val, "value", None) is None
                            if is_none and not _is_prompt_var(name):
                                # 检查对应 try body 里是否是 import 语句
                                has_import = any(isinstance(s, (ast.Import, ast.ImportFrom))
                                                 for s in (node.body or []))
                                if has_import:
                                    self._add("6_code_smell",
                                              "smell_try_except_none_import",
                                              "warning", stmt.lineno,
                                              "检测到 try: import ... except: {} = None 模式（对话 A 禁止模式）".format(name))

            # 模式 B: except: pass / except Exception: pass
            # part3.7:signature + snippet 锚点从 h.lineno(except 行)改为
            # body[0].lineno(pass 真实行)。老 pending issue 会洗牌一次,
            # 换诊断报告典型代码片段显示真实违规行而不是 `except X:` 伪像。
            if len(body) == 1 and isinstance(body[0], ast.Pass):
                self._add("6_code_smell", "smell_silent_except",
                          "warning", body[0].lineno,
                          "检测到 except: pass 静默吞异常（对话 A 禁止模式）")

            # 模式 C: except 只有一句 print(),没有日志/raise
            # part3.7:行号锚点同上,改为 body[0].lineno(print 真实行)。
            if len(body) == 1 and isinstance(body[0], ast.Expr):
                expr = body[0].value
                if isinstance(expr, ast.Call):
                    fn = expr.func
                    fn_name = getattr(fn, "id", None)
                    if fn_name == "print":
                        self._add("6_code_smell", "smell_except_print_only",
                                  "info", body[0].lineno,
                                  "检测到 except: print(...) 只打印不落日志/不抛（建议改用 log_operation_event）")
        self.generic_visit(node)

    def _add(self, dim_code, rule_id, severity, lineno, msg):
        self.issues.append({
            "dim_code": dim_code,
            "severity": severity,
            "endpoint": None,
            "signature": _sig(dim_code, self.rel_path, lineno, rule_id),
            "rule_id": rule_id,
            "detail": {
                "file": self.rel_path,
                "line": lineno,
                "snippet": _snippet(self.src_lines, lineno),
                "msg": msg,
            },
        })


# ============================================================
# 顶层 API
# ============================================================

def _resolve_script_paths(script_paths):
    """归一 script_paths。
    接受:
      - None 或 空列表 → 使用默认清单（scripts/<默认文件>）
      - 单字符串 → 视作目录或文件
      - list[str] → 逐一解析,目录时展开 *.py
    返回: list[Path]
    """
    base = Path(__file__).parent  # scripts 目录
    paths = []

    if not script_paths:
        # 默认清单,以 scripts/ 为基准
        candidates = [base / fn for fn in _DEFAULT_SCRIPT_FILES]
        for p in candidates:
            if p.exists():
                paths.append(p)
        return paths

    if isinstance(script_paths, (str, Path)):
        script_paths = [script_paths]

    for sp in script_paths:
        p = Path(sp)
        if not p.is_absolute():
            # 尝试相对 scripts/ 目录
            alt = base / p
            if alt.exists():
                p = alt
            else:
                # 相对 cwd
                alt2 = Path.cwd() / p
                if alt2.exists():
                    p = alt2
        if p.is_file() and p.suffix == ".py":
            paths.append(p)
        elif p.is_dir():
            for sub in sorted(p.rglob("*.py")):
                if any(part in _IGNORE_DIRS for part in sub.parts):
                    continue
                paths.append(sub)
        # else: 忽略不存在的路径（静态扫描容忍）

    return paths


def _scan_one_file(path, visitor_class, base_dir, extra_args=()):
    """对单文件应用 visitor,返回 issue 列表 + 可能的 info 级解析失败标记。"""
    rel_path = _rel(path, base_dir)
    src, lines, err = _read_source(path)
    if err:
        return [{
            "dim_code": "0_read",
            "severity": "info",
            "endpoint": None,
            "signature": _sig("0_read", rel_path, 0, "read_failed"),
            "rule_id": "read_failed",
            "detail": {"file": rel_path, "line": 0, "snippet": "",
                       "msg": "源码读取失败: " + err},
        }]
    tree, err = _parse_ast(src, path)
    if err:
        return [{
            "dim_code": "0_parse",
            "severity": "info",
            "endpoint": None,
            "signature": _sig("0_parse", rel_path, 0, "parse_failed"),
            "rule_id": "parse_failed",
            "detail": {"file": rel_path, "line": 0, "snippet": "",
                       "msg": "AST 解析失败: " + err},
        }]
    v = visitor_class(rel_path, lines, *extra_args)
    v.visit(tree)
    return v.issues


def scan_prompt_call_consistency(script_paths=None):
    """维度③：Prompt 调用一致性扫描。

    返回 list[issue dict]。signature 可直接喂给 db.upsert_e2e_issue。
    """
    paths = _resolve_script_paths(script_paths)
    base_dir = Path(__file__).parent.parent  # 仓库根
    out = []
    for p in paths:
        out.extend(_scan_one_file(p, _PromptCallVisitor, base_dir))
    return out


def scan_field_contract(script_paths=None, db_schema_snapshot=None):
    """维度④：字段契约扫描。

    db_schema_snapshot: dict 形如 {"knowledge_points": [col_name, ...], ...}
                        对话 2 引擎层通过 PRAGMA table_info 构造后传入
                        传 None 时退化为"仅白名单"模式（允许对话 1 独立跑）
    """
    kp_cols = []
    if db_schema_snapshot and isinstance(db_schema_snapshot, dict):
        kp_cols = db_schema_snapshot.get("knowledge_points") or []
    known = set(_KP_AS_ALIAS_WHITELIST) | set(kp_cols)

    paths = _resolve_script_paths(script_paths)
    base_dir = Path(__file__).parent.parent
    out = []
    for p in paths:
        out.extend(_scan_one_file(p, _FieldContractVisitor, base_dir, (known,)))
    return out


def scan_code_smells(script_paths=None):
    """维度⑥：代码异味扫描。"""
    paths = _resolve_script_paths(script_paths)
    base_dir = Path(__file__).parent.parent
    out = []
    for p in paths:
        out.extend(_scan_one_file(p, _CodeSmellVisitor, base_dir))
    return out


def run_static_scan(script_paths=None, db_schema_snapshot=None):
    """一次跑完三个维度。对话 2 引擎层主调用入口。

    返回:
      {
        "dim3": list[issue],
        "dim4": list[issue],
        "dim6": list[issue],
        "scanned_files": int,        # 实际处理的 .py 文件数
        "signature_set": set[str],   # 便于对话 2 做报告内去重
      }
    """
    paths = _resolve_script_paths(script_paths)
    base_dir = Path(__file__).parent.parent

    dim3_issues = []
    dim4_issues = []
    dim6_issues = []

    # 拼字段契约的 known set
    kp_cols = []
    if db_schema_snapshot and isinstance(db_schema_snapshot, dict):
        kp_cols = db_schema_snapshot.get("knowledge_points") or []
    known_fields = set(_KP_AS_ALIAS_WHITELIST) | set(kp_cols)

    for p in paths:
        dim3_issues.extend(_scan_one_file(p, _PromptCallVisitor, base_dir))
        dim4_issues.extend(_scan_one_file(p, _FieldContractVisitor, base_dir,
                                          (known_fields,)))
        dim6_issues.extend(_scan_one_file(p, _CodeSmellVisitor, base_dir))

    signature_set = set()
    for iss in (dim3_issues + dim4_issues + dim6_issues):
        signature_set.add(iss["signature"])

    return {
        "dim3": dim3_issues,
        "dim4": dim4_issues,
        "dim6": dim6_issues,
        "scanned_files": len(paths),
        "signature_set": signature_set,
    }


# ============================================================
# CLI 调试入口（可选）
# 用法: python -m scripts.static_analyzer
#       或 python scripts/static_analyzer.py
# ============================================================

def _print_issues(label, issues):
    print("== {} ({} 条) ==".format(label, len(issues)))
    for iss in issues:
        d = iss.get("detail") or {}
        print("  [{}] {}:{}  {}  {}".format(
            iss.get("severity"), d.get("file", ""), d.get("line", 0),
            iss.get("rule_id", ""), d.get("msg", "")))


if __name__ == "__main__":
    import sys
    paths = sys.argv[1:] if len(sys.argv) > 1 else None
    res = run_static_scan(paths, db_schema_snapshot=None)
    print("扫描文件数:", res["scanned_files"])
    print("总 issue 数:", len(res["signature_set"]))
    _print_issues("维度③ Prompt 调用一致性", res["dim3"])
    _print_issues("维度④ 字段契约",       res["dim4"])
    _print_issues("维度⑥ 代码异味",       res["dim6"])
