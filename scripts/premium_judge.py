# -*- coding: utf-8 -*-
"""
premium_judge.py - 精品候选 AI 判定引擎

版本: v2.3.5-part2-hotfix1.1 - 版本统一(Claude Code 系统修复)

职责:对所有"可引用级"(content_readiness IN ('quotable','premium'))的 kp,
    分别从"客户视角"和"投标视角"调用 V3 AI 判定精品资格,结果写 premium_ai_cache 表。

设计决策(Phase 2 冻结档案 §6):
  - 方案 B:两条独立 Prompt(CLIENT + RFP),不合并一次调用
  - N=1:单条调用,不批处理(老唐 Phase 2 选择,稳定性优先)
  - 两视角独立判:同一条 kp 可能 client=strong + rfp=not(允许视角分化)
  - 强推门槛不在 AI 侧实现,由前端按 composite_score Top 10-15% 标 strong

三级降级链(§6.3):
  主链: _call_v3(CLIENT_PROMPT / RFP_PROMPT) 单条调用
   └ JSON 解析失败 / 字段非法 → L1: 同条重试 1 次
   └ 仍失败 → L2: 本地规则兜底
         client: qa>=4.5 AND has_annotation → optional, 其他 → not
         rfp:    source_authority IN ('official','authoritative') → optional, 其他 → not
         source='rule_fallback',便于审计

对齐 health_checker.py 架构:
  - 五方法两签名 V3 适配器
  - _safe_log_event 事件埋点(立规则 4)
  - 成本累计与 _v3_call_count 计数

运行量级(Phase 2 冻结档案):
  - 2000+ quotable kp × 2 视角 = 4000 次 AI 调用
  - 预估 40-60 分钟 / 7-10 元(单条调用延迟 ~6-8 秒)
  - 进度每 10 条上报一次(前端 2 秒轮询看得到动)

立规则对齐:
  第 4 条:关键操作必记 operation_events(start/done/failed)
  第 9 条:调用 db 方法前对照真实签名(见 db_manager.py v2.3.1 新增 7 方法)
  第 11 条:Prompt 顶层裸 import,禁 try/except 静默降级
  第 18 条:AI 客户端五方法两签名适配器
  第 21 条:模块支持 headless(progress_callback=None 兜底)
  第 50 条:跨模块 import 双路径兜底
"""

import json
import sys
from typing import Dict, List, Optional, Callable, Any

# --- 立规则 11:Prompt 顶层裸 import,不 try/except None 兜底 ---
# --- 立规则 50 第 6 项:跨模块 import 双路径兜底(scripts.xxx vs 裸模块)---
try:
    from scripts.prompts.prompt_templates import (
        PREMIUM_JUDGE_CLIENT_PROMPT,
        PREMIUM_JUDGE_RFP_PROMPT,
        PROMPT_VERSION,
    )
except ImportError:
    from prompts.prompt_templates import (
        PREMIUM_JUDGE_CLIENT_PROMPT,
        PREMIUM_JUDGE_RFP_PROMPT,
        PROMPT_VERSION,
    )


# V3 模型成本粗估(元/百万 token):DeepSeek V3 官方标准价
V3_PRICE_INPUT_PER_M = 2.0    # 输入 token 单价
V3_PRICE_OUTPUT_PER_M = 8.0   # 输出 token 单价
V3_TEMPERATURE = 0.1          # V3 判定温度(对齐 health_checker)
V3_TIMEOUT_PER_CALL = 60      # 单次超时(秒)

# 三级降级链常量
L1_RETRY_ONCE = True          # 主链失败同条重试 1 次
AI_METHOD_CANDIDATES = ('call_chat', 'chat', 'complete', 'call', 'generate')


