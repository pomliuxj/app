import json
import logging
from api_test.common.decorator import clock
from concurrent.futures import ThreadPoolExecutor
from datetime import datetime
from django.contrib.auth.models import User
from django.core.exceptions import ObjectDoesNotExist
from django.core.paginator import Paginator, PageNotAnInteger, EmptyPage
from django.db import transaction
from django.db.models import Q
from drf_spectacular.utils import extend_schema, OpenApiParameter, OpenApiResponse, OpenApiExample
from rest_framework.authentication import TokenAuthentication
from rest_framework.parsers import JSONParser
from rest_framework.views import APIView
from api_test.config.Glb_config import THEAD_COUNT
from api_test.common.WriteExcel import Write
from api_test.common.addTask import creatTask,delTask
from api_test.common.api_response import JsonResponse
from api_test.common.common import record_dynamic, create_json, set_step_id_map
from api_test.common.confighttp import test_api
from api_test.common.auto_task_test import test_api as test_api_sequential
from api_test.common.schema_utils import (
    PROJECT_ID_PARAM, PAGE_PARAM, PAGE_SIZE_PARAM, NAME_PARAM,
    FIRST_GROUP_ID_PARAM, CASE_ID_PARAM, API_ID_PARAM,
    success_response, error_responses, param_error_response,
    not_found_response, permission_denied_response,
    simple_response, create_response, list_response,
    json_body,
)
from api_test.models import Project, AutomationGroupLevelFirst, \
    AutomationTestCase, AutomationCaseApi, AutomationParameter, GlobalHost, AutomationHead, AutomationTestTask, \
    AutomationTestResult, AutomationCaseTestResult, ApiInfo, AutomationParameterRaw, AutomationResponseJson, \
    AutomationJsonCheck

from api_test.serializers import AutomationGroupLevelFirstSerializer, AutomationTestCaseSerializer, \
    AutomationCaseApiSerializer, AutomationCaseApiListSerializer, AutomationTestTaskSerializer, \
    AutomationTestResultSerializer, ApiInfoSerializer, CorrelationDataSerializer, AutomationTestReportSerializer, \
    AutomationTestCaseDeserializer, AutomationCaseApiDeserializer, AutomationHeadDeserializer, \
    AutomationParameterDeserializer, AutomationTestTaskDeserializer, ProjectSerializer, \
    AutomationCaseDownSerializer,AutomationJsonCkeckserializer
logger = logging.getLogger(__name__)


class Group(APIView):
    authentication_classes = (TokenAuthentication,)
    permission_classes = ()

    @extend_schema(
        summary="获取用例分组列表",
        description="根据项目 ID 获取该项目下所有自动化用例分组",
        parameters=[PROJECT_ID_PARAM],
        responses={
            200: success_response("成功", data_example=[{"id":1,"name":"用例分组","project":1}]),
            **error_responses(),
        },
    )
    def get(self, request):
        """
        获取用例分组
        :return:
        """
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
        obi = AutomationGroupLevelFirst.objects.filter(project=project_id)
        serialize = AutomationGroupLevelFirstSerializer(obi, many=True)
        return JsonResponse(data=serialize.data, code="999999", msg="成功！")


class AddGroup(APIView):
    authentication_classes = (TokenAuthentication,)
    permission_classes = ()

    def parameter_check(self, data):
        """
        校验参数
        :param data:
        :return:
        """
        try:
            # 校验project_id类型为int
            if not isinstance(data["project_id"], int):
                return JsonResponse(code="999996", msg="参数有误！")
            # 必传参数 name, host
            if not data["name"]:
                return JsonResponse(code="999996", msg="参数有误！")
        except KeyError:
            return JsonResponse(code="999996", msg="参数有误！")

    @extend_schema(
        summary="新增用例分组",
        description="在指定项目下创建新的自动化用例分组",
        request=json_body(
            properties={
                "project_id": {"type": "integer", "description": "项目 ID"},
                "name": {"type": "string", "description": "分组名称"},
            },
            required=["project_id", "name"],
        ),
        responses={
            200: create_response(id_field="group_id"),
            **error_responses(),
        },
    )
    def post(self, request):
        """
        新增用例分组
        :param request:
        :return:
        """
        data = JSONParser().parse(request)
        result = self.parameter_check(data)
        if result:
            return result
        try:
            obj = Project.objects.get(id=data["project_id"])
            if not request.user.is_superuser and obj.user.is_superuser:
                return JsonResponse(code="999983", msg="无操作权限！")
        except ObjectDoesNotExist:
            return JsonResponse(code="999995", msg="项目不存在！")
        pro_data = ProjectSerializer(obj)
        if not pro_data.data["status"]:
            return JsonResponse(code="999985", msg="该项目已禁用")
        serializer = AutomationGroupLevelFirstSerializer(data=data)
        if serializer.is_valid():
            serializer.save(project=obj)
        else:
            return JsonResponse(code="999998", msg="失败！")
        record_dynamic(project=serializer.data.get("id"),
                       _type="添加", operationObject="用例分组", user=request.user.pk,
                       data="新增用例分组“%s”" % data["name"])
        return JsonResponse(data={
            "group_id": serializer.data.get("id")
        }, code="999999", msg="成功！")


class DelGroup(APIView):
    authentication_classes = (TokenAuthentication,)
    permission_classes = ()

    def parameter_check(self, data):
        """
        校验参数
        :param data:
        :return:
        """
        try:
            # 校验project_id, id类型为int
            if not isinstance(data["project_id"], int) or not isinstance(data["id"], int):
                return JsonResponse(code="999996", msg="参数有误！")
        except KeyError:
            return JsonResponse(code="999996", msg="参数有误！")

    @extend_schema(
        summary="删除用例分组",
        description="删除指定的自动化用例分组",
        request=json_body(
            properties={
                "project_id": {"type": "integer", "description": "项目 ID"},
                "id": {"type": "integer", "description": "分组 ID"},
            },
            required=["project_id", "id"],
        ),
        responses={
            200: simple_response(),
            **error_responses(),
        },
    )
    def post(self, request):
        """
        删除用例分组
        :param request:
        :return:
        """
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
        obi = AutomationGroupLevelFirst.objects.filter(id=data["id"], project=data["project_id"])
        if obi:
            name = obi[0].name
            obi.delete()
        else:
            return JsonResponse(code="999991", msg="分组不存在！")
        record_dynamic(project=data["project_id"],
                       _type="删除", operationObject="用例分组", user=request.user.pk, data="删除用例分组“%s”" % name)
        return JsonResponse(code="999999", msg="成功！")


class UpdateNameGroup(APIView):
    authentication_classes = (TokenAuthentication,)
    permission_classes = ()

    def parameter_check(self, data):
        """
        校验参数
        :param data:
        :return:
        """
        try:
            # 校验project_id, id类型为int
            if not isinstance(data["project_id"], int) or not isinstance(data["id"], int):
                return JsonResponse(code="999996", msg="参数有误！")
            # 必传参数 name, host
            if not data["name"]:
                return JsonResponse(code="999996", msg="参数有误！")
        except KeyError:
            return JsonResponse(code="999996", msg="参数有误！")

    @extend_schema(
        summary="修改用例分组名称",
        description="修改指定自动化用例分组的名称",
        request=json_body(
            properties={
                "project_id": {"type": "integer", "description": "项目 ID"},
                "id": {"type": "integer", "description": "分组 ID"},
                "name": {"type": "string", "description": "新分组名称"},
            },
            required=["project_id", "id", "name"],
        ),
        responses={
            200: simple_response(),
            **error_responses(),
        },
    )
    def post(self, request):
        """
        修改用例分组名称
        :param request:
        :return:
        """
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
        try:
            obj = AutomationGroupLevelFirst.objects.get(id=data["id"], project=data["project_id"])
        except ObjectDoesNotExist:
            return JsonResponse(code="999991", msg="分组不存在！")
        serializer = AutomationGroupLevelFirstSerializer(data=data)
        if serializer.is_valid():
            serializer.update(instance=obj, validated_data=data)
        else:
            return JsonResponse(code="999998", msg="失败！")
        record_dynamic(project=serializer.data.get("id"),
                       _type="修改", operationObject="用例分组", user=request.user.pk,
                       data="修改用例分组“%s”" % data["name"])
        return JsonResponse(code="999999", msg="成功！")


