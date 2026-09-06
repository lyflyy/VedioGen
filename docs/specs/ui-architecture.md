# UI 架构规格 v0.1

- 状态：待项目方评审
- 版本：0.1
- 日期：2026-09-05
- 产品负责人：项目方（具体负责人待指定）
- 设计/前端负责人：待指定
- 依据：[创作体验规格](experience-spec.md)、[模型管理后台体验规格](model-management-console.md)、[UI 与 Skills 调研](../research/2026-09-05-ui-skills-and-product-study.md)

## 1. 目标

建立可扩展、可测试且职责清晰的 Web UI。P0 需要同时支撑：

- 普通创作者从一句想法到下载成片的主任务。
- AI Creative Advisor 的流式对话、方案比较与两次确认。
- Storyboard 与 Shot 的局部编辑、生成状态和重试。
- 内部管理员通过界面管理模型平台、Key、部署、路由、测试和调用记录。
- 后续新增母婴、育儿等 Content Pack，而不重写导航壳和基础组件。

## 2. 架构原则

1. **按用户任务分壳**：Creator Shell 和 Admin Shell 共享设计系统，不共享导航心智模型。
2. **服务端状态为事实源**：项目、版本、运行和路由配置都由 API 返回；聊天文本和浏览器状态不能替代领域对象。
3. **URL 表达可恢复位置**：项目、阶段、版本和选中 Shot 的关键位置可以刷新、收藏和分享给有权限的人。
4. **结构化输出驱动界面**：Proposal、Brief、Storyboard、Shot Manifest 由已定义 Schema 渲染，不从大模型自由文本中抓取字段。
5. **高成本动作显式提交**：保存草稿、确认版本、开始生成、发布路由和回滚是不同命令。
6. **局部实时、全局可恢复**：流式消息和生成事件提升反馈速度，但刷新后必须从服务端快照恢复。
7. **单一组件基础**：只使用 Radix/shadcn 作为基础视觉组件，领域组件在其上组合。

## 3. 应用壳与路由边界

建议使用一个 Next.js 应用、两个 route group：

```text
apps/web/src/app/
  (creator)/
    projects/
      page.tsx
      new/page.tsx
      [projectId]/
        layout.tsx
        intake/page.tsx
        strategy/page.tsx
        brief/page.tsx
        storyboard/page.tsx
        generation/page.tsx
        final/page.tsx
  admin/
    layout.tsx
    model-providers/
    credentials/
    deployments/
    routing/
    playground/
    invocations/
  error.tsx
  not-found.tsx
```

### 3.1 Creator Shell

- 全局左侧栏：产品标识、项目、最近项目、账号内容资料、收起动作。
- 项目内顶部：返回项目、项目名、保存状态、当前版本、全局运行状态。
- 项目内步骤栏：`资料`、`策略`、`Brief`、`脚本分镜`、`生成`、`成片`。
- 主内容区随任务变化；属性面板只显示当前上下文，不成为第三套导航。

### 3.2 Admin Shell

- 顶部明确显示“管理后台”，防止用户误以为仍在创作项目中。
- 左侧栏固定为 `模型平台`、`API Key`、`模型部署`、`能力路由`、`测试台`、`调用记录`。
- 页面标题区固定容纳标题、说明、主要动作和状态；下方才是筛选与内容。
- Creator 与 Admin 间只提供受权限控制的切换入口，不在项目步骤栏混排。

## 4. 前端分层

```text
src/
  components/
    ui/                 # shadcn/Radix 基础组件，禁止业务请求
    patterns/           # PageHeader、DataTable、FilterBar、DetailPanel、EmptyState
    creator/            # ProposalCompare、BriefEditor、StoryboardTimeline、ShotInspector
    admin/              # CredentialForm、DeploymentProbe、RoutingEditor、InvocationDetail
  features/
    projects/
    advisor/
    briefs/
    storyboards/
    generation/
    model-admin/
  lib/
    api/                # OpenAPI 生成客户端、SSE、错误规范化
    schemas/            # 共享 JSON Schema 派生类型/校验
    telemetry/
  styles/
    tokens.css
    globals.css
```

依赖方向只能从领域组件指向 Pattern，再指向 UI Primitive。`components/ui` 不导入 `features`，页面不直接拼接底层 Radix 状态机。

## 5. 数据与状态

### 5.1 分类

| 状态 | 事实源 | 前端处理 |
| --- | --- | --- |
| Project、BriefVersion、StoryboardVersion | API/PostgreSQL | 服务端加载；命令成功后刷新对应资源 |
| Advisor 流式消息 | API 流 | 增量展示；完成后用结构化 Run 快照校正 |
| Generation/Shot 状态 | `/projects/{id}/events` SSE | 合并事件；断线后带游标重连并重新获取 Run |
| 表单草稿 | 当前页面 | 本地表单状态；离开前检查未保存修改 |
| 面板、Tab、筛选器 | URL search params 优先 | 可恢复、可分享；临时 Hover 不进入 URL |
| Toast、Tooltip、菜单 | 浏览器瞬时状态 | 不进入全局 Store |

P0 不建立一个承载所有数据的全局状态仓库。只有跨多个同级组件且无法由 URL、服务端缓存或表单容器管理的 UI 状态，才允许进入轻量 Context/Store。

### 5.2 API 客户端

- 从 [OpenAPI](api.openapi.yaml) 生成 TypeScript 请求/响应类型，禁止手写重复 DTO。
- 所有错误先规范化为 `code`、`message`、`fieldErrors`、`retryable`、`correlationId`。
- Mutation 携带版本号或 ETag；发生 `409` 时保留用户草稿并展示差异恢复入口。
- API Key 请求体中的秘密字段在提交后立即从表单状态清空，响应类型中不存在秘密值。

