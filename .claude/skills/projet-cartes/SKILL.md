---
name: projet-cartes
description: Cahier des charges et grille de notation du projet "Plateforme de Jeu de Cartes" (Django, PostgreSQL, Redis, Docker Compose, UI/UX Design Tokens/Atomic Design) — référence à consulter pendant le développement de PROJET-CARTES.
---

# 🃏 Projet Django Artisanal : Plateforme de Jeu de Cartes Web

## Contexte & Objectifs

Développement **artisanal et guidé** (pas de génération IA autonome) : maîtriser chaque ligne de code, chaque modèle ORM, chaque choix d'infrastructure.

Objectif : concevoir, développer et déployer une **plateforme web de jeu de cartes** (ex : *Bataille*, *Blackjack*, *Belote*, *Uno* ou *Tarot simplifié*) basée sur **Django**. Le projet fait le pont entre développement web (Django), intégration UI/UX (Design Tokens, Atomic Design) et infrastructure (Docker & Compose).

Pourquoi le code manuel :
- **ORM et algorithmes** : gestion d'une main de cartes, mélange de paquet (*shuffle*), validation des coups, machine à états d'une partie → logique pure sans bugs d'effets de bord.
- **Design System** : jeu de cartes réactif → maîtrise fine des CSS Design Tokens et composants atomiques.
- **Infra** : Docker Compose manuel, isolation PostgreSQL/Django → compréhension concrète des réseaux et volumes de conteneurs.

## Modalités de Rendu

- **Groupe :** 1 à 3 personnes.
- **Livrable :** lien vers un dépôt **GitHub Public**.
- **Environnement :** doit s'exécuter localement en **une seule commande** : `docker compose up --build`.
- **Organisation Git :** commits atomiques et explicites, répartition claire du travail dans l'équipe (pas de commit unique monolithique).

## Spécifications Techniques Obligatoires

### 🐍 Backend & Logique Métier Django

- **Modélisation ORM complète :**
  - `Game` / `Session` : état de la partie (`EN_ATTENTE`, `EN_COURS`, `TERMINEE`), tour actuel, joueurs.
  - `Player` / `Profile` : auth Django, statistiques, score.
  - `Card` & `Deck` : enseignes, valeurs, méthodes d'action (`draw()`, `shuffle()`).
  - `MoveLog` : historique traçable des coups joués.
- **Architecture MVT & SRP :**
  - Moteur de jeu isolé dans `game_engine.py`, en dehors des vues Django.
  - Vues basées sur formulaires ou API AJAX/Fetch (interaction sans rechargement complet si souhaité).
- **Sécurité & Authentification :**
  - Validation stricte des règles côté serveur (impossible de tricher en modifiant la requête client).
  - CSRF Tokens activés, sessions sécurisées.

### 🎨 Frontend, UI/UX & Design Tokens

- **Design System & Tokens :** variables CSS centralisées (`tokens.css`/SCSS) : couleurs des enseignes (Cœur, Carreau, Pique, Trèfle), espacements, typographies.
- **Atomic Design :**
  - Atomes : cartes individuelles (`.card-unit`), badges d'état, boutons d'action.
  - Molécules : main du joueur (`.player-hand`), pioche (`.deck-stack`), zone d'action.
  - Organismes : tapis de jeu réactif (`.game-table`), tableau de bord des scores.
