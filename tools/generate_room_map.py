"""Generate the Room collision Tile Map from the 16 px logical grid contract."""

from __future__ import annotations

import json
from pathlib import Path


GRID_SIZE = 16
MAP_WIDTH = 100
MAP_HEIGHT = 100
SIDE_WALL_THICKNESS = 2
TOP_WALL_THICKNESS = 36
BOTTOM_WALL_THICKNESS = 2
OUTPUT = Path(__file__).resolve().parents[1] / "web" / "room" / "data" / "room-map.json"
FLOOR_TOKEN = "__ROOM_FLOOR_DATA__"
WALL_TOKEN = "__ROOM_WALL_DATA__"


def layer_data(value_at):
    return [value_at(x, y) for y in range(MAP_HEIGHT) for x in range(MAP_WIDTH)]


def main() -> None:
    floor = layer_data(lambda _x, _y: 2)
    walls = layer_data(
        lambda x, y: 1
        if x < SIDE_WALL_THICKNESS
        or y < TOP_WALL_THICKNESS
        or x >= MAP_WIDTH - SIDE_WALL_THICKNESS
        or y >= MAP_HEIGHT - BOTTOM_WALL_THICKNESS
        else 0
    )
    room_map = {
        "compressionlevel": -1,
        "height": MAP_HEIGHT,
        "infinite": False,
        "layers": [
            {
                "data": FLOOR_TOKEN,
                "height": MAP_HEIGHT,
                "id": 1,
                "name": "floor",
                "opacity": 1,
                "type": "tilelayer",
                "visible": True,
                "width": MAP_WIDTH,
                "x": 0,
                "y": 0,
            },
            {
                "data": WALL_TOKEN,
                "height": MAP_HEIGHT,
                "id": 2,
                "name": "walls",
                "opacity": 1,
                "type": "tilelayer",
                "visible": True,
                "width": MAP_WIDTH,
                "x": 0,
                "y": 0,
            },
        ],
        "nextlayerid": 3,
        "nextobjectid": 1,
        "orientation": "orthogonal",
        "renderorder": "right-down",
        "tiledversion": "1.11.0",
        "tileheight": GRID_SIZE,
        "tilesets": [
            {
                "columns": 3,
                "firstgid": 1,
                "image": "room-placeholder-tiles.png",
                "imageheight": GRID_SIZE,
                "imagewidth": GRID_SIZE * 3,
                "margin": 0,
                "name": "room-placeholder-tiles",
                "spacing": 0,
                "tilecount": 3,
                "tileheight": GRID_SIZE,
                "tilewidth": GRID_SIZE,
            }
        ],
        "tilewidth": GRID_SIZE,
        "type": "map",
        "version": "1.10",
        "width": MAP_WIDTH,
    }
    text = json.dumps(room_map, ensure_ascii=False, indent=2)
    text = text.replace(f'"{FLOOR_TOKEN}"', format_rows(floor))
    text = text.replace(f'"{WALL_TOKEN}"', format_rows(walls))
    OUTPUT.write_text(text + "\n", encoding="utf-8")


def format_rows(data: list[int]) -> str:
    rows = [data[index:index + MAP_WIDTH] for index in range(0, len(data), MAP_WIDTH)]
    rendered = ["        " + ", ".join(map(str, row)) for row in rows]
    return "[\n" + ",\n".join(rendered) + "\n      ]"


if __name__ == "__main__":
    main()
