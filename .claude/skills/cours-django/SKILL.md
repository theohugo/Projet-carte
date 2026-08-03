---
name: cours-django
description: Cours et références Django — architecture MVT, setup avec uv, tutoriel officiel Django, repo de référence du prof (django-intro).
---

# Django

## Architecture MVT

Django est un framework web Python open-source de haut niveau qui privilégie un développement rapide et une conception propre, selon sa philosophie « batteries incluses » (sécurité, authentification, administration et accès aux données intégrés dès l'installation). Au cœur de tout projet Django se trouve l'architecture **MVT (Model-View-Template)**.

### Les trois composants (analogie du restaurant)

**1. Le Model — « Le Garde-Manger & la Réserve »**
Gère les données de l'application via l'ORM (Object-Relational Mapping), sans nécessiter d'écrire du SQL brut :
- Structure et types de données
- Règles de validation et relations (1-N, N-N)
- Opérations CRUD (Create, Read, Update, Delete)

**2. La View — « Le Chef Cuisinier »**
Contient la logique métier : reçoit la requête, interroge le Model pour récupérer les données, puis prépare la réponse :
- Traitement de la requête HTTP
- Appel des méthodes du Model
- Sélection du Template approprié et transmission du contexte

**3. Le Template — « Le Dressage de l'Assiette »**
S'occupe de la présentation visuelle : un fichier HTML enrichi du langage de gabarit Django (DTL) qui affiche dynamiquement les données reçues de la Vue :
- Structure HTML/CSS
- Variables et filtres (`{{ article.titre }}`)
- Structures de contrôle (`{% for item in liste %}`)

### Différence avec le MVC classique

Dans le modèle **MVC** traditionnel, le **Controller** reçoit la requête et pilote la logique, tandis que la **View** affiche l'interface utilisateur. En **MVT** Django, les rôles sont redistribués :
- Le rôle du **Controller** est pris en charge par le **framework Django lui-même** (le routeur d'URL `urls.py` et le middleware d'aiguillage).
- La **View** Django correspond en réalité au **Controller** du MVC (gestion de la logique métier).
- Le **Template** Django correspond à la **View** du MVC (rendu visuel HTML).

### Cycle de requête HTTP

1. **Acheminement (URL Dispatcher)** : la requête arrive dans `urls.py`, qui compare l'URL demandée aux motifs déclarés (URL patterns).
2. **Exécution de la Vue** : l'URL associée pointe vers une fonction/classe dans `views.py`.
3. **Accès aux données (ORM)** : la Vue communique avec `models.py` pour lire/modifier la base de données.
4. **Combinaison avec le Template** : la Vue injecte les données (le contexte) dans un fichier HTML du dossier `templates/`.
5. **Réponse HTTP** : Django génère le HTML final et le renvoie au navigateur avec un code statut (ex. `200 OK`).

### Exemple de code (structure typique)

```python
# mysite/urls.py
from django.urls import path
from . import views

urlpatterns = [
    path('articles/<int:id>/', views.article_detail, name='article_detail'),
]
```

```python
# blog/models.py
from django.db import models

class Article(models.Model):
    titre = models.CharField(max_length=200)
    contenu = models.TextField()
    date_publication = models.DateTimeField(auto_now_add=True)
    publie = models.BooleanField(default=True)

    def __str__(self):
        return self.titre
```

```python
# blog/views.py
from django.shortcuts import render, get_object_or_404
from .models import Article

def article_detail(request, id):
    article = get_object_or_404(Article, pk=id, publie=True)
    context = {'article': article, 'titre_page': f"Article : {article.titre}"}
    return render(request, 'blog/article_detail.html', context)
```

### Avantages sécurité intégrés du MVT

- **Anti-injection SQL** : l'ORM paramètre automatiquement toutes les requêtes, éliminant le risque d'injection.
- **Protection XSS native** : le moteur de Template (DTL) échappe automatiquement les caractères HTML dangereux dans les variables.
- **Protection CSRF** : Django requiert le jeton `{% csrf_token %}` dans tout formulaire `POST` ; toute requête inter-site non authentifiée par ce jeton est rejetée (erreur 403).

### Commandes clés

- `python manage.py makemigrations` : génère les scripts de migration à partir des modifications de `models.py`.
- `python manage.py migrate` : applique les migrations en base de données.
- `python manage.py runserver` : lance le serveur de développement local sur `http://127.0.0.1:8000/`.

**Lien :** https://modules.apti.space/developpement/django/architecture-mvt

## Set up a Django project with uv

Workflow rapide pour initialiser un projet Django avec [uv](https://docs.astral.sh/uv/) (toutes les commandes passent par `uv run`, pas d'activation manuelle de venv ; `.python-version` fige la version Python ; `uv.lock` garantit un environnement reproductible via `uv sync`).

```bash
uv init --python 3.13
uv venv
uv add django
uv run django-admin startproject django_intro .
uv run python manage.py migrate
uv run python manage.py runserver
uv run python manage.py startapp <nom_app>
uv run python manage.py check
```

Ne pas oublier d'enregistrer l'app créée dans `INSTALLED_APPS` (`django_intro/settings.py`), sinon `manage.py check` échoue silencieusement à la détecter.

**Lien :** https://pydevtools.com/handbook/tutorial/set-up-a-django-project-with-uv/

## Repo de référence du prof — django-intro

https://github.com/aptitek/django-intro — implémentation de référence du setup ci-dessus : projet `django_intro`, app `ehlo` avec une vue `index` (`HttpResponse("Ehlo World!")`) routée sur `/`, et un `Taskfile.yml` (via [Task](https://taskfile.dev/)) avec les tâches `run`, `check`, `lint`, `lint:fix`, `test`, `preview`, `clean`. Déjà repris dans `PROJET-COURS/` de ce repo.

**Lien :** https://github.com/aptitek/django-intro

## Tutoriel officiel Django — Écrire sa première application, partie 1

Guide la création d'une application de sondage (« polls ») en Django : création du projet, structure générée, création d'une app, première vue, configuration des URLs.

### 1. Créer le projet Django

```bash
django-admin startproject mysite djangotutorial
```

```
djangotutorial/
    manage.py
    mysite/
        __init__.py
        settings.py   # paramètres et configuration du projet
        urls.py       # table de routage du projet
        asgi.py       # point d'entrée ASGI
        wsgi.py       # point d'entrée WSGI
```

### 2. Vérifier l'installation

```bash
python manage.py runserver
```

`http://127.0.0.1:8000/` doit afficher la page « Congratulations! ».

### 3. Créer l'application « polls »

```bash
python manage.py startapp polls
```

```
polls/
    __init__.py
    admin.py
    apps.py
    migrations/
        __init__.py
    models.py
    tests.py
    views.py
```

### 4. Écrire la première vue (`polls/views.py`)

```python
from django.http import HttpResponse

def index(request):
    return HttpResponse("Hello, world. You're at the polls index.")
```

### 5. Créer `polls/urls.py`

```python
from django.urls import path
from . import views

urlpatterns = [
    path("", views.index, name="index"),
]
```

### 6. Inclure les URLs de l'app dans le projet (`mysite/urls.py`)

```python
from django.contrib import admin
from django.urls import include, path

urlpatterns = [
    path("polls/", include("polls.urls")),
    path("admin/", admin.site.urls),
]
```

`include()` permet de brancher les URLs de l'app sous n'importe quel préfixe, gardant l'app découplée du reste du projet.

### 7. Lancer le serveur et tester

`http://localhost:8000/polls/` doit afficher **« Hello, world. You're at the polls index. »**

Le serveur de dev recharge automatiquement le code à chaque modification, mais un redémarrage manuel est requis lors de l'ajout de nouveaux fichiers.

**Lien :** https://docs.djangoproject.com/en/6.0/intro/tutorial01/
