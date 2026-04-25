"""
api_server.py - Flask API + 管理后台
路径：scripts/api_server.py
版本：v2.3.0-part3.8 - 6 批量路由 errors 收集改造(E2 方案)

v2.3.0-part3.8 变更(hotfix,2026-04-24):
    F062 白名单大扩展配套——6 批量路由改代码收集错误原因(立规则 A 禁止裸 except+pass 模式)
      - batch-confirm (行 ~541) 改为 except Exception as e: errors.append({id, error})
      - batch-ignore (行 ~558) 同上
      - batch-delete (行 ~570) 同上
      - batch-renew-freshness (行 ~620) 同上
      - batch-mark-outdated (行 ~646) 同上
      - batch-restore-to-pending (行 ~970) 同上
    返回 JSON 新增 2 字段:
      - errors: [{"id": ..., "error": ...}] 失败条目列表(error 限 200 字符)
      - failed_count: len(errors)
    保留兼容:n (confirmed/ignored/deleted/renewed/marked/restored) 仍为成功计数
    前端:review.html v2.3.0-part3.8 同步改造 6 个批量按钮的 fetch 回调,
          失败列表通过新增 #batchResultModal 展示(复用既有 batch_resolve_duplicates 模式)

v2.3.0-part3.5 变更(新功能,2026-04-24):
    Feature: F062 配套——E2E 端到端测试诊断包导出
      - 新增路由 GET /api/tools/e2e/export/<rid>
        返回 Markdown 格式的完整诊断包(元数据+六维分+白名单+issue 聚合清单+
        近 7 天 warn/error 事件日志摘要+诊断说明+版本上下文),供发给 Claude 做异地诊断
      - 路由内部委托 scripts/e2e_diagnosis_exporter.build_e2e_diagnosis_markdown
      - Response 带 Content-Disposition: attachment,浏览器直接下载
      - 纯读功能,不写 DB、不调 AI、不占 _task 锁槽
    配套:
      - 新模块 scripts/e2e_diagnosis_exporter.py(~500 行,聚合+渲染 Markdown)
      - review.html E2E 报告弹窗 footer 新增"导出诊断包"按钮 + 1 个 JS 函数

v2.3.0-part3.4 版本号同步(2026-04-23):
    本文件代码无改动。同版本 hotfix 集中在 db_manager.py 和 e2e_tester.py:
      - db_manager.get_polish_candidates: WHERE 横向边界去掉 'confirmed' 排除
        (修复体检维度⑤永久 100 分 / 跳过打磨的 bug)
      - e2e_tester._write_issues: 签名加 report_id + 对齐 upsert_e2e_issue 真实签名
      - e2e_tester._run_pipeline: 调用顺序调整为 save_report → write_issues
        (修复"报告显示 185 个 issue / 列表显示 0 条"的幻觉数字 bug)
    立规则第 9 条(签名)第三次应验 + 第 40 条(横向边界)补注。
    详见 CHANGELOG.md v2.3.0-part3.4 条目。

v2.3.0-part3.2 变更(hotfix,2026-04-23)：
    Bug A 修复(仪表盘三张标签分布卡"暂无数据" / "展开全部 0 个")：
      - db_manager.get_tag_distribution: pattern 改用 tag_name 匹配(原 tag_code 永不匹配)
      - db_manager.get_tag_distribution: 新增 count>0 过滤,杜绝"N 个标签在使用中"虚假宣传
      - review.html.renderTagCard.getName: 补 tag_name 字段兼容（原仅认 name/tag/label）
      - review.html.toggleTagCardMore: 改用 data-total 属性替代 DOM 计数反推
      - 根因：extractor._sanitize_tags 存 tag_name(中文)入 DB,但
        get_tag_distribution 用 tag_code 做 LIKE 永远查不到;
        旧版把 count=0 也塞入结果,靠"凑数"把假象覆盖掉;
        一旦加 count>0 过滤真相暴露 → "暂无数据"
    Bug B 修复(质检分数口径与"待补跑"打架:未质检 0 vs 待补跑 2043)：
      - /api/dashboard qa_distribution: 将 qa_score=0.0 归入 unscored,与
        get_qc_rerun_summary("待补跑=NULL 或 0.0")口径对齐
      - review.html 删除两处硬编码版本号 span (v2.2.3 F057 / v2.3.0 F049)
    Feature(v2.3.1 批量重算成熟度 的保守前置版本,不替代完整迭代):
      - db_manager.promote_readiness_by_qa_score: qa>=4 且 draft → quotable
        (只升不降,不碰 premium,editorial 轴与 qa 轴解耦)
      - db_manager.get_readiness_promote_preview: dry-run 预览给前端确认弹窗
      - POST /api/tools/readiness_promote + GET /preview: 独立工具触发
      - 质检补跑 _qc_rerun_core 尾部自动调联动,result 返回 readiness_promote
      - review.html 工具箱新增"就绪度联动"按钮(R 橙),独立 runTool 分支
    Feature(质检补跑异步化,解决"刷新即失+无进度+不可并发"三连)：
      - 新增 _qc_task / _qc_task_lock / _qc_task_update_progress,**独立于 _task**
        (故意不进 _task 单例锁槽,允许与预处理/提取/体检/E2E 并发)
      - _qc_rerun_core(progress_cb=None): 逐文件上报进度
      - POST /api/tools/qc_rerun: 改异步,立即返回 202,后台线程执行
      - GET /api/tools/qc_rerun/progress: 独立进度查询
      - 新增 _qc_readiness_check(): 对齐 F048/F062 四项自检模板
        (虽用独立锁理论不受"_task_lock 前置"字面约束,仍按精神对齐)
      - review.html 新增独立 #qcTaskProgress 面板 + qcStartPolling 三函数,
        admin tab 切入时 qcCheckRunningTask() 自动恢复刷新后的进度条
    并发写兜底：
      - db_manager.get_connection: PRAGMA busy_timeout=10000
        (WAL 已开,补这个兜 10 秒等锁,应用层不再需要 retry)
    关键教训(写入 01 工程手册新立规则 §二数据层第 10 条)：
      - 新增 SQL 查询同一 JSON 字段前,必须对照存储侧的写入逻辑确认字段格式
      - 本次:get_tag_distribution 用 tag_code,extractor._sanitize_tags 存 tag_name,
        潜伏 2 个月(从 v2.1.0 三层标签体系上线起),靠"count=0 也塞入"掩盖

v2.3.0-part3.1 变更(hotfix,2026-04-24)：
    Bug A 修复(F061 质检补跑全线崩溃)：
      - _qc_rerun_core 两处 ext._quality_check() 调用补齐 filename/content_summary 参数
      - 根因：F058(v2.2.3)重构 _quality_check 强制 5 参,F061 的调用保留旧 2 参签名
      - 影响：潜伏 2 个月,首次触发质检补跑立刻 TypeError 全线崩
    Bug B 修复(F062 三表老库未建,500 错误):
      - 模块顶层 DatabaseManager() 实例化后追加 db.init_tables() 兜底
      - 根因：part3 升级只替换代码不重跑首次安装,init_tables() 无机会执行
      - 影响：立规则"api_server 启动兜底 init_tables"写入 01 工程手册 §二

v2.3.0-part3 变更(F062 界面层)：
    新增 7 个 F062 端到端测试路由（全部追加在文件末尾 main() 之前，既有代码零改动）：
      GET  /api/tools/e2e/latest                      —— 工具箱第 11 卡显示"最近一次"+ 软提醒徽章
      POST /api/tools/e2e/start                       —— 启动端到端测试（后台线程，_task type="e2e"）
      GET  /api/tools/e2e/history                     —— 历史报告列表（走 db.get_e2e_test_report_list）
      GET  /api/tools/e2e/report/<rid>                —— 单份报告详情（含 full_report_json 自动 parse）
      GET  /api/tools/e2e/issues                      —— issue 四态列表（含 by_status 分组 + 筛选 status/dim_code）
      POST /api/tools/e2e/issues/<iid>/status         —— 四态切换（走 db.set_e2e_issue_status）
    新增 2 个辅助函数（模块级，路由前声明）：
      _e2e_readiness_check()      —— 启动就绪性 4 项自检（对齐 F048 模板，对话 B 立的 _task_lock 前置规则）
      _e2e_progress_adapter()     —— E2ETester 进度回调 → _task["progress"] 映射（9 stage，对齐对话 2 VALID_STAGES）
    关键契约（与 v2.3.0-part3-alpha2 对话 2 e2e_tester 引擎层对齐）：
      - _task["type"] = "e2e"（前后端口径锁定，review.html checkRunningTask titles["e2e"]）
      - scan_depth 白名单 quick/deep，非白名单值兜底 quick（不 400）
      - /latest 接口 total_score 从 full_report_json 解出（不回改 db，遵守对话 3 纪律）
      - /issues 按 status 分组排序（pending > intermittent > fixed > ignored + last_seen_at DESC）
      - /issues/<iid>/status 支持无限四态切换（给老唐逃生口）
      - progress_adapter total_files=9 固定（对齐 e2e_tester VALID_STAGES 9 种）

v2.3.0-part2.2 变更（F048 防护层）：
    新增 1 个模块级辅助函数（api_server 顶部 import 段后）：
      _health_readiness_check()  —— 启动就绪性 4 项自检，返回 (ok, errors)
    /api/tools/health/start 路由在 with _task_lock 之前插入前置自检调用：
      自检失败 → HTTP 400 带 details 故障清单，不占用 _task 单例
      自检通过 → 进入原有后台线程逻辑
    自检 4 项（对齐对话 A 发现的 4 类系统性 bug + 对话 B 字段契约）：
      [1] 6 个 F048 Prompt 顶层可 import（对话 A 缺陷 1：Prompt 未落地）
      [2] 6 个 F048 Prompt 非 None 且为 dict（对话 A 缺陷 2：import 静默降级）
      [3] 每个 Prompt dict 含非空 system_prompt / user_prompt_template（对话 A 缺陷 4：key 错配）
      [4] db.get_kp_for_health_scan() 返回 dict 含 category / subcategory 两 key（对话 B 缺陷 3：字段契约）
    设计纪律：
      - 自检放 _task_lock 之前：失败不占用单例锁，避免"自检失败但抢了 _task"脏状态
      - 自检耗时 <100ms（读第 1 条 kp）：用户感知 "点了秒回 400" 远优于 "2 秒后 500"
      - 空库时 [4] 跳过（不算失败）：新部署首次体检无 kp 数据允许通过

v2.3.0-part2 变更（F048 界面层）：
    新增 8 个体检路由（全部追加在文件末尾 main() 之前，既有代码零改动）：
      GET  /api/tools/health/latest                    —— 工具箱卡片显示"最近一次"用
      POST /api/tools/health/start                     —— 启动体检（后台线程，_task type="health"）
      GET  /api/tools/health/history                   —— 历史报告列表
      GET  /api/tools/health/report/<rid>              —— 单份报告详情
      GET  /api/tools/health/suggestions/<rid>         —— 该报告的 Review 清单
      POST /api/tools/health/suggestions/<sid>/adopt   —— L1/L2 采纳（三步原子：备份→update_kp→apply）
      POST /api/tools/health/suggestions/<sid>/drop    —— drop 独立路由（走 ignore_knowledge_point）
      POST /api/tools/health/suggestions/<sid>/reject  —— 驳回（仅标 rejected）
    新增 3 个辅助函数（模块级，路由前声明）：
      _get_suggestion_by_id(sid)          —— 按 sid 查单条 polish_suggestion，两个 JSON 字段手动解析
      _merge_ai_content(kp_row, sc)       —— suggested_content 字段合并为 update_knowledge_point 参数
      _health_progress_adapter(payload)   —— HealthChecker 进度回调 → _task["progress"] 映射
    关键契约（与 v2.3.0-part2-alpha2 引擎层 + 对话3 需求锁定对齐）：
      - _merge_ai_content：tags.layer1→final_category_tags / layer2→final_attribute_tags /
        layer3→final_keywords（三者仅非空时覆盖）；description/polish_notes 存进
        ai_extracted_content 新键（polished_description/polish_notes）不覆盖原主字段；
        title 直接覆盖；practical_insights 直接覆盖（list）；content_readiness **不传**保留原值
      - split 语义：isinstance(sc, list) and len(sc)>1 时只取 sc[0]，响应带 split_note 提示
        "AI 建议拆分为 N 条，已采纳第 1 条，其余 N-1 条请到 Tab 1 手动创建"
      - drop 独立路由：不走 _merge_ai_content，走 db.ignore_knowledge_point(kp_id,
        reason="health_drop: " + diagnosis[:200])，三步与 adopt 对齐
      - L3_manual 采纳返 400："L3 建议仅支持驳回或略过，请到 Tab 1 手工修订"
      - 采纳/drop 三步任一失败返 500，附 step 标识（backup / update_kp / apply）
      - _health_progress_adapter 映射表 total_files=8 固定，stage→current_file 序号为
        init=1 / dim1=2 / dim2=3 / dim3=4 / dim4_island=5 / dim5_polish=6 /
        dim6_monetize=7 / done=8 / failed=8
      - 打磨阶段（dim5_polish）把 HealthChecker 回调里的 current/total 拼接进 message
        显示"打磨中 X/Y"

v2.3.0-part1 变更：
    F049 仪表盘工具箱优化（后端）：
      - /api/knowledge-points 和 /api/knowledge-points/ids 新增 layer1_tag 参数（穿透跳转用）
      - /api/dashboard 新增 data["tag_distribution"] = {"A":[...], "C":[...], "D":[...]}
      - 新增 POST /api/tools/duplicate_unified：合并"增量重复/最近一周/全量扫描/清理重扫"为一个接口
        旧路由 /api/tools/duplicate-scan 和 /api/tools/duplicate-reset-rescan 保留不动（向下兼容）
    F059 批量重跑与AI去重联动（后端）：
      - 新增 GET /api/tools/batch-rerun-scan：返回候选文件列表（kp 计数 + 是否含注解）
      - 新增 POST /api/tasks/batch_rerun：批量重跑任务（复用 task_reextract 大框架）
        差异：type="batch_rerun" / operation_hook("batch_rerun") /
             用 delete_extracted_kps_by_source_file 而非 delete_kps_by_source_file
    顺手修（仅 db 层）：get_all_knowledge_points 补齐 qa_source_filter 签名
        （本文件 v2.2.3 已在传此参数，但 db 层签名当时漏改，导致该筛选始终无效）

v2.2.3 - 界面层 hotfix
    F060 关键操作强制备份（3 触发点接入：版本重提取 / 重复合并单条与批量 / 全库重扫）
    F061 历史质检补跑 API（/api/tools/qc_rerun 走 F058 降级链）
    新增 /api/events 事件日志查询、/api/tools/truncation_summary 截断摘要
    dashboard 聚合截断摘要供仪表盘"截断补救"卡使用
    旧 /api/tools/qa-backfill 保留为向下兼容转发（内部调新降级链）
"""
import os,sys,json,re,traceback,webbrowser,threading
from pathlib import Path
from datetime import datetime, timedelta
PROJECT_ROOT = Path(__file__).parent.parent
sys.path.insert(0, str(PROJECT_ROOT))
from flask import Flask, request, jsonify, Response
from flask_cors import CORS
from scripts.db_manager import DatabaseManager
# v2.2.3 F060: 关键操作备份钩子 + 备份失败异常
from scripts.backup_manager import operation_hook, BackupFailedError
# v2.3.0-part3.5: E2E 诊断包 Markdown 导出(纯读格式化)
from scripts.e2e_diagnosis_exporter import build_e2e_diagnosis_markdown
# v2.3.1 F2/F6: 精品候选 AI 判定 + 精品导出(立规则 50 第 6 项:跨模块 import 双路径兜底)
try:
    from scripts.premium_judge import run_premium_refresh
    from scripts.premium_exporter import build_premium_export
except ImportError:
    from premium_judge import run_premium_refresh
    from premium_exporter import build_premium_export

app = Flask(__name__)
CORS(app)
db = DatabaseManager()

# v2.3.0-part3.1 (hotfix): 启动追齐 schema
# 避免"只替换代码不重跑首次安装"导致老库缺新表(如 F062 三表)
# CREATE TABLE IF NOT EXISTS 无副作用,失败打 WARN 不阻塞启动
# 立规则: api_server 启动入口必须 silent 重入一次 init_tables(),详见 01 工程手册 §二
try:
    db.init_tables()
except Exception as _e:
    print("[WARN] init_tables 启动兜底失败(将继续启动): %s" % str(_e))

# ================================================================
# v2.1.2 F047: 长任务管理器
# ================================================================
_task_lock = threading.Lock()
_task = {
    "running": False,
    "type": "",       # preprocess | extract | reextract
    "started_at": None,
    "progress": {
        "total_files": 0,
        "current_file": 0,
        "current_filename": "",
        "current_step": "",
        "total_extracted": 0,
        "message": ""
    },
    "result": None,
    "error": None
}

def _task_update_progress(data):
    """供Extractor回调更新进度"""
    with _task_lock:
        for k, v in data.items():
            if k in _task["progress"]:
                _task["progress"][k] = v

# ================================================================
# v2.3.0-hotfix: 质检补跑独立任务槽（可与 _task 并发）
# ----------------------------------------------------------------
# 设计动机：
#   - _task 是全局单例锁(同时只能跑一个长任务)，用于预处理/提取/重提取/批量重跑
#     /体检/端到端测试 这几条互斥的管线
#   - 质检补跑只改 qa_score/qa_flags/qa_source 几个字段，写面窄，和上面那些
#     任务实际上数据不冲突，按"并发"设计
#   - 给它单开 _qc_task，和 _task 物理隔离；两次质检补跑本身仍互斥(没意义并发)
#   - SQLite 并发写极少数情况下可能出 "database is locked"，需要时在核心加 retry
# ================================================================
_qc_task_lock = threading.Lock()
_qc_task = {
    "running": False,
    "started_at": None,
    "progress": {
        "total_files": 0,        # 候选文件分组总数（orphan 不算）
        "current_file": 0,       # 已处理的文件分组数
        "current_filename": "",  # 当前正在跑的文件名
        "total_candidates": 0,   # 候选知识点总数
        "processed_kps": 0,      # 已补跑完成的知识点数
        "current_step": "",      # 高层步骤描述
        "message": ""            # 最新提示消息
    },
    "result": None,
    "error": None
}

def _qc_task_update_progress(data):
    """供 _qc_rerun_core 主循环回调更新进度"""
    with _qc_task_lock:
        for k, v in data.items():
            if k in _qc_task["progress"]:
                _qc_task["progress"][k] = v


def _qc_readiness_check():
    """v2.3.0-part3.2: 质检补跑启动就绪性自检（对齐 F048 / F062 模板）。
    返回 (ok: bool, errors: list[str])。

    按对话 B 立的规则"长任务启动就绪性自检必须在 _task_lock 之前"精神对齐。
    本任务虽用独立 _qc_task_lock 不受该规则字面约束,仍按模板四项补齐,
    保持架构整齐、避免未来迁移时遗漏。

    自检 4 项：
      [1] db 实例存在且可连(SELECT 1)
      [2] db 有 get_qc_rerun_candidates / get_qc_rerun_summary /
          promote_readiness_by_qa_score 三个关键方法
      [3] scripts.extractor.Extractor 可 import 且有 _quality_check 方法;
          签名含 filename/content_summary 两个参数(防止再次签名漂移)
      [4] 候选表 knowledge_points 字段契约:qa_score / qa_flags /
          content_readiness / final_category_tags / suggested_category_tags

    总耗时 <100ms,失败时调用方必须在 with _qc_task_lock 之前返回 500。
    """
    errors = []

    # ---- [1] db 可连 ----
    try:
        conn = db.get_connection(); c = conn.cursor()
        c.execute("SELECT 1"); c.fetchone()
        conn.close()
    except Exception as e:
        errors.append("[1] db 连接失败: " + str(e))
        return False, errors

    # ---- [2] db 关键方法 ----
    for m in ("get_qc_rerun_candidates", "get_qc_rerun_summary",
              "promote_readiness_by_qa_score"):
        if not hasattr(db, m):
            errors.append("[2] db 缺方法: " + m)

    # ---- [3] Extractor 可 import + _quality_check 签名正确 ----
    try:
        from scripts.extractor import Extractor
        if not hasattr(Extractor, "_quality_check"):
            errors.append("[3] Extractor 缺 _quality_check 方法")
        else:
            import inspect
            try:
                sig = inspect.signature(Extractor._quality_check)
                params = list(sig.parameters.keys())
                # 期望:self, filename, content_summary, kps, kps_info, source_content
                # F058 签名漂移事故专防:检查前两个必选参数名
                # (self 是第一个,filename 和 content_summary 应是第 2/3)
                if len(params) < 5:
                    errors.append(
                        "[3] _quality_check 参数数量异常(应 ≥5,实 %d): %s"
                        % (len(params), params))
                elif params[1] != "filename" or params[2] != "content_summary":
                    errors.append(
                        "[3] _quality_check 签名漂移警告:期望 (self, filename, "
                        "content_summary, kps, kps_info, ...),实 %s" % params)
            except (ValueError, TypeError):
                # 签名无法 introspect(C 扩展等边缘情形),不强阻断
                pass
    except Exception as e:
        errors.append("[3] Extractor import 失败: " + str(e))

    # ---- [4] knowledge_points 关键字段存在 ----
    try:
        conn = db.get_connection(); c = conn.cursor()
        c.execute("PRAGMA table_info(knowledge_points)")
        cols = {r[1] for r in c.fetchall()}
        conn.close()
        required = {"qa_score", "qa_flags", "content_readiness",
                    "final_category_tags", "suggested_category_tags",
                    "review_status", "source_file_id"}
        missing = required - cols
        if missing:
            errors.append("[4] knowledge_points 缺字段: " + ", ".join(sorted(missing)))
    except Exception as e:
        errors.append("[4] 字段契约检查失败: " + str(e))

    return (len(errors) == 0), errors


# ================================================================
# v2.3.1 F2 精品候选 AI 判定独立任务槽(对齐 _qc_task 模式)
# ----------------------------------------------------------------
# 设计动机:
#   - F2 AI 刷新是长任务(40-60 分钟),必须异步
#   - 只写 premium_ai_cache 表,与其他任务数据不冲突,允许并发
#   - 独立于 _task 单例锁和 _qc_task(对齐 part3.2 多任务槽设计)
#   - A+C 双保险频率保护:
#       A. last_completed_at 冷却期 10 分钟
#       C. 前端弹确认框"预估 7-10 元"(前端实现)
#   - cancel_requested 标志供引擎 cancel_check 协作式退出
# ================================================================
PREMIUM_COOLDOWN_SECONDS = 600  # A 保护:10 分钟冷却

