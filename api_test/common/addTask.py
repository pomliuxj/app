from api_test.common.auto_test import automation_task,allTaskRecode
import logging
LOGGINGS =logging.getLogger('logging')
import time
from django.conf import settings
from pytz import timezone
logging.basicConfig()
logging.getLogger('apscheduler').setLevel(logging.INFO)
from apscheduler.schedulers.background import BackgroundScheduler
from apscheduler.executors.pool import ThreadPoolExecutor
executors = {
 'default': ThreadPoolExecutor(20),
}
scheduler = BackgroundScheduler(executors=executors,timezone=timezone("Asia/Shanghai"))
# scheduler = BackgroundScheduler(executors=executors)
scheduler.add_jobstore(jobstore='redis', **settings.REDIS_CONFIG)
scheduler.start()





def creatTask(host_id, _type, start_time, case_id,end_time, project,taskName ,frequency=None, unit=None):
    """
        :param host_id:  测试域名
        :param _type:  执行类型
        :param start_time:  执行时间
        :param end_time:  结束时间
        :param frequency:  时间间隔
        :param unit:  时间单位
        :param project:  项目ID
        :param case_id:  用例集合
        :return:
        """
    time_array = time.strptime(start_time, "%Y-%m-%d %H:%M:%S")
    job_id=taskName+str(time.mktime(time_array)).split('.')[0]
    LOGGINGS.info(f'job_id:{job_id}')
    if _type=='timing':
        scheduler.add_job(automation_task,'date',run_date=start_time,args=[host_id,project,case_id,taskName],id=job_id,)
    else:
        if unit=='m':
            try:
                scheduler.add_job(automation_task,'interval',minutes=frequency,start_date=start_time,
                                  end_date=end_time,args=[host_id,project,case_id,taskName],id=job_id)
            except Exception as E:
                LOGGINGS.info(E)
        elif unit=='h':
            try:
                scheduler.add_job(automation_task,'interval',hours=frequency,start_date=start_time,
                                  end_date=end_time,args=[host_id,project,case_id,taskName],id=job_id)
            except Exception as E:
                LOGGINGS.info(E)
        elif unit=='d':
            try:
                scheduler.add_job(automation_task,'interval',days=frequency,start_date=start_time,
                                  end_date=end_time,args=[host_id,project,case_id,taskName],id=job_id)
            except Exception as E:
                LOGGINGS.info(E)
        elif unit=='w':
            try:
                scheduler.add_job(automation_task,'interval',weeks=frequency,start_date=start_time,
                                  end_date=end_time,args=[host_id,project,case_id,taskName],id=job_id)
            except Exception as E:
                LOGGINGS.info(E)

def delTask(start_time,taskName):
    time_array = time.strptime(start_time, "%Y-%m-%d %H:%M:%S")
    job_id = taskName + str(time.mktime(time_array)).split('.')[0]
    try:
        scheduler.remove_job(job_id=job_id)
        return ('任务删除成功')
    except Exception as E:
        LOGGINGS.info(f'删除定时任务报错：{E}')
        return ('定时任务已停止或不存在!')

def updateTask(host_id, _type, start_time, case_id, project,taskName ,end_time,frequency=None, unit=None):
    time_array = time.strptime(str(start_time), "%Y-%m-%d %H:%M:%S")
    job_id = taskName + str(time.mktime(time_array)).split('.')[0]
    try:
        if _type == 'timing':
            scheduler.add_job(automation_task, 'date', run_date=start_time, args=[host_id, project, case_id, taskName],
                              id=job_id)
        else:
            if unit == 'm':
                scheduler.add_job(automation_task, 'interval', minutes=frequency, start_date=start_time,
                                  end_date=end_time, args=[host_id, project, case_id, taskName], id=job_id)
            elif unit == 'h':
                scheduler.add_job(automation_task, 'interval', hours=frequency, start_date=start_time,
                                  end_date=end_time, args=[host_id, project, case_id, taskName], id=job_id)
            elif unit == 'd':
                scheduler.add_job(automation_task, 'interval', days=frequency, start_date=start_time,
                                  end_date=end_time, args=[host_id, project, case_id, taskName], id=job_id)
            elif unit == 'w':
                scheduler.add_job(automation_task, 'interval', weeks=frequency, start_date=start_time,
                                  end_date=end_time, args=[host_id, project, case_id, taskName], id=job_id)
            else:
                return {'msg': '修改失败，类型不对!', 'result': True}

        return {'msg':'修改成功!','result':True}
    except Exception as E:
        LOGGINGS.info(f'修改定时任务报错：{E}')
        return {'msg':'定时任务已停止或不存在!','result':False}




def createTaskRecode():
    try:
        logging.info('开始创建定时任务记录')
        scheduler.add_job(allTaskRecode,'interval',hours=8,id='allTaskRecode')
        logging.info('完成创建定时任务记录')
    except Exception as E:
        LOGGINGS.info(E)



