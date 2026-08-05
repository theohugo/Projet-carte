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

    const $ = (selector) => root.querySelector(selector);
    const $$ = (selector) => [...root.querySelectorAll(selector)];
    const feedback = $("[data-feedback]");
    const announcer = $("[data-announcer]");
    const csrfToken = $("[name=csrfmiddlewaretoken]")?.value || "";
    const views = Object.fromEntries($$("[data-view]").map((node) => [node.dataset.view, node]));
    const resultLabels = { MISS: "Raté", HIT: "Touché", CAPTURED: "Capturé" };
    const statusLabels = {
        EN_ATTENTE: "En attente",
        PLACEMENT: "Déploiement",
        EN_COURS: "Bataille en cours",
        TERMINEE: "Terminée",
    };

    const coordinate = (row, col) => `${String.fromCharCode(65 + col)}${row + 1}`;
    const cellKey = (row, col) => `${row}:${col}`;

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
        sync.querySelector("span").textContent = busy ? "Synchronisation…" : "Synchronisé";
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
                throw new Error(data.error || "La mer est momentanément inaccessible.");
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
            const copy = document.createElement("span");
            const name = document.createElement("strong");
            name.textContent = formation.pokemon.name_fr;
            const size = document.createElement("small");
            size.textContent = `${formation.size} cases · ${formation.is_placed ? "Placé" : "À placer"}`;
            copy.append(name, size);
            const marker = document.createElement("i");
            marker.textContent = formation.is_placed ? "✓" : String(formation.size);
            marker.setAttribute("aria-hidden", "true");
            button.append(copy, marker);
            button.addEventListener("click", () => {
                selectedFormationId = formation.id;
                renderPlacementFormations();
                renderPlacementGrid();
                $("[data-placement-hint]").textContent = `${formation.pokemon.name_fr} · ${formation.size} cases`;
            });
            container.append(button);
        });
        const ready = $("[data-ready]");
        ready.disabled = !state.can_ready || requestInFlight;
        ready.textContent = state.me.is_ready ? "Équipe verrouillée · attente du rival" : "Verrouiller mon équipe";
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
                button.setAttribute("aria-label", formation ? `${coord}, ${formation.pokemon.name_fr}` : `${coord}, libre`);
                if (formation) {
                    button.classList.add("is-occupied", `is-slot-${formation.slot}`);
                    const [firstRow, firstCol] = formation.cells[0];
                    if (row === firstRow && col === firstCol) button.append(makePokemonImage(formation.pokemon));
                }
                button.addEventListener("click", async () => {
                    if (!active) {
                        setFeedback("Sélectionne d'abord un Pokémon.");
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
        if (state.me.is_ready) hint.textContent = "Position verrouillée · attente du rival";
        else if (selectedFormationId) {
            const selected = state.own_formations.find((item) => item.id === selectedFormationId);
            hint.textContent = selected ? `${selected.pokemon.name_fr} · ${selected.size} cases` : "Sélectionne un Pokémon";
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
                button.setAttribute("aria-label", `${coord}${shot ? `, ${resultLabels[shot.result]}` : ", inexploré"}`);
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
                    if (response?.action_result) {
                        const action = response.action_result;
                        const message = `${action.coordinate} : ${resultLabels[action.result]}${action.captured_pokemon ? ` — ${action.captured_pokemon.name_fr}` : ""}.`;
                        setFeedback(message, action.result === "MISS" ? "info" : "success");
                    }
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
            label.textContent = formation.is_captured ? `${formation.pokemon.name_fr} capturé` : `${formation.pokemon.name_fr} · ${formation.size - formation.hit_cells.length}/${formation.size}`;
            item.append(label);
            squad.append(item);
        });
    }

    function renderBattle() {
        renderEnemyGrid();
        renderOwnGrid();
        $("[data-opponent-name]").textContent = state.opponent?.username || "l’adversaire";
        const firedHits = state.shots_fired.filter((shot) => shot.result !== "MISS").length;
        const receivedHits = state.shots_received.filter((shot) => shot.result !== "MISS").length;
        $("[data-enemy-score]").textContent = `${firedHits} / 12 touches`;
        $("[data-own-score]").textContent = `${12 - receivedHits} cases intactes`;
        const turn = $("[data-turn]");
        turn.classList.toggle("is-active", state.is_my_turn);
        turn.querySelector("span").textContent = state.is_my_turn ? "À toi d'explorer" : `Tour de ${state.current_turn?.username || "l'adversaire"}`;
        $("[data-enemy-help]").textContent = state.is_my_turn ? "Choisis une coordonnée à explorer." : "Observe le radar pendant le tour adverse.";
        if (state.last_shot) {
            const shot = state.last_shot;
            $("[data-last-shot]").textContent = `${shot.coordinate} · ${resultLabels[shot.result]}${shot.captured_pokemon ? ` · ${shot.captured_pokemon.name_fr} capturé` : ""}`;
        } else {
            $("[data-last-shot]").textContent = "Aucun tir pour le moment.";
        }
    }

    function renderResult() {
        const won = state.winner?.id === state.me.id;
        $("[data-result-title]").textContent = won ? "Archipel conquis !" : "Ton équipe a été repérée";
        $("[data-result-copy]").textContent = won
            ? `Belle lecture du radar : tu as capturé toute l'escouade de ${state.opponent?.username}.`
            : `${state.winner?.username} a trouvé tes quatre formations. La revanche t'attend.`;
        const reveal = $("[data-reveal]");
        reveal.replaceChildren();
        state.opponent_formations.forEach((formation) => {
            const card = document.createElement("article");
            card.append(makePokemonImage(formation.pokemon));
            const copy = document.createElement("span");
            const name = document.createElement("strong");
            name.textContent = formation.pokemon.name_fr;
            const placement = document.createElement("small");
            placement.textContent = `${coordinate(formation.row, formation.col)} · ${formation.orientation === "H" ? "horizontal" : "vertical"}`;
            copy.append(name, placement);
            card.append(copy);
            reveal.append(card);
        });
    }

    function renderWaiting() {
        $("[data-invite-url]").textContent = window.location.href;
    }

    function render() {
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
    $("[data-ready]")?.addEventListener("click", () => post(root.dataset.readyUrl, {}));
    $("[data-copy]")?.addEventListener("click", async (event) => {
        try {
            await navigator.clipboard.writeText(window.location.href);
            event.currentTarget.textContent = "Lien copié !";
            announcer.textContent = "Lien d'invitation copié.";
        } catch (_error) {
            setFeedback("Copie impossible. Sélectionne le lien manuellement.");
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
                state = next;
                render();
                if (previousStatus !== state.status) {
                    const heading = root.querySelector("[data-view]:not([hidden]) h2");
                    heading?.focus({ preventScroll: true });
                } else if (!previousTurn && state.is_my_turn) {
                    announcer.textContent = "C'est à toi d'explorer une coordonnée.";
                }
            }
        } catch (_error) {
            const sync = $("[data-sync]");
            sync.querySelector("span").textContent = "Reconnexion…";
        }
    }

    render();
    window.setInterval(poll, 1800);
})();
