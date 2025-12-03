// Minimal Cloudflare Worker + Durable Object implementation for shared draw rooms.
// Works on free Workers plan (no external DB, state lives in Durable Object).

const faviconSvg = `<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 100 100">
  <rect width="100" height="100" rx="15" fill="#000"/>
  <circle cx="30" cy="30" r="8" fill="#fff"/>
  <circle cx="50" cy="50" r="8" fill="#fff"/>
  <circle cx="70" cy="30" r="8" fill="#fff"/>
  <circle cx="30" cy="70" r="8" fill="#fff"/>
  <circle cx="70" cy="70" r="8" fill="#fff"/>
</svg>`;

export default {
  async fetch(request, env, ctx) {
    const url = new URL(request.url);

    // Health check
    if (url.pathname === "/health") {
      return new Response("ok");
    }

    // Serve favicon
    if (url.pathname === "/favicon.svg") {
      return new Response(faviconSvg, {
        status: 200,
        headers: { "content-type": "image/svg+xml" },
      });
    }

    // Create a new room
    if (url.pathname === "/create-room" && request.method === "POST") {
      const roomId = shortId();
      return json({
        roomId,
        joinUrl: `${url.origin}/room/${roomId}`,
      });
    }

    // WebSocket upgrade routed to the room Durable Object
    const wsMatch = url.pathname.match(/^\/ws\/room\/([A-Za-z0-9-]+)$/);
    if (wsMatch && request.headers.get("Upgrade") === "websocket") {
      const roomId = wsMatch[1];
      const id = env.ROOM_DO.idFromName(roomId);
      const stub = env.ROOM_DO.get(id);
      return stub.fetch(request);
    }

    // Room page (simple static HTML/JS)
    const roomPageMatch = url.pathname.match(/^\/room\/([A-Za-z0-9-]+)$/);
    if (roomPageMatch && request.method === "GET") {
      return html(renderApp(roomPageMatch[1]));
    }

    // Landing page
    if (url.pathname === "/" && request.method === "GET") {
      return html(renderApp(""));
    }

    return new Response("not found", { status: 404 });
  },
};

// Durable Object for a single room
export class RoomDurableObject {
  constructor(state, env) {
    this.state = state;
    this.env = env;
    this.clients = new Map(); // clientId -> WebSocket
    this.names = new Map(); // clientId -> name
    this.lastResult = null;
    this.listItems = [];
    this.drawnHistory = [];
    this.withReplacement = true;
    this.remainingIndices = [];
  }

  async fetch(request) {
    if (request.headers.get("Upgrade") !== "websocket") {
      return new Response("room ready", { status: 200 });
    }

    const pair = new WebSocketPair();
    const [client, server] = Object.values(pair);
    this.handleSession(server);
    return new Response(null, { status: 101, webSocket: client });
  }

  handleSession(socket) {
    socket.accept();
    const clientId = crypto.randomUUID();
    const defaultName = `Guest-${clientId.slice(0, 5)}`;

    this.clients.set(clientId, socket);
    this.names.set(clientId, defaultName);

    // Send last result to newcomer
    if (this.lastResult) {
      socket.send(JSON.stringify({ type: "result", ...this.lastResult }));
    }

    // Send list state if any
    if (this.listItems.length) {
      socket.send(
        JSON.stringify({
          type: "list_state",
          items: this.listItems,
          drawn: this.withReplacement ? [] : this.drawnHistory,
          withReplacement: this.withReplacement,
        })
      );
    }

    this.broadcastUsers();

    socket.addEventListener("message", (event) => {
      try {
        this.handleMessage(clientId, event.data);
      } catch (err) {
        console.error("message error", err);
      }
    });

    const closeHandler = () => this.disconnect(clientId);
    socket.addEventListener("close", closeHandler);
    socket.addEventListener("error", closeHandler);
  }

