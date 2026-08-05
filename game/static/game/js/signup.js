(function () {
    "use strict";

    const form = document.getElementById("signup-form");
    const checklist = document.getElementById("password-checklist");
    if (!form || !checklist) return;
    const isEnglish = String(form.dataset.language || document.documentElement.lang || "fr")
        .toLowerCase()
        .startsWith("en");
    const tr = (french, english) => (isEnglish ? english : french);

    const username = form.querySelector("#id_username");
    const password1 = form.querySelector("#id_password1");
    const password2 = form.querySelector("#id_password2");
    if (!password1 || !password2) return;

    const MAX_SIMILARITY = 0.7;
    const DIGITS_ONLY = /^[\p{Nd}]+$/u;
    const NON_WORD = /\W+/u;

    // Reproduction de `difflib.SequenceMatcher.quick_ratio`, utilisé par
    // `UserAttributeSimilarityValidator` côté serveur.
    function quickRatio(a, b) {
        const total = a.length + b.length;
        if (total === 0) return 1;

        const available = new Map();
        for (const character of b) {
            available.set(character, (available.get(character) || 0) + 1);
        }

        let matches = 0;
        for (const character of a) {
            const remaining = available.get(character) || 0;
            if (remaining > 0) matches += 1;
            available.set(character, remaining - 1);
        }
        return (2 * matches) / total;
    }

    // Même court-circuit que `exceeds_maximum_length_ratio` côté serveur.
    function exceedsMaximumLengthRatio(password, value) {
        const lengthBoundSimilarity = (MAX_SIMILARITY / 2) * password.length;
        return password.length >= 10 * value.length && value.length < lengthBoundSimilarity;
    }

    function isTooSimilarToUsername(password, rawUsername) {
        if (!rawUsername) return false;
        const value = rawUsername.toLowerCase();
        const parts = value.split(NON_WORD).concat([value]);
        return parts.some(
            (part) =>
                !exceedsMaximumLengthRatio(password, part) && quickRatio(password, part) >= MAX_SIMILARITY,
        );
    }

    // `null` signifie « pas encore évaluable » : la règle reste neutre.
    const checks = {
        length: (state, rule) => state.password.length >= Number(rule.dataset.minLength || 8),
        "not-numeric": (state) => !DIGITS_ONLY.test(state.password),
        "not-similar": (state) => !isTooSimilarToUsername(state.password.toLowerCase(), state.username),
        match: (state) => (state.confirmation ? state.password === state.confirmation : null),
    };

    const rules = Array.from(checklist.querySelectorAll("[data-rule]"));

    function applyState(rule, satisfied) {
        const status = rule.querySelector("[data-rule-status]");
        rule.classList.remove("is-pending", "is-satisfied", "is-missing");
        if (satisfied === null) {
            rule.classList.add("is-pending");
            if (status) status.textContent = tr("règle à vérifier", "requirement to check");
            return;
        }
        rule.classList.add(satisfied ? "is-satisfied" : "is-missing");
        if (status) {
            status.textContent = satisfied
                ? tr("règle respectée", "requirement met")
                : tr("règle non respectée", "requirement not met");
        }
    }

    function refresh() {
        const state = {
            password: password1.value,
            confirmation: password2.value,
            username: username ? username.value.trim() : "",
        };

        for (const rule of rules) {
            // Les règles vérifiées uniquement par le serveur (mot de passe trop
            // courant) redeviennent neutres dès que la saisie change.
            if (rule.dataset.serverOnly === "true" || !state.password) {
                applyState(rule, null);
                continue;
            }
            const check = checks[rule.dataset.rule];
            applyState(rule, check ? check(state, rule) : null);
        }
    }

    for (const field of [username, password1, password2]) {
        if (field) field.addEventListener("input", refresh);
    }

    // Les états rendus par le serveur restent affichés tant que rien n'est saisi.
    if (password1.value || password2.value) refresh();
})();
