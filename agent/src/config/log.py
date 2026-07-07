import os
import pytz
import socket
from datetime import datetime
import logging.handlers
from logging import Formatter

#按照日志平台的路径与格式
logging.captureWarnings(True)  # 将 warnings 重定向到 logging 系统
app_id = os.getenv('APP_ID', 'agentflow')
hostname = socket.gethostname()
path = os.path.join("/data/logs", app_id, hostname)
os.makedirs(path, exist_ok=True)
log_path = os.path.join(path, "applog.log")
beijing_tz = pytz.timezone('Asia/Shanghai')


class BeijingFormatter(Formatter):
    def formatTime(self, record, datefmt=None):
        dt = datetime.fromtimestamp(record.created, tz=beijing_tz)
        if datefmt:
            return dt.strftime(datefmt)
        else:
            return dt.strftime("%Y-%m-%d %H:%M:%S.%f")[:-3]

# 强制规定，日志行格式必须为该格式
log_format = "[%(asctime)s] [%(levelname)s] [%(process)d] [] [] [] %(module)s:%(name)s:%(lineno)d %(message)s"

LOGGING_CONFIG = {
    "version": 1,
    "disable_existing_loggers": False,
    "formatters": {
        "beijing_formatter": {
            "()": BeijingFormatter,
            "format": log_format,
        },
    },
    "handlers": {
        "console": {
            "class": "logging.StreamHandler",
            "formatter": "beijing_formatter",
            "stream": "ext://sys.stdout",
        },
        "file": {
            "class": "logging.handlers.RotatingFileHandler",
            "formatter": "beijing_formatter",
            "filename": log_path,
            "maxBytes": 500 * 1024 * 1024,  # 500 MB
            "backupCount": 10,
            "encoding": "utf-8",
        },
    },
    "root": {
        "level": "INFO",
        "handlers": ["console", "file"],
    },
    "loggers": {
        "uvicorn": {
            "level": "INFO",
            "handlers": ["console", "file"],
            "propagate": False
        },
        "uvicorn.error": {
            "level": "INFO",
            "handlers": ["console", "file"],
            "propagate": False
        },
        "uvicorn.access": {
            "level": "INFO",
            "handlers": ["console", "file"],
            "propagate": False
        },
        "py.warnings": {  # 添加对 warnings 的处理
            "level": "WARNING",
            "handlers": ["console", "file"],
            "propagate": False
        },
    },
}
