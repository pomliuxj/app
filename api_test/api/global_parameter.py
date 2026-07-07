import logging
from django.core.exceptions import ObjectDoesNotExist
from django.core.paginator import Paginator, PageNotAnInteger, EmptyPage
from django.db import transaction
from drf_spectacular.utils import extend_schema, OpenApiParameter, OpenApiResponse, OpenApiExample
from rest_framework.authentication import TokenAuthentication
from rest_framework.parsers import JSONParser
from rest_framework.views import APIView
from api_test.common.api_response import JsonResponse
from api_test.common.common import record_dynamic
from api_test.common.debug_code import RunOnlineCode
from api_test.common.dataPool import DataExcuteBase
from api_test.common.GlobalStatusCode import *
from api_test.common.schema_utils import (
    PROJECT_ID_PARAM, PAGE_PARAM, PAGE_SIZE_PARAM, NAME_PARAM,
    success_response, error_responses, param_error_response,
    json_body, list_response, create_response, simple_response,
)
from api_test.models import Project, GlobalHost, OnlineCode,DataBaseInfo,CaseDataExcute,AutomationCaseApi
from api_test.serializers import GlobalHostSerializer, ProjectSerializer,OnlineCodeSerializer,OnlineCodeDeserializer,\
    DataBaseInfoDeserializer,CaseDataExcuteDeserializer,CaseDataExcuteSerializer
logger = logging.getLogger(__name__)  # 这里使用 __name__ 动态搜索定义的 logger 配置，这里有一个层次关系的知识点。


