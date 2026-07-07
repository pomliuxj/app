import datetime
import json
import logging
import re
import threading
import django
import sys
import os

from api_test.serializers import ProjectDynamicDeserializer
from  api_test.common.debug_code import RunOnlineCode
curPath = os.path.abspath(os.path.dirname(__file__))
rootPath = os.path.split(curPath)[0]

logger = logging.getLogger(__name__)

# Thread-local step→api_id mapping for $N.field syntax resolution
_step_map_local = threading.local()


def set_step_id_map(step_map: dict):
    """Set the step→api_id mapping for the current execution thread."""
    _step_map_local.map = step_map


def get_step_id_map() -> dict:
    """Get the step→api_id mapping for the current execution thread."""
    return getattr(_step_map_local, 'map', {})


_STEP_REF_RE = re.compile(r'^\$(\d+)\.(.+)$')
# For finding $N.field.path embedded inside longer strings (e.g. URLs)
_SUB_STEP_REF_RE = re.compile(r'\$(\d+)\.([\w.\[\]]+)')


def _lookup_step_response(step_num, field_path, api_id):
    """
    Look up a stored response for the given api_id and extract field_path.

    Tries AutomationTestResult (manual test) first, then falls back to
    AutomationCaseTestResult (auto / sequential test).

    Returns the extracted value, or None if not found / extraction failed.
    """
    # Try manual-test result table first
    try:
        result = AutomationTestResult.objects.get(automationCaseApi=api_id)
        response_data = json.loads(result.responseData)
        resolved = get_json(response_data, field_path)
        logger.info(
            "resolve_step_refs: $%d.%s → api_id=%s (AutomationTestResult) → value=%s",
            step_num, field_path, api_id, resolved,
        )
        return resolved
    except AutomationTestResult.DoesNotExist:
        pass
    except Exception:
        logger.exception(
            "resolve_step_refs: $%d.%s → api_id=%s (AutomationTestResult) → FAILED",
            step_num, field_path, api_id,
        )

    # Fall back to auto / sequential test result table
    try:
        qs = AutomationCaseTestResult.objects.filter(
            automationCaseApi=api_id,
        ).order_by('-id').values()
        if qs:
            response_data = json.loads(qs[0].get("responseData", "{}"))
            resolved = get_json(response_data, field_path)
            logger.info(
                "resolve_step_refs: $%d.%s → api_id=%s (AutomationCaseTestResult) → value=%s",
                step_num, field_path, api_id, resolved,
            )
            return resolved
    except Exception:
        logger.exception(
            "resolve_step_refs: $%d.%s → api_id=%s (AutomationCaseTestResult) → FAILED",
            step_num, field_path, api_id,
        )

    logger.warning(
        "resolve_step_refs: $%d.%s → api_id=%s → NO stored response in either table "
        "(step may not have executed yet, or self-reference)",
        step_num, field_path, api_id,
    )
    return None


def resolve_step_refs(value, step_id_map=None):
    """
    Resolve unified $N.field.path syntax to the actual value from a
    previous step's stored response.

    ``$1.data.token`` → looks up Step 1's response → extracts data.token
    ``$var.xxx`` → untouched (handled by replace_variables later)

    Recurses into dicts and lists.
    """
    if step_id_map is None:
        step_id_map = get_step_id_map()
    if not step_id_map:
        logger.debug("resolve_step_refs: step_id_map is empty, skipping resolution")
        return value

    if isinstance(value, dict):
        return {k: resolve_step_refs(v, step_id_map) for k, v in value.items()}
    if isinstance(value, list):
        return [resolve_step_refs(v, step_id_map) for v in value]
    if isinstance(value, str):
        m = _STEP_REF_RE.match(value)
        if m:
            step_num = int(m.group(1))
            field_path = m.group(2)
            logger.info("resolve_step_refs: matched $%d.%s, step_id_map=%s", step_num, field_path, step_id_map)
            if step_num in step_id_map:
                api_id = step_id_map[step_num]
                resolved = _lookup_step_response(step_num, field_path, api_id)
                if resolved is not None:
                    return resolved
            else:
                logger.warning(
                    "resolve_step_refs: step_num=%d not found in step_id_map=%s",
                    step_num, step_id_map,
                )
            # Keep original string if resolution failed
    return value


