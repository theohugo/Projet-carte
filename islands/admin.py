from django.contrib import admin

from .models import Formation, IslandGame, IslandPlayer, Shot


class FormationInline(admin.TabularInline):
    model = Formation
    extra = 0
    readonly_fields = ("pokemon_card", "slot", "size")


@admin.register(IslandGame)
class IslandGameAdmin(admin.ModelAdmin):
    list_display = ("id", "status", "created_by", "turn_revision", "created_at")
    list_filter = ("status",)
    search_fields = ("id", "created_by__username")


@admin.register(IslandPlayer)
class IslandPlayerAdmin(admin.ModelAdmin):
    list_display = ("game", "display_name", "user", "bot_name", "turn_order", "is_ready")
    list_filter = ("is_ready",)
    inlines = (FormationInline,)


@admin.register(Shot)
class ShotAdmin(admin.ModelAdmin):
    list_display = ("game", "shooter", "target", "row", "col", "result")
    list_filter = ("result",)
