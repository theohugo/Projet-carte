(function () {
    "use strict";

    const root = document.getElementById("silhouette-game");
    const initialStateElement = document.getElementById("silhouette-initial-state");
    if (!root || !initialStateElement) return;

    const stage = root.querySelector("[data-stage]");
    const waiting = root.querySelector("[data-waiting]");
    const image = root.querySelector("[data-silhouette]");
    const answer = root.querySelector("[data-answer]");
    const timer = root.querySelector("[data-timer]");
    const roundNumber = root.querySelector("[data-round-number]");
    const hints = {
        type: root.querySelector('[data-hint="type"]'),
        letters: root.querySelector('[data-hint="letters"]'),
    };
    const guessForm = root.querySelector("[data-guess-form]");
    const guessInput = root.querySelector("[data-guess-input]");
    const guessSubmit = root.querySelector("[data-guess-submit]");
    const myGuesses = root.querySelector("[data-my-guesses]");
    const found = root.querySelector("[data-found]");
    const scores = root.querySelector("[data-scores]");
    const feedback = document.getElementById("sil-feedback");
    const announcer = document.getElementById("sil-announcer");

    // Le serveur est la seule horloge qui compte : on ne fait qu'interpoler
    // entre deux réponses pour que le compte à rebours reste fluide.
    let state = JSON.parse(initialStateElement.textContent);
    let secondsLeftAt = performance.now();
    let pollTimer = null;
    let imageKey = "";
    let isSending = false;

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

    function renderHints(round) {
        const typeHint = round?.hints?.type;
        hints.type.hidden = !typeHint;
        if (typeHint) hints.type.textContent = `Type : ${typeHint.join(" / ")}`;

        const letters = round?.hints?.letters;
        hints.letters.hidden = !letters;
        if (letters) {
            hints.letters.textContent = `${round.hints.letter_count} lettres : ${letters}`;
        }
    }

    function renderRound() {
        const round = state.round;
        const isPlaying = state.status === "EN_COURS" && round;
        stage.hidden = !isPlaying;
        waiting.hidden = state.status !== "EN_ATTENTE";

        if (!isPlaying) {
            if (state.status === "TERMINEE") announce("Partie terminée.");
            return;
        }

        roundNumber.textContent = `Manche ${round.number} / ${round.total}`;

        // L'URL ne change pas entre la silhouette et la révélation : on force
        // le rechargement avec la révision, sinon le navigateur garderait
        // l'image noire affichée.
        const nextKey = `${round.number}:${round.revealed}`;
        if (nextKey !== imageKey) {
            imageKey = nextKey;
            image.src = `${round.image_url}?r=${state.turn_revision}`;
        }
        image.classList.toggle("is-revealed", round.revealed);

        answer.hidden = !round.revealed;
        if (round.revealed) {
            answer.textContent = `C'était ${round.answer} !`;
            announce(`C'était ${round.answer}.`);
        }

        renderHints(round);

        guessInput.disabled = round.revealed || round.i_found;
        guessSubmit.disabled = guessInput.disabled;
        guessInput.placeholder = round.i_found ? "Trouvé !" : "Son nom…";

        myGuesses.replaceChildren(
            ...round.my_guesses.map((guess) => {
                const item = document.createElement("li");
                item.className = guess.is_correct ? "is-correct" : "is-wrong";
                item.textContent = guess.is_correct
                    ? `${guess.text} — +${guess.points} pts`
                    : guess.text;
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
    }

    function renderTimer() {
        const round = state.round;
        if (!round || round.revealed) {
            timer.textContent = "0";
            return;
        }
        const elapsed = (performance.now() - secondsLeftAt) / 1000;
        timer.textContent = String(Math.max(0, Math.round(round.seconds_left - elapsed)));
    }

    function applyState(nextState) {
        state = nextState;
        secondsLeftAt = performance.now();
        renderScores();
        renderRound();
        renderTimer();
    }

    async function poll() {
        try {
            const response = await fetch(root.dataset.stateUrl, {
                headers: { "X-Requested-With": "XMLHttpRequest" },
            });
            if (response.ok) applyState(await response.json());
        } catch (_) {
            // Une coupure ponctuelle sera rattrapée au prochain tour de poll.
        } finally {
            schedulePoll();
        }
    }

    function schedulePoll() {
        window.clearTimeout(pollTimer);
        // Pendant une manche, l'affichage doit suivre les indices à la seconde ;
        // en dehors, un rythme lent suffit.
        const delay = state.status === "EN_COURS" ? 1000 : 2500;
        pollTimer = window.setTimeout(poll, delay);
    }

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
            guessSubmit.disabled = guessInput.disabled;
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
