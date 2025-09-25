from fastapi.routing import APIRouter

from auth_microservice.web.api import auth, docs, echo, monitoring, rabbit, rbac, redis, settings
from auth_microservice.web.api.v1.auth import views as v1_auth_views
from auth_microservice.web.api.v1.bootstrap import views as v1_bootstrap_views
from auth_microservice.web.api.v1.billing import views as v1_billing_views
from auth_microservice.web.api.v1.feedback import views as v1_feedback_views
from auth_microservice.web.api.v1.orgs import views as v1_orgs_views
from auth_microservice.web.api.v1.rbac import views as v1_rbac_views
from auth_microservice.web.api.v1.search import views as v1_search_views
from auth_microservice.web.api.v1.support import views as v1_support_views
from auth_microservice.web.api.v1.users import views as v1_users_views

api_router = APIRouter()
api_router.include_router(monitoring.router)
api_router.include_router(auth.views.router)
api_router.include_router(v1_auth_views.router)
api_router.include_router(v1_bootstrap_views.router)
api_router.include_router(v1_billing_views.plans_router)
api_router.include_router(v1_support_views.support_router)
api_router.include_router(v1_orgs_views.router)
api_router.include_router(v1_rbac_views.router)
api_router.include_router(v1_users_views.router)
api_router.include_router(v1_billing_views.org_router)
api_router.include_router(v1_feedback_views.feedback_router)
api_router.include_router(v1_search_views.search_router)
api_router.include_router(rbac.views.router)
api_router.include_router(settings.views.router)
api_router.include_router(docs.router)
api_router.include_router(echo.router, prefix="/echo", tags=["echo"])
api_router.include_router(redis.router, prefix="/redis", tags=["redis"])
api_router.include_router(rabbit.router, prefix="/rabbit", tags=["rabbit"])
