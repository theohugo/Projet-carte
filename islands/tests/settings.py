from pokecarte.settings import *

# Les quatre nouveaux modes sont développés en parallèle. Cette suite reste
# autonome et ne dépend donc jamais d'un module voisin encore en construction.
INSTALLED_APPS = [app for app in INSTALLED_APPS if app not in {"metamorph", "rocket", "starterrace"}]
if "islands" not in INSTALLED_APPS:
    INSTALLED_APPS = [*INSTALLED_APPS, "islands"]

ROOT_URLCONF = "islands.tests.urls"
PASSWORD_HASHERS = ["django.contrib.auth.hashers.MD5PasswordHasher"]
