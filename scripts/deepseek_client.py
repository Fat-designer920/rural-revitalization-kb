"""
deepseek_client.py - DeepSeek API封装 + 硅基流动OCR
路径：scripts/deepseek_client.py
版本：v2.3.3 - 提取系统截断防御重构(D1-D8 落地)

变更说明(v2.3.3):
  D1 R1 max_tokens 显式设 8192(原默认 4K)
  D2 V3 max_tokens 默认从 4096 升 8192
  D3 chat_with_json 启用 response_format={"type":"json_object"} (JSON Mode)
  D4 双保险:同时保留 system_prompt 的"必须 JSON"硬话
  D5 JSON Mode 启用后空 content/解析失败 → 自动降级一次不带 mode 重试
  D7 新增 chat_continue_with_prefix() 走 https://api.deepseek.com/beta 端点
  D8 续写默认走 V3(deepseek-chat),成本降 8 倍
  新增 chat_with_jsonl() — JSON Lines 逐行解析容错,返回 prefix_for_continuation
  保留 _repair_truncated_json — 作为 jsonl 解析失败的最终兜底
"""
import os, sys, json, time, base64, re, requests, tempfile
from pathlib import Path

PROJECT_ROOT = Path(__file__).parent.parent
sys.path.insert(0, str(PROJECT_ROOT))
from scripts.db_manager import DatabaseManager


class CostLimitExceeded(Exception):
    pass


