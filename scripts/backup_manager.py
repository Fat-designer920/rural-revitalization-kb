"""
备份恢复管理器
版本: v2.1.0-a
功能: 数据库一键备份、恢复、清理
"""

import os
import sys
import sqlite3
from datetime import datetime, timedelta


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


# ==================================================
# 命令行入口
# ==================================================

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
    print("  乡村振兴知识库 - 一键备份")
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
    print("  乡村振兴知识库 - 一键恢复")
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
    print("  乡村振兴知识库 - 清理旧备份")
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
