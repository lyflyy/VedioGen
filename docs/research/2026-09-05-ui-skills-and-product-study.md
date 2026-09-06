# 企业化 UI、开源产品与 Agent Skills 调研

- 状态：待项目方评审
- 调研日期：2026-09-05
- 调研方式：`npx skills find`、skills.sh 排行页、已认证 GitHub CLI `gh search repos`、`gh repo view` 和 `gh api`
- 范围：创作者工作台、模型管理后台、设计系统、可访问性、React 性能和 UI 测试
- 说明：Star 与安装量为调研日快照，会变化；正式采用依赖时必须重新锁定版本与许可证

## 1. 结论

本项目需要两套共享设计语言但职责隔离的产品界面：

1. **创作者工作台**：围绕“想法 -> 策略 -> Brief -> 脚本分镜 -> 生成 -> 成片”的线性任务流，隐藏 Provider、模型和节点概念。
2. **管理控制台**：围绕资源清单、配置草稿、探针测试、发布/回滚、调用追踪和故障处理，允许更高信息密度。

不整体复刻某个开源产品前端。采用 Radix Primitives + shadcn/ui 的开源代码分发模式作为基础，借鉴 Dify、Langfuse、Supabase、Temporal UI 和 Ant Design Pro 的成熟信息架构，再实现本项目自己的 Creative Advisor、Storyboard、Shot Run 和 Model Routing 领域组件。

## 2. Skills 检索与核验

### 2.1 已执行检索

```powershell
npx skills find "frontend design"
npx skills find "enterprise dashboard"
npx skills find "design system"
npx skills find "vercel react"
npx skills find "web design guidelines"
npx skills find "accessibility"
npx skills find "playwright ui testing"
```

skills.sh 排行页中可以检索到 Anthropic 与 Vercel 的高安装量 Skill。搜索结果不能单独证明质量，因此又使用 `gh repo view`、`gh api` 检查来源仓库、Skill 内容、维护状态和许可证。

### 2.2 已安装并计划使用

| Skill | 安装量快照 | 源仓库 Star | 核验结论 | 本项目用途 |
| --- | ---: | ---: | --- | --- |
| `anthropics/skills@frontend-design` | 855.9K | 174,324 | 官方来源；Skill 自带 Apache-2.0 | 建立领域化视觉方向，避免通用 SaaS 模板感；编码前与截图评审时使用 |
| `vercel-labs/agent-skills@vercel-react-best-practices` | 690.5K | 30,856 | Vercel 官方；Skill 声明 MIT | React/Next.js 编码、评审和性能门 |
| `vercel-labs/agent-skills@web-design-guidelines` | 608.7K | 30,856 | Vercel 官方；Skill 文件未声明许可证 | 只作为 UI 代码审查流程使用，不复制其内容进产品代码 |
| `addyosmani/web-quality-skills@accessibility` | 50.3K | 2,753 | 高信誉维护者；仓库与 Skill 为 MIT | WCAG 2.2、键盘、语义结构、Lighthouse/axe 审查 |

安装命令：

```powershell
npx skills add anthropics/skills@frontend-design -g -y
npx skills add vercel-labs/agent-skills@vercel-react-best-practices -g -y
npx skills add vercel-labs/agent-skills@web-design-guidelines -g -y
npx skills add addyosmani/web-quality-skills@accessibility -g -y
```

四项已安装到用户级 `.agents/skills/`。Skills CLI 同时报告了 Codex 安装成功和 PromptScript 不支持全局安装；后者不影响本项目使用，但不能误写为所有 Agent Harness 都安装成功。

### 2.3 明确不采用的搜索结果

- `enterprise dashboard` 搜索结果最高仅 240 次安装，多数低于 100，不作为架构依据。
- Playwright 相关 Skill 的通用搜索结果最高 135 次安装，缺乏足够成熟的跨项目来源；P0 直接使用 Playwright 官方测试库、axe 和项目自己的验收规则。
- `arvindrk/extract-design-system` 虽有 128.5K 安装，但源仓库约 204 Star，且“抽取其他网站 Token”不是建立独立产品语言的必要步骤，不安装。
- 不因安装量高而同时安装多套互相冲突的审美 Skill；视觉决策由本项目设计规范统一约束。

## 3. 可检查的开源 UI 样本

