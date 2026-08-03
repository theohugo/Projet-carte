(function () {
    "use strict";

    const lobby = document.getElementById("lobby-app");
    const initialState = document.getElementById("lobby-initial-state");
    if (!lobby || !initialState) return;

    const knownState = JSON.stringify(JSON.parse(initialState.textContent));
    const reloadContextKey = `poke-uno:lobby-reload:${window.location.pathname}`;
    let isRequestPending = false;
    let reloadRequested = false;

    function saveReloadContext() {
        const activeElement = document.activeElement;
        const focusKey =
            activeElement instanceof Element
                ? activeElement.closest("[data-reload-focus-key]")?.dataset.reloadFocusKey || null
                : null;
        try {
            window.sessionStorage.setItem(
                reloadContextKey,
                JSON.stringify({
                    savedAt: Date.now(),
                    windowScroll: { left: window.scrollX, top: window.scrollY },
                    focusKey,
                }),
            );
        } catch (_) {
            // Le stockage peut être désactivé : le rechargement reste fonctionnel.
        }
    }

    function restoreReloadContext() {
        let context;
        try {
            const serializedContext = window.sessionStorage.getItem(reloadContextKey);
            window.sessionStorage.removeItem(reloadContextKey);
            if (!serializedContext) return;
            context = JSON.parse(serializedContext);
        } catch (_) {
            return;
        }

        if (!context?.savedAt || Date.now() - context.savedAt > 15000) return;
        const previousScrollRestoration = "scrollRestoration" in window.history ? window.history.scrollRestoration : null;
        if (previousScrollRestoration !== null) window.history.scrollRestoration = "manual";

        window.requestAnimationFrame(() => {
            window.requestAnimationFrame(() => {
                window.scrollTo(context.windowScroll?.left || 0, context.windowScroll?.top || 0);
                if (context.focusKey) {
                    const focusTarget = document.querySelector(
                        `[data-reload-focus-key="${CSS.escape(context.focusKey)}"]`,
                    );
                    if (
                        focusTarget instanceof HTMLElement &&
                        !focusTarget.matches(":disabled") &&
                        !focusTarget.closest("[hidden], [inert]") &&
                        focusTarget.getClientRects().length
                    ) {
                        focusTarget.focus({ preventScroll: true });
                    }
                }
                if (previousScrollRestoration !== null) window.history.scrollRestoration = previousScrollRestoration;
            });
        });
    }

    async function refreshIfLobbyChanged() {
        if (document.hidden || isRequestPending || reloadRequested) return;
        isRequestPending = true;
        try {
            const response = await fetch(lobby.dataset.stateUrl, { cache: "no-store" });
            if (!response.ok) return;
            const serializedState = JSON.stringify(await response.json());
            if (serializedState !== knownState) {
                reloadRequested = true;
                saveReloadContext();
                window.location.reload();
            }
        } catch (_) {
            // Une indisponibilité réseau ponctuelle ne doit pas perturber la page.
        } finally {
            isRequestPending = false;
        }
    }

    restoreReloadContext();
    window.setInterval(refreshIfLobbyChanged, 2000);
    document.addEventListener("visibilitychange", refreshIfLobbyChanged);
})();
