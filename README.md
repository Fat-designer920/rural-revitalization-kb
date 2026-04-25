# 乡村振兴知识库搭建助手

> 基于 DeepSeek R1/V3 双模型的专业知识库构建工具，面向四川乡村振兴领域。
>
> **知识工厂**：原料 → 加工 → 质检 → 产品 → 卖钱。底座是知识库，上面长出多种产品形态。
>
> **当前版本**:**v2.3.2-hotfix1**(hotfix:F055 智能问答 4 处 bug 清除 + 体验优化;立规则 9 应验扩至第 13 次 + 立规则 53 第 4 次自证)

---

## 系统定位

这不是普通的文档管理工具，而是**知识工厂**——将行业文件、政策法规和 20 年实战经验加工成可变现的知识产品。

**核心竞争力**：每一条知识点都有入库质检、人工审核、政策验证、定期保鲜的完整质量链。**500 条精品级知识 > 5000 条草稿级内容**。老唐的加工（判断/注解/验证）才是付费点。

| 阶段 | 做什么 | 验证什么 |
|------|--------|---------|
| 当前(v2.3.2-hotfix1 后) | **本地问答助手自用 + 分享朋友试用** | 回答质量 / 付费意愿 |
| 200 条精品+ | 政策解读文章发行业圈子 | 内容付费 |
| 300 条精品+ | 云端问答助手产品化 | C 端订阅 |
| 500 条精品+ | 投标辅助 / 培训 / 合规自检 | B 端高客单价 |

---

## 技术栈

| 组件 | 技术 |
|------|------|
| 运行环境 | Windows + Python 3.8+（便携版，绿色免安装） |
| AI 引擎 | DeepSeek API（R1 提取 + 打磨；V3 辅助判断 + 校验 + E2E 语义 + 问答生成） |
| OCR 引擎 | 硅基流动 API（Qwen2.5-VL-72B 视觉模型） |
| 数据库 | SQLite(**24 张业务表** + 31 条索引;v2.3.2 新增 qa_history + qa_feedback 两表 + 4 索引) |
| Web 界面 | Flask 本地管理后台（严格 ES5 前端，Tab 1 知识审核 + Tab 2 系统管理 + Tab 3 智能问答） |
| 操作方式 | 管理后台为主，bat 入口辅助 |

---

## 双 API 架构

| API | 用途 | 模型 |
|-----|------|------|
| DeepSeek | 知识提取 / 打磨 / 分类 / 质检 / 预分析 / 政策扫描 / 重复判断 / 体检分析 / 打磨校验 / 问答 / E2E 语义 | deepseek-reasoner / deepseek-chat |
| 硅基流动 | 扫描件 PDF 和图片 OCR（仅 OCR，不做推理） | Qwen/Qwen2.5-VL-72B-Instruct |

---

## 快速开始

### 首次部署

```
双击 首次安装.bat
```

按提示完成 Python 环境检查、依赖安装、双 API Key 配置、数据库初始化（21 张表一次建成）。

### 日常使用

```
1. 将文件放入 data/pending/ 目录
2. 双击 启动后台.bat → 自动打开管理后台
3. Tab 2 系统管理 → 提取管理
4. Tab 1 知识审核 → 人工审核
5. Tab 2 系统管理 → 工具箱 → 定期体检打磨 / 定期 E2E 扫描
```

### Tab 2 工具箱（12 个按钮）

系统检查 / 一键备份 / 恢复备份 / 保鲜扫描 / 智能重复检测 / 政策补跑 / 质检补跑 / **就绪度联动（R 橙，v2.3.0-part3.2 新增）** / 审核统计 / API 费用 / **知识库体检（F048）** / **端到端健康测试（F062）**

**v2.3.2 关键交付**:
- **F055 本地问答助手首版**:`scripts/qa_assistant.py` 866 行(QaAssistantEngine + 模块级 `run_qa()`),精品+quotable 池检索 + V3 重排 + 三级降级链 + 4 板块通用回答(直答/依据/延伸思考/补漏提醒);Tab 3 整段新建(~700 行 HTML+JS,严格 ES5);URL `?mode=friend` 朋友试用模式 + 反馈闭环 👍/👎/💬;老唐自测 `is_test_query=1` 不写埋点(防脏数据);商业化路径从"自用"过渡到"朋友试用 + 内容付费"
- **F056 单 HTML 查看器**:`web/templates/f056_viewer.html` 471 行零依赖,双击浏览器打开即用;拖 JSON 进页面 + 校验 v1.0 标准(E001-E027 完整)+ 渲染 13 字段;朋友拿到导出 JSON 即看精品包
- **api_server.py +7 路由 + 独立 `_qa_task` 槽**:`/api/qa/{ask,cancel,progress,history,history/<hid>,feedback,stats}`,4 层 readiness_check
- **db_manager.py +6 方法 + 2 表 + 4 索引**:qa_history + qa_feedback + qa 相关索引
- **3 新 Prompt + 9 新事件**:PROMPT_VERSION 升 v2.3.2(28→31);`qa_*` 族 9 种事件埋点
- **立规则 57 首立**:Phase 3 工作量 grep 预评估,主动拆 part3a/part3b 不冒险

