"""
api_server.py - Flask API + 管理后台
路径：scripts/api_server.py
版本：v2.2.0 bugfix-6 - 强制重新处理已完成文件
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
        r = db.get_all_knowledge_points(
            review_status=request.args.get("status"), content_type=request.args.get("type"),
            category_id=request.args.get("category",None,type=int),
            level1_code=request.args.get("level1",None),
            search_query=request.args.get("search",None),
            content_readiness=request.args.get("readiness",None),
            freshness_filter=freshness_filter,
            policy_filter=policy_filter,
            source_type_filter=source_type_filter,
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

@app.route("/api/knowledge-points/batch-mark-outdated", methods=["POST"])
def batch_mark_outdated():
    """批量标记过时"""
    try:
        d = request.get_json() or {}
        ids = d.get("ids", [])
        reason = d.get("reason", "")
        n = 0
        for kid in ids:
            try:
                db.mark_knowledge_outdated(kid, reason)
                n += 1
            except: pass
        return jsonify({"success":True,"marked":n})
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
    """处理重复组：保留指定知识点，删除其余（支持keep_ids多选）"""
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
        # 删除未勾选的知识点
        deleted = []
        for mid in member_ids:
            if mid not in keep_ids:
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
    """批量处理重复组：支持按AI建议处理或全部标记非重复"""
    try:
        d = request.get_json() or {}
        group_ids = d.get("group_ids", [])
        action = d.get("action", "ai_suggest")  # ai_suggest=按AI建议保留, dismiss=全部标记非重复
        if not group_ids:
            return jsonify({"error":"请选择至少一个重复组"}),400
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
        for kid in ids:
            try:
                kp = db.get_knowledge_point(kid)
                if kp and kp["review_status"] == "ignored":
                    db.restore_to_pending(kid)
                    n += 1
            except: pass
        return jsonify({"success":True,"restored":n})
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
        c.execute("""SELECT CAST(qa_score AS INTEGER) as qs, COUNT(*) FROM knowledge_points
                     WHERE qa_score IS NOT NULL GROUP BY qs ORDER BY qs""")
        qa_dist = {}
        for row in c.fetchall():
            qa_dist[str(row[0])] = row[1]
        c.execute("SELECT COUNT(*) FROM knowledge_points WHERE qa_score IS NULL")
        qa_dist["unscored"] = c.fetchone()[0]
        data["qa_distribution"] = qa_dist

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
    """执行全库重复检测（同步，知识库小时可用）"""
    try:
        from scripts.duplicate_checker import DuplicateChecker
        checker = DuplicateChecker(db=db)
        new_groups = checker.scan_full()
        summary = db.get_duplicate_summary()
        return jsonify({"success": True, "new_groups": new_groups, "summary": summary})
    except Exception as e:
        traceback.print_exc()
        return jsonify({"error": str(e)}), 500

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
    """执行版本重提取(备份→删除旧知识点→重置源文件状态→启动提取)"""
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
            # Step 1: 自动备份
            _task_update_progress({"current_step": "自动备份", "message": "正在备份数据库..."})
            try:
                from scripts.backup_manager import BackupManager
                bm = BackupManager()
                bm.create_backup("reextract_auto")
            except Exception as e:
                print(f"  [WARN] 自动备份失败: {e}")

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
    import time; time.sleep(1.5); webbrowser.open(f"http://localhost:{port}")

def _open(port):
    import time; time.sleep(1.5); webbrowser.open(f"http://localhost:{port}")

def main():
    p=PROJECT_ROOT/"config"/"settings.json"; port=5000
    if p.exists():
        with open(p,"r",encoding="utf-8") as f: port=json.load(f).get("flask_port",5000)
    print("="*60)
    print(f"  乡村振兴知识库 - 管理后台 v2.2.0")
    print(f"  Tab1 知识审核 | Tab2 系统管理(仪表盘+工具箱+提取管理+经验速记)")
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