class UpdateGroup(APIView):
    authentication_classes = (TokenAuthentication,)
    permission_classes = ()

    def parameter_check(self, data):
        """
        校验参数
        :param data:
        :return:
        """
        try:
            # 校验project_id, id类型为int
            if not data["project_id"] or not data["ids"] or not data["automationGroupLevelFirst_id"]:
                return JsonResponse(code="999996", msg="参数有误！")
            if not isinstance(data["project_id"], int) or not isinstance(data["ids"], list) \
                    or not isinstance(data["automationGroupLevelFirst_id"], int):
                return JsonResponse(code="999996", msg="参数有误！")
            for i in data["ids"]:
                if not isinstance(i, int):
                    return JsonResponse(code="999996", msg="参数有误！")
        except KeyError:
            return JsonResponse(code="999996", msg="参数有误！")

    @extend_schema(
        summary="修改用例所属分组",
        description="批量将用例移动到指定分组",
        request=json_body(
            properties={
                "project_id": {"type": "integer", "description": "项目 ID"},
                "ids": {
                    "type": "array",
                    "description": "用例 ID 列表",
                    "items": {"type": "integer"},
                },
                "automationGroupLevelFirst_id": {"type": "integer", "description": "目标分组 ID"},
            },
            required=["project_id", "ids", "automationGroupLevelFirst_id"],
        ),
        responses={
            200: simple_response(),
            **error_responses(),
        },
    )
    def post(self, request):
        """
        修改用例所属分组
        :param request:
        :return:
        """
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
        try:
            obj = AutomationGroupLevelFirst.objects.get(id=data["automationGroupLevelFirst_id"])
        except ObjectDoesNotExist:
            return JsonResponse(code="999991", msg="分组不存在！")
        id_list = Q()
        for i in data["ids"]:
            id_list = id_list | Q(id=i)
        case_list = AutomationTestCase.objects.filter(id_list, project=data["project_id"])
        with transaction.atomic():
            case_list.update(automationGroupLevelFirst=obj)
            name_list = []
            for j in case_list:
                name_list.append(str(j.caseName))
            record_dynamic(project=data["project_id"],
                           _type="修改", operationObject="用例", user=request.user.pk, data="修改用例分组，列表“%s”" % name_list)
            return JsonResponse(code="999999", msg="成功！")


class CaseList(APIView):
    authentication_classes = (TokenAuthentication,)
    permission_classes = ()

    @extend_schema(
        summary="获取用例列表",
        description="分页获取自动化测试用例列表，可按分组、名称筛选",
        parameters=[
            PROJECT_ID_PARAM,
            FIRST_GROUP_ID_PARAM,
            NAME_PARAM,
            PAGE_PARAM,
            PAGE_SIZE_PARAM,
        ],
        responses={
            200: list_response("成功", item_example={"id":1,"caseName":"测试用例","automationGroupLevelFirst":1}),
            **error_responses(),
        },
    )
    def get(self, request):
        """
        获取用例列表
        :param request:
        :return:
        """
        try:
            page_size = int(request.GET.get("page_size", 20))
            page = int(request.GET.get("page", 1))
        except (TypeError, ValueError):
            return JsonResponse(code="999985", msg="page and page_size must be integer！")
        project_id = request.GET.get("project_id")
        first_group_id = request.GET.get("first_group_id")
        name = request.GET.get("name")
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
        if first_group_id:
            if not first_group_id.isdecimal():
                return JsonResponse(code="999996", msg="参数有误！")
            if name:
                obi = AutomationTestCase.objects.filter(project=project_id, caseName__contains=name,
                                                        automationGroupLevelFirst=first_group_id).order_by("id")
            else:
                obi = AutomationTestCase.objects.filter(project=project_id,
                                                        automationGroupLevelFirst=first_group_id).order_by("id")
        else:
            if name:
                obi = AutomationTestCase.objects.filter(project=project_id, caseName__contains=name, ).order_by(
                    "id")
            else:
                obi = AutomationTestCase.objects.filter(project=project_id).order_by("id")
        paginator = Paginator(obi, page_size)  # paginator对象
        total = paginator.count  # 总记录数
        try:
            obm = paginator.page(page)
        except PageNotAnInteger:
            obm = paginator.page(1)
        except EmptyPage:
            obm = paginator.page(paginator.num_pages)
        serialize = AutomationTestCaseSerializer(obm, many=True)
        return JsonResponse(data={"data": serialize.data,
                                  "page": page,
                                  "total": total
                                  }, code="999999", msg="成功！")


class AddCase(APIView):
    authentication_classes = (TokenAuthentication,)
    permission_classes = ()

    def parameter_check(self, data):
        """
        校验参数
        :param data:
        :return:
        """
        try:
            # 校验project_id, id类型为int
            if not data["project_id"] or not data["caseName"] or not data["automationGroupLevelFirst_id"]:
                return JsonResponse(code="999996", msg="参数有误！")
            if not isinstance(data["project_id"], int) or not isinstance(data["automationGroupLevelFirst_id"], int):
                return JsonResponse(code="999996", msg="参数有误！")
        except KeyError:
            return JsonResponse(code="999996", msg="参数有误！")

    @extend_schema(
        summary="添加用例",
        description="在项目下创建新的自动化测试用例",
        request=json_body(
            properties={
                "project_id": {"type": "integer", "description": "项目 ID"},
                "caseName": {"type": "string", "description": "用例名称"},
                "automationGroupLevelFirst_id": {"type": "integer", "description": "一级分组 ID"},
            },
            required=["project_id", "caseName", "automationGroupLevelFirst_id"],
        ),
        responses={
            200: create_response(id_field="case_id"),
            **error_responses(),
        },
    )
    def post(self, request):
        """
        添加用例
        :param request:
        :return:
        """
        data = JSONParser().parse(request)
        result = self.parameter_check(data)
        if result:
            return result
        data["user"] = request.user.pk
        try:
            obj = Project.objects.get(id=data["project_id"])
            if not request.user.is_superuser and obj.user.is_superuser:
                return JsonResponse(code="999983", msg="无操作权限！")
        except ObjectDoesNotExist:
            return JsonResponse(code="999995", msg="项目不存在！")
        pro_data = ProjectSerializer(obj)
        if not pro_data.data["status"]:
            return JsonResponse(code="999985", msg="该项目已禁用")
        with transaction.atomic():
            # 在事务内查重，避免并发创建同名用例组
            if AutomationTestCase.objects.filter(caseName=data["caseName"], project=data["project_id"]).exists():
                return JsonResponse(code="999997", msg="存在相同名称！")
            try:
                serialize = AutomationTestCaseDeserializer(data=data)
                if serialize.is_valid():
                    try:
                        if not isinstance(data["automationGroupLevelFirst_id"], int):
                            return JsonResponse(code="999996", msg="参数有误！")
                        obi = AutomationGroupLevelFirst.objects.get(id=data["automationGroupLevelFirst_id"], project=data["project_id"])
                        serialize.save(project=obj, automationGroupLevelFirst=obi, user=User.objects.get(id=data["user"]))
                    except KeyError:
                        serialize.save(project=obj, user=User.objects.get(id=data["user"]))
                    record_dynamic(project=data["project_id"],
                                   _type="新增", operationObject="用例", user=request.user.pk,
                                   data="新增用例\"%s\"" % data["caseName"])
                    return JsonResponse(data={"case_id": serialize.data.get("id")},
                                        code="999999", msg="成功！")
                return JsonResponse(code="999996", msg="参数有误！")
            except:
                return JsonResponse(code="999998", msg="失败！")


class UpdateCase(APIView):
    authentication_classes = (TokenAuthentication,)
    permission_classes = ()

    def parameter_check(self, data):
        """
        校验参数
        :param data:
        :return:
        """
        try:
            # 校验project_id, id类型为int
            if not data["project_id"] or not data["caseName"] or not data["id"] \
                    or not data["automationGroupLevelFirst_id"]:
                return JsonResponse(code="999996", msg="参数有误！")
            if not isinstance(data["project_id"], int) or not isinstance(data["id"], int) \
                    or not isinstance(data["automationGroupLevelFirst_id"], int):
                return JsonResponse(code="999996", msg="参数有误！")
        except KeyError:
            return JsonResponse(code="999996", msg="参数有误！")

    @extend_schema(
        summary="修改用例",
        description="修改现有自动化测试用例的名称和所属分组",
        request=json_body(
            properties={
                "project_id": {"type": "integer", "description": "项目 ID"},
                "id": {"type": "integer", "description": "用例 ID"},
                "caseName": {"type": "string", "description": "用例名称"},
                "automationGroupLevelFirst_id": {"type": "integer", "description": "一级分组 ID"},
            },
            required=["project_id", "id", "caseName", "automationGroupLevelFirst_id"],
        ),
        responses={
            200: simple_response(),
            **error_responses(),
        },
    )
    def post(self, request):
        """
        修改用例
        :param request:
        :return:
        """
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
        try:
            obj = AutomationTestCase.objects.get(id=data["id"], project=data["project_id"])
        except ObjectDoesNotExist:
            return JsonResponse(code="999987", msg="用例不存在！")
        try:
            AutomationGroupLevelFirst.objects.get(id=data["automationGroupLevelFirst_id"], project=data["project_id"])
        except ObjectDoesNotExist:
            return JsonResponse(code="999991", msg="分组不存在！")
        case_name = AutomationTestCase.objects.filter(caseName=data["caseName"], project=data["project_id"]).exclude(id=data["id"])
        if len(case_name):
            return JsonResponse(code="999997", msg="存在相同名称！")
        else:
            serialize = AutomationTestCaseDeserializer(data=data)
            if serialize.is_valid():
                serialize.update(instance=obj, validated_data=data)
                return JsonResponse(code="999999", msg="成功！")
            return JsonResponse(code="999998", msg="失败！")


