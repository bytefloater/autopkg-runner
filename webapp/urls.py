from django.contrib.auth.views import LogoutView
from django.urls import path
from django.views.generic import RedirectView

from webapp.views import (
    dashboard, runs, schedule, config, api_tokens, users, pwa, account,
    notifications, share, about, recipes, filebrowser,
)
from webapp.views.config import LogLevelPickerView

urlpatterns = [
    path('', RedirectView.as_view(url='/dashboard/'), name='home'),

    # -- Core views ------------------------------------------------------------
    path('dashboard/', dashboard.DashboardView.as_view(), name='dashboard'),
    path('runs/',         runs.RunListView.as_view(),   name='run-list'),
    path('runs/trigger/', runs.TriggerRunView.as_view(), name='trigger-run'),
    path('runs/delete/',  runs.RunDeleteView.as_view(),  name='run-delete'),
    path('runs/<uuid:run_id>/cancel/', runs.RunCancelView.as_view(), name='run-cancel'),
    path('runs/<uuid:run_id>/',        runs.RunDetailView.as_view(), name='run-detail'),
    path('runs/<uuid:run_id>/stream/', runs.run_stream,               name='run-stream'),
    path('schedule/', schedule.ScheduleView.as_view(), name='schedule'),
    path('about/',    about.AboutView.as_view(),        name='about'),

    # -- Configuration root ----------------------------------------------------
    path('config/', config.ConfigRootView.as_view(), name='config'),

    # -- Configuration sections ------------------------------------------------
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

    # -- Notifications ---------------------------------------------------------
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
    path('config/notifications/<uuid:pk>/test/',
         notifications.NotifierTestView.as_view(), name='notifier-test'),
    path('config/notifications/settings/',
         notifications.NotificationSettingsView.as_view(), name='notification-settings'),
    path('config/notifications/vapid-key/',
         notifications.WebPushVapidKeyView.as_view(), name='webpush-vapid-key'),
    path('config/notifications/<uuid:pk>/subscribe/',
         notifications.WebPushSubscribeView.as_view(), name='webpush-subscribe'),
    path('config/notifications/<uuid:pk>/unsubscribe/<int:sub_id>/',
         notifications.WebPushUnsubscribeView.as_view(), name='webpush-unsubscribe'),
    path('config/logging/level/',
         LogLevelPickerView.as_view(), name='config-logging-level'),

    # -- Recipes ---------------------------------------------------------------
    path('recipes/', RedirectView.as_view(url='/recipes/repos/'), name='recipes'),
    path('recipes/repos/',
         recipes.ReposView.as_view(), name='recipes-repos'),
    path('recipes/repos/add/',
         recipes.RepoAddView.as_view(), name='recipes-repo-add'),
    path('recipes/repos/delete/',
         recipes.RepoDeleteView.as_view(), name='recipes-repo-delete'),
    path('recipes/repos/update/',
         recipes.RepoUpdateView.as_view(), name='recipes-repo-update'),
    path('recipes/list/',
         recipes.RecipeListView.as_view(), name='recipes-list'),
    path('recipes/list/data/',
         recipes.RecipeDataView.as_view(), name='recipes-list-data'),
    path('recipes/list/cache-reset/',
         recipes.RecipeCacheResetView.as_view(), name='recipes-cache-reset'),
    path('recipes/overrides/create/',
         recipes.OverrideCreateView.as_view(), name='recipes-override-create'),
    path('recipes/overrides/<path:fname>/edit/',
         recipes.OverrideEditView.as_view(), name='recipes-override-edit'),
    path('recipes/overrides/<path:fname>/delete/',
         recipes.OverrideDeleteView.as_view(), name='recipes-override-delete'),

    # -- File browser API (used by path pickers in config pages) ---------------
    path('api/browse/',       filebrowser.BrowseView.as_view(), name='api-browse'),
    path('api/browse/mkdir/', filebrowser.MkdirView.as_view(),  name='api-browse-mkdir'),

    # -- Other -----------------------------------------------------------------
    path('api-tokens/', api_tokens.ApiTokensView.as_view(), name='api-tokens'),
    path('users/',      users.UsersView.as_view(),          name='users'),
    path('users/<int:pk>/', users.UserEditView.as_view(),   name='user-edit'),
    path('account/change-password/', account.ChangePasswordView.as_view(), name='change-password'),
    # -- Share links (unauthenticated) -----------------------------------------
    path('share/<str:token>/', share.RunShareView.as_view(), name='run-share'),

    path('favicon.ico',   RedirectView.as_view(url='/static/logos/favicon.ico', permanent=True), name='favicon'),
    path('manifest.json', pwa.ManifestView.as_view(),        name='manifest'),
    path('sw.js',         pwa.ServiceWorkerView.as_view(),   name='service-worker'),
    path('login/',  account.MobileAwareLoginView.as_view(), name='login'),
    path('logout/', LogoutView.as_view(), name='logout'),
]
