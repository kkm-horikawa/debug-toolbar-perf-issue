from django.contrib import admin
from django.urls import include, path

from demo import views

urlpatterns = [
    path('', views.index, name='index'),
    path('slow/', views.slow_query, name='slow_query'),
    path('admin/', admin.site.urls),
    path('__debug__/', include('debug_toolbar.urls')),
]
