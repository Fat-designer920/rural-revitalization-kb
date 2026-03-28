"""
tag_config.py - 标签体系配置
路径：scripts/tag_config.py
版本：v2.1.0-d
三层标签体系：
    第一层：分类标签（从固定清单中选，6组41个）
    第二层：属性标签（从限定维度中选）
    第三层：关键词（AI自由提取）

新增领域时只需要在A组添加标签，B-F组是通用框架不需要改。
v2.0.0-b新增：get_metadata_for_prompt()辅助函数
v2.1.0-d新增：FRESHNESS_RULES保鲜周期配置
"""

# ============================================================
# 第一层：分类标签（41个）
# 每条知识点选3-6个，AI从此清单中选择
# ============================================================
LAYER1_TAGS = {
    "A": {
        "group_name": "业务领域",
        "description": "这条知识属于什么业务板块",
        "required": True,  # 每条知识点必须至少选1个A组标签
        "tags": [
            {"code": "A01", "name": "全域土地综合整治", "definition": "整治试点、管理办法、实施方案、综合整治相关的一切内容"},
            {"code": "A02", "name": "增减挂钩", "definition": "城乡建设用地增减挂钩指标的产生、交易、使用"},
            {"code": "A03", "name": "占补平衡", "definition": "耕地占补平衡、补充耕地指标"},
            {"code": "A04", "name": "集体建设用地入市", "definition": "集体经营性建设用地入市规则、定价、收益分配"},
            {"code": "A05", "name": "川西林盘保护", "definition": "川西林盘的认定、修复、保护利用"},
            {"code": "A06", "name": "高标准农田", "definition": "高标准农田建设、提质改造、验收"},
            {"code": "A07", "name": "生态修复治理", "definition": "矿山修复、水土治理、生态补偿、碳汇"},
            {"code": "A08", "name": "国土空间规划", "definition": "用途管制、三区三线、村庄规划"},
            {"code": "A09", "name": "宅基地改革", "definition": "宅基地退出、流转、有偿使用"},
            {"code": "A10", "name": "乡村产业运营", "definition": "民宿农旅、集体经济、产业导入、运营管理"},
            {"code": "A11", "name": "耕地保护", "definition": "永久基本农田、非农化非粮化、耕地保护责任"},
            {"code": "A12", "name": "农村人居环境", "definition": "人居环境整治、风貌提升、基础设施"},
            {"code": "A13", "name": "指标交易与定价", "definition": "各类指标(增减挂钩/占补/碳汇)的市场化交易规则与价格"},
        ]
    },
    "B": {
        "group_name": "项目阶段",
        "description": "这条知识对应操盘的哪个环节",
        "required": False,
        "tags": [
            {"code": "B01", "name": "前期策划", "definition": "选址论证、可行性分析、合作模式选择"},
            {"code": "B02", "name": "立项审批", "definition": "项目申报、批复流程、部门协调"},
            {"code": "B03", "name": "规划设计", "definition": "方案编制、规划衔接、技术标准"},
            {"code": "B04", "name": "资金筹措", "definition": "资金来源、融资方案、资金拼盘设计"},
            {"code": "B05", "name": "招标采购", "definition": "招标方式、EPC打捆、评标标准"},
            {"code": "B06", "name": "实施推进", "definition": "施工管理、进度协调、问题处置"},
            {"code": "B07", "name": "验收评估", "definition": "竣工验收、成效评估、指标核算"},
            {"code": "B08", "name": "运营移交", "definition": "后期运营、资产移交、长效管护"},
        ]
    },
    "C": {
        "group_name": "知识形态",
        "description": "这条知识在产品中扮演什么角色、当什么素材用",
        "required": True,
        "tags": [
            {"code": "C01", "name": "政策解读", "definition": "对政策条款的提炼和实操解读，用于文章的政策背景和合规依据"},
            {"code": "C02", "name": "实战案例", "definition": "有地点、有数据、有过程、有结果的真实项目，用于案例举证和对标"},
            {"code": "C03", "name": "操盘方法", "definition": "可复用的策略、流程、方法论，产品的核心干货部分"},
            {"code": "C04", "name": "数据支撑", "definition": "可直接引用的数据、基准值、对比数据，增强说服力的硬证据"},
            {"code": "C05", "name": "避坑指南", "definition": "失败教训、风险点、常见误区，最吸引眼球的血泪教训"},
            {"code": "C06", "name": "深度洞察", "definition": "反常识判断、行业真相、趋势预判，产品的灵魂和差异化卖点"},
            {"code": "C07", "name": "模板范本", "definition": "可直接套用的方案结构、合同条款、申报材料"},
            {"code": "C08", "name": "话术表达", "definition": "面向不同对象的沟通方式、汇报策略"},
            {"code": "C09", "name": "问答语料", "definition": "一问一答粒度的知识颗粒，直接支撑问答助手"},
        ]
    },
    "D": {
        "group_name": "客户视角",
        "description": "这条知识对谁最有价值",
        "required": False,
        "tags": [
            {"code": "D01", "name": "决策参考", "definition": "面向政府领导/局长，关注该不该做、怎么选择"},
            {"code": "D02", "name": "操盘指导", "definition": "面向平台公司/项目经理，关注具体怎么做、步骤是什么"},
            {"code": "D03", "name": "专业深化", "definition": "面向咨询师/规划师，关注怎么做得更好、有什么别人不知道的"},
            {"code": "D04", "name": "入门普及", "definition": "面向新人/跨行者，关注这是什么、为什么这样"},
            {"code": "D05", "name": "谈判说服", "definition": "面向需要对外说服他人的人，需要案例+数据+话术"},
        ]
    },
    "E": {
        "group_name": "稀缺度",
        "description": "这条知识的独特性程度，决定产品定价的底气",
        "required": True,
        "tags": [
            {"code": "E01", "name": "独家经验", "definition": "只有亲身经历过才知道的，网上搜不到"},
            {"code": "E02", "name": "稀缺信息", "definition": "虽非独家，但行业内少数人知道、不易获取"},
            {"code": "E03", "name": "公开信息", "definition": "网上可以搜到的政策原文、公开数据，做背景铺垫用"},
        ]
    },
    "F": {
        "group_name": "内容状态",
        "description": "内容的时效性风险标记",
        "required": True,
        "tags": [
            {"code": "F01", "name": "时效敏感", "definition": "包含可能过时的数据、价格、政策状态，引用时需加时效提醒"},
            {"code": "F02", "name": "长期有效", "definition": "方法论、经验、流程等不易过时的内容"},
            {"code": "F03", "name": "待验证", "definition": "未经充分实战验证的判断或传闻，引用时需加仅供参考标记"},
        ]
    }
}

