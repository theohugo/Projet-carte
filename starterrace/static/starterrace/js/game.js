(() => {
    "use strict";

    const game = document.getElementById("starterrace-game");
    const initialNode = document.getElementById("starterrace-initial-state");
    const i18nNode = document.getElementById("starterrace-i18n");
    if (!game || !initialNode || !i18nNode) return;

    let messages = {};
    let state;
    try {
        messages = JSON.parse(i18nNode.textContent);
        state = JSON.parse(initialNode.textContent);
    } catch (_) {
        game.textContent = messages.load_error || "The board could not be loaded. Refresh the page.";
        return;
    }

    function t(key, variables = {}) {
        const template = messages[key] || key;
        return template.replace(/\{(\w+)\}/g, (match, name) => (
            Object.hasOwn(variables, name) ? String(variables[name]) : match
        ));
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
        addBot: game.querySelector("[data-add-bot]"),
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
        EN_ATTENTE: t("status_waiting"),
        EN_COURS: t("status_running"),
        TERMINEE: t("status_finished"),
    };
    const COLOR_VALUES = {
        leaf: "var(--sr-leaf)",
        flame: "var(--sr-flame)",
        wave: "var(--sr-wave)",
        spark: "var(--sr-spark)",
    };
    const COLOR_NAMES = {
        leaf: t("color_leaf"),
        flame: t("color_flame"),
        wave: t("color_wave"),
        spark: t("color_spark"),
    };
    const reducedMotion = window.matchMedia("(prefers-reduced-motion: reduce)");
    const csrfToken = game.querySelector('[name="csrfmiddlewaretoken"]')?.value || readCookie("csrftoken");
    let busy = false;
    let feedbackTimer = null;
    let pollController = null;
    let lastView = null;
    let lastAnimatedSequence = state.moves.at(-1)?.sequence || 0;
    let lastPendingRollSignature = pendingRollSignature(state);
    let lastRevealedRoll = state.pending_roll === null ? null : {
        playerId: state.current_turn?.id,
        roll: state.pending_roll,
    };
    let moveAnimationTimer = null;

    function pendingRollSignature(candidate) {
        if (candidate.pending_roll === null || !candidate.current_turn) return "";
        return `${candidate.current_turn.id}:${candidate.pending_roll}:${candidate.turn_revision}`;
    }

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
        if (value) setSync("syncing", t("sending"));
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
        elements.status.textContent = STATUS_LABELS[state.status] || t("race");
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
        animatePendingRoll();
        animateLatestMove();
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
            const player = state.players.find((candidate) => candidate.turn_order === index);
            const seat = document.createElement("div");
            seat.className = `sr-seat${player ? "" : " is-empty"}`;
            if (player) {
                seat.style.setProperty("--player-color", playerColor(player));
                seat.appendChild(makeImage(player));
                const copy = document.createElement("span");
                copy.className = "sr-seat-copy";
                const name = document.createElement("strong");
                name.textContent = player.username;
                const starter = document.createElement("small");
                starter.textContent = `${player.starter.name} · ${t("ready")}${player.is_bot ? ` · ${t("computer")}` : ""}`;
                copy.append(name, starter);
                seat.appendChild(copy);
                if (state.is_host && player.is_bot) {
                    const form = document.createElement("form");
                    form.method = "post";
                    form.action = game.dataset.removeBotUrlTemplate.replace(
                        /\/0\/remove\/$/,
                        `/${player.id}/remove/`,
                    );
                    form.className = "sr-remove-bot-form";
                    const csrf = document.createElement("input");
                    csrf.type = "hidden";
                    csrf.name = "csrfmiddlewaretoken";
                    csrf.value = csrfToken;
                    const remove = document.createElement("button");
                    remove.type = "submit";
                    remove.className = "sr-remove-bot";
                    remove.textContent = "×";
                    remove.setAttribute("aria-label", t("remove_bot_aria", { player: player.username }));
                    remove.title = t("remove_bot");
                    form.append(csrf, remove);
                    seat.appendChild(form);
                }
            } else {
                const icon = document.createElement("span");
                icon.className = "sr-seat-icon";
                icon.setAttribute("aria-hidden", "true");
                icon.textContent = "+";
                const copy = document.createElement("span");
                copy.className = "sr-seat-copy";
                const name = document.createElement("strong");
                name.textContent = t("open_seat");
                const status = document.createElement("small");
                status.textContent = t("waiting");
                copy.append(name, status);
                seat.append(icon, copy);
            }
            elements.waitingSeats.appendChild(seat);
        }

        if (elements.addBot) elements.addBot.disabled = !state.can_add_bot;
        if (elements.startButton) {
            elements.startButton.disabled = !state.can_start;
            elements.startHint.textContent = state.can_start
                ? t("trainers_ready", { count: state.players.length })
                : t("need_trainer");
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
        const values = { starter: player.starter.name, number };
        if (pawn.zone === "HOME") return t("pawn_home", values);
        if (pawn.zone === "FINISHED") return t("pawn_finished", values);
        if (pawn.zone === "FINAL_LANE") {
            return t("pawn_lane", { ...values, cell: pawn.final_index + 1 });
        }
        return t("pawn_track", { ...values, cell: pawn.global_position + 1 });
    }

    function makePawn(pawn, player) {
        const selectable = state.can_move && state.legal_pawn_ids.some((id) => sameId(id, pawn.id));
        const node = document.createElement(selectable ? "button" : "span");
        node.className = "sr-pawn";
        node.dataset.playerId = String(player.id);
        node.dataset.pawnNumber = String(pawn.number);
        node.style.setProperty("--player-color", playerColor(player));
        node.setAttribute("aria-label", `${pawnLabel(pawn, player)}${selectable ? `. ${t("move_pawn")}` : ""}`);
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
            const labels = [t("cell", { cell: cell + 1 })];

            if (safeCells.has(cell)) {
                item.classList.add("is-safe");
                labels.push(t("safe"));
            }
            if (shortcuts.has(cell)) {
                item.classList.add("is-shortcut");
                labels.push(t("shortcut_to", { cell: shortcuts.get(cell) + 1 }));
            }
            const starter = starts.get(cell);
            if (starter) {
                item.classList.add("is-start");
                item.style.setProperty("--start-color", playerColor(starter));
                labels.push(t("start_of", { starter: starter.starter.name }));
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
            score.textContent = t("arrived", { count: player.finished_count });
            heading.append(title, score);
            const starter = document.createElement("small");
            starter.textContent = t("team", {
                starter: player.starter.name,
                color: COLOR_NAMES[player.color],
            });

            const lane = document.createElement("div");
            lane.className = "sr-pawn-lane";
            lane.setAttribute("aria-label", t("camp_lane", { player: player.username }));
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
        elements.turnProgress.textContent = t("league_progress", { count: current.finished_count });

        if (state.is_my_turn && state.pending_roll === null) {
            elements.turnTitle.textContent = t("your_roll");
            elements.turnHint.textContent = t("six_help");
        } else if (state.is_my_turn) {
            elements.turnTitle.textContent = t("you_rolled", { roll: state.pending_roll });
            elements.turnHint.textContent = t("choose_glowing");
        } else if (state.pending_roll !== null) {
            elements.turnTitle.textContent = t("player_rolled", {
                player: current.username,
                roll: state.pending_roll,
            });
            elements.turnHint.textContent = t("choosing_move", { starter: current.starter.name });
        } else {
            elements.turnTitle.textContent = t("players_turn", { player: current.username });
            elements.turnHint.textContent = t("about_to_roll", { starter: current.starter.name });
        }

        elements.roll.disabled = busy || !state.can_roll;
        elements.dieFace.textContent = state.pending_roll === null ? "?" : String(state.pending_roll);
        if (state.can_roll) {
            elements.actionTitle.textContent = t("roll_die");
            elements.actionHelp.textContent = t("roll_help");
        } else if (state.can_move) {
            elements.actionTitle.textContent = t("choose_to_move", { roll: state.pending_roll });
            elements.actionHelp.textContent = state.legal_pawn_ids.length === 1
                ? t("available_pawn_one")
                : t("available_pawn_many", { count: state.legal_pawn_ids.length });
        } else {
            elements.actionTitle.textContent = t("action_turn", { player: current.username });
            elements.actionHelp.textContent = t("board_updates");
        }
    }

    function moveDescription(move) {
        const name = move.player.username;
        if (move.was_pass) {
            const result = t("no_move", { player: name, roll: move.roll });
            return move.grants_extra_turn ? `${result} ${t("new_try")}` : result;
        }
        const parts = [];
        if (move.from_position === -1) {
            parts.push(t("enters_track", { player: name, pawn: move.pawn_number + 1 }));
        } else {
            parts.push(t(move.roll === 1 ? "moves_space_one" : "moves_space_many", {
                player: name,
                pawn: move.pawn_number + 1,
                roll: move.roll,
            }));
        }
        if (move.shortcut_from !== null) {
            parts.push(t("takes_shortcut", { cell: move.shortcut_to + 1 }));
        }
        if (move.captured_pawns.length) {
            const names = move.captured_pawns.map((captured) => captured.username).join(", ");
            parts.push(t(move.captured_pawns.length > 1 ? "captured_many" : "captured_one", {
                players: names,
            }));
        }
        if (move.to_position === 43) parts.push(t("reaches_league"));
        if (move.grants_extra_turn) parts.push(t("roll_again"));
        return parts.join(" ");
    }

    function renderHistory() {
        elements.moveCount.textContent = String(state.moves.length);
        elements.historyEmpty.hidden = state.moves.length > 0;
        const entries = state.moves.map((move) => {
            const item = document.createElement("li");
            item.className = "sr-history-entry";
            item.dataset.moveSequence = String(move.sequence);
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
        elements.resultTitle.textContent = t("winner", { player: winner.username });
        elements.resultCopy.textContent = t("winner_copy", { starter: winner.starter.name });
    }

    function animatePendingRoll() {
        const signature = pendingRollSignature(state);
        if (!signature || signature === lastPendingRollSignature) return;
        lastPendingRollSignature = signature;
        lastRevealedRoll = {
            playerId: state.current_turn?.id,
            roll: state.pending_roll,
        };
        if (reducedMotion.matches || state.status !== "EN_COURS") return;

        window.clearTimeout(moveAnimationTimer);
        elements.dieFace.textContent = String(state.pending_roll);
        elements.roll.classList.remove("is-revealing");
        void elements.roll.offsetWidth;
        elements.roll.classList.add("is-revealing");
        moveAnimationTimer = window.setTimeout(() => {
            elements.roll.classList.remove("is-revealing");
        }, 760);
    }

    function animateLatestMove() {
        const latest = state.moves.at(-1);
        if (!latest || latest.sequence <= lastAnimatedSequence) return;
        lastAnimatedSequence = latest.sequence;
        const rollWasAlreadyRevealed = lastRevealedRoll
            && sameId(lastRevealedRoll.playerId, latest.player.id)
            && lastRevealedRoll.roll === latest.roll;
        if (rollWasAlreadyRevealed) lastRevealedRoll = null;
        if (reducedMotion.matches || state.status === "EN_ATTENTE") return;

        window.clearTimeout(moveAnimationTimer);
        if (!rollWasAlreadyRevealed) {
            elements.dieFace.textContent = String(latest.roll);
            elements.roll.classList.remove("is-revealing");
            void elements.roll.offsetWidth;
            elements.roll.classList.add("is-revealing");
        }

        const historyEntry = elements.history.querySelector(
            `[data-move-sequence="${latest.sequence}"]`,
        );
        historyEntry?.classList.add("is-new");

        if (!latest.was_pass && latest.pawn_number !== null) {
            const movedPawn = game.querySelector(
                `[data-player-id="${latest.player.id}"][data-pawn-number="${latest.pawn_number}"]`,
            );
            movedPawn?.classList.add(
                latest.to_position === 43
                    ? "is-arriving"
                    : latest.shortcut_from !== null
                        ? "is-shortcut-hop"
                        : "is-moving",
            );
        }

        for (const captured of latest.captured_pawns) {
            game.querySelector(
                `[data-player-id="${captured.player_id}"][data-pawn-number="${captured.pawn_number}"]`,
            )?.classList.add("is-captured");
        }

        const boardEffect = latest.captured_pawns.length
            ? "is-capture-flash"
            : latest.to_position === 43
                ? "is-finish-flash"
                : latest.shortcut_from !== null
                    ? "is-shortcut-flash"
                    : null;
        if (boardEffect) game.classList.add(boardEffect);

        moveAnimationTimer = window.setTimeout(() => {
            elements.roll.classList.remove("is-revealing");
            elements.dieFace.textContent = state.pending_roll === null ? "?" : String(state.pending_roll);
            game.classList.remove("is-capture-flash", "is-shortcut-flash", "is-finish-flash");
        }, 1000);
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
                throw new Error(result.error || t("action_failed"));
            }
            state = result;
            render();
            if (successMessage) announce(successMessage(result));
            setSync("ready", t("synced"));
        } catch (error) {
            showFeedback(error.message);
            setSync("offline", t("refresh"));
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
                ? t("turn_passed")
                : t("roll_announce", { roll: next.pending_roll })
        ));
    });

    game.addEventListener("click", (event) => {
        const pawn = event.target.closest("button[data-pawn-id]");
        if (!pawn || busy) return;
        const pawnId = Number.parseInt(pawn.dataset.pawnId, 10);
        if (!reducedMotion.matches) pawn.classList.add("is-launching");
        postAction(game.dataset.moveUrl, { pawn_id: pawnId }, () => t("pawn_moved"));
    });

    elements.copyInvite?.addEventListener("click", async () => {
        try {
            await navigator.clipboard.writeText(window.location.href);
            elements.copyInvite.textContent = t("link_copied");
            window.setTimeout(() => { elements.copyInvite.textContent = t("copy_link"); }, 1800);
        } catch (_) {
            showFeedback(t("copy_fallback"));
        }
    });

    async function poll() {
        if (busy || document.hidden || pollController) return;
        pollController = new AbortController();
        setSync("syncing", t("updating"));
        try {
            const response = await fetch(game.dataset.stateUrl, {
                credentials: "same-origin",
                headers: { Accept: "application/json" },
                signal: pollController.signal,
            });
            if (!response.ok) throw new Error(t("sync_interrupted"));
            const nextState = await response.json();
            const changed = nextState.turn_revision !== state.turn_revision
                || nextState.status !== state.status
                || nextState.players.length !== state.players.length;
            state = nextState;
            if (changed) render();
            setSync("ready", t("synced"));
        } catch (error) {
            if (error.name !== "AbortError") setSync("offline", t("offline"));
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
