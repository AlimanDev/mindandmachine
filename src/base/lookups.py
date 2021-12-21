from django.db.models import Field
from django.db.models.lookups import GreaterThanOrEqual, LessThanOrEqual


class OrIsNullMixin:
    def as_sql(self, compiler, connection):
        lhs_sql, params = self.process_lhs(compiler, connection)
        rhs_sql, rhs_params = self.process_rhs(compiler, connection)
        params.extend(rhs_params)
        rhs_sql = self.get_rhs_op(connection, rhs_sql)
        return '(%s %s OR %s IS NULL)' % (lhs_sql, rhs_sql, lhs_sql), params

    def get_rhs_op(self, connection, rhs):
        return connection.operators['gte'] % rhs


@Field.register_lookup
class GreaterThanOrEqualOrIsNull(OrIsNullMixin, GreaterThanOrEqual):
    lookup_name = 'gte_or_isnull'


@Field.register_lookup
class LessThanOrEqualOrIsNull(OrIsNullMixin, LessThanOrEqual):
    lookup_name = 'lte_or_isnull'
