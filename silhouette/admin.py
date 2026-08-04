from django.contrib import admin

from silhouette.models import SilhouetteGame, SilhouetteGuess, SilhouettePlayer, SilhouetteRound


class SilhouettePlayerInline(admin.TabularInline):
    model = SilhouettePlayer
    extra = 0


@admin.register(SilhouetteGame)
class SilhouetteGameAdmin(admin.ModelAdmin):
    list_display = ("id", "status", "created_by", "round_count", "created_at")
    list_filter = ("status", "round_count")
    inlines = [SilhouettePlayerInline]


@admin.register(SilhouetteRound)
class SilhouetteRoundAdmin(admin.ModelAdmin):
    list_display = ("game", "number", "pokemon_card", "started_at", "revealed_at")
    list_filter = ("game",)


@admin.register(SilhouetteGuess)
class SilhouetteGuessAdmin(admin.ModelAdmin):
    list_display = ("round", "player", "text", "is_correct", "points", "elapsed_ms")
    list_filter = ("is_correct",)
