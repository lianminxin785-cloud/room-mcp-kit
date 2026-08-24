const Phaser = globalThis.Phaser;

const TILE_SIZE = 16;
const WORLD_WIDTH = 1600;
const WORLD_HEIGHT = 1600;
const VIEWPORT_WIDTH = 1280;
const VIEWPORT_HEIGHT = 720;
const MOBILE_VIEWPORT_WORLD_WIDTH = 720;
const MIN_CAMERA_ZOOM_RATIO = 0.8;
const MAX_CAMERA_ZOOM_RATIO = 1.6;
const INITIAL_CAMERA_ZOOM_RATIO = 1;
const CAMERA_DRAG_THRESHOLD = 12;
const WALK_SPEED = 192;
const WALK_FRAME_MS = 180;
const WORK_FRAME_MS = 330;
const ROOM_LAYOUT_STORAGE_KEY = "room-mcp-kit:layout:home:v1";
const DIRECTIONS = ["down", "left", "up", "right"];
const WALK_FRAME_SEQUENCE = ["0", "idle", "1"];
const CHARACTER_FRAME_WIDTH = 192;
const CHARACTER_FRAME_HEIGHT = 304;
const CHARACTER_FOOT_WIDTH = 12;
const CHARACTER_FOOT_HEIGHT = 6;
const FURNITURE_NAMES = {
  bed: "床",
  sofa: "沙发",
  computer: "双人工位",
  television: "电视区",
  rug: "地毯",
  "coffee-table": "茶几",
  dresser: "斗柜",
  wardrobe: "衣柜",
  bookcase: "书架阅读区",
  "lounge-area": "娱乐区",
  "wall-shelf": "墙面置物架",
  "wall-photo": "照片墙",
};
const INTERACTION_ACTIONS = {
  sleep: "sleeping",
  rest: "resting",
  sit: "sitting",
  work: "working",
  read: "reading",
  toggle_tv: "watching_tv",
};
const ACTION_BADGES = {
  sleeping: "Zzz",
  resting: "休息",
  sitting: "坐下",
  working: "工作",
  reading: "看书",
  watching_tv: "看电视",
};
const ACTION_POSES = {
  sleep: { pose: "sleep", anchor: "pillowAnchor", canvas: "lying" },
  rest: { pose: "rest", anchor: "pillowAnchor", canvas: "lying" },
  sit: { pose: "sit", anchor: "hipAnchor", canvas: "seated" },
  work: { pose: "work", anchor: "hipAnchor", canvas: "seated" },
  read: { pose: "read", anchor: "hipAnchor", canvas: "seated" },
};

export class RoomScene extends Phaser.Scene {
  constructor() {
    super("RoomScene");
    this.map = null;
    this.wallLayer = null;
    this.actors = new Map();
    this.furniture = new Map();
    this.furnitureTiles = new Set();
    this.furnitureSlotOccupancy = new Map();
    this.furnitureManifest = null;
    this.characterPack = null;
    this.actionPack = null;
    this.targetMarker = null;
    this.buildMode = false;
    this.draggedFurniture = null;
    this.footprintPreview = null;
    this.refreshingDefinitions = false;
    this.remoteMode = false;
    this.cameraPointers = new Map();
    this.cameraGestureDragged = false;
    this.cameraGesturePinched = false;
    this.pinchDistance = 0;
    this.cameraBaseZoom = 1;
  }

  preload() {
    const runtime = globalThis.ROOM_MCP_KIT_RUNTIME;
    if (!runtime?.furnitureManifest || !runtime?.characterPack || !runtime?.actionPack) {
      throw new Error("Room MCP Kit runtime configuration is missing");
    }
    this.furnitureManifest = runtime.furnitureManifest;
    this.characterPack = runtime.characterPack;
    this.actionPack = runtime.actionPack;
    this.load.tilemapTiledJSON("room-map", "room/data/room-map.json?v=13");
    this.load.json("initial-state", "room/data/initial-state.json?v=23");
    this.load.image(this.furnitureManifest.background.key, this.furnitureManifest.background.path);
    for (const [key, path] of Object.entries(this.furnitureManifest.textures)) {
      this.load.image(`furniture-${key}`, path);
    }
    for (const item of this.actionPack.duoActions ?? []) {
      this.load.image(this.duoActionTextureKey(item.id), item.path);
    }
    for (const [id, role] of Object.entries(this.characterPack.roles)) {
      for (const [outfitId, outfit] of Object.entries(role.outfits)) {
        for (const direction of DIRECTIONS) {
          this.load.image(
            this.characterTextureKey(id, direction, "idle", outfitId),
            this.characterFramePath(outfit, "idle", direction),
          );
          for (const frame of ["0", "1"]) {
            this.load.image(
              this.characterTextureKey(id, direction, frame, outfitId),
              this.characterFramePath(outfit, "walk", direction, frame),
            );
          }
        }
        for (const pose of ["sit", "sleep", "rest", "read"]) {
          this.load.image(
            this.characterActionTextureKey(id, pose, null, outfitId),
            this.characterActionPath(outfit, pose),
          );
        }
        for (const frame of ["0", "1"]) {
          this.load.image(
            this.characterActionTextureKey(id, "work", frame, outfitId),
            this.characterActionPath(outfit, "work", frame),
          );
        }
      }
    }
  }

  create() {
    this.createPlaceholderTileset();
    this.configureCharacterTextures();
    this.configureFurnitureTextures();
    this.configureDuoActionTextures();
    this.add.image(0, 0, this.furnitureManifest.background.key)
      .setOrigin(0)
      .setDisplaySize(WORLD_WIDTH, WORLD_HEIGHT)
      .setDepth(0);

    this.map = this.make.tilemap({ key: "room-map" });
    const tileset = this.map.addTilesetImage(
      "room-placeholder-tiles",
      "room-placeholder-tiles",
      TILE_SIZE,
      TILE_SIZE,
      0,
      0,
    );

    if (!tileset) throw new Error("Room placeholder tileset could not be created");

    this.map.createLayer("floor", tileset, 0, 0).setAlpha(0);
    this.wallLayer = this.map.createLayer("walls", tileset, 0, 0);
    this.wallLayer.setAlpha(0);
    this.wallLayer.setCollisionByExclusion([-1]);
    this.physics.world.setBounds(0, 0, this.map.widthInPixels, this.map.heightInPixels);
    this.cameraBaseZoom = this.cameraBaseZoomFor(this.scale.width, this.scale.height);
    this.cameras.main
      .setBounds(0, 0, WORLD_WIDTH, WORLD_HEIGHT)
      .setZoom(this.cameraBaseZoom * INITIAL_CAMERA_ZOOM_RATIO)
      .centerOn(WORLD_WIDTH / 2, 760);

    const initialState = this.cache.json.get("initial-state");
    for (const furniture of initialState.furniture) {
      this.createFurniture(JSON.parse(JSON.stringify(furniture)));
    }
    this.applySavedLayout();
    this.rebuildFurnitureTiles();
    for (const character of initialState.characters) {
      this.createActor(JSON.parse(JSON.stringify(character)));
    }

    const owner = this.actors.get("owner");
    if (!owner) throw new Error("Owner initial state is required");

    this.targetMarker = this.add.rectangle(
      owner.sprite.x,
      owner.sprite.y,
      TILE_SIZE - 2,
      TILE_SIZE - 2,
      0xfff1cf,
      0.16,
    ).setStrokeStyle(1, 0xfff1cf, 0.9).setVisible(false).setDepth(4);

    this.input.on("pointerdown", (pointer) => this.beginCameraGesture(pointer));
    this.input.on("pointermove", (pointer) => this.updateCameraGesture(pointer));
    this.input.on("pointerup", (pointer) => this.endCameraGesture(pointer));
    this.input.on("pointerupoutside", (pointer) => this.endCameraGesture(pointer, true));
    this.input.on("wheel", (pointer, _objects, _deltaX, deltaY) => {
      this.handleCameraWheel(pointer, deltaY);
    });
    this.input.on("dragstart", (_pointer, gameObject) => this.startFurnitureDrag(gameObject));
    this.input.on("drag", (_pointer, gameObject, dragX, dragY) => {
      this.dragFurniture(gameObject, dragX, dragY);
    });
    this.input.on("dragend", (_pointer, gameObject) => this.finishFurnitureDrag(gameObject));
    this.roomInteractHandler = (event) => this.performInteraction(event.detail);
    this.roomBuildModeHandler = (event) => this.setBuildMode(event.detail.enabled);
    this.roomRefreshLayoutHandler = () => this.refreshFurnitureDefinitions();
    this.roomCameraXHandler = (event) => this.setCameraXRatio(event.detail.ratio);
    this.roomRemoteModeHandler = (event) => {
      this.remoteMode = Boolean(event.detail.enabled);
    };
    this.roomAuthorityStateHandler = (event) => this.applyAuthorityState(event.detail);
    this.roomResizeHandler = (gameSize) => this.handleViewportResize(gameSize);
    window.addEventListener("room:interact", this.roomInteractHandler);
    window.addEventListener("room:build-mode", this.roomBuildModeHandler);
    window.addEventListener("room:refresh-layout", this.roomRefreshLayoutHandler);
    window.addEventListener("room:camera-x", this.roomCameraXHandler);
    window.addEventListener("room:remote-mode", this.roomRemoteModeHandler);
    window.addEventListener("room:authority-state", this.roomAuthorityStateHandler);
    this.scale.on("resize", this.roomResizeHandler);
    this.events.once(Phaser.Scenes.Events.SHUTDOWN, () => {
      window.removeEventListener("room:interact", this.roomInteractHandler);
      window.removeEventListener("room:build-mode", this.roomBuildModeHandler);
      window.removeEventListener("room:refresh-layout", this.roomRefreshLayoutHandler);
      window.removeEventListener("room:camera-x", this.roomCameraXHandler);
      window.removeEventListener("room:remote-mode", this.roomRemoteModeHandler);
      window.removeEventListener("room:authority-state", this.roomAuthorityStateHandler);
      this.scale.off("resize", this.roomResizeHandler);
    });
    this.syncActorDecorations();
    this.publishState();

    const renderer = this.game.renderer.type === Phaser.WEBGL ? "WebGL" : "Canvas";
    window.dispatchEvent(new CustomEvent("room:ready", {
      detail: {
        renderer,
        width: this.scale.width,
        height: this.scale.height,
        worldWidth: WORLD_WIDTH,
        worldHeight: WORLD_HEIGHT,
        zoom: this.cameras.main.zoom,
      },
    }));
    this.publishCameraState();
    this.publishLayoutSnapshot("loaded");
  }

