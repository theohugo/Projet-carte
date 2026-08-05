from django.urls import include, path

urlpatterns = [
    path("accounts/", include("django.contrib.auth.urls")),
    path("qui-est-ce/", include(("guesswho.urls", "guesswho"), namespace="guesswho")),
    path(
        "qui-est-ce-pokemon/",
        include(("silhouette.urls", "silhouette"), namespace="silhouette"),
    ),
    path(
        "pictionary/",
        include(("pictionary.urls", "pictionary"), namespace="pictionary"),
    ),
    path(
        "metamorph/",
        include(("metamorph.urls", "metamorph"), namespace="metamorph"),
    ),
    path("rocket/", include(("rocket.urls", "rocket"), namespace="rocket")),
    path("islands/", include(("islands.urls", "islands"), namespace="islands")),
    path(
        "starterrace/",
        include(("starterrace.urls", "starterrace"), namespace="starterrace"),
    ),
    path("", include("game.urls")),
]
