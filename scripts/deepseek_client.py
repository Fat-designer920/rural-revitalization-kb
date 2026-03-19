"""
deepseek_client.py - DeepSeek API封装
路径：scripts/deepseek_client.py
版本：v1.0.1 - 新增R1模型(deepseek-reasoner)支持
"""
import os, sys, json, time, base64, requests
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
        # R1的completion_tokens已包含reasoning_tokens，直接用于费用计算即可

        cost = self._estimate_cost(use_model, inp, out)
        self.db.log_api_call(call_type, use_model, inp, out, cost)

        result = {
            "content": content,
            "input_tokens": inp,
            "output_tokens": out,
            "estimated_cost": cost,
            "model": use_model
        }
        # 如果有思考过程，附带返回（方便调试，不影响主流程）
        if reasoning:
            result["reasoning_content"] = reasoning

        return result

    def chat_with_json(self, system_prompt, user_prompt, temperature=0.1, max_tokens=4096,
                       call_type="json_extract", model_override=None):
        """
        聊天并解析JSON输出。
        R1模型时：max_tokens自动提高到8192以容纳更细粒度的输出。
        """
        use_model = model_override or self.model

        # R1模型做提取时，输出通常更长，提高token上限
        if self._is_r1(use_model) and max_tokens < 8192:
            max_tokens = 8192

        json_sys = system_prompt + "\n\n重要:请严格按JSON格式输出,不要包含markdown代码块标记。"
        result = self.chat(json_sys, user_prompt, temperature, max_tokens, call_type,
                           model_override=use_model)
        content = result["content"].strip()

        # 清理可能的markdown代码块包裹
        for prefix in ["```json", "```"]:
            if content.startswith(prefix):
                content = content[len(prefix):]
        if content.endswith("```"):
            content = content[:-3]
        content = content.strip()

        # 尝试解析JSON
        try:
            result["parsed_json"] = json.loads(content)
        except json.JSONDecodeError:
            try:
                # 尝试提取JSON对象
                s, e = content.find("{"), content.rfind("}") + 1
                if s >= 0 and e > s:
                    result["parsed_json"] = json.loads(content[s:e])
                else:
                    # 尝试提取JSON数组
                    s, e = content.find("["), content.rfind("]") + 1
                    if s >= 0 and e > s:
                        result["parsed_json"] = json.loads(content[s:e])
                    else:
                        result["parsed_json"] = None
                        result["json_parse_error"] = "无法解析JSON"
            except Exception:
                result["parsed_json"] = None
                result["json_parse_error"] = "JSON解析失败"
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
