# CLAUDE.md

> 稻也·乡村振兴AI助手 — 知识提取管道 + QA 助手 + 管理后台。
> 聚焦四川,服务基层操盘手。老唐 20 年经验是核心差异化资产。

## 项目身份

- **代码仓库**: https://github.com/Fat-designer920/rural-revitalization-kb
- **当前版本**: v2.3.8 (务实重构版)
- **技术栈**: Python 3.8+ / SQLite / Flask / DeepSeek V4-Pro
- **角色**: Claude = 技术实现者,老唐 = 产品决策者

## 真实能力(当前能做什么)

| 能力 | 状态 | 入口 |
|------|------|------|
| 知识提取管道 | 文件 → V4-Pro 提取 → KP 入库 | `python scripts/run_pipeline.py --feed-only` |
| QA 助手 | 检索 + 生成 + 朋友模式 IP 限速 | `python scripts/api_server.py` → /qa |
| 爬虫系统 | 信源发现 + 核验 + 全省爬取 | `python scripts/run_pipeline.py --crawl` |
| 知识审核后台 | 人工审核 KP + 标签 + 保鲜 | 浏览器打开管理后台 |
| 经验喂入 | 手动 .md → 入库 | `python scripts/feed_experience.py` |
| 安全门禁 | DFA 敏感词过滤(QA 入口) + 来源追溯(QA 出口) | 自动,QA 链路内置 |

## 当前不能做什么

- **没有付费/订阅/账号系统**(5 档定价是远期规划,零代码)
- **没有课程生成/合规自检/政策日报**(代码已移除,需要时再开发)
- **知识库 88% 是政策提取**,差异化经验只有 130 条

## 启动序列(每次新对话)

```
1. 读本文件 + README.md + CHANGELOG.md + docs/business.md
2. 脑中列 todos(本对话要做什么)
3. 开工前 3 问:
   (a) 有没有需要 grep 的真实签名/字段名?
   (b) 有没有需要老唐告知的事实?
   (c) 这个任务预估会沉默 > 2 分钟吗? → 先输出 1 句话进度
4. 任务完成后跑: python scripts/auto_tester.py --smoke
```

## 关键规则(少而精)

1. **代码不臆造** — grep 真实签名,不凭记忆
2. **改动即测试** — 改完代码跑 smoke,通过才说"完成"
3. **先说话再干活** — 接到任务先输出 1 句话进度,禁止 > 2 分钟沉默
4. **做减法** — 不加不必要的抽象/框架/管理器
5. **数据零损失** — data/ 目录和 DB 表不能删改
6. **异常不裸奔** — 禁止 bare except

## 项目文件导航

| 想找什么 | 去哪 |
|---------|------|
| 项目当前状态 | README.md |
| 知识分类 + 标签体系 | docs/knowledge.md |
| Prompt 模板 | docs/prompts.md |
| 商业方向 | docs/business.md |
| 工程架构 | docs/architecture.md |
| 版本变更 | CHANGELOG.md |
| 对外说明 | README.md |

## 核心架构(代码层)

```
agents/  → 功能模块(crawler_scheduler, auto_feeder, brand_redlines, reader_tagger 等)
scripts/ → 核心引擎(extractor, qa_assistant, api_server, db_manager, run_pipeline 等)
data/    → 数据库 + 爬取文件 + 经验 inbox(不可删)
docs/    → 项目文档(5 个文件)
archive/ → 已移除的历史代码(不影响运行)
```

## 测试

```
python scripts/auto_tester.py --smoke        # 快速冒烟(每次任务后必跑)
python scripts/auto_tester.py --auto --no-ai # 自动检测变更 + 无 AI 测试
```

## 上下文压缩保全

当对话中出现上下文压缩提醒时: 扫描本次对话中新需求/质量要求 → 写入对应项目文件 → 标注 `[F066 保全 YYYY-MM-DD]` → 再压缩。

---

**末尾铁律**: 本文件是每次新对话第一站。不读直接开工 = 违规。