  update(_time, delta) {
    for (const actor of this.actors.values()) {
      this.updateActor(actor, delta);
      this.updateActorAction(actor, delta);
    }
  }

  createActor(state) {
    const style = this.characterPack.roles[state.id];
    if (!style) throw new Error(`Unknown Room character: ${state.id}`);

    const start = this.tileCenter(state.position);
    state.clothes = this.characterClothes(state);
    const sprite = this.physics.add.sprite(
      start.x,
      start.y,
      this.characterTextureKey(state.id, state.direction, "idle", state.clothes),
    );
    sprite.setOrigin(0.5, 1);
    sprite.setDisplaySize(style.displaySize[0], style.displaySize[1]);
    sprite.setCollideWorldBounds(true);
    const unscaledFootWidth = CHARACTER_FOOT_WIDTH / Math.abs(sprite.scaleX);
    const unscaledFootHeight = CHARACTER_FOOT_HEIGHT / Math.abs(sprite.scaleY);
    sprite.body.setSize(unscaledFootWidth, unscaledFootHeight).setOffset(
      (CHARACTER_FRAME_WIDTH - unscaledFootWidth) / 2,
      CHARACTER_FRAME_HEIGHT - unscaledFootHeight,
    );
    this.physics.add.collider(sprite, this.wallLayer);

    const label = this.add.text(
      start.x,
      start.y - CHARACTER_FRAME_HEIGHT - 4,
      state.displayName || style.displayName,
      {
        color: "#fff8ed",
        fontFamily: "ui-monospace, monospace",
        fontSize: "28px",
        padding: { x: 10, y: 5 },
        backgroundColor: style.labelBackground,
      },
    ).setOrigin(0.5, 1).setDepth(5000);

    const actionBadge = this.add.text(start.x, start.y + 6, "", {
      color: "#56463f",
      fontFamily: "ui-monospace, monospace",
      fontSize: "28px",
      padding: { x: 10, y: 5 },
      backgroundColor: "#fff1cf",
    }).setOrigin(0.5, 0).setDepth(5000).setVisible(false);

    this.actors.set(state.id, {
      state,
      sprite,
      label,
      actionBadge,
      path: [],
      walkFrame: 0,
      walkFrameElapsed: 0,
      actionFrame: 0,
      actionFrameElapsed: 0,
    });
  }

  createFurniture(state) {
    if (!Array.isArray(state.layers) || state.layers.length === 0) {
      throw new Error(`Room furniture is missing v2 layers: ${state.id}`);
    }
    const layerSprites = new Map();
    for (const layer of state.layers) {
      const textureKey = this.furnitureLayerTextureKey(state, layer);
      if (!this.textures.exists(textureKey)) {
        throw new Error(`Missing Room furniture layer: ${state.id}:${layer.id}`);
      }
      layerSprites.set(
        layer.id,
        this.add.image(state.position.x, state.position.y, textureKey).setOrigin(0.5, 1),
      );
    }
    const interactiveLayerId = state.interactiveLayer ?? state.layers[0].id;
    const sprite = layerSprites.get(interactiveLayerId);
    if (!sprite) throw new Error(`Missing interactive Room layer: ${state.id}:${interactiveLayerId}`);

    sprite.setInteractive({
      useHandCursor: !state.pointerPassthrough,
      cursor: state.pointerPassthrough ? "default" : "pointer",
    });
    sprite.setData("furnitureId", state.id);
    this.input.setDraggable(sprite, true);
    sprite.on("pointerdown", (_pointer, _localX, _localY, event) => {
      if (this.buildMode) return;
      if (state.pointerPassthrough) return;
      event?.stopPropagation();
      this.showFurnitureActions(state.id);
    });

    const entry = {
      state,
      sprite,
      layerSprites,
      defaultPosition: { ...state.position },
      defaultFootprint: { ...state.footprint },
    };
    this.furniture.set(state.id, entry);
    this.syncFurnitureSprite(entry);
  }

  furnitureLayerTextureKey(state, layer) {
    const alias = state.textureState && layer.textures
      ? layer.textures[state.textureState]
      : layer.texture;
    return `furniture-${alias}`;
  }

  furnitureLayerTransform(layer) {
    return {
      x: Number(layer.transform?.x) || 0,
      y: Number(layer.transform?.y) || 0,
      scale: Number(layer.transform?.scale) || 1,
    };
  }

  furnitureSprites(entry) {
    return Array.from(entry.layerSprites.values());
  }

  positionFurnitureLayers(entry, position) {
    for (const layer of entry.state.layers) {
      const transform = this.furnitureLayerTransform(layer);
      entry.layerSprites.get(layer.id)
        ?.setPosition(position.x + transform.x, position.y + transform.y)
        .setScale(transform.scale);
    }
  }

  updateActor(actor, delta) {
    if (actor.path.length === 0) return;

    const nextTile = actor.path[0];
    const target = this.tileCenter(nextTile);
    const dx = target.x - actor.sprite.x;
    const dy = target.y - actor.sprite.y;
    const distance = Math.hypot(dx, dy);
    const arrivalDistance = WALK_SPEED * (delta / 1000) + 0.5;

    if (distance <= arrivalDistance) {
      actor.sprite.setVelocity(0, 0);
      actor.sprite.setPosition(target.x, target.y);
      actor.state.position = { x: nextTile.x, y: nextTile.y };
      actor.path.shift();
      this.publishState();

      if (actor.path.length === 0) this.finishMovement(actor);
      this.syncActorDecorations(actor);
      return;
    }

    const direction = this.directionForDelta(dx, dy);
    if (direction !== actor.state.direction) {
      actor.state.direction = direction;
      actor.walkFrame = 0;
      actor.walkFrameElapsed = 0;
    }

    actor.walkFrameElapsed += delta;
    if (actor.walkFrameElapsed >= WALK_FRAME_MS) {
      actor.walkFrameElapsed %= WALK_FRAME_MS;
      actor.walkFrame = (actor.walkFrame + 1) % WALK_FRAME_SEQUENCE.length;
    }

    actor.sprite.setTexture(this.characterTextureKey(
      actor.state.id,
      direction,
      WALK_FRAME_SEQUENCE[actor.walkFrame],
    ));
    actor.sprite.setVelocity((dx / distance) * WALK_SPEED, (dy / distance) * WALK_SPEED);
    this.syncActorDecorations(actor);
  }

