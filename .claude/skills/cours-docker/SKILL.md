---
name: cours-docker
description: Aide-mémoire Docker — commandes CLI (conteneurs, images, logs, nettoyage) classées par catégorie, référence de cours pour ce projet.
---

# Docker

## Aide-Mémoire Docker

Synthèse des commandes indispensables de la CLI Docker, classées par thématique.

### Anatomie de la commande `docker run`

```bash
# Squelette général
docker run [OPTIONS] IMAGE [COMMANDE]

# Exemple complet combinant les options courantes
docker run -d --rm --name mon-app -p 8080:80 -v $PWD/app:/app -e ENV=production nginx:alpine
```

```bash
-d                      # Mode détaché : exécute le conteneur en arrière-plan
--rm                    # Supprime automatiquement le conteneur à son arrêt
--name mon-app          # Nom personnalisé du conteneur
-p 8080:80              # Redirige le port hôte 8080 vers le port 80 du conteneur (HOTE:CONTENEUR)
-v $PWD/app:/app         # Monte un volume (persistance/dev)
-e ENV=production        # Injecte une variable d'environnement
```

### 1. Gestion des Conteneurs

```bash
docker run -d -p 80:80 --name web nginx   # Créer et démarrer un conteneur
docker ps                                  # Lister les conteneurs actifs
docker ps -a                               # Lister TOUS les conteneurs (actifs + arrêtés)
docker stop mon-conteneur                  # Arrêt propre (SIGTERM)
docker start mon-conteneur                 # Redémarrer un conteneur arrêté
docker restart mon-conteneur               # stop + start
docker kill mon-conteneur                  # Arrêt immédiat (SIGKILL)
docker rm mon-conteneur                    # Supprimer un conteneur arrêté
docker rm -f mon-conteneur                 # Forcer l'arrêt PUIS supprimer
```

Cycle de vie : `run` (créer+démarrer) → `stop`/`kill` → `start`/`restart` → `rm`. `docker ps`/`docker ps -a` pour surveiller l'état.

### 2. Gestion des Images

```bash
docker build -t mon-app:1.0 .     # Construire depuis un Dockerfile
docker images                      # Lister les images locales
docker pull postgres:15            # Télécharger depuis un registry
docker push mon-pseudo/mon-app:1.0 # Publier vers un registry
docker rmi nginx:latest            # Supprimer une image locale
docker tag app:latest app:v1.0     # Retag / alias
docker history mon-app             # Couches (layers) et instructions Dockerfile associées
```

Flux typique : `build` → `tag` → `push` (publication) ; `pull` → `run` (consommation).

### 3. Logs, Inspection & Diagnostic

```bash
docker logs mon-conteneur                  # Journaux du conteneur
docker logs -f --tail 100 mon-conteneur    # Suivre en temps réel, 100 dernières lignes
docker exec -it mon-conteneur bash         # Shell interactif dans le conteneur
docker inspect mon-conteneur               # Métadonnées JSON complètes
docker stats                               # Conso CPU/RAM/réseau en direct
docker top mon-conteneur                   # Processus internes du conteneur
```

`docker exec -it ... bash` = commande de débogage la plus utilisée. `docker logs -f` pour suivre une appli en direct. `docker stats`/`docker top` pour diagnostiquer perf. `docker inspect` pour la config précise (IP, volumes, env...).

### 4. Maintenance et Nettoyage de l'Espace Disque

Niveau de danger croissant :

```bash
docker system df                       # 🟢 Utilisation disque détaillée
docker image prune                     # 🟢 Purge les images "dangling" (orphelines)
docker container prune                 # 🟡 Purge TOUS les conteneurs arrêtés
docker volume prune                    # 🟠 Purge les volumes non rattachés (perte de données possible)
docker system prune -a --volumes       # 🔴 Grand nettoyage : tout ce qui n'est pas utilisé
```

Toujours commencer par `docker system df` avant une purge. Être prudent avec `--volumes` — dans un contexte Django, les volumes contiennent souvent la base (Postgres) ou les médias uploadés.

**Lien :** https://modules.apti.space/docker/cheatsheet
