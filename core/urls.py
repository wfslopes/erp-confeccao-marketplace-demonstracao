from django.contrib import admin
from django.contrib.auth import views as auth_views
from django.urls import include, path
from fabrica import views  # <-- IMPORTANTE: Importa direto do app fabrica

urlpatterns = [
    path('admin/', admin.site.urls),
    path('categorias/cadastrar/', views.categorias_view, name='cadastrar_categoria'),
    path(
        'login/',
        auth_views.LoginView.as_view(template_name='fabrica/login.html'),
        name='login',
    ),
    path(
        'logout/',
        auth_views.LogoutView.as_view(next_page='login'),
        name='logout',
    ),
    path('', include('fabrica.urls')),  # Inclui as rotas do app fabrica
]