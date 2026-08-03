from pokecarte.settings import *

if "guesswho" not in INSTALLED_APPS:
    INSTALLED_APPS = [*INSTALLED_APPS, "guesswho"]
ROOT_URLCONF = "guesswho.tests.urls"
PASSWORD_HASHERS = ["django.contrib.auth.hashers.MD5PasswordHasher"]
