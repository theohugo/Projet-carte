(function () {
    "use strict";

    const lobby = document.getElementById("silhouette-lobby");
    if (!lobby) return;

    let knownSignature = signatureOf(lobby.querySelectorAll("[data-open-games] .game-list-item").length);

    function signatureOf(count) {
        return String(count);
    }

    async function poll() {
        try {
            const response = await fetch(lobby.dataset.stateUrl, {
                headers: { "X-Requested-With": "XMLHttpRequest" },
            });
            if (response.ok) {
                const state = await response.json();
                const signature = signatureOf(state.open_games.length);
                // Le rendu des salons vit dans le gabarit : plutôt que de le
                // dupliquer en JS, on recharge quand la liste a bougé.
                if (signature !== knownSignature) {
                    knownSignature = signature;
                    window.location.reload();
                    return;
                }
            }
        } catch (_) {
            // Le prochain tour réessaiera.
        }
        window.setTimeout(poll, 4000);
    }

    window.setTimeout(poll, 4000);
})();
