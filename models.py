import json
import re
from datetime import datetime, timezone
from enum import Enum

from lnbits.db import FilterModel
from pydantic import BaseModel, Field, validator

from .helpers import Card, get_hand_value, is_valid_email_address


########################### Dealers ############################
class CreateDealers(BaseModel):
    name: str
    wallet_id: str
    min_bet: int
    max_bet: int
    decks: int | None = 6
    hit_soft_17: bool = True
    blackjack_payout: str = "3:2"
    active: bool = True
    created_at: datetime = Field(default_factory=lambda: datetime.now(timezone.utc))

    @validator("min_bet", "max_bet", "decks")
    def validate_positive_ints(cls, v, field):
        if v is None and field.name == "decks":
            return v
        if v <= 0:
            raise ValueError(f"{field.name} must be greater than zero")
        return v

    @validator("max_bet")
    def validate_bet_limits(cls, v, values):
        min_bet = values.get("min_bet")
        if min_bet and v < min_bet:
            raise ValueError("max_bet must be greater than or equal to min_bet")
        return v

    @validator("blackjack_payout")
    def validate_blackjack_payout(cls, v):
        # Validate that the payout is in the format "X:Y" where X and Y are numbers
        if not re.match(r"^\d+:\d+$", v):
            raise ValueError("Blackjack payout must be in the format 'X:Y' (e.g., '3:2', '6:5')")

        parts = v.split(":")
        numerator = int(parts[0])
        denominator = int(parts[1])

        if denominator == 0:
            raise ValueError("Blackjack payout denominator cannot be zero")

        if numerator < denominator:
            raise ValueError("Blackjack payout numerator should be greater than or equal to denominator")

        return v


class Dealers(CreateDealers):
    id: str
    updated_at: datetime = Field(default_factory=lambda: datetime.now(timezone.utc))


class PublicDealer(BaseModel):
    id: str
    name: str
    min_bet: int
    max_bet: int
    decks: int | None = None
    hit_soft_17: bool
    blackjack_payout: str
    active: bool

    @classmethod
    def from_db(cls, dealer: Dealers):
        return cls.parse_obj(dealer.dict())


class DealersFilters(FilterModel):
    __search_fields__ = [
        "name",
        "wallet_id",
        "min_bet",
        "max_bet",
        "decks",
        "hit_soft_17",
        "blackjack_payout",
        "active",
    ]

    __sort_fields__ = [
        "name",
        "wallet_id",
        "min_bet",
        "max_bet",
        "decks",
        "hit_soft_17",
        "blackjack_payout",
        "active",
        "created_at",
        "updated_at",
    ]

    created_at: datetime | None
    updated_at: datetime | None


class ExtensionSettings(BaseModel):
    id: str | None = None
    user_id: str
    risk_multiplier: int = 5
    rake: float = 0.0
    rake_wallet_id: str | None = None
    updated_at: datetime = Field(default_factory=lambda: datetime.now(timezone.utc))

    @validator("risk_multiplier")
    def validate_risk_multiplier(cls, v):
        if v < 1:
            raise ValueError("risk_multiplier must be greater than zero")
        return v

    @validator("rake")
    def validate_rake(cls, v):
        if v < 0 or v > 100:
            raise ValueError("rake must be between 0 and 100")
        return v


################################# Hands Played ###########################


class HandStatus(str, Enum):
    PENDING = "pending"
    IN_PROGRESS = "in_progress"
    COMPLETED = "completed"
    CANCELLED = "cancelled"


class HandOutcome(str, Enum):
    PLAYER_WINS = "player_wins"
    DEALER_WINS = "dealer_wins"
    PUSH = "push"


class CreateHandsPlayed(BaseModel):
    dealers_id: str
    status: HandStatus = HandStatus.PENDING  # initial status
    bet_amount: int
    lnaddress: str
    payment_hash: str | None = None
    player_hand: str | None = None
    dealer_hand: str | None = None
    player_score: int | None = None
    dealer_score: int | None = None
    shoe: str | None = None
    outcome: HandOutcome | None = None
    client_seed: str | None = None
    server_seed: str | None = None
    server_seed_hash: str | None = None
    payout_amount: int | None = None
    created_at: datetime = Field(default_factory=lambda: datetime.now(timezone.utc))
    updated_at: datetime = Field(default_factory=lambda: datetime.now(timezone.utc))

    @validator("lnaddress")
    def validate_lnaddress(cls, v):
        if not is_valid_email_address(v):
            raise ValueError("Invalid Lightning Address format")
        return v

    @validator("bet_amount")
    def validate_bet_amount(cls, v):
        if v <= 0:
            raise ValueError("bet_amount must be greater than zero")
        return v

    def is_player_blackjack(self) -> bool:
        if not self.player_hand:
            return False
        hand = [Card.from_dict(c) for c in json.loads(self.player_hand)]
        return len(hand) == 2 and get_hand_value(hand) == 21


class HandsPlayed(CreateHandsPlayed):
    id: str
    ended_at: datetime | None = None
    paid: bool = False
    payout_sent: bool = False


