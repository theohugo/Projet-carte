(() => {
    "use strict";

    const root = document.querySelector("#islands-game");
    const initialNode = document.querySelector("#islands-initial-state");
    if (!root || !initialNode) return;
    const page = root.closest(".is-game-page") || document;

    let state = JSON.parse(initialNode.textContent);
    let selectedFormationId = null;
    let orientation = "H";
    let requestInFlight = false;
    let focusedEnemyCoordinate = null;
    let botTurnTimer = null;
    let comboSignature = "";
    const reducedMotion = window.matchMedia("(prefers-reduced-motion: reduce)");

    const $ = (selector) => root.querySelector(selector);
    const $$ = (selector) => [...root.querySelectorAll(selector)];
    const copy = (key, fallback = "") => state.ui?.[key] || fallback;
    const feedback = $("[data-feedback]");
    const announcer = $("[data-announcer]");
    const csrfToken = $("[name=csrfmiddlewaretoken]")?.value || "";
    const views = Object.fromEntries($$("[data-view]").map((node) => [node.dataset.view, node]));
    const resultLabels = {
        MISS: copy("result_miss", "Miss"),
        HIT: copy("result_hit", "Hit"),
        CAPTURED: copy("result_captured", "Captured"),
    };
    const statusLabels = {
        EN_ATTENTE: copy("status_waiting", "Waiting"),
        PLACEMENT: copy("status_placement", "Deployment"),
        EN_COURS: copy("status_battle", "Battle in progress"),
        TERMINEE: copy("status_finished", "Finished"),
    };

    const coordinate = (row, col) => `${String.fromCharCode(65 + col)}${row + 1}`;
    const cellKey = (row, col) => `${row}:${col}`;
    const pokemonLabel = (pokemon) => pokemon?.name || pokemon?.name_fr || pokemon?.name_en || "Pokémon";

    function setFeedback(message, kind = "error") {
        feedback.textContent = message || "";
        feedback.dataset.kind = kind;
        feedback.hidden = !message;
        if (message) announcer.textContent = message;
    }

    function setBusy(busy) {
        requestInFlight = busy;
        root.setAttribute("aria-busy", String(busy));
        const sync = page.querySelector("[data-sync]");
        sync.classList.toggle("is-syncing", busy);
        sync.querySelector("span").textContent = busy
            ? copy("syncing", "Syncing…")
            : copy("synced", "Synced");
    }

    async function post(url, payload) {
        if (requestInFlight) return null;
        setBusy(true);
        setFeedback("");
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
            const data = await response.json().catch(() => ({}));
            if (!response.ok) {
                if (data.state) {
                    state = data.state;
                    render();
                }
                throw new Error(data.error || copy("network_error", "The sea is temporarily unreachable."));
            }
            state = data;
            render();
            return data;
        } catch (error) {
            setFeedback(error.message);
            return null;
        } finally {
            setBusy(false);
            // Le premier rendu a lieu pendant la requête et neutralise les
            // actions. Un second passage rétablit immédiatement les contrôles
            // autorisés (notamment « Verrouiller » après le 4e placement).
            render();
        }
    }

    function showView(name) {
        Object.entries(views).forEach(([viewName, node]) => {
            node.hidden = viewName !== name;
        });
    }

    function shotCombo(shots) {
        let combo = 0;
        for (let index = shots.length - 1; index >= 0; index -= 1) {
            if (shots[index].result === "MISS") break;
            combo += 1;
        }
        return combo;
    }

    function animateShot(gridSelector, action) {
        if (!action || reducedMotion.matches) return;
        const cell = $(`${gridSelector} [data-row="${action.row}"][data-col="${action.col}"]`);
        const visibleCell = cell && !cell.closest("[data-view]")?.hidden;
        const target = visibleCell ? cell : root;
        if (visibleCell) {
            cell.classList.remove("is-struck");
            void cell.offsetWidth;
            cell.classList.add("is-struck");
        }
        const effect = document.createElement("span");
        effect.className = `is-shot-fx is-${action.result.toLowerCase()}${visibleCell ? "" : " is-final-impact"}`;
        effect.setAttribute("aria-hidden", "true");
        for (let index = 0; index < 5; index += 1) effect.append(document.createElement("i"));
        target.append(effect);
        window.setTimeout(() => {
            effect.remove();
            cell?.classList.remove("is-struck");
        }, 1750);
    }

    function renderCombo() {
        const combo = $("[data-combo]");
        const lastShot = state.last_shot;
        const isOwnShot = lastShot && state.shots_fired.some((shot) => shot.id === lastShot.id);
        const source = isOwnShot ? state.shots_fired : state.shots_received;
        const count = lastShot?.result === "MISS" ? 0 : shotCombo(source);
        const shooterStillActive = lastShot && (
            (isOwnShot && state.current_turn?.id === state.me.id)
            || (!isOwnShot && state.current_turn?.id === state.opponent?.id)
        );
        combo.hidden = !shooterStillActive || count < 1;
        if (combo.hidden) {
            comboSignature = "";
            return;
        }
        $("[data-combo-count]").textContent = String(count);
        $("[data-combo-copy]").textContent = isOwnShot
            ? copy("you_replay", "You play again!")
            : `${state.opponent?.username || copy("rival", "Your opponent")} ${copy("replays", "plays again")}`;
        const signature = `${lastShot.id}:${count}`;
        if (signature !== comboSignature) {
            comboSignature = signature;
            combo.classList.remove("is-flaring");
            void combo.offsetWidth;
            combo.classList.add("is-flaring");
        }
    }

    function announceShot(action, { incoming = false } = {}) {
        if (!action) return;
        animateShot(incoming ? "[data-own-grid]" : "[data-enemy-grid]", action);
        const captured = action.captured_pokemon ? ` — ${pokemonLabel(action.captured_pokemon)}` : "";
        const replay = action.keeps_turn
            ? incoming
                ? ` ${state.opponent?.username || copy("opponent", "Your opponent")} ${copy("replays", "plays again")}${action.combo > 1 ? ` · combo ×${action.combo}` : ""} !`
                : ` ${copy("you_replay_inline", "You play again")}${action.combo > 1 ? ` · combo ×${action.combo}` : ""} !`
            : "";
        const message = `${action.coordinate} : ${resultLabels[action.result]}${captured}.${replay}`;
        setFeedback(message, action.result === "MISS" ? "info" : incoming ? "error" : "success");
    }

    function makePokemonImage(pokemon, className = "") {
        const image = document.createElement("img");
        image.src = pokemon.sprite_url;
        image.alt = "";
        image.width = 88;
        image.height = 88;
        image.loading = "lazy";
        image.className = className;
        return image;
    }

    function formationAt(row, col) {
        return state.own_formations.find((formation) =>
            formation.cells.some(([cellRow, cellCol]) => cellRow === row && cellCol === col)
        );
    }

    function renderPlacementFormations() {
        const container = $("[data-formations]");
        const placedCount = state.own_formations.filter((formation) => formation.is_placed).length;
        $("[data-placement-count]").textContent = `${placedCount}/4`;
        if (!selectedFormationId || !state.own_formations.some((item) => item.id === selectedFormationId)) {
            selectedFormationId = (state.own_formations.find((item) => !item.is_placed) || state.own_formations[0])?.id;
        }
        container.replaceChildren();
        state.own_formations.forEach((formation) => {
            const button = document.createElement("button");
            button.type = "button";
            button.className = "is-formation";
            button.dataset.slot = formation.slot;
            button.setAttribute("aria-pressed", String(formation.id === selectedFormationId));
            button.disabled = !state.can_place;
            button.append(makePokemonImage(formation.pokemon));
            const formationCopy = document.createElement("span");
            const name = document.createElement("strong");
            name.textContent = pokemonLabel(formation.pokemon);
            const size = document.createElement("small");
            size.textContent = `${formation.size} ${copy("cells", "cells")} · ${formation.is_placed ? copy("placed", "Placed") : copy("to_place", "To place")}`;
            formationCopy.append(name, size);
            const marker = document.createElement("i");
            marker.textContent = formation.is_placed ? "✓" : String(formation.size);
            marker.setAttribute("aria-hidden", "true");
            button.append(formationCopy, marker);
            button.addEventListener("click", () => {
                selectedFormationId = formation.id;
                renderPlacementFormations();
                renderPlacementGrid();
                $("[data-placement-hint]").textContent = `${pokemonLabel(formation.pokemon)} · ${formation.size} ${copy("cells", "cells")}`;
            });
            container.append(button);
        });
        const ready = $("[data-ready]");
        ready.disabled = !state.can_ready || requestInFlight;
        ready.textContent = state.me.is_ready
            ? copy("team_locked_waiting", "Team locked · waiting for opponent")
            : copy("lock_team", "Lock my team");
    }

    function renderPlacementGrid() {
        const grid = $("[data-placement-grid]");
        const active = state.own_formations.find((formation) => formation.id === selectedFormationId);
        grid.replaceChildren();
        for (let row = 0; row < 8; row += 1) {
            for (let col = 0; col < 8; col += 1) {
                const button = document.createElement("button");
                const coord = coordinate(row, col);
                const formation = formationAt(row, col);
                button.type = "button";
                button.setAttribute("role", "gridcell");
                button.dataset.row = row;
                button.dataset.col = col;
                button.className = "is-cell";
                button.disabled = !state.can_place;
                button.setAttribute("aria-label", formation
                    ? `${coord}, ${pokemonLabel(formation.pokemon)}`
                    : `${coord}, ${copy("free_cell", "free")}`);
                if (formation) {
                    button.classList.add("is-occupied", `is-slot-${formation.slot}`);
                    const [firstRow, firstCol] = formation.cells[0];
                    if (row === firstRow && col === firstCol) button.append(makePokemonImage(formation.pokemon));
                }
                button.addEventListener("click", async () => {
                    if (!active) {
                        setFeedback(copy("select_first", "Select a Pokémon first."));
                        return;
                    }
                    await post(root.dataset.placeUrl, {
                        formation_id: active.id,
                        row,
                        col,
                        orientation,
                    });
                });
                grid.append(button);
            }
        }
    }

    function renderPlacement() {
        renderPlacementFormations();
        renderPlacementGrid();
        const hint = $("[data-placement-hint]");
        if (state.me.is_ready) {
            hint.textContent = copy("position_locked_waiting", "Position locked · waiting for opponent");
        }
        else if (selectedFormationId) {
            const selected = state.own_formations.find((item) => item.id === selectedFormationId);
            hint.textContent = selected
                ? `${pokemonLabel(selected.pokemon)} · ${selected.size} ${copy("cells", "cells")}`
                : copy("select_pokemon", "Select a Pokémon");
        }
        $$("[data-orientation]").forEach((button) => {
            button.disabled = !state.can_place;
            button.setAttribute("aria-pressed", String(button.dataset.orientation === orientation));
        });
    }

    function renderEnemyGrid() {
        const grid = $("[data-enemy-grid]");
        const shots = new Map(state.shots_fired.map((shot) => [cellKey(shot.row, shot.col), shot]));
        const activeElement = document.activeElement;
        if (activeElement?.closest("[data-enemy-grid]")) focusedEnemyCoordinate = activeElement.dataset.coordinate;
        const available = [];
        for (let row = 0; row < 8; row += 1) {
            for (let col = 0; col < 8; col += 1) {
                if (!shots.has(cellKey(row, col))) available.push(coordinate(row, col));
            }
        }
        if (!focusedEnemyCoordinate || !available.includes(focusedEnemyCoordinate)) focusedEnemyCoordinate = available[0] || "A1";
        grid.replaceChildren();
        for (let row = 0; row < 8; row += 1) {
            for (let col = 0; col < 8; col += 1) {
                const button = document.createElement("button");
                const coord = coordinate(row, col);
                const shot = shots.get(cellKey(row, col));
                button.type = "button";
                button.setAttribute("role", "gridcell");
                button.className = "is-cell";
                button.dataset.row = row;
                button.dataset.col = col;
                button.dataset.coordinate = coord;
                button.tabIndex = coord === focusedEnemyCoordinate ? 0 : -1;
                button.disabled = Boolean(shot) || !state.is_my_turn || requestInFlight;
                button.setAttribute("aria-label", `${coord}${shot ? `, ${resultLabels[shot.result]}` : `, ${copy("unexplored", "unexplored")}`}`);
                if (shot) {
                    button.classList.add(`is-${shot.result.toLowerCase()}`);
                    const marker = document.createElement("span");
                    marker.setAttribute("aria-hidden", "true");
                    marker.textContent = shot.result === "MISS" ? "·" : shot.result === "HIT" ? "×" : "◆";
                    button.append(marker);
                }
                button.addEventListener("focus", () => { focusedEnemyCoordinate = coord; });
                button.addEventListener("click", async () => {
                    const response = await post(root.dataset.fireUrl, { row, col });
                    announceShot(response?.action_result);
                });
                button.addEventListener("keydown", handleGridKeydown);
                grid.append(button);
            }
        }
    }

    function handleGridKeydown(event) {
        const moves = { ArrowLeft: [0, -1], ArrowRight: [0, 1], ArrowUp: [-1, 0], ArrowDown: [1, 0] };
        if (!moves[event.key]) return;
        event.preventDefault();
        const [rowMove, colMove] = moves[event.key];
        let row = Number(event.currentTarget.dataset.row);
        let col = Number(event.currentTarget.dataset.col);
        for (let attempts = 0; attempts < 64; attempts += 1) {
            row = (row + rowMove + 8) % 8;
            col = (col + colMove + 8) % 8;
            const next = $( `[data-enemy-grid] [data-row="${row}"][data-col="${col}"]` );
            if (next && !next.disabled) {
                event.currentTarget.tabIndex = -1;
                next.tabIndex = 0;
                next.focus();
                break;
            }
        }
    }

    function renderOwnGrid() {
        const grid = $("[data-own-grid]");
        const shots = new Map(state.shots_received.map((shot) => [cellKey(shot.row, shot.col), shot]));
        grid.replaceChildren();
        for (let row = 0; row < 8; row += 1) {
            for (let col = 0; col < 8; col += 1) {
                const cell = document.createElement("span");
                const formation = formationAt(row, col);
                const shot = shots.get(cellKey(row, col));
                cell.className = "is-cell";
                cell.dataset.row = row;
                cell.dataset.col = col;
                cell.setAttribute("aria-hidden", "true");
                if (formation) {
                    cell.classList.add("is-occupied", `is-slot-${formation.slot}`);
                    const [firstRow, firstCol] = formation.cells[0];
                    if (row === firstRow && col === firstCol) cell.append(makePokemonImage(formation.pokemon));
                }
                if (shot) {
                    cell.classList.add(`is-${shot.result.toLowerCase()}`);
                    const marker = document.createElement("b");
                    marker.textContent = shot.result === "MISS" ? "·" : "×";
                    cell.append(marker);
                }
                grid.append(cell);
            }
        }
        const squad = $("[data-own-squad]");
        squad.replaceChildren();
        state.own_formations.forEach((formation) => {
            const item = document.createElement("span");
            item.className = formation.is_captured ? "is-captured" : "";
            item.append(makePokemonImage(formation.pokemon));
            const label = document.createElement("small");
            label.textContent = formation.is_captured
                ? `${pokemonLabel(formation.pokemon)} ${copy("captured_suffix", "captured")}`
                : `${pokemonLabel(formation.pokemon)} · ${formation.size - formation.hit_cells.length}/${formation.size}`;
            item.append(label);
            squad.append(item);
        });
    }

    function renderBattle() {
        renderEnemyGrid();
        renderOwnGrid();
        $("[data-opponent-name]").textContent = state.opponent?.username || copy("opponent", "your opponent");
        const firedHits = state.shots_fired.filter((shot) => shot.result !== "MISS").length;
        const receivedHits = state.shots_received.filter((shot) => shot.result !== "MISS").length;
        $("[data-enemy-score]").textContent = `${firedHits} / 12 ${copy("hits", "hits")}`;
        $("[data-own-score]").textContent = `${12 - receivedHits} ${copy("intact_cells", "intact cells")}`;
        const turn = $("[data-turn]");
        turn.classList.toggle("is-active", state.is_my_turn);
        turn.querySelector("span").textContent = state.is_my_turn
            ? copy("your_turn", "Your turn to explore")
            : `${copy("turn_of", "Turn:")} ${state.current_turn?.username || copy("opponent", "your opponent")}`;
        $("[data-enemy-help]").textContent = state.is_my_turn
            ? copy("choose_coordinate", "Choose a coordinate to explore.")
            : copy("watch_radar", "Watch the radar during your opponent's turn.");
        if (state.last_shot) {
            const shot = state.last_shot;
            $("[data-last-shot]").textContent = `${shot.coordinate} · ${resultLabels[shot.result]}${shot.captured_pokemon ? ` · ${pokemonLabel(shot.captured_pokemon)} ${copy("captured_suffix", "captured")}` : ""}`;
        } else {
            $("[data-last-shot]").textContent = copy("no_shots", "No shots yet.");
        }
        renderCombo();
    }

    function renderResult() {
        const won = state.winner?.id === state.me.id;
        $("[data-result-title]").textContent = won
            ? copy("victory_title", "Archipelago conquered!")
            : copy("defeat_title", "Your team has been located");
        $("[data-result-copy]").textContent = won
            ? `${copy("victory_prefix", "Excellent radar work: you captured the entire squad of")} ${state.opponent?.username}.`
            : `${state.winner?.username} ${copy("defeat_suffix", "found all four of your formations. A rematch awaits.")}`;
        const reveal = $("[data-reveal]");
        reveal.replaceChildren();
        state.opponent_formations.forEach((formation) => {
            const card = document.createElement("article");
            card.append(makePokemonImage(formation.pokemon));
            const resultCopy = document.createElement("span");
            const name = document.createElement("strong");
            name.textContent = pokemonLabel(formation.pokemon);
            const placement = document.createElement("small");
            placement.textContent = `${coordinate(formation.row, formation.col)} · ${formation.orientation === "H" ? copy("horizontal", "horizontal") : copy("vertical", "vertical")}`;
            resultCopy.append(name, placement);
            card.append(resultCopy);
            reveal.append(card);
        });
    }

    function renderWaiting() {
        $("[data-invite-url]").textContent = window.location.href;
        const players = state.players || [];
        const ui = state.ui || {};
        const hasBot = players.some((player) => player.is_bot);
        $("[data-waiting-count]").textContent = String(players.length);
        $("#is-wait-title").textContent = hasBot
            ? ui.bot_joined_title || "Your AI opponent is ready"
            : ui.waiting_title || "Waiting for an opponent";
        $("[data-waiting-lead]").textContent = hasBot
            ? ui.bot_joined_lead || "Its fleet will stay secret. Start deploying your team when ready."
            : ui.waiting_lead || "Share this link or add an AI opponent to begin.";
        $(".is-invite").hidden = hasBot;
        const roster = $("[data-waiting-players]");
        roster.replaceChildren();
        for (let index = 0; index < state.max_players; index += 1) {
            const player = players[index];
            const item = document.createElement("li");
            item.className = `is-waiting-player${player?.is_bot ? " is-bot" : ""}${player ? "" : " is-open"}`;
            const avatar = document.createElement("span");
            avatar.className = "is-player-avatar";
            avatar.setAttribute("aria-hidden", "true");
            avatar.textContent = player ? (player.is_bot ? ui.bot_initial || "AI" : player.username.slice(0, 1).toUpperCase()) : "+";
            const playerCopy = document.createElement("span");
            const name = document.createElement("strong");
            name.textContent = player?.username || ui.open_slot || "Open slot";
            const role = document.createElement("small");
            role.textContent = player
                ? (player.is_bot ? ui.bot_ready || "AI opponent · ready" : ui.human_ready || "Human captain")
                : ui.max_two || "2 players maximum";
            playerCopy.append(name, role);
            item.append(avatar, playerCopy);
            if (state.is_host && player?.is_bot) {
                const remove = document.createElement("button");
                remove.type = "button";
                remove.className = "is-player-remove";
                remove.textContent = "×";
                remove.disabled = requestInFlight;
                remove.setAttribute("aria-label", `${ui.remove_bot || "Remove AI"} ${player.username}`);
                remove.addEventListener("click", () => removeBot(player.id));
                item.append(remove);
            }
            roster.append(item);
        }

        const controls = $("[data-host-controls]");
        controls.hidden = !state.is_host;
        const addButton = $("[data-add-bot]");
        const startButton = $("[data-start-bot]");
        addButton.disabled = !state.can_add_bot || requestInFlight;
        startButton.disabled = !state.can_start || requestInFlight;
        const hint = $("[data-start-hint]");
        hint.textContent = state.can_start
            ? ui.start_ready || "The AI has joined. Start deployment when you are ready."
            : players.length >= state.max_players
                ? ui.table_full || "The table is full."
                : ui.invite_or_bot || "Invite a friend or add an AI opponent to play now.";
    }

    function removeBot(botId) {
        const url = root.dataset.removeBotUrlTemplate.replace(/\/0\/remove\/$/, `/${botId}/remove/`);
        return post(url, {});
    }

    function scheduleBotTurn() {
        window.clearTimeout(botTurnTimer);
        botTurnTimer = null;
        if (requestInFlight || document.hidden || !state.bot_turn_pending || !root.dataset.botTurnUrl) return;
        $("[data-enemy-help]").textContent = state.ui?.bot_thinking || "The AI is scanning the radar…";
        botTurnTimer = window.setTimeout(async () => {
            botTurnTimer = null;
            const response = await post(root.dataset.botTurnUrl, {});
            announceShot(response?.action_result, { incoming: true });
        }, reducedMotion.matches ? 300 : 950);
    }

    function render() {
        window.clearTimeout(botTurnTimer);
        botTurnTimer = null;
        page.querySelector("[data-status]").textContent = statusLabels[state.status] || state.status;
        if (state.status === "EN_ATTENTE") {
            showView("waiting");
            renderWaiting();
        } else if (state.status === "PLACEMENT") {
            showView("placement");
            renderPlacement();
        } else if (state.status === "EN_COURS") {
            showView("battle");
            renderBattle();
            scheduleBotTurn();
        } else {
            showView("result");
            renderResult();
        }
    }

    $$("[data-orientation]").forEach((button) => {
        button.addEventListener("click", () => {
            orientation = button.dataset.orientation;
            $$("[data-orientation]").forEach((item) => item.setAttribute("aria-pressed", String(item === button)));
        });
    });
    $("[data-add-bot]")?.addEventListener("click", () => post(root.dataset.addBotUrl, {}));
    $("[data-start-bot]")?.addEventListener("click", () => post(root.dataset.startUrl, {}));
    $("[data-ready]")?.addEventListener("click", () => post(root.dataset.readyUrl, {}));
    $("[data-copy]")?.addEventListener("click", async (event) => {
        try {
            await navigator.clipboard.writeText(window.location.href);
            event.currentTarget.textContent = copy("link_copied", "Link copied!");
            announcer.textContent = copy("invitation_copied", "Invitation link copied.");
        } catch (_error) {
            setFeedback(copy("copy_failed", "Could not copy. Select the link manually."));
        }
    });

    async function poll() {
        if (document.hidden || requestInFlight || state.status === "TERMINEE") return;
        try {
            const response = await fetch(root.dataset.stateUrl, {
                headers: { Accept: "application/json" },
                credentials: "same-origin",
            });
            if (!response.ok) return;
            const next = await response.json();
            if (next.turn_revision !== state.turn_revision || next.status !== state.status) {
                const previousStatus = state.status;
                const previousTurn = state.is_my_turn;
                const previousShotId = state.last_shot?.id;
                state = next;
                render();
                if (state.last_shot && state.last_shot.id !== previousShotId) {
                    const incoming = state.shots_received.some((shot) => shot.id === state.last_shot.id);
                    announceShot(state.last_shot, { incoming });
                }
                if (previousStatus !== state.status) {
                    const heading = root.querySelector("[data-view]:not([hidden]) h2");
                    heading?.focus({ preventScroll: true });
                } else if (!previousTurn && state.is_my_turn) {
                    announcer.textContent = copy(
                        "your_turn_announcement",
                        "It is your turn to explore a coordinate.",
                    );
                }
            }
        } catch (_error) {
            const sync = page.querySelector("[data-sync]");
            sync.querySelector("span").textContent = copy("reconnecting", "Reconnecting…");
        }
    }

    render();
    document.addEventListener("visibilitychange", () => {
        if (!document.hidden) {
            render();
            poll();
        }
    });
    window.setInterval(poll, 1800);
})();
