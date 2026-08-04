from django.contrib.auth.models import User
from django.test import TestCase
from django.urls import reverse

from game.models import Friendship, Profile


class ProfileViewTests(TestCase):
    def setUp(self):
        self.user = User.objects.create_user(
            username="alice",
            password="MotDePasse123!",
            first_name="Alice",
            last_name="Martin",
            email="alice@example.com",
        )

        self.other_user = User.objects.create_user(
            username="bobby",
            password="MotDePasse123!",
            first_name="Bob",
            last_name="Durand",
            email="bob@example.com",
        )

        self.profile, _ = Profile.objects.get_or_create(
            user=self.user,
        )

        self.other_profile, _ = Profile.objects.get_or_create(
            user=self.other_user,
        )

    def test_profile_pages_require_a_full_account(self):
        protected_urls = [
            reverse("my_profile"),
            reverse("edit_profile"),
            reverse("friends"),
            reverse("player_search"),
            reverse(
                "public_profile",
                kwargs={
                    "username": self.other_user.username,
                },
            ),
        ]

        for url in protected_urls:
            with self.subTest(url=url):
                response = self.client.get(url)

                # Un visiteur ou un invité reçoit l'argumentaire du compte
                # plutôt qu'une redirection sèche vers la connexion.
                self.assertEqual(
                    response.status_code,
                    200,
                )
                self.assertTemplateUsed(
                    response,
                    "members_only.html",
                )

    def test_my_profile_displays_private_email(self):
        self.client.force_login(self.user)

        response = self.client.get(
            reverse("my_profile"),
        )

        self.assertEqual(
            response.status_code,
            200,
        )

        self.assertContains(
            response,
            self.user.username,
        )

        self.assertContains(
            response,
            self.user.email,
        )

        self.assertTrue(
            response.context["is_owner"],
        )

    def test_public_profile_hides_email_from_other_users(self):
        self.client.force_login(self.other_user)

        response = self.client.get(
            reverse(
                "public_profile",
                kwargs={
                    "username": self.user.username,
                },
            )
        )

        self.assertEqual(
            response.status_code,
            200,
        )

        self.assertContains(
            response,
            self.user.username,
        )

        self.assertNotContains(
            response,
            self.user.email,
        )

        self.assertFalse(
            response.context["is_owner"],
        )

    def test_user_can_update_account_and_profile(self):
        self.client.force_login(self.user)

        response = self.client.post(
            reverse("edit_profile"),
            {
                "username": "alice_updated",
                "first_name": "Alice",
                "last_name": "Martin",
                "email": "alice.updated@example.com",
                "description": ("Passionnée par les cartes Pokémon " "et les jeux multijoueurs."),
            },
        )

        self.assertRedirects(
            response,
            reverse("my_profile"),
        )

        self.user.refresh_from_db()
        self.profile.refresh_from_db()

        self.assertEqual(
            self.user.username,
            "alice_updated",
        )

        self.assertEqual(
            self.user.email,
            "alice.updated@example.com",
        )

        self.assertEqual(
            self.profile.description,
            ("Passionnée par les cartes Pokémon " "et les jeux multijoueurs."),
        )

    def test_email_must_be_unique(self):
        self.client.force_login(self.user)

        response = self.client.post(
            reverse("edit_profile"),
            {
                "username": self.user.username,
                "first_name": self.user.first_name,
                "last_name": self.user.last_name,
                "email": self.other_user.email,
                "description": "",
            },
        )

        self.assertEqual(
            response.status_code,
            200,
        )

        self.assertTrue(
            response.context["account_form"].errors,
        )

        self.user.refresh_from_db()

        self.assertEqual(
            self.user.email,
            "alice@example.com",
        )

    def test_player_search_finds_another_user(self):
        self.client.force_login(self.user)

        response = self.client.get(
            reverse("player_search"),
            {
                "q": "bobby",
            },
        )

        self.assertEqual(
            response.status_code,
            200,
        )

        self.assertContains(
            response,
            "bobby",
        )

        usernames = [result["user"].username for result in response.context["search_results"]]

        self.assertIn(
            "bobby",
            usernames,
        )

        self.assertNotIn(
            "alice",
            usernames,
        )