| 项目 | Star 快照 | 许可快照 | 观察到的结构 | 借鉴 | 不照搬 |
| --- | ---: | --- | --- | --- | --- |
| Dify | 154,496 | 自定义 Dify Open Source License | Workspace、应用、数据、工具、模型 Provider 分区；Next.js route groups 与详情侧栏 | 创作区和系统配置区隔离；Provider 清单与配置分层 | 节点图不暴露给普通创作者；不复制其多租户代码 |
| Langfuse | 34,218 | 仓库许可需按目录复核 | Organization/Project 层级；Trace、Prompt、Dataset、Playground 与可筛选详情 | 调用记录、路由版本、过滤器、详情抽屉和 Trace 关联 | 观测模型不能成为本项目业务状态来源 |
| Supabase | 108,862 | Apache-2.0 | Organization/Project 上下文、稳定侧栏、设置分组、密集工具页面 | 清晰的上下文切换、资源列表到详情、危险操作分区 | 不复制数据库产品的导航深度 |
| Appsmith | 40,816 | Apache-2.0 | 编辑器与管理能力分离，内部工具页面强调高效操作 | “创作任务”和“系统治理”分壳 | 不引入通用低代码画布 |
| ToolJet | 40,846 | AGPL-3.0 | 应用编辑、数据源、工作流与企业治理 | 配置对象列表、状态和权限思路 | 不复制 AGPL 代码，不采用通用 Builder 心智模型 |
| Temporal UI | 430 | MIT | Workflow 列表、Run 详情、Event History、重试/终止 | Shot/Generation Run 的状态、事件、重试和失败详情 | 不向创作者显示底层事件噪声 |
| Ant Design Pro | 38,740 | MIT | 企业后台脚手架、菜单、表格、表单和权限 | 管理后台密度、批量操作、筛选布局 | 不整体采用主题，避免 creator/admin 变成同一种后台模板 |

GitHub CLI 还搜索到 `supabase/supabase`、`ToolJet/ToolJet`、`mlflow/mlflow` 等 AI/企业平台，以及 `ant-design/ant-design-pro` 等后台项目。最终样本按与本产品任务的相关性选取，不按 Star 机械排序。

## 4. 设计系统候选

| 项目 | Star 快照 | 许可 | 判断 |
| --- | ---: | --- | --- |
| shadcn/ui | 123,066 | MIT | **采用代码分发模式**；组件代码归项目所有，便于形成独立视觉语言 |
| Radix Primitives | 19,243 | MIT | **采用无样式可访问性原语**；用于 Dialog、Popover、Tabs、Tooltip、Select 等交互基础 |
| Ant Design | 99,393 | MIT | 作为企业表格/表单模式参考，不与 shadcn 混装整套组件体系 |
| Carbon | 9,428 | Apache-2.0 | 作为状态、数据表格、无障碍和企业信息密度参考 |
| PatternFly React | 861 | MIT | 作为复杂管理任务与批量操作参考，不作为 P0 运行依赖 |
| Storybook | 91,011 | MIT | **采用开发工具**；隔离展示领域组件、状态矩阵与视觉基线 |
| Playwright | 95,648 | Apache-2.0 | **采用测试工具**；跨 Chromium、Firefox、WebKit 验证主路径 |
| axe-core | 7,475 | MPL-2.0 | **采用测试工具**；自动发现部分可访问性问题，不能替代人工键盘检查 |
| Lucide | 24,361 | ISC（需按包复核） | **采用图标基础**；统一熟悉工具图标，不手绘重复 SVG |
| TanStack Table | 28,408 | MIT | 暂不锁定；管理表格超过基础能力时再做 POC |

选择原则：一个应用只能有一个基础组件体系。混用 Ant Design、MUI、shadcn 等整套组件会产生 Token、交互和包体冲突。P0 使用 Radix/shadcn，缺失的复杂领域组件在其上组合；如果后续数据表格需求显著增长，再单独评估 TanStack Table，不提前引入第二套视觉体系。

## 5. 可复用 UI 方法论

### 5.1 对创作者

- 用任务步骤和明确产物建立方向感，不把聊天记录当作唯一状态。
- AI 建议、用户事实、公开依据和创意假设必须视觉区分。
- 主工作区只保留一个主要动作；次要动作进入局部工具栏或菜单。
- 高成本动作前显示影响范围、资源等级和确认版本。
- 生成过程按 Shot 呈现，可局部重试；总体进度不能掩盖失败镜头。
- 空状态给出下一步操作，失败状态提供恢复路径，不使用营销文案。

