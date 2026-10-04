from rest_framework.permissions import BasePermission


class IsAdminRole(BasePermission):
    """仅管理员（role=admin 或超级用户）可执行；操作工只读。"""

    message = "仅管理员可粘贴、续期与作废止日贴纸"

    def has_permission(self, request, view):
        user = request.user
        return bool(
            user
            and user.is_authenticated
            and (user.is_superuser or getattr(user, "role", None) == "admin")
        )
