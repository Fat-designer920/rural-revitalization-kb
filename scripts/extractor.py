"""
extractor.py - 知识点提取引擎
路径：scripts/extractor.py
版本：v2.3.4-hotfix3 - 0 条 kp 不进降级链 + 配合 deepseek_client 的 JSONL 兼容降级

变更说明（v2.3.4-hotfix3）：
  X1 _extract_with_auto_split 第 340 行附近 BUG#2A 修复:
    - 原:if not result["truncated"] and kps: return kps  ← 致命 and kps
    - 改:未截断时一律 return kps,0 条 kp 也是 R1 合理判定(背景段/章节标题)
    - 新增分支:0 kp + raw_parsed=True → "本段无可提取知识点(R1 合理判定,跳过救援)"
    - 仅当 0 kp + raw_parsed=False(7 步降级也救不回)才进降级链
  X2 配合 deepseek_client.chat_with_jsonl 的 X2:
    - 上层不变,但 raw_parsed=True 的概率因 7 步保险大幅提升
    - 老唐 0428 第 2 段 958 字 0.099 元 R1 输出全丢,本版起会被 7 步保险救回
  根因:hotfix1 引入降级链时把"0 kp"和"截断"混为一谈,实际 R1 完成思考且未截断时
       0 kp 是合法结果(背景段/章节标题/空白页),不应触发不必要救援链
  立规则 9 第 18 次应验:if not X and Y 形式的判定容易把"X 不成立"和"Y 不存在"混淆,
       应明确分支条件,prefer "if not X: return Y(可空)" 形式

变更说明（v2.3.4-hotfix1）：
  H1 _extract_with_auto_split 降级链重写(段内同步,不留事后批量重跑):
    - L0: chat_with_jsonl (R1, deepseek-reasoner) 主提取 → 截断/0 partial/解析失败 ↓
    - L1: chat_jsonl_via_siliconflow (Kimi-K2.6, 思考型, 256K) 整段重提 → 仍失败 ↓
    - L2: chat_jsonl_via_siliconflow (Pro/deepseek-ai/DeepSeek-R1, R1 跨厂商镜像) 整段重提 ↓
    - L3: F057 老逻辑(若 partial_kps>=1 时尾段补救) ↓
    - L4: 保留已提取 + error 事件 + 控制台 ❌
  H2 废弃 prefix 续写主链(_recover_via_prefix 整体不再被调用,代码保留作未来重启)
  H3 每条 kp 在生成时打 _extracted_by_model 标记(r1/kimi/r1_mirror/f057_recovery)
     入库 add_knowledge_point 透传 extracted_by_model 字段(老唐肉眼仪表盘监控)
  H4 _truncation_stats 扩字段:kimi_recoveries / r1_mirror_recoveries / total_failures
  H5 控制台 📊 [文件统计] 字段升级:截断/Kimi救/R1镜像救/F057兜底/全失败
  根因:v2.3.4 prefix 续写假设 partial_kps>=1, R1 思考爆 token 时 partial==0 直接失效。
  老唐 2026-04-28 喂料实测第 8/10 段(611字)触发缺口,整段失败 0 提取。
  新方案:多思考型模型整段重提,跨模型概率冗余压低截断概率到接近 0。

变更说明（v2.3.4）：
  D9 输出形态升级为 JSON Lines:
    - _extract_single 改用 self.client.chat_with_jsonl()
    - 返回 dict 增加 prefix_for_continuation / meta 两字段
  D10 截断处理新流程(三级降级):
    - L0/L1: prefix 续写(走 beta 端点 + V3,最多 2 次) [v2.3.4-hotfix1 起 DEPRECATED]
    - L2 兜底: F057 老逻辑 excerpt 三级定位
    - L3 终态: 保留已提取 + warning 日志
  D11 文件级控制台统计:
    - extract_from_file 入口重置 self._truncation_stats
    - 完成时控制台输出一行 📊 [文件统计]
"""
import os, sys, json, re, shutil, hashlib, time
from pathlib import Path
from datetime import datetime

PROJECT_ROOT = Path(__file__).parent.parent
sys.path.insert(0, str(PROJECT_ROOT))

from scripts.file_reader import FileReader
from scripts.deepseek_client import DeepSeekClient, CostLimitExceeded
from scripts.db_manager import DatabaseManager
from scripts.prompts.prompt_templates import (
    get_extraction_prompt, get_prompt_version,
    CONTEXT_RELAY_TEMPLATE, PRE_ANALYSIS_PROMPT,
    SEGMENT_SUMMARY_PROMPT, CROSS_SEGMENT_CHECK_PROMPT,
    QC_CHECK_PROMPT, QC_CHECK_SINGLE_PROMPT  # v2.2.3 F058
)
from scripts.tag_config import get_layer1_tag_names, CONTENT_READINESS, SOURCE_AUTHORITY
from scripts.policy_validator import PolicyValidator
from scripts.duplicate_checker import DuplicateChecker


