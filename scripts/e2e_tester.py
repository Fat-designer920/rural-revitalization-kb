"""
e2e_tester.py - F062 端到端健康测试 Agent 引擎
路径：scripts/e2e_tester.py
版本：v2.3.6-part1
"""

import json
import time
import traceback
from datetime import datetime, timedelta


# 顶层 import — 禁止 try/except 降级(对话 A 立规则)


from scripts.prompts.prompt_templates import (
    E2E_RESPONSE_JUDGE_PROMPT,
    PROMPT_VERSION,
)
from scripts import static_analyzer



# static_analyzer 默认扫描的 scripts 清单(跟 static_analyzer._DEFAULT_SCRIPT_FILES 保持一致)
STATIC_SCAN_TARGETS = None  # None → 使用 static_analyzer 内置默认清单

# 启动就绪性自检的 5 个核心引擎(按模块路径)
READINESS_CHECK_TARGETS = [
    ("scripts.extractor", "知识提取引擎"),
    ("scripts.relation_analyzer", "知识关系分析引擎"),
    ("scripts.preprocessor", "预处理引擎"),
    ("scripts.experience_notes", "经验速记引擎"),
    ("scripts.health_checker", "体检引擎"),
]

# deep 档事件采样
RECENT_EVENTS_LOOKBACK_DAYS = 7
DEEP_EVENT_MAX_SAMPLES = 30  # V3 判断最多抽样 30 条事件

# V3 调用参数
V3_TIMEOUT = 120
V3_TEMPERATURE = 0.0

# 期望行为映射(喂给 V3 判断的 expected_behavior 字段)
# 按 endpoint 前缀粗匹配,未命中走通用兜底
EXPECTED_BEHAVIOR_MAP = {
    "/api/tools/extract":      "提取成功且全库入库,若触发 F057 截断补救应记 info 级事件并保持 200",
    "/api/tools/health":       "体检完成返回 total_score 和六维度明细,任一维度 AI 失败只记 warning 不整单 failed",
    "/api/tools/duplicate":    "重复检测输出分组,V3 精判失败应三级降级而非直接 500",
    "/api/tools/qa-backfill":  "质检补跑走三级降级链,禁止灰色地带",
    "/api/tools/batch":        "批量重跑只清 pending,保留 confirmed/ignored 审核工作",
    "/api/tools/polish":       "打磨采纳走 backup → update_kp → apply_suggestion 原子三步",
}
DEFAULT_EXPECTED_BEHAVIOR = "响应正常,无降级/抢救/跳过/异常继续关键词"

# 得分公式权重(quick 档 dim5 skipped,权重等比重分给其他五维)
DIM_WEIGHTS_DEEP = {
    "dim1": 0.12,
    "dim2": 0.20,
    "dim3": 0.16,
    "dim4": 0.12,
    "dim5": 0.24,
    "dim6": 0.16,
}
DIM_WEIGHTS_QUICK = {
    "dim1": 0.15,
    "dim2": 0.25,
    "dim3": 0.20,
    "dim4": 0.15,
    # dim5 skipped
    "dim6": 0.25,
}

# progress_callback 合法 stage 取值白名单
VALID_STAGES = {
    "init", "dim1_route", "dim2_readiness", "dim3_prompt",
    "dim4_field", "dim5_event", "dim6_smell", "done", "failed",
}


# 白名单二次过滤(对话 2 落地,基于对话 1 真实扫描产出)
# v2.3.0-part3.3 (2026-04-23) 刷新：基于 db_manager.py v2.3.0-part3.2 重扫
# 原因：part3.2 hotfix 新增 promote_readiness_by_qa_score /
#       get_readiness_promote_preview 两方法 + get_tag_distribution 改
#       pattern，导致 db_manager.py 下游所有行号漂移；原 41 条白名单全
#       部打不中，DIM4 issue 从个位数暴涨到 140，DIM6 从 0 涨到 94，
#       报告总分跌到 0 分（立规则 §5.8 已预告的坑，part3.2 遗漏执行）。


# dim4 字段契约 已知合理项(67 个 unique signature)
# 来源：v2.3.0-part3.3 用真实 db_manager.py v2.3.0-part3.2 (~2496 行)
#       通过 AST 遍历 Subscript + get('...') 识别"非 kp 表字段"访问点位
# 分类说明:
#   - SQL 聚合别名(cnt/tc/count):COUNT(*) as cnt / SUM(...) as tc,非 kp 字段
#   - 其他表字段:categories / tag_definitions / edit_history / duplicate_groups /
#                annotations / polish_suggestions / health_reports / e2e_issues /
#                api_endpoint_registry / e2e_test_reports 等
#   - 统计 dict key:stats/summary/result 内部累积用，非数据库字段
#   - JSON 字段:full_report_json / test_template_json / new_endpoints_json /
#                related_knowledge_ids / edited_fields / original_content /
#                suggested_content 等
# 维护规则(立规则 §5.8 强化)：每次 db_manager.py 重构后必须重扫更新本 set
DIM4_KNOWN_FALSE_POSITIVES = {
    # tag_definitions / categories / init 相关（init_tag_definitions）
    "4_field_contract|scripts/db_manager.py:477|field_unknown",   # cnt, categories 存在性检查
    "4_field_contract|scripts/db_manager.py:523|field_unknown",   # cnt, tag_definitions 存在性检查
    "4_field_contract|scripts/db_manager.py:527|field_unknown",   # tags, tag_definitions 结构
    "4_field_contract|scripts/db_manager.py:531|field_unknown",   # code/name/definition/group_name
    "4_field_contract|scripts/db_manager.py:533|field_unknown",   # values, tag_definitions dim
    "4_field_contract|scripts/db_manager.py:537|field_unknown",   # name, tag_definitions dim
    # knowledge_points 查询聚合（get_all_knowledge_points）
    "4_field_contract|scripts/db_manager.py:709|field_unknown",   # cnt, SQL COUNT 别名
    # get_tag_distribution（part3.2 改过的方法）
    "4_field_contract|scripts/db_manager.py:872|field_unknown",   # tag_code/tag_name, tag_definitions 表
    "4_field_contract|scripts/db_manager.py:888|field_unknown",   # cnt, SQL COUNT 别名
    "4_field_contract|scripts/db_manager.py:898|field_unknown",   # count, sort key
    # get_batch_rerun_candidate_files
    "4_field_contract|scripts/db_manager.py:933|field_unknown",   # has_annotations+cnt, 计算列
    # get_edit_history / restore_from_history
    "4_field_contract|scripts/db_manager.py:954|field_unknown",   # edited_fields, edit_history 表
    "4_field_contract|scripts/db_manager.py:963|field_unknown",   # edited_fields
    "4_field_contract|scripts/db_manager.py:969|field_unknown",   # old, history change dict
    # categories_tree
    "4_field_contract|scripts/db_manager.py:1032|field_unknown",  # children, tree dict
    # get_all_knowledge_for_upgrade
    "4_field_contract|scripts/db_manager.py:1063|field_unknown",  # related_knowledge_ids, 关联表
    "4_field_contract|scripts/db_manager.py:1064|field_unknown",  # related_knowledge_ids
    # get_freshness_summary
    "4_field_contract|scripts/db_manager.py:1147|field_unknown",  # cnt+outdated, summary dict
    "4_field_contract|scripts/db_manager.py:1150|field_unknown",  # cnt+unchecked
    "4_field_contract|scripts/db_manager.py:1156|field_unknown",  # cnt+expired
    "4_field_contract|scripts/db_manager.py:1163|field_unknown",  # cnt+expiring_soon
    "4_field_contract|scripts/db_manager.py:1169|field_unknown",  # cnt+fresh
    # get_policy_validation_summary
    "4_field_contract|scripts/db_manager.py:1211|field_unknown",  # cnt, SQL 聚合
    "4_field_contract|scripts/db_manager.py:1213|field_unknown",  # unvalidated, summary key
    "4_field_contract|scripts/db_manager.py:1215|field_unknown",  # validated
    "4_field_contract|scripts/db_manager.py:1217|field_unknown",  # pending
    "4_field_contract|scripts/db_manager.py:1219|field_unknown",  # exempt
    "4_field_contract|scripts/db_manager.py:1221|field_unknown",  # no_policy
    # get_today_api_cost / get_statistics
    "4_field_contract|scripts/db_manager.py:1249|field_unknown",  # tc, SUM today_api_cost 别名
    "4_field_contract|scripts/db_manager.py:1260|field_unknown",  # files+cnt, stats dict
    "4_field_contract|scripts/db_manager.py:1262|field_unknown",  # knowledge_points+cnt
    "4_field_contract|scripts/db_manager.py:1264|field_unknown",  # by_type+cnt
    "4_field_contract|scripts/db_manager.py:1265|field_unknown",  # today_api_cost
    "4_field_contract|scripts/db_manager.py:1267|field_unknown",  # total_confirmed+cnt
    "4_field_contract|scripts/db_manager.py:1269|field_unknown",  # total_pending+cnt
    "4_field_contract|scripts/db_manager.py:1271|field_unknown",  # pending_suggestions+cnt
    "4_field_contract|scripts/db_manager.py:1274|field_unknown",  # by_readiness+cnt
    "4_field_contract|scripts/db_manager.py:1276|field_unknown",  # by_access+cnt
    "4_field_contract|scripts/db_manager.py:1280|field_unknown",  # pending_duplicates+cnt
    "4_field_contract|scripts/db_manager.py:1282|field_unknown",  # pending_duplicates=0 兜底
    # get_duplicate_summary
    "4_field_contract|scripts/db_manager.py:1337|field_unknown",  # status, duplicate_groups 表
    "4_field_contract|scripts/db_manager.py:1338|field_unknown",  # status+cnt
    # get_annotations_by_kp
    "4_field_contract|scripts/db_manager.py:1387|field_unknown",  # tags, annotations 表
    "4_field_contract|scripts/db_manager.py:1389|field_unknown",  # tags JSON 解析
    "4_field_contract|scripts/db_manager.py:1391|field_unknown",  # tags 兜底
    # get_annotation_summary
    "4_field_contract|scripts/db_manager.py:1413|field_unknown",  # annotated_kps, summary key
    "4_field_contract|scripts/db_manager.py:1415|field_unknown",  # total_annotations
    "4_field_contract|scripts/db_manager.py:1418|field_unknown",  # by_type
    # get_latest_health_report / get_health_report_detail
    "4_field_contract|scripts/db_manager.py:1711|field_unknown",  # full_report_json, health_reports 表
    "4_field_contract|scripts/db_manager.py:1749|field_unknown",  # full_report_json
    # get_polish_suggestions_by_report
    "4_field_contract|scripts/db_manager.py:1810|field_unknown",  # original_content, polish_suggestions 表
    "4_field_contract|scripts/db_manager.py:1811|field_unknown",  # suggested_content
    # get_endpoint_registry / update_endpoint_last_tested
    "4_field_contract|scripts/db_manager.py:2225|field_unknown",  # test_template_json, api_endpoint_registry 表
    "4_field_contract|scripts/db_manager.py:2238|field_unknown",  # test_template_json
    "4_field_contract|scripts/db_manager.py:2239|field_unknown",  # test_template_json
    # get_latest_e2e_test_report / get_e2e_test_report_detail / get_e2e_test_report_list
    "4_field_contract|scripts/db_manager.py:2332|field_unknown",  # new_endpoints_json, e2e_test_reports 表
    "4_field_contract|scripts/db_manager.py:2333|field_unknown",  # new_endpoints_json
    "4_field_contract|scripts/db_manager.py:2346|field_unknown",  # new_endpoints_json
    "4_field_contract|scripts/db_manager.py:2347|field_unknown",  # new_endpoints_json
    "4_field_contract|scripts/db_manager.py:2348|field_unknown",  # full_report_json
    "4_field_contract|scripts/db_manager.py:2349|field_unknown",  # full_report_json
    "4_field_contract|scripts/db_manager.py:2376|field_unknown",  # new_endpoints_json
    "4_field_contract|scripts/db_manager.py:2377|field_unknown",  # new_endpoints_json
    # upsert_e2e_issue
    "4_field_contract|scripts/db_manager.py:2445|field_unknown",  # issue_id, e2e_issues 表
    "4_field_contract|scripts/db_manager.py:2446|field_unknown",  # status
    "4_field_contract|scripts/db_manager.py:2447|field_unknown",  # occurrence_count
    "4_field_contract|scripts/db_manager.py:2448|field_unknown",  # first_seen_at
    # ===== part3.8 跨文件扩展 =====
    # api_server.py - get_knowledge_point 已通过 LEFT JOIN source_files 把
    # renamed_filename/original_filename 带进 kp dict,规则前提不知此事
    "4_field_contract|scripts/api_server.py:830|field_unknown",
    # extractor.py - kp 此处是 AI 返回的 JSON dict,不是 DB kp 对象
    # (_sanitize_tags 里的 suggested_readiness/suggested_authority/suggested_category_code)
    "4_field_contract|scripts/extractor.py:595|field_unknown",
    "4_field_contract|scripts/extractor.py:598|field_unknown",
    "4_field_contract|scripts/extractor.py:1744|field_unknown",
    # health_checker.py - source_file_name/source_file 新老字段兼容,
    # excerpt 来自 AI 返回结构
    "4_field_contract|scripts/health_checker.py:805|field_unknown",
    "4_field_contract|scripts/health_checker.py:832|field_unknown",
    "4_field_contract|scripts/health_checker.py:1231|field_unknown",
    "4_field_contract|scripts/health_checker.py:1232|field_unknown",
}

