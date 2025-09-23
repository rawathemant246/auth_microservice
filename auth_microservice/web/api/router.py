from fastapi.routing import APIRouter

from auth_microservice.web.api import auth, docs, echo, monitoring, rabbit, rbac, redis, settings

api_router = APIRouter()
api_router.include_router(monitoring.router)
api_router.include_router(auth.views.router)
api_router.include_router(rbac.views.router)
api_router.include_router(settings.views.router)
api_router.include_router(docs.router)
api_router.include_router(echo.router, prefix="/echo", tags=["echo"])
api_router.include_router(redis.router, prefix="/redis", tags=["redis"])
api_router.include_router(rabbit.router, prefix="/rabbit", tags=["rabbit"])
