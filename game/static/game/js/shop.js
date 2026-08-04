(function () {
    "use strict";

    const shop = document.getElementById("shop");
    if (!shop) return;

    const opening = document.querySelector("[data-opening]");
    const scene = opening.querySelector(".opening-scene");
    const pack = opening.querySelector("[data-pack]");
    const deck = opening.querySelector("[data-deck]");
    const dots = opening.querySelector("[data-dots]");
    const caption = opening.querySelector("[data-caption]");
    const hint = opening.querySelector("[data-hint]");
    const flash = opening.querySelector("[data-flash]");
    const recap = opening.querySelector("[data-recap]");
    const fan = opening.querySelector("[data-fan]");
    const summary = opening.querySelector("[data-summary]");
    const feedback = document.getElementById("shop-feedback");
    const pointsValue = shop.querySelector("[data-points]");
    const reducedMotion = window.matchMedia("(prefers-reduced-motion: reduce)");

    // État de l'ouverture en cours.
    let pulls = [];
    let cardElements = [];
    let index = 0;
    let locked = true;
    let isBusy = false;

    const RARITY_CLASS = {
        COMMUNE: "is-commune",
        RARE: "is-rare",
        LEGENDAIRE: "is-legendaire",
    };

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

    function setHint(text) {
        hint.textContent = text;
        hint.classList.toggle("is-visible", Boolean(text));
    }

    function fireFlash() {
        if (reducedMotion.matches) return;
        flash.classList.remove("is-firing");
        void flash.offsetWidth; // relance l'animation même sur deux cartes d'affilée
        flash.classList.add("is-firing");
    }

    // ── Construction des cartes ────────────────────────────────────────────

    function buildCard(card) {
        const holder = document.createElement("div");
        holder.className = `tcg-card ${RARITY_CLASS[card.rarity] || "is-commune"}`;

        const tilt = document.createElement("div");
        tilt.className = "tcg-card-tilt";

        const inner = document.createElement("div");
        inner.className = "tcg-card-inner";

        const back = document.createElement("div");
        back.className = "tcg-face tcg-back";
        back.innerHTML = '<span class="tcg-back-mark"></span>';

        const front = document.createElement("div");
        front.className = "tcg-face tcg-front";

        // Le visuel officiel quand on l'a, le sprite du catalogue sinon.
        const image = document.createElement("img");
        image.src = card.image_url || card.sprite_url;
        image.alt = card.name;
        front.appendChild(image);

        if (card.rarity !== "COMMUNE") {
            const holo = document.createElement("span");
            holo.className = "tcg-holo";
            front.appendChild(holo);
        }

        const glare = document.createElement("span");
        glare.className = "tcg-glare";
        front.appendChild(glare);

        inner.append(back, front);
        tilt.appendChild(inner);
        holder.appendChild(tilt);

        const burst = document.createElement("span");
        burst.className = "tcg-burst";
        holder.appendChild(burst);

        return holder;
    }

    function buildDots(count) {
        dots.replaceChildren(
            ...Array.from({ length: count }, () => document.createElement("span")),
        );
        dots.hidden = false;
    }

    function paintDots() {
        [...dots.children].forEach((dot, position) => {
            dot.classList.toggle("is-done", position < index);
            dot.classList.toggle("is-current", position === index);
        });
    }

    // La pile : la carte active devant, les suivantes décalées derrière elle.
    function layout() {
        cardElements.forEach((element, position) => {
            const depth = position - index;
            element.style.setProperty("--depth", String(Math.max(depth, 0)));
            element.style.zIndex = String(cardElements.length - Math.max(depth, 0));
        });
    }

    function sparkle(element) {
        if (reducedMotion.matches) return;
        for (let i = 0; i < 14; i += 1) {
            const spark = document.createElement("span");
            spark.className = "spark";
            spark.style.setProperty("--angle", `${Math.random() * 360}deg`);
            spark.style.setProperty("--distance", `${120 + Math.random() * 150}px`);
            spark.style.setProperty("--life", `${700 + Math.random() * 500}ms`);
            spark.addEventListener("animationend", () => spark.remove());
            element.appendChild(spark);
        }
    }

    // ── Révélation ────────────────────────────────────────────────────────

    async function revealCurrent() {
        const card = pulls[index];
        const element = cardElements[index];

        locked = true;
        caption.classList.remove("is-visible");
        setHint("");
        paintDots();
        layout();

        await wait(160);
        element.classList.add("is-active", "is-revealed");

        // La scène prend la couleur de la rareté à mi-retournement : on voit
        // qu'on tient quelque chose avant même de lire l'étiquette.
        await wait(300);
        opening.dataset.rarity = card.rarity;
        opening.classList.toggle("is-special", card.rarity !== "COMMUNE");
        if (card.rarity !== "COMMUNE") {
            element.classList.add("is-bursting");
            sparkle(element);
            fireFlash();
        }

        await wait(420);
        caption.innerHTML = "";
        const name = document.createElement("span");
        name.className = "opening-caption-name";
        name.textContent = card.name;
        const tags = document.createElement("span");
        tags.className = "opening-caption-tags";
        const rarity = document.createElement("span");
        rarity.className = "rarity-chip";
        rarity.dataset.rarity = card.rarity;
        rarity.textContent = card.rarity_label;
        tags.appendChild(rarity);
        if (card.is_new) {
            const fresh = document.createElement("span");
            fresh.className = "new-chip";
            fresh.textContent = "Nouvelle";
            tags.appendChild(fresh);
        }
        caption.append(name, tags);
        caption.classList.add("is-visible");

        locked = false;
        setHint(
            index === pulls.length - 1
                ? "Clique pour voir les cinq cartes"
                : `Balaie ou clique — carte ${index + 1} sur ${pulls.length}`,
        );
    }

    function next(direction) {
        if (locked) return;
        locked = true;

        const element = cardElements[index];
        const towardsRight = direction >= 0;
        element.style.setProperty("--exit-x", towardsRight ? "130%" : "-130%");
        element.style.setProperty("--exit-rot", towardsRight ? "18deg" : "-18deg");
        element.classList.remove("is-active", "is-tilting");
        element.classList.add("is-gone");

        index += 1;
        if (index >= pulls.length) {
            finish();
            return;
        }
        revealCurrent();
    }

    async function finish() {
        opening.classList.remove("is-special");
        opening.dataset.rarity = "COMMUNE";
        caption.classList.remove("is-visible");
        setHint("");
        dots.hidden = true;

        await wait(420);
        deck.hidden = true;

        fan.replaceChildren(
            ...pulls.map((card, position) => {
                const holder = document.createElement("figure");
                holder.className = `recap-card ${RARITY_CLASS[card.rarity] || "is-commune"}`;
                holder.style.setProperty("--i", String(position));
                holder.style.setProperty("--mid", String((pulls.length - 1) / 2));
                holder.title = `${card.name} · ${card.rarity_label}`;
                const image = document.createElement("img");
                image.src = card.image_url || card.sprite_url;
                image.alt = card.name;
                holder.appendChild(image);
                return holder;
            }),
        );

        const best = pulls.some((card) => card.rarity === "LEGENDAIRE")
            ? "Un légendaire dans ce booster."
            : pulls.some((card) => card.rarity === "RARE")
              ? "Une rare dans ce booster."
              : "Cinq cartes de plus pour la collection.";
        const fresh = pulls.filter((card) => card.is_new).length;
        summary.textContent = fresh
            ? `${best} ${fresh} nouvelle${fresh > 1 ? "s" : ""} carte${fresh > 1 ? "s" : ""}.`
            : `${best} Aucune nouveauté cette fois.`;

        recap.hidden = false;
    }

    // ── Le sachet ─────────────────────────────────────────────────────────

    async function tearPack() {
        if (!pulls.length || opening.classList.contains("is-torn")) return;
        opening.classList.add("is-torn");
        setHint("");
        fireFlash();

        await wait(560);
        pack.hidden = true;
        deck.hidden = false;
        buildDots(pulls.length);
        await revealCurrent();
    }

    // ── Relief au pointeur ────────────────────────────────────────────────

    let tiltFrame = 0;

    function applyTilt(event) {
        const element = cardElements[index];
        if (!element || locked) return;

        const bounds = deck.getBoundingClientRect();
        const x = (event.clientX - bounds.left) / bounds.width;
        const y = (event.clientY - bounds.top) / bounds.height;

        if (tiltFrame) window.cancelAnimationFrame(tiltFrame);
        tiltFrame = window.requestAnimationFrame(() => {
            const tilt = element.querySelector(".tcg-card-tilt");
            // Le retournement a déjà tourné la carte de 180° : on ajoute le
            // basculement par-dessus, borné pour rester lisible.
            tilt.style.setProperty("--rx", `${(0.5 - y) * 22}deg`);
            tilt.style.setProperty("--ry", `${(x - 0.5) * 22}deg`);
            const front = element.querySelector(".tcg-front");
            front.style.setProperty("--mx", `${(1 - x) * 100}%`);
            front.style.setProperty("--my", `${y * 100}%`);
            front.style.setProperty("--sheen", String(90 + (x - 0.5) * 80));
        });
    }

    function resetTilt() {
        const element = cardElements[index];
        if (!element) return;
        const tilt = element.querySelector(".tcg-card-tilt");
        tilt.style.setProperty("--rx", "0deg");
        tilt.style.setProperty("--ry", "0deg");
    }

    // ── Balayage ──────────────────────────────────────────────────────────

    let dragStart = null;

    function onPointerDown(event) {
        if (locked || deck.hidden) return;
        dragStart = { x: event.clientX, y: event.clientY, moved: false };
        try {
            // Le pointeur peut déjà être relâché (souris rapide, événement simulé).
            deck.setPointerCapture(event.pointerId);
        } catch (_) {
            /* le suivi reste correct sans capture */
        }
        cardElements[index]?.classList.add("is-dragging", "is-tilting");
    }

    function onPointerMove(event) {
        if (event.pointerType === "mouse" && !dragStart) applyTilt(event);
        if (!dragStart) return;

        const dx = event.clientX - dragStart.x;
        if (Math.abs(dx) > 6) dragStart.moved = true;
        const element = cardElements[index];
        if (!element) return;
        element.style.setProperty("--dx", `${dx}px`);
        element.style.setProperty("--rot", `${dx / 18}deg`);
        applyTilt(event);
    }

    function onPointerUp(event) {
        const element = cardElements[index];
        if (!dragStart || !element) return;

        const dx = event.clientX - dragStart.x;
        const swiped = Math.abs(dx) > 80;
        element.classList.remove("is-dragging", "is-tilting");
        element.style.removeProperty("--dx");
        element.style.removeProperty("--rot");
        resetTilt();

        const wasDrag = dragStart.moved;
        dragStart = null;

        // Un clic net avance aussi : sur ordinateur, personne ne balaie.
        if (swiped) next(dx);
        else if (!wasDrag) next(-1);
    }

    // ── Achat ─────────────────────────────────────────────────────────────

    function resetScene() {
        opening.classList.remove("is-torn", "is-special");
        opening.dataset.rarity = "COMMUNE";
        pack.hidden = false;
        deck.hidden = true;
        deck.replaceChildren();
        dots.hidden = true;
        recap.hidden = true;
        caption.classList.remove("is-visible");
        caption.textContent = "";
        setHint("");
        index = 0;
        pulls = [];
        cardElements = [];
    }

    function closeOpening() {
        opening.hidden = true;
        opening.classList.remove("is-open");
        document.body.classList.remove("has-opening");
        resetScene();
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
            resetScene();
            pulls = payload.cards;
            cardElements = pulls.map(buildCard);
            deck.replaceChildren(...cardElements);
            layout();

            opening.hidden = false;
            document.body.classList.add("has-opening");
            window.requestAnimationFrame(() => opening.classList.add("is-open"));
            setHint(reducedMotion.matches ? "" : "Clique sur le sachet pour l’ouvrir");
            pack.focus({ preventScroll: true });

            // Sans animation, on saute directement au contenu.
            if (reducedMotion.matches) await tearPack();
        } catch (_) {
            showFeedback("Connexion perdue : le booster n’a pas été ouvert.");
        } finally {
            isBusy = false;
            const price = Number(button.dataset.price);
            button.disabled = Number(pointsValue.textContent) < price;
            if (button.disabled) button.textContent = "Points insuffisants";
        }
    }

    shop.addEventListener("click", (event) => {
        const button = event.target.closest("[data-open-booster]");
        if (button && !button.disabled) buyBooster(button);
    });

    pack.addEventListener("click", tearPack);
    deck.addEventListener("pointerdown", onPointerDown);
    deck.addEventListener("pointermove", onPointerMove);
    deck.addEventListener("pointerup", onPointerUp);
    deck.addEventListener("pointercancel", onPointerUp);
    deck.addEventListener("pointerleave", resetTilt);

    scene.addEventListener("click", (event) => {
        if (event.target.closest("[data-opening-close]")) closeOpening();
    });

    document.addEventListener("keydown", (event) => {
        if (opening.hidden) return;
        if (event.key === "Escape") closeOpening();
        if (event.key === "Enter" || event.key === " ") {
            if (!opening.classList.contains("is-torn")) return; // le sachet est déjà un bouton
            event.preventDefault();
            next(-1);
        }
    });
})();