  updateActorAction(actor, delta) {
    if (actor.activeFurnitureAction?.interaction !== "work") return;
    actor.actionFrameElapsed += delta;
    if (actor.actionFrameElapsed < WORK_FRAME_MS) return;
    actor.actionFrameElapsed %= WORK_FRAME_MS;
    actor.actionFrame = actor.actionFrame === 0 ? 1 : 0;
    this.refreshFurnitureActionVisual(actor.activeFurnitureAction.furnitureId);
  }

  beginCameraGesture(pointer) {
    if (this.buildMode) return;
    this.cameraPointers.set(pointer.id, {
      startX: pointer.x,
      startY: pointer.y,
      x: pointer.x,
      y: pointer.y,
    });
    if (this.cameraPointers.size === 1) {
      this.cameraGestureDragged = false;
      this.cameraGesturePinched = false;
      this.pinchDistance = 0;
    } else if (this.cameraPointers.size === 2) {
      this.cameraGesturePinched = true;
      this.cameraGestureDragged = true;
      this.pinchDistance = this.cameraPointerDistance();
      this.closeFurnitureActions();
    }
  }

  updateCameraGesture(pointer) {
    if (this.buildMode || !this.cameraPointers.has(pointer.id)) return;
    const tracked = this.cameraPointers.get(pointer.id);
    const previousX = tracked.x;
    const previousY = tracked.y;
    tracked.x = pointer.x;
    tracked.y = pointer.y;

    if (this.cameraPointers.size >= 2) {
      const nextDistance = this.cameraPointerDistance();
      const midpoint = this.cameraPointerMidpoint();
      if (this.pinchDistance > 0 && nextDistance > 0) {
        this.zoomCameraAt(
          midpoint.x,
          midpoint.y,
          this.cameras.main.zoom * (nextDistance / this.pinchDistance),
        );
      }
      this.pinchDistance = nextDistance;
      this.cameraGesturePinched = true;
      this.cameraGestureDragged = true;
      return;
    }

    const moved = Math.hypot(tracked.x - tracked.startX, tracked.y - tracked.startY);
    if (!this.cameraGestureDragged && moved < CAMERA_DRAG_THRESHOLD) return;
    if (!this.cameraGestureDragged) this.closeFurnitureActions();
    this.cameraGestureDragged = true;
    const camera = this.cameras.main;
    camera.scrollX -= (tracked.x - previousX) / camera.zoom;
    camera.scrollY -= (tracked.y - previousY) / camera.zoom;
    camera.preRender();
    this.publishCameraState();
  }

  endCameraGesture(pointer, cancelled = false) {
    if (!this.cameraPointers.has(pointer.id)) return;
    const wasSinglePointer = this.cameraPointers.size === 1;
    const shouldMove = wasSinglePointer
      && !cancelled
      && !this.buildMode
      && !this.cameraGestureDragged
      && !this.cameraGesturePinched;
    this.cameraPointers.delete(pointer.id);
    if (this.cameraPointers.size < 2) this.pinchDistance = 0;
    if (shouldMove) {
      const worldPoint = this.cameras.main.getWorldPoint(pointer.x, pointer.y);
      this.handleGroundClick(worldPoint);
    }
    if (this.cameraPointers.size === 0) {
      this.cameraGestureDragged = false;
      this.cameraGesturePinched = false;
    }
  }

  handleCameraWheel(pointer, deltaY) {
    if (this.buildMode || !Number.isFinite(deltaY) || deltaY === 0) return;
    pointer.event?.preventDefault?.();
    this.closeFurnitureActions();
    this.zoomCameraAt(
      pointer.x,
      pointer.y,
      this.cameras.main.zoom * Math.exp(-deltaY * 0.0012),
    );
  }

  zoomCameraAt(screenX, screenY, requestedZoom) {
    const camera = this.cameras.main;
    const nextZoom = Phaser.Math.Clamp(
      requestedZoom,
      this.cameraBaseZoom * MIN_CAMERA_ZOOM_RATIO,
      this.cameraBaseZoom * MAX_CAMERA_ZOOM_RATIO,
    );
    if (Math.abs(nextZoom - camera.zoom) < 0.0001) return;
    const before = camera.getWorldPoint(screenX, screenY);
    camera.setZoom(nextZoom);
    camera.preRender();
    const after = camera.getWorldPoint(screenX, screenY);
    camera.scrollX += before.x - after.x;
    camera.scrollY += before.y - after.y;
    camera.preRender();
    this.publishCameraState();
  }

  cameraBaseZoomFor(width, height) {
    const portraitPhone = width <= 640 && height > width;
    const targetWorldWidth = portraitPhone ? MOBILE_VIEWPORT_WORLD_WIDTH : VIEWPORT_WIDTH;
    return Math.max(0.01, width / targetWorldWidth);
  }

  handleViewportResize(gameSize) {
    const width = Number(gameSize?.width) || this.scale.width;
    const height = Number(gameSize?.height) || this.scale.height;
    const camera = this.cameras.main;
    const centerX = camera.worldView.centerX || WORLD_WIDTH / 2;
    const centerY = camera.worldView.centerY || 760;
    const zoomRatio = this.cameraBaseZoom > 0
      ? camera.zoom / this.cameraBaseZoom
      : INITIAL_CAMERA_ZOOM_RATIO;
    this.cameraBaseZoom = this.cameraBaseZoomFor(width, height);
    camera.setZoom(this.cameraBaseZoom * Phaser.Math.Clamp(
      zoomRatio,
      MIN_CAMERA_ZOOM_RATIO,
      MAX_CAMERA_ZOOM_RATIO,
    ));
    camera.centerOn(centerX, centerY);
    camera.preRender();
    this.closeFurnitureActions();
    this.publishCameraState();
  }

  cameraPointerDistance() {
    const [first, second] = Array.from(this.cameraPointers.values());
    return first && second ? Math.hypot(second.x - first.x, second.y - first.y) : 0;
  }

  cameraPointerMidpoint() {
    const [first, second] = Array.from(this.cameraPointers.values());
    return {
      x: (first.x + second.x) / 2,
      y: (first.y + second.y) / 2,
    };
  }

  setCameraXRatio(ratio) {
    if (this.buildMode || !Number.isFinite(ratio)) return;
    const camera = this.cameras.main;
    camera.preRender();
    const worldView = camera.worldView;
    const maxScroll = Math.max(0, WORLD_WIDTH - worldView.width);
    camera.scrollX = Phaser.Math.Clamp(ratio, 0, 1) * maxScroll;
    camera.preRender();
    this.closeFurnitureActions();
    this.publishCameraState();
  }

  publishCameraState() {
    const camera = this.cameras.main;
    camera.preRender();
    const worldView = camera.worldView;
    const maxScroll = Math.max(0, WORLD_WIDTH - worldView.width);
    const ratio = maxScroll > 0
      ? Phaser.Math.Clamp(worldView.x / maxScroll, 0, 1)
      : 0.5;
    window.dispatchEvent(new CustomEvent("room:camera", {
      detail: {
        ratio,
        zoom: camera.zoom,
        zoomRatio: camera.zoom / this.cameraBaseZoom,
        x: worldView.x,
        y: worldView.y,
        width: worldView.width,
        height: worldView.height,
        viewportWidth: this.scale.width,
        viewportHeight: this.scale.height,
      },
    }));
  }

  handleGroundClick(worldPoint) {
    if (this.buildMode) return;
    this.closeFurnitureActions();
    const target = this.map.worldToTileXY(worldPoint.x, worldPoint.y, true);

    if (!target || !this.isWalkable(target.x, target.y)) {
      const blockedByFurniture = target
        && this.furnitureTiles.has(this.tileKey(target.x, target.y));
      this.publishNotice(blockedByFurniture
          ? "这里摆着家具，角色走不过去"
          : "这里被墙挡住了，角色走不过去");
      return;
    }

    if (this.remoteMode) {
      window.dispatchEvent(new CustomEvent("room:move-request", {
        detail: { target: { x: target.x, y: target.y } },
      }));
      return;
    }
    this.moveCharacter("owner", target, { showTarget: true });
  }

