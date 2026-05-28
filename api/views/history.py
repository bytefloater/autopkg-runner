from datetime import date

from rest_framework.response import Response
from rest_framework.views import APIView


class GetRunDataView(APIView):
    def get(self, request):
        from webapp.models import Run
        from api.serializers import RunDetailSerializer

        uuid_val = request.query_params.get('uuid')
        if not uuid_val:
            return Response({'error': 'uuid parameter is required'}, status=400)

        try:
            run = Run.objects.get(id=uuid_val)
        except (Run.DoesNotExist, ValueError):
            return Response({'error': 'Run not found'}, status=404)

        return Response(RunDetailSerializer(run).data)


class ListRunsView(APIView):
    def get(self, request):
        from webapp.models import Run
        from api.serializers import RunSerializer

        qs = Run.objects.order_by('-started_at')

        start_str = request.query_params.get('start_date')
        end_str = request.query_params.get('end_date')

        try:
            start = date.fromisoformat(start_str) if start_str else None
        except ValueError:
            return Response(
                {'error': f'Invalid start_date "{start_str}". Use YYYY-MM-DD.'}, status=400
            )
        try:
            end = date.fromisoformat(end_str) if end_str else None
        except ValueError:
            return Response(
                {'error': f'Invalid end_date "{end_str}". Use YYYY-MM-DD.'}, status=400
            )

        if start and end:
            qs = qs.filter(started_at__date__gte=start, started_at__date__lte=end)
        elif start:
            qs = qs.filter(started_at__date__gte=start)
        elif end:
            qs = qs.filter(started_at__date__lte=end)

        return Response(RunSerializer(qs, many=True).data)
