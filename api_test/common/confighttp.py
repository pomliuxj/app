from .dubbo_api import Dubbo
from api_test.common.common import replace_variables
import json
import logging
import re
import operator
import requests

from django.core import serializers
from requests import ReadTimeout
from api_test.common.dataPool import query_private_keys
from api_test.common.common import check_json, record_results, get_json, resolve_step_refs, resolve_step_refs_in_string
from api_test.models import GlobalHost, AutomationCaseApi, AutomationParameter, AutomationTestResult, AutomationHead, \
    AutomationParameterRaw
from api_test.serializers import AutomationCaseApiSerializer, AutomationParameterRawSerializer

logger = logging.getLogger(__name__)  # 这里使用 __name__ 动态搜索定义的 logger 配置，这里有一个层次关系的知识点。


def test_api(prams):
    """
    执行接口测试
    :param host_id: 测试的host域名
    :param case_id: 测试用例ID
    :param _id:  用例下接口ID
    :param project_id: 所属项目
    :return:
    """
    host_id = prams[0]
    case_id = prams[1]
    project_id = prams[2]
    _id = prams[3]
    host = GlobalHost.objects.get(id=host_id, project=project_id)
    data = AutomationCaseApiSerializer(AutomationCaseApi.objects.get(id=_id, automationTestCase=case_id)).data
    http_type = data['httpType']
    request_type = data['requestType']
    if http_type == 'DUBBO':
        address = data['apiAddress']
    else:
        address = host.host + data['apiAddress']
    head = json.loads(serializers.serialize('json', AutomationHead.objects.filter(automationCaseApi=_id)))
    header = {}
    request_parameter_type = data['requestParameterType']
    examine_type = data['examineType']
    http_code = data['httpCode']
    response_parameter_list = data['responseData']
    if http_type == 'HTTP':
        url = 'http://' + address
    elif http_type == 'HTTPS':
        url = 'https://' + address
    elif http_type == 'DUBBO':
        url = host.host
    else:
        return {'success': 'false', 'case_id': _id}

    if data['requestParameterType'] == 'form-data':
        parameter_list = json.loads(serializers.serialize('json',
                                                          AutomationParameter.objects.filter(automationCaseApi=_id)))
        parameter = {}
        for i in parameter_list:
            key_ = i['fields']['name']
            value = i['fields']['value']
            if i['fields']['interrelate']:
                # If value uses new $N.field syntax, defer to resolve_step_refs()
                if value.startswith('$'):
                    parameter[key_] = value
                else:
                    try:
                        api_id = value.split('|')[0]
                        rule = value.split('|')[1]
                        responseData = json.loads(
                            AutomationTestResult.objects.get(automationCaseApi=api_id).responseData)
                        param_data = get_json(responseData, rule)
                    except Exception as e:
                        logger.error(e)
                        record_results(_id=_id, url=url, request_type=request_type, header=header,
                                       parameter=parameter,
                                       host=host.name,
                                       status_code=http_code, examine_type=examine_type,
                                       examine_data=response_parameter_list,
                                       _result='ERROR', code="", response_data="请求参数关联有误！")
                        return {'success': 'false', 'case_id': _id}

                    parameter[key_] = param_data
            else:
                parameter[key_] = value

        if data["formatRaw"]:
            request_parameter_type = "raw"

    else:
        parameter = AutomationParameterRawSerializer(AutomationParameterRaw.objects.filter(automationCaseApi=_id),
                                                     many=True).data
        if len(parameter):
            raw_data = parameter[0].get("data", "")
            if raw_data:
                try:
                    parameter = json.loads(raw_data)
                except (json.JSONDecodeError, TypeError) as e:
                    logger.warning(
                        "raw 参数解析失败(api=%s): %s\n原始数据前200字符: %s",
                        _id, e, str(raw_data)[:200],
                    )
                    # 尝试修复 LLM 生成 JSON 时的常见错误
                    fixed = raw_data
                    # 1. 中文标点 → 英文
                    fixed = fixed.replace("“", "\"").replace("”", "\"")  # ""
                    fixed = fixed.replace("，", ",")   # ，
                    fixed = fixed.replace("：", ":")   # ：
                    # 2. 单引号 → 双引号（Python dict 格式）
                    fixed = fixed.replace("'", "\"")
                    try:
                        parameter = json.loads(fixed)
                    except (json.JSONDecodeError, TypeError):
                        logger.exception("JSON 修复失败(api=%s)", _id)
                        record_results(_id=_id, url=url, request_type=request_type, header=header,
                                       parameter=raw_data, host=host.name,
                                       status_code=http_code, examine_type=examine_type,
                                       examine_data=response_parameter_list,
                                       _result='ERROR', code="", response_data="raw参数格式错误，请重新编辑接口参数")
                        return {'success': 'false', 'case_id': _id}
            else:
                parameter = {}
        else:
            parameter = {}

    for i in head:
        key_ = i['fields']['name']
        value = i['fields']['value']
        if i['fields']['interrelate']:
            # If value uses new $N.field syntax, defer to resolve_step_refs()
            if value.startswith('$'):
                header[key_] = value
            else:
                try:
                    api_id = value.split('|')[0]
                    rule = value.split('|')[1]
                    responseData = json.loads(
                        AutomationTestResult.objects.get(automationCaseApi=api_id).responseData)
                    param_data = get_json(responseData, rule)
                except Exception as e:
                    logger.error(e)
                    record_results(_id=_id, url=url, request_type=request_type, header=header, parameter=parameter,
                                   host=host.name,
                                   status_code=http_code, examine_type=examine_type,
                                   examine_data=response_parameter_list,
                                   _result='ERROR', code="", response_data="请求头关联有误！")
                    return {'success': 'false', 'case_id': _id}
                header[key_] = param_data
        else:
            header[key_] = value
    # ── Resolve unified $N.field syntax → actual values ──────────
    parameter = resolve_step_refs(parameter)
    header = resolve_step_refs(header)
    # Also resolve $N.field refs embedded in URL / address (e.g. ?project_id=$3.data.id)
    url = resolve_step_refs_in_string(url)
    address = resolve_step_refs_in_string(address)

    try:
        if request_type == 'GET':
            code, response_data, header_data = get(header, url, request_parameter_type, parameter)
        elif request_type == 'POST':
            code, response_data, header_data = post(header, url, request_parameter_type, parameter)
        elif request_type == 'PUT':
            code, response_data, header_data = put(header, url, request_parameter_type, parameter)
        elif request_type == 'DELETE':
            code, response_data, header_data = delete(header, url, parameter)
        elif request_type == 'DUBBO':
            code, response_data, header_data = dubbo(url, address, parameter)
        else:
            return {'success': 'ERROR', 'case_id': _id}
    except ReadTimeout:
        logger.exception(ReadTimeout)
        record_results(_id=_id, url=url, request_type=request_type, header=header, parameter=parameter, host=host.name,
                       status_code=http_code, examine_type=examine_type, examine_data=response_parameter_list,
                       _result='TimeOut', code="408", response_data="")
        return {'success': 'timeout', 'case_id': _id}

    # ── Always try to parse response as JSON for interrelate support ──
    _stored_response = response_data
    if isinstance(response_data, str):
        try:
            _stored_response = json.loads(response_data)
        except (json.JSONDecodeError, ValueError):
            pass  # Not valid JSON, keep raw string for storage

    success = "true"
    check_data = None
    check_code = http_code
    private_obj = query_private_keys(_id)#获取数据库查询返回变量集合
    if examine_type == 'no_check':
        record_results(_id=_id, url=url, request_type=request_type, header=header, parameter=parameter, host=host.name,
                       status_code=http_code, examine_type=examine_type, examine_data=response_parameter_list,
                       _result='PASS', code=code, response_data=_stored_response)
        return {'success': success, 'case_id': _id}

    elif examine_type == 'json':
        if isinstance(response_data, str):
            try:
                response_data = json.loads(response_data)
            except:
                logger.info(f'返回参数转换dict失败：{response_data}')
        jsonCheckDetail = data.get('jsonCheckDetail')
        jsoncheckResult = []
        if int(http_code) == code and len(jsonCheckDetail) > 0:
            for i in jsonCheckDetail:
                checkData = i.get('value')
                if '$' in checkData and private_obj:#判断校验值是否有私有变量
                    checkData = private_obj.get(checkData[1:])
                checkType = i.get('checkType')
                try:
                    responseCheckData = get_json(response_data, i.get('checkRule'))
                    if isinstance(responseCheckData, int) and checkType != 'notNull':
                        if type(responseCheckData) == bool and checkData == 'true':
                            checkData = True
                        elif type(responseCheckData) == bool and checkData == 'false':
                            checkData = False
                        elif type(responseCheckData) == bool:
                            pass
                        else:
                            checkData = int(checkData)
                    elif isinstance(responseCheckData, dict) and checkType != 'notNull':
                        checkData = json.loads(checkData)
                    elif isinstance(responseCheckData, str) and checkType != 'notNull':
                        # responseCheckData is a numeric string → try to coerce to int
                        # so that checkData (int) and responseCheckData (str) are comparable
                        try:
                            responseCheckData = int(responseCheckData)
                            checkData = int(checkData)
                        except (ValueError, TypeError):
                            pass  # Keep both as strings if coercion fails
                    result = check_json(checkData, responseCheckData, checkType=checkType)
                    jsoncheckResult.append({'checkRule': i.get('checkRule'),
                                            'checkData': checkData, 'responseCheckData': responseCheckData,
                                            'result': result})
                    check_data = jsoncheckResult
                    if not result:
                        record_results(_id=_id, url=url, request_type=request_type, header=header, parameter=parameter,
                                       status_code=http_code, examine_type="JSON校验",
                                       examine_data=json.dumps(jsoncheckResult, ensure_ascii=False),
                                       host=host.name, _result='FAIL', code=code, response_data=_stored_response)
                        success = 'false'

                except Exception as E:
                    jsoncheckResult.append({'checkRule': i.get('checkRule'),
                                            'error': str(E)})
                    record_results(_id=_id, url=url, request_type=request_type, header=header, parameter=parameter,
                                   status_code=http_code, examine_type="JSON校验",
                                   examine_data=E,
                                   host=host.name, _result='FAIL', code=code, response_data=_stored_response)
                    success = 'false'
                logger.info(f'json校验结果：{result}')
            if result == True:
                record_results(_id=_id, url=url, request_type=request_type, header=header, parameter=parameter,
                               status_code=http_code, examine_type="JSON校验",
                               examine_data=json.dumps(jsoncheckResult, ensure_ascii=False),
                               host=host.name, _result='PASS', code=code, response_data=_stored_response)
        else:
            record_results(_id=_id, url=url, request_type=request_type, header=header, parameter=parameter,
                           status_code=http_code, examine_type="JSON校验",
                           examine_data=json.dumps(jsoncheckResult, ensure_ascii=False),
                           host=host.name, _result='FAIL', code=code, response_data=_stored_response)
            success = 'false'
    elif examine_type == 'entirely_check':
        if int(http_code) == code:
            try:
                result = operator.eq(json.loads(response_parameter_list), response_data)
            except (json.JSONDecodeError, TypeError):
                logger.warning(f"完全校验 JSON 解析失败，尝试兼容 Python 字面量")
                try:
                    # 安全替代 eval：仅处理布尔/null 字面量 → JSON 兼容格式
                    normalized = (response_parameter_list
                                  .replace('True', 'true')
                                  .replace('False', 'false')
                                  .replace('None', 'null'))
                    expected = json.loads(normalized)
                    result = operator.eq(expected, response_data)
                except Exception as e2:
                    logger.exception(e2)
                    result = False
            if result:
                record_results(_id=_id, url=url, request_type=request_type, header=header, parameter=parameter,
                               status_code=http_code, examine_type="完全校验", examine_data=response_parameter_list,
                               host=host.name, _result='PASS', code=code, response_data=_stored_response)
            else:
                record_results(_id=_id, url=url, request_type=request_type, header=header, parameter=parameter,
                               status_code=http_code, examine_type="完全校验", examine_data=response_parameter_list,
                               host=host.name, _result='FAIL', code=code, response_data=_stored_response)
                success = 'false'
        else:
            record_results(_id=_id, url=url, request_type=request_type, header=header, parameter=parameter,
                           status_code=http_code, examine_type="完全校验", examine_data=response_parameter_list,
                           host=host.name, _result='FAIL', code=code, response_data=_stored_response)
            success = 'false'

    elif examine_type == 'Regular_check':
        if int(http_code) == code:
            try:
                logger.info(response_parameter_list)
                if response_parameter_list.startswith("$") and private_obj:
                    response_parameter_list = private_obj.get(response_parameter_list[1:])
                response_json = json.dumps(response_data, ensure_ascii=False, separators=(',', ':'))
                result = response_parameter_list in response_json

                check_data = response_parameter_list
            except Exception as e:
                logger.exception(e)
                success = 'false'
            if result:
                record_results(_id=_id, url=url, request_type=request_type, header=header, parameter=parameter,
                               status_code=http_code, examine_type="正则校验", examine_data=response_parameter_list,
                               host=host.name, _result='PASS', code=code, response_data=_stored_response)
            else:
                record_results(_id=_id, url=url, request_type=request_type, header=header, parameter=parameter,
                               status_code=http_code, examine_type="正则校验", examine_data=response_parameter_list,
                               host=host.name, _result='FAIL', code=code, response_data=_stored_response)
                success = 'false'
        else:
            record_results(_id=_id, url=url, request_type=request_type, header=header, parameter=parameter,
                           status_code=http_code, examine_type="正则校验", examine_data=response_parameter_list,
                           host=host.name, _result='FAIL', code=code, response_data=_stored_response)
            success = 'false'

    else:
        record_results(_id=_id, url=url, request_type=request_type, header=header, parameter=parameter,
                       status_code=http_code, examine_type=examine_type, examine_data=response_parameter_list,
                       host=host.name, _result='FAIL', code=code, response_data=_stored_response)
        success = 'false'
    return {'success': success, 'case_id': _id, 'response_data': response_data, 'check_data': check_data,
            'examine_type': examine_type, 'check_code': check_code, 'response_code': code}