_premium_task_lock = threading.Lock()
_premium_task = {
    "running": False,
    "started_at": None,
    "last_completed_at": None,    # 用于冷却期判断
    "cancel_requested": False,
    "progress": {
        "total_kps": 0,
        "processed_kps": 0,
        "current_view": "",         # client / rfp / client+rfp
        "ai_calls_count": 0,
        "cost_estimate_cny": 0.0,
        "current_step": "",
        "message": "",
    },
    "result": None,
    "error": None,
}

def _premium_task_update_progress(data):
    """供 premium_judge 主循环回调更新进度."""
    with _premium_task_lock:
        for k, v in data.items():
            if k in _premium_task["progress"]:
                _premium_task["progress"][k] = v


def _premium_cancel_check():
    """供 premium_judge 引擎查询取消标志."""
    with _premium_task_lock:
        return bool(_premium_task.get("cancel_requested"))


def _premium_readiness_check():
    """v2.3.1 F2 精品 AI 刷新启动就绪性自检(对齐 F048/F062/part3.2 模板).

    自检 4 项(§5.4):
      [1] db 可连 SELECT 1
      [2] db 有 get_premium_judge_candidates / upsert_premium_ai_cache /
          bless_premium / unbless_premium / get_premium_export_data 关键方法
      [3] Prompt 可 import:PREMIUM_JUDGE_CLIENT_PROMPT + PREMIUM_JUDGE_RFP_PROMPT
          均有 system_prompt 和 user_prompt_template 两 key(立规则 13)
      [4] knowledge_points 含 premium_client/premium_rfp/premium_tier 字段
          (防止老库未跑 migrate_v2_3_1.py 就点刷新)

    总耗时 <100ms,失败时调用方必须在 _premium_task_lock 之前返回 400.
    """
    errors = []

    # [1] db 可连
    try:
        conn = db.get_connection(); c = conn.cursor()
        c.execute("SELECT 1"); c.fetchone()
        conn.close()
    except Exception as e:
        errors.append("[1] db 连接失败: " + str(e))
        return False, errors

    # [2] db 关键方法
    for m in ("get_premium_judge_candidates", "upsert_premium_ai_cache",
              "get_premium_ai_cache_by_kp", "get_premium_pool_list",
              "bless_premium", "unbless_premium", "get_premium_export_data"):
        if not hasattr(db, m):
            errors.append("[2] db 缺方法: " + m)

    # [3] Prompt 可 import + 双 key 规范
    try:
        try:
            from scripts.prompts.prompt_templates import (
                PREMIUM_JUDGE_CLIENT_PROMPT as _CP,
                PREMIUM_JUDGE_RFP_PROMPT as _RP,
            )
        except ImportError:
            from prompts.prompt_templates import (
                PREMIUM_JUDGE_CLIENT_PROMPT as _CP,
                PREMIUM_JUDGE_RFP_PROMPT as _RP,
            )
        for name, pr in (("PREMIUM_JUDGE_CLIENT_PROMPT", _CP),
                          ("PREMIUM_JUDGE_RFP_PROMPT", _RP)):
            if not isinstance(pr, dict):
                errors.append("[3] %s 不是 dict" % name)
                continue
            if "system_prompt" not in pr:
                errors.append("[3] %s 缺 system_prompt key" % name)
            if "user_prompt_template" not in pr:
                errors.append("[3] %s 缺 user_prompt_template key" % name)
    except Exception as e:
        errors.append("[3] Prompt import 失败: " + str(e)[:200])

    # [4] 字段契约
    try:
        conn = db.get_connection(); c = conn.cursor()
        c.execute("PRAGMA table_info(knowledge_points)")
        cols = {r[1] for r in c.fetchall()}
        conn.close()
        for f in ("premium_client", "premium_rfp", "premium_tier",
                  "used_count", "last_used_at", "used_for",
                  "premium_freshness_status"):
            if f not in cols:
                errors.append("[4] kp 缺字段 " + f + "(可能老库未跑 migrate_v2_3_1.py)")
    except Exception as e:
        errors.append("[4] 字段契约检查失败: " + str(e))

    return (len(errors) == 0), errors


# ================================================================
# v2.3.2 F055 本地问答助手独立任务槽(对齐 _premium_task 模式)
# ----------------------------------------------------------------
# 设计动机:
#   - 单次问答 ~10-30 秒(短任务),但仍走异步以支持取消 + 进度查看
#   - 与 _qc_task / _premium_task 物理隔离,允许并发
#     (老唐自测的同时朋友试用,互不干扰)
#   - cancel_requested 标志供 qa_assistant 引擎 cancel_check 协作式退出
#   - 端到端硬上限 60 秒,超时由前端发起 /cancel
# ================================================================
_qa_task_lock = threading.Lock()
_qa_task = {
    "running": False,
    "started_at": None,
    "cancel_requested": False,
    "progress": {
        "total_kps": 5,            # 5 个 stage 固定(tokenize/retrieve/rerank/generate/record)
        "processed_kps": 0,
        "current_step": "",        # tokenize | retrieve | rerank | generate | record
        "message": "",
        "ai_calls_count": 0,
        "cost_estimate_cny": 0.0,
    },
    "result": None,
    "error": None,
}


def _qa_task_update_progress(data):
    """供 qa_assistant 主循环回调更新进度(同 _premium_task_update_progress 模式)."""
    with _qa_task_lock:
        for k, v in data.items():
            if k in _qa_task["progress"]:
                _qa_task["progress"][k] = v


def _qa_cancel_check():
    """供 qa_assistant 引擎查询取消标志."""
    with _qa_task_lock:
        return bool(_qa_task.get("cancel_requested"))


def _qa_readiness_check():
    """v2.3.2 F055 问答助手启动就绪性自检(对齐 F048/F062/part3.2 模板).

    自检 4 项(立规则 31):
      [1] db 可连 SELECT 1
      [2] db 有 v2.3.2-part1 落地的 6 个 qa 方法 + log_operation_event
      [3] Prompt 可 import:QA_RETRIEVAL_RANK_PROMPT / QA_ANSWER_GEN_PROMPT /
          QA_FOLLOWUP_GEN_PROMPT 均含 system_prompt + user_prompt_template
      [4] qa_history / qa_feedback 表存在(防老库未跑 setup.py 就启用)

    总耗时 <100ms,失败时调用方必须在 _qa_task_lock 之前返回 400.
    """
    errors = []

    # [1] db 可连
    try:
        conn = db.get_connection(); c = conn.cursor()
        c.execute("SELECT 1"); c.fetchone()
        conn.close()
    except Exception as e:
        errors.append("[1] db 连接失败: " + str(e))
        return False, errors

    # [2] db 关键方法(6 个 v2.3.2 新方法 + log_operation_event)
    for m in ("get_qa_retrieval_candidates", "save_qa_history",
              "save_qa_feedback", "record_kp_used",
              "get_qa_history_list", "get_qa_stats",
              "log_operation_event"):
        if not hasattr(db, m):
            errors.append("[2] db 缺方法: " + m)

    # [3] Prompt 可 import + 双 key 规范
    try:
        try:
            from scripts.prompts.prompt_templates import (
                QA_RETRIEVAL_RANK_PROMPT as _RP,
                QA_ANSWER_GEN_PROMPT as _AP,
                QA_FOLLOWUP_GEN_PROMPT as _FP,
            )
        except ImportError:
            from prompts.prompt_templates import (
                QA_RETRIEVAL_RANK_PROMPT as _RP,
                QA_ANSWER_GEN_PROMPT as _AP,
                QA_FOLLOWUP_GEN_PROMPT as _FP,
            )
        for name, pr in (("QA_RETRIEVAL_RANK_PROMPT", _RP),
                          ("QA_ANSWER_GEN_PROMPT", _AP),
                          ("QA_FOLLOWUP_GEN_PROMPT", _FP)):
            if not isinstance(pr, dict):
                errors.append("[3] %s 不是 dict" % name)
                continue
            if "system_prompt" not in pr:
                errors.append("[3] %s 缺 system_prompt key" % name)
            if "user_prompt_template" not in pr:
                errors.append("[3] %s 缺 user_prompt_template key" % name)
    except Exception as e:
        errors.append("[3] Prompt import 失败: " + str(e)[:200])

    # [4] qa_history / qa_feedback 表存在(防老库未跑 setup.py)
    try:
        conn = db.get_connection(); c = conn.cursor()
        c.execute("SELECT name FROM sqlite_master WHERE type='table' "
                  "AND name IN ('qa_history','qa_feedback')")
        existing = {r[0] for r in c.fetchall()}
        conn.close()
        for t in ("qa_history", "qa_feedback"):
            if t not in existing:
                errors.append("[4] 表 " + t + " 不存在(请先运行 首次安装.bat 追齐 schema)")
    except Exception as e:
        errors.append("[4] schema 检查失败: " + str(e))

    return (len(errors) == 0), errors


REVIEW_HTML = None
for _p in [PROJECT_ROOT/"web"/"templates"/"review.html", PROJECT_ROOT/"web"/"review.html", PROJECT_ROOT/"review.html"]:
    if _p.exists():
        with open(_p,"r",encoding="utf-8") as _f: REVIEW_HTML = _f.read()
        print(f"  [OK] review.html: {_p}"); break

def _parse(v):
    if v is None or isinstance(v,(dict,list)): return v
    if isinstance(v,str):
        try: return json.loads(v)
        except: return v
    return v

def _safe(item):
    r = {}
    for k,v in item.items(): r[k] = v.decode("utf-8",errors="replace") if isinstance(v,bytes) else v
    # 解析所有JSON字段
    for f in ["ai_extracted_content","suggested_tags","final_tags","domain_tags",
              "suggested_category_tags","final_category_tags",
              "suggested_attribute_tags","final_attribute_tags",
              "suggested_keywords","final_keywords","qa_flags",
              "policy_dependencies","practical_insights"]:
        if f in r: r[f] = _parse(r[f])
    return r

# === 标签质量过滤（保留，用于旧标签兼容） ===
_POISON_EXACT = {"乡村振兴","土地政策","项目管理","工作","文件","内容","要求","标准","规定",
    "报送","填报","附件","详见","通知","印发","转发","函","编号","落实","推进","加强"}
_POISON_PATTERNS = [
    re.compile(r'^\d+[%％]'),
    re.compile(r'^\d+[\.\d]*$'),
    re.compile(r'^\d+[万亿元]'),
    re.compile(r'第[一二三四五六七八九十\d]+[条款项章节]'),
    re.compile(r'^[一二三四五六七八九十]+、'),
]
def _is_valid_tag(tag):
    if not tag or len(tag) < 2 or len(tag) > 14: return False
    if tag in _POISON_EXACT: return False
    for p in _POISON_PATTERNS:
        if p.search(tag): return False
    return True

@app.before_request
def _log(): print(f"  >> {request.method} {request.path}")

@app.errorhandler(404)
def _404(e): return jsonify({"error":"not found:"+request.path}),404

@app.route("/")
def index():
    if REVIEW_HTML: return Response(REVIEW_HTML, mimetype="text/html; charset=utf-8")
    return "<h1>review.html not found</h1>",404

# ================================================================
# 知识点 CRUD
# ================================================================
@app.route("/api/knowledge-points", methods=["GET"])
def get_kps():
    try:
        sort_by_qa = request.args.get("sort_by_qa", None)
        freshness_filter = request.args.get("freshness", None)
        policy_filter = request.args.get("policy", None)
        source_type_filter = request.args.get("source_type", None)
        qa_score_filter = request.args.get("qa_score", None)
        # v2.2.3: qa_source 筛选（batch/small_batch/single/rule_fallback）
        qa_source_filter = request.args.get("qa_source", None)
        # v2.3.0-part1 F049: 一层标签穿透（A/C/D组卡片跳转用）
        layer1_tag = request.args.get("layer1_tag", None)
        r = db.get_all_knowledge_points(
            review_status=request.args.get("status"), content_type=request.args.get("type"),
            category_id=request.args.get("category",None,type=int),
            level1_code=request.args.get("level1",None),
            search_query=request.args.get("search",None),
            content_readiness=request.args.get("readiness",None),
            freshness_filter=freshness_filter,
            policy_filter=policy_filter,
            source_type_filter=source_type_filter,
            qa_score_filter=qa_score_filter,
            qa_source_filter=qa_source_filter,
            layer1_tag=layer1_tag,
            page=request.args.get("page",1,type=int), per_page=request.args.get("per_page",20,type=int))
        items = r["items"]
        if sort_by_qa:
            # 按qa_score升序排列，NULL排最后
            items.sort(key=lambda x: (x.get("qa_score") is None, x.get("qa_score") or 999))
        r["items"] = [_safe(i) for i in items]
        return jsonify(r)
    except Exception as e:
        traceback.print_exc()
        return jsonify({"error":str(e),"items":[],"total":0,"page":1,"per_page":20}),500

@app.route("/api/knowledge-points/<int:kid>", methods=["GET"])
def get_kp(kid):
    try:
        kp = db.get_knowledge_point(kid)
        if not kp: return jsonify({"error":"not found"}),404
        return jsonify(_safe(kp))
    except Exception as e: traceback.print_exc(); return jsonify({"error":str(e)}),500

@app.route("/api/knowledge-points/<int:kid>/confirm", methods=["POST"])
def confirm(kid):
    try:
        d = request.get_json() or {}
        cat = d.get("final_category_id")
        if cat is None:
            kp = db.get_knowledge_point(kid)
            if kp: cat = kp.get("suggested_category_id")
        db.confirm_knowledge_point(kid, cat, d.get("final_tags"), d.get("reviewer_notes",""))
        return jsonify({"success":True})
    except Exception as e: traceback.print_exc(); return jsonify({"error":str(e)}),500

@app.route("/api/knowledge-points/<int:kid>/ignore", methods=["POST"])
def ignore(kid):
    try:
        reason = (request.get_json() or {}).get("reason","")
        kp = db.get_knowledge_point(kid)
        if kp and kp.get("review_status") == "confirmed":
            db.add_edit_history(kid, {"review_status": {"old": "confirmed", "new": "ignored"}},
                "移除出库: " + (reason or "无原因"))
        db.ignore_knowledge_point(kid, reason)
        return jsonify({"success":True})
    except Exception as e: traceback.print_exc(); return jsonify({"error":str(e)}),500

# v2.0.0 新增：物理删除
@app.route("/api/knowledge-points/<int:kid>", methods=["DELETE"])
def delete_kp(kid):
    try:
        kp = db.get_knowledge_point(kid)
        if not kp: return jsonify({"error":"not found"}),404
        db.delete_knowledge_point(kid)
        return jsonify({"success":True})
    except Exception as e: traceback.print_exc(); return jsonify({"error":str(e)}),500

@app.route("/api/knowledge-points/<int:kid>", methods=["PUT"])
def update(kid):
    try:
        d = request.get_json() or {}
        kp = db.get_knowledge_point(kid)
        # v2.0.0: 增加三层标签和元数据的追踪
        track_fields = ["title","final_category_id","final_tags","reviewer_notes",
                        "original_excerpt","ai_extracted_content",
                        "final_category_tags","final_attribute_tags","final_keywords",
                        "content_readiness","source_authority","access_level",
                        "freshness_interval_days"]
        if kp and kp.get("review_status") == "confirmed":
            changes = {}
            for f in track_fields:
                if f in d:
                    old_val = kp.get(f)
                    new_val = d[f]
                    old_cmp = json.dumps(old_val, ensure_ascii=False) if isinstance(old_val, (dict,list)) else str(old_val or "")
                    new_cmp = json.dumps(new_val, ensure_ascii=False) if isinstance(new_val, (dict,list)) else str(new_val or "")
                    if old_cmp != new_cmp:
                        changes[f] = {"old": old_val, "new": new_val}
            if changes:
                db.add_edit_history(kid, changes, "人工编辑")
        # v2.1.0-d: 扩展允许更新的字段（含保鲜周期）
        allowed_update = ["title","final_category_id","final_tags","reviewer_notes",
                          "ai_extracted_content","original_excerpt",
                          "final_category_tags","final_attribute_tags","final_keywords",
                          "content_readiness","source_authority","access_level",
                          "freshness_interval_days","freshness_note"]
        u = {k:d[k] for k in allowed_update if k in d}
        # 如果编辑了内容，自动刷新保鲜时间
        content_fields = {"title","ai_extracted_content","original_excerpt"}
        if any(k in d for k in content_fields):
            u["freshness_checked_at"] = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
        if u: db.update_knowledge_point(kid, **u)
        return jsonify({"success":True})
    except Exception as e: traceback.print_exc(); return jsonify({"error":str(e)}),500

# ================================================================
# 批量操作
# ================================================================
@app.route("/api/knowledge-points/ids", methods=["GET"])
def get_kp_ids():
    """返回当前筛选条件下的所有知识点ID（用于全选全部）"""
    try:
        r = db.get_all_knowledge_points(
            review_status=request.args.get("status"),
            content_type=request.args.get("type"),
            category_id=request.args.get("category",None,type=int),
            level1_code=request.args.get("level1",None),
            search_query=request.args.get("search",None),
            content_readiness=request.args.get("readiness",None),
            freshness_filter=request.args.get("freshness",None),
            policy_filter=request.args.get("policy",None),
            source_type_filter=request.args.get("source_type",None),
            qa_score_filter=request.args.get("qa_score",None),
            qa_source_filter=request.args.get("qa_source",None),
            layer1_tag=request.args.get("layer1_tag",None),
            page=1, per_page=99999)
        ids = [item["id"] for item in (r.get("items") or [])]
        return jsonify({"ids":ids, "total":len(ids)})
    except Exception as e:
        traceback.print_exc()
        return jsonify({"error":str(e),"ids":[],"total":0}),500

@app.route("/api/knowledge-points/batch-confirm", methods=["POST"])
def batch_confirm():
    try:
        ids = (request.get_json() or {}).get("ids",[])
        n = 0
        errors = []
        for kid in ids:
            try:
                kp = db.get_knowledge_point(kid)
                if kp and kp["review_status"]=="pending":
                    db.confirm_knowledge_point(kid, kp.get("suggested_category_id")); n+=1
            except Exception as e:
                errors.append({"id": kid, "error": str(e)[:200]})
        return jsonify({"success":True,"confirmed":n,"errors":errors,"failed_count":len(errors)})
    except Exception as e: traceback.print_exc(); return jsonify({"error":str(e)}),500

# v2.0.0 新增
@app.route("/api/knowledge-points/batch-ignore", methods=["POST"])
def batch_ignore():
    try:
        ids = (request.get_json() or {}).get("ids",[])
        n = 0
        errors = []
        for kid in ids:
            try:
                kp = db.get_knowledge_point(kid)
                if kp and kp["review_status"] in ("pending","confirmed"):
                    if kp["review_status"] == "confirmed":
                        db.add_edit_history(kid, {"review_status":{"old":"confirmed","new":"ignored"}}, "批量移除")
                    db.ignore_knowledge_point(kid, "批量忽略"); n+=1
            except Exception as e:
                errors.append({"id": kid, "error": str(e)[:200]})
        return jsonify({"success":True,"ignored":n,"errors":errors,"failed_count":len(errors)})
    except Exception as e: traceback.print_exc(); return jsonify({"error":str(e)}),500

# v2.0.0 新增
@app.route("/api/knowledge-points/batch-delete", methods=["POST"])
def batch_delete():
    try:
        ids = (request.get_json() or {}).get("ids",[])
        n = 0
        errors = []
        for kid in ids:
            try:
                db.delete_knowledge_point(kid); n+=1
            except Exception as e:
                errors.append({"id": kid, "error": str(e)[:200]})
        return jsonify({"success":True,"deleted":n,"errors":errors,"failed_count":len(errors)})
    except Exception as e: traceback.print_exc(); return jsonify({"error":str(e)}),500

@app.route("/api/knowledge-points/<int:kid>/restore-to-pending", methods=["POST"])
def restore_to_pending(kid):
    try:
        kp = db.get_knowledge_point(kid)
        if not kp: return jsonify({"error":"not found"}),404
        if kp["review_status"] != "ignored":
            return jsonify({"error":"只能恢复已忽略的知识点"}),400
        db.restore_to_pending(kid)
        return jsonify({"success":True})
    except Exception as e: traceback.print_exc(); return jsonify({"error":str(e)}),500

# ================================================================
# v2.1.0-d 新增：保鲜管理
# ================================================================
@app.route("/api/freshness/summary", methods=["GET"])
def freshness_summary():
    """返回保鲜状态摘要（供审核界面顶部提示栏使用）"""
    try:
        summary = db.get_freshness_summary()
        return jsonify(summary)
    except Exception as e:
        traceback.print_exc()
        return jsonify({"error":str(e),"expired":0,"expiring":0,"fresh":0}),500

@app.route("/api/knowledge-points/<int:kid>/renew-freshness", methods=["POST"])
def renew_freshness(kid):
    """续期单条知识点保鲜"""
    try:
        d = request.get_json() or {}
        note = d.get("freshness_note", "")
        db.renew_freshness(kid, note)
        return jsonify({"success":True})
    except Exception as e: traceback.print_exc(); return jsonify({"error":str(e)}),500

@app.route("/api/knowledge-points/batch-renew-freshness", methods=["POST"])
def batch_renew_freshness():
    """批量续期保鲜"""
    try:
        d = request.get_json() or {}
        ids = d.get("ids", [])
        note = d.get("freshness_note", "")
        n = 0
        errors = []
        for kid in ids:
            try:
                db.renew_freshness(kid, note)
                n += 1
            except Exception as e:
                errors.append({"id": kid, "error": str(e)[:200]})
        return jsonify({"success":True,"renewed":n,"errors":errors,"failed_count":len(errors)})
    except Exception as e: traceback.print_exc(); return jsonify({"error":str(e)}),500

@app.route("/api/knowledge-points/<int:kid>/mark-outdated", methods=["POST"])
def mark_outdated(kid):
    """标记知识点已过时"""
    try:
        d = request.get_json() or {}
        reason = d.get("reason", "")
        db.mark_knowledge_outdated(kid, reason)
        return jsonify({"success":True})
    except Exception as e: traceback.print_exc(); return jsonify({"error":str(e)}),500

@app.route("/api/knowledge-points/batch-mark-outdated", methods=["POST"])
def batch_mark_outdated():
    """批量标记过时"""
    try:
        d = request.get_json() or {}
        ids = d.get("ids", [])
        reason = d.get("reason", "")
        n = 0
        errors = []
        for kid in ids:
            try:
                db.mark_knowledge_outdated(kid, reason)
                n += 1
            except Exception as e:
                errors.append({"id": kid, "error": str(e)[:200]})
        return jsonify({"success":True,"marked":n,"errors":errors,"failed_count":len(errors)})
    except Exception as e: traceback.print_exc(); return jsonify({"error":str(e)}),500

# ================================================================
# v2.1.0-d F028: 政策依赖校验
# ================================================================
@app.route("/api/policy-validation/summary", methods=["GET"])
def policy_validation_summary():
    """返回政策校验状态摘要"""
    try:
        summary = db.get_policy_validation_summary()
        return jsonify(summary)
    except Exception as e:
        traceback.print_exc()
        return jsonify({"error":str(e),"unvalidated":0,"validated":0,"pending":0,"exempt":0,"no_policy":0}),500