  moveCharacter(id, target, options = {}) {
    const actor = this.actors.get(id);
    if (!actor) return false;

    if (!options.forInteraction) {
      actor.pendingInteraction = null;
      this.releaseActorSlot(actor);
    }
    this.restoreActorFootAnchor(actor);
    const current = { ...actor.state.position };
    const nextPath = this.findPath(current, target);

    if (nextPath.length === 0) {
      if (id === "owner") this.publishNotice("暂时找不到去那里的路");
      return false;
    }

    if (nextPath.length === 1) {
      const currentCenter = this.tileCenter(current);
      actor.sprite.setPosition(currentCenter.x, currentCenter.y);
      actor.state.position = { x: current.x, y: current.y };
      this.finishMovement(actor);
      return true;
    }

    actor.path = nextPath.slice(1);
    actor.state.action = "walking";
    this.clearActionFeedback(actor);

    if (options.showTarget) {
      const targetCenter = this.tileCenter(target);
      this.targetMarker?.setPosition(targetCenter.x, targetCenter.y).setVisible(true);
    }

    this.publishState();
    return true;
  }

  findPath(start, target) {
    const startKey = this.tileKey(start.x, start.y);
    const targetKey = this.tileKey(target.x, target.y);
    const queue = [{ x: start.x, y: start.y }];
    const parents = new Map([[startKey, null]]);
    const neighbors = [
      { x: 0, y: -1 },
      { x: -1, y: 0 },
      { x: 1, y: 0 },
      { x: 0, y: 1 },
    ];

    for (let index = 0; index < queue.length; index += 1) {
      const current = queue[index];
      const currentKey = this.tileKey(current.x, current.y);
      if (currentKey === targetKey) break;

      for (const offset of neighbors) {
        const next = { x: current.x + offset.x, y: current.y + offset.y };
        const nextKey = this.tileKey(next.x, next.y);
        if (parents.has(nextKey) || !this.isWalkable(next.x, next.y)) continue;
        parents.set(nextKey, currentKey);
        queue.push(next);
      }
    }

    if (!parents.has(targetKey)) return [];

    const path = [];
    let cursor = targetKey;
    while (cursor) {
      const [x, y] = cursor.split(",").map(Number);
      path.push({ x, y });
      cursor = parents.get(cursor);
    }

    return path.reverse();
  }

  isWalkable(x, y) {
    if (x < 0 || y < 0 || x >= this.map.width || y >= this.map.height) return false;
    const wall = this.wallLayer.getTileAt(x, y);
    return (!wall || wall.index < 0) && !this.furnitureTiles.has(this.tileKey(x, y));
  }

  finishMovement(actor) {
    actor.path = [];
    actor.sprite.setVelocity(0, 0);
    actor.walkFrame = 0;
    actor.walkFrameElapsed = 0;
    actor.state.action = "idle";
    this.clearActionFeedback(actor);
    actor.sprite.setTexture(this.characterTextureKey(
      actor.state.id,
      actor.state.direction,
      "idle",
    ));
    if (actor.state.id === "owner") this.targetMarker?.setVisible(false);
    const pendingInteraction = actor.pendingInteraction;
    actor.pendingInteraction = null;
    if (pendingInteraction) {
      this.executeFurnitureAction(actor, pendingInteraction);
      return;
    }
    this.publishState();
    this.syncActorDecorations(actor);
  }

  publishState() {
    const characters = Array.from(this.actors.values(), (actor) => (
      JSON.parse(JSON.stringify(actor.state))
    ));
    const furniture = Array.from(this.furniture.values(), (entry) => (
      JSON.parse(JSON.stringify(entry.state))
    ));
    window.dispatchEvent(new CustomEvent("room:state", { detail: { characters, furniture } }));
  }

  publishNotice(message) {
    window.dispatchEvent(new CustomEvent("room:notice", { detail: { message } }));
  }

  syncActorDecorations(actor = null) {
    const actors = actor ? [actor] : this.actors.values();
    for (const current of actors) {
      current.sprite.setDepth(current.actionDepth ?? Math.round(current.sprite.y));
      current.label.setPosition(current.sprite.x, current.sprite.y - current.sprite.displayHeight - 4);
      current.actionBadge.setPosition(current.sprite.x, current.sprite.y + 5);
    }
  }

  showFurnitureActions(furnitureId) {
    const entry = this.furniture.get(furnitureId);
    if (!entry || entry.state.interactions.length === 0) {
      this.closeFurnitureActions();
      return;
    }
    const camera = this.cameras.main;
    camera.preRender();
    const anchorWorld = {
      x: entry.state.position.x,
      y: Math.max(
        24,
        entry.state.position.y
          - Math.max(...this.furnitureSprites(entry).map((sprite) => sprite.displayHeight))
          - 8,
      ),
    };
    const viewport = { width: this.scale.width, height: this.scale.height };
    const screenAnchor = {
      x: (anchorWorld.x - camera.worldView.x) * camera.zoom,
      y: (anchorWorld.y - camera.worldView.y) * camera.zoom,
    };
    window.dispatchEvent(new CustomEvent("room:interaction", {
      detail: {
        furniture: JSON.parse(JSON.stringify(entry.state)),
        anchor: {
          x: Phaser.Math.Clamp(screenAnchor.x, 80, viewport.width - 80),
          y: Phaser.Math.Clamp(screenAnchor.y, 48, viewport.height - 12),
        },
        viewport,
      },
    }));
  }

  closeFurnitureActions() {
    window.dispatchEvent(new CustomEvent("room:interaction", {
      detail: { furniture: null, anchor: null },
    }));
  }

  performInteraction({ furnitureId, interaction, actorId = "owner", slotId = null }) {
    const entry = this.furniture.get(furnitureId);
    const actor = this.actors.get(actorId);
    const action = INTERACTION_ACTIONS[interaction];
    if (this.buildMode || !actor || !entry || !action) return false;
    if (!entry.state.interactions.includes(interaction)) return false;

    this.restoreActorFootAnchor(actor);
    const slot = this.selectInteractionSlot(entry, interaction, actor, slotId);
    this.closeFurnitureActions();
    if (!slot) {
      this.publishNotice(`${FURNITURE_NAMES[entry.state.id] ?? "家具"}暂时没有空位`);
      return false;
    }

    const approach = this.findNearestFurnitureApproach(actor, entry.state);
    if (!approach) {
      this.publishNotice(`${FURNITURE_NAMES[entry.state.id] ?? "家具"}被挡住了`);
      return false;
    }

    this.reserveFurnitureSlot(actor, furnitureId, slot);
    actor.pendingInteraction = { furnitureId, interaction, slot };
    const moving = this.moveCharacter(actorId, approach.target, {
      showTarget: actorId === "owner",
      forInteraction: true,
    });
    if (!moving) this.releaseActorSlot(actor);
    return moving;
  }

  selectInteractionSlot(entry, interaction, actor, requestedSlotId) {
    const configured = entry.state.interactionSlots?.[interaction];
    if (!Array.isArray(configured) || configured.length === 0) {
      return {
        id: interaction,
        anchor: entry.state.actionAnchors?.[interaction] ?? null,
        reservable: false,
      };
    }

    const available = configured.filter((slot) => {
      if (requestedSlotId && slot.id !== requestedSlotId) return false;
      if (Array.isArray(slot.actorIds) && !slot.actorIds.includes(actor.state.id)) return false;
      const occupant = this.furnitureSlotOccupancy.get(`${entry.state.id}:${slot.id}`);
      return !occupant || occupant === actor.state.id;
    });
    available.sort((first, second) => {
      const firstX = entry.state.position.x + first.anchor.x;
      const firstY = entry.state.position.y + first.anchor.y;
      const secondX = entry.state.position.x + second.anchor.x;
      const secondY = entry.state.position.y + second.anchor.y;
      return Math.hypot(actor.sprite.x - firstX, actor.sprite.y - firstY)
        - Math.hypot(actor.sprite.x - secondX, actor.sprite.y - secondY);
    });
    return available[0] ? { ...available[0], reservable: true } : null;
  }

