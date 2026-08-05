(() => {
    "use strict";

    const game = document.getElementById("starterrace-game");
    const initialNode = document.getElementById("starterrace-initial-state");
    if (!game || !initialNode) return;

    let state;
    try {
        state = JSON.parse(initialNode.textContent);
    } catch (_) {
        game.textContent = "Le plateau n’a pas pu être chargé. Recharge la page.";
        return;
    }

    const elements = {
        status: document.querySelector("[data-status]"),
        sync: document.querySelector("[data-sync]"),
        syncLabel: document.querySelector("[data-sync] span"),
        feedback: game.querySelector("[data-feedback]"),
        announcer: game.querySelector("[data-announcer]"),
        waiting: game.querySelector('[data-view="waiting"]'),
        race: game.querySelector('[data-view="race"]'),
        result: game.querySelector('[data-view="result"]'),
        inviteUrl: game.querySelector("[data-invite-url]"),
        copyInvite: game.querySelector("[data-copy-invite]"),
        waitingSeats: game.querySelector("[data-waiting-seats]"),
        startButton: game.querySelector("[data-start-button]"),
        startHint: game.querySelector("[data-start-hint]"),
        track: game.querySelector("[data-track]"),
        players: game.querySelector("[data-players]"),
        turnAvatar: game.querySelector("[data-turn-avatar]"),
        turnTitle: game.querySelector("[data-turn-title]"),
        turnHint: game.querySelector("[data-turn-hint]"),
        turnProgress: game.querySelector("[data-turn-progress]"),
        actionTitle: game.querySelector("[data-action-title]"),
        actionHelp: game.querySelector("[data-action-help]"),
        roll: game.querySelector("[data-roll]"),
        dieFace: game.querySelector("[data-die-face]"),
        history: game.querySelector("[data-history]"),
        historyEmpty: game.querySelector("[data-history-empty]"),
        moveCount: game.querySelector("[data-move-count]"),
        resultTitle: game.querySelector("[data-result-title]"),
        resultCopy: game.querySelector("[data-result-copy]"),
        resultArt: game.querySelector("[data-result-art]"),
    };

    const STATUS_LABELS = {
        EN_ATTENTE: "En préparation",
        EN_COURS: "Course en cours",
        TERMINEE: "Terminée",
    };
    const COLOR_VALUES = {
        leaf: "var(--sr-leaf)",
        flame: "var(--sr-flame)",
        wave: "var(--sr-wave)",
        spark: "var(--sr-spark)",
    };
    const COLOR_NAMES = {
        leaf: "verte",
        flame: "rouge",
        wave: "bleue",
        spark: "jaune",
    };
    const reducedMotion = window.matchMedia("(prefers-reduced-motion: reduce)");
    const csrfToken = game.querySelector('[name="csrfmiddlewaretoken"]')?.value || readCookie("csrftoken");
    let busy = false;
    let feedbackTimer = null;
    let pollController = null;
    let lastView = null;

    function readCookie(name) {
        const prefix = `${name}=`;
        return document.cookie
            .split(";")
            .map((part) => part.trim())
            .find((part) => part.startsWith(prefix))
            ?.slice(prefix.length) || "";
    }

    function sameId(left, right) {
        return left !== null && left !== undefined && right !== null && right !== undefined
            && String(left) === String(right);
    }

    function playerById(id) {
        return state.players.find((player) => sameId(player.id, id));
    }

    function playerColor(player) {
        return COLOR_VALUES[player?.color] || "var(--color-brand)";
    }

    function setSync(mode, label) {
        if (!elements.sync) return;
        elements.sync.classList.toggle("is-syncing", mode === "syncing");
        elements.sync.classList.toggle("is-offline", mode === "offline");
        if (elements.syncLabel) elements.syncLabel.textContent = label;
    }

    function setBusy(value) {
        busy = value;
        game.setAttribute("aria-busy", String(value));
        if (value) setSync("syncing", "Envoi…");
        elements.roll.disabled = value || !state.can_roll;
        for (const pawn of game.querySelectorAll("button[data-pawn-id]")) pawn.disabled = value;
    }

    function showFeedback(message) {
        window.clearTimeout(feedbackTimer);
        elements.feedback.textContent = message;
        elements.feedback.hidden = false;
        feedbackTimer = window.setTimeout(() => {
            elements.feedback.hidden = true;
        }, 6000);
    }

    function announce(message) {
        elements.announcer.textContent = "";
        window.requestAnimationFrame(() => {
            elements.announcer.textContent = message;
        });
    }

    function setView(name) {
        elements.waiting.hidden = name !== "waiting";
        elements.race.hidden = name !== "race";
        elements.result.hidden = name !== "result";
        const changed = lastView !== name;
        lastView = name;
        return changed;
    }

    function render() {
        elements.status.textContent = STATUS_LABELS[state.status] || "Course";
        if (state.status === "EN_ATTENTE") {
            setView("waiting");
            renderWaiting();
        } else if (state.status === "TERMINEE") {
            const changed = setView("result");
            renderResult();
            if (changed) elements.resultTitle.focus({ preventScroll: true });
        } else {
            setView("race");
            renderRace();
        }
        setBusy(false);
    }

    function makeImage(player, className = "") {
        const image = document.createElement("img");
        image.src = player.starter.sprite_url;
        image.alt = "";
        image.width = 64;
        image.height = 64;
        image.decoding = "async";
        if (className) image.className = className;
        return image;
    }

    function renderWaiting() {
        elements.inviteUrl.textContent = window.location.href;
        elements.waitingSeats.replaceChildren();
        for (let index = 0; index < state.max_players; index += 1) {
            const player = state.players[index];
            const seat = document.createElement("div");
            seat.className = `sr-seat${player ? "" : " is-empty"}`;
            if (player) {
                seat.style.setProperty("--player-color", playerColor(player));
                seat.appendChild(makeImage(player));
                const copy = document.createElement("span");
                const name = document.createElement("strong");
                name.textContent = player.username;
                const starter = document.createElement("small");
                starter.textContent = `${player.starter.name} · prêt`;
                copy.append(name, starter);
                seat.appendChild(copy);
            } else {
                const icon = document.createElement("span");
                icon.className = "sr-seat-icon";
                icon.setAttribute("aria-hidden", "true");
                icon.textContent = "+";
                const copy = document.createElement("span");
                const name = document.createElement("strong");
                name.textContent = "Place libre";
                const status = document.createElement("small");
                status.textContent = "En attente…";
                copy.append(name, status);
                seat.append(icon, copy);
            }
            elements.waitingSeats.appendChild(seat);
        }

        if (elements.startButton) {
            elements.startButton.disabled = !state.can_start;
            elements.startHint.textContent = state.can_start
                ? `${state.players.length} dresseurs prêts. En avant !`
                : "Il faut encore un dresseur.";
        }
    }

    function gridCoordinates(cell) {
        if (cell <= 10) return [1, cell + 1];
        if (cell <= 20) return [cell - 9, 11];
        if (cell <= 30) return [11, 31 - cell];
        return [41 - cell, 1];
    }

    function pawnLabel(pawn, player) {
        const number = pawn.number + 1;
        if (pawn.zone === "HOME") return `${player.starter.name}, pion ${number}, au camp`;
        if (pawn.zone === "FINISHED") return `${player.starter.name}, pion ${number}, arrivé à la Ligue`;
        if (pawn.zone === "FINAL_LANE") return `${player.starter.name}, pion ${number}, couloir final case ${pawn.final_index + 1}`;
        return `${player.starter.name}, pion ${number}, case ${pawn.global_position + 1}`;
    }

    function makePawn(pawn, player) {
        const selectable = state.can_move && state.legal_pawn_ids.some((id) => sameId(id, pawn.id));
        const node = document.createElement(selectable ? "button" : "span");
        node.className = "sr-pawn";
        node.style.setProperty("--player-color", playerColor(player));
        node.setAttribute("aria-label", `${pawnLabel(pawn, player)}${selectable ? ". Déplacer ce pion." : ""}`);
        if (selectable) {
            node.type = "button";
            node.dataset.pawnId = String(pawn.id);
        } else {
            node.setAttribute("role", "img");
        }
        node.appendChild(makeImage(player));
        return node;
    }

    function renderTrack() {
        const safeCells = new Set(state.board.safe_cells);
        const shortcuts = new Map(state.board.shortcuts.map((shortcut) => [shortcut.from, shortcut.to]));
        const starts = new Map(state.players.map((player) => [player.start_cell, player]));
        const pawnsByCell = new Map();
        for (const player of state.players) {
            for (const pawn of player.pawns) {
                if (pawn.zone !== "TRACK") continue;
                if (!pawnsByCell.has(pawn.global_position)) pawnsByCell.set(pawn.global_position, []);
                pawnsByCell.get(pawn.global_position).push([pawn, player]);
            }
        }

        const cells = [];
        for (let cell = 0; cell < state.board.track_length; cell += 1) {
            const item = document.createElement("li");
            item.className = "sr-cell";
            const [row, column] = gridCoordinates(cell);
            item.style.setProperty("--row", String(row));
            item.style.setProperty("--column", String(column));
            const labels = [`Case ${cell + 1}`];

            if (safeCells.has(cell)) {
                item.classList.add("is-safe");
                labels.push("refuge");
            }
            if (shortcuts.has(cell)) {
                item.classList.add("is-shortcut");
                labels.push(`raccourci vers la case ${shortcuts.get(cell) + 1}`);
            }
            const starter = starts.get(cell);
            if (starter) {
                item.classList.add("is-start");
                item.style.setProperty("--start-color", playerColor(starter));
                labels.push(`départ de ${starter.starter.name}`);
            }
            item.setAttribute("aria-label", labels.join(", "));

            const number = document.createElement("span");
            number.className = "sr-cell-number";
            number.setAttribute("aria-hidden", "true");
            number.textContent = String(cell + 1);
            item.appendChild(number);

            if (safeCells.has(cell) || shortcuts.has(cell) || starter) {
                const symbol = document.createElement("span");
                symbol.className = "sr-cell-symbol";
                symbol.setAttribute("aria-hidden", "true");
                symbol.textContent = shortcuts.has(cell) ? "⇱" : starter ? "●" : "◇";
                item.appendChild(symbol);
            }

            const pawnGroup = document.createElement("span");
            pawnGroup.className = "sr-cell-pawns";
            for (const [pawn, player] of pawnsByCell.get(cell) || []) {
                pawnGroup.appendChild(makePawn(pawn, player));
            }
            item.appendChild(pawnGroup);
            cells.push(item);
        }
        elements.track.replaceChildren(...cells);
    }

    function renderPlayers() {
        const cards = [];
        for (const player of state.players) {
            const card = document.createElement("article");
            card.className = `sr-player-card${sameId(state.current_turn?.id, player.id) ? " is-current" : ""}`;
            card.style.setProperty("--player-color", playerColor(player));
            card.appendChild(makeImage(player));

            const content = document.createElement("div");
            const heading = document.createElement("header");
            const title = document.createElement("h3");
            title.textContent = player.username;
            const score = document.createElement("span");
            score.textContent = `${player.finished_count}/4 arrivés`;
            heading.append(title, score);
            const starter = document.createElement("small");
            starter.textContent = `${player.starter.name} · équipe ${COLOR_NAMES[player.color]}`;

            const lane = document.createElement("div");
            lane.className = "sr-pawn-lane";
            lane.setAttribute("aria-label", `Camp et couloir final de ${player.username}`);
            const slots = [];
            for (let index = 0; index < 8; index += 1) {
                const slot = document.createElement("span");
                slot.className = index < 4 ? "sr-home-slot" : "sr-final-slot";
                slot.setAttribute("aria-hidden", "true");
                slots.push(slot);
                lane.appendChild(slot);
            }
            for (const pawn of player.pawns) {
                if (pawn.zone === "HOME") {
                    slots[pawn.number].removeAttribute("aria-hidden");
                    slots[pawn.number].appendChild(makePawn(pawn, player));
                } else if (pawn.zone === "FINAL_LANE" || pawn.zone === "FINISHED") {
                    const slot = slots[4 + pawn.final_index];
                    slot.removeAttribute("aria-hidden");
                    slot.appendChild(makePawn(pawn, player));
                }
            }
            content.append(heading, starter, lane);
            card.appendChild(content);
            cards.push(card);
        }
        elements.players.replaceChildren(...cards);
    }

    function renderTurn() {
        const current = playerById(state.current_turn?.id);
        if (!current) return;
        elements.turnAvatar.style.setProperty("--player-color", playerColor(current));
        elements.turnAvatar.replaceChildren(makeImage(current));
        elements.turnProgress.textContent = `${current.finished_count}/4 à la Ligue`;

        if (state.is_my_turn && state.pending_roll === null) {
            elements.turnTitle.textContent = "À toi de lancer !";
            elements.turnHint.textContent = "Un 6 fait sortir un Starter et te permet de rejouer.";
        } else if (state.is_my_turn) {
            elements.turnTitle.textContent = `Tu as fait ${state.pending_roll}`;
            elements.turnHint.textContent = "Choisis un pion illuminé sur le plateau ou dans ton camp.";
        } else if (state.pending_roll !== null) {
            elements.turnTitle.textContent = `${current.username} a fait ${state.pending_roll}`;
            elements.turnHint.textContent = `${current.starter.name} choisit son prochain mouvement.`;
        } else {
            elements.turnTitle.textContent = `Au tour de ${current.username}`;
            elements.turnHint.textContent = `${current.starter.name} s’apprête à lancer le dé.`;
        }

        elements.roll.disabled = busy || !state.can_roll;
        elements.dieFace.textContent = state.pending_roll === null ? "?" : String(state.pending_roll);
        if (state.can_roll) {
            elements.actionTitle.textContent = "Lance le dé";
            elements.actionHelp.textContent = "Clique sur le dé pour avancer.";
        } else if (state.can_move) {
            elements.actionTitle.textContent = `Choisis pour avancer de ${state.pending_roll}`;
            elements.actionHelp.textContent = `${state.legal_pawn_ids.length} pion${state.legal_pawn_ids.length > 1 ? "s" : ""} disponible${state.legal_pawn_ids.length > 1 ? "s" : ""}.`;
        } else {
            elements.actionTitle.textContent = `Tour de ${current.username}`;
            elements.actionHelp.textContent = "Le plateau se mettra à jour automatiquement.";
        }
    }

    function moveDescription(move) {
        const name = move.player.username;
        if (move.was_pass) {
            return `${name} a lancé ${move.roll}, mais aucun pion ne pouvait avancer.${move.grants_extra_turn ? " Le 6 lui offre une nouvelle tentative." : ""}`;
        }
        const parts = [];
        if (move.from_position === -1) {
            parts.push(`${name} fait entrer son pion ${move.pawn_number + 1} en piste avec un 6.`);
        } else {
            parts.push(`${name} avance son pion ${move.pawn_number + 1} de ${move.roll} case${move.roll > 1 ? "s" : ""}.`);
        }
        if (move.shortcut_from !== null) parts.push(`Raccourci jusqu’à la case ${move.shortcut_to + 1} !`);
        if (move.captured_pawns.length) {
            const names = move.captured_pawns.map((captured) => captured.username).join(", ");
            parts.push(`${names} ${move.captured_pawns.length > 1 ? "retournent" : "retourne"} au camp.`);
        }
        if (move.to_position === 43) parts.push("Un Starter atteint la Ligue !");
        if (move.grants_extra_turn) parts.push("Le 6 lui permet de rejouer.");
        return parts.join(" ");
    }

    function renderHistory() {
        elements.moveCount.textContent = String(state.moves.length);
        elements.historyEmpty.hidden = state.moves.length > 0;
        const entries = state.moves.map((move) => {
            const item = document.createElement("li");
            item.className = "sr-history-entry";
            const die = document.createElement("span");
            die.className = "sr-history-die";
            die.setAttribute("aria-hidden", "true");
            die.textContent = String(move.roll);
            const text = document.createElement("p");
            text.textContent = moveDescription(move);
            item.append(die, text);
            return item;
        });
        elements.history.replaceChildren(...entries);
        if (entries.length) elements.history.scrollTop = elements.history.scrollHeight;
    }

    function renderRace() {
        renderTurn();
        renderTrack();
        renderPlayers();
        renderHistory();
    }

    function renderResult() {
        const winner = playerById(state.winner?.id);
        if (!winner) return;
        elements.resultArt.replaceChildren(makeImage(winner));
        elements.resultTitle.textContent = `${winner.username} remporte la Ligue !`;
        elements.resultCopy.textContent = `${winner.starter.name} et ses quatre coéquipiers ont franchi l’arrivée avant toutes les autres équipes.`;
    }

    async function postAction(url, payload, successMessage) {
        if (busy) return;
        setBusy(true);
        try {
            const response = await fetch(url, {
                method: "POST",
                credentials: "same-origin",
                headers: {
                    Accept: "application/json",
                    "Content-Type": "application/json",
                    "X-CSRFToken": csrfToken,
                },
                body: JSON.stringify({ ...payload, expected_turn_revision: state.turn_revision }),
            });
            const result = await response.json().catch(() => ({}));
            if (!response.ok) {
                if (result.state) {
                    state = result.state;
                    render();
                }
                throw new Error(result.error || "Cette action n’a pas pu être effectuée.");
            }
            state = result;
            render();
            if (successMessage) announce(successMessage(result));
            setSync("ready", "Synchronisé");
        } catch (error) {
            showFeedback(error.message);
            setSync("offline", "À actualiser");
        } finally {
            setBusy(false);
        }
    }

    elements.roll.addEventListener("click", () => {
        if (!state.can_roll || busy) return;
        if (!reducedMotion.matches) {
            elements.roll.classList.remove("is-rolling");
            void elements.roll.offsetWidth;
            elements.roll.classList.add("is-rolling");
        }
        postAction(game.dataset.rollUrl, {}, (next) => (
            next.pending_roll === null
                ? "Aucun pion ne pouvait avancer : le tour est passé."
                : `Tu as lancé ${next.pending_roll}. Choisis un pion.`
        ));
    });

    game.addEventListener("click", (event) => {
        const pawn = event.target.closest("button[data-pawn-id]");
        if (!pawn || busy) return;
        const pawnId = Number.parseInt(pawn.dataset.pawnId, 10);
        postAction(game.dataset.moveUrl, { pawn_id: pawnId }, () => "Le pion a avancé.");
    });

    elements.copyInvite?.addEventListener("click", async () => {
        try {
            await navigator.clipboard.writeText(window.location.href);
            elements.copyInvite.textContent = "Lien copié !";
            window.setTimeout(() => { elements.copyInvite.textContent = "Copier le lien"; }, 1800);
        } catch (_) {
            showFeedback("Copie le lien affiché dans la barre d’adresse.");
        }
    });

    async function poll() {
        if (busy || document.hidden || pollController) return;
        pollController = new AbortController();
        setSync("syncing", "Actualisation…");
        try {
            const response = await fetch(game.dataset.stateUrl, {
                credentials: "same-origin",
                headers: { Accept: "application/json" },
                signal: pollController.signal,
            });
            if (!response.ok) throw new Error("Synchronisation interrompue.");
            const nextState = await response.json();
            const changed = nextState.turn_revision !== state.turn_revision
                || nextState.status !== state.status
                || nextState.players.length !== state.players.length;
            state = nextState;
            if (changed) render();
            setSync("ready", "Synchronisé");
        } catch (error) {
            if (error.name !== "AbortError") setSync("offline", "Hors ligne");
        } finally {
            pollController = null;
        }
    }

    document.addEventListener("visibilitychange", () => {
        if (!document.hidden) poll();
    });
    render();
    window.setInterval(poll, 1800);
})();