@app.route("/api/knowledge-points/<int:kid>/exempt-policy", methods=["POST"])
def exempt_policy(kid):
    """人工豁免政策校验（标记为不需要政策校验）"""
    try:
        kp = db.get_knowledge_point(kid)
        if not kp: return jsonify({"error":"not found"}),404
        d = request.get_json() or {}
        reason = d.get("reason", "")
        db.update_knowledge_point(kid, policy_validated=3,
            policy_dependencies=json.dumps([{"exempt_reason": reason or "human_exempt"}], ensure_ascii=False))
        if kp.get("content_readiness") == "draft" and kp.get("policy_validated") == 2:
            db.update_knowledge_point(kid, content_readiness="draft")
        db.log_operation("exempt_policy", "knowledge_points", kid, {"reason": reason})
        return jsonify({"success":True})
    except Exception as e: traceback.print_exc(); return jsonify({"error":str(e)}),500

@app.route("/api/knowledge-points/<int:kid>/revalidate-policy", methods=["POST"])
def revalidate_policy(kid):
    """重新校验单条知识点的政策依赖"""
    try:
        kp = db.get_knowledge_point(kid)
        if not kp: return jsonify({"error":"not found"}),404
        if kp.get("content_type") == "policy":
            return jsonify({"error":"政策类知识点无需校验"}),400
        from scripts.policy_validator import PolicyValidator
        pv = PolicyValidator(db=db)
        ai_content = {}
        raw = kp.get("ai_extracted_content", "{}")
        if isinstance(raw, str):
            try: ai_content = json.loads(raw)
            except: pass
        elif isinstance(raw, dict):
            ai_content = raw
        kps_mock = [{
            "title": kp["title"],
            "original_excerpt": kp.get("original_excerpt", ""),
            "core_provisions": ai_content.get("core_provisions", ""),
            "core_strategy": ai_content.get("core_strategy", ""),
            "core_conclusion": ai_content.get("core_conclusion", ""),
            "detailed_method": ai_content.get("detailed_method", ""),
        }]
        kps_info_mock = [{"kp_id": kid, "title": kp["title"]}]
        count = pv.validate_batch(kps_mock, kps_info_mock, kp["content_type"])
        db.log_operation("revalidate_policy", "knowledge_points", kid)
        return jsonify({"success":True,"validated":count})
    except Exception as e: traceback.print_exc(); return jsonify({"error":str(e)}),500

# ================================================================
# v2.2.0 F029: 专家注解
# ================================================================
@app.route("/api/knowledge-points/<int:kid>/annotations", methods=["GET"])
def get_annotations(kid):
    """获取某知识点的全部注解"""
    try:
        anns = db.get_annotations_by_kp(kid)
        return jsonify(anns)
    except Exception as e:
        traceback.print_exc()
        return jsonify([])

@app.route("/api/knowledge-points/<int:kid>/annotations", methods=["POST"])
def add_annotation(kid):
    """添加注解"""
    try:
        kp = db.get_knowledge_point(kid)
        if not kp: return jsonify({"error":"not found"}),404
        d = request.get_json() or {}
        ann_type = d.get("annotation_type", "")
        content = d.get("content", "").strip()
        tags = d.get("tags", [])
        if ann_type not in ("agree","disagree","supplement","correction","experience"):
            return jsonify({"error":"无效的注解类型"}),400
        if ann_type in ("disagree","correction") and not content:
            return jsonify({"error":"反对或纠错注解必须填写理由"}),400
        # agree类型自动添加"老唐实战验证"标签
        if ann_type == "agree" and "老唐实战验证" not in tags:
            tags.append("老唐实战验证")
        aid = db.add_annotation(kid, ann_type, content, tags)
        return jsonify({"success":True, "id":aid})
    except Exception as e:
        traceback.print_exc()
        return jsonify({"error":str(e)}),500

@app.route("/api/annotations/<int:aid>", methods=["DELETE"])
def delete_annotation(aid):
    """删除注解"""
    try:
        db.delete_annotation(aid)
        return jsonify({"success":True})
    except Exception as e:
        traceback.print_exc()
        return jsonify({"error":str(e)}),500

@app.route("/api/annotation-tags", methods=["GET"])
def get_annotation_tags():
    """返回预设注解标签列表"""
    try:
        from scripts.experience_notes import ANNOTATION_TAGS
        return jsonify(ANNOTATION_TAGS)
    except ImportError:
        try:
            from experience_notes import ANNOTATION_TAGS
            return jsonify(ANNOTATION_TAGS)
        except:
            return jsonify(["老唐实战验证","有实战案例佐证","需要现场确认","已过时需更新",
                           "四川特有经验","可直接用于培训","可用于投标方案","需要补充政策依据",
                           "客户常问的问题","反常识但正确"])

# ================================================================
# v2.2.0 F045: 经验速记
# ================================================================
@app.route("/api/quicknote", methods=["POST"])
def quicknote():
    """经验速记：接收表单 → V3结构化 → 入库"""
    try:
        d = request.get_json() or {}
        title = (d.get("title") or "").strip()
        content = (d.get("content") or "").strip()
        content_type = d.get("content_type", "experience")
        keywords_raw = (d.get("keywords") or "").strip()
        if not title:
            return jsonify({"error":"标题不能为空"}),400
        if not content:
            return jsonify({"error":"内容不能为空"}),400
        keywords = [kw.strip() for kw in keywords_raw.split(",") if kw.strip()] if keywords_raw else None
        try:
            from scripts.experience_notes import ExperienceNotes
        except ImportError:
            from experience_notes import ExperienceNotes
        en = ExperienceNotes(db=db)
        kp_id = en.structure_and_save(title, content, content_type, keywords)
        if kp_id:
            return jsonify({"success":True, "kp_id":kp_id,
                           "message":"已保存并结构化，请到知识审核Tab查看"})
        return jsonify({"error":"保存失败，请检查控制台日志"}),500
    except Exception as e:
        traceback.print_exc()
        return jsonify({"error":str(e)}),500

# ================================================================
# v2.1.1 F039: 重复检测
# ================================================================
@app.route("/api/duplicate-groups", methods=["GET"])
def get_duplicate_groups():
    """获取重复检测结果列表（默认只返回pending）"""
    try:
        status = request.args.get("status", "pending")
        if status == "all":
            groups = db.get_duplicate_groups(status=None)
        else:
            groups = db.get_duplicate_groups(status=status)
        # 解析JSON字段并附带知识点标题
        result = []
        for g in groups:
            item = dict(g)
            item["member_ids"] = _parse(item.get("member_ids"))
            item["ai_judgment"] = _parse(item.get("ai_judgment"))
            # 查询每个成员知识点的标题和类型
            members_detail = []
            if isinstance(item["member_ids"], list):
                for mid in item["member_ids"]:
                    kp = db.get_knowledge_point(mid)
                    if kp:
                        members_detail.append({
                            "id": mid,
                            "title": kp["title"],
                            "content_type": kp["content_type"],
                            "source_file": kp.get("renamed_filename") or kp.get("original_filename", ""),
                            "review_status": kp.get("review_status", ""),
                            "content_readiness": kp.get("content_readiness", "draft"),
                            "qa_score": kp.get("qa_score"),
                            "original_excerpt": (kp.get("original_excerpt") or "")[:500],
                            "ai_extracted_content": kp.get("ai_extracted_content") or ""
                        })
                    else:
                        members_detail.append({"id": mid, "title": "(已删除)", "content_type": "unknown"})
            item["members_detail"] = members_detail
            result.append(item)
        return jsonify(result)
    except Exception as e:
        traceback.print_exc()
        return jsonify([])

@app.route("/api/duplicate-groups/summary", methods=["GET"])
def duplicate_summary():
    """获取重复检测摘要"""
    try:
        summary = db.get_duplicate_summary()
        return jsonify(summary)
    except Exception as e:
        traceback.print_exc()
        return jsonify({"pending":0,"resolved":0,"dismissed":0})

@app.route("/api/duplicate-groups/<int:gid>/resolve", methods=["POST"])
def resolve_duplicate(gid):
    """处理重复组：保留指定知识点，删除其余（支持keep_ids多选）
    v2.2.3 F060: 实际删除前强制备份，备份失败终止操作
    """
    try:
        group = db.get_duplicate_group(gid)
        if not group: return jsonify({"error":"not found"}),404
        d = request.get_json() or {}
        action = d.get("action", "resolve")  # resolve=保留勾选删其余, dismiss=全部保留
        if action == "dismiss":
            db.update_duplicate_group(gid, "dismissed", "人工判定：非重复，全部保留")
            return jsonify({"success":True, "action":"dismissed"})
        # 支持keep_ids(多选)和keep_id(单选，向下兼容)
        keep_ids = d.get("keep_ids")
        if not keep_ids:
            keep_id = d.get("keep_id")
            if keep_id:
                keep_ids = [keep_id]
        if not keep_ids:
            return jsonify({"error":"缺少keep_ids参数"}),400
        member_ids = _parse(group["member_ids"])
        if not isinstance(member_ids, list):
            return jsonify({"error":"member_ids格式错误"}),500
        for kid in keep_ids:
            if kid not in member_ids:
                return jsonify({"error":"keep_id #%d 不在组成员中" % kid}),400
        # v2.2.3 F060: 仅当有实际删除时才备份
        will_delete = [mid for mid in member_ids if mid not in keep_ids]
        if will_delete:
            try:
                operation_hook("dup_merge")
            except BackupFailedError as be:
                return jsonify({"error": "备份失败，合并终止: " + str(be)}), 500
        # 执行删除
        deleted = []
        for mid in will_delete:
            db.delete_knowledge_point(mid)
            deleted.append(mid)
        if deleted:
            action_desc = "保留#%s，删除#%s" % (",".join(str(x) for x in keep_ids), ",".join(str(x) for x in deleted))
        else:
            action_desc = "全部保留(勾选了所有成员)"
        db.update_duplicate_group(gid, "resolved", action_desc)
        return jsonify({"success":True, "kept":keep_ids, "deleted":deleted, "action":"resolved"})
    except Exception as e:
        traceback.print_exc()
        return jsonify({"error":str(e)}),500

@app.route("/api/duplicate-groups/batch-resolve", methods=["POST"])
def batch_resolve_duplicates():
    """批量处理重复组：支持按AI建议处理或全部标记非重复
    v2.2.3 F060: ai_suggest 分支会批量删除，启动前强制备份
    """
    try:
        d = request.get_json() or {}
        group_ids = d.get("group_ids", [])
        action = d.get("action", "ai_suggest")  # ai_suggest=按AI建议保留, dismiss=全部标记非重复
        if not group_ids:
            return jsonify({"error":"请选择至少一个重复组"}),400
        # v2.2.3 F060: ai_suggest 涉及实际删除，批量开始前备份一次；dismiss 不删除不需要
        if action == "ai_suggest":
            try:
                operation_hook("dup_merge_batch")
            except BackupFailedError as be:
                return jsonify({"error": "备份失败，批量合并终止: " + str(be)}), 500
        resolved = 0
        dismissed = 0
        errors = []
        for gid in group_ids:
            try:
                group = db.get_duplicate_group(gid)
                if not group: continue
                if action == "dismiss":
                    db.update_duplicate_group(gid, "dismissed", "批量标记非重复")
                    dismissed += 1
                elif action == "ai_suggest":
                    judgment = _parse(group.get("ai_judgment"))
                    if isinstance(judgment, dict) and judgment.get("suggested_keep_id"):
                        keep_id = judgment["suggested_keep_id"]
                        member_ids = _parse(group["member_ids"])
                        if isinstance(member_ids, list) and keep_id in member_ids:
                            deleted = []
                            for mid in member_ids:
                                if mid != keep_id:
                                    db.delete_knowledge_point(mid)
                                    deleted.append(mid)
                            action_desc = "批量AI建议: 保留#%d，删除#%s" % (keep_id, ",".join(str(x) for x in deleted))
                            db.update_duplicate_group(gid, "resolved", action_desc)
                            resolved += 1
                        else:
                            errors.append("组#%d: AI建议ID不在成员中" % gid)
                    else:
                        errors.append("组#%d: 无AI建议" % gid)
            except Exception as ex:
                errors.append("组#%d: %s" % (gid, str(ex)))
        return jsonify({"success":True, "resolved":resolved, "dismissed":dismissed, "errors":errors})
    except Exception as e:
        traceback.print_exc()
        return jsonify({"error":str(e)}),500

@app.route("/api/knowledge-points/batch-restore-to-pending", methods=["POST"])
def batch_restore_to_pending():
    """批量恢复到待审核"""
    try:
        d = request.get_json() or {}
        ids = d.get("ids", [])
        n = 0
        errors = []
        for kid in ids:
            try:
                kp = db.get_knowledge_point(kid)
                if kp and kp["review_status"] == "ignored":
                    db.restore_to_pending(kid)
                    n += 1
            except Exception as e:
                errors.append({"id": kid, "error": str(e)[:200]})
        return jsonify({"success":True,"restored":n,"errors":errors,"failed_count":len(errors)})
    except Exception as e: traceback.print_exc(); return jsonify({"error":str(e)}),500

# ================================================================
# 编辑历史
# ================================================================
@app.route("/api/knowledge-points/<int:kid>/history", methods=["GET"])
def get_history(kid):
    try: return jsonify(db.get_edit_history(kid))
    except: return jsonify([])

@app.route("/api/knowledge-points/<int:kid>/restore-version/<int:hid>", methods=["POST"])
def restore_version(kid, hid):
    try:
        ok, msg = db.restore_from_history(kid, hid)
        if ok: return jsonify({"success":True,"message":msg})
        return jsonify({"error":msg}),400
    except Exception as e: traceback.print_exc(); return jsonify({"error":str(e)}),500

# ================================================================
# 分类管理
# ================================================================
@app.route("/api/categories/add", methods=["POST"])
def add_cat():
    try:
        d = request.get_json() or {}
        is_new_l1 = d.get("is_new_level1", False)
        l1_code = d.get("level1_code","").strip()
        l1_name = d.get("level1_name","").strip()
        l2_name = d.get("level2_name","").strip()
        desc = d.get("description","").strip()
        if not l1_name or not l2_name:
            return jsonify({"error":"分类名称不能为空"}),400
        if not is_new_l1 and not l1_code:
            return jsonify({"error":"请选择一级分类"}),400
        result = db.add_category(l1_code, l1_name, l2_name, desc, is_new_level1=is_new_l1)
        return jsonify({"success":True,"category":result})
    except Exception as e: traceback.print_exc(); return jsonify({"error":str(e)}),500

@app.route("/api/categories/stats", methods=["GET"])
def cat_stats():
    try: return jsonify(db.get_category_stats())
    except: return jsonify([])

@app.route("/api/categories")
def cats():
    try: return jsonify(db.get_all_categories())
    except: return jsonify([])

@app.route("/api/categories/tree")
def tree():
    try: return jsonify(db.get_categories_tree())
    except: return jsonify({})

# ================================================================
# AI建议
# ================================================================
@app.route("/api/architecture-suggestions", methods=["GET"])
def get_suggestions():
    try: return jsonify(db.get_pending_suggestions())
    except: return jsonify([])

@app.route("/api/architecture-suggestions/<int:sid>/approve", methods=["POST"])
def approve_suggestion(sid):
    try:
        db.update_suggestion_status(sid, "approved")
        return jsonify({"success":True})
    except Exception as e: traceback.print_exc(); return jsonify({"error":str(e)}),500

@app.route("/api/architecture-suggestions/<int:sid>/reject", methods=["POST"])
def reject_suggestion(sid):
    try:
        db.update_suggestion_status(sid, "rejected")
        return jsonify({"success":True})
    except Exception as e: traceback.print_exc(); return jsonify({"error":str(e)}),500

# ================================================================
# v2.0.0 新增：标签定义API（供前端标签选择器使用）
# ================================================================
@app.route("/api/tag-definitions")
def get_tag_defs():
    """返回三层标签体系的完整定义"""
    try:
        from scripts.tag_config import (LAYER1_TAGS, LAYER2_DIMENSIONS, LAYER3_KEYWORD_RULES,
                                        CONTENT_READINESS, SOURCE_AUTHORITY, ACCESS_LEVEL,
                                        FRESHNESS_INTERVALS)
        return jsonify({
            "layer1": LAYER1_TAGS,
            "layer2": LAYER2_DIMENSIONS,
            "layer3_rules": LAYER3_KEYWORD_RULES,
            "readiness": CONTENT_READINESS,
            "authority": SOURCE_AUTHORITY,
            "access_level": ACCESS_LEVEL,
            "freshness_intervals": FRESHNESS_INTERVALS
        })
    except Exception as e:
        traceback.print_exc()
        return jsonify({"error":str(e)}),500

# ================================================================
# 标签、统计、文件、系统
# ================================================================
@app.route("/api/tags")
def get_all_tags():
    try:
        conn = db.get_connection(); c = conn.cursor()
        c.execute("SELECT suggested_tags, final_tags FROM knowledge_points")
        tag_count = {}
        for row in c.fetchall():
            for field in [row["suggested_tags"], row["final_tags"]]:
                if not field: continue
                try:
                    tags = json.loads(field) if isinstance(field, str) else field
                    if isinstance(tags, list):
                        for t in tags:
                            t = t.strip()
                            if t and _is_valid_tag(t):
                                tag_count[t] = tag_count.get(t, 0) + 1
                except: pass
        conn.close()
        sorted_tags = sorted(tag_count.items(), key=lambda x: -x[1])
        return jsonify([{"tag": t, "count": c} for t, c in sorted_tags])
    except: traceback.print_exc(); return jsonify([])

@app.route("/api/statistics")
def stats():
    try: return jsonify(db.get_statistics())
    except: return jsonify({"files":{},"knowledge_points":{},"by_type":{},"today_api_cost":0,"total_confirmed":0,"total_pending":0,"pending_suggestions":0})

@app.route("/api/files")
def files():
    try:
        conn=db.get_connection();c=conn.cursor()
        s=request.args.get("status")
        if s: c.execute("SELECT * FROM source_files WHERE process_status=? ORDER BY created_at DESC",(s,))
        else: c.execute("SELECT * FROM source_files ORDER BY created_at DESC")
        rows=[dict(r) for r in c.fetchall()];conn.close();return jsonify(rows)
    except: return jsonify([])

@app.route("/api/system/health")
def health(): return jsonify({"status":"ok"})

@app.route("/api/debug")
def debug():
    info={"status":"ok","errors":[],"html_loaded":REVIEW_HTML is not None,"html_len":len(REVIEW_HTML) if REVIEW_HTML else 0}
    try:
        conn=db.get_connection();c=conn.cursor()
        c.execute("SELECT name FROM sqlite_master WHERE type='table'")
        info["tables"]=[r[0] for r in c.fetchall()]
        info["counts"]={}
        for t in info["tables"]:
            c.execute(f"SELECT COUNT(*) FROM {t}"); info["counts"][t]=c.fetchone()[0]
        c.execute("SELECT id,title,review_status FROM knowledge_points LIMIT 5")
        info["sample"]=[dict(r) for r in c.fetchall()]
        info["db_path"]=db.db_path; conn.close()
    except Exception as e: info["status"]="error"; info["errors"].append(str(e))
    return jsonify(info)

