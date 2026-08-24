# 新增家具

家具包含三部分：透明图层、运行纹理清单、玩法定义。

## 1. 保存权威母版

将人工确认后的透明裁切放到：

```text
web/room/assets/room-v2/source/manual/furniture/<furniture-id>/<layer>.png
```

单层家具通常使用 `back.png`。需要遮挡人物的家具可以使用多个图层，例如：

```text
bed/back.png
bed/blanket-front.png
workstation/chair-owner-back.png
workstation/chair-companion-back.png
workstation/desk-front.png
```

## 2. 生成运行图层

```powershell
python tools/process_furniture_asset.py `
  --input web/room/assets/room-v2/source/manual/furniture/bookcase/back.png `
  --output web/room/assets/room-v2/game/furniture/bookcase/back.png `
  --canvas 440x440 `
  --texture-key v2-bookcase-back
```

脚本透明裁边、纯 NEAREST 缩放、底部居中，并更新 `furniture-manifest.json`。多层家具对每层各运行一次。

## 3. 添加玩法定义

在 `web/room/data/initial-state.json` 的 `furniture` 数组增加对象。至少包含：

```json
{
  "id": "bookcase",
  "type": "furniture",
  "asset": "bookcase",
  "interactiveLayer": "back",
  "layers": [
    { "id": "back", "texture": "v2-bookcase-back", "role": "back" }
  ],
  "position": { "x": 1000, "y": 752 },
  "footprint": { "x": 49, "y": 36, "width": 27, "height": 11 },
  "interactions": ["read"]
}
```

纹理键必须存在于 `furniture-manifest.json`。`position` 是世界像素坐标，footprint 使用 16px 网格。

## 4. 非阻挡装饰

地毯和墙饰使用：

```json
{
  "blocking": false,
  "pointerPassthrough": true,
  "layer": "floor"
}
```

墙饰把 `layer` 改成 `wall`。普通模式不会拦截移动，建造模式仍可拖动。

## 5. 交互与固定槽位

在 `interactions` 声明动作，在 `interactionSlots` 中声明位置。需要固定左右角色时使用 `actorIds`：

```json
"interactionSlots": {
  "sit": [
    { "id": "seatLeft", "anchor": { "x": -65, "y": -118 }, "actorIds": ["owner"] },
    { "id": "seatRight", "anchor": { "x": 65, "y": -118 }, "actorIds": ["companion"] }
  ]
}
```

MCP 不需要为新家具增加工具；继续调用 `room_use_furniture(furniture_id, interaction)`。
