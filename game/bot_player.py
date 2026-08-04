"""Politique déterministe des joueurs IA, sans dépendance externe."""

from collections import Counter
from dataclasses import dataclass
from typing import TYPE_CHECKING, Literal

from game.deck_builder import species_type_slugs
from game.models import GameCard

if TYPE_CHECKING:
    from game.game_engine import GameEngine
    from game.models import GamePlayer


@dataclass(frozen=True, slots=True)
class BotDecision:
    kind: Literal["play", "draw"]
    card_id: int | None = None
    declared_type: str = ""


ACTION_PRIORITY = {
    GameCard.Action.DRAW_TWO: 0,
    GameCard.Action.REVERSE: 1,
    GameCard.Action.SHIELD: 2,
    GameCard.Action.NORMAL: 3,
    GameCard.Action.DRAW_FOUR: 4,
}


def _best_declared_type(remaining_cards: list[GameCard], game_type_slugs: list[str]) -> str:
    """Le type de la partie le mieux représenté dans la main restante."""

    counts: Counter[str] = Counter()
    for game_card in remaining_cards:
        counts.update(slug for slug in species_type_slugs(game_card.pokemon_card))

    type_order = {slug: index for index, slug in enumerate(game_type_slugs)}
    if not game_type_slugs:
        return ""
    return min(game_type_slugs, key=lambda slug: (-counts[slug], type_order[slug]))


def choose_bot_move(engine: "GameEngine", bot: "GamePlayer") -> BotDecision:
    """Choisit un coup reproductible en réutilisant les validations du moteur."""
    if not bot.is_bot:
        raise ValueError("Le joueur courant n'est pas une IA.")

    hand = list(
        GameCard.objects.select_related("pokemon_card__primary_type", "pokemon_card__secondary_type")
        .filter(game=engine.game, location=GameCard.Location.MAIN, owner=bot)
        .order_by("order_index", "id")
    )
    playable = [game_card for game_card in hand if engine.is_move_valid(bot, game_card)[0]]
    if not playable:
        return BotDecision(kind="draw")

    selected = min(
        playable,
        key=lambda game_card: (
            engine.requires_type_choice(game_card),
            ACTION_PRIORITY[game_card.action],
            game_card.order_index,
            game_card.id,
        ),
    )
    declared_type = ""
    if engine.requires_type_choice(selected):
        declared_type = _best_declared_type(
            [game_card for game_card in hand if game_card.pk != selected.pk],
            [pokemon_type.slug for pokemon_type in engine.get_selected_types()],
        )
    return BotDecision(
        kind="play",
        card_id=selected.id,
        declared_type=declared_type,
    )


def perform_bot_turn(engine: "GameEngine") -> BotDecision:
    bot = engine.get_current_player()
    decision = choose_bot_move(engine, bot)
    if decision.kind == "draw":
        engine.draw_card(bot)
        return decision

    game_card = GameCard.objects.select_related(
        "pokemon_card__primary_type", "pokemon_card__secondary_type"
    ).get(pk=decision.card_id, game=engine.game)
    engine.play_card(bot, game_card, declared_type_slug=decision.declared_type)
    return decision
