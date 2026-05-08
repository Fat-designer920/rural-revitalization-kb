---
name: feedback-project-file-updates
description: 项目文件更新规范 — 改动前先读后改，版本号同步
type: feedback
---

# 项目文件更新规范

**Why**: 老唐的口头决策必须即时写入项目文件，否则下次对话丢失上下文。版本号、产品体系、Agent数量必须在所有文件中一致。

**How to apply**: 
1. 老唐做出产品/战略决策 → 立即写入 memory/ + 更新项目文件
2. 改动项目文件前先读当前内容，确认不冲突
3. 版本号变更时同步 CLAUDE.md / README / docs/00 / CHANGELOG
4. Agent数量变更时同步 CLAUDE.md / 01工程手册 / agent_orchestra.py
