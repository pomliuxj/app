"""
用户账号管理 — CRUD 视图
所有接口仅限超级管理员访问。
"""

import logging
from django.contrib.auth.models import User
from django.core.paginator import Paginator, PageNotAnInteger, EmptyPage
from django.db.models import Q
from rest_framework.authentication import TokenAuthentication
from rest_framework.authtoken.models import Token
from rest_framework.parsers import JSONParser
from rest_framework.views import APIView
from drf_spectacular.utils import extend_schema

from api_test.common.api_response import JsonResponse
from api_test.common.schema_utils import (
    PAGE_PARAM, PAGE_SIZE_PARAM,
    success_response, list_response, simple_response,
    error_responses,
    json_body,
)
from api_test.models import UserProfile
from api_test.serializers import (
    UserAccountSerializer,
    UserCreateSerializer,
    UserUpdateSerializer,
    UserPasswordResetSerializer,
)

logger = logging.getLogger(__name__)


def _require_superuser(request):
    """返回 True 表示无权限（需拦截），False 表示放行"""
    if not request.user.is_superuser:
        return True
    return False


# ═══════════════════════════════════════════════════════════════════════
# 用户列表
# ═══════════════════════════════════════════════════════════════════════

class UserList(APIView):
    authentication_classes = (TokenAuthentication,)
    permission_classes = ()

    @extend_schema(
        summary="获取用户列表",
        description="分页获取所有用户，可按用户名或邮箱模糊搜索。仅超级管理员可用。",
        parameters=[PAGE_PARAM, PAGE_SIZE_PARAM],
        responses={
            200: list_response("成功", item_example={
                "id": 1, "username": "admin", "email": "admin@test.com",
                "first_name": "管理员", "is_active": True, "is_superuser": True,
            }),
            **error_responses(),
        },
    )
    def get(self, request):
        if _require_superuser(request):
            return JsonResponse(code="999983", msg="无操作权限！")

        try:
            page_size = int(request.GET.get("page_size", 20))
            page = int(request.GET.get("page", 1))
        except (TypeError, ValueError):
            return JsonResponse(code="999985", msg="page and page_size must be integer!")

        search = request.GET.get("search", "")
        if search:
            users = User.objects.filter(
                Q(username__contains=search) | Q(email__contains=search)
            ).order_by("id")
        else:
            users = User.objects.all().order_by("id")

        paginator = Paginator(users, page_size)
        total = paginator.count
        try:
            obm = paginator.page(page)
        except PageNotAnInteger:
            obm = paginator.page(1)
        except EmptyPage:
            obm = paginator.page(paginator.num_pages)

        serialize = UserAccountSerializer(obm, many=True)
        return JsonResponse(
            data={"data": serialize.data, "page": page, "total": total},
            code="999999", msg="成功!"
        )


# ═══════════════════════════════════════════════════════════════════════
# 用户详情
# ═══════════════════════════════════════════════════════════════════════

class UserDetail(APIView):
    authentication_classes = (TokenAuthentication,)
    permission_classes = ()

    @extend_schema(
        summary="获取用户详情",
        description="获取指定用户的详细信息（含手机号、项目角色等）。仅超级管理员可用。",
        parameters=[
            PAGE_PARAM,  # reuse project_id style — actually we need user_id
        ],
        responses={
            200: success_response("成功", data_example={
                "id": 1, "username": "admin", "roles": [{"project_id": 1, "project_name": "项目A", "role": "超级管理员"}],
            }),
            **error_responses(),
        },
    )
    def get(self, request):
        if _require_superuser(request):
            return JsonResponse(code="999983", msg="无操作权限！")

        user_id = request.GET.get("user_id")
        if not user_id or not user_id.isdecimal():
            return JsonResponse(code="999996", msg="参数有误!")

        try:
            user = User.objects.get(id=int(user_id))
        except User.DoesNotExist:
            return JsonResponse(code="999995", msg="用户不存在！")

        serialize = UserAccountSerializer(user)
        return JsonResponse(data=serialize.data, code="999999", msg="成功!")