# dim6 代码异味 已知合理项
# part3.8 升级说明:
#   · static_analyzer 在 part3.7 统一改用 body[0].lineno 作为 signature 锚点,
#     以前 "except 行 + body 行双覆盖" 简化为仅 body 行(pass / print 行)
#   · 白名单从 db_manager 单文件扩展到 7 个文件,覆盖批量路由外的所有合理兜底
#   · 6 处批量路由 (api_server.py 541/558/570/620/646/970) 不进白名单,
#     走代码改造路径(except Exception as e: errors.append),E2 方案
DIM6_KNOWN_FALSE_POSITIVES = {
    # -----------------------------------------------------------------
    # db_manager.py(漂移对齐 v2.3.0-part3.4 真实行号)
    # -----------------------------------------------------------------
    # qa_score int 转换失败,筛选器入参容忍
    "6_code_smell|scripts/db_manager.py:714|smell_silent_except",
    # edited_fields JSON 解析失败,向下兼容老数据
    "6_code_smell|scripts/db_manager.py:974|smell_silent_except",
    # duplicate_groups 表可能不存在,向下兼容老库
    "6_code_smell|scripts/db_manager.py:1359|smell_silent_except",
    # annotations 统计失败兜底,仪表盘非关键聚合
    "6_code_smell|scripts/db_manager.py:1439|smell_silent_except",
    # print 失败兜底(Windows CMD 编码异常),日志非关键
    "6_code_smell|scripts/db_manager.py:1861|smell_silent_except",
    # 时间解析失败兜底,偶发升级非关键逻辑
    "6_code_smell|scripts/db_manager.py:2488|smell_silent_except",
    # -----------------------------------------------------------------
    # api_server.py 非批量 silent_except (22 条 warning)
    # -----------------------------------------------------------------
    "6_code_smell|scripts/api_server.py:312|smell_silent_except",   # signature introspect 失败
    "6_code_smell|scripts/api_server.py:693|smell_silent_except",   # ai_extracted_content JSON 解析
    "6_code_smell|scripts/api_server.py:1089|smell_silent_except",  # tags JSON 解析
    "6_code_smell|scripts/api_server.py:1275|smell_silent_except",  # config 读取兜底
    "6_code_smell|scripts/api_server.py:1523|smell_silent_except",  # config 读取兜底
    "6_code_smell|scripts/api_server.py:1558|smell_silent_except",  # progress_cb 回调失败
    "6_code_smell|scripts/api_server.py:1678|smell_silent_except",  # qc_rerun_summary 失败
    "6_code_smell|scripts/api_server.py:1737|smell_silent_except",  # log_event 失败
    "6_code_smell|scripts/api_server.py:1954|smell_silent_except",  # config 读取兜底
    "6_code_smell|scripts/api_server.py:2006|smell_silent_except",  # daily_cost_limit 读取兜底
    "6_code_smell|scripts/api_server.py:2313|smell_silent_except",  # 迁移模块可选 ImportError
    "6_code_smell|scripts/api_server.py:2485|smell_silent_except",  # JSON 非标准保留原字符串
    "6_code_smell|scripts/api_server.py:2597|smell_silent_except",  # int 转换兜底
    "6_code_smell|scripts/api_server.py:2741|smell_silent_except",  # log_event 埋点失败
    "6_code_smell|scripts/api_server.py:3024|smell_silent_except",  # log_event 埋点失败
    "6_code_smell|scripts/api_server.py:3126|smell_silent_except",  # log_event 埋点失败
    "6_code_smell|scripts/api_server.py:3179|smell_silent_except",  # log_event 埋点失败
    "6_code_smell|scripts/api_server.py:3320|smell_silent_except",  # full_report 解析失败
    "6_code_smell|scripts/api_server.py:3360|smell_silent_except",  # log_event 埋点失败
    "6_code_smell|scripts/api_server.py:3510|smell_silent_except",  # log_event 埋点失败
    "6_code_smell|scripts/api_server.py:3526|smell_silent_except",  # log_event 埋点失败
    "6_code_smell|scripts/api_server.py:3642|smell_silent_except",  # log_event 埋点失败
    # -----------------------------------------------------------------
    # api_server.py info 级 except_print_only (6 条)
    # -----------------------------------------------------------------
    "6_code_smell|scripts/api_server.py:188|smell_except_print_only",   # init_tables 启动兜底 print WARN
    "6_code_smell|scripts/api_server.py:2315|smell_except_print_only",  # 迁移失败 print WARN
    "6_code_smell|scripts/api_server.py:2322|smell_except_print_only",  # set_model 失败 print WARN
    "6_code_smell|scripts/api_server.py:2359|smell_except_print_only",  # 重置源文件状态 print WARN
    "6_code_smell|scripts/api_server.py:2397|smell_except_print_only",  # 分类建议检查 print WARN
    "6_code_smell|scripts/api_server.py:3672|smell_except_print_only",  # DB 健康检查 print WARN
    # -----------------------------------------------------------------
    # extractor.py silent_except (4 条 warning,冗余 10 条已在 part3.8 删除)
    # -----------------------------------------------------------------
    "6_code_smell|scripts/extractor.py:176|smell_silent_except",   # progress_callback 失败
    "6_code_smell|scripts/extractor.py:450|smell_silent_except",   # truncation_count 增量失败
    "6_code_smell|scripts/extractor.py:709|smell_silent_except",   # segment_plan 保存失败
    "6_code_smell|scripts/extractor.py:1451|smell_silent_except",  # float 转换失败
    # -----------------------------------------------------------------
    # extractor.py info 级 except_print_only (17 条,其中 2033/2035 在 main 内漂到 2012/2014)
    # -----------------------------------------------------------------
    "6_code_smell|scripts/extractor.py:228|smell_except_print_only",
    "6_code_smell|scripts/extractor.py:520|smell_except_print_only",
    "6_code_smell|scripts/extractor.py:538|smell_except_print_only",
    "6_code_smell|scripts/extractor.py:554|smell_except_print_only",
    "6_code_smell|scripts/extractor.py:635|smell_except_print_only",
    "6_code_smell|scripts/extractor.py:675|smell_except_print_only",
    "6_code_smell|scripts/extractor.py:972|smell_except_print_only",
    "6_code_smell|scripts/extractor.py:974|smell_except_print_only",
    "6_code_smell|scripts/extractor.py:1561|smell_except_print_only",
    "6_code_smell|scripts/extractor.py:1563|smell_except_print_only",
    "6_code_smell|scripts/extractor.py:1791|smell_except_print_only",
    "6_code_smell|scripts/extractor.py:1816|smell_except_print_only",
    "6_code_smell|scripts/extractor.py:1818|smell_except_print_only",
    "6_code_smell|scripts/extractor.py:1830|smell_except_print_only",
    "6_code_smell|scripts/extractor.py:1832|smell_except_print_only",
    "6_code_smell|scripts/extractor.py:2012|smell_except_print_only",  # KeyboardInterrupt 取消
    "6_code_smell|scripts/extractor.py:2014|smell_except_print_only",  # main Exception print
    # -----------------------------------------------------------------
    # health_checker.py silent_except (6 条 warning)
    # -----------------------------------------------------------------
    "6_code_smell|scripts/health_checker.py:244|smell_silent_except",   # 体检失败日志兜底
    "6_code_smell|scripts/health_checker.py:498|smell_silent_except",   # int 转换兜底
    "6_code_smell|scripts/health_checker.py:1201|smell_silent_except",  # 成本累计兜底
    "6_code_smell|scripts/health_checker.py:1257|smell_silent_except",  # JSON 解析兜底
    "6_code_smell|scripts/health_checker.py:1288|smell_silent_except",  # log_event fallback 的 fallback
    "6_code_smell|scripts/health_checker.py:1301|smell_silent_except",  # progress emit 失败
    # -----------------------------------------------------------------
    # relation_analyzer.py(v2.3.5-part1 替代 duplicate_checker.py)
    # silent_except 1 条(ai_extracted_content JSON 解析) + except_print_only 3 条
    # -----------------------------------------------------------------
    "6_code_smell|scripts/relation_analyzer.py:139|smell_silent_except",   # ai_extracted_content JSON 解析兜底
    "6_code_smell|scripts/relation_analyzer.py:350|smell_except_print_only",  # AI 判别失败 print
    "6_code_smell|scripts/relation_analyzer.py:447|smell_except_print_only",  # main DeepSeekClient 初始化失败 print
    "6_code_smell|scripts/relation_analyzer.py:452|smell_except_print_only",  # main 整体兜底 print + traceback
    # -----------------------------------------------------------------
    # preprocessor.py info 级 except_print_only (6 条)
    # -----------------------------------------------------------------
    "6_code_smell|scripts/preprocessor.py:44|smell_except_print_only",   # 清理旧文件失败
    "6_code_smell|scripts/preprocessor.py:52|smell_except_print_only",   # 清理旧缓存失败
    "6_code_smell|scripts/preprocessor.py:95|smell_except_print_only",   # 清理 source_files 失败
    "6_code_smell|scripts/preprocessor.py:117|smell_except_print_only",  # 清理旧记录失败
    "6_code_smell|scripts/preprocessor.py:127|smell_except_print_only",  # 清理旧记录失败
    "6_code_smell|scripts/preprocessor.py:202|smell_except_print_only",  # main Exception print
    # -----------------------------------------------------------------
    # backup_manager.py info 级 except_print_only (5 条)
    # -----------------------------------------------------------------
    "6_code_smell|scripts/backup_manager.py:302|smell_except_print_only",  # 清理策略异常
    "6_code_smell|scripts/backup_manager.py:327|smell_except_print_only",  # cleanup_by_op_name 失败
    "6_code_smell|scripts/backup_manager.py:369|smell_except_print_only",  # enforce_size_limit 失败
    "6_code_smell|scripts/backup_manager.py:399|smell_except_print_only",  # _log_backup_event 失败
    "6_code_smell|scripts/backup_manager.py:526|smell_except_print_only",  # 数字格式错误提示
}

