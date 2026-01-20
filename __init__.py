import asyncio

from fastapi import APIRouter
from lnbits.tasks import create_permanent_unique_task
from loguru import logger

from .crud import db
from .tasks import wait_for_paid_invoices
from .views import blackjack_generic_router
from .views_api import blackjack_api_router

blackjack_ext: APIRouter = APIRouter(prefix="/blackjack", tags=["BlackJack"])
blackjack_ext.include_router(blackjack_generic_router)
blackjack_ext.include_router(blackjack_api_router)


blackjack_static_files = [
    {
        "path": "/blackjack/static",
        "name": "blackjack_static",
    }
]

scheduled_tasks: list[asyncio.Task] = []


def blackjack_stop():
    for task in scheduled_tasks:
        try:
            task.cancel()
        except Exception as ex:
            logger.warning(ex)


def blackjack_start():
    task = create_permanent_unique_task("ext_blackjack", wait_for_paid_invoices)
    scheduled_tasks.append(task)


__all__ = [
    "blackjack_ext",
    "blackjack_start",
    "blackjack_static_files",
    "blackjack_stop",
    "db",
]
