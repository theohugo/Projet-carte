(() => {
    "use strict";

    const root = document.getElementById("rocket-game");
    const initial = document.getElementById("rocket-initial-state");
    if (!root || !initial) return;

    let state = JSON.parse(initial.textContent);
    let busy = false;
    let pollTimer = null;
    let lastAnnouncement = "";

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
        return document.cookie.split(";").map((value) => value.trim()).find((value) => value.startsWith(prefix))?.slice(prefix.length) || "";
    }

    function setHidden(element, hidden) {
        if (element) element.hidden = hidden;
    }

    function showError(message) {
        elements.error.textContent = message || "Une erreur est survenue.";
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
                headers: { "Content-Type": "application/json", "X-CSRFToken": cookie("csrftoken") },
                body: JSON.stringify({ ...payload, expected_turn_revision: state.game.turn_revision }),
            });
            const data = await response.json().catch(() => ({}));
            if (!response.ok) {
                if (data.state) {
                    state = data.state;
                    render();
                }
                throw new Error(data.error || "Action refusée.");
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
        if (state.me.night_action_kind === "KILL") return player.id !== state.me.id && !roleIs(player, "ROCKET");
        if (state.me.night_action_kind === "INSPECT") return player.id !== state.me.id;
        return state.me.night_action_kind === "PROTECT";
    }

    function targetEndpoint() {
        return state.game.status === "VOTE" ? root.dataset.voteUrl : root.dataset.nightUrl;
    }

    function selectedTargetId() {
        return state.game.status === "VOTE" ? state.me.vote_target_id : state.me.night_action_target_id;
    }

    function playerSubtitle(player) {
        if (!player.is_alive) return "Éliminé";
        if (player.role) return player.role.name;
        if (player.is_me && state.game.status === "VOTE" && state.vote.own_submitted) return "Vote enregistré";
        if (player.is_me) return "Toi";
        return "En mission";
    }

    function renderPlayerGrid() {
        elements.playerGrid.replaceChildren();
        const selected = selectedTargetId();
        state.players.forEach((player) => {
            const interactive = canTarget(player);
            const card = document.createElement(interactive ? "button" : "div");
            if (interactive) {
                card.type = "button";
                card.addEventListener("click", () => post(targetEndpoint(), { target_id: player.id }));
            }
            card.className = "rk-agent-card";
            card.classList.toggle("is-dead", !player.is_alive);
            card.classList.toggle("is-selected", selected === player.id);
            if (player.is_me) card.classList.add("is-me");
            if (interactive) card.setAttribute("aria-label", `Choisir ${player.username}`);

            const number = document.createElement("span");
            number.className = "rk-agent-number";
            number.textContent = `AGENT ${String(player.turn_order + 1).padStart(2, "0")}`;
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
                empty.textContent = "Aucun rapport pour l’instant.";
                elements.detectiveResults.append(empty);
            }
            reports.forEach((report) => {
                const item = document.createElement("li");
                item.classList.toggle("is-rocket", report.is_rocket);
                item.textContent = `Nuit ${report.round} · ${report.target_name} : ${report.is_rocket ? "Team Rocket" : "Alliance"}`;
                elements.detectiveResults.append(item);
            });
        }
    }

    function eventDescription(event) {
        if (!event?.kind) return "";
        if (event.kind === "night") {
            if (event.attack_blocked) return "Le sabotage de la Team Rocket a été bloqué pendant la nuit.";
            if (event.victim_name) return `${event.victim_name} a été éliminé pendant la nuit.`;
            return "La nuit s’est achevée sans victime.";
        }
        if (event.tie) return "Le conseil s’est terminé sur une égalité : personne n’est éliminé.";
        if (event.eliminated_name) return `${event.eliminated_name} a été éliminé par le conseil.`;
        return "Le vote est terminé.";
    }

    function renderDirective() {
        const status = state.game.status;
        const alive = state.me.is_alive;
        elements.progress.hidden = true;
        elements.chat.hidden = true;
        elements.finished.hidden = true;

        if (status === "NUIT") {
            elements.directiveKicker.textContent = `Nuit ${state.game.round}`;
            if (!alive) {
                elements.directiveTitle.textContent = "Observe la mission.";
                elements.directiveText.textContent = "Tu es éliminé : les actions restantes se déroulent sans toi.";
            } else if (state.me.night_action_kind === "KILL") {
                elements.directiveTitle.textContent = "Choisis une cible à saboter.";
                elements.directiveText.textContent = "Les agents Rocket votent pendant la nuit. En cas d’égalité, la cible la plus ancienne dans l’escouade est retenue.";
            } else if (state.me.night_action_kind === "INSPECT") {
                elements.directiveTitle.textContent = "Ouvre une enquête secrète.";
                elements.directiveText.textContent = "Choisis un joueur : son camp sera ajouté à tes rapports privés.";
            } else if (state.me.night_action_kind === "PROTECT") {
                elements.directiveTitle.textContent = "Place ta protection.";
                elements.directiveText.textContent = "Choisis n’importe quel survivant, toi compris. Une attaque contre lui sera annulée.";
            } else {
                elements.directiveTitle.textContent = "La ville s’endort…";
                elements.directiveText.textContent = "Ton rôle n’agit pas la nuit. Attends que les rôles spéciaux terminent leur mission.";
            }
            elements.progress.hidden = false;
            elements.progressBar.style.width = state.night.own_submitted ? "100%" : "18%";
            elements.progressLabel.textContent = state.night.own_submitted ? "Ton choix est verrouillé · attente des autres rôles" : "Résolution automatique à la fin du délai";
        } else if (status === "DISCUSSION") {
            elements.directiveKicker.textContent = `Jour ${state.game.round}`;
            elements.directiveTitle.textContent = alive ? "Débusque les infiltrés." : "Écoute le débat.";
            elements.directiveText.textContent = alive ? "Compare les versions, partage tes indices sans dévoiler trop vite ton rôle, puis laisse l’hôte ouvrir le conseil." : "Tu peux lire les échanges, mais les joueurs éliminés ne peuvent plus intervenir.";
            elements.chat.hidden = false;
        } else if (status === "VOTE") {
            elements.directiveKicker.textContent = "Conseil en cours";
            elements.directiveTitle.textContent = alive ? "Vote contre un suspect." : "Le conseil délibère.";
            elements.directiveText.textContent = alive ? "Ton bulletin reste secret jusqu’à la résolution. Tu peux changer de cible tant que tous les survivants n’ont pas voté." : "Les survivants choisissent le prochain joueur éliminé.";
            elements.progress.hidden = false;
            const required = Math.max(1, state.vote.required);
            elements.progressBar.style.width = `${Math.min(100, state.vote.submitted / required * 100)}%`;
            elements.progressLabel.textContent = `${state.vote.submitted}/${state.vote.required} bulletins déposés`;
        } else if (status === "TERMINEE") {
            elements.directiveKicker.textContent = "Dossiers déclassifiés";
            elements.directiveTitle.textContent = "Tous les rôles sont révélés.";
            elements.directiveText.textContent = "L’escouade peut maintenant reconstituer chaque bluff de la mission.";
            elements.finished.hidden = false;
            elements.winner.textContent = `${state.game.winner_label} gagne`;
            elements.resultCopy.textContent = state.me.team_won ? "Ton camp remporte cette infiltration." : "Ton camp a été démasqué. La revanche t’attend.";
        }
    }

    function renderChat() {
        elements.chatRound.textContent = state.game.round;
        elements.messages.replaceChildren();
        const messages = state.messages || [];
        if (!messages.length) {
            const empty = document.createElement("li");
            const copy = document.createElement("p");
            copy.textContent = "Le canal est silencieux. Qui prendra la parole en premier ?";
            empty.append(copy);
            elements.messages.append(empty);
        }
        messages.forEach((message) => {
            const item = document.createElement("li");
            const author = document.createElement("strong");
            author.textContent = message.username;
            const time = document.createElement("time");
            time.dateTime = message.created_at;
            time.textContent = new Intl.DateTimeFormat(undefined, { hour: "2-digit", minute: "2-digit" }).format(new Date(message.created_at));
            const body = document.createElement("p");
            body.textContent = message.body;
            item.append(author, time, body);
            elements.messages.append(item);
        });
        elements.messages.scrollTop = elements.messages.scrollHeight;
        elements.chatForm.hidden = !state.me.is_alive;
        elements.openVote.hidden = !state.me.is_alive;
    }

    function render() {
        const waiting = state.game.status === "EN_ATTENTE";
        elements.waiting.hidden = !waiting;
        elements.board.hidden = waiting;
        elements.phase.textContent = state.game.status_label;
        elements.round.textContent = waiting ? `${state.players.length}/${state.game.max_players} joueurs` : `Cycle ${state.game.round}`;
        elements.phasePill.dataset.status = state.game.status;
        root.querySelectorAll("[data-host-only]").forEach((element) => { element.hidden = !state.me.is_host; });
        elements.minimum.textContent = state.players.length < state.game.min_players ? `${state.game.min_players - state.players.length} joueur(s) encore nécessaire(s) pour démarrer.` : "Escouade suffisante : l’hôte peut lancer la mission.";

        if (waiting) {
            announce(`${state.players.length} joueurs dans le salon.`);
            return;
        }

        renderRole();
        renderDirective();
        renderPlayerGrid();
        renderRoster();
        renderChat();
        const alive = state.players.filter((player) => player.is_alive).length;
        elements.aliveCount.textContent = `${alive} survivant${alive > 1 ? "s" : ""}`;
        elements.playerCount.textContent = `${state.players.length} joueurs`;
        const report = eventDescription(state.game.last_event);
        elements.event.hidden = !report;
        elements.eventText.textContent = report;
        announce(`${state.game.status_label}, cycle ${state.game.round}. ${report}`);
    }

    async function poll() {
        if (busy || document.hidden) return;
        try {
            const response = await fetch(root.dataset.stateUrl, { headers: { Accept: "application/json" }, cache: "no-store" });
            if (!response.ok) return;
            const next = await response.json();
            if (next.game.turn_revision !== state.game.turn_revision) {
                state = next;
                render();
            }
        } catch (_) {
            // Le prochain polling reprendra automatiquement après une coupure brève.
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
    elements.openVote?.addEventListener("click", () => post(root.dataset.startVoteUrl));
    root.querySelector("[data-copy-link]")?.addEventListener("click", async (event) => {
        try {
            await navigator.clipboard.writeText(window.location.href);
            event.currentTarget.textContent = "Lien copié";
        } catch (_) {
            showError("Impossible de copier automatiquement le lien.");
        }
    });

    render();
    pollTimer = window.setInterval(poll, 1800);
    window.addEventListener("pagehide", () => window.clearInterval(pollTimer), { once: true });
    document.addEventListener("visibilitychange", () => { if (!document.hidden) poll(); });
})();
