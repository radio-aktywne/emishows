from django.conf import settings
from django.conf.urls.static import static
from django.urls import include, path
from rest_framework import routers

from emishows.app import views

router = routers.DefaultRouter()
router.register("shows", views.ShowViewSet)
router.register("events", views.EventViewSet)
router.register("timetable", views.TimetableViewSet, basename="Timetable")

urlpatterns = [
    path("", include(router.urls)),
    path("ics", views.ICSView.as_view()),
] + static(settings.STATIC_URL, document_root=settings.STATIC_ROOT)
