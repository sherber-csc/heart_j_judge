import random
from typing import Any

from game.models import (
    ActionCard,
    EliminationRecord,
    GameConfig,
    GameState,
    Player,
    PrivatePlayerView,
    PublicGameView,
    SpeechRecord,
    VoteRecord,
)
from game.roles import ControllerType, Role
from game.voting import choose_eliminated, count_votes, get_top_targets, validate_vote


class GameEngine:
    """Placeholder game engine for future rule implementation."""

    def __init__(self, config: GameConfig) -> None:
        self.config = config
        self.state = GameState(debug=config.debug)

    def create_players(self) -> list[Player]:
        role_total = (
            self.config.heart_j_count
            + self.config.traitor_count
            + self.config.prisoner_count
        )
        if role_total != self.config.player_count:
            raise ValueError("Role counts must match player_count.")

        roles = (
            [Role.HEART_J] * self.config.heart_j_count
            + [Role.TRAITOR] * self.config.traitor_count
            + [Role.PRISONER] * self.config.prisoner_count
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

    def deal_action_cards(self) -> list[Player]:
        if not self.state.players:
            raise ValueError("Players must be created before dealing action cards.")

        for player in self.state.players:
            player.action_card = ActionCard(name="observe")
        return self.state.players

    def use_observe_card(self, player_id: int, target_id: int) -> dict[str, bool | int]:
        player = next(
            (
                current_player
                for current_player in self.state.players
                if current_player.id == player_id
            ),
            None,
        )
        if player is None:
            raise ValueError(f"Player {player_id} does not exist.")
        if not player.alive:
            raise ValueError(f"Player {player_id} is not alive.")

        target = next(
            (
                current_player
                for current_player in self.state.players
                if current_player.id == target_id
            ),
            None,
        )
        if target is None:
            raise ValueError(f"Target {target_id} does not exist.")

        if player.action_card is None:
            raise ValueError(f"Player {player_id} has no action card.")
        if player.action_card.name != "observe":
            raise ValueError(f"Player {player_id} does not have an observe card.")
        if player.action_card.used:
            raise ValueError(f"Player {player_id} has already used the observe card.")

        player.action_card.used = True
        return {
            "target_id": target_id,
            "is_heart_j_camp": target.role in (Role.HEART_J, Role.TRAITOR),
        }

    def get_public_view(self) -> PublicGameView:
        return PublicGameView(
            round_no=self.state.round_no,
            alive_player_ids=[
                player.id for player in self.state.players if player.alive
            ],
            speech_history=list(self.state.speech_history),
            vote_history=list(self.state.vote_history),
            elimination_history=list(self.state.elimination_history),
        )

    def get_player_view(self, player_id: int) -> PrivatePlayerView:
        player = next(
            (
                current_player
                for current_player in self.state.players
                if current_player.id == player_id
            ),
            None,
        )
        if player is None:
            raise ValueError(f"Player {player_id} does not exist.")

        return PrivatePlayerView(
            player_id=player.id,
            role=player.role,
            public_view=self.get_public_view(),
        )

    def record_speech(self, player_id: int, speech: str) -> SpeechRecord:
        player = next(
            (
                current_player
                for current_player in self.state.players
                if current_player.id == player_id
            ),
            None,
        )
        if player is None:
            raise ValueError(f"Player {player_id} does not exist.")

        if not player.alive:
            raise ValueError(f"Player {player_id} is not alive.")

        normalized_speech = speech.strip()
        if not normalized_speech:
            raise ValueError("Speech cannot be empty.")

        record = SpeechRecord(
            round_no=self.state.round_no,
            player_id=player_id,
            speech=normalized_speech,
        )
        self.state.speech_history.append(record)
        return record

    def record_vote(
        self, voter_id: int, target_id: int, reason: str | None = None
    ) -> VoteRecord:
        validate_vote(self.state, voter_id=voter_id, target_id=target_id)

        record = VoteRecord(
            round_no=self.state.round_no,
            voter_id=voter_id,
            target_id=target_id,
            reason=reason,
        )
        self.state.vote_history.append(record)
        return record

    def run_round_with_controllers(self, controllers: dict[int, Any]) -> dict[str, Any]:
        alive_players = [player for player in self.state.players if player.alive]

        for player in alive_players:
            if player.id not in controllers:
                raise ValueError(f"Missing controller for player {player.id}.")

        for player in alive_players:
            player_view = self.get_player_view(player.id)
            speech = controllers[player.id].speak(player_view)
            self.record_speech(player.id, speech)

        for player in alive_players:
            player_view = self.get_player_view(player.id)
            target_id = controllers[player.id].vote(player_view)
            self.record_vote(player.id, target_id)

        eliminated = self.resolve_current_round_votes()
        winner = self.check_winner()
        if winner is not None:
            self.state.winner = winner
            self.state.game_over = True
        else:
            self.advance_round()

        return {
            "eliminated": eliminated,
            "winner": self.state.winner,
            "game_over": self.state.game_over,
            "round_no": self.state.round_no,
        }

    def resolve_current_round_votes(self) -> Player | None:
        current_round_votes = [
            vote for vote in self.state.vote_history if vote.round_no == self.state.round_no
        ]
        if not current_round_votes:
            return None

        vote_counts = count_votes(current_round_votes)
        top_targets = get_top_targets(vote_counts)
        rng = random.Random(self.config.seed) if self.config.seed is not None else None
        eliminated_player_id = choose_eliminated(top_targets, rng=rng)
        if eliminated_player_id is None:
            return None

        return self.eliminate_player(
            eliminated_player_id,
            by_tie_break=len(top_targets) > 1,
        )

    def advance_round(self) -> int:
        if self.state.game_over:
            raise ValueError("Cannot advance round after game is over.")

        self.state.round_no += 1
        return self.state.round_no

    def eliminate_player(
        self, player_id: int, by_tie_break: bool = False
    ) -> Player:
        player = next(
            (current_player for current_player in self.state.players if current_player.id == player_id),
            None,
        )
        if player is None:
            raise ValueError(f"Player {player_id} does not exist.")

        if not player.alive:
            raise ValueError(f"Player {player_id} is already eliminated.")

        player.alive = False
        self.state.elimination_history.append(
            EliminationRecord(
                round_no=self.state.round_no,
                player_id=player_id,
                by_tie_break=by_tie_break,
            )
        )
        return player

    def check_winner(self) -> str | None:
        heart_j_player = next(
            (player for player in self.state.players if player.role is Role.HEART_J),
            None,
        )
        if heart_j_player is None:
            return None

        if not heart_j_player.alive:
            return "prisoners"

        alive_count = sum(1 for player in self.state.players if player.alive)
        if self.state.round_no >= self.config.max_round:
            return "heart_j"

        if alive_count <= 3:
            return "heart_j"

        return None
