import json
from types import SimpleNamespace

import pytest
from lnbits.core.models import Payment

from .. import services
from ..crud import create_dealers, get_hands_played_by_id
from ..models import CreateDealers, CreateHandsPlayed, HandStatus
from ..services import (
    payment_received_for_hands_played,
    payment_request_for_hands_played,
    player_hit,
    player_stand,
)


def fake_payment(payment_hash: str, hands_played_id: str | None = None) -> Payment:
    return Payment(
        checking_id=payment_hash,
        payment_hash=payment_hash,
        wallet_id="test_wallet",
        amount=10_000,
        fee=0,
        bolt11=f"lnbc-{payment_hash}",
        extra={"hands_played_id": hands_played_id} if hands_played_id else {},
    )


@pytest.fixture
def mock_lnbits_services(monkeypatch):
    async def create_invoice(**kwargs):
        return fake_payment("test_payment_hash")

    async def websocket_updater(*args, **kwargs):
        return None

    async def process_payout(*args, **kwargs):
        return None

    async def get_wallet(*args, **kwargs):
        return SimpleNamespace(user="test_user")

    monkeypatch.setattr(services, "create_invoice", create_invoice)
    monkeypatch.setattr(services, "websocket_updater", websocket_updater)
    monkeypatch.setattr(services, "process_payout", process_payout)
    monkeypatch.setattr(services, "get_wallet", get_wallet)


@pytest.mark.asyncio
async def test_paid_hand_happy_flow(mock_lnbits_services):
    dealer = await create_dealers(
        CreateDealers(
            name="test_dealer",
            wallet_id="test_wallet",
            min_bet=10,
            max_bet=100,
            decks=1,
        )
    )

    hand_data = CreateHandsPlayed(
        dealers_id=dealer.id,
        bet_amount=10,
        lnaddress="test@lnaddress.com",
        client_seed=None,
        payment_hash=None,
    )
    payment_response = await payment_request_for_hands_played(dealer.id, hand_data)
    hand = await get_hands_played_by_id(payment_response.hands_played_id)
    assert hand is not None
    assert hand.status == HandStatus.PENDING
    assert hand.paid is False
    assert hand.player_hand is None
    assert hand.dealer_hand is None
    assert hand.server_seed is not None
    assert hand.server_seed_hash is not None
    assert payment_response.payment_hash is not None

    await payment_received_for_hands_played(fake_payment(payment_response.payment_hash, hand.id))

    hand = await get_hands_played_by_id(hand.id)
    assert hand is not None
    assert hand.paid is True
    assert hand.status == HandStatus.IN_PROGRESS
    assert len(json.loads(hand.player_hand or "[]")) == 2
    assert len(json.loads(hand.dealer_hand or "[]")) == 2

    hand = await player_hit(hand.id)
    assert hand.paid is True
    assert len(json.loads(hand.player_hand or "[]")) >= 2

    if hand.status != HandStatus.COMPLETED:
        hand = await player_stand(hand.id)

    assert hand.status == HandStatus.COMPLETED
    assert hand.outcome is not None
    assert hand.server_seed is not None


@pytest.mark.asyncio
async def test_unpaid_hand_cannot_be_played(mock_lnbits_services):
    dealer = await create_dealers(
        CreateDealers(
            name="test_dealer",
            wallet_id="test_wallet",
            min_bet=10,
            max_bet=100,
            decks=1,
        )
    )
    payment_response = await payment_request_for_hands_played(
        dealer.id,
        CreateHandsPlayed(
            dealers_id=dealer.id,
            bet_amount=10,
            lnaddress="test@lnaddress.com",
            client_seed=None,
            payment_hash=None,
        ),
    )

    with pytest.raises(ValueError, match="unpaid"):
        await player_hit(payment_response.hands_played_id)

    with pytest.raises(ValueError, match="unpaid"):
        await player_stand(payment_response.hands_played_id)
