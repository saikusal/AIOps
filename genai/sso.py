from typing import Optional

from django.conf import settings
from django.contrib.auth import get_user_model, login as auth_login


User = get_user_model()


def _meta_key(header_name: str) -> str:
    normalized = (header_name or "").strip().upper().replace("-", "_")
    if not normalized:
        return ""
    if normalized in {"CONTENT_TYPE", "CONTENT_LENGTH"}:
        return normalized
    return f"HTTP_{normalized}"


def get_sso_identity(request) -> Optional[dict]:
    if not getattr(settings, "SSO_ENABLED", False):
        return None

    username = request.META.get(_meta_key(settings.SSO_USERNAME_HEADER), "").strip()
    if not username:
        return None

    email = request.META.get(_meta_key(settings.SSO_EMAIL_HEADER), "").strip()
    full_name = request.META.get(_meta_key(settings.SSO_NAME_HEADER), "").strip()
    return {
        "username": username,
        "email": email,
        "full_name": full_name,
    }


def ensure_sso_user(request):
    identity = get_sso_identity(request)
    if not identity:
        return None

    user, created = User.objects.get_or_create(
        username=identity["username"],
        defaults={"email": identity["email"]},
    )

    changed = False
    if identity["email"] and user.email != identity["email"]:
        user.email = identity["email"]
        changed = True

    if identity["full_name"]:
        parts = identity["full_name"].split(None, 1)
        first_name = parts[0]
        last_name = parts[1] if len(parts) > 1 else ""
        if user.first_name != first_name:
            user.first_name = first_name
            changed = True
        if user.last_name != last_name:
            user.last_name = last_name
            changed = True

    if created:
        user.set_unusable_password()
        changed = True

    if changed:
        user.save()

    if not request.user.is_authenticated or request.user.pk != user.pk:
        auth_login(request, user, backend="django.contrib.auth.backends.ModelBackend")
    return user
