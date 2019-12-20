

class WaitTimeInfo(models.Model):
    id = models.BigAutoField(primary_key=True)

    dt = models.DateField()
    work_type = models.ForeignKey(WorkType, on_delete=models.PROTECT)
    wait_time = models.PositiveIntegerField()
    proportion = models.FloatField()
    type = models.CharField(max_length=1, choices=PeriodDemand.FORECAST_TYPES)
