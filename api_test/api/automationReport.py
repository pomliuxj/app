from django.core.exceptions import ObjectDoesNotExist
from django.db.models import Q
from drf_spectacular.utils import extend_schema, OpenApiParameter, OpenApiResponse, OpenApiExample
from rest_framework.authentication import TokenAuthentication
from rest_framework.views import APIView
from api_test.common.decorator import clock
from api_test.common.api_response import JsonResponse
from api_test.common.schema_utils import (
    PROJECT_ID_PARAM, TIME_PARAM, TASK_NAME_PARAM,
    success_response, error_responses,
)
import logging
import re
import json
Logging= logging.getLogger(__name__)
from api_test.models import Project, AutomationTaskRunTime, AutomationTestCase, AutomationCaseApi, \
    AutomationCaseTestResult,AutomationTestTask
from api_test.serializers import AutomationAutoTestResultSerializer, \
    AutomationTestLatelyTenTimeSerializer, AutomationTaskRunTimeSerializer, ProjectSerializer


class TestTime(APIView):
    authentication_classes = (TokenAuthentication,)
    permission_classes = ()

    @extend_schema(
        summary="获取测试执行时间",
        description="获取项目最近 10 次测试任务执行时间记录",
        parameters=[PROJECT_ID_PARAM],
        responses={
            200: success_response("成功", data_example=[{"startTime":"2021-01-01 00:00:00","elapsedTime":"10s","taskName":"任务名"}]),
            **error_responses(),
        },
    )
    def get(self, request):
        """
        获取执行测试时间
        :param request:
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
        try:
            data = AutomationTaskRunTimeSerializer(
                AutomationTaskRunTime.objects.filter(project=project_id).order_by("-startTime")[:10],
                many=True).data
        except IndexError:
            data = AutomationTaskRunTimeSerializer(
                AutomationTaskRunTime.objects.filter(project=project_id).order_by("-startTime"),
                many=True).data
        return JsonResponse(code="999999", msg="成功！", data=data)


class AutoTestReport(APIView):
    authentication_classes = (TokenAuthentication,)
    permission_classes = ()

    @extend_schema(
        summary="获取测试报告详情",
        description="获取指定时间和任务的测试结果报告",
        parameters=[
            PROJECT_ID_PARAM,
            TIME_PARAM,
            TASK_NAME_PARAM,
        ],
        responses={
            200: success_response("成功", data_example={"data": [], "total": 0, "pass": 0, "fail": 0, "error": 0, "NotRun": 0}),
            **error_responses(),
        },
    )
    def get(self, request):
        """
        测试结果报告
        :param request:
        :return:
        """
        project_id = request.GET.get("project_id")
        time = request.GET.get('time')
        taskName=request.GET.get('taskName')
        if not project_id or not time:
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
        caseId= json.loads(AutomationTestTask.objects.get(name=taskName,project=project_id).caseId)
        obj = AutomationTestCase.objects.filter(id__in=caseId)
        if obj:
            case = Q()
            for i in obj:
                case = case | Q(automationTestCase=i.pk)
            case_data = AutomationCaseApi.objects.filter(case)
            api = Q()
            if case_data:
                for j in case_data:
                    api = api | Q(automationCaseApi=j.pk)
                data = AutomationAutoTestResultSerializer(
                    AutomationCaseTestResult.objects.filter(api, testTime=time), many=True).data
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
                return JsonResponse(code="999999", msg="成功！")
        else:
            return JsonResponse(code="999987", msg="用例不存在！")


class AutoLatelyTenTime(APIView):
    authentication_classes = (TokenAuthentication,)
    permission_classes = ()

    @extend_schema(
        summary="获取最近十次测试数据",
        description="获取项目最近十次自动化测试的通过率统计",
        parameters=[PROJECT_ID_PARAM],
        responses={
            200: success_response("成功", data_example=[{"startTime":"2021-01-01 00:00:00","pass":"0.8000","fail":"0.2000"}]),
            **error_responses(),
        },
    )
    @clock
    def get(self, request):
        """
        获取最近十次的测试数据
        project_id 项目ID
        :param request:
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
        try:
            qurrySet=AutomationTaskRunTime.objects.only('id','startTime','caseRunDetail').filter(project=project_id).order_by('-id')[:10]
            data = AutomationTestLatelyTenTimeSerializer(
                qurrySet,
                many=True).data
        except IndexError:
            qurrySet=AutomationTaskRunTime.objects.only('id','startTime','caseRunDetail').filter(project=project_id).order_by('-id')
            data = AutomationTestLatelyTenTimeSerializer(
                qurrySet,
                many=True).data
        for i in data:
            try:
                #通过正则获取报告数据，格式：“总执行测试接口数：5  成功:5, 失败:0, 执行错误:0, 超时:0”
                RunDetail = re.findall(r'\d+', i.get('caseRunDetail'), flags=re.DOTALL)
                _pass = int(RunDetail[1])
                fail = int(RunDetail[2])
                error = int(RunDetail[3] + RunDetail[4])
                total = int(RunDetail[0])
            except Exception as E:
                logging.info(f'获取报告数据异常{E}')
                total = 0
            if total:
                data[data.index(i)]["fail"] = "%.4f" % (fail / total)
                data[data.index(i)]["error"] = "%.4f" % (error / total)
                data[data.index(i)]["pass"] = "%.4f" % (1 - fail / total - error / total)
        return JsonResponse(code="999999", msg="成功！", data=data)
