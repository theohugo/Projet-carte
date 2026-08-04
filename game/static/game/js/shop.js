(function () {
    "use strict";

    const shop = document.getElementById("shop");
    if (!shop) return;

    const opening = document.querySelector("[data-opening]");
    const pack = opening.querySelector("[data-pack]");
    const packHint = opening.querySelector("[data-pack-hint]");
    const cardsHolder = opening.querySelector("[data-cards]");
    const actions = opening.querySelector("[data-opening-actions]");
    const summary = opening.querySelector("[data-summary]");
    const feedback = document.getElementById("shop-feedback");
    const pointsValue = shop.querySelector("[data-points]");
    const reducedMotion = window.matchMedia("(prefers-reduced-motion: reduce)");

    let pendingCards = null;
    let isBusy = false;

    function csrfToken() {
        return document.cookie.match(/(?:^|;\s*)csrftoken=([^;]+)/)?.[1] || "";
    }

    function wait(duration) {
        return new Promise((resolve) => window.setTimeout(resolve, reducedMotion.matches ? 0 : duration));
    }

    function showFeedback(message) {
        feedback.textContent = message;
        feedback.hidden = !message;
    }

    function buildCard(card, index) {
        const holder = document.createElement("div");
        holder.className = `pull-card is-${card.rarity.toLowerCase()}`;
        holder.style.setProperty("--index", String(index));

        const inner = document.createElement("div");
        inner.className = "pull-card-inner";

        const back = document.createElement("div");
        back.className = "pull-card-face pull-card-back";
        back.innerHTML = '<span class="pull-card-back-mark"></span>';

        const front = document.createElement("div");
        front.className = "pull-card-face pull-card-front";

        // L'illustration officielle quand on l'a, le sprite du catalogue sinon.
        const image = document.createElement("img");
        image.src = card.image_url || card.sprite_url;
        image.alt = card.name;
        image.loading = "lazy";
        front.appendChild(image);

        const label = document.createElement("span");
        label.className = "pull-card-name";
        label.textContent = card.name;
        front.appendChild(label);

        const rarity = document.createElement("span");
        rarity.className = "pull-card-rarity";
        rarity.textContent = card.is_new ? `${card.rarity_label} · nouvelle` : card.rarity_label;
        front.appendChild(rarity);

        if (card.rarity !== "COMMUNE") {
            const shine = document.createElement("span");
            shine.className = "pull-card-shine";
            front.appendChild(shine);
        }

        inner.append(back, front);
        holder.appendChild(inner);
        return holder;
    }

    async function revealCards(cards) {
        cardsHolder.replaceChildren(...cards.map(buildCard));
        cardsHolder.hidden = false;

        const elements = [...cardsHolder.children];
        for (const [index, element] of elements.entries()) {
            await wait(index === 0 ? 260 : 180);
            element.classList.add("is-flipped");
            // Les cartes rares font trembler la scène : l'effet doit se voir
            // sans qu'on ait à lire l'étiquette.
            if (element.classList.contains("is-legendaire")) {
                opening.classList.add("is-legendary-pull");
                await wait(420);
            } else if (element.classList.contains("is-rare")) {
                opening.classList.add("is-rare-pull");
                await wait(220);
            }
        }

        const best = cards.some((card) => card.rarity === "LEGENDAIRE")
            ? "Un légendaire dans ce booster."
            : cards.some((card) => card.rarity === "RARE")
              ? "Une rare dans ce booster."
              : "Cinq cartes de plus pour la collection.";
        const fresh = cards.filter((card) => card.is_new).length;
        summary.textContent = fresh
            ? `${best} ${fresh} nouvelle${fresh > 1 ? "s" : ""} carte${fresh > 1 ? "s" : ""}.`
            : `${best} Aucune nouveauté cette fois.`;
        actions.hidden = false;
    }

    function closeOpening() {
        opening.hidden = true;
        opening.classList.remove("is-open", "is-torn", "is-rare-pull", "is-legendary-pull");
        cardsHolder.hidden = true;
        cardsHolder.replaceChildren();
        actions.hidden = true;
        pendingCards = null;
        document.body.classList.remove("has-opening");
    }

    async function tearPack() {
        if (!pendingCards || opening.classList.contains("is-torn")) return;
        opening.classList.add("is-torn");
        packHint.textContent = "";
        await wait(620);
        await revealCards(pendingCards);
    }

    async function buyBooster(button) {
        if (isBusy) return;
        isBusy = true;
        button.disabled = true;
        showFeedback("");

        try {
            const url = shop.dataset.openUrlTemplate.replace("KEY", button.dataset.openBooster);
            const response = await fetch(url, {
                method: "POST",
                headers: {
                    "X-CSRFToken": csrfToken(),
                    "X-Requested-With": "XMLHttpRequest",
                },
            });
            const payload = await response.json();

            if (!response.ok) {
                showFeedback(payload.error || "Ouverture impossible.");
                return;
            }

            pointsValue.textContent = String(payload.points_left);
            pendingCards = payload.cards;

            opening.hidden = false;
            document.body.classList.add("has-opening");
            window.requestAnimationFrame(() => opening.classList.add("is-open"));
            packHint.textContent = reducedMotion.matches ? "Ouverture…" : "Clique pour déchirer";
            pack.focus?.();

            // Sans animation, on affiche directement le contenu.
            if (reducedMotion.matches) await tearPack();
        } catch (_) {
            showFeedback("Connexion perdue : le booster n'a pas été ouvert.");
        } finally {
            isBusy = false;
            // Le bouton se réactive selon les points restants.
            const price = Number(button.closest(".booster-card").querySelector(".booster-price").textContent.replace(/\D/g, ""));
            button.disabled = Number(pointsValue.textContent) < price;
            if (button.disabled) button.textContent = "Points insuffisants";
        }
    }

    shop.addEventListener("click", (event) => {
        const button = event.target.closest("[data-open-booster]");
        if (button && !button.disabled) buyBooster(button);
    });

    pack.addEventListener("click", tearPack);
    opening.addEventListener("click", (event) => {
        if (event.target.closest("[data-opening-close]")) closeOpening();
    });
    document.addEventListener("keydown", (event) => {
        if (event.key === "Escape" && !opening.hidden) closeOpening();
        if (event.key === "Enter" && !opening.hidden && !opening.classList.contains("is-torn")) tearPack();
    });
})();
