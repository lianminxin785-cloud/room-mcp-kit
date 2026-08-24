# 架构与数据流

Room MCP Kit 是静态 Phaser 前端、SQLite 状态服务和 MCP 服务的组合，不使用 React 或打包器。

```text
网页 owner 操作
      │ REST + SSE
      ▼
room_service/app.py ── RoomStore / SQLite ── room_service/mcp_server.py
                                                ▲
                                                │ 四个 MCP 工具
                                                │
                                          AI companion
```

## 前端入口

- `web/index.html`：宽屏 Room 页面；
- `web/calibration.html`：资源包与动作校准页；
- `web/room/main.js`：DOM、状态卡、REST 事件桥；
- `web/room/scenes/RoomScene.js`：地图、相机、人物、家具、寻路和动作显示；
- `web/room/RoomServiceClient.js`：浏览器 Room REST/SSE 客户端。

必须通过本地 HTTP 服务访问，不能以 `file://` 作为受支持运行方式。

## 三类运行配置

- `furniture-manifest.json`：背景和家具纹理键；
- `character-pack.json`：角色、显示名、服装、帧路径、画布和锚点；
- `action-pack.json`：可选双人合成动作。

家具位置、footprint、交互和固定槽位位于 `web/room/data/initial-state.json`；墙体和可行走网格位于 `room-map.json`。美术清单与玩法数据分开，替换图片时不需要改碰撞。

## 共享状态

`room_service/core.py` 是状态权威。网页只能写 `owner`，MCP 只能写 `companion`。前端本地模式用于视觉调试；连接服务后，以 REST/SSE 状态为准。