### 5.3 SSE

- 页面首次加载以 REST 快照为准，再连接 SSE。
- 事件包含 `eventId`、`projectId`、`runId`、`entityVersion` 和发生时间。
- 重复事件按 `eventId` 去重；旧 `entityVersion` 不覆盖新状态。
- 断线显示非阻塞状态，指数退避重连；超过阈值改为低频轮询并允许手动刷新。
- 页面隐藏时降低视觉更新频率，但不丢事件；回到前台重新拉取快照。

## 6. 领域组件

### 6.1 Creative Advisor

- `ConversationRail`：对话、追问、流式状态和补充输入。
- `ProposalCompare`：2 至 3 个真正不同的策略，支持选择、比较和合并。
- `FactsEvidencePanel`：区分用户事实、公开依据、平台建议和创意假设。
- `ApprovalBar`：显示版本、影响和主动作，不随页面滚动丢失。

### 6.2 Storyboard

- `VideoStage`：固定 `9:16`，仅承载当前镜头/成片预览和播放控制。
- `ShotTimeline`：稳定缩略图尺寸、排序、选中、状态和局部动作。
- `ShotInspector`：编辑当前 Shot，不让一张表单同时编辑全部镜头。
- `DurationSummary`：总时长、Shot 数、字幕/音轨状态和资源等级。

### 6.3 Generation

- `GenerationOverview`：Run 总状态、开始时间、预计范围和取消动作。
- `ShotRunRow`：每个 Shot 的等待、运行、成功、失败、降级与重试。
- `RunEventPanel`：默认显示人能理解的阶段；技术事件在详情中展开。
- `ArtifactVersionPicker`：区分 Preview、Final 和历史版本。

### 6.4 Model Admin

- `ResourceTable`：稳定列、筛选、分页、行操作和批量状态。
- `CredentialForm`：一次性 Secret 输入和明确的提交后状态。
- `ProbeResult`：能力、延迟、标准错误、时间和可发布性。
- `RoutingEditor`：Primary + 有序 Fallback，不使用节点画布。
- `VersionDiff`：Draft 与 Published 的字段级差异。
- `InvocationDetail`：路由、重试、Token、成本、耗时与脱敏输入输出。

## 7. 渲染与性能

- 页面壳、标题和首屏只读数据优先使用 Server Components。
- 对话输入、拖动排序、播放器、表格交互和 SSE 使用边界明确的 Client Components。
- Storyboard 编辑器、播放器编解码辅助和复杂管理表格按路由动态加载。
- 独立请求并行发起，避免串行瀑布；列表页不预取大体积 Prompt、视频和事件历史。
- 缩略图使用固定尺寸与响应式图片；视频只加载当前预览，其他镜头使用 Poster。
- 长列表使用分页；在实际数据证明需要前不引入虚拟滚动。

实现与评审必须使用已安装的 `vercel-react-best-practices` Skill。

## 8. 权限和敏感数据边界

- P0 本机模式仍保留 `creator` 与 `admin` 路由守卫接口；不得用“隐藏菜单”代替服务端授权。
- 外部测试前引入 `model-admin` 与 `viewer` 权限，服务端是最终判定方。
- Credential Secret 不进入 URL、HTML、React props、浏览器持久化、错误上报和日志。
- 原始 Prompt/响应默认折叠，详情请求单独鉴权；列表只返回摘要。
- 上传、外链预览和富文本输出不得执行任意 HTML/脚本。

## 9. 失败、恢复与并发

- 页面级失败保留 Shell 和返回路径；局部失败不替换整个页面。
- 保存失败保留输入，按钮恢复可操作，显示可重试原因和关联 ID。
- 版本冲突不能静默覆盖；提供“查看最新版本”“保留我的副本”动作。
- SSE 断线、Provider 失败和生成失败使用不同状态文案。
- 用户取消 Run 后保留已完成 Shot；重新生成由新 Run 承担，不篡改旧运行记录。

## 10. 可观测性

前端事件最少包含：页面、操作、Project/Run 匿名引用、结果、耗时和 correlation ID。不得采集 Secret、完整 Prompt、上传素材内容或模型原始响应。P0 关注：

- 从新建项目到 Brief 确认的完成率和耗时。
- 从 Storyboard 确认到 Final 的完成率和失败阶段。
- Proposal 选择、合并、坚持用户方向的比例。
- Shot 局部重试、降级和取消次数。
- 路由草稿验证、发布和回滚结果。

## 11. 开放问题

1. UI 前端部署是否与 API 同域；P0 建议同域代理，降低 Cookie、CORS 和 SSE 复杂度。
2. Storyboard 排序在移动端是否允许；建议 P0 移动端只查看、回复和确认。
3. Storybook 是否只作为 CI Artifact，还是也部署内部预览站；不影响 P0 采用。

## 12. 验收标准

- Creator/Admin 两个 Shell 的导航、权限和错误边界独立。
- 所有核心页面都有稳定 URL，刷新后恢复相同项目、阶段和版本。
- 断开 SSE 后可自动恢复，不重复或倒退 Shot 状态。
- API 类型由 OpenAPI 生成，四个核心 Schema 有对应 UI Fixture。
- Key 不出现在响应、DOM、浏览器持久化和前端日志中。
- 关键领域组件具备 Loading、Empty、Success、Error、Disabled 和只读状态。
- 满足 [UI 验收规格](ui-acceptance.md) 的自动与人工质量门。