  reserveFurnitureSlot(actor, furnitureId, slot) {
    if (!slot.reservable) return;
    this.releaseActorSlot(actor);
    const key = `${furnitureId}:${slot.id}`;
    this.furnitureSlotOccupancy.set(key, actor.state.id);
    actor.activeFurnitureSlot = key;
  }

  releaseActorSlot(actor) {
    const previousFurnitureId = actor.activeFurnitureAction?.furnitureId
      ?? actor.activeFurnitureSlot?.split(":", 1)[0];
    if (actor.activeFurnitureSlot
      && this.furnitureSlotOccupancy.get(actor.activeFurnitureSlot) === actor.state.id) {
      this.furnitureSlotOccupancy.delete(actor.activeFurnitureSlot);
    }
    delete actor.activeFurnitureSlot;
    delete actor.activeFurnitureAction;
    this.clearActorActionVisual(actor);
    if (previousFurnitureId) this.refreshFurnitureActionVisual(previousFurnitureId);
  }

  findNearestFurnitureApproach(actor, furniture) {
    const { x, y, width, height } = furniture.footprint;
    const candidates = [];
    for (let tileX = x - 1; tileX <= x + width; tileX += 1) {
      candidates.push({ x: tileX, y: y - 1 }, { x: tileX, y: y + height });
    }
    for (let tileY = y; tileY < y + height; tileY += 1) {
      candidates.push({ x: x - 1, y: tileY }, { x: x + width, y: tileY });
    }

    const start = { ...actor.state.position };
    let nearest = null;
    for (const target of candidates) {
      if (!this.isWalkable(target.x, target.y)) continue;
      const path = this.findPath(start, target);
      if (path.length === 0) continue;
      if (!nearest || path.length < nearest.path.length) nearest = { target, path };
    }
    return nearest;
  }

  executeFurnitureAction(actor, { furnitureId, interaction, slot }, options = {}) {
    const entry = this.furniture.get(furnitureId);
    const action = INTERACTION_ACTIONS[interaction];
    if (!entry || !action) return;

    actor.state.action = action;
    actor.actionFrame = 0;
    actor.actionFrameElapsed = 0;
    const anchor = slot?.anchor ?? entry.state.actionAnchors?.[interaction];
    actor.activeFurnitureAction = anchor ? {
      furnitureId,
      interaction,
      slotId: slot?.id ?? interaction,
      anchor: { ...anchor },
      scale: Number(slot?.scale) || Number(entry.state.actionScale) || 1,
    } : null;
    if (slot?.facing) {
      actor.state.direction = slot.facing;
      actor.sprite.setTexture(this.characterTextureKey(
        actor.state.id,
        slot.facing,
        "idle",
      ));
    }
    if (interaction === "toggle_tv" && options.toggleTexture !== false) {
      this.toggleFurnitureState(entry);
    }
    actor.actionDepth = this.furnitureSortY(entry);
    actor.sprite.clearTint();
    actor.actionBadge.setText(ACTION_BADGES[action]).setVisible(true);
    this.refreshFurnitureActionVisual(furnitureId);
    if (!actor.activeFurnitureAction) actor.sprite.setTint(0xffedcf);
    this.syncActorDecorations(actor);
    if (options.publish !== false) this.publishState();
    const style = this.characterPack.roles[actor.state.id];
    const actorName = actor.state.displayName || style?.displayName || actor.state.id;
    if (options.notice !== false) {
      this.publishNotice(`${actorName} 正在使用${FURNITURE_NAMES[entry.state.id] ?? "家具"}`);
    }
  }

  toggleFurnitureState(entry) {
    const nextState = entry.state.textureState === "on" ? "off" : "on";
    if (!entry.state.layers.some((layer) => layer.textures?.[nextState])) return false;
    entry.state.textureState = nextState;
    for (const layer of entry.state.layers) {
      if (!layer.textures) continue;
      entry.layerSprites.get(layer.id)?.setTexture(
        this.furnitureLayerTextureKey(entry.state, layer),
      );
    }
    return true;
  }

  restoreActorFootAnchor(actor) {
    if (actor.state.action === "idle" || actor.state.action === "walking") return;
    this.releaseActorSlot(actor);
    delete actor.actionDepth;
    const foot = this.tileCenter(actor.state.position);
    actor.sprite.setPosition(foot.x, foot.y);
    actor.state.action = "idle";
    actor.sprite.setTexture(this.characterTextureKey(
      actor.state.id,
      actor.state.direction,
      "idle",
    ));
    actor.sprite.setScale(1);
    actor.sprite.setVisible(true);
    actor.label.setVisible(true);
    this.clearActionFeedback(actor);
    this.syncActorDecorations(actor);
  }

  clearActionFeedback(actor) {
    actor.sprite.clearTint();
    actor.actionBadge.setVisible(false).setText("");
  }

  clearActorActionVisual(actor) {
    actor.actionSprite?.destroy();
    actor.actionSprite = null;
    actor.sprite.setVisible(true).setScale(1);
    actor.label.setVisible(true);
  }

  clearFurnitureActionVisual(entry) {
    entry.actionSprite?.destroy();
    entry.actionSprite = null;
  }

  duoActionDefinition(entry, actors) {
    if (actors.length !== 2) return null;
    const ids = new Set(actors.map((actor) => actor.state.id));
    if (!ids.has("owner") || !ids.has("companion")) return null;
    const interactions = new Set(
      actors.map((actor) => actor.activeFurnitureAction?.interaction),
    );
    if (interactions.size !== 1) return null;
    const [interaction] = interactions;
    return (this.actionPack.duoActions ?? []).find(
      (item) => item.id === interaction && item.furniture === entry.state.asset,
    ) ?? null;
  }

  placeDuoAtFurnitureAction(entry, definition, actors) {
    const textureKey = this.duoActionTextureKey(definition.id);
    if (!entry.actionSprite) {
      entry.actionSprite = this.add.image(0, 0, textureKey).setOrigin(0.5, 1);
    } else {
      entry.actionSprite.setTexture(textureKey);
    }
    entry.actionSprite
      .setPosition(
        entry.state.position.x + definition.transform.x,
        entry.state.position.y + definition.transform.y,
      )
      .setScale(definition.transform.scale)
      .setDepth(this.furnitureSortY(entry))
      .setVisible(true);
    for (const actor of actors) {
      actor.sprite.setVisible(false);
      actor.label.setVisible(false);
      actor.actionBadge.setVisible(false);
    }
  }

  placeActorAtFurnitureAction(actor, entry) {
    const active = actor.activeFurnitureAction;
    const definition = ACTION_POSES[active?.interaction];
    if (!active || !definition) return false;
    const canvas = this.characterPack.canvases[definition.canvas].size;
    const anchor = this.characterPack.anchors[definition.anchor];
    const scale = Number(active.scale) || Number(entry.state.actionScale) || 1;
    const frame = definition.pose === "work" ? actor.actionFrame : null;
    actor.sprite.setTexture(
      this.characterActionTextureKey(actor.state.id, definition.pose, frame),
    ).setScale(scale).clearTint().setVisible(true);
    const target = {
      x: entry.state.position.x + active.anchor.x,
      y: entry.state.position.y + active.anchor.y,
    };
    actor.sprite.setPosition(
      target.x + (canvas[0] / 2 - anchor.x) * scale,
      target.y + (canvas[1] - anchor.y) * scale,
    );
    actor.actionDepth = this.furnitureSortY(entry);
    actor.label.setVisible(false);
    actor.actionBadge.setVisible(false);
    this.syncActorDecorations(actor);
    return true;
  }

  refreshFurnitureActionVisual(furnitureId) {
    const entry = this.furniture.get(furnitureId);
    if (!entry) return;

    const actors = Array.from(this.actors.values()).filter(
      (actor) => actor.activeFurnitureAction?.furnitureId === furnitureId,
    );
    const duoAction = this.duoActionDefinition(entry, actors);
    if (duoAction) {
      this.placeDuoAtFurnitureAction(entry, duoAction, actors);
      return;
    }
    this.clearFurnitureActionVisual(entry);
    for (const actor of actors) {
      this.placeActorAtFurnitureAction(actor, entry);
    }
  }

  refreshAllFurnitureActionVisuals() {
    for (const furnitureId of this.furniture.keys()) {
      this.refreshFurnitureActionVisual(furnitureId);
    }
  }