  handleMessage(clientId, data) {
    let msg;
    try {
      msg = JSON.parse(data);
    } catch {
      return;
    }

    const socket = this.clients.get(clientId);
    if (!socket) return;

    if (msg.type === "ping") {
      socket.send(JSON.stringify({ type: "pong" }));
      return;
    }

    if (msg.type === "join") {
      const safeName = sanitizeName(msg.name);
      this.names.set(clientId, safeName);
      this.broadcastUsers();
      return;
    }

    if (msg.type === "set_list") {
      const { items, withReplacement } = sanitizeListPayload(msg);
      if (!items.length) {
        socket.send(
          JSON.stringify({ type: "error", message: "List is empty" })
        );
        return;
      }
      this.listItems = items;
      this.withReplacement = withReplacement;
      this.drawnHistory = [];
      this.remainingIndices = items.map((_, idx) => idx);
      this.broadcastList();
      return;
    }

    if (msg.type === "draw") {
      const mode = msg.mode === "coin" ? "coin" : msg.mode === "list" ? "list" : "number";
      let result;

      if (mode === "coin") {
        result = Math.random() < 0.5 ? "Heads" : "Tails";
      } else if (mode === "number") {
        const min = clampInt(msg.min ?? 1, -1_000_000, 1_000_000);
        const max = clampInt(msg.max ?? 100, -1_000_000, 1_000_000);
        if (min > max) {
          socket.send(
            JSON.stringify({ type: "error", message: "min cannot exceed max" })
          );
          return;
        }
        const span = max - min + 1;
        result = String(min + Math.floor(Math.random() * span));
      } else {
        // list mode
        if (!this.listItems.length) {
          socket.send(
            JSON.stringify({
              type: "error",
              message: "Add a list before drawing",
            })
          );
          return;
        }
        if (this.withReplacement) {
          const idx = Math.floor(Math.random() * this.listItems.length);
          result = this.listItems[idx];
        } else {
          if (!this.remainingIndices.length) {
            socket.send(
              JSON.stringify({
                type: "error",
                message: "All items already drawn",
              })
            );
            return;
          }
          const pick = Math.floor(Math.random() * this.remainingIndices.length);
          const idx = this.remainingIndices.splice(pick, 1)[0];
          result = this.listItems[idx];
          this.drawnHistory.push(result);
          this.broadcastList(); // update drawn list for clients
        }
      }

      const payload = {
        type: "result",
        mode,
        result,
        by: this.names.get(clientId) || "Guest",
        ts: Date.now(),
      };

      this.lastResult = payload;
      this.broadcast(payload);
      return;
    }
  }

  disconnect(clientId) {
    const socket = this.clients.get(clientId);
    if (socket) {
      try {
        socket.close();
      } catch {
        // ignore
      }
    }
    this.clients.delete(clientId);
    this.names.delete(clientId);
    this.broadcastUsers();
  }

  broadcastUsers() {
    const users = Array.from(this.names.values());
    this.broadcast({ type: "users", users });
  }

  broadcastList() {
    this.broadcast({
      type: "list_state",
      items: this.listItems,
      drawn: this.withReplacement ? [] : this.drawnHistory,
      withReplacement: this.withReplacement,
    });
  }

  broadcast(payload) {
    const dead = [];
    const message = JSON.stringify(payload);
    for (const [id, ws] of this.clients.entries()) {
      try {
        ws.send(message);
      } catch {
        dead.push(id);
      }
    }
    dead.forEach((id) => this.disconnect(id));
  }
}

// Helpers
const sanitizeName = (name) => {
  if (!name || typeof name !== "string") return "Guest";
  const trimmed = name.trim();
  if (!trimmed) return "Guest";
  return trimmed.slice(0, 32);
};

const clampInt = (value, min, max) => {
  const num = Number.parseInt(value, 10);
  if (Number.isNaN(num)) return min;
  return Math.min(Math.max(num, min), max);
};

const shortId = () => {
  const buf = new Uint32Array(2);
  crypto.getRandomValues(buf);
  return (buf[0].toString(36) + buf[1].toString(36)).slice(0, 8);
};

