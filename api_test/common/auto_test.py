import datetime
import django
import sys,json
import os
import pytz
import logging
LOGGINGS = logging.getLogger(__name__)
from api_test.common.decorator import handle_db_connections ,close_old_connections
curPath = os.path.abspath(os.path.dirname(__file__))
rootPath = os.path.split(curPath)[0]
PathProject = os.path.split(rootPath)[0]
sys.path.append(rootPath)
sys.path.append(PathProject)
os.environ.setdefault("DJANGO_SETTINGS_MODULE", "api_automation_test.settings")
django.setup()

from api_test.common.auto_task_test import test_api
from api_test.models import AutomationCaseApi, AutomationTaskRunTime, GlobalHost, Project,AutomationTestTask


def automation_task(host_id, project_id, case_id, taskName):
    tz = pytz.timezone('Asia/Shanghai')
    start_time = datetime.datetime.now(tz)
    format_start_time = start_time.strftime('%Y-%m-%d %H:%M:%S')
    case = case_id
    host = GlobalHost.objects.get(id=host_id, project=project_id).host
    _pass = 0
    fail = 0
    error = 0
    time_out = 0
    for j in case:
        data = AutomationCaseApi.objects.filter(automationTestCase=j)
        for i in data:
            LOGGINGS.info(f'定时任务执行开始params:{host, j, i.pk}')
            try:
                result = test_api(host=host, case_id=j, _id=i.pk, time=format_start_time)
                LOGGINGS.info(f'执行结果返回：{result}')
                if result == 'success':
                    _pass = _pass + 1
                elif result == 'fail':
                    fail = fail + 1
                elif result == 'ERROR':
                    error = error + 1
                elif result == 'timeout':
                    time_out = time_out + 1
            except Exception as E:
                LOGGINGS.info(f'执行结果报错：{E}')
                error = error + 1
                continue

    total = _pass + fail + error + time_out
    result_data = "Hi, all:\n    测试时间： %s\n" \
                  "    总执行测试接口数： %s\n" \
                  "    成功： %s,  失败： %s, 执行错误： %s, 超时： %s\n" \
                  "    详情查看地址：http://127.0.0.1:8080/#/projectReport/project=%s" % (format_start_time, total,
                                                                                         _pass, fail, error, time_out
                                                                                         , project_id)
    taskResult = (lambda x, y: True if x == y else False)
    result_detail = "总执行测试接口数：%s  成功:%s, 失败:%s, 执行错误:%s, 超时:%s" % (
    total, _pass, fail, error, time_out)
    elapsed_time = (datetime.datetime.now(tz) - start_time).seconds
    try:
        AutomationTaskRunTime(project=Project.objects.get(id=project_id), startTime=format_start_time,
                              elapsedTime=elapsed_time, taskResult=taskResult(total, _pass),
                              caseRunDetail=result_detail, taskName=taskName, host=host).save()
    except Exception as E:
        LOGGINGS.info(E)
    close_old_connections()


def allTaskRecode():
    close_old_connections()
    obj = AutomationTestTask.objects.all().values()
    tz = pytz.timezone('Asia/Shanghai')
    start_time = datetime.datetime.now(tz)
    search_time = (datetime.datetime.now() - datetime.timedelta(hours=8)).strftime('%Y-%m-%d %H:%M:%S')
    format_start_time = start_time.strftime('%Y-%m-%d %H:%M:%S')
    taskRecs = []
    for i in obj:
        execuete = AutomationTaskRunTime.objects.filter(taskName=i['name'], startTime__gte=search_time).values(
            'taskResult', 'startTime', 'host', 'caseRunDetail')
        execuetes = []
        failTaskCount = 0
        if len(execuete):
            for j in execuete:
                if j['taskResult'] == False:  # 失败记录详情
                    execuetes.append(j)
                    failTaskCount = failTaskCount + 1
            taskRunDetail = {i['name']: {"allTaskRunCount": len(execuete),
                                         "failTaskRunCount": failTaskCount,
                                         "successTaskRunCount": len(execuete) - failTaskCount}}
            if len(execuetes) > 0:
                taskRunDetail['failTaskRunDetail'] = execuetes
            taskRecs.append(taskRunDetail)

    close_old_connections()
    taskrecodedata = f'执行时间：{format_start_time} \n' \
                     f'所有执行记录如下：{json.dumps(taskRecs, ensure_ascii=False)} '
    LOGGINGS.info(taskrecodedata)
