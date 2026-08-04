from django.contrib import admin

from pictionary.models import PictionaryGame, PictionaryGuess, PictionaryPlayer, PictionaryRound


class PictionaryPlayerInline(admin.TabularInline):
    model = PictionaryPlayer
    extra = 0


@admin.register(PictionaryGame)
class PictionaryGameAdmin(admin.ModelAdmin):
    list_display = ("id", "status", "created_by", "round_count", "created_at")
    list_filter = ("status", "round_count")
    inlines = [PictionaryPlayerInline]


@admin.register(PictionaryRound)
class PictionaryRoundAdmin(admin.ModelAdmin):
    list_display = ("game", "number", "drawer", "pokemon_card", "started_at", "ended_at")


@admin.register(PictionaryGuess)
class PictionaryGuessAdmin(admin.ModelAdmin):
    list_display = ("round", "player", "text", "is_correct", "points", "elapsed_ms")
    list_filter = ("is_correct",)
