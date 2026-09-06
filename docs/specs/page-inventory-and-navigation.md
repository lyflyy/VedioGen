# 页面清单与导航规格 v0.1

- 状态：待项目方评审
- 版本：0.1
- 日期：2026-09-05
- 适用范围：P0 桌面 Web 与移动端轻量确认
- 关联：[创作体验](experience-spec.md)、[UI 架构](ui-architecture.md)、[设计系统](design-system.md)

## 1. 用户与入口

| 用户 | 默认入口 | 主要任务 | P0 权限 |
| --- | --- | --- | --- |
| Creator | `/projects` | 输入想法、选择策略、确认 Brief/Storyboard、生成和下载 | 本机单用户 |
| Model Admin | `/admin/model-providers` | 配置模型、Key、路由、测试和诊断 | 本机单管理员 |
| Viewer（外部测试前） | `/admin/model-invocations` | 查看脱敏配置和调用 | P0 只保留角色边界，不实现 |

P0 不做营销首页。访问根路由时，有 Creator 上下文就进入 `/projects`；没有时进入最小本地初始化页。

## 2. 全局站点图

```text
/
├─ /projects
│  ├─ /new
│  └─ /:projectId
│     ├─ /intake
│     ├─ /strategy
│     ├─ /brief
│     ├─ /storyboard
│     ├─ /generation
│     └─ /final
├─ /account-brief
└─ /admin
   ├─ /model-providers
   ├─ /credentials
   ├─ /deployments
   ├─ /routing
   ├─ /playground
   └─ /invocations
```

版本、Shot 和调用详情优先用路径或 search params 表达：

```text
/projects/:id/storyboard?version=:versionId&shot=:shotId
/projects/:id/generation?run=:runId
/admin/invocations?status=failed&capability=creative-advisor
/admin/invocations/:invocationId
```

## 3. Creator 页面清单

| 路由 | 页面目的 | 主要内容 | 主要动作 | P0 |
| --- | --- | --- | --- | --- |
| `/projects` | 找到或开始工作 | 最近项目、状态、内容方向、更新时间、成片状态 | `新建项目` | 必须 |
| `/projects/new` | 用最低成本表达想法 | 多行想法、素材上传、平台、时长、真实/概念、Account Brief | `获取创意建议` | 必须 |
| `/account-brief` | 保存账号长期上下文 | 账号定位、受众、语气、栏目、禁用内容、日更节奏 | `保存账号资料` | 必须，单份 |
| `/:id/intake` | 查看已提取事实和素材 | 输入记录、Project Facts、素材、冲突 | `继续获取建议` | 必须 |
| `/:id/strategy` | 与 AI 讨论并选择方向 | Conversation、诊断、2-3 个 Proposal、事实/依据 | `采用方案` | 必须 |
| `/:id/brief` | 固化内容策略 | 可编辑 Brief、版本、影响摘要 | `确认并生成脚本` | 必须 |
| `/:id/storyboard` | 编辑脚本与原子镜头 | 9:16 舞台、Shot 时间线、Inspector、总时长 | `确认并生成` | 必须 |
| `/:id/generation` | 监控和恢复生成 | Run、Shot 状态、预览、失败、重试/降级 | `取消生成` 或 `查看成片` | 必须 |
| `/:id/final` | 检查和取得结果 | 成片播放器、版本、质量摘要、下载 | `下载视频` | 必须 |

### 3.1 项目列表

- 默认按最近更新排序，状态筛选为 `全部`、`待确认`、`生成中`、`需处理`、`已完成`。
- 项目项使用真实缩略图时可以用 Card；没有缩略图时使用密集 List，不生成装饰占位图。
- 项目名称、内容方向、当前阶段、更新时间和下一动作始终可扫描。
- 生成中的项目通过 SSE 更新，但不得引发列表跳序；只在刷新或用户明确排序时重排。

### 3.2 新建项目

- 页面焦点是一个明确多行输入框，不使用欢迎 Hero。
- 上传区支持图片、视频和多角度图片；显示上传进度、失败与移除。
- 高级字段默认折叠，普通用户无需理解模型或渲染参数。
- 车型名称存在冲突时不在此页阻塞，进入 Advisor 由事实面板确认。