class DelCase(AddCase):
    authentication_classes = (TokenAuthentication,)
    permission_classes = ()

    def parameter_check(self, data):
        """
        校验参数
        :param data:
        :return:
        """
        try:
            # 校验project_id, id类型为int
            if not data["project_id"] or not data["ids"]:
                return JsonResponse(code="999996", msg="参数有误！")
            if not isinstance(data["project_id"], int) or not isinstance(data["ids"], list):
                return JsonResponse(code="999996", msg="参数有误！")
            for i in data["ids"]:
                if not isinstance(i, int):
                    return JsonResponse(code="999996", msg="参数有误！")
        except KeyError:
            return JsonResponse(code="999996", msg="参数有误！")

    @extend_schema(
        summary="删除用例",
        description="批量删除指定的自动化测试用例",
        request=json_body(
            properties={
                "project_id": {"type": "integer", "description": "项目 ID"},
                "ids": {
                    "type": "array",
                    "description": "用例 ID 列表",
                    "items": {"type": "integer"},
                },
            },
            required=["project_id", "ids"],
        ),
        responses={
            200: simple_response(),
            **error_responses(),
        },
    )
    def post(self, request):
        """
        删除用例
        :param request:
        :return:
        """
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
        for j in data["ids"]:
            obi = AutomationTestCase.objects.filter(id=j, project=data['project_id'])
            if len(obi) != 0:
                name = obi[0].caseName
                obi.delete()
                record_dynamic(project=data["project_id"],
                               _type="删除", operationObject="用例", user=request.user.pk, data="删除用例\"%s\"" % name)
        return JsonResponse(code="999999", msg="成功！")


class ApiList(APIView):
    authentication_classes = (TokenAuthentication,)
    permission_classes = ()

    @extend_schema(
        summary="获取用例接口列表",
        description="分页获取指定测试用例下的 API 接口列表",
        parameters=[
            PROJECT_ID_PARAM,
            CASE_ID_PARAM,
            PAGE_PARAM,
            PAGE_SIZE_PARAM,
        ],
        responses={
            200: list_response("成功", item_example={"id":1,"name":"API接口","httpType":"HTTP","requestType":"GET","apiAddress":"/api/test"}),
            **error_responses(),
        },
    )
    def get(self, request):
        """
        获取用例接口列表
        :param request:
        :return:
        """
        try:
            page_size = int(request.GET.get("page_size", 10))
            page = int(request.GET.get("page", 1))
        except (TypeError, ValueError):
            return JsonResponse(code="999985", msg="page and page_size must be integer！")
        project_id = request.GET.get("project_id")
        case_id = request.GET.get("case_id")
        if not project_id.isdecimal() or not case_id.isdecimal():
            return JsonResponse(code="999996", msg="参数有误！")
        try:
            pro_data = Project.objects.get(id=project_id)
        except ObjectDoesNotExist:
            return JsonResponse(code="999995", msg="项目不存在！")
        pro_data = ProjectSerializer(pro_data)
        if not pro_data.data["status"]:
            return JsonResponse(code="999985", msg="该项目已禁用")
        try:
            AutomationTestCase.objects.get(id=case_id, project=project_id)
        except ObjectDoesNotExist:
            return JsonResponse(code="999987", msg="用例不存在！")
        data = AutomationCaseApi.objects.filter(automationTestCase=case_id).order_by("id")
        paginator = Paginator(data, page_size)  # paginator对象
        total = paginator.count  # 总记录数
        totalnum= len(data)
        try:
            obm = paginator.page(page)
        except PageNotAnInteger:
            obm = paginator.page(1)
        except EmptyPage:
            obm = paginator.page(paginator.num_pages)
        serialize = AutomationCaseApiListSerializer(obm, many=True)
        for i in range(0, len(serialize.data)-1):
            serialize.data[i]["testStatus"] = False
        return JsonResponse(data={"data": serialize.data,
                                  "page": page,
                                  "total": total,
                                  "totalNum":totalnum
                                  }, code="999999", msg="成功！")


class CaseApiInfo(APIView):
    authentication_classes = (TokenAuthentication,)
    permission_classes = ()

    @extend_schema(
        summary="获取用例接口详情",
        description="获取指定用例中某个 API 接口的详细信息",
        parameters=[
            PROJECT_ID_PARAM,
            CASE_ID_PARAM,
            API_ID_PARAM,
        ],
        responses={
            200: success_response("成功", data_example={"id":1,"name":"API接口","httpType":"HTTP","requestType":"GET","apiAddress":"/api/test","headers":[],"requestList":[]}),
            **error_responses(),
        },
    )
    def get(self, request):
        """
        获取接口详细信息
        :param request:
        :return:
        """
        project_id = request.GET.get("project_id")
        case_id = request.GET.get("case_id")
        api_id = request.GET.get("api_id")
        if not project_id.isdecimal() or not api_id.isdecimal() or not case_id.isdecimal():
            return JsonResponse(code="999996", msg="参数有误！")
        try:
            pro_data = Project.objects.get(id=project_id)
        except ObjectDoesNotExist:
            return JsonResponse(code="999995", msg="项目不存在！")
        pro_data = ProjectSerializer(pro_data)
        if not pro_data.data["status"]:
            return JsonResponse(code="999985", msg="该项目已禁用")
        try:
            AutomationTestCase.objects.get(id=case_id, project=project_id)
        except ObjectDoesNotExist:
            return JsonResponse(code="999987", msg="用例不存在！")
        try:
            obm = AutomationCaseApi.objects.get(id=api_id, automationTestCase=case_id)
        except ObjectDoesNotExist:
            return JsonResponse(code="999990", msg="接口不存在！")
        data = AutomationCaseApiSerializer(obm).data
        try:
            name = AutomationResponseJson.objects.get(automationCaseApi=api_id, type="Regular")
            data["RegularParam"] = name.name
        except ObjectDoesNotExist:
            pass
        return JsonResponse(data=data, code="999999", msg="成功！")


class AddOldApi(APIView):
    authentication_classes = (TokenAuthentication,)
    permission_classes = ()

    def parameter_check(self, data):
        """
        校验参数
        :param data:
        :return:
        """
        try:
            # 校验project_id, id类型为int
            if not data["project_id"] or not data["case_id"] or not data["api_ids"]:
                return JsonResponse(code="999996", msg="参数有误！")
            if not isinstance(data["project_id"], int) or \
                    not isinstance(data["api_ids"], list) or not isinstance(data["case_id"], int):
                return JsonResponse(code="999996", msg="参数有误！")
            for i in data["api_ids"]:
                if not isinstance(i, int):
                    return JsonResponse(code="999996", msg="参数有误！")
        except KeyError:
            return JsonResponse(code="999996", msg="参数有误！")

    @extend_schema(
        summary="用例下新增已有 API",
        description="将已有的 API 接口批量添加到测试用例中",
        request=json_body(
            properties={
                "project_id": {"type": "integer", "description": "项目 ID"},
                "case_id": {"type": "integer", "description": "用例 ID"},
                "api_ids": {
                    "type": "array",
                    "description": "已有接口 ID 列表",
                    "items": {"type": "integer"},
                },
            },
            required=["project_id", "case_id", "api_ids"],
        ),
        responses={
            200: simple_response(),
            **error_responses(),
        },
    )
    def post(self, request):
        """
        用例下新增已有的api接口
        :param request:
        :return:
        """
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
        try:
            obj = AutomationTestCase.objects.get(id=data["case_id"], project=data["project_id"])
        except ObjectDoesNotExist:
            return JsonResponse(code="999987", msg="用例不存在！")
        for i in data["api_ids"]:
            try:
                api_data = ApiInfoSerializer(ApiInfo.objects.get(id=i, project=data["project_id"])).data
            except ObjectDoesNotExist:
                continue
            with transaction.atomic():
                api_data["automationTestCase_id"] = obj.pk
                api_serialize = AutomationCaseApiDeserializer(data=api_data)
                if api_serialize.is_valid():
                    api_serialize.save(automationTestCase=obj)
                    case_api = api_serialize.data.get("id")
                    if api_data["requestParameterType"] == "form-data":
                        if api_data["requestParameter"]:
                            for j in api_data["requestParameter"]:
                                if j["name"]:
                                    AutomationParameter(automationCaseApi=AutomationCaseApi.objects.get(id=case_api),
                                                        name=j["name"], value=j["value"], interrelate=False).save()
                    else:
                        if api_data["requestParameterRaw"]:
                            logger.info(f'请求参数：{api_data["requestParameterRaw"]["data"]}')
                            AutomationParameterRaw(automationCaseApi=AutomationCaseApi.objects.get(id=case_api),
                                                   data=str(api_data["requestParameterRaw"]["data"])).save()
                    if api_data.get("headers"):
                        for n in api_data["headers"]:
                            if n["name"]:
                                AutomationHead(automationCaseApi=AutomationCaseApi.objects.get(id=case_api),
                                               name=n["name"], value=n["value"], interrelate=False).save()
                    case_name = AutomationTestCaseSerializer(obj).data["caseName"]
                    record_dynamic(project=data["project_id"],
                                   _type="新增", operationObject="用例接口", user=request.user.pk,
                                   data="用例“%s”新增接口\"%s\"" % (case_name, api_serialize.data.get("name")))

        return JsonResponse(code="999999", msg="成功！")


