"""Points d'entrée SEO publics de PokéTable.

La liste du sitemap est volontairement fermée : ajouter une nouvelle route au
projet ne doit jamais publier par accident une table de jeu, un profil ou une
page de compte.
"""

from dataclasses import dataclass

from django.http import HttpRequest, HttpResponse
from django.shortcuts import render
from django.urls import reverse
from django.views.decorators.http import require_safe


@dataclass(frozen=True, slots=True)
class PublicPage:
    route_name: str
    change_frequency: str = "weekly"
    priority: str = "0.8"


PUBLIC_INDEX_PAGES = (
    PublicPage("home", change_frequency="weekly", priority="1.0"),
    PublicPage("lobby"),
    PublicPage("guesswho:lobby"),
    PublicPage("silhouette:lobby"),
    PublicPage("pictionary:lobby"),
    PublicPage("metamorph:lobby"),
    PublicPage("rocket:lobby"),
    PublicPage("islands:lobby"),
    PublicPage("starterrace:lobby"),
)


def _public_response_headers(response: HttpResponse, *, max_age: int) -> HttpResponse:
    response["Content-Language"] = "fr"
    response["Cache-Control"] = f"public, max-age={max_age}"
    response["X-Content-Type-Options"] = "nosniff"
    return response


@require_safe
def robots_txt(request: HttpRequest) -> HttpResponse:
    response = render(
        request,
        "seo/robots.txt",
        {"sitemap_url": request.build_absolute_uri(reverse("sitemap_xml"))},
        content_type="text/plain; charset=utf-8",
    )
    return _public_response_headers(response, max_age=86_400)


@require_safe
def sitemap_xml(request: HttpRequest) -> HttpResponse:
    entries = [
        {
            "location": request.build_absolute_uri(reverse(page.route_name)),
            "change_frequency": page.change_frequency,
            "priority": page.priority,
        }
        for page in PUBLIC_INDEX_PAGES
    ]
    response = render(
        request,
        "seo/sitemap.xml",
        {"entries": entries},
        content_type="application/xml; charset=utf-8",
    )
    return _public_response_headers(response, max_age=3_600)
