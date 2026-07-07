import logging

from django.core.exceptions import ObjectDoesNotExist
from django.core.paginator import Paginator, PageNotAnInteger, EmptyPage
from drf_spectacular.utils import extend_schema
from rest_framework.authentication import TokenAuthentication
from rest_framework.parsers import JSONParser
from rest_framework.views import APIView

from api_test.common.api_response import JsonResponse
from api_test.common.common import record_dynamic
from api_test.common.schema_utils import (
    PROJECT_ID_PARAM, PAGE_PARAM, PAGE_SIZE_PARAM,
    success_response, error_responses, json_body,
    list_response, simple_response,
)
from api_test.models import Project, ProjectMember, AutomationReportSendConfig
from api_test.serializers import ProjectMemberSerializer, AutomationReportSendConfigSerializer, \
    AutomationReportSendConfigDeserializer, ProjectSerializer

logger = logging.getLogger(__name__)  # 这里使用 __name__ 动态搜索定义的 logger 配置，这里有一个层次关系的知识点。


class ProjectMemberList(APIView):
    authentication_classes = (TokenAuthentication,)
    permission_classes = ()

    @extend_schema(
        summary="获取项目成员列表",
        description="分页获取指定项目的成员列表",
        parameters=[PROJECT_ID_PARAM, PAGE_PARAM, PAGE_SIZE_PARAM],
        responses={
            200: list_response("成功"),
            **error_responses(),
        },
    )
    def get(self, request):
        """
        获取项目成员列表
        :param request:
        :return:
        """
        try:
            page_size = int(request.GET.get("page_size", 20))
            page = int(request.GET.get("page", 1))
        except (TypeError, ValueError):
            return JsonResponse(code="999985", msg="page and page_size must be integer！")
        project_id = request.GET.get("project_id")
        if not project_id:
            return JsonResponse(code="999996", msg="参数有误！")
        if not project_id.isdecimal():
            return JsonResponse(code="999996", msg="参数有误！")
        try:
            pro_data = Project.objects.get(id=project_id)
        except ObjectDoesNotExist:
            return JsonResponse(code="999995", msg="项目不存在！")
        pro_data = ProjectSerializer(pro_data)
        if not pro_data.data["status"]:
            return JsonResponse(code="999985", msg="该项目已禁用")
        obi = ProjectMember.objects.filter(project=project_id).order_by("id")
        paginator = Paginator(obi, page_size)  # paginator对象
        total = paginator.count  # 总记录数
        try:
            obm = paginator.page(page)
        except PageNotAnInteger:
            obm = paginator.page(1)
        except EmptyPage:
            obm = paginator.page(paginator.num_pages)
        serialize = ProjectMemberSerializer(obm, many=True)
        return JsonResponse(data={"data": serialize.data,
                                  "page": page,
                                  "total": total
                                  }, code="999999", msg="成功！")