class AddNewApi(APIView):
    authentication_classes = (TokenAuthentication,)
    permission_classes = ()

    def parameter_check(self, data):
        """
        校验参数
        :param data:
        :return:
        """
        try:
            # 校验project_id, id类型为int
            if not data["project_id"] or not data["automationTestCase_id"] or not data["name"] or not data["httpType"]\
                    or not data["requestType"] or not data["apiAddress"] or not data["requestParameterType"]\
                    or not data["examineType"]:
                return JsonResponse(code="999996", msg="参数有误！")
            if not isinstance(data["project_id"], int) or not isinstance(data["automationTestCase_id"], int):
                return JsonResponse(code="999996", msg="参数有误！")
            if data["httpType"] not in ["HTTP", "HTTPS"]:
                return JsonResponse(code="999996", msg="参数有误！")
            if data["requestType"] not in ["POST", "GET", "PUT", "DELETE", "DUBBO"]:
                return JsonResponse(code="999996", msg="参数有误！")
            if data["requestParameterType"] not in ["form-data", "raw", "Restful"]:
                return JsonResponse(code="999996", msg="参数有误！")
            if data["examineType"] not in ["no_check", "only_check_status", "json", "entirely_check", "Regular_check"]:
                return JsonResponse(code="999996", msg="参数有误！")
            if data["httpCode"]:
                if data["httpCode"] not in ["200", "404", "400", "502", "500", "302"]:
                    return JsonResponse(code="999996", msg="参数有误！")
            if not isinstance(data['formatRaw'], bool):
                return JsonResponse(code="999996", msg="参数有误！")
        except KeyError:
            return JsonResponse(code="999996", msg="参数有误！")

    @extend_schema(
        summary="用例下新增 API 接口",
        description="在测试用例下创建全新的 API 接口",
        request=json_body(
            properties={
                "project_id": {"type": "integer", "description": "项目 ID"},
                "automationTestCase_id": {"type": "integer", "description": "测试用例 ID"},
                "name": {"type": "string", "description": "接口名称"},
                "httpType": {"type": "string", "description": "协议类型", "enum": ["HTTP", "HTTPS", "DUBBO"]},
                "requestType": {"type": "string", "description": "请求方式", "enum": ["POST", "GET", "PUT", "DELETE", "DUBBO"]},
                "apiAddress": {"type": "string", "description": "接口地址"},
                "requestParameterType": {"type": "string", "description": "参数类型", "enum": ["form-data", "raw", "Restful"]},
                "examineType": {"type": "string", "description": "校验类型", "enum": ["no_check", "only_check_status", "json", "entirely_check", "Regular_check"]},
                "httpCode": {"type": "string", "description": "期望 HTTP 状态码（可选）", "enum": ["200", "404", "400", "502", "500", "302"]},
                "formatRaw": {"type": "boolean", "description": "是否格式化 raw 数据"},
                "headDict": {"type": "array", "description": "请求头列表"},
                "requestList": {"type": "array", "description": "请求参数列表"},
                "jsonCheckData": {"type": "array", "description": "JSON 校验数据"},
                "responseData": {"type": "string", "description": "响应数据"},
                "RegularParam": {"type": "string", "description": "正则参数"},
            },
            required=["project_id", "automationTestCase_id", "name", "httpType", "requestType", "apiAddress", "requestParameterType", "examineType", "formatRaw"],
        ),
        responses={
            200: create_response(id_field="api_id"),
            **error_responses(),
        },
    )
    def post(self, request):
        """
        用例下新增新的api接口
        :param request:
        :return:
        """
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
        try:
            obj = AutomationTestCase.objects.get(id=data["automationTestCase_id"], project=data["project_id"])
        except ObjectDoesNotExist:
            return JsonResponse(code="999987", msg="用例不存在！")
        api_name = AutomationCaseApi.objects.filter(name=data["name"], automationTestCase=data["automationTestCase_id"])
        if len(api_name):
            return JsonResponse(code="999997", msg="存在相同名称！")
        with transaction.atomic():
            sid = transaction.savepoint()
            try:
                serialize = AutomationCaseApiDeserializer(data=data)
                if serialize.is_valid():
                    serialize.save(automationTestCase=obj)
                    api_id = serialize.data.get("id")
                    api_obj = AutomationCaseApi.objects.get(id=api_id)
                    if len(data.get("headDict")):
                        for i in data["headDict"]:
                            if i["name"]:
                                i["automationCaseApi_id"] = api_id
                                head_serialize = AutomationHeadDeserializer(data=i)
                                if head_serialize.is_valid():
                                    head_serialize.save(automationCaseApi=api_obj)
                    if data["requestParameterType"] == "form-data":
                        if len(data.get("requestList")):
                            for i in data.get("requestList"):
                                if i.get("name"):
                                    i["automationCaseApi_id"] = api_id
                                    param_serialize = AutomationParameterDeserializer(data=i)
                                    if param_serialize.is_valid():
                                        param_serialize.save(automationCaseApi=api_obj)
                    else:
                        if len(data.get("requestList")):
                            AutomationParameterRaw(automationCaseApi=api_obj,
                                                   data=data["requestList"]).save()
                    if data.get("examineType") == "json":
                        # json校验数据存储
                        try:
                            logger.info(f'json校验数据存储:{data["jsonCheckData"]}')
                            jsonCheckData = data.get("jsonCheckData")
                            if isinstance(jsonCheckData, list) and len(jsonCheckData):
                                for i in jsonCheckData:
                                    serialize_jsoncheck = AutomationJsonCkeckserializer(data=i)
                                    if serialize_jsoncheck.is_valid():
                                        serialize_jsoncheck.save(automationCaseApi=api_obj)
                                    else:
                                        transaction.savepoint_rollback(sid)
                                        return JsonResponse(code="999998", msg=serialize_jsoncheck.errors)
                        except Exception as E:
                            logger.info(f'json校验数据序列化失败：{E}')
                            return JsonResponse(code="999998", msg="失败！")
                    elif data.get("examineType") == 'Regular_check':
                        if data.get("RegularParam"):
                            AutomationResponseJson(automationCaseApi=api_obj,
                                                   name=data["RegularParam"],
                                                   tier='<response[Regular][%s]["%s"]' % (api_id, data["responseData"]),
                                                   type='Regular').save()
                    return JsonResponse(data={"api_id": api_id}, code="999999", msg="成功！")
                return JsonResponse(code="999998", msg=serialize.errors)
            except Exception:
                transaction.savepoint_rollback(sid)
                return JsonResponse(code="999998", msg="失败！")


class GetCorrelationResponse(APIView):
    authentication_classes = (TokenAuthentication,)
    permission_classes = ()

    @extend_schema(
        summary="获取关联接口响应数据",
        description="获取测试用例中指定接口之前的所有接口响应数据（用于关联参数传递）",
        parameters=[
            PROJECT_ID_PARAM,
            CASE_ID_PARAM,
            OpenApiParameter("api_id", str, description="当前接口 ID（可选，获取之前的接口响应）", required=False),
        ],
        responses={
            200: success_response("成功", data_example=[{"name":"前置接口","responseData":"{...}"}]),
            **error_responses(),
        },
    )
    def get(self, request):
        """
        获取关联接口数据
        :param request:
        :return:
        """
        project_id = request.GET.get("project_id")
        case_id = request.GET.get("case_id")
        api_id = request.GET.get("api_id")
        if not project_id.isdecimal() or not case_id.isdecimal():
            return JsonResponse(code="999996", msg="参数有误！")
        try:
            pro_data = Project.objects.get(id=project_id)
        except ObjectDoesNotExist:
            return JsonResponse(code="999995", msg="项目不存在！")
        pro_data = ProjectSerializer(pro_data)
        if not pro_data.data["status"]:
            return JsonResponse(code="999985", msg="该项目已禁用")
        try:
            AutomationTestCase.objects.get(id=case_id, project=project_id)
        except ObjectDoesNotExist:
            return JsonResponse(code="999987", msg="用例不存在！")
        if api_id:
            data = CorrelationDataSerializer(AutomationCaseApi.objects.filter(automationTestCase=case_id,
                                                                              id__lt=api_id), many=True).data
        else:
            data = CorrelationDataSerializer(AutomationCaseApi.objects.filter(automationTestCase=case_id),
                                             many=True).data
        return JsonResponse(code="999999", msg="成功！", data=data)


