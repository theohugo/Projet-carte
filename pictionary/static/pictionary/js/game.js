(function () {
    "use strict";

    const root = document.getElementById("pictionary-game");
    const initialStateElement = document.getElementById("pictionary-initial-state");
    if (!root || !initialStateElement) return;

    const stage = root.querySelector("[data-stage]");
    const waiting = root.querySelector("[data-waiting]");
    const canvas = root.querySelector("[data-canvas]");
    const context = canvas.getContext("2d");
    const tools = root.querySelector("[data-tools]");
    const board = root.querySelector("[data-board]");
    const reveal = root.querySelector("[data-reveal]");
    const watchBadge = root.querySelector("[data-watch-badge]");
    const watchText = root.querySelector("[data-watch-text]");
    const statusBadge = root.querySelector("[data-status-badge]");
    const roundDots = root.querySelector("[data-round-dots]");
    const waitingPlayers = root.querySelector("[data-waiting-players]");
    const scoresNote = root.querySelector("[data-scores-note]");
    const timerRing = root.querySelector("[data-timer-ring]");
    const timerProgress = root.querySelector("[data-timer-progress]");
    const secretWord = root.querySelector("[data-secret-word]");
    const wordLabel = root.querySelector("[data-word]");
    const turnLabel = root.querySelector("[data-turn]");
    const roundLabel = root.querySelector("[data-round-number]");
    const timer = root.querySelector("[data-timer]");
    const guessForm = root.querySelector("[data-guess-form]");
    const guessInput = root.querySelector("[data-guess-input]");
    const guessSubmit = root.querySelector("[data-guess-submit]");
    const myGuesses = root.querySelector("[data-my-guesses]");
    const scores = root.querySelector("[data-scores]");
    const feedback = document.getElementById("pic-feedback");
    const announcer = document.getElementById("pic-announcer");

    const reducedMotion = window.matchMedia("(prefers-reduced-motion: reduce)");
    const RING_LENGTH = 2 * Math.PI * 44;

    let state = JSON.parse(initialStateElement.textContent);
    const t = (french, english) => (state.language === "en" ? english : french);
    let lastSequence = 0;
    let renderedRound = null;
    let revealedRound = null;
    let renderedStatus = null;
    let secondsLeftAt = performance.now();
    let pollTimer = null;
    let celebrationTimer = null;
    let isSending = false;

    // Trait en cours de tracé : envoyé au serveur quand le doigt/la souris se lève.
    let penColor = "#f6f9ff";
    let penWidth = 8;
    let currentStroke = null;

    function csrfToken() {
        return document.cookie.match(/(?:^|;\s*)csrftoken=([^;]+)/)?.[1] || "";
    }

    function showFeedback(message) {
        if (!feedback) return;
        feedback.textContent = message;
        feedback.hidden = !message;
    }

    function announce(message) {
        if (announcer) announcer.textContent = message;
    }

    function avatar(username) {
        const element = document.createElement("span");
        element.className = "user-avatar";
        element.setAttribute("aria-hidden", "true");
        element.textContent = (username[0] || "?").toUpperCase();
        return element;
    }

    function renderWaitingPlayers() {
        if (!waitingPlayers) return;
        const rows = state.players.map((player, index) => {
            const item = document.createElement("li");
            item.className = "room-player";
            const name = document.createElement("span");
            name.className = "room-player-name";
            name.textContent = player.username;
            const role = document.createElement("small");
            role.textContent = index === 0
                ? t("Premier au crayon", "First to draw")
                : state.language === "en"
                  ? `Draws in round ${index + 1}`
                  : `Dessine à la manche ${index + 1}`;
            name.appendChild(role);
            item.append(avatar(player.username), name);
            return item;
        });
        const seat = document.createElement("li");
        seat.className = "room-player room-seat";
        seat.textContent = t("Place libre — le lien suffit pour rejoindre", "Open seat — use the link to join");
        rows.push(seat);
        waitingPlayers.replaceChildren(...rows);
    }

    function renderRoundDots() {
        if (!roundDots) return;
        const current = state.round?.number || 0;
        roundDots.replaceChildren(
            ...Array.from({ length: state.round_count }, (_, index) => {
                const dot = document.createElement("li");
                const number = index + 1;
                if (number < current) dot.className = "is-done";
                else if (number === current) dot.className = "is-current";
                return dot;
            }),
        );
    }

    function clearCanvas() {
        context.clearRect(0, 0, canvas.width, canvas.height);
    }

    function drawStroke(stroke) {
        if (stroke.is_clear) {
            clearCanvas();
            return;
        }
        const points = stroke.points || [];
        if (!points.length) return;

        context.strokeStyle = stroke.color;
        context.lineWidth = stroke.width;
        context.lineCap = "round";
        context.lineJoin = "round";
        context.beginPath();
        points.forEach(([x, y], index) => {
            const pixelX = x * canvas.width;
            const pixelY = y * canvas.height;
            if (index === 0) context.moveTo(pixelX, pixelY);
            else context.lineTo(pixelX, pixelY);
        });
        if (points.length === 1) {
            // Un point isolé : un trait de longueur nulle ne dessine rien.
            context.lineTo(points[0][0] * canvas.width + 0.1, points[0][1] * canvas.height);
        }
        context.stroke();
    }

    function renderScores() {
        const round = state.round;
        const foundNames = new Set((round?.found || []).map((entry) => entry.username));
        scores.replaceChildren(
            ...[...state.players]
                .sort((a, b) => b.score - a.score)
                .map((player, index) => {
                    const item = document.createElement("li");
                    item.className = "score-row";
                    if (player.is_me) item.classList.add("is-me");
                    if (foundNames.has(player.username)) item.classList.add("is-found");

                    const rank = document.createElement("span");
                    rank.className = "score-rank";
                    rank.textContent = String(index + 1);

                    const name = document.createElement("span");
                    name.className = "score-name";
                    name.textContent = player.username;

                    const points = document.createElement("span");
                    points.className = "score-points";
                    points.textContent = `${player.score} pts`;

                    item.append(rank, avatar(player.username), name);
                    if (round && !round.am_drawer && round.drawer === player.username) {
                        const flag = document.createElement("span");
                        flag.className = "score-found-flag";
                        flag.textContent = t("dessine", "drawing");
                        item.appendChild(flag);
                    } else if (foundNames.has(player.username)) {
                        const flag = document.createElement("span");
                        flag.className = "score-found-flag";
                        flag.textContent = t("trouvé", "found");
                        item.appendChild(flag);
                    }
                    item.appendChild(points);
                    return item;
                }),
        );

        if (!scoresNote) return;
        if (state.status === "TERMINEE") {
            const best = [...state.players].sort((a, b) => b.score - a.score)[0];
            scoresNote.textContent = best
                ? state.language === "en"
                    ? `Game over — ${best.username} wins.`
                    : `Partie terminée — ${best.username} l'emporte.`
                : "";
        } else {
            scoresNote.textContent = t(
                "Le dessinateur marque à chaque joueur qui trouve.",
                "The artist scores for every player who guesses correctly.",
            );
        }
    }

    function renderRound() {
        const round = state.round;
        const isActive = state.status === "EN_COURS";
        const isPlaying = isActive && round;
        const statusChanged = renderedStatus !== state.status;
        root.dataset.gameStatus = state.status || "";
        document.documentElement.classList.toggle("pic-game-document--active", isActive);
        document.body.classList.toggle("pic-game-shell--active", isActive);
        stage.hidden = !isPlaying;
        waiting.hidden = state.status !== "EN_ATTENTE";
        if (statusBadge) {
            statusBadge.textContent =
                {
                    EN_ATTENTE: t("En attente", "Waiting"),
                    EN_COURS: t("En cours", "In progress"),
                    TERMINEE: t("Terminée", "Finished"),
                }[state.status] || "";
            statusBadge.dataset.status = state.status.toLowerCase();
        }
        renderRoundDots();
        if (!isPlaying) {
            renderedStatus = state.status;
            return;
        }

        if (statusChanged && !reducedMotion.matches) {
            stage.classList.remove("is-entering");
            void stage.offsetWidth;
            stage.classList.add("is-entering");
        }
        renderedStatus = state.status;

        // Nouvelle manche : la toile repart vierge et le curseur de traits aussi.
        if (renderedRound !== round.number) {
            renderedRound = round.number;
            lastSequence = 0;
            clearCanvas();
            board.classList.remove("is-round-entering");
            if (!reducedMotion.matches) {
                void board.offsetWidth;
                board.classList.add("is-round-entering");
            }
        }

        roundLabel.textContent = `${t("Manche", "Round")} ${round.number} / ${round.total}`;
        turnLabel.textContent = round.am_drawer
            ? t("À toi de dessiner", "Your turn to draw")
            : state.language === "en"
              ? `${round.drawer} is drawing`
              : `${round.drawer} dessine`;

        tools.hidden = !round.am_drawer || round.ended;
        board.classList.toggle("is-drawing", Boolean(round.am_drawer) && !round.ended);
        if (round.am_drawer && round.word) secretWord.textContent = round.word;

        // Les devineurs ont besoin de savoir que la toile est vivante même
        // quand le dessinateur réfléchit : un badge « en direct » le dit.
        if (watchBadge) {
            watchBadge.hidden = round.am_drawer || round.ended;
            if (watchText) {
                watchText.textContent = state.language === "en" ? `${round.drawer} is drawing` : `${round.drawer} dessine`;
            }
        }

        reveal.hidden = !round.ended;
        if (round.ended) {
            wordLabel.textContent = round.word;
            if (revealedRound !== round.number && !reducedMotion.matches) {
                revealedRound = round.number;
                reveal.classList.remove("is-popping");
                void reveal.offsetWidth;
                reveal.classList.add("is-popping");
            }
        } else {
            reveal.classList.remove("is-popping");
        }

        const canGuess = !round.am_drawer && !round.ended && !round.i_found;
        guessForm.hidden = round.am_drawer;
        guessForm.classList.toggle("is-found", Boolean(round.i_found));
        guessInput.disabled = !canGuess;
        guessSubmit.disabled = !canGuess;
        guessInput.placeholder = round.i_found
            ? t("Trouvé ! On attend les autres…", "Found! Waiting for the others…")
            : t("C’est quel Pokémon ?", "Which Pokémon is it?");

        myGuesses.replaceChildren(
            ...round.my_guesses
                .slice()
                .reverse()
                .map((guess) => {
                    const item = document.createElement("li");
                    item.className = guess.is_correct ? "is-correct" : "is-wrong";
                    item.textContent = guess.is_correct
                        ? `${guess.text} — +${guess.points} pts`
                        : guess.text;
                    return item;
                }),
        );

        round.strokes.forEach(drawStroke);
        if (round.strokes.length) {
            lastSequence = round.strokes[round.strokes.length - 1].sequence;
        } else if (round.last_sequence < lastSequence) {
            lastSequence = round.last_sequence;
        }
    }

    function renderTimer() {
        const round = state.round;
        if (!round) return;

        const elapsedSincePoll = (performance.now() - secondsLeftAt) / 1000;
        const secondsLeft = round.ended ? 0 : Math.max(0, round.seconds_left - elapsedSincePoll);
        timer.textContent = String(Math.ceil(secondsLeft));

        const ratio = Math.max(0, Math.min(1, secondsLeft / round.round_seconds));
        timerProgress.style.strokeDashoffset = String(RING_LENGTH * (1 - ratio));

        // Couleur + chiffre : l'urgence ne repose jamais sur la seule couleur.
        const color =
            secondsLeft <= 10 ? "var(--color-danger)" : secondsLeft <= 30 ? "#ffd166" : "var(--color-accent)";
        timerRing.style.setProperty("--timer-color", color);
        timerRing.classList.toggle("is-warning", secondsLeft > 10 && secondsLeft <= 30);
        timerRing.classList.toggle("is-urgent", secondsLeft > 0 && secondsLeft <= 10);
    }

    function celebrateCorrectGuess() {
        if (reducedMotion.matches) return;
        window.clearTimeout(celebrationTimer);
        root.classList.remove("is-correct-answer");
        void root.offsetWidth;
        root.classList.add("is-correct-answer");
        celebrationTimer = window.setTimeout(() => {
            root.classList.remove("is-correct-answer");
        }, 900);
    }

    function applyState(nextState) {
        const previousRound = state.round;
        state = nextState;
        secondsLeftAt = performance.now();
        renderWaitingPlayers();
        renderScores();
        renderRound();
        renderTimer();
        if (state.round?.ended && previousRound && !previousRound.ended) {
            announce(
                state.language === "en"
                    ? `Round over: it was ${state.round.word}.`
                    : `Manche terminée : c'était ${state.round.word}.`,
            );
        }
    }

    async function poll() {
        try {
            const response = await fetch(`${root.dataset.stateUrl}?since=${lastSequence}`, {
                headers: { "X-Requested-With": "XMLHttpRequest" },
            });
            if (response.ok) applyState(await response.json());
        } catch (_) {
            // Réessai au prochain tour.
        } finally {
            schedulePoll();
        }
    }

    function schedulePoll() {
        window.clearTimeout(pollTimer);
        // Le dessin doit apparaître presque en direct chez les devineurs ; le
        // dessinateur, lui, voit déjà son trait localement.
        const round = state.round;
        const isWatching = state.status === "EN_COURS" && round && !round.am_drawer && !round.ended;
        pollTimer = window.setTimeout(poll, isWatching ? 700 : 2000);
    }

    // -- Dessin -------------------------------------------------------------

    function canDraw() {
        const round = state.round;
        return Boolean(round && round.am_drawer && !round.ended && state.status === "EN_COURS");
    }

    function pointFromEvent(event) {
        const bounds = canvas.getBoundingClientRect();
        return [
            Math.min(1, Math.max(0, (event.clientX - bounds.left) / bounds.width)),
            Math.min(1, Math.max(0, (event.clientY - bounds.top) / bounds.height)),
        ];
    }

    async function sendStroke(payload) {
        try {
            const response = await fetch(root.dataset.strokeUrl, {
                method: "POST",
                headers: {
                    "Content-Type": "application/json",
                    "X-CSRFToken": csrfToken(),
                    "X-Requested-With": "XMLHttpRequest",
                },
                body: JSON.stringify(payload),
            });
            if (response.ok) {
                const { sequence } = await response.json();
                // Le trait est déjà tracé localement : on avance le curseur pour
                // ne pas le redessiner au prochain poll.
                lastSequence = Math.max(lastSequence, sequence);
            }
        } catch (_) {
            showFeedback(t("Un trait n'a pas pu être envoyé.", "A stroke could not be sent."));
        }
    }

    canvas.addEventListener("pointerdown", (event) => {
        if (!canDraw()) return;
        canvas.setPointerCapture(event.pointerId);
        currentStroke = { points: [pointFromEvent(event)], color: penColor, width: penWidth };
    });

    canvas.addEventListener("pointermove", (event) => {
        if (!currentStroke) return;
        const point = pointFromEvent(event);
        currentStroke.points.push(point);
        drawStroke({ points: currentStroke.points.slice(-2), color: penColor, width: penWidth });
    });

    function finishStroke() {
        if (!currentStroke) return;
        const stroke = currentStroke;
        currentStroke = null;
        if (!stroke.points.length) return;
        sendStroke(stroke);
    }

    canvas.addEventListener("pointerup", finishStroke);
    canvas.addEventListener("pointercancel", finishStroke);
    canvas.addEventListener("pointerleave", finishStroke);

    function selectTool(buttons, button, apply) {
        apply();
        buttons.forEach((other) => {
            const isActive = other === button;
            other.classList.toggle("is-active", isActive);
            other.setAttribute("aria-pressed", String(isActive));
        });
    }

    const colorButtons = [...root.querySelectorAll("[data-color]")];
    colorButtons.forEach((button) => {
        button.addEventListener("click", () => {
            selectTool(colorButtons, button, () => {
                penColor = button.dataset.color;
            });
        });
    });

    const sizeButtons = [...root.querySelectorAll("[data-size]")];
    sizeButtons.forEach((button) => {
        button.addEventListener("click", () => {
            selectTool(sizeButtons, button, () => {
                penWidth = Number(button.dataset.size) || 8;
            });
        });
    });

    root.querySelector("[data-clear]").addEventListener("click", () => {
        if (!canDraw()) return;
        clearCanvas();
        sendStroke({ is_clear: true });
    });

    // -- Propositions -------------------------------------------------------

    guessForm.addEventListener("submit", async (event) => {
        event.preventDefault();
        if (isSending) return;
        const text = guessInput.value.trim();
        if (!text) return;

        isSending = true;
        guessSubmit.disabled = true;
        showFeedback("");
        try {
            const response = await fetch(root.dataset.guessUrl, {
                method: "POST",
                headers: {
                    "Content-Type": "application/json",
                    "X-CSRFToken": csrfToken(),
                    "X-Requested-With": "XMLHttpRequest",
                },
                body: JSON.stringify({ text, expected_turn_revision: state.turn_revision }),
            });
            const payload = await response.json();
            if (response.ok) {
                guessInput.value = "";
                applyState(payload.state);
                if (payload.is_correct) celebrateCorrectGuess();
                announce(
                    payload.is_correct
                        ? state.language === "en"
                            ? `Found it, +${payload.points} points.`
                            : `Trouvé, +${payload.points} points.`
                        : t("Raté.", "Wrong guess."),
                );
            } else if (payload.state) {
                applyState(payload.state);
                showFeedback(payload.error || "");
            } else {
                showFeedback(payload.error || t("Impossible d'envoyer la proposition.", "Could not send the guess."));
            }
        } catch (_) {
            showFeedback(t("Connexion perdue, réessaie.", "Connection lost. Try again."));
        } finally {
            isSending = false;
            guessInput.focus();
        }
    });

    root.querySelector("[data-copy-link]")?.addEventListener("click", async (event) => {
        const button = event.currentTarget;
        const label = button.querySelector("[data-copy-label]");
        try {
            await navigator.clipboard.writeText(window.location.href);
            label.textContent = t("Lien copié", "Link copied");
        } catch (_) {
            label.textContent = window.location.href;
        }
        window.setTimeout(() => {
            label.textContent = t("Copier le lien d’invitation", "Copy invitation link");
        }, 2500);
    });

    timerProgress.style.strokeDasharray = String(RING_LENGTH);
    applyState(state);
    window.setInterval(renderTimer, 200);
    schedulePoll();
    document.addEventListener("visibilitychange", () => {
        if (!document.hidden) {
            window.clearTimeout(pollTimer);
            poll();
        }
    });
})();