def resolve_step_refs_in_string(value: str, step_id_map=None) -> str:
    """
    Resolve $N.field.path references embedded *inside* a longer string
    (e.g. URL query strings like ``/api/foo?project_id=$3.data.id``).

    Each ``$N.field.path`` token found anywhere in the string is replaced
    with its resolved value (stringified).  Tokens that can't be resolved
    are left unchanged.

    Returns the (possibly modified) string.
    """
    if not isinstance(value, str):
        return value
    if step_id_map is None:
        step_id_map = get_step_id_map()
    if not step_id_map:
        logger.debug("resolve_step_refs_in_string: empty step_id_map, skipping")
        return value

    def _replacer(m: re.Match) -> str:
        step_num = int(m.group(1))
        field_path = m.group(2)
        if step_num in step_id_map:
            api_id = step_id_map[step_num]
            resolved = _lookup_step_response(step_num, field_path, api_id)
            if resolved is not None:
                return str(resolved)
        # Leave unresolved references as-is
        return m.group(0)

    return _SUB_STEP_REF_RE.sub(_replacer, value)


PathProject = os.path.split(rootPath)[0]
sys.path.append(rootPath)
sys.path.append(PathProject)
os.environ.setdefault("DJANGO_SETTINGS_MODULE", "api_automation_test.settings")
django.setup()
import logging
logger = logging.getLogger(__name__)

from rest_framework.views import exception_handler

from api_test.models import AutomationTestResult, AutomationCaseApi, AutomationResponseJson, \
    AutomationCaseTestResult,OnlineCode


def custom_exception_handler(exc, context):
    # Call REST framework's default exception handler first,
    # to get the standard error response.
    response = exception_handler(exc, context)
    # Now add the HTTP status code to the response.
    if response is not None:
        try:
            response.data['code'] = response.status_code
            response.data['msg'] = response.data['detail']
            #   response.data['data'] = None #可以存在
            # 删除detail字段
            del response.data['detail']
        except KeyError:
            for k, v in dict(response.data).items():
                if v == ['无法使用提供的认证信息登录。']:
                    if response.status_code == 400:
                        response.status_code = 200
                    response.data = {}
                    response.data['code'] = '999984'
                    response.data['msg'] = '账号或密码错误'
                elif v == ['该字段是必填项。']:
                    if response.status_code == 400:
                        response.status_code = 200
                    response.data = {}
                    response.data['code'] = '999996'
                    response.data['msg'] = '参数有误'

    return response



