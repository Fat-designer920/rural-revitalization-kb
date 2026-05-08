"""
knowledge_graph.py - 轻量级知识图谱引擎(v1,基于现有KP数据,JSON存储)
路径：scripts/knowledge_graph.py
版本：v2.3.7-part7
"""
import json, os, re, sqlite3
from pathlib import Path
from collections import defaultdict
from datetime import datetime

PROJECT_ROOT = Path(__file__).parent.parent
DATA_DIR = PROJECT_ROOT / "data" / "knowledge_graph"
DEFAULT_DB_PATH = PROJECT_ROOT / "data" / "database" / "knowledge_base.db"

# ── 四川区划名单(地级市+自治州+部分重点县) ──
SICHUAN_PREFECTURES = [
    "成都", "绵阳", "德阳", "宜宾", "南充", "泸州", "达州", "乐山",
    "凉山", "内江", "自贡", "眉山", "遂宁", "广安", "攀枝花", "广元",
    "资阳", "巴中", "雅安", "阿坝", "甘孜", "都江堰", "彭州", "邛崃",
    "崇州", "简阳", "广汉", "什邡", "绵竹", "江油", "峨眉山", "阆中",
    "华蓥", "万源", "西昌", "康定", "马尔康", "汶川", "理县", "茂县",
]
SICHUAN_COUNTIES = [
    "三台", "射洪", "大英", "蓬溪", "安岳", "乐至", "仁寿", "洪雅",
    "丹棱", "青神", "叙永", "古蔺", "合江", "泸县", "中江", "罗江",
    "南部", "仪陇", "营山", "蓬安", "西充", "阆中", "通江", "南江",
    "平昌", "宣汉", "大竹", "渠县", "开江", "安州", "盐亭", "梓潼",
    "平武", "北川", "苍溪", "剑阁", "旺苍", "青川", "荣县", "富顺",
    "荣经", "汉源", "石棉", "天全", "芦山", "宝兴", "长宁", "高县",
    "珙县", "筠连", "兴文", "屏山", "米易", "盐边", "会理", "会东",
    "宁南", "普格", "布拖", "金阳", "昭觉", "喜德", "越西", "甘洛",
    "美姑", "雷波", "松潘", "九寨沟", "金川", "小金", "黑水", "壤塘",
    "阿坝", "若尔盖", "红原", "德格", "白玉", "石渠", "色达", "理塘",
    "巴塘", "乡城", "稻城", "得荣",
]

# ── 正则模式 ──
ENTITY_PATTERNS = {
    "policy_document": re.compile(
        r"《([^》]{2,60})》"
    ),
    "government_body": re.compile(
        r"(国务院|财政部|自然资源部|农业农村部|国家发改委|生态环境部|住房城乡建设部|"
        r"交通运输部|水利部|文化和旅游部|国家卫生健康委|教育部|科技部|公安部|司法部|"
        r"人力资源和社会保障部|应急管理部|退役军人事务部|中国人民银行|审计署|"
        r"国家乡村振兴局|国家粮食和物资储备局|国家能源局|国家林业和草原局|"
        r"中国银保监会|中国证监会|国家标准化管理委员会|"
        r"省委|省政府|省人大|省政协|"
        r"省自然资源厅|省农业农村厅|省财政厅|省发改委|省住建厅|省交通厅|省水利厅|"
        r"省生态环境厅|省文旅厅|省卫健委|省教育厅|省科技厅|省人社厅|"
        r"市委|市政府|市人大|市政协|"
        r"市自然资源局|市农业农村局|市财政局|市发改委|市住建局|"
        r"县委|县政府|县自然资源局|县农业农村局|县财政局|"
        r"自然资源部办公厅|农业农村部办公厅|财政部办公厅|"
        r"省自然资源厅办公室|省农业农村厅办公室|"
        r"领导小组|指挥部|工作专班|联席会议|"
        r"自然资源和规划局|乡村振兴局|发展和改革局|住房和城乡建设局)"
    ),
    "funding_amount": re.compile(
        r"(\d+(?:\.\d+)?)\s*(万元|亿元|万)\b"
    ),
    "legal_article": re.compile(
        r"第([一二三四五六七八九十百千\d]+)\s*条"
    ),
    "date": re.compile(
        r"(\d{4})\s*年\s*(\d{1,2})\s*月\s*(\d{1,2})\s*日"
    ),
    "percentage": re.compile(
        r"(\d+(?:\.\d+)?)\s*%"
    ),
}

