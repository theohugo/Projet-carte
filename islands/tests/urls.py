from django.contrib import admin
from django.urls import include, path

urlpatterns = [
    path("admin/", admin.site.urls),
    path("accounts/", include("django.contrib.auth.urls")),
    path("qui-est-ce/", include("guesswho.urls")),
    path("qui-est-ce-pokemon/", include("silhouette.urls")),
    path("pictionary/", include("pictionary.urls")),
    path("bataille-des-iles/", include(("islands.urls", "islands"), namespace="islands")),
    path("", include("game.urls")),
]
