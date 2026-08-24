import { RoomScene } from "./scenes/RoomScene.js?v=29";
import { RoomServiceClient } from "./RoomServiceClient.js?v=1";

const Phaser = globalThis.Phaser;
const loading = document.getElementById("room-loading");
const status = document.getElementById("room-status");
const actions = document.getElementById("room-actions");
const buildToggle = document.getElementById("room-build-toggle");
const buildRefresh = document.getElementById("room-build-refresh");
const buildHint = document.getElementById("room-build-hint");
const cameraSlider = document.getElementById("room-camera-slider");
const cameraZoom = document.getElementById("room-camera-zoom");
const characterCards = document.getElementById("room-character-cards");
let engineSummary = "Phaser 4.2.1";
let latestCharacters = [];
let latestAuthorityState = null;
let latestLayout = null;
let noticeTimer = null;
let buildMode = false;
let serviceConnected = false;
let layoutBootstrapped = false;
let roomViewportSize = { width: 1280, height: 720 };
const roomService = new RoomServiceClient();
const RUNTIME_CONFIG_URLS = {
  furnitureManifest: "room/assets/room-v2/config/furniture-manifest.json",
  characterPack: "room/assets/room-v2/config/character-pack.json",
  actionPack: "room/assets/room-v2/config/action-pack.json",
};
const ACTIVITY_LABELS = {
  idle: "空闲",
  moving: "走动中",
  sleep: "睡觉中",
  rest: "休息中",
  sit: "坐着",
  work: "工作中",
  read: "看书中",
  watch_tv: "看电视",
  sleep_together: "一起睡觉中",
  rest_together: "一起休息中",
  sit_together: "一起坐着",
  work_together: "一起工作中",
  read_together: "一起看书中",
};
const FURNITURE_LABELS = {
  bed: "床",
  sofa: "沙发",
  workstation: "双人工位",
  computer: "双人工位",
  television: "电视区",
  rug: "地毯",
  "coffee-table": "茶几",
  dresser: "斗柜",
  wardrobe: "衣柜",
  bookcase: "书架阅读区",
  "lounge-area": "娱乐区",
};
const INTERACTION_LABELS = {
  sleep: "睡觉",
  rest: "休息",
  sit: "坐下",
  work: "工作",
  read: "看书",
  toggle_tv: "开电视",
};
window.addEventListener("pointerdown", (pointerEvent) => {
  const actionButton = pointerEvent.target instanceof Element
    ? pointerEvent.target.closest(".room-action-button")
    : null;
  if (!actionButton || !actions?.contains(actionButton)) return;

  pointerEvent.preventDefault();
  pointerEvent.stopImmediatePropagation();
  const { furnitureId, interaction } = actionButton.dataset;
  if (!furnitureId || !interaction) return;
  if (roomService.connected) {
    roomService.useFurniture(furnitureId, interaction).catch((error) => {
      window.dispatchEvent(new CustomEvent("room:notice", {
        detail: { message: error.message || "家具暂时不能使用" },
      }));
    });
  } else {
    window.dispatchEvent(new CustomEvent("room:interact", {
      detail: { furnitureId, interaction, actorId: "owner" },
    }));
  }
}, { capture: true });

function renderCharacterStatus() {
  if (!status) return;
  status.textContent = `${engineSummary} · ${serviceConnected ? "共享状态已连接" : "本地模式"}`;
}

function localActivity(character) {
  return {
    idle: "idle",
    walking: "moving",
    sleeping: "sleep",
    resting: "rest",
    sitting: "sit",
    working: "work",
    reading: "read",
    watching_tv: "watch_tv",
  }[character.action] || character.action;
}

