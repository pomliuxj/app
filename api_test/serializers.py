from django.contrib.auth.models import User
from rest_framework import serializers
from rest_framework.authtoken.models import Token

from api_test.models import Project, ProjectDynamic, ProjectMember, GlobalHost, ApiGroupLevelFirst, \
    ApiInfo, APIRequestHistory, ApiOperationHistory, AutomationGroupLevelFirst, \
    AutomationTestCase, AutomationCaseApi, AutomationHead, AutomationParameter, AutomationTestTask, \
    AutomationTestResult, ApiHead, ApiParameter, ApiResponse, ApiParameterRaw, AutomationParameterRaw, \
    AutomationResponseJson, AutomationTaskRunTime, AutomationCaseTestResult, AutomationReportSendConfig,\
    OnlineCode,AutomationJsonCheck,DataBaseInfo,CaseDataExcute



class TokenSerializer(serializers.ModelSerializer):
    """
    用户信息序列化
    """
    first_name = serializers.CharField(source="user.first_name", allow_null=True, default=None)
    last_name = serializers.CharField(source="user.last_name")
    phone = serializers.CharField(source="user.user.phone")
    email = serializers.CharField(source="user.email")
    date_joined = serializers.CharField(source="user.date_joined")

    class Meta:
        model = Token
        fields = ('first_name', 'last_name', 'phone', 'email', 'key', 'date_joined')


class UserSerializer(serializers.ModelSerializer):

    class Meta:
        model = User
        fields = ('id', 'username', 'first_name')


class UserRegisterSerializer(serializers.ModelSerializer):
    """
    用户注册序列化器
    """
    phone = serializers.CharField(max_length=11, required=False, allow_blank=True, write_only=True)
    password = serializers.CharField(min_length=6, max_length=128, write_only=True)

    class Meta:
        model = User
        fields = ('id', 'username', 'password', 'first_name', 'email', 'phone')

    def validate_username(self, value):
        """校验用户名唯一性"""
        if User.objects.filter(username=value).exists():
            raise serializers.ValidationError("用户名已存在")
        return value

    def validate_email(self, value):
        """校验邮箱唯一性（如果提供）"""
        if value and User.objects.filter(email=value).exists():
            raise serializers.ValidationError("邮箱已被注册")
        return value

    def create(self, validated_data):
        """创建用户及关联的 UserProfile"""
        phone = validated_data.pop('phone', None)
        password = validated_data.pop('password')
        user = User(**validated_data)
        user.set_password(password)
        user.save()
        # 创建或更新 UserProfile
        from api_test.models import UserProfile
        profile, _ = UserProfile.objects.get_or_create(user=user)
        if phone:
            profile.phone = phone
            profile.save()
        # 创建认证 Token
        Token.objects.get_or_create(user=user)
        return user


class ProjectDeserializer(serializers.ModelSerializer):
    """
    项目信息反序列化
    """
    class Meta:
        model = Project
        fields = ('id', 'name', 'version', 'type', 'status', 'LastUpdateTime', 'createTime', 'description', 'user')


class ProjectSerializer(serializers.ModelSerializer):
    """
    项目信息序列化
    """
    apiCount = serializers.SerializerMethodField()
    dynamicCount = serializers.SerializerMethodField()
    memberCount = serializers.SerializerMethodField()
    LastUpdateTime = serializers.DateTimeField(format="%Y-%m-%d %H:%M:%S", required=False, read_only=True)
    createTime = serializers.DateTimeField(format="%Y-%m-%d %H:%M:%S", required=False, read_only=True)
    user = serializers.CharField(source='user.first_name', allow_null=True, default=None)

    class Meta:
        model = Project
        fields = ('id', 'name', 'version', 'type', 'status', 'LastUpdateTime', 'createTime', 'apiCount',
                  'dynamicCount', 'memberCount', 'description', 'user')

    def get_apiCount(self, obj):
        return obj.api_project.all().count()

    def get_dynamicCount(self, obj):
        return obj.dynamic_project.all().count()

    def get_memberCount(self, obj):
        return obj.member_project.all().count()


class ProjectDynamicDeserializer(serializers.ModelSerializer):
    """
    项目动态信息反序列化
    """
    class Meta:
        model = ProjectDynamic
        fields = ('id', 'project', 'time', 'type', 'operationObject', 'user', 'description')


