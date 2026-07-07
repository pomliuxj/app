from api_test.common.addTask import creatTask,updateTask,delTask,createTaskRecode
from api_test.models import AutomationTestTask,Project,GlobalHost,AutomationTaskRunTime
from api_test.serializers import AutomationTestTaskSerializer,AutomationTestTaskDeserializer,ProjectMemberDeserializer,\
                                    ProjectSerializer,AutomationTaskRunTimeSerializer
from api_test.common.common import record_dynamic
from drf_spectacular.utils import extend_schema, OpenApiParameter, OpenApiResponse, OpenApiExample
from api_test.common.schema_utils import (
    PROJECT_ID_PARAM, PAGE_PARAM, PAGE_SIZE_PARAM, NAME_PARAM,
    success_response, error_responses, json_body,
    list_response, create_response, simple_response,
)
import logging
import time
LOGGINGS =logging.getLogger('logging')
from django.core.paginator import Paginator, PageNotAnInteger, EmptyPage
from rest_framework.authentication import TokenAuthentication
from rest_framework.parsers import JSONParser
from api_test.common.api_response import JsonResponse
from datetime import datetime
from django.db import transaction
from django.core.exceptions import ObjectDoesNotExist



from rest_framework.views import APIView

createTaskRecode()


class TaskInfo(APIView):
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
            if not isinstance(data["project_id"], int) or not isinstance(data["Host_id"], int) or \
                    not (data["case_id"],list):
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
        summary="获取任务列表",
        description="分页获取测试任务列表",
        parameters=[
            OpenApiParameter("projectId", int, description="项目 ID", required=True),
            NAME_PARAM,
            PAGE_PARAM,
            PAGE_SIZE_PARAM,
        ],
        responses={
            200: list_response("成功"),
            **error_responses(),
        },
    )
    def get(self,request):
        """
        获取任务列表
        :param request:
        :return:
        """
        try:
            page_size = int(request.GET.get("page_size", 10))
            page = int(request.GET.get("page", 1))
            projectId=int(request.GET.get("projectId", 1))
        except (TypeError, ValueError):
            return JsonResponse(code="999985", msg="page and page_size projectId must be integer!")
        name = request.GET.get("name")
        if name:
            obi = AutomationTestTask.objects.filter(name__contains=name,project=projectId).order_by("-id")
        else:
            obi = AutomationTestTask.objects.filter(project=projectId).order_by("-id")
        paginator = Paginator(obi, page_size)  # paginator对象
        total = paginator.count  # 总记录数
        try:
            obm = paginator.page(page)
        except PageNotAnInteger:
            obm = paginator.page(1)
        except EmptyPage:
            obm = paginator.page(paginator.num_pages)
        serialize = AutomationTestTaskSerializer(obm, many=True)
        return JsonResponse(data={"data": serialize.data,
                                  "page": page,
                                  "total": total
                                  }, code="999999", msg="成功")

    @extend_schema(
        summary="添加测试任务",
        description="创建新的定时或循环测试任务",
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
                "case_id": {"type": "array", "description": "关联用例 ID 列表", "items": {"type": "integer"}},
            },
            required=["project_id", "name", "type", "Host_id", "startTime", "endTime", "case_id"],
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
                    serialize.save(project=pro_id, Host=host_data,caseId=data['case_id'])
                    task_id = AutomationTestTaskSerializer(AutomationTestTask.objects.get(name=data["name"])).data['id']
                    LOGGINGS.info(f'task_id:{task_id}')
                else:
                    return JsonResponse(code="999996", msg="参数有误！")
            except ObjectDoesNotExist:
                serialize = AutomationTestTaskDeserializer(data=data)
                if serialize.is_valid():
                    serialize.save(project=pro_id, Host=host_data,caseId=data['case_id'])
                    task_id = AutomationTestTaskSerializer(AutomationTestTask.objects.get(name=data["name"])).data['id']
                else:
                    return JsonResponse(code="999996", msg="参数有误！")
            record_dynamic(project=data["project_id"],
                           _type="新增", operationObject="任务",
                           user=request.user.pk, data="新增循环任务\"%s\"" % data["name"])
            creatTask(host_id=data["Host_id"], _type=data["type"], project=str(data["project_id"]),
                      start_time=start_time, end_time=end_time, frequency=data["frequency"], unit=data["unit"],
                      taskName=data['name'],case_id=data["case_id"])

        else:
            try:
                serialize = AutomationTestTaskDeserializer(data=data)
                if serialize.is_valid():
                    serialize.save(project=pro_id, Host=host_data,caseId=data['case_id'])
                    task_id = AutomationTestTaskSerializer(AutomationTestTask.objects.get(name=data["name"])).data['id']
                else:
                    return JsonResponse(code="999996", msg="参数有误！")
            except ObjectDoesNotExist:
                serialize = AutomationTestTaskDeserializer(data=data)
                if serialize.is_valid():
                    serialize.save(project=pro_id, Host=host_data,caseId=data['case_id'])
                    task_id = AutomationTestTaskSerializer(AutomationTestTask.objects.get(name=data["name"])).data['id']
                else:
                    return JsonResponse(code="999996", msg="参数有误！")
            record_dynamic(project=data["project_id"],
                           _type="新增", operationObject="任务",
                           user=request.user.pk, data="新增定时任务\"%s\"" % data["name"])
            creatTask(host_id=data["Host_id"], _type=data["type"], project=str(data["project_id"]),
                      start_time=start_time, end_time=end_time, taskName=data['name'],case_id=data["case_id"])
        return JsonResponse(data={"task_id": task_id}, code="999999", msg="成功！")

    @extend_schema(
        summary="修改测试任务",
        description="修改已有的定时或循环测试任务",
        request=json_body(
            properties={
                "id": {"type": "integer", "description": "任务 ID"},
                "project_id": {"type": "integer", "description": "项目 ID"},
                "name": {"type": "string", "description": "任务名称"},
                "type": {"type": "string", "description": "任务类型", "enum": ["circulation", "timing"]},
                "Host_id": {"type": "integer", "description": "目标 Host ID"},
                "startTime": {"type": "string", "description": "开始时间"},
                "endTime": {"type": "string", "description": "结束时间"},
                "frequency": {"type": "integer", "description": "执行频率"},
                "unit": {"type": "string", "description": "频率单位", "enum": ["m", "h", "d", "w"]},
                "caseId": {"type": "array", "description": "关联用例 ID 列表", "items": {"type": "integer"}},
            },
            required=["id", "project_id", "name", "type", "Host_id", "startTime", "endTime", "caseId"],
        ),
        responses={
            200: simple_response(),
            **error_responses(),
        },
    )
    def put(self,request):
        """
        修改测试任务
        :param request:
        :return:
        """
        data = JSONParser().parse(request)
        try:
            taskObj = AutomationTestTask.objects.get(id=data["id"])
            pro_id = Project.objects.get(id=taskObj.project_id)
            if not request.user.is_superuser and pro_id.user.is_superuser:
                return JsonResponse(code="999983", msg="无操作权限！")
        except ObjectDoesNotExist:
            return JsonResponse(code="999995", msg="项目不存在或任务不存在！")
        except KeyError :
            return JsonResponse(code="999994", msg="任务id为空！")
        pro_data = ProjectSerializer(pro_id)
        time_array = str(taskObj.startTime)
        delTask(time_array,taskObj.name)
        if not pro_data.data["status"]:
            return JsonResponse(code="999985", msg="该项目已禁用")
        data["endTime"] = datetime.strptime(data["endTime"], "%Y-%m-%d %H:%M:%S")
        data["startTime"] = datetime.strptime(data["startTime"], "%Y-%m-%d %H:%M:%S")
        try:
            host_data = GlobalHost.objects.get(id=data["Host_id"], project=data["project_id"])
        except ObjectDoesNotExist:
            return JsonResponse(code="999992", msg="host不存在！")
        valid_data = dict(
            project=pro_id,Host=host_data,endTime=data["endTime"],
            startTime=data["startTime"],name=data["name"], type=data["type"],
            frequency=data["frequency"], unit=data["unit"],caseId=str(data["caseId"])
        )
        serialize = AutomationTestTaskDeserializer(data=valid_data)
        if taskObj.type == "circulation" and taskObj:
            try:
                if serialize.is_valid() :
                    serialize.update(instance=AutomationTestTask.objects.get(id=data['id']),validated_data=data)
                else:
                    return JsonResponse(code="999996", msg=f'参数序列化报错：{serialize.errors}')
            except Exception as E:
                logging.info(E)
                return JsonResponse(code="999996", msg="参数有误！")
            record_dynamic(project=data["project_id"],
                           _type="修改", operationObject="任务",
                           user=request.user.pk, data="修改循环任务\"%s\"" % taskObj.name)
            result = updateTask(host_id=data["Host_id"], _type=data["type"],
                                project=str(data["project_id"]),
                                start_time=data["startTime"], end_time=data["endTime"], frequency=data["frequency"],
                                unit=data["unit"],
                                taskName=data["name"], case_id=data["caseId"])
        elif taskObj.type == "timing" and taskObj:
            try:
                if serialize.is_valid():
                    serialize.update(instance=AutomationTestTask.objects.get(id=data['id']), validated_data=data)
                else:
                    return JsonResponse(code="999996", msg=f'参数序列化报错：{serialize.errors}')
            except Exception as E:
                logging.info(f'更新任务报错{E}')
                return JsonResponse(code="999996", msg="参数有误！")
            record_dynamic(project=data["project_id"],
                           _type="修改", operationObject="任务",
                           user=request.user.pk, data="修改定时任务\"%s\"" % taskObj.name)
            result = updateTask(host_id=data["Host_id"], _type=data["type"],
                                project=str(data["project_id"]),
                                start_time=data["startTime"], end_time=data["endTime"], taskName=data["name"],
                                case_id=data["caseId"])
        else:
            return JsonResponse(code="999998", msg="任务不存在或任务类型不支持！")
        if result.get('result'):
            return JsonResponse(code="999999", msg="成功！")
        else:
            return JsonResponse(code="999998", msg=result.get('msg'))

    @extend_schema(
        summary="删除测试任务",
        description="删除指定的测试任务",
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
    def delete(self, request):
        """
        删除测试任务
        :param request:
        :return:
        """
        try:
            data = JSONParser().parse(request)
        except Exception:
            data = {k: v for k, v in request.GET.items()}
            if not data:
                return JsonResponse(code="999996", msg="参数有误！")
        try:
            # 校验project_id, id类型为int
            if not data["project_id"] or not data["taskName"]:
                return JsonResponse(code="999996", msg="参数有误！")
            if not isinstance(data["project_id"], int):
                return JsonResponse(code="999996", msg="参数有误！")
        except KeyError:
            return JsonResponse(code="999996", msg="参数有误！")
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
                sid = transaction.savepoint()
                try:
                    res=delTask(taskData['startTime'],taskData['name'])
                    obm.delete()
                    record_dynamic(project=data["project_id"],
                                   _type="删除", operationObject="任务",
                                   user=request.user.pk, data="删除任务")
                    return JsonResponse(code="999999", msg=res)
                except :
                    transaction.savepoint_rollback(sid)
                    return JsonResponse(code="999986", msg='定时任务已停止或不存在!')
                else:
                    transaction.savepoint_commit(sid)
        else:
            return JsonResponse(code="999986", msg='定时任务已停止或不存在!')




class TaskRecode(APIView):
    authentication_classes = (TokenAuthentication,)
    permission_classes = ()

    @extend_schema(
        summary="获取任务执行记录",
        description="分页获取测试任务的执行记录，可按任务名称、执行结果、时间筛选",
        parameters=[
            OpenApiParameter("taskName", str, description="任务名称（可选）", required=False),
            OpenApiParameter("taskResult", str, description="执行结果 (true/false, 可选)", required=False),
            OpenApiParameter("startTime", str, description="开始时间筛选 (>=, 可选)", required=False),
            OpenApiParameter("endTime", str, description="结束时间筛选 (<=, 可选)", required=False),
            PAGE_PARAM,
            PAGE_SIZE_PARAM,
        ],
        responses={
            200: list_response("成功"),
            **error_responses(),
        },
    )
    def get(self,request):
        """
        获取任务执行记录
        :param request:
        :return:
        """
        try:
            page_size = int(request.GET.get("page_size", 10))
            page = int(request.GET.get("page", 1))
            taskName = request.GET.get("taskName")
        except (TypeError, ValueError):
            return JsonResponse(code="999985", msg="page and page_size  must be integer!")
        # 构建查询过滤条件
        filter_kwargs = {}
        if taskName:
            filter_kwargs["taskName"] = taskName
        # 状态筛选: taskResult 为布尔值，传 "true"/"false" 或 "1"/"0"
        task_result = request.GET.get("taskResult")
        if task_result is not None:
            if task_result.lower() in ("true", "1"):
                filter_kwargs["taskResult"] = True
            elif task_result.lower() in ("false", "0"):
                filter_kwargs["taskResult"] = False
        # 开始时间筛选: 查询 startTime >= 传入值的记录
        start_time = request.GET.get("startTime")
        if start_time:
            filter_kwargs["startTime__gte"] = start_time
        # 结束时间筛选: 查询 elapsedTime <= 传入值的记录
        end_time = request.GET.get("endTime")
        if end_time:
            filter_kwargs["elapsedTime__lte"] = end_time
        obi = AutomationTaskRunTime.objects.filter(**filter_kwargs).order_by("-id")
        paginator = Paginator(obi, page_size)  # paginator对象
        total = paginator.count  # 总记录数
        try:
            obm = paginator.page(page)
        except PageNotAnInteger:
            obm = paginator.page(1)
        except EmptyPage:
            obm = paginator.page(paginator.num_pages)
        serialize = AutomationTaskRunTimeSerializer(obm, many=True)
        return JsonResponse(data={"data": serialize.data,
                                  "page": page,
                                  "total": total
                                  }, code="999999", msg="成功")




