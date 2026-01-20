import json
import re
from datetime import datetime, timezone
from enum import Enum

from lnbits.db import FilterModel
from pydantic import BaseModel, Field, validator

from .helpers import Card, get_hand_value


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

    @validator("blackjack_payout")
    def validate_blackjack_payout(cls, v):
        # Validate that the payout is in the format "X:Y" where X and Y are numbers
        if not re.match(r"^\d+:\d+$", v):
            raise ValueError("Blackjack payout must be in the format 'X:Y' (e.g., '3:2', '6:5')")
        return v


class Dealers(CreateDealers):
    id: str
    updated_at: datetime = Field(default_factory=lambda: datetime.now(timezone.utc))


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
    payment_hash: str | None
    player_hand: str | None
    dealer_hand: str | None
    player_score: int | None
    dealer_score: int | None
    shoe: str | None
    outcome: HandOutcome | None
    client_seed: str | None
    server_seed: str | None = None
    server_seed_hash: str | None = None
    created_at: datetime = Field(default_factory=lambda: datetime.now(timezone.utc))
    updated_at: datetime = Field(default_factory=lambda: datetime.now(timezone.utc))

    def is_player_blackjack(self) -> bool:
        if not self.player_hand:
            return False
        hand = [Card.from_dict(c) for c in json.loads(self.player_hand)]
        return len(hand) == 2 and get_hand_value(hand) == 21


class HandsPlayed(CreateHandsPlayed):
    id: str
    ended_at: datetime | None
    paid: bool = False
    payout_sent: bool = False


class UpdateHand(BaseModel):
    status: HandStatus | None
    outcome: HandOutcome | None


class HandsPlayedPaymentRequest(BaseModel):
    hands_played_id: str
    payment_hash: str | None = None
    payment_request: str | None = None


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