### 3.3 Strategy 工作台线框

```text
┌────────── Creator nav ──────────┬────────────────────────────────────────────┐
│ Projects / Recent               │ Project header + save/version/run status   │
│                                 ├────────────────────────────────────────────┤
│                                 │ 资料  策略  Brief  脚本分镜  生成  成片     │
├──────────────┬──────────────────┼───────────────────────────┬────────────────┤
│ Conversation │ Diagnosis        │ Proposal compare          │ Facts/Evidence │
│ 320px        │ opportunity/risk │ 2-3 alternatives         │ 336px          │
│ input bottom │ rationale        │ adopt / merge / revise    │ conflicts      │
└──────────────┴──────────────────┴───────────────────────────┴────────────────┘
```

中央可用宽度不足时，Diagnosis 合入 Proposal 顶部；右侧变 Drawer。不能把三列机械压缩到导致长中文溢出。

### 3.4 Storyboard 工作台线框

```text
┌──────────────── Project header / step bar / duration / version ──────────────┐
├──────────────────────────┬───────────────────────────────┬───────────────────┤
│ Shot timeline            │ 9:16 video stage              │ Shot inspector    │
│ fixed thumbnails         │ preview + safe-area overlay   │ selected shot     │
│ status + reorder         │ stable playback controls      │ fields + source   │
├──────────────────────────┴───────────────────────────────┴───────────────────┤
│ affected items / resource level                         Confirm and generate │
└───────────────────────────────────────────────────────────────────────────────┘
```

- 选中 Shot 后只更新舞台和 Inspector，不改变时间线尺寸。
- 旁白、字幕和声音按分组编辑，默认不同时展开所有高级字段。
- 删除、重新生成、前移和后移使用图标；“确认并生成”保留文本。

### 3.5 Generation 与 Final

- Generation 首屏显示总状态和 Shot 列表，不用只有一个百分比的等待页。
- 失败 Shot 就地提供 `重试`、`使用降级方案`、`返回修改`。
- Final 的真实视频必须第一屏可播放；生成摘要与下载在旁侧/下方，不能用说明卡遮挡成片。
- 历史版本可选择但默认当前版本；下载文件显示格式、尺寸、时长和预计大小。

## 4. Admin 页面清单

| 路由 | 页面目的 | 列表/主区 | 详情/编辑 | 主要动作 |
| --- | --- | --- | --- | --- |
| `/admin/model-providers` | 管理平台连接 | 名称、类型、Base URL、状态、Deployment、健康 | Provider 表单、引用 | `添加平台` |
| `/admin/credentials` | 管理 Secret 引用 | 别名、Provider、末四位、状态、轮换/成功时间 | 一次性输入、测试、轮换、撤销 | `添加 API Key` |
| `/admin/deployments` | 管理可路由模型 | Provider、模型 ID、能力、限制、健康、Ready | 能力/价格/限制、Probe 结果 | `添加部署` |
| `/admin/routing` | 发布业务能力路由 | 能力别名与 Published 状态 | Primary、Fallback、规则、Draft Diff | `验证草稿` / `发布路由` |
| `/admin/playground` | 执行固定探针 | Fixture、能力、Draft/Published | 流、Schema、工具、Fallback 结果 | `运行测试` |
| `/admin/invocations` | 诊断调用 | 时间、能力、模型、状态、耗时、成本 | 路由链、重试、Token、脱敏内容 | 无默认写动作 |

### 4.1 Admin 列表模式

```text
┌─ Admin nav ─────┬─────────────────────────────────────────────────────────────┐
│ Model providers │ Page title                                      Add action │
│ API Keys        ├─────────────────────────────────────────────────────────────┤
│ Deployments     │ Filters / search / saved view                               │
│ Routing         ├─────────────────────────────────────────────────────────────┤
│ Playground      │ Resource table                                               │
│ Invocations     │ status | identity | relation | health | updated | actions   │
│                 ├─────────────────────────────────────────────────────────────┤
│ Creator app     │ Pagination                                      Detail pane │
└─────────────────┴─────────────────────────────────────────────────────────────┘
```

