(function () {
    "use strict";

    function getCookie(name) {
        const match = document.cookie.match(new RegExp("(^| )" + name + "=([^;]+)"));
        return match ? decodeURIComponent(match[2]) : null;
    }

    async function postJSON(url, body) {
        const response = await fetch(url, {
            method: "POST",
            headers: {
                "Content-Type": "application/json",
                "X-CSRFToken": getCookie("csrftoken"),
            },
            body: JSON.stringify(body || {}),
        });
        const data = await response.json();
        if (!response.ok) {
            throw new Error(data.error || "Une erreur est survenue.");
        }
        return data;
    }

    const mountEl = document.getElementById("game-app");
    if (!mountEl) return;

    const stateUrl = mountEl.dataset.stateUrl;
    const playUrl = mountEl.dataset.playUrl;
    const drawUrl = mountEl.dataset.drawUrl;

    const { createApp } = Vue;

    createApp({
        data() {
            return {
                loaded: false,
                state: null,
                error: null,
                pendingLegendaryCard: null,
                pollHandle: null,
            };
        },
        computed: {
            me() {
                if (!this.state) return null;
                return this.state.players.find((p) => "hand" in p) || null;
            },
            opponents() {
                if (!this.state) return [];
                return this.state.players.filter((p) => !("hand" in p));
            },
            isMyTurn() {
                return !!(this.state && this.state.is_my_turn);
            },
            myHand() {
                return this.me ? this.me.hand : [];
            },
            topDiscard() {
                return this.state ? this.state.top_discard : null;
            },
            allTypeSlugs() {
                return [
                    "normal", "fire", "water", "electric", "grass", "ice",
                    "fighting", "poison", "ground", "flying", "psychic", "bug",
                    "rock", "ghost", "dragon", "dark", "steel", "fairy",
                ];
            },
        },
        methods: {
            async refresh() {
                try {
                    const response = await fetch(stateUrl);
                    this.state = await response.json();
                    this.loaded = true;
                } catch (e) {
                    this.error = "Impossible de récupérer l'état de la partie.";
                }
            },
            async playCard(card) {
                if (!this.isMyTurn) return;
                if (card.is_legendary) {
                    this.pendingLegendaryCard = card;
                    return;
                }
                await this._sendPlay(card, null);
            },
            async chooseDeclaredType(typeSlug) {
                if (!this.pendingLegendaryCard) return;
                await this._sendPlay(this.pendingLegendaryCard, typeSlug);
                this.pendingLegendaryCard = null;
            },
            cancelLegendaryChoice() {
                this.pendingLegendaryCard = null;
            },
            async _sendPlay(card, declaredType) {
                this.error = null;
                try {
                    this.state = await postJSON(playUrl, {
                        game_card_id: card.id,
                        declared_type: declaredType,
                    });
                } catch (e) {
                    this.error = e.message;
                }
            },
            async drawCard() {
                if (!this.isMyTurn) return;
                this.error = null;
                try {
                    this.state = await postJSON(drawUrl, {});
                } catch (e) {
                    this.error = e.message;
                }
            },
        },
        mounted() {
            this.refresh();
            this.pollHandle = setInterval(this.refresh, 2000);
        },
        beforeUnmount() {
            clearInterval(this.pollHandle);
        },
        template: `
            <div v-if="!loaded"><p>Chargement de la partie…</p></div>
            <div v-else>
                <p v-if="error" class="message message-error">{{ error }}</p>

                <div class="opponents-row">
                    <div v-for="p in opponents" :key="p.id"
                         class="turn-indicator" :class="{ 'is-active': p.is_current_turn }">
                        <span class="turn-indicator-dot"></span>
                        {{ p.username }} — {{ p.hand_count }} carte(s) — score {{ p.score }}
                    </div>
                </div>

                <div class="center-row">
                    <div class="deck-stack" @click="drawCard" :title="'Pioche (' + state.draw_pile_count + ' cartes)'">
                        <div class="card-unit card-unit-back"></div>
                    </div>

                    <div class="discard-pile">
                        <div v-if="topDiscard" class="card-unit" :data-type="topDiscard.primary_type">
                            <img :src="topDiscard.sprite_url" :alt="topDiscard.name_fr">
                            <span class="card-unit-name">{{ topDiscard.name_fr }}</span>
                        </div>
                        <span v-if="state.active_type" class="badge" :data-type="state.active_type">
                            Type imposé : {{ state.active_type }}
                        </span>
                    </div>
                </div>

                <div v-if="pendingLegendaryCard" class="auth-card">
                    <p>Carte légendaire : choisis le prochain type à imposer.</p>
                    <div class="player-hand">
                        <button v-for="slug in allTypeSlugs" :key="slug"
                                class="badge" :data-type="slug"
                                @click="chooseDeclaredType(slug)">{{ slug }}</button>
                    </div>
                    <button class="btn btn-ghost" @click="cancelLegendaryChoice">Annuler</button>
                </div>

                <div class="my-hand-row">
                    <p class="turn-indicator" :class="{ 'is-active': isMyTurn }">
                        <span class="turn-indicator-dot"></span>
                        {{ isMyTurn ? "C'est votre tour" : "En attente des autres joueurs" }}
                    </p>
                    <div class="player-hand">
                        <div v-for="card in myHand" :key="card.id"
                             class="card-unit" :class="{ 'is-disabled': !isMyTurn }"
                             :data-type="card.primary_type"
                             @click="playCard(card)">
                            <img :src="card.sprite_url" :alt="card.name_fr">
                            <span class="card-unit-name">{{ card.name_fr }}</span>
                        </div>
                    </div>
                </div>

                <div v-if="state.status === 'TERMINEE'" class="score-board">
                    <h2>Partie terminée</h2>
                    <table>
                        <thead><tr><th>Joueur</th><th>Score</th></tr></thead>
                        <tbody>
                            <tr v-for="p in state.players" :key="p.id">
                                <td>{{ p.username }}</td>
                                <td>{{ p.score }}</td>
                            </tr>
                        </tbody>
                    </table>
                </div>
            </div>
        `,
    }).mount("#game-app");
})();
