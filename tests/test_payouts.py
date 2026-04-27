import json
from types import SimpleNamespace

import pytest

from .. import services
from ..crud import (
    create_dealers,
    create_hands_played,
    get_hands_played_by_id,
    update_hands_played,
)
from ..models import CreateDealers, CreateHandsPlayed, HandOutcome, HandStatus
from ..services import process_payout, resolve_dealer_turn


@pytest.mark.asyncio
async def test_process_payout_pays_winning_hand_once(monkeypatch):
    dealer = await create_dealers(
        CreateDealers(
            name="payout_dealer",
            wallet_id="dealer_wallet",
            min_bet=10,
            max_bet=100,
            decks=1,
        )
    )
    hand = await create_hands_played(
        CreateHandsPlayed(
            dealers_id=dealer.id,
            bet_amount=10,
            lnaddress="winner@lnaddress.com",
        )
    )
    hand.status = HandStatus.COMPLETED
    hand.paid = True
    hand.outcome = HandOutcome.PLAYER_WINS
    hand.player_hand = json.dumps(
        [
            {"suit": "H", "rank": "9", "value": 9},
            {"suit": "S", "rank": "7", "value": 7},
        ]
    )
    await update_hands_played(hand)

    lnurl_requests: list[tuple[str, int]] = []
    paid_requests: list[dict] = []

    async def fake_get_wallet(wallet_id):
        assert wallet_id == dealer.wallet_id
        return SimpleNamespace(user="dealer_user")

    async def fake_get_pr_from_lnurl(lnaddress, amount_msat):
        lnurl_requests.append((lnaddress, amount_msat))
        return "lnbc1payoutinvoice"

    async def fake_pay_invoice(**kwargs):
        paid_requests.append(kwargs)
        assert kwargs["wallet_id"] == dealer.wallet_id
        assert kwargs["payment_request"] == "lnbc1payoutinvoice"
        assert kwargs["max_sat"] == 20
        return SimpleNamespace(payment_hash="paid-payout-hash")

    monkeypatch.setattr(services, "get_wallet", fake_get_wallet)
    monkeypatch.setattr(services, "get_pr_from_lnurl", fake_get_pr_from_lnurl)
    monkeypatch.setattr(services, "pay_invoice", fake_pay_invoice)

    await process_payout(hand)
    await process_payout(hand)

    stored = await get_hands_played_by_id(hand.id)
    assert stored is not None
    assert stored.payout_sent is True
    assert stored.payout_amount == 20
    assert lnurl_requests == [("winner@lnaddress.com", 20_000)]
    assert len(paid_requests) == 1


@pytest.mark.asyncio
async def test_resolve_dealer_turn_persists_final_hand_before_payout(monkeypatch):
    dealer = await create_dealers(
        CreateDealers(
            name="race_dealer",
            wallet_id="race_wallet",
            min_bet=10,
            max_bet=100,
            decks=1,
        )
    )
    hand = await create_hands_played(
        CreateHandsPlayed(
            dealers_id=dealer.id,
            bet_amount=10,
            lnaddress="winner@lnaddress.com",
        )
    )
    hand.status = HandStatus.IN_PROGRESS
    hand.paid = True
    hand.player_score = 20
    hand.player_hand = json.dumps(
        [
            {"suit": "H", "rank": "K", "value": 10},
            {"suit": "S", "rank": "Q", "value": 10},
        ]
    )
    hand.dealer_hand = json.dumps(
        [
            {"suit": "D", "rank": "10", "value": 10},
            {"suit": "C", "rank": "7", "value": 7},
        ]
    )
    hand.shoe = json.dumps([])
    await update_hands_played(hand)

    async def fake_get_wallet(wallet_id):
        assert wallet_id == dealer.wallet_id
        return SimpleNamespace(user="dealer_user")

    async def fake_process_payout(final_hand):
        stored = await get_hands_played_by_id(final_hand.id)
        assert stored is not None
        assert stored.status == HandStatus.COMPLETED
        assert stored.outcome == HandOutcome.PLAYER_WINS
        assert stored.payout_amount == 20
        final_hand.payout_sent = True
        await update_hands_played(final_hand)

    monkeypatch.setattr(services, "get_wallet", fake_get_wallet)
    monkeypatch.setattr(services, "process_payout", fake_process_payout)

    resolved = await resolve_dealer_turn(hand)

    assert resolved.status == HandStatus.COMPLETED
    assert resolved.outcome == HandOutcome.PLAYER_WINS
    assert resolved.payout_sent is True
