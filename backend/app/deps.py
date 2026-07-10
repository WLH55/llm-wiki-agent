"""
依赖快捷 re-export

简化路由层 import：
    from app.deps import DbDep, CurrentUserDep
"""
from app.config.dependencies import (
    CurrentUserDep,
    DbDep,
    get_current_user,
    get_db,
)

__all__ = [
    "DbDep",
    "CurrentUserDep",
    "get_db",
    "get_current_user",
]
