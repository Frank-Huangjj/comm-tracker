"""配置管理模块。"""

import os
from pathlib import Path
from typing import Any

import yaml
from dotenv import load_dotenv

# 加载 .env 文件中的环境变量
load_dotenv()


def get_project_root() -> Path:
    """获取项目根目录。"""
    return Path(__file__).parent.parent.parent


def load_config(filename: str) -> dict[str, Any]:
    """加载 YAML 配置文件。"""
    config_paths = [
        Path.cwd() / "config" / filename,
        get_project_root() / "config" / filename,
    ]
    for path in config_paths:
        if path.exists():
            with open(path, "r", encoding="utf-8") as f:
                return yaml.safe_load(f) or {}
    return {}


def load_manufacturers() -> list[dict[str, Any]]:
    """加载厂家配置。"""
    config = load_config("manufacturers.yaml")
    return config.get("manufacturers", [])


def load_sources() -> list[dict[str, Any]]:
    """加载数据源配置。"""
    config = load_config("sources.yaml")
    return config.get("sources", [])


def get_settings() -> dict[str, Any]:
    """加载全局设置。"""
    return load_config("settings.yaml")


def get_database_url() -> str:
    """获取数据库 URL。"""
    env_url = os.environ.get("DATABASE_URL")
    if env_url:
        return env_url
    settings = get_settings()
    return settings.get("database", {}).get("url", "sqlite:///data/db/comm_tracker.db")


def get_llm_config() -> dict[str, Any]:
    """获取 LLM 配置。"""
    settings = get_settings()
    llm = settings.get("llm", {})
    return {
        "api_key": os.environ.get("OPENAI_API_KEY", ""),
        "base_url": os.environ.get("OPENAI_BASE_URL", llm.get("base_url", "https://api.deepseek.com/v1")),
        "model": llm.get("model", "deepseek-chat"),
        "max_daily_tokens": llm.get("max_daily_tokens", 100000),
    }
