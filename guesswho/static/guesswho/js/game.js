(() => {
    "use strict";

    const game = document.getElementById("guesswho-game");
    const stateNode = document.getElementById("guesswho-initial-state");
    if (!game || !stateNode) return;
    const documentLanguage = document.documentElement.lang.startsWith("en") ? "en" : "fr";

    let state;
    try {
        state = JSON.parse(stateNode.textContent);
    } catch (_) {
        game.setAttribute("aria-busy", "false");
        const fallback = document.createElement("p");
        fallback.className = "gw-feedback";
        fallback.setAttribute("role", "alert");
        fallback.textContent = documentLanguage === "en"
            ? "The board could not be loaded. Refresh the page to try again."
            : "Le plateau n’a pas pu être chargé. Recharge la page pour réessayer.";
        game.appendChild(fallback);
        return;
    }

    const t = (french, english) => (state.language === "en" ? english : french);
    const pokemonName = (card) => card?.name || (state.language === "en" ? card?.name_en : card?.name_fr) || card?.name_fr || card?.name_en || "Pokémon";

    const elements = {
        status: document.querySelector("[data-game-status]"),
        sync: document.querySelector("[data-sync-state]"),
        syncLabel: document.querySelector("[data-sync-state] span"),
        feedback: game.querySelector("[data-feedback]"),
        announcer: game.querySelector("[data-announcer]"),
        waitingView: game.querySelector('[data-view="waiting"]'),
        boardView: game.querySelector('[data-view="board"]'),
        resultView: game.querySelector('[data-view="result"]'),
        playerCount: game.querySelector("[data-player-count]"),
        waitingPlayers: game.querySelector("[data-waiting-players]"),
        inviteUrl: game.querySelector("[data-invite-url]"),
        roster: game.querySelector("[data-roster]"),
        boardEyebrow: game.querySelector("[data-board-eyebrow]"),
        boardTitle: game.querySelector("[data-board-title]"),
        boardHelp: game.querySelector("[data-board-help]"),
        candidateCount: game.querySelector("[data-candidate-count]"),
        resetCandidates: game.querySelector("[data-reset-candidates]"),
        guessMode: game.querySelector("[data-guess-mode]"),
        players: game.querySelector("[data-players]"),
        turnBadge: game.querySelector("[data-turn-badge]"),
        history: game.querySelector("[data-history]"),
        historyEmpty: game.querySelector("[data-history-empty]"),
        historyCount: game.querySelector("[data-history-count]"),
        actionPanel: game.querySelector("[data-action-panel]"),
        questionForm: game.querySelector("[data-question-form]"),
        questionInput: game.querySelector('[name="question"]'),
        questionSubmit: game.querySelector("[data-question-form] button[type='submit']"),
        actionHint: game.querySelector("[data-action-hint]"),
        pendingQuestion: game.querySelector("[data-pending-question]"),
        pendingQuestionText: game.querySelector("[data-pending-question-text]"),
        resultTitle: game.querySelector("[data-result-title]"),
        resultCopy: game.querySelector("[data-result-copy]"),
        resultPlayers: game.querySelector("[data-result-players]"),
        dialog: document.querySelector("[data-confirm-dialog]"),
        dialogVisual: document.querySelector("[data-dialog-visual]"),
        dialogEyebrow: document.querySelector("[data-dialog-eyebrow]"),
        dialogTitle: document.querySelector("[data-dialog-title]"),
        dialogCopy: document.querySelector("[data-dialog-copy]"),
        dialogConfirm: document.querySelector("[data-dialog-confirm]"),
    };

    const STATUS_LABELS = {
        EN_ATTENTE: t("En attente", "Waiting"),
        CHOIX: t("Choix secret", "Secret choice"),
        EN_COURS: t("Partie en cours", "Game in progress"),
        TERMINEE: t("Terminée", "Finished"),
    };
    const TCG_TYPE_NAMES = {
        grass: t("Plante", "Grass"),
        fire: t("Feu", "Fire"),
        water: t("Eau", "Water"),
        lightning: t("Électrique", "Lightning"),
        psychic: t("Psy", "Psychic"),
        fighting: t("Combat", "Fighting"),
        darkness: t("Obscurité", "Darkness"),
        metal: t("Métal", "Metal"),
        dragon: "Dragon",
        colorless: t("Incolore", "Colorless"),
    };
    const RAW_TO_TCG = {
        grass: "grass",
        bug: "grass",
        fire: "fire",
        water: "water",
        ice: "water",
        electric: "lightning",
        lightning: "lightning",
        psychic: "psychic",
        ghost: "psychic",
        fairy: "psychic",
        fighting: "fighting",
        ground: "fighting",
        rock: "fighting",
        dark: "darkness",
        darkness: "darkness",
        poison: "darkness",
        steel: "metal",
        metal: "metal",
        dragon: "dragon",
        normal: "colorless",
        flying: "colorless",
        colorless: "colorless",
    };

    const reducedMotion = window.matchMedia("(prefers-reduced-motion: reduce)");
    const precisePointer = window.matchMedia("(hover: hover) and (pointer: fine)");
    const timeFormatter = new Intl.DateTimeFormat(state.language === "en" ? "en-GB" : "fr-FR", { hour: "2-digit", minute: "2-digit" });
    const csrfToken = game.querySelector('[name="csrfmiddlewaretoken"]')?.value || readCookie("csrftoken");

    let phase = "idle";
    let guessMode = false;
    let pendingConfirmation = null;
    let pollTimer = null;
    let pollController = null;
    let feedbackTimer = null;
    let lastFocusedCardId = null;
    let renderedHistoryFingerprint = null;
    let renderedView = null;
    let focusFrame = null;

    function readCookie(name) {
        const prefix = `${name}=`;
        return document.cookie
            .split(";")
            .map((part) => part.trim())
            .find((part) => part.startsWith(prefix))
            ?.slice(prefix.length) || "";
    }

    function sameId(left, right) {
        return left !== null && left !== undefined && right !== null && right !== undefined && String(left) === String(right);
    }

    function me() {
        if (state.me) return state.me;
        const configuredId = game.dataset.playerId;
        return state.players?.find((player) => sameId(player.id, configuredId)) || null;
    }

    function tcgType(card) {
        return RAW_TO_TCG[card?.tcg_type] || RAW_TO_TCG[card?.primary_type] || "colorless";
    }

    function typeName(card) {
        return TCG_TYPE_NAMES[tcgType(card)] || t("Incolore", "Colorless");
    }

    function histories() {
        const source = state.history || state.messages || [];
        return Array.isArray(source) ? source : [];
    }

    function stateFingerprint(candidate) {
        return JSON.stringify({
            status: candidate.status,
            turnRevision: candidate.turn_revision,
            winner: candidate.winner?.id || null,
            currentTurn: candidate.current_turn?.id || null,
            pending: candidate.pending_question?.id || null,
            historyCount: (candidate.history || candidate.messages || []).length,
            eliminatedCandidates: (candidate.roster || [])
                .filter((card) => card.is_eliminated)
                .map((card) => card.id),
        });
    }

    function setSync(mode, label) {
        if (!elements.sync) return;
        elements.sync.classList.toggle("is-syncing", mode === "syncing");
        elements.sync.classList.toggle("is-offline", mode === "offline");
        if (elements.syncLabel) elements.syncLabel.textContent = label;
    }

    function announce(message) {
        if (!elements.announcer) return;
        elements.announcer.textContent = "";
        window.requestAnimationFrame(() => {
            elements.announcer.textContent = message;
        });
    }

    function showFeedback(message) {
        window.clearTimeout(feedbackTimer);
        elements.feedback.textContent = message;
        elements.feedback.hidden = false;
        feedbackTimer = window.setTimeout(() => {
            elements.feedback.hidden = true;
        }, 6000);
    }

    function setBusy(isBusy) {
        game.setAttribute("aria-busy", String(isBusy));
        if (isBusy) setSync("syncing", t("Envoi…", "Sending…"));
    }

    function setView(activeView) {
        const previousView = renderedView;
        elements.waitingView.hidden = activeView !== "waiting";
        elements.boardView.hidden = activeView !== "board";
        elements.resultView.hidden = activeView !== "result";
        if (activeView !== previousView) {
            [elements.waitingView, elements.boardView, elements.resultView].forEach((view) => {
                view.classList.remove("is-entering");
            });
            const activeElement = {
                waiting: elements.waitingView,
                board: elements.boardView,
                result: elements.resultView,
            }[activeView];
            if (activeElement && !reducedMotion.matches) {
                void activeElement.offsetWidth;
                activeElement.classList.add("is-entering");
            }
        }
        renderedView = activeView;
        return previousView;
    }

    function syncViewportMode() {
        const isActive = state.status === "CHOIX" || state.status === "EN_COURS";
        game.dataset.gamePhase = state.status || "";
        document.documentElement.classList.toggle("guesswho-document--active", isActive);
        document.body.classList.toggle("guesswho-game-shell--active", isActive);
    }

    function focusAfterRender(preferred, fallback = null) {
        if (focusFrame !== null) window.cancelAnimationFrame(focusFrame);
        focusFrame = window.requestAnimationFrame(() => {
            focusFrame = null;
            const target = [preferred, fallback].find((candidate) => (
                candidate
                && candidate.isConnected
                && !candidate.disabled
                && !candidate.closest("[hidden]")
            ));
            target?.focus({ preventScroll: true });
        });
    }

    function render() {
        syncViewportMode();
        elements.status.textContent = STATUS_LABELS[state.status] || t("Partie", "Game");

        if (state.status === "EN_ATTENTE") {
            guessMode = false;
            setView("waiting");
            renderWaiting();
            return;
        }

        if (state.status === "TERMINEE") {
            guessMode = false;
            const previousView = setView("result");
            renderResult();
            lastFocusedCardId = null;
            if (previousView !== "result") focusAfterRender(elements.resultTitle);
            return;
        }

        setView("board");
        renderBoard();
    }

    function makeAvatar(player, isOpponent = false) {
        const avatar = document.createElement("span");
        avatar.className = `gw-player-avatar${isOpponent ? " gw-player-avatar--opponent" : ""}`;
        avatar.setAttribute("aria-hidden", "true");
        avatar.textContent = (player?.username || "?").slice(0, 1).toLocaleUpperCase(state.language === "en" ? "en-GB" : "fr-FR");
        return avatar;
    }

    function renderWaiting() {
        const players = state.players || [];
        elements.playerCount.textContent = String(players.length);
        elements.inviteUrl.textContent = window.location.href;
        elements.waitingPlayers.replaceChildren();

        for (let index = 0; index < 2; index += 1) {
            const player = players[index];
            const seat = document.createElement("div");
            seat.className = `gw-waiting-player${player ? "" : " is-empty"}`;
            if (player) {
                seat.appendChild(makeAvatar(player, index === 1));
                const copy = document.createElement("span");
                const name = document.createElement("strong");
                name.textContent = player.username;
                const status = document.createElement("small");
                status.textContent = sameId(player.id, me()?.id) ? t("Toi · prêt", "You · ready") : t("Adversaire · prêt", "Opponent · ready");
                copy.append(name, status);
                seat.appendChild(copy);
            } else {
                const avatar = document.createElement("span");
                avatar.className = "gw-player-avatar";
                avatar.setAttribute("aria-hidden", "true");
                avatar.textContent = "+";
                const copy = document.createElement("span");
                const name = document.createElement("strong");
                name.textContent = t("Place libre", "Open seat");
                const status = document.createElement("small");
                status.textContent = t("En attente…", "Waiting…");
                copy.append(name, status);
                seat.append(avatar, copy);
            }
            elements.waitingPlayers.appendChild(seat);
        }
    }

    function renderBoard() {
        const currentMe = me();
        const choosing = state.status === "CHOIX";
        const hasChosen = Boolean(currentMe?.has_chosen || currentMe?.target);
        const eliminatedCount = (state.roster || []).filter((card) => card.is_eliminated).length;
        const standingCount = Math.max(0, (state.roster || []).length - eliminatedCount);

        if (choosing) guessMode = false;
        elements.guessMode.hidden = choosing;
        elements.resetCandidates.hidden = choosing;
        elements.guessMode.disabled = !state.is_my_turn || Boolean(state.pending_question);
        elements.guessMode.setAttribute("aria-pressed", String(guessMode));
        elements.resetCandidates.disabled = eliminatedCount === 0;
        elements.candidateCount.textContent = choosing
            ? `${(state.roster || []).length} ${t("Pokémon disponibles", "available Pokémon")}`
            : `${standingCount} ${t("encore debout", "still standing")}`;

        elements.boardHelp.classList.toggle("is-guessing", guessMode);
        if (choosing && !hasChosen) {
            elements.boardEyebrow.textContent = t("Choix confidentiel", "Private choice");
            elements.boardTitle.textContent = t("Choisis ton Pokémon secret", "Choose your secret Pokémon");
            elements.boardHelp.textContent = t("Ton adversaire ne verra pas ce choix. Sélectionne 1 carte pour continuer.", "Your opponent will not see this choice. Select 1 card to continue.");
        } else if (choosing) {
            elements.boardEyebrow.textContent = t("Choix enregistré", "Choice saved");
            elements.boardTitle.textContent = t("Ton Pokémon est bien gardé", "Your Pokémon is safely hidden");
            elements.boardHelp.textContent = t("En attente du choix de ton adversaire…", "Waiting for your opponent’s choice…");
        } else if (guessMode) {
            elements.boardEyebrow.textContent = t("Tentative finale", "Final guess");
            elements.boardTitle.textContent = t("Qui se cache chez l’adversaire ?", "Who is your opponent hiding?");
            elements.boardHelp.textContent = t("Choisis 1 Pokémon. Attention : une erreur donne la victoire à ton adversaire.", "Choose 1 Pokémon. Be careful: a mistake gives your opponent the win.");
        } else {
            elements.boardEyebrow.textContent = t("Ton plateau", "Your board");
            elements.boardTitle.textContent = t("24 suspects. 1 seul Pokémon.", "24 suspects. Only 1 Pokémon.");
            elements.boardHelp.textContent = t("Clique sur une carte pour la rabattre après chaque indice.", "Click a card to fold it down after each clue.");
        }

        renderRoster({ choosing, hasChosen });
        renderPlayers();
        renderHistory();
        renderActions({ choosing, hasChosen });
    }

    function rosterMatches(cards) {
        const currentIds = [...elements.roster.querySelectorAll("[data-card-id]")].map((card) => card.dataset.cardId);
        return currentIds.length === cards.length && currentIds.every((id, index) => id === String(cards[index].id));
    }

    function renderRoster(context) {
        const cards = state.roster || [];
        if (!rosterMatches(cards)) {
            const fragment = document.createDocumentFragment();
            cards.forEach((card) => fragment.appendChild(createCardElement(card)));
            elements.roster.replaceChildren(fragment);
        }

        const ownTargetId = me()?.target?.id;
        cards.forEach((card) => {
            const button = elements.roster.querySelector(`[data-card-id="${CSS.escape(String(card.id))}"]`);
            if (!button) return;
            updateCardElement(button, card, context, ownTargetId);
        });

        if (lastFocusedCardId !== null) {
            const cardToFocus = elements.roster.querySelector(`[data-card-id="${CSS.escape(String(lastFocusedCardId))}"]`);
            lastFocusedCardId = null;
            focusAfterRender(cardToFocus, elements.boardTitle);
        }
    }

    function createCardElement(card) {
        const item = document.createElement("li");
        item.className = "gw-roster-item";

        const button = document.createElement("button");
        button.type = "button";
        button.className = "gw-card";
        button.dataset.cardId = String(card.id);

        const frame = document.createElement("span");
        frame.className = "gw-card-frame";

        const symbol = document.createElement("img");
        symbol.className = "gw-tcg-symbol";
        symbol.alt = "";
        symbol.width = 22;
        symbol.height = 22;
        symbol.loading = "lazy";
        symbol.decoding = "async";
        symbol.draggable = false;
        symbol.setAttribute("aria-hidden", "true");

        const number = document.createElement("span");
        number.className = "gw-card-number";
        number.textContent = `#${card.pokedex_id}`;

        const image = document.createElement("img");
        image.className = "gw-card-image";
        image.src = card.sprite_url;
        image.alt = "";
        image.width = 96;
        image.height = 96;
        image.loading = "lazy";
        image.decoding = "async";
        image.draggable = false;

        const name = document.createElement("span");
        name.className = "gw-card-name";
        name.textContent = pokemonName(card);

        const eliminated = document.createElement("span");
        eliminated.className = "gw-card-eliminated-label";
        eliminated.setAttribute("aria-hidden", "true");
        eliminated.textContent = t("Écarté", "Eliminated");

        const mode = document.createElement("span");
        mode.className = "gw-card-mode-label";
        mode.setAttribute("aria-hidden", "true");
        mode.hidden = true;

        frame.append(symbol, number, image, name);
        button.append(frame, eliminated, mode);
        item.appendChild(button);
        setupCardTilt(button);
        return item;
    }

    function updateCardElement(button, card, context, ownTargetId) {
        const type = tcgType(card);
        button.dataset.tcgType = type;
        const symbol = button.querySelector(".gw-tcg-symbol");
        symbol.dataset.tcgType = type;
        symbol.src = card.type_icon_url;
        symbol.hidden = !card.type_icon_url;
        button.classList.toggle("is-eliminated", Boolean(card.is_eliminated));
        button.classList.toggle("is-choice-target", context.hasChosen && sameId(card.id, ownTargetId));
        button.classList.toggle("is-guess-target", false);
        button.disabled = context.choosing && context.hasChosen;

        const modeLabel = button.querySelector(".gw-card-mode-label");
        const showModeLabel = (!context.choosing && guessMode) || (context.choosing && !context.hasChosen);
        modeLabel.hidden = !showModeLabel;
        modeLabel.textContent = context.choosing ? t("Choisir", "Choose") : t("Proposer", "Guess");

        if (context.choosing && !context.hasChosen) {
            button.setAttribute("aria-label", `${t("Choisir", "Choose")} ${pokemonName(card)}, ${t("type", "type")} ${typeName(card)}`);
            button.removeAttribute("aria-pressed");
        } else if (context.choosing) {
            const isTarget = sameId(card.id, ownTargetId);
            button.setAttribute("aria-label", isTarget ? `${t("Ton Pokémon secret :", "Your secret Pokémon:")} ${pokemonName(card)}` : pokemonName(card));
            button.removeAttribute("aria-pressed");
        } else if (guessMode) {
            button.setAttribute("aria-label", `${t("Proposer", "Guess")} ${pokemonName(card)}`);
            button.removeAttribute("aria-pressed");
        } else {
            button.setAttribute(
                "aria-label",
                `${card.is_eliminated ? t("Relever", "Restore") : t("Rabattre", "Eliminate")} ${pokemonName(card)}, ${t("type", "type")} ${typeName(card)}`,
            );
            button.setAttribute("aria-pressed", String(Boolean(card.is_eliminated)));
        }
    }

    function setupCardTilt(button) {
        if (reducedMotion.matches || !precisePointer.matches) return;
        let bounds = null;
        let pointerX = 0;
        let pointerY = 0;
        let animationFrame = null;

        function paint() {
            if (!bounds) return;
            const x = Math.min(1, Math.max(0, (pointerX - bounds.left) / bounds.width));
            const y = Math.min(1, Math.max(0, (pointerY - bounds.top) / bounds.height));
            button.style.setProperty("--card-rx", `${((y - 0.5) * -9).toFixed(2)}deg`);
            button.style.setProperty("--card-ry", `${((x - 0.5) * 11).toFixed(2)}deg`);
            button.style.setProperty("--glare-x", `${(x * 100).toFixed(1)}%`);
            button.style.setProperty("--glare-y", `${(y * 100).toFixed(1)}%`);
            animationFrame = null;
        }

        button.addEventListener("pointerenter", () => {
            if (button.classList.contains("is-eliminated")) return;
            bounds = button.getBoundingClientRect();
            button.classList.add("is-tilting");
        });
        button.addEventListener("pointermove", (event) => {
            if (!bounds) return;
            pointerX = event.clientX;
            pointerY = event.clientY;
            if (animationFrame === null) animationFrame = window.requestAnimationFrame(paint);
        });
        button.addEventListener("pointerleave", () => {
            if (animationFrame !== null) window.cancelAnimationFrame(animationFrame);
            animationFrame = null;
            bounds = null;
            button.classList.remove("is-tilting");
            button.style.removeProperty("--card-rx");
            button.style.removeProperty("--card-ry");
            button.style.removeProperty("--glare-x");
            button.style.removeProperty("--glare-y");
        });
    }

    function renderPlayers() {
        const players = state.players || [];
        const currentTurnId = state.current_turn?.id;
        const currentMe = me();
        elements.players.replaceChildren();

        players.forEach((player, index) => {
            const isSelf = sameId(player.id, currentMe?.id);
            const chip = document.createElement("article");
            chip.className = `gw-player-chip${sameId(player.id, currentTurnId) ? " is-turn" : ""}`;
            chip.appendChild(makeAvatar(player, !isSelf));

            const copy = document.createElement("span");
            copy.className = "gw-player-chip-copy";
            const name = document.createElement("strong");
            name.textContent = isSelf ? `${player.username} (${t("toi", "you")})` : player.username;
            const status = document.createElement("small");
            if (state.status === "CHOIX") {
                status.textContent = player.has_chosen ? t("Choix verrouillé", "Choice locked") : t("Choisit son Pokémon…", "Choosing a Pokémon…");
            } else if (sameId(player.id, currentTurnId)) {
                status.textContent = state.pending_question ? t("Question posée", "Question asked") : t("Mène l’enquête", "Investigating");
            } else {
                status.textContent = t("Observe les indices", "Watching the clues");
            }
            copy.append(name, status);
            chip.appendChild(copy);

            const secret = document.createElement("span");
            secret.className = "gw-player-secret";
            if (player.target) {
                const targetImage = document.createElement("img");
                targetImage.src = player.target.sprite_url;
                targetImage.alt = `${isSelf ? t("Ton", "Your") : t("Son", "Their")} Pokémon secret: ${pokemonName(player.target)}`;
                targetImage.width = 28;
                targetImage.height = 32;
                targetImage.loading = "lazy";
                targetImage.decoding = "async";
                secret.appendChild(targetImage);
                chip.classList.add("has-secret");
            } else {
                secret.textContent = player.has_chosen ? "✓" : "?";
                secret.setAttribute("aria-label", player.has_chosen ? t("Pokémon secret choisi", "Secret Pokémon chosen") : t("Choix en attente", "Choice pending"));
            }
            chip.appendChild(secret);
            elements.players.appendChild(chip);
        });

        if (state.status === "CHOIX") {
            elements.turnBadge.textContent = `${players.filter((player) => player.has_chosen).length}/2 ${t("choix", "choices")}`;
            elements.turnBadge.classList.remove("is-mine");
        } else if (state.can_answer || state.must_answer) {
            elements.turnBadge.textContent = t("À toi de répondre", "Your turn to answer");
            elements.turnBadge.classList.add("is-mine");
        } else if (state.is_my_turn) {
            elements.turnBadge.textContent = t("À toi de jouer", "Your turn");
            elements.turnBadge.classList.add("is-mine");
        } else {
            const current = state.current_turn?.username || t("l’adversaire", "your opponent");
            elements.turnBadge.textContent = state.language === "en" ? `${current}’s turn` : `Tour de ${current}`;
            elements.turnBadge.classList.remove("is-mine");
        }
    }

    function formatTime(value) {
        if (!value) return "";
        const date = new Date(value);
        if (Number.isNaN(date.getTime())) return "";
        return timeFormatter.format(date);
    }

    function historyFingerprint(entries) {
        const currentPlayerId = me()?.id;
        return JSON.stringify(entries.map((entry) => {
            const actor = entry.actor || {};
            const isGuess = entry.kind === "GUESS";
            return [
                sameId(actor.id, currentPlayerId),
                (actor.username || "?").slice(0, 1).toLocaleUpperCase(state.language === "en" ? "en-GB" : "fr-FR"),
                actor.username || t("Dresseur", "Trainer"),
                entry.created_at || "",
                formatTime(entry.created_at),
                isGuess ? "GUESS" : "QUESTION",
                isGuess
                    ? state.language === "en"
                        ? `I think it’s ${pokemonName(entry.guessed_card) || "this Pokémon"}.`
                        : `Je pense que c’est ${pokemonName(entry.guessed_card) || "ce Pokémon"}.`
                    : entry.question || entry.message || entry.text || "Question",
                isGuess
                    ? Boolean(entry.is_correct)
                    : entry.answer === true
                        ? true
                        : entry.answer === false
                            ? false
                            : null,
            ];
        }));
    }

    function renderHistory() {
        const entries = histories().slice().sort((left, right) => (left.sequence || 0) - (right.sequence || 0));
        const fingerprint = historyFingerprint(entries);
        if (fingerprint === renderedHistoryFingerprint) return;

        const wasNearBottom = elements.history.scrollHeight - elements.history.scrollTop - elements.history.clientHeight < 42;
        elements.history.replaceChildren();
        elements.historyCount.textContent = String(entries.length);
        elements.historyEmpty.hidden = entries.length > 0;
        elements.history.hidden = entries.length === 0;

        entries.forEach((entry) => {
            const actor = entry.actor || {};
            const item = document.createElement("li");
            item.className = `gw-history-entry${sameId(actor.id, me()?.id) ? " is-mine" : ""}`;

            const avatar = document.createElement("span");
            avatar.className = "gw-history-avatar";
            avatar.setAttribute("aria-hidden", "true");
            avatar.textContent = (actor.username || "?").slice(0, 1).toLocaleUpperCase(state.language === "en" ? "en-GB" : "fr-FR");

            const bubble = document.createElement("div");
            bubble.className = "gw-history-bubble";
            const meta = document.createElement("div");
            meta.className = "gw-history-meta";
            const actorName = document.createElement("strong");
            actorName.textContent = actor.username || t("Dresseur", "Trainer");
            const timestamp = document.createElement("time");
            timestamp.dateTime = entry.created_at || "";
            timestamp.textContent = formatTime(entry.created_at);
            meta.append(actorName, timestamp);

            const content = document.createElement("p");
            if (entry.kind === "GUESS") {
                content.textContent = state.language === "en"
                    ? `I think it’s ${pokemonName(entry.guessed_card) || "this Pokémon"}.`
                    : `Je pense que c’est ${pokemonName(entry.guessed_card) || "ce Pokémon"}.`;
                const result = document.createElement("span");
                result.className = `gw-guess-token ${entry.is_correct ? "is-correct" : "is-wrong"}`;
                result.textContent = entry.is_correct ? t("Bonne réponse", "Correct") : t("Mauvaise réponse", "Wrong");
                bubble.append(meta, content, result);
            } else {
                content.textContent = entry.question || entry.message || entry.text || "Question";
                const answer = document.createElement("span");
                answer.className = "gw-answer-token";
                if (entry.answer === true) {
                    answer.dataset.answer = "true";
                    answer.textContent = t("Oui", "Yes");
                } else if (entry.answer === false) {
                    answer.dataset.answer = "false";
                    answer.textContent = t("Non", "No");
                } else {
                    answer.classList.add("is-pending");
                    answer.textContent = t("En attente…", "Waiting…");
                }
                bubble.append(meta, content, answer);
            }

            item.append(avatar, bubble);
            elements.history.appendChild(item);
        });

        renderedHistoryFingerprint = fingerprint;

        if (entries.length && wasNearBottom) {
            window.requestAnimationFrame(() => {
                elements.history.scrollTop = elements.history.scrollHeight;
            });
        }
    }

    function renderActions({ choosing, hasChosen }) {
        const pending = state.pending_question;
        const canAnswer = Boolean(state.can_answer || state.must_answer);
        elements.pendingQuestion.hidden = !pending || !canAnswer;
        elements.questionForm.hidden = Boolean(pending && canAnswer);

        if (pending && canAnswer) {
            elements.pendingQuestionText.textContent = pending.question;
            return;
        }

        let disabled = true;
        let hint = t("Attends le début de la partie.", "Wait for the game to begin.");
        if (choosing) {
            hint = hasChosen ? t("Ton choix est enregistré. L’enquête va bientôt commencer.", "Your choice is saved. The investigation will begin soon.") : t("Choisis d’abord ton Pokémon secret sur le plateau.", "First choose your secret Pokémon on the board.");
        } else if (pending) {
            hint = t("Ton adversaire réfléchit à sa réponse…", "Your opponent is thinking…");
        } else if (state.is_my_turn) {
            disabled = false;
            hint = t("Pose une question qui appelle « oui » ou « non ».", "Ask a yes-or-no question.");
        } else {
            hint = state.language === "en"
                ? `Wait for ${state.current_turn?.username || "your opponent"}’s question.`
                : `Attends la question de ${state.current_turn?.username || "ton adversaire"}.`;
        }

        elements.questionInput.disabled = disabled;
        elements.questionSubmit.disabled = disabled;
        elements.actionHint.textContent = hint;
    }

    function renderResult() {
        const currentMe = me();
        const winner = state.winner;
        const didWin = winner && sameId(winner.id, currentMe?.id);
        const finalGuess = histories().slice().reverse().find((entry) => entry.kind === "GUESS");
        const lostOnWrongGuess = finalGuess?.is_correct === false;
        const madeFinalGuess = sameId(finalGuess?.actor?.id, currentMe?.id);
        const guessedName = pokemonName(finalGuess?.guessed_card) || t("ce Pokémon", "this Pokémon");
        elements.resultTitle.textContent = didWin ? t("Victoire !", "Victory!") : t("Le mystère est résolu", "Mystery solved");
        if (!winner) {
            elements.resultCopy.textContent = t("La partie est terminée. Les Pokémon secrets sont maintenant révélés.", "The game is over. The secret Pokémon are now revealed.");
        } else if (lostOnWrongGuess) {
            elements.resultCopy.textContent = madeFinalGuess
                ? state.language === "en"
                    ? `Your guess, ${guessedName}, was wrong. ${winner.username} wins the game.`
                    : `Ta proposition, ${guessedName}, était incorrecte. ${winner.username} remporte la partie.`
                : state.language === "en"
                  ? `Your opponent guessed ${guessedName} and was wrong. You win the game.`
                  : `Ton adversaire a proposé ${guessedName} et s’est trompé. Tu remportes la partie.`;
        } else {
            elements.resultCopy.textContent = didWin
                ? t("Belle déduction : tu as identifié le Pokémon secret avant ton adversaire.", "Great deduction: you identified the secret Pokémon first.")
                : state.language === "en"
                  ? `${winner.username} found the correct answer. The secret Pokémon are now revealed.`
                  : `${winner.username} a trouvé la bonne réponse. Les Pokémon secrets sont maintenant révélés.`;
        }

        elements.resultPlayers.replaceChildren();
        (state.players || []).forEach((player) => {
            const item = document.createElement("article");
            item.className = `gw-result-player${sameId(player.id, winner?.id) ? " is-winner" : ""}`;
            item.appendChild(makeAvatar(player, !sameId(player.id, currentMe?.id)));
            const copy = document.createElement("span");
            copy.className = "gw-player-chip-copy";
            const name = document.createElement("strong");
            name.textContent = player.username;
            const target = document.createElement("small");
            target.textContent = player.target ? `${t("Secret :", "Secret:")} ${pokemonName(player.target)}` : t("Pokémon secret", "Secret Pokémon");
            copy.append(name, target);
            item.appendChild(copy);
            if (player.target) {
                const image = document.createElement("img");
                image.src = player.target.sprite_url;
                image.alt = "";
                image.width = 44;
                image.height = 44;
                image.loading = "lazy";
                image.decoding = "async";
                item.appendChild(image);
            }
            elements.resultPlayers.appendChild(item);
        });
    }

    function cardById(cardId) {
        return (state.roster || []).find((card) => sameId(card.id, cardId));
    }

    function openConfirmation(kind, card, trigger) {
        pendingConfirmation = { kind, card, trigger };
        elements.dialogEyebrow.textContent = kind === "choose" ? t("Choix secret", "Secret choice") : t("Tentative finale", "Final guess");
        elements.dialogTitle.textContent = kind === "choose"
            ? state.language === "en" ? `Really choose ${pokemonName(card)}?` : `${pokemonName(card)}, vraiment ?`
            : state.language === "en" ? `Is it ${pokemonName(card)}?` : `Est-ce ${pokemonName(card)} ?`;
        elements.dialogCopy.textContent = kind === "choose"
            ? t("Ton adversaire ne verra pas ce choix. Il sera verrouillé après confirmation.", "Your opponent will not see this choice. It locks after confirmation.")
            : t("Une mauvaise proposition donne immédiatement la victoire à ton adversaire.", "A wrong guess immediately gives your opponent the win.");
        elements.dialogConfirm.textContent = kind === "choose" ? t("Choisir ce Pokémon", "Choose this Pokémon") : t("Confirmer ma tentative", "Confirm my guess");
        elements.dialogVisual.replaceChildren();
        elements.dialogVisual.dataset.tcgType = tcgType(card);
        const image = document.createElement("img");
        image.src = card.sprite_url;
        image.alt = pokemonName(card);
        image.width = 110;
        image.height = 110;
        image.loading = "lazy";
        image.decoding = "async";
        elements.dialogVisual.appendChild(image);
        elements.dialog.returnValue = "";

        if (typeof elements.dialog.showModal === "function") {
            elements.dialog.showModal();
        } else if (window.confirm(`${elements.dialogTitle.textContent}\n\n${elements.dialogCopy.textContent}`)) {
            confirmPendingChoice();
        }
    }

    function confirmPendingChoice() {
        const pending = pendingConfirmation;
        pendingConfirmation = null;
        if (!pending) return;
        lastFocusedCardId = pending.card.id;
        if (pending.kind === "choose") {
            runAction(game.dataset.chooseUrl, { pokemon_card_id: pending.card.id }, {
                successMessage: state.language === "en"
                    ? `${pokemonName(pending.card)} is now your secret Pokémon.`
                    : `${pokemonName(pending.card)} est maintenant ton Pokémon secret.`,
            });
        } else {
            runAction(game.dataset.guessUrl, { pokemon_card_id: pending.card.id });
        }
    }

    function toggleUrl(cardId) {
        const url = new URL(game.dataset.toggleUrlTemplate, window.location.href);
        const segments = url.pathname.split("/");
        const placeholderIndex = segments.findIndex((segment, index) => segment === "0" && segments[index + 1] === "toggle");
        if (placeholderIndex !== -1) segments[placeholderIndex] = encodeURIComponent(String(cardId));
        url.pathname = segments.join("/");
        return url.toString();
    }

    async function requestJSON(url, payload, { signal } = {}) {
        const response = await fetch(url, {
            method: payload === undefined ? "GET" : "POST",
            credentials: "same-origin",
            cache: "no-store",
            signal,
            headers: payload === undefined
                ? { Accept: "application/json" }
                : {
                    Accept: "application/json",
                    "Content-Type": "application/json",
                    "X-CSRFToken": csrfToken,
                },
            body: payload === undefined ? undefined : JSON.stringify(payload),
        });

        let data = {};
        try {
            data = await response.json();
        } catch (_) {
            throw new Error(t("Le serveur a renvoyé une réponse illisible. Recharge la page puis réessaie.", "The server returned an unreadable response. Reload the page and try again."));
        }

        if (!response.ok) {
            const error = new Error(data.error || t("L’action a échoué. Vérifie ta connexion puis réessaie.", "The action failed. Check your connection and try again."));
            error.latestState = data.state || null;
            throw error;
        }
        return data;
    }

    async function runAction(url, payload, options = {}) {
        if (phase !== "idle") return null;
        phase = "posting";
        cancelPoll();
        setBusy(true);
        elements.feedback.hidden = true;

        try {
            const nextState = await requestJSON(url, {
                ...payload,
                expected_turn_revision: state.turn_revision,
            });
            const previous = state;
            state = nextState;
            render();
            announceStateChange(previous, nextState, options.successMessage);
            setSync("ready", t("Synchronisé", "Synced"));
            return nextState;
        } catch (error) {
            if (error.latestState) {
                state = error.latestState;
                render();
            }
            showFeedback(`${error.message} ${t("Tu peux réessayer maintenant.", "You can try again now.")}`);
            setSync("offline", t("À actualiser", "Refresh needed"));
            return null;
        } finally {
            phase = "idle";
            setBusy(false);
            schedulePoll();
        }
    }

    function announceStateChange(previous, next, explicitMessage = "") {
        if (explicitMessage) {
            announce(explicitMessage);
            return;
        }
        if (previous.status !== next.status) {
            if (next.status === "CHOIX") announce(t("Un adversaire a rejoint la table. Choisis ton Pokémon secret.", "An opponent joined the table. Choose your secret Pokémon."));
            if (next.status === "EN_COURS") announce(t("Les deux Pokémon secrets sont choisis. La partie commence.", "Both secret Pokémon are chosen. The game begins."));
            if (next.status === "TERMINEE") {
                const winner = next.winner?.username || t("Un joueur", "A player");
                announce(state.language === "en" ? `${winner} wins the game.` : `${winner} remporte la partie.`);
            }
            return;
        }
        const previousHistory = previous.history || previous.messages || [];
        const nextHistory = next.history || next.messages || [];
        if (nextHistory.length > previousHistory.length) {
            const latest = nextHistory[nextHistory.length - 1];
            if (latest.kind === "QUESTION") {
                const actor = latest.actor?.username || t("Ton adversaire", "Your opponent");
                announce(state.language === "en" ? `${actor} asks a new question.` : `${actor} pose une nouvelle question.`);
            }
            if (latest.kind === "GUESS") {
                const actor = latest.actor?.username || t("Un joueur", "A player");
                announce(state.language === "en" ? `${actor} makes a guess.` : `${actor} tente une réponse.`);
            }
        }
    }

    async function toggleCandidate(card, button) {
        const nextEliminated = !card.is_eliminated;
        lastFocusedCardId = card.id;
        button.classList.toggle("is-eliminated", nextEliminated);
        button.classList.add("is-pending");
        const nextState = await runAction(toggleUrl(card.id), { is_eliminated: nextEliminated }, {
            successMessage: nextEliminated
                ? state.language === "en" ? `${pokemonName(card)} is eliminated.` : `${pokemonName(card)} est écarté.`
                : state.language === "en" ? `${pokemonName(card)} is a candidate again.` : `${pokemonName(card)} est de nouveau candidat.`,
        });
        button.classList.remove("is-pending");
        if (!nextState) render();
    }

    async function resetAllCandidates() {
        if (phase !== "idle") return;
        const eliminatedCards = (state.roster || []).filter((card) => card.is_eliminated);
        if (!eliminatedCards.length) return;
        elements.resetCandidates.setAttribute("aria-busy", "true");
        try {
            const nextState = await runAction(game.dataset.resetUrl, {}, {
                successMessage: t("Tous les candidats sont relevés.", "All candidates are restored."),
            });
            if (nextState) {
                focusAfterRender(null, elements.boardTitle);
            }
        } finally {
            elements.resetCandidates.removeAttribute("aria-busy");
        }
    }

    function cancelPoll() {
        window.clearTimeout(pollTimer);
        pollTimer = null;
        pollController?.abort();
        pollController = null;
    }

    function schedulePoll(delay = 1400) {
        window.clearTimeout(pollTimer);
        pollTimer = window.setTimeout(pollState, delay);
    }

    async function pollState() {
        if (document.hidden || phase !== "idle") {
            schedulePoll(document.hidden ? 3500 : 900);
            return;
        }

        pollController = new AbortController();
        setSync("syncing", t("Actualisation…", "Refreshing…"));
        try {
            const nextState = await requestJSON(game.dataset.stateUrl, undefined, { signal: pollController.signal });
            if (stateFingerprint(nextState) !== stateFingerprint(state)) {
                const previous = state;
                state = nextState;
                render();
                announceStateChange(previous, nextState);
            }
            setSync("ready", t("Synchronisé", "Synced"));
        } catch (error) {
            if (error.name !== "AbortError") setSync("offline", t("Hors ligne", "Offline"));
        } finally {
            pollController = null;
            schedulePoll();
        }
    }

    game.addEventListener("click", (event) => {
        const cardButton = event.target.closest("[data-card-id]");
        if (cardButton && elements.roster.contains(cardButton)) {
            if (phase !== "idle" || cardButton.disabled) return;
            const card = cardById(cardButton.dataset.cardId);
            if (!card) return;
            if (state.status === "CHOIX") {
                openConfirmation("choose", card, cardButton);
            } else if (guessMode) {
                openConfirmation("guess", card, cardButton);
            } else if (state.status === "EN_COURS") {
                toggleCandidate(card, cardButton);
            }
            return;
        }

        const answerButton = event.target.closest("[data-answer]");
        if (answerButton && !answerButton.disabled) {
            runAction(game.dataset.answerUrl, { answer: answerButton.dataset.answer === "true" });
            return;
        }

        if (event.target.closest("[data-guess-mode]")) {
            if (elements.guessMode.disabled || phase !== "idle") return;
            guessMode = !guessMode;
            renderBoard();
            if (guessMode) announce(t("Mode tentative activé. Choisis le Pokémon adverse sur le plateau.", "Guess mode enabled. Choose your opponent’s Pokémon on the board."));
            return;
        }

        if (event.target.closest("[data-reset-candidates]")) {
            resetAllCandidates();
            return;
        }

        const copyButton = event.target.closest("[data-copy-invite]");
        if (copyButton) copyInvitation(copyButton);
    });

    elements.questionForm.addEventListener("submit", async (event) => {
        event.preventDefault();
        if (phase !== "idle" || elements.questionInput.disabled) return;
        const question = elements.questionInput.value.replace(/\s+/g, " ").trim();
        if (!question) {
            showFeedback(t("Saisis une question avant de l’envoyer.", "Type a question before sending it."));
            elements.questionInput.focus();
            return;
        }
        const nextState = await runAction(game.dataset.askUrl, { question });
        if (nextState) elements.questionInput.value = "";
    });

    elements.dialog?.addEventListener("close", () => {
        const pending = pendingConfirmation;
        if (elements.dialog.returnValue === "confirm") {
            confirmPendingChoice();
            return;
        }
        pendingConfirmation = null;
        pending?.trigger?.focus();
    });

    async function copyInvitation(button) {
        const label = button.querySelector("[data-copy-label]");
        try {
            await navigator.clipboard.writeText(window.location.href);
            label.textContent = t("Lien copié", "Link copied");
            announce(t("Lien d’invitation copié.", "Invitation link copied."));
        } catch (_) {
            label.textContent = t("Copie l’adresse du navigateur", "Copy the browser address");
            showFeedback(t("La copie automatique est bloquée. Copie l’adresse affichée dans la barre du navigateur.", "Automatic copying is blocked. Copy the address from your browser bar."));
        }
        window.setTimeout(() => {
            label.textContent = t("Copier le lien", "Copy link");
        }, 2400);
    }

    document.addEventListener("visibilitychange", () => {
        if (!document.hidden) {
            cancelPoll();
            schedulePoll(0);
        }
    });
    window.addEventListener("beforeunload", cancelPoll);

    render();
    setSync("ready", t("Synchronisé", "Synced"));
    schedulePoll();
})();