# ============================================================
# 第二层：属性标签（维度+候选值）
# AI从每个维度的候选值中选择，只填有意义的维度
# ============================================================
LAYER2_DIMENSIONS = {
    "policy_level": {
        "name": "政策层级",
        "applies_to": ["policy"],  # 只对政策类知识生效
        "values": ["国家级", "省级", "市县级", "行业规范"]
    },
    "fund_channel": {
        "name": "资金渠道",
        "applies_to": ["policy", "case", "data"],
        "values": ["专项债", "财政整合", "社会资本", "集体自筹", "指标交易收益", "银行贷款", "EOD模式"]
    },
    "stakeholder": {
        "name": "涉及主体",
        "applies_to": ["policy", "case", "experience", "tool"],
        "values": ["自然资源局", "发改委", "财政局", "农业农村局", "平台公司", "村集体", "社会资本方", "农户", "乡镇政府", "设计院", "施工单位"]
    },
    "region": {
        "name": "涉及区域",
        "applies_to": ["case", "policy", "data"],
        "values": []  # 自由填写，不限定候选值
    },
    "timeliness": {
        "name": "时效状态",
        "applies_to": ["policy"],
        "values": ["现行有效", "已废止", "待实施"]
    },
    "data_year": {
        "name": "数据年份",
        "applies_to": ["data"],
        "values": []  # 自由填写年份
    },
    "replicability": {
        "name": "可复制性",
        "applies_to": ["case", "experience"],
        "values": ["高度可复制", "条件性可复制", "特殊案例"]
    },
    "fund_scale": {
        "name": "资金规模",
        "applies_to": ["case", "data"],
        "values": ["百万级", "千万级", "亿级", "十亿级"]
    }
}

# ============================================================
# 第三层：关键词提取规则（给AI的指引）
# ============================================================
LAYER3_KEYWORD_RULES = """关键词提取规则：
1. 每条知识点提取5-15个关键词
2. 三个角度必须覆盖：
   - 术语类：行业专有名词，如"EPC+O""增存挂钩""土地发展权"
   - 实体类：具体的政策文号、项目名称、地名、机构名，如"自然资发〔2023〕95号""崇州市桤泉镇"
   - 场景类：用户可能的提问方式，如"指标跨省交易""专项债还款来源设计""村民代表大会表决流程"
3. 关键词长度2-20字，使用行业通用表述
4. 同一概念的不同表述都要收录（如"EPC打捆"和"工程总承包"）
5. 禁止：纯数字、百分比、公文操作词（报送/印发/转发）、过于宽泛的词（乡村振兴/土地政策）"""