### 5.2 对管理员

- 列表负责扫描和筛选，详情页/侧栏负责诊断，编辑页负责变更；不在一张巨型表单里混合三者。
- 所有配置变更先保存为 Draft，再验证、对比并发布不可变版本。
- Secret 只写不读；界面仅显示别名、末四位和状态。
- 危险操作固定在单独区域并说明影响对象。
- 调用记录允许从汇总下钻到一次调用，但默认折叠大段 Prompt/响应。

### 5.3 视觉方法

- 企业化不是“大量卡片 + 蓝紫渐变”，而是稳定布局、清晰层级、状态一致、可预测操作和完整失败处理。
- 摩托车领域感只在预览画面、封面、镜头时间线和少量强调色体现；工具栏、表格和管理页保持克制。
- 不做营销首页。登录后第一屏就是项目列表或最近项目。
- 创作者工作台允许媒体画面成为视觉焦点；管理后台由数据和状态成为视觉焦点。

## 6. 推荐采用边界

### Adopt

- Radix Primitives 与 shadcn/ui 的组件代码分发方式。
- Lucide 图标；图标按钮必须有 Tooltip 和可访问名称。
- Storybook 的组件状态目录，以及 Playwright + axe 的页面级可访问性与交互测试。
- Next.js route groups 隔离 creator/admin shell。

### Adapt

- Dify/Supabase 的资源与设置导航，改成本项目的 Provider、Credential、Deployment 和 Routing Policy。
- Langfuse 的 Trace/详情组织，改成 Invocation 与 Project/Run 追溯。
- Temporal UI 的运行详情，改成 Generation Run + Shot Run 两级状态。
- Ant Design Pro 的管理表格密度，只借鉴模式，不安装整套 UI。

### Reject

- 直接 Fork Dify、Appsmith、ToolJet 或 Ant Design Pro 作为产品前端。
- 向普通用户暴露 DAG、Prompt 参数、Token 或物理模型名称。
- 嵌套卡片、装饰渐变、无意义动效和所有页面共用 Dashboard 卡片模板。
- 为“企业感”提前加入计费、组织架构或复杂 RBAC；这些能力保留扩展边界，P0 不实现。

## 7. 来源与复核信息

- Skills 排行与安装量：[skills.sh](https://skills.sh/)，访问日期 2026-09-05。
- Skills 源：[Anthropic Skills](https://github.com/anthropics/skills)、[Vercel Agent Skills](https://github.com/vercel-labs/agent-skills)、[Web Quality Skills](https://github.com/addyosmani/web-quality-skills)。
- 产品源：[Dify](https://github.com/langgenius/dify)、[Langfuse](https://github.com/langfuse/langfuse)、[Supabase](https://github.com/supabase/supabase)、[Appsmith](https://github.com/appsmithorg/appsmith)、[ToolJet](https://github.com/ToolJet/ToolJet)、[Temporal UI](https://github.com/temporalio/ui)、[Ant Design Pro](https://github.com/ant-design/ant-design-pro)。
- 设计系统源：[shadcn/ui](https://github.com/shadcn-ui/ui)、[Radix Primitives](https://github.com/radix-ui/primitives)、[Ant Design](https://github.com/ant-design/ant-design)、[Carbon](https://github.com/carbon-design-system/carbon)、[PatternFly React](https://github.com/patternfly/patternfly-react)。
- 工程工具源：[Storybook](https://github.com/storybookjs/storybook)、[Playwright](https://github.com/microsoft/playwright)、[axe-core](https://github.com/dequelabs/axe-core)、[Lucide](https://github.com/lucide-icons/lucide)、[TanStack Table](https://github.com/TanStack/table)。
- 关键仓库提交快照记录在本轮 GitHub CLI 输出中；依赖落盘时由 lockfile 与 `THIRD_PARTY_NOTICES` 再次固定。

## 8. 开放问题

1. 项目品牌名称与 Logo 尚未确定，P0 先使用工作名称，不据此冻结品牌资产。
2. 深色模式是否作为 P0 必需项；建议结构支持，但 P0 只验收浅色主路径和视频预览暗色舞台。
3. 外部测试前是否需要真正的 Workspace/成员权限；当前仍按本机单用户和单管理员执行。
