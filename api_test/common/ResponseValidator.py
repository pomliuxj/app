
import json
import logging
import re
import operator

from api_test.common.common import check_json, record_results, get_json

logger = logging.getLogger(__name__)  # 这里使用 __name__ 动态搜索定义的 logger 配置，这里有一个层次关系的知识点。


class ResponseValidator:
    """响应校验器"""

    def __init__(self, test_id, url, request_type, header, parameter, host_name,
                 status_code, examine_type, examine_data, code, response_data, api_data, private_obj=None):
        self.test_id = test_id
        self.url = url
        self.request_type = request_type
        self.header = header
        self.parameter = parameter
        self.host_name = host_name
        self.status_code = status_code
        self.examine_type = examine_type
        self.examine_data = examine_data
        self.code = code
        self.response_data = response_data
        self.api_data = api_data
        self.private_obj = private_obj

    def validate(self):
        """执行校验"""
        validators = {
            'no_check': self._validate_no_check,
            'json': self._validate_json,
            'entirely_check': self._validate_entirely,
            'Regular_check': self._validate_regular,
        }

        validator = validators.get(self.examine_type)
        if validator:
            return validator()
        else:
            return self._validate_fail()

    def _record_result(self, result, examine_type=None, examine_data=None):
        """记录结果"""
        record_results(
            _id=self.test_id,
            url=self.url,
            request_type=self.request_type,
            header=self.header,
            parameter=self.parameter,
            host=self.host_name,
            status_code=self.status_code,
            examine_type=examine_type or self.examine_type,
            examine_data=examine_data or self.examine_data,
            _result=result,
            code=self.code,
            response_data=self.response_data
        )

    def _validate_no_check(self):
        """不校验"""
        self._record_result('PASS')
        return {'success': 'true', 'case_id': self.test_id}

    def _validate_json(self):
        """JSON 校验"""
        response_data = self._convert_response_data()
        jsonCheckDetail = self.api_data.get('jsonCheckDetail', [])

        if int(self.status_code) != self.code or not jsonCheckDetail:
            self._record_result('FAIL', examine_type="JSON 校验")
            return {'success': 'false', 'case_id': self.test_id}

        jsoncheckResult = []

        for check_item in jsonCheckDetail:
            try:
                result = self._check_single_json(check_item, response_data)
                jsoncheckResult.append(result)

                if not result['result']:
                    self._record_json_result(jsoncheckResult, 'FAIL')
                    return {'success': 'false', 'case_id': self.test_id}

            except Exception as E:
                jsoncheckResult.append({
                    'checkRule': check_item.get('checkRule'),
                    'error': str(E)
                })
                self._record_json_result(jsoncheckResult, 'FAIL', error=E)
                return {'success': 'false', 'case_id': self.test_id}

            logger.info(f'json 校验结果：{result["result"]}')

        self._record_json_result(jsoncheckResult, 'PASS')
        return {'success': 'true', 'case_id': self.test_id}

    def _check_single_json(self, check_item, response_data):
        """检查单个 JSON 字段"""
        checkData = check_item.get('value')

        # 处理私有变量
        if '$' in checkData and self.private_obj:
            checkData = self.private_obj.get(checkData[1:])

        checkType = check_item.get('checkType')
        responseCheckData = get_json(response_data, check_item.get('checkRule'))

        # 数据类型转换
        checkData = self._convert_check_data(checkData, checkType, responseCheckData)

        # 执行校验
        result = check_json(checkData, responseCheckData, checkType=checkType)

        return {
            'checkRule': check_item.get('checkRule'),
            'checkData': checkData,
            'responseCheckData': responseCheckData,
            'result': result
        }

    def _convert_check_data(self, checkData, checkType, responseCheckData):
        """转换校验数据类型"""
        if checkType == 'notNull':
            return checkData

        if isinstance(responseCheckData, bool):
            if checkData == 'true':
                return True
            elif checkData == 'false':
                return False
        elif isinstance(responseCheckData, int):
            try:
                return int(checkData)
            except (ValueError, TypeError):
                pass
        elif isinstance(responseCheckData, dict):
            try:
                return json.loads(checkData)
            except:
                pass

        return checkData

    def _validate_entirely(self):
        """完全校验"""
        if int(self.status_code) != self.code:
            self._record_result('FAIL', examine_type="完全校验")
            return {'success': 'false', 'case_id': self.test_id}

        try:
            expected = json.loads(self.examine_data)
            result = operator.eq(expected, self.response_data)
        except Exception as e:
            logger.exception(e)
            try:
                expected = eval(
                    self.examine_data.replace('true', 'True')
                    .replace('false', 'False')
                    .replace("null", "None")
                )
                result = operator.eq(expected, self.response_data)
            except:
                result = False

        examine_type = "完全校验"
        if result:
            self._record_result('PASS', examine_type=examine_type)
            return {'success': 'true', 'case_id': self.test_id}
        else:
            self._record_result('FAIL', examine_type=examine_type)
            return {'success': 'false', 'case_id': self.test_id}

    def _validate_regular(self):
        """正则校验"""
        if int(self.status_code) != self.code:
            self._record_result('FAIL', examine_type="正则校验")
            return {'success': 'false', 'case_id': self.test_id}

        try:
            pattern = self.examine_data

            # 处理私有变量
            if pattern.startswith("$") and self.private_obj:
                pattern = self.private_obj.get(pattern[1:])

            result = re.findall(
                pattern,
                json.dumps(self.response_data).encode('latin-1').decode('unicode_escape')
            )
            logger.info(f'正则匹配结果：{result}')

        except Exception as e:
            logger.exception(e)
            return {'success': 'false', 'case_id': self.test_id}

        examine_type = "正则校验"
        if result:
            self._record_result('PASS', examine_type=examine_type)
            return {'success': 'true', 'case_id': self.test_id}
        else:
            self._record_result('FAIL', examine_type=examine_type)
            return {'success': 'false', 'case_id': self.test_id}

    def _validate_fail(self):
        """默认失败"""
        self._record_result('FAIL')
        return {'success': 'false', 'case_id': self.test_id}

    def _record_json_result(self, jsoncheckResult, result, error=None):
        """记录 JSON 校验结果"""
        examine_data = error if error else json.dumps(jsoncheckResult, ensure_ascii=False)
        self._record_result(result, examine_type="JSON 校验", examine_data=examine_data)

    def _convert_response_data(self):
        """转换响应数据为 dict"""
        if isinstance(self.response_data, str):
            try:
                return json.loads(self.response_data)
            except:
                logger.info(f'返回参数转换 dict 失败：{self.response_data}')
                return self.response_data
        return self.response_data

