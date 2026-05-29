from django.contrib.auth.views import LogoutView
from django.urls import path
from django.views.generic import RedirectView

from webapp.views import (
    dashboard, runs, schedule, config, api_tokens, users, pwa, account,
    notifications,
)

urlpatterns = [
    path('', RedirectView.as_view(url='/dashboard/'), name='home'),

    # ── Core views ────────────────────────────────────────────────────────────
    path('dashboard/', dashboard.DashboardView.as_view(), name='dashboard'),
    path('runs/',      runs.RunListView.as_view(),        name='run-list'),
    path('runs/trigger/', runs.TriggerRunView.as_view(),  name='trigger-run'),
    path('runs/<uuid:run_id>/',        runs.RunDetailView.as_view(), name='run-detail'),
    path('runs/<uuid:run_id>/stream/', runs.run_stream,               name='run-stream'),
    path('schedule/', schedule.ScheduleView.as_view(), name='schedule'),

    # ── Configuration root ────────────────────────────────────────────────────
    path('config/', config.ConfigRootView.as_view(), name='config'),

    # ── Configuration sections ────────────────────────────────────────────────
    path('config/autopkg/',
         config.ConfigSectionView.as_view(section='autopkg'),    name='config-autopkg'),
    path('config/workflow/',
         config.ConfigSectionView.as_view(section='workflow'),   name='config-workflow'),
    path('config/repository/',
         config.ConfigSectionView.as_view(section='repository'), name='config-repository'),
    path('config/gc/',
         config.ConfigSectionView.as_view(section='gc'),         name='config-gc'),
    path('config/logging/',
         config.ConfigSectionView.as_view(section='logging'),    name='config-logging'),
    path('config/ui/',
         config.ConfigSectionView.as_view(section='ui'),         name='config-ui'),

    # ── Notifications ─────────────────────────────────────────────────────────
    path('config/notifications/',
         notifications.NotificationsView.as_view(), name='config-notifications'),
    path('config/notifications/new/',
         notifications.NotifierEditView.as_view(),  name='notifier-new'),
    path('config/notifications/<uuid:pk>/',
         notifications.NotifierEditView.as_view(),  name='notifier-edit'),
    path('config/notifications/<uuid:pk>/delete/',
         notifications.NotifierDeleteView.as_view(), name='notifier-delete'),
    path('config/notifications/<uuid:pk>/toggle/',
         notifications.NotifierToggleView.as_view(), name='notifier-toggle'),

    # ── Other ─────────────────────────────────────────────────────────────────
    path('api-tokens/', api_tokens.ApiTokensView.as_view(), name='api-tokens'),
    path('users/',      users.UsersView.as_view(),          name='users'),
    path('account/change-password/', account.ChangePasswordView.as_view(), name='change-password'),
    path('favicon.ico',   RedirectView.as_view(url='/static/webapp/icons/favicon.ico', permanent=True), name='favicon'),
    path('manifest.json', pwa.ManifestView.as_view(),        name='manifest'),
    path('sw.js',         pwa.ServiceWorkerView.as_view(),   name='service-worker'),
    path('login/',  account.MobileAwareLoginView.as_view(), name='login'),
    path('logout/', LogoutView.as_view(), name='logout'),
]
