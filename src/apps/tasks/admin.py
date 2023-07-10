from django.contrib import admin

from .models import Task


@admin.register(Task)
class TaskAdmin(admin.ModelAdmin):
    raw_id_fields = (
        'operation_type',
        'employee',
    )
    save_as = True

