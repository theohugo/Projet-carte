from pokecarte.settings import *

if "starterrace" not in INSTALLED_APPS:
    INSTALLED_APPS = [*INSTALLED_APPS, "starterrace"]

ROOT_URLCONF = "starterrace.tests.urls"
PASSWORD_HASHERS = ["django.contrib.auth.hashers.MD5PasswordHasher"]
