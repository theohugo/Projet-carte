"""Politique déterministe des joueurs IA, sans dépendance externe."""

from collections import Counter
from dataclasses import dataclass
from typing import TYPE_CHECKING, Literal

from game.models import GameCard, PokemonCard
from game.tcg_types import TCG_TYPES

if TYPE_CHECKING:
    from game.game_engine import GameEngine
    from game.models import GamePlayer


@dataclass(frozen=True, slots=True)
class BotDecision:
    kind: Literal["play", "draw"]
    card_id: int | None = None
    declared_tcg_type: str = ""


ACTION_PRIORITY = {
    PokemonCard.Action.DRAW_TWO: 0,
    PokemonCard.Action.REVERSE: 1,
    PokemonCard.Action.SHIELD: 2,
    PokemonCard.Action.NORMAL: 3,
    PokemonCard.Action.DRAW_FOUR: 4,
}


def _best_declared_tcg_type(remaining_cards: list[GameCard]) -> str:
    counts: Counter[str] = Counter()
    for game_card in remaining_cards:
        counts.update([game_card.pokemon_card.tcg_type])

    type_order = {tcg_type.slug: index for index, tcg_type in enumerate(TCG_TYPES)}
    if not counts:
        return TCG_TYPES[0].slug
    return min(counts, key=lambda slug: (-counts[slug], type_order[slug]))


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
            engine.requires_tcg_type_choice(game_card.pokemon_card),
            ACTION_PRIORITY[game_card.pokemon_card.action],
            game_card.order_index,
            game_card.id,
        ),
    )
    declared_tcg_type = ""
    if engine.requires_tcg_type_choice(selected.pokemon_card):
        declared_tcg_type = _best_declared_tcg_type(
            [game_card for game_card in hand if game_card.pk != selected.pk]
        )
    return BotDecision(
        kind="play",
        card_id=selected.id,
        declared_tcg_type=declared_tcg_type,
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
    engine.play_card(bot, game_card, declared_tcg_type=decision.declared_tcg_type)
    return decision
