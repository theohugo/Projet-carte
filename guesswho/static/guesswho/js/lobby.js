(() => {
    "use strict";

    const lobby = document.getElementById("guesswho-lobby");
    if (!lobby) return;

    const rulesButton = lobby.querySelector("[data-show-rules]");
    const rules = document.getElementById("guesswho-rules");
    const initialStateNode = document.getElementById("guesswho-lobby-state");
    const reducedMotion = window.matchMedia("(prefers-reduced-motion: reduce)");
    const precisePointer = window.matchMedia("(hover: hover) and (pointer: fine)");
    const knownState = JSON.stringify(JSON.parse(initialStateNode.textContent));
    const reloadContextKey = `guesswho:lobby-reload:${window.location.pathname}`;
    let pollPending = false;
    let reloadRequested = false;

    function saveReloadContext() {
        const activeElement = document.activeElement;
        const focusKey = activeElement instanceof Element
            ? activeElement.closest("[data-reload-focus-key]")?.dataset.reloadFocusKey || null
            : null;
        try {
            window.sessionStorage.setItem(reloadContextKey, JSON.stringify({
                savedAt: Date.now(),
                scrollX: window.scrollX,
                scrollY: window.scrollY,
                focusKey,
                rulesOpen: !rules.hidden,
            }));
        } catch (_) {
            // Le stockage peut être désactivé : le rechargement reste fonctionnel.
        }
    }

    function restoreReloadContext() {
        let context;
        try {
            context = JSON.parse(window.sessionStorage.getItem(reloadContextKey) || "null");
            window.sessionStorage.removeItem(reloadContextKey);
        } catch (_) {
            return;
        }
        if (!context?.savedAt || Date.now() - context.savedAt > 15000) return;
        if (context.rulesOpen) {
            rules.hidden = false;
            rulesButton?.setAttribute("aria-expanded", "true");
            if (rulesButton) rulesButton.textContent = "Masquer les règles";
        }
        window.requestAnimationFrame(() => window.requestAnimationFrame(() => {
            window.scrollTo(context.scrollX || 0, context.scrollY || 0);
            if (!context.focusKey) return;
            const target = document.querySelector(
                `[data-reload-focus-key="${CSS.escape(context.focusKey)}"]`,
            );
            if (target instanceof HTMLElement && !target.matches(":disabled") && target.getClientRects().length) {
                target.focus({ preventScroll: true });
            }
        }));
    }

    async function refreshIfLobbyChanged() {
        if (document.hidden || pollPending || reloadRequested || !lobby.dataset.stateUrl) return;
        pollPending = true;
        try {
            const response = await fetch(lobby.dataset.stateUrl, {
                credentials: "same-origin",
                cache: "no-store",
                headers: { Accept: "application/json" },
            });
            if (!response.ok) return;
            const latest = JSON.stringify(await response.json());
            if (latest !== knownState) {
                reloadRequested = true;
                saveReloadContext();
                window.location.reload();
            }
        } catch (_) {
            // Le prochain passage rattrapera une indisponibilité réseau ponctuelle.
        } finally {
            pollPending = false;
        }
    }

    rulesButton?.addEventListener("click", () => {
        const shouldOpen = rules.hidden;
        rules.hidden = !shouldOpen;
        rulesButton.setAttribute("aria-expanded", String(shouldOpen));
        rulesButton.textContent = shouldOpen ? "Masquer les règles" : "Comment jouer";
        if (shouldOpen) {
            rules.scrollIntoView({
                behavior: reducedMotion.matches ? "auto" : "smooth",
                block: "nearest",
            });
        }
    });

    lobby.querySelectorAll("form").forEach((form) => {
        form.addEventListener("submit", () => {
            const submitButton = form.querySelector('button[type="submit"]');
            if (!submitButton || submitButton.disabled) return;
            submitButton.disabled = true;
            submitButton.setAttribute("aria-busy", "true");
            submitButton.textContent = form.action.includes("join") ? "Connexion…" : "Création…";
        });
    });

    restoreReloadContext();
    window.setInterval(refreshIfLobbyChanged, 1800);
    document.addEventListener("visibilitychange", refreshIfLobbyChanged);

    const heroBoard = lobby.querySelector(".gw-hero-board");
    if (!heroBoard || reducedMotion.matches || !precisePointer.matches) return;

    let bounds = null;
    let pointerX = 0;
    let pointerY = 0;
    let animationFrame = null;

    function paintTilt() {
        if (!bounds) return;
        const x = Math.min(1, Math.max(0, (pointerX - bounds.left) / bounds.width));
        const y = Math.min(1, Math.max(0, (pointerY - bounds.top) / bounds.height));
        heroBoard.style.setProperty("--hero-rx", `${((y - 0.5) * -7).toFixed(2)}deg`);
        heroBoard.style.setProperty("--hero-ry", `${((x - 0.5) * 9).toFixed(2)}deg`);
        animationFrame = null;
    }

    heroBoard.addEventListener("pointerenter", () => {
        bounds = heroBoard.getBoundingClientRect();
    });

    heroBoard.addEventListener("pointermove", (event) => {
        pointerX = event.clientX;
        pointerY = event.clientY;
        if (animationFrame === null) animationFrame = window.requestAnimationFrame(paintTilt);
    });

    heroBoard.addEventListener("pointerleave", () => {
        if (animationFrame !== null) window.cancelAnimationFrame(animationFrame);
        animationFrame = null;
        bounds = null;
        heroBoard.style.removeProperty("--hero-rx");
        heroBoard.style.removeProperty("--hero-ry");
    });
})();
