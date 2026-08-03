from django.contrib import admin

from game.models import Game, GameCard, GamePlayer, MoveLog, PokemonCard, PokemonType, Profile


@admin.register(PokemonType)
class PokemonTypeAdmin(admin.ModelAdmin):
    list_display = ("name_fr", "name_en", "slug")
    search_fields = ("name_fr", "name_en", "slug")


@admin.register(PokemonCard)
class PokemonCardAdmin(admin.ModelAdmin):
    list_display = (
        "pokedex_id",
        "name_fr",
        "name_en",
        "primary_type",
        "secondary_type",
        "action",
        "is_legendary",
        "in_current_deck",
    )
    list_filter = ("primary_type", "secondary_type", "action", "is_legendary", "in_current_deck")
    search_fields = ("name_fr", "name_en", "slug")


class GamePlayerInline(admin.TabularInline):
    model = GamePlayer
    extra = 0


@admin.register(Game)
class GameAdmin(admin.ModelAdmin):
    list_display = ("id", "status", "created_by", "max_players", "created_at")
    list_filter = ("status",)
    inlines = [GamePlayerInline]


@admin.register(MoveLog)
class MoveLogAdmin(admin.ModelAdmin):
    list_display = ("game", "player", "move_type", "created_at")
    list_filter = ("move_type",)


@admin.register(Profile)
class ProfileAdmin(admin.ModelAdmin):
    list_display = ("user", "total_games_played", "total_games_won")


admin.site.register(GameCard)
