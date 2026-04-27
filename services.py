import hashlib
import json
import random
from datetime import datetime, timezone

from lnbits.core.crud import get_wallet
from lnbits.core.models import Payment
from lnbits.core.services import (
    create_invoice,
    get_pr_from_lnurl,
    pay_invoice,
    websocket_updater,
)
from loguru import logger

from .crud import (
    claim_hands_played_payout,
    create_hands_played,
    get_active_dealers_by_id,
    get_dealers_by_id,
    get_hands_played_by_id,
    get_or_create_blackjack_settings,
    reset_hands_played_payout_claim,
    update_hands_played,
)
from .helpers import Card, generate_server_seed_and_hash, get_hand_value
from .models import (
    CreateHandsPlayed,
    Dealers,
    GameUpdateData,
    HandOutcome,
    HandsPlayed,
    HandsPlayedPaymentRequest,
    HandStatus,
)


class Deck:
    def __init__(self, num_decks=1, cards: list[Card] | None = None):
        if cards is not None:
            self.cards = cards
        else:
            self.cards = self._create_deck(num_decks)

    def _create_deck(self, num_decks):
        suits = ["H", "D", "C", "S"]
        ranks = ["2", "3", "4", "5", "6", "7", "8", "9", "10", "J", "Q", "K", "A"]
        return [Card(suit, rank) for _ in range(num_decks) for suit in suits for rank in ranks]

    def shuffle(self, random_instance=None):
        if random_instance:
            random_instance.shuffle(self.cards)
        else:
            random.shuffle(self.cards)

    def deal(self):
        if not self.cards:
            return None
        return self.cards.pop()


async def start_game(hands_played_id: str) -> HandsPlayed:
    """
    Initializes and starts a new blackjack game.

    Args:
        hands_played_id (str): The ID of the hands played record.

    Returns:
        HandsPlayed: The updated hands played record.

    Raises:
        ValueError: If the hands played ID is invalid or seeds are missing.
    """
    hands_played = await get_hands_played_by_id(hands_played_id)
    if not hands_played:
        raise ValueError("Invalid hands_played_id.")

    if not hands_played.paid:
        raise ValueError("Cannot start an unpaid hand.")

    # Check if the game has already been initialized (shoe exists and hands are dealt)
    if hands_played.shoe and hands_played.player_hand and hands_played.dealer_hand:
        # If already initialized, just return the current state
        return hands_played

    if not hands_played.server_seed or not hands_played.client_seed or not hands_played.server_seed_hash:
        raise ValueError("Missing seeds for provably fair game.")

    rng_material = f"{hands_played.server_seed}{hands_played.client_seed}"
    rng_seed = int(hashlib.sha256(rng_material.encode("utf-8")).hexdigest(), 16)

    dealer = await get_active_dealers_by_id(hands_played.dealers_id)
    if not dealer:
        raise ValueError("Dealer not found or inactive for this game.")

    # Create a separate random instance instead of using global random state
    game_random = random.Random()
    game_random.seed(rng_seed)

    deck = Deck(num_decks=dealer.decks or 1)
    # Shuffle using the game-specific random instance
    deck.shuffle(random_instance=game_random)

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
    hands_played.player_hand = json.dumps([card.to_dict() for card in filtered_player_hand])
    hands_played.dealer_hand = json.dumps([card.to_dict() for card in filtered_dealer_hand])
    hands_played.shoe = json.dumps([card.to_dict() for card in deck.cards])
    hands_played.player_score = player_score
    hands_played.dealer_score = dealer_score
    hands_played.status = HandStatus.IN_PROGRESS

    await update_hands_played(hands_played)
    # Send game update without sensitive data during the game
    game_update_data = GameUpdateData.from_hands_played(hands_played, include_sensitive=False)
    logger.debug("### WEBSOCKET UPDATE START_GAME ###")
    await websocket_updater(hands_played.id, json.dumps(game_update_data.dict(), default=str))
    return hands_played


