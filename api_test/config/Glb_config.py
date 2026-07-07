# -*- coding: utf-8 -*-

# @Time    : 2019/12/13 22:12

# @Author  : litao

# @Project : api_automation_test

# @FileName: Glb_config.py

# @Software: PyCharm

APPID = 'dingoapfjxo0dzezwe47sy'

APPSECRET = '5_6b7h8eogyS1kstGWigpmuQbQUd585Vlc9ftjlcz48_avtLGQ5glolATWl3HFOf'

THEAD_COUNT = 10
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

FEISHUURL = 'https://open.feishu.cn/open-apis/bot/hook/1c38b0e8-5db8-49f8-a06e-3d3c3787c677'