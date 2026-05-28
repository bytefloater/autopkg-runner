from django.contrib import admin

from webapp.models import Schedule, Run, StageExecution, LogEntry, RecipeResult, Task


@admin.register(Schedule)
class ScheduleAdmin(admin.ModelAdmin):
    list_display = ['__str__', 'enabled', 'minute', 'hour', 'day_of_week']


class StageExecutionInline(admin.TabularInline):
    model = StageExecution
    extra = 0
    readonly_fields = ['name', 'status', 'order', 'started_at', 'completed_at']


class LogEntryInline(admin.TabularInline):
    model = LogEntry
    extra = 0
    readonly_fields = ['timestamp', 'level', 'stage_name', 'message']


@admin.register(Run)
class RunAdmin(admin.ModelAdmin):
    list_display  = ['id', 'status', 'triggered_by', 'started_at', 'completed_at']
    list_filter   = ['status', 'triggered_by']
    readonly_fields = ['id', 'started_at', 'completed_at', 'config_snapshot']
    inlines       = [StageExecutionInline]


@admin.register(LogEntry)
class LogEntryAdmin(admin.ModelAdmin):
    list_display = ['run', 'timestamp', 'level', 'stage_name', 'message']
    list_filter  = ['level', 'stage_name']
    search_fields = ['message']


@admin.register(RecipeResult)
class RecipeResultAdmin(admin.ModelAdmin):
    list_display = ['run', 'result_type']
    list_filter  = ['result_type']


@admin.register(Task)
class TaskAdmin(admin.ModelAdmin):
    list_display  = ['id', 'task_type', 'status', 'run', 'created_at', 'completed_at']
    list_filter   = ['task_type', 'status']
    readonly_fields = ['id', 'created_at', 'completed_at']
