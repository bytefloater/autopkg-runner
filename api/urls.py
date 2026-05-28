from django.urls import path

from api.views import auth, tasks, history

urlpatterns = [
    path('auth/get_token/', auth.GetTokenView.as_view(), name='api-get-token'),
    path('auth/check_token/', auth.CheckTokenView.as_view(), name='api-check-token'),
    path('tasks/trigger_run/', tasks.TriggerRunView.as_view(), name='api-trigger-run'),
    path('tasks/trigger_db_cleanup/', tasks.TriggerDbCleanupView.as_view(), name='api-trigger-cleanup'),
    path('tasks/get_task_status/', tasks.GetTaskStatusView.as_view(), name='api-task-status'),
    path('history/get_run_data/', history.GetRunDataView.as_view(), name='api-run-data'),
    path('history/list_runs/', history.ListRunsView.as_view(), name='api-list-runs'),
]