# ================================================================
# v2.1.2 F046+F033: 管理后台 - 仪表盘
# ================================================================
@app.route("/api/dashboard", methods=["GET"])
def dashboard():
    """聚合仪表盘全部数据，一次返回"""
    try:
        data = {}
        conn = db.get_connection()
        c = conn.cursor()

        # 按状态分布(直接SQL,不依赖get_statistics)
        c.execute("SELECT review_status, COUNT(*) FROM knowledge_points GROUP BY review_status")
        by_status = {}
        total_kp = 0
        for row in c.fetchall():
            by_status[row[0] or "pending"] = row[1]
            total_kp += row[1]
        data["by_status"] = by_status
        data["total_kp"] = total_kp
        data["total_pending"] = by_status.get("pending", 0)
        data["total_confirmed"] = by_status.get("confirmed", 0)

        # 按类型分布(全部知识点,不限confirmed)
        c.execute("SELECT content_type, COUNT(*) FROM knowledge_points GROUP BY content_type")
        by_type = {}
        for row in c.fetchall():
            by_type[row[0] or "policy"] = row[1]
        data["by_type"] = by_type

        # API费用: 直接从api_call_logs查询
        today = datetime.now().strftime("%Y-%m-%d")
        c.execute("SELECT SUM(estimated_cost) FROM api_call_logs WHERE call_date=?", (today,))
        today_cost_direct = c.fetchone()[0] or 0
        data["today_api_cost"] = round(today_cost_direct, 4)

        # API费用上限
        try:
            cfg_p2 = PROJECT_ROOT / "config" / "settings.json"
            if cfg_p2.exists():
                with open(cfg_p2, "r", encoding="utf-8") as f2:
                    data["daily_limit"] = json.load(f2).get("daily_cost_limit", 0)
        except:
            data["daily_limit"] = 0

        # 今日按类型统计(保留供API详情弹窗使用)
        c.execute("""SELECT call_type, COUNT(*), SUM(estimated_cost) FROM api_call_logs
                     WHERE call_date=? GROUP BY call_type ORDER BY SUM(estimated_cost) DESC""", (today,))
        api_detail = []
        for row in c.fetchall():
            api_detail.append({"type": row[0], "count": row[1], "cost": round(row[2] or 0, 4)})
        data["api_today_detail"] = api_detail

        # 近7天趋势
        c.execute("""SELECT call_date, SUM(estimated_cost) FROM api_call_logs
                     WHERE call_date >= date('now','localtime','-7 days')
                     GROUP BY call_date ORDER BY call_date""")
        trend = []
        for row in c.fetchall():
            trend.append({"date": row[0], "cost": round(row[1] or 0, 4)})
        data["api_trend_7d"] = trend

        # 就绪度分布（已确认的）
        c.execute("""SELECT content_readiness, COUNT(*) FROM knowledge_points
                     WHERE review_status='confirmed' GROUP BY content_readiness""")
        rd_map = {}
        for row in c.fetchall():
            rd_map[row[0] or "draft"] = row[1]
        data["by_readiness"] = rd_map

        # 质检分数分布(CAST为整数避免4.0 vs "4"不匹配)
        # v2.3.0-hotfix: 把 qa_score=0.0 归入 unscored，和 get_qc_rerun_summary 的
        #   "待补跑=NULL 或 0.0" 口径对齐。否则会出现"未质检:0 但待补跑:2043"的打架。
        c.execute("""SELECT CAST(qa_score AS INTEGER) as qs, COUNT(*) FROM knowledge_points
                     WHERE qa_score IS NOT NULL AND qa_score > 0 GROUP BY qs ORDER BY qs""")
        qa_dist = {}
        for row in c.fetchall():
            qa_dist[str(row[0])] = row[1]
        c.execute("SELECT COUNT(*) FROM knowledge_points WHERE qa_score IS NULL OR qa_score = 0.0")
        qa_dist["unscored"] = c.fetchone()[0]
        data["qa_distribution"] = qa_dist

        # v2.2.3: qa_source 分布（batch/small_batch/single/rule_fallback）
        try:
            c.execute("""SELECT qa_source, COUNT(*) FROM knowledge_points
                         WHERE qa_source IS NOT NULL GROUP BY qa_source""")
            qa_src_map = {}
            for row in c.fetchall():
                qa_src_map[row[0] or "batch"] = row[1]
            data["qa_source_distribution"] = qa_src_map
        except:
            data["qa_source_distribution"] = {}

        # 保鲜摘要
        try:
            data["freshness"] = db.get_freshness_summary()
            # 已设保鲜周期的知识点数
            c.execute("SELECT COUNT(*) FROM knowledge_points WHERE freshness_interval_days IS NOT NULL AND freshness_interval_days > 0")
            data["freshness"]["managed"] = c.fetchone()[0]
        except:
            data["freshness"] = {"expired": 0, "expiring": 0, "fresh": 0, "managed": 0}

        # 政策校验摘要
        try:
            data["policy"] = db.get_policy_validation_summary()
        except:
            data["policy"] = {}

        # 重复检测摘要
        try:
            data["duplicates"] = db.get_duplicate_summary()
        except:
            data["duplicates"] = {"pending": 0}

        # v2.2.3 F057: 截断补救摘要（供仪表盘"截断补救"卡）
        try:
            data["truncation"] = db.get_truncation_summary()
        except:
            data["truncation"] = {"affected_files": 0, "total_truncations": 0, "total_recovery_runs": 0}

        # v2.2.3 F061: 质检补跑候选摘要（供工具箱"质检补跑"按钮角标）
        try:
            data["qc_rerun"] = db.get_qc_rerun_summary()
        except:
            data["qc_rerun"] = {"total_candidates": 0}

        # v2.3.0-part1 F049: 标签分布（A/C/D 组，供仪表盘卡片+穿透跳转）
        try:
            data["tag_distribution"] = {
                "A": db.get_tag_distribution("A"),
                "C": db.get_tag_distribution("C"),
                "D": db.get_tag_distribution("D"),
            }
        except Exception as _td_e:
            print(f"[dashboard] tag_distribution 计算失败: {_td_e}")
            data["tag_distribution"] = {"A": [], "C": [], "D": []}

        # 文件管线
        pipeline = {}
        base = PROJECT_ROOT
        try:
            cfg_p = PROJECT_ROOT / "config" / "settings.json"
            if cfg_p.exists():
                with open(cfg_p, "r", encoding="utf-8") as f:
                    base = Path(json.load(f).get("knowledge_base_path", str(PROJECT_ROOT)))
        except:
            pass
        for d in ["pending", "processing", "completed", "failed"]:
            dd = base / "data" / d
            if dd.exists():
                pipeline[d] = len([f for f in dd.iterdir() if f.is_file() and not f.name.startswith(".") and not f.suffix == ".md"])
            else:
                pipeline[d] = 0
        data["file_pipeline"] = pipeline

        # 源文件统计(用文件夹实际文件数之和,与管线一致)
        data["total_files"] = sum(pipeline.values())

        # v2.2.0: 注解统计
        try:
            data["annotations"] = db.get_annotation_summary()
        except:
            data["annotations"] = {"annotated_kps": 0, "total_annotations": 0, "by_type": {}}

        # v2.2.0: 手动录入统计
        try:
            c2 = conn.cursor()
            c2.execute("SELECT COUNT(*) FROM knowledge_points WHERE source_type='experience_note'")
            data["manual_kps"] = c2.fetchone()[0]
        except:
            data["manual_kps"] = 0

        conn.close()
        return jsonify(data)
    except Exception as e:
        traceback.print_exc()
        return jsonify({"error": str(e)}), 500

# ================================================================
# v2.1.2 F046: 管理后台 - 工具箱
# ================================================================
@app.route("/api/tools/system-check", methods=["POST"])
def tool_system_check():
    """执行系统检查，返回结构化结果"""
    try:
        from scripts.check_system import run_checks_json
        result = run_checks_json()
        return jsonify(result)
    except Exception as e:
        traceback.print_exc()
        return jsonify({"error": str(e)}), 500

@app.route("/api/tools/backup", methods=["POST"])
def tool_backup():
    """执行一键备份"""
    try:
        from scripts.backup_manager import BackupManager
        bm = BackupManager()
        path = bm.create_backup()
        if path:
            status = bm.get_backup_status()
            return jsonify({"success": True, "backup_path": path,
                            "count": status.get("count", 0) if status else 0})
        return jsonify({"success": False, "error": "备份失败"}), 500
    except Exception as e:
        traceback.print_exc()
        return jsonify({"error": str(e)}), 500

@app.route("/api/tools/backup-list", methods=["GET"])
def tool_backup_list():
    """获取备份列表"""
    try:
        from scripts.backup_manager import BackupManager
        bm = BackupManager()
        backups = bm.list_backups()
        result = []
        for b in backups:
            result.append({
                "filename": b["filename"],
                "size_mb": round(b["size_mb"], 2),
                "datetime": b["datetime"].strftime("%Y-%m-%d %H:%M:%S"),
                "label": b.get("label", "")
            })
        return jsonify(result)
    except Exception as e:
        traceback.print_exc()
        return jsonify([])

@app.route("/api/tools/backup-restore", methods=["POST"])
def tool_backup_restore():
    """从指定备份恢复"""
    try:
        d = request.get_json() or {}
        filename = d.get("filename", "")
        if not filename:
            return jsonify({"error": "缺少filename参数"}), 400
        from scripts.backup_manager import BackupManager
        bm = BackupManager()
        ok = bm.restore_backup(filename)
        if ok:
            return jsonify({"success": True, "restored_from": filename})
        return jsonify({"success": False, "error": "恢复失败"}), 500
    except Exception as e:
        traceback.print_exc()
        return jsonify({"error": str(e)}), 500

@app.route("/api/tools/freshness-scan", methods=["POST"])
def tool_freshness_scan():
    """执行保鲜扫描"""
    try:
        from scripts.freshness_checker import scan_freshness
        result = scan_freshness()
        # 只返回摘要，不返回完整列表（太长）
        summary = {
            "total_confirmed": result.get("total_confirmed", 0),
            "stale": result.get("stale", 0),
            "overdue": result.get("overdue", 0),
            "due_7d": result.get("due_7d", 0),
            "due_30d": result.get("due_30d", 0),
            "ok": result.get("ok", 0),
            "auto_filled": result.get("auto_filled", 0)
        }
        return jsonify({"success": True, "result": summary})
    except Exception as e:
        traceback.print_exc()
        return jsonify({"error": str(e)}), 500

@app.route("/api/tools/duplicate-scan", methods=["POST"])
def tool_duplicate_scan():
    """执行全库重复检测（含V3精判）"""
    try:
        from scripts.duplicate_checker import DuplicateChecker
        from scripts.deepseek_client import DeepSeekClient
        try:
            client = DeepSeekClient()
        except Exception as ce:
            return jsonify({"error": "AI客户端初始化失败: " + str(ce)}), 500
        checker = DuplicateChecker(db=db, client=client)
        new_groups = checker.scan_full()
        summary = db.get_duplicate_summary()
        return jsonify({"success": True, "new_groups": new_groups, "summary": summary})
    except Exception as e:
        traceback.print_exc()
        return jsonify({"error": str(e)}), 500

@app.route("/api/tools/duplicate-reset-rescan", methods=["POST"])
def tool_duplicate_reset_rescan():
    """v2.2.2: 清理所有pending假阳性后用V3重新全库扫描
    v2.2.3 F060: 全库重扫前强制备份
    """
    try:
        # v2.2.3 F060: 全库重扫前强制备份
        try:
            operation_hook("full_rescan")
        except BackupFailedError as be:
            return jsonify({"error": "备份失败，重扫终止: " + str(be)}), 500
        from scripts.duplicate_checker import DuplicateChecker
        from scripts.deepseek_client import DeepSeekClient
        try:
            client = DeepSeekClient()
        except Exception as ce:
            return jsonify({"error": "AI客户端初始化失败: " + str(ce)}), 500
        checker = DuplicateChecker(db=db, client=client)
        dismissed = db.dismiss_all_pending_duplicates()
        new_groups = checker.scan_full()
        summary = db.get_duplicate_summary()
        return jsonify({"success": True, "dismissed": dismissed,
                        "new_groups": new_groups, "summary": summary})
    except Exception as e:
        traceback.print_exc()
        return jsonify({"error": str(e)}), 500

# ================================================================
# v2.3.0-part1 F049: 智能重复检测统一接口（三选一）
# ================================================================
@app.route("/api/tools/duplicate_unified", methods=["POST"])
def tool_duplicate_unified():
    """F049: 工具箱"智能重复检测"合并接口，前端弹窗三选一调用同一后端。

    入参 JSON:
      {"mode": "recent|full|reset_rescan", "days": 7}
        - recent        : 只扫最近 days 天内创建的 pending 知识点（默认 days=7，不备份）
        - full          : 全库扫描（不备份，保留历史 pending 组）
        - reset_rescan  : 强制备份(operation_hook("full_rescan")) → 清理全部 pending 组 → 全库重扫

    返回:
      {"success": True, "mode": "...", "new_groups": N, "summary": {...}, "dismissed": M(仅reset_rescan)}

    向下兼容说明:
      旧路由 /api/tools/duplicate-scan 和 /api/tools/duplicate-reset-rescan 保留不变，
      供浏览器缓存的旧 review.html 继续调用。新 review.html 应改用本接口。
    """
    try:
        d = request.get_json() or {}
        mode = (d.get("mode") or "").strip()
        if mode not in ("recent", "full", "reset_rescan"):
            return jsonify({"error": "mode 必须为 recent / full / reset_rescan"}), 400

        # reset_rescan 模式强制备份（F060）
        if mode == "reset_rescan":
            try:
                operation_hook("full_rescan")
            except BackupFailedError as be:
                return jsonify({"error": "备份失败，重扫终止: " + str(be)}), 500

        from scripts.duplicate_checker import DuplicateChecker
        from scripts.deepseek_client import DeepSeekClient
        try:
            client = DeepSeekClient()
        except Exception as ce:
            return jsonify({"error": "AI客户端初始化失败: " + str(ce)}), 500
        checker = DuplicateChecker(db=db, client=client)

        dismissed = None
        if mode == "recent":
            try:
                days = int(d.get("days", 7))
            except (TypeError, ValueError):
                days = 7
            if days <= 0:
                days = 7
            new_groups = checker.scan_recent(days=days)
        elif mode == "full":
            new_groups = checker.scan_full()
        else:  # reset_rescan
            dismissed = db.dismiss_all_pending_duplicates()
            new_groups = checker.scan_full()

        summary = db.get_duplicate_summary()
        resp = {"success": True, "mode": mode,
                "new_groups": new_groups, "summary": summary}
        if dismissed is not None:
            resp["dismissed"] = dismissed
        return jsonify(resp)
    except Exception as e:
        traceback.print_exc()
        return jsonify({"error": str(e)}), 500

# ================================================================
# v2.2.3 F061: 历史质检补跑（走 F058 三级降级链）
# ================================================================
def _load_source_content(sf):
    """F061 辅助：加载源文件内容（优先读.md缓存，再尝试文本原文件）
    用于给 _quality_check 的规则兜底做 excerpt 存在性检查（反幻觉）
    """
    if not sf:
        return ""
    base = PROJECT_ROOT
    try:
        cfg_p = PROJECT_ROOT / "config" / "settings.json"
        if cfg_p.exists():
            with open(cfg_p, "r", encoding="utf-8") as f:
                base = Path(json.load(f).get("knowledge_base_path", str(PROJECT_ROOT)))
    except:
        pass
    fn = sf.get("renamed_filename") or sf.get("original_filename") or ""
    if not fn:
        return ""
    stem = Path(fn).stem
    md_name = stem + ".md"
    # 优先 .md 缓存（可能在 processing / completed / failed 任一目录）
    for d in ["processing", "completed", "failed"]:
        p = base / "data" / d / md_name
        if p.exists():
            try:
                return p.read_text(encoding="utf-8")
            except:
                continue
    # 再尝试文本原文件
    for d in ["processing", "completed", "failed"]:
        p = base / "data" / d / fn
        if p.exists() and p.suffix.lower() in (".txt", ".md"):
            try:
                return p.read_text(encoding="utf-8")
            except:
                continue
    return ""

def _qc_rerun_core(progress_cb=None):
    """F061 核心：用 Extractor._quality_check 三级降级链补跑
    候选来自 db.get_qc_rerun_candidates()（qa_score IS NULL 或 qa_flags 含"格式异常"）
    按源文件分组逐个处理（_quality_check 需要 source_content 做规则兜底反幻觉）

    v2.3.0-hotfix: 新增 progress_cb 回调(接收 dict)，供异步化后主循环上报进度
                   不传则保持原同步语义
    """
    def _report(d):
        if progress_cb:
            try: progress_cb(d)
            except: pass

    try:
        candidates = db.get_qc_rerun_candidates()
    except Exception as e:
        traceback.print_exc()
        return {"success": False, "error": "获取候选失败: " + str(e)}
    if not candidates:
        _report({"current_step": "完成", "message": "无待补跑知识点"})
        return {"success": True, "total": 0, "processed": 0,
                "file_count": 0, "errors": [], "message": "无待补跑知识点"}
    # 按源文件分组
    by_file = {}
    orphans = []
    for kp in candidates:
        fid = kp.get("source_file_id")
        if fid is None:
            orphans.append(kp)
        else:
            by_file.setdefault(fid, []).append(kp)

    _report({
        "total_candidates": len(candidates),
        "total_files": len(by_file),
        "current_file": 0,
        "processed_kps": 0,
        "current_step": "初始化 Extractor",
        "message": "共 %d 条候选，分布在 %d 个文件 + %d 条孤儿" % (
            len(candidates), len(by_file), len(orphans))
    })

    # 实例化 Extractor
    try:
        from scripts.extractor import Extractor
        ext = Extractor()
    except Exception as ex:
        traceback.print_exc()
        _report({"current_step": "出错", "message": "Extractor 初始化失败"})
        return {"success": False, "error": "Extractor 初始化失败: " + str(ex)}
    total_processed = 0
    errors = []
    processed_file_count = 0

    def _build_kps_and_info(kps_rows):
        """把 DB 行还原为 Extractor._quality_check 期望的格式"""
        kps_list = []
        kps_info = []
        for k in kps_rows:
            aic = k.get("ai_extracted_content") or "{}"
            if isinstance(aic, str):
                try: aic = json.loads(aic)
                except: aic = {}
            if not isinstance(aic, dict):
                aic = {}
            kp_data = dict(aic)
            kp_data["title"] = k.get("title", "") or ""
            kp_data["original_excerpt"] = k.get("original_excerpt", "") or ""
            pi = k.get("practical_insights") or "[]"
            if isinstance(pi, str):
                try: pi = json.loads(pi)
                except: pi = []
            if not isinstance(pi, list):
                pi = []
            kp_data["practical_insights"] = pi
            kps_list.append(kp_data)
            kps_info.append({"kp_id": k["id"], "title": k.get("title", "") or ""})
        return kps_list, kps_info

    for fid, kps in by_file.items():
        try:
            sf = db.get_source_file(fid)
            content = _load_source_content(sf) if sf else ""
            # 即便 content 为空也继续——规则兜底的 excerpt 存在性检查会自适应
            kps_list, kps_info = _build_kps_and_info(kps)
            # v2.3.0-part3.1 (hotfix): 补齐 filename/content_summary 位置参数
            # 真实签名 _quality_check(self, filename, content_summary, kps, kps_info, source_content="")
            # 历史补跑场景无预分析上下文,content_summary 传空串
            filename = ((sf.get("renamed_filename") or sf.get("original_filename")
                         or ("file_%d" % fid)) if sf else ("file_%d" % fid))
            _report({
                "current_filename": filename,
                "current_step": "质检补跑中",
                "message": "[%d/%d] %s (%d 条)" % (
                    processed_file_count + 1, len(by_file), filename, len(kps))
            })
            ext._quality_check(filename, "", kps_list, kps_info, source_content=content)
            total_processed += len(kps)
            processed_file_count += 1
            _report({
                "current_file": processed_file_count,
                "processed_kps": total_processed
            })
        except Exception as ex:
            traceback.print_exc()
            errors.append("文件#%d: %s" % (fid, str(ex)))
            # 即便出错也推进计数，免得进度条卡住
            processed_file_count += 1
            _report({"current_file": processed_file_count})

    # 孤儿（source_file_id 为空，通常是经验速记）单独处理
    if orphans:
        try:
            _report({
                "current_filename": "experience_notes",
                "current_step": "处理孤儿条目",
                "message": "孤儿条目 %d 条（经验速记）" % len(orphans)
            })
            kps_list, kps_info = _build_kps_and_info(orphans)
            # v2.3.0-part3.1 (hotfix): 同上,补齐 filename/content_summary
            ext._quality_check("experience_notes", "", kps_list, kps_info, source_content="")
            total_processed += len(orphans)
            _report({"processed_kps": total_processed})
        except Exception as ex:
            traceback.print_exc()
            errors.append("孤儿条目(无源文件): %s" % str(ex))

    summary_after = {}
    try:
        summary_after = db.get_qc_rerun_summary()
    except:
        pass

    # v2.3.0-hotfix: 补跑尾阶段顺手跑一次就绪度联动（qa>=4 且 draft → quotable）
    # 之前单独留着 draft + qa>=4 的条目没意义；跑完补跑正好是联动最佳时机
    readiness_promote = {}
    try:
        readiness_promote = db.promote_readiness_by_qa_score()
    except Exception as _rp_e:
        traceback.print_exc()
        readiness_promote = {"error": str(_rp_e)}

    _report({
        "current_step": "完成",
        "message": "已补跑 %d 条，跳过 %d 个分组，就绪度升级 %d 条" % (
            total_processed, len(errors),
            readiness_promote.get("promoted_to_quotable", 0) if isinstance(readiness_promote, dict) else 0
        )
    })
    return {
        "success": True,
        "total": len(candidates),
        "processed": total_processed,
        "file_count": processed_file_count,
        "orphan_count": len(orphans),
        "errors": errors,
        "summary_after": summary_after,
        "readiness_promote": readiness_promote
    }

@app.route("/api/tools/qc_rerun/summary", methods=["GET"])
def qc_rerun_summary_api():
    """F061 摘要：返回待补跑的知识点数量（供前端按钮角标）"""
    try:
        s = db.get_qc_rerun_summary()
        return jsonify(s)
    except Exception as e:
        traceback.print_exc()
        return jsonify({"error": str(e), "total_candidates": 0}), 500

@app.route("/api/tools/qc_rerun", methods=["POST"])
def qc_rerun_api():
    """F061 执行：走 F058 三级降级链补跑质检
    v2.3.0-part3.2 hotfix: 改异步执行（独立 _qc_task 槽，可与 _task 并发）
                   立即返回 202，前端轮询 /api/tools/qc_rerun/progress
                   对齐 F048/F062 模板,启动就绪性自检放 _qc_task_lock 之前
    """
    # ---- v2.3.0-part3.2: 启动就绪性自检（必须在 _qc_task_lock 之前）----
    # 对齐对话 B 立的"长任务前置自检"规则(本任务虽用独立锁不受字面约束,
    # 仍按模板对齐,防止未来从独立锁迁回 _task 时遗漏)
    ok, errors = _qc_readiness_check()
    if not ok:
        try:
            db.log_operation_event(
                event_type="qc_rerun_readiness_check_failed",
                module="api_server",
                severity="error",
                payload={"errors": errors}
            )
        except Exception:
            pass
        return jsonify({
            "success": False,
            "error": "质检补跑环境未就绪",
            "errors": errors
        }), 500

    # 抢独立的质检补跑锁
    with _qc_task_lock:
        if _qc_task["running"]:
            return jsonify({
                "error": "已有质检补跑任务在执行，请等待完成或刷新查看进度",
                "running": True
            }), 409
        _qc_task["running"] = True
        _qc_task["started_at"] = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
        _qc_task["progress"] = {
            "total_files": 0, "current_file": 0, "current_filename": "",
            "total_candidates": 0, "processed_kps": 0,
            "current_step": "启动中", "message": ""
        }
        _qc_task["result"] = None
        _qc_task["error"] = None

    def _run():
        try:
            result = _qc_rerun_core(progress_cb=_qc_task_update_progress)
            with _qc_task_lock:
                if not result.get("success"):
                    _qc_task["error"] = result.get("error", "补跑失败")
                    _qc_task["progress"]["current_step"] = "出错"
                    _qc_task["progress"]["message"] = _qc_task["error"]
                else:
                    _qc_task["result"] = result
        except Exception as e:
            traceback.print_exc()
            with _qc_task_lock:
                _qc_task["error"] = str(e)
                _qc_task["progress"]["current_step"] = "出错"
                _qc_task["progress"]["message"] = str(e)
        finally:
            with _qc_task_lock:
                _qc_task["running"] = False

    threading.Thread(target=_run, daemon=True).start()
    return jsonify({
        "success": True,
        "async": True,
        "message": "质检补跑任务已启动，请在进度面板查看"
    }), 202

@app.route("/api/tools/qc_rerun/progress", methods=["GET"])
def qc_rerun_progress_api():
    """v2.3.0-hotfix: 质检补跑任务进度（独立 _qc_task 槽，不走 /api/tasks/progress）"""
    with _qc_task_lock:
        return jsonify({
            "running": _qc_task["running"],
            "started_at": _qc_task["started_at"],
            "progress": dict(_qc_task["progress"]),
            "result": _qc_task["result"],
            "error": _qc_task["error"]
        })

# ================================================================
# v2.3.0-hotfix: 就绪度联动（原 v2.3.1 单开批量按钮需求）
# ----------------------------------------------------------------
# 规则：qa_score>=4 AND readiness='draft' → 'quotable' （只升不降）
# - 质检补跑完成后会自动触发一次（见 _qc_rerun_core 尾部）
# - 也可以用下面两个端点独立触发（preview 先看要升多少，promote 真升）
# ================================================================
@app.route("/api/tools/readiness_promote/preview", methods=["GET"])
def readiness_promote_preview_api():
    """预览：如果现在跑联动，会升多少条"""
    try:
        return jsonify(db.get_readiness_promote_preview())
    except Exception as e:
        traceback.print_exc()
        return jsonify({"error": str(e), "will_promote": 0}), 500

