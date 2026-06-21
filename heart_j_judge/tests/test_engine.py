import os
import random
from unittest.mock import Mock, patch

from ai.llm_client import LLMClient, parse_ai_response
from ai.prompts import build_player_prompt
from controllers.ai import AIController
from controllers.human import HumanController
from controllers.mock import MockController
from game.engine import GameEngine
from game.models import GameConfig, Player
from game.roles import ControllerType, Role
from main import create_controllers


def test_engine_can_be_initialized() -> None:
    engine = GameEngine(GameConfig(debug=True))

    assert engine.config.debug is True
    assert engine.state.debug is True


def test_create_players_creates_six_players_by_default() -> None:
    engine = GameEngine(GameConfig())

    players = engine.create_players()

    assert len(players) == 6
    assert engine.state.players == players


def test_create_players_assigns_sequential_ids() -> None:
    engine = GameEngine(GameConfig())

    players = engine.create_players()

    assert [player.id for player in players] == [1, 2, 3, 4, 5, 6]


def test_create_players_assigns_expected_role_counts() -> None:
    engine = GameEngine(GameConfig())

    players = engine.create_players()
    role_counts = {role: 0 for role in Role}
    for player in players:
        role_counts[player.role] += 1

    assert role_counts[Role.HEART_J] == 1
    assert role_counts[Role.TRAITOR] == 1
    assert role_counts[Role.PRISONER] == 4


def test_create_players_marks_all_players_alive_by_default() -> None:
    engine = GameEngine(GameConfig())

    players = engine.create_players()

    assert all(player.alive for player in players)


def test_create_players_raises_when_role_counts_do_not_match_player_count() -> None:
    engine = GameEngine(
        GameConfig(player_count=6, heart_j_count=1, traitor_count=1, prisoner_count=3)
    )

    try:
        engine.create_players()
    except ValueError as exc:
        assert str(exc) == "Role counts must match player_count."
    else:
        raise AssertionError("Expected ValueError for mismatched role counts.")


def test_create_players_is_reproducible_with_same_seed() -> None:
    engine_one = GameEngine(GameConfig(seed=7))
    engine_two = GameEngine(GameConfig(seed=7))

    players_one = engine_one.create_players()
    players_two = engine_two.create_players()

    assert [player.role for player in players_one] == [
        player.role for player in players_two
    ]


def test_deal_action_cards_gives_each_player_one_observe_card() -> None:
    engine = GameEngine(GameConfig())
    engine.create_players()

    players = engine.deal_action_cards()

    assert all(player.action_card is not None for player in players)
    assert all(player.action_card.name == "observe" for player in players if player.action_card is not None)
    assert all(player.action_card.used is False for player in players if player.action_card is not None)


def test_deal_action_cards_raises_when_players_not_created() -> None:
    engine = GameEngine(GameConfig())

    try:
        engine.deal_action_cards()
    except ValueError as exc:
        assert str(exc) == "Players must be created before dealing action cards."
    else:
        raise AssertionError("Expected ValueError when dealing cards before creating players.")


def build_engine_with_players(round_no: int = 1, max_round: int = 4) -> GameEngine:
    engine = GameEngine(GameConfig(max_round=max_round))
    engine.state.round_no = round_no
    engine.state.players = [
        Player(id=1, role=Role.HEART_J, controller_type=ControllerType.HUMAN),
        Player(id=2, role=Role.TRAITOR, controller_type=ControllerType.AI),
        Player(id=3, role=Role.PRISONER, controller_type=ControllerType.MOCK),
        Player(id=4, role=Role.PRISONER, controller_type=ControllerType.MOCK),
        Player(id=5, role=Role.PRISONER, controller_type=ControllerType.MOCK),
        Player(id=6, role=Role.PRISONER, controller_type=ControllerType.MOCK),
    ]
    return engine


def test_check_winner_returns_prisoners_when_heart_j_is_dead() -> None:
    engine = build_engine_with_players()
    engine.state.players[0].alive = False

    assert engine.check_winner() == "prisoners"


