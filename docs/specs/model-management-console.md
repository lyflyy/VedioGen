# 模型管理后台体验规格 v0.1

- 状态：待项目方评审
- 版本：0.1
- 日期：2026-09-05
- 产品决策：模型与 Key 必须通过界面配置
- 负责人：待指定

## 1. 目标

内部管理员可以在不修改代码、配置文件或重启业务服务的情况下完成：

- 添加和停用模型平台。
- 写入、测试、轮换和撤销 API Key。
- 配置物理模型及其能力、价格和限制。
- 把 `creative-advisor` 等业务能力映射到主模型和备用模型。
- 发布、验证和回滚路由配置。
- 查看调用、错误、Fallback、耗时和费用。

该后台是内部运营能力，与普通创作者的创作工作台隔离。普通用户只看到生成状态和资源等级，不看到 Provider、物理模型或 Key。

## 2. 导航

```text
管理后台
  -> 模型平台
  -> API Key
  -> 模型部署
  -> 能力路由
  -> 测试台
  -> 调用记录
```

P0 可通过独立 `/admin` 入口提供本机管理员访问，不与普通创作步骤混排。外部部署前必须增加管理员身份和权限。

## 3. 页面

### 3.1 模型平台

列表字段：平台名称、适配类型、Base URL、区域、启用状态、可用 Deployment 数、最近健康状态和更新时间。

创建/编辑字段：

- 显示名称与稳定 Provider ID。
- 适配器类型，例如 LiteLLM 原生 Provider 或 OpenAI-compatible。
- Base URL、组织/项目标识等非秘密连接参数。
- 网络区域、默认超时、启用状态。
- 自定义 Headers 只允许引用 Secret，不允许在列表显示值。

删除前检查是否被有效路由引用；存在引用时只能停用或先迁移。

### 3.2 API Key

列表只显示 Key 别名、Provider、末四位、状态、创建/轮换时间、最近成功时间和最近错误。永远没有“显示完整 Key”功能。

支持动作：

- `添加 Key`：在一次性密码输入框写入 Secret Store。
- `测试连接`：选择一个低成本模型执行最小请求。
- `轮换`：写入新 Key，测试通过后激活并将旧 Key 标记为 draining。
- `撤销`：停止新请求，确认无执行中请求后失效。

浏览器提交后立即清空输入值；服务端响应不得包含明文或可逆密文。

### 3.3 模型部署

Deployment 是“某个平台、某个物理模型、某个 Key 引用和一组限制”的可路由单元。

字段包括：

- 显示名称、Provider、物理模型 ID、Credential Ref。
- 文本、视觉、Streaming、Tool Calling、Structured Output 等能力开关。
- 上下文/输出上限、并发、超时、速率限制。
- 输入/输出/缓存等计价单位和价格版本。
- 健康状态、最后探针结果和是否允许生产路由。

管理员保存后必须先运行能力探针，探针通过才能标记为 `ready`。

### 3.4 能力路由

左侧列出业务能力别名，右侧编辑当前能力：

- Primary Deployment。
- 有顺序的 Fallback 列表，支持拖动排序。
- 超时、总尝试次数、预算等级和允许 Fallback 的错误类型。
- Streaming、结构化输出、视觉等不可缺少的能力要求。

界面使用选择器和有序列表，不使用节点画布。系统即时阻止以下无效配置：

- Deployment 不满足能力要求。
- Primary 或 Fallback 已停用/未通过探针。
- 同一 Deployment 重复出现。
- 没有 Primary、预算为空或重试次数超过系统上限。

路由修改只形成 Draft。管理员必须填写变更说明并点击 `发布`，新版本才对新请求生效。

### 3.5 测试台

管理员选择能力别名、Draft/Published 路由和固定测试 Fixture，执行：

- 连接与鉴权测试。
- Streaming 测试。
- 结构化输出 Schema 测试。
- 工具调用测试。
- 中文创意与事实保持样例。
- 主 Provider 故障时的 Fallback 演练。

结果显示真实路由链、Token、耗时、标准错误和费用，但 Prompt/响应中的 Secret 必须脱敏。P0 不允许测试台输入任意系统命令或直接修改业务数据。

### 3.6 调用记录

按时间、能力、Provider、模型、状态和 Project/Run 查询。详情显示路由版本、Prompt 版本、Token、耗时、费用、重试和 Fallback 链。

原始输入输出默认折叠，并按数据保存策略限制访问；Key 和鉴权 Header 永不进入记录。

