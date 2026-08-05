"""
URL configuration for pokecarte project.

The `urlpatterns` list routes URLs to views. For more information please see:
    https://docs.djangoproject.com/en/6.0/topics/http/urls/
Examples:
Function views
    1. Add an import:  from my_app import views
    2. Add a URL to urlpatterns:  path('', views.home, name='home')
Class-based views
    1. Add an import:  from other_app.views import Home
    2. Add a URL to urlpatterns:  path('', Home.as_view(), name='home')
Including another URLconf
    1. Import the include() function: from django.urls import include, path
    2. Add a URL to urlpatterns:  path('blog/', include('blog.urls'))
"""

from django.conf import settings
from django.conf.urls.static import static
from django.contrib import admin
from django.urls import include, path

from . import seo

urlpatterns = [
    path("robots.txt", seo.robots_txt, name="robots_txt"),
    path("sitemap.xml", seo.sitemap_xml, name="sitemap_xml"),
    path("admin/", admin.site.urls),
    path("accounts/", include("django.contrib.auth.urls")),
    path("qui-est-ce/", include("guesswho.urls")),
    path("qui-est-ce-pokemon/", include("silhouette.urls")),
    path("pictionary/", include("pictionary.urls")),
    path("metamorph-mystere/", include("metamorph.urls")),
    path("infiltration-rocket/", include("rocket.urls")),
    path("bataille-des-iles/", include("islands.urls")),
    path("course-des-starters/", include("starterrace.urls")),
    path("", include("game.urls")),
]

if settings.DEBUG:
    urlpatterns += static(
        settings.MEDIA_URL,
        document_root=settings.MEDIA_ROOT,
    )
