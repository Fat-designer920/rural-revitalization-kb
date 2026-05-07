"""
backup_manager.py - 备份管理器
路径：scripts/backup_manager.py
版本：v2.3.6-part1
"""

import os
import sys
import sqlite3
from datetime import datetime, timedelta


class BackupFailedError(Exception):
    """
    v2.2.3 F060: 备份失败异常
    当 operation_hook() 无法创建备份时抛出，调用方可精确catch
    以便终止破坏性操作（批量重跑/重复合并/全库重扫等）
    """
    pass


class BackupManager:
    """数据库备份与恢复管理"""

    def __init__(self, db_path=None, backup_dir=None):
        base_dir = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))

        if db_path is None:
            db_path = os.path.join(base_dir, 'data', 'database', 'knowledge_base.db')
        self.db_path = db_path

        if backup_dir is None:
            backup_dir = os.path.join(base_dir, 'data', 'backups')
        self.backup_dir = backup_dir

        os.makedirs(self.backup_dir, exist_ok=True)

    # --------------------------------------------------
    # 核心操作
    # --------------------------------------------------

    def create_backup(self, label=None):
        """
        创建备份
        label: 可选标签, 如 'before_upgrade', 'restore_before'
        返回: 备份文件路径, 失败返回 None
        """
        if not os.path.exists(self.db_path):
            print("[错误] 数据库文件不存在: {}".format(self.db_path))
            return None

        timestamp = datetime.now().strftime('%Y%m%d_%H%M%S')
        if label:
            filename = "backup_{}_{}.db".format(timestamp, label)
        else:
            filename = "backup_{}.db".format(timestamp)

        backup_path = os.path.join(self.backup_dir, filename)

        try:
            # 使用 SQLite 原生 backup API, 保证数据一致性
            # 即使数据库正在被读取, 也能安全备份
            source = sqlite3.connect(self.db_path)
            dest = sqlite3.connect(backup_path)
            source.backup(dest)
            dest.close()
            source.close()

            size_mb = os.path.getsize(backup_path) / (1024 * 1024)
            print("[成功] 备份已创建: {} ({:.2f} MB)".format(filename, size_mb))
            return backup_path

        except Exception as e:
            print("[错误] 备份失败: {}".format(e))
            if os.path.exists(backup_path):
                os.remove(backup_path)
            return None

    def restore_backup(self, backup_filename):
        """
        从备份恢复数据库
        恢复前自动备份当前状态(带 restore_before 标签)
        返回: True/False
        """
        backup_path = os.path.join(self.backup_dir, backup_filename)
        if not os.path.exists(backup_path):
            print("[错误] 备份文件不存在: {}".format(backup_filename))
            return False

        # 恢复前自动备份当前状态
        print("[提示] 恢复前自动备份当前数据库...")
        auto_backup = self.create_backup(label='restore_before')
        if auto_backup is None:
            print("[警告] 自动备份失败, 但将继续恢复操作")

        try:
            source = sqlite3.connect(backup_path)
            dest = sqlite3.connect(self.db_path)
            source.backup(dest)
            dest.close()
            source.close()

            print("[成功] 数据库已恢复到: {}".format(backup_filename))
            return True

        except Exception as e:
            print("[错误] 恢复失败: {}".format(e))
            return False

    def delete_backup(self, backup_filename):
        """删除指定备份"""
        backup_path = os.path.join(self.backup_dir, backup_filename)
        if not os.path.exists(backup_path):
            print("[错误] 备份文件不存在: {}".format(backup_filename))
            return False

        try:
            os.remove(backup_path)
            print("[成功] 已删除备份: {}".format(backup_filename))
            return True
        except Exception as e:
            print("[错误] 删除失败: {}".format(e))
            return False

    def cleanup_old_backups(self, keep_days=30, keep_min=3):
        """
        清理超过 keep_days 天的旧备份
        但至少保留 keep_min 个最新备份
        返回: 删除数量
        """
        backups = self.list_backups()
        if len(backups) <= keep_min:
            print("[提示] 当前只有{}个备份, 不需要清理 (至少保留{}个)".format(
                len(backups), keep_min))
            return 0

        cutoff = datetime.now() - timedelta(days=keep_days)
        deleted = 0

        for i, backup in enumerate(backups):
            # 最新的 keep_min 个始终保留
            if i < keep_min:
                continue
            if backup['datetime'] < cutoff:
                if self.delete_backup(backup['filename']):
                    deleted += 1

        if deleted > 0:
            print("[完成] 共清理了{}个超过{}天的旧备份".format(deleted, keep_days))
        else:
            print("[提示] 没有需要清理的备份")
        return deleted

    # --------------------------------------------------
    # 查询
    # --------------------------------------------------

    def list_backups(self):
        """
        列出所有备份, 按时间倒序排列(最新在前)
        返回: [{'filename', 'filepath', 'size_mb', 'datetime', 'label'}, ...]
        """
        backups = []
        if not os.path.exists(self.backup_dir):
            return backups

        for f in os.listdir(self.backup_dir):
            if f.startswith('backup_') and f.endswith('.db'):
                filepath = os.path.join(self.backup_dir, f)
                size_mb = os.path.getsize(filepath) / (1024 * 1024)

                # 从文件名解析时间和标签
                try:
                    name_body = f[7:-3]  # 去掉 'backup_' 和 '.db'
                    time_str = name_body[:15]  # YYYYMMDD_HHMMSS
                    dt = datetime.strptime(time_str, '%Y%m%d_%H%M%S')
                    label = name_body[16:] if len(name_body) > 15 else ''
                except (ValueError, IndexError):
                    dt = datetime.fromtimestamp(os.path.getmtime(filepath))
                    label = ''

                backups.append({
                    'filename': f,
                    'filepath': filepath,
                    'size_mb': size_mb,
                    'datetime': dt,
                    'label': label
                })

        return sorted(backups, key=lambda x: x['datetime'], reverse=True)

    def get_backup_status(self):
        """
        获取备份状态概要 (供 check_system.py 调用)
        返回: dict
        """
        backups = self.list_backups()
        if not backups:
            return {
                'has_backup': False,
                'count': 0,
                'latest': None,
                'total_size_mb': 0
            }

        return {
            'has_backup': True,
            'count': len(backups),
            'latest': backups[0]['datetime'].strftime('%Y-%m-%d %H:%M:%S'),
            'latest_filename': backups[0]['filename'],
            'total_size_mb': round(sum(b['size_mb'] for b in backups), 2)
        }

    # --------------------------------------------------
    # v2.2.3 F060: 关键操作强制备份钩子
    # --------------------------------------------------

    # 每类 op_name 保留的最大备份数
    OP_KEEP_PER_NAME = 5
    # backups目录总量上限（MB），超出按时间清理
    TOTAL_SIZE_LIMIT_MB = 2048

    def operation_hook(self, op_name):
        """
        F060: 关键操作前强制自动备份，失败则终止操作

        5个触发点调用：
          - extractor.py 版本重提取（F044）
          - api_server.py 批量重跑（F059）
          - api_server.py 重复合并
          - health_checker.py 体检采纳（F048）
          - api_server.py 全库清空重扫（F049）

        调用方式:
          from backup_manager import BackupManager, BackupFailedError
          try:
              BackupManager().operation_hook('pre_batch_rerun')
          except BackupFailedError as e:
              return jsonify({"status":"error","message":"备份失败，操作已终止"}), 500

        行为：
          1. 调 create_backup(label=op_name) 生成备份
          2. 成功：调 cleanup_by_op_name(op_name) 执行每类保留5个
                  + enforce_size_limit() 执行总量上限
          3. 失败：先写 operation_events(severity='error', event_type='backup_failed')
                  再 raise BackupFailedError

        参数: op_name - 操作标识，建议用 snake_case
              如 pre_batch_rerun / pre_reextract / pre_dup_merge / pre_polish_apply / pre_full_rescan
        返回: 成功返回备份文件路径，失败raise BackupFailedError
        """
        print("[operation_hook] 触发点: {}".format(op_name))
        backup_path = self.create_backup(label=op_name)

        if backup_path is None:
            # 备份失败：先写结构化事件日志，再抛异常终止操作
            self._log_backup_event(
                event_type='backup_failed',
                severity='error',
                op_name=op_name,
                payload={'reason': 'create_backup returned None'}
            )
            raise BackupFailedError(
                "操作前备份失败（op={}），已终止破坏性操作。请检查磁盘空间和数据库文件权限。".format(op_name)
            )

        # 备份成功：写事件日志
        self._log_backup_event(
            event_type='backup_trigger',
            severity='info',
            op_name=op_name,
            payload={'backup_path': os.path.basename(backup_path)}
        )

        # 执行保留策略
        try:
            self.cleanup_by_op_name(op_name, keep=self.OP_KEEP_PER_NAME)
            self.enforce_size_limit(limit_mb=self.TOTAL_SIZE_LIMIT_MB)
        except Exception as e:
            # 清理失败不影响主操作，仅警告
            print("[operation_hook] 清理策略执行异常（不影响主操作）: {}".format(e))

        return backup_path

    def cleanup_by_op_name(self, op_name, keep=5):
        """
        按操作名分组保留最近N个，超出部分删除

        例：op_name='pre_batch_rerun' keep=5
            如果该类备份已有8个，删掉最老的3个
        """
        backups = self.list_backups()
        # 筛选同 op_name 的备份（label精确匹配）
        same_op = [b for b in backups if b.get('label') == op_name]
        if len(same_op) <= keep:
            return 0

        deleted = 0
        # list_backups 已按时间倒序，保留前keep个，删掉后面的
        for b in same_op[keep:]:
            try:
                os.remove(b['filepath'])
                deleted += 1
                print("[cleanup_by_op_name] 删除旧备份: {}".format(b['filename']))
            except Exception as e:
                print("[cleanup_by_op_name] 删除失败 {}: {}".format(b['filename'], e))

        if deleted > 0:
            print("[cleanup_by_op_name] op={} 已清理 {} 个老备份（保留最新 {} 个）".format(
                op_name, deleted, keep))
        return deleted

    def enforce_size_limit(self, limit_mb=2048):
        """
        backups目录总量上限：超过limit_mb时按时间从老到新删除
        保留兜底：即使总量超限，也至少为每类op_name保留1个最新备份

        默认上限 2GB。
        """
        backups = self.list_backups()
        total_mb = sum(b['size_mb'] for b in backups)
        if total_mb <= limit_mb:
            return 0

        # 建立"每类op_name最新一个"的保留白名单
        protected = set()
        seen_labels = set()
        for b in backups:  # 倒序（最新在前）
            label = b.get('label', '') or '__unlabeled__'
            if label not in seen_labels:
                protected.add(b['filepath'])
                seen_labels.add(label)

        # 按时间正序（老的优先删）
        deleted = 0
        for b in sorted(backups, key=lambda x: x['datetime']):
            if total_mb <= limit_mb:
                break
            if b['filepath'] in protected:
                continue
            try:
                os.remove(b['filepath'])
                total_mb -= b['size_mb']
                deleted += 1
                print("[enforce_size_limit] 删除旧备份: {} ({:.1f}MB)".format(
                    b['filename'], b['size_mb']))
            except Exception as e:
                print("[enforce_size_limit] 删除失败 {}: {}".format(b['filename'], e))

        if deleted > 0:
            print("[enforce_size_limit] 总量超限({} MB)，已清理 {} 个老备份，当前总量约 {:.1f} MB".format(
                limit_mb, deleted, total_mb))
        return deleted

    def _log_backup_event(self, event_type, severity, op_name, payload=None):
        """
        内部辅助：调用 db_manager.log_operation_event 写事件日志
        延迟导入 DatabaseManager 避免循环依赖
        任何异常静默吞掉（日志不能打断主流程）
        """
        try:
            # 延迟导入避免循环依赖
            sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
            from db_manager import DatabaseManager

            # 使用和当前db_path相同的数据库
            db = DatabaseManager(db_path=self.db_path)
            p = dict(payload) if payload else {}
            p['op_name'] = op_name
            db.log_operation_event(
                event_type=event_type,
                module='backup',
                severity=severity,
                payload=p
            )
        except Exception as e:
            # 日志失败不影响主流程，仅stdout提示
            print("[_log_backup_event 失败] {}".format(e))