class UpdateApi(APIView):
    authentication_classes = (TokenAuthentication,)
    permission_classes = ()

    def parameter_check(self, data):
        """
        校验参数
        :param data:
        :return:
        """
        try:
            # 校验project_id, id类型为int
            if not data["project_id"] or not data["automationTestCase_id"] or not data["name"] or not data["httpType"]\
                    or not data["requestType"] or not data["apiAddress"] or not data["requestParameterType"]\
                    or not data["examineType"] or not data["id"]:
                return JsonResponse(code="999996", msg="参数有误！")
            if not isinstance(data["project_id"], int) or not isinstance(data["automationTestCase_id"], int):
                return JsonResponse(code="999996", msg="参数有误！")
            if data["httpType"] not in ["HTTP", "HTTPS","DUBBO"]:
                return JsonResponse(code="999996", msg="参数有误！")
            if data["requestType"] not in ["POST", "GET", "PUT", "DELETE","DUBBO"]:
                return JsonResponse(code="999996", msg="参数有误！")
            if data["requestParameterType"] not in ["form-data", "raw", "Restful"]:
                return JsonResponse(code="999996", msg="参数有误！")
            if data["examineType"] not in ["no_check", "only_check_status", "json", "entirely_check", "Regular_check"]:
                return JsonResponse(code="999996", msg="参数有误！")
            if data["httpCode"]:
                if data["httpCode"] not in ["200", "404", "400", "502", "500", "302"]:
                    return JsonResponse(code="999996", msg="参数有误！")
            if not isinstance(data['formatRaw'], bool):
                return JsonResponse(code="999996", msg="参数有误！")
        except KeyError:
            return JsonResponse(code="999996", msg="参数有误！")

    @extend_schema(
        summary="修改用例 API 接口",
        description="修改测试用例中某个 API 接口的配置",
        request=json_body(
            properties={
                "project_id": {"type": "integer", "description": "项目 ID"},
                "id": {"type": "integer", "description": "接口记录 ID"},
                "automationTestCase_id": {"type": "integer", "description": "测试用例 ID"},
                "name": {"type": "string", "description": "接口名称"},
                "httpType": {"type": "string", "description": "协议类型", "enum": ["HTTP", "HTTPS", "DUBBO"]},
                "requestType": {"type": "string", "description": "请求方式", "enum": ["POST", "GET", "PUT", "DELETE", "DUBBO"]},
                "apiAddress": {"type": "string", "description": "接口地址"},
                "requestParameterType": {"type": "string", "description": "参数类型", "enum": ["form-data", "raw", "Restful"]},
                "examineType": {"type": "string", "description": "校验类型", "enum": ["no_check", "only_check_status", "json", "entirely_check", "Regular_check"]},
                "httpCode": {"type": "string", "description": "期望 HTTP 状态码", "enum": ["200", "404", "400", "502", "500", "302"]},
                "formatRaw": {"type": "boolean", "description": "是否格式化 raw 数据"},
                "headDict": {"type": "array", "description": "请求头列表"},
                "requestList": {"type": "array", "description": "请求参数列表"},
                "jsonCheckData": {"type": "array", "description": "JSON 校验数据"},
                "responseData": {"type": "string", "description": "响应数据"},
                "RegularParam": {"type": "string", "description": "正则参数"},
            },
            required=["project_id", "id", "automationTestCase_id", "name", "httpType", "requestType", "apiAddress", "requestParameterType", "examineType", "formatRaw"],
        ),
        responses={
            200: simple_response(),
            **error_responses(),
        },
    )
    def post(self, request):
        """
        用例下修改api接口
        :param request:
        :return:
        """
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
        try:
            obi = AutomationTestCase.objects.get(id=data["automationTestCase_id"], project=data["project_id"])
        except ObjectDoesNotExist:
            return JsonResponse(code="999987", msg="用例不存在！")
        try:
            obj = AutomationCaseApi.objects.get(id=data["id"], automationTestCase=data["automationTestCase_id"])
        except ObjectDoesNotExist:
            return JsonResponse(code="999990", msg="接口不存在！")
        api_name = AutomationCaseApi.objects.filter(name=data["name"], automationTestCase=data["automationTestCase_id"]).exclude(id=data["id"])
        if len(api_name):
            return JsonResponse(code="999997", msg="存在相同名称！")
        with transaction.atomic():
            serialize = AutomationCaseApiDeserializer(data=data)
            if serialize.is_valid():
                serialize.update(instance=obj, validated_data=data)
                header = Q()
                if len(data.get("headDict")):
                    for i in data["headDict"]:
                        if i.get("automationCaseApi") and i.get("id"):
                            header = header | Q(id=i["id"])
                            if i["name"]:
                                head_serialize = AutomationHeadDeserializer(data=i)
                                if head_serialize.is_valid():
                                    i["automationCaseApi"] = AutomationCaseApi.objects.get(id=i["automationCaseApi"])
                                    head_serialize.update(instance=AutomationHead.objects.get(id=i["id"]), validated_data=i)
                        else:
                            if i.get("name"):
                                i["automationCaseApi"] = data['id']
                                head_serialize = AutomationHeadDeserializer(data=i)
                                if head_serialize.is_valid():
                                    head_serialize.save(automationCaseApi=AutomationCaseApi.objects.get(id=data["id"]))
                                    header = header | Q(id=head_serialize.data.get("id"))
                AutomationHead.objects.exclude(header).filter(automationCaseApi=data["id"]).delete()
                api_param = Q()
                api_param_raw = Q()
                if len(data.get("requestList")):
                    if data["requestParameterType"] == "form-data":
                        AutomationParameterRaw.objects.filter(automationCaseApi=data["id"]).delete()
                        for i in data["requestList"]:
                            if i.get("automationCaseApi") and i.get("id"):
                                api_param = api_param | Q(id=i["id"])
                                if i["name"]:
                                    param_serialize = AutomationParameterDeserializer(data=i)
                                    if param_serialize.is_valid():
                                        i["automationCaseApi"] = AutomationCaseApi.objects.get(id=i["automationCaseApi"])
                                        param_serialize.update(instance=AutomationParameter.objects.get(id=i["id"]),
                                                               validated_data=i)
                            else:
                                if i.get("name"):
                                    i["automationCaseApi"] = data['id']
                                    param_serialize = AutomationParameterDeserializer(data=i)
                                    if param_serialize.is_valid():
                                        param_serialize.save(automationCaseApi=AutomationCaseApi.objects.get(id=data["id"]))
                                        api_param = api_param | Q(id=param_serialize.data.get("id"))
                    else:
                        try:
                            obj = AutomationParameterRaw.objects.get(automationCaseApi=data["id"])
                            obj.data = data["requestList"]
                            obj.save()
                        except ObjectDoesNotExist:
                            obj = AutomationParameterRaw(automationCaseApi=AutomationCaseApi.objects.get(id=data['id']), data=data["requestList"])
                            obj.save()
                        api_param_raw = api_param_raw | Q(id=obj.id)
                AutomationParameter.objects.exclude(api_param).filter(automationCaseApi=data["id"]).delete()
                AutomationParameterRaw.objects.exclude(api_param_raw).filter(automationCaseApi=data["id"]).delete()
                api_id = AutomationCaseApi.objects.get(id=data["id"])
                AutomationResponseJson.objects.filter(automationCaseApi=api_id).filter(automationCaseApi=data["id"]).delete()
                if data.get("examineType") == "json":
                   #json校验数据存储
                    jsonCheck = Q()
                    try:
                        logger.info(f'json校验数据存储:{data["jsonCheckData"]}')
                        jsonCheckData = data.get("jsonCheckData")
                        if isinstance(jsonCheckData,list) and len(jsonCheckData):
                            for i in jsonCheckData:
                                if i.get('name') and i.get('id'):
                                    jsonCheck = jsonCheck | Q(id=i.get('id'))
                                    i['automationCaseApi'] = api_id
                                    serialize_jsoncheck = AutomationJsonCkeckserializer(data=i)
                                    if serialize_jsoncheck.is_valid():
                                        serialize_jsoncheck.update(instance=AutomationJsonCheck.objects.get(id=i['id']), validated_data=i)
                                elif i.get('name'):
                                    serialize_jsoncheck = AutomationJsonCkeckserializer(data=i)
                                    if serialize_jsoncheck.is_valid():
                                        serialize_jsoncheck.save(automationCaseApi=api_id)
                                        jsonCheck = jsonCheck | Q(id=serialize_jsoncheck.data.get('id'))
                            AutomationResponseJson.objects.filter(automationCaseApi=api_id).delete()
                            AutomationJsonCheck.objects.exclude(jsonCheck).filter(automationCaseApi=api_id).delete()

                        else:
                            return JsonResponse(code="999998", msg="校验内容不能为空或数据类型不是数组！")
                    except Exception as E:
                        logger.info(f'json校验数据序列化失败：{E}')
                        return JsonResponse(code="999998", msg="失败！")
                elif data.get("examineType") == 'Regular_check':
                    if data.get("RegularParam"):
                        AutomationResponseJson(automationCaseApi=api_id,
                                               name=data["RegularParam"],
                                               tier='<response[Regular][%s]["%s"]' % (api_id, data["responseData"]),
                                               type='Regular').save()
                record_dynamic(project=data["project_id"],
                               _type="修改", operationObject="用例接口", user=request.user.pk,
                               data="用例“%s”修改接口\"%s\"" % (obi.caseName, data["name"]))
                return JsonResponse(code="999999", msg="成功！")
            return JsonResponse(code="999998", msg="失败！")