async def payment_request_for_hands_played(
    dealers_id: str,
    data: CreateHandsPlayed,
) -> HandsPlayedPaymentRequest:
    """
    Creates a payment request (invoice) for a new bet.

    Args:
        dealers_id (str): The ID of the dealer.
        data (CreateHandsPlayed): The data for creating a hands played record.

    Returns:
        HandsPlayedPaymentRequest: The payment request details.

    Raises:
        ValueError: If the dealer ID is invalid or bet amount is out of limits.
    """
    dealer = await get_active_dealers_by_id(dealers_id)
    if not dealer:
        raise ValueError("Invalid or inactive dealers ID.")

    # check if bet amount is within dealer limits
    if data.bet_amount < dealer.min_bet or data.bet_amount > dealer.max_bet:
        raise ValueError("Bet amount is outside the dealer's allowed limits.")

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
        server_seed_hash=server_seed_hash,
    )
    return hands_played_resp


async def payment_received_for_hands_played(payment: Payment) -> bool:
    """
    Handles the payment received event for a hands played record.

    Args:
        payment (Payment): The payment object.

    Returns:
        bool: True if processed successfully, False otherwise.
    """
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
    # Send game update without sensitive data during the game
    game_update_data = GameUpdateData.from_hands_played(hands_played, include_sensitive=False)
    logger.debug("### WEBSOCKET UPDATE PAYMENT_RECEIVED ###")
    await websocket_updater(hands_played.id, json.dumps(game_update_data.dict(), default=str))
    await start_game(hands_played_id)
    return True


async def player_hit(hands_played_id: str) -> HandsPlayed:
    """
    Processes a 'hit' action for the player.

    Args:
        hands_played_id (str): The ID of the hands played record.

    Returns:
        HandsPlayed: The updated hands played record.

    Raises:
        ValueError: If the hands played ID is invalid or game state is incorrect.
    """
    hands_played = await get_hands_played_by_id(hands_played_id)
    if not hands_played:
        raise ValueError("Invalid hands_played_id.")

    if not hands_played.paid:
        raise ValueError("Cannot play an unpaid hand.")

    if hands_played.status != HandStatus.IN_PROGRESS:
        raise ValueError("Game is not in progress.")

    # Check if the game has started properly (shoe exists and hands are dealt)
    if not hands_played.shoe or not hands_played.player_hand or not hands_played.dealer_hand:
        # If the game hasn't started properly yet, start it first
        await start_game(hands_played_id)
        hands_played = await get_hands_played_by_id(hands_played_id)
        if not hands_played:
            raise ValueError("Failed to retrieve hands_played after starting game.")

    if not hands_played.shoe or not hands_played.player_hand:
        raise ValueError("Game has not been started correctly.")

    deck = Deck(cards=[Card.from_dict(c) for c in json.loads(hands_played.shoe)])
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

        # For dealer wins, payout is 0
        hands_played.payout_amount = 0
    elif hands_played.player_score == 21:
        # Player got 21, automatically stand and resolve dealer turn
        hands_played = await resolve_dealer_turn(hands_played)
    else:
        # Game continues
        hands_played.status = HandStatus.IN_PROGRESS

    await update_hands_played(hands_played)
    # Send game update without sensitive data while the game is ongoing
    game_update_data = GameUpdateData.from_hands_played(
        hands_played, include_sensitive=hands_played.status == HandStatus.COMPLETED
    )
    logger.debug("### WEBSOCKET UPDATE PLAYER_HIT ###")
    await websocket_updater(hands_played.id, json.dumps(game_update_data.dict(), default=str))
    return hands_played


async def player_stand(hands_played_id: str) -> HandsPlayed:
    """
    Processes a 'stand' action for the player.

    Args:
        hands_played_id (str): The ID of the hands played record.

    Returns:
        HandsPlayed: The updated hands played record.

    Raises:
        ValueError: If the hands played ID is invalid or game state is incorrect.
    """
    hands_played = await get_hands_played_by_id(hands_played_id)
    if not hands_played:
        raise ValueError("Invalid hands_played_id.")

    if not hands_played.paid:
        raise ValueError("Cannot play an unpaid hand.")

    if hands_played.status != HandStatus.IN_PROGRESS:
        raise ValueError("Game is not in progress.")

    # Check if the game has started properly (shoe exists and hands are dealt)
    if not hands_played.shoe or not hands_played.player_hand or not hands_played.dealer_hand:
        # If the game hasn't started properly yet, start it first
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
    hands_played = await update_hands_played(hands_played)

    # Send game update - include sensitive data if the game is completed
    include_sensitive = hands_played.status == HandStatus.COMPLETED
    game_update_data = GameUpdateData.from_hands_played(hands_played, include_sensitive=include_sensitive)
    logger.debug("### WEBSOCKET UPDATE PLAYER_STAND ###")
    await websocket_updater(hands_played.id, json.dumps(game_update_data.dict(), default=str))
    return hands_played


