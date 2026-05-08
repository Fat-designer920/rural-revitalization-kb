# Deprecated Database Fields

These `knowledge_points` columns are retained for backward compatibility.
Do NOT use them in new code. Do NOT delete them (schema compatibility).

| Field | Reason Deprecated | All-Rows Status |
|-------|------------------|-----------------|
| `premium_client` | 精品系统 removed (2026-05) | All 0 |
| `premium_rfp` | Frozen by design v2.3.6 | All 0 |
| `premium_tier` | 精品判定 removed | All NULL |
| `premium_freshness_status` | Never populated | All NULL |

## When Safe To Drop

After the next major version where DB migration is explicitly planned.
Not before v3.0.
