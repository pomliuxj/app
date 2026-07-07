"""
项目成员管理 — 增删改视图
权限：项目「超级管理员」或系统超级管理员。
"""

import logging
from django.contrib.auth.models import User
from django.core.exceptions import ObjectDoesNotExist
from rest_framework.authentication import TokenAuthentication
from rest_framework.parsers import JSONParser
from rest_framework.views import APIView
from drf_spectacular.utils import extend_schema

from api_test.common.api_response import JsonResponse
from api_test.common.common import record_dynamic
from api_test.common.schema_utils import (
    success_response, simple_response, error_responses, json_body,
)
from api_test.models import Project, ProjectMember
from api_test.serializers import (
    ProjectMemberAddSerializer,
    ProjectMemberUpdateRoleSerializer,
    ProjectMemberSerializer,
    ProjectSerializer,
)

logger = logging.getLogger(__name__)

# 可选的角色
VALID_ROLES = ('超级管理员', '开发人员', '测试人员')


def _check_project_admin(user, project_id):
    """检查用户是否有项目管理权限（项目超级管理员 or 系统超级管理员）"""
    if user.is_superuser:
        return True
    return ProjectMember.objects.filter(
        project_id=project_id, user=user, permissionType='超级管理员'
    ).exists()


def _get_project(project_id):
    """获取项目并校验状态，返回 (project, error_response)"""
    try:
        project = Project.objects.get(id=project_id)
    except ObjectDoesNotExist:
        return None, JsonResponse(code="999995", msg="项目不存在!")
    pro_data = ProjectSerializer(project)
    if not pro_data.data["status"]:
        return None, JsonResponse(code="999985", msg="该项目已禁用")
    return project, None


# ═══════════════════════════════════════════════════════════════════════
# 添加项目成员
# ═══════════════════════════════════════════════════════════════════════

class ProjectMemberAdd(APIView):
    authentication_classes = (TokenAuthentication,)
    permission_classes = ()

    @extend_schema(
        summary="添加项目成员",
        description="向指定项目添加成员并指定角色。需项目超级管理员或系统超级管理员权限。",
        request=json_body(
            properties={
                "project_id": {"type": "integer", "description": "项目 ID"},
                "user_id": {"type": "integer", "description": "用户 ID"},
                "permissionType": {
                    "type": "string",
                    "description": "角色",
                    "enum": list(VALID_ROLES),
                },
            },
            required=["project_id", "user_id", "permissionType"],
        ),
        responses={
            200: success_response("成功", data_example={"member_id": 1}),
            **error_responses(),
        },
    )
    def post(self, request):
        data = JSONParser().parse(request)
        project_id = data.get("project_id")
        user_id = data.get("user_id")
        permission_type = data.get("permissionType")

        # 参数校验
        if not project_id or not user_id or not permission_type:
            return JsonResponse(code="999996", msg="参数有误!")
        if not isinstance(project_id, int) or not isinstance(user_id, int):
            return JsonResponse(code="999996", msg="参数有误!")
        if permission_type not in VALID_ROLES:
            return JsonResponse(code="999996", msg="角色类型无效!")

        # 权限校验
        if not _check_project_admin(request.user, project_id):
            return JsonResponse(code="999983", msg="无操作权限！")

        # 项目校验
        project, err = _get_project(project_id)
        if err:
            return err

        # 用户校验
        try:
            target_user = User.objects.get(id=user_id)
        except ObjectDoesNotExist:
            return JsonResponse(code="999995", msg="用户不存在！")

        # 重复检查
        if ProjectMember.objects.filter(project_id=project_id, user_id=user_id).exists():
            return JsonResponse(code="999985", msg="该用户已是项目成员！")

        # 创建
        member = ProjectMember.objects.create(
            project=project, user=target_user, permissionType=permission_type,
        )
        record_dynamic(
            project=project_id,
            _type="添加", operationObject="项目成员", user=request.user.pk,
            data=f"添加成员“{target_user.username}”为{permission_type}"
        )
        logger.info("User %s added %s to project %s as %s",
                    request.user.username, target_user.username, project_id, permission_type)
        return JsonResponse(data={"member_id": member.id}, code="999999", msg="成功!")


# ═══════════════════════════════════════════════════════════════════════
# 移除项目成员
# ═══════════════════════════════════════════════════════════════════════

