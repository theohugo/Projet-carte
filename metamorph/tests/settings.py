from pokecarte.settings import *

if "metamorph" not in INSTALLED_APPS:
    INSTALLED_APPS = [*INSTALLED_APPS, "metamorph"]

ROOT_URLCONF = "metamorph.tests.urls"
PASSWORD_HASHERS = ["django.contrib.auth.hashers.MD5PasswordHasher"]
