from rest_framework import parsers, renderers
from rest_framework.authtoken.models import Token
from rest_framework.authtoken.serializers import AuthTokenSerializer
from rest_framework.views import APIView
from drf_spectacular.utils import extend_schema, OpenApiResponse, OpenApiExample
from api_test.serializers import TokenSerializer
from api_test.common.api_response import JsonResponse


class ObtainAuthToken(APIView):
    throttle_classes = ()
    permission_classes = ()
    parser_classes = (parsers.FormParser, parsers.MultiPartParser, parsers.JSONParser,)
    renderer_classes = (renderers.JSONRenderer,)
    serializer_class = AuthTokenSerializer

    @extend_schema(
        summary="用户登录",
        description="用户登录接口，成功返回用户信息和 token",
        request={
            "application/json": {
                "type": "object",
                "required": ["username", "password"],
                "properties": {
                    "username": {"type": "string", "description": "用户名"},
                    "password": {"type": "string", "description": "密码", "format": "password"},
                },
            }
        },
        responses={
            200: OpenApiResponse(
                description="登录成功",
                response=TokenSerializer,
                examples=[
                    OpenApiExample(
                        "success",
                        value={
                            "code": "999999",
                            "msg": "成功",
                            "data": {"key": "token_string", "user": 1, "userphoto": "/file/userphoto.jpg"},
                        },
                    )
                ],
            ),
            400: OpenApiResponse(
                description="请求参数错误",
                examples=[
                    OpenApiExample(
                        "error",
                        value={"code": "999996", "msg": "用户名或密码错误"},
                    )
                ],
            ),
        },
    )
    def post(self, request, *args, **kwargs):
        """
        用户登录
        :param request:
        :param args:
        :param kwargs:
        :return:
        """
        serializer = self.serializer_class(data=request.data,
                                           context={"request": request})
        serializer.is_valid(raise_exception=True)
        user = serializer.validated_data["user"]
        data = TokenSerializer(Token.objects.get(user=user)).data
        data["userphoto"] = '/file/userphoto.jpg'
        return JsonResponse(data=data, code="999999", msg="成功")


obtain_auth_token = ObtainAuthToken.as_view()