# part3.8 新增:白名单覆盖范围(文件维度)
# 用途:供 e2e_diagnosis_exporter.py 第三段按文件分类展示
# "✅ 白名单覆盖内但漂移 X 条" vs "⚪ 未覆盖范围(需要独立治理)"
# 维护纪律:新文件首次进入 E2E 扫描时,**先加入本集合**再逐条判断白名单条目
WHITELIST_COVERAGE = {
    "scripts/db_manager.py",
    "scripts/api_server.py",
    "scripts/extractor.py",
    "scripts/health_checker.py",
    "scripts/relation_analyzer.py",
    "scripts/preprocessor.py",
    "scripts/backup_manager.py",
}

# 白名单原因映射(供 issue.detail.filtered_out 回写,对话 3 前端"已知合理项"折叠用)
WHITELIST_REASONS = {
    # dim4
    "scripts/db_manager.py:477":  "categories 存在性检查 cnt 别名",
    "scripts/db_manager.py:523":  "tag_definitions 存在性检查 cnt 别名",
    "scripts/db_manager.py:527":  "tag_definitions 结构字段 tags",
    "scripts/db_manager.py:531":  "tag_definitions 字段 code/name/definition/group_name",
    "scripts/db_manager.py:533":  "tag_definitions dim 字段 values",
    "scripts/db_manager.py:537":  "tag_definitions dim 字段 name",
    "scripts/db_manager.py:709":  "SQL COUNT 别名 cnt",
    "scripts/db_manager.py:872":  "tag_definitions 表 tag_code/tag_name 字段",
    "scripts/db_manager.py:888":  "SQL COUNT 别名 cnt",
    "scripts/db_manager.py:898":  "tag_distribution sort key count",
    "scripts/db_manager.py:933":  "SQL LEFT JOIN 计算列 has_annotations+cnt",
    "scripts/db_manager.py:954":  "edit_history 表 edited_fields 字段",
    "scripts/db_manager.py:963":  "edit_history 表 edited_fields 字段",
    "scripts/db_manager.py:969":  "edit_history change dict old 键",
    "scripts/db_manager.py:1032": "tree dict children 键",
    "scripts/db_manager.py:1063": "关联表 related_knowledge_ids 字段",
    "scripts/db_manager.py:1064": "关联表 related_knowledge_ids 兜底",
    "scripts/db_manager.py:1147": "freshness summary outdated+cnt",
    "scripts/db_manager.py:1150": "freshness summary unchecked+cnt",
    "scripts/db_manager.py:1156": "freshness summary expired+cnt",
    "scripts/db_manager.py:1163": "freshness summary expiring_soon+cnt",
    "scripts/db_manager.py:1169": "freshness summary fresh+cnt",
    "scripts/db_manager.py:1211": "policy summary 聚合 cnt",
    "scripts/db_manager.py:1213": "policy summary unvalidated key",
    "scripts/db_manager.py:1215": "policy summary validated key",
    "scripts/db_manager.py:1217": "policy summary pending key",
    "scripts/db_manager.py:1219": "policy summary exempt key",
    "scripts/db_manager.py:1221": "policy summary no_policy key",
    "scripts/db_manager.py:1249": "SQL SUM 别名 tc (today_api_cost)",
    "scripts/db_manager.py:1260": "stats dict files+cnt",
    "scripts/db_manager.py:1262": "stats dict knowledge_points+cnt",
    "scripts/db_manager.py:1264": "stats dict by_type+cnt",
    "scripts/db_manager.py:1265": "stats dict today_api_cost",
    "scripts/db_manager.py:1267": "stats dict total_confirmed+cnt",
    "scripts/db_manager.py:1269": "stats dict total_pending+cnt",
    "scripts/db_manager.py:1271": "stats dict pending_suggestions+cnt",
    "scripts/db_manager.py:1274": "stats dict by_readiness+cnt",
    "scripts/db_manager.py:1276": "stats dict by_access+cnt",
    "scripts/db_manager.py:1280": "stats dict pending_duplicates+cnt",
    "scripts/db_manager.py:1282": "stats dict pending_duplicates 兜底",
    "scripts/db_manager.py:1337": "duplicate_groups 表 status 字段",
    "scripts/db_manager.py:1338": "duplicate_groups status+cnt",
    "scripts/db_manager.py:1387": "annotations 表 tags 字段",
    "scripts/db_manager.py:1389": "annotations tags JSON 解析",
    "scripts/db_manager.py:1391": "annotations tags 兜底",
    "scripts/db_manager.py:1413": "annotation summary annotated_kps",
    "scripts/db_manager.py:1415": "annotation summary total_annotations",
    "scripts/db_manager.py:1418": "annotation summary by_type",
    "scripts/db_manager.py:1711": "health_reports 表 full_report_json 字段",
    "scripts/db_manager.py:1749": "health_reports 表 full_report_json 字段",
    "scripts/db_manager.py:1810": "polish_suggestions 表 original_content 字段",
    "scripts/db_manager.py:1811": "polish_suggestions 表 suggested_content 字段",
    "scripts/db_manager.py:2225": "api_endpoint_registry 表 test_template_json 字段",
    "scripts/db_manager.py:2238": "api_endpoint_registry test_template_json 字段",
    "scripts/db_manager.py:2239": "api_endpoint_registry test_template_json 字段",
    "scripts/db_manager.py:2332": "e2e_test_reports new_endpoints_json 字段",
    "scripts/db_manager.py:2333": "e2e_test_reports new_endpoints_json 字段",
    "scripts/db_manager.py:2346": "e2e_test_reports new_endpoints_json 字段",
    "scripts/db_manager.py:2347": "e2e_test_reports new_endpoints_json 字段",
    "scripts/db_manager.py:2348": "e2e_test_reports full_report_json 字段",
    "scripts/db_manager.py:2349": "e2e_test_reports full_report_json 字段",
    "scripts/db_manager.py:2376": "e2e_test_reports new_endpoints_json 字段",
    "scripts/db_manager.py:2377": "e2e_test_reports new_endpoints_json 字段",
    "scripts/db_manager.py:2445": "e2e_issues 表 issue_id 字段",
    "scripts/db_manager.py:2446": "e2e_issues 表 status 字段",
    "scripts/db_manager.py:2447": "e2e_issues 表 occurrence_count 字段",
    "scripts/db_manager.py:2448": "e2e_issues 表 first_seen_at 字段",
    # part3.8 dim4 新增(跨文件扩展)
    "scripts/api_server.py:830":       "get_knowledge_point LEFT JOIN source_files 合成字段",
    "scripts/extractor.py:595":        "AI 返回 JSON dict 的 suggested_readiness 字段",
    "scripts/extractor.py:598":        "AI 返回 JSON dict 的 suggested_authority 字段",
    "scripts/extractor.py:1744":       "AI 返回 JSON dict 的 suggested_category_code 字段",
    "scripts/health_checker.py:805":   "source_file_name/source_file 新老字段兼容(unknown 兜底)",
    "scripts/health_checker.py:832":   "source_file_name/source_file 新老字段兼容(unknown 兜底)",
    "scripts/health_checker.py:1231":  "source_file_name/source_file 新老字段兼容",
    "scripts/health_checker.py:1232":  "AI 返回 excerpt 字段",
    # -----------------------------------------------------------------
    # dim6 db_manager 漂移对齐 v2.3.0-part3.4(part3.8 更新)
    # -----------------------------------------------------------------
    "scripts/db_manager.py:714":  "qa_score int 转换失败兜底,筛选器入参容忍",
    "scripts/db_manager.py:974":  "edited_fields JSON 解析失败,向下兼容老数据",
    "scripts/db_manager.py:1359": "duplicate_groups 表可能不存在,向下兼容老库",
    "scripts/db_manager.py:1439": "annotations 统计失败兜底,仪表盘非关键聚合",
    "scripts/db_manager.py:1861": "print 失败兜底(Windows CMD 编码异常),日志非关键",
    "scripts/db_manager.py:2488": "时间解析失败兜底,偶发升级非关键逻辑",
    # -----------------------------------------------------------------
    # dim6 api_server.py 非批量(22 warning + 6 info)
    # -----------------------------------------------------------------
    "scripts/api_server.py:312":  "_quality_check 签名 introspect 失败(C 扩展等)降级",
    "scripts/api_server.py:693":  "ai_extracted_content JSON 解析失败,保留原字符串",
    "scripts/api_server.py:1089": "tags JSON 解析失败兜底",
    "scripts/api_server.py:1275": "config.json 读取失败,默认路径兜底",
    "scripts/api_server.py:1523": "config.json 读取失败,默认路径兜底",
    "scripts/api_server.py:1558": "progress_cb 回调失败,异步化场景非关键",
    "scripts/api_server.py:1678": "get_qc_rerun_summary 查询失败兜底",
    "scripts/api_server.py:1737": "log_operation_event 埋点失败,非关键",
    "scripts/api_server.py:1954": "config.json 读取失败,默认路径兜底",
    "scripts/api_server.py:2006": "daily_cost_limit 读取失败,默认 0",
    "scripts/api_server.py:2313": "迁移脚本可选 ImportError 降级",
    "scripts/api_server.py:2485": "JSON 字段非标准保留原字符串",
    "scripts/api_server.py:2597": "int 转换失败兜底,进度显示非关键",
    "scripts/api_server.py:2741": "log_operation_event 埋点失败",
    "scripts/api_server.py:3024": "log_operation_event 埋点失败",
    "scripts/api_server.py:3126": "log_operation_event 埋点失败",
    "scripts/api_server.py:3179": "log_operation_event 埋点失败",
    "scripts/api_server.py:3320": "full_report_json 解析失败兜底",
    "scripts/api_server.py:3360": "log_operation_event 埋点失败",
    "scripts/api_server.py:3510": "log_operation_event 埋点失败",
    "scripts/api_server.py:3526": "log_operation_event 埋点失败",
    "scripts/api_server.py:3642": "log_operation_event 埋点失败",
    "scripts/api_server.py:188":  "init_tables 启动兜底失败 WARN print",
    "scripts/api_server.py:2315": "迁移失败 WARN print",
    "scripts/api_server.py:2322": "set_model 失败 WARN print",
    "scripts/api_server.py:2359": "重置源文件状态失败 WARN print",
    "scripts/api_server.py:2397": "分类建议检查失败 WARN print",
    "scripts/api_server.py:3672": "DB 健康检查失败 WARN print",
    # -----------------------------------------------------------------
    # dim6 extractor.py (4 warning + 17 info)
    # -----------------------------------------------------------------
    "scripts/extractor.py:176":  "progress_callback 失败兜底",
    "scripts/extractor.py:450":  "truncation_count 增量失败兜底",
    "scripts/extractor.py:709":  "segment_plan 保存失败兜底",
    "scripts/extractor.py:1451": "float 转换失败兜底",
    "scripts/extractor.py:228":  "pending 文件清理失败 print",
    "scripts/extractor.py:520":  "事件日志失败 print",
    "scripts/extractor.py:538":  "文件归档失败 print",
    "scripts/extractor.py:554":  "文件隔离失败 print",
    "scripts/extractor.py:635":  "预分析出错 print",
    "scripts/extractor.py:675":  "结构摘要失败 print",
    "scripts/extractor.py:972":  "费用达上限跳过补漏 print",
    "scripts/extractor.py:974":  "补漏检查失败 print",
    "scripts/extractor.py:1561": "AI 分类建议费用上限 print",
    "scripts/extractor.py:1563": "AI 分类建议出错 print",
    "scripts/extractor.py:1791": "知识点入库失败 print",
    "scripts/extractor.py:1816": "政策校验费用上限 print",
    "scripts/extractor.py:1818": "政策校验出错 print",
    "scripts/extractor.py:1830": "重复检测费用上限 print",
    "scripts/extractor.py:1832": "重复检测出错 print",
    "scripts/extractor.py:2012": "main KeyboardInterrupt 取消 print",
    "scripts/extractor.py:2014": "main Exception print",
    # -----------------------------------------------------------------
    # dim6 health_checker.py (6 warning)
    # -----------------------------------------------------------------
    "scripts/health_checker.py:244":  "体检失败日志兜底",
    "scripts/health_checker.py:498":  "int 转换失败兜底",
    "scripts/health_checker.py:1201": "成本累计兜底",
    "scripts/health_checker.py:1257": "JSON 解析兜底",
    "scripts/health_checker.py:1288": "log_event fallback 的 fallback (print 失败)",
    "scripts/health_checker.py:1301": "progress emit 失败",
    # -----------------------------------------------------------------
    # dim6 relation_analyzer.py(v2.3.5-part1 替代 duplicate_checker.py)
    # silent_except 1 + except_print_only 3 = 4 条
    # -----------------------------------------------------------------
    "scripts/relation_analyzer.py:139": "ai_extracted_content JSON 解析兜底",
    "scripts/relation_analyzer.py:350": "AI 判别失败 print",
    "scripts/relation_analyzer.py:447": "main DeepSeekClient 初始化失败 print",
    "scripts/relation_analyzer.py:452": "main 整体兜底 print + traceback",
    # -----------------------------------------------------------------
    # dim6 preprocessor.py (6 info)
    # -----------------------------------------------------------------
    "scripts/preprocessor.py:44":  "清理旧文件失败 print",
    "scripts/preprocessor.py:52":  "清理旧缓存失败 print",
    "scripts/preprocessor.py:95":  "清理 source_files 记录失败 print",
    "scripts/preprocessor.py:117": "清理旧记录失败 print",
    "scripts/preprocessor.py:127": "清理旧记录失败 print",
    "scripts/preprocessor.py:202": "main Exception print",
    # -----------------------------------------------------------------
    # dim6 backup_manager.py (5 info)
    # -----------------------------------------------------------------
    "scripts/backup_manager.py:302": "清理策略异常 print (不影响主操作)",
    "scripts/backup_manager.py:327": "cleanup_by_op_name 删除失败 print",
    "scripts/backup_manager.py:369": "enforce_size_limit 删除失败 print",
    "scripts/backup_manager.py:399": "_log_backup_event 失败 print",
    "scripts/backup_manager.py:526": "数字格式错误提示 print",
}

