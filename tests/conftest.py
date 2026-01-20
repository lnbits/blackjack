import asyncio
import inspect

import pytest
import pytest_asyncio
from lnbits.db import Database
from loguru import logger

from .. import migrations


@pytest.fixture(scope="session")
def event_loop():
    loop = asyncio.get_event_loop()
    yield loop
    loop.close()


@pytest_asyncio.fixture(scope="session", autouse=True)
async def migrate_db():
    db = Database("ext_blackjack")
    await db.execute("DROP TABLE IF EXISTS blackjack.extension_settings;")
    await db.execute("DROP TABLE IF EXISTS blackjack.dealers;")
    await db.execute("DROP TABLE IF EXISTS blackjack.hands_played;")
    # check if exists else skip migrations
    for key, migrate in inspect.getmembers(migrations, inspect.isfunction):
        logger.info(f"Running migration '{key}'.")
        await migrate(db)
    yield db
