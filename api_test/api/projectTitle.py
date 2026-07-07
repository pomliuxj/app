import logging

from django.core.exceptions import ObjectDoesNotExist
from drf_spectacular.utils import extend_schema, OpenApiParameter, OpenApiResponse
from rest_framework.authentication import TokenAuthentication
from rest_framework.views import APIView

from api_test.common.api_response import JsonResponse
from api_test.common.schema_utils import (
    PROJECT_ID_PARAM, success_response, error_responses,
)
from api_test.models import Project, AutomationCaseApi ,AutomationTestCase ,AutomationTestTask
from api_test.serializers import ProjectSerializer

logger = logging.getLogger(__name__) # 这里使用 __name__ 动态搜索定义的 logger 配置，这里有一个层次关系的知识点。


class ProjectInfo(APIView):
    authentication_classes = (TokenAuthentication,)
    permission_classes = ()

    @extend_schema(
        summary="获取项目详情",
        description="获取项目的详细信息，包含接口和任务统计",
        parameters=[PROJECT_ID_PARAM],
        responses={
            200: success_response("成功", data_example={"id":1,"name":"项目名","version":"1.0","type":"Web","status":True,"automationCaseCount":10,"automationTask":3}),
            **error_responses(),
        },
    )
    def get(self, request):
        """
        获取项目详情
        :param request:
        :return:
        """
        project_id = request.GET.get("project_id")
        if not project_id:
            return JsonResponse(code="999996", msg="参数有误！")
        if not project_id.isdecimal():
            return JsonResponse(code="999996", msg="参数有误！")
        # 查找项目是否存在
        try:
            obj = Project.objects.get(id=project_id)
        except ObjectDoesNotExist:
            return JsonResponse(code="999995", msg="项目不存在！")
        serialize = ProjectSerializer(obj).data
        automationCase = AutomationCaseApi.objects.filter(automationTestCase__project_id=project_id).count()
        automationTask = AutomationTestTask.objects.filter(project_id=project_id).count()
        serialize['automationCaseCount'] = automationCase
        serialize['automationTask'] = automationTask
        if serialize["status"]:
            return JsonResponse(data=serialize, code="999999", msg="成功！")
        else:
            return JsonResponse(code="999985", msg="该项目已禁用")
