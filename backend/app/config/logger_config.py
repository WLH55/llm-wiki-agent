"""
日志配置模块
"""
import logging
import logging.handlers
from pathlib import Path
from app.config.settings import settings


def setup_logging():
    """
    配置日志系统

    特性：
    - 按日期轮转日志文件（每天午夜）
    - 自动压缩旧日志为 .gz 格式
    - 自动清理超过 LOG_RETENTION_DAYS 的日志
    """
    # 确保日志目录存在
    settings.LOGS_DIR.mkdir(parents=True, exist_ok=True)

    # 创建日志格式
    log_format = "[%(asctime)s] %(levelname)s: %(message)s"
    date_format = "%Y-%m-%d %H:%M:%S"

    # 创建 formatter
    formatter = logging.Formatter(log_format, datefmt=date_format)

    # 控制台处理器
    console_handler = logging.StreamHandler()
    console_handler.setFormatter(formatter)
    console_handler.setLevel(settings.LOG_LEVEL)

    # 文件处理器（按日期轮转）
    from logging.handlers import TimedRotatingFileHandler

    log_file = settings.LOGS_DIR / "app.log"

    file_handler = TimedRotatingFileHandler(
        filename=str(log_file),
        when="midnight",
        interval=1,
        backupCount=settings.LOG_RETENTION_DAYS,
        encoding="utf-8"
    )
    file_handler.setFormatter(formatter)
    file_handler.setLevel(settings.LOG_LEVEL)

    # 轮转时压缩旧日志
    def namer(default_name):
        """重命名轮转的日志文件，添加 .gz 压缩后缀"""
        return default_name + ".gz"

    file_handler.namer = namer
    file_handler.rotator = _rotator

    # 配置根 logger
    root_logger = logging.getLogger()
    root_logger.setLevel(settings.LOG_LEVEL)
    root_logger.addHandler(console_handler)
    root_logger.addHandler(file_handler)


def _rotator(source, dest):
    """日志轮转时的压缩函数"""
    import gzip
    import shutil

    with open(source, "rb") as f_in:
        with gzip.open(dest, "wb") as f_out:
            shutil.copyfileobj(f_in, f_out)

    Path(source).unlink()
    _cleanup_old_logs()


def _cleanup_old_logs():
    """清理超过保留天数的日志文件"""
    import time

    current_time = time.time()
    cutoff_time = current_time - (settings.LOG_RETENTION_DAYS * 86400)

    for log_file in settings.LOGS_DIR.glob("*.log*"):
        try:
            if log_file.stat().st_mtime < cutoff_time:
                log_file.unlink()
        except (FileNotFoundError, Exception):
            pass