@app.route("/api/tools/readiness_promote", methods=["POST"])
def readiness_promote_api():
    """执行：按规则批量升 draft→quotable。操作快(单 UPDATE)，直接同步。"""
    try:
        result = db.promote_readiness_by_qa_score()
        return jsonify({"success": True, **result})
    except Exception as e:
        traceback.print_exc()
        return jsonify({"success": False, "error": str(e)}), 500


# ================================================================
# v2.3.1 F2 精品候选 AI 判定路由(7 条)
# ----------------------------------------------------------------
# 设计对齐 Phase 2 冻结档案 §5.1/5.2:
#   POST   /api/tools/premium_pool/refresh          启动 AI 刷新(异步 202)
#   POST   /api/tools/premium_pool/refresh/cancel   取消刷新
#   GET    /api/tools/premium_pool/refresh/progress 刷新进度(2 秒轮询)
#   GET    /api/tools/premium_pool/list             候选队列(view/status 过滤)
#   POST   /api/tools/premium_pool/bless            封神(单条或批量)
#   POST   /api/tools/premium_pool/unbless          撤销(单条)
#   POST   /api/tools/premium_pool/skip             跳过(仅埋点)
# ================================================================

@app.route("/api/tools/premium_pool/refresh", methods=["POST"])
def premium_pool_refresh():
    """启动一次两视角 AI 刷新(异步 202).

    A+C 双保险:
      A. 10 分钟冷却期(return 429 + 剩余秒数)
      C. 前端弹确认框(前端实现,本路由不再弹)
    """
    # [A] 冷却期检查
    with _premium_task_lock:
        if _premium_task["running"]:
            return jsonify({"success": False, "error": "精品 AI 刷新已在执行中"}), 409
        last_done = _premium_task.get("last_completed_at")
    if last_done:
        try:
            elapsed = (datetime.now() - datetime.strptime(last_done, "%Y-%m-%d %H:%M:%S")).total_seconds()
            if elapsed < PREMIUM_COOLDOWN_SECONDS:
                remain = int(PREMIUM_COOLDOWN_SECONDS - elapsed)
                return jsonify({
                    "success": False,
                    "error": "冷却期未结束,还需 %d 秒" % remain,
                    "cooldown_remaining_seconds": remain,
                }), 429
        except Exception:
            pass  # 时间解析失败不阻断

    # 启动就绪性自检(立规则 31:必须在 _premium_task_lock 之前)
    ok, errors = _premium_readiness_check()
    if not ok:
        try:
            db.log_operation_event(
                event_type="premium_readiness_check_failed",
                module="api_server", severity="error",
                payload={"errors": errors},
            )
        except Exception:
            pass
        return jsonify({"success": False, "error": "启动自检失败",
                        "details": errors}), 400

    # 抢锁并启动后台线程
    with _premium_task_lock:
        if _premium_task["running"]:  # double check
            return jsonify({"success": False, "error": "精品 AI 刷新已在执行中"}), 409
        _premium_task["running"] = True
        _premium_task["started_at"] = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
        _premium_task["cancel_requested"] = False
        _premium_task["result"] = None
        _premium_task["error"] = None
        # 重置进度
        for k in _premium_task["progress"]:
            _premium_task["progress"][k] = 0 if isinstance(
                _premium_task["progress"][k], (int, float)) else ""

    def _worker():
        try:
            # 取 AI 客户端(与 extractor / health_checker 用同一个)
            from scripts.deepseek_client import DeepSeekClient
            client = DeepSeekClient()
            result = run_premium_refresh(
                db, client,
                progress_callback=_premium_task_update_progress,
                cancel_check=_premium_cancel_check,
            )
            with _premium_task_lock:
                _premium_task["result"] = result
                _premium_task["error"] = None
                _premium_task["last_completed_at"] = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
        except Exception as e:
            traceback.print_exc()
            with _premium_task_lock:
                _premium_task["error"] = str(e)
                _premium_task["result"] = None
            try:
                db.log_operation_event(
                    event_type="premium_refresh_failed", module="api_server",
                    severity="error", payload={"error": str(e)[:500]},
                )
            except Exception:
                pass
        finally:
            with _premium_task_lock:
                _premium_task["running"] = False
                _premium_task["cancel_requested"] = False

    threading.Thread(target=_worker, daemon=True).start()
    return jsonify({
        "success": True,
        "status": "started",
        "message": "精品 AI 刷新已启动,预估 40-60 分钟,请通过 /progress 轮询",
    }), 202


@app.route("/api/tools/premium_pool/refresh/cancel", methods=["POST"])
def premium_pool_refresh_cancel():
    """请求取消正在执行的刷新(协作式,引擎下一次判定条目时检查)."""
    with _premium_task_lock:
        if not _premium_task["running"]:
            return jsonify({"success": False, "error": "当前无刷新任务"}), 409
        _premium_task["cancel_requested"] = True
    return jsonify({"success": True, "message": "已发送取消请求,引擎将在下一次循环退出"})


@app.route("/api/tools/premium_pool/refresh/progress", methods=["GET"])
def premium_pool_refresh_progress():
    """获取当前刷新进度(前端 2 秒轮询)."""
    with _premium_task_lock:
        snap = {
            "running": _premium_task["running"],
            "started_at": _premium_task["started_at"],
            "last_completed_at": _premium_task["last_completed_at"],
            "cancel_requested": _premium_task["cancel_requested"],
            "progress": dict(_premium_task["progress"]),
            "result": _premium_task["result"],
            "error": _premium_task["error"],
        }
    # 附带冷却剩余
    if snap["last_completed_at"] and not snap["running"]:
        try:
            elapsed = (datetime.now() - datetime.strptime(snap["last_completed_at"], "%Y-%m-%d %H:%M:%S")).total_seconds()
            snap["cooldown_remaining_seconds"] = max(0, int(PREMIUM_COOLDOWN_SECONDS - elapsed))
        except Exception:
            snap["cooldown_remaining_seconds"] = 0
    else:
        snap["cooldown_remaining_seconds"] = 0
    return jsonify(snap)


@app.route("/api/tools/premium_pool/list", methods=["GET"])
def premium_pool_list():
    """精品候选队列(按视角 + 状态过滤 + composite_score 排序).

    Query:
      view=client|rfp       (必填)
      status=strong|optional (选填,不填返回全部 strong+optional)
      exclude_blessed=1|0   (选填,默认 1:本视角已封神的不返回)
    """
    view = (request.args.get("view") or "").strip()
    if view not in ("client", "rfp"):
        return jsonify({"success": False, "error": "view 必须是 client 或 rfp"}), 400
    status_filter = request.args.get("status")
    if status_filter and status_filter not in ("strong", "optional"):
        status_filter = None
    exclude_blessed = request.args.get("exclude_blessed", "1") != "0"

    try:
        items = db.get_premium_pool_list(
            view=view, status_filter=status_filter,
            exclude_blessed_in_view=exclude_blessed,
        )
    except Exception as e:
        traceback.print_exc()
        return jsonify({"success": False, "error": str(e)}), 500

    # 强推门槛(冻结档案 §6.4):Top 10-15% 标 strong,中段 40% 标 optional
    # 不做剔除,只在返回体上标注 level(前端按 level 分 tab 显示)
    total = len(items)
    if total > 0:
        # composite_score 已降序,直接按位置划档
        strong_cutoff = max(1, int(total * 0.15))
        optional_cutoff = max(strong_cutoff, int(total * 0.55))
        for idx, it in enumerate(items):
            if idx < strong_cutoff:
                it["level"] = "strong"
            elif idx < optional_cutoff:
                it["level"] = "optional"
            else:
                it["level"] = "low"
        # 如果传了 status_filter,返回前过滤一遍 level
        # (AI 的 recommendation 字段仍保留,供 UI 展示 AI 的原始推荐)
        if status_filter == "strong":
            items = [it for it in items if it["level"] == "strong"]
        elif status_filter == "optional":
            items = [it for it in items if it["level"] == "optional"]
        else:
            items = [it for it in items if it["level"] in ("strong", "optional")]

    # 总量统计(不受 status_filter 影响)
    with _premium_task_lock:
        last_refresh = _premium_task.get("last_completed_at")

    # 重新拿一次 strong/optional 总数(原 items 基础上)
    strong_count = sum(1 for it in items if it.get("level") == "strong")
    optional_count = sum(1 for it in items if it.get("level") == "optional")

    return jsonify({
        "success": True,
        "view": view,
        "items": items,
        "total_returned": len(items),
        "strong_count": strong_count,
        "optional_count": optional_count,
        "last_refreshed_at": last_refresh,
    })


@app.route("/api/tools/premium_pool/bless", methods=["POST"])
def premium_pool_bless():
    """封神一条或多条.

    Body JSON:
      kp_ids: [int, ...]  (至少 1 条)
      view:   'client' | 'rfp'

    批量 (len(kp_ids) >= 10) 强制备份 operation_hook('premium_blessed').
    """
    data = request.get_json(force=True, silent=True) or {}
    kp_ids = data.get("kp_ids") or []
    view = (data.get("view") or "").strip()
    if not isinstance(kp_ids, list) or not kp_ids:
        return jsonify({"success": False, "error": "kp_ids 必须是非空数组"}), 400
    if view not in ("client", "rfp"):
        return jsonify({"success": False, "error": "view 必须是 client 或 rfp"}), 400

    # 批量门槛:≥10 条强制备份
    if len(kp_ids) >= 10:
        try:
            operation_hook("premium_blessed")
        except BackupFailedError as e:
            return jsonify({"success": False,
                            "error": "批量封神前置备份失败: " + str(e)}), 500
        except Exception as e:
            # 其他备份异常也阻断(保守)
            traceback.print_exc()
            return jsonify({"success": False,
                            "error": "批量封神前置备份异常: " + str(e)}), 500

    blessed_ok = []
    failed = []
    for kid in kp_ids:
        try:
            r = db.bless_premium(int(kid), view)
            if r.get("ok"):
                blessed_ok.append(int(kid))
            else:
                failed.append({"kp_id": kid, "error": r.get("error", "unknown")})
        except Exception as e:
            failed.append({"kp_id": kid, "error": str(e)[:200]})

    return jsonify({
        "success": True,
        "blessed_count": len(blessed_ok),
        "blessed_kp_ids": blessed_ok,
        "failed": failed,
        "view": view,
    })


@app.route("/api/tools/premium_pool/unbless", methods=["POST"])
def premium_pool_unbless():
    """撤销一条(单条,不支持批量——批量撤销风险过大).

    Body JSON:
      kp_id: int
      view:  'client' | 'rfp'
    """
    data = request.get_json(force=True, silent=True) or {}
    kp_id = data.get("kp_id")
    view = (data.get("view") or "").strip()
    if not isinstance(kp_id, int) and not (isinstance(kp_id, str) and kp_id.isdigit()):
        return jsonify({"success": False, "error": "kp_id 必须是整数"}), 400
    if view not in ("client", "rfp"):
        return jsonify({"success": False, "error": "view 必须是 client 或 rfp"}), 400
    try:
        r = db.unbless_premium(int(kp_id), view)
        return jsonify({"success": True, **r})
    except Exception as e:
        traceback.print_exc()
        return jsonify({"success": False, "error": str(e)}), 500


@app.route("/api/tools/premium_pool/skip", methods=["POST"])
def premium_pool_skip():
    """跳过一条(仅埋点,不改 kp 状态).

    Body JSON: kp_id / view
    """
    data = request.get_json(force=True, silent=True) or {}
    kp_id = data.get("kp_id")
    view = (data.get("view") or "").strip()
    if view not in ("client", "rfp"):
        return jsonify({"success": False, "error": "view 必须是 client 或 rfp"}), 400
    try:
        db.log_operation_event(
            event_type="premium_skipped", module="api_server",
            severity="info", related_kp_id=int(kp_id) if kp_id else None,
            payload={"view": view},
        )
    except Exception:
        pass
    return jsonify({"success": True, "kp_id": kp_id, "view": view})


# ================================================================
# v2.3.1 F6 精品导出路由(1 条)
# ================================================================
@app.route("/api/tools/premium_export", methods=["GET"])
def premium_export():
    """精品导出(Markdown 或 JSON, 直接下载).

    Query:
      scope:        all_premium | client_only | rfp_only | by_category
      format:       markdown | json (默认 markdown)
      tier_filter:  逗号分隔 verified,trusted,candidate (选填)
      category_id:  int (scope=by_category 时必填)
    """
    scope = (request.args.get("scope") or "all_premium").strip()
    fmt = (request.args.get("format") or "markdown").strip()
    tier_filter_raw = request.args.get("tier_filter")
    tier_filter = None
    if tier_filter_raw:
        tier_filter = [t.strip() for t in tier_filter_raw.split(",") if t.strip()]
    category_id = None
    if scope == "by_category":
        try:
            category_id = int(request.args.get("category_id"))
        except (TypeError, ValueError):
            return jsonify({"success": False,
                            "error": "scope=by_category 时 category_id 必填且为整数"}), 400

    try:
        content, filename, mime = build_premium_export(
            db, scope=scope, format=fmt,
            tier_filter=tier_filter, category_id=category_id,
        )
    except ValueError as e:
        return jsonify({"success": False, "error": str(e)}), 400
    except Exception as e:
        traceback.print_exc()
        try:
            db.log_operation_event(
                event_type="premium_export_failed", module="api_server",
                severity="error",
                payload={"scope": scope, "format": fmt, "error": str(e)[:300]},
            )
        except Exception:
            pass
        return jsonify({"success": False, "error": str(e)}), 500

    # 埋点:成功
    try:
        db.log_operation_event(
            event_type="premium_export_success", module="api_server",
            severity="info",
            payload={"scope": scope, "format": fmt,
                     "tier_filter": tier_filter,
                     "category_id": category_id, "filename": filename},
        )
    except Exception:
        pass

    # URL-encode 中文文件名(兼容老浏览器 + RFC 5987)
    from urllib.parse import quote
    resp = Response(content, mimetype=mime)
    resp.headers["Content-Disposition"] = (
        "attachment; filename=\"%s\"; filename*=UTF-8''%s"
        % (quote(filename), quote(filename))
    )
    return resp


# ================================================================
# 旧 /api/tools/qa-backfill 接口（v2.2.2 F054）
# v2.2.3 起：向下兼容转发到新的三级降级链，字段映射保持原响应格式
# ================================================================
@app.route("/api/tools/qa-backfill", methods=["POST"])
def tool_qa_backfill():
    """v2.2.3 F061: 向下兼容转发到 _qc_rerun_core()
    旧接口语义：批量V3质检未质检条目
    新能力：三级降级链(批量15→小批3→逐条→规则兜底)，覆盖未质检+格式异常+低分
    响应字段映射：processed→checked, errors数组长度→errors, 保持原前端兼容
    """
    try:
        r = _qc_rerun_core()
        if not r.get("success"):
            return jsonify({"error": r.get("error", "补跑失败")}), 500
        errs = r.get("errors", []) or []
        err_count = len(errs) if isinstance(errs, list) else 0
        processed = r.get("processed", 0)
        total = r.get("total", 0)
        return jsonify({
            "success": True,
            "checked": processed,
            "errors": err_count,
            "total": total,
            "message": "已补跑 %d 条(三级降级链)，跳过 %d 个文件/分组" % (processed, err_count),
            "summary_after": r.get("summary_after", {})
        })
    except Exception as e:
        traceback.print_exc()
        return jsonify({"error": str(e)}), 500

# ================================================================
# v2.2.3 新增：事件日志查询
# ================================================================
@app.route("/api/events", methods=["GET"])
def api_events():
    """查询 operation_events 结构化事件日志
    参数：event_type / severity / module / file_id / limit（默认500）
    """
    try:
        event_type = request.args.get("event_type") or None
        severity = request.args.get("severity") or None
        module = request.args.get("module") or None
        file_id = request.args.get("file_id", None, type=int)
        limit = request.args.get("limit", 500, type=int)
        events = db.get_operation_events(
            event_type=event_type,
            severity=severity,
            module=module,
            file_id=file_id,
            limit=limit
        )
        result = []
        for e in (events or []):
            # 支持 sqlite Row 和 dict 两种返回
            if hasattr(e, "keys") and not isinstance(e, dict):
                item = {k: e[k] for k in e.keys()}
            else:
                item = dict(e)
            pj = item.get("payload_json")
            if isinstance(pj, str):
                try: item["payload"] = json.loads(pj)
                except: item["payload"] = {}
            elif isinstance(pj, dict):
                item["payload"] = pj
            else:
                item["payload"] = {}
            result.append(item)
        return jsonify(result)
    except Exception as e:
        traceback.print_exc()
        return jsonify([])

# ================================================================
# v2.2.3 F057 辅助：截断摘要
# ================================================================
@app.route("/api/tools/truncation_summary", methods=["GET"])
def truncation_summary_api():
    """F057 截断摘要：供仪表盘"截断补救"卡使用"""
    try:
        s = db.get_truncation_summary()
        return jsonify(s)
    except Exception as e:
        traceback.print_exc()
        return jsonify({
            "error": str(e),
            "affected_files": 0,
            "total_truncations": 0,
            "total_recovery_runs": 0
        }), 500

# ================================================================
# 工具箱其余端点（续）
# ================================================================
@app.route("/api/tools/policy-revalidate", methods=["POST"])
def tool_policy_revalidate():
    """对未校验知识点补跑政策校验"""
    try:
        from scripts.policy_validator import PolicyValidator
        pv = PolicyValidator(db=db)
        count = pv.run_standalone()
        return jsonify({"success": True, "validated": count})
    except Exception as e:
        traceback.print_exc()
        return jsonify({"error": str(e)}), 500

@app.route("/api/tools/review-analytics", methods=["GET"])
def tool_review_analytics():
    """获取审核反馈统计"""
    try:
        from scripts.review_analytics import get_analytics_json
        result = get_analytics_json()
        return jsonify(result)
    except Exception as e:
        traceback.print_exc()
        return jsonify({"error": str(e)}), 500

@app.route("/api/tools/file-pipeline", methods=["GET"])
def tool_file_pipeline():
    """获取文件管线详情"""
    try:
        base = PROJECT_ROOT
        try:
            cfg_p = PROJECT_ROOT / "config" / "settings.json"
            if cfg_p.exists():
                with open(cfg_p, "r", encoding="utf-8") as f:
                    base = Path(json.load(f).get("knowledge_base_path", str(PROJECT_ROOT)))
        except:
            pass
        pipeline = {}
        for d, desc in [("pending", "待分析"), ("processing", "处理中"),
                        ("completed", "已完成"), ("failed", "失败隔离")]:
            dd = base / "data" / d
            files = []
            if dd.exists():
                for fp in sorted(dd.iterdir()):
                    if fp.is_file() and not fp.name.startswith("."):
                        files.append({
                            "name": fp.name,
                            "size_kb": round(fp.stat().st_size / 1024, 1),
                            "modified": datetime.fromtimestamp(fp.stat().st_mtime).strftime("%Y-%m-%d %H:%M")
                        })
            pipeline[d] = {"label": desc, "count": len(files), "files": files}
        return jsonify(pipeline)
    except Exception as e:
        traceback.print_exc()
        return jsonify({"error": str(e)}), 500

@app.route("/api/tools/api-cost", methods=["GET"])
def tool_api_cost():
    """获取API费用详情"""
    try:
        conn = db.get_connection()
        c = conn.cursor()
        today = datetime.now().strftime("%Y-%m-%d")
        # 今日费用
        c.execute("""SELECT SUM(estimated_cost) FROM api_call_logs
                     WHERE call_date=?""", (today,))
        today_cost = c.fetchone()[0] or 0
        # 按类型统计今日
        c.execute("""SELECT call_type, COUNT(*), SUM(estimated_cost) FROM api_call_logs
                     WHERE call_date=? GROUP BY call_type ORDER BY SUM(estimated_cost) DESC""", (today,))
        today_detail = []
        for row in c.fetchall():
            today_detail.append({"type": row[0], "count": row[1], "cost": round(row[2] or 0, 4)})
        # 最近7天趋势
        c.execute("""SELECT call_date as d, SUM(estimated_cost) FROM api_call_logs
                     WHERE call_date >= date('now','localtime','-7 days')
                     GROUP BY d ORDER BY d""")
        trend = []
        for row in c.fetchall():
            trend.append({"date": row[0], "cost": round(row[1] or 0, 4)})
        # 费用上限
        limit = 0
        cfg_p = PROJECT_ROOT / "config" / "settings.json"
        if cfg_p.exists():
            try:
                with open(cfg_p, "r", encoding="utf-8") as f:
                    limit = json.load(f).get("daily_cost_limit", 0)
            except:
                pass
        conn.close()
        return jsonify({
            "today_cost": round(today_cost, 4),
            "daily_limit": limit,
            "today_detail": today_detail,
            "trend_7d": trend
        })
    except Exception as e:
        traceback.print_exc()
        return jsonify({"error": str(e)}), 500

# ================================================================
# v2.1.2 F047: 长任务端点(预处理/提取/进度)
# ================================================================
@app.route("/api/tasks/progress", methods=["GET"])
def task_progress():
    """获取当前任务进度"""
    with _task_lock:
        return jsonify({
            "running": _task["running"],
            "type": _task["type"],
            "started_at": _task["started_at"],
            "progress": dict(_task["progress"]),
            "result": _task["result"],
            "error": _task["error"]
        })

@app.route("/api/tasks/preprocess", methods=["POST"])
def task_preprocess():
    """启动文件预处理(后台线程)"""
    with _task_lock:
        if _task["running"]:
            return jsonify({"error": "有任务正在执行: " + _task["type"]}), 409
        _task["running"] = True
        _task["type"] = "preprocess"
        _task["started_at"] = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
        _task["progress"] = {"total_files": 0, "current_file": 0, "current_filename": "",
                             "current_step": "启动预处理", "total_extracted": 0, "message": ""}
        _task["result"] = None
        _task["error"] = None

    # v2.2.0 bugfix-5: 读取文档来源属性; bugfix-6: 强制重新处理
    d = request.get_json() or {}
    doc_origin = d.get("doc_origin", "external")
    if doc_origin not in ("self", "external"):
        doc_origin = "external"
    force_reprocess = bool(d.get("force_reprocess", False))

    def _run():
        try:
            try:
                from scripts.preprocessor import Preprocessor
            except ImportError:
                from preprocessor import Preprocessor
            msg = "正在处理文件..."
            if force_reprocess:
                msg = "强制重处理模式, 正在处理文件..."
            _task_update_progress({"current_step": "执行预处理", "message": msg})
            proc = Preprocessor()
            results = proc.run(doc_origin=doc_origin, force_reprocess=force_reprocess)
            ok = sum(1 for r in results if r.get("success"))
            fail = len(results) - ok
            with _task_lock:
                _task["result"] = {"success": True, "message": "预处理完成: 成功%d 失败%d" % (ok, fail), "ok": ok, "fail": fail, "skip": 0}
                _task["progress"]["current_step"] = "完成"
                _task["progress"]["message"] = "预处理完成: 成功%d 失败%d" % (ok, fail)
        except Exception as e:
            traceback.print_exc()
            with _task_lock:
                _task["error"] = str(e)
                _task["progress"]["current_step"] = "出错"
                _task["progress"]["message"] = str(e)
        finally:
            with _task_lock:
                _task["running"] = False

    threading.Thread(target=_run, daemon=True).start()
    return jsonify({"success": True, "message": "预处理任务已启动"})

