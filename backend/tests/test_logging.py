import logging
from datetime import datetime, timezone

from app.config.logging import BeijingFormatter


def test_beijing_formatter_renders_utc_timestamp_as_china_standard_time():
    formatter = BeijingFormatter(
        "[%(asctime)s] %(levelname)s: %(message)s",
        datefmt="%Y-%m-%d %H:%M:%S",
    )
    record = logging.LogRecord(
        name="test",
        level=logging.WARNING,
        pathname=__file__,
        lineno=1,
        msg="文件过大",
        args=(),
        exc_info=None,
    )
    record.created = datetime(2026, 7, 26, 9, 5, 31, tzinfo=timezone.utc).timestamp()

    assert formatter.format(record) == "[2026-07-26 17:05:31] WARNING: 文件过大"
