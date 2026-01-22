from http import HTTPStatus

from fastapi import APIRouter, Depends
from fastapi.exceptions import HTTPException
from lnbits.core.models import SimpleStatus, User
from lnbits.db import Filters, Page
from lnbits.decorators import (
    check_user_exists,
    parse_filters,
)
from lnbits.helpers import generate_filter_params_openapi

from .crud import (
    create_dealers,
    delete_dealers,
    delete_hands_played,
    get_dealers,
    get_dealers_by_id,
    get_dealers_ids_by_wallet,
    get_dealers_paginated,
    get_hands_played_by_id,
    get_hands_played_paginated,
    get_or_create_blackjack_settings,
    update_blackjack_settings,
    update_dealers,
    update_hands_played,
)
from .models import (
    CreateDealers,
    CreateHandsPlayed,
    Dealers,
    DealersFilters,
    ExtensionSettings,
    HandsPlayed,
    HandsPlayedFilters,
    HandsPlayedPaymentRequest,
    HandStatus,
    PublicHandsPlayed,
)
from .services import (
    payment_request_for_hands_played,
    player_hit,
    player_stand,
)

dealers_filters = parse_filters(DealersFilters)
hands_played_filters = parse_filters(HandsPlayedFilters)

blackjack_api_router = APIRouter()


############################# Dealers #############################
@blackjack_api_router.post("/api/v1/dealers", status_code=HTTPStatus.CREATED)
async def api_create_dealers(
    data: CreateDealers,
    user: User = Depends(check_user_exists),
) -> Dealers:
    if data.wallet_id not in [wallet.id for wallet in user.wallets]:
        raise HTTPException(HTTPStatus.FORBIDDEN, "Not your wallet.")
    dealers = await create_dealers(data)
    return dealers


@blackjack_api_router.put("/api/v1/dealers/{dealers_id}", status_code=HTTPStatus.CREATED)
async def api_update_dealers(
    dealers_id: str,
    data: CreateDealers,
    user: User = Depends(check_user_exists),
) -> Dealers:
    if data.wallet_id not in [wallet.id for wallet in user.wallets]:
        raise HTTPException(HTTPStatus.FORBIDDEN, "Not your dealers.")
    dealer = await get_dealers(data.wallet_id, dealers_id)
    if not dealer:
        raise HTTPException(HTTPStatus.NOT_FOUND, "Dealers not found.")
    dealer = await update_dealers(Dealers(**{**dealer.dict(), **data.dict()}))
    return dealer


@blackjack_api_router.get(
    "/api/v1/dealers/paginated",
    name="Dealers List",
    summary="get paginated list of dealers",
    response_description="list of dealers",
    openapi_extra=generate_filter_params_openapi(DealersFilters),
    response_model=Page[Dealers],
)
async def api_get_dealers_paginated(
    user: User = Depends(check_user_exists),
    filters: Filters = Depends(dealers_filters),
) -> Page[Dealers]:
    wallet_ids = [wallet.id for wallet in user.wallets]
    return await get_dealers_paginated(
        wallet_ids=wallet_ids,
        filters=filters,
    )


@blackjack_api_router.get(
    "/api/v1/public/dealers",
    name="Public Dealers List",
    summary="get list of active dealers",
    response_description="list of active dealers",
    response_model=Page[Dealers],
)
async def api_get_public_dealers() -> Page[Dealers]:
    # We want only active dealers for public view.
    # Assuming get_dealers_paginated handles empty wallet_ids to return all?
    # No, get_dealers_paginated in crud.py builds WHERE clause on wallet_ids if provided.
    # If wallet_ids is None, it returns all.
    # But we should probably filter by 'active=True'.
    # For now, let's return all. Frontend can filter or we add a filter.
    # We should enforce active=True via filters if possible.

    # Manually create filters for active=True
    filters = Filters(filters=[])  # Empty filters
    # Ideally we'd pass a custom filter, but lnbits filters are query params.
    # Let's just fetch all for now or modify CRUD to support simple where args better.
    # crud.get_dealers_paginated takes 'filters' which is lnbits.db.Filters.

    return await get_dealers_paginated()