# ═══════════════════════════════════════════════════════════════════════
# 创建用户
# ═══════════════════════════════════════════════════════════════════════

class UserCreate(APIView):
    authentication_classes = (TokenAuthentication,)
    permission_classes = ()

    @extend_schema(
        summary="创建用户",
        description="管理员手动创建新用户账号。仅超级管理员可用。",
        request=json_body(
            properties={
                "username": {"type": "string", "description": "用户名（3-50 字符）"},
                "password": {"type": "string", "description": "密码（6-128 字符）"},
                "email": {"type": "string", "description": "邮箱（可选）"},
                "first_name": {"type": "string", "description": "显示名称（可选）"},
                "phone": {"type": "string", "description": "手机号（可选，11 位）"},
                "is_active": {"type": "boolean", "description": "是否启用，默认 true"},
                "is_superuser": {"type": "boolean", "description": "是否超级管理员，默认 false"},
            },
            required=["username", "password"],
        ),
        responses={
            200: success_response("创建成功", data_example={"user_id": 1}),
            **error_responses(),
        },
    )
    def post(self, request):
        if _require_superuser(request):
            return JsonResponse(code="999983", msg="无操作权限！")

        data = JSONParser().parse(request)
        # 参数校验
        if not data.get("username") or not data.get("password"):
            return JsonResponse(code="999996", msg="参数有误!")
        username = data.get("username", "")
        if not (3 <= len(username) <= 50):
            return JsonResponse(code="999996", msg="用户名长度应为3-50个字符!")
        password = data.get("password", "")
        if not (6 <= len(password) <= 128):
            return JsonResponse(code="999996", msg="密码长度应为6-128个字符!")

        serializer = UserCreateSerializer(data=data)
        if serializer.is_valid():
            user = serializer.save()
            logger.info("Admin %s created user %s", request.user.username, user.username)
            return JsonResponse(data={"user_id": user.id}, code="999999", msg="创建成功!")
        # 提取第一个校验错误
        errors = serializer.errors
        first_error = ""
        for field, msgs in errors.items():
            first_error = f"{field}: {msgs[0] if isinstance(msgs, list) else msgs}"
            break
        return JsonResponse(code="999985", msg=first_error or "创建失败!")


# ═══════════════════════════════════════════════════════════════════════
# 编辑用户
# ═══════════════════════════════════════════════════════════════════════

class UserUpdate(APIView):
    authentication_classes = (TokenAuthentication,)
    permission_classes = ()

    @extend_schema(
        summary="编辑用户信息",
        description="编辑用户信息（部分更新，只更新传入的字段）。仅超级管理员可用。",
        request=json_body(
            properties={
                "user_id": {"type": "integer", "description": "用户 ID"},
                "username": {"type": "string", "description": "新用户名（可选）"},
                "email": {"type": "string", "description": "新邮箱（可选）"},
                "first_name": {"type": "string", "description": "新显示名称（可选）"},
                "phone": {"type": "string", "description": "新手机号（可选）"},
                "is_active": {"type": "boolean", "description": "是否启用（可选）"},
                "is_superuser": {"type": "boolean", "description": "是否超级管理员（可选）"},
            },
            required=["user_id"],
        ),
        responses={
            200: simple_response(),
            **error_responses(),
        },
    )
    def put(self, request):
        if _require_superuser(request):
            return JsonResponse(code="999983", msg="无操作权限！")

        data = JSONParser().parse(request)
        user_id = data.get("user_id")
        if not user_id or not isinstance(user_id, int):
            return JsonResponse(code="999996", msg="参数有误!")

        try:
            target_user = User.objects.get(id=user_id)
        except User.DoesNotExist:
            return JsonResponse(code="999995", msg="用户不存在！")

        # 禁止取消自己的超级管理员权限
        if request.user.id == target_user.id:
            if "is_superuser" in data and not data["is_superuser"]:
                return JsonResponse(code="999983", msg="不能取消自己的超级管理员权限！")

        serializer = UserUpdateSerializer(target_user, data=data, partial=True)
        if serializer.is_valid():
            user = serializer.save()
            # 更新 UserProfile.phone
            if "phone" in data:
                from api_test.models import UserProfile
                profile, _ = UserProfile.objects.get_or_create(user=user)
                profile.phone = data.get("phone", "")
                profile.save()
            logger.info("Admin %s updated user %s", request.user.username, user.username)
            return JsonResponse(code="999999", msg="成功!")

        errors = serializer.errors
        first_error = ""
        for field, msgs in errors.items():
            first_error = f"{field}: {msgs[0] if isinstance(msgs, list) else msgs}"
            break
        return JsonResponse(code="999985", msg=first_error or "更新失败!")


