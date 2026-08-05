"""Jeu d'icônes SVG inséré en ligne : ``{% icon "coin" %}``.

Les icônes sont dessinées en trait sur une grille de 24, sans remplissage :
elles prennent la couleur du texte qui les entoure et restent nettes à
n'importe quelle taille. Rien à télécharger, donc aucune requête en plus et
aucun décalage de mise en page au chargement.
"""

from django import template
from django.utils.html import format_html
from django.utils.safestring import mark_safe

from game.type_icons import type_icon_url

register = template.Library()

# Chaque entrée est le contenu du <svg> : viewBox 0 0 24 24, trait courant.
ICONS = {
    # Navigation
    "back": '<path d="M14.5 5.5 8 12l6.5 6.5"/>',
    "home": '<path d="M4 10.6 12 4l8 6.6"/><path d="M6.2 9.6V19h11.6V9.6"/>',
    "close": '<path d="m6.5 6.5 11 11m0-11-11 11"/>',
    "external": '<path d="M13.5 5.5H18.5V10.5"/><path d="m18.5 5.5-7 7"/>'
    '<path d="M17 14.5V18a1 1 0 0 1-1 1H6a1 1 0 0 1-1-1V8a1 1 0 0 1 1-1h3.5"/>',
    # Économie
    "coin": '<circle cx="12" cy="12" r="8.6"/><path d="M9.7 17V7h3.2a2.7 2.7 0 0 1 0 5.4H9.7"/>'
    '<path d="M7.9 14.6h5.4"/>',
    "pack": '<rect x="6" y="3.6" width="12" height="16.8" rx="1.8"/><path d="M6 7.6h12"/>'
    '<path d="M12 11v4"/>',
    "shop": '<path d="M5 8.5h14l-1.1 10a1.6 1.6 0 0 1-1.6 1.4H7.7a1.6 1.6 0 0 1-1.6-1.4Z"/>'
    '<path d="M9 8.5V7a3 3 0 0 1 6 0v1.5"/>',
    "collection": '<rect x="3.6" y="4.4" width="7" height="15.2" rx="1.4"/>'
    '<rect x="13.4" y="4.4" width="7" height="15.2" rx="1.4"/><path d="M13.4 10h7"/>',
    "quest": '<path d="M5 6.5h5.5M5 12h5.5M5 17.5h5.5"/>'
    '<path d="m14 6.2 1.6 1.6L19 4.5"/><path d="m14 11.7 1.6 1.6L19 10"/><path d="m14 17.2 1.6 1.6L19 15.5"/>',
    "star": '<path d="m12 4.6 2.3 4.7 5.2.8-3.8 3.7.9 5.2-4.6-2.5-4.6 2.5.9-5.2L4.5 10l5.2-.8Z"/>',
    "lock": '<rect x="5.4" y="10.4" width="13.2" height="9.2" rx="2"/>'
    '<path d="M8.6 10.4V7.8a3.4 3.4 0 0 1 6.8 0v2.6"/>',
    # Jeux
    "cards": '<rect x="9.4" y="5.2" width="9.6" height="13.6" rx="1.8"/>'
    '<path d="M6.6 7.4 5.2 8a1.8 1.8 0 0 0-1 2.3l3 8.2"/>',
    "guesswho": '<rect x="4.4" y="4.4" width="15.2" height="15.2" rx="2"/>'
    '<path d="M10 9.6a2.1 2.1 0 1 1 2.6 2.1v1.4"/><path d="M12.6 16.1h.01"/>',
    # Buste plein : c'est la silhouette elle-même, pas un contour comme "user".
    "silhouette": '<path fill="currentColor" stroke="none" d="M12 4.2a3.7 3.7 0 1 1 0 7.4 3.7 3.7 0 0 1 0-7.4Z"/>'
    '<path fill="currentColor" stroke="none" d="M12 12.8c3.9 0 7 2.5 7 5.6v1.4H5v-1.4c0-3.1 3.1-5.6 7-5.6Z"/>',
    "brush": '<path d="M6.4 14.6 14.9 6a2.4 2.4 0 0 1 3.4 3.4l-8.6 8.5"/>'
    '<path d="M6.4 14.6c-1.3.9-1.1 2.4-2.4 3.6 1.9.8 4.7.9 5.7-.3"/>',
    "dice": '<rect x="4.4" y="4.4" width="15.2" height="15.2" rx="3"/>'
    '<path d="M9 9h.01M15 9h.01M9 15h.01M15 15h.01M12 12h.01"/>',
    # Social
    "user": '<circle cx="12" cy="8.6" r="3.6"/><path d="M5.4 19.6a6.8 6.8 0 0 1 13.2 0"/>',
    "friends": '<circle cx="9.4" cy="8.8" r="3.2"/><path d="M3.8 19.4a5.8 5.8 0 0 1 11.2 0"/>'
    '<path d="M16 6a3.2 3.2 0 0 1 0 6.2"/><path d="M17.4 14.6a5.6 5.6 0 0 1 2.8 4.8"/>',
    "mail": '<rect x="3.6" y="5.6" width="16.8" height="12.8" rx="2"/><path d="m4.4 7.4 7.6 5.4 7.6-5.4"/>',
    "logout": '<path d="M14 5.6H7.4a1.8 1.8 0 0 0-1.8 1.8v9.2a1.8 1.8 0 0 0 1.8 1.8H14"/>'
    '<path d="M17.2 15.2 20.4 12l-3.2-3.2"/><path d="M20.4 12h-9"/>',
    "login": '<path d="M10 5.6h6.6a1.8 1.8 0 0 1 1.8 1.8v9.2a1.8 1.8 0 0 1-1.8 1.8H10"/>'
    '<path d="M6.8 15.2 3.6 12l3.2-3.2"/><path d="M3.6 12h9"/>',
    "signup": '<circle cx="10" cy="8.6" r="3.4"/><path d="M3.6 19.4a6.5 6.5 0 0 1 11.4-4.3"/>'
    '<path d="M17.6 14.4v5.2M15 17h5.2"/>',
    "play": '<path d="M8.6 5.8 18 12l-9.4 6.2Z"/>',
    "trophy": '<path d="M8 4.6h8v4.6a4 4 0 0 1-8 0Z"/><path d="M8 6.2H5.4v1.4a3 3 0 0 0 2.8 3"/>'
    '<path d="M16 6.2h2.6v1.4a3 3 0 0 1-2.8 3"/><path d="M12 13.2v3.2M9 19.4h6"/>',
}