class FriendshipViewTests(TestCase):
    def setUp(self):
        self.alice = User.objects.create_user(
            username="alice",
            password="MotDePasse123!",
            first_name="Alice",
            last_name="Martin",
        )

        self.bob = User.objects.create_user(
            username="bob",
            password="MotDePasse123!",
            first_name="Bob",
            last_name="Durand",
        )

        self.charlie = User.objects.create_user(
            username="charlie",
            password="MotDePasse123!",
            first_name="Charlie",
            last_name="Bernard",
        )

        for user in (
            self.alice,
            self.bob,
            self.charlie,
        ):
            Profile.objects.get_or_create(
                user=user,
            )

    def test_user_can_send_friend_request(self):
        self.client.force_login(self.alice)

        response = self.client.post(
            reverse(
                "send_friend_request",
                kwargs={
                    "username": self.bob.username,
                },
            )
        )

        self.assertRedirects(
            response,
            reverse(
                "public_profile",
                kwargs={
                    "username": self.bob.username,
                },
            ),
        )

        friendship = Friendship.objects.get()

        self.assertEqual(
            friendship.requester,
            self.alice,
        )

        self.assertEqual(
            friendship.addressee,
            self.bob,
        )

        self.assertEqual(
            friendship.status,
            Friendship.Status.PENDING,
        )

    def test_friend_request_cannot_be_sent_to_self(self):
        self.client.force_login(self.alice)

        response = self.client.post(
            reverse(
                "send_friend_request",
                kwargs={
                    "username": self.alice.username,
                },
            )
        )

        self.assertRedirects(
            response,
            reverse("my_profile"),
        )

        self.assertFalse(
            Friendship.objects.exists(),
        )

    def test_duplicate_request_does_not_create_duplicate(self):
        self.client.force_login(self.alice)

        request_url = reverse(
            "send_friend_request",
            kwargs={
                "username": self.bob.username,
            },
        )

        self.client.post(request_url)
        self.client.post(request_url)

        self.assertEqual(
            Friendship.objects.count(),
            1,
        )

        self.assertEqual(
            Friendship.objects.get().status,
            Friendship.Status.PENDING,
        )

    def test_recipient_can_accept_friend_request(self):
        friendship = Friendship.objects.create(
            requester=self.alice,
            addressee=self.bob,
        )

        self.client.force_login(self.bob)

        response = self.client.post(
            reverse(
                "accept_friend_request",
                kwargs={
                    "friendship_id": friendship.id,
                },
            )
        )

        self.assertRedirects(
            response,
            reverse("friends"),
        )

        friendship.refresh_from_db()

        self.assertEqual(
            friendship.status,
            Friendship.Status.ACCEPTED,
        )

    def test_unrelated_user_cannot_accept_request(self):
        friendship = Friendship.objects.create(
            requester=self.alice,
            addressee=self.bob,
        )

        self.client.force_login(self.charlie)

        response = self.client.post(
            reverse(
                "accept_friend_request",
                kwargs={
                    "friendship_id": friendship.id,
                },
            )
        )

        self.assertEqual(
            response.status_code,
            404,
        )

        friendship.refresh_from_db()

        self.assertEqual(
            friendship.status,
            Friendship.Status.PENDING,
        )

    def test_recipient_can_reject_friend_request(self):
        friendship = Friendship.objects.create(
            requester=self.alice,
            addressee=self.bob,
        )

        self.client.force_login(self.bob)

        response = self.client.post(
            reverse(
                "reject_friend_request",
                kwargs={
                    "friendship_id": friendship.id,
                },
            )
        )

        self.assertRedirects(
            response,
            reverse("friends"),
        )

        friendship.refresh_from_db()

        self.assertEqual(
            friendship.status,
            Friendship.Status.REJECTED,
        )

    def test_requester_can_cancel_friend_request(self):
        friendship = Friendship.objects.create(
            requester=self.alice,
            addressee=self.bob,
        )

        self.client.force_login(self.alice)

        response = self.client.post(
            reverse(
                "cancel_friend_request",
                kwargs={
                    "friendship_id": friendship.id,
                },
            )
        )

        self.assertRedirects(
            response,
            reverse("friends"),
        )

        self.assertFalse(
            Friendship.objects.filter(
                pk=friendship.pk,
            ).exists()
        )

    def test_crossed_request_is_automatically_accepted(self):
        Friendship.objects.create(
            requester=self.bob,
            addressee=self.alice,
        )

        self.client.force_login(self.alice)

        response = self.client.post(
            reverse(
                "send_friend_request",
                kwargs={
                    "username": self.bob.username,
                },
            )
        )

        self.assertEqual(
            response.status_code,
            302,
        )

        self.assertEqual(
            Friendship.objects.count(),
            1,
        )

        friendship = Friendship.objects.get()

        self.assertEqual(
            friendship.status,
            Friendship.Status.ACCEPTED,
        )

    def test_friend_can_be_removed(self):
        friendship = Friendship.objects.create(
            requester=self.alice,
            addressee=self.bob,
            status=Friendship.Status.ACCEPTED,
        )

        self.client.force_login(self.alice)

        response = self.client.post(
            reverse(
                "remove_friend",
                kwargs={
                    "friendship_id": friendship.id,
                },
            )
        )

        self.assertRedirects(
            response,
            reverse("friends"),
        )

        self.assertFalse(
            Friendship.objects.filter(
                pk=friendship.pk,
            ).exists()
        )

    def test_friends_page_displays_received_requests(self):
        Friendship.objects.create(
            requester=self.bob,
            addressee=self.alice,
        )

        self.client.force_login(self.alice)

        response = self.client.get(
            reverse("friends"),
        )

        self.assertEqual(
            response.status_code,
            200,
        )

        self.assertContains(
            response,
            "Demandes reçues",
        )

        self.assertContains(
            response,
            self.bob.username,
        )

    def test_friends_page_displays_sent_requests(self):
        Friendship.objects.create(
            requester=self.alice,
            addressee=self.bob,
        )

        self.client.force_login(self.alice)

        response = self.client.get(
            reverse("friends"),
        )

        self.assertEqual(
            response.status_code,
            200,
        )

        self.assertContains(
            response,
            "Demandes envoyées",
        )

        self.assertContains(
            response,
            self.bob.username,
        )

    def test_friends_page_displays_accepted_friends(self):
        Friendship.objects.create(
            requester=self.alice,
            addressee=self.bob,
            status=Friendship.Status.ACCEPTED,
        )

        self.client.force_login(self.alice)

        response = self.client.get(
            reverse("friends"),
        )

        self.assertEqual(
            response.status_code,
            200,
        )

        self.assertContains(
            response,
            "Liste d’amis",
        )

        self.assertContains(
            response,
            self.bob.username,
        )

    def test_public_profile_displays_pending_request_status(self):
        Friendship.objects.create(
            requester=self.alice,
            addressee=self.bob,
        )

        self.client.force_login(self.alice)

        response = self.client.get(
            reverse(
                "public_profile",
                kwargs={
                    "username": self.bob.username,
                },
            )
        )

        self.assertEqual(
            response.status_code,
            200,
        )

        self.assertEqual(
            response.context["friendship_status"],
            "sent",
        )

        self.assertContains(
            response,
            "Demande envoyée",
        )

    def test_public_profile_displays_received_request_status(self):
        Friendship.objects.create(
            requester=self.bob,
            addressee=self.alice,
        )

        self.client.force_login(self.alice)

        response = self.client.get(
            reverse(
                "public_profile",
                kwargs={
                    "username": self.bob.username,
                },
            )
        )

        self.assertEqual(
            response.status_code,
            200,
        )

        self.assertEqual(
            response.context["friendship_status"],
            "received",
        )

        self.assertContains(
            response,
            "Accepter la demande",
        )

    def test_friendship_actions_reject_get_requests(self):
        friendship = Friendship.objects.create(
            requester=self.alice,
            addressee=self.bob,
        )

        self.client.force_login(self.bob)

        response = self.client.get(
            reverse(
                "accept_friend_request",
                kwargs={
                    "friendship_id": friendship.id,
                },
            )
        )

        self.assertEqual(
            response.status_code,
            405,
        )

        friendship.refresh_from_db()

        self.assertEqual(
            friendship.status,
            Friendship.Status.PENDING,
        )
