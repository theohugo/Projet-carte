(() => {
    "use strict";

    const root = document.getElementById("metamorph-game");
    const initialNode = document.getElementById("metamorph-initial-state");
    if (!root || !initialNode) return;

    let state;
    try {
        state = JSON.parse(initialNode.textContent);
    } catch (_) {
        return;
    }

    const elements = {
        status: document.querySelector("[data-status]"),
        sync: document.querySelector("[data-sync]"),
        syncLabel: document.querySelector("[data-sync] span"),
        feedback: root.querySelector("[data-feedback]"),
        announcer: root.querySelector("[data-announcer]"),
        waitingView: root.querySelector('[data-view="waiting"]'),
        boardView: root.querySelector('[data-view="board"]'),
        resultView: root.querySelector('[data-view="result"]'),
        waitingCount: root.querySelector("[data-waiting-count]"),
        waitingPlayers: root.querySelector("[data-waiting-players]"),
        inviteUrl: root.querySelector("[data-invite-url]"),
        copyLink: root.querySelector("[data-copy-link]"),
        startGame: root.querySelector("[data-start-game]"),
        startHint: root.querySelector("[data-start-hint]"),
        turnKicker: root.querySelector("[data-turn-kicker]"),
        turnTitle: root.querySelector("[data-turn-title]"),
        turnHelp: root.querySelector("[data-turn-help]"),
        direction: root.querySelector("[data-direction]"),
        players: root.querySelector("[data-players]"),
        sourceTitle: root.querySelector("[data-source-title]"),
        sourceCount: root.querySelector("[data-source-count]"),
        drawCards: root.querySelector("[data-draw-cards]"),
        drawHint: root.querySelector("[data-draw-hint]"),
        pairCount: root.querySelector("[data-pair-count]"),
        pairs: root.querySelector("[data-pairs]"),
        history: root.querySelector("[data-history]"),
        historyEmpty: root.querySelector("[data-history-empty]"),
        handCount: root.querySelector("[data-hand-count]"),
        myHand: root.querySelector("[data-my-hand]"),
        handEmpty: root.querySelector("[data-hand-empty]"),
        resultTitle: root.querySelector("[data-result-title]"),
        resultCopy: root.querySelector("[data-result-copy]"),
        standings: root.querySelector("[data-standings]"),
    };

    const STATUS_LABELS = {
        EN_ATTENTE: "En attente",
        EN_COURS: "Partie en cours",
        TERMINEE: "Terminée",
    };
    const csrfToken = root.querySelector('[name="csrfmiddlewaretoken"]')?.value || readCookie("csrftoken");
    const reducedMotion = window.matchMedia("(prefers-reduced-motion: reduce)");
    let phase = "idle";
    let pollController = null;
    let feedbackTimer = null;
    let renderedFingerprint = null;

    function readCookie(name) {
        const prefix = `${name}=`;
        return document.cookie.split(";").map((part) => part.trim()).find((part) => part.startsWith(prefix))?.slice(prefix.length) || "";
    }

    function sameId(left, right) {
        return left !== null && left !== undefined && right !== null && right !== undefined && String(left) === String(right);
    }

    function plural(count, singular, pluralForm = `${singular}s`) {
        return `${count} ${count > 1 ? pluralForm : singular}`;
    }

    function fingerprint(candidate) {
        return JSON.stringify({
            status: candidate.status,
            revision: candidate.turn_revision,
            current: candidate.current_turn?.id || null,
            players: (candidate.players || []).map((player) => [player.id, player.hand_count, player.rank, player.is_loser]),
            myHand: (candidate.me?.hand || []).map((card) => [card.physical_id, card.position]),
            moves: (candidate.moves || []).length,
            pairs: (candidate.paired_pokemon || []).length,
        });
    }

    function makeElement(tag, className, text) {
        const element = document.createElement(tag);
        if (className) element.className = className;
        if (text !== undefined) element.textContent = text;
        return element;
    }

    function makeAvatar(player) {
        const avatar = makeElement("span", "mm-avatar", (player?.username || "?").slice(0, 1).toLocaleUpperCase("fr-FR"));
        avatar.setAttribute("aria-hidden", "true");
        return avatar;
    }

    function setSync(mode, label) {
        elements.sync?.classList.toggle("is-syncing", mode === "syncing");
        elements.sync?.classList.toggle("is-offline", mode === "offline");
        if (elements.syncLabel) elements.syncLabel.textContent = label;
    }

    function setBusy(busy) {
        phase = busy ? "mutation" : "idle";
        root.setAttribute("aria-busy", String(busy));
        if (busy) setSync("syncing", "Envoi…");
    }

    function announce(message) {
        if (!elements.announcer) return;
        elements.announcer.textContent = "";
        window.requestAnimationFrame(() => { elements.announcer.textContent = message; });
    }

    function showFeedback(message) {
        window.clearTimeout(feedbackTimer);
        elements.feedback.textContent = message;
        elements.feedback.hidden = false;
        feedbackTimer = window.setTimeout(() => { elements.feedback.hidden = true; }, 5500);
    }

    function setView(name) {
        elements.waitingView.hidden = name !== "waiting";
        elements.boardView.hidden = name !== "board";
        elements.resultView.hidden = name !== "result";
    }

    function render(force = false) {
        const nextFingerprint = fingerprint(state);
        if (!force && nextFingerprint === renderedFingerprint) return;
        renderedFingerprint = nextFingerprint;
        elements.status.textContent = STATUS_LABELS[state.status] || "Partie";

        if (state.status === "EN_ATTENTE") {
            setView("waiting");
            renderWaiting();
        } else if (state.status === "TERMINEE") {
            setView("result");
            renderResult();
        } else {
            setView("board");
            renderBoard();
        }
    }

    function renderWaiting() {
        const players = state.players || [];
        elements.waitingCount.textContent = String(players.length);
        elements.inviteUrl.textContent = window.location.href;
        elements.waitingPlayers.replaceChildren();

        for (let index = 0; index < state.max_players; index += 1) {
            const player = players[index];
            const item = makeElement("li", "mm-waiting-player");
            if (player) {
                item.append(makeAvatar(player), makeElement("strong", "", player.username));
            } else {
                const avatar = makeElement("span", "mm-avatar", "+");
                avatar.setAttribute("aria-hidden", "true");
                item.append(avatar, makeElement("span", "", "Place libre"));
            }
            elements.waitingPlayers.appendChild(item);
        }

        elements.startGame.hidden = !state.is_host;
        elements.startGame.disabled = !state.can_start || phase !== "idle";
        if (state.is_host) {
            elements.startHint.textContent = players.length < state.min_players
                ? "Encore un joueur pour commencer."
                : `${players.length} joueurs prêts.`;
        } else {
            elements.startHint.textContent = "L'hôte lancera la partie.";
        }
    }

    function renderBoard() {
        renderTurn();
        renderPlayers();
        renderDrawZone();
        renderPairs();
        renderHistory();
        renderHand();
    }

    function renderTurn() {
        const current = state.current_turn;
        if (state.can_draw) {
            elements.turnKicker.textContent = "À toi de jouer";
            elements.turnTitle.textContent = "Choisis une carte à l'aveugle";
            elements.turnHelp.textContent = `Pioche dans la main de ${state.draw_source?.player?.username || "ton voisin"}.`;
        } else if (state.me?.rank) {
            elements.turnKicker.textContent = "Main vidée";
            elements.turnTitle.textContent = `Tu es classé·e n°${state.me.rank}`;
            elements.turnHelp.textContent = "Tu peux suivre la fin de la partie en direct.";
        } else {
            elements.turnKicker.textContent = "Tour en cours";
            elements.turnTitle.textContent = `${current?.username || "Un joueur"} observe les cartes`;
            elements.turnHelp.textContent = "Les mains vides sont automatiquement sautées.";
        }
        const directionIcon = elements.direction.querySelector("b");
        if (directionIcon) directionIcon.style.transform = state.direction === -1 ? "scaleX(-1)" : "none";
    }

    function renderPlayers() {
        elements.players.replaceChildren();
        for (const player of state.players || []) {
            const item = makeElement("li", "mm-player-chip");
            item.classList.toggle("is-current", sameId(player.id, state.current_turn?.id));
            item.classList.toggle("is-ranked", Boolean(player.rank));
            const copy = makeElement("span");
            const label = `${player.username}${player.is_me ? " · toi" : ""}`;
            let detail = plural(player.hand_count, "carte");
            if (player.rank) detail = player.is_loser ? "Métamorph · dernier" : `Classé·e n°${player.rank}`;
            copy.append(makeElement("strong", "", label), makeElement("small", "", detail));
            item.append(makeAvatar(player), copy);
            elements.players.appendChild(item);
        }
    }

    function renderDrawZone() {
        const source = state.draw_source;
        elements.drawCards.replaceChildren();
        if (!source) {
            elements.sourceTitle.textContent = "Aucune main disponible";
            elements.sourceCount.textContent = "0 carte";
            elements.drawHint.textContent = "La partie se termine…";
            return;
        }

        elements.sourceTitle.textContent = `Main de ${source.player.username}`;
        elements.sourceCount.textContent = plural(source.card_count, "carte");
        const positions = state.can_draw
            ? source.hidden_cards
            : Array.from({ length: source.card_count }, (_, index) => ({ position: index + 1 }));
        for (const hiddenCard of positions) {
            const button = makeElement("button", "mm-card-back");
            button.type = "button";
            button.disabled = !state.can_draw || phase !== "idle";
            button.style.setProperty("--card-rotation", `${((hiddenCard.position % 5) - 2) * 1.8}deg`);
            button.setAttribute("aria-label", `Piocher la carte ${hiddenCard.position} sur ${source.card_count}`);
            button.appendChild(makeElement("span", "", String(hiddenCard.position)));
            if (state.can_draw) button.addEventListener("click", () => submitDraw(hiddenCard.position));
            elements.drawCards.appendChild(button);
        }
        elements.drawHint.textContent = state.can_draw
            ? "Clique sur un dos. Son contenu restera secret s'il ne forme pas de paire."
            : `${state.current_turn?.username || "Le joueur actif"} choisit une carte…`;
    }

    function renderPairs() {
        const pairs = state.paired_pokemon || [];
        elements.pairCount.textContent = String(pairs.length);
        elements.pairs.replaceChildren();
        for (const pokemon of pairs.slice(-9)) {
            const token = makeElement("span", "mm-pair-token");
            token.title = pokemon.name_fr;
            const image = document.createElement("img");
            image.src = pokemon.sprite_url;
            image.alt = "";
            image.width = 62;
            image.height = 80;
            image.loading = "lazy";
            token.append(image, makeElement("span", "", "×2"));
            elements.pairs.appendChild(token);
        }
        if (!pairs.length) elements.pairs.appendChild(makeElement("small", "mm-zone-hint", "Les paires apparaîtront ici."));
    }

    function renderHistory() {
        const moves = state.moves || [];
        elements.history.replaceChildren();
        elements.historyEmpty.hidden = moves.length > 0;
        for (const move of moves.slice(-6).reverse()) {
            const item = document.createElement("li");
            if (move.pair) {
                const image = document.createElement("img");
                image.src = move.pair.sprite_url;
                image.alt = "";
                image.width = 34;
                image.height = 34;
                const copy = makeElement("span");
                copy.append(makeElement("strong", "", move.actor.username), document.createTextNode(` forme la paire ${move.pair.name_fr}.`));
                item.append(image, copy);
            } else {
                const mark = makeElement("span", "mm-avatar", "?");
                mark.setAttribute("aria-hidden", "true");
                const copy = makeElement("span");
                copy.append(makeElement("strong", "", move.actor.username), document.createTextNode(` pioche chez ${move.source.username}.`));
                item.append(mark, copy);
            }
            elements.history.appendChild(item);
        }
    }

    function renderHand() {
        const hand = state.me?.hand || [];
        elements.handCount.textContent = plural(hand.length, "carte");
        elements.handEmpty.hidden = hand.length > 0;
        elements.myHand.replaceChildren();
        for (const card of hand) {
            const figure = makeElement("figure", "mm-hand-card");
            figure.classList.toggle("is-ditto", card.is_ditto);
            figure.style.setProperty("--hand-rotation", `${((card.position % 7) - 3) * 0.8}deg`);
            const image = document.createElement("img");
            image.src = card.pokemon.sprite_url;
            image.alt = card.pokemon.name_fr;
            image.width = 145;
            image.height = 145;
            image.loading = "lazy";
            image.decoding = "async";
            figure.append(
                image,
                makeElement("span", "mm-hand-card-number", `#${card.pokemon.pokedex_id}`),
                makeElement("figcaption", "mm-hand-card-copy", card.pokemon.name_fr),
            );
            if (card.is_ditto) figure.appendChild(makeElement("span", "mm-hand-card-secret", "À éviter"));
            elements.myHand.appendChild(figure);
        }
    }

    function renderResult() {
        const loser = state.loser;
        const iLost = sameId(loser?.id, state.me?.id);
        elements.resultTitle.textContent = iLost ? "Métamorph t'a trouvé·e" : "Tu as évité Métamorph !";
        elements.resultCopy.textContent = loser
            ? `${loser.username} termine avec la carte mystère. Toutes les autres mains sont victorieuses.`
            : "Toutes les cartes ont trouvé leur place.";
        elements.standings.replaceChildren();
        for (const player of state.standings || []) {
            const item = makeElement("li", "mm-standing");
            item.classList.toggle("is-loser", player.is_loser);
            const label = `${player.username}${player.is_me ? " · toi" : ""}`;
            item.append(
                makeElement("b", "", String(player.rank)),
                makeElement("span", "", label),
                makeElement("small", "", player.is_loser ? "Métamorph" : "Victoire"),
            );
            elements.standings.appendChild(item);
        }
    }

    async function postMutation(url, payload) {
        if (phase !== "idle") return null;
        pollController?.abort();
        setBusy(true);
        render(true);
        try {
            const response = await fetch(url, {
                method: "POST",
                headers: {
                    Accept: "application/json",
                    "Content-Type": "application/json",
                    "X-CSRFToken": csrfToken,
                },
                credentials: "same-origin",
                body: JSON.stringify({ ...payload, expected_turn_revision: state.turn_revision }),
            });
            const data = await response.json().catch(() => ({}));
            if (!response.ok) {
                if (data.state) {
                    state = data.state;
                    renderedFingerprint = null;
                }
                throw new Error(data.error || "Action impossible pour le moment.");
            }
            state = data;
            renderedFingerprint = null;
            return data;
        } catch (error) {
            showFeedback(error.message || "La connexion a échoué.");
            return null;
        } finally {
            setBusy(false);
            render(true);
            setSync("ready", "Synchronisé");
        }
    }

    async function submitDraw(position) {
        const previousRevision = state.turn_revision;
        const next = await postMutation(root.dataset.drawUrl, { card_position: position });
        if (next && next.turn_revision !== previousRevision) {
            const move = next.moves?.at(-1);
            announce(move?.formed_pair ? `Paire ${move.pair.name_fr} formée.` : "Carte ajoutée à ta main.");
        }
    }

    async function poll() {
        if (phase !== "idle" || document.hidden) return;
        pollController?.abort();
        pollController = new AbortController();
        try {
            const response = await fetch(root.dataset.stateUrl, {
                headers: { Accept: "application/json" },
                credentials: "same-origin",
                cache: "no-store",
                signal: pollController.signal,
            });
            if (!response.ok) throw new Error();
            const nextState = await response.json();
            const changed = fingerprint(nextState) !== fingerprint(state);
            state = nextState;
            if (changed) render();
            setSync("ready", "Synchronisé");
        } catch (error) {
            if (error.name !== "AbortError") setSync("offline", "Reconnexion…");
        }
    }

    elements.startGame?.addEventListener("click", async () => {
        const next = await postMutation(root.dataset.startUrl, {});
        if (next) announce("La distribution est terminée. La partie commence.");
    });

    elements.copyLink?.addEventListener("click", async () => {
        try {
            await navigator.clipboard.writeText(window.location.href);
            elements.copyLink.textContent = "Lien copié";
            window.setTimeout(() => { elements.copyLink.textContent = "Copier le lien"; }, 1800);
        } catch (_) {
            showFeedback("Copie le lien directement depuis la barre d'adresse.");
        }
    });

    render(true);
    setSync("ready", "Synchronisé");
    window.setInterval(poll, 1600);
    document.addEventListener("visibilitychange", poll);
})();
