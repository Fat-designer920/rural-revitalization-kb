"""
config_wizard.py - 首次配置向导（图形界面）
路径：scripts/config_wizard.py
版本：v2.3.6-part1 - Kimi UI 残留清理

变更说明(v2.3.6-part1):
  删除第 5 项 Kimi 官方 API Key 输入框 + 测试按钮 + 保存逻辑。
  Kimi 兜底链(v2.3.5-part2 已整体废弃),UI 残留同步清理。
"""
import os, sys, json, tkinter as tk
from tkinter import ttk, filedialog, messagebox
from pathlib import Path
from datetime import datetime

PROJECT_ROOT = Path(__file__).parent.parent
sys.path.insert(0, str(PROJECT_ROOT))

def get_or_create_key():
    key_path = PROJECT_ROOT / "config" / ".secret_key"
    if key_path.exists():
        with open(key_path, "rb") as f: return f.read()
    from cryptography.fernet import Fernet
    key = Fernet.generate_key()
    key_path.parent.mkdir(parents=True, exist_ok=True)
    with open(key_path, "wb") as f: f.write(key)
    try:
        import ctypes; ctypes.windll.kernel32.SetFileAttributesW(str(key_path), 0x02)
    except Exception: pass
    return key

def encrypt_value(value):
    from cryptography.fernet import Fernet
    return Fernet(get_or_create_key()).encrypt(value.encode("utf-8")).decode("utf-8")

def decrypt_value(encrypted_value):
    from cryptography.fernet import Fernet
    return Fernet(get_or_create_key()).decrypt(encrypted_value.encode("utf-8")).decode("utf-8")

def load_config():
    p = PROJECT_ROOT / "config" / "settings.json"
    if p.exists():
        with open(p, "r", encoding="utf-8") as f: return json.load(f)
    return {}

def save_config(config):
    p = PROJECT_ROOT / "config" / "settings.json"
    p.parent.mkdir(parents=True, exist_ok=True)
    with open(p, "w", encoding="utf-8") as f: json.dump(config, f, ensure_ascii=False, indent=2)


