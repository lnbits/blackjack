import hashlib
import json
import random
import secrets
from datetime import datetime, timezone

from loguru import logger

from lnbits.core.crud import get_account, get_wallet
from lnbits.core.models import Payment
from lnbits.core.services import (
    create_invoice,
    get_pr_from_lnurl,
    pay_invoice,
    websocket_updater,
)

from .crud import (
    create_hands_played,
    get_dealers_by_id,
    get_hands_played_by_id,
    get_or_create_blackjack_settings,
    update_hands_played,
)
from .helpers import Card, get_hand_value
from .models import (
    CreateHandsPlayed,
    Dealers,
    HandOutcome,
    HandsPlayed,
    HandsPlayedPaymentRequest,
    HandStatus,
)


def generate_server_seed_and_hash(client_seed: str) -> tuple[str, str]:
    server_seed = secrets.token_hex(32)  # 64 hex characters = 32 bytes
    combined_seed = f"{server_seed}{client_seed}"
    server_seed_hash = hashlib.sha256(combined_seed.encode("utf-8")).hexdigest()
    return server_seed, server_seed_hash


class Deck:
    def __init__(self, num_decks=1):
        self.cards = self._create_deck(num_decks)

    def _create_deck(self, num_decks):
        suits = ["H", "D", "C", "S"]
        ranks = ["2", "3", "4", "5", "6", "7", "8", "9", "10", "J", "Q", "K", "A"]
        return [
            Card(suit, rank)
            for _ in range(num_decks)
            for suit in suits
            for rank in ranks
        ]

    def shuffle(self):
        random.shuffle(self.cards)

    def deal(self):
        if not self.cards:
            return None
        return self.cards.pop()


async def start_game(hands_played_id: str) -> HandsPlayed:
    hands_played = await get_hands_played_by_id(hands_played_id)
    if not hands_played:
        raise ValueError("Invalid hands_played_id.")

    # Check if the game has already been started
    if hands_played.status != HandStatus.PENDING:
        # If already started, just return the current state
        return hands_played

    if (
        not hands_played.server_seed
        or not hands_played.client_seed
        or not hands_played.server_seed_hash
    ):
        raise ValueError("Missing seeds for provably fair game.")

    rng_seed = int(hands_played.server_seed_hash.encode("utf-8").hex(), 16)

    dealer = await get_dealers_by_id(hands_played.dealers_id)
    if not dealer:
        raise ValueError("Dealer not found for this game.")

    # Create a separate random instance instead of using global random state
    game_random = random.Random()
    game_random.seed(rng_seed)

    deck = Deck(num_decks=dealer.decks or 1)
    # Shuffle using the game-specific random instance
    game_random.shuffle(deck.cards)

    # Deal initial cards and ensure they are not None
    player_card1 = deck.deal()
    player_card2 = deck.deal()
    dealer_card1 = deck.deal()
    dealer_card2 = deck.deal()

    if not all([player_card1, player_card2, dealer_card1, dealer_card2]):
        raise ValueError("Not enough cards in the deck to start the game.")

    player_hand = [player_card1, player_card2]
    dealer_hand = [dealer_card1, dealer_card2]

    # Filter out any None values from hands before calculating scores
    filtered_player_hand = [card for card in player_hand if card is not None]
    filtered_dealer_hand = [card for card in dealer_hand if card is not None]

    player_score = get_hand_value(filtered_player_hand)
    dealer_score = get_hand_value(filtered_dealer_hand)

    # serialize hands and shoe
    hands_played.player_hand = json.dumps(
        [card.to_dict() for card in filtered_player_hand]
    )
    hands_played.dealer_hand = json.dumps(
        [card.to_dict() for card in filtered_dealer_hand]
    )
    hands_played.shoe = json.dumps([card.to_dict() for card in deck.cards])
    hands_played.player_score = player_score
    hands_played.dealer_score = dealer_score
    hands_played.status = HandStatus.IN_PROGRESS

    await update_hands_played(hands_played)
    await websocket_updater(
        hands_played.id, json.dumps(hands_played.dict(), default=str)
    )
    return hands_played


async def payment_request_for_hands_played(
    dealers_id: str,
    data: CreateHandsPlayed,
) -> HandsPlayedPaymentRequest:
    dealer = await get_dealers_by_id(dealers_id)
    if not dealer:
        raise ValueError("Invalid dealers ID.")

    data.status = HandStatus.PENDING
    hands_played = await create_hands_played(data)

    payment: Payment = await create_invoice(
        wallet_id=dealer.wallet_id,
        amount=hands_played.bet_amount,
        extra={"tag": "blackjack", "hands_played_id": hands_played.id},
        memo=f"Payment for {dealer.name}. Hands Played ID: {hands_played.id}",
    )
    client_seed = payment.payment_hash
    server_seed, server_seed_hash = generate_server_seed_and_hash(client_seed)
    hands_played.client_seed = client_seed
    hands_played.server_seed_hash = server_seed_hash
    hands_played.server_seed = server_seed
    await update_hands_played(hands_played)

    hands_played_resp = HandsPlayedPaymentRequest(
        hands_played_id=hands_played.id,
        payment_hash=payment.payment_hash,
        payment_request=payment.bolt11,
    )
    return hands_played_resp


