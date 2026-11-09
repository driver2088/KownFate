# -*- coding: utf-8 -*-
"""Anthropic 客户端工厂：答疑对话与命格复核共用。"""
import anthropic

from . import config

_client = None


def ai_ready() -> bool:
    return bool(config.ANTHROPIC_API_KEY)


def get_client():
    """未配置密钥时返回 None（调用方自行降级或提示）。"""
    global _client
    if _client is None and config.ANTHROPIC_API_KEY:
        kwargs = {"api_key": config.ANTHROPIC_API_KEY, "timeout": 60.0}
        if config.ANTHROPIC_BASE_URL:
            kwargs["base_url"] = config.ANTHROPIC_BASE_URL
        _client = anthropic.Anthropic(**kwargs)
    return _client


def http_status_for(e):
    """把 anthropic 异常映射为 (HTTP状态码, 中文提示)。"""
    if isinstance(e, anthropic.APIStatusError):
        status = getattr(e, "status_code", 0)
        if status == 429:
            return 429, "AI 先生正被众多缘主问询，请稍后再试"
        if status == 401:
            return 502, "ANTHROPIC_API_KEY 无效，请检查 .env 配置"
        return 502, f"AI 服务暂时不可用（{status}），缘主稍后再试"
    if isinstance(e, anthropic.APIConnectionError):
        return 502, "无法连接 AI 服务，请检查网络后重试"
    return 502, "AI 服务异常，请稍后再试"