class PublicHandsPlayed(BaseModel):
    """
    Safe public view of HandsPlayed that excludes sensitive game state like the shoe.
    """

    id: str
    dealers_id: str
    status: HandStatus
    bet_amount: int
    player_hand: str | None
    dealer_hand: str | None
    player_score: int | None
    dealer_score: int | None
    outcome: HandOutcome | None
    # Exclude shoe!
    # Server seed hash is public (commitment)
    server_seed_hash: str | None = None
    # Server seed is only revealed after game
    server_seed: str | None = None

    payout_amount: int | None = None
    created_at: datetime
    updated_at: datetime
    ended_at: datetime | None
    paid: bool
    payout_sent: bool

    @classmethod
    def from_db(cls, hands_played: HandsPlayed):
        # Logic to mask dealer hole card
        dealer_hand = hands_played.dealer_hand
        if dealer_hand and hands_played.status != HandStatus.COMPLETED:
            # Hide the dealer's second card if the player is still in the game
            try:
                dealer_cards = json.loads(dealer_hand)
                if len(dealer_cards) > 1:
                    dealer_cards[1] = {"rank": "Hidden", "suit": "Hidden"}
                    dealer_hand = json.dumps(dealer_cards)
            except json.JSONDecodeError:
                pass

        data = hands_played.dict(exclude={"shoe", "lnaddress", "payment_hash", "client_seed"})
        data["dealer_hand"] = dealer_hand

        # Only include server_seed if game is completed
        if hands_played.status != HandStatus.COMPLETED:
            data["server_seed"] = None

        return cls.parse_obj(data)


class UpdateHand(BaseModel):
    status: HandStatus | None
    outcome: HandOutcome | None


class HandsPlayedPaymentRequest(BaseModel):
    hands_played_id: str
    payment_hash: str | None = None
    payment_request: str | None = None
    server_seed_hash: str | None = None


class HandsPlayedFilters(FilterModel):
    __search_fields__ = [
        "dealers_id",
        "status",
        "bet_amount",
        "lnaddress",
        "payment_hash",
        "player_hand",
        "dealer_hand",
        "player_score",
        "dealer_score",
        "shoe",
        "outcome",
        "client_seed",
        "server_seed",
        "server_seed_hash",
        "ended_at",
        "paid",
        "payout_sent",
    ]

    __sort_fields__ = [
        "dealers_id",
        "status",
        "bet_amount",
        "lnaddress",
        "payment_hash",
        "player_hand",
        "dealer_hand",
        "player_score",
        "dealer_score",
        "shoe",
        "outcome",
        "client_seed",
        "server_seed",
        "server_seed_hash",
        "ended_at",
        "paid",
        "payout_sent",
        "created_at",
        "updated_at",
    ]

    created_at: datetime | None
    updated_at: datetime | None


class GameUpdateData(BaseModel):
    """Model for sending game updates to the frontend, excluding sensitive data during game."""

    id: str
    dealers_id: str
    status: HandStatus
    bet_amount: int
    player_hand: str | None
    dealer_hand: str | None
    player_score: int | None
    dealer_score: int | None
    outcome: HandOutcome | None
    payout_amount: int | None
    payout_sent: bool = False
    created_at: datetime
    updated_at: datetime
    ended_at: datetime | None
    paid: bool = False
    # Only include these fields when the game is completed
    server_seed_hash: str | None = None
    server_seed: str | None = None

    @classmethod
    def from_hands_played(cls, hands_played: "HandsPlayed", include_sensitive: bool = False):
        """Create a GameUpdateData instance from HandsPlayed, with option to include sensitive data."""
        dealer_hand = hands_played.dealer_hand
        if dealer_hand and not include_sensitive:
            # Hide the dealer's second card if the player is still in the game
            try:
                dealer_cards = json.loads(dealer_hand)
                if len(dealer_cards) > 1:
                    dealer_cards[1] = {"rank": "Hidden", "suit": "Hidden"}
                    dealer_hand = json.dumps(dealer_cards)
            except json.JSONDecodeError:
                pass  # Should not happen if data is valid

        data = {
            "id": hands_played.id,
            "dealers_id": hands_played.dealers_id,
            "status": hands_played.status,
            "bet_amount": hands_played.bet_amount,
            "player_hand": hands_played.player_hand,
            "dealer_hand": dealer_hand,
            "player_score": hands_played.player_score,
            "dealer_score": hands_played.dealer_score,
            "outcome": hands_played.outcome,
            "payout_amount": hands_played.payout_amount,
            "payout_sent": hands_played.payout_sent,
            "created_at": hands_played.created_at,
            "updated_at": hands_played.updated_at,
            "ended_at": hands_played.ended_at,
            "paid": hands_played.paid,
            "server_seed_hash": hands_played.server_seed_hash,
        }

        # Only include sensitive data if explicitly requested (typically when game is completed)
        if include_sensitive:
            data.update(
                {
                    "server_seed": hands_played.server_seed,
                }
            )

        return cls.parse_obj(data)
