import pytest

from ..crud import (
    create_dealers,
    delete_dealers,
    get_dealers,
    get_dealers_by_id,
    get_dealers_ids_by_wallet,
    update_dealers,
)
from ..models import CreateDealers, Dealers


@pytest.mark.asyncio
async def test_create_dealers():
    data = CreateDealers(
        name="test_dealer",
        wallet_id="test_wallet",
        min_bet=10,
        max_bet=100,
        decks=1,
    )

    dealer = await create_dealers(data)

    assert dealer.wallet_id == data.wallet_id
    assert dealer.name == data.name
    assert dealer.min_bet == data.min_bet
    assert dealer.max_bet == data.max_bet
    assert dealer.decks == data.decks


@pytest.mark.asyncio
async def test_get_dealers():
    data = CreateDealers(
        name="test_dealer",
        wallet_id="test_wallet",
        min_bet=10,
        max_bet=100,
        decks=1,
    )
    dealer = await create_dealers(data)
    retrieved_dealer = await get_dealers("test_wallet", dealer.id)
    assert retrieved_dealer == dealer


@pytest.mark.asyncio
async def test_get_dealers_by_id():
    data = CreateDealers(
        name="test_dealer",
        wallet_id="test_wallet",
        min_bet=10,
        max_bet=100,
        decks=1,
    )
    dealer = await create_dealers(data)
    retrieved_dealer = await get_dealers_by_id(dealer.id)
    assert retrieved_dealer == dealer


@pytest.mark.asyncio
async def test_get_dealers_ids_by_wallet():
    data = CreateDealers(
        name="test_dealer",
        wallet_id="test_wallet",
        min_bet=10,
        max_bet=100,
        decks=1,
    )
    dealer = await create_dealers(data)
    dealer_ids = await get_dealers_ids_by_wallet("test_wallet")
    assert len(dealer_ids) >= 1
    assert dealer.id in dealer_ids


@pytest.mark.asyncio
async def test_update_dealers():
    data = CreateDealers(
        name="test_dealer",
        wallet_id="test_wallet",
        min_bet=10,
        max_bet=100,
        decks=1,
    )
    dealer = await create_dealers(data)
    updated_data = Dealers(**dealer.dict())
    updated_data.name = "updated_dealer_name"
    updated_dealer = await update_dealers(updated_data)
    assert updated_dealer.name == "updated_dealer_name"
    retrieved_dealer = await get_dealers("test_wallet", dealer.id)
    assert retrieved_dealer is not None
    assert retrieved_dealer.name == "updated_dealer_name"


@pytest.mark.asyncio
async def test_delete_dealers():
    data = CreateDealers(
        name="test_dealer",
        wallet_id="test_wallet",
        min_bet=10,
        max_bet=100,
        decks=1,
    )
    dealer = await create_dealers(data)
    await delete_dealers("test_wallet", dealer.id)
    retrieved_dealer = await get_dealers("test_wallet", dealer.id)
    assert retrieved_dealer is None
