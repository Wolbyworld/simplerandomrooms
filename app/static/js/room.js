(() => {
    "use strict";

    const $ = (selector, root = document) => root.querySelector(selector);
    const t = (key, values) => window.DrawI18n.t(key, values);
    const codeFromPage = document.body.dataset.roomCode || location.pathname.split("/").filter(Boolean).pop() || "";
    let roomCode = codeFromPage.toUpperCase();
    const clientKey = `draw:client:${roomCode}`;
    let clientId = sessionStorage.getItem(clientKey);
    if (!clientId) {
        clientId = globalThis.crypto?.randomUUID?.() || `${Date.now()}-${Math.random().toString(36).slice(2)}`;
        sessionStorage.setItem(clientKey, clientId);
    }

    function captureHostToken() {
        const fragment = new URLSearchParams(location.hash.slice(1));
        const fromFragment = fragment.get("host");
        const key = `draw:host:${roomCode}`;
        if (fromFragment) {
            try { sessionStorage.setItem(key, fromFragment); } catch (_) { /* fragment remains the fallback only until scrubbed */ }
            history.replaceState(null, "", `${location.pathname}${location.search}`);
            return fromFragment;
        }
        try { return sessionStorage.getItem(key) || ""; } catch (_) { return ""; }
    }

    const hostToken = captureHostToken();
    let userName = localStorage.getItem("draw:name") || "";
    let state = null;
    let socket = null;
    let heartbeat = null;
    let reconnectTimer = null;
    let reconnectAttempt = 0;
    let started = false;
    let pendingAction = false;
    let lastDrawSignature = "";
    let toastTimer = null;

    const elements = {
        code: $("#room-code-value"), connection: $("#connection-banner"), connectionText: $("#connection-text"), count: $("#participant-count"),
        mode: $("#mode-label"), remaining: $("#remaining-count"), slip: $("#result-slip"), result: $("#result-value"), context: $("#result-context"),
        index: $("#slip-index"), time: $("#result-time"), announcement: $("#result-announcement"), recent: $("#recent-results"),
        completion: $("#completion-card"), draw: $("#draw-button"), drawLabel: $("#draw-button-label"), drawHelp: $("#draw-help"), history: $("#history-list"),
        participants: $("#participants-list"), settingsFields: $("#settings-mode-fields"), toast: $("#toast")
    };

    function safeElement(tag, className, text) {
        const element = document.createElement(tag);
        if (className) element.className = className;
        if (text !== undefined && text !== null) element.textContent = String(text);
        return element;
    }

    function requestHeaders() {
        const headers = { "Accept": "application/json", "Content-Type": "application/json" };
        if (hostToken) headers.Authorization = `Bearer ${hostToken}`;
        return headers;
    }

    function errorMessage(data, fallback = t("common.error")) {
        const detail = data?.detail ?? data?.error?.message ?? data?.message ?? data?.error;
        if (typeof detail === "string") return detail;
        if (Array.isArray(detail)) return detail.map((item) => item.msg).filter(Boolean).join(" · ") || fallback;
        return fallback;
    }

    async function request(url, options = {}) {
        const response = await fetch(url, { ...options, headers: { ...requestHeaders(), ...(options.headers || {}) } });
        const data = await response.json().catch(() => ({}));
        if (!response.ok) {
            const error = new Error(errorMessage(data));
            error.status = response.status;
            throw error;
        }
        return data;
    }

    function normalizeState(payload) {
        if (!payload || typeof payload !== "object") return null;
        return payload.state || payload.room_state || payload.data?.state || (payload.room ? payload : payload.data) || payload;
    }

    function normalizeMode(mode) {
        const value = String(mode || "numbers").toLowerCase();
        return ({ number: "numbers", names: "list", "names/list": "list" })[value] || value;
    }

    function participantName(participant) {
        return String(participant?.name ?? participant?.username ?? participant?.user_name ?? "Guest");
    }

    function localizedPrimitive(value) {
        if (window.DrawI18n.language === "es" && value === "Heads") return "Cara";
        if (window.DrawI18n.language === "es" && value === "Tails") return "Cruz";
        return String(value);
    }

    function formatOne(value) {
        if (value === null || value === undefined) return "—";
        if (typeof value !== "object") return localizedPrimitive(value);
        if (Array.isArray(value)) return value.map(formatOne).join(" · ");
        if (Array.isArray(value.rolls)) {
            const rolls = value.rolls.map(String).join(" + ");
            return value.rolls.length > 1 ? `${rolls} = ${value.total ?? value.rolls.reduce((a, b) => a + b, 0)}` : rolls;
        }
        if ("value" in value) return formatOne(value.value);
        if (Array.isArray(value.results)) return value.results.map(formatOne).join(" · ");
        return JSON.stringify(value);
    }

    function formatResult(result, eventOrConfig = null) {
        const config = eventOrConfig?.details || eventOrConfig || state?.room?.config || {};
        if (Array.isArray(result) && config.presentation === "order") {
            return result.map((value, index) => t("room.orderPosition", { number: index + 1, value: formatOne(value) })).join("\n");
        }
        if (Array.isArray(result) && config.presentation === "teams") {
            const teamCount = Math.max(2, Number(config.team_count) || 2);
            const teams = Array.from({ length: teamCount }, () => []);
            result.forEach((value, index) => teams[index % teamCount].push(formatOne(value)));
            return teams.map((team, index) => `${t("room.team", { number: index + 1 })}: ${team.join(", ")}`).join("\n");
        }
        if (Array.isArray(result)) return result.map(formatOne).join(" · ");
        return formatOne(result);
    }

    function drawEvents(history = []) {
        return history.filter((entry) => (entry.kind || entry.type || "draw") === "draw");
    }

    function latestDraw(current) {
        const draws = drawEvents(current.history || current.draw_history || current.receipts || []);
        const valid = draws.filter((entry) => !entry.invalidated);
        return valid.length ? valid[valid.length - 1] : null;
    }

    function eventSignature(event) {
        if (!event) return "";
        return String(event.event_index ?? event.id ?? `${event.draw_index}:${event.timestamp}:${formatResult(event.result, event)}`);
    }

    function formatTime(timestamp, full = false) {
        if (!timestamp) return "—";
        const date = new Date(timestamp);
        if (Number.isNaN(date.valueOf())) return String(timestamp);
        const options = full ? { dateStyle: "medium", timeStyle: "short" } : { hour: "2-digit", minute: "2-digit" };
        return new Intl.DateTimeFormat(window.DrawI18n.language, options).format(date);
    }

    function modeLabel(mode) { return t(`modes.${normalizeMode(mode)}`); }

    function toast(message) {
        clearTimeout(toastTimer);
        elements.toast.textContent = message;
        elements.toast.hidden = false;
        toastTimer = setTimeout(() => { elements.toast.hidden = true; }, 3200);
    }

    async function copyText(text) {
        if (navigator.clipboard && window.isSecureContext) return navigator.clipboard.writeText(text);
        const textarea = safeElement("textarea");
        textarea.value = text;
        textarea.style.position = "fixed";
        textarea.style.opacity = "0";
        document.body.append(textarea);
        textarea.select();
        document.execCommand("copy");
        textarea.remove();
    }

    function softFeedback() {
        if ($("#haptics-setting").checked && navigator.vibrate) navigator.vibrate(24);
        if (!$("#sound-setting").checked) return;
        try {
            const AudioContext = window.AudioContext || window.webkitAudioContext;
            if (!AudioContext) return;
            const context = new AudioContext();
            const oscillator = context.createOscillator();
            const gain = context.createGain();
            oscillator.type = "sine";
            oscillator.frequency.setValueAtTime(125, context.currentTime);
            gain.gain.setValueAtTime(.0001, context.currentTime);
            gain.gain.exponentialRampToValueAtTime(.05, context.currentTime + .012);
            gain.gain.exponentialRampToValueAtTime(.0001, context.currentTime + .11);
            oscillator.connect(gain).connect(context.destination);
            oscillator.start();
            oscillator.stop(context.currentTime + .12);
            oscillator.addEventListener("ended", () => context.close());
        } catch (_) { /* feedback is optional */ }
    }

    function reveal(event, animate) {
        if (!event) {
            elements.result.textContent = "?";
            elements.context.textContent = t("room.ready");
            elements.index.textContent = "№ —";
            elements.time.textContent = "—";
            return;
        }
        // Events retain the presentation that was in effect at draw time.  Do
        // not reinterpret an older team/order draw through newer room rules.
        const result = formatResult(event.result, event);
        const render = () => {
            elements.result.textContent = result;
            elements.result.classList.toggle("is-long", result.length > 12);
            elements.result.classList.toggle("is-multiple", Array.isArray(event.result) && event.result.length > 1);
            elements.context.textContent = `${modeLabel(event.mode || state?.room?.mode)} · ${t("room.by")} ${event.actor || event.user_name || "—"}`;
            elements.index.textContent = `№ ${event.draw_index ?? event.event_index ?? "—"}`;
            elements.time.textContent = formatTime(event.timestamp);
            // State refreshes are also sent for reconnects, presence, and
            // settings. Announce only a new completed draw, never history.
            if (animate) elements.announcement.textContent = t("room.drawAnnounce", { result });
        };
        elements.slip.classList.remove("is-revealing");
        if (animate && !matchMedia("(prefers-reduced-motion: reduce)").matches) {
            elements.result.textContent = "…";
            void elements.slip.offsetWidth;
            elements.slip.classList.add("is-revealing");
            setTimeout(() => { render(); softFeedback(); }, 430);
        } else {
            render();
            if (animate) softFeedback();
        }
    }

    function auditLabel(kind) {
        const labels = {
            reset: window.DrawI18n.language === "es" ? "Ronda reiniciada" : "Round reset",
            invalidate: window.DrawI18n.language === "es" ? "Resultado invalidado" : "Result invalidated",
            settings: window.DrawI18n.language === "es" ? "Reglas actualizadas" : "Rules updated",
            end: window.DrawI18n.language === "es" ? "Sala terminada" : "Room ended"
        };
        return labels[kind] || String(kind || "Event");
    }

    function receiptDetails(entry) {
        const details = safeElement("details", "history-receipt");
        details.append(safeElement("summary", "", t("room.receipt")));
        const list = safeElement("dl", "receipt-grid");
        const fields = [
            [t("audit.index"), entry.draw_index ?? entry.event_index ?? "—"],
            [t("audit.time"), formatTime(entry.timestamp, true)],
            [t("audit.mode"), modeLabel(entry.mode)],
            [t("audit.actor"), entry.actor || "—"],
            [t("audit.poolCount"), entry.receipt?.pool_count ?? entry.pool_count ?? "—"],
            [t("audit.pool"), entry.receipt?.pool_fingerprint || entry.pool_fingerprint || "—"]
        ];
        fields.forEach(([label, value]) => { list.append(safeElement("dt", "", label), safeElement("dd", "", value)); });
        details.append(list);
        const backendNote = entry.receipt?.note;
        const note = window.DrawI18n.language === "en" && backendNote ? backendNote : t("room.receiptNote");
        details.append(safeElement("p", "receipt-note", note));
        return details;
    }

    function renderHistory(history) {
        elements.history.replaceChildren();
        if (!history.length) {
            const item = safeElement("li", "history-empty");
            item.append(safeElement("strong", "", t("room.noResults")), safeElement("span", "", t("room.noResultsHelp")));
            elements.history.append(item);
            return;
        }
        [...history].reverse().forEach((entry) => {
            const kind = entry.kind || entry.type || "draw";
            const item = safeElement("li", `history-entry${kind === "draw" ? "" : " is-audit"}${entry.invalidated ? " is-invalidated" : ""}`);
            item.append(safeElement("span", "history-index", kind === "draw" ? `#${entry.draw_index ?? entry.event_index ?? "—"}` : "§"));
            const main = safeElement("div", "history-main");
            const result = kind === "draw" ? formatResult(entry.result, entry) : auditLabel(kind);
            main.append(safeElement("strong", "history-result", result));
            const byline = safeElement("div", "history-byline");
            byline.append(safeElement("span", "", `${t("room.by")} ${entry.actor || entry.user_name || "—"}`), safeElement("time", "", formatTime(entry.timestamp)));
            if (entry.invalidated) byline.append(safeElement("span", "host-tag", t("room.invalidated")));
            main.append(byline);
            if (kind === "draw") main.append(receiptDetails(entry));
            item.append(main);
            elements.history.append(item);
        });
    }

    function renderRecent(history) {
        const recent = drawEvents(history).filter((entry) => !entry.invalidated).slice(-5).reverse();
        elements.recent.replaceChildren();
        if (!recent.length) { elements.recent.append(safeElement("span", "recent-empty", t("room.noResultsShort"))); return; }
        recent.forEach((entry) => elements.recent.append(safeElement("span", "recent-chip", formatResult(entry.result, entry))));
    }

    function renderParticipants(participants, hostName) {
        elements.participants.replaceChildren();
        if (!participants.length) {
            const item = safeElement("li", "participant-row");
            item.append(safeElement("span", "participant-name", userName || hostName || "Guest"));
            elements.participants.append(item);
            return;
        }
        participants.forEach((participant) => {
            const item = safeElement("li", "participant-row");
            const isYou = participant.is_self === true;
            const label = `${participantName(participant)}${isYou ? ` · ${t("people.you")}` : ""}`;
            item.append(safeElement("span", "participant-name", label));
            const meta = safeElement("span", "participant-meta");
            if (participant.is_host || participant.role === "host") meta.append(safeElement("span", "host-tag", t("room.host")));
            meta.append(safeElement("span", "participant-status"));
            item.append(meta);
            elements.participants.append(item);
        });
    }

    function makeField(label, input) {
        const field = safeElement("label", "field");
        field.append(safeElement("span", "", label), input);
        return field;
    }

    function numberInput(id, value, min, max) {
        const input = safeElement("input");
        input.id = id; input.type = "number"; input.step = "1"; input.value = String(value ?? "");
        if (min !== undefined) input.min = String(min);
        if (max !== undefined) input.max = String(max);
        return input;
    }

    function replacementField(config) {
        const label = safeElement("label", "check-field");
        const input = safeElement("input"); input.id = "settings-replacement"; input.type = "checkbox"; input.checked = Boolean(config.with_replacement);
        const copy = safeElement("span");
        copy.append(safeElement("strong", "", t("fields.replace")), safeElement("small", "", t("settings.noReplacementHelp")));
        label.append(input, copy);
        return label;
    }

    function populateSettings(room, canManage, force = false) {
        // Keep an open host form intact during ordinary state broadcasts, but
        // rebuild it when the display language changes so its generated labels
        // cannot remain in the prior language.
        if ($("#settings-dialog").open && !force) return;
        const mode = normalizeMode(room.mode);
        const config = room.config || {};
        elements.settingsFields.replaceChildren();
        if (mode === "numbers") {
            const row = safeElement("div", "field-row field-row-three");
            row.append(makeField(t("fields.from"), numberInput("settings-min", config.min, undefined, undefined)), makeField(t("fields.to"), numberInput("settings-max", config.max, undefined, undefined)), makeField(t("fields.howMany"), numberInput("settings-count", config.draw_count || 1, 1, 100)));
            elements.settingsFields.append(row, replacementField(config));
        } else if (mode === "list") {
            const textarea = safeElement("textarea"); textarea.id = "settings-items"; textarea.rows = 7;
            textarea.value = (config.items || []).map((item) => typeof item === "string" ? item : `${item.value}${item.weight > 1 ? ` :: ${item.weight}` : ""}`).join("\n");
            elements.settingsFields.append(makeField(t("fields.entries"), textarea));
            const count = makeField(t("fields.howMany"), numberInput("settings-count", config.draw_count || 1, 1, 100));
            count.style.marginTop = "16px";
            elements.settingsFields.append(count, replacementField(config));
        } else if (mode === "dice") {
            const row = safeElement("div", "field-row");
            row.append(makeField(t("fields.diceCount"), numberInput("settings-dice-count", config.dice_count || 1, 1, 20)), makeField(t("fields.diceSides"), numberInput("settings-dice-sides", config.dice_sides || 6, 2, 1000)));
            elements.settingsFields.append(row);
        }
        elements.settingsFields.querySelectorAll("input, textarea, select").forEach((control) => { control.disabled = !canManage; });
    }

    function renderState(next, options = {}) {
        const canonical = normalizeState(next);
        if (!canonical?.room) return;
        state = canonical;
        const room = canonical.room;
        const history = canonical.history || canonical.draw_history || canonical.receipts || [];
        const participants = canonical.participants || canonical.users || [];
        const permissions = canonical.permissions || {};
        const isHost = Boolean(permissions.is_host ?? canonical.is_host ?? hostToken);
        const canManage = Boolean(permissions.can_manage ?? isHost);
        const canDraw = Boolean(permissions.can_draw ?? (room.draw_policy === "anyone" || isHost));
        roomCode = String(room.code || room.short_code || roomCode).toUpperCase();
        elements.code.textContent = roomCode;
        document.title = `${t("brand")} — ${roomCode}`;
        elements.mode.textContent = modeLabel(room.mode);
        elements.remaining.textContent = room.remaining_count ?? canonical.remaining_count ?? "—";
        elements.count.textContent = String(participants.length || 1);
        // At narrow widths the visible action labels are intentionally hidden;
        // keep the icon controls named for screen readers in the current UI
        // language.
        $("#participants-button").setAttribute("aria-label", `${participants.length || 1} ${t("room.people")}`);
        $("#share-button").setAttribute("aria-label", t("room.share"));
        renderParticipants(participants, room.host_name);
        renderHistory(history);
        renderRecent(history);

        const latest = latestDraw(canonical);
        const signature = eventSignature(latest);
        const newestEvent = history[history.length - 1];
        const shouldReveal = Boolean(options.reveal || (lastDrawSignature && signature && signature !== lastDrawSignature && (newestEvent?.kind || newestEvent?.type) === "draw"));
        reveal(latest, shouldReveal);
        lastDrawSignature = signature;

        const mode = normalizeMode(room.mode);
        elements.drawLabel.textContent = mode === "coin" ? t("room.flip") : mode === "dice" ? t("room.roll") : t("room.draw");
        const ended = room.status && room.status !== "active";
        const remaining = Number(room.remaining_count ?? canonical.remaining_count);
        const exhausted = ["numbers", "list"].includes(mode) && room.config?.with_replacement === false && remaining === 0;
        elements.completion.hidden = !exhausted;
        elements.draw.disabled = pendingAction || ended || exhausted || !canDraw;
        elements.drawHelp.textContent = ended ? t("room.endedHelp") : !canDraw ? t("room.permissionHelp") : t("room.drawHelp");
        $("#completion-reset-button").hidden = !canManage;
        $("#host-controls").hidden = !isHost;
        $("#settings-permission-note").hidden = canManage;
        $("#save-settings-button").hidden = !canManage;
        document.querySelectorAll('input[name="draw_policy"]').forEach((input) => { input.checked = input.value === room.draw_policy; input.disabled = !canManage; });
        populateSettings(room, canManage);
    }

    function setConnection(kind) {
        elements.connection.classList.toggle("is-connected", kind === "connected");
        elements.connection.classList.toggle("is-disconnected", kind === "reconnecting" || kind === "offline");
        elements.connectionText.textContent = t(`connection.${kind}`);
    }

    async function loadState({ reveal = false } = {}) {
        const primary = `/api/rooms/${encodeURIComponent(roomCode)}?client_id=${encodeURIComponent(clientId)}`;
        let data;
        try { data = await request(primary); }
        catch (error) {
            if (error.status !== 404) throw error;
            data = await request(`/api/rooms/${encodeURIComponent(roomCode)}/state?client_id=${encodeURIComponent(clientId)}`);
        }
        renderState(data, { reveal });
    }

    function connectSocket() {
        clearTimeout(reconnectTimer);
        setConnection(reconnectAttempt ? "reconnecting" : "connecting");
        const scheme = location.protocol === "https:" ? "wss" : "ws";
        const params = new URLSearchParams({ client_id: clientId, name: userName || "Guest" });
        socket = new WebSocket(`${scheme}://${location.host}/ws/room/${encodeURIComponent(roomCode)}?${params}`);
        socket.addEventListener("open", () => {
            reconnectAttempt = 0;
            setConnection("connected");
            if (hostToken) socket.send(JSON.stringify({ type: "auth", host_token: hostToken }));
            clearInterval(heartbeat);
            heartbeat = setInterval(() => { if (socket?.readyState === WebSocket.OPEN) socket.send(JSON.stringify({ type: "heartbeat" })); }, 25000);
        });
        socket.addEventListener("message", (event) => {
            let message;
            try { message = JSON.parse(event.data); } catch (_) { return; }
            if (message.type === "error") { toast(errorMessage(message)); return; }
            if (message.type === "heartbeat_ack") return;
            const canonical = normalizeState(message);
            if (canonical?.room) renderState(canonical);
        });
        socket.addEventListener("close", () => {
            clearInterval(heartbeat);
            if (!started) return;
            setConnection(navigator.onLine ? "reconnecting" : "offline");
            reconnectAttempt += 1;
            reconnectTimer = setTimeout(connectSocket, Math.min(1000 * (2 ** reconnectAttempt), 15000));
        });
        socket.addEventListener("error", () => socket.close());
    }

    async function action(endpoint, body = {}, fallbackEndpoint = "") {
        if (pendingAction) return;
        pendingAction = true;
        elements.draw.disabled = true;
        const oldLabel = elements.drawLabel.textContent;
        if (endpoint === "draw") elements.drawLabel.textContent = t("room.drawing");
        try {
            let response;
            try {
                response = await request(`/api/rooms/${encodeURIComponent(roomCode)}/${endpoint}`, { method: "POST", body: JSON.stringify({ actor: userName || "Guest", ...body }) });
            } catch (error) {
                if (!fallbackEndpoint || error.status !== 404) throw error;
                response = await request(`/api/rooms/${encodeURIComponent(roomCode)}/${fallbackEndpoint}`, { method: "POST", body: JSON.stringify({ actor: userName || "Guest", ...body }) });
            }
            renderState(response, { reveal: endpoint === "draw" });
            return response;
        } catch (error) { toast(error instanceof Error ? error.message : t("common.error")); }
        finally {
            pendingAction = false;
            if (elements.drawLabel.textContent === t("room.drawing")) elements.drawLabel.textContent = oldLabel;
            if (state) renderState(state);
        }
    }

    function settingsConfig() {
        const mode = normalizeMode(state.room.mode);
        if (mode === "numbers") return { min: Number($("#settings-min").value), max: Number($("#settings-max").value), draw_count: Number($("#settings-count").value), with_replacement: $("#settings-replacement").checked };
        if (mode === "list") return { list_text: $("#settings-items").value, draw_count: Number($("#settings-count").value), with_replacement: $("#settings-replacement").checked };
        if (mode === "dice") return { dice_count: Number($("#settings-dice-count").value), dice_sides: Number($("#settings-dice-sides").value), draw_count: 1 };
        return { draw_count: 1 };
    }

    async function saveSettings(event) {
        event.preventDefault();
        localStorage.setItem("draw:sound", String($("#sound-setting").checked));
        localStorage.setItem("draw:haptics", String($("#haptics-setting").checked));
        if (!state?.permissions?.can_manage) return;
        const policy = $('input[name="draw_policy"]:checked')?.value || "host_only";
        try {
            const response = await request(`/api/rooms/${encodeURIComponent(roomCode)}`, { method: "PATCH", body: JSON.stringify({ mode: state.room.mode, config: settingsConfig(), draw_policy: policy, actor: userName }) });
            renderState(response);
            $("#settings-dialog").close();
            toast(t("settings.saved"));
        } catch (error) { toast(error instanceof Error ? error.message : t("common.error")); }
    }

    function historyText() {
        const history = state?.history || [];
        const lines = [`${t("brand")} · ${roomCode}`];
        history.forEach((entry) => {
            const event = entry.kind === "draw" ? `#${entry.draw_index} ${formatResult(entry.result, entry)}` : auditLabel(entry.kind);
            lines.push(`${event} — ${entry.actor || "—"}, ${formatTime(entry.timestamp, true)}${entry.invalidated ? ` (${t("room.invalidated")})` : ""}`);
        });
        return lines.join("\n");
    }

    function openDialog(selector) {
        const dialog = $(selector);
        if (dialog && !dialog.open) dialog.showModal();
    }

    $("#draw-button").addEventListener("click", () => action("draw", { count: state?.room?.config?.draw_count || 1 }));
    $("#completion-reset-button").addEventListener("click", () => { if (confirm(t("room.resetConfirm"))) action("reset"); });
    $("#reset-button").addEventListener("click", () => { if (confirm(t("room.resetConfirm"))) action("reset"); });
    $("#invalidate-button").addEventListener("click", () => { if (confirm(t("room.invalidateConfirm"))) action("invalidate", {}, "invalidate-last"); });
    $("#end-button").addEventListener("click", () => { if (confirm(t("room.endConfirm"))) action("end"); });
    $("#settings-form").addEventListener("submit", saveSettings);
    $("#settings-button").addEventListener("click", () => openDialog("#settings-dialog"));
    $("#share-button").addEventListener("click", () => openDialog("#share-dialog"));
    $("#participants-button").addEventListener("click", () => openDialog("#participants-dialog"));
    document.querySelectorAll("[data-close-dialog]").forEach((button) => button.addEventListener("click", () => button.closest("dialog").close()));
    document.querySelectorAll("dialog").forEach((dialog) => dialog.addEventListener("click", (event) => { if (event.target === dialog && dialog.id !== "join-dialog") dialog.close(); }));

    $("#copy-code-button").addEventListener("click", async () => { await copyText(roomCode); toast(t("room.copiedCode")); });
    const shareUrl = `${location.origin}/room/${encodeURIComponent(roomCode)}`;
    $("#share-url").value = shareUrl;
    $("#whatsapp-share").href = `https://wa.me/?text=${encodeURIComponent(`${t("share.text", { code: roomCode })} ${shareUrl}`)}`;
    $("#copy-link-button").addEventListener("click", async () => { await copyText(shareUrl); toast(t("share.copied")); });
    $("#native-share-button").hidden = !navigator.share;
    $("#native-share-button").addEventListener("click", async () => { try { await navigator.share({ title: t("brand"), text: t("share.text", { code: roomCode }), url: shareUrl }); } catch (error) { if (error.name !== "AbortError") toast(t("common.error")); } });
    $("#qr-button").addEventListener("click", () => {
        const panel = $("#qr-panel"); panel.hidden = !panel.hidden;
        if (!panel.hidden) { $("#qr-image").src = `/api/rooms/${encodeURIComponent(roomCode)}/qr.svg`; $("#qr-image").alt = t("share.scan"); }
    });
    $("#copy-history-button").addEventListener("click", async () => { await copyText(historyText()); toast(t("room.copiedHistory")); });
    $("#export-history-button").addEventListener("click", () => {
        const link = safeElement("a"); link.href = `/api/rooms/${encodeURIComponent(roomCode)}/export?format=csv`; link.download = `draw-history-${roomCode}.csv`; document.body.append(link); link.click(); link.remove(); toast(t("room.exported"));
    });

    $("#sound-setting").checked = localStorage.getItem("draw:sound") === "true";
    $("#haptics-setting").checked = localStorage.getItem("draw:haptics") === "true";
    $("#sound-setting").addEventListener("change", (event) => localStorage.setItem("draw:sound", String(event.target.checked)));
    $("#haptics-setting").addEventListener("change", (event) => localStorage.setItem("draw:haptics", String(event.target.checked)));

    document.addEventListener("keydown", (event) => {
        if (!started || event.repeat || ![" ", "Enter"].includes(event.key)) return;
        if (event.target.closest("input, textarea, select, button, a, summary, [contenteditable='true']")) return;
        if (document.querySelector("dialog[open]")) return;
        event.preventDefault();
        if (!elements.draw.disabled) elements.draw.click();
    });
    window.addEventListener("offline", () => setConnection("offline"));
    window.addEventListener("online", () => { if (!socket || socket.readyState > WebSocket.OPEN) connectSocket(); });
    window.addEventListener("draw:languagechange", () => {
        if (!state) return;
        renderState(state);
        const permissions = state.permissions || {};
        const isHost = Boolean(permissions.is_host ?? state.is_host ?? hostToken);
        populateSettings(state.room, Boolean(permissions.can_manage ?? isHost), true);
    });

    async function start() {
        if (started) return;
        started = true;
        try {
            const shouldReveal = sessionStorage.getItem(`draw:reveal:${roomCode}`) === "true";
            sessionStorage.removeItem(`draw:reveal:${roomCode}`);
            await loadState({ reveal: shouldReveal });
            connectSocket();
        } catch (error) {
            setConnection(navigator.onLine ? "reconnecting" : "offline");
            toast(error instanceof Error ? error.message : t("common.error"));
            reconnectTimer = setTimeout(() => { started = false; start(); }, 3000);
        }
    }

    $("#join-form").addEventListener("submit", (event) => {
        event.preventDefault();
        const cleaned = $("#guest-name").value.replace(/\s+/g, " ").trim();
        if (!cleaned) return;
        userName = cleaned.slice(0, 40);
        localStorage.setItem("draw:name", userName);
        $("#join-dialog").close();
        start();
    });

    elements.code.textContent = roomCode;
    if (userName) start();
    else $("#join-dialog").showModal();
})();
