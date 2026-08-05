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

    const t = (french, english) => (state.language === "en" ? english : french);
    const pokemonName = (pokemon) => (
        pokemon?.name
        || (state.language === "en" ? pokemon?.name_en : pokemon?.name_fr)
        || pokemon?.name_fr
        || pokemon?.name_en
        || "Pokémon"
    );

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
        addBot: root.querySelector("[data-add-bot]"),
        startHint: root.querySelector("[data-start-hint]"),
        turnKicker: root.querySelector("[data-turn-kicker]"),
        turnTitle: root.querySelector("[data-turn-title]"),
        turnHelp: root.querySelector("[data-turn-help]"),
        direction: root.querySelector("[data-direction]"),
        players: root.querySelector("[data-players]"),
        drawZone: root.querySelector(".mm-draw-zone"),
        sourceTitle: root.querySelector("[data-source-title]"),
        sourceCount: root.querySelector("[data-source-count]"),
        drawCards: root.querySelector("[data-draw-cards]"),
        drawHint: root.querySelector("[data-draw-hint]"),
        pairCount: root.querySelector("[data-pair-count]"),
        pairsPanel: root.querySelector(".mm-pairs"),
        pairs: root.querySelector("[data-pairs]"),
        history: root.querySelector("[data-history]"),
        historyEmpty: root.querySelector("[data-history-empty]"),
        handCount: root.querySelector("[data-hand-count]"),
        handPanel: root.querySelector(".mm-my-hand"),
        myHand: root.querySelector("[data-my-hand]"),
        handEmpty: root.querySelector("[data-hand-empty]"),
        resultTitle: root.querySelector("[data-result-title]"),
        resultCopy: root.querySelector("[data-result-copy]"),
        standings: root.querySelector("[data-standings]"),
    };

    const STATUS_LABELS = {
        EN_ATTENTE: t("En attente", "Waiting"),
        EN_COURS: t("Partie en cours", "Game in progress"),
        TERMINEE: t("Terminée", "Finished"),
    };
    const csrfToken = root.querySelector('[name="csrfmiddlewaretoken"]')?.value || readCookie("csrftoken");
    const reducedMotion = window.matchMedia("(prefers-reduced-motion: reduce)");
    let phase = "idle";
    let pollController = null;
    let feedbackTimer = null;
    let botTurnTimer = null;
    let renderedFingerprint = null;
    let visualSnapshot = null;
    const animationTimers = new Map();

    function readCookie(name) {
        const prefix = `${name}=`;
        return document.cookie.split(";").map((part) => part.trim()).find((part) => part.startsWith(prefix))?.slice(prefix.length) || "";
    }

    function sameId(left, right) {
        return left !== null && left !== undefined && right !== null && right !== undefined && String(left) === String(right);
    }

    function plural(count, frenchSingular, frenchPlural, englishSingular, englishPlural) {
        const singular = state.language === "en" ? englishSingular : frenchSingular;
        const pluralForm = state.language === "en" ? englishPlural : frenchPlural;
        return `${count} ${count === 1 ? singular : pluralForm}`;
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

    function makeVisualSnapshot(candidate) {
        return {
            status: candidate.status,
            currentTurn: candidate.current_turn?.id || null,
            moveCount: (candidate.moves || []).length,
            pairCount: (candidate.paired_pokemon || []).length,
        };
    }

    function restartAnimation(element, className, duration) {
        if (!element || reducedMotion.matches) return;
        const previousTimer = animationTimers.get(className);
        if (previousTimer) window.clearTimeout(previousTimer);
        element.classList.remove(className);
        void element.offsetWidth;
        element.classList.add(className);
        animationTimers.set(className, window.setTimeout(() => {
            element.classList.remove(className);
            animationTimers.delete(className);
        }, duration));
    }

    function animateStateChange(previous, current) {
        if (current.status !== "EN_COURS") return;
        if (!previous || previous.status !== "EN_COURS") {
            restartAnimation(elements.boardView, "is-entering", 520);
        }
        if (previous && previous.currentTurn !== current.currentTurn) {
            restartAnimation(elements.players, "is-turn-transition", 720);
        }
        if (previous && current.moveCount > previous.moveCount) {
            restartAnimation(elements.drawZone, "is-draw-transition", 720);
        }
        if (previous && current.pairCount > previous.pairCount) {
            restartAnimation(elements.pairsPanel, "is-pair-transition", 820);
            restartAnimation(elements.handPanel, "is-pair-transition", 820);
        }
    }

    function syncViewportMode() {
        const isActive = state.status === "EN_COURS";
        root.dataset.gameStatus = state.status || "";
        document.documentElement.classList.toggle("metamorph-document--active", isActive);
        document.body.classList.toggle("metamorph-game-shell--active", isActive);
    }

    function makeElement(tag, className, text) {
        const element = document.createElement(tag);
        if (className) element.className = className;
        if (text !== undefined) element.textContent = text;
        return element;
    }

    function makeAvatar(player) {
        const avatar = makeElement(
            "span",
            "mm-avatar",
            (player?.username || "?").slice(0, 1).toLocaleUpperCase(state.language === "en" ? "en-GB" : "fr-FR"),
        );
        avatar.setAttribute("aria-hidden", "true");
        return avatar;
    }

    function makeTypeIcon(type) {
        if (!type?.icon_url) return null;
        const icon = document.createElement("img");
        icon.className = "mm-type-icon";
        icon.src = type.icon_url;
        icon.alt = `${t("Type", "Type")} ${type.name || type.name_fr || type.name_en || type.slug}`;
        icon.title = icon.alt;
        icon.width = 22;
        icon.height = 22;
        icon.loading = "lazy";
        icon.decoding = "async";
        return icon;
    }

    function setSync(mode, label) {
        elements.sync?.classList.toggle("is-syncing", mode === "syncing");
        elements.sync?.classList.toggle("is-offline", mode === "offline");
        if (elements.syncLabel) elements.syncLabel.textContent = label;
    }

    function setBusy(busy) {
        phase = busy ? "mutation" : "idle";
        root.setAttribute("aria-busy", String(busy));
        if (busy) setSync("syncing", t("Envoi…", "Sending…"));
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
        syncViewportMode();
        const nextFingerprint = fingerprint(state);
        if (!force && nextFingerprint === renderedFingerprint) return;
        renderedFingerprint = nextFingerprint;
        const nextVisualSnapshot = makeVisualSnapshot(state);
        elements.status.textContent = STATUS_LABELS[state.status] || t("Partie", "Game");

        if (state.status === "EN_ATTENTE") {
            window.clearTimeout(botTurnTimer);
            setView("waiting");
            renderWaiting();
        } else if (state.status === "TERMINEE") {
            window.clearTimeout(botTurnTimer);
            setView("result");
            renderResult();
        } else {
            setView("board");
            renderBoard();
            scheduleBotTurn();
        }
        animateStateChange(visualSnapshot, nextVisualSnapshot);
        visualSnapshot = nextVisualSnapshot;
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
                const copy = makeElement("span");
                copy.append(
                    makeElement("strong", "", player.username),
                    makeElement(
                        "small",
                        "",
                        player.is_bot ? t("Joueur IA · prêt", "AI player · ready") : t("Prêt à jouer", "Ready to play"),
                    ),
                );
                item.append(makeAvatar(player), copy);
                if (state.is_host && player.is_bot) {
                    const remove = makeElement("button", "btn-icon", "×");
                    remove.type = "button";
                    remove.setAttribute("aria-label", `${t("Retirer", "Remove")} ${player.username}`);
                    remove.disabled = phase !== "idle";
                    remove.addEventListener("click", () => submitRemoveBot(player.id));
                    item.appendChild(remove);
                }
            } else {
                const avatar = makeElement("span", "mm-avatar", "+");
                avatar.setAttribute("aria-hidden", "true");
                item.append(avatar, makeElement("span", "", t("Place libre", "Open seat")));
            }
            elements.waitingPlayers.appendChild(item);
        }

        elements.startGame.hidden = !state.is_host;
        elements.startGame.disabled = !state.can_start || phase !== "idle";
        elements.addBot.hidden = !state.is_host;
        elements.addBot.disabled = !state.can_add_bot || phase !== "idle";
        if (state.is_host) {
            elements.startHint.textContent = players.length < state.min_players
                ? t("Encore un joueur pour commencer.", "One more player is needed to start.")
                : state.language === "en"
                  ? `${players.length} players ready.`
                  : `${players.length} joueurs prêts.`;
        } else {
            elements.startHint.textContent = t("L'hôte lancera la partie.", "The host will start the game.");
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
            elements.turnKicker.textContent = t("À toi de jouer", "Your turn");
            elements.turnTitle.textContent = t("Choisis une carte à l'aveugle", "Choose a card blind");
            const neighbor = state.draw_source?.player?.username || t("ton voisin", "your neighbor");
            elements.turnHelp.textContent = state.language === "en"
                ? `Draw from ${neighbor}’s hand.`
                : `Pioche dans la main de ${neighbor}.`;
        } else if (state.me?.rank) {
            elements.turnKicker.textContent = t("Main vidée", "Empty hand");
            elements.turnTitle.textContent = state.language === "en"
                ? `You placed #${state.me.rank}`
                : `Tu es classé·e n°${state.me.rank}`;
            elements.turnHelp.textContent = t(
                "Tu peux suivre la fin de la partie en direct.",
                "You can watch the rest of the game live.",
            );
        } else {
            elements.turnKicker.textContent = t("Tour en cours", "Current turn");
            const currentName = current?.username || t("Un joueur", "A player");
            elements.turnTitle.textContent = state.language === "en"
                ? `${currentName} is studying the cards`
                : `${currentName} observe les cartes`;
            elements.turnHelp.textContent = t(
                "Les mains vides sont automatiquement sautées.",
                "Players with empty hands are skipped automatically.",
            );
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
            const label = `${player.username}${player.is_me ? t(" · toi", " · you") : ""}`;
            let detail = plural(player.hand_count, "carte", "cartes", "card", "cards");
            if (player.rank) {
                detail = player.is_loser
                    ? t("Métamorph · dernier", "Ditto · last")
                    : state.language === "en"
                      ? `Placed #${player.rank}`
                      : `Classé·e n°${player.rank}`;
            }
            copy.append(makeElement("strong", "", label), makeElement("small", "", detail));
            item.append(makeAvatar(player), copy);
            elements.players.appendChild(item);
        }
    }

    function renderDrawZone() {
        const source = state.draw_source;
        elements.drawCards.replaceChildren();
        if (!source) {
            elements.sourceTitle.textContent = t("Aucune main disponible", "No hand available");
            elements.sourceCount.textContent = plural(0, "carte", "cartes", "card", "cards");
            elements.drawHint.textContent = t("La partie se termine…", "The game is ending…");
            return;
        }

        elements.sourceTitle.textContent = state.language === "en"
            ? `${source.player.username}’s hand`
            : `Main de ${source.player.username}`;
        elements.sourceCount.textContent = plural(source.card_count, "carte", "cartes", "card", "cards");
        const positions = state.can_draw
            ? source.hidden_cards
            : Array.from({ length: source.card_count }, (_, index) => ({ position: index + 1 }));
        for (const hiddenCard of positions) {
            const button = makeElement("button", "mm-card-back");
            button.type = "button";
            button.disabled = !state.can_draw || phase !== "idle";
            button.style.setProperty("--card-rotation", `${((hiddenCard.position % 5) - 2) * 1.8}deg`);
            button.setAttribute(
                "aria-label",
                state.language === "en"
                    ? `Draw card ${hiddenCard.position} of ${source.card_count}`
                    : `Piocher la carte ${hiddenCard.position} sur ${source.card_count}`,
            );
            button.appendChild(makeElement("span", "", String(hiddenCard.position)));
            if (state.can_draw) button.addEventListener("click", () => submitDraw(hiddenCard.position));
            elements.drawCards.appendChild(button);
        }
        elements.drawHint.textContent = state.can_draw
            ? t(
                "Clique sur un dos. Son contenu restera secret s'il ne forme pas de paire.",
                "Select a card back. Its identity stays hidden unless it makes a pair.",
            )
            : state.language === "en"
              ? `${state.current_turn?.username || "The active player"} is choosing a card…`
              : `${state.current_turn?.username || "Le joueur actif"} choisit une carte…`;
    }

    function renderPairs() {
        const pairs = state.paired_pokemon || [];
        elements.pairCount.textContent = String(pairs.length);
        elements.pairs.replaceChildren();
        for (const pokemon of pairs.slice(-9)) {
            const token = makeElement("span", "mm-pair-token");
            token.title = pokemonName(pokemon);
            const image = document.createElement("img");
            image.src = pokemon.sprite_url;
            image.alt = "";
            image.width = 62;
            image.height = 80;
            image.loading = "lazy";
            token.append(image, makeElement("span", "", "×2"));
            const typeIcon = makeTypeIcon(pokemon.primary_type);
            if (typeIcon) {
                typeIcon.classList.add("mm-pair-type-icon");
                token.appendChild(typeIcon);
            }
            elements.pairs.appendChild(token);
        }
        if (!pairs.length) {
            elements.pairs.appendChild(
                makeElement("small", "mm-zone-hint", t("Les paires apparaîtront ici.", "Pairs will appear here.")),
            );
        }
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
                copy.append(
                    makeElement("strong", "", move.actor.username),
                    document.createTextNode(
                        state.language === "en"
                            ? ` makes the ${pokemonName(move.pair)} pair.`
                            : ` forme la paire ${pokemonName(move.pair)}.`,
                    ),
                );
                item.append(image, copy);
            } else {
                const mark = makeElement("span", "mm-avatar", "?");
                mark.setAttribute("aria-hidden", "true");
                const copy = makeElement("span");
                copy.append(
                    makeElement("strong", "", move.actor.username),
                    document.createTextNode(
                        state.language === "en"
                            ? ` draws from ${move.source.username}.`
                            : ` pioche chez ${move.source.username}.`,
                    ),
                );
                item.append(mark, copy);
            }
            elements.history.appendChild(item);
        }
    }

    function renderHand() {
        const hand = state.me?.hand || [];
        elements.handCount.textContent = plural(hand.length, "carte", "cartes", "card", "cards");
        elements.handEmpty.hidden = hand.length > 0;
        elements.myHand.replaceChildren();
        for (const card of hand) {
            const figure = makeElement("figure", "mm-hand-card");
            figure.classList.toggle("is-ditto", card.is_ditto);
            figure.style.setProperty("--hand-rotation", `${((card.position % 7) - 3) * 0.8}deg`);
            const image = document.createElement("img");
            image.src = card.pokemon.sprite_url;
            image.alt = pokemonName(card.pokemon);
            image.width = 145;
            image.height = 145;
            image.loading = "lazy";
            image.decoding = "async";
            figure.append(
                image,
                makeElement("span", "mm-hand-card-number", `#${card.pokemon.pokedex_id}`),
                makeElement("figcaption", "mm-hand-card-copy", pokemonName(card.pokemon)),
            );
            const typeIcons = makeElement("span", "mm-card-types");
            [card.pokemon.primary_type, card.pokemon.secondary_type].forEach((type) => {
                const icon = makeTypeIcon(type);
                if (icon) typeIcons.appendChild(icon);
            });
            if (typeIcons.childElementCount) figure.appendChild(typeIcons);
            if (card.is_ditto) {
                figure.appendChild(makeElement("span", "mm-hand-card-secret", t("À éviter", "Avoid")));
            }
            elements.myHand.appendChild(figure);
        }
    }

    function renderResult() {
        const loser = state.loser;
        const iLost = sameId(loser?.id, state.me?.id);
        elements.resultTitle.textContent = iLost
            ? t("Métamorph t'a trouvé·e", "Ditto found you")
            : t("Tu as évité Métamorph !", "You avoided Ditto!");
        elements.resultCopy.textContent = loser
            ? state.language === "en"
                ? `${loser.username} ends with the mystery card. Every other hand wins.`
                : `${loser.username} termine avec la carte mystère. Toutes les autres mains sont victorieuses.`
            : t("Toutes les cartes ont trouvé leur place.", "Every card found its place.");
        elements.standings.replaceChildren();
        for (const player of state.standings || []) {
            const item = makeElement("li", "mm-standing");
            item.classList.toggle("is-loser", player.is_loser);
            const label = `${player.username}${player.is_me ? t(" · toi", " · you") : ""}`;
            item.append(
                makeElement("b", "", String(player.rank)),
                makeElement("span", "", label),
                makeElement("small", "", player.is_loser ? t("Métamorph", "Ditto") : t("Victoire", "Victory")),
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
                throw new Error(data.error || t("Action impossible pour le moment.", "That action is not available right now."));
            }
            state = data;
            renderedFingerprint = null;
            return data;
        } catch (error) {
            showFeedback(error.message || t("La connexion a échoué.", "The connection failed."));
            return null;
        } finally {
            setBusy(false);
            render(true);
            setSync("ready", t("Synchronisé", "Synced"));
        }
    }

    async function submitDraw(position) {
        const previousRevision = state.turn_revision;
        const next = await postMutation(root.dataset.drawUrl, { card_position: position });
        if (next && next.turn_revision !== previousRevision) {
            const move = next.moves?.at(-1);
            announce(
                move?.formed_pair
                    ? state.language === "en"
                        ? `${pokemonName(move.pair)} pair made.`
                        : `Paire ${pokemonName(move.pair)} formée.`
                    : t("Carte ajoutée à ta main.", "Card added to your hand."),
            );
        }
    }

    async function submitRemoveBot(botId) {
        const url = root.dataset.removeBotUrlTemplate.replace(/\/0\/remove\/$/, `/${botId}/remove/`);
        await postMutation(url, {});
    }

    function scheduleBotTurn() {
        window.clearTimeout(botTurnTimer);
        botTurnTimer = null;
        if (
            phase !== "idle"
            || state.status !== "EN_COURS"
            || !state.current_turn?.is_bot
            || !root.dataset.botTurnUrl
        ) return;
        botTurnTimer = window.setTimeout(async () => {
            botTurnTimer = null;
            await postMutation(root.dataset.botTurnUrl, {});
        }, reducedMotion.matches ? 350 : 1100);
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
            setSync("ready", t("Synchronisé", "Synced"));
        } catch (error) {
            if (error.name !== "AbortError") setSync("offline", t("Reconnexion…", "Reconnecting…"));
        }
    }

    elements.startGame?.addEventListener("click", async () => {
        const next = await postMutation(root.dataset.startUrl, {});
        if (next) announce(t("La distribution est terminée. La partie commence.", "The deal is complete. The game begins."));
    });

    elements.addBot?.addEventListener("click", async () => {
        await postMutation(root.dataset.addBotUrl, {});
    });

    elements.copyLink?.addEventListener("click", async () => {
        try {
            await navigator.clipboard.writeText(window.location.href);
            elements.copyLink.textContent = t("Lien copié", "Link copied");
            window.setTimeout(() => { elements.copyLink.textContent = t("Copier le lien", "Copy link"); }, 1800);
        } catch (_) {
            showFeedback(t("Copie le lien directement depuis la barre d'adresse.", "Copy the link directly from the address bar."));
        }
    });

    render(true);
    setSync("ready", t("Synchronisé", "Synced"));
    window.setInterval(poll, 1600);
    document.addEventListener("visibilitychange", poll);
})();