class ProjectDynamicSerializer(serializers.ModelSerializer):
    """
    项目动态信息序列化
    """
    operationUser = serializers.CharField(source='user.first_name', allow_null=True, default=None)
    time = serializers.DateTimeField(format="%Y-%m-%d %H:%M:%S", required=False, read_only=True)

    class Meta:
        model = ProjectDynamic
        fields = ('id', 'time', 'type', 'operationObject', 'operationUser', 'description')


class ProjectMemberDeserializer(serializers.ModelSerializer):
    """
    项目成员信息反序列化
    """
    class Meta:
        model = ProjectMember
        fields = ('id', 'permissionType', 'project', 'user')


class ProjectMemberSerializer(serializers.ModelSerializer):
    """
    项目成员信息序列化
    """
    id = serializers.IntegerField(source='user.id')
    username = serializers.CharField(source='user.first_name', allow_null=True, default=None)
    userPhone = serializers.CharField(source='user.user.phone')
    userEmail = serializers.CharField(source='user.email')

    class Meta:
        model = ProjectMember
        fields = ('id', 'permissionType', 'username', 'userPhone', 'userEmail')


class GlobalHostSerializer(serializers.ModelSerializer):
    """
    host信息序列化
    """

    class Meta:
        model = GlobalHost
        fields = ('id', 'project_id', 'name', 'host', 'status', 'description')


class ApiGroupLevelFirstSerializer(serializers.ModelSerializer):
    """
    接口一级分组信息序列化
    """
    class Meta:
        model = ApiGroupLevelFirst
        fields = ('id', 'project_id', 'name')


class ApiGroupLevelFirstDeserializer(serializers.ModelSerializer):
    """
    接口一级分组信息反序列化
    """
    class Meta:
        model = ApiGroupLevelFirst
        fields = ('id', 'project_id', 'name')


class ApiHeadSerializer(serializers.ModelSerializer):
    """
    接口请求头序列化
    """
    class Meta:
        model = ApiHead
        fields = ('id', 'api', 'name', 'value')


class ApiHeadDeserializer(serializers.ModelSerializer):
    """
    接口请求头反序列化
    """

    class Meta:
        model = ApiHead
        fields = ('id', 'api', 'name', 'value')


class ApiParameterSerializer(serializers.ModelSerializer):
    """
    接口请求参数序列化
    """

    class Meta:
        model = ApiParameter
        fields = ('id', 'api', 'name', 'value', '_type', 'required', 'restrict', 'description')


class ApiParameterDeserializer(serializers.ModelSerializer):
    """
    接口请求参数反序列化
    """

    class Meta:
        model = ApiParameter
        fields = ('id', 'api', 'name', 'value', '_type', 'required', 'restrict', 'description')


class ApiParameterRawSerializer(serializers.ModelSerializer):
    """
    接口请求参数源数据序列化
    """

    class Meta:
        model = ApiParameterRaw
        fields = ('id', 'api', 'data')


class ApiParameterRawDeserializer(serializers.ModelSerializer):
    """
    接口请求参数源数据序列化
    """

    class Meta:
        model = ApiParameterRaw
        fields = ('id', 'api', 'data')


class ApiResponseSerializer(serializers.ModelSerializer):
    """
    接口返回参数序列化
    """

    class Meta:
        model = ApiResponse
        fields = ('id', 'api', 'name', 'tier', 'value', '_type', 'required', 'description')


class ApiResponseDeserializer(serializers.ModelSerializer):
    """
    接口返回参数序列化
    """

    class Meta:
        model = ApiResponse
        fields = ('id', 'api', 'name', 'tier', 'value', '_type', 'required', 'description')


class ApiInfoSerializer(serializers.ModelSerializer):
    """
    接口详细信息序列化
    """
    lastUpdateTime = serializers.DateTimeField(format="%Y-%m-%d %H:%M:%S", required=False, read_only=True)
    headers = ApiHeadSerializer(many=True, read_only=True)
    requestParameter = ApiParameterSerializer(many=True, read_only=True)
    response = ApiResponseSerializer(many=True, read_only=True)
    requestParameterRaw = ApiParameterRawSerializer(many=False, read_only=True)
    userUpdate = serializers.CharField(source='userUpdate.first_name')

    class Meta:
        model = ApiInfo
        fields = ('id', 'apiGroupLevelFirst', 'name', 'httpType', 'requestType', 'apiAddress', 'headers',
                  'requestParameterType', 'requestParameter', 'requestParameterRaw', 'status',
                  'response', 'mockCode', 'data', 'lastUpdateTime', 'userUpdate', 'description')