## 4. 发布与回滚

```text
编辑 Draft
  -> 自动配置校验
  -> 运行选定 Fixture
  -> 查看差异和成本
  -> 填写变更说明
  -> 原子发布 RoutingPolicyVersion
  -> 新请求使用新版本
  -> 监控
  -> 必要时一键回滚上一版本
```

执行中的 Run 始终使用启动时快照，发布或回滚不能中途更换模型。紧急停用有安全优先权：阻止新请求后，执行中请求按超时或取消规则结束。

## 5. 状态与权限

- Provider：`draft`、`active`、`disabled`。
- Credential：`draft`、`active`、`draining`、`revoked`、`error`。
- Deployment：`draft`、`testing`、`ready`、`degraded`、`disabled`。
- Routing Policy：`draft`、`published`、`superseded`、`rolled-back`。

P0 是本机单管理员模式。进入外部测试前至少拆分 `model-admin` 和 `viewer`：前者可写入 Key 和发布路由，后者只能查看脱敏配置与调用记录。

## 6. 失败与保护

- 保存 Key 失败：输入值不进入日志，提示重新输入。
- 探针失败：Deployment 保持不可发布，展示标准错误和建议动作。
- 发布冲突：使用版本号做乐观锁，要求刷新后重新合并。
- 路由无可用模型：阻止发布，不允许把流量发布到空路由。
- 回滚目标引用已撤销 Key：阻止一键回滚并提示先修复凭证。
- 费用配置缺失：允许开发测试，但禁止标记为生产就绪。

## 7. 后端管理动作

管理界面通过正式管理 API 完成配置，不直接写数据库：

| 动作 | API 意图 | 关键约束 |
| --- | --- | --- |
| 新增/编辑 Provider | `POST/PATCH /admin/model-providers` | 稳定 ID、适配器和 Base URL 校验 |
| 写入/轮换 Key | `POST /admin/model-credentials` | 请求只写；响应只返回 Credential ID 和末四位 |
| 测试 Deployment | `POST /admin/model-deployments/{id}/probe` | 返回能力、延迟和标准错误，不返回 Key |
| 保存路由草稿 | `POST /admin/model-routing/drafts` | 乐观锁和完整配置校验 |
| 发布路由 | `POST /admin/model-routing/{routingDraftId}/publication` | 原子生成不可变版本 |
| 回滚路由 | `POST /admin/model-routing/{routingPolicyVersionId}/rollback` | 先验证目标版本所有引用仍可用 |
| 查看调用 | `GET /admin/model-invocations` | 分页、筛选、脱敏和访问控制 |
| 查看路由版本 | `GET /admin/model-routing/versions` | 分页返回不可变版本，不混入 Draft |
| 运行/查看测试 | `POST/GET /admin/model-playground-runs` | 只允许固定 Fixture；结果和路由链脱敏 |
| 查看调用详情 | `GET /admin/model-invocations/{id}` | 单独鉴权；返回路由链与脱敏输入输出 |

这些意图已经在 [OpenAPI 契约](api.openapi.yaml) 中冻结为具体请求/响应和错误结构；实现变更必须先更新契约并通过 Lint。

## 8. P0 范围

P0 必须实现模型平台、API Key、模型部署、能力路由、测试台和最小调用记录六个页面。暂不实现复杂 Dashboard、自动质量路由、团队级 Key 和 BYOK。

管理 UI 可以先使用服务端表单和基础表格；配置发布和 Key 处理必须调用正式 API，不能只操作本地配置文件。

## 9. 验收标准

- 管理员完全通过界面添加两个 Provider 和对应 Key。
- Key 保存后任何页面、网络响应、数据库查询和日志均无法取得明文。
- 管理员通过界面把 `creative-advisor` 从平台 A 切换到平台 B，无需改代码或重启。
- Draft 未发布时不影响新请求；发布后只有新请求使用新路由。
- Fallback 演练可见平台 A 失败、平台 B 成功的完整调用链。
- 一键回滚恢复上一版本，新运行记录引用正确版本。
- 普通创作界面不显示 Provider、模型名和 Key 管理入口。

## 10. 待评审项

1. P0 是否只允许本机访问 `/admin`，外部测试前再增加管理员登录。
2. 管理后台视觉是集成在同一 Web 应用，还是使用独立部署入口；建议同一代码库、独立路由与权限。
3. 调用记录是否允许管理员查看完整 Prompt/响应，还是默认只允许查看脱敏摘要。