async def resolve_dealer_turn(hands_played: HandsPlayed) -> HandsPlayed:
    """Resolve the dealer's turn and determine the game outcome."""
    if not hands_played.shoe or not hands_played.dealer_hand:
        raise ValueError("Game has not been started correctly.")

    deck = Deck(cards=[Card.from_dict(c) for c in json.loads(hands_played.shoe)])
    dealer_hand = [Card.from_dict(c) for c in json.loads(hands_played.dealer_hand)]
    dealer_hand = [card for card in dealer_hand if card.rank != "Hidden" and card.suit != "Hidden"]

    dealer = await get_dealers_by_id(hands_played.dealers_id)
    if not dealer:
        raise ValueError("Invalid dealer ID.")

    dealer_hand = _dealer_draw(dealer_hand, deck, dealer)

    hands_played.dealer_hand = json.dumps([card.to_dict() for card in dealer_hand])
    hands_played.dealer_score = get_hand_value([card for card in dealer_hand if card is not None])
    hands_played.shoe = json.dumps([card.to_dict() for card in deck.cards])

    if hands_played.player_score is None or hands_played.dealer_score is None:
        raise ValueError("Player or dealer score not set.")

    hands_played.outcome = _determine_outcome(hands_played.player_score, hands_played.dealer_score)
    hands_played.status = HandStatus.COMPLETED
    hands_played.ended_at = datetime.now(timezone.utc)

    await _calculate_and_store_payout(hands_played, dealer)
    hands_played = await update_hands_played(hands_played)

    if hands_played.outcome in [HandOutcome.PLAYER_WINS, HandOutcome.PUSH] and hands_played.lnaddress:
        await process_payout(hands_played)
        updated_hands_played = await get_hands_played_by_id(hands_played.id)
        return updated_hands_played or hands_played

    return hands_played


def _dealer_draw(dealer_hand: list[Card], deck: Deck, dealer: Dealers) -> list[Card]:
    while True:
        filtered_hand = [card for card in dealer_hand if card is not None]
        score = get_hand_value(filtered_hand)
        should_hit = score < 17

        if dealer.hit_soft_17 and score == 17:
            aces = [card for card in filtered_hand if card.rank == "A"]
            non_ace_total = sum(card.value for card in filtered_hand if card.rank != "A")
            if aces and non_ace_total == 6:
                should_hit = True

        if not should_hit:
            break

        new_card = deck.deal()
        if not new_card:
            break
        dealer_hand.append(new_card)
    return dealer_hand


def _determine_outcome(player_score: int, dealer_score: int) -> HandOutcome:
    if dealer_score > 21:
        return HandOutcome.PLAYER_WINS
    if player_score > dealer_score:
        return HandOutcome.PLAYER_WINS
    if player_score < dealer_score:
        return HandOutcome.DEALER_WINS
    return HandOutcome.PUSH


async def _calculate_and_store_payout(hands_played: HandsPlayed, dealer: Dealers):
    potential_payout = _calculate_payout_amount(hands_played, dealer)
    wallet = await get_wallet(dealer.wallet_id)
    user_id = wallet.user if wallet else None
    if user_id:
        settings = await get_or_create_blackjack_settings(user_id)
        rake_percentage = settings.rake if settings else 0
        if hands_played.outcome in [HandOutcome.PLAYER_WINS, HandOutcome.PUSH]:
            rake_amount = _calculate_rake_amount(hands_played, potential_payout, rake_percentage)
            hands_played.payout_amount = potential_payout - rake_amount
        else:
            hands_played.payout_amount = 0


