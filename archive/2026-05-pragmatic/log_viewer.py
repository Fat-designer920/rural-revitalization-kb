"""
log_viewer.py - 日志查看器
路径：scripts/log_viewer.py
版本：v2.3.7
"""
import os, json
from pathlib import Path
from datetime import datetime, timedelta


PROJECT_ROOT = Path(__file__).parent.parent


class LogViewer:
    def __init__(self):
        self.project_root = PROJECT_ROOT
        self.debug_dir = self.project_root / "data" / "debug"
        self.logs_dir = self.project_root / "logs"

        # 确保目录存在
        self.debug_dir.mkdir(parents=True, exist_ok=True)
        self.logs_dir.mkdir(parents=True, exist_ok=True)

    def show_latest_extraction(self, lines=100):
        """显示最新的提取日志(如果存在)"""
        log_file = self.logs_dir / "extraction.log"
        if not log_file.exists():
            print("  [INFO] extraction.log 不存在,可能还没有运行过提取")
            return None

        print(f"\n{'='*60}")
        print(f"  最新提取日志 (最后 {lines} 行)")
        print(f"  文件: {log_file}")
        print(f"{'='*60}\n")

        try:
            with open(log_file, 'r', encoding='utf-8') as f:
                all_lines = f.readlines()
                recent = all_lines[-lines:] if len(all_lines) > lines else all_lines
                for line in recent:
                    print(line.rstrip())
            return recent
        except Exception as e:
            print(f"  [ERROR] 读取日志失败: {e}")
            return None

    def show_errors(self, hours=24, keyword=None):
        """显示最近N小时的错误日志"""
        cutoff = datetime.now() - timedelta(hours=hours)
        errors = []

        # 扫描 debug 目录
        if self.debug_dir.exists():
            for f in self.debug_dir.glob("*.txt"):
                try:
                    mtime = datetime.fromtimestamp(f.stat().st_mtime)
                    if mtime >= cutoff:
                        if keyword is None or keyword.lower() in f.name.lower():
                            errors.append((mtime, f))
                except Exception:
                    pass

        if not errors:
            print(f"\n  [INFO] 最近 {hours} 小时无错误日志")
            return []

        errors.sort(reverse=True)  # 最新的在前

        print(f"\n{'='*60}")
        print(f"  最近 {hours} 小时错误日志 (共 {len(errors)} 个)")
        print(f"{'='*60}\n")

        for mtime, fpath in errors:
            print(f"  [{mtime.strftime('%Y-%m-%d %H:%M:%S')}] {fpath.name}")

        return errors

    def show_debug_file(self, filepath):
        """显示单个调试文件内容"""
        print(f"\n{'='*60}")
        print(f"  调试文件: {filepath.name}")
        print(f"  时间: {datetime.fromtimestamp(filepath.stat().st_mtime).strftime('%Y-%m-%d %H:%M:%S')}")
        print(f"{'='*60}\n")

        try:
            with open(filepath, 'r', encoding='utf-8') as f:
                content = f.read()
                # 限制输出长度
                if len(content) > 5000:
                    print(content[:2500])
                    print(f"\n... (中间省略 {len(content)-5000} 字符) ...\n")
                    print(content[-2500:])
                else:
                    print(content)
        except Exception as e:
            print(f"  [ERROR] 读取失败: {e}")

    def show_debug_files(self, limit=5, keyword=None):
        """显示最新的N个调试文件"""
        files = []

        if self.debug_dir.exists():
            for f in self.debug_dir.glob("*.txt"):
                try:
                    if keyword is None or keyword.lower() in f.name.lower():
                        mtime = datetime.fromtimestamp(f.stat().st_mtime)
                        files.append((mtime, f))
                except Exception:
                    pass

        if not files:
            print(f"\n  [INFO] 无调试文件")
            return []

        files.sort(reverse=True)
        files = files[:limit]

        print(f"\n{'='*60}")
        print(f"  最新 {len(files)} 个调试文件")
        print(f"{'='*60}\n")

        for i, (mtime, fpath) in enumerate(files, 1):
            print(f"  [{i}] {mtime.strftime('%Y-%m-%d %H:%M:%S')} - {fpath.name}")
            size_kb = fpath.stat().st_size / 1024
            print(f"      大小: {size_kb:.1f} KB")

        return files

    def analyze_extraction_errors(self):
        """分析提取过程中的常见错误"""
        print(f"\n{'='*60}")
        print(f"  提取错误分析")
        print(f"{'='*60}\n")

        error_types = {}

        if self.debug_dir.exists():
            for f in self.debug_dir.glob("json_fail_*.txt"):
                # 从文件名提取错误类型
                parts = f.name.split('_')
                if len(parts) >= 3:
                    error_type = '_'.join(parts[2:-2])  # 去掉 json_fail_ 前缀和时间戳
                    error_types[error_type] = error_types.get(error_type, 0) + 1

        if not error_types:
            print("  [INFO] 无 JSON 解析错误记录")
            return

        print("  错误类型统计:")
        for etype, count in sorted(error_types.items(), key=lambda x: -x[1]):
            print(f"    {etype}: {count} 次")

        # 显示最新的错误详情
        latest = max(self.debug_dir.glob("json_fail_*.txt"),
                    key=lambda f: f.stat().st_mtime, default=None)
        if latest:
            print(f"\n  最新错误详情:")
            self.show_debug_file(latest)

    def get_extraction_stats(self):
        """从数据库获取提取统计(需要 db_manager)"""
        try:
            from scripts.db_manager import DatabaseManager
            db = DatabaseManager()
            conn = db.get_connection()
            c = conn.cursor()

            print(f"\n{'='*60}")
            print(f"  提取统计")
            print(f"{'='*60}\n")

            # 按模型统计
            c.execute("""
                SELECT extracted_by_model, COUNT(*) as cnt
                FROM knowledge_points
                WHERE extracted_by_model IS NOT NULL
                GROUP BY extracted_by_model
                ORDER BY cnt DESC
            """)

            print("  按提取模型统计:")
            for row in c.fetchall():
                model = row[0] or "unknown"
                cnt = row[1]
                print(f"    {model}: {cnt} 条")

            # 最近提取的文件
            c.execute("""
                SELECT sf.filename, sf.created_at, COUNT(kp.id) as kp_count
                FROM source_files sf
                LEFT JOIN knowledge_points kp ON sf.id = kp.source_file_id
                WHERE sf.status = 'completed'
                GROUP BY sf.id
                ORDER BY sf.created_at DESC
                LIMIT 10
            """)

            print(f"\n  最近提取的文件 (最新10个):")
            for row in c.fetchall():
                filename = row[0]
                created = row[1]
                kp_count = row[2]
                print(f"    {created} - {filename} ({kp_count} 条知识点)")

            conn.close()

        except Exception as e:
            print(f"  [ERROR] 获取统计失败: {e}")


def main():
    """命令行入口"""
    import sys

    lv = LogViewer()

    if len(sys.argv) > 1:
        cmd = sys.argv[1]
        if cmd == "extraction":
            lv.show_latest_extraction()
        elif cmd == "errors":
            hours = int(sys.argv[2]) if len(sys.argv) > 2 else 24
            lv.show_errors(hours=hours)
        elif cmd == "debug":
            limit = int(sys.argv[2]) if len(sys.argv) > 2 else 5
            lv.show_debug_files(limit=limit)
        elif cmd == "analyze":
            lv.analyze_extraction_errors()
        elif cmd == "stats":
            lv.get_extraction_stats()
        else:
            print(f"未知命令: {cmd}")
    else:
        # 默认显示概览
        print("\n日志查看工具 - 概览\n")
        lv.show_errors(hours=24)
        lv.analyze_extraction_errors()
        lv.get_extraction_stats()


if __name__ == "__main__":
    main()
