# 新增场景与功能

第一版场景 ID 是 `home`。新增场景时，为每个场景提供独立的初始状态、地图、背景和布局缓存键。

## 场景需要的文件

- `initial-state.json`：人物、家具、交互和初始位置；
- `room-map.json`：网格尺寸与墙体；
- 背景运行图；
- 稳定的 `scene.id`。

不要只换背景而继续使用不匹配的碰撞图。语义区域来自家具 footprint，可以与非阻挡地毯和墙饰重叠。

## 新增家具动作

1. 在家具的 `interactions` 增加动作 ID；
2. 在 `RoomScene.js` 的 `INTERACTION_ACTIONS` 声明运行状态；
3. 在 `ACTION_POSES` 声明人物 pose、画布和锚点；
4. 在 `main.js` 增加显示文案；
5. 给状态服务和前端补测试。

只在动作需要新人物图时扩展角色包；家具数量增加不应增加 MCP 工具数量。

## 调整地图边界

`tools/generate_room_map.py` 中的墙体厚度按 16px 网格定义。修改后重新生成 `room-map.json`，再验证人物不能走进墙体、地毯仍可到达、家具 footprint 不越界。