class HostTotal(APIView):
    authentication_classes = (TokenAuthentication,)
    permission_classes = ()

    def parameter_check(self, data):
        """
        校验HOST参数
        :param data:
        :return:
        """
        try:
            # 校验project_id类型为int
            if not isinstance(data["project_id"], int):
                return JsonResponse(code="999995", msg="参数有误！")
            # 必传参数 name, host
            if not data["name"] or not data["host"]:
                return JsonResponse(code="999995", msg="参数有误！")
        except KeyError:
            return JsonResponse(code="999995", msg="参数有误！")


    @extend_schema(
        summary="获取 Host 列表",
        description="分页获取项目的域名/Host 配置列表",
        parameters=[PROJECT_ID_PARAM, NAME_PARAM, PAGE_PARAM, PAGE_SIZE_PARAM],
        responses={
            200: list_response("成功"),
            **error_responses(),
        },
    )
    def get(self, request):
        """
        获取host列表
        :param request:
        :return:
        """
        try:
            page_size = int(request.GET.get("page_size", 20))
            page = int(request.GET.get("page", 1))
        except (TypeError, ValueError):
            return JsonResponse(code="999995", msg="page and page_size must be integer！")
        project_id = request.GET.get("project_id")
        if not project_id.isdecimal():
            return JsonResponse(code="999995", msg="参数有误！")
        try:
            pro_data = Project.objects.get(id=project_id)
        except ObjectDoesNotExist:
            return JsonResponse(code="999995", msg="项目不存在！")
        pro_data = ProjectSerializer(pro_data)
        if not pro_data.data["status"]:
            return JsonResponse(code="999985", msg="该项目已禁用")
        name = request.GET.get("name")
        if name:
            obi = GlobalHost.objects.filter(name__contains=name, project=project_id).order_by("id")
        else:
            obi = GlobalHost.objects.filter(project=project_id).order_by("id")
        paginator = Paginator(obi, page_size)  # paginator对象
        total = paginator.count  # 总记录数
        try:
            obm = paginator.page(page)
        except PageNotAnInteger:
            obm = paginator.page(1)
        except EmptyPage:
            obm = paginator.page(paginator.num_pages)
        serialize = GlobalHostSerializer(obm, many=True)
        return JsonResponse(data={"data": serialize.data,
                                  "page": page,
                                  "total": total
                                  }, code="999999", msg="成功！")

    @extend_schema(
        summary="添加 Host",
        description="在项目下新增域名/Host 配置",
        request=json_body(
            properties={
                "project_id": {"type": "integer", "description": "项目 ID"},
                "name": {"type": "string", "description": "Host 名称"},
                "host": {"type": "string", "description": "Host 地址"},
            },
            required=["project_id", "name", "host"],
        ),
        responses={
            200: create_response(id_field="host_id"),
            **error_responses(),
        },
    )
    def post(self, request):
        """
        添加Host
        :param request:
        :return:
        """
        data = JSONParser().parse(request)
        logger.info(data)
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
        obi = GlobalHost.objects.filter(name=data["name"], project=data["project_id"])
        if obi:
            return JsonResponse(code="999997", msg="存在相同名称！")
        else:
            serializer = GlobalHostSerializer(data=data)
            with transaction.atomic():
                if serializer.is_valid():
                    # 外键project_id
                    serializer.save(project=obj)
                    # 记录动态
                    record_dynamic(project=data["project_id"],
                                   _type="添加", operationObject="域名", user=request.user.pk, data=data["name"])
                    return JsonResponse(data={
                        "host_id": serializer.data.get("id")
                    }, code="999999", msg="成功！")
                return JsonResponse(code="999998", msg="失败！")

    @extend_schema(
        summary="修改 Host",
        description="修改已有的域名/Host 配置",
        request=json_body(
            properties={
                "project_id": {"type": "integer", "description": "项目 ID"},
                "id": {"type": "integer", "description": "Host ID"},
                "name": {"type": "string", "description": "Host 名称"},
                "host": {"type": "string", "description": "Host 地址"},
            },
            required=["project_id", "id", "name", "host"],
        ),
        responses={
            200: simple_response(),
            **error_responses(),
        },
    )
    def put(self, request):
        """
        修改host域名
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
            obi = GlobalHost.objects.get(id=data["id"])
        except ObjectDoesNotExist:
            return JsonResponse(code="999992", msg="host不存在！")
        host_name = GlobalHost.objects.filter(name=data["name"]).exclude(id=data["id"])
        if len(host_name):
            return JsonResponse(code="999997", msg="存在相同名称！")
        else:
            serializer = GlobalHostSerializer(data=data)
            with transaction.atomic():
                if serializer.is_valid():
                    # 外键project_id
                    serializer.update(instance=obi, validated_data=data)
                    # 记录动态
                    record_dynamic(project=data["project_id"],
                                   _type="修改", operationObject="域名", user=request.user.pk, data=data["name"])
                    return JsonResponse(code="999999", msg="成功！")
                return JsonResponse(code="999998", msg="失败！")
    @extend_schema(
        summary="删除 Host",
        description="批量删除域名/Host 配置",
        request=json_body(
            properties={
                "project_id": {"type": "integer", "description": "项目 ID"},
                "ids": {
                    "type": "array",
                    "description": "Host ID 列表",
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
    def delete(self, request):
        """
        删除域名
        :param request:
        :return:
        """
        try:
            data = JSONParser().parse(request)
        except Exception:
            # axios v0.18.x 不支持 DELETE 的 {data:} 配置，参数可能在 query string
            data = {k: v for k, v in request.GET.items()}
            if not data:
                return JsonResponse(code="999996", msg="参数有误！")
        print(data)
        # result = self.parameter_check(data)
        # # if result:
        # #     return result
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
            for j in data["ids"]:
                obj = GlobalHost.objects.filter(id=j)
                if len(obj)>0:
                    name = obj[0].name
                    obj.delete()
                    record_dynamic(project=data["project_id"],
                                   _type="删除", operationObject="域名", user=request.user.pk, data=name)
                else:
                    return JsonResponse(code="999995", msg="HOST不存在！")
            return JsonResponse(code="999999", msg="成功！")
        except ObjectDoesNotExist:
            return JsonResponse(code="999995", msg="项目不存在！")




class DisableHost(APIView):
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
            if not isinstance(data["project_id"], int) or not isinstance(data["host_id"], int):
                return JsonResponse(code="999995", msg="参数有误！")
        except KeyError:
            return JsonResponse(code="999995", msg="参数有误！")

    @extend_schema(
        summary="禁用 Host",
        description="禁用指定的 Host 配置",
        request=json_body(
            properties={
                "project_id": {"type": "integer", "description": "项目 ID"},
                "host_id": {"type": "integer", "description": "Host ID"},
            },
            required=["project_id", "host_id"],
        ),
        responses={
            200: simple_response(),
            **error_responses(),
        },
    )
    def post(self, request):
        """
        禁用host
        :param request:
        :return:
        """
        data = JSONParser().parse(request)
        result = self.parameter_check(data)
        if result:
            return result
        # 查找项目是否存在
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
            obj = GlobalHost.objects.get(id=data["host_id"], project=data["project_id"])
        except ObjectDoesNotExist:
            return JsonResponse(code="999992", msg="host不存在")
        obj.status = False
        obj.save()
        record_dynamic(project=data["project_id"],
                       _type="禁用", operationObject="域名", user=request.user.pk, data=obj.name)
        return JsonResponse(code="999999", msg="成功！")


class EnableHost(APIView):
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
            if not isinstance(data["project_id"], int) or not isinstance(data["host_id"], int):
                return JsonResponse(code="999995", msg="参数有误！")
        except KeyError:
            return JsonResponse(code="999995", msg="参数有误！")

    @extend_schema(
        summary="启用 Host",
        description="启用指定的 Host 配置",
        request=json_body(
            properties={
                "project_id": {"type": "integer", "description": "项目 ID"},
                "host_id": {"type": "integer", "description": "Host ID"},
            },
            required=["project_id", "host_id"],
        ),
        responses={
            200: simple_response(),
            **error_responses(),
        },
    )
    def post(self, request):
        """
        启用Host
        :param request:
        :return:
        """
        data = JSONParser().parse(request)
        result = self.parameter_check(data)
        if result:
            return result
        # 查找项目是否存在
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
            obj = GlobalHost.objects.get(id=data["host_id"], project=data["project_id"])
        except ObjectDoesNotExist:
            return JsonResponse(code="999992", msg="host不存在")
        obj.status = True
        obj.save()
        record_dynamic(project=data["project_id"],
                       _type="禁用", operationObject="域名", user=request.user.pk, data=obj.name)
        return JsonResponse(code="999999", msg="成功！")

class GlobalOnlineCode(APIView):
    authentication_classes = (TokenAuthentication,)
    permission_classes = ()
    def parameter_check(self, data):
        """
        校验参数
        :param data:
        :return:
        """
        try:
            if not isinstance(data["Code"], str) or not isinstance(data["variablesName"], str):
                return JsonResponse(code="999995", msg="参数有误！")
        except KeyError:
            return JsonResponse(code="999995", msg="参数有误！")

    @extend_schema(
        summary="在线运行代码",
        description="在线执行调试代码片段",
        request=json_body(
            properties={
                "Code": {"type": "string", "description": "Python 代码"},
                "variablesName": {"type": "string", "description": "变量名称"},
            },
            required=["Code", "variablesName"],
        ),
        responses={
            200: success_response("成功", data_example={"data":"执行结果"}),
            **error_responses(),
        },
    )
    def post(self,request):
        """
        在线运行代码
        :param data:
        :return:
        """
        data = JSONParser().parse(request)
        result = self.parameter_check(data)
        if result:
            return result
        # 检验参数Code，variablesName
        try:
            code = data.get('Code')
            variablesName=data["variablesName"]
            codeResponse = RunOnlineCode(code,variablesName).run()
            return JsonResponse(data={
                        "data":codeResponse
                    }, code="999999", msg="成功！")
        except Exception as E:

            logger.error(f'代码执行错误：{E}')
            return JsonResponse(data={
                "error": E
            },code=fail().get('code'),msg=fail().get('msg'))
    @extend_schema(
        summary="获取全局变量列表",
        description="分页获取在线代码/全局变量列表",
        parameters=[
            OpenApiParameter("variablesName", str, description="变量名（模糊搜索）", required=False),
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
        全局变量列表
        :param data:
        :return:
        """
        try:
            page_size = int(request.GET.get("page_size", 20))
            page = int(request.GET.get("page", 1))
        except (TypeError, ValueError):
            return JsonResponse(code="999995", msg="page and page_size must be integer！")
        name = request.GET.get("variablesName")
        if name:
            obi = OnlineCode.objects.filter(variablesName__contains=name).order_by("id")
        else:
            obi = OnlineCode.objects.all().order_by("id")
        paginator = Paginator(obi, page_size)  # paginator对象
        total = paginator.count  # 总记录数
        try:
            obm = paginator.page(page)
        except PageNotAnInteger:
            obm = paginator.page(1)
        except EmptyPage:
            obm = paginator.page(paginator.num_pages)
        serialize = OnlineCodeDeserializer(obm, many=True)
        return JsonResponse(data={"data": serialize.data,
                                  "page": page,
                                  "total": total
                                  }, code="999999", msg="成功！")
    @extend_schema(
        summary="保存全局变量",
        description="创建新的全局变量/代码片段",
        request=json_body(
            properties={
                "project_id": {"type": "integer", "description": "项目 ID"},
                "variablesName": {"type": "string", "description": "变量名称"},
                "Code": {"type": "string", "description": "Python 代码"},
            },
            required=["project_id", "variablesName", "Code"],
        ),
        responses={
            200: simple_response(),
            **error_responses(),
        },
    )
    def put(self,request):
        """
        保存全局变量
        :param data:
        :return:
        """
        try:
            data = JSONParser().parse(request)
            logger.info(data)
        except Exception as E:
            logger.error(f'保存全局变量异常：{E}')
        obj = Project.objects.get(id=data['project_id'])
        serializer = OnlineCodeSerializer(data=data)
        obm = OnlineCode.objects.filter(variablesName=data['variablesName'])
        if obm:
            return JsonResponse(data="",code=999997,msg="存在相同名称")
        try:
            if serializer.is_valid():
                serializer.save(project=obj)
                return JsonResponse(data="", code=999999, msg="成功")
        except Exception as E:
            logger.info(E)
            return JsonResponse(data="",code=999998,msg="保存失败，请检查参数")

    @extend_schema(
        summary="修改或保存全局变量",
        description="修改已有全局变量/代码片段，若不存在则新增",
        request=json_body(
            properties={
                "project_id": {"type": "integer", "description": "项目 ID"},
                "variablesName": {"type": "string", "description": "变量名称"},
                "Code": {"type": "string", "description": "Python 代码"},
            },
            required=["project_id", "variablesName", "Code"],
        ),
        responses={
            200: simple_response(),
            **error_responses(),
        },
    )
    def delete(self,request):
        """
        修改全局变量
        :param data:
        :return:
        """
        try:
            data = JSONParser().parse(request)
            logger.info(data)
        except Exception as E:
            logger.error(f'JSON parse fallback to query params: {E}')
            data = {k: v for k, v in request.GET.items()}
            if not data:
                return JsonResponse(code="999996", msg="参数有误！")
        obm = OnlineCode.objects.filter(variablesName=data['variablesName'])
        if obm:
            #判断全局变量是否存在
            try:
                obm.update(Code=data['Code'],project_id=data['project_id'])
                return JsonResponse(data="", code=success().get('code'), msg="成功")
            except Exception as E:
                logger.info(E)
                return JsonResponse(data="", code=999998, msg="修改失败，请检查参数")
        else:
            obj = Project.objects.get(id=data['project_id'])
            serializer = OnlineCodeSerializer(data=data)
            try:
                if serializer.is_valid():
                    serializer.save(project=obj)
                    return JsonResponse(data="", code=success().get('code'), msg="成功")
                else:
                    return JsonResponse(data="", code=fail().get('code'), msg=f'{serializer.errors}')
            except Exception as E:
                logger.info(E)
                return JsonResponse(data="", code=999998, msg="修改失败，请检查参数")