class HttpClient:
    """HTTP 请求客户端"""

    def __init__(self, timeout=8):
        """
        初始化客户端
        :param timeout: 请求超时时间（秒）
        """
        self.timeout = timeout
        self.session = requests.Session()

    def _prepare_request(self, header, data, request_parameter_type=None):
        """
        准备请求数据
        :param header: 请求头
        :param data: 请求参数
        :param request_parameter_type: 参数类型 (form-data, raw, Restful)
        :return: 处理后的 header 和 data
        """
        # 参数替换
        if isinstance(data, dict):
            data = replace_variables(data)

        logger.info(f"原始数据：{data}")

        # 处理 raw 格式
        if request_parameter_type == 'raw':
            data = json.dumps(data)

        # 全局变量替换
        header = replace_variables(header)

        logger.info(f'请求参数：{data}，请求头信息：{header}')
        return header, data

    def _handle_response(self, response):
        """
        处理响应
        :param response: requests 响应对象
        :return: (status_code, response_data, headers)
        """
        try:
            return response.status_code, response.json(), response.headers
        except (json.decoder.JSONDecodeError, ValueError):
            return response.status_code, '', response.headers
        except Exception as e:
            logger.exception('ERROR')
            logger.error(e)
            return {}, {}, response.headers

    def post(self, header, address, request_parameter_type, data):
        """
        POST 请求
        :param header: 请求头
        :param address: 请求地址
        :param request_parameter_type: 接口请求参数格式 (form-data, raw, Restful)
        :param data: 请求参数
        :return: (status_code, response_data, headers)
        """
        header, data = self._prepare_request(header, data, request_parameter_type)

        if request_parameter_type == 'form-data':
            response = self.session.post(url=address, data=data, headers=header, timeout=self.timeout)
        else:
            response = self.session.post(url=address, data=data, headers=header, timeout=self.timeout)

        return self._handle_response(response)

    def get(self, header, address, request_parameter_type, data):
        """
        GET 请求
        :param header: 请求头
        :param address: 请求地址
        :param request_parameter_type: 接口请求参数格式 (form-data, raw, Restful)
        :param data: 请求参数
        :return: (status_code, response_data, headers)
        """
        header, data = self._prepare_request(header, data, request_parameter_type)

        response = self.session.get(url=address, params=data, headers=header, timeout=self.timeout)

        # 处理 301 重定向
        if response.status_code == 301:
            response = self.session.get(url=response.headers["location"])

        return self._handle_response(response)

    def put(self, header, address, request_parameter_type, data):
        """
        PUT 请求
        :param header: 请求头
        :param address: 请求地址
        :param request_parameter_type: 接口请求参数格式 (form-data, raw, Restful)
        :param data: 请求参数
        :return: (status_code, response_data, headers)
        """
        header, data = self._prepare_request(header, data, request_parameter_type)

        response = self.session.put(url=address, data=data, headers=header, timeout=self.timeout)
        return self._handle_response(response)

    def delete(self, header, address, data):
        """
        DELETE 请求
        :param header: 请求头
        :param address: 请求地址
        :param data: 请求参数
        :return: (status_code, response_data, headers)
        """
        header, data = self._prepare_request(header, data)

        response = self.session.delete(url=address, params=data, headers=header, timeout=self.timeout)
        return self._handle_response(response)


