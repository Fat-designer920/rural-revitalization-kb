# 稻也·乡村振兴AI助手

**一个聚焦四川乡村振兴的知识工具。**
**现在能：政策文件提取 + AI 问答 + 爬虫采集 + 知识审核。**
**还不能：付费使用、课程生成、合规自检（远期目标）。**

## 系统架构

```
原始文件 → 预处理 → V4-Pro 提取 → 质检 → 关系分析 → 知识库(SQLite)
                                                    ↓
                                               QA 助手(检索 + 生成)
                                                    ↓
                                               Web 管理后台
```

## 快速开始

```
1. 双击 首次安装.bat → 安装依赖
2. 编辑 config/settings.json → 填入 API Key
3. 双击 启动后台.bat → 打开管理后台
4. 放入文件到 data/pending/ → Tab2 提取管理
```

## 命令行

```
python scripts/run_pipeline.py --status        # 知识库状态
python scripts/run_pipeline.py --feed-only     # 喂料+提取
python scripts/run_pipeline.py --crawl         # 爬虫采集
python scripts/feed_experience.py              # 经验喂入
python scripts/auto_tester.py --smoke          # 冒烟测试
```

## 技术栈

Python 3.8+ / SQLite / Flask / DeepSeek V4-Pro / DFA 敏感词过滤

## 知识库现状

- 知识点 ~1,830 条 (88% 政策 / 7% 经验 / 5% 案例)
- 爬虫采集 5,000+ 条
- 分类: 5 大类 27+ 子类

## 版本

**v2.3.8** — 务实重构版 (2026-05-08)

## 项目文件

| 文件 | 内容 |
|------|------|
| CLAUDE.md | 开发协作规范 |
| docs/architecture.md | 工程架构 |
| docs/knowledge.md | 知识体系 |
| docs/prompts.md | Prompt 模板 |
| docs/business.md | 商业方向 |
| CHANGELOG.md | 版本历史 |
| FUTURE_NOTES.md | 未来待办 |
| DEPRECATED_FIELDS.md | DB 死字段 |
