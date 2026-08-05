from django.contrib import admin

from .models import RocketGame, RocketMessage, RocketNightAction, RocketPlayer, RocketVote


class RocketPlayerInline(admin.TabularInline):
    model = RocketPlayer
    extra = 0


@admin.register(RocketGame)
class RocketGameAdmin(admin.ModelAdmin):
    list_display = ("id", "status", "round_number", "created_by", "created_at")
    list_filter = ("status", "winner_side")
    inlines = (RocketPlayerInline,)


admin.site.register(RocketNightAction)
admin.site.register(RocketVote)
admin.site.register(RocketMessage)
