import random

from django.test import TestCase
from django.urls import reverse

from game.card_prints import prints_of
from game.game_engine import GameEngine
from game.models import (
    BoosterOpening,
    BoosterTicket,
    CollectionCard,
    PokemonCard,
    Profile,
    QuestProgress,
)
from game.quests import (
    EVENT_GAME_PLAYED,
    EVENT_GAME_WON,
    EVENT_PICTIONARY_FOUND,
    EVENT_SILHOUETTE_FOUND,
    QUESTS,
    QUESTS_BY_KEY,
    QuestError,
    claim_reward,
    period_key,
    quest_board,
    record_event,
)
from game.rarities import (
    COMMUNE,
    DOUBLE_RARE,
    HYPER_RARE,
    ILLUSTRATION_SPECIALE,
    LEGENDAIRE,
    RARE,
    RARITIES_BY_KEY,
    ULTRA_RARE,
)
from game.seasons import SEASON_151, SEASON_BASE
from game.shop import (
    BOOSTERS,
    BOOSTERS_BY_KEY,
    ShopError,
    draw_cards,
    open_booster,
    open_ticket,
    rarity_of,
)
from game.tcg_card_images import get_tcg_image_url
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

        claim = claim_reward(self.user, "daily_silhouettes")

        self.user.profile.refresh_from_db()
        self.assertEqual(claim.points, QUESTS_BY_KEY["daily_silhouettes"].reward)
        self.assertEqual(self.user.profile.points, claim.points)
        with self.assertRaises(QuestError):
            claim_reward(self.user, "daily_silhouettes")

    def test_a_daily_quest_pays_in_points_only(self):
        for _ in range(5):
            record_event(self.user, EVENT_SILHOUETTE_FOUND)

        claim = claim_reward(self.user, "daily_silhouettes")

        self.assertEqual(claim.booster_label, "")
        self.assertEqual(BoosterTicket.objects.filter(user=self.user).count(), 0)

    def test_every_weekly_quest_offers_a_booster(self):
        for quest in QUESTS:
            if quest.period == "weekly":
                with self.subTest(quest=quest.key):
                    self.assertIn(quest.booster, BOOSTERS_BY_KEY)

    def test_a_weekly_quest_adds_a_booster_to_open(self):
        for _ in range(5):
            record_event(self.user, EVENT_GAME_WON)

        claim = claim_reward(self.user, "weekly_champion")

        ticket = BoosterTicket.objects.get(user=self.user)
        self.user.profile.refresh_from_db()
        self.assertEqual(self.user.profile.points, QUESTS_BY_KEY["weekly_champion"].reward)
        self.assertEqual(ticket.booster_key, QUESTS_BY_KEY["weekly_champion"].booster)
        self.assertEqual(ticket.source, "weekly_champion")
        self.assertIsNone(ticket.opened_at)
        self.assertEqual(claim.booster_label, BOOSTERS_BY_KEY[ticket.booster_key].label)

    def test_a_weekly_quest_claimed_twice_offers_a_single_booster(self):
        for _ in range(5):
            record_event(self.user, EVENT_GAME_WON)
        claim_reward(self.user, "weekly_champion")

        with self.assertRaises(QuestError):
            claim_reward(self.user, "weekly_champion")

        self.assertEqual(BoosterTicket.objects.filter(user=self.user).count(), 1)

    def test_the_board_announces_the_booster_of_a_weekly_quest(self):
        board = quest_board(self.user)

        weekly = next(q for q in board["weekly"] if q["key"] == "weekly_champion")
        daily = next(q for q in board["daily"] if q["key"] == "daily_win_one")
        self.assertEqual(weekly["booster_label"], BOOSTERS_BY_KEY["s151_ultra"].label)
        self.assertEqual(daily["booster_label"], "")

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

    def fill_gen_one_catalogue(self):
        """Complète le catalogue jusqu'à 151 espèces.

        Une saison à impressions tire dans tout le set : sans les 151 espèces,
        la moitié des cartes tirées n'aurait pas d'entrée au catalogue.
        """

        known = set(PokemonCard.objects.values_list("pokedex_id", flat=True))
        PokemonCard.objects.bulk_create(
            PokemonCard(
                pokedex_id=pokedex_id,
                slug=f"espece-{pokedex_id}",
                name_fr=f"Espèce {pokedex_id}",
                name_en=f"Species {pokedex_id}",
                primary_type=self.types["fire"],
                sprite_url=f"https://example.com/{pokedex_id}.png",
            )
            for pokedex_id in range(1, 152)
            if pokedex_id not in known
        )

    def test_rarity_follows_the_catalogue(self):
        self.assertEqual(rarity_of(self.legendary), LEGENDAIRE)
        self.assertEqual(rarity_of(PokemonCard.objects.get(pokedex_id=6)), RARE)
        self.assertEqual(rarity_of(PokemonCard.objects.get(pokedex_id=19)), COMMUNE)

    def test_a_second_season_booster_fills_its_own_collection(self):
        self.fill_gen_one_catalogue()
        self.give_points(1000)

        open_booster(self.user, "s151", random.Random(4))

        self.assertEqual(CollectionCard.objects.filter(user=self.user, season=SEASON_BASE).count(), 0)
        self.assertEqual(CollectionCard.objects.filter(user=self.user, season=SEASON_151).count(), 5)
        self.assertEqual(BoosterOpening.objects.get().season, SEASON_151)

    def test_a_print_without_a_species_is_shown_but_not_collected(self):
        # Catalogue volontairement incomplet : l'ouverture doit rester possible.
        self.give_points(1000)

        result = open_booster(self.user, "s151", random.Random(4))

        self.assertEqual(len(result["cards"]), 5)
        collected = CollectionCard.objects.filter(user=self.user, season=SEASON_151).count()
        self.assertLessEqual(collected, 5)

    def test_a_second_season_draw_carries_the_rarity_of_the_real_card(self):
        self.fill_gen_one_catalogue()
        self.give_points(5000)

        result = open_booster(self.user, "s151", random.Random(4))

        for card in result["cards"]:
            with self.subTest(card=card["name"]):
                self.assertIn(card["rarity"], RARITIES_BY_KEY)
                self.assertTrue(card["variant"])
                self.assertTrue(card["reveal"])
        stored = CollectionCard.objects.filter(user=self.user, season=SEASON_151)
        self.assertTrue(all(row.rarity and row.variant for row in stored))

    def test_the_same_pokemon_is_collected_once_per_season(self):
        card = PokemonCard.objects.get(pokedex_id=19)
        CollectionCard.objects.create(user=self.user, pokemon_card=card, season=SEASON_BASE)

        CollectionCard.objects.create(user=self.user, pokemon_card=card, season=SEASON_151)

        self.assertEqual(CollectionCard.objects.filter(user=self.user, pokemon_card=card).count(), 2)

    def test_two_prints_of_the_same_pokemon_are_two_cards_to_collect(self):
        card = PokemonCard.objects.get(pokedex_id=6)

        CollectionCard.objects.create(user=self.user, pokemon_card=card, season=SEASON_151, variant="6")
        CollectionCard.objects.create(user=self.user, pokemon_card=card, season=SEASON_151, variant="183")

        self.assertEqual(
            CollectionCard.objects.filter(user=self.user, season=SEASON_151, pokemon_card=card).count(),
            2,
        )

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

    def test_a_batch_opens_every_booster_at_once(self):
        self.fill_gen_one_catalogue()
        self.give_points(5000)

        result = open_booster(self.user, "s151", random.Random(11), quantity=5)

        self.user.profile.refresh_from_db()
        self.assertEqual(result["quantity"], 5)
        self.assertEqual(len(result["cards"]), 25)
        self.assertEqual(self.user.profile.points, 5000 - 5 * BOOSTERS_BY_KEY["s151"].price)
        # Une archive par booster, pas une seule pour le lot.
        self.assertEqual(BoosterOpening.objects.count(), 5)

    def test_a_batch_out_of_reach_is_refused_whole(self):
        self.give_points(BOOSTERS_BY_KEY["base"].price * 3)

        with self.assertRaisesMessage(ShopError, "ces 5 boosters"):
            open_booster(self.user, "base", quantity=5)

        self.user.profile.refresh_from_db()
        self.assertEqual(self.user.profile.points, BOOSTERS_BY_KEY["base"].price * 3)
        self.assertEqual(BoosterOpening.objects.count(), 0)

    def test_an_invented_batch_size_falls_back_on_one(self):
        self.give_points(BOOSTERS_BY_KEY["base"].price)

        result = open_booster(self.user, "base", random.Random(1), quantity=999)

        self.assertEqual(result["quantity"], 1)
        self.assertEqual(len(result["cards"]), 5)

    def test_a_booster_out_of_reach_is_refused(self):
        self.give_points(10)

        with self.assertRaisesMessage(ShopError, "Il te manque"):
            open_booster(self.user, "base")

        self.assertEqual(BoosterOpening.objects.count(), 0)

    def test_an_unknown_booster_is_refused(self):
        self.give_points(1000)

        with self.assertRaises(ShopError):
            open_booster(self.user, "booster-fantome")

    def test_a_quest_booster_opens_without_spending_a_point(self):
        ticket = BoosterTicket.objects.create(user=self.user, booster_key="s151", source="weekly_guesser")

        result = open_ticket(self.user, ticket.pk, random.Random(2))

        ticket.refresh_from_db()
        self.user.profile.refresh_from_db()
        self.assertEqual(len(result["cards"]), 5)
        self.assertEqual(result["season"], SEASON_151)
        self.assertEqual(self.user.profile.points, 0)
        self.assertIsNotNone(ticket.opened_at)
        self.assertEqual(BoosterOpening.objects.get().price, 0)

    def test_a_quest_booster_cannot_be_opened_twice(self):
        ticket = BoosterTicket.objects.create(user=self.user, booster_key="base")
        open_ticket(self.user, ticket.pk, random.Random(2))

        with self.assertRaises(ShopError):
            open_ticket(self.user, ticket.pk, random.Random(2))

        self.assertEqual(BoosterOpening.objects.count(), 1)

    def test_a_ticket_belonging_to_someone_else_is_refused(self):
        (other,) = make_users(1)
        ticket = BoosterTicket.objects.create(user=other, booster_key="base")

        with self.assertRaises(ShopError):
            open_ticket(self.user, ticket.pk)

        self.assertEqual(BoosterOpening.objects.count(), 0)


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

    def test_the_shop_opens_a_batch_from_the_page(self):
        Profile.objects.filter(user=self.user).update(points=2000)

        response = self.client.post(reverse("api_open_booster", args=["base"]), {"quantity": 5})

        payload = response.json()
        self.assertEqual(response.status_code, 200)
        self.assertEqual(payload["quantity"], 5)
        self.assertEqual(len(payload["cards"]), 25)
        self.assertEqual(payload["points_left"], 2000 - 5 * 150)

    def test_the_collection_marks_what_is_owned(self):
        card = PokemonCard.objects.filter(pokedex_id__lte=151).first()
        CollectionCard.objects.create(user=self.user, pokemon_card=card, copies=2)

        response = self.client.get(reverse("collection"))

        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.context["owned_count"], 1)
        self.assertContains(response, "×2")

    def test_the_collection_shows_one_season_at_a_time(self):
        # En saison 2, une carte se possède par impression : c'est le numéro de
        # la carte dans le set qui la désigne, pas l'espèce.
        card = PokemonCard.objects.get(pokedex_id=1)
        CollectionCard.objects.create(
            user=self.user,
            pokemon_card=card,
            season=SEASON_151,
            variant="1",
            rarity=COMMUNE,
        )

        first = self.client.get(reverse("collection"))
        second = self.client.get(reverse("collection"), {"saison": SEASON_151})

        self.assertEqual(first.context["owned_count"], 0)
        self.assertEqual(second.context["owned_count"], 1)
        self.assertEqual(second.context["season"].number, SEASON_151)

    def test_an_unknown_season_falls_back_on_the_first(self):
        response = self.client.get(reverse("collection"), {"saison": "neuf"})

        self.assertEqual(response.context["season"].number, SEASON_BASE)

    def test_the_shop_lists_the_boosters_won_in_quests(self):
        ticket = BoosterTicket.objects.create(user=self.user, booster_key="s151")

        response = self.client.get(reverse("shop"))

        self.assertEqual([row["id"] for row in response.context["tickets"]], [ticket.pk])
        self.assertContains(response, "Tes boosters de quête")

    def test_an_opened_ticket_leaves_the_shop(self):
        ticket = BoosterTicket.objects.create(user=self.user, booster_key="s151")

        response = self.client.post(reverse("api_open_ticket", args=[ticket.pk]))

        payload = response.json()
        self.assertEqual(response.status_code, 200)
        self.assertEqual(payload["season"], SEASON_151)
        self.assertEqual(payload["tickets_left"], 0)
        self.assertEqual(self.client.get(reverse("shop")).context["tickets"], [])

    def test_opening_someone_elses_ticket_is_refused(self):
        (other,) = make_users(1)
        ticket = BoosterTicket.objects.create(user=other, booster_key="base")

        response = self.client.post(reverse("api_open_ticket", args=[ticket.pk]))

        self.assertEqual(response.status_code, 400)
        self.assertEqual(BoosterOpening.objects.count(), 0)

    def test_claiming_a_quest_from_the_page_credits_the_points(self):
        for _ in range(5):
            record_event(self.user, EVENT_SILHOUETTE_FOUND)

        response = self.client.post(reverse("claim_quest", args=["daily_silhouettes"]))

        self.user.profile.refresh_from_db()
        self.assertRedirects(response, reverse("quests"))
        self.assertEqual(self.user.profile.points, QUESTS_BY_KEY["daily_silhouettes"].reward)

    def test_claiming_a_weekly_quest_announces_the_booster(self):
        for _ in range(5):
            record_event(self.user, EVENT_GAME_WON)

        response = self.client.post(reverse("claim_quest", args=["weekly_champion"]), follow=True)

        self.assertContains(response, BOOSTERS_BY_KEY["s151_ultra"].label)
        self.assertEqual(BoosterTicket.objects.filter(user=self.user).count(), 1)


