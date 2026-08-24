export class RoomServiceClient {
  constructor() {
    const config = globalThis.ROOM_MCP_KIT_CONFIG ?? {};
    this.apiRoot = String(config.apiBase || "/api/v1/room").replace(/\/$/, "");
    this.connected = false;
    this.eventSource = null;
    this.eventCursor = 0;
    this.refreshTimer = null;
  }

  async request(path, options = {}) {
    const response = await fetch(`${this.apiRoot}/${path}`, {
      credentials: "same-origin",
      cache: "no-store",
      ...options,
      headers: {
        ...(options.body ? { "Content-Type": "application/json" } : {}),
        ...(options.headers || {}),
      },
    });
    if (!response.ok) {
      let message = `Room service ${response.status}`;
      try {
        const body = await response.json();
        message = body.detail || message;
      } catch (_error) {
        // Keep the status fallback.
      }
      throw new Error(message);
    }
    return response.json();
  }

  async connect() {
    try {
      const state = await this.request("state");
      this.connected = true;
      this.applyState(state);
      this.connectEvents();
      window.dispatchEvent(new CustomEvent("room:service", {
        detail: { connected: true },
      }));
      return state;
    } catch (_error) {
      this.connected = false;
      window.dispatchEvent(new CustomEvent("room:service", {
        detail: { connected: false },
      }));
      return null;
    }
  }

  applyState(state) {
    this.eventCursor = Number(state.event_cursor) || this.eventCursor;
    window.dispatchEvent(new CustomEvent("room:authority-state", { detail: state }));
  }

  async refresh() {
    if (!this.connected) return null;
    const state = await this.request("state");
    this.applyState(state);
    return state;
  }

  connectEvents() {
    this.eventSource?.close();
    this.eventSource = new EventSource(
      `${this.apiRoot}/events?after=${encodeURIComponent(this.eventCursor)}`,
      { withCredentials: true },
    );
    this.eventSource.onmessage = () => this.scheduleRefresh();
    for (const type of [
      "character_move_started",
      "character_transition_completed",
      "furniture_use_started",
      "character_stopped",
      "layout_changed",
      "character_moods_updated",
    ]) {
      this.eventSource.addEventListener(type, () => this.scheduleRefresh());
    }
    this.eventSource.onerror = () => {
      window.dispatchEvent(new CustomEvent("room:service", {
        detail: { connected: this.connected, reconnecting: true },
      }));
    };
  }

  scheduleRefresh() {
    clearTimeout(this.refreshTimer);
    this.refreshTimer = setTimeout(() => {
      this.refresh().catch(() => {});
    }, 80);
  }

  async moveOwner(target) {
    const state = await this.request("characters/owner/move", {
      method: "POST",
      body: JSON.stringify({ target }),
    });
    this.applyState(state);
    return state;
  }

  async useFurniture(furnitureId, interaction) {
    const state = await this.request("characters/owner/use", {
      method: "POST",
      body: JSON.stringify({ furniture_id: furnitureId, interaction }),
    });
    this.applyState(state);
    return state;
  }

  async stopOwner() {
    const state = await this.request("characters/owner/stop", { method: "POST" });
    this.applyState(state);
    return state;
  }

  async saveLayout(positions) {
    const state = await this.request("layout", {
      method: "PUT",
      body: JSON.stringify({ positions }),
    });
    this.applyState(state);
    return state;
  }

  close() {
    clearTimeout(this.refreshTimer);
    this.eventSource?.close();
    this.eventSource = null;
  }
}
