from functools import wraps
from typing import Any, Dict, Iterable, Optional

from django.conf import settings
from django.contrib.auth import get_user_model
from django.db import models
from django.http import HttpRequest, JsonResponse
from django.shortcuts import get_object_or_404

from .models import (
    TENANT_ROLE_ADMIN,
    TENANT_ROLE_AUDITOR,
    TENANT_ROLE_OPERATOR,
    TENANT_ROLE_OWNER,
    TENANT_ROLE_RESPONDER,
    TENANT_ROLE_VIEWER,
    Tenant,
    TenantAuditEvent,
    TenantMembership,
)


DEFAULT_TENANT_SLUG = "default-workspace"

ROLE_PERMISSIONS = {
    TENANT_ROLE_OWNER: {"*"},
    TENANT_ROLE_ADMIN: {
        "alerts.manage",
        "alerts.read",
        "audit.read",
        "cache.read",
        "cache.manage",
        "code_context.manage",
        "code_context.read",
        "fleet.manage",
        "fleet.read",
        "incidents.archive",
        "incidents.manage",
        "incidents.read",
        "integrations.manage",
        "integrations.read",
        "investigations.execute_diagnostic",
        "investigations.read",
        "lifecycle.read",
        "operations.read",
        "remediations.execute",
        "tenant.manage",
        "tenant.read",
    },
    TENANT_ROLE_OPERATOR: {
        "alerts.manage",
        "alerts.read",
        "cache.read",
        "code_context.read",
        "fleet.manage",
        "fleet.read",
        "incidents.archive",
        "incidents.manage",
        "incidents.read",
        "integrations.read",
        "investigations.execute_diagnostic",
        "investigations.read",
        "lifecycle.read",
        "operations.read",
        "remediations.execute",
        "tenant.read",
    },
    TENANT_ROLE_RESPONDER: {
        "alerts.read",
        "cache.read",
        "code_context.read",
        "fleet.read",
        "incidents.manage",
        "incidents.read",
        "integrations.read",
        "investigations.execute_diagnostic",
        "investigations.read",
        "lifecycle.read",
        "operations.read",
        "tenant.read",
    },
    TENANT_ROLE_VIEWER: {
        "alerts.read",
        "cache.read",
        "code_context.read",
        "fleet.read",
        "incidents.read",
        "integrations.read",
        "investigations.read",
        "lifecycle.read",
        "operations.read",
        "tenant.read",
    },
    TENANT_ROLE_AUDITOR: {
        "alerts.read",
        "audit.read",
        "cache.read",
        "fleet.read",
        "incidents.read",
        "integrations.read",
        "investigations.read",
        "lifecycle.read",
        "operations.read",
        "tenant.read",
    },
}


def get_default_tenant() -> Tenant:
    tenant, _ = Tenant.objects.get_or_create(
        slug=DEFAULT_TENANT_SLUG,
        defaults={
            "name": getattr(settings, "AIOPS_DEFAULT_TENANT_NAME", "Default Workspace"),
            "metadata_json": {"created_by": "runtime_default"},
        },
    )
    return tenant


def ensure_default_membership(user) -> Optional[TenantMembership]:
    if not getattr(user, "is_authenticated", False):
        return None
    membership = (
        TenantMembership.objects.select_related("tenant")
        .filter(user=user, is_active=True, tenant__is_active=True)
        .order_by("tenant__name")
        .first()
    )
    if membership:
        return membership
    role = TENANT_ROLE_OWNER if getattr(user, "is_superuser", False) else TENANT_ROLE_ADMIN
    return TenantMembership.objects.create(tenant=get_default_tenant(), user=user, role=role, is_active=True)


def user_memberships(user) -> Iterable[TenantMembership]:
    if not getattr(user, "is_authenticated", False):
        return []
    return (
        TenantMembership.objects.select_related("tenant")
        .filter(user=user, is_active=True, tenant__is_active=True)
        .order_by("tenant__name")
    )


