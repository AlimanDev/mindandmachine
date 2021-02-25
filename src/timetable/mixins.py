from django.contrib.auth.mixins import AccessMixin

class SuperuserRequiredMixin(AccessMixin):
    """
    Mixin allows you to require a user with `is_superuser` set to True.
    """
    def dispatch(self, request, *args, **kwargs):
        if not request.user.is_superuser:
            return self.handle_no_permission(request)

        return super(SuperuserRequiredMixin, self).dispatch(
            request, *args, **kwargs)
