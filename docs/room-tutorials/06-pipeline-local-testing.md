# 素材流水线与本地测试

## 背景

```powershell
python tools/process_room_background.py `
  --input web/room/assets/room-v2/source/manual/background/background.png `
  --output web/room/assets/room-v2/game/background/room-square.png `
  --size 1600x1600
```

背景默认使用 LANCZOS 缩放；已经完成像素统一的背景可加 `--sampling nearest`。

## 人物

```powershell
python tools/process_character_assets.py --help
```

人物脚本只接受完整透明帧目录，先验证全部输入，再用 NEAREST 写生成目录和角色包配置。

## 家具

```powershell
python tools/process_furniture_asset.py --help
```

家具脚本一次处理一个图层，因此不会从历史组合图重新裁切，也不会触碰其他家具。

## 地图

```powershell
python tools/generate_room_map.py
```

## 本地运行

```powershell
python -m pip install -r room_service/requirements.txt
python tools/run_room_shared_dev.py --port 8877
```

访问：

- `http://127.0.0.1:8877/`
- `http://127.0.0.1:8877/calibration.html`

状态数据库默认保存在 `room_service/data/room.db`，因此通过服务保存的家具布局在刷新后保留。

## 测试

```powershell
python -m unittest discover -s tests -v
node --check web/room/main.js
node --check web/room/scenes/RoomScene.js
```

处理脚本的测试必须使用临时目录和测试图，不读取使用者自己的素材目录。