# 模块级便捷函数（v2.3.0-part1.1 新增）
# 供 api_server.py 等调用方直接 import 使用：
#   from scripts.backup_manager import operation_hook, BackupFailedError
#   try:
#       operation_hook("batch_rerun")
#   except BackupFailedError as e:
#       return jsonify({"status":"error","message":"备份失败，操作已终止"}), 500

def operation_hook(op_name):
    """
    模块级便捷函数：等价于 BackupManager().operation_hook(op_name)

    保留此包装是为了匹配工程手册原始设计意图
    （backup_manager.operation_hook(op_name) 而非 BackupManager().operation_hook(...)）
    以及 api_server.py 顶部的既有 import 语句。

    参数: op_name - 操作标识，snake_case，如:
          reextract / batch_rerun / dup_merge / health_adopt / full_rescan
    返回: 成功返回备份文件路径
    异常: 备份失败抛 BackupFailedError，调用方必须 try/except 终止破坏性操作
    """
    return BackupManager().operation_hook(op_name)


# 命令行入口

def _print_backup_list(manager):
    """打印备份列表"""
    backups = manager.list_backups()
    if not backups:
        print("  (暂无备份)")
        return backups

    for i, b in enumerate(backups, 1):
        label_str = " [{}]".format(b['label']) if b['label'] else ""
        print("  {}. {} | {:.2f} MB{}".format(
            i,
            b['datetime'].strftime('%Y-%m-%d %H:%M:%S'),
            b['size_mb'],
            label_str
        ))

    total_mb = sum(b['size_mb'] for b in backups)
    print("\n  共{}个备份, 总大小 {:.2f} MB".format(len(backups), total_mb))
    return backups


