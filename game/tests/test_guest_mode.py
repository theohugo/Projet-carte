from datetime import timedelta

from django.contrib.auth.models import User
from django.core.management import call_command
from django.test import TestCase
from django.urls import reverse
from django.utils import timezone

from game.game_engine import GameEngine
from game.guests import GUEST_USERNAME_PREFIX, create_guest_user, is_guest, is_member
from game.models import Game
from game.tests.factories import make_cards, make_draft_catalogue, make_game, make_types, make_users


class GuestSessionTests(TestCase):
    def test_playing_as_guest_creates_a_temporary_account(self):
        response = self.client.post(reverse("play_as_guest"))

        user = User.objects.get()
        self.assertEqual(response.status_code, 302)
        self.assertTrue(user.username.startswith(GUEST_USERNAME_PREFIX))
        self.assertTrue(is_guest(user))
        self.assertFalse(is_member(user))
        self.assertFalse(user.has_usable_password())

    def test_the_guest_lands_where_they_were_going(self):
        response = self.client.post(reverse("play_as_guest"), {"next": reverse("lobby")})

        self.assertRedirects(response, reverse("lobby"))

    def test_an_outside_next_url_is_ignored(self):
        response = self.client.post(reverse("play_as_guest"), {"next": "https://attaquant.example/vol"})

        self.assertRedirects(response, reverse("home"))

    def test_an_existing_session_is_never_replaced_by_a_guest(self):
        (member,) = make_users(1)
        self.client.force_login(member)

        self.client.post(reverse("play_as_guest"))

        self.assertEqual(User.objects.count(), 1)

    def test_guest_usernames_never_collide(self):
        names = {create_guest_user().username for _ in range(25)}

        self.assertEqual(len(names), 25)


class GuestAccessTests(TestCase):
    def setUp(self):
        self.types = make_types()
        make_cards(self.types)
        make_draft_catalogue(self.types)

    def test_the_hub_is_open_to_visitors(self):
        response = self.client.get(reverse("home"))

        self.assertEqual(response.status_code, 200)
        self.assertContains(response, "Jouer sans compte")

    def test_a_visitor_gets_the_guest_gate_on_a_game(self):
        for url in (
            reverse("lobby"),
            reverse("guesswho:lobby"),
            reverse("silhouette:lobby"),
            reverse("pictionary:lobby"),
        ):
            with self.subTest(url=url):
                response = self.client.get(url)

                self.assertEqual(response.status_code, 200)
                self.assertContains(response, "Jouer en invité")
                self.assertTemplateUsed(response, "guest_gate.html")

    def test_a_guest_can_open_every_game_lobby(self):
        self.client.post(reverse("play_as_guest"))

        for url in (
            reverse("lobby"),
            reverse("guesswho:lobby"),
            reverse("silhouette:lobby"),
            reverse("pictionary:lobby"),
        ):
            with self.subTest(url=url):
                self.assertEqual(self.client.get(url).status_code, 200)

    def test_a_guest_can_create_and_play_a_poke_uno_game(self):
        self.client.post(reverse("play_as_guest"))

        response = self.client.post(reverse("lobby"))

        game = Game.objects.get()
        self.assertEqual(response.status_code, 302)
        self.assertEqual(game.players.count(), 1)
        self.assertTrue(is_guest(game.created_by))

    def test_member_pages_send_the_guest_to_the_account_pitch(self):
        self.client.post(reverse("play_as_guest"))

        for name in ("collection", "quests", "friends", "my_profile", "game_invitations"):
            with self.subTest(page=name):
                response = self.client.get(reverse(name))

                self.assertEqual(response.status_code, 200)
                self.assertTemplateUsed(response, "members_only.html")
                self.assertContains(response, "Transformer mon pseudo en compte")

    def test_member_pages_stay_open_to_real_accounts(self):
        (member,) = make_users(1)
        self.client.force_login(member)

        for name in ("collection", "quests", "friends", "my_profile"):
            with self.subTest(page=name):
                response = self.client.get(reverse(name))

                self.assertEqual(response.status_code, 200)
                self.assertTemplateNotUsed(response, "members_only.html")

    def test_a_guest_cannot_send_a_friend_request_through_the_back_door(self):
        (member,) = make_users(1)
        self.client.post(reverse("play_as_guest"))

        response = self.client.post(reverse("send_friend_request", args=[member.username]))

        self.assertTemplateUsed(response, "members_only.html")


class GuestUpgradeTests(TestCase):
    def setUp(self):
        self.types = make_types()
        make_cards(self.types)
        make_draft_catalogue(self.types)

    def test_signing_up_keeps_the_guest_games_and_scores(self):
        self.client.post(reverse("play_as_guest"))
        guest = User.objects.get()
        game = make_game(guest)
        GameEngine(game).add_player(guest)

        response = self.client.post(
            reverse("signup"),
            {
                "username": "dresseur",
                "password1": "Une-Phrase-Solide-2026!",
                "password2": "Une-Phrase-Solide-2026!",
            },
        )

        guest.refresh_from_db()
        self.assertEqual(response.status_code, 302)
        # Toujours le même compte : la partie n'a pas changé de propriétaire.
        self.assertEqual(User.objects.count(), 1)
        self.assertEqual(guest.username, "dresseur")
        self.assertFalse(is_guest(guest))
        self.assertTrue(guest.has_usable_password())
        self.assertEqual(game.players.filter(user=guest).count(), 1)

    def test_the_upgraded_account_can_open_member_pages(self):
        self.client.post(reverse("play_as_guest"))
        self.client.post(
            reverse("signup"),
            {
                "username": "dresseuse",
                "password1": "Une-Phrase-Solide-2026!",
                "password2": "Une-Phrase-Solide-2026!",
            },
        )

        response = self.client.get(reverse("collection"))

        self.assertTemplateNotUsed(response, "members_only.html")

    def test_a_visitor_signing_up_still_creates_a_new_account(self):
        self.client.post(
            reverse("signup"),
            {
                "username": "nouvelle",
                "password1": "Une-Phrase-Solide-2026!",
                "password2": "Une-Phrase-Solide-2026!",
            },
        )

        self.assertTrue(is_member(User.objects.get(username="nouvelle")))


class GuestPurgeTests(TestCase):
    def setUp(self):
        self.types = make_types()
        make_cards(self.types)
        make_draft_catalogue(self.types)

    def age(self, user, days):
        User.objects.filter(pk=user.pk).update(date_joined=timezone.now() - timedelta(days=days))

    def test_old_guests_without_a_game_are_removed(self):
        stale = create_guest_user()
        fresh = create_guest_user()
        self.age(stale, 30)

        call_command("purge_guest_accounts")

        self.assertFalse(User.objects.filter(pk=stale.pk).exists())
        self.assertTrue(User.objects.filter(pk=fresh.pk).exists())

    def test_a_guest_still_in_a_game_is_kept(self):
        playing = create_guest_user()
        self.age(playing, 30)
        game = make_game(playing)
        GameEngine(game).add_player(playing)

        call_command("purge_guest_accounts")

        self.assertTrue(User.objects.filter(pk=playing.pk).exists())

    def test_members_are_never_touched(self):
        (member,) = make_users(1)
        self.age(member, 400)

        call_command("purge_guest_accounts")

        self.assertTrue(User.objects.filter(pk=member.pk).exists())
