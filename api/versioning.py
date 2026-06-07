from __future__ import annotations

from fastapi import APIRouter, Response

CURRENT_API_VERSION = "v1"
SUPPORTED_VERSIONS = ["v1"]


class VersionedRouter:
    def __init__(self, version: str = CURRENT_API_VERSION, **kwargs):
        self.version = version
        self.prefix = f"/{version}"
        self.router = APIRouter(prefix=self.prefix, **kwargs)

    def include_router(self, router: APIRouter, **kwargs) -> None:
        prefix = kwargs.pop("prefix", "")
        self.router.include_router(router, prefix=prefix, **kwargs)


def create_versioned_app(app, routers: list[APIRouter], version: str) -> None:
    prefix = f"/{version}"
    for router in routers:
        app.include_router(router, prefix=prefix)


def add_deprecation_headers(response: Response, sunset_date: str) -> None:
    response.headers["Deprecation"] = "true"
    response.headers["Sunset"] = sunset_date