- **Retours Visuels & Ergonomie :** transitions CSS fluides (survol/jeu d'une carte), indication claire du tour de jeu actuel et du joueur actif.

### 🐳 Infrastructure & Docker Compose

- **Dockerfile :** image Python légère (`python:3.11-slim`), utilisateur **non-root**, migrations (`manage.py migrate`) et `collectstatic` automatisés.
- **`docker-compose.yml` multi-services :**
  - `web` : Django via Gunicorn/Uvicorn.
  - `db` : PostgreSQL, volume nommé persistant (`postgres_data`).
  - `cache` : Redis (sessions + cache de l'état de jeu).
- **Réseau & Isolement :** variables d'environnement (`.env`) pour `SECRET_KEY`, `POSTGRES_PASSWORD`, etc. ; réseau privé conteneurisé ; **healthchecks** pour que Django attende PostgreSQL avant de démarrer.

### 🧪 DevOps, QA & Qualité de Code

- **Tests automatisés Django (`tests.py`) :** distribution des cartes, comptage des points, transitions d'état (unitaires) ; vues Django et permissions d'accès (intégration).
- **Clean Code :** PEP8, linting `flake8`/`ruff`, formatage `black`.
- **CI/CD (GitHub Actions) :** pipeline exécutant linter + suite de tests à chaque `push`/`pull_request`.

## Le Rapport Technique (README.md)

1. **Présentation & En-tête :** noms/prénoms, règles du jeu retenu, capture d'écran de l'interface principale.
2. **Guide de Démarrage Rapide :** instructions exactes pour `docker compose up --build` + création d'un compte admin.
3. **Architecture Logicielle (UML/ERD) :** diagramme de classes des modèles ORM (Cartes, Joueurs, Parties) ; schéma de la Machine à États régissant les tours.
4. **Choix UI/UX & Design Tokens :** structure des tokens, hiérarchie Atomic Design.
5. **Journal d'Architecture & Auto-Évaluation :** rétrospective sur le code manuel, difficultés ORM/Docker et résolutions.

## 📝 Fiche de Notation (20 Points)

### 🚫 Critères Éliminatoires (Go / No-Go)

*Si une case est "NON", le projet n'est pas corrigé (Note = 0 ou rattrapage).*

- Présence du `README.md` complet avec guide de lancement et schémas.
- L'application démarre sans erreur via `docker compose up` avec PostgreSQL.
- La boucle de jeu complète (distribution, tours, fin de partie, calcul de score) est jouable.
- Le code métier backend/frontend est rédigé et maîtrisé par les étudiants (pas de copier-coller brut).

### 📊 Grille Détaillée

**Backend Django & Modélisation Métier (6 pts)**
| Critère | Détail | Note |
|---|---|---|
| Modélisation ORM & SRP | Modèles (Game, Player, Card, Deck) propres, indexés, découplage métier | / 2.5 |
| Logique de Jeu & Moteur | `game_engine.py` gère machine à états, mélange, validation des coups | / 2.5 |
| Sécurité & Sessions | Droits, CSRF, sécurité de l'authentification | / 1 |

**UI/UX & Design System (5 pts)**
| Critère | Détail | Note |
|---|---|---|
| Design Tokens (CSS) | Variables de design (enseignes, thèmes, espacements), pas de valeurs codées en dur | / 2 |
| Atomic Design & Ergonomie | Composants hiérarchisés, interface réactive | / 2 |
| Feedback Visuel | Transitions soignées, joueur actif/score clairs | / 1 |

**DevOps, Docker & Infrastructure (5 pts)**
| Critère | Détail | Note |
|---|---|---|
| Dockerfile Prod/Dev | Optimisé, multi-stage/slim, non-root, gestion des statiques | / 2 |
| Orchestration Compose | `docker-compose.yml` : Django + PostgreSQL + Redis, volumes nommés | / 2 |
| Variables & Healthchecks | Isolation `.env`, `depends_on` avec `healthcheck` | / 1 |

**Qualité du Code, Tests & QA (4 pts)**
| Critère | Détail | Note |
|---|---|---|
| Tests Automatisés Django | Couverture modèles/règles/vues par `TestCase` | / 2 |
| Linting & Propreté Git | `black`/`ruff`, historique de commits clair et collaboratif | / 1 |
| Intégration Continue (CI) | Pipeline GitHub Actions : tests + linter à chaque commit/PR | / 1 |

## Notes pour ce projet précis (PROJET-CARTES)

- Thème choisi : cartes **Pokémon** (au lieu des enseignes classiques Cœur/Carreau/Pique/Trèfle) — noms et images à récupérer via une API externe (voir [[cours-django]] pour les notions Django de base), en **français et anglais**.
- Équipe : Hugo Raguin, Amine TALEB, Rizlene Berrag.
- Frontend souhaité en **Vue 3** si possible, en plus/à la place des templates Django classiques — à concilier avec l'exigence Design Tokens/Atomic Design du cahier des charges.
- Voir aussi [[cours-docker]] pour les commandes Docker et [[cours-ui-ux]] pour la théorie couleurs/icônes utile aux Design Tokens.

**Lien :** https://modules.apti.space/projets/jeu-de-cartes-django
