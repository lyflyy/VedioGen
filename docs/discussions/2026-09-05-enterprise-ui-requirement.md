# 企业化 UI 与 Skills 要求讨论记录

- 日期：2026-09-05
- 状态：已记录，设计方案待评审
- 来源：项目方本轮补充要求

## 项目方要求

- 整体 UI 必须现代、合理、有清晰逻辑，并具备真实企业服务的完整度。
- 不能孤立设计，需要通过 GitHub CLI 调研高关注项目和成熟实现。
- 需要搜索、核验并使用有信誉的 Agent Skills 来约束后续前端实现和评审。
- 创作者流程与配置管理能力都必须在界面上得到合理规划。

## 本轮解释

“企业化”在 P0 中解释为：稳定的信息架构、一致的设计系统、可预测的状态和操作、完整的空/加载/错误/恢复状态、可追溯的配置发布，以及可访问、响应式和可自动测试的实现。它不等同于提前加入计费、组织架构和复杂权限。

创作者和管理员共享 Token、基础组件和质量门，但使用独立导航：

- 创作者按内容生产阶段工作，不看到底层模型、Key 或工作流节点。
- 管理员按 Provider、Credential、Deployment、Routing、测试和调用记录工作，不混入创作步骤。

## 已执行工作

- 使用 `npx skills find` 检索前端设计、企业后台、设计系统、React、可访问性和 Playwright 方向。
- 使用 skills.sh 排行页与 GitHub CLI 核验安装量、仓库热度、来源、维护状态和许可证。
- 安装 Anthropic Frontend Design、Vercel React Best Practices、Vercel Web Design Guidelines 和 Addy Osmani Accessibility 四项 Skill。
- 调研 Dify、Langfuse、Supabase、Appsmith、ToolJet、Temporal UI、Ant Design Pro、shadcn/ui、Radix、Carbon 和 PatternFly。
- 形成 UI 架构、设计系统、页面导航与验收规格；它们将成为 P0 前端实现的约束。
- 将 OpenAPI 从 31 条路径、38 个操作扩展到 39 条路径、47 个操作，补齐 Account Brief、工作区恢复、Artifact 下载、路由历史、测试台和调用详情。

## 决策影响

- 编码前新增 UI Gate：页面清单、低保真线框、Token 与关键状态必须通过评审。
- 采用 Radix + shadcn 的单一基础组件体系，不直接 Fork 一个通用后台。
- P0 必须同时完成创作者关键链路和 `/admin` 六个管理页面，不能只做漂亮的生成首页。
- UI 验收纳入 Playwright、axe、截图基线、键盘操作、窄屏和长中文内容测试。

## 待项目方评审

1. 是否接受 creator/admin 两套独立导航壳。
2. 是否接受“编辑工作台采用暗色媒体舞台，其余界面以中性浅色为主”的视觉方向。
3. 是否接受桌面优先、移动端只完成查看/回复/确认的 P0 边界。
4. 是否接受页面清单与核心线框通过后再开始工程脚手架。