class DubboClient:
    """Dubbo 请求客户端"""

    def __init__(self, connect_timeout=20):
        """
        初始化 Dubbo 客户端
        :param connect_timeout: 连接超时时间（秒）
        """
        self.connect_timeout = connect_timeout

    def invoke(self, url, classpath, data):
        """
        调用 Dubbo 接口
        :param url: Dubbo 地址 (格式：ip:port)
        :param classpath: 类路径
        :param data: 请求参数
        :return: (status_code, response_data, message)
        """
        # 解析 URL
        try:
            listIP = url.split(':', 1)
            ip = listIP[0]
            port = listIP[1]
        except Exception as E:
            logger.info(E)
            return 404, 'dubbo host type not support', None

        # 创建连接
        try:
            conn = Dubbo(ip, port)
            conn.set_connect_timeout(self.connect_timeout)
        except ConnectionError as E:
            return 408, E, None

        # 发送请求
        try:
            if isinstance(data, dict):
                data = replace_variables(data)

            if not isinstance(data, str):
                data = json.dumps(data, ensure_ascii='utf-8')

            response = conn.invoke(classpath, data)
            return 200, response, 'None'
        except Exception as E:
            logger.info(E)
            return 500, E, None


# 创建全局单例
http_client = HttpClient()
dubbo_client = DubboClient()