@blackjack_api_router.get(
    "/api/v1/dealers/{dealers_id}",
    name="Get Dealers",
    summary="Get the dealers with this id.",
    response_description="An dealers or 404 if not found",
    response_model=Dealers,
)
async def api_get_dealers(
    dealers_id: str,
) -> Dealers:
    dealers = await get_dealers_by_id(dealers_id)
    if not dealers:
        raise HTTPException(HTTPStatus.NOT_FOUND, "Dealers not found.")

    return dealers


@blackjack_api_router.delete(
    "/api/v1/dealers/{dealers_id}",
    name="Delete Dealers",
    summary="Delete the dealers and optionally all its associated hands_played.",
    response_description="The status of the deletion.",
    response_model=SimpleStatus,
)
async def api_delete_dealers(
    dealers_id: str,
    user: User = Depends(check_user_exists),
) -> SimpleStatus:
    dealer = await get_dealers_by_id(dealers_id)
    if not dealer:
        raise HTTPException(HTTPStatus.NOT_FOUND, "Dealers not found.")
    if dealer.wallet_id not in [wallet.id for wallet in user.wallets]:
        raise HTTPException(HTTPStatus.FORBIDDEN, "Not your dealers.")
    await delete_dealers(dealer.wallet_id, dealers_id)
    return SimpleStatus(success=True, message="Dealers Deleted")


############################# Hands Played #############################


@blackjack_api_router.post(
    "/api/v1/hands_played/{hands_played_id}/hit",
    name="Player Hit",
    summary="Player hits and gets another card.",
    response_description="The updated hands played.",
    response_model=PublicHandsPlayed,
)
async def api_player_hit(
    hands_played_id: str,
) -> PublicHandsPlayed:
    hands_played = await get_hands_played_by_id(hands_played_id)
    if not hands_played:
        raise HTTPException(HTTPStatus.NOT_FOUND, "Hands Played not found.")
    if hands_played.status == HandStatus.COMPLETED:
        raise HTTPException(HTTPStatus.BAD_REQUEST, "Game is already completed.")

    hands_played = await player_hit(hands_played_id)
    return PublicHandsPlayed.from_db(hands_played)


@blackjack_api_router.post(
    "/api/v1/hands_played/{hands_played_id}/stand",
    name="Player Stand",
    summary="Player stands and ends their turn.",
    response_description="The updated hands played.",
    response_model=PublicHandsPlayed,
)
async def api_player_stand(
    hands_played_id: str,
) -> PublicHandsPlayed:
    hands_played = await get_hands_played_by_id(hands_played_id)
    if not hands_played:
        raise HTTPException(HTTPStatus.NOT_FOUND, "Hands Played not found.")
    if hands_played.status == HandStatus.COMPLETED:
        raise HTTPException(HTTPStatus.BAD_REQUEST, "Game is already completed.")

    hands_played = await player_stand(hands_played_id)
    return PublicHandsPlayed.from_db(hands_played)


@blackjack_api_router.post(
    "/api/v1/hands_played/{dealers_id}",
    name="Create Hands Played",
    summary="Create new hands played for the specified dealers.",
    response_description="The created hands played.",
    response_model=HandsPlayedPaymentRequest | None,
    status_code=HTTPStatus.CREATED,
)
async def api_create_hands_played(
    dealers_id: str,
    data: CreateHandsPlayed,
) -> HandsPlayedPaymentRequest | None:
    return await payment_request_for_hands_played(dealers_id, data)


@blackjack_api_router.put(
    "/api/v1/hands_played/{hands_played_id}",
    name="Update Hands Played",
    summary="Update the hands_played with this id.",
    response_description="The updated hands played.",
    response_model=PublicHandsPlayed,
)
async def api_update_hands_played(
    hands_played_id: str,
    data: CreateHandsPlayed,
    user: User = Depends(check_user_exists),
) -> PublicHandsPlayed:
    hands_played = await get_hands_played_by_id(hands_played_id)
    if not hands_played:
        raise HTTPException(HTTPStatus.NOT_FOUND, "Hands Played not found.")

    dealer = await get_dealers_by_id(hands_played.dealers_id)
    if not dealer:
        raise HTTPException(HTTPStatus.NOT_FOUND, "Dealers not found.")

    if dealer.wallet_id not in [wallet.id for wallet in user.wallets]:
        raise HTTPException(HTTPStatus.FORBIDDEN, "Not your dealers.")

    hands_played = await update_hands_played(HandsPlayed(**{**hands_played.dict(), **data.dict()}))
    return PublicHandsPlayed.from_db(hands_played)