@app.route("/api/tasks/extract", methods=["POST"])
def task_extract():
    """启动知识提取(后台线程)"""
    with _task_lock:
        if _task["running"]:
            return jsonify({"error": "有任务正在执行: " + _task["type"]}), 409
        _task["running"] = True
        _task["type"] = "extract"
        _task["started_at"] = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
        _task["progress"] = {"total_files": 0, "current_file": 0, "current_filename": "",
                             "current_step": "启动提取引擎", "total_extracted": 0, "message": ""}
        _task["result"] = None
        _task["error"] = None

    d = request.get_json() or {}
    model_key = d.get("model", "1")

    def _run():
        try:
            from scripts.extractor import Extractor
            ext = Extractor(progress_callback=_task_update_progress)
            result = ext.run_headless(model_key=model_key)
            with _task_lock:
                _task["result"] = result
                _task["progress"]["current_step"] = "完成"
        except Exception as e:
            traceback.print_exc()
            with _task_lock:
                _task["error"] = str(e)
                _task["progress"]["current_step"] = "出错"
                _task["progress"]["message"] = str(e)
        finally:
            with _task_lock:
                _task["running"] = False

    threading.Thread(target=_run, daemon=True).start()
    return jsonify({"success": True, "message": "提取任务已启动"})

# ================================================================
# v2.1.2 F044: 版本重提取
# ================================================================
@app.route("/api/tools/reextract-scan", methods=["GET"])
def reextract_scan():
    """扫描旧Prompt版本的知识点，按源文件分组"""
    try:
        try:
            from scripts.prompts.prompt_templates import get_prompt_version
            current_pv = get_prompt_version()
        except:
            try:
                from prompts.prompt_templates import get_prompt_version
                current_pv = get_prompt_version()
            except:
                current_pv = "unknown"
        rows = db.get_reextract_scan(current_pv)
        return jsonify({"current_version": current_pv, "files": rows})
    except Exception as e:
        traceback.print_exc()
        return jsonify({"error": str(e)}), 500

@app.route("/api/tasks/reextract", methods=["POST"])
def task_reextract():
    """执行版本重提取(备份→删除旧知识点→重置源文件状态→启动提取)
    v2.2.3 F060: 备份改用 operation_hook，失败立即终止任务
    """
    with _task_lock:
        if _task["running"]:
            return jsonify({"error": "有任务正在执行: " + _task["type"]}), 409
        _task["running"] = True
        _task["type"] = "reextract"
        _task["started_at"] = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
        _task["progress"] = {"total_files": 0, "current_file": 0, "current_filename": "",
                             "current_step": "准备重提取", "total_extracted": 0, "message": ""}
        _task["result"] = None
        _task["error"] = None

    d = request.get_json() or {}
    file_ids = d.get("file_ids", [])
    model_key = d.get("model", "1")

    if not file_ids:
        with _task_lock:
            _task["running"] = False
        return jsonify({"error": "未选择文件"}), 400

    def _run():
        try:
            # Step 1: v2.2.3 F060 强制自动备份（失败直接终止任务）
            _task_update_progress({"current_step": "自动备份", "message": "正在备份数据库..."})
            try:
                operation_hook("reextract")
            except BackupFailedError as be:
                with _task_lock:
                    _task["error"] = "备份失败，任务终止: " + str(be)
                    _task["progress"]["current_step"] = "出错"
                    _task["progress"]["message"] = str(be)
                    _task["running"] = False
                return

            # Step 2: 删除旧知识点 + 重置源文件状态
            _task_update_progress({"current_step": "删除旧知识点", "message": "正在清理旧数据...",
                                   "total_files": len(file_ids)})
            total_deleted = 0
            for idx, fid in enumerate(file_ids, 1):
                sf = db.get_source_file(fid)
                fn = (sf.get("renamed_filename") or sf.get("original_filename", "")) if sf else str(fid)
                _task_update_progress({"current_file": idx, "current_filename": fn,
                                       "message": "清理: " + fn})
                deleted = db.delete_kps_by_source_file(fid)
                total_deleted += deleted
                # 重置源文件状态为processing
                db.update_source_file(fid, process_status="processing",
                                      process_message="待重提取(v2.1.2)")

            _task_update_progress({"message": "已删除%d条旧知识点，开始重提取..." % total_deleted,
                                   "current_step": "启动提取引擎"})

            # Step 3: 启动提取
            from scripts.extractor import Extractor
            ext = Extractor(progress_callback=_task_update_progress)
            result = ext.run_headless(model_key=model_key)
            result["deleted_old"] = total_deleted
            with _task_lock:
                _task["result"] = result
                _task["progress"]["current_step"] = "完成"
        except Exception as e:
            traceback.print_exc()
            with _task_lock:
                _task["error"] = str(e)
                _task["progress"]["current_step"] = "出错"
                _task["progress"]["message"] = str(e)
        finally:
            with _task_lock:
                _task["running"] = False

    threading.Thread(target=_run, daemon=True).start()
    return jsonify({"success": True, "message": "重提取任务已启动", "file_count": len(file_ids)})

# ================================================================
# v2.3.0-part1 F059: 批量重跑候选扫描 + 批量重跑任务 + AI 去重联动
# ================================================================
@app.route("/api/tools/batch-rerun-scan", methods=["GET"])
def batch_rerun_scan():
    """F059: 批量重跑候选文件扫描。

    直接透传 db.get_batch_rerun_candidate_files() 结果，供前端提取管理 Tab 勾选。
    返回每个文件的 kp 总数/状态分布/是否含注解/截断计数等，让老唐肉眼判断要不要重跑。
    """
    try:
        rows = db.get_batch_rerun_candidate_files()
        return jsonify({"success": True, "files": rows, "total": len(rows)})
    except Exception as e:
        traceback.print_exc()
        return jsonify({"error": str(e)}), 500

@app.route("/api/tasks/batch_rerun", methods=["POST"])
def task_batch_rerun():
    """F059: 批量重跑任务（长任务，threading 后台 + 前端 2 秒轮询 /api/tasks/progress）。

    入参 JSON:
      {"file_ids": [1,2,3], "model": "1"}
        - file_ids 必填，至少 1 个源文件 id
        - model   : 可选，默认 "1"（主 API Key）

    关键流程:
      Step 1 operation_hook("batch_rerun") 强制备份，失败直接终止（BackupFailedError → 500）
      Step 2 保护性跑 5 个 migrate（与 run_headless 一致），初始化 Extractor + set_model
      Step 3 逐文件循环:
              a. db.delete_extracted_kps_by_source_file(fid)  # 仅删 pending，保留已审核
              b. db.update_source_file(fid, process_status="processing", ...)
              c. ext.extract_from_file(sf)  # 走正常提取链（F057 截断补救 / F058 质检降级 / Step 8）
              d. 累积 all_kps_info 与成功/跳过/失败计数，实时回调进度
              e. 费用上限则提前 break（与 run_headless 一致）
      Step 4 _check_category_suggestions(all_kps_info)  # 与 run_headless 行为对齐
      Step 5 跨文件 AI 去重联动: checker.scan_incremental(new_kp_ids)
              （scan_incremental 本身会与已 confirmed 的知识点比对；按"全部完成后统一跑一次"
                节省 R1 开销，并避免逐文件跑时上一步的 pending 还没入库就被作为比对基线）
      Step 6 汇总写入 _task["result"]

    返回（同步）:
      {"success": True, "message": "批量重跑已启动", "file_count": N}
    """
    with _task_lock:
        if _task["running"]:
            return jsonify({"error": "有任务正在执行: " + _task["type"]}), 409
        _task["running"] = True
        _task["type"] = "batch_rerun"
        _task["started_at"] = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
        _task["progress"] = {"total_files": 0, "current_file": 0, "current_filename": "",
                             "current_step": "准备批量重跑", "total_extracted": 0, "message": ""}
        _task["result"] = None
        _task["error"] = None

    d = request.get_json() or {}
    file_ids = d.get("file_ids") or []
    model_key = d.get("model", "1")

    if not isinstance(file_ids, list) or len(file_ids) == 0:
        with _task_lock:
            _task["running"] = False
        return jsonify({"error": "file_ids 不能为空"}), 400

    def _run():
        try:
            # ---- Step 1: F060 强制备份 ----
            _task_update_progress({"current_step": "自动备份",
                                   "message": "正在备份数据库..."})
            try:
                operation_hook("batch_rerun")
            except BackupFailedError as be:
                with _task_lock:
                    _task["error"] = "备份失败，任务终止: " + str(be)
                    _task["progress"]["current_step"] = "出错"
                    _task["progress"]["message"] = str(be)
                    _task["running"] = False
                return

            # ---- Step 2: 保护性迁移 + 初始化 Extractor ----
            _task_update_progress({"current_step": "初始化提取引擎",
                                   "message": "加载 Extractor...",
                                   "total_files": len(file_ids)})
            for mig_mod in ("migrate_v210c", "migrate_v210d_f028", "migrate_v211",
                            "migrate_v211_dup", "migrate_v223"):
                try:
                    mod = __import__("scripts." + mig_mod, fromlist=["migrate"])
                    mod.migrate()
                except ImportError:
                    pass
                except Exception as me:
                    print(f"  [WARN] 迁移 {mig_mod} 失败: {me}")

            from scripts.extractor import Extractor
            ext = Extractor(progress_callback=_task_update_progress)
            try:
                ext.set_model(model_key)
            except Exception as mke:
                print(f"  [WARN] set_model 失败，使用默认: {mke}")

            # ---- Step 3: 逐文件清理 pending + 重提取 ----
            all_kps_info = []
            total_deleted = 0
            ok, fail, skip = 0, 0, 0
            total_kps = 0
            per_file_results = []

            for idx, fid in enumerate(file_ids, 1):
                sf = db.get_source_file(fid)
                if not sf:
                    fail += 1
                    per_file_results.append({"file_id": fid, "status": "missing",
                                              "error": "source_file 不存在"})
                    print(f"  [WARN] 文件 id={fid} 不存在，跳过")
                    continue
                fn = sf.get("renamed_filename") or sf.get("original_filename") or str(fid)

                _task_update_progress({"current_file": idx, "current_filename": fn,
                                       "current_step": "清理旧知识点 (%d/%d)" % (idx, len(file_ids)),
                                       "message": "清理 pending: " + fn,
                                       "total_extracted": total_kps})

                # 仅删 pending，保留 confirmed/ignored 的审核成果（db 层方法保证）
                try:
                    deleted = db.delete_extracted_kps_by_source_file(fid)
                except Exception as de:
                    print(f"  [WARN] 清理 pending 失败 fid={fid}: {de}")
                    deleted = 0
                total_deleted += deleted

                # 重置源文件状态，让 extract_from_file 走正常 processing → completed 流程
                try:
                    db.update_source_file(fid, process_status="processing",
                                          process_message="待重提取(F059批量)")
                except Exception as ue:
                    print(f"  [WARN] 重置源文件状态失败 fid={fid}: {ue}")

                _task_update_progress({"current_file": idx, "current_filename": fn,
                                       "current_step": "重提取 (%d/%d)" % (idx, len(file_ids)),
                                       "message": "重提取: " + fn})

                try:
                    # sf 字典直接作为 rec 传入（字段结构兼容 extract_from_file）
                    r = ext.extract_from_file(sf)
                except Exception as ee:
                    traceback.print_exc()
                    r = {"success": False, "knowledge_count": 0,
                         "error": str(ee), "kps_info": []}

                status = "ok"
                if r.get("success"):
                    ok += 1
                    total_kps += r.get("knowledge_count", 0)
                    all_kps_info.extend(r.get("kps_info", []))
                elif "重复" in r.get("error", "") or "跳过" in r.get("error", ""):
                    skip += 1
                    status = "skip"
                else:
                    fail += 1
                    status = "fail"
                per_file_results.append({"file_id": fid, "filename": fn, "status": status,
                                         "knowledge_count": r.get("knowledge_count", 0),
                                         "error": r.get("error", "") if not r.get("success") else ""})

                if not r.get("success") and "费用上限" in r.get("error", ""):
                    _task_update_progress({"message": "费用达到上限，提前终止批量重跑"})
                    break

            # ---- Step 4: 分类建议（与 run_headless 行为对齐） ----
            if all_kps_info:
                try:
                    ext._check_category_suggestions(all_kps_info)
                except Exception as ce:
                    print(f"  [WARN] 分类建议检查失败: {ce}")

            # ---- Step 5: 跨文件 AI 去重联动 ----
            new_kp_ids = [info["kp_id"] for info in all_kps_info if info.get("kp_id")]
            dup_result = {"new_groups": 0, "scanned_kps": 0, "skipped": True}
            if new_kp_ids:
                _task_update_progress({"current_step": "跨文件去重",
                                       "message": "对新增 %d 条知识点做 AI 去重联动..."
                                                  % len(new_kp_ids)})
                try:
                    from scripts.duplicate_checker import DuplicateChecker
                    from scripts.deepseek_client import DeepSeekClient
                    dup_client = DeepSeekClient()
                    dup_checker = DuplicateChecker(db=db, client=dup_client)
                    new_groups = dup_checker.scan_incremental(new_kp_ids)
                    dup_result = {"new_groups": new_groups,
                                  "scanned_kps": len(new_kp_ids),
                                  "skipped": False}
                except Exception as de:
                    traceback.print_exc()
                    dup_result = {"new_groups": 0, "scanned_kps": len(new_kp_ids),
                                  "skipped": True, "error": str(de)}

            # ---- Step 6: 汇总 ----
            result = {
                "success": True,
                "file_count": len(file_ids),
                "ok": ok, "fail": fail, "skip": skip,
                "total_kps": total_kps,
                "deleted_old": total_deleted,
                "per_file": per_file_results,
                "duplicate_scan": dup_result,
                "message": "批量重跑完成: %d成功/%d跳过/%d失败，共%d条新知识点"
                           % (ok, skip, fail, total_kps)
            }
            with _task_lock:
                _task["result"] = result
                _task["progress"]["current_step"] = "完成"
                _task["progress"]["message"] = result["message"]
        except Exception as e:
            traceback.print_exc()
            with _task_lock:
                _task["error"] = str(e)
                _task["progress"]["current_step"] = "出错"
                _task["progress"]["message"] = str(e)
        finally:
            with _task_lock:
                _task["running"] = False

    threading.Thread(target=_run, daemon=True).start()
    return jsonify({"success": True, "message": "批量重跑已启动",
                    "file_count": len(file_ids)})

# ================================================================
# v2.3.0-part2 F048 知识库体检 Agent（界面层，对话3/3）
# ----------------------------------------------------------------
# 8 个路由 + 3 个辅助函数
# 所有路由零改动既有代码，仅在文件末尾追加。
# 辅助函数 3 个：_get_suggestion_by_id / _merge_ai_content / _health_progress_adapter
# ================================================================

# ------ 辅助函数 1：按 sid 查单条 polish_suggestion（db 层未提供该粒度方法） ------
def _get_suggestion_by_id(sid):
    """F048 对话3 辅助：按 suggestion_id 查单条打磨建议。

    db_manager 只暴露 get_polish_suggestions_by_report 批量查；此处 api_server 内
    手写 10 行 SQL 解决，不回改 db 层（按对话3 设计决策）。

    Returns: dict 或 None；original_content / suggested_content 自动 json.loads
    """
    try:
        conn = db.get_connection(); c = conn.cursor()
        c.execute("SELECT * FROM polish_suggestions WHERE suggestion_id=?", (int(sid),))
        row = c.fetchone()
        conn.close()
    except Exception as e:
        print(f"[_get_suggestion_by_id] sid={sid} 查询失败: {e}")
        return None
    if not row:
        return None
    r = dict(row)
    for f in ("original_content", "suggested_content"):
        v = r.get(f)
        if isinstance(v, str) and v.strip():
            try:
                r[f] = json.loads(v)
            except Exception:
                # 不是合法 JSON 就保留原字符串
                pass
    return r


# ------ 辅助函数 2：合并 AI 建议内容为 update_knowledge_point 参数 ------
def _merge_ai_content(kp_row, sc):
    """F048 对话3 辅助：把 suggested_content (dict) 合并为 update_knowledge_point 的 **kwargs。

    映射路径（与 v2.3.0-part2 设计决策锁定一致）：
      - sc["title"]                → kw["title"]（直接覆盖）
      - sc["practical_insights"]   → kw["practical_insights"]（直接覆盖 list）
      - sc["tags"]["layer1"]       → kw["final_category_tags"]（仅非空 list 时覆盖）
      - sc["tags"]["layer2"]       → kw["final_attribute_tags"]（仅非空 dict 时覆盖）
      - sc["tags"]["layer3"]       → kw["final_keywords"]（仅非空 list 时覆盖）
      - sc["description"]          → 写进 ai_extracted_content["polished_description"] 新键，
                                      不覆盖任何主字段（作为参考内容供人工查看）
      - sc["polish_notes"]         → 写进 ai_extracted_content["polish_notes"] 新键
      - content_readiness 不传     → 保留数据库原值（成熟度联动在 v2.3.1 单开批量按钮）

    Args:
        kp_row: dict，update_knowledge_point 前的 kp 原始行（主要用其 ai_extracted_content）
        sc:     dict，polish_suggestions.suggested_content 解析后的 dict

    Returns:
        kw: dict，可直接 db.update_knowledge_point(kp_id, **kw) 调用
    """
    if not isinstance(sc, dict):
        return {}
    kw = {}

    # 1) title（直接覆盖）
    if "title" in sc and isinstance(sc["title"], str) and sc["title"].strip():
        kw["title"] = sc["title"].strip()

    # 2) practical_insights（直接覆盖 list）
    if "practical_insights" in sc and isinstance(sc["practical_insights"], list):
        kw["practical_insights"] = sc["practical_insights"]

    # 3) 三层标签（仅非空时覆盖）
    tags = sc.get("tags") or {}
    if isinstance(tags, dict):
        l1 = tags.get("layer1")
        if isinstance(l1, list) and len(l1) > 0:
            kw["final_category_tags"] = l1
        l2 = tags.get("layer2")
        if isinstance(l2, dict) and len(l2) > 0:
            kw["final_attribute_tags"] = l2
        l3 = tags.get("layer3")
        if isinstance(l3, list) and len(l3) > 0:
            kw["final_keywords"] = l3

    # 4) description / polish_notes 写进 ai_extracted_content 子键（不覆盖主字段）
    desc = sc.get("description")
    notes = sc.get("polish_notes")
    if (isinstance(desc, str) and desc.strip()) or (isinstance(notes, str) and notes.strip()):
        orig_aec = kp_row.get("ai_extracted_content") if kp_row else None
        if isinstance(orig_aec, str):
            try:
                orig_aec = json.loads(orig_aec)
            except Exception:
                orig_aec = {}
        if not isinstance(orig_aec, dict):
            orig_aec = {}
        merged_aec = dict(orig_aec)
        if isinstance(desc, str) and desc.strip():
            merged_aec["polished_description"] = desc
        if isinstance(notes, str) and notes.strip():
            merged_aec["polish_notes"] = notes
        kw["ai_extracted_content"] = merged_aec

    return kw


# ------ 辅助函数 3：HealthChecker 进度回调 → _task["progress"] 映射 ------
_HEALTH_STAGE_MAP = {
    "init":           (1, "初始化扫描"),
    "dim1":           (2, "①健康度扫描"),
    "dim2":           (3, "②结构分布扫描"),
    "dim3":           (4, "③加工深度扫描"),
    "dim4_island":    (5, "④关联密度(孤岛精判)"),
    "dim5_polish":    (6, "⑤低分打磨(V3诊断→R1打磨→V3校验)"),
    "dim6_monetize":  (7, "⑥变现匹配度"),
    "done":           (8, "完成"),
    "failed":         (8, "出错"),
}

def _health_progress_adapter(payload):
    """F048 对话3 辅助：把 HealthChecker 的 {stage,current,total,message} 映射到
    _task["progress"]（{total_files,current_file,current_step,message,...}）。

    total_files 固定 8（六维度 + init + done 合算）。
    dim5_polish 阶段把 current/total 拼进 message：'打磨中 X/Y'。
    """
    if not isinstance(payload, dict):
        return
    stage = payload.get("stage") or ""
    msg = payload.get("message") or ""
    cur = payload.get("current")
    tot = payload.get("total")

    step_idx, step_label = _HEALTH_STAGE_MAP.get(stage, (0, stage or ""))

    # 打磨阶段把进度细节拼进 message
    extra_msg = msg
    if stage == "dim5_polish":
        try:
            ci = int(cur) if cur is not None else 0
            ti = int(tot) if tot is not None else 0
            if ti > 0:
                detail = "打磨中 " + str(ci) + "/" + str(ti)
                extra_msg = detail + (" | " + msg if msg else "")
        except Exception:
            pass

    _task_update_progress({
        "current_file": step_idx,
        "current_step": step_label,
        "message": extra_msg,
    })


