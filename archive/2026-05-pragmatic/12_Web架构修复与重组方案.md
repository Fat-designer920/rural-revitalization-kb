# Web架构修复与重组方案

> 问题发现: 管理后台被覆盖 + F056命名困惑 + 模板文件混乱 + 路由架构缺失

---

## 问题诊断

### 问题1: 管理后台不见了

**根因**: `api_server.py` 第580-584行, `/` 路由优先返回 `LANDING_HTML`, 导致 `REVIEW_HTML`(管理后台)被覆盖。

```python
# 当前(错误):
@app.route("/")
def index():
    if LANDING_HTML: return Response(LANDING_HTML, ...)  # ← 优先landing
    if REVIEW_HTML: return Response(REVIEW_HTML, ...)    # ← 管理后台被跳过
```

### 问题2: F056是什么

F056是项目内部的功能编号系统(F=Feature, 056=序号):
- F048 = 知识库体检
- F055 = 本地问答助手
- F056 = 精品资产发布JSON标准
- F062 = 端到端测试

`f056_viewer.html` = 精品JSON查看器(拖拽JSON文件→解析渲染13字段)。对老唐有用(导出精品包发给朋友,朋友拖到页面看),但命名对外人不可读。

### 问题3: 模板文件混乱

| 文件 | 大小 | 用途 | 问题 |
|------|------|------|------|
| review.html | **340KB** | 管理后台 | 巨大,单文件堆砌,需拆分 |
| qa_public.html | 41KB | 公开QA | 与qa_modern重复 |
| qa_modern.html | 8KB | 新版QA | 不完整,与qa_public竞争 |
| landing.html | 22KB | 落地页 | 正常 |
| training_camp_landing.html | 39KB | 训练营页 | 远期产品,提前创建? |
| f056_viewer.html | 20KB | 精品查看器 | 文件名不可读 |
| design_system.css | 5KB | 设计系统 | **存在但未被其他文件引用!** |

### 问题4: 我想到你可能没想到的

**a. design_system.css是孤岛** — 5KB的CSS设计系统文件存在但6个HTML文件都没引用它。写了但没用。

**b. qa_modern.html vs qa_public.html打架** — 两个QA页面同时存在。qa_modern(5月2日,8KB)比qa_public(5月1日,41KB)更新但更小,可能是重构未完成。

**c. training_camp_landing.html提前出生** — 训练营是远期产品(月入>¥25万后)。39KB的页面已经存在但产品还没开发,资源错配。

**d. review.html 340KB是定时炸弹** — 单文件340KB的HTML,内联所有CSS+JS。每次改一行都要加载整个文件。后续维护成本指数增长。

**e. 无路由架构** — Flask路由缺乏清晰设计:
- `/` 应该是什么?管理后台?落地页?
- `/admin` 不存在
- `/landing` 不存在(刚需)
- 用户(老唐)和访客(客户)的入口混在一起

**f. 启动后台.bat的预期被破坏** — 老唐双击启动后台的肌肉记忆:期望看到管理后台。现在看到落地页→困惑。

---

## 修复方案

### 路由重设计

```
/           → review.html (管理后台,老唐入口) [恢复原行为]
/admin      → review.html (同上,显式路由)
/landing    → landing.html (产品落地页,客户入口) [新增]
/qa         → qa_public.html (朋友试用) [保持不变]
/premium    → premium_viewer.html (精品查看器) [重命名+新路由]
/course     → course.html (录播课,Phase B用到) [预置]
```

### 文件重命名

```
f056_viewer.html → premium_viewer.html (可读)
合并: qa_public.html + qa_modern.html → qa.html (统一)
保留: review.html (重,但先不动,Phase 1.5设计系统建立后再拆分)
保留: landing.html
保留: design_system.css
暂不处理: training_camp_landing.html (远期产品,保留但标记为"远期")
```

### 管理后台恢复

修改 `api_server.py`:
```python
@app.route("/")
def index():
    # 恢复: / 默认返回管理后台(老唐入口)
    if REVIEW_HTML: return Response(REVIEW_HTML, mimetype="text/html; charset=utf-8")
    return "<h1>管理后台加载失败</h1>", 404

@app.route("/landing")
def landing():
    # 新增: /landing 返回产品落地页(客户入口)
    if LANDING_HTML: return Response(LANDING_HTML, mimetype="text/html; charset=utf-8")
    return "<h1>产品页加载中...</h1>", 404
```

### design_system.css激活

在 `landing.html` 和后续所有新页面中引用 `design_system.css`:
```html
<link rel="stylesheet" href="/static/design_system.css">
```
新增 `/static/` 路由服务web/templates/下的CSS文件。

---

## 延伸思考(补充Phase 1.5)

### Web文件最终组织

```
web/templates/
  ├── design_system.css          # 全局设计token(激活,所有页面共用)
  ├── admin.html                 # [远期] review.html拆分后的管理后台
  ├── review.html                # [近期保留] 管理后台(340KB,后续拆分)
  ├── landing.html               # 产品落地页
  ├── qa.html                    # [合并qa_public+qa_modern] 统一QA页
  ├── premium_viewer.html        # [重命名] 精品JSON查看器
  ├── course.html                # [Phase B] 录播课展示页
  └── archive/                   # [远期备份]
      ├── training_camp_landing.html  # 远期产品页(保留不动)
      ├── qa_public.html              # 旧版(归档)
      └── qa_modern.html              # 旧版(归档)
```

### 启动后台.bat行为

```
双击启动后台.bat:
  1. 启动Flask → 打印: 管理后台: http://localhost:5000
  2. 打印: 产品落地页: http://localhost:5000/landing
  3. 打印: 朋友试用: http://localhost:5000/qa
  4. 自动打开浏览器 → http://localhost:5000 (管理后台)
```

---

## 与Phase 1.5的关系

```
本次修复(立即) 
  ├─ 路由修复(恢复管理后台)
  ├─ f056_viewer重命名
  ├─ design_system.css激活
  └─ 文件组织清理
        │
        ▼
Phase 1.5(确认后)
  ├─ SkillScout UI工具侦察
  ├─ 设计系统建立
  ├─ QA产品页mobile-first
  └─ 微信/PWA/语音/分享
```

**本次修复是Phase 1.5的前置条件,必须先做。修复后无缝进入Phase 1.5。**

---

## 执行清单

| # | 操作 | 文件 | 风险 |
|---|------|------|------|
| 1 | 修复 `/` 路由→恢复管理后台 | api_server.py | 低 |
| 2 | 新增 `/landing` 路由 | api_server.py | 低 |
| 3 | 新增 `/static/` 路由(CSS访问) | api_server.py | 低 |
| 4 | 重命名 f056_viewer.html → premium_viewer.html | 文件系统 | 需检查引用 |
| 5 | 新增 `/premium` 路由 | api_server.py | 低 |
| 6 | 备份 qa_public.html + qa_modern.html → archive/ | 文件系统 | 低 |
| 7 | design_system.css 接入 landing.html | landing.html | 低 |
| 8 | 检查 training_camp_landing.html 引用 | grep | 低 |
| 9 | 冒烟测试 | auto_tester | 低 |

**总工时: 1.5小时(9项操作)**

---

**请确认: 是否立即执行这9项修复? 修复后自动进入Phase 1.5 UI升级。**
