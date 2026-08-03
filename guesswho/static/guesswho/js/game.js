(() => {
    "use strict";

    const game = document.getElementById("guesswho-game");
    const stateNode = document.getElementById("guesswho-initial-state");
    if (!game || !stateNode) return;

    let state;
    try {
        state = JSON.parse(stateNode.textContent);
    } catch (_) {
        game.setAttribute("aria-busy", "false");
        const fallback = document.createElement("p");
        fallback.className = "gw-feedback";
        fallback.setAttribute("role", "alert");
        fallback.textContent = "Le plateau n’a pas pu être chargé. Recharge la page pour réessayer.";
        game.appendChild(fallback);
        return;
    }

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
        EN_ATTENTE: "En attente",
        CHOIX: "Choix secret",
        EN_COURS: "Partie en cours",
        TERMINEE: "Terminée",
    };
    const TCG_TYPE_NAMES = {
        grass: "Plante",
        fire: "Feu",
        water: "Eau",
        lightning: "Électrique",
        psychic: "Psy",
        fighting: "Combat",
        darkness: "Obscurité",
        metal: "Métal",
        dragon: "Dragon",
        colorless: "Incolore",
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
    const timeFormatter = new Intl.DateTimeFormat("fr-FR", { hour: "2-digit", minute: "2-digit" });
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
        return TCG_TYPE_NAMES[tcgType(card)] || "Incolore";
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
        if (isBusy) setSync("syncing", "Envoi…");
    }

    function setView(activeView) {
        const previousView = renderedView;
        elements.waitingView.hidden = activeView !== "waiting";
        elements.boardView.hidden = activeView !== "board";
        elements.resultView.hidden = activeView !== "result";
        renderedView = activeView;
        return previousView;
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
        elements.status.textContent = STATUS_LABELS[state.status] || "Partie";

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
        avatar.textContent = (player?.username || "?").slice(0, 1).toLocaleUpperCase("fr-FR");
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
                status.textContent = sameId(player.id, me()?.id) ? "Toi · prêt" : "Adversaire · prêt";
                copy.append(name, status);
                seat.appendChild(copy);
            } else {
                const avatar = document.createElement("span");
                avatar.className = "gw-player-avatar";
                avatar.setAttribute("aria-hidden", "true");
                avatar.textContent = "+";
                const copy = document.createElement("span");
                const name = document.createElement("strong");
                name.textContent = "Place libre";
                const status = document.createElement("small");
                status.textContent = "En attente…";
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
            ? `${(state.roster || []).length} Pokémon disponibles`
            : `${standingCount} encore debout`;

        elements.boardHelp.classList.toggle("is-guessing", guessMode);
        if (choosing && !hasChosen) {
            elements.boardEyebrow.textContent = "Choix confidentiel";
            elements.boardTitle.textContent = "Choisis ton Pokémon secret";
            elements.boardHelp.textContent = "Ton adversaire ne verra pas ce choix. Sélectionne 1 carte pour continuer.";
        } else if (choosing) {
            elements.boardEyebrow.textContent = "Choix enregistré";
            elements.boardTitle.textContent = "Ton Pokémon est bien gardé";
            elements.boardHelp.textContent = "En attente du choix de ton adversaire…";
        } else if (guessMode) {
            elements.boardEyebrow.textContent = "Tentative finale";
            elements.boardTitle.textContent = "Qui se cache chez l’adversaire ?";
            elements.boardHelp.textContent = "Choisis 1 Pokémon. Attention : une erreur donne la victoire à ton adversaire.";
        } else {
            elements.boardEyebrow.textContent = "Ton plateau";
            elements.boardTitle.textContent = "24 suspects. 1 seul Pokémon.";
            elements.boardHelp.textContent = "Clique sur une carte pour la rabattre après chaque indice.";
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

        const symbol = document.createElement("span");
        symbol.className = "gw-tcg-symbol";
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
        name.textContent = card.name_fr;

        const eliminated = document.createElement("span");
        eliminated.className = "gw-card-eliminated-label";
        eliminated.setAttribute("aria-hidden", "true");
        eliminated.textContent = "Écarté";

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
        button.querySelector(".gw-tcg-symbol").dataset.tcgType = type;
        button.classList.toggle("is-eliminated", Boolean(card.is_eliminated));
        button.classList.toggle("is-choice-target", context.hasChosen && sameId(card.id, ownTargetId));
        button.classList.toggle("is-guess-target", false);
        button.disabled = context.choosing && context.hasChosen;

        const modeLabel = button.querySelector(".gw-card-mode-label");
        const showModeLabel = (!context.choosing && guessMode) || (context.choosing && !context.hasChosen);
        modeLabel.hidden = !showModeLabel;
        modeLabel.textContent = context.choosing ? "Choisir" : "Proposer";

        if (context.choosing && !context.hasChosen) {
            button.setAttribute("aria-label", `Choisir ${card.name_fr} comme Pokémon secret, type ${typeName(card)}`);
            button.removeAttribute("aria-pressed");
        } else if (context.choosing) {
            const isTarget = sameId(card.id, ownTargetId);
            button.setAttribute("aria-label", isTarget ? `Ton Pokémon secret : ${card.name_fr}` : card.name_fr);
            button.removeAttribute("aria-pressed");
        } else if (guessMode) {
            button.setAttribute("aria-label", `Proposer ${card.name_fr} comme Pokémon secret adverse`);
            button.removeAttribute("aria-pressed");
        } else {
            button.setAttribute(
                "aria-label",
                `${card.is_eliminated ? "Relever" : "Rabattre"} ${card.name_fr}, type ${typeName(card)}`,
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
            name.textContent = isSelf ? `${player.username} (toi)` : player.username;
            const status = document.createElement("small");
            if (state.status === "CHOIX") {
                status.textContent = player.has_chosen ? "Choix verrouillé" : "Choisit son Pokémon…";
            } else if (sameId(player.id, currentTurnId)) {
                status.textContent = state.pending_question ? "Question posée" : "Mène l’enquête";
            } else {
                status.textContent = "Observe les indices";
            }
            copy.append(name, status);
            chip.appendChild(copy);

            const secret = document.createElement("span");
            secret.className = "gw-player-secret";
            if (player.target) {
                const targetImage = document.createElement("img");
                targetImage.src = player.target.sprite_url;
                targetImage.alt = `${isSelf ? "Ton" : "Son"} Pokémon secret : ${player.target.name_fr}`;
                targetImage.width = 28;
                targetImage.height = 32;
                targetImage.loading = "lazy";
                targetImage.decoding = "async";
                secret.appendChild(targetImage);
                chip.classList.add("has-secret");
            } else {
                secret.textContent = player.has_chosen ? "✓" : "?";
                secret.setAttribute("aria-label", player.has_chosen ? "Pokémon secret choisi" : "Choix en attente");
            }
            chip.appendChild(secret);
            elements.players.appendChild(chip);
        });

        if (state.status === "CHOIX") {
            elements.turnBadge.textContent = `${players.filter((player) => player.has_chosen).length}/2 choix`;
            elements.turnBadge.classList.remove("is-mine");
        } else if (state.can_answer || state.must_answer) {
            elements.turnBadge.textContent = "À toi de répondre";
            elements.turnBadge.classList.add("is-mine");
        } else if (state.is_my_turn) {
            elements.turnBadge.textContent = "À toi de jouer";
            elements.turnBadge.classList.add("is-mine");
        } else {
            const current = state.current_turn?.username || "l’adversaire";
            elements.turnBadge.textContent = `Tour de ${current}`;
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
                (actor.username || "?").slice(0, 1).toLocaleUpperCase("fr-FR"),
                actor.username || "Dresseur",
                entry.created_at || "",
                formatTime(entry.created_at),
                isGuess ? "GUESS" : "QUESTION",
                isGuess
                    ? `Je pense que c’est ${entry.guessed_card?.name_fr || "ce Pokémon"}.`
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
            avatar.textContent = (actor.username || "?").slice(0, 1).toLocaleUpperCase("fr-FR");

            const bubble = document.createElement("div");
            bubble.className = "gw-history-bubble";
            const meta = document.createElement("div");
            meta.className = "gw-history-meta";
            const actorName = document.createElement("strong");
            actorName.textContent = actor.username || "Dresseur";
            const timestamp = document.createElement("time");
            timestamp.dateTime = entry.created_at || "";
            timestamp.textContent = formatTime(entry.created_at);
            meta.append(actorName, timestamp);

            const content = document.createElement("p");
            if (entry.kind === "GUESS") {
                content.textContent = `Je pense que c’est ${entry.guessed_card?.name_fr || "ce Pokémon"}.`;
                const result = document.createElement("span");
                result.className = `gw-guess-token ${entry.is_correct ? "is-correct" : "is-wrong"}`;
                result.textContent = entry.is_correct ? "Bonne réponse" : "Mauvaise réponse";
                bubble.append(meta, content, result);
            } else {
                content.textContent = entry.question || entry.message || entry.text || "Question";
                const answer = document.createElement("span");
                answer.className = "gw-answer-token";
                if (entry.answer === true) {
                    answer.dataset.answer = "true";
                    answer.textContent = "Oui";
                } else if (entry.answer === false) {
                    answer.dataset.answer = "false";
                    answer.textContent = "Non";
                } else {
                    answer.classList.add("is-pending");
                    answer.textContent = "En attente…";
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
        let hint = "Attends le début de la partie.";
        if (choosing) {
            hint = hasChosen ? "Ton choix est enregistré. L’enquête va bientôt commencer." : "Choisis d’abord ton Pokémon secret sur le plateau.";
        } else if (pending) {
            hint = "Ton adversaire réfléchit à sa réponse…";
        } else if (state.is_my_turn) {
            disabled = false;
            hint = "Pose une question qui appelle « oui » ou « non ».";
        } else {
            hint = `Attends la question de ${state.current_turn?.username || "ton adversaire"}.`;
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
        const guessedName = finalGuess?.guessed_card?.name_fr || "ce Pokémon";
        elements.resultTitle.textContent = didWin ? "Victoire !" : "Le mystère est résolu";
        if (!winner) {
            elements.resultCopy.textContent = "La partie est terminée. Les Pokémon secrets sont maintenant révélés.";
        } else if (lostOnWrongGuess) {
            elements.resultCopy.textContent = madeFinalGuess
                ? `Ta proposition, ${guessedName}, était incorrecte. ${winner.username} remporte la partie.`
                : `Ton adversaire a proposé ${guessedName} et s’est trompé. Tu remportes la partie.`;
        } else {
            elements.resultCopy.textContent = didWin
                ? "Belle déduction : tu as identifié le Pokémon secret avant ton adversaire."
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
            target.textContent = player.target ? `Secret : ${player.target.name_fr}` : "Pokémon secret";
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
        elements.dialogEyebrow.textContent = kind === "choose" ? "Choix secret" : "Tentative finale";
        elements.dialogTitle.textContent = kind === "choose" ? `${card.name_fr}, vraiment ?` : `Est-ce ${card.name_fr} ?`;
        elements.dialogCopy.textContent = kind === "choose"
            ? "Ton adversaire ne verra pas ce choix. Il sera verrouillé après confirmation."
            : "Une mauvaise proposition donne immédiatement la victoire à ton adversaire.";
        elements.dialogConfirm.textContent = kind === "choose" ? "Choisir ce Pokémon" : "Confirmer ma tentative";
        elements.dialogVisual.replaceChildren();
        elements.dialogVisual.dataset.tcgType = tcgType(card);
        const image = document.createElement("img");
        image.src = card.sprite_url;
        image.alt = card.name_fr;
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
                successMessage: `${pending.card.name_fr} est maintenant ton Pokémon secret.`,
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
            throw new Error("Le serveur a renvoyé une réponse illisible. Recharge la page puis réessaie.");
        }

        if (!response.ok) {
            const error = new Error(data.error || "L’action a échoué. Vérifie ta connexion puis réessaie.");
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
            setSync("ready", "Synchronisé");
            return nextState;
        } catch (error) {
            if (error.latestState) {
                state = error.latestState;
                render();
            }
            showFeedback(`${error.message} Tu peux réessayer maintenant.`);
            setSync("offline", "À actualiser");
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
            if (next.status === "CHOIX") announce("Un adversaire a rejoint la table. Choisis ton Pokémon secret.");
            if (next.status === "EN_COURS") announce("Les deux Pokémon secrets sont choisis. La partie commence.");
            if (next.status === "TERMINEE") announce(`${next.winner?.username || "Un joueur"} remporte la partie.`);
            return;
        }
        const previousHistory = previous.history || previous.messages || [];
        const nextHistory = next.history || next.messages || [];
        if (nextHistory.length > previousHistory.length) {
            const latest = nextHistory[nextHistory.length - 1];
            if (latest.kind === "QUESTION") announce(`${latest.actor?.username || "Ton adversaire"} pose une nouvelle question.`);
            if (latest.kind === "GUESS") announce(`${latest.actor?.username || "Un joueur"} tente une réponse.`);
        }
    }

    async function toggleCandidate(card, button) {
        const nextEliminated = !card.is_eliminated;
        lastFocusedCardId = card.id;
        button.classList.toggle("is-eliminated", nextEliminated);
        button.classList.add("is-pending");
        const nextState = await runAction(toggleUrl(card.id), { is_eliminated: nextEliminated }, {
            successMessage: nextEliminated ? `${card.name_fr} est écarté.` : `${card.name_fr} est de nouveau candidat.`,
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
                successMessage: "Tous les candidats sont relevés.",
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
        setSync("syncing", "Actualisation…");
        try {
            const nextState = await requestJSON(game.dataset.stateUrl, undefined, { signal: pollController.signal });
            if (stateFingerprint(nextState) !== stateFingerprint(state)) {
                const previous = state;
                state = nextState;
                render();
                announceStateChange(previous, nextState);
            }
            setSync("ready", "Synchronisé");
        } catch (error) {
            if (error.name !== "AbortError") setSync("offline", "Hors ligne");
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
            if (guessMode) announce("Mode tentative activé. Choisis le Pokémon adverse sur le plateau.");
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
            showFeedback("Saisis une question avant de l’envoyer.");
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
            label.textContent = "Lien copié";
            announce("Lien d’invitation copié.");
        } catch (_) {
            label.textContent = "Copie l’adresse du navigateur";
            showFeedback("La copie automatique est bloquée. Copie l’adresse affichée dans la barre du navigateur.");
        }
        window.setTimeout(() => {
            label.textContent = "Copier le lien";
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
    setSync("ready", "Synchronisé");
    schedulePoll();
})();