# result = True
def check_json(src_data, dst_data, checkType):
    """
    校验的json
    :param checkType:  校验类型
    :param src_data:  校验内容
    :param dst_data:  接口返回的数据（被校验的内容
    :return:
    """
    try:
        if checkType == 'equal':
            if isinstance(src_data, dict):
                if len(src_data.keys()) != len(dst_data.keys()):
                    return False
                for key in src_data.keys():
                    if key in dst_data.keys():
                        if not check_json(src_data[key], dst_data[key], checkType='equal'):
                            return False
                    else:
                        return False
                return True
            elif isinstance(src_data, list):
                if len(src_data) == len(dst_data):
                    for src, dst in zip(sorted(src_data), sorted(dst_data)):
                        if not check_json(src, dst, checkType='equal'):
                            return False
                    return True
                else:
                    return False
            elif isinstance(src_data, (str, int, bool)):
                return src_data == dst_data
            return False
        elif checkType == 'contain':
            if isinstance(src_data, dict):
                for key in src_data.keys():
                    if key in dst_data.keys():
                        if not check_json(src_data[key], dst_data[key], checkType='contain'):
                            return False
                    else:
                        return False
                return True
            elif isinstance(src_data, list):
                for src, dst in zip(sorted(src_data), sorted(dst_data)):
                    if not check_json(src, dst, checkType='contain'):
                        return False
                return True
            elif isinstance(src_data, (str, int, bool)):
                return src_data == dst_data
            return False
        elif checkType == 'gte':
            try:
                if isinstance(src_data, str): src_data = int(src_data)
                if isinstance(dst_data, str): dst_data = int(dst_data)
            except (ValueError, TypeError):
                pass
            if isinstance(src_data, int) and isinstance(dst_data, int):
                return src_data >= dst_data
            return False
        elif checkType == 'lte':
            try:
                if isinstance(src_data, str): src_data = int(src_data)
                if isinstance(dst_data, str): dst_data = int(dst_data)
            except (ValueError, TypeError):
                pass
            if isinstance(src_data, int) and isinstance(dst_data, int):
                return src_data <= dst_data
            return False
        elif checkType == 'notNull':
            if dst_data is not None and src_data == 'true': return True
            elif dst_data is None and src_data == 'false': return True
            elif dst_data is not None: return True
            return False
        return False
    except Exception as E:
        logger.info(f'校验的json报错:{E}')
        return False


def get_json(jsonData: dict, checkRule: str):
    """
    从 JSON 响应中按路径提取值
    支持两种格式: "data.token" 或 ".data.token"（兼容旧格式）
    支持数组索引: "data.list.0.id"
    """
    try:
        rulelist = checkRule.split('.')
        if rulelist and rulelist[0] == '':
            rulelist.pop(0)
        for key in rulelist:
            try:
                key = int(key)
            except (ValueError, TypeError):
                pass
            try:
                jsonData = jsonData[key]
            except (KeyError, IndexError):
                return f'response cant find key {key}'
    except Exception:
        pass
    return jsonData


def record_results(_id, url, request_type, header, parameter, host,
                   status_code, examine_type, examine_data, _result, code, response_data):
    """
    记录手动测试结果
    :param _id: ID
    :param url:  请求地址
    :param request_type:  请求方式
    :param header: 请求头
    :param parameter: 请求参数
    :param status_code: 期望HTTP状态
    :param examine_type: 校验方式
    :param examine_data: 校验内容
    :param _result:  是否通过
    :param code:  HTTP状态码
    :param response_data:  返回结果
    :param host:  测试地址
    :return:
    """
    rt = AutomationTestResult.objects.filter(automationCaseApi=_id)
    try:
        if isinstance(examine_data,(dict,list)):
            examine_data=json.dumps(examine_data,ensure_ascii=False)
        if isinstance(header,dict):
            header=json.dumps(header,ensure_ascii=False)
        if isinstance(parameter,(dict, list)):
            parameter=json.dumps(parameter,ensure_ascii=False)
        if isinstance(response_data,dict):
            response_data=json.dumps(response_data,ensure_ascii=False)
    except Exception as E:
        logger.info(f'转换json失败:{E}')
    if rt:
        rt.update(url=url, requestType=request_type, header=header, parameter=parameter, host=host,
                  statusCode=status_code, examineType=examine_type, data=examine_data,
                  result=_result, httpStatus=code, responseData=response_data)
    else:
        result_ = AutomationTestResult(automationCaseApi=AutomationCaseApi.objects.get(id=_id), host=host,
                                       url=url, requestType=request_type, header=header, parameter=parameter,
                                       statusCode=status_code, examineType=examine_type, data=examine_data,
                                       result=_result, httpStatus=code, responseData=response_data)
        result_.save()


