# 使用和编辑校准页

通过 `http://127.0.0.1:8877/calibration.html` 打开校准页。它读取与正式 Room 相同的三个公共配置，不读取源图目录。

## 当前能力

- 预览 `character-pack.json` 中的角色与默认 outfit；
- 显示家具、角色、动作三类 schema 摘要；
- 当 `action-pack.json` 提供双人图时，调整 X、Y 和统一缩放；
- 动作包为空时正常启动并明确显示独立人物回退。

校准页修改的是浏览器内预览值，不自动覆盖 JSON 或源图。复制确认后的 JSON，再人工写回配置。

## 双人动作格式

```json
{
  "id": "sit",
  "furniture": "sofa",
  "path": "room/assets/room-v2/game/action-packs/my-pack/sit.png",
  "transform": { "x": 0, "y": 0, "scale": 1 }
}
```

将对象放入 `action-pack.json` 的 `duoActions`。图像必须是处理后的透明运行副本；源图保存在自选的手工源目录。

## 编辑页面

- 页面结构：`web/calibration.html`；
- 数据读取与控件：`web/room/anchor-calibration-v2.js`；
- 样式：`web/room/anchor-calibration-v2.css`。

增加控件时遵守同一原则：校准数据来自公共配置，正式 Room 与校准页使用同一个字段，不能在两个文件中维护两套数值。

人物单帧锚点和完整家具 footprint 的可视化编辑仍是待扩展能力；在完成前使用人物处理脚本的固定画布契约，以及 Room 建造模式保存家具位置。