async def payment_received_for_hands_played(payment: Payment) -> bool:
    hands_played_id = payment.extra.get("hands_played_id")
    if not hands_played_id:
        logger.warning("Payment does not have a hands_played_id in extra.")
        return False

    hands_played = await get_hands_played_by_id(hands_played_id)
    if not hands_played:
        logger.warning(f"No hands played found for ID: {hands_played_id}")
        return False

    # Update the payment hash in the hands_played record
    hands_played.payment_hash = payment.payment_hash
    hands_played.paid = True
    hands_played.status = HandStatus.IN_PROGRESS
    await update_hands_played(hands_played)
    logger.info(f"Hands Played {hands_played_id} paid.")
    await websocket_updater(
        hands_played.id, json.dumps(hands_played.dict(), default=str)
    )
    await start_game(hands_played_id)
    return True


async def player_hit(hands_played_id: str) -> HandsPlayed:
    hands_played = await get_hands_played_by_id(hands_played_id)
    if not hands_played:
        raise ValueError("Invalid hands_played_id.")

    # Check if the game has started (shoe exists)
    if not hands_played.shoe:
        # If the game hasn't started yet, start it first
        await start_game(hands_played_id)
        hands_played = await get_hands_played_by_id(hands_played_id)
        if not hands_played:
            raise ValueError("Failed to retrieve hands_played after starting game.")

    if not hands_played.shoe or not hands_played.player_hand:
        raise ValueError("Game has not been started correctly.")

    deck = Deck()
    deck.cards = [Card.from_dict(c) for c in json.loads(hands_played.shoe)]

    player_hand = [Card.from_dict(c) for c in json.loads(hands_played.player_hand)]
    new_card = deck.deal()
    if new_card:
        player_hand.append(new_card)

    hands_played.player_hand = json.dumps([card.to_dict() for card in player_hand])
    # Filter out None values before calculating score
    filtered_player_hand = [card for card in player_hand if card is not None]
    hands_played.player_score = get_hand_value(filtered_player_hand)
    hands_played.shoe = json.dumps([card.to_dict() for card in deck.cards])

    if hands_played.player_score > 21:
        # Player busts
        hands_played.status = HandStatus.COMPLETED
        hands_played.outcome = HandOutcome.DEALER_WINS
    elif hands_played.player_score == 21:
        # Player got 21, automatically stand and resolve dealer turn
        # Ensure hands_played is not None before calling resolve_dealer_turn
        if not hands_played:
            raise ValueError(
                "Failed to retrieve hands_played for resolving dealer turn."
            )
        hands_played = await resolve_dealer_turn(hands_played)
    else:
        # Game continues
        hands_played.status = HandStatus.IN_PROGRESS

    await update_hands_played(hands_played)
    await websocket_updater(
        hands_played.id, json.dumps(hands_played.dict(), default=str)
    )
    return hands_played


async def player_stand(hands_played_id: str) -> HandsPlayed:
    hands_played = await get_hands_played_by_id(hands_played_id)
    if not hands_played:
        raise ValueError("Invalid hands_played_id.")

    # Check if the game has started (shoe exists)
    if not hands_played.shoe:
        # If the game hasn't started yet, start it first
        await start_game(hands_played_id)
        hands_played = await get_hands_played_by_id(hands_played_id)
        if not hands_played:
            raise ValueError("Failed to retrieve hands_played after starting game.")

    # Ensure hands_played is not None before calling resolve_dealer_turn
    if not hands_played:
        raise ValueError("Failed to retrieve hands_played after starting game.")

    # Resolve dealer's turn and determine outcome
    hands_played = await resolve_dealer_turn(hands_played)

    # Update the game state in the database
    await update_hands_played(hands_played)

    await websocket_updater(
        hands_played.id, json.dumps(hands_played.dict(), default=str)
    )
    return hands_played