**part3.8 关键修复**:
- **F062 白名单一次性清账**:白名单从 db_manager 单文件扩展到 7 文件(db_manager+api_server+extractor+health_checker+duplicate_checker+preprocessor+backup_manager),DIM4 67→75/DIM6 11→79 条,新增 `WHITELIST_COVERAGE` 常量。E2E 扫分从 79.2 回到预期 92-95
- **6 批量路由 errors 收集改造**(E2 方案):批量确认/忽略/删除/续期/标记过时/恢复/移除 共 7 个按钮,把原 `except:pass` 改为 `except Exception as e: errors.append({id,error})`,前端混合策略(成功 toast/有失败弹 `#batchResultModal` 看详情)。老唐以后能看到每条失败原因
- **冗余代码清理(立规则 52 条首次应用)**:extractor.py 删 37 行(run_headless 5 迁移 import 整段 -17 + main 双路径 fallback -20),duplicate_checker.py 删 3 行(main 内 migrate),10 条 dim6 issue 自然消失

**part3.7 关键修复**:
- **F062 规则精度**:E2E 扫描 issue 从 207 降到 60-90,信噪比质变。规则精度三连改(snippet 显示真实 pass 行 / `r` 不再当 kp / 历史 Prompt key 白名单静默)
- **诊断包口径对齐**:第三段 dim4/dim6 count 与第四段聚合清单同源

**part3.6 关键修复**:
- **诊断包准确性**:六维度得分权重列不再全 0、白名单失效自检输出警告、近 7 天事件日志正常显示
- **工程纪律**:沉淀立规则 49/50/51 三条

**历史版本精华**(part3.3/part3.4/part3.5):低分打磨候选池允许 confirmed / E2E issue 签名漂移修复 / 审核统计 UI 重写 / E2E 诊断包导出 feature —— 详见 CHANGELOG

---

## 目录结构

```
rural-revitalization-kb/
├── scripts/
│   ├── prompts/             # Prompt 模板（26 个）
│   ├── api_server.py        # 管理后台 API（v2.3.0-part3.8，F048 8 + F062 8 + qc_rerun 3 路由 + 启动兜底 init_tables；part3.8 6 批量路由 errors 收集改造）
│   ├── extractor.py         # 知识提取引擎（v2.3.0-part3.8，含 F057/F058，part3.8 冗余迁移 import 清理-21 行）
│   ├── deepseek_client.py   # DeepSeek + 硅基流动 API 封装
│   ├── preprocessor.py      # 文件预处理 + .md 缓存
│   ├── db_manager.py        # 数据库管理（v2.3.0-part3.4，21 表，F048 12 方法 + F062 9 方法 + part3.2 新增 2 方法；part3.4 get_polish_candidates WHERE 修复）
│   ├── experience_notes.py  # 经验速记
│   ├── config_wizard.py     # 配置向导
│   ├── check_system.py      # 系统检查（v2.5.2，19 项）
│   ├── duplicate_checker.py # 重复检测（v2.3.0-part3.8）
│   ├── policy_validator.py  # 政策依赖校验
│   ├── freshness_checker.py # 保鲜扫描
│   ├── backup_manager.py    # 备份恢复 + operation_hook（6 触发点）
│   ├── review_analytics.py  # 审核统计
│   ├── tag_config.py        # 标签体系
│   ├── file_reader.py       # 多格式文件读取
│   ├── setup.py             # 初始化（v2.3.0-part3）
│   ├── upgrade_manager.py   # 架构升级
│   ├── health_checker.py    # F048 体检引擎（~1360 行）
│   ├── e2e_tester.py        # F062 端到端测试引擎（v2.3.0-part3.8，~1645 行，白名单 DIM4 75 / DIM6 79 / 覆盖 7 文件）
│   ├── e2e_diagnosis_exporter.py  # F062 诊断包 Markdown 导出引擎（v2.3.0-part3.8，~1077 行，第三段按文件维度分类视图）
│   ├── static_analyzer.py   # F062 静态规则库（v2.3.0-part3.7，~720 行，规则精度三连改）
│   └── db_health_check.py   # 数据层只读体检（v1.2）
├── web/templates/
│   └── review.html          # 管理后台（v2.3.0-part3.8，工具箱 12 卡 + 独立 QC 进度面板 + 审核统计 6 段结构化 + 7 批量按钮混合策略 + #batchResultModal）
├── data/                    # 数据目录
├── backups/                 # 备份目录
├── config/                  # 配置文件
├── 启动后台.bat
├── 首次安装.bat
├── CHANGELOG.md
└── README.md
```

