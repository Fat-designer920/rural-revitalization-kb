"""
archivist_agent.py - 档案管理员(源文件分类+爬虫存储+目录治理)
路径：agents/archivist_agent.py
版本：v2.3.7-part3

CEO招聘指令: 真人型、思考型、务实肯干型Agent。负责所有文件的分类、归档、
命名规范、目录维护。不搞花架子，每一份文件都知道自己属于哪个类别、应该放在哪。
"""
import os, json, shutil
from pathlib import Path
from datetime import datetime
from agents.base_agent import BaseAgent


class ArchivistAgent(BaseAgent):
    """档案管理员——文件分类/归档/命名/目录治理的思考型Agent"""

    def __init__(self, client=None, db=None,
                 source_library=None, crawl_dir=None, completed_dir=None):
        super().__init__(
            "archivist", "档案管理员", "quality",
            self._build_identity(),
            core_questions=[
                "这个文件属于哪个分类?为什么?",
                "分类体系是否需要调整?有没有文件找不到合适的分类?",
                "源文件命名是否规范?是否需要重命名?",
                "有没有重复文件?有没有文件放错目录?",
                "爬虫抓取的文件归好类了吗?文件名有意义吗?",
            ],
            quality_standards=[
                "每个文件有明确的分类归属(不超过2级目录)",
                "文件名遵循命名规范: 年份+来源+主题+版本",
                "重复文件24小时内识别并清理",
                "目录结构每月审计一次,过时分类归档或删除",
                "所有文件路径记录到数据库source_files表",
            ],
            scoring_dimensions=[
                "分类准确度", "命名规范度", "目录整洁度",
                "去重及时度", "可检索性",
            ],
            client=client, db=db,
        )
        self.source_library = Path(source_library) if source_library else None
        self.crawl_dir = Path(crawl_dir) if crawl_dir else None
        self.completed_dir = Path(completed_dir) if completed_dir else None

    @staticmethod
    def _build_identity():
        return (
            "我是档案管理员,知识工厂的文件大管家。我的工作哲学:\n"
            "1. 每一份文件都必须知道自己属于哪里——分类不是装饰,是可检索性的基础\n"
            "2. 命名规范是纪律——文件名要让人一眼看懂:什么年份、什么来源、什么主题\n"
            "3. 重复文件是垃圾——发现了立刻清理,绝不让两份相同文件占用不同位置\n"
            "4. 目录结构是活的——随着知识库发展,分类要跟着演进,过时的分类要淘汰\n"
            "5. 务实第一——不搞花里胡哨的目录层级,2级够用就不建3级\n\n"
            "我的收入贡献:文件管理好=内容生产快=时间成本降低=月利润增加5000-10000。\n"
            "我不写漂亮的文档,我只让文件井井有条。"
        )

    # ================================================================
    # 核心能力: 文件分类
    # ================================================================

    def classify_file(self, file_path, filename=None):
        """对单个文件进行智能分类。
        返回: {category, subcategory, suggested_name, confidence, reason}
        """
        path = Path(file_path)
        if not path.exists():
            return {"error": f"文件不存在: {file_path}", "category": "unknown"}

        fname = filename or path.name
        ext = path.suffix.lower()

        # 规则层: 基于文件名和扩展名推断分类
        category, subcategory, confidence = self._rule_classify(fname, ext)

        # 如果规则层置信度低且有AI客户端,调AI深度分析
        if confidence < 0.7 and self.client and self.db:
            ai_result = self._ai_classify(file_path, fname)
            if ai_result and ai_result.get("confidence", 0) > confidence:
                return ai_result

        return {
            "category": category,
            "subcategory": subcategory,
            "suggested_name": self._suggest_filename(fname, category, subcategory),
            "confidence": confidence,
            "reason": f"规则分类: {category}/{subcategory}",
            "file_path": str(file_path),
        }

    def _rule_classify(self, filename, ext):
        """基于规则的分类(快速,不需要AI)"""
        name_lower = filename.lower()
        cat = "unknown"
        sub = "misc"

        # 政策类
        policy_keywords = [
            "通知", "意见", "办法", "条例", "规定", "决定", "公告",
            "一号文件", "政策", "规划", "标准", "指南", "方案",
            "notice", "policy", "regulation",
        ]
        for kw in policy_keywords:
            if kw in filename:
                cat = "policy"
                break

        # 经验/案例类
        exp_keywords = [
            "经验", "案例", "踩坑", "操盘", "实战", "心得", "总结",
            "交流", "发言", "培训", "讲课", "分享",
            "case", "experience", "lesson",
        ]
        for kw in exp_keywords:
            if kw in filename:
                cat = "experience" if cat == "unknown" else cat
                break

        # 数据类
        data_keywords = ["数据", "统计", "报表", "指标", "台账", "data", "statistics"]
        for kw in data_keywords:
            if kw in filename:
                cat = "data"
                break

        # 文件格式类(扫描件/图片)
        if ext in (".pdf",):
            sub = "scanned" if cat == "unknown" else sub
        elif ext in (".png", ".jpg", ".jpeg", ".bmp", ".tiff"):
            cat = "data" if cat == "unknown" else cat
            sub = "image"
        elif ext in (".xlsx", ".xls", ".csv"):
            sub = "spreadsheet"

        # 地域识别
        sichuan_kw = ["四川", "成都", "绵阳", "德阳", "宜宾", "南充", "泸州",
                      "达州", "乐山", "凉山", "甘孜", "阿坝", "广元", "遂宁",
                      "内江", "眉山", "广安", "巴中", "资阳", "雅安", "攀枝花",
                      "天府", "大邑", "双流", "郫都", "温江", "新津"]
        for kw in sichuan_kw:
            if kw in filename:
                sub = "sichuan" if sub in ("misc", "scanned", "spreadsheet") else sub
                break

        confidence = 0.8 if cat != "unknown" else 0.3
        return cat, sub, confidence

    def _ai_classify(self, file_path, filename):
        """AI深度分类(规则层搞不定时调用)"""
        if not self.client:
            return None
        try:
            # 读取文件前500字作为内容样本
            content_sample = ""
            try:
                with open(file_path, "r", encoding="utf-8") as f:
                    content_sample = f.read(500)
            except Exception:
                pass

            prompt = (
                f"文件名: {filename}\n"
                f"内容样本: {content_sample[:300]}\n\n"
                "请分类这个文件:\n"
                "1. 主类别: policy(政策)/experience(经验)/case(案例)/data(数据)/template(模板)/other\n"
                "2. 子类别: 四川相关?什么主题领域?\n"
                "3. 建议文件名: 按'年份_来源_主题_版本'格式\n"
                "返回JSON: {category, subcategory, suggested_name, confidence, reason}"
            )
            resp = self.client.chat_with_json(
                "你是文件分类专家。精确、务实、快速。", prompt,
                temperature=0.1, call_type="archivist_classify",
            )
            parsed = resp.get("parsed_json") if isinstance(resp, dict) else {}
            if parsed and isinstance(parsed, dict):
                parsed["file_path"] = str(file_path)
                return parsed
        except Exception:
            pass
        return None

    def _suggest_filename(self, fname, category, subcategory):
        """建议规范化文件名: 年份_来源_主题.扩展名"""
        # 简化版: 保留原名但确保分类前缀
        # 完整版需要AI解析文件名中的年份/来源/主题
        return fname

    # ================================================================
    # 核心能力: 批量分类
    # ================================================================

    def classify_directory(self, dir_path, recursive=True):
        """批量分类目录下所有文件。
        返回: [{file_path, category, subcategory, suggested_name, confidence}]
        """
        results = []
        root = Path(dir_path)
        if not root.exists():
            return [{"error": f"目录不存在: {dir_path}"}]

        pattern = "**/*" if recursive else "*"
        for fpath in root.glob(pattern):
            if fpath.is_file() and not fpath.name.startswith("."):
                result = self.classify_file(str(fpath), fpath.name)
                results.append(result)

        # 统计
        cats = {}
        for r in results:
            c = r.get("category", "unknown")
            cats[c] = cats.get(c, 0) + 1
        print(f"  档案分类完成: {len(results)}个文件, 分布: {cats}")
        return results

    # ================================================================
    # 核心能力: 归档整理
    # ================================================================

    def organize_files(self, dir_path, target_base=None, dry_run=True):
        """按分类整理文件到分类子目录。
        dry_run=True: 只输出方案,不实际移动。
        """
        classified = self.classify_directory(dir_path, recursive=False)

        plan = []
        for item in classified:
            cat = item.get("category", "unknown")
            sub = item.get("subcategory", "misc")
            target_dir = Path(target_base or dir_path) / cat / sub
            plan.append({
                "source": item.get("file_path"),
                "target": str(target_dir / Path(item.get("file_path", "")).name),
                "category": cat,
                "subcategory": sub,
                "confidence": item.get("confidence", 0),
            })

        if not dry_run:
            for p in plan:
                target_dir = Path(p["target"]).parent
                os.makedirs(target_dir, exist_ok=True)
                shutil.move(p["source"], p["target"])

        return plan

    # ================================================================
    # 核心能力: 去重
    # ================================================================

    def deduplicate(self, dir_path, by_name=True, by_size=False):
        """检测重复文件。"""
        from collections import defaultdict

        size_map = defaultdict(list)
        name_map = defaultdict(list)
        duplicates = []

        for fpath in Path(dir_path).rglob("*"):
            if fpath.is_file() and not fpath.name.startswith("."):
                if by_name:
                    name_map[fpath.name].append(str(fpath))
                if by_size:
                    try:
                        size_map[fpath.stat().st_size].append(str(fpath))
                    except Exception:
                        pass

        if by_name:
            for name, paths in name_map.items():
                if len(paths) > 1:
                    duplicates.append({"type": "same_name", "name": name, "paths": paths})

        return duplicates


def build_archivist_agent(client=None, db=None, project_root=None):
    """工厂函数: 构建档案管理员Agent实例"""
    root = Path(project_root) if project_root else Path(__file__).parent.parent
    return ArchivistAgent(
        client=client, db=db,
        source_library=str(root / "source_library" / "乡村振兴资料库"),
        crawl_dir=str(root / "data" / "crawled"),
        completed_dir=str(root / "data" / "completed"),
    )
