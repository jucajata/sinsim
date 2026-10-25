"""Aplicación FastAPI local (constitución II y V).

Sirve solo en 127.0.0.1, sin autenticación (NG-08). Todos los errores salen como Problem
Details con `trace_id`; los errores no previstos nunca exponen el stack trace.
"""

from __future__ import annotations

import logging
from collections.abc import Awaitable, Callable

from fastapi import FastAPI, Request, Response
from fastapi.exceptions import RequestValidationError
from fastapi.staticfiles import StaticFiles
from starlette.middleware.gzip import GZipMiddleware

from sinsim.api import problems
from sinsim.api.routers import cases, geo, n1, runs, sc, snapshots
from sinsim.api.security import host_allowed, origin_allowed
from sinsim.bootstrap import AppContext, build_context
from sinsim.config import sinsim_version
from sinsim.domain.errors import DomainError
from sinsim.observability import current_trace_id, log_event, new_trace_id

log = logging.getLogger("sinsim.api")


def create_app(ctx: AppContext | None = None) -> FastAPI:
    """Crea la aplicación con el contexto dado (o el del repositorio)."""
    app = FastAPI(
        title="sinsim API local",
        version=sinsim_version(),
        description="API REST local del flujo de potencia del SIN sobre despacho programado.",
    )
    app.state.ctx = ctx or build_context()

    @app.middleware("http")
    async def trace_middleware(
        request: Request, call_next: Callable[[Request], Awaitable[Response]]
    ) -> Response:
        trace_id = new_trace_id()
        # FR-047: solo peticiones dirigidas a 127.0.0.1/localhost y, en cambios, desde un origen
        # local. Ver api/security.py.
        blocked: DomainError | None = None
        if not host_allowed(request.headers.get("host")):
            blocked = DomainError("HOST_NOT_ALLOWED", f"host {request.headers.get('host')!r}")
        elif not origin_allowed(
            request.method, request.headers.get("origin"), request.headers.get("referer")
        ):
            origin = request.headers.get("origin") or request.headers.get("referer")
            blocked = DomainError("ORIGIN_NOT_ALLOWED", f"origen {origin!r}")
        response = (
            problems.from_domain_error(blocked, trace_id)
            if blocked is not None
            else await call_next(request)
        )
        response.headers["X-Trace-Id"] = trace_id
        log_event(
            log,
            "request",
            method=request.method,
            path=request.url.path,
            status=response.status_code,
        )
        return response

    @app.exception_handler(DomainError)
    async def domain_error_handler(_: Request, exc: DomainError) -> Response:
        return problems.from_domain_error(exc, current_trace_id())

    @app.exception_handler(RequestValidationError)
    async def validation_handler(_: Request, exc: RequestValidationError) -> Response:
        detail = "; ".join(
            f"{'.'.join(str(p) for p in e.get('loc', []))}: {e.get('msg', '')}"
            for e in exc.errors()
        )
        return problems.problem_response(
            code="REQUEST_INVALID",
            status=422,
            title="Petición inválida",
            detail=detail,
            user_message="La petición no cumple el esquema. Revisa los campos indicados.",
            trace_id=current_trace_id(),
        )

    @app.exception_handler(Exception)
    async def unexpected_handler(_: Request, exc: Exception) -> Response:
        log.exception("error no previsto", extra={"extra_fields": {"error": type(exc).__name__}})
        return problems.internal_error(current_trace_id())

    # Las topologías con flujos pesan ~0,5 MB; comprimidas quedan en ~70 KB (FR-036).
    app.add_middleware(GZipMiddleware, minimum_size=1024)
    app.include_router(snapshots.router, prefix="/api")
    app.include_router(cases.router, prefix="/api")
    app.include_router(runs.router, prefix="/api")
    app.include_router(geo.router, prefix="/api")
    app.include_router(n1.router, prefix="/api")
    app.include_router(sc.router, prefix="/api")
    # La interfaz construida, si existe, se sirve desde la raíz (FR-045). Se monta al final:
    # las rutas /api/… tienen prioridad.
    web = app.state.ctx.paths.web
    if web is not None:
        app.mount("/", StaticFiles(directory=web, html=True), name="web")
    return app


app = create_app()
