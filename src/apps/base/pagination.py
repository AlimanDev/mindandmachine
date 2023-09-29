from rest_framework.pagination import LimitOffsetPagination
from distutils.util import strtobool

class LimitOffsetPaginationWithOptionalCount(LimitOffsetPagination):
    def paginate_queryset(self, queryset, request, view=None):
        return_total_count = strtobool(request.query_params.get('return_total_count', 'true'))
        self.limit = self.get_limit(request)
        if self.limit is None:
            return None
        self.offset = self.get_offset(request)
        data = list(queryset[self.offset:self.offset + self.limit])
        self.count = len(data)
        if return_total_count:
            self.count = self.get_count(queryset)
        
        self.request = request
        if self.count > self.limit and self.template is not None and return_total_count:
            self.display_page_controls = True

        if self.count == 0 or (self.offset > self.count and return_total_count):
            return []
        return data
