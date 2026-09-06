# Spec 入口

- 状态：首批核心文档待评审

已建立并等待项目方评审：

1. [产品需求文档 v0.1](product-requirements.md)
2. [创作体验规格 v0.1](experience-spec.md)
3. [大模型接入、切换与 API Key 规格 v0.1](model-provider-routing.md)
4. [模型管理后台体验规格 v0.1](model-management-console.md)
5. [核心领域模型 v0.1](domain-model.md)
6. [Creative Advisor Schema](creative-advisor.schema.json)
7. [Creative Brief Schema](creative-brief.schema.json)
8. [Storyboard Schema](storyboard.schema.json)
9. [Shot Manifest Schema](shot-manifest.schema.json)
10. [OpenAPI 3.1 契约](api.openapi.yaml)
11. [工作流状态机 v0.1](workflow-state-machine.md)
12. [测试与验收策略 v0.1](test-strategy.md)
13. [外部工具与媒体 Provider 契约 v0.1](tool-contract.md)
14. [垂直内容包契约 v0.1](content-pack-contract.md)
15. [P0 视频与渲染输出规格 v0.1](rendering-profile.md)
16. [UI 架构规格 v0.1](ui-architecture.md)
17. [设计系统规格 v0.1](design-system.md)
18. [页面清单与导航规格 v0.1](page-inventory-and-navigation.md)
19. [UI 测试与验收规格 v0.1](ui-acceptance.md)

评审通过后仍需补齐的后续专项规格：

1. `asset-pipeline.md`：Blender 资产进入正式生产前，冻结建模、命名、坐标、材质、绑定、LOD 和质检标准。
2. `security-and-provenance.md`：进入外部部署前，冻结租户隔离、上传和运行环境边界；P0 Key 与任意代码边界已在现有规格中定义。

每份 Spec 必须包含状态、负责人、版本、已决策项、开放问题和可验证的验收标准。未经接受的草案不能作为实现完成的依据。
