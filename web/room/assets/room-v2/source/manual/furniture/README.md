# 手工家具母版

这里保存人工确认后的透明家具图层，是家具素材的权威输入目录。

```text
<furniture-id>/
├─ back.png
└─ optional-front-layer.png
```

工位示例使用：

```text
workstation/
├─ chair-owner-back.png
├─ chair-companion-back.png
└─ desk-front.png
```

使用 `tools/process_furniture_asset.py` 一次处理一个图层。脚本不会重新裁切历史组合图，也不会覆盖这里的母版。
