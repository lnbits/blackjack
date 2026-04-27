# Description: This file contains the CRUD operations for talking to the database.

from datetime import datetime, timezone

from lnbits.db import Database, Filters, Page
from lnbits.helpers import urlsafe_short_hash

from .models import (
    CreateDealers,
    CreateHandsPlayed,
    Dealers,
    DealersFilters,
    ExtensionSettings,
    HandsPlayed,
    HandsPlayedFilters,
)

db = Database("ext_blackjack")


########################### Dealers ############################
async def create_dealers(data: CreateDealers) -> Dealers:
    dealer_id = urlsafe_short_hash()
    dealers = Dealers(
        id=dealer_id,
        **data.dict(),
    )
    await db.insert("blackjack.dealers", dealers)
    return dealers


async def get_dealers(
    wallet_id: str,
    dealers_id: str,
) -> Dealers | None:
    return await db.fetchone(
        """
            SELECT * FROM blackjack.dealers
            WHERE id = :id AND wallet_id = :wallet_id
        """,
        {"id": dealers_id, "wallet_id": wallet_id},
        Dealers,
    )


async def get_dealers_by_id(
    dealers_id: str,
) -> Dealers | None:
    return await db.fetchone(
        """
            SELECT * FROM blackjack.dealers
            WHERE id = :id
        """,
        {"id": dealers_id},
        Dealers,
    )


async def get_active_dealers_by_id(
    dealers_id: str,
) -> Dealers | None:
    return await db.fetchone(
        """
            SELECT * FROM blackjack.dealers
            WHERE id = :id AND active = true
        """,
        {"id": dealers_id},
        Dealers,
    )


async def get_dealers_ids_by_wallet(
    wallet_id: str,
) -> list[str]:
    rows: list[dict] = await db.fetchall(
        """
            SELECT DISTINCT id FROM blackjack.dealers
            WHERE wallet_id = :wallet_id
        """,
        {"wallet_id": wallet_id},
    )

    return [row["id"] for row in rows]


async def get_dealers_paginated(
    wallet_ids: list[str] | None = None,
    filters: Filters[DealersFilters] | None = None,
    active_only: bool = False,
) -> Page[Dealers]:
    where = []
    values = {}
    if active_only:
        where.append("active = true")

    if wallet_ids:
        id_clause = []
        for i, wallet_id in enumerate(wallet_ids):
            # wallet_ids are not user input, so this is safe
            wallet = f"wallet_id__{i}"
            id_clause.append(f"wallet_id = :{wallet}")
            values[wallet] = wallet_id
        or_clause = " OR ".join(id_clause)
        where.append(f"({or_clause})")

    return await db.fetch_page(
        "SELECT * FROM blackjack.dealers",
        where=where,
        values=values,
        filters=filters,
        model=Dealers,
    )


async def update_dealers(data: Dealers) -> Dealers:
    data.updated_at = datetime.now(timezone.utc)
    await db.update("blackjack.dealers", data)
    return data


async def delete_dealers(wallet_id: str, dealers_id: str) -> None:
    await db.execute(
        """
            DELETE FROM blackjack.dealers
            WHERE id = :id AND wallet_id = :wallet_id
        """,
        {"id": dealers_id, "wallet_id": wallet_id},
    )


################################# Hands Played ###########################


async def create_hands_played(data: CreateHandsPlayed) -> HandsPlayed:
    hands_played = HandsPlayed(**data.dict(), id=urlsafe_short_hash())
    await db.insert("blackjack.hands_played", hands_played)
    return hands_played


async def get_hands_played(
    dealers_id: str,
    hands_played_id: str,
) -> HandsPlayed | None:
    return await db.fetchone(
        """
            SELECT * FROM blackjack.hands_played
            WHERE id = :id AND dealers_id = :dealers_id
        """,
        {"id": hands_played_id, "dealers_id": dealers_id},
        HandsPlayed,
    )


async def get_hands_played_by_id(
    hands_played_id: str,
) -> HandsPlayed | None:
    return await db.fetchone(
        """
            SELECT * FROM blackjack.hands_played
            WHERE id = :id
        """,
        {"id": hands_played_id},
        HandsPlayed,
    )


async def get_hands_played_paginated(
    dealers_ids: list[str] | None = None,
    filters: Filters[HandsPlayedFilters] | None = None,
) -> Page[HandsPlayed]:
    if not dealers_ids:
        return Page(data=[], total=0)

    where = []
    values = {}
    id_clause = []
    for i, item_id in enumerate(dealers_ids):
        # dealers_ids are not user input, but DB entries, so this is safe
        dealers_id = f"dealers_id__{i}"
        id_clause.append(f"dealers_id = :{dealers_id}")
        values[dealers_id] = item_id
    or_clause = " OR ".join(id_clause)
    where.append(f"({or_clause})")

    return await db.fetch_page(
        "SELECT * FROM blackjack.hands_played",
        where=where,
        values=values,
        filters=filters,
        model=HandsPlayed,
    )


async def update_hands_played(data: HandsPlayed) -> HandsPlayed:
    data.updated_at = datetime.now(timezone.utc)
    await db.update("blackjack.hands_played", data)
    return data


async def claim_hands_played_payout(hands_played_id: str) -> bool:
    result = await db.execute(
        """
            UPDATE blackjack.hands_played
            SET payout_sent = true
            WHERE id = :id AND payout_sent = false
        """,
        {"id": hands_played_id},
    )
    return result.rowcount == 1


async def reset_hands_played_payout_claim(hands_played_id: str) -> None:
    await db.execute(
        """
            UPDATE blackjack.hands_played
            SET payout_sent = false
            WHERE id = :id
        """,
        {"id": hands_played_id},
    )


async def delete_hands_played(dealers_id: str, hands_played_id: str) -> None:
    await db.execute(
        """
            DELETE FROM blackjack.hands_played
            WHERE id = :id AND dealers_id = :dealers_id
        """,
        {"id": hands_played_id, "dealers_id": dealers_id},
    )


############################ Settings #############################
async def get_or_create_blackjack_settings(
    user_id: str,
) -> ExtensionSettings:
    settings = await db.fetchone(
        "SELECT * FROM blackjack.extension_settings WHERE user_id = :user_id",
        {"user_id": user_id},
        model=ExtensionSettings,
    )
    if settings:
        return settings
    else:
        settings = ExtensionSettings(id=urlsafe_short_hash(), user_id=user_id)
        await db.insert("blackjack.extension_settings", settings)
        return settings


async def update_blackjack_settings(settings: ExtensionSettings) -> ExtensionSettings:
    await db.update("blackjack.extension_settings", settings)
    return settings


async def delete_blackjack_settings(user_id: str) -> None:
    await db.execute(
        "DELETE FROM blackjack.extension_settings WHERE user_id = :user_id",
        {"user_id": user_id},
    )