class PremiumJudgeEngine:
    """F2 精品候选 AI 判定引擎.

    入口: run_refresh() -> dict(汇总结果)

    状态:
      _v3_call_count:  AI 调用次数
      _cost:           累计成本(元)
      _ai_success:     AI 成功写 cache 次数
      _rule_fallback:  规则兜底写 cache 次数
      _failed_records: 失败记录(每条含 kp_id/view/reason),最多保留 50 条供审计
    """

    def __init__(self, db, client,
                 progress_callback: Optional[Callable[[Dict], None]] = None,
                 cancel_check: Optional[Callable[[], bool]] = None):
        self.db = db
        self.client = client
        self.progress_callback = progress_callback or (lambda x: None)
        self.cancel_check = cancel_check or (lambda: False)
        # 统计
        self._v3_call_count = 0
        self._cost = 0.0
        self._ai_success = 0
        self._rule_fallback = 0
        self._failed_records: List[Dict] = []

    # ================================================================
    # 主入口
    # ================================================================
    def run_refresh(self) -> Dict[str, Any]:
        """执行一次完整的精品刷新.

        步骤:
          1. 取候选池 (db.get_premium_judge_candidates)
          2. 逐条 × 两视角 AI 判定
          3. 每 10 条回调一次 progress
          4. 检测 cancel_check(),True 时优雅退出
          5. 汇总结果返回

        返回字段:
          ok / total_kps / processed_kps / ai_success / rule_fallback_count /
          total_ai_calls / total_cost_cny / canceled / failed_records(最多 50)
        """
        self._safe_log_event("premium_refresh_start", "info", {
            "prompt_version": PROMPT_VERSION,
        })

        # Step 1: 取候选
        try:
            candidates = self.db.get_premium_judge_candidates()
        except Exception as e:
            self._safe_log_event("premium_refresh_failed", "error", {
                "stage": "get_candidates", "error": str(e)[:300],
            })
            return {
                "ok": False, "error": "get_candidates 失败: " + str(e)[:200],
                "total_kps": 0, "processed_kps": 0,
            }

        total = len(candidates)
        self.progress_callback({
            "total_kps": total,
            "processed_kps": 0,
            "current_view": "",
            "ai_calls_count": 0,
            "cost_estimate_cny": 0.0,
            "current_step": "初始化",
            "message": "候选 %d 条, 开始两视角判定..." % total,
        })

        if total == 0:
            self._safe_log_event("premium_refresh_done", "info", {
                "total_kps": 0, "note": "无候选,跳过判定",
            })
            return {
                "ok": True, "total_kps": 0, "processed_kps": 0,
                "ai_success": 0, "rule_fallback_count": 0,
                "total_ai_calls": 0, "total_cost_cny": 0.0,
                "canceled": False, "failed_records": [],
            }

        # Step 2: 遍历候选,每条跑两视角
        canceled = False
        processed = 0
        for i, kp in enumerate(candidates):
            # 检查取消
            if self.cancel_check():
                canceled = True
                self._safe_log_event("premium_refresh_canceled", "warning", {
                    "processed_kps": processed, "total_kps": total,
                })
                break

            # 两视角判定
            self._judge_one_kp(kp, "client")
            self._judge_one_kp(kp, "rfp")
            processed = i + 1

            # Step 3: 每 10 条或到末尾回调一次 progress
            if processed % 10 == 0 or processed == total:
                self.progress_callback({
                    "processed_kps": processed,
                    "total_kps": total,
                    "current_view": "client+rfp",
                    "ai_calls_count": self._v3_call_count,
                    "cost_estimate_cny": round(self._cost, 4),
                    "current_step": "判定中",
                    "message": "已处理 %d/%d 条" % (processed, total),
                })

        # Step 4: 汇总
        result = {
            "ok": True,
            "total_kps": total,
            "processed_kps": processed,
            "ai_success": self._ai_success,
            "rule_fallback_count": self._rule_fallback,
            "total_ai_calls": self._v3_call_count,
            "total_cost_cny": round(self._cost, 4),
            "canceled": canceled,
            "failed_records": self._failed_records[:50],
        }

        if canceled:
            # 已经在循环里打过 canceled 事件
            pass
        else:
            self._safe_log_event("premium_refresh_done", "info", {
                "total_kps": total, "processed": processed,
                "ai_success": self._ai_success,
                "rule_fallback": self._rule_fallback,
                "ai_calls": self._v3_call_count,
                "cost_cny": round(self._cost, 4),
            })

        # 最终进度回调(告知完成)
        self.progress_callback({
            "processed_kps": processed,
            "total_kps": total,
            "ai_calls_count": self._v3_call_count,
            "cost_estimate_cny": round(self._cost, 4),
            "current_step": "已完成" if not canceled else "已取消",
            "message": "完成 %d/%d, 成功 %d, 规则兜底 %d" % (
                processed, total, self._ai_success, self._rule_fallback
            ),
        })
        return result

    # ================================================================
    # 单条 × 单视角判定(含 L1 重试 + L2 规则兜底)
    # ================================================================
    def _judge_one_kp(self, kp: Dict, view: str) -> None:
        """判定一条 kp 的一个视角.

        流程:
          主链 → L1(失败重试 1 次) → L2(规则兜底)
        结果:写入 premium_ai_cache 表
        """
        kp_id = kp.get("kp_id")
        if view == "client":
            sys_p = PREMIUM_JUDGE_CLIENT_PROMPT["system_prompt"]
            usr_tpl = PREMIUM_JUDGE_CLIENT_PROMPT["user_prompt_template"]
        elif view == "rfp":
            sys_p = PREMIUM_JUDGE_RFP_PROMPT["system_prompt"]
            usr_tpl = PREMIUM_JUDGE_RFP_PROMPT["user_prompt_template"]
        else:
            return

        try:
            user_prompt = self._build_user_prompt(usr_tpl, kp)
        except Exception as e:
            self._safe_log_event("premium_ai_call_failed", "warning", {
                "kp_id": kp_id, "view": view,
                "error": "prompt 构建失败: " + str(e)[:200],
            })
            self._write_rule_fallback(kp, view, reason_hint="prompt 构建异常")
            return

        # 主链调用
        parsed = self._call_and_parse(sys_p, user_prompt, view, retry=False)

        # L1: 失败同条重试 1 次
        if parsed is None and L1_RETRY_ONCE:
            parsed = self._call_and_parse(sys_p, user_prompt, view, retry=True)

        # L2: 规则兜底
        if parsed is None:
            self._write_rule_fallback(kp, view, reason_hint="AI 两次调用均失败")
            return

        # 成功路径:写 ai cache
        try:
            self.db.upsert_premium_ai_cache(
                kp_id=kp_id,
                view=view,
                recommendation=parsed["recommendation"],
                reason=parsed["reason"],
                score=parsed["score"],
                source="ai",
            )
            self._ai_success += 1
        except Exception as e:
            self._safe_log_event("premium_ai_call_failed", "warning", {
                "kp_id": kp_id, "view": view,
                "error": "upsert_premium_ai_cache 失败: " + str(e)[:200],
            })
            self._record_failure(kp_id, view, "upsert_failed")

    # ================================================================
    # Prompt 构造
    # ================================================================
    def _build_user_prompt(self, template: str, kp: Dict) -> str:
        """把 kp dict 填入 user_prompt_template.

        占位符对齐 PREMIUM_JUDGE_*_PROMPT 契约:
          {filename} / {category_path} / {source_authority} /
          {qa_score} / {has_annotation} / {kp_content_json}
        """
        cat = kp.get("category") or "未分类"
        subcat = kp.get("subcategory") or ""
        category_path = (cat + " / " + subcat) if subcat else cat

        # kp_content_json: 精简传给 AI(避免 token 爆炸,保留判定关键信息)
        ai_content = kp.get("ai_extracted_content") or {}
        key_points = ai_content.get("key_points") if isinstance(ai_content, dict) else []
        content_payload = {
            "title": kp.get("title") or "",
            "excerpt": (kp.get("original_excerpt") or "")[:800],
            "key_points": key_points if isinstance(key_points, list) else [],
            "practical_insights": kp.get("practical_insights") or [],
            "tags": kp.get("final_category_tags") or [],
        }
        content_json = json.dumps(content_payload, ensure_ascii=False, indent=2)
        if len(content_json) > 3000:
            content_json = content_json[:3000] + "..."

        filename = (kp.get("renamed_filename")
                    or kp.get("original_filename")
                    or "未知来源")
        source_authority = kp.get("source_authority") or "unknown"
        qa_score = kp.get("qa_score") or 0.0
        has_annot = "是" if kp.get("has_annotation") else "否"

        return template.format(
            filename=filename,
            category_path=category_path,
            source_authority=source_authority,
            qa_score=qa_score,
            has_annotation=has_annot,
            kp_content_json=content_json,
        )

    # ================================================================
    # 单次调用 + 解析
    # ================================================================
    def _call_and_parse(self, system_prompt: str, user_prompt: str,
                         view: str, retry: bool = False) -> Optional[Dict]:
        """调用 V3 + 解析 JSON + 字段校验.

        返回规范化 dict {recommendation, reason, score} 或 None.
        """
        try:
            raw = self._call_v3(system_prompt, user_prompt, timeout=V3_TIMEOUT_PER_CALL)
        except Exception as e:
            # 只在首次失败时记事件(避免重试也刷屏)
            if not retry:
                self._safe_log_event("premium_ai_call_failed", "warning", {
                    "view": view, "retry": retry, "error": str(e)[:200],
                })
            return None

        if not raw:
            return None

        parsed = self._parse_json_loose(raw)
        if not parsed:
            if not retry:
                self._safe_log_event("premium_ai_call_failed", "warning", {
                    "view": view, "retry": retry,
                    "error": "JSON 解析失败", "raw_excerpt": str(raw)[:200],
                })
            return None

        # 字段校验
        rec = parsed.get("recommendation")
        if rec not in ("strong", "optional", "not"):
            return None
        score = parsed.get("score")
        if not isinstance(score, (int, float)):
            try:
                score = float(score) if score is not None else None
            except (ValueError, TypeError):
                score = None
        if score is None:
            return None
        # 规范化到 0-100
        score = max(0.0, min(100.0, float(score)))
        reason = (parsed.get("reason") or "")[:200]

        return {"recommendation": rec, "reason": reason, "score": score}

    # ================================================================
    # V3 适配器(五方法两签名,立规则 18)
    # ================================================================
    def _call_v3(self, system_prompt: str, user_prompt: str,
                 timeout: int = V3_TIMEOUT_PER_CALL) -> Optional[str]:
        """调用 V3 模型,返回文本.

        五方法顺序:call_chat / chat / complete / call / generate
        两签名顺序:messages= 列表 / system_prompt=/user_prompt= 关键字
        """
        if self.client is None:
            raise RuntimeError("AI 客户端未注入")

        last_err = None
        for method_name in AI_METHOD_CANDIDATES:
            if not hasattr(self.client, method_name):
                continue
            method = getattr(self.client, method_name)

            # 签名 A: messages= 数组
            msgs = [
                {"role": "system", "content": system_prompt},
                {"role": "user", "content": user_prompt},
            ]
            for kwargs in (
                {"messages": msgs, "model": "deepseek-chat",
                 "temperature": V3_TEMPERATURE, "timeout": timeout},
                # 签名 B: 独立 system_prompt/user_prompt 参数
                {"system_prompt": system_prompt, "user_prompt": user_prompt,
                 "model_override": "deepseek-chat",
                 "temperature": V3_TEMPERATURE, "timeout": timeout},
                {"system_prompt": system_prompt, "user_prompt": user_prompt,
                 "temperature": V3_TEMPERATURE, "timeout": timeout},
            ):
                try:
                    result = method(**kwargs)
                    content, usage = self._normalize_result(result)
                    self._v3_call_count += 1
                    if usage:
                        self._accumulate_cost(usage)
                    return content
                except TypeError as e:
                    # 签名不匹配,继续试下一个
                    last_err = e
                    continue
                except Exception as e:
                    # 真实调用异常,中断本方法后继续下一个方法
                    last_err = e
                    break

        # 所有方法都不行
        raise RuntimeError("所有 AI 客户端适配尝试失败: " + str(last_err)[:200]
                           if last_err else "未找到可用方法")

    def _normalize_result(self, result):
        """AI 客户端返回值标准化为 (content, usage)."""
        if isinstance(result, tuple) and len(result) == 2:
            return result[0], result[1]
        if isinstance(result, dict):
            content = result.get("content") or result.get("text") or result.get("output") or ""
            usage = result.get("usage")
            return content, usage
        if isinstance(result, str):
            return result, None
        return str(result), None

    def _accumulate_cost(self, usage):
        """累计 V3 成本(元)."""
        if not isinstance(usage, dict):
            return
        in_tok = (usage.get("prompt_tokens")
                  or usage.get("input_tokens") or 0)
        out_tok = (usage.get("completion_tokens")
                   or usage.get("output_tokens") or 0)
        try:
            self._cost += (float(in_tok) * V3_PRICE_INPUT_PER_M
                           + float(out_tok) * V3_PRICE_OUTPUT_PER_M) / 1_000_000.0
        except (ValueError, TypeError):
            pass

    # ================================================================
    # JSON 容错解析
    # ================================================================
    @staticmethod
    def _parse_json_loose(text: str) -> Optional[Dict]:
        """容错 JSON 解析:剥离 ``` 包裹 + 提取第一个 {...} 块."""
        if not text:
            return None
        t = text.strip()
        # 剥离 ```json ... ``` 包裹
        if t.startswith("```"):
            lines = t.split("\n")
            # 去首行 ``` 和可能的末行 ```
            if lines[-1].strip() == "```":
                t = "\n".join(lines[1:-1])
            else:
                t = "\n".join(lines[1:])
        # 直接尝试
        try:
            return json.loads(t)
        except (ValueError, TypeError):
            pass
        # 找第一个 { 到最后一个 }
        i = t.find("{")
        j = t.rfind("}")
        if i >= 0 and j > i:
            try:
                return json.loads(t[i:j + 1])
            except (ValueError, TypeError):
                return None
        return None

    # ================================================================
    # 规则兜底(L2)
    # ================================================================
    def _write_rule_fallback(self, kp: Dict, view: str, reason_hint: str = "") -> None:
        """L2 本地规则兜底,写入 premium_ai_cache 表(source='rule_fallback').

        规则来自 Phase 2 冻结档案 §6.3:
          client: qa>=4.5 AND has_annotation → optional, 其他 → not
          rfp:    source_authority IN ('official','authoritative') → optional, 其他 → not
          score: 50(中位数,不污染排序)
        """
        kp_id = kp.get("kp_id")
        if view == "client":
            qa = kp.get("qa_score") or 0.0
            has_annot = bool(kp.get("has_annotation"))
            if qa >= 4.5 and has_annot:
                rec = "optional"
                reason = "AI 判定失败,规则兜底(质检高且有注解)"
            else:
                rec = "not"
                reason = "AI 判定失败,规则兜底"
        else:  # rfp
            auth = kp.get("source_authority") or ""
            if auth in ("official", "authoritative"):
                rec = "optional"
                reason = "AI 判定失败,规则兜底(权威级别合格)"
            else:
                rec = "not"
                reason = "AI 判定失败,规则兜底"

        try:
            self.db.upsert_premium_ai_cache(
                kp_id=kp_id, view=view,
                recommendation=rec, reason=reason, score=50.0,
                source="rule_fallback",
            )
            self._rule_fallback += 1
        except Exception as e:
            self._safe_log_event("premium_ai_call_failed", "warning", {
                "kp_id": kp_id, "view": view,
                "error": "rule_fallback upsert 失败: " + str(e)[:200],
            })

        self._record_failure(kp_id, view, reason_hint or "rule_fallback")

    def _record_failure(self, kp_id, view: str, reason: str):
        """记一条失败,最多保留前 50 条供汇总."""
        if len(self._failed_records) >= 50:
            return
        self._failed_records.append({
            "kp_id": kp_id, "view": view, "reason": reason,
        })

    # ================================================================
    # 事件日志(立规则 4 / 14)
    # ================================================================
    def _safe_log_event(self, event_type: str, severity: str, payload: Dict) -> None:
        """封装 db.log_operation_event,失败不抛.

        severity 强制校验三态 info/warning/error(立规则 14).
        """
        if severity not in ("info", "warning", "error"):
            severity = "warning"
        try:
            self.db.log_operation_event(
                event_type=event_type,
                module="premium_judge",
                severity=severity,
                payload=payload,
            )
        except Exception:
            # 日志失败不阻塞主流程
            pass


# ================================================================
# 模块级便捷入口(对齐 health_checker.run_health_check 模式)
# ================================================================
def run_premium_refresh(db, client,
                         progress_callback: Optional[Callable[[Dict], None]] = None,
                         cancel_check: Optional[Callable[[], bool]] = None) -> Dict:
    """模块级便捷函数,供 api_server 调用.

    调用方式:
      from scripts.premium_judge import run_premium_refresh
      result = run_premium_refresh(db, client,
                                    progress_callback=cb,
                                    cancel_check=lambda: _premium_task['cancel_requested'])
    """
    engine = PremiumJudgeEngine(db, client, progress_callback, cancel_check)
    return engine.run_refresh()
