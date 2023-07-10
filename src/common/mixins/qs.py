from django.db.models import Case, When, BooleanField


class AnnotateValueEqualityQSMixin:
    def annotate_value_equality(self, annotate_name, field_name, value):
        return self.annotate(**{annotate_name: Case(
            When(**{field_name: value}, then=True),
            default=False, output_field=BooleanField()
        )})