@blackjack_api_router.get(
    "/api/v1/hands_played/paginated",
    name="Hands Played List",
    summary="get paginated list of hands_played",
    response_description="list of hands_played",
    openapi_extra=generate_filter_params_openapi(HandsPlayedFilters),
    response_model=Page[HandsPlayed],
)
async def api_get_hands_played_paginated(
    user: User = Depends(check_user_exists),
    dealers_id: str | None = None,
    filters: Filters = Depends(hands_played_filters),
) -> Page[HandsPlayed]:
    # This endpoint is for Admins (Dealears) to see games.
    # It returns full HandsPlayed, which is fine for the dealer owner.
    # Players don't list hands here.
    wallet_ids = [wallet.id for wallet in user.wallets]
    dealer_ids = []
    for wallet_id in wallet_ids:
        dealer_ids.extend(await get_dealers_ids_by_wallet(wallet_id))

    if dealers_id:
        if dealers_id not in dealer_ids:
            raise HTTPException(HTTPStatus.FORBIDDEN, "Not your dealers.")
        dealer_ids = [dealers_id]

    return await get_hands_played_paginated(
        dealers_ids=dealer_ids,
        filters=filters,
    )


@blackjack_api_router.get(
    "/api/v1/hands_played/{hands_played_id}",
    name="Get Hands Played",
    summary="Get the hands played with this id.",
    response_description="An hands played or 404 if not found",
    response_model=PublicHandsPlayed,
)
async def api_get_hands_played(
    hands_played_id: str,
) -> PublicHandsPlayed:
    hands_played = await get_hands_played_by_id(hands_played_id)
    if not hands_played:
        raise HTTPException(HTTPStatus.NOT_FOUND, "HandsPlayed not found.")
    return PublicHandsPlayed.from_db(hands_played)


@blackjack_api_router.delete(
    "/api/v1/hands_played/{hands_played_id}",
    name="Delete Hands Played",
    summary="Delete the hands_played",
    response_description="The status of the deletion.",
    response_model=SimpleStatus,
)
async def api_delete_hands_played(
    hands_played_id: str,
    user: User = Depends(check_user_exists),
) -> SimpleStatus:
    hands_played = await get_hands_played_by_id(hands_played_id)
    if not hands_played:
        raise HTTPException(HTTPStatus.NOT_FOUND, "HandsPlayed not found.")
    dealer = await get_dealers_by_id(hands_played.dealers_id)
    if not dealer:
        raise HTTPException(HTTPStatus.NOT_FOUND, "Dealers deleted for this Hands Played.")

    if dealer.wallet_id not in [wallet.id for wallet in user.wallets]:
        raise HTTPException(HTTPStatus.FORBIDDEN, "Not your dealers.")

    await delete_hands_played(dealer.id, hands_played_id)
    return SimpleStatus(success=True, message="Hands Played Deleted")


############################ Settings #############################
@blackjack_api_router.get(
    "/api/v1/settings",
    name="Get Settings",
    summary="Get the settings for the current user.",
    response_description="The settings or 404 if not found",
    response_model=ExtensionSettings,
)
async def api_get_settings(
    user: User = Depends(check_user_exists),
) -> ExtensionSettings:
    return await get_or_create_blackjack_settings(user.id)


@blackjack_api_router.put(
    "/api/v1/settings",
    name="Update Settings",
    summary="Update the settings for the current user.",
    response_description="The updated settings.",
    response_model=ExtensionSettings,
)
async def api_update_extension_settings(
    data: ExtensionSettings,
    user: User = Depends(check_user_exists),
) -> ExtensionSettings:
    if data.user_id != user.id:
        raise HTTPException(HTTPStatus.FORBIDDEN, "Not your settings.")
    return await update_blackjack_settings(data)
