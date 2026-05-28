from rest_framework import serializers

from webapp.models import Run, StageExecution, LogEntry, RecipeResult, Task


class StageExecutionSerializer(serializers.ModelSerializer):
    class Meta:
        model = StageExecution
        fields = ['name', 'status', 'order', 'started_at', 'completed_at']


class LogEntrySerializer(serializers.ModelSerializer):
    class Meta:
        model = LogEntry
        fields = ['timestamp', 'level', 'stage_name', 'message']


class RecipeResultSerializer(serializers.ModelSerializer):
    class Meta:
        model = RecipeResult
        fields = ['result_type', 'data']


class RunSerializer(serializers.ModelSerializer):
    duration_seconds = serializers.SerializerMethodField()

    class Meta:
        model = Run
        fields = ['id', 'status', 'triggered_by', 'started_at', 'completed_at', 'duration_seconds']

    def get_duration_seconds(self, obj):
        if obj.started_at and obj.completed_at:
            return (obj.completed_at - obj.started_at).total_seconds()
        return None


class RunDetailSerializer(RunSerializer):
    stages = StageExecutionSerializer(source='stage_executions', many=True)
    logs = LogEntrySerializer(source='log_entries', many=True)
    results = RecipeResultSerializer(source='recipe_results', many=True)

    class Meta(RunSerializer.Meta):
        fields = RunSerializer.Meta.fields + ['config_snapshot', 'stages', 'logs', 'results']


class TaskSerializer(serializers.ModelSerializer):
    run_uuid = serializers.SerializerMethodField()

    class Meta:
        model = Task
        fields = ['id', 'task_type', 'status', 'run_uuid', 'created_at', 'completed_at', 'error']

    def get_run_uuid(self, obj):
        return str(obj.run_id) if obj.run_id else None
