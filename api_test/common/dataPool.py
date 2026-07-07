import importlib
import pymysql
from dbutils.pooled_db import PooledDB
from api_test.models import DataBaseInfo,CaseDataExcute
import logging
logger= logging.getLogger(__name__)


class DataExcuteBase(object):

    def __init__(self, db_type, config):

        self.__db_type = db_type

        if self.__db_type == 'mysql':
            db_creator = importlib.import_module('pymysql')
        elif self.__db_type == 'oracle':
            db_creator = importlib.import_module('cx_Oracle')
        else:
            raise Exception('unsupported database type ' + self.__db_type)
        self.pool = PooledDB(
            creator=db_creator,
            mincached=0,
            maxcached=6,
            maxconnections=0,
            blocking=True,
            cursorclass=pymysql.cursors.DictCursor,
            charset='utf8',
            **config
        )
    def check_database(self):
        """
        检查数据库是否可用
        """
        result = self.pool.steady_connection()._ping_check()
        return result

    def execute_query(self, sql):
        """
        查询语句
        :param sql:
        :param as_dict:
        :return:
        """
        conn = None
        cur = None
        try:
            conn = self.pool.connection()
            cur = conn.cursor()
            cur.execute(sql)
            rst = cur.fetchall()
            # if rst:
            #     if as_dict:
            #         fields = [tup[0] for tup in cur._cursor.description]
            #         return [dict(zip(fields, row)) for row in rst]
            #     return rst
            return rst

        except Exception as e:
            logger.error('execute_query_sql:[{}]meet error'.format(sql))
            logger.error('execute_query_error:{}'.format(e.args[-1]))
            return e.args[-1]
        finally:
            if conn:
                conn.close()
            if cur:
                cur.close()

    def execute_manay(self, sql, data):
        """
        执行多条语句
        :param sql:
        :param data:
        :return:
        """
        conn = None
        cur = None
        try:
            conn = self.pool.connection()
            cur = conn.cursor()
            cur.executemany(sql, data)
            conn.commit()
            return True
        except Exception as e:
            logger.error('[{}]meet error'.format(sql))
            return e.args[-1]
            conn.rollback()
            return False
        finally:
            if conn:
                conn.close()
            if cur:
                cur.close()
    def insert(self,sql):
        """
        执行insert语句
        :param sql:
        :return:True,False
        """
        conn = None
        cur = None
        try:
            conn = self.pool.connection()
            cur = conn.cursor()
            res=cur.execute(sql)
            conn.commit()
            return res
        except Exception as e:
            logger.error('[{}]meet error'.format(sql))
            return e.args[-1]
            conn.rollback()
            return False
        finally:
            if conn:
                conn.close()
            if cur:
                cur.close()


def query_private_keys(id):
    """
    查询数据库返回数据
    :param id:用例id
    :return:dict or None
    """
    queryobject = CaseDataExcute.objects.filter(AutomationCaseApi_id=id).values()
    queryResult = {}
    if len(queryobject):
        for i in queryobject:
            config = DataBaseInfo.objects.filter(id=i.get('dataInfo_id')
                                                 ).values('user', 'password', 'host', 'port', 'db')[0]
            db_type = i.get('type')
            sql = i.get('excutesql')
            resp = DataExcuteBase(config=config, db_type=db_type).execute_query(sql)[0]
            if isinstance(resp, dict):
                queryResult = {**queryResult, **resp}
            else:
                logger.error(f'执行sql异常：{resp}')
        logger.info(f'合并的json数据：{queryResult}')
        return queryResult
    else:
        return None