def record_auto_results(_id, time,  header, parameter, _result, responseHeader, code, response_data):
    """
    记录自动测试结果
    :param _id: ID
    :param time:  测试时间
    :param header: 请求头
    :param parameter: 请求参数
    :param _result:  是否通过
    :param code:  HTTP状态码
    :param responseHeader:  返回头
    :param response_data:  返回结果
    :return:
    """
    rt = AutomationCaseTestResult.objects.filter(automationCaseApi=_id)
    try:
        if isinstance(responseHeader, (dict, list)):
            responseHeader = json.dumps(responseHeader, ensure_ascii=False)
        if isinstance(header, dict):
            header = json.dumps(header, ensure_ascii=False)
        if isinstance(parameter, (dict, list)):
            parameter = json.dumps(parameter, ensure_ascii=False)
        if isinstance(response_data, dict):
            response_data = json.dumps(response_data, ensure_ascii=False)
    except Exception as E:
        logger.info(f'转换json失败:{E}')
    result_ = AutomationCaseTestResult(automationCaseApi=AutomationCaseApi.objects.get(id=_id), header=header,
                                       parameter=parameter, testTime=time, responseHeader=responseHeader,
                                       result=_result, httpStatus=code, responseData=response_data)
    result_.save()


def create_json(api_id, api, data):
    """
    根据json数据生成关联数据接口
    :param api_id: 接口ID
    :param data: Json数据
    :param api: 格式化api数据
    :return:
    """
    if isinstance(data, dict):
        for i in data:
            m = (api+"[\"%s\"]" % i)
            AutomationResponseJson(automationCaseApi=api_id, name=i, tier=m, type='json').save()
            create_json(api_id, m, data[i])


def record_dynamic(project, _type, operationObject,  user, data):
    """
    记录动态
    :param project: 项目ID
    :param _type: 类型
    :param operationObject:  操作对象
    :param user:  用户ID
    :param data:  操作内容
    :return:
    """
    time = datetime.datetime.now()
    dynamic_serializer = ProjectDynamicDeserializer(
        data={
            "time": time,
            "project": project, "type": _type,
            "operationObject": operationObject, "user": user,
            "description": data
        }
    )
    if dynamic_serializer.is_valid():
        dynamic_serializer.save()



def replace_variables(reqdata:dict):
    """
    变量替换 — 支持 $变量名 和 $var.变量名 两种格式
    注意：$N.xxx 格式的步骤引用应该先经过 resolve_step_refs() 转换，不应到达这里
    :param reqdata: 请求参数
    :return:
    """
    for i in reqdata.keys():
        values = reqdata.get(i)
        if isinstance(values, str):
            if values[:1] == '$':
                name = values[1:]
                # 跳过步骤引用（$N.xxx，N是数字），不应到这里
                if name and name[0].isdigit():
                    continue
                # 兼容 $var.变量名 格式 → 剥离 var. 前缀
                if name.startswith("var."):
                    name = name[4:]
                try:
                    obj = OnlineCode.objects.get(variablesName=name)
                    if obj:
                        resp = RunOnlineCode(obj.Code, obj.variablesName).run().replace('\n', '').replace('\r', '')
                        reqdata[i] = resp
                except Exception as E:
                    logger.error(f'RunOnlineCode 异常报错:{E}')

        elif isinstance(values, dict):
            replace_variables(values)

        elif isinstance(values, list):
            for j in range(len(values)):
                if isinstance(values[j], str):
                    if values[j][:1] == '$':
                        name = values[j][1:]
                        if name and name[0].isdigit():
                            continue
                        if name.startswith("var."):
                            name = name[4:]
                        try:
                            obj = OnlineCode.objects.get(variablesName=name)
                            if obj:
                                resp = RunOnlineCode(obj.Code, obj.variablesName).run().replace('\n', '').replace('\r', '')
                                values[j] = resp
                        except Exception as E:
                            logger.error(f'RunOnlineCode 异常报错:{E}')
                elif isinstance(values[j], dict):
                    replace_variables(values[j])
                else:
                    continue
        else:
            continue
    return reqdata