class GlobalDataBase(APIView):
    authentication_classes = (TokenAuthentication,)
    permission_classes = ()

    @extend_schema(
        summary="添加数据源配置",
        description="新增数据库连接配置",
        request=json_body(
            properties={
                "name": {"type": "string", "description": "数据源名称"},
                "host": {"type": "string", "description": "数据库主机"},
                "port": {"type": "string", "description": "端口"},
                "user": {"type": "string", "description": "用户名"},
                "password": {"type": "string", "description": "密码"},
                "db": {"type": "string", "description": "数据库名"},
            },
            required=["name", "host", "port", "user", "password", "db"],
        ),
        responses={
            200: success_response("成功", data_example={"id":1,"name":"数据源","host":"localhost","port":"3306"}),
            **error_responses(),
        },
    )
    def post(self,request):
        """
         数据源配置
        :param data:
        :return:
        """
        data = JSONParser().parse(request)
        logger.info(f'GlobalDataBase请求参数:{data}')
        try:
            serializer = DataBaseInfoDeserializer(data=data)
            if serializer.is_valid():
                serializer.save()
                return JsonResponse(data=serializer.data,code="999999", msg="成功！")
            else:
                return JsonResponse(data={},code=fail().get("code"),msg=serializer.errors)
        except Exception as E:
            return JsonResponse(data={}, code=fail().get("code"), msg=f"失败原因：{E}")


    @extend_schema(
        summary="获取数据源列表",
        description="分页获取数据库连接配置列表",
        parameters=[NAME_PARAM, PAGE_PARAM, PAGE_SIZE_PARAM],
        responses={
            200: list_response("成功"),
            **error_responses(),
        },
    )
    def get(self,request):
        """
        数据源列表
        :param data:
        :return:
        """
        try:
            page_size = int(request.GET.get("page_size", 20))
            page = int(request.GET.get("page", 1))
        except (TypeError, ValueError):
            return JsonResponse(code="999995", msg="page and page_size must be integer！")
        name = request.GET.get("name")
        if name:
            obi = DataBaseInfo.objects.filter(name__contains=name).order_by("-id")
        else:
            obi = DataBaseInfo.objects.all().order_by("-id")
        paginator = Paginator(obi, page_size)  # paginator对象
        total = paginator.count  # 总记录数
        try:
            obm = paginator.page(page)
        except PageNotAnInteger:
            obm = paginator.page(1)
        except EmptyPage:
            obm = paginator.page(paginator.num_pages)
        serialize = DataBaseInfoDeserializer(obm, many=True)
        return JsonResponse(data={"data": serialize.data,
                                  "page": page,
                                  "total": total
                                  }, code="999999", msg="成功！")
    @extend_schema(
        summary="修改数据源配置",
        description="修改已有的数据库连接配置",
        request=json_body(
            properties={
                "id": {"type": "integer", "description": "数据源 ID"},
                "name": {"type": "string", "description": "数据源名称"},
                "host": {"type": "string", "description": "数据库主机"},
                "port": {"type": "string", "description": "端口"},
                "user": {"type": "string", "description": "用户名"},
                "password": {"type": "string", "description": "密码"},
                "db": {"type": "string", "description": "数据库名"},
            },
            required=["id"],
        ),
        responses={
            200: success_response("成功"),
            **error_responses(),
        },
    )
    def put(self,request):
        """
        修改数据源
        :param data:
        :return:
        """

        try:
            data = JSONParser().parse(request)
            obj = DataBaseInfo.objects.get(id=data['id'])
            logger.info(f'GlobalDataBase请求参数:{data}')
        except Exception as E:
            logger.error(f'报错信息：{E}')
            return JsonResponse(data="",msg=parameter_wrong().get('msg'),code=parameter_wrong().get('code'))
        serializer = DataBaseInfoDeserializer(data=data)
        try:
            if serializer.is_valid():
                serializer.update(instance=obj,validated_data=data)
                return JsonResponse(data=serializer.data, code=999999, msg="成功")
            else:
                return JsonResponse(data={}, code=fail().get("code"), msg=serializer.errors)
        except Exception as E:
            logger.info(E)
            return JsonResponse(data="",code=999998,msg="保存失败，请检查参数")

    @extend_schema(
        summary="删除数据源配置",
        description="批量删除数据库连接配置",
        request=json_body(
            properties={
                "ids": {
                    "type": "array",
                    "description": "数据源 ID 列表",
                    "items": {"type": "integer"},
                },
            },
            required=["ids"],
        ),
        responses={
            200: simple_response(),
            **error_responses(),
        },
    )
    def delete(self,request):
        """
        删除数据源
        :param data:
        :return:
        """
        try:
            data = JSONParser().parse(request)
        except Exception:
            data = {k: v for k, v in request.GET.items()}
        try:
            ids = data.get('ids', data.get('ids[]', []))
            if isinstance(ids, str):
                ids = [int(ids)]
            obm = DataBaseInfo.objects.filter(id__in=ids)
            logger.info(data)
        except Exception as E:
            logger.error(f'参数异常：{E}')
            return JsonResponse(data="", msg=parameter_wrong().get('msg'), code=parameter_wrong().get('code'))
        if obm:
            #判断数据源是否存在
            try:
                obm.delete()
                return JsonResponse(data="", code=success().get('code'), msg=success().get('msg'))
            except Exception as E:
                logger.info(E)
                return JsonResponse(data="", code=fail().get('code'), msg=f"删除失败：{E}")
        else:
            return JsonResponse(data="", code=fail().get('code'), msg="删除失败，数据不存在")



