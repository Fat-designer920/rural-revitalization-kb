"""
citation_verifier.py - 知识库引文校验引擎
路径：scripts/citation_verifier.py
版本：v2.3.7-part7
校验KP中引用的政策文件号/名称/日期是否可追溯、可验证
"""
import os, sys, re, json
from pathlib import Path
from datetime import datetime
from typing import Dict, List, Optional, Tuple, Any

PROJECT_ROOT = Path(__file__).parent.parent
sys.path.insert(0, str(PROJECT_ROOT))

# 中国政府公文发文字号正则(机关代字〔年份〕序号号)
_DOC_NUM_RE = re.compile(
    r'([一-鿿]{2,15}发[一-鿿]{0,10})'
    r'〔(\d{4})〕'
    r'(\d{1,6})\s*号'
)
# 备选格式: 半角括号
_DOC_NUM_RE_ALT = re.compile(
    r'([一-鿿]{2,15}发[一-鿿]{0,10})'
    r'[\[\(](\d{4})[\]\)]'
    r'(\d{1,6})\s*号'
)
# 政策文件名称模式(书名号包裹)
_POLICY_NAME_RE = re.compile(r'《([^》]{4,80})》')
# 年份提取
_YEAR_RE = re.compile(r'(19\d{2}|20\d{2})')
# 日期模式
_DATE_RE = re.compile(r'(\d{4})[年/-](\d{1,2})[月/-](\d{1,2})日?')

# 已知发文机关代字前缀(不完全列表, 覆盖乡村振兴常见领域)
KNOWN_AGENCY_PREFIXES = [
    "国发", "国办发", "中发", "中办发",
    "川府发", "川办发", "川自然资发", "川农发", "川财农",
    "自然资发", "自然资办发", "农发", "农办发",
    "财农", "财预", "发改", "发改农经",
    "生态环境部发", "住建发", "文旅发", "水利发",
    "川发改", "川环发", "川住建发",
]