class ProjectMemberRemove(APIView):
    authentication_classes = (TokenAuthentication,)
    permission_classes = ()

    @extend_schema(
        summary="移除项目成员",
        description="从项目中移除指定成员。不允许移除最后一个超级管理员。",
        request=json_body(
            properties={
                "project_id": {"type": "integer", "description": "项目 ID"},
                "user_id": {"type": "integer", "description": "要移除的用户 ID"},
            },
            required=["project_id", "user_id"],
        ),
        responses={
            200: simple_response(),
            **error_responses(),
        },
    )
    def post(self, request):
        data = JSONParser().parse(request)
        project_id = data.get("project_id")
        user_id = data.get("user_id")

        if not project_id or not user_id:
            return JsonResponse(code="999996", msg="参数有误!")
        if not isinstance(project_id, int) or not isinstance(user_id, int):
            return JsonResponse(code="999996", msg="参数有误!")

        # 权限校验
        if not _check_project_admin(request.user, project_id):
            return JsonResponse(code="999983", msg="无操作权限！")

        # 项目校验
        _, err = _get_project(project_id)
        if err:
            return err

        # 成员校验
        try:
            member = ProjectMember.objects.get(project_id=project_id, user_id=user_id)
        except ObjectDoesNotExist:
            return JsonResponse(code="999995", msg="该用户不是项目成员！")

        # 至少保留一个超级管理员
        if member.permissionType == '超级管理员':
            admin_count = ProjectMember.objects.filter(
                project_id=project_id, permissionType='超级管理员'
            ).count()
            if admin_count <= 1:
                return JsonResponse(code="999983", msg="至少保留一个超级管理员！")

        username = member.user.username
        member.delete()
        record_dynamic(
            project=project_id,
            _type="删除", operationObject="项目成员", user=request.user.pk,
            data=f"移除成员“{username}”"
        )
        logger.info("User %s removed %s from project %s",
                    request.user.username, username, project_id)
        return JsonResponse(code="999999", msg="成功!")


# ═══════════════════════════════════════════════════════════════════════
# 修改成员角色
# ═══════════════════════════════════════════════════════════════════════

class ProjectMemberUpdateRole(APIView):
    authentication_classes = (TokenAuthentication,)
    permission_classes = ()

    @extend_schema(
        summary="修改成员角色",
        description="修改项目中指定成员的角色。不允许将最后一个超级管理员降级。",
        request=json_body(
            properties={
                "project_id": {"type": "integer", "description": "项目 ID"},
                "user_id": {"type": "integer", "description": "用户 ID"},
                "permissionType": {
                    "type": "string",
                    "description": "新角色",
                    "enum": list(VALID_ROLES),
                },
            },
            required=["project_id", "user_id", "permissionType"],
        ),
        responses={
            200: success_response("成功", data_example={
                "member_id": 1, "permissionType": "测试人员",
            }),
            **error_responses(),
        },
    )
    def put(self, request):
        data = JSONParser().parse(request)
        project_id = data.get("project_id")
        user_id = data.get("user_id")
        new_role = data.get("permissionType")

        if not project_id or not user_id or not new_role:
            return JsonResponse(code="999996", msg="参数有误!")
        if not isinstance(project_id, int) or not isinstance(user_id, int):
            return JsonResponse(code="999996", msg="参数有误!")
        if new_role not in VALID_ROLES:
            return JsonResponse(code="999996", msg="角色类型无效!")

        # 权限校验
        if not _check_project_admin(request.user, project_id):
            return JsonResponse(code="999983", msg="无操作权限！")

        # 项目校验
        _, err = _get_project(project_id)
        if err:
            return err

        # 成员校验
        try:
            member = ProjectMember.objects.get(project_id=project_id, user_id=user_id)
        except ObjectDoesNotExist:
            return JsonResponse(code="999995", msg="该用户不是项目成员！")

        old_role = member.permissionType

        # 不允许将最后一个超级管理员降级
        if old_role == '超级管理员' and new_role != '超级管理员':
            admin_count = ProjectMember.objects.filter(
                project_id=project_id, permissionType='超级管理员'
            ).count()
            if admin_count <= 1:
                return JsonResponse(code="999983", msg="至少保留一个超级管理员！")

        member.permissionType = new_role
        member.save()
        record_dynamic(
            project=project_id,
            _type="修改", operationObject="项目成员", user=request.user.pk,
            data=f"修改成员“{member.user.username}”角色：{old_role} → {new_role}"
        )
        logger.info("User %s changed role of %s in project %s: %s → %s",
                    request.user.username, member.user.username, project_id, old_role, new_role)
        return JsonResponse(
            data={"member_id": member.id, "permissionType": new_role},
            code="999999", msg="成功!"
        )
