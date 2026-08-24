# 共享状态与 MCP

## 角色权限

```text
网页 REST  -> owner
MCP        -> companion
```

两条控制路径共享 `RoomStore` 和 SQLite，不需要判断网页是否在线。

## REST

浏览器使用：

```text
GET  /api/v1/room/state
GET  /api/v1/room/events
POST /api/v1/room/characters/owner/move
POST /api/v1/room/characters/owner/use
POST /api/v1/room/characters/owner/stop
PUT  /api/v1/room/layout
```

网页没有控制 `companion` 的写路由。

## MCP 工具

- `room_get_state(scope, detail)`
- `room_move(target)`
- `room_use_furniture(furniture_id, interaction)`
- `room_stop()`

MCP 工具没有 `actor_id` 参数，调用身份固定为 `companion`。`room_move` 可以使用 tile、furniture 或 character 目标；character 目标只能是 `owner`。

## 家具交互

`room_use_furniture` 根据家具定义选择允许且空闲的槽位。两个角色在同一家具执行同一可共同动作时，状态分别写成例如：

```text
owner.activity     = work_together
companion.activity = work_together
```

前端仍显示两张人物状态卡，不增加第三张“我们”卡片。若动作包存在匹配的双人合成图，前端显示合成图；否则显示两个独立 pose。

## 心情字段

状态中保留来源中立的 `mood` 对象，但公共服务不依赖日历或聊天系统。使用者可以在自己的私有集成中调用状态层更新心情，不需要改变四个 MCP 工具。