# ================================================================
# v2.3.0-part2.2 新增：F048 启动就绪性自检（对话 B 防护层）
# ================================================================
def _health_readiness_check():
    """F048 体检启动前置自检。返回 (ok: bool, errors: list[str])。

    对齐对话 A 发现的 4 类系统性 bug + 对话 B 字段契约：
      [1] 6 个 F048 Prompt 顶层可 import（对话 A 缺陷 1：Prompt 未落地）
      [2] 6 个 Prompt 非 None 且为 dict（对话 A 缺陷 2：import 静默降级）
      [3] 每 Prompt 含非空 system_prompt / user_prompt_template（对话 A 缺陷 4：key 错配）
      [4] db.get_kp_for_health_scan 返回 dict 含 category / subcategory（对话 B 缺陷 3：字段契约）

    设计约束：
      - 总耗时 <100ms（读第 1 条 kp）
      - 空库时 [4] 跳过，不算失败（首次部署允许启动）
      - 自检失败时调用方必须在 with _task_lock 之前返回，不占用 _task 单例
    """
    errors = []

    # ---- [1]/[2] Prompt 顶层 import ----
    required_prompts = [
        "HEALTH_DIAGNOSIS_PROMPT",
        "HEALTH_POLISH_PROMPT",
        "HEALTH_POLISH_VERIFY_PROMPT",
        "HEALTH_POLISH_CONSERVATIVE_PROMPT",
        "HEALTH_ISLAND_JUDGE_PROMPT",
        "HEALTH_MONETIZE_REPORT_PROMPT",
    ]
    try:
        from scripts.prompts import prompt_templates as pt
    except Exception as e:
        errors.append("[1] prompt_templates 模块 import 失败: " + str(e))
        return False, errors

    prompt_objs = {}
    for name in required_prompts:
        obj = getattr(pt, name, None)
        if obj is None:
            errors.append("[1] Prompt " + name + " 未定义或为 None（对话 A 缺陷 1/2）")
            continue
        if not isinstance(obj, dict):
            errors.append("[2] Prompt " + name + " 不是 dict（实际类型: " +
                          type(obj).__name__ + "）")
            continue
        prompt_objs[name] = obj

    # ---- [3] Prompt dict 含正确 key ----
    for name, obj in prompt_objs.items():
        sys_p = obj.get("system_prompt")
        usr_p = obj.get("user_prompt_template")
        if not sys_p or not isinstance(sys_p, str):
            errors.append("[3] Prompt " + name +
                          " 缺 system_prompt 或为空（对话 A 缺陷 4：key 错配）")
        if not usr_p or not isinstance(usr_p, str):
            errors.append("[3] Prompt " + name +
                          " 缺 user_prompt_template 或为空（对话 A 缺陷 4：key 错配）")

    # ---- [4] DB 字段契约（category / subcategory AS 映射）----
    try:
        sample = db.get_kp_for_health_scan(include_annotations=False)
        if sample:
            first = sample[0]
            missing_keys = []
            if "category" not in first:
                missing_keys.append("category")
            if "subcategory" not in first:
                missing_keys.append("subcategory")
            if missing_keys:
                errors.append("[4] get_kp_for_health_scan 返回 dict 缺字段: " +
                              ", ".join(missing_keys) +
                              "（对话 B 缺陷 3：LEFT JOIN categories AS 映射未兑现）")
        # 空库不算失败（首次部署允许启动）
    except Exception as e:
        errors.append("[4] get_kp_for_health_scan 调用失败: " + str(e))

    ok = len(errors) == 0
    return ok, errors


# ================================================================
# F048 路由 1：工具箱卡片用 —— 最近一次体检概要
# ================================================================
@app.route("/api/tools/health/latest", methods=["GET"])
def health_latest():
    """返回最新一份 completed 报告的概要（工具箱第 10 张卡展示用）。
    无报告时 success=True，报告字段为 None。
    """
    try:
        r = db.get_latest_health_report()
        if not r:
            return jsonify({"success": True, "report": None})
        # 瘦身：仅回概要字段，不回 full_report_json
        summary = {
            "report_id": r.get("report_id"),
            "created_at": r.get("created_at"),
            "total_score": r.get("total_score"),
            "dim1_health_score": r.get("dim1_health_score"),
            "dim2_structure_score": r.get("dim2_structure_score"),
            "dim3_processing_score": r.get("dim3_processing_score"),
            "dim4_relation_score": r.get("dim4_relation_score"),
            "dim5_polish_score": r.get("dim5_polish_score"),
            "dim6_monetize_score": r.get("dim6_monetize_score"),
            "scanned_kp_count": r.get("scanned_kp_count"),
        }
        return jsonify({"success": True, "report": summary})
    except Exception as e:
        traceback.print_exc()
        return jsonify({"error": str(e)}), 500


# ================================================================
# F048 路由 2：启动体检（后台线程）
# ================================================================
@app.route("/api/tools/health/start", methods=["POST"])
def health_start():
    """启动全库体检。

    入参 JSON：
      {"polish_max": 50}  # 允许值: 30/50/100/200/None（不限）

    v2.3.0-part2.2 新增：在 with _task_lock 之前做 4 项启动就绪性自检。
      自检失败 → HTTP 400 带 details 清单，不占用 _task 单例。
      自检通过 → 进入原有后台线程逻辑。
    """
    # ---- v2.3.0-part2.2 启动就绪性自检（必须在 _task_lock 之前）----
    ok, errors = _health_readiness_check()
    if not ok:
        try:
            db.log_operation_event(
                event_type="health_readiness_check_failed",
                module="api_server",
                severity="error",
                payload={"errors": errors},
            )
        except Exception:
            pass
        return jsonify({
            "success": False,
            "error": "F048 体检环境未就绪",
            "details": errors,
            "message": "请检查 Prompt 落地、字段契约。排查步骤：命令行运行 python scripts/db_health_check.py",
        }), 400

    with _task_lock:
        if _task["running"]:
            return jsonify({"error": "有任务正在执行: " + _task["type"]}), 409
        _task["running"] = True
        _task["type"] = "health"
        _task["started_at"] = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
        _task["progress"] = {
            "total_files": 8, "current_file": 0, "current_filename": "",
            "current_step": "准备启动体检", "total_extracted": 0, "message": ""
        }
        _task["result"] = None
        _task["error"] = None

    d = request.get_json() or {}
    # polish_max 白名单在 HealthChecker 内部还会再校验一次，此处放宽
    polish_max = d.get("polish_max", 50)
    # 前端可能传字符串 "None" / "" 表示不限
    if polish_max in ("None", "none", "", None):
        polish_max = None
    else:
        try:
            polish_max = int(polish_max)
        except (TypeError, ValueError):
            polish_max = 50

    def _run():
        try:
            from scripts.health_checker import HealthChecker
            from scripts.deepseek_client import DeepSeekClient
            try:
                client = DeepSeekClient()
            except Exception as ce:
                with _task_lock:
                    _task["error"] = "DeepSeek 客户端初始化失败: " + str(ce)
                    _task["progress"]["current_step"] = "出错"
                    _task["progress"]["message"] = str(ce)
                return

            _task_update_progress({"current_step": "初始化体检引擎",
                                   "message": "加载 HealthChecker..."})

            hc = HealthChecker(
                db=db, client=client,
                progress_callback=_health_progress_adapter,
            )
            result = hc.run_full_check(polish_max=polish_max)

            with _task_lock:
                if result and result.get("success"):
                    _task["result"] = {
                        "success": True,
                        "report_id": result.get("report_id"),
                        "total_score": result.get("total_score"),
                        "message": "体检完成，总分 " + str(result.get("total_score") or "--"),
                    }
                    _task["progress"]["current_step"] = "完成"
                    _task["progress"]["current_file"] = 8
                    _task["progress"]["message"] = "体检完成"
                else:
                    err = (result or {}).get("error") or "未知错误"
                    _task["error"] = "体检失败: " + str(err)
                    _task["progress"]["current_step"] = "出错"
                    _task["progress"]["message"] = str(err)
        except Exception as e:
            traceback.print_exc()
            with _task_lock:
                _task["error"] = str(e)
                _task["progress"]["current_step"] = "出错"
                _task["progress"]["message"] = str(e)
        finally:
            with _task_lock:
                _task["running"] = False

    threading.Thread(target=_run, daemon=True).start()
    return jsonify({"success": True, "message": "知识库体检已启动",
                    "polish_max": polish_max})


# ================================================================
# F048 路由 3：历史报告列表
# ================================================================
@app.route("/api/tools/health/history", methods=["GET"])
def health_history():
    """历史报告列表，默认最多 20 份。
    query: ?limit=50
    """
    try:
        limit = request.args.get("limit", 20)
        try:
            limit = int(limit)
        except (TypeError, ValueError):
            limit = 20
        rows = db.get_health_report_list(limit=limit)
        return jsonify({"success": True, "items": rows, "count": len(rows)})
    except Exception as e:
        traceback.print_exc()
        return jsonify({"error": str(e)}), 500


# ================================================================
# F048 路由 4：单份报告详情（含 full_report_json）
# ================================================================
@app.route("/api/tools/health/report/<int:rid>", methods=["GET"])
def health_report_detail(rid):
    """单份报告详情，full_report_json 已在 db 层解析为 dict。"""
    try:
        r = db.get_health_report_detail(rid)
        if not r:
            return jsonify({"error": "report not found: " + str(rid)}), 404
        return jsonify({"success": True, "report": r})
    except Exception as e:
        traceback.print_exc()
        return jsonify({"error": str(e)}), 500


# ================================================================
# F048 路由 5：该报告的 Review 清单
# ================================================================
@app.route("/api/tools/health/suggestions/<int:rid>", methods=["GET"])
def health_suggestions_list(rid):
    """拉取某报告的打磨建议列表。
    query:
      ?status=pending|applied|rejected|manual_review_needed  （可选，不传返回全部）
    """
    try:
        status = request.args.get("status") or None
        items = db.get_polish_suggestions_by_report(rid, status=status)
        # 附加 kp 当前标题，方便前端卡片展示（若 kp 已被物理删除则用 original_content.title 兜底）
        conn = db.get_connection(); c = conn.cursor()
        for it in items:
            try:
                c.execute("SELECT title, review_status FROM knowledge_points WHERE id=?",
                          (it.get("kp_id"),))
                row = c.fetchone()
                if row:
                    it["kp_current_title"] = row[0] or ""
                    it["kp_current_status"] = row[1] or ""
                else:
                    oc = it.get("original_content") or {}
                    it["kp_current_title"] = oc.get("title", "") if isinstance(oc, dict) else ""
                    it["kp_current_status"] = "deleted"
            except Exception:
                it["kp_current_title"] = ""
                it["kp_current_status"] = ""
        conn.close()
        return jsonify({"success": True, "items": items, "count": len(items)})
    except Exception as e:
        traceback.print_exc()
        return jsonify({"error": str(e)}), 500


# ================================================================
# F048 路由 6：采纳（L1/L2，三步原子）
# ================================================================
@app.route("/api/tools/health/suggestions/<int:sid>/adopt", methods=["POST"])
def health_suggestion_adopt(sid):
    """L1/L2 采纳。

    三步原子（任一失败返 500 附 step 标识）：
      Step 1 operation_hook("health_adopt") 备份
      Step 2 db.update_knowledge_point(kp_id, **_merge_ai_content(kp_row, sc))
      Step 3 db.apply_polish_suggestion(sid)

    特殊规则：
      - tier='L3_manual' → 返 400（L3 仅支持驳回/略过）
      - suggestion_type='drop' → 返 400（drop 请走 /drop 路由）
      - suggestion_type='split' 且 sc 是 list 且 len>1 → 仅取 sc[0]，响应带 split_note
    """
    sugg = _get_suggestion_by_id(sid)
    if not sugg:
        return jsonify({"error": "suggestion not found: " + str(sid)}), 404

    status = sugg.get("status") or ""
    if status not in ("pending", "manual_review_needed"):
        return jsonify({"error": "当前建议状态不可采纳: " + status}), 409

    tier = sugg.get("tier") or ""
    stype = sugg.get("suggestion_type") or ""

    # L3 兜底不支持采纳
    if tier == "L3_manual":
        return jsonify({
            "error": "L3 建议仅支持驳回或略过，请到 Tab 1 手工修订对应知识点"
        }), 400

    # drop 走独立路由
    if stype == "drop":
        return jsonify({
            "error": "drop 类型建议请调用 /api/tools/health/suggestions/<sid>/drop"
        }), 400

    sc = sugg.get("suggested_content")
    if sc is None:
        return jsonify({"error": "该建议 suggested_content 为空，无法采纳"}), 400

    # split 语义：多条时只取第一条
    split_note = None
    if isinstance(sc, list):
        if len(sc) == 0:
            return jsonify({"error": "suggested_content 为空数组，无法采纳"}), 400
        if len(sc) > 1:
            split_note = ("AI 建议拆分为 " + str(len(sc)) +
                          " 条，已采纳第 1 条；其余 " + str(len(sc) - 1) +
                          " 条请到 Tab 1 手动创建")
        sc = sc[0]

    if not isinstance(sc, dict):
        return jsonify({"error": "suggested_content 格式异常，非 dict"}), 400

    kp_id = sugg.get("kp_id")
    if not kp_id:
        return jsonify({"error": "建议未关联 kp_id"}), 400

    # 读 kp 当前行（用于合并 ai_extracted_content 子键，以及存在性校验）
    try:
        kp_row = db.get_knowledge_point(kp_id)
    except Exception:
        kp_row = None
    if not kp_row:
        return jsonify({"error": "知识点已不存在（可能被删除）: kp_id=" + str(kp_id)}), 404

    # ---- Step 1: 备份 ----
    try:
        operation_hook("health_adopt")
    except BackupFailedError as be:
        return jsonify({
            "error": "备份失败，采纳终止: " + str(be),
            "step": "backup",
        }), 500
    except Exception as e:
        traceback.print_exc()
        return jsonify({"error": "备份异常: " + str(e), "step": "backup"}), 500

    # ---- Step 2: 合并并更新 kp ----
    try:
        kw = _merge_ai_content(kp_row, sc)
        if not kw:
            return jsonify({
                "error": "合并后无可更新字段（AI 建议内容为空或全部跳过）",
                "step": "update_kp",
            }), 500
        db.update_knowledge_point(kp_id, **kw)
    except Exception as e:
        traceback.print_exc()
        return jsonify({
            "error": "更新知识点失败: " + str(e),
            "step": "update_kp",
        }), 500

    # ---- Step 3: 标记 suggestion applied ----
    try:
        ok = db.apply_polish_suggestion(sid)
        if not ok:
            return jsonify({
                "error": "标记建议 applied 失败（可能已被其他操作处理）",
                "step": "apply",
            }), 500
    except Exception as e:
        traceback.print_exc()
        return jsonify({"error": "标记建议失败: " + str(e), "step": "apply"}), 500

    # ---- 事件日志（尽力而为，失败不影响主流程） ----
    try:
        db.log_operation_event(
            event_type="health_suggestion_adopted",
            module="health_checker",
            severity="info",
            payload={
                "suggestion_id": sid, "kp_id": kp_id,
                "tier": tier, "suggestion_type": stype,
                "split_note": split_note,
                "fields_updated": list(kw.keys()),
            },
        )
    except Exception:
        pass

    resp = {
        "success": True,
        "suggestion_id": sid,
        "kp_id": kp_id,
        "tier": tier,
        "suggestion_type": stype,
        "fields_updated": list(kw.keys()),
        "message": "采纳成功",
    }
    if split_note:
        resp["split_note"] = split_note
    return jsonify(resp)


# ================================================================
# F048 路由 7：drop 独立路由（走 ignore_knowledge_point）
# ================================================================
@app.route("/api/tools/health/suggestions/<int:sid>/drop", methods=["POST"])
def health_suggestion_drop(sid):
    """drop 类型建议专用路由。

    三步：
      Step 1 operation_hook("health_adopt")  —— 复用同一 op_name 避免 backup 分桶过碎
      Step 2 db.ignore_knowledge_point(kp_id, reason="health_drop: " + diagnosis[:200])
      Step 3 db.apply_polish_suggestion(sid)
    """
    sugg = _get_suggestion_by_id(sid)
    if not sugg:
        return jsonify({"error": "suggestion not found: " + str(sid)}), 404

    status = sugg.get("status") or ""
    if status not in ("pending", "manual_review_needed"):
        return jsonify({"error": "当前建议状态不可处理: " + status}), 409

    stype = sugg.get("suggestion_type") or ""
    if stype != "drop":
        return jsonify({
            "error": "非 drop 类型建议请走 /adopt 路由（当前 suggestion_type=" + stype + ")"
        }), 400

    kp_id = sugg.get("kp_id")
    if not kp_id:
        return jsonify({"error": "建议未关联 kp_id"}), 400

    try:
        kp_row = db.get_knowledge_point(kp_id)
    except Exception:
        kp_row = None
    if not kp_row:
        return jsonify({"error": "知识点已不存在: kp_id=" + str(kp_id)}), 404

    diagnosis = sugg.get("diagnosis") or ""
    reason = "health_drop: " + (diagnosis[:200] if isinstance(diagnosis, str) else "")

    # ---- Step 1: 备份 ----
    try:
        operation_hook("health_adopt")
    except BackupFailedError as be:
        return jsonify({
            "error": "备份失败，操作终止: " + str(be),
            "step": "backup",
        }), 500
    except Exception as e:
        traceback.print_exc()
        return jsonify({"error": "备份异常: " + str(e), "step": "backup"}), 500

    # ---- Step 2: ignore kp ----
    try:
        db.ignore_knowledge_point(kp_id, reason=reason)
    except Exception as e:
        traceback.print_exc()
        return jsonify({
            "error": "标记 kp ignored 失败: " + str(e),
            "step": "update_kp",
        }), 500

    # ---- Step 3: 标记 suggestion applied ----
    try:
        ok = db.apply_polish_suggestion(sid)
        if not ok:
            return jsonify({
                "error": "标记建议 applied 失败（可能已被其他操作处理）",
                "step": "apply",
            }), 500
    except Exception as e:
        traceback.print_exc()
        return jsonify({"error": "标记建议失败: " + str(e), "step": "apply"}), 500

    # ---- 事件日志 ----
    try:
        db.log_operation_event(
            event_type="health_suggestion_dropped",
            module="health_checker",
            severity="info",
            payload={
                "suggestion_id": sid, "kp_id": kp_id,
                "reason": reason,
            },
        )
    except Exception:
        pass

    return jsonify({
        "success": True,
        "suggestion_id": sid,
        "kp_id": kp_id,
        "action": "ignored",
        "reason": reason,
        "message": "已按 AI 建议忽略该知识点（可到 Tab 1 恢复）",
    })


# ================================================================
# F048 路由 8：驳回（仅标 rejected）
# ================================================================
@app.route("/api/tools/health/suggestions/<int:sid>/reject", methods=["POST"])
def health_suggestion_reject(sid):
    """驳回建议。无备份、无 kp 变更，只改 polish_suggestion 行状态。
    入参 JSON（可选）: {"reason": "..."}
    """
    sugg = _get_suggestion_by_id(sid)
    if not sugg:
        return jsonify({"error": "suggestion not found: " + str(sid)}), 404

    status = sugg.get("status") or ""
    if status not in ("pending", "manual_review_needed"):
        return jsonify({"error": "当前建议状态不可驳回: " + status}), 409

    d = request.get_json(silent=True) or {}
    reason = d.get("reason") or ""

    try:
        ok = db.reject_polish_suggestion(sid, reason=reason)
        if not ok:
            return jsonify({"error": "驳回失败（可能已被处理）"}), 500
    except Exception as e:
        traceback.print_exc()
        return jsonify({"error": "驳回异常: " + str(e)}), 500

    try:
        db.log_operation_event(
            event_type="health_suggestion_rejected",
            module="health_checker",
            severity="info",
            payload={
                "suggestion_id": sid,
                "kp_id": sugg.get("kp_id"),
                "tier": sugg.get("tier"),
                "suggestion_type": sugg.get("suggestion_type"),
                "reason": reason,
            },
        )
    except Exception:
        pass

    return jsonify({
        "success": True,
        "suggestion_id": sid,
        "message": "已驳回",
    })


# ================================================================
# v2.3.0-part3 新增：F062 端到端健康测试 Agent 界面层（对话 3/3）
# ================================================================
#
# 设计原则（严格对齐对话 2 e2e_tester 引擎层契约 + F048 对话 B 规则）：
#   - _task["type"] = "e2e"（前后端锁定，review.html checkRunningTask 必须用 "e2e"）
#   - _e2e_readiness_check() 在 with _task_lock 之前执行（对话 B 立规则）
#   - progress_adapter 9 stage 完全对齐 e2e_tester.VALID_STAGES
#   - /latest total_score 从 full_report_json 解出（遵守对话 3 不回改 db 纪律）
# ================================================================

# ---- 进度 stage 映射表（与 e2e_tester.VALID_STAGES 严格对齐 9 种）----
_E2E_STAGE_MAP = {
    "init":           (1, "初始化端到端测试"),
    "dim1_route":     (2, "维度 1/6: 路由自省"),
    "dim2_readiness": (3, "维度 2/6: 启动就绪性"),
    "dim3_prompt":    (4, "维度 3/6: Prompt 调用一致性"),
    "dim4_field":     (5, "维度 4/6: 字段契约"),
    "dim5_event":     (6, "维度 5/6: V3 事件语义"),
    "dim6_smell":     (7, "维度 6/6: 代码异味"),
    "done":           (9, "扫描完成"),
    "failed":         (9, "扫描失败"),
}


def _e2e_progress_adapter(payload):
    """F062 进度回调适配器：e2e_tester {stage, current, total, message}
    -> _task["progress"] {current_file, current_step, message}。
    total_files = 9（固定，对齐 VALID_STAGES 9 种）。
    """
    payload = payload or {}
    stage = payload.get("stage") or ""
    msg = payload.get("message") or ""
    step_idx, step_label = _E2E_STAGE_MAP.get(stage, (0, stage or ""))
    _task_update_progress({
        "current_file": step_idx,
        "current_step": step_label,
        "message": msg,
    })


def _e2e_readiness_check():
    """F062 端到端测试启动前置自检（对齐 F048 _health_readiness_check 对话 B 模板）。
    返回 (ok: bool, errors: list[str])。

    自检 4 项：
      [1] E2E_RESPONSE_JUDGE_PROMPT 顶层可 import
      [2] Prompt 非 None 且为 dict，含非空 system_prompt / user_prompt_template
      [3] static_analyzer + e2e_tester 顶层可 import，关键方法/类存在
      [4] db 有 9 个 F062 方法（对话 1 落地 8 + 对话 3 补齐 get_e2e_test_report_list）

    总耗时 <50ms（无 SQL 调用）。自检失败时调用方必须在 with _task_lock 之前返回。
    """
    errors = []

    # ---- [1][2] Prompt 契约 ----
    try:
        from scripts.prompts import prompt_templates as pt
    except Exception as e:
        errors.append("[1] prompt_templates 模块 import 失败: " + str(e))
        return False, errors

    p = getattr(pt, "E2E_RESPONSE_JUDGE_PROMPT", None)
    if p is None:
        errors.append("[1] E2E_RESPONSE_JUDGE_PROMPT 未定义或为 None（对话 A 缺陷 1/2）")
    elif not isinstance(p, dict):
        errors.append("[2] E2E_RESPONSE_JUDGE_PROMPT 不是 dict（实际类型: " +
                      type(p).__name__ + "）")
    else:
        sys_p = p.get("system_prompt")
        usr_p = p.get("user_prompt_template")
        if not sys_p or not isinstance(sys_p, str):
            errors.append("[2] E2E_RESPONSE_JUDGE_PROMPT 缺 system_prompt 或为空（对话 A 缺陷 4：key 错配）")
        if not usr_p or not isinstance(usr_p, str):
            errors.append("[2] E2E_RESPONSE_JUDGE_PROMPT 缺 user_prompt_template 或为空（对话 A 缺陷 4：key 错配）")

    # ---- [3] static_analyzer + e2e_tester 顶层 import ----
    try:
        from scripts import static_analyzer as sa
        for m in ("scan_prompt_call_consistency", "scan_field_contract",
                  "scan_code_smells", "run_static_scan"):
            if not hasattr(sa, m):
                errors.append("[3] static_analyzer 缺方法: " + m)
    except Exception as e:
        errors.append("[3] static_analyzer import 失败: " + str(e))

    try:
        from scripts import e2e_tester as et
        if not hasattr(et, "E2ETester"):
            errors.append("[3] e2e_tester 缺 E2ETester 类")
        if not hasattr(et, "run_e2e_scan"):
            errors.append("[3] e2e_tester 缺 run_e2e_scan 便捷函数")
    except Exception as e:
        errors.append("[3] e2e_tester import 失败: " + str(e))

    # ---- [4] db 有 9 个 F062 方法 ----
    required_db_methods = [
        "register_endpoint", "get_endpoint_registry", "update_endpoint_last_tested",
        "save_e2e_test_report", "get_latest_e2e_test_report",
        "get_e2e_test_report_detail", "get_e2e_test_report_list",
        "upsert_e2e_issue", "set_e2e_issue_status",
    ]
    for m in required_db_methods:
        if not hasattr(db, m):
            errors.append("[4] db 缺 F062 方法: " + m)

    return len(errors) == 0, errors


