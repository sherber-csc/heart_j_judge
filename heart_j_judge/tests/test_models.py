from game.models import (
    EliminationRecord,
    GameConfig,
    GameState,
    Player,
    SpeechRecord,
    VoteRecord,
)
from game.roles import ControllerType, Role


def test_player_can_be_created() -> None:
    player = Player(id=1, role=Role.PRISONER, controller_type=ControllerType.HUMAN)

    assert player.id == 1
    assert player.role is Role.PRISONER
    assert player.controller_type is ControllerType.HUMAN
    assert player.alive is True
    assert player.controller is None


def test_game_state_defaults_are_empty() -> None:
    state = GameState()

    assert state.round_no == 1
    assert state.players == []
    assert state.speech_history == []
    assert state.vote_history == []
    assert state.elimination_history == []
    assert state.game_over is False
    assert state.winner is None


def test_records_and_config_can_be_created() -> None:
    speech = SpeechRecord(round_no=1, player_id=1, speech="test")
    vote = VoteRecord(round_no=1, voter_id=1, target_id=2, reason="guess")
    elimination = EliminationRecord(round_no=1, player_id=2)
    config = GameConfig()

    assert speech.speech == "test"
    assert vote.target_id == 2
    assert elimination.by_tie_break is False
    assert config.player_count == 6
