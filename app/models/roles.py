"""Instance role matrix (Phase 9).

Roles are plain strings on memberships (no Postgres enum by design).
Permissions compose by inheritance; admins hold everything. Legacy
`ADMIN` users and site-wide grants bypass the matrix entirely.
"""

from typing import Any

# Base user capabilities. Admin-only capabilities are everything else.
USER_PERMS = frozenset(
    {
        "vote",
        "comment",
        "chat",
        "create_idea",
        "edit_own_idea",
        "iterate_own",
    }
)

ROLE_PERMISSIONS = {
    "USER": USER_PERMS,
    "DEVELOPER": USER_PERMS | {"run_actions", "view_discovery"},
    "BA": USER_PERMS | {"edit_docs", "flag_comments"},
    "DEPLOYMENT": USER_PERMS | {"run_actions", "change_status", "edit_docs"},
    "INSTANCE_ADMIN": USER_PERMS
    | {
        "run_actions",
        "view_discovery",
        "edit_docs",
        "flag_comments",
        "change_status",
        "edit_any_idea",
        "manage_prompts",
        "manage_members",
        "manage_config",
    },
    "SITE_ADMIN": USER_PERMS
    | {
        "run_actions",
        "view_discovery",
        "edit_docs",
        "flag_comments",
        "change_status",
        "edit_any_idea",
        "manage_prompts",
        "manage_members",
        "manage_config",
        "manage_instances",
        "manage_billing",
    },
}

# Assignable on per-instance memberships (SITE_ADMIN is global-only).
ASSIGNABLE_ROLES = ("USER", "DEVELOPER", "BA", "DEPLOYMENT", "INSTANCE_ADMIN")


def role_permissions(role: str) -> frozenset:
    return ROLE_PERMISSIONS.get(role, frozenset())


def has_permission(user: Any, perm: str, instance_id: Any = None) -> bool:
    """True if the user holds perm in context (legacy admins: everything).

    Membership powers require instance context: unscoped tokens only
    carry the legacy ADMIN role and site-wide grants. Otherwise an
    instance-A admin could act on instance B simply by dropping the
    claim.
    """
    if user.role.value == "ADMIN":
        return True
    from app.models import Membership

    if Membership.is_site_admin(user.id):
        return True
    if instance_id is None:
        return False
    role = Membership.get_role(user.id, instance_id)
    return perm in role_permissions(role) if role else False


def can_edit_idea(user: Any, idea: Any) -> bool:
    """Content/iterate access: any-idea perm, or own-idea perm + authorship."""
    from flask import g

    instance_id = getattr(g, "instance_id", None)
    if has_permission(user, "edit_any_idea", instance_id):
        return True
    return bool(
        has_permission(user, "edit_own_idea", instance_id)
        and idea.created_by_id is not None
        and idea.created_by_id == user.id
    )