# ================================================================
# F062 路由 1：最近一次扫描概要（工具箱卡片 + 软提醒徽章用）
# ================================================================
@app.route("/api/tools/e2e/latest", methods=["GET"])
def e2e_latest():
    """最新一份 E2E 报告的瘦身摘要。
    total_score 从 full_report_json 解出（走 detail 方法获取）。
    """
    try:
        latest = db.get_latest_e2e_test_report()
        if not latest:
            return jsonify({"success": True, "report": None})
        # 取 total_score 需要解 full_report_json
        rid = latest.get("report_id")
        total_score = None
        if rid:
            try:
                full = db.get_e2e_test_report_detail(rid)
                if full:
                    fr = full.get("full_report_json") or {}
                    if isinstance(fr, dict):
                        total_score = fr.get("total_score")
            except Exception:
                pass
        summary = {
            "report_id": latest.get("report_id"),
            "created_at": latest.get("created_at"),
            "trigger_type": latest.get("trigger_type"),
            "scan_depth": latest.get("scan_depth"),
            "total_endpoints": latest.get("total_endpoints"),
            "passed_count": latest.get("passed_count"),
            "failed_count": latest.get("failed_count"),
            "warning_count": latest.get("warning_count"),
            "v3_call_count": latest.get("v3_call_count"),
            "cost_estimate": latest.get("cost_estimate"),
            "total_score": total_score,
            "new_endpoints_count": len(latest.get("new_endpoints_json") or []),
        }
        return jsonify({"success": True, "report": summary})
    except Exception as e:
        traceback.print_exc()
        return jsonify({"error": str(e)}), 500


# ================================================================
# F062 路由 2：启动端到端测试（后台线程）
# ================================================================
@app.route("/api/tools/e2e/start", methods=["POST"])
def e2e_start():
    """启动 F062 端到端健康扫描。
    入参 JSON: {"scan_depth": "quick"|"deep"}
    """
    # ---- 启动就绪性自检（必须在 _task_lock 之前）----
    ok, errors = _e2e_readiness_check()
    if not ok:
        try:
            db.log_operation_event(
                event_type="e2e_readiness_check_failed",
                module="api_server",
                severity="error",
                payload={"errors": errors},
            )
        except Exception:
            pass
        return jsonify({
            "success": False,
            "error": "F062 端到端测试环境未就绪",
            "details": errors,
            "message": "请检查 Prompt 落地、依赖 import、db 方法契约。"
                       "排查步骤：命令行运行 python scripts/db_health_check.py",
        }), 400

    # ---- 占用 _task 单例 ----
    with _task_lock:
        if _task["running"]:
            return jsonify({"error": "有任务正在执行: " + _task["type"]}), 409
        _task["running"] = True
        _task["type"] = "e2e"
        _task["started_at"] = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
        _task["progress"] = {
            "total_files": 9, "current_file": 0, "current_filename": "",
            "current_step": "准备启动端到端测试",
            "total_extracted": 0, "message": ""
        }
        _task["result"] = None
        _task["error"] = None

    d = request.get_json() or {}
    scan_depth = d.get("scan_depth", "quick")
    if scan_depth not in ("quick", "deep"):
        scan_depth = "quick"

    def _run():
        try:
            from scripts.e2e_tester import run_e2e_scan
            from scripts.deepseek_client import DeepSeekClient
            try:
                client = DeepSeekClient()
            except Exception as ce:
                with _task_lock:
                    _task["error"] = "DeepSeek 客户端初始化失败: " + str(ce)
                    _task["progress"]["current_step"] = "出错"
                    _task["progress"]["message"] = str(ce)
                return

            _task_update_progress({
                "current_step": "初始化端到端测试引擎",
                "message": "加载 E2ETester..."
            })

            result = run_e2e_scan(
                db=db, client=client,
                progress_callback=_e2e_progress_adapter,
                scan_depth=scan_depth,
            )

            with _task_lock:
                if result and result.get("success"):
                    _task["result"] = {
                        "success": True,
                        "report_id": result.get("report_id"),
                        "total_score": result.get("total_score"),
                        "scan_depth": result.get("scan_depth"),
                        "message": "端到端测试完成，总分 " +
                                   str(result.get("total_score") or "--"),
                    }
                    _task["progress"]["current_step"] = "完成"
                    _task["progress"]["current_file"] = 9
                    _task["progress"]["message"] = "扫描完成"
                else:
                    err = (result or {}).get("error") or "未知错误"
                    _task["error"] = "扫描失败: " + str(err)
                    _task["progress"]["current_step"] = "出错"
                    _task["progress"]["message"] = str(err)
        except Exception as e:
            traceback.print_exc()
            with _task_lock:
                _task["error"] = str(e)
                _task["progress"]["current_step"] = "出错"
                _task["progress"]["message"] = str(e)
        finally:
            with _task_lock:
                _task["running"] = False

    threading.Thread(target=_run, daemon=True).start()
    return jsonify({"success": True, "message": "端到端测试已启动",
                    "scan_depth": scan_depth})


# ================================================================
# F062 路由 3：历史报告列表
# ================================================================
@app.route("/api/tools/e2e/history", methods=["GET"])
def e2e_history():
    """历史 E2E 报告列表。query: ?limit=20"""
    try:
        limit = request.args.get("limit", 20)
        try:
            limit = int(limit)
        except (TypeError, ValueError):
            limit = 20
        rows = db.get_e2e_test_report_list(limit=limit)
        return jsonify({"success": True, "items": rows, "count": len(rows)})
    except Exception as e:
        traceback.print_exc()
        return jsonify({"error": str(e)}), 500


# ================================================================
# F062 路由 4：单份报告详情（含 full_report_json 自动 parse）
# ================================================================
@app.route("/api/tools/e2e/report/<int:rid>", methods=["GET"])
def e2e_report_detail(rid):
    try:
        r = db.get_e2e_test_report_detail(rid)
        if not r:
            return jsonify({"error": "report not found: " + str(rid)}), 404
        return jsonify({"success": True, "report": r})
    except Exception as e:
        traceback.print_exc()
        return jsonify({"error": str(e)}), 500


# ================================================================
# F062 路由 4.5(v2.3.0-part3.5 新增)：E2E 诊断包 Markdown 导出
# ================================================================
# 设计思路:
#   - 纯读功能,直接委托 e2e_diagnosis_exporter 格式化
#   - Response 带 Content-Disposition: attachment 让浏览器触发下载
#   - 失败返回 404(报告不存在) 或 500(格式化异常),不污染任何 _task 槽
#   - 事件日志:打 export_success / export_failed 便于审计
# ================================================================
@app.route("/api/tools/e2e/export/<int:rid>", methods=["GET"])
def e2e_export_diagnosis(rid):
    """导出 E2E 诊断包为 Markdown 文件(浏览器下载)。

    纯读 + 零副作用:不写 DB、不调 AI、不抢 _task 锁。
    """
    try:
        md, filename = build_e2e_diagnosis_markdown(db, rid)
    except ValueError as ve:
        # report_id 不存在
        return jsonify({"error": str(ve)}), 404
    except Exception as e:
        traceback.print_exc()
        try:
            db.log_operation_event(
                event_type="e2e_export_failed",
                module="api_server",
                severity="error",
                payload={"report_id": rid, "error": str(e)},
            )
        except Exception:
            pass
        return jsonify({"error": str(e)}), 500

    # 成功埋点(非关键操作,失败不阻塞下载)
    try:
        db.log_operation_event(
            event_type="e2e_export_success",
            module="api_server",
            severity="info",
            payload={
                "report_id": rid,
                "filename": filename,
                "bytes": len(md.encode("utf-8")),
            },
        )
    except Exception:
        pass

    # 浏览器下载:Content-Disposition attachment + UTF-8
    # 兼容旧浏览器用 filename*=,新浏览器也认
    headers = {
        "Content-Disposition": (
            "attachment; filename=\"" + filename + "\"; "
            "filename*=UTF-8''" + filename
        ),
        "Cache-Control": "no-cache, no-store, must-revalidate",
    }
    return Response(md, mimetype="text/markdown; charset=utf-8", headers=headers)


# ================================================================
# F062 路由 5：issue 四态列表（含分组 + 筛选）
# ================================================================
@app.route("/api/tools/e2e/issues", methods=["GET"])
def e2e_issues_list():
    """issue 四态列表。
    query:
      ?status=pending|fixed|intermittent|ignored|all
      ?dim_code=1_route_introspect|...
      ?limit=500
    """
    try:
        status = request.args.get("status") or None
        dim_code = request.args.get("dim_code") or None
        try:
            limit = int(request.args.get("limit", 500))
            if limit < 1 or limit > 2000:
                limit = 500
        except (TypeError, ValueError):
            limit = 500

        if status and status not in ("pending", "fixed", "intermittent", "ignored", "all"):
            return jsonify({"error": "invalid status: " + status}), 400
        if status == "all":
            status = None

        where = []
        params = []
        if status:
            where.append("status=?")
            params.append(status)
        if dim_code:
            where.append("dim_code=?")
            params.append(dim_code)
        wsql = (" WHERE " + " AND ".join(where)) if where else ""

        conn = db.get_connection(); c = conn.cursor()
        c.execute("""SELECT issue_id, report_id, dim_code, endpoint, severity,
                            signature, status, first_seen_at, last_seen_at,
                            occurrence_count, resolved_at, payload_json
                     FROM e2e_issues""" + wsql + """
                     ORDER BY CASE status
                         WHEN 'pending' THEN 1
                         WHEN 'intermittent' THEN 2
                         WHEN 'fixed' THEN 3
                         WHEN 'ignored' THEN 4
                         ELSE 9
                     END, last_seen_at DESC
                     LIMIT ?""",
                  params + [limit])
        rows = c.fetchall()
        cols = [d[0] for d in c.description]
        items = []
        for r in rows:
            row = dict(zip(cols, r))
            try:
                raw = row.pop("payload_json") or "{}"
                row["payload"] = json.loads(raw) if isinstance(raw, str) else (raw or {})
            except Exception:
                row["payload"] = {}
            items.append(row)
        conn.close()

        by_status = {"pending": [], "intermittent": [], "fixed": [], "ignored": []}
        for it in items:
            s = it.get("status") or "pending"
            if s in by_status:
                by_status[s].append(it)

        return jsonify({"success": True, "items": items,
                        "by_status": by_status, "count": len(items)})
    except Exception as e:
        traceback.print_exc()
        return jsonify({"error": str(e)}), 500


# ================================================================
# F062 路由 6：issue 四态切换（无限双向，给老唐逃生口）
# ================================================================
@app.route("/api/tools/e2e/issues/<int:iid>/status", methods=["POST"])
def e2e_issue_set_status(iid):
    """四态切换。入参 JSON: {"status": "pending|fixed|intermittent|ignored"}
    允许无限四态切换，不限方向。
    """
    try:
        d = request.get_json() or {}
        new_status = (d.get("status") or "").strip()
        if new_status not in ("pending", "fixed", "intermittent", "ignored"):
            return jsonify({"error": "invalid status: " + new_status}), 400

        ok = db.set_e2e_issue_status(iid, new_status)
        if not ok:
            return jsonify({"error": "issue not found: " + str(iid)}), 404

        try:
            db.log_operation_event(
                event_type="e2e_issue_status_changed",
                module="e2e_tester",
                severity="info",
                payload={"issue_id": iid, "new_status": new_status},
            )
        except Exception:
            pass

        return jsonify({"success": True, "issue_id": iid, "new_status": new_status})
    except Exception as e:
        traceback.print_exc()
        return jsonify({"error": str(e)}), 500


# ================================================================
# v2.3.2 F055 本地问答助手路由(7 条)
# ----------------------------------------------------------------
# /api/qa/ask              POST   启动问答(异步 202)
# /api/qa/progress         GET    进度轮询(2 秒一次)
# /api/qa/cancel           POST   取消(协作式退出)
# /api/qa/history          GET    问答历史列表(分页 + 模式筛选 + test 过滤)
# /api/qa/history/<hid>    GET    单条问答详情
# /api/qa/feedback         POST   反馈写入(👍/👎/💬)
# /api/qa/stats            GET    反馈聚合统计
#
# 设计要点:
#   - 独立 _qa_task 槽,允许并发(老唐自测 + 朋友试用同时跑)
#   - 端到端硬上限 60 秒,前端轮询超时主动 /cancel
#   - mode='self|friend' 由请求体传(默认 self),朋友试用走 ?mode=friend URL
#   - is_test_query=1 标记老唐自测,不回写 used_count(防脏数据)
# ================================================================
@app.route("/api/qa/ask", methods=["POST"])
def qa_ask():
    """启动一次问答(异步 202).

    Body JSON:
      query:         str   用户问题(必填,1-500 字)
      mode:          'self' | 'friend'  默认 self
      is_test_query: 0 | 1  老唐自测标记,默认 0
    """
    try:
        body = request.get_json(silent=True) or {}
    except Exception:
        body = {}
    query = (body.get("query") or "").strip()
    mode = body.get("mode") or "self"
    if mode not in ("self", "friend"):
        mode = "self"
    is_test = 1 if body.get("is_test_query") else 0

    if not query:
        return jsonify({"success": False, "error": "query 必填"}), 400
    if len(query) > 500:
        return jsonify({"success": False, "error": "query 超长(>500 字)"}), 400

    # 启动就绪性自检(立规则 31:必须在 _qa_task_lock 之前)
    ok, errors = _qa_readiness_check()
    if not ok:
        try:
            db.log_operation_event(
                event_type="qa_readiness_check_failed",
                module="api_server", severity="error",
                payload={"errors": errors},
            )
        except Exception:
            pass
        return jsonify({"success": False, "error": "启动自检失败",
                        "details": errors}), 400

    # 抢锁并启动后台线程
    with _qa_task_lock:
        if _qa_task["running"]:
            return jsonify({
                "success": False,
                "error": "另一个问答正在进行,请等待或先 /cancel"
            }), 409
        _qa_task["running"] = True
        _qa_task["started_at"] = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
        _qa_task["cancel_requested"] = False
        _qa_task["result"] = None
        _qa_task["error"] = None
        # 重置进度
        _qa_task["progress"] = {
            "total_kps": 5,
            "processed_kps": 0,
            "current_step": "starting",
            "message": "正在启动...",
            "ai_calls_count": 0,
            "cost_estimate_cny": 0.0,
        }

    # 埋点:启动事件
    try:
        db.log_operation_event(
            event_type="qa_ask_start", module="api_server", severity="info",
            payload={"query_preview": query[:200], "mode": mode,
                     "is_test_query": is_test},
        )
    except Exception:
        pass

    def _worker():
        try:
            from scripts.qa_assistant import run_qa
            from scripts.deepseek_client import DeepSeekClient
            client = DeepSeekClient()
            result = run_qa(
                db, client, query,
                mode=mode, is_test_query=is_test,
                progress_callback=_qa_task_update_progress,
                cancel_check=_qa_cancel_check,
            )
            with _qa_task_lock:
                _qa_task["result"] = result
                _qa_task["error"] = None
        except Exception as e:
            traceback.print_exc()
            with _qa_task_lock:
                _qa_task["error"] = str(e)[:500]
                _qa_task["result"] = None
            try:
                db.log_operation_event(
                    event_type="qa_ask_failed", module="api_server",
                    severity="error",
                    payload={"error": str(e)[:500],
                             "query_preview": query[:200]},
                )
            except Exception:
                pass
        finally:
            with _qa_task_lock:
                _qa_task["running"] = False
                _qa_task["cancel_requested"] = False

    threading.Thread(target=_worker, daemon=True).start()
    return jsonify({
        "success": True,
        "status": "started",
        "message": "问答任务已启动,请通过 /api/qa/progress 轮询",
    }), 202


@app.route("/api/qa/cancel", methods=["POST"])
def qa_cancel():
    """请求取消正在执行的问答(协作式,引擎下一个 stage 检查)."""
    with _qa_task_lock:
        if not _qa_task["running"]:
            return jsonify({"success": False,
                            "error": "当前无问答任务"}), 409
        _qa_task["cancel_requested"] = True
    return jsonify({"success": True,
                    "message": "已发送取消请求,引擎将在下一个 stage 退出"})


@app.route("/api/qa/progress", methods=["GET"])
def qa_progress():
    """获取当前问答进度(前端 1-2 秒轮询)."""
    with _qa_task_lock:
        snap = {
            "running": _qa_task["running"],
            "started_at": _qa_task["started_at"],
            "cancel_requested": _qa_task["cancel_requested"],
            "progress": dict(_qa_task["progress"]),
            "result": _qa_task["result"],
            "error": _qa_task["error"],
        }
    return jsonify(snap)


@app.route("/api/qa/history", methods=["GET"])
def qa_history_list():
    """问答历史列表(分页 + 模式筛选 + test 过滤).

    Query:
      limit:        int  (默认 20)
      offset:       int  (默认 0)
      mode:         self | friend | (空)
      exclude_test: 0/1  (默认 0)
    """
    try:
        limit = int(request.args.get("limit") or 20)
        offset = int(request.args.get("offset") or 0)
    except (ValueError, TypeError):
        return jsonify({"success": False,
                        "error": "limit/offset 必须为整数"}), 400
    mode = request.args.get("mode")
    if mode not in ("self", "friend"):
        mode = None
    exclude_test = bool(int(request.args.get("exclude_test") or 0))

    try:
        rows = db.get_qa_history_list(
            limit=limit, offset=offset,
            mode=mode, exclude_test=exclude_test,
        )
    except Exception as e:
        traceback.print_exc()
        return jsonify({"success": False, "error": str(e)[:500]}), 500
    return jsonify({"success": True, "items": rows, "count": len(rows)})


@app.route("/api/qa/history/<int:hid>", methods=["GET"])
def qa_history_detail(hid):
    """获取单条问答详情(含 4 板块解析后的完整 answer + 反馈聚合)."""
    try:
        # 复用 list 方法但传 limit=1, offset 强校验
        # db 没有 get_qa_history_by_id, 用 list + filter 兜底
        all_rows = db.get_qa_history_list(limit=10000, offset=0)
        target = None
        for r in all_rows:
            if r.get("id") == hid:
                target = r
                break
        if not target:
            return jsonify({"success": False,
                            "error": "history_id %d 不存在" % hid}), 404
        # 附带本条反馈(从 qa_feedback 表查)
        conn = db.get_connection(); c = conn.cursor()
        c.execute("""SELECT id, feedback_type, comment, created_at
                       FROM qa_feedback
                      WHERE qa_history_id=?
                      ORDER BY created_at DESC""", (hid,))
        fb = [dict(r) for r in c.fetchall()]
        conn.close()
        target["feedbacks"] = fb
        return jsonify({"success": True, "item": target})
    except Exception as e:
        traceback.print_exc()
        return jsonify({"success": False, "error": str(e)[:500]}), 500


@app.route("/api/qa/feedback", methods=["POST"])
def qa_feedback():
    """提交反馈(👍/👎/💬).

    Body JSON:
      qa_history_id: int    必填
      feedback_type: 'helpful' | 'not_helpful' | 'comment'   必填
      comment:       str    可选(comment 类型时建议非空)
    """
    try:
        body = request.get_json(silent=True) or {}
    except Exception:
        body = {}
    try:
        hid = int(body.get("qa_history_id"))
    except (TypeError, ValueError):
        return jsonify({"success": False,
                        "error": "qa_history_id 必填且为整数"}), 400
    ft = body.get("feedback_type")
    if ft not in ("helpful", "not_helpful", "comment"):
        return jsonify({
            "success": False,
            "error": "feedback_type 必须是 helpful/not_helpful/comment"
        }), 400
    comment = (body.get("comment") or "").strip()
    if ft == "comment" and not comment:
        return jsonify({"success": False,
                        "error": "comment 类型时 comment 字段必填"}), 400

    try:
        fid = db.save_qa_feedback(hid, ft, comment if comment else None)
        try:
            db.log_operation_event(
                event_type="qa_feedback_received", module="api_server",
                severity="info",
                payload={"qa_history_id": hid, "feedback_type": ft,
                         "feedback_id": fid,
                         "comment_preview": comment[:200]},
            )
        except Exception:
            pass
        return jsonify({"success": True, "feedback_id": fid})
    except Exception as e:
        traceback.print_exc()
        return jsonify({"success": False, "error": str(e)[:500]}), 500


@app.route("/api/qa/stats", methods=["GET"])
def qa_stats():
    """反馈 + 历史聚合统计(老唐用于自测、朋友试用、付费意愿验证看板)."""
    try:
        out = db.get_qa_stats()
        return jsonify({"success": True, **out})
    except Exception as e:
        traceback.print_exc()
        return jsonify({"success": False, "error": str(e)[:500]}), 500


# ================================================================
# 启动
# ================================================================
def _open(port):
    import time; time.sleep(1.5); webbrowser.open(f"http://localhost:{port}")

def main():
    p=PROJECT_ROOT/"config"/"settings.json"; port=5000
    if p.exists():
        with open(p,"r",encoding="utf-8") as f: port=json.load(f).get("flask_port",5000)
    print("="*60)
    print(f"  乡村振兴知识库 - 管理后台 v2.3.2-part3a")
    print(f"  Tab1 知识审核 | Tab2 系统管理 | Tab3 智能问答(后端 ready, 前端 part3b 启用)")
    print(f"  v2.3.2-part3a: F055 问答助手后端 7 路由 + _qa_task 槽 + readiness_check")
    print("="*60)
    print(f"  地址: http://localhost:{port}")
    print(f"  诊断: http://localhost:{port}/api/debug")
    print("-"*60)
    try:
        conn=db.get_connection();c=conn.cursor()
        c.execute("SELECT COUNT(*) FROM knowledge_points")
        print(f"  数据库正常, {c.fetchone()[0]} 条知识点"); conn.close()
    except Exception as e: print(f"  [WARN] DB: {e}")
    print("-"*60)
    threading.Thread(target=_open,args=(port,),daemon=True).start()
    app.run(host="127.0.0.1",port=port,debug=False)

if __name__=="__main__": main()
