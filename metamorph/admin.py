from django.contrib import admin

from .models import MetamorphCard, MetamorphGame, MetamorphMove, MetamorphPlayer


class MetamorphPlayerInline(admin.TabularInline):
    model = MetamorphPlayer
    extra = 0
    readonly_fields = ("joined_at", "finished_at")


@admin.register(MetamorphGame)
class MetamorphGameAdmin(admin.ModelAdmin):
    list_display = ("id", "status", "created_by", "current_turn", "turn_revision", "created_at")
    list_filter = ("status", "created_at")
    search_fields = ("id", "created_by__username")
    inlines = (MetamorphPlayerInline,)


@admin.register(MetamorphCard)
class MetamorphCardAdmin(admin.ModelAdmin):
    list_display = ("id", "game", "pokemon_card", "owner", "is_ditto", "hand_position")
    list_filter = ("is_ditto", "paired_at")
    search_fields = ("game__id", "pokemon_card__name_fr", "owner__user__username")


@admin.register(MetamorphMove)
class MetamorphMoveAdmin(admin.ModelAdmin):
    list_display = ("game", "sequence", "actor", "source", "formed_pair", "created_at")
    list_filter = ("formed_pair",)
    search_fields = ("game__id", "actor__user__username", "source__user__username")
