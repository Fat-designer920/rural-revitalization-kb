# Future Notes

Ideas worth revisiting when the project reaches the appropriate stage.
None of these are implemented. Do not reference them as current capabilities.

## Archived Prompts (from prompt_templates.py cleanup 2026-05-08)

- **QA_DERIVATION_PROMPT**: Auto-generate Q&A pairs from confirmed KPs. Would serve the QA assistant with pre-built training data. Requires: confirmed KP volume > 500, QA usage data to validate quality.
- **EXPERIENCE_STRUCTURE_PROMPT**: Convert free-text 老唐 experience notes into structured KP format. Partially replaced by `scripts/feed_experience.py`.
- **ARCHITECTURE_SUGGESTION_PROMPT**: Auto-suggest category tree expansions. Low priority until category system shows gaps.
- **CONFLICT_DETECTION_PROMPT**: Detect contradictory KPs. Requires: larger KP volume, relation network maturity.
- **VERSION_DIFF_PROMPT**: Compare old vs new policy versions. Useful when policy update tracking is active.

## Placeholder Products (removed from api_server.py 2026-05-08)

- /course — 线上录播课 (5模块20课)
- /compliance — 项目合规自检工具
- /daily — 政策变化日报
- /templates — 模板工具包

## Code Standards

When ready to enforce formatting:
- `black agents/ scripts/` (31 files need reformatting)
- `ruff check --fix agents/ scripts/` (156 auto-fixable issues)
- 68 unused imports (F401) to clean
