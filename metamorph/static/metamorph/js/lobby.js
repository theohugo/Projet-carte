(() => {
    "use strict";

    const lobby = document.getElementById("metamorph-lobby");
    const initialNode = document.getElementById("metamorph-lobby-state");
    if (!lobby || !initialNode) return;

    let initialState;
    try {
        initialState = JSON.parse(initialNode.textContent);
    } catch (_) {
        return;
    }

    const stateUrl = lobby.dataset.stateUrl;
    const rules = document.getElementById("metamorph-rules");
    const rulesButton = lobby.querySelector("[data-toggle-rules]");
    const initialFingerprint = fingerprint(initialState);
    let pending = false;

    function fingerprint(state) {
        return JSON.stringify({
            open: (state.open_games || []).map((game) => [game.id, game.player_count, game.status]),
            mine: (state.my_games || []).map((game) => [game.id, game.player_count, game.status]),
        });
    }

    async function refreshIfChanged() {
        if (pending || document.hidden) return;
        pending = true;
        try {
            const response = await fetch(stateUrl, {
                headers: { Accept: "application/json" },
                credentials: "same-origin",
                cache: "no-store",
            });
            if (!response.ok) return;
            const nextState = await response.json();
            if (fingerprint(nextState) !== initialFingerprint) {
                sessionStorage.setItem("metamorph-lobby-scroll", String(window.scrollY));
                window.location.reload();
            }
        } catch (_) {
            // Le prochain polling rattrapera une coupure ponctuelle.
        } finally {
            pending = false;
        }
    }

    rulesButton?.addEventListener("click", () => {
        const willOpen = rules.hidden;
        rules.hidden = !willOpen;
        rulesButton.setAttribute("aria-expanded", String(willOpen));
        rulesButton.textContent = willOpen ? "Masquer les règles" : "Comment jouer";
        if (willOpen) rules.scrollIntoView({ behavior: "smooth", block: "nearest" });
    });

    lobby.querySelectorAll("form").forEach((form) => {
        form.addEventListener("submit", () => {
            const button = form.querySelector('button[type="submit"]');
            if (!button || button.disabled) return;
            button.disabled = true;
            button.setAttribute("aria-busy", "true");
            button.textContent = button.hasAttribute("data-create-game") ? "Création…" : "Connexion…";
        });
    });

    const savedScroll = Number(sessionStorage.getItem("metamorph-lobby-scroll"));
    if (Number.isFinite(savedScroll) && savedScroll > 0) {
        sessionStorage.removeItem("metamorph-lobby-scroll");
        window.requestAnimationFrame(() => window.scrollTo({ top: savedScroll }));
    }

    window.setInterval(refreshIfChanged, 1800);
    document.addEventListener("visibilitychange", refreshIfChanged);
})();