async def resolve_dealer_turn(hands_played: HandsPlayed) -> HandsPlayed:
    """Resolve the dealer's turn and determine the game outcome."""
    if not hands_played.shoe or not hands_played.dealer_hand:
        raise ValueError("Game has not been started correctly.")

    deck = Deck()
    deck.cards = [Card.from_dict(c) for c in json.loads(hands_played.shoe)]
    dealer_hand = [Card.from_dict(c) for c in json.loads(hands_played.dealer_hand)]

    # Get dealer settings to determine hit rules
    dealer = await get_dealers_by_id(hands_played.dealers_id)
    if not dealer:
        raise ValueError("Invalid dealer ID.")

    # Dealer draws until reaching 17 or higher
    # If hit_soft_17 is True, dealer hits on soft 17 (Ace + 6)
    while True:
        # Filter out None values before calculating score
        filtered_dealer_hand = [card for card in dealer_hand if card is not None]
        dealer_score = get_hand_value(filtered_dealer_hand)

        # Check if dealer should hit
        should_hit = dealer_score < 17

        # If dealer hits on soft 17, check for soft 17 (score of 17 with an Ace valued as 11)
        if dealer.hit_soft_17 and dealer_score == 17:
            # Check if there's an Ace counted as 11 (making it a soft 17)
            aces = [card for card in filtered_dealer_hand if card.rank == "A"]
            non_ace_total = sum(
                card.value for card in filtered_dealer_hand if card.rank != "A"
            )

            # If there's an Ace and the non-ace total is 6, it's a soft 17
            if aces and non_ace_total == 6:
                should_hit = True

        if not should_hit:
            break

        new_card = deck.deal()
        if new_card:
            dealer_hand.append(new_card)
        else:
            # If deck is empty, break to avoid infinite loop
            break

    hands_played.dealer_hand = json.dumps([card.to_dict() for card in dealer_hand])
    # Filter out None values before calculating score
    filtered_dealer_hand = [card for card in dealer_hand if card is not None]
    hands_played.dealer_score = get_hand_value(filtered_dealer_hand)
    hands_played.shoe = json.dumps([card.to_dict() for card in deck.cards])

    player_score = hands_played.player_score
    dealer_score = hands_played.dealer_score

    if player_score is None or dealer_score is None:
        raise ValueError("Player or dealer score not set.")

    # Determine outcome
    if dealer_score > 21:
        hands_played.outcome = HandOutcome.PLAYER_WINS
    elif player_score > dealer_score:
        hands_played.outcome = HandOutcome.PLAYER_WINS
    elif player_score < dealer_score:
        hands_played.outcome = HandOutcome.DEALER_WINS
    else:
        hands_played.outcome = HandOutcome.PUSH

    hands_played.status = HandStatus.COMPLETED

    # Process payout if player wins or there's a push
    if (
        hands_played.outcome in [HandOutcome.PLAYER_WINS, HandOutcome.PUSH]
        and hands_played.lnaddress
    ):
        await process_payout(hands_played)

    return hands_played


async def process_payout(hands_played: HandsPlayed) -> None:
    """Process the payout for winning hands."""
    try:
        dealer = await get_dealers_by_id(hands_played.dealers_id)
        if not dealer:
            raise ValueError("Invalid dealer ID.")

        user_id = await get_user_id_from_wallet_id(dealer.wallet_id)
        if not user_id:
            raise ValueError("Could not determine user ID from dealer wallet.")

        payout_amount = _calculate_payout_amount(hands_played, dealer)
        if payout_amount <= 0:
            return

        settings = await get_or_create_blackjack_settings(user_id)
        rake_percentage = settings.rake if settings else 0

        # Apply rake to the total payout amount (original bet + winnings)
        if hands_played.outcome in [HandOutcome.PLAYER_WINS, HandOutcome.PUSH]:
            rake_amount = int(payout_amount * (rake_percentage / 100))
            final_payout = payout_amount - rake_amount
        else:
            final_payout = 0

        if final_payout <= 0:
            return

        # Check if lnaddress is available before attempting payout
        if not hands_played.lnaddress:
            logger.warning(
                f"No lnaddress available for payout for hands_played_id {hands_played.id}"
            )
            return

        payment_request = await get_pr_from_lnurl(
            hands_played.lnaddress,
            int(final_payout * 1000),  # Convert satoshis to milli-satoshis
        )

        if payment_request:
            await pay_invoice(
                payment_request=payment_request,
                wallet_id=dealer.wallet_id,
                description=f"Blackjack payout for hands_played_id: {hands_played.id}",
                extra={"tag": "blackjack_payout", "hands_played_id": hands_played.id},
            )
            hands_played.payout_sent = True
            hands_played.ended_at = datetime.now(timezone.utc)
            await update_hands_played(hands_played)

    except Exception as e:
        logger.error(
            f"Error processing payout for hands_played_id {hands_played.id}: {e}"
        )


async def get_user_id_from_wallet_id(wallet_id: str) -> str | None:
    wallet = await get_wallet(wallet_id)
    if wallet:
        account = await get_account(wallet.user)
        if account:
            return account.id
    return None


def _calculate_payout_amount(hands_played: HandsPlayed, dealer: Dealers) -> int:
    """Calculate the payout amount based on the game outcome."""
    if hands_played.outcome == HandOutcome.PLAYER_WINS:
        if hands_played.is_player_blackjack():
            payout_ratio_parts = dealer.blackjack_payout.split(":")
            if len(payout_ratio_parts) != 2:
                raise ValueError("Invalid blackjack payout format")
            try:
                payout_numerator = int(payout_ratio_parts[0])
                payout_denominator = int(payout_ratio_parts[1])
                if payout_denominator == 0:
                    raise ValueError("Invalid blackjack payout - division by zero")
                payout_multiplier = payout_numerator / payout_denominator
                return hands_played.bet_amount + int(
                    hands_played.bet_amount * payout_multiplier
                )
            except ValueError:
                raise ValueError("Invalid blackjack payout values")
        else:
            # Regular win (1:1)
            return hands_played.bet_amount * 2
    elif hands_played.outcome == HandOutcome.PUSH:
        # Push means return original bet
        return hands_played.bet_amount
    return 0