class DelApi(APIView):
    authentication_classes = (TokenAuthentication,)
    permission_classes = ()

    def parameter_check(self, data):
        """
        校验参数
        :param data:
        :return:
        """
        try:
            # 校验project_id, id类型为int
            if not data["project_id"] or not data["case_id"] or not data["ids"]:
                return JsonResponse(code="999996", msg="参数有误！")
            if not isinstance(data["project_id"], int) or not isinstance(data["case_id"], int) \
                    or not isinstance(data["ids"], list):
                return JsonResponse(code="999996", msg="参数有误！")
            for i in data["ids"]:
                if not isinstance(i, int):
                    return JsonResponse(code="999996", msg="参数有误！")
        except KeyError:
            return JsonResponse(code="999996", msg="参数有误！")

    @extend_schema(
        summary="删除用例 API 接口",
        description="批量删除测试用例下的 API 接口",
        request=json_body(
            properties={
                "project_id": {"type": "integer", "description": "项目 ID"},
                "case_id": {"type": "integer", "description": "用例 ID"},
                "ids": {
                    "type": "array",
                    "description": "接口记录 ID 列表",
                    "items": {"type": "integer"},
                },
            },
            required=["project_id", "case_id", "ids"],
        ),
        responses={
            200: simple_response(),
            **error_responses(),
        },
    )
    def post(self, request):
        """
        删除用例下的 API 接口
        :param request:
        :return:
        """
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
        try:
            obj = AutomationTestCase.objects.get(id=data["case_id"], project=data["project_id"])
        except ObjectDoesNotExist:
            return JsonResponse(code="999987", msg="用例不存在！")
        for j in data["ids"]:
            obi = AutomationCaseApi.objects.filter(id=j, automationTestCase=data["case_id"])
            if len(obi) != 0:
                name = obi[0].name
                obi.delete()
                record_dynamic(project=data["project_id"],
                               _type="删除", operationObject="用例接口",
                               user=request.user.pk, data="删除用例\"%s\"的接口\"%s\"" % (obj.caseName, name))
        return JsonResponse(code="999999", msg="成功！")


class StartTest(APIView):
    authentication_classes = (TokenAuthentication,)
    permission_classes = ()

    def parameter_check(self, data):
        """
        校验参数
        :param data:
        :return:
        """
        try:
            # 校验project_id, id类型为int
            if not data["project_id"] or not data["case_id"] or not data["id"] or not data["host_id"]:
                return JsonResponse(code="999996", msg="参数有误！")
            if not isinstance(data["project_id"], int) or not isinstance(data["case_id"], int) \
                    or not isinstance(data["id"], list) or not isinstance(data["host_id"], int):
                return JsonResponse(code="999996", msg="参数有误！")
        except KeyError:
            return JsonResponse(code="999996", msg="参数有误！")

    @extend_schema(
        summary="执行测试用例",
        description="启动指定测试用例中选中的 API 接口测试",
        request=json_body(
            properties={
                "project_id": {"type": "integer", "description": "项目 ID"},
                "case_id": {"type": "integer", "description": "用例 ID"},
                "id": {
                    "type": "array",
                    "description": "要测试的 API 接口记录 ID 列表",
                    "items": {"type": "integer"},
                },
                "host_id": {"type": "integer", "description": "目标 Host ID"},
            },
            required=["project_id", "case_id", "id", "host_id"],
        ),
        responses={
            200: success_response("测试结果", data_example={"result": []}),
            **error_responses(),
        },
    )
    @clock
    def post(self, request):
        """
        执行测试用例
        :param request:
        :return:
        """
        data = JSONParser().parse(request)
        result = self.parameter_check(data)
        if result:
            return result
        try:
            pro_data = Project.objects.get(id=data["project_id"])
        except ObjectDoesNotExist:
            return JsonResponse(code="999995", msg="项目不存在！")
        pro_data = ProjectSerializer(pro_data)
        if not pro_data.data["status"]:
            return JsonResponse(code="999985", msg="该项目已禁用")
        try:
            obi = AutomationTestCase.objects.get(id=data["case_id"], project=data["project_id"])
        except ObjectDoesNotExist:
            return JsonResponse(code="999987", msg="用例不存在！")
        try:
            GlobalHost.objects.get(id=data["host_id"], project=data["project_id"])
        except ObjectDoesNotExist:
            return JsonResponse(code="999992", msg="host不存在！")
        for i in data['id']:
            try:
                obj = AutomationCaseApi.objects.get(id=i, automationTestCase=data["case_id"])
            except ObjectDoesNotExist:
                return JsonResponse(code="999990", msg=f"caseid{i}不存在！")
            AutomationTestResult.objects.filter(automationCaseApi=i).delete()
            record_dynamic(project=data["project_id"],
                           _type="测试", operationObject="用例接口",
                           user=request.user.pk, data="测试用例“%s”接口\"%s\"" % (obi.caseName, obj.name))
        # ── Build step→api_id mapping for $N.field syntax ────────────
        step_id_map = {i + 1: api_id for i, api_id in enumerate(data["id"])}
        set_step_id_map(step_id_map)

        # ── Sequential execution for interrelate support ──────────────
        results = []
        for api_id in data["id"]:
            try:
                result = test_api((data["host_id"], data["case_id"], data["project_id"], api_id))
                results.append(result)
            except Exception as E:
                logger.error("API %s execution error: %s", api_id, E)
                results.append({"success": "false", "case_id": api_id})
        return JsonResponse(data={
            "result": results
        }, code="999999", msg="成功！")