function renderCharacterCards(characters) {
  if (!characterCards) return;
  const byId = new Map((characters || []).map((character) => [character.id, character]));
  for (const characterId of ["owner", "companion"]) {
    const card = characterCards.querySelector(`[data-character-card="${characterId}"]`);
    const character = byId.get(characterId);
    if (!card || !character) continue;
    const displayName = character.display_name
      || character.displayName
      || globalThis.ROOM_MCP_KIT_RUNTIME?.characterPack?.roles?.[characterId]?.displayName
      || characterId;
    const activity = character.activity || localActivity(character);
    const mood = character.mood;
    const activeFurniture = character.active_furniture_id;
    const location = activeFurniture
      ? FURNITURE_LABELS[activeFurniture] || activeFurniture
      : `位置 ${character.position.x}, ${character.position.y}`;
    card.querySelector("[data-character-activity]").textContent = ACTIVITY_LABELS[activity] || activity;
    card.querySelector("[data-character-location]").textContent = location;
    card.querySelector("[data-character-mood]").textContent = mood?.label
      ? `心情：${mood.label}`
      : "心情：未设置";
    card.querySelector("strong").textContent = displayName;
  }
}

function showReady(detail) {
  loading?.classList.add("is-ready");
  status?.classList.add("is-ready");
  engineSummary = `Phaser 4.2.1 · ${detail.renderer}`;
  roomViewportSize = { width: detail.width, height: detail.height };
  renderCharacterStatus();
}

function setBuildMode(enabled) {
  buildMode = enabled;
  buildToggle?.setAttribute("aria-pressed", String(enabled));
  buildToggle?.classList.toggle("is-active", enabled);
  const label = buildToggle?.querySelector(".room-build-toggle-label");
  if (label) label.textContent = enabled ? "完成摆放" : "建造模式";
  if (buildRefresh) buildRefresh.hidden = !enabled;
  if (buildHint) buildHint.hidden = !enabled;
  if (enabled && actions) {
    actions.replaceChildren();
    actions.hidden = true;
  }
  window.dispatchEvent(new CustomEvent("room:build-mode", { detail: { enabled } }));
}

buildToggle?.addEventListener("click", () => setBuildMode(!buildMode));
cameraSlider?.addEventListener("input", () => {
  window.dispatchEvent(new CustomEvent("room:camera-x", {
    detail: { ratio: Number(cameraSlider.value) / 1000 },
  }));
});
buildRefresh?.addEventListener("click", () => {
  buildRefresh.disabled = true;
  buildRefresh.textContent = "刷新中…";
  window.dispatchEvent(new CustomEvent("room:refresh-layout"));
});
window.addEventListener("room:layout-refreshed", () => {
  if (!buildRefresh) return;
  buildRefresh.disabled = false;
  buildRefresh.textContent = "刷新房间";
});

