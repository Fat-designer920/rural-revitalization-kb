"""
hardware_profile.py - 通用硬件配置检测与能力评估
路径：agents/hardware_profile.py
版本：v2.3.7-part6
跨平台, 升级硬件后自动重新检测。
"""
import os, json, time, platform, ctypes
from datetime import datetime
from pathlib import Path


def _get_windows_memory():
    """用Windows kernel32 API获取精确内存信息。"""
    try:
        class MEMORYSTATUSEX(ctypes.Structure):
            _fields_ = [
                ("dwLength", ctypes.c_ulong),
                ("dwMemoryLoad", ctypes.c_ulong),
                ("ullTotalPhys", ctypes.c_ulonglong),
                ("ullAvailPhys", ctypes.c_ulonglong),
                ("ullTotalPageFile", ctypes.c_ulonglong),
                ("ullAvailPageFile", ctypes.c_ulonglong),
                ("ullTotalVirtual", ctypes.c_ulonglong),
                ("ullAvailVirtual", ctypes.c_ulonglong),
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
    """获取磁盘使用情况。"""
    try:
        p = path or str(Path(__file__).parent.parent)
        if os.name == 'nt':
            free = ctypes.c_ulonglong(0)
            total = ctypes.c_ulonglong(0)
            ctypes.windll.kernel32.GetDiskFreeSpaceExW(
                ctypes.c_wchar_p(p), None, ctypes.byref(total), ctypes.byref(free))
            total_gb = round(total.value / (1024**3), 1)
            free_gb = round(free.value / (1024**3), 1)
            used_pct = round(100 * (total_gb - free_gb) / max(1, total_gb), 0)
        else:
            import shutil
            usage = shutil.disk_usage(p)
            total_gb = round(usage.total / (1024**3), 1)
            free_gb = round(usage.free / (1024**3), 1)
            used_pct = round(100 * (total_gb - free_gb) / max(1, total_gb), 0)
        return {"total_gb": total_gb, "free_gb": free_gb, "used_pct": used_pct}
    except Exception:
        return {"total_gb": 0, "free_gb": 0, "used_pct": 0}


class HardwareProfile:
    """通用硬件配置检测与能力评估。跨平台, 升级硬件后自动重新检测。"""

    def __init__(self):
        self.cpu = self._detect_cpu()
        self.ram = self._detect_ram()
        self.npu = self._detect_npu()
        self.gpu = self._detect_gpu()
        self.disk = self._detect_disk()
        self._capacity_score = None
        self._task_plan = None
        self._detected_at = datetime.now().isoformat()

    # ================================================================
    # 硬件检测
    # ================================================================

    def _detect_cpu(self):
        """CPU: cores, model, frequency (GHz)."""
        info = {
            "cores": os.cpu_count() or 1,
            "physical_cores": None,
            "model": platform.processor() or platform.machine() or "unknown",
            "freq_ghz": None,
            "platform": platform.system(),
            "platform_release": platform.release(),
        }
        # 尝试获取物理核心数和频率(Windows)
        if os.name == 'nt':
            try:
                import subprocess
                r = subprocess.run(
                    ["wmic", "cpu", "get", "NumberOfCores,MaxClockSpeed,Name"],
                    capture_output=True, text=True, timeout=5)
                lines = [l.strip() for l in r.stdout.split('\n') if l.strip()]
                if len(lines) >= 2:
                    parts = lines[1].split()
                    if parts:
                        try:
                            info["physical_cores"] = int(parts[0])
                        except (ValueError, IndexError):
                            pass
                        try:
                            mhz = float(parts[1]) if len(parts) > 1 else None
                            if mhz:
                                info["freq_ghz"] = round(mhz / 1000, 1)
                        except (ValueError, IndexError):
                            pass
            except Exception:
                pass
        # Linux: /proc/cpuinfo
        if info["physical_cores"] is None:
            try:
                info["physical_cores"] = os.cpu_count() or 1
            except Exception:
                info["physical_cores"] = 1
        return info

    def _detect_ram(self):
        """RAM: total, available, type (DDR4/DDR5)."""
        info = {
            "total_gb": 0,
            "available_gb": 0,
            "used_pct": 0,
            "used_gb": 0,
            "ram_type": "unknown",
        }
        mem = _get_windows_memory()
        if mem:
            info["total_gb"] = mem["total_gb"]
            info["available_gb"] = mem["available_gb"]
            info["used_pct"] = mem["used_pct"]
            info["used_gb"] = mem["used_gb"]

        # Detect RAM type via WMIC (Windows)
        if os.name == 'nt':
            try:
                import subprocess
                r = subprocess.run(
                    ["wmic", "memorychip", "get", "SMBIOSMemoryType"],
                    capture_output=True, text=True, timeout=5)
                lines = r.stdout.strip().split('\n')
                for line in lines[1:]:
                    line = line.strip()
                    if line and line.isdigit():
                        mt = int(line)
                        # SMBIOS types: 20=DDR, 21=DDR2, 22=DDR2 FB-DIMM, 24=DDR3, 26=DDR4, 34=DDR5
                        type_map = {20: "DDR", 21: "DDR2", 22: "DDR2", 24: "DDR3",
                                    26: "DDR4", 34: "DDR5"}
                        info["ram_type"] = type_map.get(mt, f"SMBIOS-{mt}")
                        break
            except Exception:
                pass

        # Linux: /proc/meminfo
        if info["total_gb"] == 0 and hasattr(os, "sysconf"):
            try:
                info["total_gb"] = round(os.sysconf('SC_PAGE_SIZE')
                                         * os.sysconf('SC_PHYS_PAGES') / (1024**3), 1)
            except Exception:
                pass

        return info

    def _detect_npu(self):
        """NPU: DirectML / Intel NPU / Qualcomm AI Engine / Apple Neural Engine."""
        info = {
            "available": False,
            "provider": None,
            "detail": "",
        }
        # ONNX Runtime DirectML (Windows: Intel NPU / AMD / Qualcomm)
        try:
            import onnxruntime as ort
            providers = ort.get_available_providers()
            if 'DmlExecutionProvider' in providers:
                info["available"] = True
                info["provider"] = "DirectML"
                info["detail"] = "ONNX Runtime DirectML (Intel NPU / AMD / Qualcomm)"
                return info
            if 'CUDAExecutionProvider' in providers:
                info["provider"] = "CUDA"  # CUDA maps to GPU below
        except ImportError:
            pass

        # Apple Neural Engine (CoreML via onnxruntime)
        if platform.system() == "Darwin":
            try:
                import onnxruntime as ort
                providers = ort.get_available_providers()
                if 'CoreMLExecutionProvider' in providers:
                    info["available"] = True
                    info["provider"] = "CoreML"
                    info["detail"] = "Apple Neural Engine (CoreML)"
                    return info
            except ImportError:
                pass

        # Intel OpenVINO (Intel NPU on Linux/Windows)
        try:
            import onnxruntime as ort
            providers = ort.get_available_providers()
            if 'OpenVINOExecutionProvider' in providers:
                info["available"] = True
                info["provider"] = "OpenVINO"
                info["detail"] = "Intel NPU via OpenVINO"
                return info
        except (ImportError, AttributeError):
            pass

        return info

    def _detect_gpu(self):
        """GPU: CUDA / DirectML / OpenCL / MPS."""
        info = {
            "available": False,
            "provider": None,
            "name": None,
            "vram_gb": 0,
        }

        # CUDA (NVIDIA)
        try:
            import torch
            if torch.cuda.is_available():
                info["available"] = True
                info["provider"] = "CUDA"
                info["name"] = torch.cuda.get_device_name(0) or "NVIDIA GPU"
                try:
                    info["vram_gb"] = round(
                        torch.cuda.get_device_properties(0).total_memory / (1024**3), 1)
                except Exception:
                    pass
                return info
        except ImportError:
            pass

        # MPS (Apple Silicon)
        if platform.system() == "Darwin":
            try:
                import torch
                if torch.backends.mps.is_available():
                    info["available"] = True
                    info["provider"] = "MPS"
                    info["name"] = "Apple GPU (MPS)"
                    return info
            except ImportError:
                pass

        # DirectML via ONNX (AMD/NPU shared fallback)
        try:
            import onnxruntime as ort
            providers = ort.get_available_providers()
            if 'DmlExecutionProvider' in providers:
                info["available"] = True
                info["provider"] = "DirectML"
                info["name"] = "DirectML GPU (AMD/Intel)"
                return info
        except ImportError:
            pass

        return info

    def _detect_disk(self):
        """Disk: total, free, used_pct for project drive."""
        return _get_disk_usage()

    # ================================================================
    # 综合能力评估
    # ================================================================

    def assess_capacity(self):
        """综合能力评分 0-100。

        CPU: 25 pts (cores * freq_ghz 归一化)
        RAM: 25 pts (total_gb 归一化)
        NPU: 25 pts (DirectML/CoreML/OpenVINO available?)
        GPU: 25 pts (CUDA/DirectML/MPS available?)
        """
        if self._capacity_score is not None:
            return self._capacity_score

        score = 0.0

        # CPU: 25 pts
        cores = self.cpu.get("cores", 1)
        freq = self.cpu.get("freq_ghz") or 2.0
        cpu_power = cores * freq
        # 4 cores x 2.5 GHz = 10 as "normal", scale to 25 pts
        cpu_score = min(25, cpu_power / 10.0 * 15 + 5)
        score += cpu_score

        # RAM: 25 pts
        ram_gb = self.ram.get("total_gb", 0)
        # 8 GB = 10 pts, 16 GB = 20 pts, 32 GB = 25 pts
        ram_score = min(25, ram_gb / 32.0 * 25 + 5)
        score += ram_score

        # NPU: 25 pts
        if self.npu.get("available"):
            score += 25
        elif self.gpu.get("available") and self.gpu.get("provider") == "DirectML":
            score += 15  # GPU DirectML can serve NPU-like tasks

        # GPU: 25 pts
        if self.gpu.get("available"):
            vram = self.gpu.get("vram_gb", 0)
            if vram >= 8:
                score += 25
            elif vram >= 4:
                score += 18
            else:
                score += 12
        if self.npu.get("available"):
            pass  # NPU already counted above

        self._capacity_score = round(score, 1)
        return self._capacity_score

    # ================================================================
    # 任务规划
    # ================================================================

    def plan_tasks(self, task_types=None):
        """根据硬件能力规划任务并行度和批处理大小。

        返回: {
            max_concurrent: int,
            batch_sizes: {task_type: size},
            can_use_npu: bool,
            can_use_gpu: bool,
            recommended_model_size: 'small'|'medium'|'large',
        }
        """
        types = task_types or ["semantic_search", "qa", "batch_embedding"]

        ram_gb = self.ram.get("total_gb", 8)
        cores = self.cpu.get("cores", 4)

        # 并行度: RAM-dependent (每任务约 500MB)
        max_concurrent = max(1, min(cores, int(ram_gb / 0.5)))

        # 批处理大小: RAM + NPU/GPU dependent
        batch_sizes = {}
        base_batch = {
            "batch_embedding": 64,
            "batch_ocr": 16,
            "batch_audit": 32,
            "quality_classify": 50,
            "semantic_search": 100,
            "qa": 1,
        }
        ram_factor = min(2.0, ram_gb / 16.0)  # 16GB = 1x, 8GB = 0.5x
        for t in types:
            base = base_batch.get(t, 32)
            adjusted = max(1, int(base * ram_factor))
            if self.gpu.get("available"):
                adjusted = min(adjusted * 2, 512)
            batch_sizes[t] = adjusted

        # 模型大小建议
        if ram_gb >= 32 and self.gpu.get("vram_gb", 0) >= 8:
            model_size = "large"
        elif ram_gb >= 16:
            model_size = "medium"
        else:
            model_size = "small"

        self._task_plan = {
            "max_concurrent": max_concurrent,
            "batch_sizes": batch_sizes,
            "can_use_npu": self.npu.get("available", False),
            "can_use_gpu": self.gpu.get("available", False),
            "recommended_model_size": model_size,
        }
        return self._task_plan

    # ================================================================
    # 快照与对比
    # ================================================================

    def get_snapshot(self):
        """完整硬件快照(Markdown格式,可展示在UI)。"""
        capacity = self.assess_capacity()
        task_plan = self.plan_tasks()
        lines = [
            "## 硬件快照",
            f"- **检测时间**: {self._detected_at}",
            f"- **平台**: {self.cpu.get('platform', '?')} {self.cpu.get('platform_release', '')}",
            "",
            "### CPU",
            f"- 型号: {self.cpu.get('model', '?')}",
            f"- 核心: {self.cpu.get('physical_cores', '?')}物理 / {self.cpu.get('cores', '?')}逻辑",
            f"- 频率: {self.cpu.get('freq_ghz', '?')} GHz",
            "",
            "### 内存",
            f"- 总量: {self.ram.get('total_gb', '?')} GB",
            f"- 可用: {self.ram.get('available_gb', '?')} GB ({100 - self.ram.get('used_pct', 0):.0f}%)",
            f"- 类型: {self.ram.get('ram_type', '?')}",
            "",
            "### NPU",
            f"- 可用: {'是' if self.npu.get('available') else '否'}",
            f"- 引擎: {self.npu.get('provider') or '无'}",
            f"- 详情: {self.npu.get('detail') or 'N/A'}",
            "",
            "### GPU",
            f"- 可用: {'是' if self.gpu.get('available') else '否'}",
            f"- 引擎: {self.gpu.get('provider') or '无'}",
            f"- 型号: {self.gpu.get('name') or 'N/A'}",
            f"- 显存: {self.gpu.get('vram_gb') or 0} GB",
            "",
            "### 磁盘",
            f"- 总量: {self.disk.get('total_gb', '?')} GB",
            f"- 可用: {self.disk.get('free_gb', '?')} GB ({100 - self.disk.get('used_pct', 0):.0f}%)",
            "",
            "### 综合能力",
            f"- **评分**: {capacity}/100",
            f"- 最大并行任务: {task_plan.get('max_concurrent', '?')}",
            f"- 推荐模型规模: {task_plan.get('recommended_model_size', '?')}",
        ]
        return '\n'.join(lines)

    def compare_to(self, previous_snapshot):
        """与前一次快照对比,检测硬件升级变化。
        previous_snapshot: dict, 来自 get_snapshot_dict() 的 JSON 反序列化。
        返回: {changed: bool, changes: [str], summary: str}。
        """
        current = self.to_dict()
        prev = previous_snapshot or {}
        changes = []

        def _compare(path, label, fmt=str):
            cur_val = _nested_get(current, path)
            prev_val = _nested_get(prev, path)
            if cur_val != prev_val and cur_val is not None and prev_val is not None:
                changes.append(f"{label}: {fmt(prev_val)} -> {fmt(cur_val)}")

        _compare("cpu.cores", "CPU逻辑核心")
        _compare("cpu.physical_cores", "CPU物理核心")
        _compare("cpu.freq_ghz", "CPU频率(GHz)")
        _compare("ram.total_gb", "内存总量(GB)")
        _compare("ram.ram_type", "内存类型")
        _compare("npu.available", "NPU可用")
        _compare("npu.provider", "NPU引擎")
        _compare("gpu.available", "GPU可用")
        _compare("gpu.provider", "GPU引擎")
        _compare("gpu.vram_gb", "GPU显存(GB)")
        _compare("disk.total_gb", "磁盘总量(GB)")

        return {
            "changed": len(changes) > 0,
            "changes": changes,
            "summary": "; ".join(changes) if changes else "硬件无变化",
        }

    # ================================================================
    # 序列化
    # ================================================================

    def to_dict(self):
        """JSON 可序列化的完整硬件信息。"""
        return {
            "detected_at": self._detected_at,
            "cpu": self.cpu,
            "ram": self.ram,
            "npu": self.npu,
            "gpu": self.gpu,
            "disk": self.disk,
            "capacity_score": self.assess_capacity(),
            "task_plan": self._task_plan or self.plan_tasks(),
        }

    def __repr__(self):
        return (f"HardwareProfile(CPU:{self.cpu.get('cores')}c "
                f"RAM:{self.ram.get('total_gb')}GB "
                f"NPU:{'ON' if self.npu.get('available') else 'OFF'} "
                f"GPU:{'ON' if self.gpu.get('available') else 'OFF'} "
                f"Score:{self.assess_capacity()}/100)")


# ================================================================
# 辅助
# ================================================================

def _nested_get(d, path, default=None):
    """从嵌套 dict 取值,路径用 '.' 分隔 (e.g. 'cpu.cores')."""
    keys = path.split('.')
    cur = d
    for k in keys:
        if isinstance(cur, dict):
            cur = cur.get(k)
        else:
            return default
        if cur is None:
            return default
    return cur
