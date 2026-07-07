import json
import logging
import re
import operator
from django.core import serializers
from requests import ReadTimeout
from api_test.common.dataPool import query_private_keys
from api_test.common.confighttp import get, post, put, delete,dubbo
from api_test.common.common import check_json, record_auto_results, get_json, resolve_step_refs, resolve_step_refs_in_string
from api_test.models import AutomationCaseApi, AutomationParameter, AutomationHead, \
    AutomationParameterRaw, AutomationCaseTestResult
from api_test.serializers import AutomationCaseApiSerializer, AutomationParameterRawSerializer

logger = logging.getLogger(__name__)  # 这里使用 __name__ 动态搜索定义的 logger 配置，这里有一个层次关系的知识点。


def test_api(host, case_id, _id, time):
    """
    执行接口测试
    :param host: 测试的host域名
    :param case_id: 测试用例ID
    :param _id:  用例下接口ID
    :param time: 测试时间
    :return:
    """
    data = AutomationCaseApiSerializer(AutomationCaseApi.objects.get(id=_id, automationTestCase=case_id)).data
    http_type = data['httpType']
    request_type = data['requestType']
    if http_type == 'DUBBO':
        address = data['apiAddress']
    else:
        address = host + data['apiAddress']
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
        url = host
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
                        quetySet = \
                        AutomationCaseTestResult.objects.filter(automationCaseApi=api_id).order_by('-id').values()[0]
                        responseData = json.loads(quetySet.get("responseData"))
                        param_data = get_json(responseData, rule)
                        logger.info(f'依赖参数param_data：{param_data}')
                    except Exception as e:
                        logger.error(e)
                        record_auto_results(_id=_id, header=header, parameter=parameter,
                                            _result='ERROR', code="", response_data="请求参数关联错误！", time=time,
                                            responseHeader="{}")
                        return 'ERROR'
                    parameter[key_] = param_data
            else:
                parameter[key_] = value
        if data["formatRaw"]:
            request_parameter_type = "raw"
    else:
        parameter = AutomationParameterRawSerializer(AutomationParameterRaw.objects.filter(automationCaseApi=_id),
                                                     many=True).data
        if len(parameter[0]["data"]):
            raw_data = parameter[0]["data"]
            try:
                parameter = json.loads(raw_data)
            except (json.JSONDecodeError, TypeError):
                # 尝试修复 LLM 生成 JSON 时的常见错误
                fixed = raw_data
                fixed = fixed.replace(""", "\"").replace(""", "\"")
                fixed = fixed.replace("，", ",").replace("：", ":")
                fixed = fixed.replace("'", "\"")
                try:
                    parameter = json.loads(fixed)
                except Exception:
                    record_auto_results(_id=_id, header=header, parameter=parameter,
                                        _result='ERROR', code="", response_data="", time=time, responseHeader="{}")
                    return 'fail'
        else:
            parameter = []

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
                    quetySet = AutomationCaseTestResult.objects.filter(automationCaseApi=api_id).order_by('-id').values()[0]
                    responseData = json.loads(quetySet.get("responseData"))
                    param_data = get_json(responseData, rule)
                    logger.info(f'依赖参数param_data：{param_data}')
                except Exception as e:
                    logger.error(e)
                    record_auto_results(_id=_id, header=header, parameter=parameter,
                                        _result='ERROR', code="", response_data="请求头关联错误！",
                                        time=time, responseHeader="{}")
                    return 'ERROR'
                header[key_] = param_data
        else:
            header[key_] = value
    # ── Resolve unified $N.field syntax → internal format ──────────
    parameter = resolve_step_refs(parameter)
    header = resolve_step_refs(header)
    # Also resolve $N.field refs embedded in URL / address (e.g. ?project_id=$3.data.id)
    url = resolve_step_refs_in_string(url)
    address = resolve_step_refs_in_string(address)

    # header["Content-Length"] = '%s' % len(str(parameter))
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
            return 'ERROR'
    except ReadTimeout:
        record_auto_results(_id=_id, header=header, parameter=parameter,
                            _result='TimeOut', code="", response_data="", time=time, responseHeader="{}")
        return 'timeout'

    # ── Always try to parse response as JSON for interrelate support ──
    # This is independent of examine_type — interrelate data extraction
    # should work regardless of how the response is validated.
    _stored_response = response_data
    if isinstance(response_data, str):
        try:
            _stored_response = json.loads(response_data)
        except (json.JSONDecodeError, ValueError):
            pass  # Not valid JSON, keep raw string for storage

    private_obj = query_private_keys(_id)  # 获取数据库查询返回变量集合
    if examine_type == 'no_check':
        record_auto_results(_id=_id, header=header, parameter=parameter,
                            _result='PASS', code=code, response_data=_stored_response,
                            time=time, responseHeader=header_data)
        return 'success'

    elif examine_type == 'json':
        if int(http_code) == code:
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
                    if '$' in checkData and private_obj:  # 判断校验值是否有私有变量
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
                            try:
                                responseCheckData = int(responseCheckData)
                                checkData = int(checkData)
                            except (ValueError, TypeError):
                                pass
                        result = check_json(checkData, responseCheckData, checkType=checkType)
                        jsoncheckResult.append({'checkRule': i.get('checkRule'),
                                                'checkData': checkData, 'responseCheckData': responseCheckData,
                                                'result': result})
                        if not result:
                            record_auto_results(_id=_id, header=header, parameter=parameter,
                                                _result='FAIL', code=code, response_data=_stored_response,
                                                time=time,
                                                responseHeader=json.dumps(jsoncheckResult, ensure_ascii=False))
                            return 'fail'
                    except Exception as E:
                        jsoncheckResult.append({'checkRule': i.get('checkRule'),
                                                'error': str(E)})
                        record_auto_results(_id=_id, header=header, parameter=parameter,
                                            _result='FAIL', code=code, response_data=_stored_response,
                                            time=time, responseHeader=jsoncheckResult)
                        return 'fail'

                    logger.info(f'json校验结果：{result}')
                if result == True:
                    record_auto_results(_id=_id, header=header, parameter=parameter,
                                        _result='PASS', code=code, response_data=_stored_response,
                                        time=time, responseHeader=json.dumps(jsoncheckResult, ensure_ascii=False))
                    return 'success'
            else:
                record_auto_results(_id=_id, header=header, parameter=parameter,
                                    _result='FAIL', code=code, response_data=_stored_response,
                                    time=time, responseHeader=json.dumps(jsoncheckResult, ensure_ascii=False))
                return 'fail'
    elif examine_type == 'entirely_check':
        if int(http_code) == code:
            try:
                result = operator.eq(eval(response_parameter_list), response_data)
            except:
                result = operator.eq(eval(
                    response_parameter_list.replace('true', 'True').replace('false', 'False').replace("null", "None")),
                                     response_data)
            if result:
                record_auto_results(_id=_id, header=header, parameter=parameter,
                                    _result='PASS', code=code, response_data=_stored_response,
                                    time=time, responseHeader=header_data)
                return 'success'
            else:
                record_auto_results(_id=_id, header=header, parameter=parameter,
                                    _result='FAIL', code=code, response_data=_stored_response,
                                    time=time, responseHeader=header_data)
                return 'fail'
        else:
            record_auto_results(_id=_id, header=header, parameter=parameter,
                                _result='FAIL', code=code, response_data=_stored_response,
                                time=time, responseHeader=header_data)
            return 'fail'

    elif examine_type == 'Regular_check':
        if int(http_code) == code:
            try:
                logging.info(response_parameter_list)
                if response_parameter_list.startswith("$") and private_obj:
                    response_parameter_list = private_obj.get(response_parameter_list[1:])
                result = re.findall(response_parameter_list,
                                    json.dumps(response_data).encode('latin-1').decode('unicode_escape'))
                logging.info(result)
            except Exception as e:
                logging.exception(e)
                return "fail"
            if result:
                record_auto_results(_id=_id, header=header, parameter=parameter,
                                    _result='PASS', code=code, response_data=_stored_response,
                                    time=time, responseHeader=header_data)
                return 'success'
            else:
                record_auto_results(_id=_id, header=header, parameter=parameter,
                                    _result='FAIL', code=code, response_data=_stored_response,
                                    time=time, responseHeader=header_data)
                return 'fail'
        else:
            record_auto_results(_id=_id, header=header, parameter=parameter,
                                _result='FAIL', code=code, response_data=_stored_response,
                                time=time, responseHeader=header_data)
            return 'fail'

    else:
        record_auto_results(_id=_id, header=header, parameter=parameter,
                            _result='FAIL', code=code, response_data=_stored_response,
                            time=time, responseHeader=header_data)
        return 'fail'
