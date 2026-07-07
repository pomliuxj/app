def success():
    return {"code":"999999", "msg":"成功"}


def fail():
    return {"code":"999998","msg":"失败"}


def name_repetition():
    return {"code":"999997", "msg":"存在相同名称"}


def parameter_wrong():
    return {"code":"999996","msg":"参数有误"}


def project_not_exist():
    return {"code":"999995","msg":"项目不存在"}


def project_is_exist():
    return {"code":"999994", "msg":"项目已存在"}


def host_is_exist():
    return {"code":"999993","msg":"host已存在"}


def host_not_exist():
    return {"code":"999992","msg":"host不存在"}


def group_not_exist():
    return {"code":"999991","msg":"分组不存在"}


def api_not_exist():
    return {"code":"999990","msg":"接口不存在"}


def api_is_exist():
    return {"code":"999989","msg":"接口已存在"}


def history_not_exist():
    return {"code":"999988","msg":"请求历史不存在"}


def case_not_exist():
    return {"code":"999987", "msg":"用例不存在"}


def task_not_exist():
    return {"code":"999986", "msg":"任务不存在"}


def page_not_int():
    return {"code":"999985", "msg":"page and page_size must be integer!"}


def mock_error():
    return {"code":"999984", "msg":"未匹配到mock地址或未开启!"}