  setBuildMode(enabled) {
    this.buildMode = Boolean(enabled);
    this.targetMarker?.setVisible(false);

    if (this.buildMode) {
      for (const actor of this.actors.values()) {
        actor.pendingInteraction = null;
        this.releaseActorSlot(actor);
        this.restoreActorFootAnchor(actor);
        this.stopActorForBuilding(actor);
      }
      this.publishState();
    }

    for (const { state, sprite } of this.furniture.values()) {
      if (sprite.input) {
        sprite.input.cursor = this.buildMode
          ? "grab"
          : (state.pointerPassthrough ? "default" : "pointer");
      }
    }

    this.closeFurnitureActions();
    this.publishNotice(this.buildMode
      ? "建造模式已开启：拖动家具来重新布置房间"
      : "布局已经保存，可以继续和房间互动了");
  }

  stopActorForBuilding(actor) {
    if (actor.path.length === 0) return;
    const tile = this.map.worldToTileXY(actor.sprite.x, actor.sprite.y, true);
    const center = this.tileCenter(tile);
    actor.path = [];
    actor.sprite.setVelocity(0, 0).setPosition(center.x, center.y);
    actor.state.position = { x: tile.x, y: tile.y };
    actor.state.action = "idle";
    actor.sprite.setTexture(this.characterTextureKey(
      actor.state.id,
      actor.state.direction,
      "idle",
    ));
    this.clearActionFeedback(actor);
    this.syncActorDecorations(actor);
    this.publishState();
  }

  startFurnitureDrag(gameObject) {
    if (!this.buildMode) return;
    const entry = this.furniture.get(gameObject.getData("furnitureId"));
    if (!entry) return;
    this.draggedFurniture = entry;
    entry.dragStart = {
      position: { ...entry.state.position },
      footprint: { ...entry.state.footprint },
    };
    this.furnitureSprites(entry).forEach((sprite, index) => {
      sprite.setDepth(9000 + index).setTint(0xfff0d2);
    });
    this.showFootprintPreview(entry.state.footprint, true);
  }

  dragFurniture(gameObject, dragX, dragY) {
    if (!this.buildMode || this.draggedFurniture?.sprite !== gameObject) return;
    const entry = this.draggedFurniture;
    const interactiveLayer = entry.state.layers.find(
      (layer) => layer.id === entry.state.interactiveLayer,
    ) ?? entry.state.layers[0];
    const transform = this.furnitureLayerTransform(interactiveLayer);
    entry.dragPosition = { x: dragX - transform.x, y: dragY - transform.y };
    this.positionFurnitureLayers(entry, entry.dragPosition);
    const footprint = this.dragFootprint(entry, entry.dragPosition.x, entry.dragPosition.y);
    this.showFootprintPreview(
      footprint,
      this.canPlaceFurniture(this.draggedFurniture, footprint),
    );
  }

  finishFurnitureDrag(gameObject) {
    if (!this.buildMode || this.draggedFurniture?.sprite !== gameObject) return;
    const entry = this.draggedFurniture;
    const position = entry.dragPosition ?? { x: gameObject.x, y: gameObject.y };
    const footprint = this.dragFootprint(entry, position.x, position.y);
    this.furnitureSprites(entry).forEach((sprite) => sprite.clearTint());

    if (this.canPlaceFurniture(entry, footprint)) {
      entry.state.position = { x: Math.round(position.x), y: Math.round(position.y) };
      entry.state.footprint = { ...footprint };
      this.syncFurnitureSprite(entry);
      this.rebuildFurnitureTiles();
      const saved = this.saveFurnitureLayout();
      this.publishState();
      this.publishNotice(saved
        ? `${FURNITURE_NAMES[entry.state.id] ?? "家具"}已摆好并保存`
        : `${FURNITURE_NAMES[entry.state.id] ?? "家具"}已摆好，但浏览器没有允许本地保存`);
    } else {
      entry.state.position = { ...entry.dragStart.position };
      entry.state.footprint = { ...entry.dragStart.footprint };
      this.syncFurnitureSprite(entry);
      this.publishNotice("这里放不下：请避开墙壁、角色和其他家具");
    }

    delete entry.dragStart;
    delete entry.dragPosition;
    this.draggedFurniture = null;
    this.footprintPreview?.clear().setVisible(false);
  }

  dragFootprint(entry, x, y) {
    const deltaX = x - entry.dragStart.position.x;
    const deltaY = y - entry.dragStart.position.y;
    return {
      ...entry.dragStart.footprint,
      x: entry.dragStart.footprint.x + Math.round(deltaX / TILE_SIZE),
      y: entry.dragStart.footprint.y + Math.round(deltaY / TILE_SIZE),
    };
  }

  canPlaceFurniture(entry, footprint) {
    return this.isFurniturePlacementValid(entry, footprint, this.currentActorTiles());
  }

  isFurniturePlacementValid(entry, footprint, actorTiles = []) {
    if (!footprint
      || ![footprint.x, footprint.y, footprint.width, footprint.height].every(Number.isInteger)
      || footprint.width < 1
      || footprint.height < 1) {
      return false;
    }

    if (entry.state.layer === "wall") {
      return footprint.x >= 0
        && footprint.y >= 0
        && footprint.x + footprint.width <= this.map.width
        && footprint.y + footprint.height <= this.map.height;
    }

    const actors = new Set(actorTiles.map(({ x, y }) => this.tileKey(x, y)));
    for (let y = footprint.y; y < footprint.y + footprint.height; y += 1) {
      for (let x = footprint.x; x < footprint.x + footprint.width; x += 1) {
        if (!this.isFloorTile(x, y)) return false;
        if (entry.state.blocking !== false && actors.has(this.tileKey(x, y))) return false;
      }
    }

    if (entry.state.blocking === false) return true;
    for (const [otherId, other] of this.furniture) {
      if (otherId === entry.state.id || other.state.blocking === false) continue;
      if (this.footprintsOverlap(footprint, other.state.footprint)) return false;
    }
    return true;
  }

  footprintsOverlap(first, second) {
    return first.x < second.x + second.width
      && first.x + first.width > second.x
      && first.y < second.y + second.height
      && first.y + first.height > second.y;
  }

  isLayoutValid(layouts, actorTiles = []) {
    const occupied = new Map();
    const actors = new Set(actorTiles.map(({ x, y }) => this.tileKey(x, y)));
    for (const [id, entry] of this.furniture) {
      const layout = layouts.get(id);
      const footprint = layout?.footprint;
      if (!layout || !Number.isFinite(layout.position?.x) || !Number.isFinite(layout.position?.y)
        || !footprint || ![footprint.x, footprint.y, footprint.width, footprint.height].every(Number.isInteger)
        || footprint.width < 1 || footprint.height < 1) {
        return false;
      }
      if (entry.state.layer === "wall") {
        if (footprint.x < 0 || footprint.y < 0
          || footprint.x + footprint.width > this.map.width
          || footprint.y + footprint.height > this.map.height) {
          return false;
        }
        continue;
      }
      for (let y = footprint.y; y < footprint.y + footprint.height; y += 1) {
        for (let x = footprint.x; x < footprint.x + footprint.width; x += 1) {
          if (!this.isFloorTile(x, y)) return false;
          if (entry.state.blocking === false) continue;
          const key = this.tileKey(x, y);
          if (actors.has(key)) return false;
          if (occupied.has(key)) return false;
          occupied.set(key, id);
        }
      }
    }

    return true;
  }

  showFootprintPreview(footprint, valid) {
    if (!this.footprintPreview) this.footprintPreview = this.add.graphics().setDepth(10000);
    const graphics = this.footprintPreview.setVisible(true).clear();
    const color = valid ? 0x86b69a : 0xd98282;
    const x = footprint.x * TILE_SIZE;
    const y = footprint.y * TILE_SIZE;
    const width = footprint.width * TILE_SIZE;
    const height = footprint.height * TILE_SIZE;
    graphics.fillStyle(color, 0.22).fillRect(x, y, width, height);
    graphics.lineStyle(1, color, 0.78).strokeRect(x, y, width, height);
    for (let column = 1; column < footprint.width; column += 1) {
      graphics.lineBetween(x + column * TILE_SIZE, y, x + column * TILE_SIZE, y + height);
    }
    for (let row = 1; row < footprint.height; row += 1) {
      graphics.lineBetween(x, y + row * TILE_SIZE, x + width, y + row * TILE_SIZE);
    }
  }

