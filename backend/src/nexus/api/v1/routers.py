from __future__ import annotations

from fastapi import APIRouter

from nexus.api.v1 import (
    activity,
    analytics,
    auth,
    companies,
    contacts,
    custom_fields,
    duplicates,
    import_,
    lists,
    quality,
    saved_views,
    search,
    tags,
    users,
)
from nexus.api.v1 import settings as settings_router

api_router = APIRouter()
api_router.include_router(auth.router)
api_router.include_router(users.router)
api_router.include_router(companies.router)
api_router.include_router(contacts.router)
api_router.include_router(import_.router)
api_router.include_router(search.router)
api_router.include_router(lists.router)
api_router.include_router(tags.router)
api_router.include_router(duplicates.router)
api_router.include_router(quality.router)
api_router.include_router(analytics.router)
api_router.include_router(activity.router)
api_router.include_router(settings_router.router)
api_router.include_router(custom_fields.router)
api_router.include_router(saved_views.router)