def test_use_observe_card_returns_true_for_heart_j() -> None:
    engine = build_engine_with_players()
    engine.deal_action_cards()

    result = engine.use_observe_card(2, 1)

    assert result == {"target_id": 1, "is_heart_j_camp": True}


def test_use_observe_card_returns_true_for_traitor() -> None:
    engine = build_engine_with_players()
    engine.deal_action_cards()

    result = engine.use_observe_card(1, 2)

    assert result == {"target_id": 2, "is_heart_j_camp": True}


def test_use_observe_card_returns_false_for_prisoner() -> None:
    engine = build_engine_with_players()
    engine.deal_action_cards()

    result = engine.use_observe_card(1, 3)

    assert result == {"target_id": 3, "is_heart_j_camp": False}


def test_use_observe_card_marks_card_as_used() -> None:
    engine = build_engine_with_players()
    engine.deal_action_cards()

    engine.use_observe_card(1, 3)

    assert engine.state.players[0].action_card is not None
    assert engine.state.players[0].action_card.used is True


def test_use_observe_card_raises_when_reused() -> None:
    engine = build_engine_with_players()
    engine.deal_action_cards()
    engine.use_observe_card(1, 3)

    try:
        engine.use_observe_card(1, 2)
    except ValueError as exc:
        assert str(exc) == "Player 1 has already used the observe card."
    else:
        raise AssertionError("Expected ValueError for reused observe card.")


def test_dead_player_cannot_use_observe_card() -> None:
    engine = build_engine_with_players()
    engine.deal_action_cards()
    engine.eliminate_player(1)

    try:
        engine.use_observe_card(1, 2)
    except ValueError as exc:
        assert str(exc) == "Player 1 is not alive."
    else:
        raise AssertionError("Expected ValueError for dead player observe card usage.")


def test_use_observe_card_raises_for_missing_target() -> None:
    engine = build_engine_with_players()
    engine.deal_action_cards()

    try:
        engine.use_observe_card(1, 99)
    except ValueError as exc:
        assert str(exc) == "Target 99 does not exist."
    else:
        raise AssertionError("Expected ValueError for missing observe target.")


def test_check_winner_returns_heart_j_when_max_round_reached() -> None:
    engine = build_engine_with_players(round_no=4, max_round=4)

    assert engine.check_winner() == "heart_j"


def test_check_winner_returns_heart_j_when_alive_count_is_three_or_less() -> None:
    engine = build_engine_with_players()
    engine.state.players[3].alive = False
    engine.state.players[4].alive = False
    engine.state.players[5].alive = False

    assert engine.check_winner() == "heart_j"


def test_check_winner_returns_none_when_no_win_condition_is_met() -> None:
    engine = build_engine_with_players(round_no=2, max_round=4)

    assert engine.check_winner() is None


def test_eliminate_player_returns_eliminated_player() -> None:
    engine = build_engine_with_players(round_no=2)

    eliminated_player = engine.eliminate_player(3)

    assert eliminated_player.id == 3


def test_eliminate_player_marks_player_as_dead() -> None:
    engine = build_engine_with_players(round_no=2)

    engine.eliminate_player(3)

    assert engine.state.players[2].alive is False


def test_eliminate_player_writes_elimination_record() -> None:
    engine = build_engine_with_players(round_no=2)

    engine.eliminate_player(3)

    assert len(engine.state.elimination_history) == 1
    record = engine.state.elimination_history[0]
    assert record.round_no == 2
    assert record.player_id == 3
    assert record.by_tie_break is False


def test_eliminate_player_raises_for_missing_player() -> None:
    engine = build_engine_with_players()

    try:
        engine.eliminate_player(99)
    except ValueError as exc:
        assert str(exc) == "Player 99 does not exist."
    else:
        raise AssertionError("Expected ValueError for missing player.")