async def process_payout(hands_played: HandsPlayed) -> None:
    """Process the payout for winning hands."""
    if hands_played.payout_sent:
        logger.warning(f"Payout already sent for hands_played_id {hands_played.id}")
        return

    payout_claimed = False
    try:
        dealer = await get_dealers_by_id(hands_played.dealers_id)
        if not dealer or not hands_played.lnaddress:
            return

        if not await claim_hands_played_payout(hands_played.id):
            logger.warning(f"Payout already claimed for hands_played_id {hands_played.id}")
            return
        payout_claimed = True

        wallet = await get_wallet(dealer.wallet_id)
        user_id = wallet.user if wallet else None
        if not user_id:
            await reset_hands_played_payout_claim(hands_played.id)
            payout_claimed = False
            return

        payout_amount = _calculate_payout_amount(hands_played, dealer)
        settings = await get_or_create_blackjack_settings(user_id)
        rake_percentage = settings.rake if settings else 0

        if not hands_played.outcome:
            await reset_hands_played_payout_claim(hands_played.id)
            payout_claimed = False
            return

        final_payout, rake_amount = _calculate_final_payout(hands_played, payout_amount, rake_percentage)

        if final_payout <= 0:
            await reset_hands_played_payout_claim(hands_played.id)
            payout_claimed = False
            return

        payment_request = await get_pr_from_lnurl(hands_played.lnaddress, int(final_payout * 1000))
        if payment_request:
            await pay_invoice(
                payment_request=payment_request,
                wallet_id=dealer.wallet_id,
                max_sat=final_payout,
                description=f"Blackjack payout: {hands_played.id}",
                extra={"tag": "blackjack_payout", "hands_played_id": hands_played.id},
            )
            await _handle_rake_transfer(hands_played, dealer, settings, rake_amount)
            hands_played.payout_sent = True
            hands_played.payout_amount = final_payout
            await update_hands_played(hands_played)
        else:
            await reset_hands_played_payout_claim(hands_played.id)
            payout_claimed = False

    except Exception as exc:
        if payout_claimed:
            await reset_hands_played_payout_claim(hands_played.id)
        logger.exception(f"Error payout for {hands_played.id}: {type(exc).__name__}: {exc!s}")


def _calculate_final_payout(hands_played: HandsPlayed, payout_amount: int, rake_percentage: float) -> tuple[int, int]:
    if hands_played.outcome in [HandOutcome.PLAYER_WINS, HandOutcome.PUSH]:
        rake_amount = _calculate_rake_amount(hands_played, payout_amount, rake_percentage)

        return payout_amount - rake_amount, rake_amount

    return 0, 0


def _calculate_rake_amount(hands_played: HandsPlayed, payout_amount: int, rake_percentage: float) -> int:
    profit = max(payout_amount - hands_played.bet_amount, 0)
    return int(profit * (rake_percentage / 100))


async def _handle_rake_transfer(hands_played: HandsPlayed, dealer: Dealers, settings, rake_amount: int):
    if rake_amount > 0 and settings.rake_wallet_id:
        try:
            rake_invoice = await create_invoice(
                wallet_id=settings.rake_wallet_id,
                amount=rake_amount,
                memo=f"Rake for Blackjack Hand {hands_played.id}",
                extra={"tag": "blackjack_rake", "hands_played_id": hands_played.id},
            )
            await pay_invoice(
                payment_request=rake_invoice.bolt11,
                wallet_id=dealer.wallet_id,
                max_sat=rake_amount,
                description=f"Rake payment for hand {hands_played.id}",
                extra={
                    "tag": "blackjack_rake_payment",
                    "hands_played_id": hands_played.id,
                },
            )
        except Exception as e:
            logger.error(f"Failed to pay rake for hand {hands_played.id}: {e}")


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
                return hands_played.bet_amount + int(hands_played.bet_amount * payout_multiplier)
            except ValueError:
                raise ValueError("Invalid blackjack payout values") from None
        else:
            # Regular win (1:1)
            return hands_played.bet_amount * 2
    elif hands_played.outcome == HandOutcome.PUSH:
        # Push means return original bet
        return hands_played.bet_amount
    return 0
