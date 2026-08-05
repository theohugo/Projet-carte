import html
import json
import re
from xml.etree import ElementTree

from django.contrib.auth.models import User
from django.template import engines
from django.test import RequestFactory, SimpleTestCase, TestCase, override_settings
from django.urls import reverse

from game.tests.i18n import LanguageIsolationMixin
from pokecarte.seo import PUBLIC_INDEX_PAGES


@override_settings(ALLOWED_HOSTS=["testserver", "poketable.example"])
class SeoEndpointTests(SimpleTestCase):
    def test_robots_is_plain_text_absolute_and_blocks_private_areas(self):
        response = self.client.get(
            reverse("robots_txt"),
            HTTP_HOST="poketable.example",
            HTTP_X_FORWARDED_PROTO="https",
        )

        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.headers["Content-Type"], "text/plain; charset=utf-8")
        self.assertEqual(response.headers["Content-Language"], "fr")
        self.assertEqual(response.headers["X-Content-Type-Options"], "nosniff")
        self.assertIn("max-age=86400", response.headers["Cache-Control"])
        body = response.content.decode()
        self.assertIn("User-agent: *", body)
        self.assertIn("Allow: /", body)
        self.assertIn("Sitemap: https://poketable.example/sitemap.xml", body)
        for private_path in (
            "/games/",
            "/api/",
            "/accounts/",
            "/invitations/",
            "/qui-est-ce/games/",
            "/metamorph-mystere/games/",
            "/infiltration-rocket/games/",
            "/bataille-des-iles/games/",
            "/course-des-starters/games/",
        ):
            self.assertIn(f"Disallow: {private_path}", body)

    def test_sitemap_is_a_strict_allowlist_of_home_and_eight_lobbies(self):
        response = self.client.get(
            reverse("sitemap_xml"),
            HTTP_HOST="poketable.example",
            HTTP_X_FORWARDED_PROTO="https",
        )

        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.headers["Content-Type"], "application/xml; charset=utf-8")
        self.assertEqual(response.headers["Content-Language"], "fr")
        self.assertIn("max-age=3600", response.headers["Cache-Control"])
        document = ElementTree.fromstring(response.content)
        namespace = {"sitemap": "http://www.sitemaps.org/schemas/sitemap/0.9"}
        locations = [node.text for node in document.findall("sitemap:url/sitemap:loc", namespace)]
        expected = [f"https://poketable.example{reverse(page.route_name)}" for page in PUBLIC_INDEX_PAGES]

        self.assertEqual(locations, expected)
        self.assertEqual(len(locations), 9)
        self.assertEqual(len(set(locations)), 9)
        self.assertFalse(any("/games/" in location or "/api/" in location for location in locations))
        self.assertFalse(any(re.search(r"[0-9a-f]{8}-[0-9a-f-]{27,}", location) for location in locations))

    def test_seo_endpoints_accept_head_requests(self):
        for route_name in ("robots_txt", "sitemap_xml"):
            with self.subTest(route_name=route_name):
                response = self.client.head(reverse(route_name))
                self.assertEqual(response.status_code, 200)
                self.assertEqual(response.content, b"")