def test_eliminate_player_raises_for_already_eliminated_player() -> None:
    engine = build_engine_with_players()
    engine.eliminate_player(3)

    try:
        engine.eliminate_player(3)
    except ValueError as exc:
        assert str(exc) == "Player 3 is already eliminated."
    else:
        raise AssertionError("Expected ValueError for already eliminated player.")


def test_eliminate_player_records_tie_break_flag() -> None:
    engine = build_engine_with_players(round_no=3)

    engine.eliminate_player(4, by_tie_break=True)

    record = engine.state.elimination_history[0]
    assert record.round_no == 3
    assert record.player_id == 4
    assert record.by_tie_break is True


def test_record_speech_succeeds_for_alive_player() -> None:
    engine = build_engine_with_players(round_no=2)

    record = engine.record_speech(1, "I am speaking.")

    assert record.round_no == 2
    assert record.player_id == 1
    assert record.speech == "I am speaking."
    assert engine.state.speech_history[0] == record


def test_record_speech_strips_whitespace() -> None:
    engine = build_engine_with_players()

    record = engine.record_speech(2, "  hello world  ")

    assert record.speech == "hello world"


def test_record_speech_raises_for_empty_speech() -> None:
    engine = build_engine_with_players()

    try:
        engine.record_speech(1, "   ")
    except ValueError as exc:
        assert str(exc) == "Speech cannot be empty."
    else:
        raise AssertionError("Expected ValueError for empty speech.")


def test_record_speech_raises_for_dead_player() -> None:
    engine = build_engine_with_players()
    engine.eliminate_player(2)

    try:
        engine.record_speech(2, "I should not speak.")
    except ValueError as exc:
        assert str(exc) == "Player 2 is not alive."
    else:
        raise AssertionError("Expected ValueError for dead player speech.")


def test_record_speech_raises_for_missing_player() -> None:
    engine = build_engine_with_players()

    try:
        engine.record_speech(99, "Hello")
    except ValueError as exc:
        assert str(exc) == "Player 99 does not exist."
    else:
        raise AssertionError("Expected ValueError for missing player speech.")


def test_record_vote_succeeds_for_valid_vote() -> None:
    engine = build_engine_with_players(round_no=3)

    record = engine.record_vote(1, 2)

    assert record.round_no == 3
    assert record.voter_id == 1
    assert record.target_id == 2
    assert engine.state.vote_history[0] == record


def test_record_vote_preserves_reason() -> None:
    engine = build_engine_with_players()

    record = engine.record_vote(1, 2, reason="suspicious behavior")

    assert record.reason == "suspicious behavior"


def test_record_vote_raises_for_invalid_vote() -> None:
    engine = build_engine_with_players()

    try:
        engine.record_vote(1, 1)
    except ValueError as exc:
        assert str(exc) == "Voter cannot vote for self."
    else:
        raise AssertionError("Expected ValueError for invalid vote.")


def test_resolve_current_round_votes_eliminates_highest_vote_target() -> None:
    engine = build_engine_with_players(round_no=2)
    engine.record_vote(1, 3)
    engine.record_vote(2, 3)
    engine.record_vote(4, 5)

    eliminated_player = engine.resolve_current_round_votes()

    assert eliminated_player is not None
    assert eliminated_player.id == 3
    assert engine.state.players[2].alive is False


def test_resolve_current_round_votes_only_counts_current_round() -> None:
    engine = build_engine_with_players(round_no=1)
    engine.record_vote(1, 4)
    engine.record_vote(2, 4)
    engine.state.round_no = 2
    engine.record_vote(1, 3)
    engine.record_vote(2, 3)
    engine.record_vote(4, 5)

    eliminated_player = engine.resolve_current_round_votes()

    assert eliminated_player is not None
    assert eliminated_player.id == 3
    assert engine.state.players[2].alive is False
    assert engine.state.players[3].alive is True


def test_resolve_current_round_votes_returns_none_when_no_votes_exist() -> None:
    engine = build_engine_with_players(round_no=3)

    eliminated_player = engine.resolve_current_round_votes()

    assert eliminated_player is None
    assert engine.state.elimination_history == []