class Extractor:
    TYPE_NAMES = {
        "policy": "政策文件", "case": "项目案例", "experience": "操盘经验",
        "tool": "实操工具", "data": "数据资料"
    }

    MODEL_OPTIONS = {
        "1": {
            "model": "deepseek-reasoner",
            "name": "R1 深度推理",
            "desc": "最精准,逐段深度分析,速度较慢,费用较高",
            "segment_max": 3000  # v2.1.0-d: 从4000降到3000,减少截断
        },
        "2": {
            "model": "deepseek-chat",
            "name": "V3 快速提取",
            "desc": "速度快,性价比高,适合批量处理",
            "segment_max": 6000
        }
    }

    # 第一层标签的合法名称清单（启动时从tag_config加载）
    VALID_LAYER1_NAMES = set(get_layer1_tag_names())

    # 元数据合法值
    VALID_READINESS = set(CONTENT_READINESS.keys())
    VALID_AUTHORITY = set(SOURCE_AUTHORITY.keys())

    # v2.2.3 F058: 类级质检flag映射（三级降级共用；从原 _quality_check 内部提升）
    QC_FLAG_MAP = {
        "缺上下文": "independence", "独立性不足": "independence",
        "信息空泛": "density", "信息密度低": "density",
        "颗粒度过粗": "granularity_coarse", "过粗": "granularity_coarse",
        "颗粒度过细": "granularity_fine", "过细": "granularity_fine",
        "标签不符": "tag_mismatch", "标签不匹配": "tag_mismatch",
        "疑似重复": "duplicate_suspect", "重复": "duplicate_suspect",
        "启示无依据": "insight_no_basis", "举一反三无依据": "insight_no_basis",
        "提炼与原文重复": "low_value_add", "提炼无增值": "low_value_add",
    }

    # v2.2.3 F057: 截断补救降级最大次数 + 最小段长阈值
    TRUNCATION_MAX_ATTEMPTS = 3
    TRUNCATION_MIN_SEG_LEN = 500
    TRUNCATION_MIN_TAIL_LEN = 200

    def __init__(self, progress_callback=None):
        p = PROJECT_ROOT / "config" / "settings.json"
        with open(p, "r", encoding="utf-8") as f:
            self.config = json.load(f)
        self.reader = FileReader(self.config)
        self.client = DeepSeekClient(self.config)
        self.db = DatabaseManager()
        self.pending = Path(self.config.get("pending_path", PROJECT_ROOT / "data" / "pending"))
        self.processing = Path(self.config.get("processing_path", PROJECT_ROOT / "data" / "processing"))
        self.completed = Path(self.config.get("completed_path", PROJECT_ROOT / "data" / "completed"))
        self.failed_dir = Path(self.config.get("failed_path", PROJECT_ROOT / "data" / "failed"))
        self.completed.mkdir(parents=True, exist_ok=True)
        self.failed_dir.mkdir(parents=True, exist_ok=True)
        self.extraction_model = None
        self.extraction_model_name = None
        self.segment_max_len = 3000  # v2.1.0-d: 默认值也改为3000
        self.policy_validator = PolicyValidator(db=self.db, client=self.client)
        self.duplicate_checker = DuplicateChecker(db=self.db, client=self.client)
        self._progress_callback = progress_callback
        self._headless = False  # v2.1.2 bugfix: headless模式跳过所有input()

    def select_model(self):
        print(f"\n  请选择提取模型:")
        print(f"  {'=' * 50}")
        for key, opt in self.MODEL_OPTIONS.items():
            print(f"  [{key}] {opt['name']}")
            print(f"      {opt['desc']}")
        print(f"  {'=' * 50}")
        while True:
            choice = input("  请输入选项编号 (1/2): ").strip()
            if choice in self.MODEL_OPTIONS:
                opt = self.MODEL_OPTIONS[choice]
                self.extraction_model = opt["model"]
                self.extraction_model_name = opt["name"]
                self.segment_max_len = opt["segment_max"]
                print(f"\n  已选择: {opt['name']} ({opt['model']})")
                return
            print(f"  无效输入,请输入 1 或 2")

    def set_model(self, model_key="1"):
        """非交互式模型选择，供API调用"""
        opt = self.MODEL_OPTIONS.get(model_key, self.MODEL_OPTIONS["1"])
        self.extraction_model = opt["model"]
        self.extraction_model_name = opt["name"]
        self.segment_max_len = opt["segment_max"]
        self._headless = True  # API调用时启用headless模式

    def _report_progress(self, **kw):
        """向进度回调报告当前状态"""
        if self._progress_callback:
            try:
                self._progress_callback(kw)
            except:
                pass

    @staticmethod
    def calculate_file_hash(file_path):
        h = hashlib.md5()
        with open(file_path, "rb") as f:
            while True:
                chunk = f.read(8192)
                if not chunk: break
                h.update(chunk)
        return h.hexdigest()

    def check_duplicate(self, file_path, filename):
        file_hash = self.calculate_file_hash(file_path)
        existing = self.db.check_file_hash_exists(file_hash)
        if existing:
            exist_name = existing.get("renamed_filename") or existing.get("original_filename")
            exist_status = existing.get("process_status", "")
            exist_msg = existing.get("process_message", "")
            if exist_status == "completed" and "提取" in exist_msg and "知识点" in exist_msg and "未提取到" not in exist_msg:
                print(f"     [发现重复] 该文件已成功处理过(MD5指纹相同)")
                print(f"       原记录: {exist_name} | {exist_msg}")
                if self._headless:
                    print(f"     [headless] 自动重新分析")
                    return False, file_hash
                while True:
                    answer = input("     是否重新分析? (Y=重新分析 / N=跳过): ").strip().upper()
                    if answer == "Y":
                        print(f"     好的,将重新分析此文件")
                        return False, file_hash
                    elif answer == "N":
                        print(f"     已跳过")
                        return True, file_hash
                    else:
                        print(f"     请输入 Y 或 N")
            if exist_status == "failed":
                print(f"     [重新处理] 该文件上次处理失败,本次将重新提取")
            elif "未提取到" in exist_msg:
                print(f"     [重新处理] 该文件上次未提取到知识点,本次将重新提取")
            else:
                print(f"     [重新处理] 该文件存在旧记录(状态:{exist_status}),本次将重新提取")
            return False, file_hash
        return False, file_hash

    def _clean_pending(self, original_filename):
        try:
            for f in self.pending.iterdir():
                if f.name == original_filename:
                    os.remove(str(f))
                    print(f"     已清理pending中的原始文件: {original_filename}")
                    return
        except Exception as e:
            print(f"     ! pending文件清理失败: {e}")

    def get_processing_files(self):
        conn = self.db.get_connection(); c = conn.cursor()
        c.execute("SELECT * FROM source_files WHERE process_status='processing' ORDER BY created_at")
        rows = [dict(r) for r in c.fetchall()]; conn.close(); return rows

    def _determine_type(self, rec, content):
        fn = (rec.get("renamed_filename") or rec["original_filename"]).lower()
        if any(k in fn for k in ["政策", "通知", "办法", "规定", "意见", "规划", "zc"]): return "policy"
        if any(k in fn for k in ["案例", "项目", "al"]): return "case"
        if any(k in fn for k in ["经验", "心得", "复盘", "jy"]): return "experience"
        if any(k in fn for k in ["模板", "工具", "合同", "gj"]): return "tool"
        if any(k in fn for k in ["数据", "统计", "测算", "sj"]): return "data"
        preview = content[:1000]
        if sum(1 for kw in ["发布", "施行", "通知", "各省", "第一条", "本办法"] if kw in preview) >= 2: return "policy"
        return "policy"

    def _split(self, content, max_len=None):
        if max_len is None: max_len = self.segment_max_len
        if len(content) <= max_len: return [content]
        segs, cur = [], ""
        for para in content.split("\n\n"):
            if len(cur) + len(para) > max_len and cur:
                segs.append(cur); cur = para
            else:
                cur = cur + "\n\n" + para if cur else para
        if cur: segs.append(cur)
        return segs

    # ================================================================
    # v2.3.4 D9: 单段提取 — JSON Lines 输出 + prefix 续写支持
    # ================================================================
    def _extract_single(self, content, filename, prompt, ctype, relay_prefix=""):
        """调用R1/V3提取单段内容,返回统一dict契约。

        v2.3.4 改动:
        - 改用 self.client.chat_with_jsonl()(JSON Lines 输出)
        - 返回 dict 增加 prefix_for_continuation(供 prefix 续写) + meta(_meta 元数据)
        - 兼容字段保留:kps / truncated / last_excerpt / raw_parsed / cost

        返回:
        {
            "kps": [...],                    # 已成功解析的知识点列表
            "truncated": bool,               # finish_reason=length
            "last_excerpt": str,             # 最后一条 kp 的 excerpt(F057 兜底用)
            "raw_parsed": bool,              # 是否有任意行解析成功
            "cost": float,                   # 本次调用费用
            "prefix_for_continuation": str,  # v2.3.4 新增:prefix 续写起点
            "meta": dict or None,            # v2.3.4 新增:_meta 元数据(file_summary/extraction_notes)
            "system_prompt": str,            # v2.3.4 新增:供续写时复用
            "user_prompt": str,              # v2.3.4 新增:供续写时复用
        }
        """
        up = prompt["user_prompt_template"].format(filename=filename, full_content=content)
        if relay_prefix:
            up = relay_prefix + "\n\n" + up
        sp = prompt["system_prompt"]

        ai = self.client.chat_with_jsonl(
            sp, up, temperature=0.2,
            call_type=f"extract_{ctype}", model_override=self.extraction_model)

        kp_objects = ai.get("kp_objects", []) or []
        meta_object = ai.get("meta_object", None)
        was_truncated = ai.get("was_truncated", False)
        cost = ai.get("estimated_cost", 0)
        prefix_for_continuation = ai.get("prefix_for_continuation", "") or ""
        cost_info = f"(花费约{cost:.4f}元)"

        # 解析失败(0 行解析成功 + 0 _meta)
        raw_parsed = bool(kp_objects or meta_object)
        if not raw_parsed:
            err = ai.get("json_parse_error", "JSONL 0 行解析成功")
            if was_truncated:
                print(f"     ! 输出被截断且无完整知识点可解析 {cost_info}")
            else:
                print(f"     ! JSON Lines 解析失败: {err} {cost_info}")
            return {"kps": [], "truncated": was_truncated, "last_excerpt": "",
                    "raw_parsed": False, "cost": cost,
                    "prefix_for_continuation": prefix_for_continuation,
                    "meta": meta_object,
                    "system_prompt": sp, "user_prompt": up}

        # 解析成功
        kps = kp_objects
        if meta_object:
            notes = meta_object.get("extraction_notes", "")
            if notes:
                print(f"     AI说明: {notes[:80]}")

        # 定位 last_excerpt(F057 兜底链路用)
        last_excerpt = ""
        if kps:
            try:
                last_excerpt = kps[-1].get("original_excerpt", "") or ""
            except Exception:
                last_excerpt = ""

        if was_truncated:
            print(f"     [注意] R1输出被截断,已解析{len(kps)}条完整知识点 {cost_info}")
        else:
            print(f"     本段提取{len(kps)}个知识点 {cost_info}")

        return {"kps": kps, "truncated": was_truncated,
                "last_excerpt": last_excerpt, "raw_parsed": True, "cost": cost,
                "prefix_for_continuation": prefix_for_continuation,
                "meta": meta_object,
                "system_prompt": sp, "user_prompt": up}

    def _extract_with_auto_split(self, content, filename, prompt, ctype,
                                 current_max_len=None, relay_prefix="", file_id=None):
        """单段提取的外层调度。

        v2.3.4-hotfix1 五级降级链(段内同步,不留事后批量重跑):
          L0: chat_with_jsonl (R1) 主提取 → 截断/0 partial/解析失败 ↓
          L1: chat_jsonl_via_siliconflow (Kimi-K2.6) 整段重提 → 仍失败 ↓
          L2: chat_jsonl_via_siliconflow (R1 跨厂商镜像) 整段重提 → 仍失败 ↓
          L3: F057 老逻辑(若 partial_kps>=1) ↓
          L4: 保留已提取 + 控制台 ❌

        每条 kp 在生成时打 _extracted_by_model 标记,入库时透传 extracted_by_model 字段。
        """
        if current_max_len is None:
            current_max_len = self.segment_max_len

        # ============= L0: R1 主提取 =============
        result = self._extract_single(content, filename, prompt, ctype, relay_prefix)
        kps = result["kps"]
        # L0 成功的 kp 打标 r1
        for k in kps:
            if isinstance(k, dict):
                k["_extracted_by_model"] = "r1"

        # v2.3.4-hotfix3 BUG#2A 修复:未截断时一律返回,0 条 kp 也是合理结果
        # ─────────────────────────────────────────────────────────────
        # 修复前(BUG):if not result["truncated"] and kps: return kps
        #   → 0 kp + 未截断 落入降级链,触发不必要的 L1/L2 救援
        #   → 老唐 0428 实测第 1 段背景段 151 字本就无知识点,被错误启动救援链
        # 修复后:
        #   - 未截断 + 解析成功(raw_parsed=True):0 条也是 R1 合理判定 → return
        #   - 未截断 + 解析失败(raw_parsed=False):格式异常 → 进降级链
        #   - 已截断:任何 kp 数都进降级链(原逻辑)
        # ─────────────────────────────────────────────────────────────
        if not result["truncated"]:
            if kps:
                return kps
            if result.get("raw_parsed"):
                # R1 已成功解析 + 0 条 kp = 合理判定(背景段/章节标题/空白页)
                # 不进降级链,直接返回空(不浪费时间和 token)
                print(f"     本段无可提取知识点(R1 合理判定,跳过救援链)")
                return []
            # 未截断 + 0 条 + 解析失败:7 步保险也救不回 → 真正的格式异常,进降级链

        # 已截断 或 (未截断 + 0 条 + 解析失败) → 进入多模型整段重提
        truncated = result.get("truncated", False)
        if truncated:
            self._truncation_stats["truncations"] += 1
            if file_id:
                try:
                    self.db.increment_truncation_count(file_id)
                except Exception:
                    pass

        # 输出原因到控制台
        if truncated and not kps:
            print(f"     [L0 失败] R1 输出截断且 0 完整 kp,启动 L1 Kimi 整段重提")
        elif truncated and kps:
            print(f"     [L0 部分] R1 截断但已解析{len(kps)}条,启动 L1 Kimi 整段重提补全")
        else:
            # 未截断 + 0 条 + 解析失败(走到这里说明 7 步保险也救不回)
            print(f"     [L0 失败] R1 输出格式异常 + 7 步降级未救回,启动 L1 Kimi 整段重提")

        # ============= L1: Kimi-K2.6 整段重提 =============
        l1_kps = self._retry_via_siliconflow(
            content, filename, prompt, ctype, relay_prefix, file_id,
            model_id=self.client.SILICONFLOW_TEXT_MODEL_L1,
            model_tag="kimi", layer_label="L1")

        if l1_kps is not None:  # L1 成功(有 kp 返回,即使 0 条但解析成功也算)
            self._truncation_stats["kimi_recoveries"] += 1
            for k in l1_kps:
                if isinstance(k, dict):
                    k["_extracted_by_model"] = "kimi"
            # L1 是整段重提,理论上覆盖 L0 全部内容,但保留 L0 已成功 kp 防止漏掉
            merged = self._dedupe_kps_by_excerpt(kps + l1_kps)
            print(f"     [L1 Kimi 救回] L0:{len(kps)}条 + L1:{len(l1_kps)}条 = 去重后{len(merged)}条")
            return merged

        # ============= L2: R1 跨厂商镜像整段重提 =============
        print(f"     [L1 失败] Kimi 整段重提失败,启动 L2 R1 镜像")
        l2_kps = self._retry_via_siliconflow(
            content, filename, prompt, ctype, relay_prefix, file_id,
            model_id=self.client.SILICONFLOW_TEXT_MODEL_L2,
            model_tag="r1_mirror", layer_label="L2")

        if l2_kps is not None:
            self._truncation_stats["r1_mirror_recoveries"] += 1
            for k in l2_kps:
                if isinstance(k, dict):
                    k["_extracted_by_model"] = "r1_mirror"
            merged = self._dedupe_kps_by_excerpt(kps + l2_kps)
            print(f"     [L2 R1镜像 救回] L0:{len(kps)}条 + L2:{len(l2_kps)}条 = 去重后{len(merged)}条")
            return merged

        # ============= L3: F057 老逻辑兜底(仅当 partial_kps>=1) =============
        print(f"     [L2 失败] R1 镜像也失败,启动 L3 F057 兜底")
        if not kps:
            # 0 partial,F057 没有 last_excerpt 可定位,跳过
            self._truncation_stats["total_failures"] += 1
            print(f"     ❌ [L4 全失败] L0/L1/L2 均失败且 partial=0,F057 无锚点跳过")
            self._safe_log_event(
                "extract_full_fail", "extractor", "error",
                file_id=file_id,
                payload={"filename": filename,
                         "reason": "L0/L1/L2 all failed, partial_kps=0",
                         "last_attempted": "siliconflow_r1_mirror"})
            return []

        self._truncation_stats["f057_fallbacks"] += 1
        next_max = current_max_len // 2
        recovered = self._recover_from_truncation(
            original_content=content,
            partial_kps=kps,
            prompt=prompt,
            ctype=ctype,
            next_max_len=next_max,
            file_id=file_id,
            base_relay_prefix=relay_prefix,
            attempt=1,
            filename=filename,
            last_excerpt=result["last_excerpt"]
        )
        # F057 救回的 kp 打标
        for k in recovered:
            if isinstance(k, dict):
                k["_extracted_by_model"] = "f057_recovery"

        # 合并并按 (title, excerpt前100) 去重
        merged = self._dedupe_kps_by_excerpt(kps + recovered)
        if len(merged) < len(kps) + len(recovered):
            dup_n = len(kps) + len(recovered) - len(merged)
            print(f"     [F057 合并] 去重{dup_n}条疑似重复,最终{len(merged)}条")
        if not recovered:
            self._truncation_stats["lost_segments"] += 1
        return merged

    # ================================================================
    # v2.3.4-hotfix1 H1: L1/L2 硅基流动整段重提
    # ================================================================
    def _retry_via_siliconflow(self, content, filename, prompt, ctype, relay_prefix,
                               file_id, model_id, model_tag, layer_label):
        """走硅基流动文本模型整段重提(L1 Kimi / L2 R1 镜像 共用)。

        参数:
          model_id    硅基流动模型 ID(如 Pro/moonshotai/Kimi-K2.6)
          model_tag   失败/成功事件日志中的标记(kimi / r1_mirror)
          layer_label 控制台输出标签(L1 / L2)

        返回:
          List[dict] 提取到的 kp 列表(可能为空 [],也算成功 — 表明该段确实没 kp)
          None       接口异常 / 0 partial 且解析失败 — 进入下一层
        """
        # 复用同一套 prompt 包(prompt 100% 复用,立规则 H3)
        up = prompt["user_prompt_template"].format(filename=filename, full_content=content)
        if relay_prefix:
            up = relay_prefix + "\n\n" + up
        sp = prompt["system_prompt"]

        try:
            ai = self.client.chat_jsonl_via_siliconflow(
                sp, up,
                model=model_id,
                temperature=0.2, max_tokens=8192,
                call_type=f"extract_{model_tag}_{filename[:30]}"
            )
        except Exception as e:
            err_msg = f"{type(e).__name__}: {str(e)[:200]}"
            print(f"     [{layer_label} 异常] {err_msg}")
            self._safe_log_event(
                "siliconflow_retry", "extractor", "warning",
                file_id=file_id,
                payload={"layer": layer_label, "model": model_id, "model_tag": model_tag,
                         "reason": "exception", "error": err_msg, "filename": filename})
            return None

        kp_objects = ai.get("kp_objects", []) or []
        was_truncated = ai.get("was_truncated", False)
        cost = ai.get("estimated_cost", 0)
        self._truncation_stats["total_cost"] += cost

        # 判断结果:
        # 1. 0 kp + 解析失败 → 视为失败,进入下一层
        # 2. 0 kp + 解析成功(_meta 存在或全段无 kp 真实情况) → 视为成功,返回 []
        # 3. >0 kp → 成功
        meta_object = ai.get("meta_object", None)
        raw_parsed = bool(kp_objects or meta_object)

        if not raw_parsed:
            # 解析失败,认为本层不可用
            print(f"     [{layer_label} 失败] {model_id} 解析 0 行 ({cost:.4f}元)")
            self._safe_log_event(
                "siliconflow_retry", "extractor", "warning",
                file_id=file_id,
                payload={"layer": layer_label, "model": model_id, "model_tag": model_tag,
                         "reason": "parse_failed", "was_truncated": was_truncated,
                         "cost": cost, "filename": filename})
            return None

        # 解析成功(包括 0 kp 但有 _meta 的合理情况)
        trunc_note = "(截断但已解析)" if was_truncated else "(完整)"
        print(f"     [{layer_label} 成功] {model_id} 提取{len(kp_objects)}条{trunc_note} ({cost:.4f}元)")
        self._safe_log_event(
            "siliconflow_retry", "extractor", "info",
            file_id=file_id,
            payload={"layer": layer_label, "model": model_id, "model_tag": model_tag,
                     "kp_count": len(kp_objects), "was_truncated": was_truncated,
                     "cost": cost, "filename": filename})
        return kp_objects

    # ================================================================
    # v2.3.4 D10 L0/L1: Prefix 续写补救核心 [DEPRECATED in v2.3.4-hotfix1]
    # ----------------------------------------------------------------
    # ⚠️ 本方法在 v2.3.4-hotfix1 起不再被 _extract_with_auto_split 调用。
    # 废弃理由:本方法的设计前提是"R1 截断时已生成 ≥1 条 partial kp,prefix 有内容可续";
    # 老唐 2026-04-28 实测发现 R1 思考爆 token 时 partial==0,prefix 空,本方法 386 行直接降级。
    # 替代方案:_retry_via_siliconflow 多思考型模型整段重提(L1 Kimi-K2.6 / L2 R1 镜像)。
    # 代码完整保留作未来"prefix 续写适用"场景重启可能。
    # ================================================================
    def _recover_via_prefix(self, init_result, file_id, filename, max_attempts=2):
        """L0/L1 prefix 续写。

        参数 init_result:_extract_single 返回的 dict(包含 prefix_for_continuation/system_prompt/user_prompt)
        返回:
          List[dict] 续写新增的 kp(成功);
          None(续写失败,需走 L2 F057 兜底)
        """
        prefix_content = init_result.get("prefix_for_continuation", "") or ""
        sp = init_result.get("system_prompt", "") or ""
        up = init_result.get("user_prompt", "") or ""

        if not prefix_content or not sp or not up:
            print(f"     [Prefix续写跳过] prefix/system/user_prompt 缺失,直接降级")
            return None

        all_recovered = []
        current_prefix = prefix_content

        for attempt in range(1, max_attempts + 1):
            print(f"     [L{attempt-1} Prefix续写] 第{attempt}次,prefix 末尾长度 {len(current_prefix)} 字符...")

            try:
                rc = self.client.chat_continue_with_prefix(
                    system_prompt=sp,
                    user_prompt=up,
                    prefix_content=current_prefix,
                    max_tokens=8192,
                    call_type=f"extract_continue_{filename[:30]}",
                    # D8 续写默认走 V3,内部已处理
                )
            except Exception as e:
                print(f"     [Prefix续写异常] {type(e).__name__}: {e}")
                self._safe_log_event(
                    "prefix_recovery", "extractor", "warning",
                    file_id=file_id,
                    payload={"attempt": attempt, "reason": "exception",
                             "error": f"{type(e).__name__}: {str(e)[:200]}",
                             "filename": filename})
                return None

            new_content = rc.get("content", "") or ""
            new_truncated = rc.get("was_truncated", False)
            new_cost = rc.get("estimated_cost", 0)
            self._truncation_stats["total_cost"] += new_cost

            # 把"prefix + 续写内容"合并后整体走 jsonl 解析,
            # 把已生成 + 新生成统一逐行 try parse
            full_text = current_prefix + new_content
            new_kps, new_meta, new_prefix_for_next, broken_line = self._parse_jsonl_text(full_text)

            # 计算"新增"的 kp = 整体解析的 kp 减去之前已有的 kp
            # 通过 (title, excerpt前100) 比对
            already_seen_keys = set()
            for k in init_result.get("kps", []) + all_recovered:
                if not isinstance(k, dict):
                    continue
                t = (k.get("title", "") or "").strip()
                e = (k.get("original_excerpt", "") or "").strip()[:100]
                already_seen_keys.add((t, e))

            this_round_new = []
            for k in new_kps:
                t = (k.get("title", "") or "").strip()
                e = (k.get("original_excerpt", "") or "").strip()[:100]
                key = (t, e)
                if key in already_seen_keys:
                    continue
                already_seen_keys.add(key)
                this_round_new.append(k)

            all_recovered.extend(this_round_new)
            print(f"     [Prefix续写成功 第{attempt}次] 新增{len(this_round_new)}条 ({new_cost:.4f}元)")
            self._safe_log_event(
                "prefix_recovery", "extractor", "info",
                file_id=file_id,
                payload={"attempt": attempt, "new_count": len(this_round_new),
                         "still_truncated": new_truncated, "cost": new_cost,
                         "filename": filename})

            # 续写未截断 → 完成
            if not new_truncated:
                self._truncation_stats["prefix_recoveries"] += 1
                return all_recovered

            # 仍截断且还有重试次数 → 用合并后文本作为下次 prefix
            if attempt < max_attempts:
                current_prefix = full_text
                continue

        # 用完 max_attempts 仍截断
        # 已有续写成果就回传,让上层合并;若 0 条则视为续写失败
        if all_recovered:
            self._truncation_stats["prefix_recoveries"] += 1
            print(f"     [Prefix续写部分成功] 已尝试{max_attempts}次,仍截断,保留{len(all_recovered)}条")
            return all_recovered
        return None

    def _parse_jsonl_text(self, text):
        """对一段 JSON Lines 文本逐行 try parse。
        返回 (kp_list, meta_dict, prefix_for_continuation_str, last_broken_line)
        与 deepseek_client.chat_with_jsonl 内部解析逻辑一致。
        """
        cleaned = (text or "").strip()
        cb = re.search(r'```(?:json)?\s*([\s\S]*?)```', cleaned)
        if cb:
            cleaned = cb.group(1).strip()

        kps = []
        meta = None
        completed_text_parts = []
        last_broken_line = ""
        for raw_line in cleaned.split("\n"):
            line = raw_line.strip()
            if not line:
                continue
            try:
                obj = json.loads(line)
                if isinstance(obj, dict):
                    if obj.get("_meta") is True:
                        meta = obj
                    else:
                        kps.append(obj)
                    completed_text_parts.append(raw_line)
                else:
                    completed_text_parts.append(raw_line)
            except json.JSONDecodeError:
                last_broken_line = raw_line
                break

        prefix_for_next = ""
        if completed_text_parts:
            prefix_for_next = "\n".join(completed_text_parts) + "\n"
        if last_broken_line:
            prefix_for_next += last_broken_line
        return kps, meta, prefix_for_next, last_broken_line

    # ================================================================
    # v2.2.3 F057: 截断补救核心
    # ================================================================
    def _locate_cut_boundary(self, content, last_excerpt):
        """在原段中定位 last_excerpt 的末尾位置，返回切分点字符下标；定位失败返回 None。
        三级定位：完整匹配 → 首30字模糊 → 尾30字反向。
        """
        if not last_excerpt or not content:
            return None
        excerpt = last_excerpt.strip()
        if not excerpt:
            return None

        # L1: 完整匹配
        pos = content.find(excerpt)
        if pos >= 0:
            return pos + len(excerpt)

        # L2: 首30字模糊（AI偶尔会对excerpt做微小改写）
        if len(excerpt) >= 30:
            head = excerpt[:30]
            pos = content.find(head)
            if pos >= 0:
                return pos + min(len(excerpt), 300)

        # L3: 尾30字反向
        if len(excerpt) >= 30:
            tail = excerpt[-30:]
            pos = content.rfind(tail)
            if pos >= 0:
                return pos + len(tail)

        return None

    def _dedupe_kps_by_excerpt(self, kps):
        """按 (title, original_excerpt[:100]) 去重，保顺序。"""
        seen = set()
        out = []
        for kp in kps:
            if not isinstance(kp, dict):
                continue
            title = (kp.get("title", "") or "").strip()
            excerpt = (kp.get("original_excerpt", "") or "").strip()[:100]
            key = (title, excerpt)
            if key in seen:
                continue
            seen.add(key)
            out.append(kp)
        return out

    def _recover_from_truncation(self, original_content, partial_kps, prompt, ctype,
                                 next_max_len, file_id, base_relay_prefix,
                                 attempt, filename, last_excerpt):
        """F057 截断补救核心：定位→取尾段→重提；支持嵌套降级，最多3次。"""
        # 降级到头
        if attempt > self.TRUNCATION_MAX_ATTEMPTS or next_max_len < self.TRUNCATION_MIN_SEG_LEN:
            self._safe_log_event(
                "truncation_recovery", "extractor", "warning",
                file_id=file_id,
                payload={
                    "reason": "max_attempts_reached",
                    "total_attempts": attempt - 1,
                    "final_max_len": next_max_len,
                    "final_partial_count": len(partial_kps),
                    "filename": filename
                })
            print(f"     [F057 补救终止] 已降级{attempt-1}次仍截断,保留已提取{len(partial_kps)}条")
            return []

        # 定位切分点
        cut_pos = self._locate_cut_boundary(original_content, last_excerpt)
        if cut_pos is None:
            self._safe_log_event(
                "truncation_recovery", "extractor", "warning",
                file_id=file_id,
                payload={
                    "reason": "locate_boundary_failed",
                    "attempt": attempt,
                    "partial_kps_count": len(partial_kps),
                    "last_excerpt_preview": (last_excerpt or "")[:80],
                    "filename": filename
                })
            print(f"     [F057 补救放弃] 无法定位切分点,保留已提取{len(partial_kps)}条")
            return []

        tail_content = original_content[cut_pos:].strip()
        if len(tail_content) < self.TRUNCATION_MIN_TAIL_LEN:
            print(f"     [F057 补救跳过] 尾段过短({len(tail_content)}字),放弃补救")
            return []

        # 到这里确定启动补救 → 计数 +1
        if file_id:
            try:
                self.db.increment_truncation_count(file_id)
            except Exception:
                pass
        self._safe_log_event(
            "truncation_recovery", "extractor", "info",
            file_id=file_id,
            payload={
                "attempt": attempt,
                "next_max_len": next_max_len,
                "tail_len": len(tail_content),
                "cut_pos": cut_pos,
                "partial_kps_count": len(partial_kps),
                "filename": filename
            })
        print(f"     [F057 补救 第{attempt}次] 从{cut_pos}字后取尾段({len(tail_content)}字),新段长{next_max_len}...")

        # 构造补救 relay：在原 relay 基础上附加已提取标题
        titles_preview = "\n".join(
            f"  {i+1}. {(k.get('title','') or '')[:60]}"
            for i, k in enumerate(partial_kps[:20])
        ) or "  (无)"
        recovery_relay = (base_relay_prefix or "") + (
            "\n\n=== 截断补救上下文 ===\n"
            f"本段因R1输出截断已启动补救,前序已提取 {len(partial_kps)} 条知识点:\n"
            f"{titles_preview}\n"
            "请从以下内容继续提取,不要重复已提取过的知识点。\n"
        )

        # 按 next_max_len 拆尾段（可能分成 1-N 个子段）
        sub_segs = self._paragraph_segment(tail_content, max_len=next_max_len)
        all_recovered = []
        for j, sub in enumerate(sub_segs, 1):
            label = f"{filename}(补救{attempt}-{j}/{len(sub_segs)})"
            sub_result = self._extract_single(sub, label, prompt, ctype, recovery_relay)
            all_recovered.extend(sub_result["kps"])

            # 子段再次截断 → 递归深度降级
            if sub_result["truncated"] and sub_result["last_excerpt"]:
                deeper = self._recover_from_truncation(
                    original_content=sub,
                    partial_kps=sub_result["kps"],
                    prompt=prompt,
                    ctype=ctype,
                    next_max_len=next_max_len // 2,
                    file_id=file_id,
                    base_relay_prefix=recovery_relay,
                    attempt=attempt + 1,
                    filename=label,
                    last_excerpt=sub_result["last_excerpt"]
                )
                all_recovered.extend(deeper)
            elif sub_result["truncated"] and not sub_result["last_excerpt"]:
                # 截断但连一条完整kp都没解析出来：无锚点可定位，放弃深降
                self._safe_log_event(
                    "truncation_recovery", "extractor", "warning",
                    file_id=file_id,
                    payload={
                        "reason": "no_anchor_in_recovered_sub",
                        "attempt": attempt + 1,
                        "filename": label
                    })

        return all_recovered

    def _safe_log_event(self, event_type, module, severity, file_id=None, kp_id=None, payload=None):
        """包一层 try/except,防止日志失败污染主流程"""
        try:
            self.db.log_operation_event(
                event_type, module, severity,
                file_id=file_id, kp_id=kp_id, payload=payload or {}
            )
        except Exception as e:
            print(f"     [事件日志失败] {event_type}: {e}")

    def _move_to_completed(self, fp, fn):
        try:
            dest = self.completed / fn; c = 1
            while dest.exists():
                stem, ext = Path(fn).stem, Path(fn).suffix
                dest = self.completed / f"{stem}_{c}{ext}"; c += 1
            if os.path.exists(fp):
                shutil.copy2(fp, str(dest))
                if str(self.processing) in str(fp): os.remove(fp)
                print(f"     文件已归档至: completed/{dest.name}")
            # 同时移动.md伴侣文件
            md_src = Path(fp).with_suffix(".md")
            if md_src.exists() and str(self.processing) in str(md_src):
                md_dest = dest.with_suffix(".md")
                shutil.copy2(str(md_src), str(md_dest))
                os.remove(str(md_src))
        except Exception as e: print(f"     ! 文件归档失败: {e}")

    def _move_to_failed(self, fp, fn):
        try:
            dest = self.failed_dir / fn; c = 1
            while dest.exists():
                stem, ext = Path(fn).stem, Path(fn).suffix
                dest = self.failed_dir / f"{stem}_{c}{ext}"; c += 1
            if os.path.exists(fp):
                shutil.copy2(fp, str(dest))
                if str(self.processing) in str(fp): os.remove(fp)
                print(f"     文件已隔离至: failed/{dest.name}")
            # 同时移动.md伴侣文件
            md_src = Path(fp).with_suffix(".md")
            if md_src.exists() and str(self.processing) in str(md_src):
                os.remove(str(md_src))
        except Exception as e: print(f"     ! 文件隔离失败: {e}")

    # ================================================================
    # v2.0.0 新增：标签数据校验
    # ================================================================
    def _sanitize_tags(self, kp):
        """校验并清理AI返回的三层标签数据，确保格式正确、值合法。"""
        # --- 第一层：分类标签 ---
        raw_cat_tags = kp.get("suggested_category_tags", [])
        if not isinstance(raw_cat_tags, list):
            raw_cat_tags = []
        # 只保留在合法清单中的标签名
        clean_cat_tags = [t for t in raw_cat_tags if isinstance(t, str) and t in self.VALID_LAYER1_NAMES]
        if len(clean_cat_tags) < len(raw_cat_tags):
            removed = set(raw_cat_tags) - set(clean_cat_tags)
            if removed:
                print(f"     [标签校验] 过滤了{len(removed)}个不在清单中的分类标签: {', '.join(list(removed)[:3])}")

        # --- 第二层：属性标签 ---
        raw_attr_tags = kp.get("suggested_attribute_tags", {})
        if not isinstance(raw_attr_tags, dict):
            raw_attr_tags = {}
        clean_attr_tags = {}
        for dim_key, dim_val in raw_attr_tags.items():
            if isinstance(dim_key, str) and dim_val:
                if isinstance(dim_val, list):
                    dim_val = "、".join(str(v) for v in dim_val)
                clean_attr_tags[dim_key] = str(dim_val)

        # --- 第三层：关键词 ---
        raw_keywords = kp.get("suggested_keywords", [])
        if not isinstance(raw_keywords, list):
            raw_keywords = []
        seen = set()
        clean_keywords = []
        for kw in raw_keywords:
            if isinstance(kw, str) and 2 <= len(kw) <= 20 and kw not in seen:
                seen.add(kw)
                clean_keywords.append(kw)

        # --- 元数据 ---
        readiness = kp.get("suggested_readiness", "draft")
        if readiness not in self.VALID_READINESS:
            readiness = "draft"
        authority = kp.get("suggested_authority", "firsthand")
        if authority not in self.VALID_AUTHORITY:
            authority = "firsthand"

        return {
            "category_tags": clean_cat_tags,
            "attribute_tags": clean_attr_tags,
            "keywords": clean_keywords,
            "readiness": readiness,
            "authority": authority,
        }

    # ================================================================
    # v2.1.0-c 新增：V3预分析
    # ================================================================
    def _pre_analyze(self, content, filename):
        """V3预分析：质量评估+分类建议+结构识别。失败时暂停让用户选择。"""
        preview = content[:2000]
        char_count = len(content)
        prompt = PRE_ANALYSIS_PROMPT
        up = prompt["user_prompt_template"].format(
            filename=filename, char_count=char_count, content_preview=preview)

        for attempt in range(1, 4):
            try:
                ai = self.client.chat_with_json(
                    prompt["system_prompt"], up, temperature=0.2,
                    call_type="pre_analysis", model_override="deepseek-chat")
                parsed = ai.get("parsed_json")
                if parsed and isinstance(parsed, dict):
                    cost = ai.get("estimated_cost", 0)
                    print(f"     预分析完成(花费{cost:.4f}元)")
                    return parsed
                print(f"     预分析返回格式异常(第{attempt}次)")
            except CostLimitExceeded:
                raise
            except Exception as e:
                print(f"     预分析出错(第{attempt}次): {e}")

        # 3次失败，暂停让用户选择
        print(f"\n     [预分析未能完成] 可能是网络问题")
        if self._headless:
            print(f"     [headless] 自动跳过预分析，使用文件名推断分类")
            return None
        while True:
            choice = input("     [1]重试 [2]跳过预分析直接提取 [3]跳过该文件: ").strip()
            if choice == "1":
                return self._pre_analyze(content, filename)  # 递归重试
            elif choice == "2":
                print("     跳过预分析，使用文件名推断分类")
                return None
            elif choice == "3":
                return "SKIP_FILE"
            else:
                print("     请输入 1/2/3")

    # ================================================================
    # v2.1.0-c 新增：V3结构摘要
    # ================================================================
    def _get_structure_summary(self, content, filename):
        """V3分析文件结构，返回分段建议。失败返回None。"""
        char_count = len(content)
        prompt = SEGMENT_SUMMARY_PROMPT
        up = prompt["user_prompt_template"].format(
            filename=filename, char_count=char_count, full_content=content[:8000])
        try:
            ai = self.client.chat_with_json(
                prompt["system_prompt"], up, temperature=0.2,
                call_type="segment_summary", model_override="deepseek-chat")
            parsed = ai.get("parsed_json")
            if parsed and isinstance(parsed, dict):
                cost = ai.get("estimated_cost", 0)
                print(f"     结构摘要完成(花费{cost:.4f}元)")
                return parsed
        except CostLimitExceeded:
            raise
        except Exception as e:
            print(f"     结构摘要失败: {e}")
        return None

    # ================================================================
    # v2.1.0-c 新增：三级智能分段
    # ================================================================
    def _smart_segment(self, content, pre_result, filename):
        """三级分段策略，绝不回退到机械切割。
        返回 (segments_list, file_structure_text)"""
        if len(content) <= self.segment_max_len:
            return [content], ""

        # v2.1.0-d: 过大段阈值动态计算，跟随模型设置
        oversized_threshold = int(self.segment_max_len * 1.5)

        # --- 第一级：V3结构摘要分段 ---
        structure_result = self._get_structure_summary(content, filename)
        if structure_result:
            suggested_segs = structure_result.get("suggested_segments", [])
            if suggested_segs and len(suggested_segs) >= 2:
                segs = self._apply_v3_segments(content, suggested_segs, oversized_threshold)
                if segs:
                    # 构建结构摘要文本
                    doc_structure = structure_result.get("document_structure", [])
                    struct_text = self._format_structure_text(doc_structure)
                    notes = structure_result.get("notes", "")
                    if notes:
                        print(f"     分段提示: {notes[:60]}")
                    # 保存分段方案
                    try:
                        self.db.update_source_file(
                            self._current_file_id,
                            segment_plan=json.dumps(structure_result, ensure_ascii=False))
                    except:
                        pass
                    return segs, struct_text
            print(f"     V3分段建议不可用,切换到本地规则分段")
        else:
            print(f"     V3结构摘要不可用,切换到本地规则分段")

        # --- 第二级：本地规则分段 ---
        segs = self._local_rule_segment(content, oversized_threshold)
        if segs and len(segs) >= 2:
            print(f"     使用本地规则分段(按章节标记)")
            # 从预分析中提取结构信息
            struct_text = ""
            if pre_result and isinstance(pre_result, dict):
                overview = pre_result.get("content_overview", "")
                struct_text = overview
            return segs, struct_text

        # --- 第三级：段落边界分段 ---
        print(f"     使用段落边界分段")
        segs = self._paragraph_segment(content)
        struct_text = ""
        if pre_result and isinstance(pre_result, dict):
            struct_text = pre_result.get("content_overview", "")
        return segs, struct_text

    def _apply_v3_segments(self, content, suggested_segs, oversized_threshold=None):
        """根据V3建议的分段方案切割内容"""
        # v2.1.0-d: 使用传入的动态阈值
        if oversized_threshold is None:
            oversized_threshold = int(self.segment_max_len * 1.5)

        segments = []
        content_lower = content
        for seg_info in suggested_segs:
            start_kw = seg_info.get("start_keyword", "")
            if not start_kw:
                continue
            # 找到起始位置
            pos = content_lower.find(start_kw)
            if pos < 0:
                # 尝试模糊匹配（取前10个字）
                short_kw = start_kw[:10]
                pos = content_lower.find(short_kw)
            if pos >= 0:
                segments.append(pos)

        if len(segments) < 2:
            return None

        # 按位置排序并切割
        segments.sort()
        result = []
        for i in range(len(segments)):
            start = segments[i]
            end = segments[i + 1] if i + 1 < len(segments) else len(content)
            seg_text = content[start:end].strip()
            if seg_text:
                result.append(seg_text)

        # 如果第一段之前有内容，加到第一段前面
        if segments[0] > 0:
            prefix = content[:segments[0]].strip()
            if prefix and result:
                result[0] = prefix + "\n\n" + result[0]

        # v2.1.0-d: 过大段拆分使用动态阈值
        final = []
        for seg in result:
            if len(seg) > oversized_threshold:
                sub_segs = self._paragraph_segment(seg, max_len=self.segment_max_len)
                final.extend(sub_segs)
            else:
                final.append(seg)

        return final if len(final) >= 1 else None

    def _local_rule_segment(self, content, oversized_threshold=None):
        """按章节标记分段：识别中文文档常见的结构标记"""
        # v2.1.0-d: 使用动态阈值
        if oversized_threshold is None:
            oversized_threshold = int(self.segment_max_len * 1.5)

        # 常见章节标记模式
        patterns = [
            r'\n(第[一二三四五六七八九十百]+[章编篇])',    # 第一章、第一编
            r'\n(第[一二三四五六七八九十\d]+条[\s\u3000])',  # 第一条 （政策文件）
            r'\n([一二三四五六七八九十]+、)',              # 一、二、三、
            r'\n(附[则件录表]\s)',                        # 附则、附件
        ]

        # 尝试每种模式，选择最佳（切出2-15段的）
        for pattern in patterns:
            positions = []
            for m in re.finditer(pattern, content):
                positions.append(m.start())

            if len(positions) >= 2:
                # 切割
                segments = []
                for i in range(len(positions)):
                    start = positions[i]
                    end = positions[i + 1] if i + 1 < len(positions) else len(content)
                    seg = content[start:end].strip()
                    if seg:
                        segments.append(seg)

                # 第一段之前的内容加到第一段
                if positions[0] > 0:
                    prefix = content[:positions[0]].strip()
                    if prefix and segments:
                        segments[0] = prefix + "\n\n" + segments[0]

                # 合并过小的段（小于500字的与后一段合并）
                merged = []
                buf = ""
                for seg in segments:
                    if buf:
                        buf = buf + "\n\n" + seg
                    else:
                        buf = seg
                    if len(buf) >= 500:
                        merged.append(buf)
                        buf = ""
                if buf:
                    if merged:
                        merged[-1] = merged[-1] + "\n\n" + buf
                    else:
                        merged.append(buf)

                # v2.1.0-d: 拆分过大的段（使用动态阈值）
                final = []
                for seg in merged:
                    if len(seg) > oversized_threshold:
                        sub = self._paragraph_segment(seg, max_len=self.segment_max_len)
                        final.extend(sub)
                    else:
                        final.append(seg)

                if 2 <= len(final) <= 20:
                    return final

        return None  # 没有找到合适的章节标记

    def _paragraph_segment(self, content, max_len=None):
        """按段落边界分段，保证不在段落中间切断"""
        if max_len is None:
            max_len = self.segment_max_len
        if len(content) <= max_len:
            return [content]
        paragraphs = content.split("\n\n")
        segments = []
        current = ""
        for para in paragraphs:
            # 如果当前段加上新段落会超限，且当前段非空，先保存当前段
            if len(current) + len(para) + 2 > max_len and current:
                segments.append(current.strip())
                current = para
            else:
                current = current + "\n\n" + para if current else para
        if current.strip():
            segments.append(current.strip())
        # 如果只产生了一段（整个内容没有段落分隔），按换行分
        if len(segments) <= 1 and len(content) > max_len:
            lines = content.split("\n")
            segments = []
            current = ""
            for line in lines:
                if len(current) + len(line) + 1 > max_len and current:
                    segments.append(current.strip())
                    current = line
                else:
                    current = current + "\n" + line if current else line
            if current.strip():
                segments.append(current.strip())
        return segments if segments else [content]

    def _format_structure_text(self, doc_structure):
        """将V3返回的文档结构格式化为文本"""
        if not doc_structure:
            return ""
        lines = []
        for item in doc_structure:
            level = item.get("level", 1)
            title = item.get("title", "")
            indent = "  " * (level - 1)
            lines.append(f"{indent}- {title}")
        return "\n".join(lines)

    # ================================================================
    # v2.1.0-c 新增：上下文接力信息构建
    # ================================================================
    def _build_context_relay(self, seg_idx, total_segs, file_structure, prev_kps, source_nature=""):
        """构建分段提取的上下文接力信息。
        v2.2.3: 单段文件也传递来源属性信息。"""
        # v2.2.3: 来源属性描述
        SOURCE_NATURE_DESC = {
            "official_policy": "政府发文/法规/通知（应分到政策库）",
            "research_report": "第三方调研分析/行业研究（应分到案例库或经验库/反常识洞察，不是操盘经验）",
            "personal_experience": "作者本人操盘记录/工作笔记（应分到经验库）",
            "project_case": "具体项目案例报告（应分到案例库）",
            "tool_template": "模板/合同/清单（应分到工具库）",
            "data_material": "数据表/统计资料（应分到数据库）",
        }
        nature_text = SOURCE_NATURE_DESC.get(source_nature, "(未识别)") if source_nature else "(未识别)"

        if total_segs <= 1:
            # v2.2.3: 单段文件也传递来源属性
            if source_nature:
                return f"\n=== 文档来源属性 ===\n本文档来源属性: {source_nature} — {nature_text}\n请据此选择正确的分类方向。\n"
            return ""
        # 前段已提取的知识点标题
        if prev_kps:
            titles = [kp.get("title", "") for kp in prev_kps]
            titles_text = "\n".join(f"  {i+1}. {t}" for i, t in enumerate(titles))
        else:
            titles_text = "  (这是第一段，暂无)"
        return CONTEXT_RELAY_TEMPLATE.format(
            total_segments=total_segs,
            current_segment=seg_idx,
            source_nature=f"{source_nature} — {nature_text}" if source_nature else "(未识别)",
            file_structure_summary=file_structure or "(结构摘要不可用)",
            previous_titles=titles_text
        )

    # ================================================================
    # v2.1.0-c 新增：跨段补漏检查
    # ================================================================
    def _cross_segment_check(self, filename, file_structure, all_kps):
        """V3检查分段提取是否有遗漏。返回遗漏信息dict或None。"""
        if not file_structure:
            print(f"     无结构摘要,跳过补漏检查")
            return None

        all_titles = "\n".join(f"  {i+1}. {kp.get('title', '')}" for i, kp in enumerate(all_kps))
        prompt = CROSS_SEGMENT_CHECK_PROMPT
        up = prompt["user_prompt_template"].format(
            filename=filename,
            document_structure=file_structure,
            all_kp_titles=all_titles)

        try:
            ai = self.client.chat_with_json(
                prompt["system_prompt"], up, temperature=0.2,
                call_type="cross_segment_check", model_override="deepseek-chat")
            parsed = ai.get("parsed_json")
            if parsed and isinstance(parsed, dict):
                cost = ai.get("estimated_cost", 0)
                missed = parsed.get("missed_sections", [])
                coverage = parsed.get("overall_coverage", "未知")
                dupes = parsed.get("duplicate_suspects", [])
                print(f"     补漏检查完成(花费{cost:.4f}元)")
                print(f"     覆盖评估: {coverage}")
                if missed:
                    important_missed = [m for m in missed if m.get("importance") in ("高", "中")]
                    if important_missed:
                        print(f"     [注意] 发现{len(important_missed)}个可能遗漏的章节:")
                        for m in important_missed[:3]:
                            print(f"       - {m.get('section_title', '')} (重要性:{m.get('importance', '')})")
                        print(f"     建议在审核时重点关注相关知识点的完整性")
                if dupes:
                    print(f"     [提示] 发现{len(dupes)}组疑似重复知识点")
                return parsed
        except CostLimitExceeded:
            print(f"     费用已达上限,跳过补漏检查")
        except Exception as e:
            print(f"     补漏检查失败: {e}")
        return None

    # ================================================================
    # v2.1.0-c 新增：费用预估
    # ================================================================
    def _estimate_extraction_cost(self, segments):
        """估算R1提取费用（粗略估算，给用户一个量级参考）"""
        # R1定价：输入4元/百万token，输出16元/百万token
        # 粗估：1000中文字 ≈ 800 token
        total_chars = sum(len(s) for s in segments)
        est_input_tokens = int(total_chars * 0.8)  # 输入（含system prompt约3000字）
        est_input_tokens += len(segments) * 3000 * 0.8  # 每段的system prompt
        est_output_tokens = len(segments) * 1500  # 每段估算输出1500 token
        cost = (est_input_tokens / 1e6) * 4.0 + (est_output_tokens / 1e6) * 16.0
        return round(cost, 2)

    # ================================================================
    # v2.2.3 F058: V3质检 —— 三级降级链
    # L0 批量15/批 → L1 小批3/批最多2轮 → L2 逐条 → L3 规则兜底
    # 每条kp必有qa_score + qa_source；守门员机制保证不遗漏
    # ================================================================
    def _build_qc_items(self, kps, kps_info):
        """构造质检用的 item 列表（L0/L1/L2 共用数据结构）。
        每个 item 的 'index' 字段保留全局索引，供回写 kp_id 时映射。
        """
        items = []
        for i, kp in enumerate(kps):
            qc_item = {
                "index": i,  # 全局索引
                "title": kp.get("title", "未命名"),
                "original_excerpt": (kp.get("original_excerpt") or "")[:200],
                "suggested_category_tags": kp.get("suggested_category_tags", []),
                "suggested_keywords": kp.get("suggested_keywords", [])[:5]
            }
            # v2.1.1 F038: 传递 practical_insights 供V3评估可靠性
            if i < len(kps_info):
                insights = kps_info[i].get("practical_insights", [])
                if insights:
                    qc_item["practical_insights"] = insights
            items.append(qc_item)
        return items

    def _qc_batch_call(self, batch_items, filename, file_summary):
        """批量质检V3调用（L0 和 L1 共用）。
        batch_items: 包含 'index' 字段的 item 列表
        返回: {"success": bool, "results": [...], "cost": float, "error": str}
        results 中的 kp_index 是批内局部序号（0-based），由调用方映射到全局index
        """
        try:
            # V3看到的 JSON 去掉 'index' 字段（避免误导模型以全局序号作答）
            local_items = [{k: v for k, v in it.items() if k != "index"} for it in batch_items]
            knowledge_points_json = json.dumps(local_items, ensure_ascii=False, indent=2)
            up = QC_CHECK_PROMPT["user_prompt_template"].format(
                filename=filename,
                file_summary=file_summary or "(无摘要)",
                kp_count=len(local_items),
                knowledge_points_json=knowledge_points_json
            )
            ai = self.client.chat_with_json(
                QC_CHECK_PROMPT["system_prompt"], up, temperature=0.2,
                call_type="qc_check", model_override="deepseek-chat")
            parsed = ai.get("parsed_json")
            cost = ai.get("estimated_cost", 0) or 0

            if not parsed or not isinstance(parsed, dict):
                return {"success": False, "results": [], "cost": cost,
                        "error": "parsed_not_dict"}
            results = parsed.get("qa_results", [])
            if not results or not isinstance(results, list):
                return {"success": False, "results": [], "cost": cost,
                        "error": "no_qa_results"}
            return {"success": True, "results": results, "cost": cost, "error": ""}
        except CostLimitExceeded:
            raise
        except Exception as e:
            return {"success": False, "results": [], "cost": 0,
                    "error": f"{type(e).__name__}:{e}"}

    def _qc_single_call(self, kp_item, filename):
        """逐条质检V3调用（L2，用 QC_CHECK_SINGLE_PROMPT）。
        kp_item: 单个 item（含 'index' 字段，用于日志）
        返回: {"success": bool, "result": {...}, "cost": float, "error": str}
        """
        try:
            local_item = {k: v for k, v in kp_item.items() if k != "index"}
            knowledge_point_json = json.dumps(local_item, ensure_ascii=False, indent=2)
            up = QC_CHECK_SINGLE_PROMPT["user_prompt_template"].format(
                filename=filename,
                knowledge_point_json=knowledge_point_json
            )
            ai = self.client.chat_with_json(
                QC_CHECK_SINGLE_PROMPT["system_prompt"], up, temperature=0.2,
                call_type="qc_check_single", model_override="deepseek-chat")
            parsed = ai.get("parsed_json")
            cost = ai.get("estimated_cost", 0) or 0

            if not parsed or not isinstance(parsed, dict):
                return {"success": False, "result": None, "cost": cost,
                        "error": "parsed_not_dict"}
            if "qa_score" not in parsed:
                return {"success": False, "result": None, "cost": cost,
                        "error": "missing_qa_score"}
            return {"success": True, "result": parsed, "cost": cost, "error": ""}
        except CostLimitExceeded:
            raise
        except Exception as e:
            return {"success": False, "result": None, "cost": 0,
                    "error": f"{type(e).__name__}:{e}"}

    def _excerpt_in_source(self, excerpt, content):
        """检查 excerpt 是否在 source_content 中出现（规则兜底用）。
        三级匹配：完整 in → 首30字 in → 尾30字 in。
        """
        if not excerpt or not content:
            return False
        ex = excerpt.strip()
        if not ex:
            return False
        if ex in content:
            return True
        if len(ex) >= 30:
            if ex[:30] in content:
                return True
            if ex[-30:] in content:
                return True
        return False

    def _qc_rule_fallback(self, kp_raw, source_content):
        """L3 本地规则兜底：长度/必填字段/excerpt存在性 3项检查。
        全通过 → qa_score=3（待人工复核）
        任一不通过 → qa_score=1
        """
        excerpt = (kp_raw.get("original_excerpt", "") or "")
        title = (kp_raw.get("title", "") or "")
        flags = []
        passed = True

        # Check 1: excerpt 长度 30-800 字
        el = len(excerpt.strip())
        if el < 30:
            flags.append("excerpt_too_short")
            passed = False
        elif el > 800:
            flags.append("excerpt_too_long")
            passed = False

        # Check 2: 必填字段（title / excerpt / 任意AI提取字段）
        if not title.strip():
            flags.append("missing_title")
            passed = False
        if not excerpt.strip():
            flags.append("missing_excerpt")
            passed = False
        if not kp_raw or not isinstance(kp_raw, dict):
            flags.append("missing_ai_content")
            passed = False

        # Check 3: excerpt 存在性（仅当有 source_content 时才检查）
        if source_content and excerpt.strip():
            if not self._excerpt_in_source(excerpt, source_content):
                flags.append("excerpt_hallucination")
                passed = False

        if passed:
            return {
                "qa_score": 3,
                "qa_flags": ["v3_qc_failed_manual_review"],
                "insight_reliability": None,
                "improvement_suggestion": ""  # 不入库
            }
        flags.append("rule_fallback_fail")
        return {
            "qa_score": 1,
            "qa_flags": flags,
            "insight_reliability": None,
            "improvement_suggestion": ""
        }

    def _write_qc_result(self, kp_id, qc_fields, qa_source):
        """F058 质检结果统一写入出口。
        任何一级（L0/L1/L2/L3）的结果都必须走这里，保证 qa_score + qa_source 一致性。
        """
        # 评分校验
        try:
            score = int(qc_fields.get("qa_score", 0) or 0)
        except (TypeError, ValueError):
            score = 0
        if score < 1 or score > 5:
            # 异常评分兜底为3（中性）
            score = 3

        # flags 标准化
        raw_flags = qc_fields.get("qa_flags", [])
        if not isinstance(raw_flags, list):
            raw_flags = []
        normalized_flags = []
        for f in raw_flags:
            if not isinstance(f, str):
                continue
            mapped = self.QC_FLAG_MAP.get(f)
            if mapped:
                normalized_flags.append(mapped)
            else:
                # 已是英文码 or 规则兜底产出的标记 → 原样保留
                normalized_flags.append(f)

        # insight_reliability 校验
        insight_rel = qc_fields.get("insight_reliability", None)
        valid_rel = ("reliable", "uncertain", "unreliable", "no_insights")
        if insight_rel not in valid_rel:
            insight_rel = None

        update_kw = {
            "qa_score": score,
            "qa_flags": json.dumps(normalized_flags, ensure_ascii=False),
            "qa_source": qa_source
        }
        if insight_rel:
            update_kw["insight_reliability"] = insight_rel

        try:
            self.db.update_knowledge_point(kp_id, **update_kw)
            return True
        except Exception as e:
            print(f"     ! 质检结果写入失败(ID={kp_id}): {e}")
            return False

    def _quality_check(self, filename, content_summary, kps, kps_info, source_content=""):
        """V3 质检三级降级链（v2.2.3 F058）。
        kps: 原始AI提取的知识点列表（含完整内容）
        kps_info: 写入DB后的info列表（含kp_id和practical_insights）
        source_content: 原文（规则兜底做excerpt存在性检查用）
        返回成功写入 qa_score 的知识点数（守门员后应 == len(kps_info)）
        """
        if not kps or not kps_info:
            return 0

        # 构造质检数据
        all_qc_items = self._build_qc_items(kps, kps_info)
        total_cost = 0.0
        processed_kp_ids = set()

        # ===== L0: 批量 15/批 =====
        L0_BATCH_SIZE = 15
        l0_batches = [all_qc_items[i:i + L0_BATCH_SIZE]
                      for i in range(0, len(all_qc_items), L0_BATCH_SIZE)]
        l0_failed_items = []  # L0 失败需降级的 items

        if len(l0_batches) > 1:
            print(f"     知识点较多({len(kps)}条),分{len(l0_batches)}批质检...")

        try:
            for batch_idx, batch in enumerate(l0_batches):
                r = self._qc_batch_call(batch, filename, content_summary)
                total_cost += r.get("cost", 0)

                if r["success"]:
                    written = self._apply_batch_results(
                        r["results"], batch, kps_info, processed_kp_ids, "batch")
                    if len(l0_batches) > 1:
                        print(f"     L0 第{batch_idx+1}/{len(l0_batches)}批 通过: {written}条(花费{r['cost']:.4f}元)")
                else:
                    err = r.get("error", "unknown")
                    print(f"     L0 第{batch_idx+1}/{len(l0_batches)}批 失败: {err}")
                    l0_failed_items.extend(batch)
                    self._safe_log_event(
                        "qc_downgrade", "qc", "warning",
                        payload={
                            "level": "L0_to_L1",
                            "reason": err,
                            "batch_idx": batch_idx,
                            "kp_count": len(batch),
                            "filename": filename
                        })
        except CostLimitExceeded:
            print(f"     费用已达上限,剩余知识点走规则兜底")
            # 费用超限 → 剩余未处理的全部走L3
            self._fallback_remaining(all_qc_items, kps, kps_info,
                                     processed_kp_ids, source_content,
                                     reason="cost_limit_exceeded")
            self._print_qc_summary(kps_info, processed_kp_ids, total_cost)
            return len(processed_kp_ids)

        # ===== L1: 小批 3/批 最多 2 轮 =====
        if l0_failed_items:
            print(f"     [F058 L1] {len(l0_failed_items)}条进入小批降级(3/批,最多2轮)...")
            L1_BATCH_SIZE = 3
            L1_MAX_ROUNDS = 2
            remaining = list(l0_failed_items)

            try:
                for round_num in range(1, L1_MAX_ROUNDS + 1):
                    if not remaining:
                        break
                    small_batches = [remaining[i:i + L1_BATCH_SIZE]
                                     for i in range(0, len(remaining), L1_BATCH_SIZE)]
                    next_failed = []
                    round_written = 0
                    for sb_idx, sb in enumerate(small_batches):
                        r = self._qc_batch_call(sb, filename, content_summary)
                        total_cost += r.get("cost", 0)
                        if r["success"]:
                            round_written += self._apply_batch_results(
                                r["results"], sb, kps_info, processed_kp_ids, "small_batch")
                        else:
                            next_failed.extend(sb)
                    if round_written > 0 or len(next_failed) < len(remaining):
                        print(f"     L1 第{round_num}轮: 通过{len(remaining)-len(next_failed)}条, 剩余{len(next_failed)}条")
                    remaining = next_failed

                if remaining:
                    self._safe_log_event(
                        "qc_downgrade", "qc", "warning",
                        payload={
                            "level": "L1_to_L2",
                            "kp_count": len(remaining),
                            "filename": filename
                        })
                l1_failed_items = remaining
            except CostLimitExceeded:
                print(f"     费用已达上限,剩余知识点走规则兜底")
                self._fallback_remaining(all_qc_items, kps, kps_info,
                                         processed_kp_ids, source_content,
                                         reason="cost_limit_exceeded_in_L1")
                self._print_qc_summary(kps_info, processed_kp_ids, total_cost)
                return len(processed_kp_ids)
        else:
            l1_failed_items = []

        # ===== L2: 逐条 QC_CHECK_SINGLE_PROMPT =====
        l2_failed = []  # [(item, kp_id, err)]
        if l1_failed_items:
            print(f"     [F058 L2] {len(l1_failed_items)}条进入逐条降级(1/次)...")
            l2_success = 0
            try:
                for item in l1_failed_items:
                    global_idx = item.get("index", -1)
                    if not (0 <= global_idx < len(kps_info)):
                        continue
                    kp_id = kps_info[global_idx].get("kp_id")
                    if not kp_id or kp_id in processed_kp_ids:
                        continue

                    r = self._qc_single_call(item, filename)
                    total_cost += r.get("cost", 0)
                    if r["success"]:
                        if self._write_qc_result(kp_id, r["result"], "single"):
                            processed_kp_ids.add(kp_id)
                            l2_success += 1
                    else:
                        l2_failed.append((item, kp_id, r.get("error", "unknown")))
                print(f"     L2 逐条: 通过{l2_success}条, 剩余{len(l2_failed)}条进入规则兜底")
            except CostLimitExceeded:
                print(f"     费用已达上限,剩余知识点走规则兜底")
                # 把 L2 未处理完的也丢给 L3
                for item in l1_failed_items:
                    gi = item.get("index", -1)
                    if 0 <= gi < len(kps_info):
                        kid = kps_info[gi].get("kp_id")
                        if kid and kid not in processed_kp_ids:
                            if not any(t[1] == kid for t in l2_failed):
                                l2_failed.append((item, kid, "cost_limit_exceeded"))

        # ===== L3: 规则兜底 =====
        if l2_failed:
            print(f"     [F058 L3] {len(l2_failed)}条进入规则兜底...")
            for item, kp_id, err in l2_failed:
                if kp_id in processed_kp_ids:
                    continue
                global_idx = item.get("index", -1)
                kp_raw = kps[global_idx] if 0 <= global_idx < len(kps) else {}
                fallback = self._qc_rule_fallback(kp_raw, source_content)
                if self._write_qc_result(kp_id, fallback, "rule_fallback"):
                    processed_kp_ids.add(kp_id)
                self._safe_log_event(
                    "rule_fallback", "qc", "error",
                    kp_id=kp_id,
                    payload={
                        "reason": "single_qc_failed",
                        "err_msg": err,
                        "rule_fallback_score": fallback.get("qa_score"),
                        "filename": filename
                    })

        # ===== 守门员：遍历 kps_info 扫漏网 =====
        for idx, info in enumerate(kps_info):
            kp_id = info.get("kp_id")
            if not kp_id or kp_id in processed_kp_ids:
                continue
            kp_raw = kps[idx] if 0 <= idx < len(kps) else {}
            fallback = self._qc_rule_fallback(kp_raw, source_content)
            if self._write_qc_result(kp_id, fallback, "rule_fallback"):
                processed_kp_ids.add(kp_id)
            self._safe_log_event(
                "rule_fallback", "qc", "warning",
                kp_id=kp_id,
                payload={"reason": "goalkeeper_sweep", "filename": filename})
            print(f"     [F058 守门员] kp_id={kp_id} 未被三级处理,强制规则兜底")

        # 汇总输出
        self._print_qc_summary(kps_info, processed_kp_ids, total_cost)
        return len(processed_kp_ids)

    def _apply_batch_results(self, v3_results, batch, kps_info, processed_kp_ids, qa_source):
        """将 V3 批量返回的 qa_results 写入DB。
        v3_results 中的 kp_index 是批内局部序号（0-based），通过 batch[local_idx]['index'] 映射到全局。
        返回成功写入的条数。
        """
        written = 0
        for qr in v3_results:
            if not isinstance(qr, dict):
                continue
            local_idx = qr.get("kp_index", -1)
            try:
                local_idx = int(local_idx)
            except (TypeError, ValueError):
                local_idx = -1
            if not (0 <= local_idx < len(batch)):
                continue
            global_idx = batch[local_idx].get("index", -1)
            if not (0 <= global_idx < len(kps_info)):
                continue
            kp_id = kps_info[global_idx].get("kp_id")
            if not kp_id or kp_id in processed_kp_ids:
                continue
            if self._write_qc_result(kp_id, qr, qa_source):
                processed_kp_ids.add(kp_id)
                written += 1
        return written

    def _fallback_remaining(self, all_qc_items, kps, kps_info,
                            processed_kp_ids, source_content, reason):
        """费用超限等场景：把未处理的全部走 L3 规则兜底。"""
        for item in all_qc_items:
            global_idx = item.get("index", -1)
            if not (0 <= global_idx < len(kps_info)):
                continue
            kp_id = kps_info[global_idx].get("kp_id")
            if not kp_id or kp_id in processed_kp_ids:
                continue
            kp_raw = kps[global_idx] if 0 <= global_idx < len(kps) else {}
            fallback = self._qc_rule_fallback(kp_raw, source_content)
            if self._write_qc_result(kp_id, fallback, "rule_fallback"):
                processed_kp_ids.add(kp_id)
            self._safe_log_event(
                "rule_fallback", "qc", "error",
                kp_id=kp_id,
                payload={"reason": reason})

    def _print_qc_summary(self, kps_info, processed_kp_ids, total_cost):
        """打印质检汇总：分数分布 + 来源分布"""
        if not processed_kp_ids:
            print(f"     质检完成(总花费{total_cost:.4f}元),但无成功评分记录")
            return
        try:
            conn = self.db.get_connection(); c = conn.cursor()
            kp_ids = list(processed_kp_ids)
            placeholder = ",".join("?" * len(kp_ids))
            c.execute(
                f"SELECT qa_score, qa_source FROM knowledge_points WHERE id IN ({placeholder})",
                kp_ids
            )
            rows = c.fetchall()
            conn.close()
        except Exception as e:
            print(f"     质检汇总查询失败: {e}")
            return

        scores = []
        sources = {}
        for r in rows:
            s, src = r[0], (r[1] or "unknown")
            if s is not None:
                try:
                    scores.append(float(s))
                except (TypeError, ValueError):
                    pass
            sources[src] = sources.get(src, 0) + 1

        print(f"     质检完成: {len(scores)}条评分 (总花费{total_cost:.4f}元)")
        if scores:
            avg = sum(scores) / len(scores)
            low = sum(1 for s in scores if s <= 2)
            mid = sum(1 for s in scores if s == 3)
            high = sum(1 for s in scores if s >= 4)
            print(f"     分数分布: 平均{avg:.1f}分 (优{high} / 中{mid} / 差{low})")
        if sources:
            src_parts = [f"{k}:{v}" for k, v in sources.items()]
            print(f"     质检来源: {' / '.join(src_parts)}")
            rf_count = sources.get("rule_fallback", 0)
            if rf_count > 0:
                print(f"     [注意] {rf_count}条走规则兜底(L3),前端将黄色高亮,建议人工优先复核")
        low_count = sum(1 for s in scores if s <= 2)
        if low_count > 0:
            print(f"     [注意] {low_count}条知识点评分较低,建议审核时重点关注")

    # ================================================================
    # v2.3.4 D11: 文件级截断统计输出
    # ================================================================
    def _print_truncation_stats(self, kp_count):
        """提取完成时控制台输出一行截断统计 + 总耗时 + 单价估算。
        老唐肉眼即看,不入库,不动 db。

        v2.3.4-hotfix1 H5 输出字段:截断/Kimi救/R1镜像救/F057兜底/全失败
        """
        stats = getattr(self, "_truncation_stats", None)
        if not stats:
            return
        elapsed = time.time() - stats.get("start_time", time.time())
        truncations = stats.get("truncations", 0)
        kimi_recovs = stats.get("kimi_recoveries", 0)
        r1m_recovs = stats.get("r1_mirror_recoveries", 0)
        f057_fallbacks = stats.get("f057_fallbacks", 0)
        total_fails = stats.get("total_failures", 0)
        lost = stats.get("lost_segments", 0)
        recovery_cost = stats.get("total_cost", 0.0)

        if truncations == 0:
            print(f"     📊 [文件统计] 一次成功 / 知识点{kp_count}条 / 耗时{int(elapsed)}s / Prompt {get_prompt_version()}")
        else:
            parts = [f"截断{truncations}次"]
            if kimi_recovs > 0:
                parts.append(f"L1 Kimi救{kimi_recovs}次")
            if r1m_recovs > 0:
                parts.append(f"L2 R1镜像救{r1m_recovs}次")
            if f057_fallbacks > 0:
                parts.append(f"L3 F057兜底{f057_fallbacks}次")
            if total_fails > 0:
                parts.append(f"❌ 全失败{total_fails}次")
            if lost > 0:
                parts.append(f"放弃段{lost}")
            parts.append(f"知识点{kp_count}条")
            parts.append(f"耗时{int(elapsed)}s")
            if recovery_cost > 0:
                parts.append(f"补救额外费用{recovery_cost:.4f}元")
            parts.append(f"Prompt {get_prompt_version()}")
            print(f"     📊 [文件统计] " + " / ".join(parts))

    # ================================================================
    # v1.1.0 保留：AI分类建议（v2.0.0更新prompt以感知三层标签）
    # ================================================================
    def _check_category_suggestions(self, kps_info):
        """提取完成后,分析是否需要调整分类体系。"""
        unmatched = [k for k in kps_info if not k.get("category_matched")]
        if not unmatched:
            return

        cats = self.db.get_all_categories()
        cat_tree_text = ""
        for cat in cats:
            cat_tree_text += f"  {cat['level2_code']} {cat['level2_name']}: {cat['description']}\n"

        unmatched_text = ""
        for k in unmatched[:10]:
            tags_preview = ", ".join(k.get("category_tags", [])[:4])
            unmatched_text += f"  - {k['title']} (AI建议分类编号: {k.get('suggested_code', '无')}, 分类标签: {tags_preview})\n"

        system_prompt = """你是一个知识库分类体系顾问。用户有一个乡村振兴知识库,分类体系如下。
现在有一些知识点无法匹配到现有分类,请分析是否需要调整分类体系。

注意：该知识库同时使用"分类体系"和"三层标签体系"。分类体系是档案柜（按来源类型分区），三层标签是多维标注。
你只负责分类体系的建议，不涉及标签体系。

你可以提出以下类型的建议(可以同时提多条):
1. add_level2: 在某个一级分类下新增二级分类
2. add_level1: 新增一个全新的一级分类(及其下属二级分类)
3. rename: 重命名某个分类以扩大覆盖范围
4. split: 将一个过大的分类拆分为多个
5. merge: 将多个过小的分类合并

请严格按JSON格式返回,不要有其他文字:
{"suggestions": [
  {"type": "add_level2", "name": "新分类名称", "level": "二级", "parent": "所属一级分类名称", "reason": "理由说明(50字以内)"},
  {"type": "add_level1", "name": "新一级分类名称", "level": "一级", "parent": "", "reason": "理由说明"},
  ...
]}

如果现有分类体系已经够用(只是AI分类建议不准确),请返回: {"suggestions": []}"""

        user_prompt = f"""当前分类体系:
{cat_tree_text}

以下知识点未能匹配到现有分类:
{unmatched_text}

请分析是否需要新增或调整分类。只提出真正必要的建议,不要过度拆分。"""

        try:
            print(f"\n     [AI分类建议] 分析{len(unmatched)}条未匹配知识点...")
            ai = self.client.chat_with_json(
                system_prompt, user_prompt,
                temperature=0.3, call_type="architecture_suggestion",
                model_override="deepseek-chat"
            )
            parsed = ai.get("parsed_json")
            if parsed and isinstance(parsed, dict):
                suggestions = parsed.get("suggestions", [])
                if suggestions:
                    print(f"     [AI分类建议] AI提出了{len(suggestions)}条建议:")
                    for sg in suggestions:
                        sg_type = sg.get("type", "add_level2")
                        sg_name = sg.get("name", "")
                        sg_level = sg.get("level", "二级")
                        sg_parent = sg.get("parent", "")
                        sg_reason = sg.get("reason", "")
                        print(f"       - [{sg_type}] {sg_name} ({sg_reason[:40]})")

                        parent_id = None
                        if sg_parent:
                            for cat in cats:
                                if cat["level1_name"] == sg_parent:
                                    parent_id = cat["id"]
                                    break
                        related_ids = [k.get("kp_id") for k in unmatched if k.get("kp_id")]
                        self.db.add_architecture_suggestion(
                            suggested_name=sg_name,
                            suggested_level=sg_level,
                            reason=sg_reason,
                            suggestion_type=sg_type,
                            parent_category_id=parent_id,
                            related_knowledge_ids=related_ids[:5]
                        )
                    print(f"     [AI分类建议] 已保存,请在审核界面中查看并处理")
                else:
                    print(f"     [AI分类建议] 现有分类体系够用,无需调整")
            else:
                print(f"     [AI分类建议] 解析失败,跳过")
        except CostLimitExceeded:
            print(f"     [AI分类建议] 费用已达上限,跳过分类建议")
        except Exception as e:
            print(f"     [AI分类建议] 出错: {e}")

    # ================================================================
    # 核心提取流程
    # ================================================================
    def extract_from_file(self, rec):
        result = {"success": False, "knowledge_count": 0, "error": ""}
        fid = rec["id"]
        self._current_file_id = fid  # 供_smart_segment保存分段方案
        fn = rec.get("renamed_filename") or rec["original_filename"]
        original_fn = rec["original_filename"]
        fp = None
        # v2.3.4-hotfix1 H4: 重置文件级截断统计(扩字段)
        self._truncation_stats = {
            "truncations": 0,
            "prefix_recoveries": 0,  # DEPRECATED v2.3.4-hotfix1, 保留兼容
            "kimi_recoveries": 0,    # v2.3.4-hotfix1 新增:L1 Kimi 救回次数
            "r1_mirror_recoveries": 0,  # v2.3.4-hotfix1 新增:L2 R1 镜像救回次数
            "f057_fallbacks": 0,
            "lost_segments": 0,
            "total_failures": 0,     # v2.3.4-hotfix1 新增:L4 全失败次数
            "total_cost": 0.0,
            "start_time": time.time()
        }
        try:
            print(f"\n     >> 开始提取: {fn}")
            for f in self.processing.iterdir():
                if f.name == fn or f.name == rec["original_filename"]:
                    fp = str(f); break
            if not fp: fp = rec["file_path"]
            if not os.path.exists(fp):
                result["error"] = f"文件不存在:{fp}"
                print(f"     [FAIL] {result['error']}"); return result

            is_dup, file_hash = self.check_duplicate(fp, fn)
            if is_dup:
                self.db.update_source_file(fid, process_status="completed",
                                           process_message="重复文件,用户选择跳过", file_hash=file_hash)
                self._move_to_completed(fp, fn)
                self._clean_pending(original_fn)
                result["error"] = "重复文件已跳过"; return result
            self.db.update_source_file(fid, file_hash=file_hash)

            # 优先读取预处理生成的.md文件(避免重复OCR/解析)
            md_path = Path(fp).with_suffix(".md") if not fp.endswith(".md") else None
            if md_path and md_path.exists():
                print(f"     读取预处理内容: {md_path.name}")
                with open(str(md_path), "r", encoding="utf-8") as mdf:
                    content = mdf.read()
            else:
                rr = self.reader.read_file(fp)
                if not rr["success"]:
                    result["error"] = rr["error"]
                    print(f"     [FAIL] 文件读取失败: {result['error']}")
                    self._move_to_failed(fp, fn); self._clean_pending(original_fn)
                    self.db.update_source_file(fid, process_status="failed", process_message=result["error"])
                    return result
                content = rr["content"]
                if rr.get("metadata", {}).get("needs_ocr"):
                    print(f"     需要OCR识别(无预处理缓存)...")
                    content = self.client.ocr_image(fp)["content"]

            ctype = self._determine_type(rec, content)

            # === Step 1: V3预分析 ===
            pre_result = None
            print(f"     [Step 1] V3预分析...")
            self._report_progress(current_step="Step 1/8 V3预分析")
            pre_result = self._pre_analyze(content, fn)
            if pre_result == "SKIP_FILE":
                self.db.update_source_file(fid, process_status="processing",
                                           process_message="预分析失败,用户选择跳过")
                result["error"] = "用户跳过(预分析失败)"; return result

            if pre_result and isinstance(pre_result, dict):
                # 更新分类建议
                suggested_type = pre_result.get("content_type", "")
                if suggested_type and suggested_type in self.TYPE_NAMES:
                    if suggested_type != ctype:
                        print(f"     V3建议分类: {self.TYPE_NAMES[suggested_type]}(原判断:{self.TYPE_NAMES.get(ctype, ctype)})")
                        ctype = suggested_type
                # 质量评估
                q_score = pre_result.get("quality_score", 5)
                q_reason = pre_result.get("quality_reason", "")
                est_count = pre_result.get("estimated_knowledge_count", "?")
                print(f"     质量评分: {q_score}/5 ({q_reason})")
                print(f"     预估知识点: {est_count}条")
                # 低价值文件提醒
                if q_score <= 2:
                    warnings = pre_result.get("warnings", [])
                    if warnings:
                        for w in warnings:
                            print(f"     [提醒] {w}")
                    if self._headless:
                        print(f"     [headless] 低价值文件(评分{q_score}/5)，自动继续提取")
                    else:
                        while True:
                            answer = input(f"     该文件价值较低(评分{q_score}/5), 继续提取? (Y=继续 / N=跳过): ").strip().upper()
                            if answer == "Y":
                                print(f"     好的,继续提取"); break
                            elif answer == "N":
                                self.db.update_source_file(fid, process_status="completed",
                                                           process_message=f"V3预分析评分{q_score}/5,用户选择跳过")
                                self._move_to_completed(fp, fn); self._clean_pending(original_fn)
                                result["error"] = "低价值文件已跳过"; return result
                            else: print(f"     请输入 Y 或 N")
                # 保存预分析结果
                self.db.update_source_file(fid,
                    pre_analysis_result=json.dumps(pre_result, ensure_ascii=False),
                    suggested_content_type=ctype)

            prompt = get_extraction_prompt(ctype)
            # v2.2.3: 提取来源属性
            source_nature = ""
            if pre_result and isinstance(pre_result, dict):
                source_nature = pre_result.get("source_nature", "")
            # v2.2.0 bugfix-5: doc_origin覆盖——用户标记的来源优先于V3预分析
            doc_origin = rec.get("doc_origin", "external")
            if doc_origin == "self":
                source_nature = "personal_experience"
                print(f"     文档来源: 我的经验文档(doc_origin=self, 强制authority=firsthand)")
            elif source_nature:
                print(f"     来源属性: {source_nature}")
            print(f"     文件类型: {self.TYPE_NAMES.get(ctype, ctype)}")
            print(f"     内容长度: {len(content)}字")
            print(f"     提取模型: {self.extraction_model} ({self.extraction_model_name})")
            print(f"     Prompt版本: {get_prompt_version()}")

            # === Step 2: 智能分段 ===
            print(f"     [Step 2] 智能分段...")
            self._report_progress(current_step="Step 2/8 智能分段")
            segs, file_structure = self._smart_segment(content, pre_result, fn)
            if len(segs) > 1:
                seg_lens = [len(s) for s in segs]
                print(f"     分{len(segs)}段提取(段长: {min(seg_lens)}-{max(seg_lens)}字)")
            else:
                print(f"     整段提取({len(segs[0])}字)")

            # === Step 3: 费用预估(大文件) ===
            if len(segs) >= 3:
                est_cost = self._estimate_extraction_cost(segs)
                print(f"     预估费用: R1提取约{est_cost:.2f}元 + V3辅助<0.2元")
                if est_cost > 5.0:
                    if self._headless:
                        print(f"     [headless] 费用较高({est_cost:.1f}元)，自动继续")
                    else:
                        while True:
                            answer = input(f"     预估费用较高({est_cost:.1f}元), 继续? (Y/N): ").strip().upper()
                            if answer == "Y": break
                            elif answer == "N":
                                self.db.update_source_file(fid, process_status="processing",
                                                           process_message=f"费用预估{est_cost:.1f}元,用户暂缓")
                                result["error"] = "用户暂缓(费用)"; return result
                            else: print(f"     请输入 Y 或 N")

            # === Step 4: R1逐段提取(带上下文接力+F057截断补救) ===
            print(f"     [Step 4] AI提取中,请耐心等待...")
            self._report_progress(current_step="Step 4/8 AI提取")
            kps = []
            for i, seg in enumerate(segs, 1):
                if len(segs) > 1:
                    print(f"\n     --- 第{i}/{len(segs)}段 ({len(seg)}字) ---")
                # 构建上下文接力信息
                relay_prefix = self._build_context_relay(i, len(segs), file_structure, kps, source_nature=source_nature)
                seg_kps = self._extract_with_auto_split(
                    seg, f"{fn}(第{i}/{len(segs)}段)" if len(segs) > 1 else fn,
                    prompt, ctype,
                    relay_prefix=relay_prefix,
                    file_id=fid)  # v2.2.3 F057: 传入 file_id 供补救时记日志
                kps.extend(seg_kps)

            if not kps:
                self.db.update_source_file(fid, process_status="completed", process_message="未提取到知识点")
                self._move_to_completed(fp, fn); self._clean_pending(original_fn)
                result["error"] = "未提取到知识点"
                print(f"     [注意] 未提取到知识点"); return result

            # === Step 5: 跨段补漏检查(多段文件) ===
            extraction_notes = ""
            if len(segs) > 1:
                print(f"\n     [Step 5] 跨段补漏检查...")
                self._report_progress(current_step="Step 5/8 跨段补漏")
                missed = self._cross_segment_check(fn, file_structure, kps)
                if missed:
                    extraction_notes = json.dumps(missed, ensure_ascii=False)

            # === 写入数据库（v2.1.1: 三层标签 + 元数据 + prompt_version + practical_insights） ===
            print(f"\n     写入{len(kps)}个知识点到数据库...")
            current_prompt_version = get_prompt_version()
            cnt = 0
            kps_info = []
            for kp in kps:
                try:
                    cat_code = kp.get("suggested_category_code", "")
                    cat = self.db.find_category_by_code(cat_code)
                    tags = self._sanitize_tags(kp)

                    # v2.2.0 bugfix-5: doc_origin='self'强制firsthand权威度
                    if doc_origin == "self":
                        tags["authority"] = "firsthand"

                    # v2.1.1 F038: 解析practical_insights
                    raw_insights = kp.get("practical_insights", [])
                    if not isinstance(raw_insights, list):
                        raw_insights = []
                    clean_insights = []
                    for ins in raw_insights:
                        if isinstance(ins, dict) and ins.get("insight"):
                            clean_insights.append({
                                "insight": str(ins.get("insight", "")),
                                "basis": str(ins.get("basis", "")),
                                "confidence": ins.get("confidence", "medium") if ins.get("confidence") in ("high", "medium", "low") else "medium"
                            })

                    kid = self.db.add_knowledge_point(
                        source_file_id=fid,
                        title=kp.get("title", "未命名"),
                        content_type=ctype,
                        original_excerpt=kp.get("original_excerpt", ""),
                        ai_extracted_content=kp,
                        suggested_category_id=cat["id"] if cat else None,
                        suggested_category_tags=tags["category_tags"],
                        suggested_attribute_tags=tags["attribute_tags"],
                        suggested_keywords=tags["keywords"],
                        content_readiness=tags["readiness"],
                        source_authority=tags["authority"],
                        source_page=str(kp.get("source_page", "")),
                        source_keyword=kp.get("source_keyword", ""),
                        prompt_version=current_prompt_version,
                        practical_insights=clean_insights,
                        extracted_by_model=kp.get("_extracted_by_model", "r1"))
                    cnt += 1
                    kps_info.append({
                        "kp_id": kid,
                        "title": kp.get("title", ""),
                        "suggested_code": cat_code,
                        "category_matched": cat is not None,
                        "category_tags": tags["category_tags"],
                        "practical_insights": clean_insights,
                    })
                except Exception as e:
                    print(f"     ! 第{cnt + 1}个知识点入库失败: {e}")

            self._move_to_completed(fp, fn)
            self._clean_pending(original_fn)

            # === Step 6: V3质检（三级降级链 v2.2.3 F058） ===
            qc_count = 0
            if cnt > 0:
                print(f"\n     [Step 6] V3质检三级降级({cnt}条知识点)...")
                self._report_progress(current_step="Step 6/8 V3质检")
                content_summary = ""
                if pre_result and isinstance(pre_result, dict):
                    content_summary = pre_result.get("content_overview", "")
                # v2.2.3: 传入 source_content 供规则兜底做 excerpt 存在性检查
                qc_count = self._quality_check(fn, content_summary, kps, kps_info,
                                               source_content=content)

            # === Step 7: 政策依赖校验（V3扫描+KB匹配） ===
            pv_count = 0
            if cnt > 0:
                print(f"\n     [Step 7] 政策依赖校验({cnt}条知识点)...")
                self._report_progress(current_step="Step 7/8 政策校验")
                try:
                    pv_count = self.policy_validator.validate_batch(kps, kps_info, ctype)
                except CostLimitExceeded:
                    print(f"     费用已达上限,跳过政策校验")
                except Exception as e:
                    print(f"     政策校验出错: {e}")

            # === Step 8: 增量重复检测（本地粗筛+V3精判） ===
            dup_count = 0
            if cnt > 0 and kps:
                self._report_progress(current_step="Step 8/8 重复检测")
                try:
                    # v2.3.0-part1 顺手修：kps_info 里字段名是 kp_id，不是 id
                    new_ids = [info["kp_id"] for info in kps_info if info.get("kp_id")]
                    if new_ids:
                        dup_count = self.duplicate_checker.scan_incremental(new_ids)
                except CostLimitExceeded:
                    print(f"     费用已达上限,跳过重复检测")
                except Exception as e:
                    print(f"     重复检测出错: {e}")

            model_tag = "R1" if "reasoner" in self.extraction_model else "V3"
            msg = f"{model_tag}提取{cnt}个知识点(v2.3.4)"
            if qc_count > 0:
                msg += f" [已质检{qc_count}条]"
            if pv_count > 0:
                msg += f" [已政策校验{pv_count}条]"
            if dup_count > 0:
                msg += f" [发现{dup_count}组疑似重复]"
            if extraction_notes:
                msg += " [有补漏建议]"
            self.db.update_source_file(fid, process_status="completed", process_message=msg)
            result.update({"success": True, "knowledge_count": cnt, "kps_info": kps_info})
            print(f"     [OK] {cnt}个知识点已存入待审核队列(Prompt:{get_prompt_version()})")

            # v2.3.4 D11: 文件级截断统计输出
            self._print_truncation_stats(cnt)

        except CostLimitExceeded as e:
            result["error"] = str(e)
            print(f"\n     !! 费用超限: {e}")
        except Exception as e:
            result["error"] = f"{type(e).__name__}:{e}"
            print(f"     [FAIL] {result['error']}")
            if fp and os.path.exists(fp):
                self._move_to_failed(fp, fn)
            self._clean_pending(original_fn)
            self.db.update_source_file(fid, process_status="failed", process_message=result["error"])
        return result

    def run(self):
        print(f"\n{'=' * 60}")
        print(f"  乡村振兴知识库 - 知识点提取引擎 v2.2.3")
        print(f"  产品导向提取 | Prompt:{get_prompt_version()}")
        print(f"  启动时间: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}")
        print(f"{'=' * 60}")

        usage = self.client.get_today_usage()
        print(f"\n  今日API费用: {usage['today_cost']:.2f}元 / {usage['daily_limit']:.0f}元上限"
              f" (已用{usage['usage_percent']:.0f}%)")

        self.select_model()

        files = self.get_processing_files()
        if not files:
            print(f"\n  无待提取文件。请先将文件放入 data/pending/ 文件夹并运行预处理。")
            return
        print(f"\n  共{len(files)}个文件待提取")
        print(f"  使用模型: {self.extraction_model_name} ({self.extraction_model})")
        print(f"  分段策略: 三级智能分段(V3结构摘要 > 本地规则 > 段落边界)")
        print(f"  标签体系: 三层标签(6组41个分类标签 + 8维度属性 + 自由关键词)")
        print(f"  新增功能: V3预分析+上下文接力+跨段补漏+V3质检三级降级+政策校验+举一反三+重复检测+F057截断补救")
        print(f"{'-' * 60}")

        total_kps, ok, fail, skip = 0, 0, 0, 0
        all_kps_info = []
        self._report_progress(total_files=len(files), current_file=0, current_filename="",
                              current_step="准备开始", total_extracted=0, message="开始提取")
        for i, rec in enumerate(files, 1):
            fn = rec.get("renamed_filename") or rec["original_filename"]
            print(f"\n[{i}/{len(files)}] {fn}")
            self._report_progress(total_files=len(files), current_file=i, current_filename=fn,
                                  current_step="开始处理", total_extracted=total_kps, message="")
            r = self.extract_from_file(rec)
            if r["success"]:
                ok += 1
                total_kps += r["knowledge_count"]
                all_kps_info.extend(r.get("kps_info", []))
            elif "重复" in r.get("error", "") or "跳过" in r.get("error", ""):
                skip += 1
            else:
                fail += 1
                if "费用上限" in r.get("error", ""):
                    print(f"\n  !! 费用达到上限，剩余{len(files) - i}个文件下次再处理")
                    break

        # 全部提取完成后,统一分析分类建议
        if all_kps_info:
            self._check_category_suggestions(all_kps_info)

        usage = self.client.get_today_usage()
        print(f"\n{'=' * 60}")
        print(f"  提取完成!")
        print(f"  使用模型: {self.extraction_model_name}")
        print(f"  Prompt版本: {get_prompt_version()}")
        print(f"  文件统计: {ok}个成功 / {skip}个跳过 / {fail}个失败")
        print(f"  知识点数: 共提取{total_kps}个，已V3质检(含举一反三)+政策校验+重复检测，等待人工审核")
        print(f"  今日费用: {usage['today_cost']:.2f}元 (剩余{usage['remaining']:.2f}元)")
        print(f"{'-' * 60}")
        print(f"  下一步: 运行[启动审核界面.bat]审核知识点")
        print(f"{'=' * 60}")

    def run_headless(self, model_key="1"):
        """非交互式运行，供管理后台API调用。返回结果字典。"""
        self.set_model(model_key)

        files = self.get_processing_files()
        if not files:
            self._report_progress(message="无待提取文件", total_files=0, current_file=0,
                                  current_step="完成", total_extracted=0)
            return {"success": True, "ok": 0, "fail": 0, "skip": 0, "total_kps": 0, "message": "无待提取文件"}

        total_kps, ok, fail, skip = 0, 0, 0, 0
        all_kps_info = []
        self._report_progress(total_files=len(files), current_file=0, current_filename="",
                              current_step="准备开始", total_extracted=0, message="开始提取")
        for i, rec in enumerate(files, 1):
            fn = rec.get("renamed_filename") or rec["original_filename"]
            self._report_progress(total_files=len(files), current_file=i, current_filename=fn,
                                  current_step="开始处理", total_extracted=total_kps)
            r = self.extract_from_file(rec)
            if r["success"]:
                ok += 1
                total_kps += r["knowledge_count"]
                all_kps_info.extend(r.get("kps_info", []))
            elif "重复" in r.get("error", "") or "跳过" in r.get("error", ""):
                skip += 1
            else:
                fail += 1
                if "费用上限" in r.get("error", ""):
                    break

        if all_kps_info:
            self._check_category_suggestions(all_kps_info)

        self._report_progress(total_files=len(files), current_file=len(files),
                              current_step="完成", total_extracted=total_kps,
                              message="提取完成: %d成功/%d跳过/%d失败, 共%d条知识点" % (ok, skip, fail, total_kps))
        return {"success": True, "ok": ok, "fail": fail, "skip": skip, "total_kps": total_kps,
                "message": "提取完成"}


def main():
    try:
        # v2.1.0-c: 自动检查数据库迁移
        try:
            from scripts.migrate_v210c import migrate
            migrate()
        except ImportError:
            pass  # 迁移脚本不存在，跳过
        # v2.1.0-d F028: 政策依赖校验字段迁移
        try:
            from scripts.migrate_v210d_f028 import migrate as migrate_f028
            migrate_f028()
        except ImportError:
            pass
        # v2.1.1 F038: 举一反三字段迁移
        try:
            from scripts.migrate_v211 import migrate as migrate_v211
            migrate_v211()
        except ImportError:
            pass
        # v2.1.1 F039: 重复检测表迁移
        try:
            from scripts.migrate_v211_dup import migrate as migrate_dup
            migrate_dup()
        except ImportError:
            pass
        # v2.2.3 F057+F058: schema迁移
        try:
            from scripts.migrate_v223 import migrate as migrate_v223
            migrate_v223()
        except ImportError:
            pass
        Extractor().run()
    except KeyboardInterrupt:
        print(f"\n\n  已取消操作。")
    except Exception as e:
        print(f"\n  [ERROR] {e}")
    input("\n按回车键退出...")


if __name__ == "__main__":
    main()