class ApiInfoDeserializer(serializers.ModelSerializer):
    """
    接口详细信息序列化
    """
    class Meta:
        model = ApiInfo
        fields = ('id', 'project_id', 'name', 'httpType',
                  'requestType', 'apiAddress', 'requestParameterType', 'status',
                  'mockCode', 'data', 'lastUpdateTime', 'userUpdate', 'description')


class ApiInfoDocSerializer(serializers.ModelSerializer):
    """
    接口详细信息序列化
    """
    First = ApiInfoSerializer(many=True, read_only=True)

    class Meta:
        model = ApiGroupLevelFirst
        fields = ('id', 'name', 'First')


class ApiInfoListSerializer(serializers.ModelSerializer):
    """
    接口信息序列化
    """
    lastUpdateTime = serializers.DateTimeField(format="%Y-%m-%d %H:%M:%S", required=False, read_only=True)
    userUpdate = serializers.CharField(source='userUpdate.first_name')

    class Meta:
        model = ApiInfo
        fields = ('id', 'name', 'requestType', 'apiAddress', 'httpType',
                  'requestParameterType', 'mockStatus', 'lastUpdateTime', 'userUpdate')


class APIRequestHistorySerializer(serializers.ModelSerializer):
    """
    接口请求历史信息序列化
    """
    requestTime = serializers.DateTimeField(format="%Y-%m-%d %H:%M:%S", required=False, read_only=True)

    class Meta:
        model = APIRequestHistory
        fields = ('id', 'requestTime', 'requestType', 'requestAddress', 'httpCode')


class APIRequestHistoryDeserializer(serializers.ModelSerializer):
    """
    接口请求历史信息反序列化
    """
    class Meta:
        model = APIRequestHistory
        fields = ('id', 'api_id', 'requestTime', 'requestType', 'requestAddress', 'httpCode')


class ApiOperationHistorySerializer(serializers.ModelSerializer):
    """
    接口操作历史信息序列化
    """
    time = serializers.DateTimeField(format="%Y-%m-%d %H:%M:%S", required=False, read_only=True)
    user = serializers.CharField(source='user.first_name', allow_null=True, default=None)

    class Meta:
        model = ApiOperationHistory
        fields = ('id', 'user', 'time', 'description')


class ApiOperationHistoryDeserializer(serializers.ModelSerializer):
    """
    接口操作历史信息反序列化
    """

    class Meta:
        model = ApiOperationHistory
        fields = ('id', 'apiInfo', 'user', 'time', 'description')


class AutomationGroupLevelFirstSerializer(serializers.ModelSerializer):
    """
    自动化用例一级分组信息序列化
    """
    class Meta:
        model = AutomationGroupLevelFirst
        fields = ('id', 'project_id', 'name')


class AutomationTestCaseSerializer(serializers.ModelSerializer):
    """
    自动化用例信息序列化
    """
    updateTime = serializers.DateTimeField(format="%Y-%m-%d %H:%M:%S", required=False, read_only=True)
    createUser = serializers.CharField(source='user.first_name', allow_null=True, default=None)

    class Meta:
        model = AutomationTestCase
        fields = ('id', 'automationGroupLevelFirst', 'caseName', 'createUser',
                  'description', 'updateTime')


class AutomationTestCaseDeserializer(serializers.ModelSerializer):
    """
    自动化用例信息反序列化
    """
    class Meta:
        model = AutomationTestCase
        fields = ('id', 'project_id', 'automationGroupLevelFirst', 'caseName', 'user',
                  'description', 'updateTime')


class AutomationHeadSerializer(serializers.ModelSerializer):
    """
    自动化用例接口请求头信息序列化
    """
    class Meta:
        model = AutomationHead
        fields = ('id', 'automationCaseApi', 'name', 'value', 'interrelate')


class AutomationHeadDeserializer(serializers.ModelSerializer):
    """
    自动化用例接口请求头信息反序列化
    """
    class Meta:
        model = AutomationHead
        fields = ('id', 'automationCaseApi_id', 'name', 'value', 'interrelate')


class AutomationParameterSerializer(serializers.ModelSerializer):
    """
    自动化用例接口请求参数信息序列化
    """
    class Meta:
        model = AutomationParameter
        fields = ('id', 'automationCaseApi', 'name', 'value', 'interrelate')