# ============================================================
# 就绪度、权威度、变现分级的候选值定义
# ============================================================
CONTENT_READINESS = {
    "draft": {"name": "草稿级", "definition": "内容粗糙，仅供内部参考，不适合用于付费产品"},
    "quotable": {"name": "可引用级", "definition": "内容完整准确，可用于知识产品和问答助手"},
    "premium": {"name": "精品级", "definition": "经过精心打磨，适合直接展示给付费客户"}
}

SOURCE_AUTHORITY = {
    "official": {"name": "官方文件", "definition": "国务院/部委/省政府正式发文"},
    "authoritative": {"name": "行业权威", "definition": "知名机构报告、权威期刊"},
    "firsthand": {"name": "项目实证", "definition": "亲历的项目数据和经验"},
    "informal": {"name": "业内交流", "definition": "同行分享、会议信息、非正式渠道"}
}

ACCESS_LEVEL = {
    "open": {"name": "开放", "definition": "可用于免费回答和引流内容"},
    "standard": {"name": "标准", "definition": "标准订阅用户可获取"},
    "premium": {"name": "高级", "definition": "高级订阅独享"}
}

# ============================================================
# 保鲜周期配置（v2.1.0-d新增）
# 按一级分类设定默认保鲜周期（天），后续可细化为分类x属性联合判断
# ============================================================
FRESHNESS_RULES = {
    "1": 90,    # 政策库 - 政策变化快，90天检查一次
    "2": 180,   # 案例库 - 案例相对稳定，180天
    "3": 365,   # 经验库 - 操盘经验长期有效
    "4": 365,   # 工具库 - 模板类长期有效
    "5": 90,    # 数据库 - 数据时效性强，90天
}

# 超期多少天算"逾期未检"（审核界面特殊高亮提醒）
FRESHNESS_OVERDUE_DAYS = 30

# ============================================================
# 辅助函数
# ============================================================

def get_all_layer1_tags():
    """获取所有第一层标签的扁平列表"""
    result = []
    for group_code, group in LAYER1_TAGS.items():
        for tag in group["tags"]:
            result.append({
                "group_code": group_code,
                "group_name": group["group_name"],
                "code": tag["code"],
                "name": tag["name"],
                "definition": tag["definition"]
            })
    return result


def get_layer1_for_prompt():
    """生成注入到Prompt中的第一层标签清单文本"""
    lines = []
    for group_code in sorted(LAYER1_TAGS.keys()):
        group = LAYER1_TAGS[group_code]
        lines.append(f"\n{group_code}组 - {group['group_name']}（{group['description']}）" +
                     ("【必选至少1个】" if group.get("required") else "【可选】"))
        for tag in group["tags"]:
            lines.append(f"  {tag['code']} {tag['name']}：{tag['definition']}")
    return "\n".join(lines)


def get_layer2_for_prompt(content_type):
    """生成注入到Prompt中的第二层属性标签说明"""
    lines = ["第二层属性标签（只填与本知识点相关的维度，无关维度留空）："]
    for dim_code, dim in LAYER2_DIMENSIONS.items():
        if not dim["applies_to"] or content_type in dim["applies_to"]:
            if dim["values"]:
                lines.append(f"  {dim['name']}({dim_code})：从以下选项中选——{'/'.join(dim['values'])}")
            else:
                lines.append(f"  {dim['name']}({dim_code})：自由填写")
    return "\n".join(lines)


def get_layer1_tag_names():
    """获取所有第一层标签名称的列表（用于AI打标时的候选清单）"""
    names = []
    for group in LAYER1_TAGS.values():
        for tag in group["tags"]:
            names.append(tag["name"])
    return names


def get_tag_by_name(name):
    """根据标签名称查找标签信息"""
    for group_code, group in LAYER1_TAGS.items():
        for tag in group["tags"]:
            if tag["name"] == name:
                return {**tag, "group_code": group_code, "group_name": group["group_name"]}
    return None


def get_metadata_for_prompt():
    """生成注入到Prompt中的元数据候选值说明（v2.0.0-b新增）"""
    lines = ["就绪度（suggested_readiness）："]
    for k, v in CONTENT_READINESS.items():
        lines.append(f"  {k} = {v['name']}：{v['definition']}")
    lines.append("")
    lines.append("权威度（suggested_authority）：")
    for k, v in SOURCE_AUTHORITY.items():
        lines.append(f"  {k} = {v['name']}：{v['definition']}")
    return "\n".join(lines)


def get_default_freshness_interval(content_type):
    """根据content_type获取默认保鲜周期（v2.1.0-d新增）"""
    type_to_level1 = {
        "policy": "1", "case": "2", "experience": "3",
        "tool": "4", "data": "5"
    }
    level1 = type_to_level1.get(content_type, "3")
    return FRESHNESS_RULES.get(level1, 180)
