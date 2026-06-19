from rest_framework.response import Response
from rest_framework.views import APIView

from api.permissions import CanTriggerRuns


class TriggerRunView(APIView):
    permission_classes = [CanTriggerRuns]
    def post(self, request):
        from webapp.runner import trigger_manual_run, RunAlreadyRunningError
        try:
            task_id = trigger_manual_run(triggered_by='api')
        except RunAlreadyRunningError:
            return Response({'error': 'A run is already in progress.'}, status=409)
        return Response({'task_uuid': str(task_id)}, status=202)


class TriggerDbCleanupView(APIView):
    permission_classes = [CanTriggerRuns]

    def post(self, request):
        from webapp.runner import trigger_db_cleanup
        task_id = trigger_db_cleanup()
        return Response({'task_uuid': str(task_id)}, status=202)


class GetTaskStatusView(APIView):
    permission_classes = [CanTriggerRuns]

    def get(self, request):
        from webapp.models import Task
        from api.serializers import TaskSerializer

        uuid_val = request.query_params.get('uuid')
        if not uuid_val:
            return Response({'error': 'uuid parameter is required'}, status=400)

        try:
            task = Task.objects.get(id=uuid_val)
        except Exception as exc:
            from django.core.exceptions import ValidationError as DjangoValidationError
            if not isinstance(exc, (Task.DoesNotExist, ValueError, DjangoValidationError)):
                raise
            return Response({'error': 'Task not found'}, status=404)

        return Response(TaskSerializer(task).data)
