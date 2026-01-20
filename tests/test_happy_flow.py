import pytest

from blackjack.crud import (
    create_dealers,
    get_hands_played_by_id,
    update_hands_played,
)
from blackjack.models import CreateDealers, CreateHandsPlayed
from blackjack.services import payment_request_for_hands_played, player_hit, player_stand


@pytest.mark.asyncio
async def test_happy_flow():
    # 1. Create a dealer
    dealer_data = CreateDealers(
        name="test_dealer",
        wallet_id="test_wallet",
        min_bet=10,
        max_bet=100,
        decks=1,
    )
    dealer = await create_dealers(dealer_data)
    assert dealer is not None

    # 2. Create a hand (place a bet) using the service function that handles seeds
    hand_data = CreateHandsPlayed(
        dealers_id=dealer.id,
        bet_amount=10,
        lnaddress="test@lnaddress.com",
        client_seed="test_client_seed",
        payment_hash="test_payment_hash",
    )
    hands_played_response = await payment_request_for_hands_played(dealer.id, hand_data)
    hand = await get_hands_played_by_id(hands_played_response.hands_played_id)
    assert hand is not None
    assert hand.bet_amount == 10
    assert hand.paid is False
    assert hand.server_seed is not None
    assert hand.server_seed_hash is not None

    # 3. "Pay" the invoice
    hand.paid = True
    hand = await update_hands_played(hand)
    assert hand.paid is True

    # 4. Start the game (this is done implicitly when the hand is paid)
    # let's get the hand again to check the initial cards
    hand = await get_hands_played_by_id(hand.id)
    assert hand is not None
    assert hand.player_hand is not None
    assert hand.dealer_hand is not None

    # 5. Player hits
    hand = await player_hit(hand.id)
    assert len(hand.player_hand) > 2

    # 6. Player stands
    hand = await player_stand(hand.id)
    assert hand.status == "finished"

    # 7. Check the outcome
    assert hand.outcome is not None
    if hand.outcome == "player_wins":
        # check payout
        pass
    elif hand.outcome == "dealer_wins":
        pass
    elif hand.outcome == "push":
        pass
