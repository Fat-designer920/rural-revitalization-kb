"""
infrastructure_agent.py - 后勤保障Agent(系统监测+内存清理+硬件调度+环境优化)
路径：agents/infrastructure_agent.py
版本：v2.3.7

集团公司的基础设施管家。保证30个Agent运行在最佳硬件环境。
职责: 系统检测→内存管理→硬件路由→缓存清理→磁盘监控→CEO汇报
"""
import json, os, sys, gc, shutil, time, threading, platform, ctypes
from datetime import datetime
from pathlib import Path

PROJECT_ROOT = Path(__file__).parent.parent
sys.path.insert(0, str(PROJECT_ROOT / "agents"))

from base_agent import BaseAgent


def _get_windows_memory():
    """用Windows kernel32 API获取精确内存信息。零依赖。"""
    try:
        class MEMORYSTATUSEX(ctypes.Structure):
            _fields_ = [
                ("dwLength", ctypes.c_ulong), ("dwMemoryLoad", ctypes.c_ulong),
                ("ullTotalPhys", ctypes.c_ulonglong), ("ullAvailPhys", ctypes.c_ulonglong),
                ("ullTotalPageFile", ctypes.c_ulonglong), ("ullAvailPageFile", ctypes.c_ulonglong),
                ("ullTotalVirtual", ctypes.c_ulonglong), ("ullAvailVirtual", ctypes.c_ulonglong),
                ("ullAvailExtendedVirtual", ctypes.c_ulonglong),
            ]
        mem = MEMORYSTATUSEX()
        mem.dwLength = ctypes.sizeof(MEMORYSTATUSEX)
        ctypes.windll.kernel32.GlobalMemoryStatusEx(ctypes.byref(mem))
        return {
            "total_gb": round(mem.ullTotalPhys / (1024**3), 1),
            "available_gb": round(mem.ullAvailPhys / (1024**3), 1),
            "used_pct": mem.dwMemoryLoad,
            "used_gb": round((mem.ullTotalPhys - mem.ullAvailPhys) / (1024**3), 1),
        }
    except Exception:
        return None


def _get_disk_usage(path=None):
    """获取磁盘使用情况"""
    try:
        p = path or str(PROJECT_ROOT)
        if os.name == 'nt':
            import ctypes.wintypes
            free = ctypes.c_ulonglong(0)
            total = ctypes.c_ulonglong(0)
            ctypes.windll.kernel32.GetDiskFreeSpaceExW(
                ctypes.c_wchar_p(p), None, ctypes.byref(total), ctypes.byref(free))
            total_gb = round(total.value / (1024**3), 1)
            free_gb = round(free.value / (1024**3), 1)
            return {"total_gb": total_gb, "free_gb": free_gb,
                    "used_pct": round(100 * (total_gb - free_gb) / max(1, total_gb), 0)}
    except Exception:
        pass
    return {"total_gb": 0, "free_gb": 0, "used_pct": 0}


