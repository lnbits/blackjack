import re
from collections.abc import Sequence


def is_valid_email_address(email: str) -> bool:
    email_regex = r"[A-Za-z0-9\._%+-]+@[A-Za-z0-9\.-]+\.[A-Za-z]{2,63}"
    return re.fullmatch(email_regex, email) is not None


class Card:
    def __init__(self, suit, rank):
        self.suit = suit
        self.rank = rank
        self.value = self._get_value()

    def _get_value(self):
        if self.rank in ["J", "Q", "K"]:
            return 10
        elif self.rank == "A":
            return 11
        else:
            return int(self.rank)

    def __str__(self):
        return f"{self.rank}{self.suit}"

    def to_dict(self):
        return {"suit": self.suit, "rank": self.rank, "value": self.value}

    @classmethod
    def from_dict(cls, d):
        return cls(d["suit"], d["rank"])


def get_hand_value(hand: Sequence[Card]) -> int:
    value = sum(card.value for card in hand)
    num_aces = sum(1 for card in hand if card.rank == "A")
    while value > 21 and num_aces:
        value -= 10
        num_aces -= 1
    return value