# ── 四川地名匹配(从大到小匹配避免子串误判) ──
SICHUAN_PLACE_PATTERN = re.compile(
    "(" + "|".join(
        sorted(SICHUAN_PREFECTURES + SICHUAN_COUNTIES, key=len, reverse=True)
    ) + ")"
)


class KnowledgeGraph:
    """轻量级知识图谱引擎。从knowledge_points表提取实体→构建节点/边→JSON存储→图查询。"""

    def __init__(self, db_path=None):
        self.db_path = db_path or str(DEFAULT_DB_PATH)
        DATA_DIR.mkdir(parents=True, exist_ok=True)
        self.nodes_file = DATA_DIR / "nodes.json"
        self.edges_file = DATA_DIR / "edges.json"
        self.nodes = {}      # {entity_id: {type, name, source_kp_ids, ...}}
        self.edges = []      # [{source, target, relation_type, kp_id, ...}]
        self._node_index = {}  # type→name→id lookup

    # ─── 构建 ───
    def build(self, status_filter=("confirmed", "premium")):
        """从DB提取实体,构建完整知识图谱。
        status_filter: 只处理指定review_status的KP,默认confirmed+premium。
        """
        conn = sqlite3.connect(self.db_path)
        conn.row_factory = sqlite3.Row
        c = conn.cursor()
        placeholders = ",".join("?" * len(status_filter))
        c.execute(
            f"SELECT id, title, content_type, original_excerpt, ai_extracted_content, "
            f"final_keywords, source_keyword, sichuan_prefecture "
            f"FROM knowledge_points WHERE review_status IN ({placeholders})",
            list(status_filter)
        )
        rows = c.fetchall()
        conn.close()

        self.nodes = {}
        self.edges = []
        self._node_index = defaultdict(dict)
        node_id_seq = 0
        edge_id_seq = 0

        for row in rows:
            kp_id = row["id"]
            title = row["title"] or ""
            excerpt = row["original_excerpt"] or ""
            ai_content = row["ai_extracted_content"] or ""

            # 融合文本
            full_text = f"{title} {excerpt} {self._ai_json_to_text(ai_content)}"

            # 各类实体提取
            entities_found = []

            # 政策文档名
            for m in ENTITY_PATTERNS["policy_document"].finditer(full_text):
                name = m.group(1).strip()
                if len(name) >= 3 and not self._is_noise(name):
                    entities_found.append(("policy_document", name))

            # 政府机构
            for m in ENTITY_PATTERNS["government_body"].finditer(full_text):
                name = m.group(1).strip()
                if not self._is_noise(name):
                    entities_found.append(("government_body", name))

            # 四川地名
            for m in SICHUAN_PLACE_PATTERN.finditer(full_text):
                name = m.group(1).strip()
                entities_found.append(("location", name))
            # 也从 sichuan_prefecture 字段提取
            pref = (row["sichuan_prefecture"] or "").strip()
            if pref and len(pref) >= 2:
                entities_found.append(("location", pref))

            # 金额
            for m in ENTITY_PATTERNS["funding_amount"].finditer(full_text):
                value = m.group(1)
                unit = m.group(2)
                name = f"{value}{unit}"
                entities_found.append(("funding", name))

            # 法规条款
            for m in ENTITY_PATTERNS["legal_article"].finditer(full_text):
                art_no = m.group(1)
                name = f"第{art_no}条"
                entities_found.append(("legal_article", name))

            # 日期
            for m in ENTITY_PATTERNS["date"].finditer(full_text):
                y, mm, d = m.group(1), m.group(2).zfill(2), m.group(3).zfill(2)
                name = f"{y}-{mm}-{d}"
                entities_found.append(("date", name))

            # 百分比
            for m in ENTITY_PATTERNS["percentage"].finditer(full_text):
                name = f"{m.group(1)}%"
                entities_found.append(("percentage", name))

            # 去重 + 创建/更新节点,建立KP关联
            entity_ids_in_kp = set()
            for etype, ename in entities_found:
                eid = self._get_or_create_node(ename, etype, kp_id, node_id_seq)
                if eid == node_id_seq:
                    node_id_seq += 1
                entity_ids_in_kp.add(eid)

            # 在KP内共现的实体间建边
            eids = list(entity_ids_in_kp)
            for i in range(len(eids)):
                for j in range(i + 1, len(eids)):
                    self.edges.append({
                        "id": edge_id_seq,
                        "source": eids[i],
                        "target": eids[j],
                        "relation_type": "co_occurs_in_kp",
                        "kp_id": kp_id,
                        "weight": 1,
                    })
                    edge_id_seq += 1

            # 将KP的主题类型也作为一个概念实体加入
            ct = (row["content_type"] or "").strip()
            if ct:
                tid = self._get_or_create_node(f"content_type:{ct}", "concept", kp_id, node_id_seq)
                if tid == node_id_seq:
                    node_id_seq += 1
                for eid in entity_ids_in_kp:
                    self.edges.append({
                        "id": edge_id_seq,
                        "source": eid,
                        "target": tid,
                        "relation_type": "has_content_type",
                        "kp_id": kp_id,
                        "weight": 1,
                    })
                    edge_id_seq += 1

        # 合并重复边(同source→target→relation_type合并为一条,累加weight)
        self._deduplicate_edges()

        print(f"[知识图谱] 构建完成: {len(self.nodes)} 节点 / {len(self.edges)} 边 / 处理 {len(rows)} 条KP")
        return len(self.nodes), len(self.edges)

    def _get_or_create_node(self, name, etype, kp_id, next_id):
        """按 type+name 查找已有节点;不存在则创建。返回 node_id。"""
        idx = self._node_index[etype]
        if name in idx:
            eid = idx[name]
            if kp_id not in self.nodes[eid].get("kp_ids", []):
                self.nodes[eid].setdefault("kp_ids", []).append(kp_id)
                self.nodes[eid]["mention_count"] = len(self.nodes[eid]["kp_ids"])
            return eid

        eid = next_id
        self.nodes[eid] = {
            "id": eid,
            "type": etype,
            "name": name,
            "kp_ids": [kp_id],
            "mention_count": 1,
        }
        idx[name] = eid
        return eid

    def _deduplicate_edges(self):
        """合并重复边: 同 source+target+relation_type 合并,累加 weight。"""
        edge_map = {}
        deduped = []
        for e in self.edges:
            key = (e["source"], e["target"], e["relation_type"])
            if key in edge_map:
                existing = edge_map[key]
                existing["weight"] += e.get("weight", 1)
                if e["kp_id"] not in existing.get("kp_ids", []):
                    existing.setdefault("kp_ids", []).append(e["kp_id"])
            else:
                ne = dict(e)
                ne["kp_ids"] = [ne["kp_id"]]
                del ne["kp_id"]
                edge_map[key] = ne
                deduped.append(ne)
        for i, e in enumerate(deduped):
            e["id"] = i
        self.edges = deduped

    # ─── 持久化 ───
    def save(self):
        """保存节点和边到JSON文件。"""
        data_nodes = {
            "meta": {
                "generated_at": datetime.now().strftime("%Y-%m-%d %H:%M:%S"),
                "total_nodes": len(self.nodes),
                "version": "v2.3.7-part7",
            },
            "nodes": list(self.nodes.values()),
        }
        with open(self.nodes_file, "w", encoding="utf-8") as f:
            json.dump(data_nodes, f, ensure_ascii=False, indent=2)

        data_edges = {
            "meta": {
                "generated_at": datetime.now().strftime("%Y-%m-%d %H:%M:%S"),
                "total_edges": len(self.edges),
                "version": "v2.3.7-part7",
            },
            "edges": self.edges,
        }
        with open(self.edges_file, "w", encoding="utf-8") as f:
            json.dump(data_edges, f, ensure_ascii=False, indent=2)

        print(f"[知识图谱] 已保存: {self.nodes_file} ({len(self.nodes)}节点) / {self.edges_file} ({len(self.edges)}边)")

    def load(self):
        """从JSON文件加载知识图谱。返回 True/False。"""
        if not self.nodes_file.exists() or not self.edges_file.exists():
            return False
        with open(self.nodes_file, "r", encoding="utf-8") as f:
            data_nodes = json.load(f)
        with open(self.edges_file, "r", encoding="utf-8") as f:
            data_edges = json.load(f)

        self.nodes = {}
        self._node_index = defaultdict(dict)
        for n in data_nodes.get("nodes", []):
            self.nodes[n["id"]] = n
            self._node_index[n["type"]][n["name"]] = n["id"]
        self.edges = data_edges.get("edges", [])
        print(f"[知识图谱] 已加载: {len(self.nodes)} 节点 / {len(self.edges)} 边")
        return True

    # ─── 查询 ───
    def find_entities(self, keyword, entity_type=None):
        """按关键词搜索实体。返回匹配的节点列表。"""
        results = []
        kw_lower = keyword.lower()
        for nid, node in self.nodes.items():
            if entity_type and node["type"] != entity_type:
                continue
            if kw_lower in node["name"].lower():
                results.append(dict(node))
        results.sort(key=lambda n: n.get("mention_count", 0), reverse=True)
        return results

    def find_related_entities(self, entity_name, max_depth=2):
        """查找与指定实体相关的所有实体(BFS,按深度分层)。"""
        # 找到起始节点
        start_ids = []
        for nid, node in self.nodes.items():
            if entity_name.lower() in node["name"].lower():
                start_ids.append(nid)

        if not start_ids:
            return {"entity": entity_name, "error": "未找到匹配实体", "layers": []}

        # BFS
        visited = set()
        layers = []
        current = set(start_ids)
        for depth in range(max_depth):
            if not current:
                break
            layer_entities = []
            next_frontier = set()
            for nid in current:
                if nid in visited:
                    continue
                visited.add(nid)
                layer_entities.append(dict(self.nodes[nid]))
                # 找所有相连节点
                for e in self.edges:
                    src, tgt = e["source"], e["target"]
                    if src == nid and tgt not in visited:
                        next_frontier.add(tgt)
                    elif tgt == nid and src not in visited:
                        next_frontier.add(src)
            layers.append({"depth": depth, "entities": layer_entities})
            current = next_frontier

        return {
            "entity": entity_name,
            "total_related": sum(len(l["entities"]) for l in layers),
            "layers": layers,
        }

    def find_paths(self, entity_a, entity_b, max_length=4):
        """BFS查找两实体间的最短路径。"""
        # 找到起始/目标节点
        a_ids = {nid for nid, node in self.nodes.items()
                 if entity_a.lower() in node["name"].lower()}
        b_ids = {nid for nid, node in self.nodes.items()
                 if entity_b.lower() in node["name"].lower()}

        if not a_ids or not b_ids:
            return {"from": entity_a, "to": entity_b, "error": "未找到实体", "paths": []}

        # 邻接表
        adj = defaultdict(set)
        for e in self.edges:
            adj[e["source"]].add(e["target"])
            adj[e["target"]].add(e["source"])

        # BFS双向搜索找最短路径
        paths = []
        from queue import Queue
        q = Queue()
        for aid in a_ids:
            q.put((aid, [aid], {aid}))

        while not q.empty():
            nid, path, visited_set = q.get()
            if len(path) > max_length:
                continue
            if nid in b_ids:
                path_names = [self.nodes[p]["name"] for p in path]
                paths.append({"length": len(path) - 1, "path": path_names, "node_ids": list(path)})
                if len(paths) >= 5:  # 最多返回5条路径
                    break
                continue
            for nb in adj.get(nid, set()):
                if nb not in visited_set:
                    q.put((nb, path + [nb], visited_set | {nb}))

        return {
            "from": entity_a, "to": entity_b,
            "paths_found": len(paths),
            "paths": sorted(paths, key=lambda p: p["length"]),
        }

    def most_connected(self, entity_type=None, top_n=20):
        """找出关联最多的实体(Top N)。"""
        degree = defaultdict(int)
        for e in self.edges:
            degree[e["source"]] += e.get("weight", 1)
            degree[e["target"]] += e.get("weight", 1)

        results = []
        for nid, deg in degree.items():
            node = self.nodes.get(nid)
            if not node:
                continue
            if entity_type and node["type"] != entity_type:
                continue
            results.append({
                **dict(node),
                "degree": deg,
            })
        results.sort(key=lambda n: n["degree"], reverse=True)
        return results[:top_n]

    def summary(self):
        """图谱统计摘要。"""
        type_counts = defaultdict(int)
        for n in self.nodes.values():
            type_counts[n["type"]] += 1
        relation_counts = defaultdict(int)
        for e in self.edges:
            relation_counts[e["relation_type"]] += 1
        return {
            "total_nodes": len(self.nodes),
            "total_edges": len(self.edges),
            "node_types": dict(type_counts),
            "relation_types": dict(relation_counts),
        }

    # ─── 辅助 ───
    @staticmethod
    def _ai_json_to_text(ai_content):
        """将ai_extracted_content JSON展平为文本。"""
        if not ai_content:
            return ""
        try:
            obj = json.loads(ai_content)
        except (json.JSONDecodeError, TypeError):
            return ai_content
        parts = []
        if isinstance(obj, dict):
            for v in obj.values():
                if isinstance(v, str):
                    parts.append(v)
                elif isinstance(v, list):
                    parts.extend([str(x) for x in v if isinstance(x, str)])
        elif isinstance(obj, list):
            parts = [str(x) for x in obj if isinstance(x, str)]
        return " ".join(parts[:20])

    @staticmethod
    def _is_noise(text):
        """过滤常见噪声文本。"""
        noise = {"相关文件", "具体规定", "若干意见", "本办法", "实施细则",
                 "有关规定", "相关要求", "各项措施", "相关政策"}
        return text in noise


