#!/bin/sh
set -e

python manage.py migrate --noinput
python manage.py seed_pokemon_cards
python manage.py collectstatic --noinput

exec "$@"
