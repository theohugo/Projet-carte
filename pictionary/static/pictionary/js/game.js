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
    const secretWord = root.querySelector("[data-secret-word]");
    const wordLabel = root.querySelector("[data-word]");
    const turnLabel = root.querySelector("[data-turn]");
    const roundLabel = root.querySelector("[data-round-number]");
    const timer = root.querySelector("[data-timer]");
    const guessForm = root.querySelector("[data-guess-form]");
    const guessInput = root.querySelector("[data-guess-input]");
    const guessSubmit = root.querySelector("[data-guess-submit]");
    const myGuesses = root.querySelector("[data-my-guesses]");
    const found = root.querySelector("[data-found]");
    const scores = root.querySelector("[data-scores]");
    const widthInput = root.querySelector("[data-width]");
    const feedback = document.getElementById("pic-feedback");
    const announcer = document.getElementById("pic-announcer");

    let state = JSON.parse(initialStateElement.textContent);
    let lastSequence = 0;
    let renderedRound = null;
    let secondsLeftAt = performance.now();
    let pollTimer = null;
    let isSending = false;

    // Trait en cours de tracé : envoyé au serveur quand le doigt/la souris se lève.
    let penColor = "#f6f9ff";
    let penWidth = 5;
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
        scores.replaceChildren(
            ...[...state.players]
                .sort((a, b) => b.score - a.score)
                .map((player) => {
                    const item = document.createElement("li");
                    item.className = player.is_me ? "is-me" : "";
                    const name = document.createElement("span");
                    name.textContent = player.username;
                    const score = document.createElement("strong");
                    score.textContent = `${player.score} pts`;
                    item.append(name, score);
                    return item;
                }),
        );
    }

    function renderRound() {
        const round = state.round;
        const isPlaying = state.status === "EN_COURS" && round;
        stage.hidden = !isPlaying;
        waiting.hidden = state.status !== "EN_ATTENTE";
        if (!isPlaying) return;

        // Nouvelle manche : la toile repart vierge et le curseur de traits aussi.
        if (renderedRound !== round.number) {
            renderedRound = round.number;
            lastSequence = 0;
            clearCanvas();
        }

        roundLabel.textContent = `Manche ${round.number} / ${round.total}`;
        turnLabel.textContent = round.am_drawer ? "À toi de dessiner" : `${round.drawer} dessine`;

        tools.hidden = !round.am_drawer || round.ended;
        if (round.am_drawer && round.word) secretWord.textContent = round.word;

        wordLabel.hidden = !round.ended;
        if (round.ended) wordLabel.textContent = `C'était ${round.word} !`;

        const canGuess = !round.am_drawer && !round.ended && !round.i_found;
        guessForm.hidden = round.am_drawer;
        guessInput.disabled = !canGuess;
        guessSubmit.disabled = !canGuess;
        guessInput.placeholder = round.i_found ? "Trouvé !" : "C’est quel Pokémon ?";

        myGuesses.replaceChildren(
            ...round.my_guesses.map((guess) => {
                const item = document.createElement("li");
                item.className = guess.is_correct ? "is-correct" : "is-wrong";
                item.textContent = guess.is_correct ? `${guess.text} — +${guess.points} pts` : guess.text;
                return item;
            }),
        );

        found.replaceChildren(
            ...round.found.map((entry) => {
                const item = document.createElement("li");
                item.textContent = `${entry.username} — ${entry.seconds}s · +${entry.points} pts`;
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
        if (!round || round.ended) {
            timer.textContent = "0";
            return;
        }
        const elapsed = (performance.now() - secondsLeftAt) / 1000;
        timer.textContent = String(Math.max(0, Math.round(round.seconds_left - elapsed)));
    }

    function applyState(nextState) {
        const previousRound = state.round;
        state = nextState;
        secondsLeftAt = performance.now();
        renderScores();
        renderRound();
        renderTimer();
        if (state.round?.ended && previousRound && !previousRound.ended) {
            announce(`Manche terminée : c'était ${state.round.word}.`);
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
            showFeedback("Un trait n'a pas pu être envoyé.");
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

    root.querySelectorAll("[data-color]").forEach((button) => {
        button.addEventListener("click", () => {
            penColor = button.dataset.color;
            root.querySelectorAll("[data-color]").forEach((other) => {
                other.classList.toggle("is-active", other === button);
            });
        });
    });

    widthInput.addEventListener("input", () => {
        penWidth = Number(widthInput.value) || 5;
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
                announce(payload.is_correct ? `Trouvé, +${payload.points} points.` : "Raté.");
            } else if (payload.state) {
                applyState(payload.state);
                showFeedback(payload.error || "");
            } else {
                showFeedback(payload.error || "Impossible d'envoyer la proposition.");
            }
        } catch (_) {
            showFeedback("Connexion perdue, réessaie.");
        } finally {
            isSending = false;
            guessInput.focus();
        }
    });

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
