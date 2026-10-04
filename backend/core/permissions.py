from rest_framework.permissions import BasePermission

from accounts.models import User


class IsAdminRole(BasePermission):
    """仅管理员可粘贴、续期与作废湿度计止日贴纸。"""

    message = "仅管理员可粘贴、续期与作废贴纸"

    def has_permission(self, request, view):
        user = request.user
        return bool(
            user
            and user.is_authenticated
            and getattr(user, "role", None) == User.ROLE_ADMIN
        )
