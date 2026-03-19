# 变更日志

## v1.0.1 -- 提取引擎增强

发布日期：2026-03-19

变更内容：
- 知识提取切换至DeepSeek R1模型(deepseek-reasoner)，深度推理分析
- 5个提取Prompt全面强化：要求全文逐段通读、细粒度不遗漏
- 新增MD5文件指纹去重，重复文件自动跳过
- 新增data/failed/文件夹，处理失败的文件自动隔离不堵塞队列
- 提取进度实时显示（文件序号、费用消耗、模型信息、段落进度）
- deepseek_client.py支持R1模型适配（超时延长300秒、不传temperature、费用含思考token）
- chat()/chat_with_json()新增model_override参数，可指定使用不同模型
- R1模型chat_with_json自动提高max_tokens至8192
- db_manager.py新增check_file_hash_exists()文件指纹查重方法
- 长文档分段阈值从6000字提高到12000字（适配R1长上下文能力）
- 智能去重：只跳过已成功提取知识点的文件，失败/空结果的允许重新提取
- 处理完毕后自动清理pending文件夹中的原始文件
- 修复全部11个bat文件的脚本路径错误
- 审核界面修复：标签编辑保存后正确显示、筛选状态联动、分类按编号排序
- 审核界面新增：标签芯片化编辑（AI推荐标签+下拉选择+新建标签）
- api_server.py新增/api/tags标签聚合接口

受影响文件：extractor.py, deepseek_client.py, prompt_templates.py, db_manager.py, api_server.py, review.html, 全部bat文件
数据库迁移：不需要

---

## v1.0.0 -- 核心版首次发布

发布日期：2026-03-18

变更内容：
- 核心工作流：文件读取->AI预处理->知识提取->人工审核->入库
- 10个Python脚本+11个bat+Flask审核界面
- SQLite 8张表+5种Prompt+API加密+费用保护+系统自检
- bat文件GBK编码,review.html纯ES5无emoji

受影响文件：全部
数据库迁移：不需要
