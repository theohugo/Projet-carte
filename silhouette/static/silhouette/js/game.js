(function () {
    "use strict";

    const root = document.getElementById("silhouette-game");
    const initialStateElement = document.getElementById("silhouette-initial-state");
    if (!root || !initialStateElement) return;

    const stage = root.querySelector("[data-stage]");
    const waiting = root.querySelector("[data-waiting]");
    const waitingPlayers = root.querySelector("[data-waiting-players]");
    const statusBadge = root.querySelector("[data-status-badge]");
    const roundDots = root.querySelector("[data-round-dots]");
    const frame = root.querySelector("[data-frame]");
    const image = root.querySelector("[data-silhouette]");
    const answer = root.querySelector("[data-answer]");
    const timer = root.querySelector("[data-timer]");
    const timerRing = root.querySelector("[data-timer-ring]");
    const timerProgress = root.querySelector("[data-timer-progress]");
    const roundNumber = root.querySelector("[data-round-number]");
    const hintPending = root.querySelector("[data-hint-pending]");
    const nextHint = root.querySelector("[data-next-hint]");
    const hints = {
        type: root.querySelector('[data-hint="type"]'),
        letters: root.querySelector('[data-hint="letters"]'),
    };
    const guessForm = root.querySelector("[data-guess-form]");
    const guessInput = root.querySelector("[data-guess-input]");
    const guessSubmit = root.querySelector("[data-guess-submit]");
    const myGuesses = root.querySelector("[data-my-guesses]");
    const scores = root.querySelector("[data-scores]");
    const scoresNote = root.querySelector("[data-scores-note]");
    const feedback = document.getElementById("sil-feedback");
    const announcer = document.getElementById("sil-announcer");

    const reducedMotion = window.matchMedia("(prefers-reduced-motion: reduce)");
    const RING_LENGTH = 2 * Math.PI * 44;
    const TYPE_HINT_AFTER = 5;
    const LETTER_HINT_AFTER = 10;

    // Le serveur est la seule horloge qui fasse foi : on interpole entre deux
    // réponses pour que le compte à rebours reste fluide sans dériver.
    let state = JSON.parse(initialStateElement.textContent);
    const t = (french, english) => (state.language === "en" ? english : french);
    let stateReceivedAt = performance.now();
    let pollTimer = null;
    let imageKey = "";
    let revealedRound = null;
    let isSending = false;
    let celebrationTimer = null;

    timerProgress.style.strokeDasharray = String(RING_LENGTH);

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

    function celebrateCorrectGuess() {
        window.clearTimeout(celebrationTimer);
        stage.classList.remove("is-correct-answer");
        guessForm.classList.remove("is-celebrating");
        // Restart the short animation even if two state updates land quickly.
        void stage.offsetWidth;
        stage.classList.add("is-correct-answer");
        guessForm.classList.add("is-celebrating");
        celebrationTimer = window.setTimeout(() => {
            stage.classList.remove("is-correct-answer");
            guessForm.classList.remove("is-celebrating");
        }, reducedMotion.matches ? 100 : 1100);
    }

    function avatar(username, isBot = false) {
        const element = document.createElement("span");
        element.className = `user-avatar${isBot ? " is-bot" : ""}`;
        element.setAttribute("aria-hidden", "true");
        element.textContent = (username[0] || "?").toUpperCase();
        return element;
    }

    function renderWaitingPlayers() {
        if (!waitingPlayers) return;
        const rows = state.players.map((player) => {
            const item = document.createElement("li");
            item.className = "room-player";
            const name = document.createElement("span");
            name.className = "room-player-name";
            name.textContent = player.username;
            const role = document.createElement("small");
            role.textContent = player.is_me
                ? t("C’est toi", "That’s you")
                : player.is_bot
                  ? t("IA · prête", "AI · ready")
                  : t("Prêt à jouer", "Ready to play");
            name.appendChild(role);
            item.append(avatar(player.username, player.is_bot), name);
            return item;
        });
        const seat = document.createElement("li");
        seat.className = "room-player room-seat";
        seat.textContent = t("Place libre — le lien suffit pour rejoindre", "Open seat — use the link to join");
        rows.push(seat);
        waitingPlayers.replaceChildren(...rows);
    }

    function renderRoundDots() {
        const total = state.round_count;
        const current = state.round?.number || 0;
        roundDots.replaceChildren(
            ...Array.from({ length: total }, (_, index) => {
                const dot = document.createElement("li");
                const number = index + 1;
                if (number < current) dot.className = "is-done";
                else if (number === current) dot.className = "is-current";
                return dot;
            }),
        );
    }

    function renderScores() {
        const foundNames = new Set((state.round?.found || []).map((entry) => entry.username));
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

                    item.append(rank, avatar(player.username, player.is_bot), name);
                    if (foundNames.has(player.username)) {
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
                    : `Partie terminée — ${best.username} l’emporte.`
                : "";
        } else {
            scoresNote.textContent = t(
                "Plus tu réponds tôt, plus la manche rapporte.",
                "The faster you answer, the more points the round is worth.",
            );
        }
    }

    function renderHints(round) {
        const typeHint = round?.hints?.type;
        hints.type.hidden = !typeHint;
        if (typeHint) {
            const value = hints.type.querySelector("[data-hint-value]");
            value.replaceChildren(
                ...typeHint.map((pokemonType) => {
                    const item = document.createElement("span");
                    item.className = "sil-type-hint";

                    const icon = document.createElement("img");
                    icon.className = "sil-type-icon";
                    icon.src = pokemonType.icon_url;
                    icon.alt = "";
                    icon.width = 26;
                    icon.height = 26;
                    icon.setAttribute("aria-hidden", "true");

                    const label = document.createElement("span");
                    label.textContent = pokemonType.name;
                    item.append(icon, label);
                    return item;
                }),
            );
        }

        const letters = round?.hints?.letters;
        hints.letters.hidden = !letters;
        if (letters) {
            hints.letters.querySelector("[data-hint-value]").textContent =
                `${letters} (${round.hints.letter_count} ${t("lettres", "letters")})`;
        }
    }

    function renderRound() {
        const round = state.round;
        const isPlaying = state.status === "EN_COURS" && round;
        root.dataset.gameStatus = state.status;
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
        if (!isPlaying) return;

        roundNumber.textContent = `${t("Manche", "Round")} ${round.number} / ${round.total}`;

        // L'URL de l'image ne change pas entre silhouette et révélation : la
        // révision force le rechargement au bon moment.
        const nextKey = `${round.number}:${round.revealed}`;
        if (nextKey !== imageKey) {
            imageKey = nextKey;
            image.src = `${round.image_url}?r=${state.turn_revision}`;
        }

        frame.classList.toggle("is-revealed", round.revealed);
        answer.hidden = !round.revealed;
        if (round.revealed) {
            answer.textContent = state.language === "en" ? `It was ${round.answer}!` : `C’était ${round.answer} !`;
            if (revealedRound !== round.number) {
                revealedRound = round.number;
                announce(state.language === "en" ? `It was ${round.answer}.` : `C’était ${round.answer}.`);
                if (!reducedMotion.matches) {
                    frame.classList.remove("is-popping");
                    void frame.offsetWidth;
                    frame.classList.add("is-popping");
                }
            }
        }

        renderHints(round);

        const canGuess = !round.revealed && !round.i_found;
        guessInput.disabled = !canGuess;
        guessSubmit.disabled = !canGuess;
        guessInput.placeholder = round.i_found
            ? t("Trouvé ! On attend les autres…", "Found! Waiting for the others…")
            : t("Son nom…", "Its name…");
        guessForm.classList.toggle("is-found", Boolean(round.i_found));

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
    }

    function renderTimer() {
        const round = state.round;
        if (!round) return;

        const elapsedSincePoll = (performance.now() - stateReceivedAt) / 1000;
        const secondsLeft = round.revealed ? 0 : Math.max(0, round.seconds_left - elapsedSincePoll);
        timer.textContent = String(Math.ceil(secondsLeft));

        const ratio = Math.max(0, Math.min(1, secondsLeft / round.round_seconds));
        timerProgress.style.strokeDashoffset = String(RING_LENGTH * (1 - ratio));

        // La couleur double l'information du chiffre : jamais la couleur seule.
        const color = secondsLeft <= 5 ? "var(--color-danger)" : secondsLeft <= 12 ? "#f2ce3e" : "var(--color-brand)";
        timerRing.style.setProperty("--timer-color", color);
        timerRing.classList.toggle("is-warning", secondsLeft > 5 && secondsLeft <= 12);
        timerRing.classList.toggle("is-urgent", secondsLeft > 0 && secondsLeft <= 5);
        timerRing.classList.toggle("is-critical", secondsLeft > 0 && secondsLeft <= 3);

        if (hintPending) {
            const elapsed = round.round_seconds - secondsLeft;
            const pending = [TYPE_HINT_AFTER, LETTER_HINT_AFTER].find((moment) => elapsed < moment);
            const showPending = !round.revealed && pending !== undefined;
            hintPending.hidden = !showPending;
            if (showPending) nextHint.textContent = String(Math.ceil(pending - elapsed));
        }
    }

    function applyState(nextState) {
        state = nextState;
        stateReceivedAt = performance.now();
        renderWaitingPlayers();
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
        // Pendant une manche l'affichage suit les indices à la seconde ; en
        // dehors, un rythme lent suffit.
        pollTimer = window.setTimeout(poll, state.status === "EN_COURS" ? 1000 : 2500);
    }

    guessForm.addEventListener("submit", async (event) => {
        event.preventDefault();
        if (isSending) return;
        const text = guessInput.value.trim();
        if (!text) return;

        isSending = true;
        guessSubmit.disabled = true;
        guessSubmit.classList.add("is-busy");
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
                if (!payload.is_correct && !reducedMotion.matches) {
                    guessForm.classList.remove("is-wrong");
                    void guessForm.offsetWidth;
                    guessForm.classList.add("is-wrong");
                }
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
            guessSubmit.classList.remove("is-busy");
            guessSubmit.disabled = guessInput.disabled;
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
