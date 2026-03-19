"""
deepseek_client.py - DeepSeek API封装
路径：scripts/deepseek_client.py
版本：v1.0.1 - R1模型支持 + 增强JSON解析容错
"""
import os, sys, json, time, base64, re, requests
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

    # R1模型不支持temperature参数，需要更长超时（思考过程耗时长）
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
        self.model = config.get("deepseek_model", "deepseek-chat")
        self.daily_cost_limit = config.get("daily_cost_limit", 50)
        self.max_retries = 3
        self.timeout = 120
        self.r1_timeout = 300  # R1模型超时5分钟（思考过程较长）
        if not self.base_url.startswith("https://"):
            raise ValueError("API地址必须HTTPS")
        self.api_key = self._get_api_key()
        self.db = DatabaseManager()

        # 调试输出目录
        self.debug_dir = PROJECT_ROOT / "data" / "debug"
        self.debug_dir.mkdir(parents=True, exist_ok=True)

    def _get_api_key(self):
        enc = self.config.get("deepseek_api_key_encrypted", "")
        if not enc:
            raise ValueError("未配置API Key")
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
        """判断是否为R1推理模型"""
        return model in self.R1_MODELS

    def _request(self, endpoint, payload, use_model=None):
        url = f"{self.base_url}/{endpoint.lstrip('/')}"
        headers = {"Authorization": f"Bearer {self.api_key}", "Content-Type": "application/json"}
        # R1模型用更长的超时时间
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

    def chat(self, system_prompt, user_prompt, temperature=0.3, max_tokens=4096,
             call_type="general", model_override=None):
        """
        通用聊天接口。
        model_override: 指定模型,不传则用配置文件中的默认模型。
                        传 "deepseek-reasoner" 则使用R1模型。
        """
        self._check_cost()
        use_model = model_override or self.model

        payload = {
            "model": use_model,
            "messages": [
                {"role": "system", "content": system_prompt},
                {"role": "user", "content": user_prompt}
            ],
            "max_tokens": max_tokens
        }

        # R1模型不支持temperature参数
        if not self._is_r1(use_model):
            payload["temperature"] = temperature

        resp = self._request("chat/completions", payload, use_model=use_model)

        # 提取回复内容
        msg = resp["choices"][0]["message"]
        content = msg.get("content", "")

        # R1模型会返回思考过程(reasoning_content)，记录但不混入正文
        reasoning = msg.get("reasoning_content", "")

        # 提取token用量
        u = resp.get("usage", {})
        inp = u.get("prompt_tokens", 0)
        out = u.get("completion_tokens", 0)

        cost = self._estimate_cost(use_model, inp, out)
        self.db.log_api_call(call_type, use_model, inp, out, cost)

        result = {
            "content": content,
            "input_tokens": inp,
            "output_tokens": out,
            "estimated_cost": cost,
            "model": use_model
        }
        if reasoning:
            result["reasoning_content"] = reasoning

        return result

    def _extract_json_robust(self, text):
        """
        增强版JSON提取：R1模型经常在JSON前后加解释文字，需要智能提取。
        按优先级依次尝试多种方式。
        """
        if not text or not text.strip():
            return None, "返回内容为空"

        text = text.strip()

        # 第1步：清理markdown代码块包裹
        cleaned = text
        # 处理 ```json ... ``` 包裹
        json_block = re.search(r'```json\s*([\s\S]*?)```', cleaned)
        if json_block:
            cleaned = json_block.group(1).strip()
        else:
            # 处理 ``` ... ``` 包裹
            code_block = re.search(r'```\s*([\s\S]*?)```', cleaned)
            if code_block:
                cleaned = code_block.group(1).strip()

        # 第2步：直接尝试解析（最理想的情况）
        try:
            return json.loads(cleaned), None
        except json.JSONDecodeError:
            pass

        # 第3步：提取最外层的JSON对象 { ... }
        # 找到第一个 { 和最后一个 } 之间的内容
        brace_start = cleaned.find("{")
        brace_end = cleaned.rfind("}")
        if brace_start >= 0 and brace_end > brace_start:
            try:
                candidate = cleaned[brace_start:brace_end + 1]
                return json.loads(candidate), None
            except json.JSONDecodeError:
                pass

        # 第4步：提取最外层的JSON数组 [ ... ]
        bracket_start = cleaned.find("[")
        bracket_end = cleaned.rfind("]")
        if bracket_start >= 0 and bracket_end > bracket_start:
            try:
                candidate = cleaned[bracket_start:bracket_end + 1]
                return json.loads(candidate), None
            except json.JSONDecodeError:
                pass

        # 第5步：尝试从原始文本（不清理代码块）中提取
        if cleaned != text:
            brace_start = text.find("{")
            brace_end = text.rfind("}")
            if brace_start >= 0 and brace_end > brace_start:
                try:
                    candidate = text[brace_start:brace_end + 1]
                    return json.loads(candidate), None
                except json.JSONDecodeError:
                    pass

        # 第6步：尝试修复常见的JSON格式问题
        # R1有时会在JSON中使用中文标点
        try:
            fixed = cleaned
            if brace_start >= 0 and brace_end > brace_start:
                fixed = cleaned[brace_start:brace_end + 1]
            # 替换常见的中文标点为英文
            fixed = fixed.replace("\uff1a", ":").replace("\uff0c", ",")
            fixed = fixed.replace("\u201c", '"').replace("\u201d", '"')
            fixed = fixed.replace("\u2018", "'").replace("\u2019", "'")
            return json.loads(fixed), None
        except (json.JSONDecodeError, Exception):
            pass

        # 全部失败
        return None, "JSON解析失败(已尝试6种方式)"

    def _save_debug_output(self, content, call_type):
        """解析失败时保存原始输出，方便排查"""
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

    def chat_with_json(self, system_prompt, user_prompt, temperature=0.1, max_tokens=4096,
                       call_type="json_extract", model_override=None):
        """
        聊天并解析JSON输出。
        R1模型时：max_tokens自动提高到8192以容纳更细粒度的输出。
        增强版JSON解析：支持R1模型的自由格式输出。
        """
        use_model = model_override or self.model

        # R1模型做提取时，输出通常更长，提高token上限
        if self._is_r1(use_model) and max_tokens < 8192:
            max_tokens = 8192

        json_sys = system_prompt + "\n\n【极其重要】你必须且只能输出一个JSON对象，不要输出任何其他文字、解释或说明。不要使用markdown代码块。直接以{开头，以}结尾。"
        result = self.chat(json_sys, user_prompt, temperature, max_tokens, call_type,
                           model_override=use_model)
        content = result["content"]

        # 使用增强版JSON提取
        parsed, error = self._extract_json_robust(content)

        if parsed is not None:
            result["parsed_json"] = parsed
        else:
            result["parsed_json"] = None
            result["json_parse_error"] = error
            # 保存失败的原始输出用于调试
            self._save_debug_output(content, call_type)
            # 打印返回内容的前300字帮助诊断
            preview = content[:300] if content else "(空)"
            print(f"       R1原始返回(前300字): {preview}")

        return result

    def ocr_image(self, image_path, call_type="ocr"):
        self._check_cost()
        with open(image_path, "rb") as f:
            b64 = base64.b64encode(f.read()).decode("utf-8")
        ext = Path(image_path).suffix.lower()
        mime = {".jpg": "image/jpeg", ".jpeg": "image/jpeg", ".png": "image/png"}.get(ext, "image/jpeg")
        payload = {
            "model": self.model,
            "messages": [
                {"role": "system", "content": "你是OCR专家,请精确识别图片中所有文字,保持原始排版。"},
                {"role": "user", "content": [
                    {"type": "image_url", "image_url": {"url": f"data:{mime};base64,{b64}"}},
                    {"type": "text", "text": "请识别图片中所有文字。"}
                ]}
            ],
            "max_tokens": 4096
        }
        resp = self._request("chat/completions", payload)
        content = resp["choices"][0]["message"]["content"]
        u = resp.get("usage", {})
        inp, out = u.get("prompt_tokens", 0), u.get("completion_tokens", 0)
        cost = self._estimate_cost(self.model, inp, out)
        self.db.log_api_call(call_type, self.model, inp, out, cost)
        return {"content": content, "input_tokens": inp, "output_tokens": out, "estimated_cost": cost}

    def get_today_usage(self):
        cost = self.db.get_today_api_cost()
        return {
            "today_cost": round(cost, 4),
            "daily_limit": self.daily_cost_limit,
            "remaining": round(self.daily_cost_limit - cost, 4),
            "usage_percent": round((cost / self.daily_cost_limit) * 100, 1)
        }