def resolve_request_tenant(request: HttpRequest) -> Optional[TenantMembership]:
    if not getattr(request.user, "is_authenticated", False):
        request.tenant = None
        request.tenant_membership = None
        return None

    requested = (
        request.headers.get("X-Tenant-ID")
        or request.GET.get("tenant_id")
        or request.session.get("aiops_current_tenant_id")
        or ""
    )
    memberships = user_memberships(request.user)
    membership = None
    if requested:
        membership = memberships.filter(tenant__tenant_id=str(requested)).first()
    if membership is None:
        membership = memberships.first() or ensure_default_membership(request.user)
    if membership:
        request.session["aiops_current_tenant_id"] = str(membership.tenant.tenant_id)
        request.tenant = membership.tenant
        request.tenant_membership = membership
    else:
        request.tenant = None
        request.tenant_membership = None
    return membership


def permissions_for_role(role: str) -> set[str]:
    permissions = ROLE_PERMISSIONS.get(role, set())
    if "*" in permissions:
        expanded: set[str] = set()
        for role_permissions in ROLE_PERMISSIONS.values():
            expanded.update(role_permissions)
        expanded.discard("*")
        return expanded
    return set(permissions)


def all_known_permissions() -> set[str]:
    """Union of every permission string referenced by any built-in role."""
    expanded: set[str] = set()
    for role_permissions in ROLE_PERMISSIONS.values():
        for value in role_permissions:
            if value != "*":
                expanded.add(value)
    return expanded


def membership_permissions(membership) -> set[str]:
    """All permissions granted to a membership: role permissions + extra grants."""
    if not membership:
        return set()
    role_permissions = ROLE_PERMISSIONS.get(membership.role, set())
    if "*" in role_permissions:
        return all_known_permissions()
    permissions = set(role_permissions)
    extras = getattr(membership, "extra_permissions", None) or []
    if isinstance(extras, (list, tuple, set)):
        for value in extras:
            if isinstance(value, str) and value:
                permissions.add(value)
    return permissions


def has_permission(request: HttpRequest, permission: str) -> bool:
    user = getattr(request, "user", None)
    if user is not None and getattr(user, "is_superuser", False):
        return True
    membership = getattr(request, "tenant_membership", None)
    if not membership:
        return False
    role_permissions = ROLE_PERMISSIONS.get(membership.role, set())
    if "*" in role_permissions or permission in role_permissions:
        return True
    extras = getattr(membership, "extra_permissions", None) or []
    if isinstance(extras, (list, tuple, set)) and permission in extras:
        return True
    return False


def require_permission(permission: str):
    def decorator(view_func):
        @wraps(view_func)
        def wrapped(request: HttpRequest, *args, **kwargs):
            if not getattr(request.user, "is_authenticated", False):
                return JsonResponse({"error": "authentication_required"}, status=401)
            if not getattr(request, "tenant", None):
                resolve_request_tenant(request)
            if not has_permission(request, permission):
                return JsonResponse({"error": "permission_denied", "required_permission": permission}, status=403)
            return view_func(request, *args, **kwargs)

        return wrapped

    return decorator


def tenant_queryset(request: HttpRequest, model_or_queryset):
    tenant = getattr(request, "tenant", None)
    queryset = model_or_queryset.objects.all() if hasattr(model_or_queryset, "objects") else model_or_queryset
    if tenant is None:
        return queryset.none()
    return queryset.filter(tenant=tenant)


def tenant_object_or_404(request: HttpRequest, model_or_queryset, **lookup):
    return get_object_or_404(tenant_queryset(request, model_or_queryset), **lookup)


def audit_event(request: HttpRequest, action: str, *, object_type: str = "", object_id: str = "", metadata: Optional[Dict[str, Any]] = None) -> None:
    TenantAuditEvent.objects.create(
        tenant=getattr(request, "tenant", None) or get_default_tenant(),
        actor=request.user if getattr(request.user, "is_authenticated", False) else None,
        action=action,
        object_type=object_type,
        object_id=str(object_id or ""),
        metadata_json=metadata or {},
    )
