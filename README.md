# Poké-Uno

Plateforme web de jeu de cartes façon Uno, avec des cartes Pokémon à la place des enseignes classiques. Projet Django réalisé pour le cours IPSSI (cahier des charges : voir le skill [`projet-cartes`](.claude/skills/projet-cartes/SKILL.md)).

**Auteurs :** Hugo Raguin, Amine Taleb, Rizlene Berrag

![Capture d'écran de la partie](docs/screenshot.png)
*(à ajouter : capture d'écran du plateau de jeu en cours de partie)*

## Règles du jeu

- 2 à 6 joueurs. Chacun reçoit 7 cartes Pokémon en main au démarrage.
- À son tour, un joueur pose une carte de sa main sur la défausse si elle partage une **famille de types** ou l'**espèce** (même Pokémon) avec la carte du dessus — sinon il doit piocher.
- Les cartes **légendaires** sont des jokers : elles se posent sur n'importe quelle carte, et leur propriétaire choisit la famille imposée au joueur suivant.
- Quatre pouvoirs complètent les cartes normales : **+2** (pioche 2 et passe le tour), **+4** (joker, choisit une famille, pioche 4 et passe le tour), **Inversion** (change le sens de jeu) et **Protection** (pose un bouclier personnel).
- Un bouclier reste actif jusqu'au prochain +2/+4 qui vise ce joueur : il annule la pioche et le saut de tour, puis il est consommé.
- Les 18 types Pokémon authentiques restent visibles sur les cartes, mais les règles les rassemblent en **8 familles** pour rendre les coups jouables plus fréquents. Chaque famille représente 8 à 9 espèces, soit 16 à 18 cartes dans le paquet de 108 cartes.
- Piocher une carte termine le tour, que le joueur puisse ensuite la jouer ou non (pas de rejeu immédiat en v1).
- Si la pioche est épuisée, la défausse est remélangée (sauf la carte du dessus) pour reconstituer la pioche.
- Le premier joueur à vider sa main gagne la partie. Son score s'incrémente de la valeur des cartes restantes dans la main de chaque adversaire (10 pts/carte normale, 25 pts/carte légendaire).

### Les 8 familles de types

Une carte double-type appartient à chacune des familles représentées par ses types. Si ses deux types sont dans la même famille, elle n'y est comptée qu'une fois. Les nombres ci-dessous correspondent au catalogue actif ; les deux exemplaires de chaque espèce doublent le nombre de cartes physiques.

| Famille de jeu | Types Pokémon regroupés | Espèces | Cartes |
| --- | --- | ---: | ---: |
| Écosystème toxique | Insecte, Plante, Poison | 9 | 18 |
| Royaume des ombres | Spectre, Ténèbres | 8 | 16 |
| Forge tellurique | Sol, Roche, Acier | 9 | 18 |
| Arcane | Psy, Fée | 8 | 16 |
| Marées gelées | Eau, Glace | 8 | 16 |
| Ciel ardent | Feu, Vol | 8 | 16 |
| Instinct combatif | Normal, Combat | 9 | 18 |
| Tempête draconique | Électrik, Dragon | 8 | 16 |

Cette répartition conserve l'identité des 18 types et l'intérêt des double-types, tout en limitant les correspondances à huit familles avec un écart maximal d'une espèce entre elles.

### Joueurs IA

- Dans le lobby, l'hôte peut ajouter ou retirer des joueurs IA tant que la partie n'a pas commencé. Une IA occupe une place comme un joueur humain, sans créer de faux compte Django.
- À son tour, l'IA joue automatiquement une carte valide ou pioche si aucune carte ne convient. Elle choisit aussi une famille lorsqu'elle utilise un légendaire ou un +4. Comme le jeu est piloté sans worker de tâches, au moins un participant doit garder le plateau ouvert pour déclencher les tours IA ; une partie laissée sans navigateur reprend dès le retour d'un joueur.
- Plusieurs navigateurs peuvent détecter le même tour d'IA sans provoquer plusieurs coups : chaque passage au tour suivant incrémente `Game.turn_revision`, et l'appel transmet `expected_turn_revision`. Le serveur verrouille la partie et ignore comme un *no-op* toute révision devenue obsolète.

## Démarrage rapide

```bash
cp .env.example .env   # éditer SECRET_KEY / POSTGRES_PASSWORD si besoin
docker compose up --build
```

L'application est disponible sur http://localhost:8000. Les migrations, le seed des cartes Pokémon (depuis le fixture committé, sans accès réseau) et `collectstatic` s'exécutent automatiquement au démarrage du conteneur `web`.

Pour créer un compte administrateur (accès à `/admin/`) :

```bash
docker compose exec web python manage.py createsuperuser
```

### En local, sans Docker (avec uv)

```bash
uv sync
uv run python manage.py migrate
uv run python manage.py seed_pokemon_cards
uv run python manage.py runserver
```

### Avec Task

```bash
task run     # serveur de dev
task test    # suite de tests
task check   # manage.py check
task lint    # ruff
task docker:up
```

## Architecture logicielle

### Modèles ORM

```mermaid
classDiagram
    User "1" -- "0..1" Profile
    User "0..1" -- "*" GamePlayer : contrôle humain
    Game "1" -- "*" GamePlayer : players
    Game "1" -- "*" GameCard : cards
    Game "1" -- "*" MoveLog : historique
    PokemonType "1" -- "*" PokemonCard : primary_type
    PokemonCard "1" -- "*" GameCard : instances
    GamePlayer "1" -- "*" GameCard : main (owner)
    GamePlayer "1" -- "*" MoveLog : moves

    class Game {
        +UUID id
        +status
        +current_turn_number
        +turn_revision
        +active_family
        +card_sequence_counter
    }
    class GameCard {
        +location
        +order_index
    }
    class PokemonCard {
        +pokedex_id
        +is_legendary
        +action
    }
    class GamePlayer {
        +user nullable
        +bot_name
        +turn_order
        +has_protection
    }
    class MoveLog {
        +move_type
        +declared_family
    }
```

`GameCard` est la pièce centrale du modèle : une ligne = une carte physique dans une partie précise (pioche, main d'un joueur, ou défausse), positionnée par `location` + `order_index` — pas de blob JSON pour représenter les piles. Un compteur monotone (`Game.card_sequence_counter`) horodate chaque déplacement de carte ; le dessus de la défausse et la prochaine carte à piocher se déduisent d'un simple tri sur `order_index`.

`Game.active_family` et `MoveLog.declared_family` portent désormais la règle de correspondance parmi les huit familles. `GamePlayer` représente indifféremment un humain (`user`) ou une IA (`bot_name`), avec une contrainte garantissant qu'un seul de ces deux contrôleurs est défini. `Game.turn_revision` versionne les transitions de tour afin de rendre le déclenchement distribué des IA idempotent.

### Machine à états d'une partie

```mermaid
stateDiagram-v2
    [*] --> EN_ATTENTE : create_game()
    EN_ATTENTE --> EN_ATTENTE : add_player() [places restantes]
    EN_ATTENTE --> EN_ATTENTE : add_bot() / remove_bot() [hôte]
    EN_ATTENTE --> EN_COURS : start_game() [>= 2 joueurs]
    EN_COURS --> EN_COURS : play_card() / draw_card() [humain]
    EN_COURS --> EN_COURS : perform_bot_turn() [IA]
    EN_COURS --> TERMINEE : play_card() [main vide]
    TERMINEE --> [*]
```

### Séparation des responsabilités (MVT + SRP)

Toute la logique métier (distribution, validation des coups, mélange, tour par tour, fin de partie et score) vit dans `game/game_engine.py`, isolée des vues Django — aucune dépendance à `request`/`response`, testable en pur Python. La stratégie déterministe des IA vit dans `game/bot_player.py`. Les vues (`game/views.py`, `game/api.py`) se contentent d'appeler ces services et de traduire leurs exceptions (`NotYourTurnError`, `InvalidMoveError`, ...) en réponses HTTP.

### Multijoueur en réseau

- Comptes réels via l'authentification Django (inscription/connexion).
- Un lobby permet de créer ou rejoindre une partie en attente et à son hôte d'ajouter ou retirer des IA (jusqu'à `max_players`).
- Chaque coup est validé côté serveur (tour du bon joueur, carte réellement en main, règle famille/espèce respectée) — impossible de tricher en trafiquant la requête client.
- Le plateau interroge `GET /api/games/<id>/state/` toutes les 2 secondes : plusieurs joueurs connectés depuis des navigateurs différents (y compris sur le même réseau local, via l'IP LAN de la machine hôte) voient la partie évoluer en quasi temps réel sans WebSocket.
- Lorsqu'une IA devient le joueur courant, le plateau appelle `POST /api/games/<id>/bot-turn/` avec la révision observée. La transaction, le verrou de ligne et le contrôle de `turn_revision` garantissent qu'un seul coup est appliqué, même si plusieurs clients envoient la demande simultanément.
- `GameEngine.get_game_state()` ne renvoie **jamais** la main d'un adversaire (seulement son nombre de cartes) — règle portée par le moteur, vérifiée par des tests bout en bout sur l'endpoint HTTP réel.

## Choix UI/UX & Design Tokens

- **Design Tokens** (`static/tokens.css`) : une variable de couleur par type Pokémon (18 identités visuelles authentiques, regroupées en 8 familles pour les règles), plus espacements, typographie, rayons et transitions. Aucune couleur ni espacement codé en dur ailleurs — `atoms.css`/`molecules.css`/`organisms.css` ne font que consommer ces variables.
- **Atomic Design** :
  - *Atomes* (`atoms.css`) : `.card-unit` (une carte), `.badge` (type/statut), `.btn`.
  - *Molécules* (`molecules.css`) : `.player-hand` (main d'un joueur), `.deck-stack` (pioche), `.discard-pile`, `.turn-indicator` (indicateur de tour actif).
  - *Organismes* (`organisms.css`) : `.game-table` (plateau complet), `.score-board` (tableau des scores en fin de partie).
- **Retour visuel** : transition CSS au survol/jeu d'une carte, halo vert (`--color-turn-active`) sur le joueur dont c'est le tour.
- **Frontend interactif** : Vue 3 (vendorisé localement dans `static/vendor/`, pas de CDN externe au runtime) monté uniquement sur `.game-table`, qui réutilise exactement les mêmes classes CSS que les pages server-rendered — les Design Tokens/Atomic Design du cahier des charges s'appliquent donc identiquement, que le HTML soit rendu par Django ou par Vue.

## Qualité, tests & CI

- Suite de tests Django (`game/tests/`) : modèles (contraintes d'unicité et contrôleur humain/IA), moteur de jeu (distribution, actions, familles, mélange, rotation du tour, score), IA (choix, pioche, victoire, sélection de famille et idempotence), vues/API (permissions, CSRF, synchronisation, anti-fuite de la main adverse), rendu du plateau et équilibrage des huit familles.
- Lint `ruff` + formatage `black` (config dans `pyproject.toml`, 110 colonnes, migrations exclues).
- CI GitHub Actions (`.github/workflows/ci.yml`) : services PostgreSQL + Redis, lint, format check, migrations, suite de tests — à chaque push et pull request.

## Journal d'architecture & auto-évaluation

Déviations assumées par rapport au cahier des charges, documentées ici plutôt que silencieuses :

- **Python 3.13 au lieu de `python:3.11-slim`** littéralement mentionné dans le sujet : Django 6.0 exige Python ≥ 3.12.
- **Vue 3 vendorisé** plutôt qu'un `<script src="cdn...">` : le critère éliminatoire « démarre sans erreur via `docker compose up` » ne doit pas dépendre d'un accès réseau tiers au runtime.
- **Catalogue actif de 54 Pokémon** (voir `game/management/commands/_pokedex_selection.py`) : les 18 types restent affichés et les double-types sont conservés, tout comme les 3 lignées de starters et les 5 légendaires/mythiques de la Gen 1. Pour le jeu, ils sont rassemblés par `game/type_families.py` en huit familles optimisées à 8 ou 9 espèces chacune. Deux exemplaires de chaque espèce donnent une pioche stable de 108 cartes et 16 à 18 cartes représentatives par famille. Les anciennes espèces déjà utilisées par une partie sont conservées pour l'historique mais désactivées des nouvelles pioches.
- **Polling (2s) plutôt que WebSocket** pour synchroniser l'état entre joueurs : suffisant pour un jeu au tour par tour, et beaucoup plus simple à containeriser correctement (pas de serveur ASGI dédié à mettre en place dans le temps imparti). Piste d'amélioration évidente pour une v2.
- **Piocher termine toujours le tour** (pas de "piocher puis rejouer si jouable" comme dans certaines variantes d'Uno) : règle simplifiée pour une v1, à faire évoluer si le temps le permet.

Difficultés rencontrées : la représentation correcte de la pioche/main/défausse en base relationnelle (sans blob JSON) a demandé de définir une règle unique et non ambiguë (`order_index` + compteur monotone par partie) plutôt que trois mécanismes différents — une fois cette règle posée, la pioche, la défausse et le remélange s'expriment tous comme de simples `order_by`/`filter`, ce qui a beaucoup simplifié les tests.

Répartition du travail : *(à compléter par l'équipe — qui a porté le moteur de jeu, qui a porté les Design Tokens/Atomic Design, qui a porté Docker/CI/README)*.
