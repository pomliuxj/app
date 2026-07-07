import requests
import json
import logging
from api_test.config.Glb_config import FEISHUURL
LOGGINGS = logging.getLogger('loggers')


def sendFeishuMsg(title, text):
    """
        发送飞书消息
        :param title: 标题
        :param text: 发送内容
    """
    data = {"title": title, "text": text}
    header = {"Content-Type": "application/json"}
    url = FEISHUURL
    try:
        rqs = requests.post(url=url, data=json.dumps(data), headers=header)
        logging.info(f'调用飞书返回信息：{rqs.json()}')
        if rqs.json().setdefault('ok') == False:
            # 失败重试一次
            LOGGINGS.info(f'调用飞书返回失败信息：{rqs.json().setdefault("error")}')
            requests.post(url=url, data=json.dumps(data), headers=header)
    except ConnectionError as E:
        LOGGINGS.info(f'调用飞书失败信息：{E}')
        requests.post(url=url, data=json.dumps(data), headers=header)