---

## 知识体系

### 分类体系（5 大类 27+ 子类）

1. **政策库**（法规依据）
2. **案例库**（项目参考）
3. **经验库**（差异化资产 —— 老唐 20 年实战沉淀）
4. **工具库**（可复用模板）
5. **数据库**（数据支撑）

### 三层标签体系

- **第一层 分类标签**：6 组 41 个（业务领域 / 项目阶段 / 知识形态 / 客户视角 / 稀缺度 / 内容状态）
- **第二层 属性标签**：8 个维度
- **第三层 关键词**：AI 自由提取 5-15 个

详见 `02_知识体系.md`。

---

## 迭代路线

| 版本 | 定位 | 状态 |
|------|------|------|
| v1.0 ~ v2.2.3 | 基础 → 提取 → 管理 → 资产沉淀 → 质量管控 | ✅ |
| v2.3.0-part1 / 1.1 | 工具箱整体优化 + hotfix | ✅ |
| v2.3.0-part2 | F048 知识库体检 Agent | ✅ |
| v2.3.0-part2.1 | schema 单一来源 hotfix | ✅ |
| v2.3.0-part2.2 | F048 四类系统性 bug 防护层 hotfix | ✅ |
| v2.3.0-part3 | F062 端到端健康测试 Agent 全闭环 | ✅ |
| v2.3.0-part3.1 | hotfix：F061 质检补跑签名漂移 + F062 老库自动追齐 | ✅ |
| v2.3.0-part3.2 | hotfix：仪表盘 UI + 质检补跑异步化 + 就绪度联动预埋 | ✅ |
| v2.3.0-part3.3 | hotfix：审核统计 UI 重写 + 保鲜 loading + 体检无低分提示 + E2E 白名单刷新 | ✅ |
| v2.3.0-part3.4 | hotfix：低分打磨允许 confirmed + E2E issue 签名漂移修复 | ✅ |
| **v2.3.0-part3.5** | **feature:E2E 诊断包 Markdown 导出(发给 Claude 做异地诊断)** | ✅ |
| **v2.3.0-part3.6** | **hotfix:诊断包三 bug 修复 + 新立规则 49/50/51(工程纪律三条:拷贝替换 / 改完拉通 / 更新做减法)** | ✅ |
| **v2.3.0-part3.7** | **hotfix:F062 规则精度三连改(silent_except/except_print_only snippet 行号对齐 body 真实行 + field_unknown 变量名收窄 + prompt_wrong_key 历史 key 白名单)+ 诊断包第三段口径与第四段对齐** | ✅ |
| **v2.3.0-part3.8** | **hotfix:F062 白名单大扩展(7 文件)+ 6 批量路由 errors 收集 + 冗余代码清理 + 立规则 52** | ✅ |
| **v2.3.1** | **feature:精品资产生产线(F2 双视角 AI 判定 + composite_score 排序 + 批量封神 + 精品 Markdown/JSON 导出)+ 立规则 53-56** | ✅ |
| **v2.3.1-hotfix1** | **hotfix:annotations.title bug + premium_exporter F056 v1.0 升级 + validate_publish_json 校验函数;立规则 9 第 8 次应验** | ✅ |
| **v2.3.2** | **feature:F055 本地问答助手首版(866 行 qa_assistant + 7 路由 + Tab 3 + 三级降级链 + 4 板块回答 + 朋友试用模式)+ F056 单 HTML 查看器(零依赖渲染 v1.0 标准 13 字段)+ 立规则 57 首立 + 立规则 9 第 10/11 次应验** | ✅ |
| v2.3.3 | F020 冲突检测 + F030 知识关联网络 | 规划 |
| v2.4.0+ | 内容生产 / 采集（按需） | 远期 |
| v3.x | 云端产品化 | 远期 |

详见 `CHANGELOG.md`。

---

## 协作流程

### 五阶段迭代工作流

