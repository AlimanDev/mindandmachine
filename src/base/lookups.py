from django.db.models import Field
from django.db.models.lookups import GreaterThanOrEqual, LessThanOrEqual


class BaseOrIsNullMixin:
    connection_operator = None

    def as_sql(self, compiler, connection):
        lhs_sql, params = self.process_lhs(compiler, connection)
        rhs_sql, rhs_params = self.process_rhs(compiler, connection)
        params.extend(rhs_params)
        rhs_sql = self.get_rhs_op(connection, rhs_sql)
        return '(%s %s OR %s IS NULL)' % (lhs_sql, rhs_sql, lhs_sql), params

    def get_rhs_op(self, connection, rhs):
        return connection.operators[self.connection_operator] % rhs


class GteOrIsNullMixin(BaseOrIsNullMixin):
    connection_operator = 'gte'


class LteOrIsNullMixin(BaseOrIsNullMixin):
    connection_operator = 'lte'


@Field.register_lookup
class GreaterThanOrEqualOrIsNull(GteOrIsNullMixin, GreaterThanOrEqual):
    lookup_name = 'gte_or_isnull'


@Field.register_lookup
class LessThanOrEqualOrIsNull(LteOrIsNullMixin, LessThanOrEqual):
    lookup_name = 'lte_or_isnull'