def run_backup():
    """一键备份"""
    print("")
    print("=" * 50)
    print("  乡知 - 一键备份")
    print("=" * 50)
    print("")

    manager = BackupManager()
    result = manager.create_backup()

    if result:
        print("")
        print("-" * 50)
        print("当前所有备份:")
        print("")
        _print_backup_list(manager)

    print("")
    input("按回车键退出...")


def run_restore():
    """一键恢复"""
    print("")
    print("=" * 50)
    print("  乡知 - 一键恢复")
    print("=" * 50)
    print("")
    print("[重要] 如果审核界面正在运行, 请先关闭再恢复!")
    print("")

    manager = BackupManager()
    backups = manager.list_backups()

    if not backups:
        print("[提示] 没有找到任何备份文件")
        print("")
        input("按回车键退出...")
        return

    print("可用的备份:")
    print("")
    backups = _print_backup_list(manager)

    print("")
    while True:
        choice = input("请输入要恢复的备份编号 (输入 0 取消): ").strip()
        if choice == '0' or choice == '':
            print("已取消恢复操作")
            break

        try:
            idx = int(choice) - 1
            if 0 <= idx < len(backups):
                selected = backups[idx]
                print("")
                print("[警告] 即将恢复到: {}".format(
                    selected['datetime'].strftime('%Y-%m-%d %H:%M:%S')))
                label_info = " [{}]".format(selected['label']) if selected['label'] else ""
                print("        文件: {}{}".format(selected['filename'], label_info))
                print("        当前数据库将被覆盖 (恢复前会自动备份当前状态)")
                print("")
                confirm = input("确认恢复? (输入 y 确认, 其他取消): ").strip().lower()
                if confirm == 'y':
                    print("")
                    manager.restore_backup(selected['filename'])
                else:
                    print("已取消恢复操作")
                break
            else:
                print("请输入 1-{} 之间的数字".format(len(backups)))
        except ValueError:
            print("请输入有效的数字")

    print("")
    input("按回车键退出...")


def run_cleanup():
    """清理旧备份"""
    print("")
    print("=" * 50)
    print("  乡知 - 清理旧备份")
    print("=" * 50)
    print("")

    manager = BackupManager()

    print("当前备份列表:")
    print("")
    backups = _print_backup_list(manager)

    if not backups:
        print("")
        input("按回车键退出...")
        return

    print("")
    print("将清理超过30天的旧备份 (至少保留最新3个)")
    confirm = input("确认清理? (输入 y 确认, 其他取消): ").strip().lower()
    if confirm == 'y':
        print("")
        manager.cleanup_old_backups(keep_days=30, keep_min=3)
    else:
        print("已取消清理操作")

    print("")
    input("按回车键退出...")


if __name__ == '__main__':
    if len(sys.argv) > 1:
        action = sys.argv[1]
        if action == 'backup':
            run_backup()
        elif action == 'restore':
            run_restore()
        elif action == 'cleanup':
            run_cleanup()
        else:
            print("未知操作: {}".format(action))
            print("可用操作: backup / restore / cleanup")
            input("按回车键退出...")
    else:
        # 默认执行备份
        run_backup()
