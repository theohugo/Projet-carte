import json
from datetime import timedelta
from pathlib import Path
from unittest.mock import patch

from django.conf import settings
from django.test import TestCase
from django.utils import timezone

from metamorph.models import MetamorphCard, MetamorphGame, MetamorphMove
from metamorph.services import (
    MAX_PLAYERS,
    PAIR_COUNT,
    MetamorphCatalogError,
    MetamorphPermissionError,
    MetamorphStateError,
    StaleRevisionError,
    create_game,
    draw_card,
    join_game,
    serialize_game_state,
    start_game,
)

from .factories import make_catalog, make_users


class MetamorphServiceTests(TestCase):
    def setUp(self):
        self.species, self.ditto = make_catalog()
        self.users = make_users()
        self.host = self.users[0]
        self.guest = self.users[1]
        self.outsider = self.users[-1]

    def make_waiting_game(self, player_count=2):
        game = create_game(self.host)
        for user in self.users[1:player_count]:
            game, _ = join_game(game.id, user)
        return game

    def start_deterministically(self, game, user=None, shuffle=None):
        shuffle_effect = shuffle or (lambda deck: None)
        with (
            patch("metamorph.services.random.sample", return_value=self.species[:PAIR_COUNT]),
            patch("metamorph.services.random.shuffle", side_effect=shuffle_effect),
        ):
            return start_game(
                game.id,
                user or self.host,
                game.turn_revision,
            )

    def test_create_and_join_register_two_to_six_ordered_players(self):
        game = create_game(self.host)

        self.assertEqual(game.status, MetamorphGame.Status.EN_ATTENTE)
        self.assertEqual(game.players.get().turn_order, 0)
        for user in self.users[1:MAX_PLAYERS]:
            game, player = join_game(game.id, user)
            self.assertEqual(player.turn_order, game.players.count() - 1)

        self.assertEqual(game.players.count(), MAX_PLAYERS)
        repeated_game, repeated_player = join_game(game.id, self.users[1])
        self.assertEqual(repeated_player.user, self.users[1])
        self.assertEqual(repeated_game.players.count(), MAX_PLAYERS)
        with self.assertRaisesMessage(MetamorphStateError, "complète"):
            join_game(game.id, self.outsider)

    def test_only_host_can_start_and_at_least_two_players_are_required(self):
        one_player_game = create_game(self.host)
        with self.assertRaisesMessage(MetamorphStateError, "entre 2 et 6"):
            start_game(one_player_game.id, self.host, one_player_game.turn_revision)

        game = self.make_waiting_game()
        with self.assertRaisesMessage(MetamorphPermissionError, "Seul l'hôte"):
            start_game(game.id, self.guest, game.turn_revision)

    def test_start_builds_twelve_pairs_and_one_real_ditto(self):
        game = self.start_deterministically(self.make_waiting_game())

        self.assertEqual(game.status, MetamorphGame.Status.EN_COURS)
        self.assertEqual(game.cards.count(), PAIR_COUNT * 2 + 1)
        ditto_card = game.cards.get(is_ditto=True)
        self.assertEqual(ditto_card.pokemon_card, self.ditto)
        self.assertEqual(ditto_card.copy_index, 0)
        self.assertEqual(game.current_turn.user, self.host)
        self.assertIsNotNone(game.started_at)
        for pokemon in self.species:
            self.assertEqual(
                game.cards.filter(pokemon_card=pokemon).count(),
                2,
            )

    def test_initial_pairs_are_removed_and_remaining_positions_are_compact(self):
        def force_two_initial_pairs(deck):
            deck[1], deck[2] = deck[2], deck[1]

        game = self.start_deterministically(
            self.make_waiting_game(),
            shuffle=force_two_initial_pairs,
        )

        paired = game.cards.filter(paired_at__isnull=False)
        self.assertEqual(paired.count(), 4)
        self.assertFalse(paired.filter(owner__isnull=False).exists())
        self.assertFalse(paired.filter(hand_position__gt=0).exists())
        for player in game.players.all():
            hand = list(player.hand_cards.order_by("hand_position"))
            self.assertEqual(
                [card.hand_position for card in hand],
                list(range(1, len(hand) + 1)),
            )
            pokemon_ids = [card.pokemon_card_id for card in hand if not card.is_ditto]
            self.assertEqual(len(pokemon_ids), len(set(pokemon_ids)))

    def test_draw_uses_previous_player_and_removes_a_new_pair(self):
        game = self.start_deterministically(self.make_waiting_game())
        original_revision = game.turn_revision
        host_state = serialize_game_state(game, self.host)

        self.assertEqual(host_state["draw_source"]["player"]["username"], self.guest.username)
        self.assertEqual(
            host_state["draw_source"]["hidden_cards"],
            [{"position": position} for position in range(1, PAIR_COUNT + 1)],
        )

        game = draw_card(game.id, self.host, 1, original_revision)

        move = MetamorphMove.objects.get(game=game)
        self.assertEqual(move.actor.user, self.host)
        self.assertEqual(move.source.user, self.guest)
        self.assertTrue(move.formed_pair)
        self.assertEqual(move.drawn_card.pokemon_card, self.species[0])
        self.assertEqual(
            game.cards.filter(pokemon_card=self.species[0], paired_at__isnull=False).count(),
            2,
        )
        self.assertEqual(game.current_turn.user, self.guest)
        self.assertEqual(game.turn_revision, original_revision + 1)

    def test_ranked_players_are_skipped_in_both_turn_and_draw_direction(self):
        game = self.start_deterministically(self.make_waiting_game(player_count=3))
        host, skipped, previous = list(game.players.order_by("turn_order"))
        moment = timezone.now()

        game.cards.filter(is_ditto=False).update(
            owner=None,
            hand_position=0,
            paired_at=moment,
        )
        ditto_card = game.cards.get(is_ditto=True)
        ditto_card.owner = host
        ditto_card.hand_position = 1
        ditto_card.save(update_fields=["owner", "hand_position"])
        for position, pokemon in enumerate(self.species[:2], start=2):
            first, second = list(game.cards.filter(pokemon_card=pokemon).order_by("copy_index"))
            first.owner = host
            first.hand_position = position
            first.paired_at = None
            second.owner = previous
            second.hand_position = position - 1
            second.paired_at = None
            MetamorphCard.objects.bulk_update(
                [first, second],
                ["owner", "hand_position", "paired_at"],
            )
        skipped.rank = 1
        skipped.finished_at = moment - timedelta(seconds=1)
        skipped.save(update_fields=["rank", "finished_at"])
        game.current_turn = host
        game.save(update_fields=["current_turn"])

        state = serialize_game_state(game, self.host)
        self.assertEqual(state["draw_source"]["player"]["id"], previous.id)
        game = draw_card(game.id, self.host, 1, game.turn_revision)

        self.assertEqual(game.status, MetamorphGame.Status.EN_COURS)
        self.assertEqual(game.current_turn_id, previous.id)
        previous_state = serialize_game_state(game, previous.user)
        self.assertEqual(previous_state["draw_source"]["player"]["id"], host.id)

    def test_last_ditto_holder_loses_and_everyone_receives_a_rank(self):
        game = self.start_deterministically(self.make_waiting_game())
        host_player, guest_player = list(game.players.order_by("turn_order"))
        moment = timezone.now()
        game.cards.filter(is_ditto=False).update(
            owner=None,
            hand_position=0,
            paired_at=moment,
        )
        ditto_card = game.cards.get(is_ditto=True)
        ditto_card.owner = host_player
        ditto_card.hand_position = 1
        ditto_card.save(update_fields=["owner", "hand_position"])
        first, second = list(game.cards.filter(pokemon_card=self.species[0]).order_by("copy_index"))
        first.owner = host_player
        first.hand_position = 2
        first.paired_at = None
        second.owner = guest_player
        second.hand_position = 1
        second.paired_at = None
        MetamorphCard.objects.bulk_update(
            [first, second],
            ["owner", "hand_position", "paired_at"],
        )
        game.current_turn = host_player
        game.save(update_fields=["current_turn"])

        game = draw_card(game.id, self.host, 1, game.turn_revision)

        host_player.refresh_from_db()
        guest_player.refresh_from_db()
        self.assertEqual(game.status, MetamorphGame.Status.TERMINEE)
        self.assertIsNone(game.current_turn)
        self.assertTrue(host_player.is_loser)
        self.assertEqual(host_player.rank, 2)
        self.assertFalse(guest_player.is_loser)
        self.assertEqual(guest_player.rank, 1)
        self.assertIsNotNone(game.finished_at)
        result = serialize_game_state(game, self.guest)
        self.assertEqual([entry["rank"] for entry in result["standings"]], [1, 2])
        self.assertEqual(result["loser"]["username"], self.host.username)

    def test_stale_revision_rejects_a_duplicate_draw(self):
        game = self.start_deterministically(self.make_waiting_game())
        revision = game.turn_revision
        game = draw_card(game.id, self.host, 1, revision)

        with self.assertRaises(StaleRevisionError) as raised:
            draw_card(game.id, self.host, 1, revision)

        self.assertEqual(raised.exception.actual, game.turn_revision)
        self.assertEqual(MetamorphMove.objects.filter(game=game).count(), 1)

    def test_invalid_turn_position_and_outsider_are_rejected(self):
        game = self.start_deterministically(self.make_waiting_game())
        with self.assertRaisesMessage(MetamorphStateError, "pas votre tour"):
            draw_card(game.id, self.guest, 1, game.turn_revision)
        with self.assertRaisesMessage(MetamorphStateError, "plus disponible"):
            draw_card(game.id, self.host, 999, game.turn_revision)
        with self.assertRaises(MetamorphPermissionError):
            draw_card(game.id, self.outsider, 1, game.turn_revision)

    def test_state_never_contains_an_opponents_hand_or_hidden_card_identity(self):
        game = self.start_deterministically(self.make_waiting_game())
        host_state = serialize_game_state(game, self.host)
        guest_state = serialize_game_state(game, self.guest)

        for state in (host_state, guest_state):
            for player in state["players"]:
                self.assertNotIn("hand", player)
                self.assertNotIn("cards", player)
                self.assertNotIn("pokemon", player)
            if state["can_draw"]:
                for hidden in state["draw_source"]["hidden_cards"]:
                    self.assertEqual(set(hidden), {"position"})
            else:
                self.assertEqual(state["draw_source"]["hidden_cards"], [])

        self.assertTrue(host_state["me"]["hand"])
        self.assertTrue(guest_state["me"]["hand"])
        self.assertNotEqual(
            host_state["me"]["hand"][0]["physical_id"],
            guest_state["me"]["hand"][0]["physical_id"],
        )

    def test_unmatched_move_history_does_not_reveal_drawn_pokemon(self):
        game = self.start_deterministically(self.make_waiting_game())
        host_player = game.players.get(user=self.host)
        host_copy = game.cards.get(owner=host_player, pokemon_card=self.species[0])
        host_copy.owner = None
        host_copy.hand_position = 0
        host_copy.paired_at = timezone.now()
        host_copy.save(update_fields=["owner", "hand_position", "paired_at"])
        remaining = list(game.cards.filter(owner=host_player).order_by("hand_position"))
        for position, card in enumerate(remaining, start=1):
            card.hand_position = position
        MetamorphCard.objects.bulk_update(remaining, ["hand_position"])

        game = draw_card(game.id, self.host, 1, game.turn_revision)
        guest_state = serialize_game_state(game, self.guest)

        self.assertFalse(guest_state["moves"][-1]["formed_pair"])
        self.assertIsNone(guest_state["moves"][-1]["pair"])
        move_payload = json.dumps(guest_state["moves"][-1])
        self.assertNotIn(self.species[0].name_fr, move_payload)
        self.assertNotIn(self.species[0].sprite_url, move_payload)

    def test_start_requires_ditto_and_enough_pair_species(self):
        game = self.make_waiting_game()
        self.ditto.delete()
        with self.assertRaisesMessage(MetamorphCatalogError, "Métamorph"):
            start_game(game.id, self.host, game.turn_revision)


class ShippedMetamorphCatalogTests(TestCase):
    def test_committed_catalog_contains_real_ditto_and_enough_pairs(self):
        fixture_path = Path(settings.BASE_DIR) / "game" / "fixtures" / "pokemon_cards.json"
        fixture = json.loads(fixture_path.read_text(encoding="utf-8"))
        cards = [*fixture.get("cards", []), *fixture.get("catalogue", [])]

        dittos = [card for card in cards if card.get("pokedex_id") == 132]
        self.assertEqual(len(dittos), 1)
        self.assertEqual(dittos[0]["name_fr"], "Métamorph")
        self.assertTrue(dittos[0]["sprite_url"].endswith(".png"))
        self.assertGreaterEqual(len(cards) - 1, PAIR_COUNT)