class DeepSeekClient:
    PRICING = {
        "deepseek-chat": {"input": 1.0, "output": 2.0},
        "deepseek-reasoner": {"input": 4.0, "output": 16.0}
    }

    R1_MODELS = {"deepseek-reasoner"}

    def __init__(self, config=None):
        if config is None:
            p = PROJECT_ROOT / "config" / "settings.json"
            if not p.exists():
                raise FileNotFoundError("未找到配置文件,请先运行配置向导")
            with open(p, "r", encoding="utf-8") as f:
                config = json.load(f)
        self.config = config
        self.base_url = config.get("deepseek_base_url", "https://api.deepseek.com")
        self.beta_base_url = config.get("deepseek_beta_url", "https://api.deepseek.com/beta")
        self.model = config.get("deepseek_model", "deepseek-chat")
        self.daily_cost_limit = config.get("daily_cost_limit", 50)
        self.max_retries = 3
        self.timeout = 120
        self.r1_timeout = 300
        if not self.base_url.startswith("https://"):
            raise ValueError("API地址必须HTTPS")
        self.api_key = self._get_api_key()
        self.db = DatabaseManager()

        self.debug_dir = PROJECT_ROOT / "data" / "debug"
        self.debug_dir.mkdir(parents=True, exist_ok=True)

    def _get_api_key(self):
        enc = self.config.get("deepseek_api_key_encrypted", "")
        if not enc:
            raise ValueError("未配置API Key")
        from scripts.config_wizard import decrypt_value
        return decrypt_value(enc)

    def _get_siliconflow_api_key(self):
        enc = self.config.get("siliconflow_api_key_encrypted", "")
        if not enc:
            raise ValueError(
                "未配置硅基流动API Key，请运行配置向导设置。\n"
                "硅基流动API用于扫描件PDF和图片的OCR识别。"
            )
        from scripts.config_wizard import decrypt_value
        return decrypt_value(enc)

    def _check_cost(self):
        cost = self.db.get_today_api_cost()
        if cost >= self.daily_cost_limit:
            raise CostLimitExceeded(
                f"今日API费用已达上限! 已花费:{cost:.2f}元, 上限:{self.daily_cost_limit:.2f}元")
        return cost

    def _estimate_cost(self, model, inp, out):
        p = self.PRICING.get(model, self.PRICING["deepseek-chat"])
        return round((inp / 1e6) * p["input"] + (out / 1e6) * p["output"], 6)

    def _is_r1(self, model):
        return model in self.R1_MODELS

    def _request(self, endpoint, payload, use_model=None, base_url_override=None):
        base = base_url_override or self.base_url
        url = f"{base}/{endpoint.lstrip('/')}"
        headers = {"Authorization": f"Bearer {self.api_key}", "Content-Type": "application/json"}
        timeout = self.r1_timeout if self._is_r1(use_model or self.model) else self.timeout
        last_err = None
        for attempt in range(1, self.max_retries + 1):
            try:
                r = requests.post(url, headers=headers, json=payload, timeout=timeout)
                if r.status_code == 200:
                    return r.json()
                if r.status_code == 401:
                    raise ValueError("API Key无效")
                if r.status_code == 429 or r.status_code >= 500:
                    wait = min(60, 2 ** attempt * 3)
                    print(f"    API错误({r.status_code}), {wait}秒后重试...")
                    time.sleep(wait)
                    last_err = f"HTTP {r.status_code}"
                    continue
                raise Exception(f"API错误({r.status_code}): {r.text[:300]}")
            except requests.exceptions.Timeout:
                wait = min(60, 2 ** attempt * 5)
                print(f"    超时, {wait}秒后重试...")
                time.sleep(wait)
                last_err = "timeout"
            except requests.exceptions.ConnectionError:
                wait = min(60, 2 ** attempt * 5)
                print(f"    网络错误, {wait}秒后重试...")
                time.sleep(wait)
                last_err = "connection"
            except (ValueError, Exception) as e:
                raise
        raise Exception(f"API调用失败(重试{self.max_retries}次): {last_err}")

    def chat(self, system_prompt, user_prompt, temperature=0.3, max_tokens=8192,
             call_type="general", model_override=None, response_format=None,
             extra_messages=None, base_url_override=None, stop=None):
        """v2.3.3 升级:
        - max_tokens 默认 4096 → 8192(D1+D2 R1/V3 输出窗口上限)
        - R1 分支显式传 max_tokens(原代码 pass 等于默认 4K,实测就是截断主因)
        - 新增 response_format(D3 JSON Mode)
        - 新增 extra_messages(D7 Prefix Completion 用,append 到 messages 末尾)
        - 新增 base_url_override(D7 走 beta 端点)
        - 新增 stop(可选停止符)
        """
        self._check_cost()
        use_model = model_override or self.model

        messages = [
            {"role": "system", "content": system_prompt},
            {"role": "user", "content": user_prompt}
        ]
        if extra_messages:
            messages.extend(extra_messages)

        payload = {
            "model": use_model,
            "messages": messages
        }

        # R1 模型:不传 temperature(立规则 15),max_tokens 显式设(D1)
        if self._is_r1(use_model):
            payload["max_tokens"] = max_tokens
        else:
            payload["temperature"] = temperature
            payload["max_tokens"] = max_tokens

        # D3 JSON Mode
        if response_format is not None:
            payload["response_format"] = response_format

        # 可选停止符
        if stop is not None:
            payload["stop"] = stop

        resp = self._request("chat/completions", payload, use_model=use_model,
                             base_url_override=base_url_override)

        msg = resp["choices"][0]["message"]
        content = msg.get("content", "")
        reasoning = msg.get("reasoning_content", "")

        u = resp.get("usage", {})
        inp = u.get("prompt_tokens", 0)
        out = u.get("completion_tokens", 0)

        finish_reason = resp["choices"][0].get("finish_reason", "stop")
        was_truncated = (finish_reason == "length")

        cost = self._estimate_cost(use_model, inp, out)
        self.db.log_api_call(call_type, use_model, inp, out, cost)

        result = {
            "content": content,
            "input_tokens": inp,
            "output_tokens": out,
            "estimated_cost": cost,
            "model": use_model,
            "was_truncated": was_truncated
        }
        if reasoning:
            result["reasoning_content"] = reasoning
        return result

    def _repair_truncated_json(self, text):
        """最后兜底：从截断的JSON中抢救已完成的知识点"""
        kp_match = re.search(r'"knowledge_points"\s*:\s*\[', text)
        if not kp_match:
            return None

        array_start = kp_match.end()
        completed_items = []
        depth = 0
        item_start = -1

        i = array_start
        while i < len(text):
            ch = text[i]
            if ch == '"':
                i += 1
                while i < len(text) and text[i] != '"':
                    if text[i] == '\\':
                        i += 1
                    i += 1
                i += 1
                continue
            if ch == '{':
                if depth == 0:
                    item_start = i
                depth += 1
            elif ch == '}':
                depth -= 1
                if depth == 0 and item_start >= 0:
                    item_text = text[item_start:i + 1]
                    try:
                        item = json.loads(item_text)
                        completed_items.append(item)
                    except json.JSONDecodeError:
                        pass
                    item_start = -1
            i += 1

        if completed_items:
            return {"knowledge_points": completed_items}
        return None

    def _extract_json_robust(self, text, was_truncated=False):
        """增强版JSON提取：7重保险含截断修复"""
        if not text or not text.strip():
            return None, "返回内容为空"

        text = text.strip()

        # 第1步：清理markdown代码块
        cleaned = text
        json_block = re.search(r'```json\s*([\s\S]*?)```', cleaned)
        if json_block:
            cleaned = json_block.group(1).strip()
        else:
            code_block = re.search(r'```\s*([\s\S]*?)```', cleaned)
            if code_block:
                cleaned = code_block.group(1).strip()

        # 第2步：直接解析
        try:
            return json.loads(cleaned), None
        except json.JSONDecodeError:
            pass

        # 第3步：提取JSON对象
        brace_start = cleaned.find("{")
        brace_end = cleaned.rfind("}")
        if brace_start >= 0 and brace_end > brace_start:
            try:
                return json.loads(cleaned[brace_start:brace_end + 1]), None
            except json.JSONDecodeError:
                pass

        # 第4步：提取JSON数组
        bracket_start = cleaned.find("[")
        bracket_end = cleaned.rfind("]")
        if bracket_start >= 0 and bracket_end > bracket_start:
            try:
                return json.loads(cleaned[bracket_start:bracket_end + 1]), None
            except json.JSONDecodeError:
                pass

        # 第5步：从原始文本提取
        if cleaned != text:
            brace_start = text.find("{")
            brace_end = text.rfind("}")
            if brace_start >= 0 and brace_end > brace_start:
                try:
                    return json.loads(text[brace_start:brace_end + 1]), None
                except json.JSONDecodeError:
                    pass

        # 第6步：修复中文标点
        try:
            fixed = cleaned
            if cleaned.find("{") >= 0 and cleaned.rfind("}") > cleaned.find("{"):
                fixed = cleaned[cleaned.find("{"):cleaned.rfind("}") + 1]
            fixed = fixed.replace("\uff1a", ":").replace("\uff0c", ",")
            fixed = fixed.replace("\u201c", '"').replace("\u201d", '"')
            return json.loads(fixed), None
        except (json.JSONDecodeError, Exception):
            pass

        # 第7步：截断修复兜底
        source = cleaned if cleaned.find('"knowledge_points"') >= 0 else text
        repaired = self._repair_truncated_json(source)
        if repaired:
            count = len(repaired.get("knowledge_points", []))
            print(f"       [截断修复] 从不完整输出中抢救出{count}个完整知识点")
            return repaired, None

        return None, "JSON解析失败(已尝试7种方式含截断修复)"

    def _save_debug_output(self, content, call_type):
        try:
            ts = time.strftime("%Y%m%d_%H%M%S")
            debug_file = self.debug_dir / f"json_fail_{call_type}_{ts}.txt"
            with open(debug_file, "w", encoding="utf-8") as f:
                f.write(f"=== JSON解析失败调试信息 ===\n")
                f.write(f"时间: {ts}\n")
                f.write(f"调用类型: {call_type}\n")
                f.write(f"内容长度: {len(content)}字符\n")
                f.write(f"{'=' * 50}\n")
                f.write(f"原始返回内容:\n")
                f.write(content)
            print(f"       调试信息已保存: data/debug/{debug_file.name}")
        except Exception:
            pass

    def chat_with_json(self, system_prompt, user_prompt, temperature=0.1, max_tokens=8192,
                       call_type="json_extract", model_override=None, use_json_mode=True):
        """v2.3.3 升级:
        - max_tokens 默认 4096 → 8192(D2)
        - 默认启用 response_format={"type":"json_object"}(D3 JSON Mode)
        - 双保险:同时保留 system_prompt 的"必须 JSON"硬话(D4)
        - JSON Mode 启用后空 content/解析失败 → 自动降级一次不带 mode 重试(D5)

        参数:
          use_json_mode: True 启用 JSON Mode(默认),False 走老逻辑
        """
        use_model = model_override or self.model

        json_sys = system_prompt + "\n\n【极其重要】你必须且只能输出一个JSON对象，不要输出任何其他文字、解释或说明。不要使用markdown代码块。直接以{开头，以}结尾。"
        response_format = {"type": "json_object"} if use_json_mode else None

        result = self.chat(json_sys, user_prompt, temperature, max_tokens, call_type,
                           model_override=use_model, response_format=response_format)
        content = result["content"]
        was_truncated = result.get("was_truncated", False)

        if was_truncated:
            print(f"       [注意] R1输出被截断(达到模型输出上限),尝试抢救...")

        parsed, error = self._extract_json_robust(content, was_truncated)

        # D5:JSON Mode 启用但 content 异常(空/极短/解析失败) → 降级一次
        if parsed is None and use_json_mode:
            content_abnormal = (not content) or len(content.strip()) < 10
            if content_abnormal:
                print(f"       [JSON Mode 降级] content 异常(空/极短),回退普通模式重试...")
                result_retry = self.chat(json_sys, user_prompt, temperature, max_tokens,
                                         call_type=f"{call_type}_jsonmode_fallback",
                                         model_override=use_model, response_format=None)
                retry_content = result_retry["content"]
                retry_truncated = result_retry.get("was_truncated", False)
                retry_parsed, retry_error = self._extract_json_robust(retry_content, retry_truncated)
                if retry_parsed is not None:
                    result = result_retry
                    content = retry_content
                    was_truncated = retry_truncated
                    parsed = retry_parsed
                    error = retry_error
                    print(f"       [JSON Mode 降级] 重试成功")

        if parsed is not None:
            result["parsed_json"] = parsed
        else:
            result["parsed_json"] = None
            result["json_parse_error"] = error
            self._save_debug_output(content, call_type)
            preview = content[:300] if content else "(空)"
            print(f"       R1原始返回(前300字): {preview}")

        return result

    def chat_with_jsonl(self, system_prompt, user_prompt, temperature=0.2, max_tokens=8192,
                        call_type="jsonl_extract", model_override=None):
        """v2.3.3 新增(D9):JSON Lines 输出专用解析。

        约定:模型每行输出一个独立完整的 JSON 对象,最后一行可选输出 {"_meta":true,...}
        逐行 try parse,任一行解析失败 → 视为该行被截断,后续行丢弃。

        返回 dict(在 chat() 返回基础上增加):
          - parsed_lines: List[dict] 已成功解析的所有行(含 _meta)
          - kp_objects: List[dict] 仅 kp 行(过滤 _meta)
          - meta_object: dict 或 None
          - last_broken_line: str 解析失败的最后一行原文(供 prefix 续写)
          - prefix_for_continuation: str 已生成内容(完整解析行 + 失败行,作为 prefix 续写起点)

        注意:不启用 response_format JSON Mode。JSON Mode 期望单一 JSON 对象,
        与 JSON Lines 多行多对象冲突。靠 system_prompt 强约束 + 行级容错。
        """
        use_model = model_override or self.model
        result = self.chat(system_prompt, user_prompt, temperature, max_tokens, call_type,
                           model_override=use_model)
        content = result.get("content", "") or ""
        was_truncated = result.get("was_truncated", False)

        # 清理 markdown 代码块包装(R1 偶尔会包 ```json ... ```)
        cleaned = content.strip()
        cb = re.search(r'```(?:json)?\s*([\s\S]*?)```', cleaned)
        if cb:
            cleaned = cb.group(1).strip()

        parsed_lines = []
        kp_objects = []
        meta_object = None
        last_broken_line = ""
        completed_text_parts = []  # 累积已完整解析的行原文(供 prefix 续写)

        lines = cleaned.split("\n")
        for raw_line in lines:
            line = raw_line.strip()
            if not line:
                continue
            try:
                obj = json.loads(line)
                if isinstance(obj, dict):
                    parsed_lines.append(obj)
                    if obj.get("_meta") is True:
                        meta_object = obj
                    else:
                        kp_objects.append(obj)
                    completed_text_parts.append(raw_line)
                else:
                    # 非 dict 行:不计入 kp,但仍保留原文(防止 prefix 续写位置漂移)
                    completed_text_parts.append(raw_line)
            except json.JSONDecodeError:
                # 单行解析失败 — 大概率是截断到行中间
                last_broken_line = raw_line
                break  # 后续若有行也丢弃,以截断点为界

        # prefix_for_continuation = 已完整行(行尾换行)+ 失败行(原样,供续写补完)
        prefix_for_continuation = ""
        if completed_text_parts:
            prefix_for_continuation = "\n".join(completed_text_parts) + "\n"
        if last_broken_line:
            prefix_for_continuation += last_broken_line

        result["parsed_lines"] = parsed_lines
        result["kp_objects"] = kp_objects
        result["meta_object"] = meta_object
        result["last_broken_line"] = last_broken_line
        result["prefix_for_continuation"] = prefix_for_continuation
        return result

    def chat_continue_with_prefix(self, system_prompt, user_prompt, prefix_content,
                                  max_tokens=8192, call_type="prefix_continue",
                                  model_override=None, stop=None):
        """v2.3.3 新增(D7):Chat Prefix Completion(走 beta 端点)。

        DeepSeek 官方契约:
        - 必须 base_url=https://api.deepseek.com/beta
        - messages 最后一条必须 role=assistant + prefix=True
        - 模型从 prefix_content 末尾续写

        默认走 V3(deepseek-chat),续写是格式接力不是创造,V3 够用且成本降 8 倍(D8)。
        调用方可通过 model_override 强制走 R1。

        返回 dict 同 chat()(content 是续写部分,不含 prefix)。
        """
        self._check_cost()
        # D8:续写默认走 V3
        use_model = model_override or "deepseek-chat"

        messages = [
            {"role": "system", "content": system_prompt},
            {"role": "user", "content": user_prompt},
            {"role": "assistant", "content": prefix_content, "prefix": True}
        ]

        payload = {
            "model": use_model,
            "messages": messages,
            "max_tokens": max_tokens,
        }
        if not self._is_r1(use_model):
            payload["temperature"] = 0.2
        if stop is not None:
            payload["stop"] = stop

        # 走 beta 端点(必需)
        resp = self._request("chat/completions", payload, use_model=use_model,
                             base_url_override=self.beta_base_url)

        msg = resp["choices"][0]["message"]
        content = msg.get("content", "")
        reasoning = msg.get("reasoning_content", "")
        u = resp.get("usage", {})
        inp = u.get("prompt_tokens", 0)
        out = u.get("completion_tokens", 0)
        finish_reason = resp["choices"][0].get("finish_reason", "stop")
        was_truncated = (finish_reason == "length")
        cost = self._estimate_cost(use_model, inp, out)
        self.db.log_api_call(call_type, use_model, inp, out, cost)

        result = {
            "content": content,
            "input_tokens": inp,
            "output_tokens": out,
            "estimated_cost": cost,
            "model": use_model,
            "was_truncated": was_truncated
        }
        if reasoning:
            result["reasoning_content"] = reasoning
        return result

    # ============================================================
    # 硅基流动OCR（扫描件PDF + 图片识别）
    # ============================================================

    def ocr_image(self, file_path, call_type="ocr"):
        """
        OCR识别入口：自动判断文件类型。
        - PDF文件：逐页渲染为图片后OCR
        - 图片文件：直接OCR
        使用硅基流动视觉模型（Qwen2.5-VL-72B-Instruct）
        """
        ext = Path(file_path).suffix.lower()
        if ext == ".pdf":
            return self._ocr_pdf(file_path, call_type)
        else:
            return self._ocr_single_image(file_path, call_type)

    def _ocr_single_image(self, image_path, call_type="ocr"):
        """用硅基流动视觉模型OCR识别单张图片"""
        sf_key = self._get_siliconflow_api_key()
        sf_base = self.config.get("siliconflow_base_url", "https://api.siliconflow.cn/v1")
        sf_model = self.config.get("siliconflow_model", "Qwen/Qwen2.5-VL-72B-Instruct")

        with open(image_path, "rb") as f:
            b64 = base64.b64encode(f.read()).decode("utf-8")
        ext = Path(image_path).suffix.lower()
        mime_map = {
            ".jpg": "image/jpeg", ".jpeg": "image/jpeg",
            ".png": "image/png", ".bmp": "image/bmp"
        }
        mime = mime_map.get(ext, "image/png")

        payload = {
            "model": sf_model,
            "messages": [
                {"role": "system",
                 "content": "你是OCR专家。请精确识别图片中所有文字，保持原始排版和层级结构。如有表格，用markdown表格格式输出。"},
                {"role": "user", "content": [
                    {"type": "image_url", "image_url": {"url": f"data:{mime};base64,{b64}"}},
                    {"type": "text", "text": "请识别图片中的所有文字，保持原始排版。如有表格请保留表格结构。"}
                ]}
            ],
            "max_tokens": 4096
        }

        headers = {"Authorization": f"Bearer {sf_key}", "Content-Type": "application/json"}
        url = f"{sf_base}/chat/completions"

        last_err = None
        for attempt in range(1, self.max_retries + 1):
            try:
                r = requests.post(url, headers=headers, json=payload, timeout=self.timeout)
                if r.status_code == 200:
                    resp = r.json()
                    content = resp["choices"][0]["message"]["content"]
                    u = resp.get("usage", {})
                    inp = u.get("prompt_tokens", 0)
                    out = u.get("completion_tokens", 0)
                    # 硅基流动费用估算(Qwen2.5-VL-72B约4元/百万token)
                    cost = round((inp + out) * 4.0 / 1e6, 6)
                    self.db.log_api_call(call_type, sf_model, inp, out, cost)
                    return {
                        "content": content,
                        "input_tokens": inp,
                        "output_tokens": out,
                        "estimated_cost": cost
                    }
                if r.status_code == 401:
                    raise ValueError("硅基流动API Key无效，请在配置向导中重新设置")
                if r.status_code == 429 or r.status_code >= 500:
                    wait = min(60, 2 ** attempt * 3)
                    print(f"    硅基流动API错误({r.status_code}), {wait}秒后重试...")
                    time.sleep(wait)
                    last_err = f"HTTP {r.status_code}"
                    continue
                raise Exception(f"硅基流动API错误({r.status_code}): {r.text[:300]}")
            except requests.exceptions.Timeout:
                wait = min(60, 2 ** attempt * 5)
                print(f"    硅基流动超时, {wait}秒后重试...")
                time.sleep(wait)
                last_err = "timeout"
            except requests.exceptions.ConnectionError:
                wait = min(60, 2 ** attempt * 5)
                print(f"    硅基流动网络错误, {wait}秒后重试...")
                time.sleep(wait)
                last_err = "connection"
            except (ValueError, Exception) as e:
                raise
        raise Exception(f"硅基流动OCR失败(重试{self.max_retries}次): {last_err}")

    def _ocr_pdf(self, pdf_path, call_type="ocr"):
        """扫描件PDF OCR：用pymupdf逐页渲染为图片，再调硅基流动识别"""
        try:
            import fitz  # pymupdf
        except ImportError:
            raise ImportError(
                "缺少pymupdf库，请运行: pip install pymupdf\n"
                "pymupdf用于将扫描件PDF渲染为图片以便OCR识别。"
            )

        doc = fitz.open(pdf_path)
        total_pages = len(doc)
        print(f"     扫描件PDF共{total_pages}页，逐页OCR中...")

        all_text = []
        total_cost = 0
        total_inp = 0
        total_out = 0

        for i in range(total_pages):
            page = doc[i]
            print(f"     OCR第{i + 1}/{total_pages}页...", end="", flush=True)

            # 渲染为图片(200 DPI，平衡清晰度和文件大小)
            mat = fitz.Matrix(200 / 72, 200 / 72)
            pix = page.get_pixmap(matrix=mat)

            # 保存临时PNG文件
            tmp_path = None
            try:
                with tempfile.NamedTemporaryFile(suffix=".png", delete=False) as tmp:
                    tmp_path = tmp.name
                pix.save(tmp_path)

                result = self._ocr_single_image(tmp_path, call_type)
                page_text = result.get("content", "")
                if page_text and page_text.strip():
                    all_text.append(f"[第{i + 1}页]\n{page_text.strip()}")
                total_cost += result.get("estimated_cost", 0)
                total_inp += result.get("input_tokens", 0)
                total_out += result.get("output_tokens", 0)
                print(f" OK")
            except Exception as e:
                print(f" 失败({e})")
            finally:
                if tmp_path:
                    try:
                        os.unlink(tmp_path)
                    except Exception:
                        pass

        doc.close()

        content = "\n\n".join(all_text)
        print(f"     OCR完成! 识别{len(all_text)}/{total_pages}页, 费用~{total_cost:.4f}元")
        return {
            "content": content,
            "input_tokens": total_inp,
            "output_tokens": total_out,
            "estimated_cost": total_cost
        }

    def get_today_usage(self):
        cost = self.db.get_today_api_cost()
        return {
            "today_cost": round(cost, 4),
            "daily_limit": self.daily_cost_limit,
            "remaining": round(self.daily_cost_limit - cost, 4),
            "usage_percent": round((cost / self.daily_cost_limit) * 100, 1)
        }
