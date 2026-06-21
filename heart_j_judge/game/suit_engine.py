from __future__ import annotations

import random

from game.models import (
    GameConfig,
    PrivateChatRecord,
    Player,
    RoundSuitAssignment,
    Suit,
    SuitClaimRecord,
    SuitGameState,
    SuitGuessRecord,
    SuitPlayerView,
)
from game.roles import ControllerType, Role


class SuitGuessEngine:
    def __init__(self, config: GameConfig) -> None:
        self.config = config
        self.state = SuitGameState(debug=config.debug)

    def create_players(self) -> list[Player]:
        role_total = (
            self.config.heart_j_count
            + self.config.traitor_count
            + self.config.prisoner_count
        )
        if role_total != self.config.player_count:
            heart_j_count = 1
            traitor_count = 0
            prisoner_count = self.config.player_count - 1
        else:
            heart_j_count = self.config.heart_j_count
            traitor_count = self.config.traitor_count
            prisoner_count = self.config.prisoner_count

        roles = (
            [Role.HEART_J] * heart_j_count
            + [Role.TRAITOR] * traitor_count
            + [Role.PRISONER] * prisoner_count
        )
        rng = random.Random(self.config.seed)
        rng.shuffle(roles)

        players = [
            Player(
                id=index,
                role=role,
                controller_type=ControllerType.MOCK,
            )
            for index, role in enumerate(roles, start=1)
        ]
        self.state.players = players
        return players

    def assign_suits_for_round(self) -> list[RoundSuitAssignment]:
        alive_players = [player for player in self.state.players if player.alive]
        suits = list(Suit)
        rng = (
            random.Random(f"{self.config.seed}:{self.state.round_no}")
            if self.config.seed is not None
            else random.Random()
        )
        assignments = [
            RoundSuitAssignment(
                round_no=self.state.round_no,
                player_id=player.id,
                suit=rng.choice(suits),
            )
            for player in alive_players
        ]
        self.state.current_suit_assignments = assignments
        return assignments

    def get_player_view(self, player_id: int) -> SuitPlayerView:
        player = next(
            (current_player for current_player in self.state.players if current_player.id == player_id),
            None,
        )
        if player is None:
            raise ValueError(f"Player {player_id} does not exist.")
        if not player.alive:
            raise ValueError(f"Player {player_id} is not alive.")
        if not self.state.current_suit_assignments:
            raise ValueError("Suits have not been assigned for the current round.")

        assignments_by_id = {
            assignment.player_id: assignment
            for assignment in self.state.current_suit_assignments
            if assignment.round_no == self.state.round_no
        }
        if player_id not in assignments_by_id:
            raise ValueError("Suits have not been assigned for the current round.")

        alive_player_ids = [current_player.id for current_player in self.state.players if current_player.alive]
        visible_other_suits = {
            other_id: assignment.suit
            for other_id, assignment in assignments_by_id.items()
            if other_id != player_id and other_id in alive_player_ids
        }

        return SuitPlayerView(
            player_id=player.id,
            role=player.role,
            round_no=self.state.round_no,
            alive_player_ids=alive_player_ids,
            visible_other_suits=visible_other_suits,
            claim_history=list(self.state.suit_claim_history),
            guess_history=list(self.state.suit_guess_history),
            private_chat_history=[
                chat
                for chat in self.state.private_chat_history
                if chat.from_player_id == player_id or chat.to_player_id == player_id
            ],
        )

    def record_private_chat(
        self, from_player_id: int, to_player_id: int, message: str
    ) -> PrivateChatRecord:
        sender = next(
            (
                current_player
                for current_player in self.state.players
                if current_player.id == from_player_id
            ),
            None,
        )
        if sender is None:
            raise ValueError(f"Player {from_player_id} does not exist.")
        if not sender.alive:
            raise ValueError(f"Player {from_player_id} is not alive.")
        if from_player_id == to_player_id:
            raise ValueError("Players cannot private chat with themselves.")

        target = next(
            (
                current_player
                for current_player in self.state.players
                if current_player.id == to_player_id
            ),
            None,
        )
        if target is None:
            raise ValueError(f"Target {to_player_id} does not exist.")
        if not target.alive:
            raise ValueError(f"Target {to_player_id} is not alive.")

        normalized_message = message.strip()
        if not normalized_message:
            raise ValueError("Private chat message cannot be empty.")

        record = PrivateChatRecord(
            round_no=self.state.round_no,
            from_player_id=from_player_id,
            to_player_id=to_player_id,
            message=normalized_message,
        )
        self.state.private_chat_history.append(record)
        return record

    def record_claim(
        self,
        speaker_id: int,
        target_id: int | None,
        claim_text: str,
        claimed_suit: Suit | None = None,
    ) -> SuitClaimRecord:
        speaker = next(
            (current_player for current_player in self.state.players if current_player.id == speaker_id),
            None,
        )
        if speaker is None:
            raise ValueError(f"Player {speaker_id} does not exist.")
        if not speaker.alive:
            raise ValueError(f"Player {speaker_id} is not alive.")
        if target_id is not None and not any(
            current_player.id == target_id for current_player in self.state.players
        ):
            raise ValueError(f"Target {target_id} does not exist.")

        normalized_text = claim_text.strip()
        if not normalized_text:
            raise ValueError("Claim text cannot be empty.")

        record = SuitClaimRecord(
            round_no=self.state.round_no,
            speaker_id=speaker_id,
            target_id=target_id,
            claim_text=normalized_text,
            claimed_suit=claimed_suit,
        )
        self.state.suit_claim_history.append(record)
        return record

    def record_guess(self, player_id: int, guessed_suit: Suit) -> SuitGuessRecord:
        player = next(
            (current_player for current_player in self.state.players if current_player.id == player_id),
            None,
        )
        if player is None:
            raise ValueError(f"Player {player_id} does not exist.")
        if not player.alive:
            raise ValueError(f"Player {player_id} is not alive.")
        if not self.state.current_suit_assignments:
            raise ValueError("Suits have not been assigned for the current round.")
        if not isinstance(guessed_suit, Suit):
            raise ValueError("Guessed suit must be a Suit.")
        if any(
            guess.round_no == self.state.round_no and guess.player_id == player_id
            for guess in self.state.suit_guess_history
        ):
            raise ValueError(
                f"Player {player_id} has already guessed this round."
            )

        assignment = next(
            (
                current_assignment
                for current_assignment in self.state.current_suit_assignments
                if current_assignment.round_no == self.state.round_no
                and current_assignment.player_id == player_id
            ),
            None,
        )
        if assignment is None:
            raise ValueError("Suits have not been assigned for the current round.")

        record = SuitGuessRecord(
            round_no=self.state.round_no,
            player_id=player_id,
            guessed_suit=guessed_suit,
            correct=assignment.suit is guessed_suit,
        )
        self.state.suit_guess_history.append(record)
        return record

    def resolve_guesses(self) -> list[Player]:
        dead_players: list[Player] = []
        alive_players = [player for player in self.state.players if player.alive]
        guesses_by_player = {
            guess.player_id: guess
            for guess in self.state.suit_guess_history
            if guess.round_no == self.state.round_no
        }

        for player in alive_players:
            guess = guesses_by_player.get(player.id)
            if guess is None or not guess.correct:
                player.alive = False
                dead_players.append(player)

        winner = self.check_winner()
        if winner is not None:
            self.state.winner = winner
            self.state.game_over = True

        return dead_players

    def check_winner(self) -> str | None:
        heart_j_player = next(
            (player for player in self.state.players if player.role is Role.HEART_J),
            None,
        )
        if heart_j_player is None:
            return None
        if not heart_j_player.alive:
            return "prisoners"

        alive_non_heart_j_players = [
            player
            for player in self.state.players
            if player.alive and player.role is not Role.HEART_J
        ]
        if not alive_non_heart_j_players:
            return "heart_j"
        return None

    def advance_round(self) -> int:
        if self.state.game_over:
            raise ValueError("Cannot advance round after game is over.")

        self.state.round_no += 1
        self.state.current_suit_assignments = []
        return self.state.round_no
