# -*- coding: utf-8 -*-

# @Time    : 2019/12/13 22:12

# @Author  : litao

# @Project : api_automation_test

# @FileName: Glb_config.py

# @Software: PyCharm



REDIS_CONFIG = {  # redis配置
    "host": '127.0.0.1',
    "port": 6379,
    "db": 15,  # 连接库
    "password": 'admin123',
    "max_connections": 20  # redis最大支持20个连接数
}

DATABASE = {
    'default': {
        'ENGINE': 'django.db.backends.mysql',
        'NAME': 'api',
        'USER': 'root',
        'PASSWORD': 'root1234',
        'HOST': '127.0.0.1',
        'PORT': '3306',
    }
}

