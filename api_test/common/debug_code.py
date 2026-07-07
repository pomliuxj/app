import io
import json
import shutil
import sys
import os
from django.conf import settings
import redis
import subprocess
import tempfile
import logging
logger = logging.getLogger(__name__)


EXEC = sys.executable

if 'uwsgi' in EXEC:
    EXEC = "/opt/python3/bin/python3.6"


class RunOnlineCode(object):

    def __init__(self, code, name):
        self.__code = code
        self.name = name
        self.resp = None
        self.temp = tempfile.mkdtemp(prefix='api_automation_test')

    @staticmethod
    def decode(s):
        try:
            return s.decode('utf-8')
        except UnicodeDecodeError:
            return s.decode('gbk')

    def run(self):
        """ dumps debug_code.py and run
        """
        Pool= settings.REDIS_CONF
        rds = redis.Redis(connection_pool=Pool)
        if rds.get(self.name):
            self.resp = rds.get(self.name)
            return self.decode(self.resp)
        else:
            try:
                file_path = os.path.join(self.temp, "debug_code.py")
                FileLoader.dump_python_file(file_path, self.__code)
                self.resp = self.decode(subprocess.check_output([EXEC, file_path], stderr=subprocess.STDOUT, timeout=60))
                rds.set(self.name, self.resp, ex=5)
                logger.info(f'代码执行结果：{self.resp}')

            except subprocess.CalledProcessError as e:
                self.resp = self.decode(e.output)

            except subprocess.TimeoutExpired:
                self.resp = 'RunnerTimeOut'
            shutil.rmtree(self.temp)
            return self.resp


class FileLoader(object):



    @staticmethod
    def dump_json_file(json_file, data):
        """ dump json file
        """
        with io.open(json_file, 'w', encoding='utf-8') as stream:
            json.dump(data, stream, indent=4, separators=(',', ': '), ensure_ascii=False)

    @staticmethod
    def dump_python_file(python_file, data):
        """dump python file
        """
        with io.open(python_file, 'w', encoding='utf-8') as stream:
            stream.write(data)

    @staticmethod
    def dump_binary_file(binary_file, data):
        """dump file
        """
        with io.open(binary_file, 'wb') as stream:
            stream.write(data)

