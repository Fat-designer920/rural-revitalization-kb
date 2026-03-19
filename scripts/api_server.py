"""
api_server.py - Flask API + 审核界面
路径：scripts/api_server.py
注意：不使用Flask模板引擎,启动时读取HTML到内存,用Response直接返回
"""
import os,sys,json,traceback,webbrowser,threading
from pathlib import Path
from datetime import datetime
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
    for f in ["ai_extracted_content","suggested_tags","final_tags","domain_tags"]:
        if f in r: r[f] = _parse(r[f])
    return r

@app.before_request
def _log(): print(f"  >> {request.method} {request.path}")

@app.errorhandler(404)
def _404(e): return jsonify({"error":"not found:"+request.path}),404

@app.route("/")
def index():
    if REVIEW_HTML: return Response(REVIEW_HTML, mimetype="text/html; charset=utf-8")
    return "<h1>review.html not found</h1>",404

@app.route("/api/knowledge-points", methods=["GET"])
def get_kps():
    try:
        r = db.get_all_knowledge_points(
            review_status=request.args.get("status"), content_type=request.args.get("type"),
            category_id=request.args.get("category",None,type=int),
            page=request.args.get("page",1,type=int), per_page=request.args.get("per_page",20,type=int))
        r["items"] = [_safe(i) for i in r["items"]]
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
        db.ignore_knowledge_point(kid, (request.get_json() or {}).get("reason",""))
        return jsonify({"success":True})
    except Exception as e: traceback.print_exc(); return jsonify({"error":str(e)}),500

@app.route("/api/knowledge-points/<int:kid>", methods=["PUT"])
def update(kid):
    try:
        d = request.get_json() or {}
        u = {k:d[k] for k in ["title","final_category_id","final_tags","reviewer_notes","ai_extracted_content"] if k in d}
        if u: db.update_knowledge_point(kid, **u)
        return jsonify({"success":True})
    except Exception as e: traceback.print_exc(); return jsonify({"error":str(e)}),500

@app.route("/api/knowledge-points/batch-confirm", methods=["POST"])
def batch():
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

@app.route("/api/categories")
def cats(): 
    try: return jsonify(db.get_all_categories())
    except: return jsonify([])

@app.route("/api/categories/tree")
def tree():
    try: return jsonify(db.get_categories_tree())
    except: return jsonify({})

@app.route("/api/statistics")
def stats():
    try: return jsonify(db.get_statistics())
    except: return jsonify({"files":{},"knowledge_points":{},"by_type":{},"today_api_cost":0,"total_confirmed":0,"total_pending":0})

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
    print(f"  乡村振兴知识库 - 审核界面 v1.0.0")
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
