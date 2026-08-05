from django.contrib.auth import get_user_model
from django.db import IntegrityError, transaction
from django.test import TestCase
from django.urls import reverse

from game.models import (
    Friendship,
    Game,
    GameInvitation,
    GamePlayer,
    PokemonCard,
    PokemonType,
    Profile,
)
from guesswho.models import (
    GuessWhoGame,
    GuessWhoPlayer,
)
from islands.models import Formation, IslandGame, IslandPlayer
from metamorph.models import MetamorphGame, MetamorphPlayer
from pictionary.models import (
    PictionaryGame,
    PictionaryPlayer,
)
from rocket.models import RocketGame, RocketPlayer
from silhouette.models import (
    SilhouetteGame,
    SilhouettePlayer,
)
from starterrace.models import Game as StarterRaceGame
from starterrace.models import Pawn as StarterRacePawn
from starterrace.models import Player as StarterRacePlayer

User = get_user_model()


class GameInvitationTests(TestCase):
    """Tests du système d’invitations multi-jeux."""

    MODE_DATA = {
        GameInvitation.Mode.POKE_UNO: {
            "slug": "poke-uno",
            "field": "game",
            "detail_url": "game_detail",
        },
        GameInvitation.Mode.GUESSWHO: {
            "slug": "qui-est-ce",
            "field": "guesswho_game",
            "detail_url": "guesswho:game_detail",
        },
        GameInvitation.Mode.SILHOUETTE: {
            "slug": "silhouette",
            "field": "silhouette_game",
            "detail_url": "silhouette:game_detail",
        },
        GameInvitation.Mode.PICTIONARY: {
            "slug": "pictionary",
            "field": "pictionary_game",
            "detail_url": "pictionary:game_detail",
        },
        GameInvitation.Mode.METAMORPH: {
            "slug": "metamorph-mystere",
            "field": "metamorph_game",
            "detail_url": "metamorph:game_detail",
        },
        GameInvitation.Mode.ROCKET: {
            "slug": "infiltration-rocket",
            "field": "rocket_game",
            "detail_url": "rocket:game_detail",
        },
        GameInvitation.Mode.ISLANDS: {
            "slug": "bataille-des-iles",
            "field": "islands_game",
            "detail_url": "islands:game_detail",
        },
        GameInvitation.Mode.STARTER_RACE: {
            "slug": "course-des-starters",
            "field": "starterrace_game",
            "detail_url": "starterrace:game_detail",
        },
    }

    def setUp(self):
        self.host = User.objects.create_user(
            username="host",
            password="Password123!",
        )
        self.friend = User.objects.create_user(
            username="friend",
            password="Password123!",
        )
        self.outsider = User.objects.create_user(
            username="outsider",
            password="Password123!",
        )

        for user in (
            self.host,
            self.friend,
            self.outsider,
        ):
            Profile.objects.get_or_create(
                user=user,
            )

        self.friendship = Friendship.objects.create(
            requester=self.host,
            addressee=self.friend,
            status=Friendship.Status.ACCEPTED,
        )

        # Bataille des Îles et Course des Starters construisent leurs pions à
        # partir du catalogue partagé. Ces quatre entrées rendent les salons de
        # test aussi valides que ceux créés depuis leur lobby, avec de vrais
        # ``sprite_url`` et les quatre numéros de Pokédex attendus.
        grass = PokemonType.objects.create(
            slug="grass",
            name_fr="Plante",
            name_en="Grass",
        )
        fire = PokemonType.objects.create(
            slug="fire",
            name_fr="Feu",
            name_en="Fire",
        )
        water = PokemonType.objects.create(
            slug="water",
            name_fr="Eau",
            name_en="Water",
        )
        electric = PokemonType.objects.create(
            slug="electric",
            name_fr="Électrik",
            name_en="Electric",
        )
        starter_rows = (
            (1, "Bulbizarre", grass),
            (4, "Salamèche", fire),
            (7, "Carapuce", water),
            (25, "Pikachu", electric),
        )
        self.starter_cards = [
            PokemonCard.objects.create(
                pokedex_id=pokedex_id,
                slug=f"invitation-starter-{pokedex_id}",
                name_fr=name,
                name_en=name,
                primary_type=pokemon_type,
                sprite_url=f"https://example.com/pokemon/{pokedex_id}.png",
            )
            for pokedex_id, name, pokemon_type in starter_rows
        ]

    def _create_room(
        self,
        mode,
        *,
        creator=None,
        max_players=4,
    ):
        """Crée un salon avec son créateur déjà inscrit."""

        creator = creator or self.host

        if mode == GameInvitation.Mode.POKE_UNO:
            room = Game.objects.create(
                created_by=creator,
                max_players=max_players,
            )

            GamePlayer.objects.create(
                game=room,
                user=creator,
                turn_order=0,
            )

            return room

        if mode == GameInvitation.Mode.GUESSWHO:
            room = GuessWhoGame.objects.create(
                created_by=creator,
            )

            GuessWhoPlayer.objects.create(
                game=room,
                user=creator,
                turn_order=0,
            )

            return room

        if mode == GameInvitation.Mode.SILHOUETTE:
            room = SilhouetteGame.objects.create(
                created_by=creator,
            )

            SilhouettePlayer.objects.create(
                game=room,
                user=creator,
            )

            return room

        if mode == GameInvitation.Mode.PICTIONARY:
            room = PictionaryGame.objects.create(
                created_by=creator,
            )

            PictionaryPlayer.objects.create(
                game=room,
                user=creator,
                turn_order=0,
            )

            return room

        if mode == GameInvitation.Mode.METAMORPH:
            room = MetamorphGame.objects.create(
                created_by=creator,
            )

            MetamorphPlayer.objects.create(
                game=room,
                user=creator,
                turn_order=0,
            )

            return room

        if mode == GameInvitation.Mode.ROCKET:
            room = RocketGame.objects.create(
                created_by=creator,
                max_players=12,
            )

            RocketPlayer.objects.create(
                game=room,
                user=creator,
                turn_order=0,
            )

            return room

        if mode == GameInvitation.Mode.ISLANDS:
            room = IslandGame.objects.create(
                created_by=creator,
            )

            player = IslandPlayer.objects.create(
                game=room,
                user=creator,
                turn_order=0,
            )
            Formation.objects.bulk_create(
                [
                    Formation(
                        player=player,
                        pokemon_card=card,
                        slot=slot,
                        size=size,
                    )
                    for slot, (card, size) in enumerate(zip(self.starter_cards, (2, 3, 3, 4), strict=True))
                ]
            )

            return room

        if mode == GameInvitation.Mode.STARTER_RACE:
            room = StarterRaceGame.objects.create(
                created_by=creator,
            )

            player = StarterRacePlayer.objects.create(
                game=room,
                user=creator,
                starter_card=self.starter_cards[0],
                turn_order=0,
            )
            StarterRacePawn.objects.bulk_create(
                [StarterRacePawn(player=player, number=number) for number in range(4)]
            )

            return room

        raise ValueError(f"Mode de test inconnu : {mode}")

    def _create_invitation(
        self,
        mode,
        room,
        *,
        sender=None,
        recipient=None,
        status=GameInvitation.Status.PENDING,
    ):
        """Crée une invitation reliée au bon champ de salon."""

        sender = sender or self.host
        recipient = recipient or self.friend

        mode_data = self.MODE_DATA[mode]

        values = {
            "mode": mode,
            "sender": sender,
            "recipient": recipient,
            "status": status,
            mode_data["field"]: room,
        }

        return GameInvitation.objects.create(**values)

    def _invite_page_url(
        self,
        mode,
        room,
    ):
        return reverse(
            "invite_friends_to_game",
            kwargs={
                "mode": self.MODE_DATA[mode]["slug"],
                "room_id": room.pk,
            },
        )

    def _send_url(
        self,
        mode,
        room,
        recipient=None,
    ):
        recipient = recipient or self.friend

        return reverse(
            "send_game_invitation",
            kwargs={
                "mode": self.MODE_DATA[mode]["slug"],
                "room_id": room.pk,
                "username": recipient.username,
            },
        )

    def _detail_url(
        self,
        mode,
        room,
    ):
        return reverse(
            self.MODE_DATA[mode]["detail_url"],
            kwargs={
                "game_id": room.pk,
            },
        )

    def test_invitations_page_requires_a_full_account(self):
        response = self.client.get(reverse("game_invitations"))

        self.assertEqual(
            response.status_code,
            200,
        )
        self.assertTemplateUsed(
            response,
            "members_only.html",
        )

    def test_host_can_open_friend_selection_page(self):
        room = self._create_room(GameInvitation.Mode.POKE_UNO)

        self.client.force_login(self.host)

        response = self.client.get(
            self._invite_page_url(
                GameInvitation.Mode.POKE_UNO,
                room,
            )
        )

        self.assertEqual(
            response.status_code,
            200,
        )
        self.assertContains(
            response,
            self.friend.username,
        )
        self.assertContains(
            response,
            "Poké-Uno",
        )
        self.assertContains(
            response,
            "Inviter à jouer",
        )

    def test_non_host_cannot_open_friend_selection_page(self):
        room = self._create_room(GameInvitation.Mode.POKE_UNO)

        self.client.force_login(self.friend)

        response = self.client.get(
            self._invite_page_url(
                GameInvitation.Mode.POKE_UNO,
                room,
            )
        )

        self.assertEqual(
            response.status_code,
            403,
        )

    def test_host_can_send_invitation_for_every_mode(self):
        self.client.force_login(self.host)

        for mode in self.MODE_DATA:
            with self.subTest(mode=mode):
                room = self._create_room(mode)

                response = self.client.post(
                    self._send_url(
                        mode,
                        room,
                    )
                )

                self.assertEqual(
                    response.status_code,
                    302,
                )

                invitation = GameInvitation.objects.get(
                    mode=mode,
                    recipient=self.friend,
                    status=(GameInvitation.Status.PENDING),
                )

                self.assertEqual(
                    invitation.sender,
                    self.host,
                )
                self.assertEqual(
                    invitation.room,
                    room,
                )

    def test_new_mode_factories_room_and_slugs_match_the_generic_contract(self):
        expected_models = {
            GameInvitation.Mode.METAMORPH: MetamorphGame,
            GameInvitation.Mode.ROCKET: RocketGame,
            GameInvitation.Mode.ISLANDS: IslandGame,
            GameInvitation.Mode.STARTER_RACE: StarterRaceGame,
        }

        for mode, model in expected_models.items():
            with self.subTest(mode=mode):
                room = self._create_room(mode)
                invitation = self._create_invitation(mode, room)
                mode_data = self.MODE_DATA[mode]

                self.assertIsInstance(room, model)
                self.assertEqual(room.created_by, self.host)
                self.assertTrue(room.players.filter(user=self.host).exists())
                self.assertEqual(invitation.room, room)
                self.assertEqual(
                    getattr(invitation, f"{mode_data['field']}_id"),
                    room.pk,
                )
                self.assertEqual(invitation.mode_slug, mode_data["slug"])
                self.assertIn(
                    f"/invitations/{mode_data['slug']}/",
                    self._invite_page_url(mode, room),
                )

    def test_non_friend_cannot_be_invited(self):
        room = self._create_room(GameInvitation.Mode.POKE_UNO)

        self.client.force_login(self.host)

        response = self.client.post(
            self._send_url(
                GameInvitation.Mode.POKE_UNO,
                room,
                recipient=self.outsider,
            )
        )

        self.assertEqual(
            response.status_code,
            403,
        )
        self.assertFalse(
            GameInvitation.objects.filter(
                recipient=self.outsider,
            ).exists()
        )

    def test_duplicate_pending_invitation_is_not_created(self):
        mode = GameInvitation.Mode.POKE_UNO
        room = self._create_room(mode)

        self.client.force_login(self.host)

        first_response = self.client.post(
            self._send_url(
                mode,
                room,
            )
        )
        second_response = self.client.post(
            self._send_url(
                mode,
                room,
            )
        )

        self.assertEqual(
            first_response.status_code,
            302,
        )
        self.assertEqual(
            second_response.status_code,
            302,
        )

        self.assertEqual(
            GameInvitation.objects.filter(
                game=room,
                recipient=self.friend,
                status=GameInvitation.Status.PENDING,
            ).count(),
            1,
        )

    def test_invitation_cannot_be_sent_to_started_or_full_room(
        self,
    ):
        mode = GameInvitation.Mode.POKE_UNO

        started_room = self._create_room(mode)
        started_room.status = Game.Status.EN_COURS
        started_room.save(update_fields=["status"])

        full_room = self._create_room(
            mode,
            max_players=1,
        )

        self.client.force_login(self.host)

        started_response = self.client.post(
            self._send_url(
                mode,
                started_room,
            )
        )
        full_response = self.client.post(
            self._send_url(
                mode,
                full_room,
            )
        )

        self.assertEqual(
            started_response.status_code,
            302,
        )
        self.assertEqual(
            full_response.status_code,
            302,
        )

        self.assertFalse(
            GameInvitation.objects.filter(
                game__in=[
                    started_room,
                    full_room,
                ],
                recipient=self.friend,
            ).exists()
        )

    def test_sender_can_cancel_invitation(self):
        mode = GameInvitation.Mode.SILHOUETTE
        room = self._create_room(mode)

        invitation = self._create_invitation(
            mode,
            room,
        )

        self.client.force_login(self.host)

        response = self.client.post(
            reverse(
                "cancel_game_invitation",
                kwargs={
                    "invitation_id": invitation.pk,
                },
            )
        )

        self.assertEqual(
            response.status_code,
            302,
        )

        invitation.refresh_from_db()

        self.assertEqual(
            invitation.status,
            GameInvitation.Status.CANCELLED,
        )
        self.assertIsNotNone(invitation.responded_at)

    def test_recipient_can_decline_invitation(self):
        mode = GameInvitation.Mode.PICTIONARY
        room = self._create_room(mode)

        invitation = self._create_invitation(
            mode,
            room,
        )

        self.client.force_login(self.friend)

        response = self.client.post(
            reverse(
                "decline_game_invitation",
                kwargs={
                    "invitation_id": invitation.pk,
                },
            )
        )

        self.assertEqual(
            response.status_code,
            302,
        )

        invitation.refresh_from_db()

        self.assertEqual(
            invitation.status,
            GameInvitation.Status.DECLINED,
        )
        self.assertIsNotNone(invitation.responded_at)

    def test_only_authorized_user_can_respond_to_invitation(
        self,
    ):
        mode = GameInvitation.Mode.POKE_UNO
        room = self._create_room(mode)

        invitation = self._create_invitation(
            mode,
            room,
        )

        self.client.force_login(self.friend)

        cancel_response = self.client.post(
            reverse(
                "cancel_game_invitation",
                kwargs={
                    "invitation_id": invitation.pk,
                },
            )
        )

        self.assertEqual(
            cancel_response.status_code,
            404,
        )

        self.client.force_login(self.host)

        decline_response = self.client.post(
            reverse(
                "decline_game_invitation",
                kwargs={
                    "invitation_id": invitation.pk,
                },
            )
        )

        self.assertEqual(
            decline_response.status_code,
            404,
        )

        self.client.force_login(self.outsider)

        accept_response = self.client.post(
            reverse(
                "accept_game_invitation",
                kwargs={
                    "invitation_id": invitation.pk,
                },
            )
        )

        self.assertEqual(
            accept_response.status_code,
            404,
        )

        invitation.refresh_from_db()

        self.assertEqual(
            invitation.status,
            GameInvitation.Status.PENDING,
        )

    def test_accept_invitation_joins_every_supported_game(
        self,
    ):
        self.client.force_login(self.friend)

        for mode in self.MODE_DATA:
            with self.subTest(mode=mode):
                room = self._create_room(mode)

                invitation = self._create_invitation(
                    mode,
                    room,
                )

                response = self.client.post(
                    reverse(
                        "accept_game_invitation",
                        kwargs={
                            "invitation_id": (invitation.pk),
                        },
                    )
                )

                self.assertEqual(
                    response.status_code,
                    302,
                )
                self.assertEqual(
                    response.url,
                    self._detail_url(
                        mode,
                        room,
                    ),
                )

                invitation.refresh_from_db()

                self.assertEqual(
                    invitation.status,
                    GameInvitation.Status.ACCEPTED,
                )
                self.assertIsNotNone(invitation.responded_at)

                self.assertTrue(
                    room.players.filter(
                        user=self.friend,
                    ).exists()
                )

    def test_accepting_when_already_in_room_does_not_duplicate_player(
        self,
    ):
        mode = GameInvitation.Mode.POKE_UNO
        room = self._create_room(mode)

        GamePlayer.objects.create(
            game=room,
            user=self.friend,
            turn_order=1,
        )

        invitation = self._create_invitation(
            mode,
            room,
        )

        self.client.force_login(self.friend)

        response = self.client.post(
            reverse(
                "accept_game_invitation",
                kwargs={
                    "invitation_id": invitation.pk,
                },
            )
        )

        self.assertEqual(
            response.status_code,
            302,
        )

        invitation.refresh_from_db()

        self.assertEqual(
            invitation.status,
            GameInvitation.Status.ACCEPTED,
        )
        self.assertEqual(
            room.players.filter(
                user=self.friend,
            ).count(),
            1,
        )

    def test_invitation_expires_when_room_has_started(self):
        mode = GameInvitation.Mode.SILHOUETTE
        room = self._create_room(mode)

        invitation = self._create_invitation(
            mode,
            room,
        )

        room.status = SilhouetteGame.Status.EN_COURS
        room.save(update_fields=["status"])

        self.client.force_login(self.friend)

        response = self.client.post(
            reverse(
                "accept_game_invitation",
                kwargs={
                    "invitation_id": invitation.pk,
                },
            )
        )

        self.assertEqual(
            response.status_code,
            302,
        )

        invitation.refresh_from_db()

        self.assertEqual(
            invitation.status,
            GameInvitation.Status.EXPIRED,
        )
        self.assertFalse(
            room.players.filter(
                user=self.friend,
            ).exists()
        )

    def test_invitation_expires_when_room_is_full(self):
        mode = GameInvitation.Mode.POKE_UNO

        room = self._create_room(
            mode,
            max_players=2,
        )

        GamePlayer.objects.create(
            game=room,
            user=self.outsider,
            turn_order=1,
        )

        invitation = self._create_invitation(
            mode,
            room,
        )

        self.client.force_login(self.friend)

        response = self.client.post(
            reverse(
                "accept_game_invitation",
                kwargs={
                    "invitation_id": invitation.pk,
                },
            )
        )

        self.assertEqual(
            response.status_code,
            302,
        )

        invitation.refresh_from_db()

        self.assertEqual(
            invitation.status,
            GameInvitation.Status.EXPIRED,
        )
        self.assertFalse(
            room.players.filter(
                user=self.friend,
            ).exists()
        )

    def test_invitations_page_expires_stale_invitations(
        self,
    ):
        mode = GameInvitation.Mode.PICTIONARY
        room = self._create_room(mode)

        invitation = self._create_invitation(
            mode,
            room,
        )

        room.status = PictionaryGame.Status.EN_COURS
        room.save(update_fields=["status"])

        self.client.force_login(self.friend)

        response = self.client.get(reverse("game_invitations"))

        self.assertEqual(
            response.status_code,
            200,
        )
        self.assertEqual(
            response.context["received_invitations"],
            [],
        )

        invitation.refresh_from_db()

        self.assertEqual(
            invitation.status,
            GameInvitation.Status.EXPIRED,
        )

    def test_invitation_must_reference_exactly_one_valid_room(
        self,
    ):
        poke_uno_room = self._create_room(GameInvitation.Mode.POKE_UNO)
        silhouette_room = self._create_room(GameInvitation.Mode.SILHOUETTE)

        with self.assertRaises(IntegrityError), transaction.atomic():
            GameInvitation.objects.create(
                mode=(GameInvitation.Mode.POKE_UNO),
                game=poke_uno_room,
                silhouette_game=silhouette_room,
                sender=self.host,
                recipient=self.friend,
            )

    def test_database_blocks_duplicate_pending_invitation(
        self,
    ):
        mode = GameInvitation.Mode.GUESSWHO
        room = self._create_room(mode)

        first_invitation = self._create_invitation(
            mode,
            room,
        )

        with self.assertRaises(IntegrityError), transaction.atomic():
            self._create_invitation(
                mode,
                room,
            )

        first_invitation.status = GameInvitation.Status.ACCEPTED
        first_invitation.save(update_fields=["status"])

        second_invitation = self._create_invitation(
            mode,
            room,
        )

        self.assertEqual(
            second_invitation.status,
            GameInvitation.Status.PENDING,
        )

    def test_invitation_actions_reject_get_requests(self):
        mode = GameInvitation.Mode.POKE_UNO
        room = self._create_room(mode)

        invitation = self._create_invitation(
            mode,
            room,
        )

        self.client.force_login(self.host)

        send_response = self.client.get(
            self._send_url(
                mode,
                room,
            )
        )

        self.assertEqual(
            send_response.status_code,
            405,
        )

        self.client.force_login(self.friend)

        accept_response = self.client.get(
            reverse(
                "accept_game_invitation",
                kwargs={
                    "invitation_id": invitation.pk,
                },
            )
        )

        decline_response = self.client.get(
            reverse(
                "decline_game_invitation",
                kwargs={
                    "invitation_id": invitation.pk,
                },
            )
        )

        self.assertEqual(
            accept_response.status_code,
            405,
        )
        self.assertEqual(
            decline_response.status_code,
            405,
        )

        self.client.force_login(self.host)

        cancel_response = self.client.get(
            reverse(
                "cancel_game_invitation",
                kwargs={
                    "invitation_id": invitation.pk,
                },
            )
        )

        self.assertEqual(
            cancel_response.status_code,
            405,
        )