class CitationVerifier:
    """引文校验器: 全量扫描KP → 提取引用 → 对比source_files → 生成报告."""

    def __init__(self, db: Any):
        self.db = db
        self._source_files_cache: Optional[Dict[int, Dict]] = None
        self._kg_entities_cache: Optional[set] = None

    def _load_source_files(self) -> Dict[int, Dict]:
        """加载source_files表到内存cache."""
        if self._source_files_cache is not None:
            return self._source_files_cache
        conn = self.db.get_connection()
        c = conn.cursor()
        c.execute("SELECT * FROM source_files")
        rows = [dict(r) for r in c.fetchall()]
        conn.close()
        self._source_files_cache = {r["id"]: r for r in rows}
        return self._source_files_cache

    def _load_kg_entities(self) -> set:
        """加载知识图谱中的实体名称集合(政策名/文件名)."""
        if self._kg_entities_cache is not None:
            return self._kg_entities_cache
        entities = set()
        conn = self.db.get_connection()
        c = conn.cursor()
        try:
            c.execute("SELECT name FROM graph_nodes WHERE node_type='policy'")
            for r in c.fetchall():
                entities.add(r[0])
        except Exception:
            pass
        try:
            c.execute("SELECT original_filename, renamed_filename FROM source_files")
            for r in c.fetchall():
                if r[0]:
                    entities.add(r[0])
                if r[1]:
                    entities.add(r[1])
        except Exception:
            pass
        conn.close()
        self._kg_entities_cache = entities
        return entities

    def _extract_citations(self, text: str) -> Dict:
        """从文本中提取政策文件引用: 发文字号/文件名/日期."""
        if not text:
            return {"doc_numbers": [], "policy_names": [], "years": [], "dates": []}
        doc_nums = []
        for m in _DOC_NUM_RE.finditer(text):
            doc_nums.append({
                "agency": m.group(1),
                "year": int(m.group(2)),
                "seq": int(m.group(3)),
                "full": m.group(0).strip(),
            })
        for m in _DOC_NUM_RE_ALT.finditer(text):
            full = m.group(0).strip()
            if not any(d["full"] == full for d in doc_nums):
                doc_nums.append({
                    "agency": m.group(1),
                    "year": int(m.group(2)),
                    "seq": int(m.group(3)),
                    "full": full,
                })

        names = [m.group(1).strip() for m in _POLICY_NAME_RE.finditer(text)]

        years = list(set(int(m.group(1)) for m in _YEAR_RE.finditer(text)
                         if 1949 <= int(m.group(1)) <= 2030))

        dates = []
        for m in _DATE_RE.finditer(text):
            y, mo, d = int(m.group(1)), int(m.group(2)), int(m.group(3))
            if 1949 <= y <= 2030 and 1 <= mo <= 12 and 1 <= d <= 31:
                dates.append({"year": y, "month": mo, "day": d, "full": m.group(0)})

        return {
            "doc_numbers": doc_nums,
            "policy_names": names,
            "years": years,
            "dates": dates,
        }

    def verify_kp(self, kp_id: int) -> Dict:
        """校验单个KP的引用质量。返回详细校验报告."""
        conn = self.db.get_connection()
        c = conn.cursor()
        c.execute("""SELECT kp.*, sf.original_filename, sf.renamed_filename,
                     sf.file_type, sf.policy_level
                     FROM knowledge_points kp
                     LEFT JOIN source_files sf ON kp.source_file_id = sf.id
                     WHERE kp.id = ?""", (kp_id,))
        row = c.fetchone()
        conn.close()

        if not row:
            return {"kp_id": kp_id, "error": "not found"}

        kp = dict(row)
        title = kp.get("title") or ""
        excerpt = kp.get("original_excerpt") or ""
        ai_content = kp.get("ai_extracted_content") or ""
        if isinstance(ai_content, dict):
            ai_content = (ai_content.get("description") or ""
                          + json.dumps(ai_content.get("key_points", []),
                                       ensure_ascii=False))
        elif isinstance(ai_content, str):
            try:
                parsed = json.loads(ai_content)
                ai_content = (str(parsed.get("description") or "")
                              + json.dumps(parsed.get("key_points", []),
                                           ensure_ascii=False))
            except (json.JSONDecodeError, ValueError):
                pass

        full_text = " ".join([title, excerpt, str(ai_content)])
        citations = self._extract_citations(full_text)
        sf = self._load_source_files()
        kg = self._load_kg_entities()

        issues = []
        warnings = []
        ok_checks = []

        # 检查1: 发文字号格式校验
        for dn in citations["doc_numbers"]:
            prefix_ok = any(dn["agency"].startswith(p)
                            for p in KNOWN_AGENCY_PREFIXES)
            if not prefix_ok:
                warnings.append({
                    "type": "unknown_agency_prefix",
                    "detail": "发文字号 %s 的发文机关代字不在已知列表中" % dn["full"],
                    "citation": dn,
                })
            if dn["year"] > datetime.now().year + 1 or dn["year"] < 1949:
                issues.append({
                    "type": "implausible_year",
                    "detail": "发文字号 %s 年份 %d 不合理" % (dn["full"], dn["year"]),
                    "citation": dn,
                })
            ok_checks.append("doc_number_format_ok:%s" % dn["full"][:40])

        # 检查2: 政策文件名称可追溯(是否在source_files中)
        src_filenames = set()
        for sid, sfinfo in sf.items():
            src_filenames.add(sfinfo.get("original_filename", ""))
            src_filenames.add(sfinfo.get("renamed_filename", ""))
            src_filenames.add(os.path.splitext(
                sfinfo.get("original_filename", ""))[0])

        for pn in citations["policy_names"]:
            found = False
            for sfname in src_filenames:
                if pn[:15] in sfname or sfname[:15] in pn:
                    found = True
                    break
            if not found:
                # 在知识图谱实体中查找
                for ent in kg:
                    if pn[:15] in ent or ent[:15] in pn:
                        found = True
                        break
            if found:
                ok_checks.append("policy_name_traceable:%s" % pn[:50])
            else:
                warnings.append({
                    "type": "policy_name_untraceable",
                    "detail": "政策名《%s》未在source_files/知识图谱中找到匹配" % pn,
                })

        # 检查3: 日期范围在源文件创建时间附近
        source_file = sf.get(kp.get("source_file_id")) if kp.get("source_file_id") else None
        if source_file:
            sf_created = source_file.get("created_at", "")
            sf_year = None
            for ym in _YEAR_RE.finditer(sf_created or ""):
                sf_year = int(ym.group(1))
                break
            if sf_year:
                for cite_y in citations["years"]:
                    if abs(cite_y - sf_year) > 15:
                        warnings.append({
                            "type": "year_far_from_source",
                            "detail": "引用年份%d与源文件年份%d相差>15年" % (cite_y, sf_year),
                        })
                    else:
                        ok_checks.append("year_in_range:%d vs source %d" % (cite_y, sf_year))

        # 检查4: 是否有引用(非空)
        has_any = bool(citations["doc_numbers"] or citations["policy_names"]
                       or citations["dates"])
        if not has_any:
            source_authority = kp.get("source_authority", "")
            if source_authority in ("official", "authoritative"):
                warnings.append({
                    "type": "no_citations_found",
                    "detail": "权威/官方来源KP无任何可识别引用(文件号/政策名/日期)",
                })

        all_issues = issues + warnings
        status = "fail" if issues else ("warning" if warnings else "pass")

        return {
            "kp_id": kp_id,
            "title": (kp.get("title") or "")[:120],
            "source_file": (source_file.get("original_filename", "")
                            if source_file else "N/A"),
            "citations_found": {
                "doc_numbers": len(citations["doc_numbers"]),
                "policy_names": len(citations["policy_names"]),
                "years": len(citations["years"]),
                "dates": len(citations["dates"]),
            },
            "status": status,
            "issues": issues,
            "warnings": warnings,
            "ok_checks": ok_checks[:10],
            "extracted_citations": citations,
        }

    def verify_all(self, limit: int = 0) -> Dict:
        """全量扫描confirmed KPs, 汇总校验报告."""
        conn = self.db.get_connection()
        c = conn.cursor()
        c.execute("""SELECT id FROM knowledge_points
                     WHERE review_status = 'confirmed'
                     ORDER BY id""")
        ids = [r[0] for r in c.fetchall()]
        conn.close()

        if limit > 0:
            ids = ids[:limit]

        all_reports = []
        pass_count = warn_count = fail_count = 0
        untraceable = []

        for kp_id in ids:
            r = self.verify_kp(kp_id)
            all_reports.append(r)
            if r.get("status") == "pass":
                pass_count += 1
            elif r.get("status") == "warning":
                warn_count += 1
            else:
                fail_count += 1
                untraceable.append({
                    "kp_id": r["kp_id"],
                    "title": r.get("title", ""),
                    "issues": [i["detail"] for i in r.get("issues", [])],
                })

        return {
            "total_checked": len(ids),
            "pass": pass_count,
            "warning": warn_count,
            "fail": fail_count,
            "ok_rate": round(pass_count / len(ids) * 100, 1) if ids else 0,
            "verified_at": datetime.now().isoformat(),
            "reports": all_reports,
            "unverifiable": untraceable,
        }

    def report_unverifiable(self, verify_all_result: Dict = None) -> List[Dict]:
        """返回不可校验的KP列表."""
        if verify_all_result is None:
            verify_all_result = self.verify_all()
        return verify_all_result.get("unverifiable", [])

    def generate_markdown_report(self, result: Dict) -> str:
        """生成Markdown校验报告."""
        lines = [
            "# Citation Verification Report",
            "",
            "**Verified**: %s | **Total**: %d KPs" % (
                result.get("verified_at", "?"), result.get("total_checked", 0)),
            "",
            "| Status | Count | Rate |",
            "|--------|-------|------|",
        ]
        total = result.get("total_checked", 0) or 1
        lines.append("| Pass | %d | %.1f%% |" % (result["pass"],
                      result["pass"] / total * 100))
        lines.append("| Warn | %d | %.1f%% |" % (result["warning"],
                      result["warning"] / total * 100))
        lines.append("| Fail | %d | %.1f%% |" % (result["fail"],
                      result["fail"] / total * 100))

        unv = result.get("unverifiable", [])
        if unv:
            lines.extend([
                "",
                "## Unverifiable KPs (top 10)",
                "",
                "| KP ID | Title | Issues |",
                "|-------|-------|--------|",
            ])
            for u in unv[:10]:
                lines.append("| %s | %s | %s |" % (
                    u["kp_id"],
                    (u.get("title", "") or "")[:60],
                    "; ".join(u.get("issues", []))[:100],
                ))

        lines.append("\n---\n*Generated by citation_verifier.py*")
        return "\n".join(lines)