  isFloorTile(x, y) {
    if (x < 0 || y < 0 || x >= this.map.width || y >= this.map.height) return false;
    const wall = this.wallLayer.getTileAt(x, y);
    return !wall || wall.index < 0;
  }

  currentActorTiles() {
    return Array.from(this.actors.values(), (actor) => {
      return { ...actor.state.position };
    });
  }

  syncFurnitureSprite(entry) {
    const sortY = this.furnitureSortY(entry);
    this.positionFurnitureLayers(entry, entry.state.position);
    for (const [index, layer] of entry.state.layers.entries()) {
      const sprite = entry.layerSprites.get(layer.id);
      if (!sprite) continue;
      if (entry.state.layer === "wall" || layer.role === "wall") {
        sprite.setDepth(1 + index * 0.01);
      } else if (entry.state.layer === "floor" || layer.role === "floor") {
        sprite.setDepth(2 + index * 0.01);
      } else if (layer.role === "front") {
        sprite.setDepth(sortY + 2 + index * 0.01);
      } else {
        sprite.setDepth(sortY - 2 + index * 0.01);
      }
    }
  }

  furnitureSortY(entry) {
    return (entry.state.footprint.y + entry.state.footprint.height) * TILE_SIZE;
  }

  rebuildFurnitureTiles() {
    this.furnitureTiles.clear();
    for (const { state } of this.furniture.values()) {
      if (state.blocking === false) continue;
      const { x, y, width, height } = state.footprint;
      for (let tileY = y; tileY < y + height; tileY += 1) {
        for (let tileX = x; tileX < x + width; tileX += 1) {
          this.furnitureTiles.add(this.tileKey(tileX, tileY));
        }
      }
    }
  }

  loadSavedLayout() {
    try {
      const saved = JSON.parse(localStorage.getItem(ROOM_LAYOUT_STORAGE_KEY));
      if (saved?.sceneId !== "home") return null;
      if (saved.positions) return saved.positions;
      if (!saved.items) return null;
      return Object.fromEntries(Object.entries(saved.items).flatMap(([id, item]) => {
        const position = item?.position ?? item;
        return this.isVisualPosition(position) ? [[id, position]] : [];
      }));
    } catch (_error) {
      return null;
    }
  }

  applySavedLayout() {
    const saved = this.loadSavedLayout();
    if (!saved) return;
    const layouts = new Map(Array.from(this.furniture.entries(), ([id, entry]) => (
      [id, this.layoutFromDefinition(
        entry.defaultPosition,
        entry.defaultFootprint,
        this.isVisualPosition(saved[id]) ? saved[id] : entry.defaultPosition,
      )]
    )));

    for (const [id, layout] of layouts) {
      const entry = this.furniture.get(id);
      entry.state.position = { ...layout.position };
      entry.state.footprint = { ...layout.footprint };
      this.syncFurnitureSprite(entry);
    }
  }

  saveFurnitureLayout() {
    const positions = Object.fromEntries(Array.from(this.furniture.entries(), ([id, entry]) => (
      [id, { ...entry.state.position }]
    )));
    try {
      localStorage.setItem(ROOM_LAYOUT_STORAGE_KEY, JSON.stringify({ sceneId: "home", positions }));
      this.publishLayoutSnapshot("saved", positions);
      return true;
    } catch (_error) {
      return false;
    }
  }

  publishLayoutSnapshot(reason, positions = null) {
    const current = positions ?? Object.fromEntries(Array.from(this.furniture.entries(), ([id, entry]) => (
      [id, { ...entry.state.position }]
    )));
    window.dispatchEvent(new CustomEvent("room:layout-snapshot", {
      detail: { sceneId: "home", reason, positions: current },
    }));
  }

  runtimeFurnitureId(serviceFurniture) {
    return serviceFurniture?.runtime_id
      ?? (serviceFurniture?.id === "workstation" ? "computer" : serviceFurniture?.id);
  }

  visualActionForActivity(activity) {
    if (activity === "moving") return "walking";
    if (activity === "watch_tv") return "watching_tv";
    if (String(activity).startsWith("sleep")) return "sleeping";
    if (String(activity).startsWith("rest")) return "resting";
    if (String(activity).startsWith("sit")) return "sitting";
    if (String(activity).startsWith("work")) return "working";
    if (String(activity).startsWith("read")) return "reading";
    return "idle";
  }

  applyAuthorityState(snapshot) {
    if (!snapshot || !Array.isArray(snapshot.characters)) return;
    this.remoteMode = true;
    for (const remoteFurniture of snapshot.furniture ?? []) {
      const entry = this.furniture.get(this.runtimeFurnitureId(remoteFurniture));
      if (!entry) continue;
      if (remoteFurniture.position) entry.state.position = { ...remoteFurniture.position };
      if (remoteFurniture.footprint) entry.state.footprint = { ...remoteFurniture.footprint };
      if (remoteFurniture.textureState) {
        entry.state.textureState = remoteFurniture.textureState;
        for (const layer of entry.state.layers) {
          if (!layer.textures) continue;
          entry.layerSprites.get(layer.id)?.setTexture(
            this.furnitureLayerTextureKey(entry.state, layer),
          );
        }
      }
      this.syncFurnitureSprite(entry);
    }
    this.rebuildFurnitureTiles();
    for (const remoteCharacter of snapshot.characters) {
      this.applyAuthorityCharacter(remoteCharacter);
    }
    this.refreshAllFurnitureActionVisuals();
    this.syncActorDecorations();
  }

  applyAuthorityCharacter(remote) {
    const actor = this.actors.get(remote.id);
    if (!actor || !remote.position) return;
    const movement = remote.movement;
    if (movement?.target) {
      const movementKey = `${movement.started_at}:${movement.target.x},${movement.target.y}`;
      if (actor.remoteMovementKey === movementKey && actor.path.length > 0) return;
      actor.remoteMovementKey = movementKey;
      this.releaseActorSlot(actor);
      actor.path = [];
      actor.sprite.setVelocity(0, 0);
      actor.state.position = { ...remote.position };
      actor.state.direction = remote.direction ?? actor.state.direction;
      const center = this.tileCenter(actor.state.position);
      actor.sprite.setPosition(center.x, center.y);
      const pending = movement.pending;
      actor.pendingInteraction = null;
      if (pending?.kind === "use") {
        const entry = this.furniture.get(
          pending.furniture_id === "workstation" ? "computer" : pending.furniture_id,
        );
        const slots = entry?.state.interactionSlots?.[pending.interaction] ?? [];
        const configured = slots.find((slot) => slot.id === pending.slot_id);
        const slot = configured
          ? { ...configured, reservable: true }
          : {
              id: pending.slot_id ?? pending.interaction,
              anchor: entry?.state.actionAnchors?.[pending.interaction] ?? null,
              reservable: false,
            };
        if (entry) {
          this.reserveFurnitureSlot(actor, entry.state.id, slot);
          actor.pendingInteraction = {
            furnitureId: entry.state.id,
            interaction: pending.interaction,
            slot,
          };
        }
      }
      this.moveCharacter(remote.id, movement.target, {
        showTarget: remote.id === "owner",
        forInteraction: true,
      });
      return;
    }

    delete actor.remoteMovementKey;
    actor.pendingInteraction = null;
    actor.path = [];
    actor.sprite.setVelocity(0, 0);
    this.releaseActorSlot(actor);
    actor.state.position = { ...remote.position };
    actor.state.direction = remote.direction ?? actor.state.direction;
    const center = this.tileCenter(actor.state.position);
    actor.sprite.setPosition(center.x, center.y);
    const serviceFurnitureId = remote.active_furniture_id;
    if (serviceFurnitureId && remote.interaction) {
      const runtimeId = serviceFurnitureId === "workstation" ? "computer" : serviceFurnitureId;
      const entry = this.furniture.get(runtimeId);
      if (entry) {
        const configured = (entry.state.interactionSlots?.[remote.interaction] ?? [])
          .find((slot) => slot.id === remote.slot_id);
        const slot = configured
          ? { ...configured, reservable: true }
          : {
              id: remote.slot_id ?? remote.interaction,
              anchor: entry.state.actionAnchors?.[remote.interaction] ?? null,
              reservable: false,
            };
        this.reserveFurnitureSlot(actor, runtimeId, slot);
        this.executeFurnitureAction(actor, {
          furnitureId: runtimeId,
          interaction: remote.interaction,
          slot,
        }, { publish: false, notice: false, toggleTexture: false });
        return;
      }
    }
    actor.state.action = this.visualActionForActivity(remote.activity);
    actor.sprite.setTexture(this.characterTextureKey(
      actor.state.id,
      actor.state.direction,
      "idle",
    )).setScale(1).setVisible(true).clearTint();
    actor.label.setVisible(true);
    this.clearActionFeedback(actor);
  }