# ═══════════════════════════════════════════════════════════════════════
# 重置密码
# ═══════════════════════════════════════════════════════════════════════

class UserPasswordReset(APIView):
    authentication_classes = (TokenAuthentication,)
    permission_classes = ()

    @extend_schema(
        summary="重置用户密码",
        description="管理员强制重置用户密码，重置后用户需重新登录。仅超级管理员可用。",
        request=json_body(
            properties={
                "user_id": {"type": "integer", "description": "用户 ID"},
                "new_password": {"type": "string", "description": "新密码（6-128 字符）"},
            },
            required=["user_id", "new_password"],
        ),
        responses={
            200: simple_response(),
            **error_responses(),
        },
    )
    def post(self, request):
        if _require_superuser(request):
            return JsonResponse(code="999983", msg="无操作权限！")

        data = JSONParser().parse(request)
        user_id = data.get("user_id")
        new_password = data.get("new_password", "")
        if not user_id or not isinstance(user_id, int):
            return JsonResponse(code="999996", msg="参数有误!")
        if not (6 <= len(new_password) <= 128):
            return JsonResponse(code="999996", msg="密码长度应为6-128个字符!")

        try:
            user = User.objects.get(id=user_id)
        except User.DoesNotExist:
            return JsonResponse(code="999995", msg="用户不存在！")

        user.set_password(new_password)
        user.save()
        # 删除旧 Token，强制重新登录
        Token.objects.filter(user=user).delete()
        Token.objects.create(user=user)
        logger.info("Admin %s reset password for user %s", request.user.username, user.username)
        return JsonResponse(code="999999", msg="密码重置成功！")


# ═══════════════════════════════════════════════════════════════════════
# 启用 / 禁用用户
# ═══════════════════════════════════════════════════════════════════════

class UserToggleActive(APIView):
    authentication_classes = (TokenAuthentication,)
    permission_classes = ()

    @extend_schema(
        summary="切换用户启用状态",
        description="切换用户 is_active 状态。禁用后该用户 Token 失效。仅超级管理员可用。",
        request=json_body(
            properties={
                "user_id": {"type": "integer", "description": "用户 ID"},
            },
            required=["user_id"],
        ),
        responses={
            200: success_response("成功", data_example={"user_id": 1, "is_active": False}),
            **error_responses(),
        },
    )
    def post(self, request):
        if _require_superuser(request):
            return JsonResponse(code="999983", msg="无操作权限！")

        data = JSONParser().parse(request)
        user_id = data.get("user_id")
        if not user_id or not isinstance(user_id, int):
            return JsonResponse(code="999996", msg="参数有误!")

        try:
            user = User.objects.get(id=user_id)
        except User.DoesNotExist:
            return JsonResponse(code="999995", msg="用户不存在！")

        # 禁止禁用自己
        if request.user.id == user.id:
            return JsonResponse(code="999983", msg="不能禁用自己！")

        user.is_active = not user.is_active
        user.save()

        # 禁用时清除 Token，强制下线
        if not user.is_active:
            Token.objects.filter(user=user).delete()

        status_text = "启用" if user.is_active else "禁用"
        logger.info("Admin %s %s user %s", request.user.username, status_text, user.username)
        return JsonResponse(
            data={"user_id": user.id, "is_active": user.is_active},
            code="999999", msg=f"已{status_text}!"
        )
