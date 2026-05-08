"""
pre_commit_check.py - Git pre-commit 检查,CI/CD 管道本地版
路径：scripts/pre_commit_check.py
版本：v2.3.7-part5
"""
import re
import sys
import ast
import subprocess
from pathlib import Path

PROJECT_ROOT = Path(__file__).parent.parent

def find_changed_py(staged_only=True):
    """获取变更的 .py 文件列表"""
    try:
        if staged_only:
            result = subprocess.run(
                ["git", "diff", "--cached", "--name-only", "--diff-filter=ACM"],
                capture_output=True, text=True, cwd=str(PROJECT_ROOT)
            )
        else:
            result = subprocess.run(
                ["git", "diff", "--name-only", "--diff-filter=ACM", "HEAD"],
                capture_output=True, text=True, cwd=str(PROJECT_ROOT)
            )
        files = result.stdout.strip().split("\n")
        return [f for f in files if f.endswith(".py")]
    except Exception:
        return []

def find_all_py():
    """获取所有 .py 文件"""
    py_files = []
    for pattern in ["scripts/*.py", "agents/*.py"]:
        py_files.extend(str(p.relative_to(PROJECT_ROOT)) for p in PROJECT_ROOT.glob(pattern))
    return py_files

def check_bare_except(filepath):
    """检查文件中是否有 bare except"""
    issues = []
    try:
        full_path = PROJECT_ROOT / filepath
        source = full_path.read_text(encoding="utf-8")
        tree = ast.parse(source, filename=filepath)
        for node in ast.walk(tree):
            if isinstance(node, ast.ExceptHandler):
                if node.type is None:
                    issues.append(f"  L{node.lineno}: bare except (立规则69)")
                    continue
                if isinstance(node.type, ast.Tuple):
                    for elt in node.type.elts:
                        if isinstance(elt, ast.Name) and elt.id == "BaseException":
                            issues.append(f"  L{node.lineno}: except BaseException (too broad)")
        for node in ast.walk(tree):
            if isinstance(node, ast.ExceptHandler):
                if node.type is not None:
                    line = source.splitlines()[node.lineno - 1]
                    if "except:" in line and isinstance(ast.parse(line.strip().lstrip("except:"))):
                        pass
    except SyntaxError:
        issues.append(f"  parse error, skipping AST check")
    except Exception:
        pass
    return issues

def check_api_key_leaks(filepath):
    """检查文件中是否 print/log 了 API key"""
    issues = []
    try:
        full_path = PROJECT_ROOT / filepath
        content = full_path.read_text(encoding="utf-8")
        patterns = [
            (r'print\s*\(.*(?:api[_-]?key|secret|token|password).*\)', "print()包含敏感字段"),
            (r'logging\..*\(.*(?:api[_-]?key|secret|token|password).*\)', "logging包含敏感字段"),
        ]
        for pattern, desc in patterns:
            matches = re.finditer(pattern, content, re.IGNORECASE)
            for m in matches:
                lineno = content[:m.start()].count("\n") + 1
                issues.append(f"  L{lineno}: {desc}")
    except Exception:
        pass
    return issues

def run_smoke():
    """跑冒烟测试,返回 (passed, output)"""
    try:
        result = subprocess.run(
            [sys.executable, "scripts/auto_tester.py", "--smoke"],
            capture_output=True, text=True,
            cwd=str(PROJECT_ROOT), timeout=120
        )
        passed = "0 fail" in result.stdout and result.returncode == 0
        return passed, result.stdout
    except subprocess.TimeoutExpired:
        return False, "SMOKE TEST TIMED OUT (>120s)"
    except FileNotFoundError:
        return False, "Python not found — check sys.executable"

def check_module_import(filepath):
    """检查变更的模块是否能被 importable 的包结构解析"""
    try:
        full_path = PROJECT_ROOT / filepath
        source = full_path.read_text(encoding="utf-8")
        tree = ast.parse(source, filename=filepath)
    except SyntaxError as e:
        return [f"  SyntaxError: {e}"]
    except Exception:
        return []

    issues = []
    for node in ast.walk(tree):
        if isinstance(node, (ast.Import, ast.ImportFrom)):
            if isinstance(node, ast.Import):
                for alias in node.names:
                    issues.append(f"  import {alias.name}")
            elif isinstance(node, ast.ImportFrom):
                mod = node.module or ""
                for alias in node.names:
                    issues.append(f"  from {mod} import {alias.name}")
    return issues

def main():
    if "--all" in sys.argv:
        staged_only = False
        target_label = "全量 (--all)"
    else:
        staged_only = True
        target_label = "暂存区 (pre-commit)"

    changed = find_changed_py(staged_only=staged_only)
    if not changed:
        changed = find_all_py()

    print(f"pre_commit_check — {target_label}")
    print(f"检查文件数: {len(changed)}")
    print()

    total_issues = 0

    for filepath in sorted(changed):
        bare = check_bare_except(filepath)
        leaks = check_api_key_leaks(filepath)
        all_issues = bare + leaks
        if all_issues:
            total_issues += len(all_issues)
            print(f"[!] {filepath}")
            for issue in all_issues:
                print(issue)
            print()

    print("=" * 50)
    if total_issues > 0:
        print(f"FAILED: {total_issues} issue(s) found")
    else:
        print("Code checks passed")

    print()
    passed, output = run_smoke()
    if passed:
        print("Smoke test PASSED")
    else:
        print("Smoke test FAILED")
        print(output[-500:] if len(output) > 500 else output)

    if total_issues > 0 or not passed:
        sys.exit(1)
    print("ALL CHECKS PASSED")
    sys.exit(0)

if __name__ == "__main__":
    main()
