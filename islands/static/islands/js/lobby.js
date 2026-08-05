(() => {
    "use strict";

    const root = document.querySelector("#islands-lobby");
    const toggle = document.querySelector("[data-rules-toggle]");
    const rules = document.querySelector("#islands-rules");
    const initialNode = document.querySelector("#islands-lobby-state");
    if (!root) return;

    toggle?.addEventListener("click", () => {
        const willOpen = rules.hidden;
        rules.hidden = !willOpen;
        toggle.setAttribute("aria-expanded", String(willOpen));
        if (willOpen) rules.querySelector("h2")?.focus({ preventScroll: true });
    });

    let signature = "";
    try {
        const state = JSON.parse(initialNode?.textContent || "{}");
        signature = JSON.stringify([state.open_games, state.my_games]);
    } catch (_error) {
        signature = "";
    }

    const poll = async () => {
        if (document.hidden) return;
        try {
            const response = await fetch(root.dataset.stateUrl, {
                headers: { Accept: "application/json" },
                credentials: "same-origin",
            });
            if (!response.ok) return;
            const state = await response.json();
            const nextSignature = JSON.stringify([state.open_games, state.my_games]);
            if (signature && signature !== nextSignature) window.location.reload();
            signature = nextSignature;
        } catch (_error) {
            // La prochaine interrogation reprendra sans interrompre la page.
        }
    };

    window.setInterval(poll, 4000);
})();