  layoutFromDefinition(defaultPosition, defaultFootprint, position) {
    return {
      position: { x: position.x, y: position.y },
      footprint: {
        ...defaultFootprint,
        x: defaultFootprint.x + Math.round((position.x - defaultPosition.x) / TILE_SIZE),
        y: defaultFootprint.y + Math.round((position.y - defaultPosition.y) / TILE_SIZE),
      },
    };
  }

  isVisualPosition(position) {
    return Number.isFinite(position?.x) && Number.isFinite(position?.y);
  }

  async refreshFurnitureDefinitions() {
    if (this.refreshingDefinitions) return;
    this.refreshingDefinitions = true;
    try {
      const response = await fetch(`room/data/initial-state.json?refresh=${Date.now()}`, {
        cache: "no-store",
      });
      if (!response.ok) throw new Error(`Room definition refresh failed: ${response.status}`);
      const freshState = await response.json();
      const definitions = new Map(freshState.furniture.map((item) => [item.id, item]));
      const layouts = new Map();

      for (const [id, entry] of this.furniture) {
        const definition = definitions.get(id);
        if (!definition?.footprint || !this.isVisualPosition(definition.position)) {
          layouts.set(id, {
            position: { ...entry.state.position },
            footprint: { ...entry.state.footprint },
          });
          continue;
        }

        const position = { ...entry.state.position };
        const layout = this.layoutFromDefinition(
          definition.position,
          definition.footprint,
          position,
        );
        entry.state = {
          ...JSON.parse(JSON.stringify(definition)),
          position,
          footprint: { ...layout.footprint },
        };
        entry.defaultPosition = { ...definition.position };
        entry.defaultFootprint = { ...definition.footprint };
        for (const layer of entry.state.layers) {
          const sprite = entry.layerSprites.get(layer.id);
          const textureKey = this.furnitureLayerTextureKey(entry.state, layer);
          if (sprite && this.textures.exists(textureKey)) sprite.setTexture(textureKey);
        }
        this.syncFurnitureSprite(entry);
        layouts.set(id, layout);
      }

      this.rebuildFurnitureTiles();
      this.refreshAllFurnitureActionVisuals();
      const layoutValid = this.isLayoutValid(layouts, this.currentActorTiles());
      const saved = this.saveFurnitureLayout();
      this.publishState();
      if (!layoutValid) {
        this.publishNotice("房间已刷新并保留位置；发现占地冲突，请继续调整家具");
      } else if (!saved) {
        this.publishNotice("房间已刷新，但浏览器没有允许保存当前位置");
      } else {
        this.publishNotice("房间已刷新：位置保留，占地与动作锚点已更新");
      }
      window.dispatchEvent(new CustomEvent("room:layout-refreshed", {
        detail: { ok: true, layoutValid, saved },
      }));
    } catch (_error) {
      this.publishNotice("房间刷新失败，当前布局已保留");
      window.dispatchEvent(new CustomEvent("room:layout-refreshed", {
        detail: { ok: false },
      }));
    } finally {
      this.refreshingDefinitions = false;
    }
  }

  directionForDelta(dx, dy) {
    if (Math.abs(dx) >= Math.abs(dy)) return dx < 0 ? "left" : "right";
    return dy < 0 ? "up" : "down";
  }

  tileCenter(tile) {
    return {
      x: tile.x * TILE_SIZE + TILE_SIZE / 2,
      y: tile.y * TILE_SIZE + TILE_SIZE / 2,
    };
  }

  tileKey(x, y) {
    return `${x},${y}`;
  }

  characterClothes(state) {
    const role = this.characterPack.roles[state.id];
    if (role?.outfits?.[state.clothes]) return state.clothes;
    return role?.defaultOutfit || Object.keys(role?.outfits ?? {})[0];
  }

  characterOutfitId(id, requested = null) {
    const role = this.characterPack.roles[id];
    const active = requested || this.actors.get(id)?.state?.clothes;
    if (role?.outfits?.[active]) return active;
    return role?.defaultOutfit || Object.keys(role?.outfits ?? {})[0];
  }

  characterTextureKey(id, direction, frame, outfitId = null) {
    const outfit = this.characterOutfitId(id, outfitId);
    return `character-${id}-${outfit}-${direction}-${frame}`;
  }

  characterActionTextureKey(id, pose, frame = null, outfitId = null) {
    const outfit = this.characterOutfitId(id, outfitId);
    return `character-${id}-${outfit}-${pose}${frame === null ? "" : `-${frame}`}`;
  }

  duoActionTextureKey(id) {
    return `duo-action-${id}`;
  }

  characterFramePath(role, family, direction, frame = null) {
    const configured = role.frames?.[family];
    if (typeof configured === "string") return configured;
    const directional = configured?.[direction];
    const path = frame === null ? directional : directional?.[frame];
    if (!path) throw new Error(`Missing ${family} path for ${direction}${frame === null ? "" : `:${frame}`}`);
    return path;
  }

  characterActionPath(role, pose, frame = null) {
    const configured = role.frames?.actions;
    if (typeof configured === "string") return configured;
    const action = configured?.[pose];
    const path = frame === null ? action : action?.[frame];
    if (!path) throw new Error(`Missing action path for ${pose}${frame === null ? "" : `:${frame}`}`);
    return path;
  }

  createPlaceholderTileset() {
    const texture = this.textures.createCanvas("room-placeholder-tiles", TILE_SIZE * 3, TILE_SIZE);
    texture.context.clearRect(0, 0, TILE_SIZE * 3, TILE_SIZE);
    texture.refresh();
  }

  configureCharacterTextures() {
    for (const [id, role] of Object.entries(this.characterPack.roles)) {
      for (const outfitId of Object.keys(role.outfits)) {
        for (const direction of DIRECTIONS) {
          for (const frame of WALK_FRAME_SEQUENCE) {
            const key = this.characterTextureKey(id, direction, frame, outfitId);
            if (!this.textures.exists(key)) {
              throw new Error(`Missing Room character asset: ${key}`);
            }
            this.textures.get(key).setFilter(Phaser.Textures.FilterMode.NEAREST);
          }
        }
        for (const pose of ["sit", "sleep", "rest", "read"]) {
          const key = this.characterActionTextureKey(id, pose, null, outfitId);
          if (!this.textures.exists(key)) throw new Error(`Missing Room action pose: ${key}`);
          this.textures.get(key).setFilter(Phaser.Textures.FilterMode.NEAREST);
        }
        for (const frame of [0, 1]) {
          const key = this.characterActionTextureKey(id, "work", frame, outfitId);
          if (!this.textures.exists(key)) throw new Error(`Missing Room work pose: ${key}`);
          this.textures.get(key).setFilter(Phaser.Textures.FilterMode.NEAREST);
        }
      }
    }
  }

  configureFurnitureTextures() {
    for (const key of Object.keys(this.furnitureManifest.textures)) {
      const textureKey = `furniture-${key}`;
      if (!this.textures.exists(textureKey)) {
        throw new Error(`Missing Room furniture texture: ${textureKey}`);
      }
      this.textures.get(textureKey).setFilter(Phaser.Textures.FilterMode.NEAREST);
    }
  }

  configureDuoActionTextures() {
    for (const item of this.actionPack.duoActions ?? []) {
      const textureKey = this.duoActionTextureKey(item.id);
      if (!this.textures.exists(textureKey)) {
        throw new Error(`Missing Room duo action texture: ${textureKey}`);
      }
      this.textures.get(textureKey).setFilter(Phaser.Textures.FilterMode.NEAREST);
    }
  }

}
