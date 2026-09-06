# ADR-0006：采用单一 UI 基础并分离 Creator/Admin Shell

- 状态：待评审
- 日期：2026-09-05
- 决策人：项目方待指定
- 关联：[UI 架构](../specs/ui-architecture.md)、[设计系统](../specs/design-system.md)

## 背景

平台同时服务普通自媒体创作者和内部模型管理员。前者需要低认知负担的内容生产流程，后者需要高信息密度、可追溯和可回滚的配置界面。如果共用一套导航或直接 Fork 通用 AI/低代码平台，普通用户会看到模型节点等实现细节，领域流程也会受外部产品模型限制。

## 决策

1. Web 使用一个 Next.js/React/TypeScript 代码库，建立独立 Creator Shell 与 Admin Shell。
2. UI Primitive 采用 Radix Primitives，组件代码采用 shadcn/ui 分发方式并由项目维护。
3. 图标统一使用 Lucide；样式 Token 由项目定义，不采用外部组件库默认主题。
4. Storybook 用于隔离开发和组件状态评审；Playwright + axe 用于 UI 验收。
5. Ant Design、Carbon、PatternFly、Dify、Langfuse、Supabase 和 Temporal UI 仅作为交互/信息架构参考，不混装其整套组件或 Fork 前端。
6. 普通创作者不接触节点画布、物理模型、Key、Token 和底层 Trace；管理员不在创作步骤中管理基础设施。

## 原因

- Radix 提供成熟的可访问交互原语，shadcn 的代码分发允许建立独立视觉语言。
- 单一基础组件体系减少 Token、焦点行为、包体和升级冲突。
- 分壳保持领域语言清晰，同时允许共用身份、API 客户端、Token 和质量门。
- 自有领域组件能稳定表达 Proposal、Brief、Storyboard、Shot Run 和 Routing Policy，不受通用工作流产品数据结构绑架。

## 备选方案

### 整体采用 Ant Design/Ant Design Pro

管理后台成熟，但容易让 Creator 工作台呈现通用后台模板感；如果再引入另一套创作组件会形成双系统。拒绝作为整套基础，只保留模式参考。

### Fork Dify 或通用低代码平台

能快速获得复杂页面，但领域模型、许可证和上游同步成本高，且终端用户心智不匹配。拒绝。

### 从零实现所有交互原语

会重复处理焦点、键盘、Portal、Overlay 和 ARIA，质量风险没有商业价值。拒绝。

## 后果

- 项目需要维护进入仓库的 shadcn 组件代码和自己的 Token。
- 复杂 Data Grid 若超出基础 Table 能力，需要单独评估 TanStack Table，但不能引入第二套视觉系统。
- 两个 Shell 必须各自拥有导航、路由守卫和错误边界，初期代码量略增。
- UI 实现前必须先通过页面清单、线框与 Token 评审。

## 验证

- 用两个摩托车 Fixture 跑通 Creator Shell。
- 用两个 Provider + Fallback Fixture 跑通 Admin Shell。
- Storybook 状态、Playwright 主路径、axe、截图和响应式测试全部通过。
- 由项目方评审两套 Shell 仍具有一致品牌，但不会混淆用户职责。
