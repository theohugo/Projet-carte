import json

from django.test import TestCase

from game.models import PokemonCard
from islands.models import IslandGame, Shot
from islands.services import (
    IslandCatalogError,
    IslandPermissionError,
    IslandPlacementError,
    IslandStateError,
    StaleRevisionError,
    create_game,
    fire,
    join_game,
    place_formation,
    ready_player,
    serialize_game_state,
)

from .factories import deploy_all, make_catalog, make_users, ready_both


class IslandServiceTests(TestCase):
    def setUp(self):
        self.cards = make_catalog()
        self.host, self.guest, self.outsider = make_users()

    def make_joined_game(self):
        game = create_game(self.host)
        game, _player = join_game(game.id, self.guest)
        return game

    def make_started_game(self):
        return ready_both(self.make_joined_game(), self.host, self.guest)

    def test_creation_registers_host_and_four_water_formations(self):
        game = create_game(self.host)

        self.assertEqual(game.status, IslandGame.Status.EN_ATTENTE)
        self.assertEqual(game.turn_revision, 0)
        player = game.players.get()
        self.assertEqual(player.user, self.host)
        self.assertEqual(player.turn_order, 0)
        self.assertEqual(list(player.formations.values_list("size", flat=True)), [2, 3, 3, 4])
        self.assertTrue(
            all(
                formation.pokemon_card.primary_type.slug == "water"
                for formation in player.formations.select_related("pokemon_card__primary_type")
            )
        )
        self.assertTrue(
            all(
                "official-artwork" in formation.pokemon_card.sprite_url
                for formation in player.formations.all()
            )
        )

    def test_catalog_must_hold_four_species_and_creation_rolls_back(self):
        PokemonCard.objects.filter(pk__in=[card.pk for card in self.cards[3:]]).delete()

        with self.assertRaisesMessage(IslandCatalogError, "au moins 4 Pokémon"):
            create_game(self.host)

        self.assertFalse(IslandGame.objects.exists())

    def test_non_water_catalogue_is_used_only_as_fallback(self):
        PokemonCard.objects.filter(pk__in=[card.pk for card in self.cards[2:]]).delete()
        make_catalog(water_count=0, other_count=3, start=100)

        game = create_game(self.host)
        types = [
            formation.pokemon_card.primary_type.slug
            for formation in game.players.get().formations.select_related("pokemon_card__primary_type")
        ]

        self.assertEqual(types.count("water"), 2)
        self.assertEqual(types.count("normal"), 2)

    def test_exactly_one_opponent_joins_and_repeat_join_is_idempotent(self):
        game = create_game(self.host)
        game, guest_player = join_game(game.id, self.guest)
        repeated, repeated_player = join_game(game.id, self.guest)

        self.assertEqual(game.status, IslandGame.Status.PLACEMENT)
        self.assertEqual(game.turn_revision, 1)
        self.assertEqual(repeated.turn_revision, 1)
        self.assertEqual(repeated_player.id, guest_player.id)
        self.assertEqual(game.players.count(), 2)
        with self.assertRaisesMessage(IslandStateError, "n'accepte plus"):
            join_game(game.id, self.outsider)

    def test_placement_accepts_borders_but_rejects_overflow_and_overlap(self):
        game = self.make_joined_game()
        formations = list(game.players.get(user=self.host).formations.order_by("slot"))

        game = place_formation(game.id, self.host, formations[0].id, 0, 6, "H", game.turn_revision)
        with self.assertRaisesMessage(IslandPlacementError, "dépasse"):
            place_formation(game.id, self.host, formations[1].id, 0, 6, "H", game.turn_revision)
        with self.assertRaisesMessage(IslandPlacementError, "même case"):
            place_formation(game.id, self.host, formations[1].id, 0, 5, "H", game.turn_revision)

        game = place_formation(game.id, self.host, formations[1].id, 5, 7, "V", game.turn_revision)
        formations[1].refresh_from_db()
        self.assertEqual(formations[1].cells, [(5, 7), (6, 7), (7, 7)])

    def test_player_cannot_move_opponent_formation_or_move_after_ready(self):
        game = self.make_joined_game()
        opponent_formation = game.players.get(user=self.guest).formations.first()
        with self.assertRaises(IslandPermissionError):
            place_formation(game.id, self.host, opponent_formation.id, 0, 0, "H", game.turn_revision)

        game = deploy_all(game, self.host)
        game = ready_player(game.id, self.host, game.turn_revision)
        own = game.players.get(user=self.host).formations.first()
        with self.assertRaisesMessage(IslandStateError, "verrouillée"):
            place_formation(game.id, self.host, own.id, 5, 5, "H", game.turn_revision)

    def test_ready_requires_all_four_formations_and_both_players(self):
        game = self.make_joined_game()
        with self.assertRaisesMessage(IslandPlacementError, "quatre Pokémon"):
            ready_player(game.id, self.host, game.turn_revision)

        game = deploy_all(game, self.host)
        game = ready_player(game.id, self.host, game.turn_revision)
        self.assertEqual(game.status, IslandGame.Status.PLACEMENT)
        self.assertTrue(game.players.get(user=self.host).is_ready)

        game = deploy_all(game, self.guest)
        game = ready_player(game.id, self.guest, game.turn_revision)
        self.assertEqual(game.status, IslandGame.Status.EN_COURS)
        self.assertEqual(game.current_turn.user, self.host)
        self.assertIsNotNone(game.started_at)

    def test_fire_alternates_turns_and_reports_miss_hit_then_capture(self):
        game = self.make_started_game()
        target_formation = game.players.get(user=self.guest).formations.get(slot=0)

        game, first = fire(game.id, self.host, 0, 0, game.turn_revision)
        self.assertEqual(first.result, Shot.Result.HIT)
        self.assertEqual(first.formation, target_formation)
        self.assertEqual(game.current_turn.user, self.guest)
        game, missed = fire(game.id, self.guest, 6, 7, game.turn_revision)
        self.assertEqual(missed.result, Shot.Result.MISS)
        self.assertIsNone(missed.formation)
        game, captured = fire(game.id, self.host, 0, 1, game.turn_revision)
        self.assertEqual(captured.result, Shot.Result.CAPTURED)
        self.assertEqual(captured.formation, target_formation)

    def test_wrong_turn_duplicate_and_out_of_range_shots_are_rejected(self):
        game = self.make_started_game()
        with self.assertRaisesMessage(IslandStateError, "pas votre tour"):
            fire(game.id, self.guest, 0, 0, game.turn_revision)
        with self.assertRaisesMessage(IslandPlacementError, "entre 1 et 8"):
            fire(game.id, self.host, 8, 0, game.turn_revision)

        game, _ = fire(game.id, self.host, 0, 0, game.turn_revision)
        game, _ = fire(game.id, self.guest, 6, 7, game.turn_revision)
        with self.assertRaisesMessage(IslandStateError, "déjà"):
            fire(game.id, self.host, 0, 0, game.turn_revision)

    def test_all_twelve_hits_end_game_and_reveal_winner(self):
        game = self.make_started_game()
        target_cells = [
            cell
            for formation in game.players.get(user=self.guest).formations.order_by("slot")
            for cell in formation.cells
        ]
        guest_misses = [(6, col) for col in range(7, -1, -1)] + [(5, col) for col in range(7, 3, -1)]
        for index, (row, col) in enumerate(target_cells):
            game, _ = fire(game.id, self.host, row, col, game.turn_revision)
            if index < len(target_cells) - 1:
                miss_row, miss_col = guest_misses[index]
                game, _ = fire(game.id, self.guest, miss_row, miss_col, game.turn_revision)

        self.assertEqual(game.status, IslandGame.Status.TERMINEE)
        self.assertEqual(game.winner.user, self.host)
        self.assertIsNone(game.current_turn)
        self.assertIsNotNone(game.finished_at)
        self.assertEqual(game.shots.filter(target__user=self.guest, formation__isnull=False).count(), 12)

    def test_opponent_positions_are_never_serialized_before_game_end(self):
        game = self.make_started_game()
        guest_formations = list(game.players.get(user=self.guest).formations.select_related("pokemon_card"))

        host_state = serialize_game_state(game, self.host)
        self.assertEqual(host_state["opponent_formations"], [])
        self.assertTrue(all("formation" not in shot for shot in host_state["shots_fired"]))
        self.assertTrue(all("row" in formation for formation in host_state["own_formations"]))
        # Aucun identifiant ou sprite adverse n'est présent dans la branche
        # dédiée au plateau adverse avant le premier tir.
        opponent_branch = json.dumps(
            {
                "formations": host_state["opponent_formations"],
                "shots": host_state["shots_fired"],
            }
        )
        for formation in guest_formations:
            self.assertNotIn(str(formation.id), opponent_branch)
            self.assertNotIn(formation.pokemon_card.sprite_url, opponent_branch)

    def test_finished_game_reveals_all_opponent_positions(self):
        game = self.make_started_game()
        game.status = IslandGame.Status.TERMINEE
        game.winner = game.players.get(user=self.host)
        game.save(update_fields=["status", "winner"])

        state = serialize_game_state(game, self.host)

        self.assertEqual(len(state["opponent_formations"]), 4)
        self.assertTrue(
            all(len(formation["cells"]) == formation["size"] for formation in state["opponent_formations"])
        )

    def test_outsider_cannot_read_or_mutate(self):
        game = self.make_started_game()
        with self.assertRaises(IslandPermissionError):
            serialize_game_state(game, self.outsider)
        with self.assertRaises(IslandPermissionError):
            fire(game.id, self.outsider, 0, 0, game.turn_revision)

    def test_stale_revision_prevents_duplicate_placement_and_fire(self):
        game = self.make_joined_game()
        formation = game.players.get(user=self.host).formations.first()
        stale = game.turn_revision
        game = place_formation(game.id, self.host, formation.id, 0, 0, "H", stale)
        with self.assertRaises(StaleRevisionError):
            place_formation(game.id, self.host, formation.id, 2, 0, "H", stale)
        formation.refresh_from_db()
        self.assertEqual((formation.start_row, formation.start_col), (0, 0))

        game = ready_both(game, self.host, self.guest)
        stale = game.turn_revision
        game, _ = fire(game.id, self.host, 0, 0, stale)
        with self.assertRaises(StaleRevisionError):
            fire(game.id, self.host, 0, 0, stale)
        self.assertEqual(Shot.objects.filter(shooter__user=self.host).count(), 1)

    def test_serialized_state_contract_has_no_model_objects(self):
        game = self.make_started_game()
        state = serialize_game_state(game, self.host)

        self.assertEqual(state["grid_size"], 8)
        self.assertTrue(state["is_my_turn"])
        self.assertEqual([formation["size"] for formation in state["own_formations"]], [2, 3, 3, 4])
        json.dumps(state)