def test_resolve_current_round_votes_tie_eliminates_from_top_targets() -> None:
    engine = build_engine_with_players(round_no=2, max_round=4)
    engine.config.seed = 0
    engine.record_vote(1, 3)
    engine.record_vote(2, 3)
    engine.record_vote(4, 5)
    engine.record_vote(6, 5)

    eliminated_player = engine.resolve_current_round_votes()

    assert eliminated_player is not None
    assert eliminated_player.id in [3, 5]


def test_resolve_current_round_votes_tie_records_tie_break_flag() -> None:
    engine = build_engine_with_players(round_no=2)
    engine.config.seed = 0
    engine.record_vote(1, 3)
    engine.record_vote(2, 3)
    engine.record_vote(4, 5)
    engine.record_vote(6, 5)

    engine.resolve_current_round_votes()

    assert engine.state.elimination_history[0].by_tie_break is True


def test_resolve_current_round_votes_non_tie_records_false_tie_break_flag() -> None:
    engine = build_engine_with_players(round_no=2)
    engine.record_vote(1, 3)
    engine.record_vote(2, 3)
    engine.record_vote(4, 5)

    engine.resolve_current_round_votes()

    assert engine.state.elimination_history[0].by_tie_break is False


def test_advance_round_increments_round_number() -> None:
    engine = build_engine_with_players(round_no=2)

    engine.advance_round()

    assert engine.state.round_no == 3


def test_advance_round_returns_new_round_number() -> None:
    engine = build_engine_with_players(round_no=1)

    new_round_no = engine.advance_round()

    assert new_round_no == 2


def test_advance_round_raises_when_game_is_over() -> None:
    engine = build_engine_with_players(round_no=2)
    engine.state.game_over = True
    engine.state.winner = "heart_j"

    try:
        engine.advance_round()
    except ValueError as exc:
        assert str(exc) == "Cannot advance round after game is over."
    else:
        raise AssertionError("Expected ValueError when advancing after game over.")


def test_public_view_does_not_include_role_information() -> None:
    engine = build_engine_with_players(round_no=2)
    engine.record_speech(1, "hello")
    engine.record_vote(1, 2, reason="test")
    engine.eliminate_player(3)

    public_view = engine.get_public_view()

    assert public_view.round_no == 2
    assert public_view.alive_player_ids == [1, 2, 4, 5, 6]
    assert public_view.speech_history == engine.state.speech_history
    assert public_view.vote_history == engine.state.vote_history
    assert public_view.elimination_history == engine.state.elimination_history
    assert not hasattr(public_view, "role")
    assert not hasattr(public_view, "winner")
    assert not hasattr(public_view, "players")


def test_player_view_includes_own_role() -> None:
    engine = build_engine_with_players()

    player_view = engine.get_player_view(2)

    assert player_view.player_id == 2
    assert player_view.role is Role.TRAITOR


def test_player_view_does_not_include_other_player_roles() -> None:
    engine = build_engine_with_players()

    player_view = engine.get_player_view(1)

    assert not hasattr(player_view.public_view, "players")
    assert not hasattr(player_view.public_view, "roles")
    assert not hasattr(player_view.public_view, "role")


def test_get_player_view_raises_for_missing_player() -> None:
    engine = build_engine_with_players()

    try:
        engine.get_player_view(99)
    except ValueError as exc:
        assert str(exc) == "Player 99 does not exist."
    else:
        raise AssertionError("Expected ValueError for missing player view.")


def test_mock_controller_speak_returns_non_empty_string() -> None:
    engine = build_engine_with_players()
    controller = MockController()

    speech = controller.speak(engine.get_player_view(1))

    assert isinstance(speech, str)
    assert speech.strip() != ""


def test_mock_controller_vote_does_not_vote_for_self() -> None:
    engine = build_engine_with_players()
    controller = MockController(random.Random(0))

    target_id = controller.vote(engine.get_player_view(1))

    assert target_id != 1


