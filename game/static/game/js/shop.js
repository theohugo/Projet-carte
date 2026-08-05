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
    const packSet = opening.querySelector("[data-pack-set]");
    const collectionLink = opening.querySelector("[data-collection-link]");
    const fx = opening.querySelector("[data-fx]");
    const reducedMotion = window.matchMedia("(prefers-reduced-motion: reduce)");

    // Rang de la rareté « Rare » : à partir de là, la scène se teinte et les
    // rayons tournent. En dessous, la carte se retourne et c'est tout.
    const SPECIAL_RANK = 2;

    // État de l'ouverture en cours.
    let pulls = [];
    let cardElements = [];
    let index = 0;
    let locked = true;
    let isBusy = false;
    // Au-delà d'un booster, on passe en planche plutôt qu'en défilé.
    let isSheet = false;

    // La classe suit la clé de rareté : COMMUNE -> is-commune,
    // ILLUSTRATION_SPECIALE -> is-illustration-speciale.
    function rarityClass(card) {
        return `is-${String(card.rarity || "commune").toLowerCase().replace(/_/g, "-")}`;
    }

    const SEASON_LABEL = {
        1: '1<sup>re</sup> édition',
        2: "Série 151",
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
        const rank = card.rarity_rank || 0;
        const holder = document.createElement("div");
        holder.className = `tcg-card ${rarityClass(card)}`;
        holder.style.setProperty("--rarity-color", card.rarity_color || "#9fb0c4");

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

        if (rank >= SPECIAL_RANK) {
            const holo = document.createElement("span");
            holo.className = "tcg-holo";
            front.appendChild(holo);
        }

        // À partir de la Double rare, un feuillet de plus : le prisme balaie
        // l'illustration en continu, et le sigle de rareté reste affiché.
        if (rank >= 4) {
            const prism = document.createElement("span");
            prism.className = "tcg-prism";
            front.appendChild(prism);
        }

        if (rank >= SPECIAL_RANK) {
            const badge = document.createElement("span");
            badge.className = "tcg-rarity-badge";
            badge.textContent = card.rarity_code || "";
            front.appendChild(badge);
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

    function sparkle(element, count = 14) {
        if (reducedMotion.matches) return;
        for (let i = 0; i < count; i += 1) {
            const spark = document.createElement("span");
            spark.className = "spark";
            spark.style.setProperty("--angle", `${Math.random() * 360}deg`);
            spark.style.setProperty("--distance", `${120 + Math.random() * 150}px`);
            spark.style.setProperty("--life", `${700 + Math.random() * 500}ms`);
            spark.addEventListener("animationend", () => spark.remove());
            element.appendChild(spark);
        }
    }

    // ── Effets plein écran ────────────────────────────────────────────────
    // Chaque pièce se retire d'elle-même à la fin de son animation : la couche
    // d'effets ne garde jamais de débris d'une carte sur la suivante.

    function emit(className, count, decorate) {
        if (reducedMotion.matches) return;
        const batch = document.createDocumentFragment();
        for (let i = 0; i < count; i += 1) {
            const piece = document.createElement("span");
            piece.className = className;
            decorate(piece, i);
            piece.addEventListener("animationend", () => piece.remove());
            batch.appendChild(piece);
        }
        fx.appendChild(batch);
    }

    // Pluie d'étoiles : elles tombent en biais sur toute la largeur.
    function starfall(count = 30) {
        emit("fx-star", count, (star) => {
            star.style.setProperty("--x", `${Math.random() * 100}%`);
            star.style.setProperty("--size", `${8 + Math.random() * 14}px`);
            star.style.setProperty("--life", `${900 + Math.random() * 900}ms`);
            star.style.setProperty("--delay", `${Math.random() * 500}ms`);
            star.style.setProperty("--drift", `${-60 + Math.random() * 120}px`);
        });
    }

    // Explosion : des éclats projetés depuis le centre, plus l'onde de choc.
    function explode(count = 40) {
        emit("fx-shard", count, (shard) => {
            shard.style.setProperty("--angle", `${Math.random() * 360}deg`);
            shard.style.setProperty("--distance", `${180 + Math.random() * 380}px`);
            shard.style.setProperty("--life", `${520 + Math.random() * 420}ms`);
            shard.style.setProperty("--spin", `${-540 + Math.random() * 1080}deg`);
        });
        emit("fx-wave", 3, (wave, i) => {
            wave.style.setProperty("--delay", `${i * 130}ms`);
        });
    }

    function confetti(count = 70) {
        emit("fx-confetti", count, (piece) => {
            piece.style.setProperty("--x", `${Math.random() * 100}%`);
            piece.style.setProperty("--life", `${1100 + Math.random() * 1100}ms`);
            piece.style.setProperty("--delay", `${Math.random() * 600}ms`);
            piece.style.setProperty("--drift", `${-120 + Math.random() * 240}px`);
            piece.style.setProperty("--spin", `${-720 + Math.random() * 1440}deg`);
            piece.style.setProperty("--tone", `${Math.random() * 360}deg`);
        });
    }

    function shake() {
        if (reducedMotion.matches) return;
        scene.classList.remove("is-shaking");
        void scene.offsetWidth;
        scene.classList.add("is-shaking");
    }

    // Chaque rareté a sa mise en scène. Deux voisines ne doivent jamais se
    // ressembler : c'est à ça qu'on reconnaît ce qu'on vient de tirer.
    const REVEALS = {
        simple: () => {},
        sheen: (element) => {
            sparkle(element, 6);
        },
        burst: (element) => {
            element.classList.add("is-bursting");
            sparkle(element, 14);
            fireFlash();
        },
        flare: (element) => {
            element.classList.add("is-bursting");
            sparkle(element, 26);
            fireFlash();
        },
        loop: async (element) => {
            element.classList.add("is-looping");
            sparkle(element, 18);
            fireFlash();
            await wait(300);
            sparkle(element, 12);
        },
        starfall: async (element) => {
            element.classList.add("is-bursting");
            fireFlash();
            starfall(34);
            await wait(240);
            sparkle(element, 20);
        },
        explosion: async (element) => {
            shake();
            explode(44);
            fireFlash();
            await wait(200);
            element.classList.add("is-bursting");
            sparkle(element, 26);
        },
        prism: async (element) => {
            element.classList.add("is-looping");
            fireFlash();
            starfall(26);
            await wait(260);
            explode(26);
            shake();
            await wait(240);
            sparkle(element, 30);
        },
        gold: async (element) => {
            shake();
            fireFlash();
            explode(52);
            element.classList.add("is-looping");
            await wait(260);
            confetti(80);
            starfall(30);
            await wait(320);
            fireFlash();
            sparkle(element, 40);
        },
    };

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
        const reveal = card.reveal || "simple";
        opening.dataset.rarity = card.rarity;
        opening.dataset.reveal = reveal;
        opening.style.setProperty("--rarity-color", card.rarity_color || "#9fb0c4");
        opening.classList.toggle("is-special", (card.rarity_rank || 0) >= SPECIAL_RANK);
        await (REVEALS[reveal] || REVEALS.simple)(element);

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
        rarity.style.setProperty("--rarity-color", card.rarity_color || "#9fb0c4");
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

        // En planche, tout est déjà retourné : le clic mène au récapitulatif.
        if (isSheet) {
            index = pulls.length;
            finish();
            return;
        }

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
        opening.dataset.reveal = "simple";
        caption.classList.remove("is-visible");
        setHint("");
        dots.hidden = true;

        await wait(420);
        deck.hidden = true;
        deck.classList.remove("is-sheet");
        // Un éventail de cinquante cartes ne se lit pas : au-delà d'un booster,
        // le récapitulatif passe en grille.
        fan.classList.toggle("is-grid", pulls.length > 5);

        fan.replaceChildren(
            ...pulls.map((card, position) => {
                const holder = document.createElement("figure");
                holder.className = `recap-card ${rarityClass(card)}`;
                holder.style.setProperty("--i", String(position));
                holder.style.setProperty("--mid", String((pulls.length - 1) / 2));
                holder.style.setProperty("--rarity-color", card.rarity_color || "#9fb0c4");
                holder.title = `${card.name} · ${card.rarity_label}`;
                const image = document.createElement("img");
                image.src = card.image_url || card.sprite_url;
                image.alt = card.name;
                holder.appendChild(image);
                return holder;
            }),
        );

        // La plus belle du lot donne le ton du récapitulatif.
        const best = pulls.reduce(
            (top, card) => ((card.rarity_rank || 0) > (top.rarity_rank || 0) ? card : top),
            pulls[0] || {},
        );
        const headline =
            (best.rarity_rank || 0) >= SPECIAL_RANK
                ? `${best.rarity_label} dans ce booster : ${best.name}.`
                : "Cinq cartes de plus pour la collection.";
        const fresh = pulls.filter((card) => card.is_new).length;
        summary.textContent = fresh
            ? `${headline} ${fresh} nouvelle${fresh > 1 ? "s" : ""} carte${fresh > 1 ? "s" : ""}.`
            : `${headline} Aucune nouveauté cette fois.`;

        recap.hidden = false;
    }

    // ── Planche : plusieurs boosters d'un coup ────────────────────────────

    async function revealSheet() {
        deck.classList.add("is-sheet");
        dots.hidden = true;

        for (let position = 0; position < pulls.length; position += 1) {
            const card = pulls[position];
            const element = cardElements[position];
            element.classList.add("is-revealed");

            // Seules les cartes qui comptent déclenchent leur mise en scène :
            // cinquante spectacles d'affilée n'en feraient plus aucun.
            if ((card.rarity_rank || 0) >= 4) {
                opening.dataset.rarity = card.rarity;
                opening.dataset.reveal = card.reveal;
                opening.style.setProperty("--rarity-color", card.rarity_color || "#9fb0c4");
                opening.classList.add("is-special");
                (REVEALS[card.reveal] || REVEALS.simple)(element);
                await wait(340);
            }
            await wait(reducedMotion.matches ? 0 : 55);
        }

        const best = pulls.reduce(
            (top, card) => ((card.rarity_rank || 0) > (top.rarity_rank || 0) ? card : top),
            pulls[0] || {},
        );
        caption.innerHTML = "";
        const name = document.createElement("span");
        name.className = "opening-caption-name";
        name.textContent = `${pulls.length} cartes`;
        const tags = document.createElement("span");
        tags.className = "opening-caption-tags";
        const rarity = document.createElement("span");
        rarity.className = "rarity-chip";
        rarity.dataset.rarity = best.rarity;
        rarity.style.setProperty("--rarity-color", best.rarity_color || "#9fb0c4");
        rarity.textContent = `Meilleure : ${best.rarity_label || "Commune"}`;
        tags.appendChild(rarity);
        caption.append(name, tags);
        caption.classList.add("is-visible");

        locked = false;
        setHint("Clique pour le récapitulatif");
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
        if (isSheet) {
            await revealSheet();
            return;
        }
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
        // En planche, rien ne se balaie : les cartes sont toutes posées.
        if (locked || deck.hidden || isSheet) return;
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
        if (isSheet) return;
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
        scene.classList.remove("is-shaking");
        deck.classList.remove("is-sheet");
        fx.replaceChildren();
        isSheet = false;
        opening.dataset.rarity = "COMMUNE";
        opening.dataset.reveal = "simple";
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

    // Les prix affichés se rafraîchissent après chaque ouverture : un booster
    // acheté peut mettre les autres hors de portée, et inversement.
    function refreshAffordability() {
        const points = Number(pointsValue.textContent);
        shop.querySelectorAll("[data-open-booster]").forEach((button) => {
            const price = Number(button.dataset.price);
            const quantity = Number(button.dataset.quantity || 1);
            const affordable = points >= price;
            button.disabled = !affordable;
            const label = button.querySelector("[data-label]");
            if (!label) return;
            if (!affordable) label.textContent = `−${price - points}`;
            else label.textContent = quantity === 1 ? "Ouvrir" : `×${quantity}`;
        });
    }

    // Un ticket est consommé à l'ouverture : sa carte disparaît de la boutique.
    function consumeTicket(button) {
        const card = button.closest("[data-ticket-card]");
        card?.remove();
        const shelf = shop.querySelector("[data-tickets]");
        if (shelf && !shelf.querySelector("[data-ticket-card]")) shelf.remove();
    }

    async function openPack(button) {
        if (isBusy) return;
        isBusy = true;
        button.disabled = true;
        showFeedback("");

        const ticketId = button.dataset.openTicket;
        const url = ticketId
            ? shop.dataset.ticketUrlTemplate.replace("/0/", `/${ticketId}/`)
            : shop.dataset.openUrlTemplate.replace("KEY", button.dataset.openBooster);

        const body = new URLSearchParams();
        if (!ticketId) body.set("quantity", button.dataset.quantity || "1");

        try {
            const response = await fetch(url, {
                method: "POST",
                headers: {
                    "X-CSRFToken": csrfToken(),
                    "X-Requested-With": "XMLHttpRequest",
                    "Content-Type": "application/x-www-form-urlencoded",
                },
                body,
            });
            const payload = await response.json();

            if (!response.ok) {
                showFeedback(payload.error || "Ouverture impossible.");
                return;
            }

            if (ticketId) consumeTicket(button);
            pointsValue.textContent = String(payload.points_left);
            resetScene();
            pulls = payload.cards;
            isSheet = (payload.quantity || 1) > 1;
            cardElements = pulls.map(buildCard);
            deck.replaceChildren(...cardElements);
            if (!isSheet) layout();

            const season = payload.season || 1;
            opening.dataset.season = String(season);
            packSet.innerHTML = SEASON_LABEL[season] || SEASON_LABEL[1];
            collectionLink.href = `${collectionLink.pathname}?saison=${season}`;

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
            refreshAffordability();
        }
    }

    shop.addEventListener("click", (event) => {
        const button = event.target.closest("[data-open-booster], [data-open-ticket]");
        if (button && !button.disabled) openPack(button);
    });

    pack.addEventListener("click", tearPack);
    deck.addEventListener("click", () => {
        if (isSheet) next(-1);
    });
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
