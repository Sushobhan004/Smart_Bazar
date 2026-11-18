from django.urls import path
from apps.sync.views import SyncUploadView

urlpatterns = [
    path('upload/', SyncUploadView.as_view(), name='sync-upload'),
]