class AutomationParameterDeserializer(serializers.ModelSerializer):
    """
    自动化用例接口请求参数信息反序列化
    """
    class Meta:
        model = AutomationParameter
        fields = ('id', 'automationCaseApi_id', 'name', 'value', 'interrelate')


class AutomationParameterRawSerializer(serializers.ModelSerializer):
    """
    接口请求参数源数据序列化
    """
    class Meta:
        model = AutomationParameterRaw
        fields = ('id', 'automationCaseApi', 'data')


class AutomationParameterRawDeserializer(serializers.ModelSerializer):
    """
    接口请求参数源数据反序列化
    """
    class Meta:
        model = AutomationParameterRaw
        fields = ('id', 'automationCaseApi_id', 'data')


class AutomationResponseJsonSerializer(serializers.ModelSerializer):
    """
    返回JSON参数序列化
    """

    class Meta:
        model = AutomationResponseJson
        fields = ('id', 'automationCaseApi', 'name', 'tier')



class AutomationJsonCkeckDeserializer(serializers.ModelSerializer):
    """
    返回JSON参数反序列化
    """

    class Meta:
        model = AutomationJsonCheck
        fields = ('id', 'name', 'value','checkType','checkRule','automationCaseApi')


class AutomationJsonCkeckserializer(serializers.ModelSerializer):
    """
    返回JSON参数序列化
    """

    class Meta:
        model = AutomationJsonCheck
        fields = ('id', 'name','value','checkType','checkRule')


class CorrelationDataSerializer(serializers.ModelSerializer):
    """
    关联数据序列化
    """
    jsonCheckDetail = AutomationJsonCkeckDeserializer(many=True,read_only=True)

    class Meta:
        model = AutomationCaseApi
        fields = ("id", "name", "jsonCheckDetail")



class CaseDataExcuteDeserializer(serializers.ModelSerializer):
    """
    校验数据库结果反序列化
    """
    class Meta:
        model = CaseDataExcute
        fields ="__all__"
class CaseDataExcuteSerializer(serializers.ModelSerializer):
    """
    校验数据库结果序列化
    """
    class Meta:
        model = CaseDataExcute
        fields =('name','excutesql','pre_excute','type')

class AutomationCaseApiSerializer(serializers.ModelSerializer):
    """
    自动化用例接口详细信息序列化
    """
    header = AutomationHeadSerializer(many=True, read_only=True)
    parameterList = AutomationParameterSerializer(many=True, read_only=True)
    parameterRaw = AutomationParameterRawSerializer(many=False, read_only=True)
    jsonCheckDetail = AutomationJsonCkeckDeserializer(many=True,read_only=True)
    CaseDataExcutedatail = CaseDataExcuteDeserializer(many=True,read_only=True)

    class Meta:
        model = AutomationCaseApi
        fields = ('id', 'name', 'httpType', 'requestType', 'apiAddress', 'header', 'requestParameterType', 'formatRaw',
                  'parameterList', 'parameterRaw', 'examineType', 'httpCode', 'responseData','jsonCheckDetail','CaseDataExcutedatail')


class AutomationCaseDownloadSerializer(serializers.ModelSerializer):
    """
    下载用例读取数据序列
    """
    # api = AutomationCaseApiSerializer(many=True, read_only=True)
    updateTime = serializers.DateTimeField(format="%Y-%m-%d %H:%M:%S", required=False, read_only=True)
    # automationGroupLevelFirst = serializers.CharField(source='automationGroupLevelFirst.name')
    user = serializers.CharField(source="user.first_name", allow_null=True, default=None)
    api = serializers.SerializerMethodField()

    class Meta:
        model = AutomationTestCase
        fields = ('caseName', 'user', 'updateTime', 'api')

    def get_api(self, obj):
        return AutomationCaseApiSerializer(
            AutomationCaseApi.objects.filter(automationTestCase=obj).order_by("id"),
            many=True
        ).data


class AutomationCaseDownSerializer(serializers.ModelSerializer):
    """
    下载用例读取数据序列
    """
    automationGroup = AutomationCaseDownloadSerializer(many=True, read_only=True)

    class Meta:
        model = AutomationGroupLevelFirst
        fields = ("name", "automationGroup")


