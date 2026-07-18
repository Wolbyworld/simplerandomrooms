(() => {
    "use strict";

    const $ = (selector) => document.querySelector(selector);
    const form = $("#create-room-form");
    if (!form) return;

    const modeInputs = [...document.querySelectorAll('input[name="mode"]')];
    const configs = [...document.querySelectorAll("[data-config]")];
    const listInput = $("#list-items");
    const parseFeedback = $("#parse-feedback");
    const errorBox = $("#form-error");
    const submitButton = $("#draw-now-button");
    const t = (key, values) => window.DrawI18n.t(key, values);
    let activeListPreset = null;

    const rememberedName = localStorage.getItem("draw:name");
    if (rememberedName) $("#host-name").value = rememberedName;
    $("#desk-date").textContent = new Intl.DateTimeFormat(undefined, { day: "2-digit", month: "short", year: "numeric" }).format(new Date()).toUpperCase();

    function currentMode() {
        return modeInputs.find((input) => input.checked)?.value || "numbers";
    }

    function setMode(mode) {
        const input = modeInputs.find((candidate) => candidate.value === mode);
        if (input) input.checked = true;
        configs.forEach((panel) => { panel.hidden = panel.dataset.config !== mode; });
    }

    function setListPresentation(presentation) {
        activeListPreset = presentation;
        $("#team-count-field").hidden = presentation !== "teams";
        $("#list-count-field").hidden = presentation === "teams" || presentation === "order";
    }

    function parseItems(raw) {
        const candidates = raw.split(/[\n\r,\t]+/);
        const items = [];
        const seen = new Set();
        let duplicates = 0;
        let invalidWeight = false;
        for (const candidate of candidates) {
            const cleaned = candidate.replace(/\s+/g, " ").trim();
            if (!cleaned) continue;
            const weighted = cleaned.match(/^(.*?)\s*::\s*(\d+)$/);
            const value = (weighted ? weighted[1] : cleaned).trim();
            const weight = weighted ? Number(weighted[2]) : 1;
            if (!value) continue;
            if (cleaned.includes("::") && (!weighted || weight < 1 || weight > 10000)) invalidWeight = true;
            const key = value.toLocaleLowerCase();
            if (seen.has(key)) { duplicates += 1; continue; }
            seen.add(key);
            items.push({ value, weight });
        }
        return { items, duplicates, invalidWeight };
    }

    function updateParsingFeedback() {
        const parsed = parseItems(listInput.value);
        parseFeedback.classList.toggle("has-items", parsed.items.length > 0 && !parsed.duplicates && !parsed.invalidWeight);
        parseFeedback.classList.toggle("has-warning", parsed.duplicates > 0 || parsed.invalidWeight);
        if (parsed.invalidWeight) parseFeedback.textContent = t("fields.invalidWeight");
        else if (!parsed.items.length) parseFeedback.textContent = t("fields.parseEmpty");
        else if (parsed.duplicates) parseFeedback.textContent = t("fields.parsedDuplicates", { count: parsed.items.length, duplicates: parsed.duplicates });
        else parseFeedback.textContent = t("fields.parsed", { count: parsed.items.length });
        return parsed;
    }

    function usePreset(preset) {
        if (preset === "yesno") {
            setMode("list");
            setListPresentation("winner");
            listInput.value = window.DrawI18n.language === "es" ? "Sí\nNo" : "Yes\nNo";
            $("#list-count").value = "1";
        } else if (preset === "dice") {
            setListPresentation(null);
            setMode("dice");
            $("#dice-count").value = "2";
            $("#dice-sides").value = "6";
        } else {
            setMode("list");
            setListPresentation(preset);
            if (preset === "winner") $("#list-count").value = "1";
            listInput.focus();
        }
        updateParsingFeedback();
    }

    function configFor(mode, parsedList = null) {
        if (mode === "numbers") return {
            min: Number($("#min-value").value), max: Number($("#max-value").value),
            draw_count: Number($("#number-count").value), with_replacement: $("#number-replacement").checked
        };
        if (mode === "list") {
            const items = (parsedList || updateParsingFeedback()).items;
            const drawAll = activeListPreset === "order" || activeListPreset === "teams";
            return {
                items, draw_count: drawAll ? items.length : Number($("#list-count").value), with_replacement: $("#list-replacement").checked,
                ...(activeListPreset ? { presentation: activeListPreset } : {}), ...(activeListPreset === "teams" ? { team_count: Number($("#team-count").value) } : {})
            };
        }
        if (mode === "dice") return {
            dice_count: Number($("#dice-count").value), dice_sides: Number($("#dice-sides").value), draw_count: 1
        };
        return { draw_count: 1 };
    }

    function validation(message = "", fields = []) { return { message, fields }; }

    function validate(mode, config, name, parsedList) {
        if (!name) return validation(t("home.nameNeeded"), ["#host-name"]);
        if (mode === "numbers") {
            if (["#min-value", "#max-value", "#number-count"].some((selector) => $(selector).value.trim() === "") || ![config.min, config.max, config.draw_count].every(Number.isInteger) || config.draw_count < 1 || config.draw_count > 100) return validation(t("home.invalidNumber"), ["#min-value", "#max-value", "#number-count"]);
            if (config.max < config.min) return validation(t("home.invalidRange"), ["#min-value", "#max-value"]);
            if (config.max - config.min + 1 > 100000) return validation(t("home.rangeTooLarge"), ["#min-value", "#max-value"]);
            if (!config.with_replacement && config.draw_count > config.max - config.min + 1) return validation(t("home.countTooLarge"), ["#number-count"]);
        }
        if (mode === "list") {
            if (parsedList?.invalidWeight) return validation(t("home.invalidWeight"), ["#list-items"]);
            if (config.items.length < 2) return validation(t("home.listNeeded"), ["#list-items"]);
            if ((!config.presentation || config.presentation === "plain" || config.presentation === "winner") && ($("#list-count").value.trim() === "" || !Number.isInteger(config.draw_count) || config.draw_count < 1 || config.draw_count > 100)) return validation(t("home.invalidNumber"), ["#list-count"]);
            if (config.presentation === "teams" && (!Number.isInteger(config.team_count) || config.team_count < 2 || config.team_count > 20 || config.team_count > config.items.length)) return validation(t("home.countTooLarge"), ["#team-count"]);
            if (!config.with_replacement && config.draw_count > config.items.length) return validation(t("home.countTooLarge"), ["#list-count"]);
        }
        if (mode === "dice" && ($("#dice-count").value.trim() === "" || !Number.isInteger(config.dice_count) || config.dice_count < 1 || config.dice_count > 20 || !Number.isInteger(config.dice_sides) || config.dice_sides < 2 || config.dice_sides > 1000)) return validation(t("home.invalidDice"), ["#dice-count", "#dice-sides"]);
        return validation();
    }

    function showValidation(result) {
        form.querySelectorAll("[aria-invalid='true']").forEach((field) => field.removeAttribute("aria-invalid"));
        errorBox.hidden = !result.message;
        errorBox.textContent = result.message;
        result.fields.forEach((selector) => {
            const field = $(selector);
            if (!field) return;
            field.setAttribute("aria-invalid", "true");
            field.setAttribute("aria-describedby", "form-error");
        });
    }

    async function jsonRequest(url, options) {
        const response = await fetch(url, options);
        const data = await response.json().catch(() => ({}));
        if (!response.ok) {
            const detail = data.detail || data.error?.message || data.message;
            throw new Error(typeof detail === "string" ? detail : t("common.error"));
        }
        return data;
    }

    function storeHostToken(code, token) {
        if (!token) return false;
        try {
            sessionStorage.setItem(`draw:host:${code}`, token);
            return sessionStorage.getItem(`draw:host:${code}`) === token;
        } catch (_) { return false; }
    }

    modeInputs.forEach((input) => input.addEventListener("change", () => { setListPresentation(null); setMode(currentMode()); }));
    listInput.addEventListener("input", updateParsingFeedback);
    document.querySelectorAll("[data-preset]").forEach((button) => button.addEventListener("click", () => usePreset(button.dataset.preset)));
    window.addEventListener("draw:languagechange", updateParsingFeedback);

    form.addEventListener("submit", async (event) => {
        event.preventDefault();
        const mode = currentMode();
        const parsedList = mode === "list" ? updateParsingFeedback() : null;
        const config = configFor(mode, parsedList);
        const hostName = $("#host-name").value.replace(/\s+/g, " ").trim();
        const validationResult = validate(mode, config, hostName, parsedList);
        showValidation(validationResult);
        if (validationResult.message) return;

        submitButton.disabled = true;
        const originalLabel = submitButton.querySelector("span");
        originalLabel.textContent = t("home.creating");
        try {
            localStorage.setItem("draw:name", hostName);
            const state = await jsonRequest("/api/rooms", {
                method: "POST", headers: { "Content-Type": "application/json", "Accept": "application/json" },
                body: JSON.stringify({ mode, config, draw_policy: "host_only", host_name: hostName })
            });
            const code = state.room?.code || state.code || state.room_code || state.id || state.room_id;
            const token = state.host_token || state.token || state.room?.host_token;
            if (!code || !token) throw new Error(t("common.error"));
            const stored = storeHostToken(code, token);

            await jsonRequest(`/api/rooms/${encodeURIComponent(code)}/draw`, {
                method: "POST",
                headers: { "Content-Type": "application/json", "Accept": "application/json", "Authorization": `Bearer ${token}` },
                body: JSON.stringify({ count: config.draw_count || 1, actor: hostName })
            });
            sessionStorage.setItem(`draw:reveal:${code}`, "true");
            const fragment = stored ? "" : `#host=${encodeURIComponent(token)}`;
            window.location.assign(`/room/${encodeURIComponent(code)}${fragment}`);
        } catch (error) {
            errorBox.hidden = false;
            errorBox.textContent = error instanceof Error ? error.message : t("common.error");
            submitButton.disabled = false;
            originalLabel.textContent = t("home.drawNow");
        }
    });

    setMode(currentMode());
    updateParsingFeedback();
})();