def build_and_save(db_path=None):
    """一键构建+保存知识图谱。"""
    kg = KnowledgeGraph(db_path=db_path)
    kg.build()
    kg.save()
    return kg


def load_or_build(db_path=None):
    """加载已有图谱;若不存在则构建。"""
    kg = KnowledgeGraph(db_path=db_path)
    if kg.load():
        return kg
    return build_and_save(db_path=db_path)


# ─── CLI 入口 ───
if __name__ == "__main__":
    import sys
    kg = load_or_build()
    if len(sys.argv) > 1:
        cmd = sys.argv[1]
        if cmd == "--summary":
            import pprint
            pprint.pprint(kg.summary())
        elif cmd == "--find" and len(sys.argv) > 2:
            keyword = sys.argv[2]
            etype = sys.argv[3] if len(sys.argv) > 3 else None
            results = kg.find_entities(keyword, entity_type=etype)
            for r in results[:20]:
                print(f"  [{r['type']}] {r['name']} (提及{r.get('mention_count',0)}次)")
            print(f"\n共找到 {len(results)} 个实体")
        elif cmd == "--related" and len(sys.argv) > 2:
            name = sys.argv[2]
            depth = int(sys.argv[3]) if len(sys.argv) > 3 else 2
            result = kg.find_related_entities(name, max_depth=depth)
            for layer in result.get("layers", []):
                print(f"\n深度 {layer['depth']}:")
                for e in layer["entities"]:
                    print(f"  [{e['type']}] {e['name']}")
            print(f"\n共 {result.get('total_related', 0)} 个关联实体")
        elif cmd == "--path" and len(sys.argv) > 3:
            a, b = sys.argv[2], sys.argv[3]
            result = kg.find_paths(a, b)
            for p in result.get("paths", []):
                print(f"  长度{p['length']}: {' → '.join(p['path'])}")
            print(f"\n共找到 {result.get('paths_found', 0)} 条路径")
        elif cmd == "--top" and len(sys.argv) > 1:
            etype = sys.argv[2] if len(sys.argv) > 2 else None
            top = kg.most_connected(entity_type=etype, top_n=20)
            for i, ent in enumerate(top, 1):
                print(f"  #{i} [{ent['type']}] {ent['name']} — 度{ent['degree']}")
        elif cmd == "--build":
            kg.build()
            kg.save()
        else:
            print(f"未知命令: {cmd}")
            print("用法: python knowledge_graph.py [--summary|--find <kw>|--related <name>|--path <a> <b>|--top|--build]")
    else:
        s = kg.summary()
        print(f"知识图谱: {s['total_nodes']} 节点 / {s['total_edges']} 边")
        print(f"节点类型: {s['node_types']}")
        print(f"关系类型: {s['relation_types']}")
