# Room MCP Kit 扩展教程

这组文档说明如何在不通读整个代码库的情况下扩展 Room。公共版只有两个稳定角色职责：

- `owner`：网页使用者控制；
- `companion`：AI 通过 MCP 控制。

推荐阅读顺序：

1. [架构与数据流](01-architecture.md)
2. [创建人物与换装](02-characters-and-outfits.md)
3. [新增家具](03-furniture.md)
4. [使用和编辑校准页](04-calibration.md)
5. [新增场景与功能](05-scenes-and-features.md)
6. [素材流水线与本地测试](06-pipeline-local-testing.md)
7. [集成与部署](07-integration-and-deployment.md)
8. [共享状态与 MCP](08-shared-state-and-mcp.md)

所有命令都从 `room-mcp-kit` 仓库根目录运行。源图只放在 `source/manual/**` 或项目外自选目录；处理脚本只写生成目录，不应该覆盖源图。
