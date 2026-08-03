(function () {
    "use strict";

    const board = document.getElementById("game-app");
    const initialStateElement = document.getElementById("game-initial-state");
    if (!board || !initialStateElement) return;

    const initialGameState = JSON.parse(initialStateElement.textContent);
    const myPlayer = initialGameState.players.find((player) => Array.isArray(player.hand));
    const feedback = document.getElementById("game-feedback");
    const announcer = document.getElementById("game-announcer");
    if (announcer && board.contains(announcer)) document.body.appendChild(announcer);
    const reducedMotion = window.matchMedia("(prefers-reduced-motion: reduce)");
    const precisePointer = window.matchMedia("(hover: hover) and (pointer: fine)");
    const stateUrl = board.dataset.stateUrl;

    let phase = "idle";
    let pollTimer = null;
    let pollController = null;
    let reloadRequested = false;
    let pendingLegendaryCardId = null;
    let pendingLegendaryCardElement = null;
    let resizeFrame = null;
    let botTurnTimer = null;

    function stateFingerprint(state) {
        return JSON.stringify(state, (key, value) => (key === "is_playable" ? undefined : value));
    }

    const knownStateFingerprint = stateFingerprint(initialGameState);

    function getCookie(name) {
        const match = document.cookie.match(new RegExp("(^| )" + name + "=([^;]+)"));
        return match ? decodeURIComponent(match[2]) : null;
    }

    function showError(message) {
        feedback.textContent = message;
        feedback.hidden = false;
    }

    function announce(message) {
        if (announcer) announcer.textContent = message;
    }

    function playerHandCount(player) {
        return Array.isArray(player?.hand) ? player.hand.length : (player?.hand_count ?? 0);
    }

    function playersById(state) {
        return new Map(state.players.map((player) => [String(player.id), player]));
    }

    function playerDeltas(previousState, nextState) {
        const previousPlayers = playersById(previousState);
        return nextState.players.map((player) => ({
            player,
            count: playerHandCount(player) - playerHandCount(previousPlayers.get(String(player.id))),
        }));
    }

    function hasExpectedDrawPileDelta(previousState, nextState, drawCount) {
        if (drawCount === 0) return nextState.draw_pile_count === previousState.draw_pile_count;
        if (previousState.draw_pile_count < drawCount) return true;
        return nextState.draw_pile_count === previousState.draw_pile_count - drawCount;
    }

    function playerAtOffset(state, player, direction, offset) {
        if (!player || !state.players.length) return null;
        const turnOrder = (player.turn_order + direction * offset + state.players.length) % state.players.length;
        return state.players.find((candidate) => candidate.turn_order === turnOrder) || null;
    }

    function hasExpectedCurrentPlayer(previousState, nextState, actor, direction, offset) {
        if (nextState.status !== "EN_COURS") return true;
        const expectedPlayer = playerAtOffset(previousState, actor, direction, offset);
        const currentPlayer = nextState.players.find((player) => player.is_current_turn);
        return Boolean(expectedPlayer && currentPlayer && String(expectedPlayer.id) === String(currentPlayer.id));
    }

    function analyzeRemoteStateChange(previousState, nextState) {
        const actor = previousState.players.find((player) => player.is_current_turn);
        const deltas = playerDeltas(previousState, nextState);
        const losses = deltas.filter((delta) => delta.count < 0);
        const draws = deltas.filter((delta) => delta.count > 0).map(({ player, count }) => ({ player, count }));
        const topCardChanged = nextState.top_discard?.id !== previousState.top_discard?.id;

        if (!actor) return null;

        if (!topCardChanged) {
            const isSingleDraw =
                losses.length === 0 &&
                draws.length === 1 &&
                draws[0].count === 1 &&
                String(draws[0].player.id) === String(actor.id);
            const directionUnchanged = nextState.direction === previousState.direction;
            if (
                !isSingleDraw ||
                !directionUnchanged ||
                !hasExpectedDrawPileDelta(previousState, nextState, 1) ||
                !hasExpectedCurrentPlayer(previousState, nextState, actor, previousState.direction, 1)
            ) {
                return null;
            }
            return { actor: null, draws };
        }

        const actorLoss = losses.find((delta) => String(delta.player.id) === String(actor.id));
        if (losses.length !== 1 || actorLoss?.count !== -1 || !nextState.top_discard) return null;

        const action = nextState.top_discard.action;
        const penalty = { DRAW_TWO: 2, DRAW_FOUR: 4 }[action];
        let expectedTurnOffset = 1;
        let turnDirection = previousState.direction;

        if (action === "REVERSE") {
            turnDirection = -previousState.direction;
            if (
                nextState.direction !== turnDirection ||
                draws.length !== 0 ||
                !hasExpectedDrawPileDelta(previousState, nextState, 0)
            ) {
                return null;
            }
        } else {
            if (nextState.direction !== previousState.direction) return null;
            if (penalty) {
                const target = playerAtOffset(previousState, actor, previousState.direction, 1);
                if (!target) return null;
                if (target.has_protection) {
                    if (draws.length !== 0 || !hasExpectedDrawPileDelta(previousState, nextState, 0)) return null;
                } else {
                    const isExpectedPenalty =
                        draws.length === 1 &&
                        draws[0].count === penalty &&
                        String(draws[0].player.id) === String(target.id);
                    if (!isExpectedPenalty || !hasExpectedDrawPileDelta(previousState, nextState, penalty)) return null;
                    expectedTurnOffset = 2;
                }
            } else if (draws.length !== 0 || !hasExpectedDrawPileDelta(previousState, nextState, 0)) {
                return null;
            }
        }

        if (!hasExpectedCurrentPlayer(previousState, nextState, actor, turnDirection, expectedTurnOffset)) {
            return null;
        }
        return { actor, draws };
    }

    function cancelPoll() {
        window.clearTimeout(pollTimer);
        window.clearTimeout(botTurnTimer);
        pollTimer = null;
        botTurnTimer = null;
        pollController?.abort();
        pollController = null;
    }

    function reloadOnce() {
        if (reloadRequested) return;
        reloadRequested = true;
        phase = "reloading";
        cancelPoll();
        window.location.reload();
    }

    async function postJSON(url, body) {
        const response = await fetch(url, {
            method: "POST",
            headers: { "Content-Type": "application/json", "X-CSRFToken": getCookie("csrftoken") },
            body: JSON.stringify(body),
        });
        const data = await response.json();
        if (!response.ok) throw new Error(data.error || "Une erreur est survenue. Réessaie.");
        return data;
    }

    function motionVisual(element) {
        if (!element) return null;
        if (element.matches(".card-unit, .deck-card, .opponent-card-back")) return element;
        return element.querySelector(".card-unit, .deck-card--front, .opponent-card-back:last-child");
    }

    function opponentSeat(playerId) {
        return board.querySelector(`[data-player-id="${CSS.escape(String(playerId))}"]`);
    }

    function opponentBack(playerId) {
        const backs = opponentSeat(playerId)?.querySelectorAll(".opponent-card-back");
        return backs?.length ? backs[backs.length - 1] : null;
    }

    function motionTargetForPlayer(playerId) {
        if (myPlayer && String(playerId) === String(myPlayer.id)) {
            return board.querySelector("[data-motion-hand]");
        }
        return opponentSeat(playerId)?.querySelector("[data-motion-opponent-hand]");
    }

    function prepareMotionClone(source) {
        const clone = source.cloneNode(true);
        clone.classList.add("motion-card-clone");
        clone.setAttribute("aria-hidden", "true");
        clone.removeAttribute("id");
        clone.removeAttribute("data-play-card");
        clone.tabIndex = -1;
        clone.querySelectorAll("[id]").forEach((element) => element.removeAttribute("id"));
        if (clone.matches("button, input, select, textarea")) clone.disabled = true;
        clone.querySelectorAll("button").forEach((button) => {
            button.disabled = true;
            button.tabIndex = -1;
            button.removeAttribute("data-play-card");
        });
        clone.querySelectorAll("a, input, select, textarea, [tabindex]").forEach((element) => {
            element.tabIndex = -1;
        });
        clone.inert = true;
        return clone;
    }

    async function animateCardFlight(sourceElement, targetElement, options = {}) {
        if (reducedMotion.matches || !Element.prototype.animate) return;
        const source = motionVisual(sourceElement);
        if (!source || !targetElement) return;

        // Lecture groupée avant toute écriture DOM pour éviter le layout thrashing.
        const sourceBounds = source.getBoundingClientRect();
        const targetBounds = targetElement.getBoundingClientRect();
        if (!sourceBounds.width || !targetBounds.width) return;

        const clone = prepareMotionClone(source);
        Object.assign(clone.style, {
            top: `${sourceBounds.top}px`,
            left: `${sourceBounds.left}px`,
            width: `${sourceBounds.width}px`,
            height: `${sourceBounds.height}px`,
        });
        document.body.appendChild(clone);
        source.style.opacity = "0";

        const offsetX = options.offsetX || 0;
        const offsetY = options.offsetY || 0;
        const deltaX = targetBounds.left + targetBounds.width / 2 - (sourceBounds.left + sourceBounds.width / 2) + offsetX;
        const deltaY = targetBounds.top + targetBounds.height / 2 - (sourceBounds.top + sourceBounds.height / 2) + offsetY;
        const naturalScale = targetBounds.width / sourceBounds.width;
        const endScale = options.endScale ?? Math.min(3.2, Math.max(0.34, naturalScale));
        const direction = options.direction ?? 1;
        const middleScale = Math.max(1.04, Math.min(1.22, endScale + 0.12));

        const animation = clone.animate(
            [
                { transform: `translate3d(0, 0, 0) rotateZ(${direction * -3}deg) scale(1)`, opacity: 1 },
                {
                    offset: 0.62,
                    transform: `translate3d(${deltaX * 0.62}px, ${deltaY * 0.62 - 34}px, 0) rotateZ(${direction * 8}deg) scale(${middleScale})`,
                    opacity: 1,
                },
                {
                    transform: `translate3d(${deltaX}px, ${deltaY}px, 0) rotateZ(${direction * 2}deg) scale(${endScale})`,
                    opacity: 0.94,
                },
            ],
            {
                duration: options.duration ?? 560,
                delay: options.delay ?? 0,
                easing: "cubic-bezier(0.2, 0.75, 0.22, 1)",
                fill: "forwards",
            },
        );

        try {
            await animation.finished;
        } catch (_) {
            // Une navigation ou un nouveau rendu peut interrompre proprement l'animation.
            clone.remove();
        }
    }

    function buildMotionCardFace(card) {
        const face = document.createElement("div");
        face.className = `card-unit card-unit--display motion-card-reveal${card.action !== "NORMAL" ? " has-action" : ""}`;
        face.dataset.type = card.primary_type;
        face.setAttribute("aria-hidden", "true");

        function addTypeIcon(type, position) {
            if (!type) return;
            const badge = document.createElement("span");
            badge.className = `card-unit-type ${position}`;
            badge.dataset.type = type;
            const icon = document.createElement("span");
            icon.className = "type-energy-icon";
            icon.dataset.type = type;
            badge.appendChild(icon);
            face.appendChild(badge);
        }

        addTypeIcon(card.primary_type, "primary");
        addTypeIcon(card.secondary_type, "secondary");

        const number = document.createElement("span");
        number.className = "card-unit-number";
        number.textContent = `#${card.pokedex_id}`;
        face.appendChild(number);

        if (card.action !== "NORMAL") {
            const action = document.createElement("span");
            action.className = "card-action";
            action.dataset.action = card.action;
            if (card.action === "SHIELD") {
                const shield = document.createElement("i");
                shield.className = "shield-symbol";
                action.appendChild(shield);
            } else {
                action.textContent = { DRAW_TWO: "+2", DRAW_FOUR: "+4", REVERSE: "↺" }[card.action] || "";
            }
            face.appendChild(action);
        }

        const image = document.createElement("img");
        image.src = card.sprite_url;
        image.alt = "";
        image.width = 82;
        image.height = 82;
        face.appendChild(image);

        const name = document.createElement("span");
        name.className = "card-unit-name";
        name.textContent = card.name_fr;
        face.appendChild(name);
        return face;
    }

    async function animateCardReveal(card, targetElement) {
        if (reducedMotion.matches || !Element.prototype.animate || !card || !targetElement) return;
        const targetBounds = targetElement.getBoundingClientRect();
        if (!targetBounds.width) return;

        const face = buildMotionCardFace(card);
        Object.assign(face.style, {
            top: `${targetBounds.top}px`,
            left: `${targetBounds.left}px`,
            width: `${targetBounds.width}px`,
            height: `${targetBounds.height}px`,
        });
        document.body.appendChild(face);
        const animation = face.animate(
            [
                { transform: "perspective(700px) rotateY(82deg) scale(0.86)", opacity: 0.25 },
                { transform: "perspective(700px) rotateY(0deg) scale(1)", opacity: 1 },
            ],
            { duration: 260, easing: "cubic-bezier(0.2, 0.8, 0.2, 1)", fill: "forwards" },
        );
        try {
            await animation.finished;
        } catch (_) {
            face.remove();
            return;
        }
        window.setTimeout(() => face.remove(), 1200);
    }

    async function animateDraws(draws) {
        const deck = board.querySelector("[data-motion-deck]");
        if (!deck || !draws.length) return;

        for (const draw of draws) {
            const target = motionTargetForPlayer(draw.player.id);
            if (!target) continue;
            const visibleCount = Math.min(draw.count, 4);
            const isMine = myPlayer && String(draw.player.id) === String(myPlayer.id);
            announce(`${draw.player.username} pioche ${draw.count} carte${draw.count > 1 ? "s" : ""}.`);
            await Promise.all(
                Array.from({ length: visibleCount }, (_, index) =>
                    animateCardFlight(deck, target, {
                        delay: index * 85,
                        duration: 500,
                        endScale: isMine ? 0.96 : 0.38,
                        direction: index % 2 ? -1 : 1,
                        offsetX: (index - (visibleCount - 1) / 2) * 9,
                    }),
                ),
            );
        }
    }

    function detectedDraws(previousState, nextState) {
        return playerDeltas(previousState, nextState)
            .filter((draw) => draw.count > 0)
            .map(({ player, count }) => ({ player, count }));
    }

    async function animateStateChange(previousState, nextState, context = {}) {
        const remoteChange = context.kind ? null : analyzeRemoteStateChange(previousState, nextState);
        if (!context.kind && !remoteChange) return;

        const previousTopId = previousState.top_discard?.id;
        const nextTopId = nextState.top_discard?.id;
        if (nextTopId && nextTopId !== previousTopId) {
            const actor = context.kind
                ? previousState.players.find((player) => player.is_current_turn)
                : remoteChange.actor;
            const source = context.kind === "play" ? context.source : opponentBack(actor?.id);
            const discard = board.querySelector("[data-motion-discard]") || board.querySelector(".discard-pile");
            if (actor && nextState.top_discard) {
                announce(`${actor.username} joue ${nextState.top_discard.name_fr}.`);
            }
            await animateCardFlight(source, discard, { duration: 610 });
            if (context.kind !== "play") {
                await animateCardReveal(nextState.top_discard, discard);
            }
        }

        await animateDraws(context.kind ? detectedDraws(previousState, nextState) : remoteChange.draws);
    }

    async function submitAction(url, body, context) {
        if (phase !== "idle") return;
        phase = "posting";
        cancelPoll();
        board.setAttribute("aria-busy", "true");
        feedback.hidden = true;

        let nextState;
        try {
            nextState = await postJSON(url, body);
        } catch (error) {
            board.removeAttribute("aria-busy");
            phase = "idle";
            showError(error.message);
            context.source?.focus();
            schedulePoll();
            if (context.kind === "bot") scheduleBotTurn(1800);
            return;
        }

        phase = "animating";
        try {
            await animateStateChange(initialGameState, nextState, context);
        } catch (_) {
            // Le serveur a accepté le coup : une erreur visuelle ne doit jamais
            // rendre de nouveau interactif un plateau désormais obsolète.
        }
        reloadOnce();
    }

    function schedulePoll(delay = 1500) {
        window.clearTimeout(pollTimer);
        if (reloadRequested) return;
        pollTimer = window.setTimeout(refreshIfGameChanged, delay);
    }

    async function refreshIfGameChanged() {
        if (reloadRequested) return;
        if (document.hidden || phase !== "idle") {
            schedulePoll();
            return;
        }

        pollController = new AbortController();
        try {
            const response = await fetch(stateUrl, { cache: "no-store", signal: pollController.signal });
            if (!response.ok) return;
            const nextState = await response.json();
            if (stateFingerprint(nextState) !== knownStateFingerprint) {
                phase = "animating";
                await animateStateChange(initialGameState, nextState);
                reloadOnce();
                return;
            }
        } catch (error) {
            if (error.name !== "AbortError") {
                // Une indisponibilité ponctuelle sera retentée au prochain poll.
            }
        } finally {
            pollController = null;
            if (phase === "idle") schedulePoll();
        }
    }

    function setTypeChoiceBackgroundInert(isInert) {
        board.querySelectorAll(".arena-stage, .my-hand-row").forEach((element) => {
            element.inert = isInert;
        });
    }

    function closeLegendaryChoices({ restoreFocus = true } = {}) {
        const choices = document.getElementById("legendary-choices");
        choices.hidden = true;
        setTypeChoiceBackgroundInert(false);
        pendingLegendaryCardId = null;
        if (restoreFocus) pendingLegendaryCardElement?.focus();
        pendingLegendaryCardElement = null;
    }

    function openLegendaryChoices(card) {
        pendingLegendaryCardId = card.dataset.playCard;
        pendingLegendaryCardElement = card;
        const choices = document.getElementById("legendary-choices");
        setTypeChoiceBackgroundInert(true);
        choices.hidden = false;
        choices.querySelector("[data-declared-family]")?.focus();
    }

    board.addEventListener("click", (event) => {
        const card = event.target.closest("[data-play-card]");
        if (card) {
            if (card.disabled) return;
            if (card.dataset.requiresFamilyChoice === "true") {
                openLegendaryChoices(card);
            } else {
                submitAction(
                    board.dataset.playUrl,
                    { game_card_id: card.dataset.playCard, declared_family: null },
                    { kind: "play", source: card },
                );
            }
            return;
        }

        if (event.target.closest("[data-draw]")) {
            submitAction(board.dataset.drawUrl, {}, { kind: "draw" });
            return;
        }

        const family = event.target.closest("[data-declared-family]");
        if (family && pendingLegendaryCardId) {
            const source = pendingLegendaryCardElement;
            const gameCardId = pendingLegendaryCardId;
            closeLegendaryChoices({ restoreFocus: false });
            submitAction(
                board.dataset.playUrl,
                { game_card_id: gameCardId, declared_family: family.dataset.declaredFamily },
                { kind: "play", source },
            );
            return;
        }

        if (event.target.closest("[data-cancel-legendary]")) {
            closeLegendaryChoices();
            return;
        }

        const copyButton = event.target.closest("[data-copy-game-url]");
        if (copyButton) copyInvitationLink(copyButton);
    });

    document.addEventListener("keydown", (event) => {
        const choices = document.getElementById("legendary-choices");
        if (!choices || choices.hidden) return;

        if (event.key === "Escape") {
            event.preventDefault();
            closeLegendaryChoices();
            return;
        }

        if (event.key !== "Tab") return;
        const focusable = [...choices.querySelectorAll("button:not(:disabled)")];
        const first = focusable[0];
        const last = focusable[focusable.length - 1];
        if (event.shiftKey && document.activeElement === first) {
            event.preventDefault();
            last.focus();
        } else if (!event.shiftKey && document.activeElement === last) {
            event.preventDefault();
            first.focus();
        }
    });

    async function copyInvitationLink(button) {
        const label = button.querySelector("[data-copy-label]");
        try {
            await navigator.clipboard.writeText(window.location.href);
            label.textContent = "Lien copié";
        } catch (_) {
            label.textContent = "Copie le lien de la barre d’adresse";
        }
        window.setTimeout(() => {
            label.textContent = "Copier le lien d’invitation";
        }, 2200);
    }

    function layoutPlayerHand() {
        const hand = board.querySelector("[data-player-hand]");
        if (!hand) return;
        const cards = [...hand.querySelectorAll(":scope > .card-tilt")];
        const count = cards.length;
        if (!count) return;

        const compact = window.matchMedia("(max-width: 640px)").matches;
        const overlap = compact ? (count <= 7 ? -20 : count <= 11 ? -34 : -46) : count <= 7 ? -24 : count <= 11 ? -38 : -54;
        const center = (count - 1) / 2;
        const denominator = Math.max(center, 1);
        const maximumAngle = Math.min(12, 4 + count * 0.7);
        hand.style.setProperty("--hand-overlap", `${overlap}px`);

        cards.forEach((card, index) => {
            const distance = index - center;
            const normalizedDistance = distance / denominator;
            card.style.setProperty("--fan-angle", `${(normalizedDistance * maximumAngle).toFixed(2)}deg`);
            card.style.setProperty("--fan-y", `${Math.min(20, Math.abs(distance) * 2.8).toFixed(1)}px`);
            card.style.zIndex = String(100 - Math.round(Math.abs(distance)));
        });
    }

    function setupTiltCards() {
        if (reducedMotion.matches || !precisePointer.matches) return;

        board.querySelectorAll("[data-tilt-card]").forEach((card) => {
            let animationFrame = null;
            let bounds = null;
            let pointerX = 0;
            let pointerY = 0;

            function paintTilt() {
                if (!bounds) bounds = card.getBoundingClientRect();
                const normalizedX = Math.min(1, Math.max(0, (pointerX - bounds.left) / bounds.width));
                const normalizedY = Math.min(1, Math.max(0, (pointerY - bounds.top) / bounds.height));
                const tiltY = (normalizedX - 0.5) * 14;
                const tiltX = (normalizedY - 0.5) * -12;
                card.style.setProperty("--tilt-x", `${tiltX.toFixed(2)}deg`);
                card.style.setProperty("--tilt-y", `${tiltY.toFixed(2)}deg`);
                card.style.setProperty("--glare-x", `${(normalizedX * 100).toFixed(1)}%`);
                card.style.setProperty("--glare-y", `${(normalizedY * 100).toFixed(1)}%`);
                animationFrame = null;
            }

            card.addEventListener("pointerenter", () => {
                bounds = card.getBoundingClientRect();
                card.classList.add("is-tilting");
            });
            card.addEventListener("pointermove", (event) => {
                pointerX = event.clientX;
                pointerY = event.clientY;
                if (animationFrame === null) animationFrame = window.requestAnimationFrame(paintTilt);
            });
            card.addEventListener("pointerleave", () => {
                if (animationFrame !== null) window.cancelAnimationFrame(animationFrame);
                animationFrame = null;
                bounds = null;
                card.classList.remove("is-tilting");
                card.style.removeProperty("--tilt-x");
                card.style.removeProperty("--tilt-y");
                card.style.removeProperty("--glare-x");
                card.style.removeProperty("--glare-y");
            });
        });
    }

    function scheduleHandLayout() {
        if (resizeFrame !== null) return;
        resizeFrame = window.requestAnimationFrame(() => {
            resizeFrame = null;
            layoutPlayerHand();
        });
    }

    function scheduleBotTurn(delay = 850) {
        window.clearTimeout(botTurnTimer);
        if (reloadRequested || initialGameState.status !== "EN_COURS") return;
        const currentPlayer = initialGameState.players.find((player) => player.is_current_turn);
        if (!currentPlayer?.is_bot || !board.dataset.botTurnUrl) return;

        botTurnTimer = window.setTimeout(() => {
            if (document.hidden) return;
            if (phase !== "idle") {
                scheduleBotTurn(600);
                return;
            }
            announce(`${currentPlayer.username} réfléchit…`);
            submitAction(
                board.dataset.botTurnUrl,
                { expected_turn_revision: initialGameState.turn_revision },
                { kind: "bot" },
            );
        }, delay);
    }

    layoutPlayerHand();
    setupTiltCards();
    window.addEventListener("resize", scheduleHandLayout, { passive: true });
    schedulePoll();
    scheduleBotTurn();
    document.addEventListener("visibilitychange", () => {
        if (!document.hidden && phase === "idle") {
            cancelPoll();
            schedulePoll(0);
            scheduleBotTurn(300);
        }
    });
})();