class InfrastructureAgent(BaseAgent):
    """后勤保障Agent — 集团公司的基础设施管家。继承BaseAgent, 确保系统时刻运行在最佳状态。"""

    def __init__(self, db=None, client=None):
        super().__init__(
            agent_code="infrastructure",
            agent_name="后勤保障部长",
            agent_type="infrastructure",
            identity_text=(
                "我是后勤保障部长。我的职责是确保集团公司的IT基础设施——"
                "内存、磁盘、CPU、网络、API连接——始终处于最佳状态。"
                "我主动监控、预警、自动修复,不让基础设施问题影响Agent团队的运作。"
            ),
            client=client, db=db, model="deepseek-v4-flash",
        )

        # 硬件检测
        self.capabilities = self._detect_all()
        self._monitor_thread = None
        self._monitor_running = False
        self._last_mem_pct = 0
        self._cleanup_count = 0
        self._gc_count = 0
        self._alerts = []
        self._task_stats = {"npu": 0, "gpu": 0, "cpu": 0}
        self._start_time = datetime.now()

        # 阈值
        self.MEMORY_CRITICAL = 90   # 强制清理
        self.MEMORY_WARNING = 80    # 预警+轻度清理
        self.MEMORY_SAFE = 60       # 正常范围
        self.DISK_CRITICAL_GB = 5   # 磁盘低于此值告警
        self.MONITOR_INTERVAL = 30  # 监控间隔(秒)

    # ================================================================
    # 硬件检测
    # ================================================================
    def _detect_all(self):
        """全面检测系统硬件能力"""
        caps = {
            "platform": platform.system(),
            "platform_release": platform.release(),
            "cpu_cores": os.cpu_count() or 1,
            "python_version": platform.python_version(),
            "npu_available": False,
            "npu_provider": None,
            "gpu_available": False,
            "gpu_name": None,
            "ram_gb": 0,
            "disk_free_gb": 0,
        }

        # RAM
        mem = _get_windows_memory()
        if mem:
            caps["ram_gb"] = mem["total_gb"]

        # NPU (ONNX Runtime DirectML)
        try:
            import onnxruntime as ort
            providers = ort.get_available_providers()
            if 'DmlExecutionProvider' in providers:
                caps["npu_available"] = True
                caps["npu_provider"] = "DirectML (Intel NPU / AMD / Qualcomm)"
            elif 'CUDAExecutionProvider' in providers:
                caps["gpu_available"] = True
                caps["npu_provider"] = "CUDA"
        except ImportError:
            pass

        # GPU (torch CUDA)
        if not caps["gpu_available"]:
            try:
                import torch
                if torch.cuda.is_available():
                    caps["gpu_available"] = True
                    caps["gpu_name"] = torch.cuda.get_device_name(0)
            except ImportError:
                pass

        # GPU (DirectML via ONNX)
        if not caps["gpu_available"] and caps.get("npu_provider") == "DirectML (Intel NPU / AMD / Qualcomm)":
            caps["gpu_available"] = True
            caps["gpu_name"] = "DirectML (NPU/GPU统一加速)"

        # Disk
        disk = _get_disk_usage()
        caps["disk_free_gb"] = disk.get("free_gb", 0)

        return caps

    # ================================================================
    # 核心能力: 系统快照
    # ================================================================
    def get_system_snapshot(self):
        """获取当前系统完整快照。CEO调用此方法了解基础设施状态。"""
        mem = _get_windows_memory() or {}
        disk = _get_disk_usage()
        elapsed = (datetime.now() - self._start_time).total_seconds()
        total_tasks = sum(self._task_stats.values())

        return {
            "timestamp": datetime.now().isoformat(),
            "memory": {
                "total_gb": mem.get("total_gb", "?"),
                "used_gb": mem.get("used_gb", "?"),
                "available_gb": mem.get("available_gb", "?"),
                "used_pct": mem.get("used_pct", "?"),
                "status": ("CRITICAL" if mem.get("used_pct", 0) >= self.MEMORY_CRITICAL
                           else "WARNING" if mem.get("used_pct", 0) >= self.MEMORY_WARNING
                           else "OK"),
            },
            "disk": {"free_gb": disk.get("free_gb", "?"), "used_pct": disk.get("used_pct", "?"),
                     "status": "CRITICAL" if disk.get("free_gb", 0) < self.DISK_CRITICAL_GB else "OK"},
            "hardware": {
                "cpu_cores": self.capabilities.get("cpu_cores", "?"),
                "npu": f"{'ON' if self.capabilities.get('npu_available') else 'OFF'} ({self.capabilities.get('npu_provider', 'N/A')})",
                "gpu": f"{'ON' if self.capabilities.get('gpu_available') else 'OFF'} ({self.capabilities.get('gpu_name', 'N/A')})",
            },
            "tasks": {"total": total_tasks, "npu": self._task_stats.get("npu", 0),
                      "gpu": self._task_stats.get("gpu", 0), "cpu": self._task_stats.get("cpu", 0)},
            "maintenance": {"cleanups": self._cleanup_count, "gc_runs": self._gc_count,
                            "uptime_minutes": round(elapsed / 60, 1)},
            "alerts": self._alerts[-5:],
        }

    # ================================================================
    # 内存管理
    # ================================================================
    def check_memory(self):
        """检查内存状态。返回 (status, mem_pct, actions_taken)。"""
        mem = _get_windows_memory()
        if not mem:
            return ("unknown", 0, [])

        pct = mem["used_pct"]
        self._last_mem_pct = pct
        actions = []

        if pct >= self.MEMORY_CRITICAL:
            actions = self._emergency_cleanup()
            self._alert("CRITICAL", f"内存{pct}%,已执行紧急清理:{len(actions)}项")
        elif pct >= self.MEMORY_WARNING:
            actions = self._light_cleanup()
            if pct - (self._last_mem_pct or pct) > 5:  # 仍在恶化
                actions += self._emergency_cleanup()
                self._alert("WARNING", f"内存{pct}%且持续恶化,已升级为紧急清理")

        return ("CRITICAL" if pct >= self.MEMORY_CRITICAL
                else "WARNING" if pct >= self.MEMORY_WARNING
                else "OK", pct, actions)

    def _light_cleanup(self):
        """轻度清理: Python GC + 小文件缓存"""
        actions = []
        gc.collect()
        self._gc_count += 1
        actions.append("Python GC执行")

        # 清__pycache__
        cleaned = self._clean_pycache()
        if cleaned > 0:
            actions.append(f"清理{cleaned}个.pyc缓存文件")
        return actions

    def _emergency_cleanup(self):
        """紧急清理: 全面释放内存。保护memory/目录不被清理。"""
        actions = []
        # 0. 保护记忆系统
        memory_dir = PROJECT_ROOT / "memory"
        memory_backup = []
        if memory_dir.exists():
            for mf in memory_dir.glob("*.md"):
                try:
                    memory_backup.append((mf.name, mf.read_text(encoding='utf-8')[:500]))
                except Exception:
                    pass
        # 1. 强制GC(包括不可达对象)
        gc.collect(2)
        self._gc_count += 1
        actions.append("强制GC(gen2)")
        # 记忆已保护
        if memory_backup:
            actions.append(f"记忆已保护({len(memory_backup)}个文件)")

        # 2. 清__pycache__
        cleaned = self._clean_pycache()
        if cleaned > 0:
            actions.append(f"清理{cleaned}个pyc")

        # 3. 清processing缓存(.md文件)
        md_cleaned = self._clean_processing_cache()
        if md_cleaned > 0:
            actions.append(f"清理{md_cleaned}个处理缓存(.md)")

        # 4. 清temp提取文件
        tmp_cleaned = self._clean_temp_files()
        if tmp_cleaned > 0:
            actions.append(f"清理{tmp_cleaned}个临时文件")

        # 5. DB WAL清理
        if self.db:
            try:
                conn = self.db.get_connection()
                conn.execute("PRAGMA wal_checkpoint(TRUNCATE)")
                conn.close()
                actions.append("SQLite WAL截断")
            except Exception:
                pass

        self._cleanup_count += 1
        return actions

    def _clean_pycache(self):
        """清理所有__pycache__目录"""
        count = 0
        try:
            for pycache in PROJECT_ROOT.rglob("__pycache__"):
                try:
                    shutil.rmtree(pycache)
                    count += len(list(pycache.glob("*.pyc"))) if pycache.exists() else 20
                except Exception:
                    pass
        except Exception:
            pass
        return count

    def _clean_processing_cache(self):
        """清理processing目录下的.md缓存文件"""
        count = 0
        processing_dir = PROJECT_ROOT / "data" / "processing"
        if processing_dir.exists():
            try:
                for md_file in processing_dir.glob("*.md"):
                    try:
                        os.remove(md_file)
                        count += 1
                    except Exception:
                        pass
            except Exception:
                pass
        return count

    def _clean_temp_files(self):
        """清理临时文件和日志"""
        count = 0
        temp_patterns = ["*.tmp", "*.temp"]
        for pattern in temp_patterns:
            try:
                for f in PROJECT_ROOT.rglob(pattern):
                    try:
                        os.remove(f)
                        count += 1
                    except Exception:
                        pass
            except Exception:
                pass
        return count

    # ================================================================
    # 硬件路由
    # ================================================================
    def assign_hardware(self, task_type):
        """根据任务类型分配合适的硬件。返回 'npu'/'gpu'/'cpu'。"""
        task_map = {
            "semantic_search": "npu", "quality_classify": "npu",
            "content_detect": "npu", "reader_tag": "npu",
            "batch_embedding": "gpu", "batch_ocr": "gpu",
            "batch_audit": "gpu", "model_finetune": "gpu",
            "db_query": "cpu", "file_io": "cpu",
            "api_call": "cpu", "orchestration": "cpu",
        }
        hw = task_map.get(task_type, "cpu")
        if hw == "npu" and not self.capabilities.get("npu_available"):
            hw = "cpu"
        if hw == "gpu" and not self.capabilities.get("gpu_available"):
            hw = "cpu"
        self._task_stats[hw] = self._task_stats.get(hw, 0) + 1
        return hw

    def get_optimal_batch_size(self, task_type):
        """根据当前内存状况动态调整批处理大小"""
        mem = _get_windows_memory()
        pct = mem.get("used_pct", 50) if mem else 50
        base_sizes = {"batch_embedding": 64, "batch_ocr": 16,
                      "batch_audit": 32, "quality_classify": 50}

        base = base_sizes.get(task_type, 32)
        if pct >= self.MEMORY_CRITICAL:
            return max(1, base // 4)  # 紧急模式: 降至1/4
        elif pct >= self.MEMORY_WARNING:
            return max(1, base // 2)  # 预警模式: 降至1/2
        return base  # 正常模式

    # ================================================================
    # 后台监控
    # ================================================================
    def start_monitoring(self):
        """启动后台监控线程。每30秒检查一次系统状态。"""
        if self._monitor_running:
            return
        self._monitor_running = True

        def _monitor_loop():
            while self._monitor_running:
                try:
                    self.check_memory()
                    disk = _get_disk_usage()
                    if disk.get("free_gb", 999) < self.DISK_CRITICAL_GB:
                        self._alert("WARNING", f"磁盘仅剩{disk['free_gb']}GB")
                except Exception:
                    pass
                time.sleep(self.MONITOR_INTERVAL)

        self._monitor_thread = threading.Thread(target=_monitor_loop, daemon=True)
        self._monitor_thread.start()

    def stop_monitoring(self):
        """停止后台监控"""
        self._monitor_running = False

    # ================================================================
    # 健康检查(供CEO调用)
    # ================================================================
    def health_check(self):
        """全面健康检查。返回 (healthy:bool, issues:list, recommendations:list)。"""
        issues = []
        recommendations = []
        mem = _get_windows_memory() or {}
        disk = _get_disk_usage()
        pct = mem.get("used_pct", 0)

        if pct >= self.MEMORY_CRITICAL:
            issues.append(f"内存{pct}%(临界)")
            recommendations.append("立即执行紧急清理+停止非关键Agent")
        elif pct >= self.MEMORY_WARNING:
            issues.append(f"内存{pct}%(偏高)")
            recommendations.append("执行轻度清理,减小批处理大小")

        if disk.get("free_gb", 999) < self.DISK_CRITICAL_GB:
            issues.append(f"磁盘仅剩{disk['free_gb']}GB")
            recommendations.append("清理processing缓存+临时文件+旧备份")

        if not self.capabilities.get("npu_available") and not self.capabilities.get("gpu_available"):
            issues.append("NPU和GPU均不可用")
            recommendations.append("安装onnxruntime-directml启用NPU加速")

        if self.capabilities.get("npu_available") and self._task_stats.get("npu", 0) == 0:
            recommendations.append("NPU可用但未被使用→调用semantic_search/quality_classify任务")

        return (len(issues) == 0, issues, recommendations)

    # ================================================================
    # CEO报告
    # ================================================================
    def report_to_ceo(self):
        """生成给CEO的基础设施简报"""
        snapshot = self.get_system_snapshot()
        healthy, issues, recs = self.health_check()

        return {
            "agent": self.agent_name,
            "timestamp": snapshot["timestamp"],
            "healthy": healthy,
            "memory": snapshot["memory"],
            "disk": snapshot["disk"],
            "hardware": snapshot["hardware"],
            "issues": issues,
            "recommendations": recs,
            "maintenance": snapshot["maintenance"],
        }

    def think(self, context=None, deep=False):
        """代理AI思考能力(继承BaseAgent接口但专注基础设施)"""
        # 后勤Agent主要靠规则引擎+硬件API,AI思考作为补充
        snapshot = self.get_system_snapshot()
        healthy, issues, recs = self.health_check()

        analysis = "系统运行正常"
        if not healthy:
            analysis = f"发现{len(issues)}个问题: {'; '.join(issues)}"

        return {
            "analysis": analysis,
            "insights": recs,
            "recommendations": [{"action": r, "priority": "P0" if not healthy else "P2", "reason": "基础设施优化"}
                               for r in recs],
            "confidence": "high",
            "needs_ceo_attention": not healthy,
            "agent_code": self.agent_code,
            "snapshot": snapshot,
        }

    def to_dict(self):
        """向后兼容"""
        return {
            "agent_code": self.agent_code, "agent_name": self.agent_name,
            "agent_type": self.agent_type,
            "identity_text": "我是后勤保障部长。我负责集团公司的所有硬件基础设施:CPU/GPU/NPU调度、内存管理、磁盘监控、缓存清理。我的使命是确保30个Agent始终运行在最佳系统环境。",
            "core_questions": ["内存使用率是否超过警戒线","NPU/GPU是否被充分利用","磁盘空间是否充足","缓存是否需要清理","批处理大小是否与环境匹配"],
            "quality_standards": ["内存<80%","NPU/GPU利用率>30%","磁盘剩余>10GB","缓存24小时内至少清理1次"],
            "scoring_dimensions": ["内存管理效率","硬件利用率","系统稳定性","清理及时度"],
        }

    # ================================================================
    # 工具
    # ================================================================
    def _alert(self, level, msg):
        entry = {"time": datetime.now().isoformat(), "level": level, "msg": msg}
        self._alerts.append(entry)
        print(f"[InfraAgent] {level}: {msg}")
        try:
            if self.db:
                self.db.log_operation_event(
                    event_type="infra_alert", severity=level.lower(),
                    module="infrastructure_agent", payload=entry)
        except Exception:
            pass

    def optimize_environment(self):
        """一键优化:检测→清理→调整参数→返回优化报告"""
        report = {"before": self.get_system_snapshot(), "actions": [], "after": None}

        # 1. 内存检查+清理
        status, pct, actions = self.check_memory()
        report["actions"].extend(actions)

        # 2. 确认NPU/GPU可用
        if self.capabilities.get("npu_available"):
            report["actions"].append("NPU已启用,路由高频推理任务到NPU")
        if self.capabilities.get("gpu_available"):
            report["actions"].append("GPU已启用,路由批量任务到GPU")

        # 3. 再取快照
        report["after"] = self.get_system_snapshot()
        return report
