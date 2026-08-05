(() => {
    "use strict";

    const lobby = document.getElementById("starterrace-lobby");
    const initialNode = document.getElementById("starterrace-lobby-state");
    if (!lobby || !initialNode) return;

    let fingerprint;
    try {
        fingerprint = JSON.stringify(JSON.parse(initialNode.textContent));
    } catch (_) {
        return;
    }
    let controller = null;

    function rememberFocus() {
        const focused = document.activeElement?.closest?.("[data-reload-focus-key]");
        if (focused?.dataset.reloadFocusKey) {
            sessionStorage.setItem("starterrace-focus", focused.dataset.reloadFocusKey);
        }
    }

    const savedFocus = sessionStorage.getItem("starterrace-focus");
    if (savedFocus) {
        sessionStorage.removeItem("starterrace-focus");
        document.querySelector(`[data-reload-focus-key="${CSS.escape(savedFocus)}"]`)?.focus();
    }

    async function poll() {
        if (document.hidden || controller) return;
        controller = new AbortController();
        try {
            const response = await fetch(lobby.dataset.stateUrl, {
                headers: { Accept: "application/json" },
                credentials: "same-origin",
                signal: controller.signal,
            });
            if (!response.ok) return;
            const nextState = await response.json();
            const nextFingerprint = JSON.stringify(nextState);
            if (nextFingerprint !== fingerprint) {
                rememberFocus();
                window.location.reload();
            }
        } catch (error) {
            if (error.name !== "AbortError") {
                // Le prochain passage retentera silencieusement.
            }
        } finally {
            controller = null;
        }
    }

    document.addEventListener("visibilitychange", () => {
        if (!document.hidden) poll();
    });
    window.setInterval(poll, 4000);
})();