1. **需求提交** → 老唐描述问题
2. **影响范围评估** → Claude 给修改逻辑 + 决策建议
3. **代码交付** → 完整文件 + 项目文件全量更新 + 操作清单
4. **用户执行** → 备份 → 替换 → 推送 → 更新 Projects → 验证
5. **回滚** → 有问题新开对话

### Claude Projects 6 个项目文件

- `00_项目全景.md`：模块状态 / 迭代路线 / 商业化 / **新对话启动指南**
- `01_工程手册.md`：代码清单 / 立规则（**57 条**，分 4 类）/ 架构速查 / 模块结构 / **未来扩展指南**
- `02_知识体系.md`：分类 + 三层标签 + **v2.3.2 问答历史元数据**
- `03_Prompt手册.md`：**31 个 Prompt** 清单与接口契约
- `CHANGELOG.md`：近 3 版完整 + 早期摘要
- `README.md`：本文件

### GitHub 仓库

https://github.com/Fat-designer920/rural-revitalization-kb

---

## 关键约束（改代码时必读）

> 完整立规则见 `01_工程手册.md` §二（分数据层 / 代码层 / 交互层 / 流程层 4 类 48 条）。以下是高频命中项：

**环境约束**：
- **bat 文件**：GBK 编码 + CRLF 换行；不在 Python `-c` 参数内用 `%~dp0`
- **review.html**：零 emoji + 严格 ES5（无箭头函数、无 const/let、无 async/await、无模板字符串）
- **Flask**：`Response(html, mimetype="text/html; charset=utf-8")` 返回，不用 `render_template()`
- **R1 调用**：不传 temperature，不传图片，超时 300 秒，分段 ≤ 3000 字
- **OCR**：用硅基流动不用 DeepSeek

**数据约束**：
- **删除知识点必手动级联 annotations**（外键无 CASCADE）
- **schema 单一来源**：`init_tables()` 是唯一建表真相，migrate 脚本升完即退役
- **api_server 启动兜底 init_tables**（v2.3.0-part3.1 起）：避免老库缺新表
- **字段真名**：kp 表外键是 `final_category_id` 不是 `category_id`
- **存储/查询口径一致性**（v2.3.0-part3.2 起）：JSON 字段新增 SQL 查询前，必须对照存储侧写入逻辑确认存的是 name / code / 中文 / 英文 / 扁平列表 / 嵌套
- **筛选条件边界对齐业务现状**（v2.3.0-part3.4 起）：WHERE 子句的过滤条件过段时间后可能不符业务现状，业务流程变化（如就绪度联动上线）时必须回头校对所有依赖该状态字段的查询

**流程约束**：
- **长任务启动就绪性自检必须在 `_task_lock` 之前**（独立任务槽也要对齐这个模板）
- **6 个关键操作触发点必须先 `operation_hook(op_name)` 备份**
- **`_task["type"]` 前后端字面锁定**：F048 用 `"health"`，F062 用 `"e2e"`；独立任务槽（如 part3.2 的 `_qc_task`）不占用 `_task["type"]` 映射
- **跨版本调用外部模块方法前必须对照真实签名**（v2.3.0-part3.1 起铁律）：`grep -n "def <方法名>"` 查源码，不相信记忆不相信旧文档。part3.4 第三次应验（`upsert_e2e_issue` 漂移）

**AI 调用约束**：
- **Prompt 双 key 严格**：`system_prompt` / `user_prompt_template`
- **severity 严格三态**：`info` / `warning` / `error`（禁 `warn` 简写）
- **禁止包级静默降级**（try/except 顶层 import + None 兜底）

**前后端契约约束（v2.3.0-part3.3 起）**：
- 后端升级 API 返回结构时，前端所有消费点必须同步升级渲染逻辑
- 兜底 `if(!h) showToolResult(pre(JSON))` 是临时救命草不是长期方案

**质检铁律（v2.2.3）**：
- 每条知识点必须有 `qa_score + qa_source`
- 三级降级链：L0 批量 → L1 小批 → L2 逐条 → L3 规则兜底

**就绪度联动（v2.3.0-part3.2 保守预埋，v2.3.1 补齐完整版）**：
- 规则：`qa_score >= 4 AND content_readiness='draft' → 'quotable'`
- 只升不降，不碰 `premium`（editorial 轴与 qa 轴解耦）
- 质检补跑尾部自动触发；也可通过工具箱"就绪度联动"按钮手动触发

---

## 变更日志

详见 [CHANGELOG.md](CHANGELOG.md)。

---

## 许可证与支持

本项目为个人实战资产沉淀工具，当前阶段仅供老唐本人使用。未来商业化路径见 `00_项目全景.md`。
