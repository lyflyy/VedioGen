# 2026-09-05 模型管理界面要求

- 状态：已记录
- 参与方：项目方、Codex

## 项目方要求

大模型平台、API Key 和相关切换逻辑需要通过界面上的管理功能实现配置化能力。

## 对产品与架构的影响

- P0 新增内部模型管理后台，不以手改 YAML 或环境变量作为正常管理流程。
- 管理范围包括 Provider、API Key、物理模型、能力路由、测试、发布/回滚和调用记录。
- API Key 通过界面写入 Secret Store，但不允许回显明文。
- 路由以版本化 Draft/Publish 管理，发布只影响新请求。
- 普通创作者界面与内部模型管理界面隔离。

详细设计见[模型管理后台体验规格](../specs/model-management-console.md)和[模型接入规格](../specs/model-provider-routing.md)。