class ConfigWizard:
    def __init__(self):
        self.root = tk.Tk()
        self.root.title("乡村振兴知识库搭建助手 - 配置向导")
        self.root.geometry("680x780")
        self.root.resizable(False, False)
        self.root.update_idletasks()
        x = (self.root.winfo_screenwidth() // 2) - 340
        y = (self.root.winfo_screenheight() // 2) - 390
        self.root.geometry(f"+{x}+{y}")
        self.existing = load_config()
        self.create_widgets()

    def create_widgets(self):
        tf = tk.Frame(self.root, bg="#2E75B6", height=70)
        tf.pack(fill="x"); tf.pack_propagate(False)
        tk.Label(tf, text="乡村振兴知识库搭建助手", font=("Microsoft YaHei",18,"bold"), fg="white", bg="#2E75B6").pack(pady=(12,2))
        tk.Label(tf, text="配置向导  v2.3.6-part1", font=("Microsoft YaHei",10), fg="#B0D4F1", bg="#2E75B6").pack()

        mf = tk.Frame(self.root, padx=30, pady=15); mf.pack(fill="both", expand=True)

        # 1. DeepSeek API Key
        tk.Label(mf, text="1. DeepSeek API Key (必填)", font=("Microsoft YaHei",11,"bold"), anchor="w").pack(fill="x", pady=(0,3))
        tk.Label(mf, text="在 platform.deepseek.com 申请后粘贴到下方", font=("Microsoft YaHei",9), fg="#666", anchor="w").pack(fill="x")
        self.api_key_var = tk.StringVar()
        if self.existing.get("deepseek_api_key_encrypted"):
            try:
                d = decrypt_value(self.existing["deepseek_api_key_encrypted"])
                self.api_key_var.set(d[:8]+"****"+d[-4:] if len(d)>12 else "****(已配置)")
            except Exception: pass
        tk.Entry(mf, textvariable=self.api_key_var, font=("Consolas",11), width=55).pack(fill="x", pady=(3,10))

        # 2. 知识库路径
        tk.Label(mf, text="2. 知识库存放路径 (必填)", font=("Microsoft YaHei",11,"bold"), anchor="w").pack(fill="x", pady=(0,3))
        tk.Label(mf, text="选择存放数据的文件夹 (建议D盘，不要放C盘)", font=("Microsoft YaHei",9), fg="#666", anchor="w").pack(fill="x")
        pf = tk.Frame(mf); pf.pack(fill="x", pady=(3,10))
        self.kb_path_var = tk.StringVar(value=self.existing.get("knowledge_base_path", str(PROJECT_ROOT)))
        tk.Entry(pf, textvariable=self.kb_path_var, font=("Microsoft YaHei",10), width=45).pack(side="left", fill="x", expand=True)
        tk.Button(pf, text="浏览...", command=self.browse_path, font=("Microsoft YaHei",9)).pack(side="right", padx=(10,0))

        # 3. 费用上限
        tk.Label(mf, text="3. 每日API费用上限 (元)", font=("Microsoft YaHei",11,"bold"), anchor="w").pack(fill="x", pady=(0,3))
        cf = tk.Frame(mf); cf.pack(fill="x", pady=(3,10))
        self.cost_var = tk.StringVar(value=str(self.existing.get("daily_cost_limit", 20)))
        tk.Entry(cf, textvariable=self.cost_var, font=("Microsoft YaHei",11), width=10).pack(side="left")
        tk.Label(cf, text="元/天 (建议初期设为20元)", font=("Microsoft YaHei",9), fg="#666").pack(side="left", padx=(10,0))

        # 4. 硅基流动 API Key
        tk.Label(mf, text="4. 硅基流动 API Key (扫描件PDF必填)", font=("Microsoft YaHei",11,"bold"), anchor="w").pack(fill="x", pady=(0,3))
        tk.Label(mf, text="在 cloud.siliconflow.cn 申请，用于扫描件PDF和图片的OCR识别", font=("Microsoft YaHei",9), fg="#666", anchor="w").pack(fill="x")
        self.sf_key_var = tk.StringVar()
        if self.existing.get("siliconflow_api_key_encrypted"):
            try:
                d = decrypt_value(self.existing["siliconflow_api_key_encrypted"])
                self.sf_key_var.set(d[:8]+"****"+d[-4:] if len(d)>12 else "****(已配置)")
            except Exception: pass
        tk.Entry(mf, textvariable=self.sf_key_var, font=("Consolas",11), width=55).pack(fill="x", pady=(3,10))

        # 5. Notion Token
        tk.Label(mf, text="5. Notion Token (选填，暂未启用)", font=("Microsoft YaHei",11,"bold"), anchor="w", fg="#999").pack(fill="x", pady=(0,3))
        self.notion_var = tk.StringVar(value=self.existing.get("notion_token_display", ""))
        tk.Entry(mf, textvariable=self.notion_var, font=("Consolas",11), width=55, fg="#999").pack(fill="x", pady=(3,10))

        # 按钮
        bf = tk.Frame(mf); bf.pack(fill="x", pady=(10,0))
        tk.Button(bf, text="测试DeepSeek", command=self.test_api, font=("Microsoft YaHei",10), width=12).pack(side="left")
        tk.Button(bf, text="测试硅基流动", command=self.test_siliconflow, font=("Microsoft YaHei",10), width=12).pack(side="left", padx=(6,0))
        tk.Button(bf, text="取消", command=self.root.destroy, font=("Microsoft YaHei",10), width=8).pack(side="right")
        tk.Button(bf, text="保存配置", command=self.save, font=("Microsoft YaHei",10,"bold"), width=12, bg="#2E75B6", fg="white").pack(side="right", padx=(0,8))

    def browse_path(self):
        p = filedialog.askdirectory(title="选择知识库存放路径")
        if p: self.kb_path_var.set(p)

    def _resolve_api_key(self, var, config_field):
        """解析输入框中的API Key：如果是****掩码则从已有配置中读取原值"""
        key = var.get().strip()
        if not key:
            return None
        if "****" in key:
            enc = self.existing.get(config_field, "")
            if enc:
                try:
                    return decrypt_value(enc)
                except Exception:
                    return None
            return None
        return key

    def test_api(self):
        key = self._resolve_api_key(self.api_key_var, "deepseek_api_key_encrypted")
        if not key:
            messagebox.showwarning("提示","请先输入DeepSeek API Key"); return
        try:
            import requests
            r = requests.post("https://api.deepseek.com/chat/completions",
                headers={"Authorization":f"Bearer {key}","Content-Type":"application/json"},
                json={"model":"deepseek-chat","messages":[{"role":"user","content":"回复:连接成功"}],"max_tokens":20}, timeout=30)
            if r.status_code == 200: messagebox.showinfo("成功","DeepSeek API 连接成功!")
            elif r.status_code == 401: messagebox.showerror("失败","API Key 无效")
            else: messagebox.showerror("失败", f"错误码: {r.status_code}")
        except Exception as e: messagebox.showerror("失败", str(e))

    def test_siliconflow(self):
        key = self._resolve_api_key(self.sf_key_var, "siliconflow_api_key_encrypted")
        if not key:
            messagebox.showwarning("提示","请先输入硅基流动API Key"); return
        try:
            import requests
            r = requests.post("https://api.siliconflow.cn/v1/chat/completions",
                headers={"Authorization":f"Bearer {key}","Content-Type":"application/json"},
                json={"model":"Qwen/Qwen2.5-7B-Instruct","messages":[{"role":"user","content":"回复:连接成功"}],"max_tokens":20}, timeout=30)
            if r.status_code == 200: messagebox.showinfo("成功","硅基流动API 连接成功!")
            elif r.status_code == 401: messagebox.showerror("失败","API Key 无效")
            else: messagebox.showerror("失败", f"错误码: {r.status_code}\n{r.text[:200]}")
        except Exception as e: messagebox.showerror("失败", str(e))

    def save(self):
        key = self.api_key_var.get().strip()
        if not key and not self.existing.get("deepseek_api_key_encrypted"):
            messagebox.showwarning("提示","请输入DeepSeek API Key"); return
        kb = self.kb_path_var.get().strip()
        if not kb: messagebox.showwarning("提示","请选择知识库路径"); return
        try:
            cost = float(self.cost_var.get().strip())
            if cost <= 0: raise ValueError
        except (ValueError, TypeError): messagebox.showwarning("提示","费用上限须为正数"); return

        config = load_config()
        if key and "****" not in key:
            config["deepseek_api_key_encrypted"] = encrypt_value(key)
        config["knowledge_base_path"] = kb
        config["database_path"] = str(Path(kb)/"data"/"database"/"knowledge_base.db")
        config["pending_path"] = str(Path(kb)/"data"/"pending")
        config["processing_path"] = str(Path(kb)/"data"/"processing")
        config["completed_path"] = str(Path(kb)/"data"/"completed")
        config["backup_path"] = str(Path(kb)/"backups")
        config["log_path"] = str(Path(kb)/"logs")
        config["daily_cost_limit"] = cost

        # 硅基流动API Key
        sf_key = self.sf_key_var.get().strip()
        if sf_key and "****" not in sf_key:
            config["siliconflow_api_key_encrypted"] = encrypt_value(sf_key)
        config.setdefault("siliconflow_base_url", "https://api.siliconflow.cn/v1")
        config.setdefault("siliconflow_model", "Qwen/Qwen2.5-VL-72B-Instruct")

        # Notion Token
        notion = self.notion_var.get().strip()
        if notion:
            config["notion_token_encrypted"] = encrypt_value(notion)
            config["notion_token_display"] = notion[:8]+"****"

        config.setdefault("deepseek_model","deepseek-chat")
        config.setdefault("deepseek_base_url","https://api.deepseek.com")
        config.setdefault("flask_port", 5000)
        config.setdefault("max_file_size_mb", 50)
        config["version"] = "2.3.6-part1"
        config["last_configured_at"] = datetime.now().isoformat()
        config["allowed_paths"] = [str(Path(kb)/"data"), str(Path(kb)/"config"), str(Path(kb)/"logs"), str(Path(kb)/"backups")]

        save_config(config)
        messagebox.showinfo("完成","配置已保存!\n\n如需处理扫描件PDF,请确保已配置硅基流动 API Key。")
        self.root.destroy()

    def run(self):
        self.root.mainloop()

def main():
    ConfigWizard().run()

if __name__ == "__main__":
    main()