DEFAULT_SIZE = 20
# Les pastilles de type sont fournies en 64 px ; on les rend en 20 pour rester
# nettes sur les écrans à forte densité.
TYPE_ICON_SIZE = 20


@register.simple_tag(name="icon")
def icon(name, extra_class=""):
    """Insère l'icône ``name``, décorative par défaut (aria-hidden)."""

    body = ICONS.get(name)
    if body is None:
        return ""

    classes = f"icon icon-{name}"
    if extra_class:
        classes = f"{classes} {extra_class}"

    return format_html(
        '<svg class="{}" viewBox="0 0 24 24" width="{}" height="{}" fill="none" '
        'stroke="currentColor" stroke-width="1.8" stroke-linecap="round" '
        'stroke-linejoin="round" aria-hidden="true" focusable="false">{}</svg>',
        classes,
        DEFAULT_SIZE,
        DEFAULT_SIZE,
        # Le corps vient de ce module, jamais d'une saisie : le marquer est sûr.
        mark_safe(body),
    )


@register.simple_tag(name="type_icon")
def type_icon(slug):
    """La pastille officielle d'un type : le symbole blanc sur son disque."""

    url = type_icon_url(slug)
    if not url:
        return ""

    return format_html(
        '<img class="type-icon" src="{}" width="{}" height="{}" alt="" '
        'aria-hidden="true" loading="lazy" decoding="async">',
        url,
        TYPE_ICON_SIZE,
        TYPE_ICON_SIZE,
    )
