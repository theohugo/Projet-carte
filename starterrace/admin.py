from django.contrib import admin

from .models import Game, Move, Pawn, Player


class PawnInline(admin.TabularInline):
    model = Pawn
    extra = 0


@admin.register(Player)
class PlayerAdmin(admin.ModelAdmin):
    list_display = ("user", "game", "starter_card", "turn_order")
    list_select_related = ("user", "game", "starter_card")
    inlines = (PawnInline,)


@admin.register(Game)
class GameAdmin(admin.ModelAdmin):
    list_display = ("id", "status", "created_by", "current_turn", "winner", "created_at")
    list_filter = ("status",)
    search_fields = ("id", "created_by__username")


@admin.register(Move)
class MoveAdmin(admin.ModelAdmin):
    list_display = ("sequence", "game", "player", "roll", "was_pass", "created_at")
    list_filter = ("was_pass", "grants_extra_turn")
