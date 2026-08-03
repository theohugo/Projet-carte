(function () {
    "use strict";

    const lobby = document.getElementById("lobby-app");
    const initialState = document.getElementById("lobby-initial-state");
    if (!lobby || !initialState) return;

    const knownState = JSON.stringify(JSON.parse(initialState.textContent));
    let isRequestPending = false;

    async function refreshIfLobbyChanged() {
        if (document.hidden || isRequestPending) return;
        isRequestPending = true;
        try {
            const response = await fetch(lobby.dataset.stateUrl, { cache: "no-store" });
            if (!response.ok) return;
            const serializedState = JSON.stringify(await response.json());
            if (serializedState !== knownState) window.location.reload();
        } catch (_) {
            // Une indisponibilité réseau ponctuelle ne doit pas perturber la page.
        } finally {
            isRequestPending = false;
        }
    }

    window.setInterval(refreshIfLobbyChanged, 2000);
    document.addEventListener("visibilitychange", refreshIfLobbyChanged);
})();
