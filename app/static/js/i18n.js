(() => {
    "use strict";

    const messages = {
        en: {
            skip: "Skip to setup",
            brand: "The Draw",
            common: { close: "Close", error: "Something went wrong. Try again." },
            home: {
                eyebrow: "Fair choices, fast.",
                titleLineOne: "Decide it.", titleLineTwo: "Draw it.",
                lede: "Set up a fair draw in seconds, then share the room when everyone should see the result.",
                headerTrust: "Server-drawn & fair", deskLabel: "Start a round", setupTitle: "Pick your draw", modeLegend: "Draw type", presets: "Quick setups",
                coinCopy: "One toss, two equal outcomes. The server makes the call.", drawNow: "Draw now",
                trust: "Server-made result · no account · private until you share",
                creating: "Preparing the draw…", invalidRange: "The end of the range must be greater than or equal to the start.", invalidNumber: "Enter whole numbers within the allowed limits.", rangeTooLarge: "A number range can contain at most 100,000 values.", invalidDice: "Choose 1–20 dice and 2–1,000 sides.", invalidWeight: "Use Name :: a whole number from 1 to 10,000.",
                countTooLarge: "The number of winners cannot exceed the available pool without replacement.",
                listNeeded: "Add at least two different names or options.", nameNeeded: "Enter your name to start the room."
            },
            modes: {
                numbers: "Numbers", numbersHint: "A range, drawn fairly", list: "Names / list", listHint: "People, options, or teams",
                coin: "Coin", coinHint: "A clean fifty–fifty call", dice: "Dice", diceHint: "Roll standard dice"
            },
            presets: { winner: "Pick a winner", teams: "Split teams", order: "Choose an order", yesno: "Yes / no", dice: "Standard dice" },
            fields: {
                from: "From", to: "To", howMany: "How many", replace: "Draw with replacement",
                replaceHelpNumbers: "Off means a number cannot be drawn twice in the same round.",
                replaceHelpList: "Off means a name cannot win twice in the same round.", entries: "Names or options",
                entriesPlaceholder: "Ada\nGrace\nKatherine", weightHelp: "Optional weight: write Maya :: 3 to give Maya three chances.", parseEmpty: "Paste lines, commas, or spreadsheet cells. Duplicates are removed.",
                parsed: "{count} unique entries ready.", parsedDuplicates: "{count} unique entries ready · {duplicates} duplicate(s) removed.", invalidWeight: "Use Name :: a whole number from 1 to 10,000.",
                diceCount: "Number of dice", diceSides: "Sides per die", teamCount: "Number of teams", yourName: "Your name", namePlaceholder: "Referee"
            },
            footer: { note: "A small, fair tool for decisions that matter.", how: "Results are made and recorded by the server." },
            room: {
                skip: "Skip to result", room: "Room", copyCode: "Copy room code", people: "people", participants: "Participants", share: "Share", settings: "Settings",
                currentResult: "Current result", remaining: "remaining", result: "Result", ready: "Ready when you are.", serverDrawn: "Server drawn",
                roundComplete: "Round complete", roundCompleteHelp: "Every eligible item has been drawn.", resetRound: "Reset round",
                recent: "Recent", noResultsShort: "No results yet", draw: "Draw", drawing: "Drawing…", roll: "Roll", flip: "Flip coin",
                drawHelp: "One fair result will be added to the record.", permissionHelp: "The host has limited drawing to their device.", endedHelp: "This room has ended. Its record is read-only.",
                record: "The record", history: "Result history", copy: "Copy", export: "Export", noResults: "No results on the record",
                noResultsHelp: "Make the first draw to begin this round.", receipt: "Receipt details", receiptNote: "This SHA-256 fingerprint records the eligible pool before selection. It is concise audit data, not proof of publicly verifiable randomness.", by: "by", host: "Host", invalidated: "Invalidated",
                copiedCode: "Room code copied.", copiedHistory: "Result history copied.", exported: "Result history exported.", drawAnnounce: "Result: {result}", team: "Team {number}", orderPosition: "{number}. {value}",
                resetConfirm: "Reset this round? Previous results stay on the record.", invalidateConfirm: "Invalidate the latest result and return it to the pool?",
                endConfirm: "End this room? No further draws can be made."
            },
            connection: { connecting: "Connecting…", connected: "Connected", reconnecting: "Connection lost · reconnecting…", offline: "You are offline", refreshed: "Room restored" },
            join: { eyebrow: "Enter the room", title: "What should we call you?", help: "Your name is shown to the room and on draws you make.", action: "Join room" },
            share: {
                eyebrow: "Bring people in", title: "Share this room", help: "Anyone with the link can join. Your host controls stay on this device.",
                copyLink: "Copy link", copied: "Room link copied.", device: "Share…", qr: "QR code", scan: "Scan to join this room", text: "Join my draw in room {code}."
            },
            people: { eyebrow: "At the table", title: "People in this room", you: "You", empty: "No one else is connected." },
            settings: {
                eyebrow: "Rules of the draw", title: "Room settings", whoDraws: "Who can draw?", hostOnly: "Host only",
                hostOnlyHelp: "Only the host can make a result.", anyone: "Anyone in the room", anyoneHelp: "Every participant can use Draw.",
                feedback: "Reveal feedback", language: "Language", sound: "Quiet sound", soundHelp: "A short paper tap when the result arrives.", haptics: "Haptics",
                hapticsHelp: "A brief vibration on supported devices.", hostNote: "Only the host can change room rules.", save: "Save settings",
                saved: "Room settings saved.", hostControls: "Host controls", invalidate: "Invalidate last result",
                invalidateHelp: "Keeps an audit entry and returns the item to the pool.", resetHelp: "Starts a fresh pool. Previous results stay on the record.",
                end: "End room", endHelp: "Stops new draws. The record remains available.", noReplacement: "Without replacement",
                noReplacementHelp: "Each eligible item can appear only once per round."
            },
            audit: { index: "Draw", time: "Time", mode: "Mode", actor: "Actor", pool: "Eligible pool fingerprint", poolCount: "Eligible items", event: "Event" }
        },
        es: {
            skip: "Saltar a la configuración",
            brand: "El Sorteo",
            common: { close: "Cerrar", error: "Algo ha fallado. Inténtalo de nuevo." },
            home: {
                eyebrow: "Decisiones justas, al momento.",
                titleLineOne: "Decídelo.", titleLineTwo: "Sortealo.",
                lede: "Prepara un sorteo justo en segundos y comparte la sala cuando todos deban ver el resultado.",
                headerTrust: "Justo y generado por servidor", deskLabel: "Empezar ronda", setupTitle: "Elige tu sorteo", modeLegend: "Tipo de sorteo", presets: "Preparaciones rápidas",
                coinCopy: "Un lanzamiento, dos resultados iguales. El servidor decide.", drawNow: "Sortear ahora",
                trust: "Resultado del servidor · sin cuenta · privado hasta que lo compartas",
                creating: "Preparando el sorteo…", invalidRange: "El final del rango debe ser mayor o igual que el inicio.", invalidNumber: "Introduce números enteros dentro de los límites permitidos.", rangeTooLarge: "El rango numérico puede contener como máximo 100.000 valores.", invalidDice: "Elige entre 1 y 20 dados y entre 2 y 1.000 caras.", invalidWeight: "Usa Nombre :: un número entero entre 1 y 10.000.",
                countTooLarge: "El número de ganadores no puede superar los elementos disponibles sin reemplazo.",
                listNeeded: "Añade al menos dos nombres u opciones diferentes.", nameNeeded: "Escribe tu nombre para iniciar la sala."
            },
            modes: {
                numbers: "Números", numbersHint: "Un rango, sorteado con justicia", list: "Nombres / lista", listHint: "Personas, opciones o equipos",
                coin: "Moneda", coinHint: "Una decisión al cincuenta por ciento", dice: "Dados", diceHint: "Lanza dados estándar"
            },
            presets: { winner: "Elegir ganador", teams: "Hacer equipos", order: "Elegir orden", yesno: "Sí / no", dice: "Dados estándar" },
            fields: {
                from: "Desde", to: "Hasta", howMany: "Cuántos", replace: "Sortear con reemplazo",
                replaceHelpNumbers: "Desactivado: un número no puede repetirse en la misma ronda.",
                replaceHelpList: "Desactivado: un nombre no puede ganar dos veces en la misma ronda.", entries: "Nombres u opciones",
                entriesPlaceholder: "Ada\nGrace\nKatherine", weightHelp: "Peso opcional: escribe Maya :: 3 para dar tres posibilidades a Maya.", parseEmpty: "Pega líneas, comas o celdas de una hoja. Quitaremos los duplicados.",
                parsed: "{count} entradas únicas listas.", parsedDuplicates: "{count} entradas únicas · {duplicates} duplicado(s) eliminado(s).", invalidWeight: "Usa Nombre :: un número entero entre 1 y 10.000.",
                diceCount: "Número de dados", diceSides: "Caras por dado", teamCount: "Número de equipos", yourName: "Tu nombre", namePlaceholder: "Árbitro"
            },
            footer: { note: "Una herramienta pequeña y justa para decisiones importantes.", how: "El servidor genera y registra los resultados." },
            room: {
                skip: "Saltar al resultado", room: "Sala", copyCode: "Copiar código de sala", people: "personas", participants: "Participantes", share: "Compartir", settings: "Ajustes",
                currentResult: "Resultado actual", remaining: "restantes", result: "Resultado", ready: "Cuando quieras.", serverDrawn: "Sorteo del servidor",
                roundComplete: "Ronda terminada", roundCompleteHelp: "Se han sorteado todos los elementos posibles.", resetRound: "Reiniciar ronda",
                recent: "Recientes", noResultsShort: "Aún no hay resultados", draw: "Sortear", drawing: "Sorteando…", roll: "Lanzar", flip: "Lanzar moneda",
                drawHelp: "Se añadirá un resultado justo al registro.", permissionHelp: "El anfitrión ha limitado los sorteos a su dispositivo.", endedHelp: "Esta sala ha terminado. El registro es de solo lectura.",
                record: "El acta", history: "Historial de resultados", copy: "Copiar", export: "Exportar", noResults: "No hay resultados en el acta",
                noResultsHelp: "Haz el primer sorteo para comenzar la ronda.", receipt: "Detalles del recibo", receiptNote: "Esta huella SHA-256 registra el grupo elegible antes de la selección. Es un dato de auditoría conciso, no una prueba de aleatoriedad verificable públicamente.", by: "por", host: "Anfitrión", invalidated: "Invalidado",
                copiedCode: "Código de sala copiado.", copiedHistory: "Historial copiado.", exported: "Historial exportado.", drawAnnounce: "Resultado: {result}", team: "Equipo {number}", orderPosition: "{number}. {value}",
                resetConfirm: "¿Reiniciar esta ronda? Los resultados anteriores seguirán en el acta.", invalidateConfirm: "¿Invalidar el último resultado y devolverlo al grupo?",
                endConfirm: "¿Terminar esta sala? No se podrán hacer más sorteos."
            },
            connection: { connecting: "Conectando…", connected: "Conectado", reconnecting: "Conexión perdida · reconectando…", offline: "Sin conexión", refreshed: "Sala recuperada" },
            join: { eyebrow: "Entra en la sala", title: "¿Cómo te llamamos?", help: "Tu nombre se muestra en la sala y en los sorteos que hagas.", action: "Entrar en la sala" },
            share: {
                eyebrow: "Invita a los demás", title: "Comparte esta sala", help: "Cualquiera con el enlace puede entrar. Tus controles de anfitrión se quedan en este dispositivo.",
                copyLink: "Copiar enlace", copied: "Enlace copiado.", device: "Compartir…", qr: "Código QR", scan: "Escanea para entrar en la sala", text: "Únete a mi sorteo en la sala {code}."
            },
            people: { eyebrow: "En la mesa", title: "Personas en esta sala", you: "Tú", empty: "No hay nadie más conectado." },
            settings: {
                eyebrow: "Reglas del sorteo", title: "Ajustes de la sala", whoDraws: "¿Quién puede sortear?", hostOnly: "Solo el anfitrión",
                hostOnlyHelp: "Solo el anfitrión puede generar resultados.", anyone: "Cualquiera en la sala", anyoneHelp: "Todos los participantes pueden usar Sortear.",
                feedback: "Respuesta del sorteo", language: "Idioma", sound: "Sonido suave", soundHelp: "Un toque de papel cuando llega el resultado.", haptics: "Vibración",
                hapticsHelp: "Una vibración breve en dispositivos compatibles.", hostNote: "Solo el anfitrión puede cambiar las reglas.", save: "Guardar ajustes",
                saved: "Ajustes guardados.", hostControls: "Controles del anfitrión", invalidate: "Invalidar último resultado",
                invalidateHelp: "Mantiene una entrada de auditoría y devuelve el elemento al grupo.", resetHelp: "Inicia un grupo nuevo. Los resultados previos siguen en el acta.",
                end: "Terminar sala", endHelp: "Impide nuevos sorteos. El acta sigue disponible.", noReplacement: "Sin reemplazo",
                noReplacementHelp: "Cada elemento puede aparecer solo una vez por ronda."
            },
            audit: { index: "Sorteo", time: "Hora", mode: "Modo", actor: "Autor", pool: "Huella del grupo elegible", poolCount: "Elementos elegibles", event: "Evento" }
        }
    };

    const getPath = (object, path) => path.split(".").reduce((value, key) => value && value[key], object);
    const preferred = localStorage.getItem("draw:language") || (navigator.language.toLowerCase().startsWith("es") ? "es" : "en");
    let language = messages[preferred] ? preferred : "en";

    function t(key, values = {}) {
        const template = getPath(messages[language], key) ?? getPath(messages.en, key) ?? key;
        return String(template).replace(/\{(\w+)\}/g, (_, name) => values[name] ?? `{${name}}`);
    }

    function apply(root = document) {
        document.documentElement.lang = language;
        root.querySelectorAll("[data-i18n]").forEach((element) => { element.textContent = t(element.dataset.i18n); });
        root.querySelectorAll("[data-i18n-placeholder]").forEach((element) => { element.placeholder = t(element.dataset.i18nPlaceholder); });
        root.querySelectorAll("[data-i18n-aria]").forEach((element) => { element.setAttribute("aria-label", t(element.dataset.i18nAria)); });
        document.querySelectorAll("[data-language]").forEach((button) => button.setAttribute("aria-pressed", String(button.dataset.language === language)));
    }

    function setLanguage(next) {
        if (!messages[next]) return;
        language = next;
        localStorage.setItem("draw:language", language);
        apply();
        window.dispatchEvent(new CustomEvent("draw:languagechange", { detail: { language } }));
    }

    document.addEventListener("DOMContentLoaded", () => {
        document.querySelectorAll("[data-language]").forEach((button) => button.addEventListener("click", () => setLanguage(button.dataset.language)));
        apply();
    });

    window.DrawI18n = { t, apply, setLanguage, get language() { return language; } };
})();