class CheckDataBase(APIView):
    authentication_classes = (TokenAuthentication,)
    permission_classes = ()

    @extend_schema(
        summary="测试数据库连接",
        description="测试数据库连接是否可用",
        request=json_body(
            properties={
                "host": {"type": "string", "description": "数据库主机"},
                "port": {"type": "integer", "description": "端口"},
                "user": {"type": "string", "description": "用户名"},
                "password": {"type": "string", "description": "密码"},
                "db": {"type": "string", "description": "数据库名"},
            },
            required=["host", "port", "user", "password", "db"],
        ),
        responses={
            200: simple_response("连接成功"),
            **error_responses(),
        },
    )
    def post(self,request):
        """
         测试数据库连接
        :param data:
        :return:
        """
        data = JSONParser().parse(request)
        logger.info(f'GlobalDataBase请求参数:{data}')
        config ={'host': data.get('host'),
                'port': int(data.get('port')),
                'user': data.get('user'),
                'password': data.get('password'),
                'db': data.get('db')}
        try:
            result = DataExcuteBase(config=config,db_type='mysql').check_database()
            if result:
                return JsonResponse(data={},code="999999", msg="连接成功！")
            else:
                return JsonResponse(data={},code=fail().get("code"),msg=fail().get("msg"))
        except Exception as E:
            return JsonResponse(data={}, code=fail().get("code"), msg=f"失败原因：{E}")