window.addEventListener("room:ready", (event) => showReady(event.detail), { once: true });
window.addEventListener("room:state", (event) => {
  latestCharacters = event.detail.characters;
  clearTimeout(noticeTimer);
  renderCharacterStatus();
  if (!latestAuthorityState) renderCharacterCards(latestCharacters);
});
window.addEventListener("room:authority-state", (event) => {
  latestAuthorityState = event.detail;
  renderCharacterCards(event.detail.characters);
});
window.addEventListener("room:service", (event) => {
  serviceConnected = Boolean(event.detail.connected);
  window.dispatchEvent(new CustomEvent("room:remote-mode", {
    detail: { enabled: serviceConnected },
  }));
  renderCharacterStatus();
});
window.addEventListener("room:layout-snapshot", (event) => {
  latestLayout = event.detail.positions;
  if (roomService.connected && event.detail.reason === "saved") {
    roomService.saveLayout(latestLayout).catch((error) => {
      window.dispatchEvent(new CustomEvent("room:notice", {
        detail: { message: error.message || "家具布局保存失败" },
      }));
    });
  }
});
window.addEventListener("room:move-request", (event) => {
  if (!roomService.connected) return;
  roomService.moveOwner({ kind: "tile", ...event.detail.target }).catch((error) => {
    window.dispatchEvent(new CustomEvent("room:notice", {
      detail: { message: error.message || "这里暂时走不过去" },
    }));
  });
});
window.addEventListener("room:notice", (event) => {
  if (!status) return;
  clearTimeout(noticeTimer);
  status.textContent = event.detail.message;
  noticeTimer = setTimeout(renderCharacterStatus, 1400);
});
window.addEventListener("room:camera", (event) => {
  if (event.detail.viewportWidth && event.detail.viewportHeight) {
    roomViewportSize = {
      width: event.detail.viewportWidth,
      height: event.detail.viewportHeight,
    };
  }
  if (cameraSlider && document.activeElement !== cameraSlider) {
    cameraSlider.value = String(Math.round(event.detail.ratio * 1000));
  }
  if (cameraZoom) {
    cameraZoom.textContent = `${Math.round((event.detail.zoomRatio ?? event.detail.zoom) * 100)}%`;
  }
});
window.addEventListener("room:interaction", (event) => {
  if (!actions) return;
  const furniture = event.detail.furniture;
  const anchor = event.detail.anchor;
  const viewport = event.detail.viewport ?? roomViewportSize;
  actions.replaceChildren();

  if (buildMode || !furniture) {
    actions.hidden = true;
    return;
  }

  for (const interaction of furniture.interactions) {
    const button = document.createElement("button");
    button.type = "button";
    button.className = "room-action-button";
    button.dataset.furnitureId = furniture.id;
    button.dataset.interaction = interaction;
    button.textContent = interaction === "toggle_tv"
      ? (furniture.textureState === "on" ? "关电视" : "开电视")
      : (INTERACTION_LABELS[interaction] ?? interaction);
    button.addEventListener("click", (clickEvent) => {
      clickEvent.preventDefault();
      clickEvent.stopPropagation();
    });
    actions.append(button);

  }

  if (anchor) {
    actions.style.left = `${anchor.x / viewport.width * 100}%`;
    actions.style.top = `${anchor.y / viewport.height * 100}%`;
  }
  actions.hidden = false;
});

if (!Phaser) {
  if (status) status.textContent = "Phaser 未能加载";
  if (loading) loading.textContent = "房间启动失败";
  throw new Error("Phaser 4.2.1 was not loaded before Room main.js");
}

async function loadRuntimeConfig() {
  const entries = await Promise.all(
    Object.entries(RUNTIME_CONFIG_URLS).map(async ([key, url]) => {
      const response = await fetch(url, { cache: "no-store" });
      if (!response.ok) throw new Error(`${url} returned ${response.status}`);
      return [key, await response.json()];
    }),
  );
  return Object.fromEntries(entries);
}

async function startRoom() {
  globalThis.ROOM_MCP_KIT_RUNTIME = await loadRuntimeConfig();
  new Phaser.Game({
    type: Phaser.AUTO,
    parent: "room-game",
    width: 1280,
    height: 720,
    backgroundColor: "#edc59f",
    pixelArt: true,
    antialias: false,
    roundPixels: true,
    render: {
      antialias: false,
      pixelArt: true,
      roundPixels: true,
    },
    scale: {
      mode: Phaser.Scale.RESIZE,
    },
    input: {
      activePointers: 3,
    },
    physics: {
      default: "arcade",
      arcade: {
        gravity: { x: 0, y: 0 },
        debug: false,
      },
    },
    scene: [RoomScene],
  });
}

startRoom().catch((error) => {
  if (status) status.textContent = "房间配置加载失败";
  if (loading) loading.textContent = "房间启动失败";
  console.error(error);
});

window.addEventListener("room:ready", async () => {
  const state = await roomService.connect();
  if (!state) return;
  if (state.revision === 0 && latestLayout && !layoutBootstrapped) {
    layoutBootstrapped = true;
    roomService.saveLayout(latestLayout).catch(() => {});
  }
}, { once: true });
window.addEventListener("pagehide", () => roomService.close(), { once: true });