const sanitizeListPayload = (msg) => {
  const rawItems = Array.isArray(msg.items) ? msg.items : [];
  const trimmed = rawItems
    .map((s) => (typeof s === "string" ? s.trim() : ""))
    .filter((s) => s)
    .slice(0, 200); // cap to keep payload small
  const withReplacement = msg.withReplacement !== false; // default true
  return { items: trimmed, withReplacement };
};

const json = (obj) =>
  new Response(JSON.stringify(obj), {
    status: 200,
    headers: { "content-type": "application/json" },
  });

const html = (body) =>
  new Response(body, {
    status: 200,
    headers: { "content-type": "text/html; charset=utf-8" },
  });

// Single-page HTML for landing + room.
const renderApp = (roomId) => /* html */ `<!doctype html>
<html lang="en">
<head>
  <meta charset="UTF-8" />
  <meta name="viewport" content="width=device-width, initial-scale=1" />
  <title>Quick Draw</title>
  <link rel="icon" type="image/svg+xml" href="/favicon.svg" />
  <link rel="preconnect" href="https://fonts.googleapis.com">
  <link rel="preconnect" href="https://fonts.gstatic.com" crossorigin>
  <link href="https://fonts.googleapis.com/css2?family=DM+Serif+Display&family=Inter:wght@400;500;600;700&display=swap" rel="stylesheet">
  <style>
    :root {
      color-scheme: light;
      --bg-primary: #ffffff;
      --bg-secondary: #fafafa;
      --bg-card: #ffffff;
      --bg-elevated: #f5f5f5;
      --accent-primary: #000000;
      --accent-secondary: #333333;
      --text-primary: #000000;
      --text-secondary: #666666;
      --text-muted: #999999;
      --border-light: #e5e5e5;
      --border-medium: #cccccc;
      --border-strong: #000000;
      --shadow-sm: 0 1px 3px rgba(0,0,0,0.08);
      --shadow-md: 0 4px 12px rgba(0,0,0,0.1);
      --shadow-lg: 0 8px 24px rgba(0,0,0,0.12);
    }
    * { box-sizing: border-box; }
    body {
      font-family: "Inter", system-ui, -apple-system, sans-serif;
      margin: 0;
      background: var(--bg-primary);
      color: var(--text-primary);
      line-height: 1.6;
      -webkit-font-smoothing: antialiased;
      padding-bottom: 48px;
    }
    main { max-width: 1200px; margin: 0 auto; padding: 32px 20px 80px; }

    /* Header */
    .header-card {
      background: var(--bg-card);
      border-top: 3px solid var(--border-strong);
      border-bottom: 1px solid var(--border-light);
      padding: 32px 0 24px;
      margin-bottom: 32px;
    }
    .header-content {
      display: flex;
      justify-content: space-between;
      align-items: baseline;
      gap: 20px;
      flex-wrap: wrap;
    }

    /* Typography */
    h1 {
      margin: 0 0 8px;
      font-size: clamp(32px, 5vw, 56px);
      letter-spacing: -0.03em;
      font-family: "DM Serif Display", Georgia, serif;
      color: var(--text-primary);
      font-weight: 400;
      line-height: 1.1;
    }
    h2 {
      margin: 0 0 20px;
      font-size: 28px;
      letter-spacing: -0.02em;
      color: var(--text-primary);
      font-weight: 600;
      font-family: "DM Serif Display", Georgia, serif;
    }
    h3 {
      margin: 0 0 12px;
      font-size: 11px;
      color: var(--text-secondary);
      font-weight: 700;
      letter-spacing: 0.1em;
      text-transform: uppercase;
    }
    .subtitle {
      color: var(--text-secondary);
      font-size: 16px;
      margin: 0;
      line-height: 1.5;
    }
    .muted { color: var(--text-muted); font-size: 14px; }
    small { color: var(--text-muted); font-size: 12px; }

    /* Cards & Panels */
    .card {
      background: var(--bg-card);
      border-bottom: 1px solid var(--border-light);
      padding: 0 0 32px;
      margin-bottom: 32px;
    }
    .panel {
      background: var(--bg-elevated);
      border: 1px solid var(--border-light);
      padding: 24px;
      transition: all 0.15s ease;
    }
    .panel:hover {
      border-color: var(--border-medium);
    }

    /* Result Display - Floating Card */
    .result-hero {
      background: var(--bg-primary);
      padding: 40px 28px;
      text-align: center;
      min-height: 180px;
      display: flex;
      flex-direction: column;
      align-items: center;
      justify-content: center;
      position: relative;
    }
    @keyframes fadeInUp {
      from {
        opacity: 0;
        transform: translateY(10px);
      }
      to {
        opacity: 1;
        transform: translateY(0);
      }
    }
    .result-value {
      font-size: clamp(48px, 10vw, 80px);
      font-weight: 400;
      letter-spacing: -0.03em;
      font-family: "DM Serif Display", Georgia, serif;
      color: var(--text-primary);
      margin: 0;
      line-height: 1.1;
      word-break: break-word;
      max-width: 100%;
    }
    .result-meta {
      font-size: 13px;
      color: var(--text-secondary);
      margin-top: 16px;
      letter-spacing: 0.05em;
      text-transform: uppercase;
    }
    .result-placeholder {
      color: var(--text-muted);
      font-size: 16px;
      font-style: italic;
    }

    /* Form Elements */
    label {
      display: block;
      font-size: 11px;
      margin: 0 0 8px;
      color: var(--text-secondary);
      font-weight: 700;
      text-transform: uppercase;
      letter-spacing: 0.1em;
    }
    input, textarea {
      width: 100%;
      padding: 12px 14px;
      border: 2px solid var(--border-light);
      background: var(--bg-primary);
      color: var(--text-primary);
      font-size: 15px;
      transition: all 0.15s ease;
      font-family: inherit;
    }
    input:hover, textarea:hover {
      border-color: var(--border-medium);
    }
    input:focus, textarea:focus {
      outline: none;
      border-color: var(--border-strong);
      background: var(--bg-primary);
    }
    input[readonly] {
      cursor: default;
      color: var(--text-secondary);
      background: var(--bg-secondary);
    }
    input[readonly]:hover {
      border-color: var(--border-light);
    }
    textarea {
      min-height: 120px;
      resize: vertical;
      line-height: 1.5;
    }
    input[type="checkbox"] {
      width: auto;
      accent-color: var(--accent-primary);
      cursor: pointer;
    }
    input[type="number"] {
      -moz-appearance: textfield;
    }
    input[type="number"]::-webkit-inner-spin-button,
    input[type="number"]::-webkit-outer-spin-button {
      -webkit-appearance: none;
      margin: 0;
    }

    /* Buttons */
    button {
      cursor: pointer;
      background: var(--accent-primary);
      color: var(--bg-primary);
      border: 2px solid var(--border-strong);
      padding: 14px 28px;
      font-weight: 600;
      font-size: 14px;
      transition: all 0.15s ease;
      font-family: inherit;
      text-transform: uppercase;
      letter-spacing: 0.05em;
    }
    button:hover {
      background: var(--bg-primary);
      color: var(--text-primary);
    }
    button:active {
      transform: scale(0.98);
    }
    button:disabled {
      opacity: 0.3;
      cursor: not-allowed;
    }
    button.secondary {
      background: var(--bg-primary);
      color: var(--text-primary);
      border: 2px solid var(--border-medium);
    }
    button.secondary:hover {
      border-color: var(--border-strong);
    }

    /* Layout */
    .row { display: flex; gap: 12px; flex-wrap: wrap; align-items: stretch; }
    .grow { flex: 1 1 0; min-width: 180px; }
    .grid { display: grid; gap: 20px; grid-template-columns: repeat(auto-fit, minmax(280px, 1fr)); }
    .two-col { display: grid; grid-template-columns: 1fr 1fr; gap: 16px; }
    .stack { display: flex; flex-direction: column; gap: 16px; }
    .room-layout {
      display: grid;
      grid-template-columns: 1fr;
      gap: 24px;
      position: relative;
    }

    /* Floating Result Display */
    .floating-result {
      position: fixed;
      right: 20px;
      top: 20px;
      width: 320px;
      max-height: calc(100vh - 60px);
      z-index: 100;
      background: var(--bg-primary);
      border: 3px solid var(--border-strong);
      box-shadow: var(--shadow-lg);
    }

    /* Activity Log - Hidden at bottom */
    .log-section {
      margin-top: 48px;
      padding-top: 32px;
      border-top: 1px solid var(--border-light);
    }
    .log-header {
      margin-bottom: 16px;
    }
    .log-header h3 {
      margin: 0 0 4px;
    }
    .log-header small {
      color: var(--text-muted);
    }
    #log {
      font-family: "SFMono-Regular", Consolas, "Liberation Mono", Menlo, monospace;
      background: var(--bg-secondary);
      border: 1px solid var(--border-light);
      padding: 16px;
      max-height: 300px;
      overflow-y: auto;
      color: var(--text-primary);
      font-size: 11px;
      line-height: 1.8;
    }
    #log::-webkit-scrollbar { width: 4px; }
    #log::-webkit-scrollbar-track { background: var(--bg-primary); }
    #log::-webkit-scrollbar-thumb { background: var(--border-medium); }
    #log::-webkit-scrollbar-thumb:hover { background: var(--border-strong); }
    #log > div {
      padding: 4px 0;
      border-bottom: 1px solid var(--border-light);
    }
    #log > div:last-child { border-bottom: none; }

    /* People - Discrete Inline Presence */
    .presence-bar {
      position: fixed;
      bottom: 0;
      left: 0;
      right: 0;
      background: var(--bg-primary);
      border-top: 1px solid var(--border-light);
      padding: 10px 20px;
      display: flex;
      align-items: center;
      gap: 16px;
      z-index: 99;
      font-size: 12px;
      color: var(--text-secondary);
      box-shadow: 0 -2px 8px rgba(0,0,0,0.04);
    }
    .presence-label {
      font-size: 11px;
      text-transform: uppercase;
      letter-spacing: 0.05em;
      font-weight: 700;
      color: var(--text-muted);
    }
    .presence-list {
      display: flex;
      align-items: center;
      gap: 12px;
      flex-wrap: wrap;
    }
    .presence-user {
      display: inline-flex;
      align-items: center;
      gap: 6px;
      font-size: 13px;
      color: var(--text-primary);
      font-weight: 500;
    }
    .presence-dot {
      width: 6px;
      height: 6px;
      background: #22c55e;
      border-radius: 50%;
      display: inline-block;
      animation: pulse-dot 2s ease-in-out infinite;
    }
    @keyframes pulse-dot {
      0%, 100% { opacity: 1; }
      50% { opacity: 0.6; }
    }

    /* Badges */
    .badge {
      display: inline-flex;
      align-items: center;
      gap: 6px;
      padding: 6px 12px;
      background: var(--bg-primary);
      border: 1px solid var(--border-strong);
      color: var(--text-primary);
      font-weight: 600;
      font-size: 11px;
      white-space: nowrap;
      text-transform: uppercase;
      letter-spacing: 0.05em;
    }

    /* Interactive Elements */
    .label-row {
      display: flex;
      justify-content: space-between;
      align-items: baseline;
      gap: 12px;
      margin-bottom: 16px;
    }
    .inline { display: inline-flex; align-items: center; gap: 10px; }
    .button-bar { display: flex; gap: 12px; flex-wrap: wrap; align-items: center; }
    .field { display: flex; flex-direction: column; gap: 8px; }
    .field-inline {
      display: flex;
      gap: 8px;
      align-items: stretch;
    }

    /* Steps */
    .step {
      display: flex;
      gap: 16px;
      align-items: flex-start;
      margin-bottom: 16px;
    }
    .step span {
      display: inline-flex;
      align-items: center;
      justify-content: center;
      width: 28px;
      height: 28px;
      min-width: 28px;
      background: var(--bg-primary);
      border: 2px solid var(--border-strong);
      color: var(--text-primary);
      font-weight: 700;
      font-size: 13px;
    }

    /* Status Indicator */
    .status-indicator {
      display: inline-flex;
      align-items: center;
      gap: 6px;
      padding: 4px 10px;
      background: var(--bg-primary);
      border: 1px solid var(--border-light);
      font-size: 11px;
      color: var(--text-secondary);
      text-transform: uppercase;
      letter-spacing: 0.05em;
      font-weight: 600;
    }

    /* Responsive */
    @media (max-width: 768px) {
      main { padding: 20px 16px 60px; }
      .header-card { padding: 24px 0 20px; }
      .card { padding: 0 0 24px; }
      .panel { padding: 20px; }
      .result-value { font-size: clamp(40px, 12vw, 64px); }
      h1 { font-size: clamp(28px, 8vw, 42px); }
      h2 { font-size: 24px; }
      .row, .two-col { flex-direction: column; grid-template-columns: 1fr; }
      .grid { grid-template-columns: 1fr; }
      .button-bar { flex-direction: column; }
      .button-bar button { width: 100%; }
      .header-content { flex-direction: column; align-items: flex-start; }

      /* Mobile: result floats at bottom above presence bar */
      .floating-result {
        position: fixed;
        right: 0;
        left: 0;
        top: auto;
        bottom: 44px;
        width: 100%;
        max-height: 40vh;
        border-left: none;
        border-right: none;
        border-bottom: none;
      }
      .result-hero {
        padding: 24px 20px;
        min-height: 140px;
      }
      .presence-bar {
        padding: 8px 16px;
        gap: 12px;
      }
      .presence-label {
        font-size: 10px;
      }
      .presence-user {
        font-size: 12px;
      }
    }

    @media (min-width: 769px) {
      main {
        margin-right: 360px;
      }
    }
  </style>
</head>
<body>
  <main>
    <div class="header-card">
      <div class="header-content">
        <div>
          <h1>Quick Draw</h1>
          <p class="subtitle">Create a room. Flip coins, draw numbers or items together in real time.</p>
        </div>
        <div class="badge">Live sync</div>
      </div>
    </div>

    <div class="card" id="landing" style="display:${roomId ? "none" : "block"}">
      <h2>Get Started</h2>
      <div class="grid">
        <div class="panel">
          <div class="label-row">
            <span>Create a fresh room</span>
            <small>Generates a short link</small>
          </div>
          <button id="createRoom" style="width:100%;">Create Room</button>
        </div>
        <div class="panel">
          <div class="label-row">
            <span>Join a room</span>
            <small>Paste link or code</small>
          </div>
          <div class="field-inline">
            <input id="joinId" placeholder="Room link or code" style="flex: 1;" />
            <button id="joinRoom" class="secondary">Join</button>
          </div>
        </div>
      </div>
      <div style="margin-top:32px;">
        <div class="step"><span>1</span><div>Create or join a room</div></div>
        <div class="step"><span>2</span><div>Share the link with others</div></div>
        <div class="step"><span>3</span><div>Draw together in real-time</div></div>
      </div>
    </div>

    <div class="card" id="room" style="display:${roomId ? "block" : "none"}">
      <!-- Main Content Area -->
      <div class="room-layout">
        <div class="stack">
          <!-- Settings Panel -->
          <div class="panel">
            <h3>Settings</h3>
            <div class="field">
              <label>Your name</label>
              <input id="nameInput" placeholder="Guest" />
            </div>
            <div class="field">
              <label>Share room</label>
              <button id="copyLink" class="secondary" style="width:100%;">Copy Room Link</button>
              <input id="shareLink" readonly style="display:none;" />
            </div>
          </div>

          <!-- Quick Actions -->
          <div class="panel">
            <h3>Draw</h3>
            <div class="stack">
              <div>
                <label>Coin flip</label>
                <button id="coinBtn" style="width:100%;">Flip Coin</button>
              </div>
              <div>
                <label>Number (Min - Max)</label>
                <div class="row">
                  <input id="minInput" type="number" value="1" placeholder="Min" style="flex:1;" />
                  <input id="maxInput" type="number" value="100" placeholder="Max" style="flex:1;" />
                </div>
                <button id="numberBtn" style="width:100%; margin-top:8px;">Draw Number</button>
              </div>
            </div>
          </div>

          <!-- List Draw Panel -->
          <div class="panel">
            <div class="label-row">
              <h3 style="margin:0;">List Draw</h3>
              <span class="status-indicator" id="listStatus">No list yet</span>
            </div>
            <label>Paste one item per line</label>
            <textarea id="listInput" placeholder="Apple&#10;Banana&#10;Cherry&#10;Date&#10;Elderberry"></textarea>
            <div class="button-bar">
              <label class="inline" style="margin:0;">
                <input type="checkbox" id="withRepl" checked />
                <span>With replacement</span>
              </label>
              <button id="saveListBtn" class="secondary">Save List</button>
              <button id="listDrawBtn">Draw Item</button>
            </div>
          </div>

          <!-- Activity Log Section - At Bottom -->
          <div class="log-section">
            <div class="log-header">
              <h3>Activity Log</h3>
              <small>Recent draws and events</small>
            </div>
            <div id="log"></div>
          </div>
        </div>
      </div>

      <!-- Floating Result Display (Desktop) / Bottom Panel (Mobile) -->
      <div class="floating-result">
        <div class="result-hero" id="resultDisplay">
          <div class="result-placeholder">Draw something to see results here</div>
        </div>
      </div>

      <!-- Presence Bar at Bottom -->
      <div class="presence-bar">
        <span class="presence-label">Online</span>
        <div class="presence-list" id="users"></div>
      </div>
    </div>

  </main>

  <script>
    const state = {
      roomId: "${roomId}",
      ws: null,
      listReady: false,
      listCounts: { items: 0, drawn: 0, withReplacement: true },
    };

    const el = (id) => document.getElementById(id);
    const log = (text) => {
      const box = el("log");
      const line = document.createElement("div");
      line.textContent = text;
      box.prepend(line);
    };

    const updateResultDisplay = (result, mode, by, ts) => {
      const display = el("resultDisplay");
      if (!display) return;

      const verb = mode === "coin" ? "flipped" : mode === "list" ? "drew from list" : "drew";
      const time = ts ? new Date(ts).toLocaleTimeString() : new Date().toLocaleTimeString();

      display.innerHTML = \`
        <div class="result-value" style="animation: fadeInUp 0.4s ease-out;">\${result}</div>
        <div class="result-meta" style="animation: fadeInUp 0.4s ease-out 0.1s both;">\${by || "Someone"} \${verb} · \${time}</div>
      \`;
    };

    const renderUsers = (users = []) => {
      const box = el("users");
      box.innerHTML = "";
      users.forEach((u) => {
        const user = document.createElement("span");
        user.className = "presence-user";
        user.innerHTML = \`<span class="presence-dot"></span>\${u}\`;
        box.appendChild(user);
      });
    };

    const connect = () => {
      if (!state.roomId) return;
      const proto = location.protocol === "https:" ? "wss" : "ws";
      const ws = new WebSocket(\`\${proto}://\${location.host}/ws/room/\${state.roomId}\`);
      state.ws = ws;

      ws.addEventListener("open", () => {
        ws.send(JSON.stringify({ type: "join", name: el("nameInput").value || "Guest" }));
        log("Connected to room.");
      });

      ws.addEventListener("message", (event) => {
        let msg;
        try { msg = JSON.parse(event.data); } catch { return; }
        if (msg.type === "users") {
          renderUsers(msg.users);
        }
        if (msg.type === "list_state") {
          state.listReady = msg.items?.length > 0;
          state.listCounts = {
            items: msg.items?.length || 0,
            drawn: msg.drawn?.length || 0,
            withReplacement: msg.withReplacement !== false,
          };
          el("withRepl").checked = state.listCounts.withReplacement;
          updateListStatus();
        }
        if (msg.type === "result") {
          const ts = new Date(msg.ts || Date.now()).toLocaleTimeString();
          const verb = msg.mode === "coin" ? "flipped" : msg.mode === "list" ? "drew from list" : "drew";
          log(\`[\${ts}] \${msg.by || "Someone"} \${verb}: \${msg.result}\`);
          updateResultDisplay(msg.result, msg.mode, msg.by, msg.ts);
        }
        if (msg.type === "error") {
          log("Error: " + msg.message);
        }
      });

      ws.addEventListener("close", () => log("Disconnected from room."));
    };

    const parseListInput = () => {
      const text = el("listInput").value || "";
      return text
        .split(/\\r?\\n/)
        .map((s) => s.trim())
        .filter((s) => s)
        .slice(0, 200);
    };

    const updateListStatus = () => {
      const { items, drawn, withReplacement } = state.listCounts;
      const status = state.listReady
        ? withReplacement
          ? \`\${items} items · with replacement\`
          : \`\${items - drawn} / \${items} remaining\`
        : "No list yet";
      const elStatus = el("listStatus");
      if (elStatus) elStatus.textContent = status;
    };

    const gotoRoom = (id) => {
      window.location.href = "/room/" + id;
    };

    const parseJoinValue = (value) => {
      const trimmed = value.trim();
      if (!trimmed) return "";
      const maybeUrl = (() => { try { return new URL(trimmed); } catch { return null; }})();
      if (maybeUrl && maybeUrl.pathname.includes("/room/")) {
        const parts = maybeUrl.pathname.split("/");
        return parts.pop() || parts.pop() || "";
      }
      return trimmed.replace(/[^a-zA-Z0-9-]/g, "");
    };

    // Wire UI
    if (el("createRoom")) {
      el("createRoom").onclick = async () => {
        const res = await fetch("/create-room", { method: "POST" });
        const data = await res.json();
        gotoRoom(data.roomId);
      };
    }
    if (el("joinRoom")) {
      el("joinRoom").onclick = () => {
        const id = parseJoinValue(el("joinId").value);
        if (id) gotoRoom(id);
      };
    }
    if (el("copyLink")) {
      el("copyLink").onclick = async () => {
        const link = el("shareLink").value;
        try {
          await navigator.clipboard.writeText(link);
          el("copyLink").textContent = "Copied!";
          setTimeout(() => {
            el("copyLink").textContent = "Copy Room Link";
          }, 2000);
        } catch {
          log("Copy failed. Please try again.");
        }
      };
    }
    if (el("coinBtn")) {
      el("coinBtn").onclick = () => {
        state.ws?.send(JSON.stringify({ type: "draw", mode: "coin" }));
      };
    }
    if (el("numberBtn")) {
      el("numberBtn").onclick = () => {
        const min = Number(el("minInput").value || 1);
        const max = Number(el("maxInput").value || 100);
        state.ws?.send(JSON.stringify({ type: "draw", mode: "number", min, max }));
      };
    }
    if (el("saveListBtn")) {
      el("saveListBtn").onclick = () => {
        const items = parseListInput();
        const withReplacement = el("withRepl").checked;
        state.ws?.send(JSON.stringify({ type: "set_list", items, withReplacement }));
        if (!items.length) {
          log("Add at least one item.");
        } else {
          log(\`List saved: \${items.length} items\`);
        }
      };
    }
    if (el("listDrawBtn")) {
      el("listDrawBtn").onclick = () => {
        state.ws?.send(JSON.stringify({ type: "draw", mode: "list" }));
      };
    }
    if (el("nameInput")) {
      el("nameInput").addEventListener("change", () => {
        state.ws?.send(JSON.stringify({ type: "join", name: el("nameInput").value }));
      });
    }

    if (state.roomId) {
      document.title = "Room " + state.roomId;
      const share = \`\${location.protocol}//\${location.host}/room/\${state.roomId}\`;
      const shareInput = el("shareLink");
      if (shareInput) shareInput.value = share;
      const joinInput = el("joinId");
      if (joinInput) joinInput.value = state.roomId;
      connect();
    }
    updateListStatus();
  </script>
</body>
</html>`;
