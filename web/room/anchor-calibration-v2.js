const CONFIG_ROOT = "room/assets/room-v2/config";
const CONFIG_URLS = {
  furnitureManifest: `${CONFIG_ROOT}/furniture-manifest.json`,
  characterPack: `${CONFIG_ROOT}/character-pack.json`,
  actionPack: `${CONFIG_ROOT}/action-pack.json`,
};

const status = document.getElementById("page-status");
const roleList = document.getElementById("role-list");
const duoList = document.getElementById("duo-list");
const manifestOutput = document.getElementById("manifest-output");

async function fetchJson(url) {
  const response = await fetch(url, { cache: "no-store" });
  if (!response.ok) throw new Error(`${url} returned ${response.status}`);
  return response.json();
}

function representativePath(role) {
  const outfit = role.outfits?.[role.defaultOutfit] ?? Object.values(role.outfits ?? {})[0];
  const idle = outfit?.frames?.idle;
  return typeof idle === "string" ? idle : idle?.down;
}

function makeRoleCard(roleId, role) {
  const card = document.createElement("article");
  card.className = "calibration-card";

  const header = document.createElement("header");
  const title = document.createElement("h3");
  title.textContent = `${role.displayName} · ${roleId}`;
  const note = document.createElement("p");
  note.textContent = `显示尺寸 ${role.displaySize.join("×")}；资源路径来自 character-pack.json。`;
  header.append(title, note);

  const layout = document.createElement("div");
  layout.className = "character-layout";
  const stage = document.createElement("div");
  stage.className = "preview-stage character-stage";
  const image = document.createElement("img");
  image.className = "stage-layer";
  image.src = representativePath(role);
  image.alt = `${role.displayName} placeholder`;
  image.style.inset = "8%";
  image.style.width = "84%";
  image.style.height = "84%";
  stage.append(image);

  const output = document.createElement("pre");
  output.className = "config-output";
  output.textContent = JSON.stringify({ id: roleId, ...role }, null, 2);
  layout.append(stage, output);
  card.append(header, layout);
  return card;
}

function numberControl(label, value, step, onChange) {
  const wrapper = document.createElement("label");
  wrapper.textContent = label;
  const input = document.createElement("input");
  input.type = "number";
  input.value = String(value);
  input.step = String(step);
  input.addEventListener("input", () => onChange(Number(input.value)));
  wrapper.append(input);
  return wrapper;
}

function makeDuoCard(item) {
  const current = {
    x: Number(item.transform?.x) || 0,
    y: Number(item.transform?.y) || 0,
    scale: Number(item.transform?.scale) || 1,
  };
  const card = document.createElement("article");
  card.className = "calibration-card duo-calibration-card";
  const title = document.createElement("h3");
  title.textContent = `${item.id} · ${item.furniture}`;

  const layout = document.createElement("div");
  layout.className = "calibration-layout";
  const stage = document.createElement("div");
  stage.className = "preview-stage furniture-stage";
  stage.style.setProperty("--stage-ratio", "4 / 3");
  const image = document.createElement("img");
  image.className = "stage-layer duo-actor";
  image.src = item.path;
  image.alt = item.id;
  image.style.left = "50%";
  image.style.bottom = "8%";
  image.style.maxWidth = "80%";
  image.style.maxHeight = "80%";
  image.style.transformOrigin = "50% 100%";
  stage.append(image);

  const controls = document.createElement("div");
  controls.className = "controls";
  const output = document.createElement("pre");
  output.className = "config-output";
  const update = () => {
    image.style.transform = `translate(calc(-50% + ${current.x}px), ${current.y}px) scale(${current.scale})`;
    output.textContent = JSON.stringify({ ...item, transform: { ...current } }, null, 2);
  };
  controls.append(
    numberControl("X", current.x, 1, (value) => { current.x = value; update(); }),
    numberControl("Y", current.y, 1, (value) => { current.y = value; update(); }),
    numberControl("统一缩放", current.scale, 0.01, (value) => { current.scale = value; update(); }),
    output,
  );
  layout.append(stage, controls);
  card.append(title, layout);
  update();
  return card;
}

async function boot() {
  const entries = await Promise.all(
    Object.entries(CONFIG_URLS).map(async ([key, url]) => [key, await fetchJson(url)]),
  );
  const config = Object.fromEntries(entries);

  for (const [roleId, role] of Object.entries(config.characterPack.roles)) {
    roleList.append(makeRoleCard(roleId, role));
  }
  const duoActions = config.actionPack.duoActions ?? [];
  if (duoActions.length === 0) {
    const empty = document.createElement("p");
    empty.className = "notice";
    empty.textContent = "当前动作包未提供双人合成图；正式 Room 将使用两个独立人物动作。";
    duoList.append(empty);
  } else {
    for (const item of duoActions) duoList.append(makeDuoCard(item));
  }

  manifestOutput.textContent = JSON.stringify({
    furnitureSchema: config.furnitureManifest.schemaVersion,
    characterSchema: config.characterPack.schemaVersion,
    actionSchema: config.actionPack.schemaVersion,
    roles: Object.keys(config.characterPack.roles),
    furnitureTextures: Object.keys(config.furnitureManifest.textures).length,
    duoActions: duoActions.length,
  }, null, 2);
  status.textContent = "公共配置已加载";
  status.classList.add("is-ready");
}

boot().catch((error) => {
  status.textContent = `校准页启动失败：${error.message}`;
  status.classList.add("is-error");
  console.error(error);
});
