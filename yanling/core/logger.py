"""结构化日志 — 统一日志输出."""

from __future__ import annotations

import logging
import sys
from pathlib import Path

LOG_FORMAT = "[%(asctime)s] [%(levelname)s] [%(name)s] %(message)s"
DATE_FORMAT = "%Y-%m-%d %H:%M:%S"


def setup_logger(
    name: str = "yanling",
    level: str = "INFO",
    log_file: str | Path | None = None,
) -> logging.Logger:
    """配置并返回日志器。

    Args:
        name: 日志器名称
        level: 日志级别 (DEBUG/INFO/WARNING/ERROR)
        log_file: 可选日志文件路径
    """
    logger = logging.getLogger(name)
    logger.setLevel(getattr(logging, level.upper(), logging.INFO))

    # 避免重复添加 handler
    if logger.handlers:
        return logger

    fmt = logging.Formatter(LOG_FORMAT, datefmt=DATE_FORMAT)

    # 控制台输出
    ch = logging.StreamHandler(sys.stdout)
    ch.setFormatter(fmt)
    logger.addHandler(ch)

    # 文件输出
    if log_file:
        p = Path(log_file)
        p.parent.mkdir(parents=True, exist_ok=True)
        fh = logging.FileHandler(str(p), encoding="utf-8")
        fh.setFormatter(fmt)
        logger.addHandler(fh)

    return logger


def get_logger(name: str = "yanling") -> logging.Logger:
    """获取已配置的日志器。"""
    return logging.getLogger(name)