class AutomationCaseApiDeserializer(serializers.ModelSerializer):
    """
    自动化用例接口详细信息反序列化
    """
    class Meta:
        model = AutomationCaseApi
        fields = ('id', 'automationTestCase_id', 'name', 'httpType', 'requestType', 'apiAddress', 'requestParameterType',
                  'formatRaw', 'examineType', 'httpCode', 'responseData')


class AutomationCaseApiListSerializer(serializers.ModelSerializer):
    """
    自动化用例接口列表信息序列化
    """
    class Meta:
        model = AutomationCaseApi
        fields = ('id', 'name', 'requestType', 'apiAddress')


class AutomationTestTaskSerializer(serializers.ModelSerializer):
    """
    定时任务信息序列化
    """
    startTime = serializers.DateTimeField(format="%Y-%m-%d %H:%M:%S", required=False, read_only=True)
    endTime = serializers.DateTimeField(format="%Y-%m-%d %H:%M:%S", required=False, read_only=True)

    class Meta:
        model = AutomationTestTask
        fields = ('id', 'project', 'Host', 'name', 'type', 'frequency', 'unit', 'startTime', 'endTime','caseId')


class AutomationTestTaskDeserializer(serializers.ModelSerializer):
    """
    定时任务信息反序列化
    """

    class Meta:
        model = AutomationTestTask
        fields = ( 'id','project_id', 'Host_id', 'name', 'type', 'frequency', 'unit', 'startTime', 'endTime','caseId')


class AutomationTestReportSerializer(serializers.ModelSerializer):
    """
    测试报告测试结果信息序列化
    """
    result = serializers.CharField(source='test_result.result')
    host = serializers.CharField(source='test_result.host')
    parameter = serializers.CharField(source='test_result.parameter')
    httpStatus = serializers.CharField(source='test_result.httpStatus')
    responseData = serializers.CharField(source='test_result.responseData')
    automationTestCase = serializers.CharField(source='automationTestCase.caseName')
    testTime = serializers.CharField(source='test_result.testTime')

    class Meta:
        model = AutomationCaseApi
        fields = ('id', 'automationTestCase', 'name', 'host', 'httpType', 'requestType', 'apiAddress', 'examineType',
                  'result', 'parameter', 'httpStatus', 'responseData', 'testTime')


class AutomationTaskRunTimeSerializer(serializers.ModelSerializer):
    """
    任务执行时间
    """
    startTime = serializers.DateTimeField(format="%Y-%m-%d %H:%M:%S", required=False, read_only=True)
    project = serializers.CharField(source='project.name')

    class Meta:
        model = AutomationTaskRunTime
        fields = ('id', 'project', 'startTime', 'elapsedTime', 'host','taskName','taskResult')


class AutomationTestResultSerializer(serializers.ModelSerializer):
    """
    手动测试结果详情序列化
    """
    testTime = serializers.DateTimeField(format="%Y-%m-%d %H:%M:%S", required=False, read_only=True)

    class Meta:
        model = AutomationTestResult
        fields = ('id', 'url', 'requestType', 'header', 'parameter', 'statusCode', 'examineType', 'data',
                  'result', 'httpStatus', 'responseData', 'testTime')


class AutomationAutoTestResultSerializer(serializers.ModelSerializer):
    """
    自动测试结果详情序列化
    """

    name = serializers.CharField(source='automationCaseApi.name')
    httpType = serializers.CharField(source='automationCaseApi.httpType')
    requestType = serializers.CharField(source='automationCaseApi.requestType')
    apiAddress = serializers.CharField(source='automationCaseApi.apiAddress')
    examineType = serializers.CharField(source='automationCaseApi.examineType')
    automationTestCase = serializers.CharField(source='automationCaseApi.automationTestCase')

    class Meta:
        model = AutomationCaseTestResult
        fields = ('id', 'automationTestCase', 'name', 'httpType', 'header', 'requestType', 'apiAddress', 'examineType',
                  'result', 'parameter', 'httpStatus', 'responseHeader', 'responseData', 'testTime')


class AutomationTestLatelyTenTimeSerializer(serializers.ModelSerializer):
    """
    最近10次测试结果
    """
    class Meta:
        model = AutomationTaskRunTime
        fields = ("id", "startTime","caseRunDetail")


class AutomationReportSendConfigSerializer(serializers.ModelSerializer):
    """
    发送人配置序列
    """
    project = serializers.CharField(source='project.name')

    class Meta:
        model = AutomationReportSendConfig
        fields = ("id", "project", 'reportFrom', 'mailUser', 'mailPass', 'mailSmtp')


