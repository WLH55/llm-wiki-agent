"""Agent Pipeline 插件体系：骨架 re-export + 具体插件（Batch 3）。"""
from app.agent.plugins.base import ChatContext, EventManager, Plugin

__all__ = ["ChatContext", "EventManager", "Plugin"]