def test_mock_controller_vote_targets_alive_player() -> None:
    engine = build_engine_with_players()
    engine.eliminate_player(3)
    engine.eliminate_player(4)
    controller = MockController(random.Random(1))

    target_id = controller.vote(engine.get_player_view(1))

    assert target_id in engine.get_public_view().alive_player_ids


def test_mock_controller_vote_raises_when_no_legal_targets_exist() -> None:
    engine = build_engine_with_players()
    for player in engine.state.players[1:]:
        engine.eliminate_player(player.id)
    controller = MockController()

    try:
        controller.vote(engine.get_player_view(1))
    except ValueError as exc:
        assert str(exc) == "No legal vote targets available."
    else:
        raise AssertionError("Expected ValueError when no legal targets exist.")


def build_mock_controllers_for_alive_players(engine: GameEngine) -> dict[int, MockController]:
    return {
        player.id: MockController(random.Random(player.id))
        for player in engine.state.players
        if player.alive
    }


def test_run_round_with_controllers_records_speech_for_all_alive_players() -> None:
    engine = build_engine_with_players(round_no=1)
    controllers = build_mock_controllers_for_alive_players(engine)
    alive_count = len([player for player in engine.state.players if player.alive])

    engine.run_round_with_controllers(controllers)

    current_round_speeches = [
        record for record in engine.state.speech_history if record.round_no == 1
    ]
    assert len(current_round_speeches) == alive_count


def test_run_round_with_controllers_records_votes_for_all_alive_players() -> None:
    engine = build_engine_with_players(round_no=1)
    controllers = build_mock_controllers_for_alive_players(engine)
    alive_count = len([player for player in engine.state.players if player.alive])

    engine.run_round_with_controllers(controllers)

    current_round_votes = [
        record for record in engine.state.vote_history if record.round_no == 1
    ]
    assert len(current_round_votes) == alive_count


def test_run_round_with_controllers_eliminates_one_player() -> None:
    engine = build_engine_with_players(round_no=1)
    controllers = build_mock_controllers_for_alive_players(engine)

    result = engine.run_round_with_controllers(controllers)

    assert result["eliminated"] is not None
    assert len(engine.state.elimination_history) == 1


def test_run_round_with_controllers_eliminated_player_is_not_alive() -> None:
    engine = build_engine_with_players(round_no=1)
    controllers = build_mock_controllers_for_alive_players(engine)

    result = engine.run_round_with_controllers(controllers)
    eliminated_player = result["eliminated"]

    assert eliminated_player is not None
    assert eliminated_player.alive is False


def test_run_round_with_controllers_advances_round_when_no_winner() -> None:
    engine = build_engine_with_players(round_no=1, max_round=4)
    controllers = build_mock_controllers_for_alive_players(engine)

    result = engine.run_round_with_controllers(controllers)

    assert result["winner"] is None
    assert result["game_over"] is False
    assert result["round_no"] == 2
    assert engine.state.round_no == 2


def test_run_round_with_controllers_sets_game_over_without_advancing_on_winner() -> None:
    engine = build_engine_with_players(round_no=4, max_round=4)
    controllers = build_mock_controllers_for_alive_players(engine)

    result = engine.run_round_with_controllers(controllers)

    assert result["winner"] == "heart_j"
    assert result["game_over"] is True
    assert result["round_no"] == 4
    assert engine.state.round_no == 4


def test_run_round_with_controllers_raises_when_controller_is_missing() -> None:
    engine = build_engine_with_players(round_no=1)
    controllers = build_mock_controllers_for_alive_players(engine)
    del controllers[1]

    try:
        engine.run_round_with_controllers(controllers)
    except ValueError as exc:
        assert str(exc) == "Missing controller for player 1."
    else:
        raise AssertionError("Expected ValueError for missing controller.")


def test_mock_controllers_can_run_a_complete_game() -> None:
    engine = GameEngine(GameConfig())
    players = engine.create_players()
    controllers = {
        player.id: MockController(random.Random(player.id))
        for player in players
    }

    while not engine.state.game_over:
        engine.run_round_with_controllers(controllers)

    assert engine.state.game_over is True
    assert engine.state.winner in ["prisoners", "heart_j"]


