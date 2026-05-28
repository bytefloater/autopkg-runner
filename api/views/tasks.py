from rest_framework.response import Response
from rest_framework.views import APIView


class TriggerRunView(APIView):
    def post(self, request):
        from webapp.runner import trigger_manual_run
        task_id = trigger_manual_run(triggered_by='api')
        return Response({'task_uuid': str(task_id)}, status=202)


class TriggerDbCleanupView(APIView):
    def post(self, request):
        from webapp.runner import trigger_db_cleanup
        task_id = trigger_db_cleanup()
        return Response({'task_uuid': str(task_id)}, status=202)


class GetTaskStatusView(APIView):
    def get(self, request):
        from webapp.models import Task
        from api.serializers import TaskSerializer

        uuid_val = request.query_params.get('uuid')
        if not uuid_val:
            return Response({'error': 'uuid parameter is required'}, status=400)

        try:
            task = Task.objects.get(id=uuid_val)
        except (Task.DoesNotExist, ValueError):
            return Response({'error': 'Task not found'}, status=404)

        return Response(TaskSerializer(task).data)
