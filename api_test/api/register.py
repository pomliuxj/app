import logging

from django.contrib.auth.models import User
from drf_spectacular.utils import extend_schema, OpenApiExample
from rest_framework.parsers import JSONParser
from rest_framework.views import APIView
from rest_framework.authtoken.models import Token

from api_test.common.api_response import JsonResponse
from api_test.common.schema_utils import (
    success_response, error_responses, json_body,
)
from api_test.serializers import UserRegisterSerializer, TokenSerializer

logger = logging.getLogger(__name__)


class Register(APIView):
    permission_classes = ()

    def parameter_check(self, data):
        """
        校验参数
        :param data:
        :return:
        """
        try:
            # 必传参数 username, password
            if not data.get("username") or not data.get("password"):
                return JsonResponse(code="999996", msg="用户名和密码不能为空！")
            # 用户名长度校验
            if len(data["username"]) < 3 or len(data["username"]) > 50:
                return JsonResponse(code="999996", msg="用户名长度应为3-50个字符！")
            # 密码长度校验
            if len(data["password"]) < 6 or len(data["password"]) > 128:
                return JsonResponse(code="999996", msg="密码长度应为6-128个字符！")
            # 手机号格式校验（如果提供）
            phone = data.get("phone", "")
            if phone and (not phone.isdigit() or len(phone) != 11):
                return JsonResponse(code="999996", msg="手机号格式有误！")
        except Exception:
            return JsonResponse(code="999996", msg="参数有误！")

    @extend_schema(
        summary="用户注册",
        description="注册新用户账号",
        request=json_body(
            properties={
                "username": {"type": "string", "description": "用户名 (3-50字符)"},
                "password": {"type": "string", "description": "密码 (6-128字符)", "format": "password"},
                "phone": {"type": "string", "description": "手机号 (11位数字,可选)"},
            },
            required=["username", "password"],
        ),
        responses={
            200: success_response("成功", data_example={"key":"token_string","user":1,"user_id":1,"username":"admin","userphoto":"/file/userphoto.jpg"}),
            **error_responses(),
        },
    )
    def post(self, request):
        """
        用户注册
        :param request:
        :return:
        """
        data = JSONParser().parse(request)
        # 参数校验
        result = self.parameter_check(data)
        if result:
            return result
        # 检查用户名是否已存在
        if User.objects.filter(username=data["username"]).exists():
            return JsonResponse(code="999985", msg="用户名已存在！")
        # 序列化器校验并创建用户
        serialize = UserRegisterSerializer(data=data)
        if serialize.is_valid():
            user = serialize.save()
            # 获取 token 信息
            token_data = TokenSerializer(Token.objects.get(user=user)).data
            token_data["user_id"] = user.id
            token_data["username"] = user.username
            logger.info(f"新用户注册成功: {user.username}")
            return JsonResponse(data=token_data, code="999999", msg="注册成功！")
        # 提取校验错误信息
        errors = serialize.errors
        error_msg = ""
        for field, msgs in errors.items():
            if isinstance(msgs, list):
                error_msg = str(msgs[0])
            else:
                error_msg = str(msgs)
            break
        logger.warning(f"用户注册失败: {error_msg}")
        return JsonResponse(code="999996", msg=error_msg)