def test_human_controller_can_be_instantiated() -> None:
    controller = HumanController()

    assert isinstance(controller, HumanController)


def test_build_player_prompt_includes_own_role() -> None:
    engine = build_engine_with_players(round_no=2)

    prompt = build_player_prompt(engine.get_player_view(2))

    assert "Your role: traitor" in prompt


def test_build_player_prompt_does_not_include_per_player_hidden_roles() -> None:
    engine = build_engine_with_players(round_no=2)

    prompt = build_player_prompt(engine.get_player_view(2))

    assert "Player 1: heart_j" not in prompt
    assert "Player 3: prisoner" not in prompt


def test_build_player_prompt_includes_legal_role_definitions() -> None:
    engine = build_engine_with_players(round_no=2)

    prompt = build_player_prompt(engine.get_player_view(2))

    assert "heart_j: 红桃J" in prompt
    assert "traitor: 内鬼" in prompt
    assert "prisoner: 囚犯" in prompt


def test_build_player_prompt_includes_forbidden_role_terms_notice() -> None:
    engine = build_engine_with_players(round_no=2)

    prompt = build_player_prompt(engine.get_player_view(2))

    assert "法官" in prompt
    assert "处刑人" in prompt
    assert "狼人" in prompt
    assert "预言家" in prompt
    assert "杀手" in prompt
    assert "警长" in prompt


def test_build_player_prompt_requires_speech_length_limit() -> None:
    engine = build_engine_with_players(round_no=2)

    prompt = build_player_prompt(engine.get_player_view(2))

    assert 'Keep "speech" to 1 to 3 sentences.' in prompt


def test_parse_ai_response_accepts_valid_json() -> None:
    response = parse_ai_response(
        '{"speech": "I suspect player 3.", "vote": 3, "reason": "behavior"}'
    )

    assert response["speech"] == "I suspect player 3."
    assert response["vote"] == 3
    assert response["reason"] == "behavior"


def test_parse_ai_response_raises_for_missing_fields() -> None:
    try:
        parse_ai_response('{"speech": "hello", "vote": 2}')
    except ValueError as exc:
        assert str(exc) == "AI response is missing required fields."
    else:
        raise AssertionError("Expected ValueError for missing AI response fields.")


def test_parse_ai_response_raises_when_vote_is_not_int() -> None:
    try:
        parse_ai_response('{"speech": "hello", "vote": "2", "reason": "test"}')
    except ValueError as exc:
        assert str(exc) == "AI response vote must be an int."
    else:
        raise AssertionError("Expected ValueError for non-int AI vote.")


def test_ai_controller_fake_response_returns_speech_and_vote() -> None:
    engine = build_engine_with_players()
    controller = AIController(
        fake_response='{"speech": "I suspect player 3.", "vote": 3, "reason": "test"}'
    )

    player_view = engine.get_player_view(2)

    assert controller.speak(player_view) == "I suspect player 3."
    assert controller.vote(player_view) == 3


def test_ai_controller_invalid_fake_response_falls_back_to_legal_vote() -> None:
    engine = build_engine_with_players()
    controller = AIController(fake_response="not-json", rng=random.Random(0))

    player_view = engine.get_player_view(2)
    speech = controller.speak(player_view)
    vote = controller.vote(player_view)

    assert speech == "我暂时没有足够信息。"
    assert vote in player_view.public_view.alive_player_ids
    assert vote != player_view.player_id


def test_ai_controller_falls_back_when_no_api_key_is_available() -> None:
    engine = build_engine_with_players()
    player_view = engine.get_player_view(2)

    with patch.dict(os.environ, {"DEEPSEEK_API_KEY": ""}, clear=False):
        controller = AIController(rng=random.Random(0))
        speech = controller.speak(player_view)
        vote = controller.vote(player_view)

    assert speech == "我暂时没有足够信息。"
    assert vote in player_view.public_view.alive_player_ids
    assert vote != player_view.player_id


