# SkillScout 整合方案

> 3个侦察员发现14个GitHub项目。按商业价值+护城河+安全三原则筛选整合。

---

## 发现清单(14个项目)

### NLP领域(6个)

| # | 项目 | 许可证 | 亮点 | 整合价值 | 难度 |
|---|------|--------|------|---------|------|
| 1 | **BGE/FlagEmbedding**(BAAI) | MIT | 中文嵌入SOTA,6亿+下载,ONNX可导出 | **极高** — 替代TF-IDF,NPU本地推理 | 中 |
| 2 | Qwen3-Embedding(阿里) | Apache 2.0 | MTEB多语言#1 | 高 — API可调用,备选方案 | 低 |
| 3 | Jina Embeddings v4 | Apache 2.0 | 多模态,超OpenAI 12% | 中 — 多模态对政策文档OCR有用 | 中 |
| 4 | Youtu-Embedding(腾讯) | MIT | CMTEB 77.46 | 低 — 与BGE功能重叠 | 低 |
| 5 | Yuan-EB 2.0 | Apache 2.0 | C-MTEB检索81.76,轻量0.6B | 高 — NPU部署可行,备选 | 中 |
| 6 | Qwen3-VL-Embedding | Apache 2.0 | 文本+图片+视频 | 低 — 图片嵌入对政策文档OCR有用但远期 | 高 |

### 政府数据领域(2个)

| # | 项目 | 亮点 | 整合价值 | 难度 |
|---|------|------|---------|------|
| 7 | **China-Central-Policy-MCP** | gov.cn政策搜索+全文解析,MCP协议 | **极高** — 政策数据护城河 | 低 |
| 8 | Policy-Transparency-China-2024 | 学术cross-reference数据集+HTTP可访问性 | 中 — 数据质量参考 | 低 |

### 安全领域(6个)

| # | 项目 | 亮点 | 整合价值 | 难度 |
|---|------|------|---------|------|
| 9 | **sensitive-word**(houbb) | Java,DFA算法,6万+词,7万QPS | **极高** — 补强品牌红线检查 | 中 |
| 10 | Sensitive-lexicon | 持续更新中文敏感词库 | 高 — 直接可用 | 低 |
| 11 | Chinese-offensive-language-detect | Python,深度学习,6类有害内容 | 中 — 更智能但需GPU | 中 |
| 12 | go-sensitive-word | Go,DFA/AC自动机,2915+词 | 低 — Go语言,集成成本高 | 高 |
| 13 | Sensitive-lexicon-mcp | MCP Server包装敏感词库 | 低 — MCP协议,集成复杂 | 中 |
| 14 | textfilter(observerss) | 基础敏感词表 | 低 — 词表规模小 | 低 |

---

## 推荐整合: 3个核心项目

### 整合1: BGE/FlagEmbedding → NPU引擎(最高优先级)

**整合价值**: 替代当前sklearn TF-IDF,中文语义召回提升30-50%。这是QA助手质量的基础。

**整合方案**:
```
步骤1: 下载 BAAI/bge-small-zh-v1.5 (小型,24MB,ONNX兼容)
步骤2: 用 optimum-cli 转为 ONNX 格式 → data/models/embedding_model.onnx
步骤3: npu_engine.py 加载 ONNX 模型 → DirectML GPU推理
步骤4: 替代当前 char_wb TF-IDF → 语义级中文检索
步骤5: 对比评测: TF-IDF vs BGE recall@20
```

**商业价值**: QA助手检索质量直接决定用户付费意愿。差检索=差回答=用户流失。
**护城河**: 本地NPU推理=零API成本+用户数据不出本地=隐私优势。
**安全审查**: BGE是BAAI(北京智源)官方项目,MIT许可证,已通过安全扫描。

**工时**: Claude 4小时(模型下载+ONNX转换+集成)

---

### 整合2: China-Central-Policy-MCP → 政策数据库

**整合价值**: 直接对接gov.cn政策搜索,自动获取最新政策文档。这是政策数据护城河的核心。

**整合方案**:
```
步骤1: 研究 MCP 协议接口,理解其政策搜索API
步骤2: 将搜索结果接入 crawler_scheduler 的URL列表
步骤3: 政策标题→自动分类→自动加入爬取队列
步骤4: 监控特定政策关键词(全域土地整治/集体用地/专项债)→自动推送
```

**商业价值**: 政策变化第一时间捕获→政策日报产品直接受益→独家时效优势。
**护城河**: 自动化gov.cn监控=竞品无法匹敌的时效性。
**安全审查**: 只读取公开gov.cn数据,不涉及任何隐私/安全风险。

**工时**: Claude 2-3小时(接口对接+自动化管道)

---

### 整合3: sensitive-word → 品牌红线+安全门禁

**整合价值**: 当前brand_redlines.py只有18条硬编码规则(关键词级),敏感词库可扩展到6万+。

**整合方案**:
```
步骤1: 从GitHub下载sensitive-word词库(中文部分)
步骤2: 转换为Python可用的词表格式→data/safety/sensitive_words.txt
步骤3: 在brand_redlines.py中添加sensitive_word_check()方法
步骤4: SafetyFilter.inbound()集成敏感词检测
步骤5: 可配置: 严格模式(全量) vs 宽松模式(仅政治/色情/暴力)
```

**商业价值**: 更完善的内容安全=降低法律风险=品牌保护=客户信任。
**护城河**: 持续更新的敏感词库+本地检测=零隐私泄露(不调第三方API)。
**安全审查**: 词库来自GitHub开源项目,需审查是否有过度屏蔽风险。采用可配置模式: 默认宽松,老唐手动切换严格。

**工时**: Claude 2小时(词库转换+集成)

---

## 整合优先级与时间线

| 顺序 | 项目 | 工时 | 商业价值 | 依赖 |
|------|------|------|---------|------|
| **1** | BGE/FlagEmbedding → NPU | 4h | 极高(QA质量根基) | 无 |
| **2** | China-Central-Policy-MCP → 爬虫 | 3h | 极高(政策护城河) | 无 |
| **3** | sensitive-word → 安全门禁 | 2h | 高(品牌保护) | 无 |

**三项目完全独立,可并行执行。总工时: Claude 9小时。**

---

## 暂不整合的项目(理由)

| 项目 | 理由 |
|------|------|
| Qwen3-Embedding | BGE已够用,避免多模型维护成本 |
| Jina Embeddings | 多模态目前不是刚需 |
| Youtu-Embedding | 与BGE功能重叠 |
| Yuan-EB 2.0 | 0.6B轻量但质量不如BGE,v2.4.0再评估 |
| Qwen3-VL-Embedding | 图片嵌入远期需求 |
| Policy-Transparency-China-2024 | 学术项目,实用性有限 |
| go-sensitive-word | Go语言集成成本高 |
| Sensitive-lexicon-mcp | MCP协议复杂,直接下载词库更简单 |
| textfilter | 词表规模太小 |
| Chinese-offensive-language-detect | 深度学习模型需GPU,NPU暂不支持 |