class StartTestSequential(APIView):
    """顺序执行测试用例（支持步骤间参数关联）。

    与 StartTest 不同，此接口逐个执行 API 用例（不使用线程池并行），
    确保前一步的执行结果在后一步执行时已保存在数据库中，
    从而支持 interrelate 参数关联机制（{api_id}|{json_path}）。
    """

    authentication_classes = (TokenAuthentication,)
    permission_classes = ()

    def parameter_check(self, data):
        """校验参数（与 StartTest 相同）"""
        try:
            if not data["project_id"] or not data["case_id"] or not data["id"] or not data["host_id"]:
                return JsonResponse(code="999996", msg="参数有误！")
            if not isinstance(data["project_id"], int) or not isinstance(data["case_id"], int) \
                    or not isinstance(data["id"], list) or not isinstance(data["host_id"], int):
                return JsonResponse(code="999996", msg="参数有误！")
        except KeyError:
            return JsonResponse(code="999996", msg="参数有误！")

    @extend_schema(
        summary="顺序执行测试用例（场景测试）",
        description="按顺序逐个执行 API 测试用例，支持步骤间参数关联（interrelate）。"
                    "适用于多接口场景测试，前一步的响应数据可供后一步使用。",
        request=json_body(
            properties={
                "project_id": {"type": "integer", "description": "项目 ID"},
                "case_id": {"type": "integer", "description": "用例组 ID"},
                "id": {
                    "type": "array",
                    "description": "要测试的 API 接口记录 ID 列表（按顺序执行）",
                    "items": {"type": "integer"},
                },
                "host_id": {"type": "integer", "description": "目标 Host ID"},
            },
            required=["project_id", "case_id", "id", "host_id"],
        ),
        responses={
            200: success_response("测试结果", data_example={"result": []}),
            **error_responses(),
        },
    )
    @clock
    def post(self, request):
        """顺序执行测试用例（支持步骤间参数关联）"""
        data = JSONParser().parse(request)
        result = self.parameter_check(data)
        if result:
            return result
        try:
            pro_data = Project.objects.get(id=data["project_id"])
        except ObjectDoesNotExist:
            return JsonResponse(code="999995", msg="项目不存在！")
        pro_data = ProjectSerializer(pro_data)
        if not pro_data.data["status"]:
            return JsonResponse(code="999985", msg="该项目已禁用")
        try:
            obi = AutomationTestCase.objects.get(id=data["case_id"], project=data["project_id"])
        except ObjectDoesNotExist:
            return JsonResponse(code="999987", msg="用例不存在！")
        try:
            host_obj = GlobalHost.objects.get(id=data["host_id"], project=data["project_id"])
        except ObjectDoesNotExist:
            return JsonResponse(code="999992", msg="host不存在！")

        # Validate API IDs and clean old results
        for api_id in data["id"]:
            try:
                obj = AutomationCaseApi.objects.get(id=api_id, automationTestCase=data["case_id"])
            except ObjectDoesNotExist:
                return JsonResponse(code="999990", msg=f"caseid {api_id} 不存在！")
            AutomationTestResult.objects.filter(automationCaseApi=api_id).delete()
            record_dynamic(project=data["project_id"],
                           _type="测试", operationObject="用例接口",
                           user=request.user.pk,
                           data="场景测试用例\"%s\"接口\"%s\"" % (obi.caseName, obj.name))

        # ── Build step→api_id mapping for $N.field syntax ────────────
        step_id_map = {i + 1: api_id for i, api_id in enumerate(data["id"])}
        set_step_id_map(step_id_map)

        # ── Sequential execution (NOT ThreadPoolExecutor) ─────────────
        format_start_time = datetime.now().strftime('%Y-%m-%d %H:%M:%S')
        results = []

        for api_id in data["id"]:
            try:
                result_status = test_api_sequential(
                    host=host_obj.host,
                    case_id=data["case_id"],
                    _id=api_id,
                    time=format_start_time,
                )
                # Enrich with response details from the result table
                response_code = ""
                response_data = ""
                try:
                    latest = (
                        AutomationCaseTestResult.objects
                        .filter(automationCaseApi=api_id)
                        .order_by("-testTime")
                        .first()
                    )
                    if latest:
                        response_code = str(latest.httpStatus or "")
                        response_data = (latest.responseData or "")[:500]
                except Exception:
                    pass

                results.append({
                    "case_id": api_id,
                    "success": result_status == "success",
                    "status": result_status,
                    "response_code": response_code,
                    "response_data": response_data,
                })
                logger.info(
                    "Scenario step api_id=%s completed with status=%s, http=%s",
                    api_id, result_status, response_code,
                )
            except Exception as e:
                logger.error("Scenario step api_id=%s failed with error: %s", api_id, e)
                results.append({
                    "case_id": api_id,
                    "success": False,
                    "status": "ERROR",
                    "detail": str(e),
                    "response_code": "",
                    "response_data": "",
                })

        return JsonResponse(data={"result": results}, code="999999", msg="成功！")


class AddTimeTask(APIView):
    authentication_classes = (TokenAuthentication,)
    permission_classes = ()

    def parameter_check(self, data):
        """
        校验参数
        :param data:
        :return:
        """
        try:
            # 校验project_id, id类型为int
            if not data["project_id"] or not data["name"] or not data["type"] or \
                    not data["Host_id"] or not data["startTime"] or not data["endTime"]:
                return JsonResponse(code="999996", msg="参数有误！")
            if not isinstance(data["project_id"], int) or not isinstance(data["Host_id"], int):
                return JsonResponse(code="999996", msg="参数有误！")
            if data["type"] not in ["circulation", "timing"]:
                return JsonResponse(code="999996", msg="参数有误！")
            try:
                start_time = datetime.strptime(data["startTime"], "%Y-%m-%d %H:%M:%S")
                end_time = datetime.strptime(data["endTime"], "%Y-%m-%d %H:%M:%S")
                now_time = datetime.strptime(str(datetime.now()).split('.')[0], "%Y-%m-%d %H:%M:%S")
                if start_time > end_time or start_time <now_time:
                    return JsonResponse(code="999996", msg="时间参数有误！")
            except ValueError:
                return JsonResponse(code="999996", msg="参数有误！")
        except KeyError:
            return JsonResponse(code="999996", msg="参数有误！")

    @extend_schema(
        summary="添加定时测试任务",
        description="创建循环或定时执行测试用例的任务",
        request=json_body(
            properties={
                "project_id": {"type": "integer", "description": "项目 ID"},
                "name": {"type": "string", "description": "任务名称"},
                "type": {"type": "string", "description": "任务类型", "enum": ["circulation", "timing"]},
                "Host_id": {"type": "integer", "description": "目标 Host ID"},
                "startTime": {"type": "string", "description": "开始时间 (yyyy-MM-dd HH:mm:ss)"},
                "endTime": {"type": "string", "description": "结束时间 (yyyy-MM-dd HH:mm:ss)"},
                "frequency": {"type": "integer", "description": "执行频率（循环任务必填）"},
                "unit": {"type": "string", "description": "频率单位", "enum": ["m", "h", "d", "w"]},
            },
            required=["project_id", "name", "type", "Host_id", "startTime", "endTime"],
        ),
        responses={
            200: create_response(id_field="task_id"),
            **error_responses(),
        },
    )
    def post(self, request):
        """
        添加测试任务
        :param request:
        :return:
        """
        data = JSONParser().parse(request)
        result = self.parameter_check(data)
        if result:
            return result
        try:
            pro_id = Project.objects.get(id=data["project_id"])
            if not request.user.is_superuser and pro_id.user.is_superuser:
                return JsonResponse(code="999983", msg="无操作权限！")
        except ObjectDoesNotExist:
            return JsonResponse(code="999995", msg="项目不存在！")
        pro_data = ProjectSerializer(pro_id)
        #print(pro_data)
        start_time = data["startTime"]
        end_time = data["endTime"]
        if not pro_data.data["status"]:
            return JsonResponse(code="999985", msg="该项目已禁用")
        data["startTime"] = datetime.strptime(data["startTime"], "%Y-%m-%d %H:%M:%S")
        data["endTime"] = datetime.strptime(data["endTime"], "%Y-%m-%d %H:%M:%S")
        try:
            host_data = GlobalHost.objects.get(id=data["Host_id"], project=data["project_id"])
        except ObjectDoesNotExist:
            return JsonResponse(code="999992", msg="host不存在！")
        task_name = AutomationTestTask.objects.filter(name=data["name"])
        if len(task_name):
            return JsonResponse(code="999997", msg="存在相同名称！")
        if data["type"] == "circulation":
            if not data["frequency"]:
                return JsonResponse(code="999996", msg="参数有误！")
            if not isinstance(data["frequency"], int):
                return JsonResponse(code="999996", msg="参数有误！")
            if data["unit"] not in ["m", "h", "d", "w"]:
                return JsonResponse(code="999996", msg="参数有误！")
            try:
                serialize = AutomationTestTaskDeserializer(data=data)
                if serialize.is_valid():
                    serialize.save(project=pro_id, Host=host_data)
                    task_id = AutomationTestTaskSerializer(AutomationTestTask.objects.get(name=data["name"])).data['id']
                    print(task_id)
                else:
                    return JsonResponse(code="999996", msg="参数有误！")
            except ObjectDoesNotExist:
                serialize = AutomationTestTaskDeserializer(data=data)
                if serialize.is_valid():
                    serialize.save(project=pro_id, Host=host_data)
                    task_id = AutomationTestTaskSerializer(AutomationTestTask.objects.get(name=data["name"])).data['id']
                else:
                    return JsonResponse(code="999996", msg="参数有误！")
            record_dynamic(project=data["project_id"],
                           _type="新增", operationObject="任务",
                           user=request.user.pk, data="新增循环任务\"%s\"" % data["name"])
            creatTask(host_id=data["Host_id"], _type=data["type"], project=str(data["project_id"]),
                start_time=start_time, end_time=end_time, frequency=data["frequency"], unit=data["unit"],taskName=data['name'])

        else:
            try:
                serialize = AutomationTestTaskDeserializer(data=data)
                if serialize.is_valid():
                    serialize.save(project=pro_id,Host=host_data)
                    task_id = AutomationTestTaskSerializer(AutomationTestTask.objects.get(name=data["name"])).data['id']
                else:
                    return JsonResponse(code="999996", msg="参数有误！")
            except ObjectDoesNotExist:
                serialize = AutomationTestTaskDeserializer(data=data)
                if serialize.is_valid():
                    serialize.save(project=pro_id, Host=host_data)
                    task_id = AutomationTestTaskSerializer(AutomationTestTask.objects.get(name=data["name"])).data['id']
                else:
                    return JsonResponse(code="999996", msg="参数有误！")
            record_dynamic(project=data["project_id"],
                           _type="新增", operationObject="任务",
                           user=request.user.pk, data="新增定时任务\"%s\"" % data["name"])
            creatTask(host_id=data["Host_id"], _type=data["type"], project=str(data["project_id"]),
                start_time=start_time, end_time=end_time,taskName=data['name'])
        return JsonResponse(data={"task_id": task_id}, code="999999", msg="成功！")