def test_fake_response_has_priority_over_llm_client() -> None:
    engine = build_engine_with_players()
    player_view = engine.get_player_view(2)
    llm_client = Mock(spec=LLMClient)
    controller = AIController(
        fake_response='{"speech": "priority", "vote": 3, "reason": "fake"}',
        llm_client=llm_client,
    )

    assert controller.speak(player_view) == "priority"
    assert controller.vote(player_view) == 3
    llm_client.generate.assert_not_called()


def test_ai_controller_uses_mocked_llm_client_response() -> None:
    engine = build_engine_with_players()
    player_view = engine.get_player_view(2)
    llm_client = Mock(spec=LLMClient)
    llm_client.generate.return_value = (
        '{"speech": "LLM says player 3.", "vote": 3, "reason": "mocked"}'
    )
    controller = AIController(llm_client=llm_client)

    assert controller.speak(player_view) == "LLM says player 3."
    assert controller.vote(player_view) == 3
    llm_client.generate.assert_called_once()


def test_ai_controller_falls_back_when_llm_returns_invalid_json() -> None:
    engine = build_engine_with_players()
    player_view = engine.get_player_view(2)
    llm_client = Mock(spec=LLMClient)
    llm_client.generate.return_value = "invalid-json"
    controller = AIController(llm_client=llm_client, rng=random.Random(1))

    speech = controller.speak(player_view)
    vote = controller.vote(player_view)

    assert speech == "我暂时没有足够信息。"
    assert vote in player_view.public_view.alive_player_ids
    assert vote != player_view.player_id


def test_ai_debug_false_does_not_break_fallback() -> None:
    engine = build_engine_with_players()
    player_view = engine.get_player_view(2)
    llm_client = Mock(spec=LLMClient)
    llm_client.generate.side_effect = ValueError("no api key")

    with patch.dict(os.environ, {"AI_DEBUG": "false"}, clear=False):
        controller = AIController(llm_client=llm_client, rng=random.Random(2))
        speech = controller.speak(player_view)
        vote = controller.vote(player_view)

    assert speech == "我暂时没有足够信息。"
    assert vote in player_view.public_view.alive_player_ids
    assert vote != player_view.player_id


def test_ai_debug_true_still_falls_back_without_crashing() -> None:
    engine = build_engine_with_players()
    player_view = engine.get_player_view(2)
    llm_client = Mock(spec=LLMClient)
    llm_client.generate.return_value = "not-json"

    with patch.dict(os.environ, {"AI_DEBUG": "true"}, clear=False):
        controller = AIController(llm_client=llm_client, rng=random.Random(3))
        speech = controller.speak(player_view)
        vote = controller.vote(player_view)

    assert speech == "我暂时没有足够信息。"
    assert vote in player_view.public_view.alive_player_ids
    assert vote != player_view.player_id


def test_create_controllers_uses_mock_mode_for_players_two_to_six() -> None:
    engine = GameEngine(GameConfig())
    players = engine.create_players()

    controllers = create_controllers(players, "mock")

    assert isinstance(controllers[1], HumanController)
    for player_id in range(2, 7):
        assert isinstance(controllers[player_id], MockController)


def test_create_controllers_uses_ai_mode_for_players_two_to_six() -> None:
    engine = GameEngine(GameConfig())
    players = engine.create_players()

    controllers = create_controllers(players, "ai")

    assert isinstance(controllers[1], HumanController)
    for player_id in range(2, 7):
        assert isinstance(controllers[player_id], AIController)


def test_create_controllers_raises_for_invalid_game_mode() -> None:
    engine = GameEngine(GameConfig())
    players = engine.create_players()

    try:
        create_controllers(players, "invalid")
    except ValueError as exc:
        assert str(exc) == "Unsupported GAME_MODE: invalid"
    else:
        raise AssertionError("Expected ValueError for invalid GAME_MODE.")