# 成本单价(估算,对齐 health_checker)
V3_COST_PER_1K_INPUT = 0.0014
V3_COST_PER_1K_OUTPUT = 0.0028



class E2ETester(object):
    """端到端健康测试 Agent 引擎。"""

    def __init__(self, db, client, progress_callback=None):
        self.db = db
        self.client = client
        self.progress_callback = progress_callback

        # 运行态状态
        self._v3_call_count = 0
        self._cost_accumulator = 0.0
        self._started_at = None

    # --------------------------------------------------------
    # 主入口
    # --------------------------------------------------------

    def run_full_scan(self, scan_depth="quick"):
        """主入口。scan_depth: 'quick' | 'deep'。

        返回 dict:
          {success, report_id, scan_depth, total_score, dims, summary,
           new_endpoints, v3_call_count, cost_estimate, duration_seconds}
        """
        if scan_depth not in ("quick", "deep"):
            scan_depth = "quick"

        self._v3_call_count = 0
        self._cost_accumulator = 0.0
        self._started_at = time.time()

        self._safe_log_event("e2e_scan_start", "info",
                             {"scan_depth": scan_depth,
                              "prompt_version": PROMPT_VERSION})
        self._emit_progress("init", 0, 8, "初始化: 端到端健康测试开始({} 档)".format(scan_depth))

        try:
            return self._run_pipeline(scan_depth)
        except Exception as e:
            tb = traceback.format_exc()
            self._safe_log_event("e2e_scan_failed", "error",
                                 {"err": str(e), "trace": tb[:2000]})
            self._emit_progress("failed", 8, 8, "扫描失败: " + str(e)[:120])
            return {
                "success": False,
                "error": str(e),
                "trace": tb,
                "scan_depth": scan_depth,
                "duration_seconds": int(time.time() - self._started_at),
            }

    def _run_pipeline(self, scan_depth):
        """六维度流水线。"""
        all_issues = []
        new_endpoints = []
        dims_result = {}

        # --- 维度 1 路由自省 ---
        self._emit_progress("dim1_route", 1, 8, "维度 1/6: 路由自省")
        dim1 = self._safe_dim("dim1", self._dim1_route_introspect)
        dims_result["dim1"] = dim1
        all_issues.extend(dim1.get("issues") or [])
        new_endpoints = dim1.get("new_endpoints") or []

        # --- 维度 2 启动就绪性 ---
        self._emit_progress("dim2_readiness", 2, 8, "维度 2/6: 启动就绪性自检")
        dim2 = self._safe_dim("dim2", self._dim2_readiness)
        dims_result["dim2"] = dim2
        all_issues.extend(dim2.get("issues") or [])

        # --- 静态分析一次跑完 dim3/dim4/dim6(共享 static_scan 结果) ---
        static_bundle = self._run_static_scan_shared()

        # --- 维度 3 Prompt 调用一致性 ---
        self._emit_progress("dim3_prompt", 3, 8, "维度 3/6: Prompt 调用一致性扫描")
        dim3 = self._safe_dim("dim3", lambda: self._dim3_prompt_call(static_bundle))
        dims_result["dim3"] = dim3
        all_issues.extend(dim3.get("issues") or [])

        # --- 维度 4 字段契约 ---
        self._emit_progress("dim4_field", 4, 8, "维度 4/6: 字段契约扫描")
        dim4 = self._safe_dim("dim4", lambda: self._dim4_field_contract(static_bundle))
        dims_result["dim4"] = dim4
        all_issues.extend(dim4.get("issues") or [])

        # --- 维度 5 事件语义(仅 deep) ---
        if scan_depth == "deep":
            self._emit_progress("dim5_event", 5, 8, "维度 5/6: V3 事件语义判断")
            dim5 = self._safe_dim("dim5", self._dim5_event_v3_deep)
            dims_result["dim5"] = dim5
            all_issues.extend(dim5.get("issues") or [])
        else:
            dims_result["dim5"] = {
                "score": None,
                "skipped": True,
                "reason": "quick 档不执行 V3 事件判断",
                "issues": [],
                "detail": {"scan_depth": "quick"},
            }

        # --- 维度 6 代码异味 ---
        self._emit_progress("dim6_smell", 7, 8, "维度 6/6: 代码异味扫描")
        dim6 = self._safe_dim("dim6", lambda: self._dim6_code_smell(static_bundle))
        dims_result["dim6"] = dim6
        all_issues.extend(dim6.get("issues") or [])

        # --- 汇总分数 ---
        total_score = self._compute_total_score(dims_result, scan_depth)
        summary = self._compute_summary(all_issues)

        # --- 保存报告(先保存拿 report_id,再写 issue,part3.4 调整顺序) ---
        duration = int(time.time() - self._started_at)
        # part3.6: 把计算总分用的权重字典写进 full_report,供 exporter 渲染加权贡献列
        dim_weights = DIM_WEIGHTS_DEEP if scan_depth == "deep" else DIM_WEIGHTS_QUICK
        full_report = {
            "scan_depth": scan_depth,
            "total_score": total_score,
            "dims": dims_result,
            "dim_weights": dict(dim_weights),
            "summary": summary,
            "new_endpoints": new_endpoints,
            "v3_call_count": self._v3_call_count,
            "cost_estimate": round(self._cost_accumulator, 6),
            "duration_seconds": duration,
            "prompt_version": PROMPT_VERSION,
            "generated_at": self._now_iso(),
        }

        report_id = self._save_report(
            trigger_type="manual",
            scan_depth=scan_depth,
            summary=summary,
            new_endpoints=new_endpoints,
            full_report=full_report,
        )

        # --- 写入 issue(批量 upsert,必须在 report_id 就绪后执行,part3.4) ---
        upserted_count, filtered_count = self._write_issues(all_issues, report_id)
        self._safe_log_event("e2e_issue_summary", "info", {
            "report_id": report_id,
            "upserted_count": upserted_count,
            "filtered_count": filtered_count,
        })

        self._safe_log_event("e2e_scan_done", "info", {
            "report_id": report_id,
            "scan_depth": scan_depth,
            "total_score": total_score,
            "passed": summary.get("passed_count", 0),
            "failed": summary.get("failed_count", 0),
            "warning": summary.get("warning_count", 0),
            "duration_seconds": duration,
        })
        self._emit_progress("done", 8, 8,
                            "扫描完成: 总分 {} 分,问题 {} 个".format(total_score, len(all_issues)))

        return {
            "success": True,
            "report_id": report_id,
            "scan_depth": scan_depth,
            "total_score": total_score,
            "dims": dims_result,
            "summary": summary,
            "new_endpoints": new_endpoints,
            "v3_call_count": self._v3_call_count,
            "cost_estimate": round(self._cost_accumulator, 6),
            "duration_seconds": duration,
        }

    # --------------------------------------------------------
    # 静态扫描一次跑完(共享结果给 dim3/dim4/dim6)
    # --------------------------------------------------------

    def _run_static_scan_shared(self):
        """一次调用 static_analyzer.run_static_scan,结果被 dim3/dim4/dim6 共享消费。"""
        # 构造 db_schema_snapshot(维度④ 字段契约需要)
        schema_snapshot = self._build_schema_snapshot()
        try:
            result = static_analyzer.run_static_scan(
                script_paths=STATIC_SCAN_TARGETS,
                db_schema_snapshot=schema_snapshot,
            )
            return {
                "ok": True,
                "dim3": result.get("dim3") or [],
                "dim4": result.get("dim4") or [],
                "dim6": result.get("dim6") or [],
                "scanned_files": result.get("scanned_files") or 0,
                "signature_set": result.get("signature_set") or set(),
            }
        except Exception as e:
            self._safe_log_event("e2e_static_scan_failed", "error",
                                 {"err": str(e)})
            return {"ok": False, "error": str(e),
                    "dim3": [], "dim4": [], "dim6": [], "scanned_files": 0,
                    "signature_set": set()}

    def _build_schema_snapshot(self):
        """用 PRAGMA table_info 构造 knowledge_points 列名快照。
        失败时返回 None(static_analyzer 退化为仅白名单模式)。
        """
        try:
            conn = self.db._get_connection() if hasattr(self.db, "_get_connection") else None
        except Exception:
            conn = None
        if conn is None:
            # db_manager 实例可能用其他私有连接,尝试 public 方法
            try:
                conn = self.db.conn
            except Exception:
                conn = None

        try:
            # 直接 PRAGMA(db_manager 多数方法内部自管连接,这里独立一条查询)
            import sqlite3
            db_path = getattr(self.db, "db_path", None)
            if not db_path:
                return None
            c = sqlite3.connect(db_path)
            cur = c.cursor()
            cur.execute("PRAGMA table_info(knowledge_points)")
            cols = [r[1] for r in cur.fetchall()]
            c.close()
            if not cols:
                return None
            return {"knowledge_points": cols}
        except Exception as e:
            self._safe_log_event("e2e_schema_snapshot_failed", "warning",
                                 {"err": str(e)})
            return None

    # --------------------------------------------------------
    # 维度 1 路由自省
    # --------------------------------------------------------

    def _dim1_route_introspect(self):
        """Flask url_map 自省 vs api_endpoint_registry 差集。"""
        live_endpoints = self._read_flask_url_map()
        registered = self._get_registered_endpoints()

        issues = []
        new_endpoints = []

        # 新端点识别
        for ep in live_endpoints:
            sig = ep["rule"]
            if sig not in registered:
                new_endpoints.append(ep)
                # 登记新端点
                try:
                    self.db.register_endpoint(
                        endpoint=ep["rule"],
                        methods=ep["methods"],
                    )
                except Exception as e:
                    self._safe_log_event("e2e_register_endpoint_failed", "warning",
                                         {"endpoint": ep["rule"], "err": str(e)})
                # 发信号事件
                self._safe_log_event("e2e_new_endpoint_found", "info",
                                     {"endpoint": ep["rule"],
                                      "methods": ep["methods"]})
                # 产出 info 级 issue(首次发现新端点告知老唐)
                issues.append({
                    "dim_code": "1_route",
                    "severity": "info",
                    "endpoint": ep["rule"],
                    "signature": "1_route|{}|new_endpoint".format(ep["rule"]),
                    "rule_id": "new_endpoint",
                    "detail": {
                        "msg": "新端点首次出现,建议对话 3 前端补充测试模板",
                        "methods": ep["methods"],
                    },
                })

        # 得分:无新端点满分,新端点越多扣分越多(封底 60)
        n_new = len(new_endpoints)
        if n_new == 0:
            score = 100
        else:
            score = max(60, 100 - n_new * 5)

        return {
            "score": score,
            "issues": issues,
            "new_endpoints": new_endpoints,
            "detail": {
                "live_count": len(live_endpoints),
                "registered_count": len(registered),
                "new_count": n_new,
            },
        }

    def _read_flask_url_map(self):
        """读 Flask app.url_map.iter_rules() — 不引入启动副作用(局部 import)。"""
        try:
            from scripts.api_server import app
            endpoints = []
            for rule in app.url_map.iter_rules():
                methods = sorted(
                    [m for m in (rule.methods or []) if m not in ("HEAD", "OPTIONS")]
                )
                endpoints.append({
                    "rule": str(rule.rule),
                    "methods": ",".join(methods),
                    "endpoint": rule.endpoint,
                })
            return endpoints
        except Exception as e:
            self._safe_log_event("e2e_flask_introspect_failed", "warning",
                                 {"err": str(e)})
            return []

    def _get_registered_endpoints(self):
        """从 api_endpoint_registry 读已登记端点 signature set。"""
        try:
            rows = self.db.get_endpoint_registry()
            return set(r["endpoint"] for r in rows if r and r.get("endpoint"))
        except Exception as e:
            self._safe_log_event("e2e_registry_read_failed", "warning",
                                 {"err": str(e)})
            return set()

    # --------------------------------------------------------
    # 维度 2 启动就绪性
    # --------------------------------------------------------

    def _dim2_readiness(self):
        """5 个核心引擎模块顶层 import 自检。"""
        import importlib

        issues = []
        fail_count = 0
        results = []

        for mod_path, display_name in READINESS_CHECK_TARGETS:
            try:
                mod = importlib.import_module(mod_path)
                results.append({
                    "module": mod_path,
                    "display_name": display_name,
                    "ok": True,
                })
            except Exception as e:
                fail_count += 1
                err_msg = str(e)[:300]
                results.append({
                    "module": mod_path,
                    "display_name": display_name,
                    "ok": False,
                    "error": err_msg,
                })
                issues.append({
                    "dim_code": "2_readiness",
                    "severity": "error",
                    "endpoint": None,
                    "signature": "2_readiness|{}|import_failed".format(mod_path),
                    "rule_id": "readiness_import_failed",
                    "detail": {
                        "module": mod_path,
                        "display_name": display_name,
                        "msg": "模块 import 失败: " + err_msg,
                    },
                })
                self._safe_log_event("e2e_readiness_fail", "error",
                                     {"module": mod_path, "err": err_msg})

        if fail_count == 0:
            score = 100
        else:
            score = 50  # 任一关键引擎挂掉直接拦腰,与 F048 _health_readiness_check 同口径

        return {
            "score": score,
            "issues": issues,
            "detail": {
                "checked_count": len(READINESS_CHECK_TARGETS),
                "fail_count": fail_count,
                "results": results,
            },
        }

    # --------------------------------------------------------
    # 维度 3 Prompt 调用一致性
    # --------------------------------------------------------

    def _dim3_prompt_call(self, static_bundle):
        issues = list(static_bundle.get("dim3") or [])
        # dim3 无预置白名单(Prompt key 错误必须暴露,不容忍)
        score = self._score_from_issues(issues)
        return {
            "score": score,
            "issues": issues,
            "detail": {
                "raw_count": len(issues),
                "error_count": sum(1 for i in issues if i.get("severity") == "error"),
                "warning_count": sum(1 for i in issues if i.get("severity") == "warning"),
            },
        }

    # --------------------------------------------------------
    # 维度 4 字段契约(带白名单二次过滤)
    # --------------------------------------------------------

    def _dim4_field_contract(self, static_bundle):
        raw_issues = list(static_bundle.get("dim4") or [])
        kept, filtered = self._filter_known_false_positives(
            raw_issues, DIM4_KNOWN_FALSE_POSITIVES)
        score = self._score_from_issues(kept)
        return {
            "score": score,
            "issues": kept,
            "detail": {
                "raw_count": len(raw_issues),
                "filtered_out_count": len(filtered),
                "error_count": sum(1 for i in kept if i.get("severity") == "error"),
                "warning_count": sum(1 for i in kept if i.get("severity") == "warning"),
            },
            "filtered_out": filtered,
        }

    # --------------------------------------------------------
    # 维度 5 事件语义(deep 档)
    # --------------------------------------------------------

    def _dim5_event_v3_deep(self):
        """deep 档:拉最近 7 天 warning/error 事件,抽样喂 V3 判断。"""
        events = self._fetch_recent_warn_events(RECENT_EVENTS_LOOKBACK_DAYS)
        if not events:
            return {
                "score": 100,
                "issues": [],
                "detail": {"event_count": 0, "judged_count": 0,
                           "reason": "最近 7 天无 warning/error 事件"},
            }

        # 按 event_type 去重抽样上限 DEEP_EVENT_MAX_SAMPLES
        sampled = self._sample_events(events, DEEP_EVENT_MAX_SAMPLES)

        issues = []
        fail_count = 0
        warn_count = 0
        pass_count = 0

        for idx, ev in enumerate(sampled):
            self._emit_progress("dim5_event", 5, 8,
                                "V3 事件判断 {}/{}".format(idx + 1, len(sampled)))
            judgment = self._judge_single_event(ev)
            verdict = judgment.get("judgment", "warn")
            if verdict == "fail":
                fail_count += 1
                sev = "error"
            elif verdict == "warn":
                warn_count += 1
                sev = "warning"
            else:
                pass_count += 1
                continue  # pass 不产 issue

            ep = ev.get("endpoint") or ""
            ev_id = ev.get("event_id") or 0
            sig = "5_event|{}|ev{}|v3_{}".format(ep, ev_id, verdict)
            issues.append({
                "dim_code": "5_event",
                "severity": sev,
                "endpoint": ep if ep else None,
                "signature": sig,
                "rule_id": "v3_" + verdict,
                "detail": {
                    "event_id": ev_id,
                    "event_type": ev.get("event_type"),
                    "event_severity": ev.get("severity"),
                    "endpoint": ep,
                    "v3_judgment": judgment,
                    "msg": "V3 判定 " + verdict + ": " + "; ".join(
                        judgment.get("reasons") or [])[:400],
                },
            })

        # 得分:fail×10 + warn×3 扣分
        score = max(0, 100 - fail_count * 10 - warn_count * 3)
        return {
            "score": score,
            "issues": issues,
            "detail": {
                "event_count": len(events),
                "judged_count": len(sampled),
                "pass_count": pass_count,
                "warn_count": warn_count,
                "fail_count": fail_count,
                "lookback_days": RECENT_EVENTS_LOOKBACK_DAYS,
            },
        }

    def _fetch_recent_warn_events(self, lookback_days):
        """从 operation_events 拉最近 N 天 severity IN (warning/error) 的事件。"""
        try:
            import sqlite3
            db_path = getattr(self.db, "db_path", None)
            if not db_path:
                return []
            since = (datetime.now() - timedelta(days=lookback_days)).strftime(
                "%Y-%m-%d %H:%M:%S")
            c = sqlite3.connect(db_path)
            c.row_factory = sqlite3.Row
            cur = c.cursor()
            cur.execute("""
                SELECT event_id, event_type, severity, module, file_id,
                       endpoint, payload, created_at
                FROM operation_events
                WHERE severity IN ('warning', 'error')
                  AND created_at >= ?
                ORDER BY created_at DESC
                LIMIT 500
            """, (since,))
            rows = [dict(r) for r in cur.fetchall()]
            c.close()
            return rows
        except Exception as e:
            self._safe_log_event("e2e_event_query_failed", "warning",
                                 {"err": str(e)})
            return []

    def _sample_events(self, events, max_n):
        """按 event_type 去重,每种事件类型最多取 3 条代表;总上限 max_n。"""
        by_type = {}
        for ev in events:
            t = ev.get("event_type") or "unknown"
            by_type.setdefault(t, []).append(ev)

        sampled = []
        # 每种类型先取最多 3 条,优先 severity=error
        for t, lst in by_type.items():
            lst_sorted = sorted(
                lst,
                key=lambda x: (0 if x.get("severity") == "error" else 1,
                               x.get("created_at") or ""),
            )
            sampled.extend(lst_sorted[:3])
            if len(sampled) >= max_n:
                break
        return sampled[:max_n]

    def _judge_single_event(self, ev):
        """单事件喂 V3 判断,返回 {judgment/reasons/keywords_hit/confidence}。"""
        endpoint = ev.get("endpoint") or ""
        payload_raw = ev.get("payload") or ""
        payload = payload_raw
        if isinstance(payload_raw, str):
            try:
                payload = json.loads(payload_raw)
            except Exception:
                payload = {"raw": payload_raw[:1000]}

        response_excerpt = json.dumps(payload, ensure_ascii=False, default=str)[:2000]
        status_code = 200  # operation_events 不记录 HTTP 状态码,默认给 200
        method = "UNKNOWN"
        expected = self._lookup_expected_behavior(endpoint)
        recent_events_json = json.dumps({
            "event_type": ev.get("event_type"),
            "severity": ev.get("severity"),
            "module": ev.get("module"),
            "created_at": ev.get("created_at"),
        }, ensure_ascii=False)

        user_prompt = E2E_RESPONSE_JUDGE_PROMPT["user_prompt_template"].format(
            endpoint=endpoint or "(无路由)",
            method=method,
            status_code=status_code,
            response_excerpt=response_excerpt,
            recent_events_json=recent_events_json,
            expected_behavior=expected,
        )
        system_prompt = E2E_RESPONSE_JUDGE_PROMPT["system_prompt"]

        try:
            resp_text, usage = self._call_v3(system_prompt, user_prompt, V3_TIMEOUT)
            self._v3_call_count += 1
            self._accumulate_cost_v3(usage)
            parsed = self._safe_parse_json(resp_text)
            if not parsed or not isinstance(parsed, dict):
                return {
                    "judgment": "warn",
                    "reasons": ["V3 返回解析失败,默认标 warn"],
                    "keywords_hit": [],
                    "confidence": "low",
                }
            # 兜底字段
            verdict = parsed.get("judgment") or "warn"
            if verdict not in ("pass", "warn", "fail"):
                verdict = "warn"
            return {
                "judgment": verdict,
                "reasons": parsed.get("reasons") or [],
                "keywords_hit": parsed.get("keywords_hit") or [],
                "confidence": parsed.get("confidence") or "medium",
            }
        except Exception as e:
            self._safe_log_event("e2e_ai_call_failed", "warning",
                                 {"event_id": ev.get("event_id"),
                                  "err": str(e)[:300]})
            return {
                "judgment": "warn",
                "reasons": ["V3 调用异常: " + str(e)[:200]],
                "keywords_hit": [],
                "confidence": "low",
            }

    def _lookup_expected_behavior(self, endpoint):
        if not endpoint:
            return DEFAULT_EXPECTED_BEHAVIOR
        for prefix, desc in EXPECTED_BEHAVIOR_MAP.items():
            if endpoint.startswith(prefix):
                return desc
        return DEFAULT_EXPECTED_BEHAVIOR

    # --------------------------------------------------------
    # 维度 6 代码异味(带白名单二次过滤)
    # --------------------------------------------------------

    def _dim6_code_smell(self, static_bundle):
        raw_issues = list(static_bundle.get("dim6") or [])
        kept, filtered = self._filter_known_false_positives(
            raw_issues, DIM6_KNOWN_FALSE_POSITIVES)
        score = self._score_from_issues(kept)
        return {
            "score": score,
            "issues": kept,
            "detail": {
                "raw_count": len(raw_issues),
                "filtered_out_count": len(filtered),
                "error_count": sum(1 for i in kept if i.get("severity") == "error"),
                "warning_count": sum(1 for i in kept if i.get("severity") == "warning"),
            },
            "filtered_out": filtered,
        }

    # --------------------------------------------------------
    # 白名单过滤
    # --------------------------------------------------------

    def _filter_known_false_positives(self, issues, whitelist_set):
        """按 signature 精确过滤,返回 (保留的, 被过滤的)。"""
        kept = []
        filtered = []
        for iss in issues:
            sig = iss.get("signature") or ""
            if sig in whitelist_set:
                # 附带 reason 说明便于对话 3 前端折叠展示
                d = iss.get("detail") or {}
                file_line = ""
                if d.get("file") and d.get("line") is not None:
                    file_line = "{}:{}".format(d["file"], d["line"])
                reason = WHITELIST_REASONS.get(file_line, "已知合理项,白名单过滤")
                iss_copy = dict(iss)
                iss_copy["_filter_reason"] = reason
                filtered.append(iss_copy)
            else:
                kept.append(iss)
        return kept, filtered

    # --------------------------------------------------------
    # issue 写入(批量 upsert)
    # --------------------------------------------------------

    def _write_issues(self, issues, report_id):
        """批量 upsert_e2e_issue。返回 (upserted_count, filtered_count)。

        part3.4 修复:
          - 签名加 report_id(db.upsert_e2e_issue 必填位置参数)
          - 对齐真实签名 upsert_e2e_issue(report_id, dim_code, endpoint,
            severity, signature, payload=None)
          - 旧 rule_id / detail 合并进 payload,不丢数据

        filtered_count 此处是 0(过滤已在各维度内完成),保留接口对称性。
        """
        upserted = 0
        if not report_id:
            # report_id 异常时降级:记 warn 事件,不写 issue
            self._safe_log_event("e2e_issue_skip_no_report_id", "warning",
                                 {"issue_count": len(issues)})
            return 0, 0

        for iss in issues:
            try:
                sig = iss.get("signature") or ""
                if not sig:
                    continue
                payload = {
                    "rule_id": iss.get("rule_id") or "",
                    "detail": iss.get("detail") or {},
                    "message": iss.get("message") or "",
                }
                self.db.upsert_e2e_issue(
                    report_id=report_id,
                    dim_code=iss.get("dim_code") or "",
                    endpoint=iss.get("endpoint"),
                    severity=iss.get("severity") or "info",
                    signature=sig,
                    payload=payload,
                )
                upserted += 1
            except Exception as e:
                self._safe_log_event("e2e_issue_upsert_failed", "warning",
                                     {"signature": iss.get("signature"),
                                      "err": str(e)[:300]})

        if upserted > 0:
            self._safe_log_event("e2e_issue_upserted", "info",
                                 {"count": upserted, "report_id": report_id})
        return upserted, 0

    # --------------------------------------------------------
    # 汇总计算
    # --------------------------------------------------------

    def _compute_total_score(self, dims_result, scan_depth):
        """按档位权重加权计算总分,权重取 DIM_WEIGHTS_DEEP/QUICK。"""
        if scan_depth == "deep":
            weights = DIM_WEIGHTS_DEEP
        else:
            weights = DIM_WEIGHTS_QUICK

        total = 0.0
        weight_sum = 0.0
        for dim_key, w in weights.items():
            d = dims_result.get(dim_key) or {}
            score = d.get("score")
            if score is None:
                continue  # skipped 维度跳过
            total += score * w
            weight_sum += w
        if weight_sum <= 0:
            return 0
        # 若个别维度 skipped(理论上只发生在 quick 档 dim5),权重已在 WEIGHTS_QUICK 重分
        return round(total / weight_sum * weight_sum, 2) if False else round(total, 2)

    def _compute_summary(self, issues):
        """汇总 passed/failed/warning_count。"""
        error_count = 0
        warning_count = 0
        info_count = 0
        for iss in issues:
            sev = iss.get("severity")
            if sev == "error":
                error_count += 1
            elif sev == "warning":
                warning_count += 1
            else:
                info_count += 1
        # passed_count 概念:总端点数 - failed(error) - warning
        live_count = 0
        return {
            "total_issues": len(issues),
            "passed_count": max(0, live_count - error_count - warning_count),
            "failed_count": error_count,
            "warning_count": warning_count,
            "info_count": info_count,
        }

    def _score_from_issues(self, issues):
        """通用:error×10 + warning×3 扣分,封底 0。"""
        e = sum(1 for i in issues if i.get("severity") == "error")
        w = sum(1 for i in issues if i.get("severity") == "warning")
        return max(0, 100 - e * 10 - w * 3)

    # --------------------------------------------------------
    # 报告落库
    # --------------------------------------------------------

    def _save_report(self, trigger_type, scan_depth, summary, new_endpoints, full_report):
        try:
            total_endpoints = summary.get("passed_count", 0) + \
                summary.get("failed_count", 0) + summary.get("warning_count", 0)
            report_data = {
                "trigger_type": trigger_type,
                "scan_depth": scan_depth,
                "total_endpoints": total_endpoints,
                "passed_count": summary.get("passed_count", 0),
                "failed_count": summary.get("failed_count", 0),
                "warning_count": summary.get("warning_count", 0),
                "new_endpoints_json": new_endpoints,  # db_manager 内部自动 json.dumps
                "full_report_json": full_report,     # 同上
                "v3_call_count": self._v3_call_count,
                "cost_estimate": round(self._cost_accumulator, 6),
            }
            return self.db.save_e2e_test_report(report_data)
        except Exception as e:
            self._safe_log_event("e2e_report_save_failed", "error",
                                 {"err": str(e)[:300]})
            return None

    # --------------------------------------------------------
    # V3 调用封装(五方法 + 两签名适配,借鉴 health_checker)
    # --------------------------------------------------------

    def _call_v3(self, system_prompt, user_prompt, timeout):
        """统一 V3 调用,返回 (response_text, usage_dict)。失败抛异常。"""
        response, usage = self._do_call(system_prompt, user_prompt, timeout)
        text = self._unpack_response(response)
        return text, usage

    def _do_call(self, system_prompt, user_prompt, timeout):
        """五方法适配器 + 两签名降级。
        方法顺序:call_chat / chat / complete / call / generate
        每个方法先试 messages=[...] 签名,失败再试 system_prompt=/user_prompt= 两参数签名
        """
        client = self.client
        methods = ["call_chat", "chat", "complete", "call", "generate"]
        last_err = None
        for mname in methods:
            fn = getattr(client, mname, None)
            if not fn:
                continue
            # 签名 A: messages
            try:
                messages = [
                    {"role": "system", "content": system_prompt},
                    {"role": "user", "content": user_prompt},
                ]
                try:
                    resp = fn(
                        model="deepseek-chat",
                        messages=messages,
                        temperature=V3_TEMPERATURE,
                        timeout=timeout,
                    )
                except TypeError:
                    resp = fn(
                        model="deepseek-chat",
                        messages=messages,
                        temperature=V3_TEMPERATURE,
                    )
                usage = self._extract_usage(resp)
                return resp, usage
            except TypeError as te:
                last_err = te
                # 签名 B: system_prompt / user_prompt
                try:
                    try:
                        resp = fn(
                            model="deepseek-chat",
                            system_prompt=system_prompt,
                            user_prompt=user_prompt,
                            temperature=V3_TEMPERATURE,
                            timeout=timeout,
                        )
                    except TypeError:
                        resp = fn(
                            model="deepseek-chat",
                            system_prompt=system_prompt,
                            user_prompt=user_prompt,
                            temperature=V3_TEMPERATURE,
                        )
                    usage = self._extract_usage(resp)
                    return resp, usage
                except Exception as e2:
                    last_err = e2
                    continue
            except Exception as e:
                last_err = e
                continue

        raise RuntimeError("V3 五方法适配器全部失败: " + str(last_err))

    def _unpack_response(self, resp):
        """从 response 提取文本内容。兼容多种 client 返回格式。"""
        if resp is None:
            raise RuntimeError("V3 响应为空")
        # 字典格式
        if isinstance(resp, dict):
            if "content" in resp:
                return resp["content"] or ""
            if "text" in resp:
                return resp["text"] or ""
            if "choices" in resp and resp["choices"]:
                c0 = resp["choices"][0]
                if isinstance(c0, dict):
                    msg = c0.get("message") or {}
                    return msg.get("content") or c0.get("text") or ""
        # OpenAI SDK 对象
        choices = getattr(resp, "choices", None)
        if choices:
            c0 = choices[0]
            msg = getattr(c0, "message", None)
            if msg is not None:
                return getattr(msg, "content", None) or ""
            return getattr(c0, "text", None) or ""
        # 字符串直接返
        if isinstance(resp, str):
            return resp
        # 兜底
        return str(resp)

    def _extract_usage(self, resp):
        """抽 usage 字典,失败返 {}。"""
        try:
            if isinstance(resp, dict):
                u = resp.get("usage") or {}
            else:
                u = getattr(resp, "usage", None) or {}
                if not isinstance(u, dict):
                    u = {
                        "prompt_tokens": getattr(u, "prompt_tokens", 0),
                        "completion_tokens": getattr(u, "completion_tokens", 0),
                        "total_tokens": getattr(u, "total_tokens", 0),
                    }
            return u or {}
        except Exception:
            return {}

    def _accumulate_cost_v3(self, usage):
        try:
            pt = int(usage.get("prompt_tokens", 0) or 0)
            ct = int(usage.get("completion_tokens", 0) or 0)
            cost = pt / 1000.0 * V3_COST_PER_1K_INPUT + \
                ct / 1000.0 * V3_COST_PER_1K_OUTPUT
            self._cost_accumulator += cost
        except Exception:
            pass

    # --------------------------------------------------------
    # 工具方法
    # --------------------------------------------------------

    def _safe_dim(self, dim_name, fn):
        """维度异常隔离:失败返 score=0 + issues=[] + detail.failed=True。"""
        try:
            r = fn()
            if not isinstance(r, dict):
                r = {"score": 0, "issues": [], "detail": {"failed": True, "reason": "维度返回非 dict"}}
            return r
        except Exception as e:
            tb = traceback.format_exc()
            self._safe_log_event("e2e_dim_failed", "warning",
                                 {"dim": dim_name, "err": str(e),
                                  "trace": tb[:1500]})
            return {
                "score": 0,
                "issues": [],
                "detail": {
                    "failed": True,
                    "error": str(e)[:300],
                    "dim": dim_name,
                },
            }

    def _safe_log_event(self, event_type, severity, payload):
        """事件日志,失败静默(不干扰主流程)。severity 严格对齐 info/warning/error。"""
        if severity == "warn":
            severity = "warning"
        if severity not in ("info", "warning", "error"):
            severity = "info"
        try:
            self.db.log_operation_event(
                event_type=event_type,
                severity=severity,
                module="e2e_tester",
                file_id=None,
                endpoint=None,
                payload=payload,
            )
        except Exception:
            # 事件日志本身失败不阻塞主流程
            pass

    def _emit_progress(self, stage, current, total, message):
        """进度回调。stage 必须在 VALID_STAGES 白名单内。"""
        if stage not in VALID_STAGES:
            stage = "init"
        if not self.progress_callback:
            return
        try:
            self.progress_callback({
                "stage": stage,
                "current": current,
                "total": total,
                "message": message,
            })
        except Exception:
            pass

    def _safe_parse_json(self, text):
        if not text:
            return None
        # 去掉可能的 ```json ... ``` 围栏
        t = text.strip()
        if t.startswith("```"):
            lines = t.split("\n")
            # 去首尾围栏
            if lines and lines[0].startswith("```"):
                lines = lines[1:]
            if lines and lines[-1].startswith("```"):
                lines = lines[:-1]
            t = "\n".join(lines)
        try:
            return json.loads(t)
        except Exception:
            # 尝试切到第一个 { 和最后一个 }
            try:
                a = t.find("{")
                b = t.rfind("}")
                if 0 <= a < b:
                    return json.loads(t[a:b + 1])
            except Exception:
                pass
            return None

    def _now_iso(self):
        return datetime.now().strftime("%Y-%m-%d %H:%M:%S")



def run_e2e_scan(db, client, progress_callback=None, scan_depth="quick"):
    """对话 3 api_server 路由可选调用入口。等效于 E2ETester(db,client,cb).run_full_scan(depth)。"""
    tester = E2ETester(db, client, progress_callback=progress_callback)
    return tester.run_full_scan(scan_depth=scan_depth)



# 用法: python -m scripts.e2e_tester


if __name__ == "__main__":
    print("e2e_tester.py — F062 引擎层 v2.3.0-part3-alpha2")
    print("本模块需要 db 实例和 client 实例注入,不支持独立运行。")
    print("请通过 api_server 路由(对话 3)或以下方式调用:")
    print("")
    print("  from scripts.db_manager import DBManager")
    print("  from scripts.deepseek_client import DeepSeekClient")
    print("  from scripts.e2e_tester import run_e2e_scan")
    print("  db = DBManager()")
    print("  client = DeepSeekClient()")
    print("  r = run_e2e_scan(db, client, scan_depth='quick')")
    print("  print(r)")
