#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
db_health_check.py - 数据库只读健康扫描(纯 PRAGMA + SELECT,零 AI 调用)
路径：scripts/db_health_check.py
版本：v2.3.6-part1
"""

import sys
import os
import json
import sqlite3
from datetime import datetime
from collections import defaultdict

# ===== UTF-8 stdout 强制(兼容 Windows chcp 65001) =====
try:
    sys.stdout.reconfigure(encoding='utf-8')
except Exception:
    pass

# ===== 路径常量 =====
SCRIPT_DIR = os.path.dirname(os.path.abspath(__file__))
PROJECT_DIR = os.path.dirname(SCRIPT_DIR)
DB_PATH = os.path.join(PROJECT_DIR, 'data', 'database', 'knowledge_base.db')
BACKUP_DIR = os.path.join(PROJECT_DIR, 'backups')
REPORT_PATH = os.path.join(PROJECT_DIR, 'db_health_check_report.txt')

# ===== 预期锚点 =====
EXPECTED_TABLES = [
    'source_files', 'knowledge_points', 'annotations',
    'operation_events', 'health_reports', 'polish_suggestions',
    # v2.3.0-part3 F062 三表（对话 3 决策 Q1 扩表清单）
    'api_endpoint_registry', 'e2e_test_reports', 'e2e_issues',
]
EXPECTED_F048_INDEXES = [
    'idx_health_created', 'idx_polish_report', 'idx_polish_status',
]
EXPECTED_BACKUP_OP_NAMES = [
    'reextract', 'dup_merge', 'dup_merge_batch',
    'full_rescan', 'batch_rerun', 'health_adopt',
]

# ===== 报告缓冲 + 告警收集器 =====
WARNINGS = []   # [(section, msg), ...]
LINES = []      # 所有输出行,最后写文件

def p(msg=''):
    print(msg)
    LINES.append(str(msg))

def warn(section, msg):
    WARNINGS.append((section, msg))

def header(title):
    p('')
    p('=' * 70)
    p(title)
    p('=' * 70)

def sub(title):
    p('')
    p('--- ' + title + ' ---')

def _has_table(conn, table):
    try:
        cur = conn.execute(
            "SELECT 1 FROM sqlite_master WHERE type='table' AND name=?",
            (table,)
        )
        return cur.fetchone() is not None
    except Exception:
        return False

def _has_col(conn, table, col):
    try:
        cur = conn.execute('PRAGMA table_info(' + table + ')')
        return any(row[1] == col for row in cur.fetchall())
    except Exception:
        return False

def _get_cols(conn, table):
    try:
        cur = conn.execute('PRAGMA table_info(' + table + ')')
        return [row[1] for row in cur.fetchall()]
    except Exception:
        return []


# =========================================================
# 主流程
# =========================================================

def main():
    header('乡村振兴知识库 - 数据体检报告')
    p('生成时间: ' + datetime.now().strftime('%Y-%m-%d %H:%M:%S'))
    p('数据库路径: ' + DB_PATH)

    if not os.path.exists(DB_PATH):
        p('')
        p('X 致命: 数据库文件不存在!')
        p('  请确认项目目录结构: 脚本应放在 {project}/scripts/ 下,')
        p('  数据库位于 {project}/data/database/knowledge_base.db')
        _write_report()
        return

    size_mb = os.path.getsize(DB_PATH) / 1024.0 / 1024.0
    p('数据库大小: ' + ('%.2f' % size_mb) + ' MB')

    conn = sqlite3.connect(DB_PATH)
    conn.row_factory = sqlite3.Row

    try:
        check_1_tables(conn)
        check_2_kp_basic(conn)
        check_3_qa_combo(conn)
        check_4_polish_suggestions(conn)
        check_5_health_reports(conn)
        check_6_annotations_orphan(conn)
        check_7_json_fields(conn)
        check_8_operation_events(conn)
        check_9_source_files(conn)
        check_10_backups()
        check_11_f048_code_contract(conn)
        check_12_f062_code_contract(conn)
    finally:
        conn.close()

    # ===== 总结 =====
    header('体检总结')
    if not WARNINGS:
        p('OK 全部 11 项体检通过,未发现异常。')
    else:
        p('!! 共发现 ' + str(len(WARNINGS)) + ' 项异常需关注:')
        for i, (sec, msg) in enumerate(WARNINGS, 1):
            p('  ' + str(i) + '. [' + sec + '] ' + msg)
        p('')
        p('说明: 告警(!!)不等于 bug。请把完整报告发给 Claude 做判定。')

    _write_report()
    p('')
    p('报告已保存到: ' + REPORT_PATH)


def _write_report():
    try:
        with open(REPORT_PATH, 'w', encoding='utf-8') as f:
            f.write('\n'.join(LINES))
    except Exception as e:
        print('!! 报告文件写入失败: ' + str(e))


# =========================================================
# [1/10] 数据库表清单对齐
# =========================================================

def check_1_tables(conn):
    header('[1/10] 数据库表清单对齐')
    try:
        cur = conn.execute(
            "SELECT name FROM sqlite_master WHERE type='table' "
            "AND name NOT LIKE 'sqlite_%' ORDER BY name"
        )
        tables = [r[0] for r in cur.fetchall()]
        p('实际业务表数量: ' + str(len(tables)))
        p('实际表清单:')
        for t in tables:
            p('  - ' + t)

        sub('关键表存在性检查')
        missing = []
        for t in EXPECTED_TABLES:
            if t in tables:
                p('  ' + t + ': OK')
            else:
                p('  ' + t + ': X 缺失')
                missing.append(t)
        if missing:
            warn('表清单', '缺失关键表: ' + ', '.join(missing))

        sub('F048 新增索引检查(v2.3.0-part2.1 应有)')
        cur = conn.execute(
            "SELECT name FROM sqlite_master WHERE type='index' "
            "AND name NOT LIKE 'sqlite_%'"
        )
        indexes = set(r[0] for r in cur.fetchall())
        idx_missing = []
        for idx in EXPECTED_F048_INDEXES:
            if idx in indexes:
                p('  ' + idx + ': OK')
            else:
                p('  ' + idx + ': X 缺失')
                idx_missing.append(idx)
        if idx_missing:
            warn('索引', '缺失 F048 索引: ' + ', '.join(idx_missing))

        sub('总数比对')
        if len(tables) >= 18:
            p('  OK 业务表数量 ' + str(len(tables)) + ' >= 18 (v2.3.0-part2.1 预期)')
        else:
            p('  !! 业务表数量 ' + str(len(tables)) + ' < 18')
            warn('表清单', '业务表数量 ' + str(len(tables)) + ' 少于预期 18 张')
    except Exception as e:
        p('X 执行失败: ' + str(e))
        warn('表清单', '执行失败: ' + str(e))


# =========================================================
# [2/10] knowledge_points 孤儿与异常
# =========================================================

def check_2_kp_basic(conn):
    header('[2/10] knowledge_points 孤儿与异常')
    try:
        total = conn.execute('SELECT COUNT(*) FROM knowledge_points').fetchone()[0]
        p('总条目数: ' + str(total))

        if total == 0:
            p('  !! 知识点表为空(是否新部署?)')
            return

        # 孤儿
        if _has_col(conn, 'knowledge_points', 'source_file_id'):
            n = conn.execute(
                'SELECT COUNT(*) FROM knowledge_points WHERE source_file_id IS NULL'
            ).fetchone()[0]
            p('')
            p('孤儿条目 (source_file_id IS NULL): ' + str(n) + ' 条')
            if n > 0:
                p('  注: 经验速记无 source_file_id 属正常,非经验速记的孤儿才可疑')
                cur = conn.execute(
                    'SELECT kp_id, content_type, title FROM knowledge_points '
                    'WHERE source_file_id IS NULL LIMIT 5'
                )
                for row in cur.fetchall():
                    title = (row[2] or '')[:40]
                    p('    kp_id=' + str(row[0]) + ', type=' + str(row[1]) + ', title=' + title)
                if _has_col(conn, 'knowledge_points', 'content_type'):
                    n_non_exp = conn.execute(
                        "SELECT COUNT(*) FROM knowledge_points "
                        "WHERE source_file_id IS NULL AND content_type != 'experience'"
                    ).fetchone()[0]
                    if n_non_exp > 0:
                        warn('kp孤儿', str(n_non_exp) + ' 条非经验速记的孤儿条目')

        # qa_score 范围
        if _has_col(conn, 'knowledge_points', 'qa_score'):
            n = conn.execute(
                'SELECT COUNT(*) FROM knowledge_points '
                'WHERE qa_score IS NOT NULL AND (qa_score < 0 OR qa_score > 5)'
            ).fetchone()[0]
            p('')
            p('qa_score 超出 [0, 5]: ' + str(n) + ' 条')
            if n > 0:
                warn('qa_score', str(n) + ' 条 qa_score 越界')

        # content_readiness 分布
        if _has_col(conn, 'knowledge_points', 'content_readiness'):
            valid = ('draft', 'quotable', 'premium')
            cur = conn.execute(
                'SELECT content_readiness, COUNT(*) FROM knowledge_points '
                'GROUP BY content_readiness'
            )
            p('')
            p('content_readiness 分布:')
            invalid_count = 0
            for row in cur.fetchall():
                val, cnt = row[0], row[1]
                if val is None or val in valid:
                    p('  ' + (str(val) if val else 'NULL') + ': ' + str(cnt) + ' 条')
                else:
                    p('  ' + repr(val) + ': ' + str(cnt) + ' 条 !! 异常值')
                    invalid_count += cnt
            if invalid_count > 0:
                warn('content_readiness', str(invalid_count) + ' 条非法就绪度值')

        # review_status 分布
        if _has_col(conn, 'knowledge_points', 'review_status'):
            cur = conn.execute(
                'SELECT review_status, COUNT(*) FROM knowledge_points '
                'GROUP BY review_status'
            )
            p('')
            p('review_status 分布:')
            for row in cur.fetchall():
                p('  ' + (str(row[0]) if row[0] else 'NULL') + ': ' + str(row[1]) + ' 条')
    except Exception as e:
        p('X 执行失败: ' + str(e))
        warn('kp异常', '执行失败: ' + str(e))


# =========================================================
# [3/10] qa_score / qa_source 组合合法性
# =========================================================

def check_3_qa_combo(conn):
    header('[3/10] qa_score / qa_source 组合合法性')
    try:
        if not (_has_col(conn, 'knowledge_points', 'qa_score') and
                _has_col(conn, 'knowledge_points', 'qa_source')):
            p('!! qa_score 或 qa_source 字段不存在,跳过')
            return

        total = conn.execute('SELECT COUNT(*) FROM knowledge_points').fetchone()[0]

        # qa_source 分布
        cur = conn.execute(
            'SELECT qa_source, COUNT(*) FROM knowledge_points GROUP BY qa_source'
        )
        p('qa_source 分布:')
        for row in cur.fetchall():
            p('  ' + (str(row[0]) if row[0] else 'NULL') + ': ' + str(row[1]) + ' 条')

        # 未质检
        n_unchecked = conn.execute(
            'SELECT COUNT(*) FROM knowledge_points WHERE qa_score = 0 OR qa_score IS NULL'
        ).fetchone()[0]
        p('')
        p('未质检条目 (qa_score=0 或 NULL): ' + str(n_unchecked) + ' 条')
        if n_unchecked > 0:
            p('  建议: 工具箱 > 质检补跑 (F061) 处理这些条目')
            warn('未质检', str(n_unchecked) + ' 条未质检,建议走 F061')

        # rule_fallback 但非 3 分
        n_rf_bad = conn.execute(
            "SELECT COUNT(*) FROM knowledge_points "
            "WHERE qa_source='rule_fallback' AND qa_score != 3"
        ).fetchone()[0]
        p('')
        p('qa_source=rule_fallback 但分数非 3: ' + str(n_rf_bad) + ' 条')
        if n_rf_bad > 0:
            p('  说明: F058 规则兜底默认分 3,非 3 值可能是人工编辑过(多为正常)')

        # qa_score>0 但 qa_source IS NULL
        n_null_src = conn.execute(
            'SELECT COUNT(*) FROM knowledge_points '
            'WHERE qa_score > 0 AND qa_source IS NULL'
        ).fetchone()[0]
        p('')
        p('qa_score>0 但 qa_source IS NULL: ' + str(n_null_src) + ' 条')
        if n_null_src > 0:
            warn('qa组合', str(n_null_src) + ' 条有分数但无来源标记')

        # 分段统计
        sub('qa_score 分段')
        segs = [
            (-0.5, 0.5, '0分/未质检'),
            (0.5, 2.5, '1-2分/低'),
            (2.5, 3.5, '3分/中'),
            (3.5, 5.5, '4-5分/高'),
        ]
        for lo, hi, label in segs:
            n = conn.execute(
                'SELECT COUNT(*) FROM knowledge_points WHERE qa_score > ? AND qa_score <= ?',
                (lo, hi)
            ).fetchone()[0]
            pct = (n * 100.0 / total) if total else 0
            p('  ' + label + ': ' + str(n) + ' 条 (' + ('%.1f' % pct) + '%)')
    except Exception as e:
        p('X 执行失败: ' + str(e))
        warn('qa组合', '执行失败: ' + str(e))


# =========================================================
# [4/10] polish_suggestions 状态合法性
# =========================================================

def check_4_polish_suggestions(conn):
    header('[4/10] polish_suggestions 状态合法性')
    try:
        if not _has_table(conn, 'polish_suggestions'):
            p('表不存在,跳过(F048 首次安装后默认会建表,若缺失即 bug)')
            warn('polish', 'polish_suggestions 表不存在')
            return

        total = conn.execute('SELECT COUNT(*) FROM polish_suggestions').fetchone()[0]
        p('总条目数: ' + str(total))

        if total == 0:
            p('  表为空(F048 体检未执行过或未产生建议,非 bug)')
            return

        for col, label in [('status', 'status'), ('tier', 'tier'), ('suggestion_type', 'suggestion_type')]:
            if _has_col(conn, 'polish_suggestions', col):
                cur = conn.execute(
                    'SELECT ' + col + ', COUNT(*) FROM polish_suggestions GROUP BY ' + col
                )
                p('')
                p(label + ' 分布:')
                for row in cur.fetchall():
                    p('  ' + (str(row[0]) if row[0] else 'NULL') + ': ' + str(row[1]) + ' 条')

        sub('契约违规组合检查')

        # L3_manual AND status=applied
        n = conn.execute(
            "SELECT COUNT(*) FROM polish_suggestions "
            "WHERE tier='L3_manual' AND status='applied'"
        ).fetchone()[0]
        p('  L3_manual AND status=applied (契约: L3 不应可采纳): ' + str(n) + ' 条')
        if n > 0:
            warn('polish违规', str(n) + ' 条 L3 建议被标 applied')

        # L3_manual AND suggestion_type != manual_review
        n = conn.execute(
            "SELECT COUNT(*) FROM polish_suggestions "
            "WHERE tier='L3_manual' AND suggestion_type != 'manual_review'"
        ).fetchone()[0]
        p('  L3_manual AND suggestion_type != manual_review: ' + str(n) + ' 条')
        if n > 0:
            warn('polish违规', str(n) + ' 条 L3 的 suggestion_type 错误')

        # drop AND suggested_content 非空
        n = conn.execute(
            "SELECT COUNT(*) FROM polish_suggestions "
            "WHERE suggestion_type='drop' AND suggested_content IS NOT NULL "
            "AND suggested_content != '' AND suggested_content != 'null'"
        ).fetchone()[0]
        p('  drop AND suggested_content 非空 (契约要求空): ' + str(n) + ' 条')
        if n > 0:
            warn('polish违规', str(n) + ' 条 drop 建议含 suggested_content')

        # applied AND applied_at IS NULL
        n = conn.execute(
            "SELECT COUNT(*) FROM polish_suggestions "
            "WHERE status='applied' AND applied_at IS NULL"
        ).fetchone()[0]
        p('  status=applied 但 applied_at IS NULL: ' + str(n) + ' 条')
        if n > 0:
            warn('polish违规', str(n) + ' 条已采纳但无时间戳')

        # 老 pending
        n = conn.execute(
            "SELECT COUNT(*) FROM polish_suggestions WHERE status='pending' "
            "AND julianday('now') - julianday(created_at) > 30"
        ).fetchone()[0]
        p('  status=pending 超过 30 天: ' + str(n) + ' 条 (非 bug,Review 积压提示)')
    except Exception as e:
        p('X 执行失败: ' + str(e))
        warn('polish异常', '执行失败: ' + str(e))


# =========================================================
# [5/10] health_reports 僵尸任务
# =========================================================

def check_5_health_reports(conn):
    header('[5/10] health_reports 僵尸任务')
    try:
        if not _has_table(conn, 'health_reports'):
            p('表不存在,跳过')
            warn('health', 'health_reports 表不存在')
            return

        total = conn.execute('SELECT COUNT(*) FROM health_reports').fetchone()[0]
        p('总报告数: ' + str(total))

        if total == 0:
            p('  表为空(未执行过体检,非 bug)')
            return

        cur = conn.execute(
            'SELECT status, COUNT(*) FROM health_reports GROUP BY status'
        )
        p('')
        p('status 分布:')
        for row in cur.fetchall():
            p('  ' + (str(row[0]) if row[0] else 'NULL') + ': ' + str(row[1]) + ' 条')

        # 僵尸(>2 小时)
        n = conn.execute(
            "SELECT COUNT(*) FROM health_reports WHERE status='running' "
            "AND julianday('now') - julianday(created_at) > 0.0833"
        ).fetchone()[0]
        p('')
        p('status=running 超 2 小时(僵尸任务): ' + str(n) + ' 条')
        if n > 0:
            warn('health僵尸', str(n) + ' 条 running 超 2 小时')
            cur = conn.execute(
                "SELECT report_id, created_at FROM health_reports "
                "WHERE status='running' AND julianday('now') - julianday(created_at) > 0.0833"
            )
            for row in cur.fetchall():
                p('    report_id=' + str(row[0]) + ', created_at=' + str(row[1]))

        # completed 缺 total_score
        n = conn.execute(
            "SELECT COUNT(*) FROM health_reports "
            "WHERE status='completed' AND total_score IS NULL"
        ).fetchone()[0]
        p('status=completed 但 total_score 为空: ' + str(n) + ' 条')
        if n > 0:
            warn('health异常', str(n) + ' 条 completed 缺 total_score')

        # failed 缺 error_message
        n = conn.execute(
            "SELECT COUNT(*) FROM health_reports WHERE status='failed' "
            "AND (error_message IS NULL OR error_message='')"
        ).fetchone()[0]
        p('status=failed 但 error_message 为空: ' + str(n) + ' 条')
        if n > 0:
            warn('health异常', str(n) + ' 条 failed 缺 error_message')
    except Exception as e:
        p('X 执行失败: ' + str(e))
        warn('health异常', '执行失败: ' + str(e))


# =========================================================
# [6/10] annotations 孤儿
# =========================================================

def check_6_annotations_orphan(conn):
    header('[6/10] annotations 孤儿(删除级联失败证据)')
    try:
        if not _has_table(conn, 'annotations'):
            p('表不存在,跳过')
            return

        total = conn.execute('SELECT COUNT(*) FROM annotations').fetchone()[0]
        p('注解总数: ' + str(total))

        if total == 0:
            p('  表为空')
            return

        cols = _get_cols(conn, 'annotations')

        # 孤儿
        n = conn.execute('''
            SELECT COUNT(*) FROM annotations a
            LEFT JOIN knowledge_points kp ON a.kp_id = kp.kp_id
            WHERE kp.kp_id IS NULL
        ''').fetchone()[0]
        p('孤儿注解 (kp_id 对应 kp 已不存在): ' + str(n) + ' 条')
        if n > 0:
            warn('annotations孤儿', str(n) + ' 条孤儿注解 (删除级联失败证据)')
            # 尝试抓前 5 条详情
            type_col = 'annotation_type' if 'annotation_type' in cols else ''
            pk_col = 'annotation_id' if 'annotation_id' in cols else ('id' if 'id' in cols else None)
            select_fields = []
            if pk_col:
                select_fields.append('a.' + pk_col)
            select_fields.append('a.kp_id')
            if type_col:
                select_fields.append('a.' + type_col)

            sql = ('SELECT ' + ', '.join(select_fields) +
                   ' FROM annotations a LEFT JOIN knowledge_points kp ON a.kp_id = kp.kp_id '
                   'WHERE kp.kp_id IS NULL LIMIT 5')
            cur = conn.execute(sql)
            for row in cur.fetchall():
                p('    ' + ' / '.join(str(v) for v in row))
    except Exception as e:
        p('X 执行失败: ' + str(e))
        warn('annotations', '执行失败: ' + str(e))


# =========================================================
# [7/10] JSON 字段格式异常(抽样)
# =========================================================

def check_7_json_fields(conn):
    header('[7/10] JSON 字段格式异常(每字段抽样最多 200 条)')
    try:
        candidates = [
            ('knowledge_points', 'ai_extracted_content', 'kp_id'),
            ('knowledge_points', 'practical_insights', 'kp_id'),
            ('knowledge_points', 'final_category_tags', 'kp_id'),
            ('knowledge_points', 'final_attribute_tags', 'kp_id'),
            ('knowledge_points', 'final_keywords', 'kp_id'),
            ('polish_suggestions', 'original_content', 'suggestion_id'),
            ('polish_suggestions', 'suggested_content', 'suggestion_id'),
            ('health_reports', 'full_report_json', 'report_id'),
        ]
        total_bad = 0
        for table, col, pk in candidates:
            if not _has_table(conn, table):
                continue
            if not _has_col(conn, table, col):
                continue
            cur = conn.execute(
                'SELECT ' + pk + ', ' + col + ' FROM ' + table +
                ' WHERE ' + col + ' IS NOT NULL AND ' + col + ' != "" LIMIT 200'
            )
            bad = []
            checked = 0
            for row in cur.fetchall():
                checked += 1
                val = row[1]
                try:
                    json.loads(val)
                except Exception:
                    bad.append(row[0])
            status = 'OK' if not bad else '!!'
            p('  ' + status + ' ' + table + '.' + col + ': 抽样 ' + str(checked) +
              ' 条, ' + str(len(bad)) + ' 条解析失败')
            if bad:
                sample = bad[:5]
                p('     失败 ' + pk + ' 前 5 个: ' + str(sample))
                total_bad += len(bad)

        if total_bad > 0:
            warn('JSON格式', '抽样共 ' + str(total_bad) + ' 条 JSON 字段解析失败')
    except Exception as e:
        p('X 执行失败: ' + str(e))
        warn('JSON格式', '执行失败: ' + str(e))


# =========================================================
# [8/10] operation_events 错误事件汇总(近 30 天)
# =========================================================

def check_8_operation_events(conn):
    header('[8/10] operation_events 错误事件汇总(近 30 天)')
    try:
        if not _has_table(conn, 'operation_events'):
            p('表不存在,跳过')
            return

        total = conn.execute('SELECT COUNT(*) FROM operation_events').fetchone()[0]
        p('事件总数: ' + str(total))

        if total == 0:
            p('  表为空')
            return

        # 近 30 天 severity 分布
        cur = conn.execute('''
            SELECT severity, COUNT(*) FROM operation_events
            WHERE julianday('now') - julianday(created_at) <= 30
            GROUP BY severity
        ''')
        p('')
        p('近 30 天 severity 分布:')
        err_count = 0
        for row in cur.fetchall():
            sev, cnt = row[0], row[1]
            p('  ' + (str(sev) if sev else 'NULL') + ': ' + str(cnt) + ' 条')
            if sev == 'error':
                err_count = cnt

        if err_count > 0:
            warn('events-error', '近 30 天 ' + str(err_count) + ' 条 error 事件')

        # Top 10 error/warn
        sub('近 30 天 error/warn 事件 Top 10')
        cur = conn.execute('''
            SELECT event_type, severity, COUNT(*) as n FROM operation_events
            WHERE julianday('now') - julianday(created_at) <= 30
              AND severity IN ('error', 'warn')
            GROUP BY event_type, severity
            ORDER BY n DESC LIMIT 10
        ''')
        rows = cur.fetchall()
        if rows:
            for row in rows:
                p('  [' + str(row[1]) + '] ' + str(row[0]) + ': ' + str(row[2]) + ' 次')
        else:
            p('  无 error/warn 事件')

        # 最近 5 条 error 详情
        if err_count > 0:
            sub('最近 5 条 error 事件详情')
            cur = conn.execute('''
                SELECT created_at, event_type, payload_json FROM operation_events
                WHERE severity='error'
                ORDER BY created_at DESC LIMIT 5
            ''')
            for row in cur.fetchall():
                payload = row[2] or ''
                if len(payload) > 200:
                    payload = payload[:200] + '...'
                p('  ' + str(row[0]) + ' | ' + str(row[1]))
                p('    payload: ' + payload)
    except Exception as e:
        p('X 执行失败: ' + str(e))
        warn('events', '执行失败: ' + str(e))


# =========================================================
# [9/10] source_files 状态一致性
# =========================================================

def check_9_source_files(conn):
    header('[9/10] source_files 状态一致性')
    try:
        if not _has_table(conn, 'source_files'):
            p('表不存在,跳过')
            warn('source_files', 'source_files 表不存在')
            return

        cols = _get_cols(conn, 'source_files')
        total = conn.execute('SELECT COUNT(*) FROM source_files').fetchone()[0]
        p('总文件数: ' + str(total))

        if total == 0:
            p('  表为空')
            return

        if 'status' in cols:
            cur = conn.execute('SELECT status, COUNT(*) FROM source_files GROUP BY status')
            p('')
            p('status 分布:')
            for row in cur.fetchall():
                p('  ' + (str(row[0]) if row[0] else 'NULL') + ': ' + str(row[1]) + ' 条')

        # 探测主键字段
        pk = None
        for c in ['file_id', 'id']:
            if c in cols:
                pk = c
                break

        # completed 但无 kp
        if pk and 'status' in cols and _has_col(conn, 'knowledge_points', 'source_file_id'):
            sql = (
                'SELECT sf.' + pk + ' FROM source_files sf '
                'LEFT JOIN knowledge_points kp ON kp.source_file_id = sf.' + pk + ' '
                "WHERE sf.status = 'completed' "
                'GROUP BY sf.' + pk + ' '
                'HAVING COUNT(kp.kp_id) = 0'
            )
            cur = conn.execute(sql)
            empty = [r[0] for r in cur.fetchall()]
            p('')
            p('status=completed 但无对应 kp: ' + str(len(empty)) + ' 个')
            if empty:
                p('  详情(前 5 个 ' + pk + '): ' + str(empty[:5]))
                warn('source_files', str(len(empty)) + ' 个 completed 但无 kp')

        # 截断补救统计
        if 'truncation_count' in cols:
            n = conn.execute(
                'SELECT COUNT(*) FROM source_files WHERE truncation_count > 0'
            ).fetchone()[0]
            p('')
            p('历史触发过 F057 截断补救的文件: ' + str(n) + ' 个')

        # 最近 5 个 failed
        if 'status' in cols:
            cur = conn.execute(
                "SELECT * FROM source_files WHERE status='failed' ORDER BY rowid DESC LIMIT 5"
            )
            rows = cur.fetchall()
            if rows:
                p('')
                p('最近 5 个 status=failed 的文件:')
                for row in rows:
                    d = dict(row)
                    name = (d.get('file_name') or d.get('original_name') or
                            d.get('stem') or d.get('name') or '(?)')
                    p('  ' + str(name))
    except Exception as e:
        p('X 执行失败: ' + str(e))
        warn('source_files', '执行失败: ' + str(e))


# =========================================================
# [10/10] 备份目录健康度
# =========================================================

def check_10_backups():
    header('[10/10] 备份目录健康度')
    try:
        if not os.path.isdir(BACKUP_DIR):
            p('X 备份目录不存在: ' + BACKUP_DIR)
            p('  说明: backup_manager 首次 operation_hook 触发时会自动创建')
            p('        若从未用过 6 个备份触发点,目录不存在属正常')
            warn('备份', '备份目录不存在(若从未用过备份触发点则非 bug)')
            return

        files = []
        for fn in os.listdir(BACKUP_DIR):
            path = os.path.join(BACKUP_DIR, fn)
            if os.path.isfile(path) and fn.endswith('.db'):
                files.append((fn, os.path.getsize(path), os.path.getmtime(path)))

        p('备份文件数: ' + str(len(files)))
        if not files:
            p('  !! 备份目录为空(未触发过 operation_hook)')
            return

        total_size = sum(f[1] for f in files)
        p('总大小: ' + ('%.2f' % (total_size / 1024.0 / 1024.0)) + ' MB')
        if total_size > 2 * 1024 * 1024 * 1024:
            warn('备份', '备份总大小超 2GB 上限')

        # 按 op_name 分组
        groups = defaultdict(list)
        for fn, size, mtime in files:
            stem = fn[:-3] if fn.endswith('.db') else fn
            parts = stem.split('_')
            # 格式: backup_YYYYMMDD_HHMMSS_op_name
            if len(parts) >= 4 and parts[0] == 'backup':
                op_name = '_'.join(parts[3:])
            else:
                op_name = '(unknown)'
            groups[op_name].append((fn, size, mtime))

        p('')
        p('按 op_name 分组:')
        for op in sorted(groups.keys()):
            items = sorted(groups[op], key=lambda x: x[2], reverse=True)
            latest = datetime.fromtimestamp(items[0][2]).strftime('%Y-%m-%d %H:%M')
            cnt = len(items)
            flag = ''
            if cnt > 5:
                flag = ' !! 超出 OP_KEEP_PER_NAME=5'
                warn('备份', 'op_name=' + op + ' 保留 ' + str(cnt) + ' 个超 5 上限')
            p('  ' + op + ': ' + str(cnt) + ' 个, 最新 ' + latest + flag)

        sub('6 个预期 op_name 触发点曾触发情况')
        for op in EXPECTED_BACKUP_OP_NAMES:
            if op in groups:
                p('  ' + op + ': OK 已触发过')
            else:
                p('  ' + op + ': -- 未触发过(非 bug,仅提示未使用该功能)')
    except Exception as e:
        p('X 执行失败: ' + str(e))
        warn('备份', '执行失败: ' + str(e))


# =========================================================
# [11/11] F048 代码层契约一致性（v2.3.0-part2.2 对话 B 新增）
# =========================================================

F048_PROMPTS = [
    'HEALTH_DIAGNOSIS_PROMPT',
    'HEALTH_POLISH_PROMPT',
    'HEALTH_POLISH_VERIFY_PROMPT',
    'HEALTH_POLISH_CONSERVATIVE_PROMPT',
    'HEALTH_ISLAND_JUDGE_PROMPT',
    'HEALTH_MONETIZE_REPORT_PROMPT',
]

def check_11_f048_code_contract(conn):
    header('[11/11] F048 代码层契约一致性(v2.3.0-part2.2)')
    try:
        # 修 sys.path 让脚本能 import scripts.*
        try:
            pr = os.path.abspath(os.path.join(SCRIPT_DIR, '..'))
            if pr not in sys.path:
                sys.path.insert(0, pr)
        except Exception:
            pass

        # ---- [11.1] 6 个 Prompt 顶层可 import（对话 A 缺陷 1）----
        sub('11.1 6 个 F048 Prompt 顶层 import 测试')
        try:
            from scripts.prompts import prompt_templates as pt
            p('  OK scripts.prompts.prompt_templates 模块可 import')
        except Exception as e:
            p('  X prompt_templates import 失败: ' + str(e))
            warn('F048 Prompt', 'prompt_templates 模块 import 失败(对话 A 缺陷 1)')
            return

        missing = []
        non_dict = []
        prompt_objs = {}
        for name in F048_PROMPTS:
            obj = getattr(pt, name, None)
            if obj is None:
                missing.append(name)
            elif not isinstance(obj, dict):
                non_dict.append(name + '(' + type(obj).__name__ + ')')
            else:
                prompt_objs[name] = obj
                p('  OK ' + name + ' 已定义为 dict')

        if missing:
            p('  X 缺失(为 None): ' + ', '.join(missing))
            warn('F048 Prompt', '缺失 Prompt: ' + ', '.join(missing) + ' (对话 A 缺陷 1/2)')
        if non_dict:
            p('  X 非 dict: ' + ', '.join(non_dict))
            warn('F048 Prompt', '非 dict: ' + ', '.join(non_dict))

        # ---- [11.2] 每 Prompt dict 含 system_prompt / user_prompt_template 非空（对话 A 缺陷 4）----
        sub('11.2 Prompt dict 含非空 system_prompt / user_prompt_template')
        bad_keys = []
        for name, obj in prompt_objs.items():
            sys_p = obj.get('system_prompt')
            usr_p = obj.get('user_prompt_template')
            row_bad = []
            if not sys_p or not isinstance(sys_p, str):
                row_bad.append('system_prompt')
            if not usr_p or not isinstance(usr_p, str):
                row_bad.append('user_prompt_template')
            if row_bad:
                bad_keys.append(name + '(' + ','.join(row_bad) + ')')
                p('  X ' + name + ' 缺: ' + ', '.join(row_bad))
            else:
                p('  OK ' + name + ' key 完整')
        if bad_keys:
            warn('F048 Prompt key',
                 '错配(对话 A 缺陷 4 ["system"]→["system_prompt"]): ' +
                 ', '.join(bad_keys))

        # ---- [11.3] PROMPT_VERSION 常量校验 ----
        sub('11.3 PROMPT_VERSION 常量')
        pv = getattr(pt, 'PROMPT_VERSION', None)
        if pv:
            p('  PROMPT_VERSION = ' + str(pv))
            if 'v2.3.0-part2.2' not in str(pv):
                p('  !! 建议 PROMPT_VERSION 升到 v2.3.0-part2.2(对话 A 已升,若为旧值说明代码未替换)')
                warn('F048 Prompt', 'PROMPT_VERSION=' + str(pv) + ' 可能是旧版本')
        else:
            p('  !! PROMPT_VERSION 常量未定义')
            warn('F048 Prompt', 'PROMPT_VERSION 常量未定义')

        # ---- [11.4] health_checker 顶层可 import（对话 A 已修复）----
        sub('11.4 health_checker 顶层 import 测试（对话 A import 顶层化修复）')
        try:
            from scripts import health_checker as hc
            p('  OK scripts.health_checker 可 import')
            # 检查关键常量/类
            if hasattr(hc, 'HealthChecker'):
                p('  OK HealthChecker 类存在')
            else:
                p('  X HealthChecker 类不存在')
                warn('F048 引擎', 'health_checker 缺 HealthChecker 类')
            if hasattr(hc, 'run_health_check'):
                p('  OK run_health_check 模块级函数存在')
            else:
                p('  !! run_health_check 模块级函数不存在(非致命)')
        except Exception as e:
            p('  X health_checker import 失败: ' + str(e))
            warn('F048 引擎', 'health_checker import 失败: ' + str(e))

        # ---- [11.5] db.get_kp_for_health_scan 返回值含 category/subcategory（对话 B 契约）----
        sub('11.5 db_manager.get_kp_for_health_scan 字段契约（对话 B 新增）')
        try:
            from scripts.db_manager import DatabaseManager
            dbm = DatabaseManager(DB_PATH)
            sample = dbm.get_kp_for_health_scan(include_annotations=False)
            if not sample:
                p('  -- 知识库为空,跳过字段契约验证（非 bug）')
            else:
                first = sample[0]
                missing_fields = []
                for f in ('category', 'subcategory'):
                    if f not in first:
                        missing_fields.append(f)
                if missing_fields:
                    p('  X 缺字段: ' + ', '.join(missing_fields))
                    warn('F048 字段契约',
                         'get_kp_for_health_scan 返回缺字段 ' + ','.join(missing_fields) +
                         '(对话 B LEFT JOIN categories 未落地)')
                else:
                    cat_val = first.get('category')
                    sub_val = first.get('subcategory')
                    p('  OK category / subcategory 字段均存在')
                    p('    首条 kp_id=' + str(first.get('kp_id')) +
                      ', category=' + (str(cat_val) if cat_val else 'None(未分类)') +
                      ', subcategory=' + (str(sub_val) if sub_val else 'None(未分类)'))
                    # 未分类比例
                    total = len(sample)
                    uncat = sum(1 for r in sample if not r.get('category'))
                    if uncat > 0:
                        pct = uncat * 100.0 / total
                        p('    未分类 kp: ' + str(uncat) + '/' + str(total) +
                          ' (' + ('%.1f' % pct) + '%)')
                        if pct > 30:
                            p('    !! 未分类比例偏高,维度②结构分会偏低,建议先分类')
        except Exception as e:
            p('  X 执行失败: ' + str(e))
            warn('F048 字段契约', '执行失败: ' + str(e))
    except Exception as e:
        p('X 整项执行失败: ' + str(e))
        warn('F048 整项', '执行失败: ' + str(e))


# =========================================================
# [12/12] F062 端到端测试 代码层契约一致性（v2.3.0-part3 对话 3/3 新增）
# =========================================================

F062_DB_METHODS = [
    'register_endpoint', 'get_endpoint_registry', 'update_endpoint_last_tested',
    'save_e2e_test_report', 'get_latest_e2e_test_report',
    'get_e2e_test_report_detail', 'get_e2e_test_report_list',
    'upsert_e2e_issue', 'set_e2e_issue_status',
]

def check_12_f062_code_contract(conn):
    header('[12/12] F062 端到端测试 代码层契约一致性(v2.3.0-part3)')
    try:
        # 修 sys.path
        try:
            pr = os.path.abspath(os.path.join(SCRIPT_DIR, '..'))
            if pr not in sys.path:
                sys.path.insert(0, pr)
        except Exception:
            pass

        # ---- [12.1] E2E_RESPONSE_JUDGE_PROMPT 顶层 import + 类型 ----
        sub('12.1 E2E_RESPONSE_JUDGE_PROMPT 顶层 import 测试')
        try:
            from scripts.prompts import prompt_templates as pt
            p('  OK prompt_templates 模块可 import')
        except Exception as e:
            p('  X prompt_templates import 失败: ' + str(e))
            warn('F062 Prompt', 'prompt_templates import 失败: ' + str(e))
            return

        e2e_p = getattr(pt, 'E2E_RESPONSE_JUDGE_PROMPT', None)
        if e2e_p is None:
            p('  X E2E_RESPONSE_JUDGE_PROMPT 未定义或为 None')
            warn('F062 Prompt', 'E2E_RESPONSE_JUDGE_PROMPT 未定义')
        elif not isinstance(e2e_p, dict):
            p('  X E2E_RESPONSE_JUDGE_PROMPT 不是 dict (' + type(e2e_p).__name__ + ')')
            warn('F062 Prompt', 'E2E_RESPONSE_JUDGE_PROMPT 类型错')
        else:
            p('  OK E2E_RESPONSE_JUDGE_PROMPT 已定义为 dict')
            # [12.2] 双 key
            sub('12.2 双 key (system_prompt / user_prompt_template) 非空')
            sys_p = e2e_p.get('system_prompt')
            usr_p = e2e_p.get('user_prompt_template')
            if not sys_p or not isinstance(sys_p, str):
                p('  X 缺 system_prompt 或为空')
                warn('F062 Prompt key', 'E2E_RESPONSE_JUDGE_PROMPT 缺 system_prompt')
            else:
                p('  OK system_prompt 非空,长度 ' + str(len(sys_p)))
            if not usr_p or not isinstance(usr_p, str):
                p('  X 缺 user_prompt_template 或为空')
                warn('F062 Prompt key', 'E2E_RESPONSE_JUDGE_PROMPT 缺 user_prompt_template')
            else:
                p('  OK user_prompt_template 非空,长度 ' + str(len(usr_p)))

        # ---- [12.3] static_analyzer 顶层 import + 4 方法 ----
        sub('12.3 static_analyzer 顶层 import + 4 方法齐全')
        try:
            from scripts import static_analyzer as sa
            required_sa = ('scan_prompt_call_consistency', 'scan_field_contract',
                           'scan_code_smells', 'run_static_scan')
            miss_sa = [m for m in required_sa if not hasattr(sa, m)]
            if miss_sa:
                p('  X static_analyzer 缺方法: ' + ', '.join(miss_sa))
                warn('F062 static_analyzer', '缺方法: ' + ','.join(miss_sa))
            else:
                p('  OK static_analyzer 4 方法齐全')
        except Exception as e:
            p('  X static_analyzer import 失败: ' + str(e))
            warn('F062 static_analyzer', 'import 失败: ' + str(e))

        # ---- [12.4] e2e_tester 顶层 import + 类 + 便捷函数 ----
        sub('12.4 e2e_tester 顶层 import + E2ETester 类 + run_e2e_scan 便捷函数')
        try:
            from scripts import e2e_tester as et
            if not hasattr(et, 'E2ETester'):
                p('  X e2e_tester 缺 E2ETester 类')
                warn('F062 e2e_tester', '缺 E2ETester 类')
            else:
                p('  OK E2ETester 类就绪')
            if not hasattr(et, 'run_e2e_scan'):
                p('  X e2e_tester 缺 run_e2e_scan 便捷函数')
                warn('F062 e2e_tester', '缺 run_e2e_scan')
            else:
                p('  OK run_e2e_scan 便捷函数就绪')
            # VALID_STAGES 白名单
            vs = getattr(et, 'VALID_STAGES', None)
            if vs:
                p('  VALID_STAGES 共 ' + str(len(vs)) + ' 种: ' + str(sorted(list(vs))))
            else:
                p('  !! VALID_STAGES 常量未定义')
        except Exception as e:
            p('  X e2e_tester import 失败: ' + str(e))
            warn('F062 e2e_tester', 'import 失败: ' + str(e))

        # ---- [12.5] db_manager 9 个 F062 方法 ----
        sub('12.5 db_manager 9 个 F062 方法齐全')
        try:
            from scripts.db_manager import DatabaseManager
            miss_db = [m for m in F062_DB_METHODS if not hasattr(DatabaseManager, m)]
            if miss_db:
                p('  X db_manager 缺方法: ' + ', '.join(miss_db))
                warn('F062 db_manager', '缺方法: ' + ','.join(miss_db))
            else:
                p('  OK DatabaseManager 9 F062 方法全部就绪')
                for m in F062_DB_METHODS:
                    p('    OK ' + m)
        except Exception as e:
            p('  X DatabaseManager 类 import 失败: ' + str(e))
            warn('F062 db_manager', 'import 失败: ' + str(e))

        # ---- [12.6] 3 张 F062 表存在 + 样本计数 ----
        sub('12.6 F062 三张表存在 + 样本计数')
        c = conn.cursor()
        for t in ('api_endpoint_registry', 'e2e_test_reports', 'e2e_issues'):
            try:
                c.execute('SELECT COUNT(*) FROM ' + t)
                cnt = c.fetchone()[0]
                p('  OK ' + t + ' 存在 (' + str(cnt) + ' 行)')
            except Exception as e:
                p('  X ' + t + ' 缺失或查询失败: ' + str(e))
                warn('F062 表', t + ' 缺失')

    except Exception as e:
        p('X 整项执行失败: ' + str(e))
        warn('F062 整项', '执行失败: ' + str(e))


# =========================================================

if __name__ == '__main__':
    main()
