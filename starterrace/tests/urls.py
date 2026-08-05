from django.urls import include, path

urlpatterns = [
    path("accounts/", include("django.contrib.auth.urls")),
    path("course-des-starters/", include(("starterrace.urls", "starterrace"), namespace="starterrace")),
    path("qui-est-ce/", include(("guesswho.urls", "guesswho"), namespace="guesswho")),
    path("qui-est-ce-pokemon/", include(("silhouette.urls", "silhouette"), namespace="silhouette")),
    path("pictionary/", include(("pictionary.urls", "pictionary"), namespace="pictionary")),
    path("metamorph-mystere/", include(("metamorph.urls", "metamorph"), namespace="metamorph")),
    path("infiltration-rocket/", include(("rocket.urls", "rocket"), namespace="rocket")),
    path("bataille-des-iles/", include(("islands.urls", "islands"), namespace="islands")),
    path("", include("game.urls")),
]
