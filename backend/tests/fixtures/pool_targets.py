"""解析子进程池测试的进程内目标函数。

必须是模块级函数：pebble 按引用 pickle，子进程（Windows 为 spawn 模式）
需要能通过模块路径重新 import，不能是闭包/lambda/测试函数内定义。
"""

import os
import time


def hang_forever(*args, **kwargs) -> str:
    """模拟挂死的解析器：睡 600 秒，只有杀进程能停下。

    接受任意参数，便于替换 parse_document(filename, raw_bytes, engine) 的位置。
    """
    time.sleep(600)
    return "should_never_return"


def die_instantly() -> str:
    """模拟崩溃的解析器：直接终止进程（OOM/段错误等价物）。"""
    os._exit(1)


def echo_ok(value: str) -> str:
    """正常路径探针。"""
    return value
