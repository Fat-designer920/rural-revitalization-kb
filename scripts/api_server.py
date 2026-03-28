"""
api_server.py - Flask API + 审核界面
路径：scripts/api_server.py
版本：v2.1.0-d - 保鲜提醒(续期/批量续期/标记过时/摘要/筛选)
"""
import os,sys,json,re,traceback,webbrowser,threading
from pathlib import Path
from datetime import datetime, timedelta
PROJECT_ROOT = Path(__file__).parent.parent
sys.path.insert(0, str(PROJECT_ROOT))
from flask import Flask, request, jsonify, Response
from flask_cors import CORS
from scripts.db_manager import DatabaseManager

app = Flask(__name__)
CORS(app)
db = DatabaseManager()
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
              "suggested_keywords","final_keywords","qa_flags"]:
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
        r = db.get_all_knowledge_points(
            review_status=request.args.get("status"), content_type=request.args.get("type"),
            category_id=request.args.get("category",None,type=int),
            level1_code=request.args.get("level1",None),
            search_query=request.args.get("search",None),
            content_readiness=request.args.get("readiness",None),
            freshness_filter=freshness_filter,
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
@app.route("/api/knowledge-points/batch-confirm", methods=["POST"])
def batch_confirm():
    try:
        ids = (request.get_json() or {}).get("ids",[])
        n = 0
        for kid in ids:
            try:
                kp = db.get_knowledge_point(kid)
                if kp and kp["review_status"]=="pending":
                    db.confirm_knowledge_point(kid, kp.get("suggested_category_id")); n+=1
            except: pass
        return jsonify({"success":True,"confirmed":n})
    except Exception as e: traceback.print_exc(); return jsonify({"error":str(e)}),500

# v2.0.0 新增
@app.route("/api/knowledge-points/batch-ignore", methods=["POST"])
def batch_ignore():
    try:
        ids = (request.get_json() or {}).get("ids",[])
        n = 0
        for kid in ids:
            try:
                kp = db.get_knowledge_point(kid)
                if kp and kp["review_status"] in ("pending","confirmed"):
                    if kp["review_status"] == "confirmed":
                        db.add_edit_history(kid, {"review_status":{"old":"confirmed","new":"ignored"}}, "批量移除")
                    db.ignore_knowledge_point(kid, "批量忽略"); n+=1
            except: pass
        return jsonify({"success":True,"ignored":n})
    except Exception as e: traceback.print_exc(); return jsonify({"error":str(e)}),500

# v2.0.0 新增
@app.route("/api/knowledge-points/batch-delete", methods=["POST"])
def batch_delete():
    try:
        ids = (request.get_json() or {}).get("ids",[])
        n = 0
        for kid in ids:
            try: db.delete_knowledge_point(kid); n+=1
            except: pass
        return jsonify({"success":True,"deleted":n})
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
        for kid in ids:
            try:
                db.renew_freshness(kid, note)
                n += 1
            except: pass
        return jsonify({"success":True,"renewed":n})
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

def _open(port):
    import time; time.sleep(1.5); webbrowser.open(f"http://localhost:{port}")

def main():
    p=PROJECT_ROOT/"config"/"settings.json"; port=5000
    if p.exists():
        with open(p,"r",encoding="utf-8") as f: port=json.load(f).get("flask_port",5000)
    print("="*60)
    print(f"  乡村振兴知识库 - 审核界面 v2.1.0-d")
    print(f"  三层标签审核 | 保鲜提醒 | V3质检 | 批量操作")
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
