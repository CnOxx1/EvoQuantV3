"""路由自动发现 — 扫描 api/routers/ 目录，自动注册所有 router 变量。

规则：
- 模块必须有名为 `router` 的 APIRouter 实例
- 带 _ 前缀的模块跳过
- feature_flags 中被禁用的模块跳过（FF_{MODULE}_ENABLED=0）
- 导入失败的模块记录警告并跳过（不影响其他路由）
"""

from __future__ import annotations

import importlib
import pkgutil
from pathlib import Path
from typing import List

from fastapi import APIRouter
from loguru import logger

from core.feature_flags import feature_flags


def discover_routers(package_path: str = "api.routers") -> List[APIRouter]:
    """自动扫描 api/routers/ 及 _legacy/ 下所有模块，收集导出的 router 变量。

    扫描顺序：
    1. api/routers/ 顶层（v3_* 活跃路由 + status.py）
    2. api/routers/_legacy/（旧路由，默认全部 FF 禁用）

    被 Feature Flag 禁用的模块跳过，不导入。
    """
    routers: List[APIRouter] = []
    disabled: List[str] = []
    package = importlib.import_module(package_path)
    package_dir = Path(package.__file__).parent

    # 扫描位置：顶层 + _legacy 子目录
    scan_paths = [
        (str(package_dir), package_path),
        (str(package_dir / "_legacy"), f"{package_path}._legacy"),
    ]

    for scan_dir, import_prefix in scan_paths:
        if not Path(scan_dir).is_dir():
            continue
        for module_info in pkgutil.iter_modules([scan_dir]):
            if module_info.name.startswith("_"):
                continue

            # Feature flag 检查：FF_{MODULE_NAME}_ENABLED=0 禁用路由
            if not feature_flags.is_enabled(module_info.name):
                disabled.append(module_info.name)
                continue

            try:
                module = importlib.import_module(f"{import_prefix}.{module_info.name}")
                router = getattr(module, "router", None)
                if isinstance(router, APIRouter):
                    routers.append(router)
                else:
                    logger.debug("跳过 {} — 无 router 变量", module_info.name)
            except Exception as exc:
                logger.warning("路由模块 {} 导入失败: {}", module_info.name, exc)

    if disabled:
        logger.info("自动发现 {} 个路由模块（{} 个被禁用）", len(routers), len(disabled))
    else:
        logger.info("自动发现 {} 个路由模块", len(routers))
    return routers
