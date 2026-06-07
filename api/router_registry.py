"""路由自动发现 — 扫描 api/routers/ 目录，自动注册所有 router 变量。

规则：
- 模块必须有名为 `router` 的 APIRouter 实例
- 带 _ 前缀的模块跳过
- 导入失败的模块记录警告并跳过（不影响其他路由）
"""

from __future__ import annotations

import importlib
import pkgutil
from pathlib import Path
from typing import List

from fastapi import APIRouter
from loguru import logger


def discover_routers(package_path: str = "api.routers") -> List[APIRouter]:
    """自动扫描 api/routers/ 下所有模块，收集导出的 router 变量。"""
    routers: List[APIRouter] = []
    package = importlib.import_module(package_path)
    package_dir = Path(package.__file__).parent

    for module_info in pkgutil.iter_modules([str(package_dir)]):
        if module_info.name.startswith("_"):
            continue
        try:
            module = importlib.import_module(f"{package_path}.{module_info.name}")
            router = getattr(module, "router", None)
            if isinstance(router, APIRouter):
                routers.append(router)
            else:
                logger.debug("跳过 {} — 无 router 变量", module_info.name)
        except Exception as exc:
            logger.warning("路由模块 {} 导入失败: {}", module_info.name, exc)

    logger.info("自动发现 {} 个路由模块", len(routers))
    return routers
