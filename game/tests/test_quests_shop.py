import random

from django.test import TestCase
from django.urls import reverse

from game.game_engine import GameEngine
from game.models import BoosterOpening, CollectionCard, PokemonCard, Profile, QuestProgress
from game.quests import (
    EVENT_GAME_PLAYED,
    EVENT_GAME_WON,
    EVENT_PICTIONARY_FOUND,
    EVENT_SILHOUETTE_FOUND,
    QUESTS_BY_KEY,
    QuestError,
    claim_reward,
    period_key,
    quest_board,
    record_event,
)
from game.shop import (
    BOOSTERS_BY_KEY,
    COMMUNE,
    LEGENDAIRE,
    RARE,
    ShopError,
    draw_cards,
    open_booster,
    rarity_of,
)
from game.tests.factories import make_cards, make_draft_catalogue, make_game, make_types, make_users


class QuestProgressTests(TestCase):
    def setUp(self):
        (self.user,) = make_users(1)

    def test_an_event_advances_every_quest_that_watches_it(self):
        record_event(self.user, EVENT_GAME_PLAYED)

        board = quest_board(self.user)
        daily = next(q for q in board["daily"] if q["key"] == "daily_play_three")
        weekly = next(q for q in board["weekly"] if q["key"] == "weekly_marathon")
        self.assertEqual(daily["progress"], 1)
        self.assertEqual(weekly["progress"], 1)

    def test_progress_stops_at_the_target(self):
        for _ in range(10):
            record_event(self.user, EVENT_GAME_WON)

        daily = next(q for q in quest_board(self.user)["daily"] if q["key"] == "daily_win_one")
        self.assertEqual(daily["progress"], 1)
        self.assertTrue(daily["claimable"])

    def test_a_finished_quest_pays_once(self):
        for _ in range(5):
            record_event(self.user, EVENT_SILHOUETTE_FOUND)

        reward = claim_reward(self.user, "daily_silhouettes")

        self.user.profile.refresh_from_db()
        self.assertEqual(reward, QUESTS_BY_KEY["daily_silhouettes"].reward)
        self.assertEqual(self.user.profile.points, reward)
        with self.assertRaises(QuestError):
            claim_reward(self.user, "daily_silhouettes")

    def test_an_unfinished_quest_pays_nothing(self):
        record_event(self.user, EVENT_SILHOUETTE_FOUND)

        with self.assertRaises(QuestError):
            claim_reward(self.user, "daily_silhouettes")

        self.user.profile.refresh_from_db()
        self.assertEqual(self.user.profile.points, 0)

    def test_an_unknown_quest_is_refused(self):
        with self.assertRaises(QuestError):
            claim_reward(self.user, "quete-inventee")

    def test_pictionary_finds_also_feed_the_weekly_guesser_quest(self):
        for _ in range(3):
            record_event(self.user, EVENT_PICTIONARY_FOUND)

        weekly = next(q for q in quest_board(self.user)["weekly"] if q["key"] == "weekly_guesser")
        self.assertEqual(weekly["progress"], 3)

    def test_yesterday_progress_does_not_count_today(self):
        QuestProgress.objects.create(
            user=self.user,
            quest_key="daily_win_one",
            period_key="2020-01-01",
            progress=5,
        )

        daily = next(q for q in quest_board(self.user)["daily"] if q["key"] == "daily_win_one")
        self.assertEqual(daily["progress"], 0)

    def test_daily_and_weekly_periods_are_distinct(self):
        self.assertNotEqual(
            period_key(QUESTS_BY_KEY["daily_win_one"]),
            period_key(QUESTS_BY_KEY["weekly_champion"]),
        )

    def test_a_bot_seat_never_breaks_the_tracking(self):
        record_event(None, EVENT_GAME_PLAYED)

        self.assertEqual(QuestProgress.objects.count(), 0)


class QuestFromRealGamesTests(TestCase):
    def setUp(self):
        self.types = make_types()
        make_cards(self.types)
        make_draft_catalogue(self.types)
        self.users = make_users(2)

    def test_finishing_a_poke_uno_game_advances_the_quests(self):
        game = make_game(self.users[0])
        engine = GameEngine(game)
        winner = engine.add_player(self.users[0])
        engine.add_player(self.users[1])

        engine.end_game(winner=winner)

        board = quest_board(self.users[0])
        played = next(q for q in board["daily"] if q["key"] == "daily_play_three")
        won = next(q for q in board["daily"] if q["key"] == "daily_win_one")
        loser_board = quest_board(self.users[1])
        loser_won = next(q for q in loser_board["daily"] if q["key"] == "daily_win_one")
        self.assertEqual(played["progress"], 1)
        self.assertEqual(won["progress"], 1)
        self.assertEqual(loser_won["progress"], 0)