class GetTask(APIView):
    authentication_classes = (TokenAuthentication,)
    permission_classes = ()

    @extend_schema(
        summary="获取最近测试任务",
        description="获取项目下最近的一个测试任务",
        parameters=[PROJECT_ID_PARAM],
        responses={
            200: success_response("成功", data_example={"id":1,"name":"任务名","type":"timing","startTime":"2021-01-01 00:00:00","endTime":"2021-12-31 23:59:59","Host_id":1,"project_id":1}),
            **error_responses(),
        },
    )
    def get(self, request):
        """
        获取测试用例执行任务
        :param request:
        :return:
        """
        project_id = request.GET.get("project_id")
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
            obj = AutomationTestTask.objects.filter(project=project_id).order_by('-id')[:1].values()
            if len(obj)>0:
                return JsonResponse(code="999999", msg="成功！", data=obj[0])
            else:
                return JsonResponse(code="999999", msg="成功！", data=obj)


        except ObjectDoesNotExist:
            return JsonResponse(code="999999", msg="成功！")


class DelTask(APIView):
    authentication_classes = (TokenAuthentication,)
    permission_classes = ()

    def parameter_check(self, data):
        """
        校验参数
        :param data:
        :return:
        """
        try:
            # 校验project_id, id类型为int
            if not data["project_id"] or not data["taskName"]:
                return JsonResponse(code="999996", msg="参数有误！")
            if not isinstance(data["project_id"], int):
                return JsonResponse(code="999996", msg="参数有误！")
        except KeyError:
            return JsonResponse(code="999996", msg="参数有误！")

    @extend_schema(
        summary="删除测试任务",
        description="删除指定名称的定时/循环测试任务",
        request=json_body(
            properties={
                "project_id": {"type": "integer", "description": "项目 ID"},
                "taskName": {"type": "string", "description": "任务名称"},
            },
            required=["project_id", "taskName"],
        ),
        responses={
            200: simple_response(),
            **error_responses(),
        },
    )
    def post(self, request):
        """
        删除测试任务
        :param request:
        :return:
        """
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
        obm = AutomationTestTask.objects.filter(project=data["project_id"],name=data['taskName'])
        if obm:
            taskData = AutomationTestTaskSerializer( AutomationTestTask.objects.get(project=data["project_id"]\
                                                                                    ,name=data['taskName'])).data
            with transaction.atomic():
                obm.delete()
                res=delTask(taskData['startTime'],taskData['name'])
                record_dynamic(project=data["project_id"],
                               _type="删除", operationObject="任务",
                               user=request.user.pk, data="删除任务")
                return JsonResponse(code="999999", msg=res)
        else:
            return JsonResponse(code="999986", msg='job not exist !')


class LookResult(APIView):
    authentication_classes = (TokenAuthentication,)
    permission_classes = ()

    @extend_schema(
        summary="查看测试结果详情",
        description="获取指定 API 接口的测试执行结果",
        parameters=[
            PROJECT_ID_PARAM,
            CASE_ID_PARAM,
            API_ID_PARAM,
        ],
        responses={
            200: success_response("成功", data_example={"result":"PASS","httpCode":200,"responseData":"{...}"}),
            **error_responses(),
        },
    )
    def get(self, request):
        """
        查看测试结果详情
        :param request:
        :return:
        """
        project_id = request.GET.get("project_id")
        case_id = request.GET.get("case_id")
        api_id = request.GET.get("api_id")
        if not project_id.isdecimal() or not api_id.isdecimal():
            return JsonResponse(code="999996", msg="参数有误！")
        try:
            pro_data = Project.objects.get(id=project_id)
        except ObjectDoesNotExist:
            return JsonResponse(code="999995", msg="项目不存在！")
        pro_data = ProjectSerializer(pro_data)
        if not pro_data.data["status"]:
            return JsonResponse(code="999985", msg="该项目已禁用")
        try:
            AutomationTestCase.objects.get(id=case_id, project=project_id)
        except ObjectDoesNotExist:
            return JsonResponse(code="999987", msg="用例不存在！")
        try:
            AutomationCaseApi.objects.get(id=api_id, automationTestCase=case_id)
        except ObjectDoesNotExist:
            return JsonResponse(code="999990", msg="接口不存在！")
        try:
            data = AutomationTestResult.objects.get(automationCaseApi=api_id)
            serialize = AutomationTestResultSerializer(data)
            return JsonResponse(data=serialize.data, code="999999", msg="成功！")
        except ObjectDoesNotExist:
            return JsonResponse(code="999999", msg="成功！")


class TestReport(APIView):
    authentication_classes = (TokenAuthentication,)
    permission_classes = ()

    @extend_schema(
        summary="获取测试报告",
        description="获取项目的测试报告汇总（通过/失败/错误/未运行数量）",
        parameters=[PROJECT_ID_PARAM],
        responses={
            200: success_response("成功", data_example={"data": [], "total": 0, "pass": 0, "fail": 0, "error": 0, "NotRun": 0}),
            **error_responses(),
        },
    )
    def get(self, request):
        """
        测试报告
        :param request:
        :return:
        """
        project_id = request.GET.get("project_id")
        if not project_id.isdecimal():
            return JsonResponse(code="999996", msg="参数有误！")
        try:
            pro_data = Project.objects.get(id=project_id)
        except ObjectDoesNotExist:
            return JsonResponse(code="999995", msg="项目不存在！")
        pro_data = ProjectSerializer(pro_data)
        if not pro_data.data["status"]:
            return JsonResponse(code="999985", msg="该项目已禁用")
        obj = AutomationTestCase.objects.filter(project=project_id)
        if obj:
            case = Q()
            for i in obj:
                case = case | Q(automationTestCase=i.pk)
            data = AutomationTestReportSerializer(
                AutomationCaseApi.objects.filter(case), many=True).data
            success = 0
            fail = 0
            not_run = 0
            error = 0
            for i in data:
                if i["result"] == "PASS":
                    success = success + 1
                elif i["result"] == "FAIL":
                    fail = fail + 1
                elif i["result"] == "ERROR":
                    error = error + 1
                else:
                    not_run = not_run + 1
            return JsonResponse(code="999999", msg="成功！", data={"data": data,
                                                                "total": len(data),
                                                                "pass": success,
                                                                "fail": fail,
                                                                "error": error,
                                                                "NotRun": not_run
                                                                })
        else:
            return JsonResponse(code="999987", msg="用例不存在！")


class DownLoadCase(APIView):
    authentication_classes = (TokenAuthentication,)
    permission_classes = ()

    @extend_schema(
        summary="下载用例文档",
        description="生成并返回项目测试用例的 Excel 下载路径",
        parameters=[PROJECT_ID_PARAM],
        responses={
            200: success_response("成功", data_example="./api_test/ApiDoc/项目名.xlsx"),
            **error_responses(),
        },
    )
    def get(self, request):
        """
        获取用例下载文档路径
        :param request:
        :return:
        """
        project_id = request.GET.get("project_id")
        try:
            if not project_id.isdecimal():
                return JsonResponse(code="999996", msg="参数有误!")
        except AttributeError:
            return JsonResponse(code="999996", msg="参数有误！")
        try:
            obj = Project.objects.get(id=project_id)
        except ObjectDoesNotExist:
            return JsonResponse(code="999995", msg="项目不存在!")
        pro_data = ProjectSerializer(obj)
        if not pro_data.data["status"]:
            return JsonResponse(code="999985", msg="该项目已禁用")
        obi = AutomationGroupLevelFirst.objects.filter(project=project_id).order_by("id")
        data = AutomationCaseDownSerializer(obi, many=True).data
        path = "./api_test/ApiDoc/%s.xlsx" % str(obj.name)
        result = Write(path).write_case(data)
        if result:
            return JsonResponse(code="999999", msg="成功！", data=path)
        else:
            return JsonResponse(code="999998", msg="失败")


