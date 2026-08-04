(function () {
    "use strict";

    // Les menus de l'en-tête sont de simples <details> : ils fonctionnent sans
    // JavaScript. Ce script n'ajoute que le confort attendu d'un menu — se
    // fermer au clic à côté, à l'Échap, ou quand on en ouvre un autre.
    const menus = [...document.querySelectorAll("[data-nav-menu]")];
    if (!menus.length) return;

    function closeAll(except) {
        menus.forEach((menu) => {
            if (menu !== except) menu.open = false;
        });
    }

    menus.forEach((menu) => {
        menu.addEventListener("toggle", () => {
            if (menu.open) closeAll(menu);
        });
    });

    document.addEventListener("click", (event) => {
        if (!event.target.closest("[data-nav-menu]")) closeAll(null);
    });

    document.addEventListener("keydown", (event) => {
        if (event.key !== "Escape") return;
        const open = menus.find((menu) => menu.open);
        if (!open) return;
        open.open = false;
        open.querySelector("summary")?.focus();
    });
})();
