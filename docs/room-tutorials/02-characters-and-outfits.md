# 创建人物与换装

人物资源由 `character-pack.json` 管理。一个角色可以包含多个 outfit；切换 `initial-state.json` 中角色的 `clothes` 即可选择服装。

## 输入目录

每套服装需要 18 张透明 PNG：

```text
my-character/
├─ idle/
│  ├─ down.png
│  ├─ left.png
│  ├─ up.png
│  └─ right.png
├─ walk/
│  ├─ down-0.png
│  ├─ down-1.png
│  ├─ left-0.png
│  ├─ left-1.png
│  ├─ up-0.png
│  ├─ up-1.png
│  ├─ right-0.png
│  └─ right-1.png
└─ actions/
   ├─ sit.png
   ├─ read.png
   ├─ work-0.png
   ├─ work-1.png
   ├─ sleep.png
   └─ rest.png
```

要求：每张图已经抠成透明背景 RGBA PNG，完整人物没有贴边，所有帧朝向和服装一致。脚本会在写文件前检查整套输入，缺一张就停止。

公共仓库自带中性几何 SVG 示例人物，足以运行移动和家具交互；它们不会为每种动作显示精细姿势。普通使用者自己的角色建议放在被 Git 忽略的 `local-assets/`，准备好完整 18 张后再用下方脚本替换。

## 像素统一

```powershell
python tools/process_character_assets.py `
  --input local-assets/my-owner `
  --role owner `
  --outfit default `
  --display-name "You"
```

脚本使用纯 NEAREST 缩放并写入：

```text
web/room/assets/room-v2/game/character-packs/owner/default/**
```

同时更新 `character-pack.json`。默认画布与锚点：

- idle/walk：`192×304`，脚底 `(96,296)`；
- sit/read/work：`192×280`，髋部 `(96,152)`；
- sleep/rest：`224×336`，枕头 `(112,62)`。

## 新增换装

保持 `--role` 不变，改用新的 `--outfit`：

```powershell
python tools/process_character_assets.py `
  --input local-assets/my-owner-sleepwear `
  --role owner `
  --outfit sleepwear
```

随后把 `initial-state.json` 中对应角色的 `clothes` 改为 `sleepwear`。不要复制角色 ID 来冒充换装，否则会产生第三个状态实体。

## 调整比例

不同画风可使用：

```text
--locomotion-height
--seated-height
--lying-height
--hip-ratio
--pillow-ratio
```

先保留默认值；只有校准页或 Room 实际显示证明锚点不合适时才调整。