class ShopTests(TestCase):
    def setUp(self):
        self.types = make_types()
        make_cards(self.types)
        # Un catalogue Gen 1 complet côté raretés : communes, rares, légendaire.
        for pokedex_id in (16, 19, 21, 23, 25, 27, 29):
            PokemonCard.objects.create(
                pokedex_id=pokedex_id,
                slug=f"commune-{pokedex_id}",
                name_fr=f"Commune {pokedex_id}",
                name_en=f"Common {pokedex_id}",
                primary_type=self.types["fire"],
                sprite_url=f"https://example.com/{pokedex_id}.png",
            )
        for pokedex_id in (3, 6, 9):
            PokemonCard.objects.create(
                pokedex_id=pokedex_id,
                slug=f"rare-{pokedex_id}",
                name_fr=f"Rare {pokedex_id}",
                name_en=f"Rare {pokedex_id}",
                primary_type=self.types["water"],
                sprite_url=f"https://example.com/{pokedex_id}.png",
            )
        self.legendary = PokemonCard.objects.create(
            pokedex_id=150,
            slug="mewtwo",
            name_fr="Mewtwo",
            name_en="Mewtwo",
            primary_type=self.types["water"],
            sprite_url="https://example.com/150.png",
            is_legendary=True,
        )
        (self.user,) = make_users(1)

    def give_points(self, amount):
        Profile.objects.filter(user=self.user).update(points=amount)

    def test_rarity_follows_the_catalogue(self):
        self.assertEqual(rarity_of(self.legendary), LEGENDAIRE)
        self.assertEqual(rarity_of(PokemonCard.objects.get(pokedex_id=6)), RARE)
        self.assertEqual(rarity_of(PokemonCard.objects.get(pokedex_id=19)), COMMUNE)

    def test_a_booster_holds_the_expected_number_of_cards(self):
        booster = BOOSTERS_BY_KEY["base"]

        cards = draw_cards(booster, random.Random(3))

        self.assertEqual(len(cards), booster.card_count)

    def test_the_premium_booster_always_holds_a_rare_or_better(self):
        booster = BOOSTERS_BY_KEY["premium"]

        for seed in range(15):
            with self.subTest(seed=seed):
                cards = draw_cards(booster, random.Random(seed))

                self.assertTrue(any(rarity_of(card) in (RARE, LEGENDAIRE) for card in cards))

    def test_opening_debits_the_points_and_fills_the_collection(self):
        self.give_points(500)

        result = open_booster(self.user, "base", random.Random(7))

        self.user.profile.refresh_from_db()
        self.assertEqual(len(result["cards"]), 5)
        self.assertEqual(self.user.profile.points, 350)
        self.assertEqual(result["points_left"], 350)
        self.assertEqual(BoosterOpening.objects.count(), 1)
        self.assertGreaterEqual(CollectionCard.objects.filter(user=self.user).count(), 1)

    def test_a_duplicate_card_increases_the_copies(self):
        self.give_points(2000)

        for _ in range(6):
            open_booster(self.user, "base", random.Random(1))

        best = CollectionCard.objects.filter(user=self.user).order_by("-copies").first()
        self.assertGreater(best.copies, 1)

    def test_a_booster_out_of_reach_is_refused(self):
        self.give_points(10)

        with self.assertRaisesMessage(ShopError, "Il te manque"):
            open_booster(self.user, "base")

        self.assertEqual(BoosterOpening.objects.count(), 0)

    def test_an_unknown_booster_is_refused(self):
        self.give_points(1000)

        with self.assertRaises(ShopError):
            open_booster(self.user, "booster-fantome")


class ShopViewTests(TestCase):
    def setUp(self):
        self.types = make_types()
        make_cards(self.types)
        (self.user,) = make_users(1)
        self.client.force_login(self.user)

    def test_the_shop_shows_the_points_and_the_boosters(self):
        Profile.objects.filter(user=self.user).update(points=175)

        response = self.client.get(reverse("shop"))

        self.assertEqual(response.status_code, 200)
        self.assertContains(response, "Booster Set de Base")
        self.assertContains(response, "175")

    def test_opening_without_points_answers_with_an_explanation(self):
        response = self.client.post(reverse("api_open_booster", args=["base"]))

        self.assertEqual(response.status_code, 400)
        self.assertIn("manque", response.json()["error"])

    def test_opening_returns_the_cards_and_the_remaining_points(self):
        Profile.objects.filter(user=self.user).update(points=300)

        response = self.client.post(reverse("api_open_booster", args=["base"]))

        payload = response.json()
        self.assertEqual(response.status_code, 200)
        self.assertEqual(len(payload["cards"]), 5)
        self.assertEqual(payload["points_left"], 150)
        self.assertIn("rarity", payload["cards"][0])

    def test_the_collection_marks_what_is_owned(self):
        card = PokemonCard.objects.filter(pokedex_id__lte=151).first()
        CollectionCard.objects.create(user=self.user, pokemon_card=card, copies=2)

        response = self.client.get(reverse("collection"))

        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.context["owned_count"], 1)
        self.assertContains(response, "×2")

    def test_claiming_a_quest_from_the_page_credits_the_points(self):
        for _ in range(5):
            record_event(self.user, EVENT_SILHOUETTE_FOUND)

        response = self.client.post(reverse("claim_quest", args=["daily_silhouettes"]))

        self.user.profile.refresh_from_db()
        self.assertRedirects(response, reverse("quests"))
        self.assertEqual(self.user.profile.points, QUESTS_BY_KEY["daily_silhouettes"].reward)
