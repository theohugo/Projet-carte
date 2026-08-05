from django.contrib import admin

from .models import (
    GuessWhoCandidateState,
    GuessWhoGame,
    GuessWhoPlayer,
    GuessWhoRosterCard,
    GuessWhoTurn,
)


class GuessWhoPlayerInline(admin.TabularInline):
    model = GuessWhoPlayer
    extra = 0
    readonly_fields = ("joined_at",)


@admin.register(GuessWhoGame)
class GuessWhoGameAdmin(admin.ModelAdmin):
    list_display = ("id", "play_mode", "status", "created_by", "turn_revision", "created_at")
    list_filter = ("play_mode", "status")
    search_fields = ("id", "created_by__username")
    readonly_fields = ("created_at", "started_at", "finished_at")
    inlines = (GuessWhoPlayerInline,)


@admin.register(GuessWhoRosterCard)
class GuessWhoRosterCardAdmin(admin.ModelAdmin):
    list_display = ("game", "position", "pokemon_card")
    list_filter = ("game",)


@admin.register(GuessWhoTurn)
class GuessWhoTurnAdmin(admin.ModelAdmin):
    list_display = ("game", "sequence", "kind", "actor", "answer", "is_correct")
    list_filter = ("kind", "answer", "is_correct")
    readonly_fields = ("created_at", "answered_at")


@admin.register(GuessWhoCandidateState)
class GuessWhoCandidateStateAdmin(admin.ModelAdmin):
    list_display = ("player", "roster_card", "is_eliminated", "updated_at")
    list_filter = ("is_eliminated",)