class CaseDatabaseCheck(APIView):
    authentication_classes = (TokenAuthentication,)
    permission_classes = ()

    @extend_schema(
        summary="添加数据库校验",
        description="为用例接口添加数据库校验配置",
        request=json_body(
            properties={
                "project_id": {"type": "integer", "description": "项目 ID"},
                "dataInfo_id": {"type": "integer", "description": "数据源 ID"},
                "AutomationCaseApi_id": {"type": "integer", "description": "用例接口 ID"},
                "name": {"type": "string", "description": "校验名称"},
                "excutesql": {"type": "string", "description": "校验 SQL"},
                "type": {"type": "string", "description": "数据库类型"},
            },
            required=["project_id", "dataInfo_id", "AutomationCaseApi_id"],
        ),
        responses={
            200: success_response("成功"),
            **error_responses(),
        },
    )
    def post(self,request):
        """
         数据库校验
        :param data:
        :return:
        """
        data = JSONParser().parse(request)
        logger.info(f'CaseDatabaseCheck:{data}')
        obj = Project.objects.get(id=data['project_id'])
        obm = DataBaseInfo.objects.get(id=data['dataInfo_id'])
        obi = AutomationCaseApi.objects.get(id=data['AutomationCaseApi_id'])
        try:
            serializer = CaseDataExcuteSerializer(data=data)
            if serializer.is_valid():
                serializer.save(dataInfo=obm,project=obj,AutomationCaseApi=obi)
                return JsonResponse(data=serializer.data,code=success().get('code'), msg=success().get('msg'))
            else:
                return JsonResponse(data={},code=fail().get("code"),msg=serializer.errors)
        except Exception as E:
            return JsonResponse(data={}, code=fail().get("code"), msg=f"失败原因：{E}")


    @extend_schema(
        summary="获取数据库校验列表",
        description="分页获取用例接口的数据库校验配置列表",
        parameters=[
            OpenApiParameter("AutomationCaseApi_id", int, description="用例接口 ID", required=True),
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
        数据库校验列表
        :param data:
        :return:
        """
        try:
            page_size = int(request.GET.get("page_size", 20))
            page = int(request.GET.get("page", 1))
            AutomationCaseApi_id = int(request.GET.get("AutomationCaseApi_id"))
        except (TypeError, ValueError):
            return JsonResponse(code="999995", msg="page and page_size and project_id must be integer！")
        name = request.GET.get("name")
        if name:
            obi = CaseDataExcute.objects.filter(name__contains=name,AutomationCaseApi_id=AutomationCaseApi_id).order_by("-id")
        else:
            obi = CaseDataExcute.objects.filter(AutomationCaseApi_id=AutomationCaseApi_id).order_by("-id")
        paginator = Paginator(obi, page_size)  # paginator对象
        total = paginator.count  # 总记录数
        try:
            obm = paginator.page(page)
        except PageNotAnInteger:
            obm = paginator.page(1)
        except EmptyPage:
            obm = paginator.page(paginator.num_pages)
        serialize = CaseDataExcuteDeserializer(obm, many=True)
        return JsonResponse(data={"data": serialize.data,
                                  "page": page,
                                  "total": total
                                  }, code="999999", msg="成功！")
    @extend_schema(
        summary="修改数据库校验",
        description="修改已有的数据库校验配置",
        request=json_body(
            properties={
                "id": {"type": "integer", "description": "校验记录 ID"},
                "name": {"type": "string", "description": "校验名称"},
                "excutesql": {"type": "string", "description": "校验 SQL"},
                "dataInfo_id": {"type": "integer", "description": "数据源 ID"},
            },
            required=["id"],
        ),
        responses={
            200: success_response("成功"),
            **error_responses(),
        },
    )
    def put(self,request):
        """
        修改数据库校验
        :param data:
        :return:
        """
        try:
            data = JSONParser().parse(request)
            obj = CaseDataExcute.objects.get(id=data['id'])
            logger.info(f'CaseDatabaseCheck请求参数:{data}')
        except Exception as E:
            logger.error(f'报错信息：{E}')
            return JsonResponse(data="", msg=parameter_wrong().get('msg'), code=parameter_wrong().get('code'))
        #校验名称是否变化
        if 'name' in data and obj.name == data['name']:
            data.pop('name')
        if 'dataInfo' in data:
            data['dataInfo']=DataBaseInfo.objects.get(id=data['dataInfo_id'])
        serializer = CaseDataExcuteSerializer(data=data)
        try:
            if serializer.is_valid():
                serializer.update(instance=obj,validated_data=data)
                return JsonResponse(data=serializer.data, code=999999, msg="成功")
            else:
                return JsonResponse(data={}, code=fail().get("code"), msg=serializer.errors)
        except Exception as E:
            logger.info(E)
            return JsonResponse(data="",code=999998,msg="保存失败，请检查参数")

    @extend_schema(
        summary="删除数据库校验",
        description="批量删除数据库校验配置",
        request=json_body(
            properties={
                "ids": {
                    "type": "array",
                    "description": "校验记录 ID 列表",
                    "items": {"type": "integer"},
                },
            },
            required=["ids"],
        ),
        responses={
            200: simple_response(),
            **error_responses(),
        },
    )
    def delete(self,request):
        """
        删除数据库校验
        :param data:
        :return:
        """
        try:
            data = JSONParser().parse(request)
        except Exception:
            data = {k: v for k, v in request.GET.items()}
        try:
            ids = data.get('ids', data.get('ids[]', []))
            if isinstance(ids, str):
                ids = [int(ids)]
            obm = CaseDataExcute.objects.filter(id__in=ids)
            logger.info(f'CaseDatabaseCheck请求参数:{data}')
        except Exception as E:
            logger.error(f'参数异常：{E}')
            return JsonResponse(data="", msg=parameter_wrong().get('msg'), code=parameter_wrong().get('code'))
        if obm:
            #判断数据源是否存在
            try:
                obm.delete()
                return JsonResponse(data="", code=success().get('code'), msg=success().get('msg'))
            except Exception as E:
                logger.info(E)
                return JsonResponse(data="", code=fail().get('code'), msg=f"删除失败：{E}")
        else:
            return JsonResponse(data="", code=fail().get('code'), msg="删除失败，数据不存在")


class testRunDataCase(APIView):
    authentication_classes = (TokenAuthentication,)
    permission_classes = ()

    @extend_schema(
        summary="调试 SQL",
        description="在线调试执行 SQL 语句",
        request=json_body(
            properties={
                "type": {"type": "string", "description": "数据库类型", "enum": ["mysql"]},
                "dataInfo_id": {"type": "integer", "description": "数据源 ID"},
                "excutesql": {"type": "string", "description": "SQL 语句"},
            },
            required=["type", "dataInfo_id", "excutesql"],
        ),
        responses={
            200: success_response("执行结果", data_example={}),
            **error_responses(),
        },
    )
    def post(self,request):
        """
         调试sql
        :param data:
        :return:
        """
        data = JSONParser().parse(request)
        try:
            if not data['type'] or not data['dataInfo_id'] or not data['excutesql']:
                return  JsonResponse(data={}, code=fail().get("code"), msg="必传参数为空！")
        except KeyError:
            return JsonResponse(data={}, code=fail().get("code"), msg="缺少必传参数！")
        logger.info(f'testRunDataCase请求参数:{data}')
        db_type=data.get('type')
        dataInfo_id = data.get('dataInfo_id')
        config = DataBaseInfo.objects.filter(id=dataInfo_id).values()[0]
        config.pop("id")
        config.pop("name")
        logger.info(f'数据库配置：{config}')
        try:
            check_result = DataExcuteBase(config=config,db_type=db_type).check_database()
            if check_result==True:
                result = DataExcuteBase(config=config,db_type=db_type).execute_query(sql=data.get('excutesql'))
                if isinstance(result,list):
                    return JsonResponse(data=result[0],code="999999", msg="成功！")
                else:
                    return JsonResponse(data=result, code="999999", msg="成功！")
        except Exception as E:
            return JsonResponse(data={}, code=fail().get("code"), msg=f"失败原因：{E}")