- 无复杂 Dashboard 首页；管理员进入后直接处理资源和状态。
- Provider、Credential、Deployment 是不同对象，不用一个“模型配置”巨型页面混合。
- 资源详情可使用右侧 Drawer，长编辑和 Routing 发布使用独立页面。

### 4.2 Routing 页面

- 左侧选择业务能力，右侧显示 Published 和 Draft 两个版本上下文。
- Primary 用单选 Select；Fallback 用有序列表和拖动手柄。
- 不满足能力、未 Ready、重复或 Key 不可用时就地阻止保存/发布。
- 页面底部固定显示未保存、验证状态、变更说明和发布动作。
- 发布前显示字段级 Diff 和 Fixture 结果；回滚是版本历史中的危险动作。

### 4.3 API Key 页面

- 永远不提供“查看完整 Key”。
- 添加/轮换表单明确显示 Secret 只提交一次；成功后只显示末四位。
- 撤销前展示被哪些 Deployment 和 Published Route 引用。
- `测试连接` 是低成本探针，不自动发布或更换路由。

### 4.4 Invocation 页面

- 默认筛选最近 24 小时；支持能力、Provider、模型、状态、Project/Run 和时间范围。
- 详情先显示摘要、路由链、重试/Fallback、Token/费用/耗时，再显示折叠的脱敏输入输出。
- 错误显示标准错误码、Provider 请求 ID、correlation ID 与建议动作。

## 5. 导航规则

- 当前导航项同时使用位置、背景/边框和 `aria-current`，不只改变颜色。
- 项目步骤可以回看；未完成步骤不可伪装成可进入状态。
- 修改已确认上游时，先展示哪些下游版本会过期。
- 浏览器返回/前进恢复 Tab、筛选、版本和 Shot 选择，不重复提交 Mutation。
- Breadcrumb 只在超过两级层次的详情页使用，不和步骤栏重复。
- 全局命令面板延后到 P1；P0 不为少量页面制造隐藏导航。

## 6. 响应式行为

| 宽度 | Creator | Admin |
| --- | --- | --- |
| `>=1280` | 左导航 + 完整工作台 + Inspector | 左导航 + 表格/详情 |
| `768-1279` | 导航收起；Inspector Drawer；时间线可横向滚动 | 导航收起；表格容器横向滚动；详情 Drawer |
| `<768` | 单列 Tabs；查看、回复、确认、下载 | P0 只读查看核心状态；写配置提示使用桌面 |

移动端不能把桌面三列简单缩小。表格可改为带 Label 的属性列表；涉及 Key、Routing 发布和复杂 Storyboard 编辑的写操作在 P0 桌面完成。

## 7. Content Pack 扩展

- 页面和导航名称保持稳定，不按“摩托车/育儿”建立完全不同应用。
- Content Pack 可提供 Intake 字段、Proposal 评分维度、Shot Inspector 扩展区、示例和预览 Overlay。
- 垂直字段只能插入声明的 Slot，不能改写 Shell、版本确认和生成状态。
- 育儿 Pack 验收时不显示车型、转速、3D 环绕或 Blender 字段。

## 8. 开放问题

1. Account Brief 在 P0 是全局单份还是按账号多份；当前按单份实现。
2. 项目列表使用 List 还是带真实缩略图的紧凑 Grid；建议素材可用时 Grid，否则 List。
3. Admin 在小屏是否完全禁止写操作；建议 P0 禁止 Routing/Key 写操作，其余按能力逐页降级。

## 9. 验收标准

- 任一页面都能回答“我在哪、当前状态是什么、下一步是什么”。
- 创作者主链路最多一个全局导航层和一个项目步骤层，不出现第三套常驻导航。
- Creator 不显示 Provider、Key、Token、DAG；Admin 不显示创作步骤。
- 页面清单中的每个 P0 页面都有 Default、Loading、Empty、Error、Permission/Disabled 状态设计。
- 四个关键线框（Projects、Strategy、Storyboard、Admin Routing）经项目方评审后才进入视觉实现。
