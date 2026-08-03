from django.urls import include, path

urlpatterns = [
    path("accounts/", include("django.contrib.auth.urls")),
    path("guesswho/", include(("guesswho.urls", "guesswho"), namespace="guesswho")),
    path("", include("game.urls")),
]