class EmailConfig(APIView):
    authentication_classes = (TokenAuthentication,)
    permission_classes = ()

    def parameter_check(self, data):
        try:
            if not isinstance(data["project_id"], int):
                return JsonResponse(code="999996", msg="参数有误！")
            if not data["reportFrom"] or not data["mailUser"] or not data["mailPass"] or not data["mailSmtp"]:
                return JsonResponse(code="999996", msg="参数有误！")
        except KeyError:
            return JsonResponse(code="999996", msg="参数有误！")

    @extend_schema(
        summary="配置邮件发送",
        description="添加或修改项目的邮件发送配置",
        request=json_body(
            properties={
                "project_id": {"type": "integer", "description": "项目 ID"},
                "reportFrom": {"type": "string", "description": "发件人地址"},
                "mailUser": {"type": "string", "description": "邮箱用户名"},
                "mailPass": {"type": "string", "description": "邮箱密码"},
                "mailSmtp": {"type": "string", "description": "SMTP 服务器地址"},
            },
            required=["project_id", "reportFrom", "mailUser", "mailPass", "mailSmtp"],
        ),
        responses={
            200: simple_response(),
            **error_responses(),
        },
    )
    def post(self, request):
        data = JSONParser().parse(request)
        result = self.parameter_check(data)
        if result:
            return result
        try:
            obi = Project.objects.get(id=data["project_id"])
            if not request.user.is_superuser and obi.user.is_superuser:
                return JsonResponse(code="999983", msg="无操作权限！")
        except ObjectDoesNotExist:
            return JsonResponse(code="999995", msg="项目不存在！")
        pro_data = ProjectSerializer(obi)
        if not pro_data.data["status"]:
            return JsonResponse(code="999985", msg="该项目已禁用")
        serialize = AutomationReportSendConfigDeserializer(data=data)
        if serialize.is_valid():
            try:
                obj = AutomationReportSendConfig.objects.get(project=data["project_id"])
                serialize.update(instance=obj, validated_data=data)
            except ObjectDoesNotExist:
                serialize.save(project=obi)
            record_dynamic(project=data["project_id"],
                           _type="添加", operationObject="邮箱", user=request.user.pk, data="添加邮箱配置")
            return JsonResponse(code="999999", msg="成功！")
        return JsonResponse(code="999996", msg="参数有误！")


class DelEmail(APIView):
    authentication_classes = (TokenAuthentication,)
    permission_classes = ()

    def parameter_check(self, data):
        try:
            if not isinstance(data["project_id"], int):
                return JsonResponse(code="999996", msg="参数有误！")
        except KeyError:
            return JsonResponse(code="999996", msg="参数有误！")

    @extend_schema(
        summary="删除邮件配置",
        description="删除项目的邮件发送配置",
        request=json_body(
            properties={
                "project_id": {"type": "integer", "description": "项目 ID"},
            },
            required=["project_id"],
        ),
        responses={
            200: simple_response(),
            **error_responses(),
        },
    )
    def post(self, request):
        data = JSONParser().parse(request)
        result = self.parameter_check(data)
        if result:
            return result
        try:
            pro_data = Project.objects.get(id=data["project_id"])
            if not request.user.is_superuser and pro_data.user.is_superuser:
                return JsonResponse(code="999983", msg="无操作权限！")
        except ObjectDoesNotExist:
            return JsonResponse(code="999995", msg="项目不存在！")
        pro_data = ProjectSerializer(pro_data)
        if not pro_data.data["status"]:
            return JsonResponse(code="999985", msg="该项目已禁用")
        AutomationReportSendConfig.objects.filter(project=data["project_id"]).delete()
        record_dynamic(project=data["project_id"],
                       _type="删除", operationObject="邮箱", user=request.user.pk, data="删除邮箱配置")
        return JsonResponse(code="999999", msg="成功！")


class GetEmail(APIView):
    authentication_classes = (TokenAuthentication,)
    permission_classes = ()

    @extend_schema(
        summary="获取邮件配置",
        description="获取项目的邮件发送配置",
        parameters=[PROJECT_ID_PARAM],
        responses={
            200: success_response("成功", data_example={"reportFrom":"test@test.com","mailUser":"user","mailSmtp":"smtp.test.com"}),
            **error_responses(),
        },
    )
    def get(self, request):
        project_id = request.GET.get("project_id")
        if not project_id:
            return JsonResponse(code="999996", msg="参数有误！")
        if not project_id.isdecimal():
            return JsonResponse(code="999996", msg="参数有误！")
        try:
            pro_data = Project.objects.get(id=project_id)
        except ObjectDoesNotExist:
            return JsonResponse(code="999995", msg="项目不存在！")
        pro_data = ProjectSerializer(pro_data)
        if not pro_data.data["status"]:
            return JsonResponse(code="999985", msg="该项目已禁用")
        try:
            obj = AutomationReportSendConfig.objects.get(project=project_id)
        except ObjectDoesNotExist:
            return JsonResponse(code="999999", msg="成功！")
        data = AutomationReportSendConfigSerializer(obj).data
        return JsonResponse(code="999999", msg="成功！", data=data)
