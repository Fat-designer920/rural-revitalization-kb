"""
hardware_orchestrator.py - CPU/GPU/NPU智能调度器(三者分工明确)
路径：scripts/hardware_orchestrator.py
版本：v2.3.7

分工原则:
  NPU → 高频小模型推理(语义搜索/质量分类/内容检测) - 低功耗/低延迟
  GPU → 批量并行计算(大批量嵌入/OCR加速/模型微调) - 高吞吐
  CPU → 调度编排/数据库/文件IO/API调用 - 通用计算

不混用:每种硬件做自己最擅长的事。
"""
import json
import time
from datetime import datetime


class HardwareOrchestrator(object):
    """CPU/GPU/NPU智能调度器。根据任务类型自动分配合适的硬件。"""

    TASK_HARDWARE_MAP = {
        # NPU: 高频小模型推理 — 每次查询都要用,必须快和省
        "semantic_search": "npu",        # 用户查询→向量→匹配
        "quality_classify": "npu",       # 每条KP的质量分级
        "content_type_detect": "npu",    # 新内容的类型识别
        "reader_tag_suggest": "npu",     # 读者标签推荐(轻量分类)
        "freshness_check": "npu",        # 保鲜状态快速判断

        # GPU: 批量并行 — 大批量处理时用
        "batch_embedding": "gpu",        # 全库KP重新生成嵌入向量
        "batch_ocr": "gpu",              # 大批量PDF/图片OCR处理
        "batch_quality_audit": "gpu",    # 全库质量审计(并行处理)
        "model_finetune": "gpu",         # 本地模型微调(未来)

        # CPU: 调度+IO+数据库 — 不适合并行的工作
        "db_query": "cpu",               # SQLite查询(单线程)
        "file_io": "cpu",                # 文件读写
        "api_call": "cpu",               # DeepSeek API调用
        "orchestration": "cpu",          # 任务调度编排
        "text_preprocess": "cpu",        # 文本预处理(分词/清洗)
        "rule_based_check": "cpu",       # 规则引擎检查
    }

    def __init__(self):
        self.capabilities = self._detect_hardware()
        self.task_stats = {"npu": 0, "gpu": 0, "cpu": 0}
        self.start_time = datetime.now()

    def assign(self, task_type):
        """根据任务类型分配硬件。返回 (hardware, reason)。"""
        hw = self.TASK_HARDWARE_MAP.get(task_type, "cpu")
        if hw == "npu" and not self.capabilities["npu_available"]:
            hw = "cpu"
        if hw == "gpu" and not self.capabilities["gpu_available"]:
            hw = "cpu" if task_type != "batch_embedding" else "cpu"

        self.task_stats[hw] = self.task_stats.get(hw, 0) + 1
        return hw

    def get_optimal_strategy(self, task_type, batch_size):
        """根据批量和硬件能力动态选择最优策略"""
        hw = self.assign(task_type)

        # 小批量(<10): NPU最优(低延迟)
        if batch_size < 10 and self.capabilities["npu_available"]:
            return {"hardware": "npu", "strategy": "single_inference", "batch": 1}

        # 中批量(10-100): GPU并行
        if 10 <= batch_size <= 100 and self.capabilities["gpu_available"]:
            return {"hardware": "gpu", "strategy": "parallel_batch", "batch": min(batch_size, 32)}

        # 大批量(>100): GPU分批
        if batch_size > 100 and self.capabilities["gpu_available"]:
            return {"hardware": "gpu", "strategy": "chunked_batch", "batch": 64}

        # 降级: CPU串行
        return {"hardware": "cpu", "strategy": "sequential", "batch": 1}

    def get_status(self):
        elapsed = (datetime.now() - self.start_time).total_seconds()
        total = sum(self.task_stats.values())
        return {
            "hardware": self.capabilities,
            "tasks_processed": total,
            "task_distribution": {
                "npu": f'{self.task_stats.get("npu",0)} ({100*self.task_stats.get("npu",0)//max(1,total)}%)',
                "gpu": f'{self.task_stats.get("gpu",0)} ({100*self.task_stats.get("gpu",0)//max(1,total)}%)',
                "cpu": f'{self.task_stats.get("cpu",0)} ({100*self.task_stats.get("cpu",0)//max(1,total)}%)',
            },
            "uptime_seconds": int(elapsed),
            "efficiency_note": "NPU处理高频推理,GPU处理批量并行,CPU负责调度IO",
        }

    def _detect_hardware(self):
        caps = {"npu_available": False, "gpu_available": False, "cpu_cores": 1}

        # Detect NPU
        try:
            import onnxruntime as ort
            providers = ort.get_available_providers()
            if 'DmlExecutionProvider' in providers:
                caps["npu_available"] = True
                caps["npu_provider"] = "DirectML"
        except ImportError:
            pass

        # Detect GPU
        try:
            import torch
            caps["gpu_available"] = torch.cuda.is_available()
            if caps["gpu_available"]:
                caps["gpu_name"] = torch.cuda.get_device_name(0)
        except ImportError:
            pass

        # CPU cores
        import os
        caps["cpu_cores"] = os.cpu_count() or 1

        return caps
