(() => {
    "use strict";

    const root = document.getElementById("rocket-game");
    const initial = document.getElementById("rocket-initial-state");
    const i18nNode = document.getElementById("rocket-i18n");
    if (!root || !initial || !i18nNode) return;

    let messages = {};
    let state;
    try {
        messages = JSON.parse(i18nNode.textContent);
        state = JSON.parse(initial.textContent);
    } catch (_) {
        root.textContent = "The mission could not be loaded. Refresh the page.";
        return;
    }

    function t(key, variables = {}) {
        const template = messages[key] || key;
        return template.replace(/\{(\w+)\}/g, (match, name) => (
            Object.hasOwn(variables, name) ? String(variables[name]) : match
        ));
    }

    const reducedMotion = window.matchMedia("(prefers-reduced-motion: reduce)");
    let busy = false;
    let pollTimer = null;
    let phaseAnimationTimer = null;
    let lastAnnouncement = "";
    let lastStatus = state.game.status;
    let knownAliveIds = new Set(
        state.players.filter((player) => player.is_alive).map((player) => player.id),
    );
    let lastEventSignature = JSON.stringify(state.game.last_event || {});

    const elements = {
        error: root.querySelector("[data-error]"),
        announcer: root.querySelector("[data-announcer]"),
        phasePill: root.querySelector("[data-phase-pill]"),
        phase: root.querySelector("[data-phase]"),
        round: root.querySelector("[data-round]"),
        waiting: root.querySelector("[data-waiting]"),
        board: root.querySelector("[data-board]"),
        minimum: root.querySelector("[data-minimum]"),
        roleArt: root.querySelector("[data-role-art]"),
        roleName: root.querySelector("[data-role-name]"),
        roleSide: root.querySelector("[data-role-side]"),
        roleMission: root.querySelector("[data-role-mission]"),
        detectiveLog: root.querySelector("[data-detective-log]"),
        detectiveResults: root.querySelector("[data-detective-results]"),
        event: root.querySelector("[data-event]"),
        eventText: root.querySelector("[data-event-text]"),
        directiveKicker: root.querySelector("[data-directive-kicker]"),
        directiveTitle: root.querySelector("[data-directive-title]"),
        directiveText: root.querySelector("[data-directive-text]"),
        progress: root.querySelector("[data-progress]"),
        progressBar: root.querySelector("[data-progress-bar]"),
        progressLabel: root.querySelector("[data-progress-label]"),
        aliveCount: root.querySelector("[data-alive-count]"),
        playerCount: root.querySelector("[data-player-count]"),
        playerGrid: root.querySelector("[data-player-grid]"),
        roster: root.querySelector("[data-roster]"),
        chat: root.querySelector("[data-chat]"),
        chatRound: root.querySelector("[data-chat-round]"),
        messages: root.querySelector("[data-messages]"),
        chatForm: root.querySelector("[data-chat-form]"),
        messageInput: root.querySelector("[data-chat-form] input"),
        openVote: root.querySelector("[data-open-vote]"),
        finished: root.querySelector("[data-finished]"),
        winner: root.querySelector("[data-winner]"),
        resultCopy: root.querySelector("[data-result-copy]"),
    };

    function cookie(name) {
        const prefix = `${name}=`;
        return document.cookie
            .split(";")
            .map((value) => value.trim())
            .find((value) => value.startsWith(prefix))
            ?.slice(prefix.length) || "";
    }

    function setHidden(element, hidden) {
        if (element) element.hidden = hidden;
    }

    function showError(message) {
        elements.error.textContent = message || t("general_error");
        elements.error.hidden = false;
    }

    function clearError() {
        elements.error.hidden = true;
        elements.error.textContent = "";
    }

    function announce(message) {
        if (!message || message === lastAnnouncement) return;
        lastAnnouncement = message;
        elements.announcer.textContent = message;
    }

    async function post(url, payload = {}) {
        if (busy) return;
        busy = true;
        clearError();
        root.classList.add("is-busy");
        try {
            const response = await fetch(url, {
                method: "POST",
                headers: {
                    "Content-Type": "application/json",
                    "X-CSRFToken": cookie("csrftoken"),
                },
                body: JSON.stringify({
                    ...payload,
                    expected_turn_revision: state.game.turn_revision,
                }),
            });
            const data = await response.json().catch(() => ({}));
            if (!response.ok) {
                if (data.state) {
                    state = data.state;
                    render();
                }
                throw new Error(data.error || t("action_denied"));
            }
            if (data.state) {
                state = data.state;
                render();
            }
        } catch (error) {
            showError(error.message);
        } finally {
            busy = false;
            root.classList.remove("is-busy");
        }
    }

    function roleIs(player, role) {
        return player.role?.key === role;
    }

    function canTarget(player) {
        if (!player.is_alive || !state.me.is_alive) return false;
        if (state.game.status === "VOTE") return player.id !== state.me.id;
        if (state.game.status !== "NUIT" || !state.me.night_action_kind) return false;
        if (state.me.night_action_kind === "KILL") {
            return player.id !== state.me.id && !roleIs(player, "ROCKET");
        }
        if (state.me.night_action_kind === "INSPECT") return player.id !== state.me.id;
        return state.me.night_action_kind === "PROTECT";
    }

    function targetEndpoint() {
        return state.game.status === "VOTE" ? root.dataset.voteUrl : root.dataset.nightUrl;
    }

    function selectedTargetId() {
        return state.game.status === "VOTE"
            ? state.me.vote_target_id
            : state.me.night_action_target_id;
    }

    function playerSubtitle(player) {
        if (!player.is_alive) return t("eliminated");
        if (player.role) return player.role.name;
        if (player.is_me && state.game.status === "VOTE" && state.vote.own_submitted) {
            return t("vote_saved");
        }
        if (player.is_me) return t("you");
        return t("on_mission");
    }

    function renderPlayerGrid() {
        elements.playerGrid.replaceChildren();
        const selected = selectedTargetId();
        state.players.forEach((player) => {
            const interactive = canTarget(player);
            const card = document.createElement(interactive ? "button" : "div");
            card.dataset.playerId = String(player.id);
            if (interactive) {
                card.type = "button";
                card.addEventListener("click", () => {
                    if (!reducedMotion.matches) {
                        card.classList.add(
                            state.game.status === "VOTE" ? "is-casting-vote" : "is-night-choice",
                        );
                    }
                    post(targetEndpoint(), { target_id: player.id });
                });
            }
            card.className = "rk-agent-card";
            card.classList.toggle("is-dead", !player.is_alive);
            card.classList.toggle("is-selected", selected === player.id);
            if (player.is_me) card.classList.add("is-me");
            if (interactive) {
                card.setAttribute("aria-label", t("choose_player", { player: player.username }));
            }

            const number = document.createElement("span");
            number.className = "rk-agent-number";
            number.textContent = t("agent_number", {
                number: String(player.turn_order + 1).padStart(2, "0"),
            });
            const live = document.createElement("span");
            live.className = "rk-agent-state";
            live.setAttribute("aria-hidden", "true");
            const name = document.createElement("b");
            name.textContent = player.username;
            const subtitle = document.createElement("small");
            subtitle.textContent = playerSubtitle(player);
            card.append(number, live, name, subtitle);
            elements.playerGrid.append(card);
        });
    }

    function renderRoster() {
        elements.roster.replaceChildren();
        state.players.forEach((player) => {
            const item = document.createElement("li");
            item.dataset.playerId = String(player.id);
            item.classList.toggle("is-dead", !player.is_alive);
            const name = document.createElement("b");
            name.textContent = player.username;
            item.append(name);
            if (player.role) {
                const role = document.createElement("small");
                role.textContent = player.role.name;
                item.append(role);
            }
            elements.roster.append(item);
        });
    }

    function renderRole() {
        const role = state.me.role;
        if (!role) return;
        elements.roleArt.src = role.artwork_url;
        elements.roleArt.alt = "";
        elements.roleName.textContent = role.name;
        elements.roleSide.textContent = role.side;
        elements.roleMission.textContent = role.mission;

        const reports = state.night.detective_results || [];
        setHidden(elements.detectiveLog, role.key !== "DETECTIVE");
        elements.detectiveResults.replaceChildren();
        if (role.key === "DETECTIVE") {
            if (!reports.length) {
                const empty = document.createElement("li");
                empty.textContent = t("no_report");
                elements.detectiveResults.append(empty);
            }
            reports.forEach((report) => {
                const item = document.createElement("li");
                item.classList.toggle("is-rocket", report.is_rocket);
                item.textContent = t("night_report", {
                    round: report.round,
                    player: report.target_name,
                    side: report.is_rocket ? "Team Rocket" : t("alliance_short"),
                });
                elements.detectiveResults.append(item);
            });
        }
    }

    function eventDescription(event) {
        if (!event?.kind) return "";
        if (event.kind === "night") {
            if (event.attack_blocked) return t("blocked_event");
            if (event.victim_name) return t("night_elimination", { player: event.victim_name });
            return t("no_victim");
        }
        if (event.tie) return t("vote_tie");
        if (event.eliminated_name) {
            return t("vote_elimination", { player: event.eliminated_name });
        }
        return t("vote_finished");
    }

    function renderDirective() {
        const status = state.game.status;
        const alive = state.me.is_alive;
        elements.progress.hidden = true;
        elements.chat.hidden = true;
        elements.finished.hidden = true;

        if (status === "NUIT") {
            elements.directiveKicker.textContent = t("night_round", { round: state.game.round });
            if (!alive) {
                elements.directiveTitle.textContent = t("observe_title");
                elements.directiveText.textContent = t("observe_text");
            } else if (state.me.night_action_kind === "KILL") {
                elements.directiveTitle.textContent = t("kill_title");
                elements.directiveText.textContent = t("kill_text");
            } else if (state.me.night_action_kind === "INSPECT") {
                elements.directiveTitle.textContent = t("inspect_title");
                elements.directiveText.textContent = t("inspect_text");
            } else if (state.me.night_action_kind === "PROTECT") {
                elements.directiveTitle.textContent = t("protect_title");
                elements.directiveText.textContent = t("protect_text");
            } else {
                elements.directiveTitle.textContent = t("sleep_title");
                elements.directiveText.textContent = t("sleep_text");
            }
            elements.progress.hidden = false;
            elements.progressBar.style.width = state.night.own_submitted ? "100%" : "18%";
            elements.progressLabel.textContent = state.night.own_submitted
                ? t("choice_locked")
                : t("auto_resolution");
        } else if (status === "DISCUSSION") {
            elements.directiveKicker.textContent = t("day_round", { round: state.game.round });
            elements.directiveTitle.textContent = alive ? t("find_title") : t("listen_title");
            elements.directiveText.textContent = alive
                ? t("discussion_alive")
                : t("discussion_dead");
            elements.chat.hidden = false;
        } else if (status === "VOTE") {
            elements.directiveKicker.textContent = t("council");
            elements.directiveTitle.textContent = alive ? t("vote_title") : t("deliberating");
            elements.directiveText.textContent = alive ? t("vote_alive") : t("vote_dead");
            elements.progress.hidden = false;
            const required = Math.max(1, state.vote.required);
            elements.progressBar.style.width = `${Math.min(100, state.vote.submitted / required * 100)}%`;
            elements.progressLabel.textContent = t("ballots", {
                submitted: state.vote.submitted,
                required: state.vote.required,
            });
        } else if (status === "TERMINEE") {
            elements.directiveKicker.textContent = t("declassified");
            elements.directiveTitle.textContent = t("roles_revealed");
            elements.directiveText.textContent = t("rebuild_bluffs");
            elements.finished.hidden = false;
            elements.winner.textContent = t("winner", { side: state.game.winner_label });
            elements.resultCopy.textContent = state.me.team_won ? t("team_won") : t("team_lost");
        }
    }

    function renderChat() {
        elements.chatRound.textContent = state.game.round;
        elements.messages.replaceChildren();
        const chatMessages = state.messages || [];
        if (!chatMessages.length) {
            const empty = document.createElement("li");
            const copy = document.createElement("p");
            copy.textContent = t("chat_empty");
            empty.append(copy);
            elements.messages.append(empty);
        }
        chatMessages.forEach((message) => {
            const item = document.createElement("li");
            const author = document.createElement("strong");
            author.textContent = message.username;
            const time = document.createElement("time");
            time.dateTime = message.created_at;
            time.textContent = new Intl.DateTimeFormat(undefined, {
                hour: "2-digit",
                minute: "2-digit",
            }).format(new Date(message.created_at));
            const body = document.createElement("p");
            body.textContent = message.body;
            item.append(author, time, body);
            elements.messages.append(item);
        });
        elements.messages.scrollTop = elements.messages.scrollHeight;
        elements.chatForm.hidden = !state.me.is_alive;
        elements.openVote.hidden = !state.me.is_alive;
    }

    function animateChanges() {
        const status = state.game.status;
        const eventSignature = JSON.stringify(state.game.last_event || {});
        const eliminated = state.players.filter(
            (player) => !player.is_alive && knownAliveIds.has(player.id),
        );

        if (!reducedMotion.matches && status !== lastStatus) {
            window.clearTimeout(phaseAnimationTimer);
            root.classList.remove(
                "is-phase-changing",
                "phase-night",
                "phase-day",
                "phase-vote",
                "phase-finished",
            );
            void root.offsetWidth;
            const phaseClass = {
                NUIT: "phase-night",
                DISCUSSION: "phase-day",
                VOTE: "phase-vote",
                TERMINEE: "phase-finished",
            }[status];
            if (phaseClass) {
                root.classList.add("is-phase-changing", phaseClass);
                phaseAnimationTimer = window.setTimeout(() => {
                    root.classList.remove("is-phase-changing", phaseClass);
                }, 1050);
            }
        }

        if (!reducedMotion.matches) {
            eliminated.forEach((player) => {
                root.querySelectorAll(`[data-player-id="${player.id}"]`).forEach((element) => {
                    element.classList.add("was-eliminated");
                });
            });
            if (eventSignature !== lastEventSignature && state.game.last_event?.kind) {
                elements.event.classList.remove("is-new-event");
                void elements.event.offsetWidth;
                elements.event.classList.add("is-new-event");
            }
        }

        lastStatus = status;
        lastEventSignature = eventSignature;
        knownAliveIds = new Set(
            state.players.filter((player) => player.is_alive).map((player) => player.id),
        );
    }

    function render() {
        const waiting = state.game.status === "EN_ATTENTE";
        root.dataset.status = state.game.status;
        elements.waiting.hidden = !waiting;
        elements.board.hidden = waiting;
        elements.phase.textContent = state.game.status_label;
        elements.round.textContent = waiting
            ? t("players_count", { count: `${state.players.length}/${state.game.max_players}` })
            : t("cycle", { round: state.game.round });
        elements.phasePill.dataset.status = state.game.status;
        root.querySelectorAll("[data-host-only]").forEach((element) => {
            element.hidden = !state.me.is_host;
        });
        const missing = state.game.min_players - state.players.length;
        elements.minimum.textContent = missing > 0
            ? t(missing === 1 ? "minimum_one" : "minimum_many", { count: missing })
            : t("squad_ready");

        if (waiting) {
            animateChanges();
            announce(t("room_announce", { count: state.players.length }));
            return;
        }

        renderRole();
        renderDirective();
        renderPlayerGrid();
        renderRoster();
        renderChat();
        const alive = state.players.filter((player) => player.is_alive).length;
        elements.aliveCount.textContent = alive === 1
            ? t("survivor_one")
            : t("survivor_many", { count: alive });
        elements.playerCount.textContent = t("players_count", { count: state.players.length });
        const report = eventDescription(state.game.last_event);
        elements.event.hidden = !report;
        elements.eventText.textContent = report;
        animateChanges();
        announce(t("phase_announce", {
            phase: state.game.status_label,
            round: state.game.round,
            report,
        }));
    }

    async function poll() {
        if (busy || document.hidden) return;
        try {
            const response = await fetch(root.dataset.stateUrl, {
                headers: { Accept: "application/json" },
                cache: "no-store",
            });
            if (!response.ok) return;
            const next = await response.json();
            if (next.game.turn_revision !== state.game.turn_revision) {
                state = next;
                render();
            }
        } catch (_) {
            // A later poll resumes automatically after a brief network interruption.
        }
    }

    elements.chatForm?.addEventListener("submit", async (event) => {
        event.preventDefault();
        const body = elements.messageInput.value.trim();
        if (!body) return;
        await post(root.dataset.messageUrl, { body });
        if (!elements.error.hidden) return;
        elements.messageInput.value = "";
        elements.messageInput.focus();
    });
    elements.openVote?.addEventListener("click", (event) => {
        if (!reducedMotion.matches) event.currentTarget.classList.add("is-casting-vote");
        post(root.dataset.startVoteUrl);
    });
    root.querySelector("[data-copy-link]")?.addEventListener("click", async (event) => {
        try {
            await navigator.clipboard.writeText(window.location.href);
            event.currentTarget.textContent = t("link_copied");
        } catch (_) {
            showError(t("copy_failed"));
        }
    });

    render();
    pollTimer = window.setInterval(poll, 1800);
    window.addEventListener("pagehide", () => window.clearInterval(pollTimer), { once: true });
    document.addEventListener("visibilitychange", () => {
        if (!document.hidden) poll();
    });
})();
