from .sso import ensure_sso_user
from .tenancy import resolve_request_tenant


class HeaderSSOAuthMiddleware:
    def __init__(self, get_response):
        self.get_response = get_response

    def __call__(self, request):
        from django.conf import settings
        if not getattr(settings, "SSO_ENABLED", True):
            return self.get_response(request)
        try:
            ensure_sso_user(request)
        except Exception:
            pass
        return self.get_response(request)


class TenantMiddleware:
    def __init__(self, get_response):
        self.get_response = get_response

    def __call__(self, request):
        try:
            resolve_request_tenant(request)
        except Exception:
            request.tenant = None
            request.tenant_membership = None
        return self.get_response(request)