def main():
    """CLI入口: python scripts/citation_verifier.py [kp_id] [--all] [--limit N]"""
    import argparse
    ap = argparse.ArgumentParser(description="Citation Verification Engine")
    ap.add_argument("kp_id", type=int, nargs="?", default=None,
                    help="校验单个KP ID")
    ap.add_argument("--all", action="store_true", help="全量扫描")
    ap.add_argument("--limit", type=int, default=0, help="全量扫描上限(0=不限制)")
    ap.add_argument("--unverifiable", action="store_true", help="仅输出不可校验列表")
    args = ap.parse_args()

    from scripts.db_manager import DatabaseManager
    db = DatabaseManager()
    verifier = CitationVerifier(db)

    if args.kp_id:
        r = verifier.verify_kp(args.kp_id)
        print(json.dumps(r, ensure_ascii=False, indent=2))
    elif args.all or args.unverifiable:
        result = verifier.verify_all(limit=args.limit)
        if args.unverifiable:
            unv = verifier.report_unverifiable(result)
            print("Unverifiable KPs: %d" % len(unv))
            for u in unv[:20]:
                print("  KP#%s: %s" % (u["kp_id"], (u.get("title", "") or "")[:80]))
        else:
            print(json.dumps({
                "total": result["total_checked"],
                "pass": result["pass"],
                "warning": result["warning"],
                "fail": result["fail"],
                "ok_rate": result["ok_rate"],
                "unverifiable_count": len(result.get("unverifiable", [])),
                "verified_at": result["verified_at"],
            }, ensure_ascii=False, indent=2))
            md = verifier.generate_markdown_report(result)
            print("\n" + md)
    else:
        ap.print_help()


if __name__ == "__main__":
    main()
