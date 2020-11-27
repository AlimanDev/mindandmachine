from rest_framework import serializers


class RoundingDecimalField(serializers.DecimalField):
    """
    Класс DecimalField с отключенной проверкой точности.
    Чтобы можно было принимать числа с большим количество знаков после запятой
    (при сохранении они будут округляться до нужной точности)
    """
    def validate_precision(self, value):
        return value