def post(header, address, request_parameter_type, data):
    """
    post 请求（兼容旧代码）
    :param header:  请求头
    :param address: host 地址
    :param request_parameter_type: 接口请求参数格式（form-data, raw, Restful）
    :param data: 请求参数
    :return:
    """
    return http_client.post(header, address, request_parameter_type, data)


def get(header, address, request_parameter_type, data):
    """
    get 请求（兼容旧代码）
    :param header:  请求头
    :param address: host 地址
    :param request_parameter_type: 接口请求参数格式（form-data, raw, Restful）
    :param data: 请求参数
    :return:
    """
    return http_client.get(header, address, request_parameter_type, data)


def put(header, address, request_parameter_type, data):
    """
    put 请求（兼容旧代码）
    :param header:  请求头
    :param address: host 地址
    :param request_parameter_type: 接口请求参数格式（form-data, raw, Restful）
    :param data: 请求参数
    :return:
    """
    return http_client.put(header, address, request_parameter_type, data)


def delete(header, address, data):
    """
    delete 请求（兼容旧代码）
    :param header:  请求头
    :param address: host 地址
    :param data: 请求参数
    :return:
    """
    return http_client.delete(header, address, data)


def dubbo(url, classpath, data):
    """
    dubbo 请求（兼容旧代码）
    :param url: dubbo 地址
    :param classpath: 类路径
    :param data: 请求参数
    :return:
    """
    status, response, _ = dubbo_client.invoke(url, classpath, data)
    return status, response