class AutomationReportSendConfigDeserializer(serializers.ModelSerializer):
    """
    发送人配置反序列
    """

    class Meta:
        model = AutomationReportSendConfig
        fields = ("id", "project_id", 'reportFrom', 'mailUser', 'mailPass', 'mailSmtp')


class OnlineCodeSerializer(serializers.ModelSerializer):
    """
    全局变量代码配置
    """
    class Meta:
        model = OnlineCode
        fields =("id","project","Code","variablesName")


class OnlineCodeDeserializer(serializers.ModelSerializer):
    """
    全局变量代码配置
    """
    class Meta:
        model = OnlineCode
        fields =("id","project_id","Code","variablesName")

class DataBaseInfoDeserializer(serializers.ModelSerializer):
    """
    全局变量代码配置
    """
    class Meta:
        model = DataBaseInfo
        fields = ('id','name','password','host','user','port','db')


# ═══════════════════════════════════════════════════════════════════════
# 账号权限管理 — Serializers
# ═══════════════════════════════════════════════════════════════════════

class UserAccountSerializer(serializers.ModelSerializer):
    """用户详情序列化（含 UserProfile 和项目角色）"""
    phone = serializers.CharField(source='user.phone', default='')
    openId = serializers.CharField(source='user.openId', default='')
    unionid = serializers.CharField(source='user.unionid', default='')
    date_joined = serializers.DateTimeField(format="%Y-%m-%d %H:%M:%S", read_only=True)
    last_login = serializers.DateTimeField(format="%Y-%m-%d %H:%M:%S", read_only=True)
    roles = serializers.SerializerMethodField()

    class Meta:
        model = User
        fields = (
            'id', 'username', 'email', 'first_name', 'is_active', 'is_superuser',
            'phone', 'openId', 'unionid', 'date_joined', 'last_login', 'roles',
        )

    def get_roles(self, obj):
        memberships = ProjectMember.objects.filter(user=obj).select_related('project')
        return [
            {"project_id": m.project.id, "project_name": m.project.name, "role": m.permissionType}
            for m in memberships
        ]


class UserCreateSerializer(serializers.ModelSerializer):
    """管理员创建用户序列化器"""
    phone = serializers.CharField(max_length=11, required=False, allow_blank=True, write_only=True)
    password = serializers.CharField(min_length=6, max_length=128, write_only=True)

    class Meta:
        model = User
        fields = ('username', 'password', 'email', 'first_name', 'is_active', 'is_superuser', 'phone')

    def validate_username(self, value):
        if User.objects.filter(username=value).exists():
            raise serializers.ValidationError("用户名已存在")
        return value

    def validate_email(self, value):
        if value and User.objects.filter(email=value).exists():
            raise serializers.ValidationError("邮箱已被注册")
        return value

    def create(self, validated_data):
        phone = validated_data.pop('phone', None)
        password = validated_data.pop('password')
        user = User(**validated_data)
        user.set_password(password)
        user.save()
        from api_test.models import UserProfile
        profile, _ = UserProfile.objects.get_or_create(user=user)
        if phone:
            profile.phone = phone
            profile.save()
        Token.objects.get_or_create(user=user)
        return user


class UserUpdateSerializer(serializers.ModelSerializer):
    """管理员编辑用户信息序列化器（部分更新）"""
    phone = serializers.CharField(max_length=11, required=False, allow_blank=True)

    class Meta:
        model = User
        fields = ('username', 'email', 'first_name', 'is_active', 'is_superuser', 'phone')

    def validate_username(self, value):
        if hasattr(self, 'instance') and self.instance:
            if User.objects.filter(username=value).exclude(id=self.instance.id).exists():
                raise serializers.ValidationError("用户名已存在")
        return value


class UserPasswordResetSerializer(serializers.Serializer):
    """管理员重置用户密码序列化器"""
    new_password = serializers.CharField(min_length=6, max_length=128)


class ProjectMemberAddSerializer(serializers.ModelSerializer):
    """添加项目成员序列化器"""
    class Meta:
        model = ProjectMember
        fields = ('project', 'user', 'permissionType')


class ProjectMemberUpdateRoleSerializer(serializers.ModelSerializer):
    """修改成员角色序列化器"""
    class Meta:
        model = ProjectMember
        fields = ('permissionType',)