class SeasonCatalogueTests(TestCase):
    """Les catalogues committés : visuels de la saison 1, impressions de la 2."""

    def test_the_base_set_has_a_visual_for_every_pokemon(self):
        urls = {get_tcg_image_url(pokedex_id, SEASON_BASE) for pokedex_id in range(1, 152)}

        self.assertNotIn(None, urls)
        self.assertEqual(len(urls), 151)

    def test_the_151_set_covers_every_pokemon_and_every_rarity(self):
        cards = prints_of(SEASON_151)

        self.assertEqual({card.dex_id for card in cards}, set(range(1, 152)))
        # Les huit raretés du set sont représentées, et aucune autre.
        self.assertEqual(
            {card.rarity for card in cards},
            {
                COMMUNE,
                "PEU_COMMUNE",
                RARE,
                DOUBLE_RARE,
                "ILLUSTRATION_RARE",
                ULTRA_RARE,
                ILLUSTRATION_SPECIALE,
                HYPER_RARE,
            },
        )

    def test_every_print_has_a_distinct_number_and_visual(self):
        cards = prints_of(SEASON_151)

        self.assertEqual(len({card.local_id for card in cards}), len(cards))
        self.assertEqual(len({card.image for card in cards}), len(cards))

    def test_a_pokemon_can_exist_in_several_rarities(self):
        charizard = [card for card in prints_of(SEASON_151) if card.dex_id == 6]

        rarities = {card.rarity for card in charizard}
        self.assertIn(DOUBLE_RARE, rarities)
        self.assertIn(ULTRA_RARE, rarities)
        self.assertGreater(len(charizard), 1)

    def test_each_rarity_has_its_own_reveal(self):
        reveals = [rarity.reveal for rarity in RARITIES_BY_KEY.values()]

        # Aucune rareté ne partage sa mise en scène avec une autre : c'est ce
        # qui permet de reconnaître ce qu'on vient de tirer.
        self.assertEqual(len(reveals), len(set(reveals)))

    def test_every_odds_table_adds_up_and_names_known_rarities(self):
        for booster in BOOSTERS:
            with self.subTest(booster=booster.key):
                total = sum(odds for _, odds in booster.odds)

                self.assertAlmostEqual(total, 1.0, places=6)
                for rarity, _ in booster.odds:
                    self.assertIn(rarity, RARITIES_BY_KEY)
