from __future__ import annotations

from dataclasses import dataclass, field
from enum import Enum
from typing import TYPE_CHECKING

from game.roles import ControllerType, Role

if TYPE_CHECKING:
    from controllers.base import Controller


@dataclass(slots=True)
class ActionCard:
    name: str
    used: bool = False


@dataclass(slots=True)
class Player:
    id: int
    role: Role
    controller_type: ControllerType
    alive: bool = True
    controller: Controller | None = None
    action_card: ActionCard | None = None


@dataclass(slots=True)
class SpeechRecord:
    round_no: int
    player_id: int
    speech: str


@dataclass(slots=True)
class VoteRecord:
    round_no: int
    voter_id: int
    target_id: int
    reason: str | None = None


@dataclass(slots=True)
class EliminationRecord:
    round_no: int
    player_id: int
    by_tie_break: bool = False


@dataclass(slots=True)
class GameConfig:
    player_count: int = 6
    heart_j_count: int = 1
    traitor_count: int = 1
    prisoner_count: int = 4
    max_round: int = 4
    debug: bool = False
    seed: int | None = None


@dataclass(slots=True)
class GameState:
    round_no: int = 1
    players: list[Player] = field(default_factory=list)
    speech_history: list[SpeechRecord] = field(default_factory=list)
    vote_history: list[VoteRecord] = field(default_factory=list)
    elimination_history: list[EliminationRecord] = field(default_factory=list)
    game_over: bool = False
    winner: str | None = None
    debug: bool = False


@dataclass(slots=True)
class PublicGameView:
    round_no: int
    alive_player_ids: list[int]
    speech_history: list[SpeechRecord]
    vote_history: list[VoteRecord]
    elimination_history: list[EliminationRecord]


@dataclass(slots=True)
class PrivatePlayerView:
    player_id: int
    role: Role
    public_view: PublicGameView


class Suit(str, Enum):
    HEART = "heart"
    DIAMOND = "diamond"
    CLUB = "club"
    SPADE = "spade"


@dataclass(slots=True)
class RoundSuitAssignment:
    round_no: int
    player_id: int
    suit: Suit


@dataclass(slots=True)
class SuitClaimRecord:
    round_no: int
    speaker_id: int
    target_id: int | None
    claim_text: str
    claimed_suit: Suit | None = None


@dataclass(slots=True)
class SuitGuessRecord:
    round_no: int
    player_id: int
    guessed_suit: Suit
    correct: bool


@dataclass(slots=True)
class PrivateChatRecord:
    round_no: int
    from_player_id: int
    to_player_id: int
    message: str


@dataclass(slots=True)
class SuitPlayerView:
    player_id: int
    role: Role
    round_no: int
    alive_player_ids: list[int]
    visible_other_suits: dict[int, Suit]
    claim_history: list[SuitClaimRecord]
    guess_history: list[SuitGuessRecord]
    private_chat_history: list[PrivateChatRecord]


@dataclass(slots=True)
class SuitGameState(GameState):
    current_suit_assignments: list[RoundSuitAssignment] = field(default_factory=list)
    suit_claim_history: list[SuitClaimRecord] = field(default_factory=list)
    suit_guess_history: list[SuitGuessRecord] = field(default_factory=list)
    private_chat_history: list[PrivateChatRecord] = field(default_factory=list)