@override_settings(ALLOWED_HOSTS=["testserver", "poketable.example"])
class BaseMetadataTests(LanguageIsolationMixin, TestCase):
    def test_home_has_absolute_query_free_metadata_and_valid_json_ld(self):
        response = self.client.get(
            "/?utm_source=newsletter",
            HTTP_HOST="poketable.example",
            HTTP_X_FORWARDED_PROTO="https",
        )
        content = response.content.decode()
        head = content.partition("</head>")[0]

        self.assertEqual(response.status_code, 200)
        self.assertContains(response, '<html\n    lang="fr"', html=False)
        self.assertContains(response, '<meta\n        name="description"', html=False)
        self.assertContains(
            response,
            'content="index, follow, max-image-preview:large"',
            html=False,
        )
        self.assertContains(response, 'href="https://poketable.example/"', html=False)
        self.assertContains(response, 'property="og:url" content="https://poketable.example/"', html=False)
        self.assertContains(response, 'name="twitter:card" content="summary"', html=False)
        self.assertNotIn("utm_source", head)

        match = re.search(
            r'<script id="poketable-structured-data" type="application/ld\+json">(.*?)</script>',
            content,
            re.DOTALL,
        )
        self.assertIsNotNone(match)
        structured_data = json.loads(html.unescape(match.group(1)))
        self.assertEqual(structured_data["@context"], "https://schema.org")
        self.assertEqual(
            {entry["@type"] for entry in structured_data["@graph"]},
            {"WebSite", "WebApplication"},
        )
        self.assertTrue(
            all(entry["url"] == "https://poketable.example/" for entry in structured_data["@graph"])
        )

    def test_public_lobby_is_indexable_but_account_page_is_not(self):
        lobby = self.client.get(reverse("guesswho:lobby"), secure=True)
        login = self.client.get(f"{reverse('login')}?next=/profil/", secure=True)
        login_head = login.content.decode().partition("</head>")[0]

        self.assertContains(
            lobby,
            'content="index, follow, max-image-preview:large"',
            html=False,
        )
        self.assertContains(login, 'content="noindex, nofollow, noarchive"', html=False)
        self.assertContains(
            login,
            f'href="https://testserver{reverse("login")}"',
            html=False,
        )
        self.assertNotIn("next=/profil/", login_head)

    def test_every_indexed_lobby_renders_its_real_content_for_crawlers(self):
        templates = {
            "lobby": "game/lobby.html",
            "guesswho:lobby": "guesswho/lobby.html",
            "silhouette:lobby": "silhouette/lobby.html",
            "pictionary:lobby": "pictionary/lobby.html",
            "metamorph:lobby": "metamorph/lobby.html",
            "rocket:lobby": "rocket/lobby.html",
            "islands:lobby": "islands/lobby.html",
            "starterrace:lobby": "starterrace/lobby.html",
        }

        for route_name, template_name in templates.items():
            with self.subTest(route_name=route_name):
                response = self.client.get(reverse(route_name), secure=True)
                head = response.content.decode().partition("</head>")[0]

                self.assertEqual(response.status_code, 200)
                self.assertTemplateUsed(response, template_name)
                self.assertTemplateNotUsed(response, "guest_gate.html")
                self.assertIn("<title>", head)
                self.assertIn('name="description"', head)
                self.assertIn("index, follow", head)

        self.assertEqual(User.objects.count(), 0)

    def test_home_metadata_and_json_ld_follow_browser_language(self):
        response = self.client.get(
            "/",
            HTTP_HOST="poketable.example",
            HTTP_X_FORWARDED_PROTO="https",
            HTTP_ACCEPT_LANGUAGE="en-US,en;q=0.9",
        )
        content = response.content.decode()

        self.assertContains(response, '<html\n    lang="en"', html=False)
        self.assertContains(response, "Play eight free online Pokémon games", html=False)
        match = re.search(
            r'<script id="poketable-structured-data" type="application/ld\+json">(.*?)</script>',
            content,
            re.DOTALL,
        )
        self.assertIsNotNone(match)
        structured_data = json.loads(html.unescape(match.group(1)))
        self.assertTrue(all(entry["inLanguage"] == "en-US" for entry in structured_data["@graph"]))
        self.assertIn(
            "Eight multiplayer Pokémon party games",
            structured_data["@graph"][0]["description"],
        )

    def test_title_and_description_are_overridable_blocks(self):
        template = engines["django"].from_string("""{% extends "base.html" %}
            {% block title %}Titre SEO dédié{% endblock %}
            {% block meta_description %}Description SEO dédiée.{% endblock %}
            {% block content %}<h1>Page de test</h1>{% endblock %}""")
        request = RequestFactory().get(
            "/page-seo/?source=test",
            secure=True,
            HTTP_HOST="poketable.example",
        )
        rendered = template.render({}, request=request)

        self.assertIn("<title>Titre SEO dédié</title>", rendered)
        self.assertIn('content="Description SEO dédiée."', rendered)
        self.assertIn('href="https://poketable.example/page-seo/"', rendered)
