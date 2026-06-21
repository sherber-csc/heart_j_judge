import random
from io import StringIO
from contextlib import redirect_stdout
import main_suit
from ui_suit import (
    build_player_card_data,
    build_ui_all_private_chat_recap_lines,
    build_ui_player_private_chat_lines,
    build_ui_private_chat_events,
    format_mock_personalities,
    format_suit_symbol,
    get_ui_private_chat_targets,
    initialize_ui_game,
    process_ui_human_private_chat,
    process_ui_mock_private_chat_event,
    should_show_live_private_chat_records,
    submit_ui_guess,
    submit_ui_public_speech,
)

from game.models import GameConfig, Suit
from game.roles import Role
from game.suit_engine import SuitGuessEngine
from main_suit import (
    apply_human_role_override,
    assign_mock_personalities,
    build_private_chat_events,
    classify_private_chat_truth,
    choose_claimed_suit_for_mock,
    choose_mock_guess,
    choose_mock_private_reply,
    choose_mock_public_speech,
    get_true_suit_for_round,
    has_private_chat_between_this_round,
    parse_suit_from_text,
    print_all_private_chat_history,
    print_player_private_chat_history,
    remember_round_suit_assignments,
    run_interleaved_private_chat_phase,
)


class FixedRandom:
    def __init__(self, random_values: list[float], choice_index: int = 0) -> None:
        self.random_values = list(random_values)
        self.choice_index = choice_index

    def random(self) -> float:
        if self.random_values:
            return self.random_values.pop(0)
        return 0.0

    def choice(self, items):
        return items[self.choice_index % len(items)]


class SequenceRandom:
    def __init__(
        self,
        random_values: list[float] | None = None,
        choice_indices: list[int] | None = None,
    ) -> None:
        self.random_values = list(random_values or [])
        self.choice_indices = list(choice_indices or [])

    def random(self) -> float:
        if self.random_values:
            return self.random_values.pop(0)
        return 0.0

    def choice(self, items):
        if self.choice_indices:
            index = self.choice_indices.pop(0)
            return items[index % len(items)]
        return items[0]


def build_suit_engine() -> SuitGuessEngine:
    engine = SuitGuessEngine(
        GameConfig(
            player_count=6,
            heart_j_count=1,
            traitor_count=0,
            prisoner_count=5,
            seed=7,
        )
    )
    engine.create_players()
    return engine


def test_apply_human_role_override_sets_player_one_to_heart_j() -> None:
    engine = build_suit_engine()

    players = apply_human_role_override(
        engine.state.players,
        1,
        "heart_j",
        random.Random(7),
    )

    assert next(player for player in players if player.id == 1).role is Role.HEART_J


def test_apply_human_role_override_heart_j_keeps_other_players_non_heart_j() -> None:
    engine = build_suit_engine()

    players = apply_human_role_override(
        engine.state.players,
        1,
        "heart_j",
        random.Random(7),
    )

    assert all(
        player.role is not Role.HEART_J for player in players if player.id != 1
    )


def test_apply_human_role_override_sets_player_one_to_prisoner() -> None:
    engine = build_suit_engine()

    players = apply_human_role_override(
        engine.state.players,
        1,
        "prisoner",
        random.Random(7),
    )

    assert next(player for player in players if player.id == 1).role is Role.PRISONER


def test_apply_human_role_override_prisoner_keeps_exactly_one_other_heart_j() -> None:
    engine = build_suit_engine()

    players = apply_human_role_override(
        engine.state.players,
        1,
        "prisoner",
        random.Random(7),
    )

    other_heart_j_players = [
        player for player in players if player.id != 1 and player.role is Role.HEART_J
    ]

    assert len(other_heart_j_players) == 1


def test_apply_human_role_override_raises_for_invalid_value() -> None:
    engine = build_suit_engine()

    try:
        apply_human_role_override(
            engine.state.players,
            1,
            "traitor",
            random.Random(7),
        )
    except ValueError as exc:
        assert str(exc) == "HUMAN_ROLE 只支持 heart_j / prisoner"
    else:
        raise AssertionError("Expected ValueError for invalid HUMAN_ROLE.")


def test_apply_human_role_override_does_not_force_change_when_unset() -> None:
    engine = build_suit_engine()
    original_roles = {player.id: player.role for player in engine.state.players}

    players = apply_human_role_override(
        engine.state.players,
        1,
        None,
        random.Random(7),
    )

    assert {player.id: player.role for player in players} == original_roles


def test_assign_mock_personalities_only_assigns_mock_players() -> None:
    engine = build_suit_engine()

    personalities = assign_mock_personalities(engine.state.players, 1, random.Random(7))

    assert 1 not in personalities


def test_assign_mock_personalities_assigns_every_mock_player() -> None:
    engine = build_suit_engine()

    personalities = assign_mock_personalities(engine.state.players, 1, random.Random(7))

    assert set(personalities.keys()) == {2, 3, 4, 5, 6}


def test_assign_mock_personalities_tries_to_include_deceiver() -> None:
    engine = build_suit_engine()

    personalities = assign_mock_personalities(engine.state.players, 1, random.Random(7))

    assert "deceiver" in personalities.values()


def test_create_players_creates_one_heart_j_and_rest_prisoners() -> None:
    engine = build_suit_engine()

    role_counts = {role: 0 for role in Role}
    for player in engine.state.players:
        role_counts[player.role] += 1

    assert role_counts[Role.HEART_J] == 1
    assert role_counts[Role.PRISONER] == 5
    assert role_counts[Role.TRAITOR] == 0


def test_assign_suits_for_round_only_assigns_alive_players() -> None:
    engine = build_suit_engine()
    engine.state.players[0].alive = False

    assignments = engine.assign_suits_for_round()

    assert len(assignments) == 5
    assert all(assignment.player_id != 1 for assignment in assignments)


def test_get_player_view_can_see_other_players_suits() -> None:
    engine = build_suit_engine()
    engine.assign_suits_for_round()

    player_view = engine.get_player_view(1)

    assert len(player_view.visible_other_suits) == 5
    assert 2 in player_view.visible_other_suits


def test_get_player_view_cannot_see_own_suit() -> None:
    engine = build_suit_engine()
    engine.assign_suits_for_round()

    player_view = engine.get_player_view(1)

    assert 1 not in player_view.visible_other_suits


def test_get_player_view_does_not_expose_complete_suit_table() -> None:
    engine = build_suit_engine()
    engine.assign_suits_for_round()

    player_view = engine.get_player_view(1)

    assert not hasattr(player_view, "current_suit_assignments")
    assert not hasattr(player_view, "self_suit")
    assert not hasattr(player_view, "truth_labels")
    assert not hasattr(player_view, "private_chat_truth")


def test_get_player_view_raises_when_suits_not_assigned() -> None:
    engine = build_suit_engine()

    try:
        engine.get_player_view(1)
    except ValueError as exc:
        assert str(exc) == "Suits have not been assigned for the current round."
    else:
        raise AssertionError("Expected ValueError when suits are not assigned.")


def test_record_claim_can_record_public_statement() -> None:
    engine = build_suit_engine()

    record = engine.record_claim(1, None, "I am not sure yet.")

    assert record.target_id is None
    assert record.claim_text == "I am not sure yet."


def test_record_claim_can_record_targeted_suit_statement() -> None:
    engine = build_suit_engine()

    record = engine.record_claim(1, 2, "You look like a heart.", claimed_suit=Suit.HEART)

    assert record.target_id == 2
    assert record.claimed_suit is Suit.HEART


def test_record_claim_raises_for_empty_text() -> None:
    engine = build_suit_engine()

    try:
        engine.record_claim(1, None, "   ")
    except ValueError as exc:
        assert str(exc) == "Claim text cannot be empty."
    else:
        raise AssertionError("Expected ValueError for empty claim text.")


def test_record_private_chat_can_record_private_message() -> None:
    engine = build_suit_engine()

    record = engine.record_private_chat(1, 2, "I think you are a heart.")

    assert record.from_player_id == 1
    assert record.to_player_id == 2
    assert record.message == "I think you are a heart."


def test_record_private_chat_raises_for_empty_message() -> None:
    engine = build_suit_engine()

    try:
        engine.record_private_chat(1, 2, "   ")
    except ValueError as exc:
        assert str(exc) == "Private chat message cannot be empty."
    else:
        raise AssertionError("Expected ValueError for empty private chat message.")


def test_dead_player_cannot_send_private_chat() -> None:
    engine = build_suit_engine()
    engine.state.players[0].alive = False

    try:
        engine.record_private_chat(1, 2, "hello")
    except ValueError as exc:
        assert str(exc) == "Player 1 is not alive."
    else:
        raise AssertionError("Expected ValueError for dead sender private chat.")


def test_record_private_chat_cannot_target_self() -> None:
    engine = build_suit_engine()

    try:
        engine.record_private_chat(1, 1, "hello self")
    except ValueError as exc:
        assert str(exc) == "Players cannot private chat with themselves."
    else:
        raise AssertionError("Expected ValueError for self private chat.")


def test_record_private_chat_raises_for_missing_target() -> None:
    engine = build_suit_engine()

    try:
        engine.record_private_chat(1, 99, "hello")
    except ValueError as exc:
        assert str(exc) == "Target 99 does not exist."
    else:
        raise AssertionError("Expected ValueError for missing private chat target.")


def test_parse_suit_from_text_parses_heart() -> None:
    assert parse_suit_from_text("heart") is Suit.HEART


def test_parse_suit_from_text_parses_diamond() -> None:
    assert parse_suit_from_text("diamond") is Suit.DIAMOND


def test_parse_suit_from_text_parses_club() -> None:
    assert parse_suit_from_text("club") is Suit.CLUB


def test_parse_suit_from_text_parses_spade() -> None:
    assert parse_suit_from_text("spade") is Suit.SPADE


def test_parse_suit_from_text_parses_red_heart_chinese() -> None:
    assert parse_suit_from_text("红桃") is Suit.HEART


def test_parse_suit_from_text_parses_diamond_chinese() -> None:
    assert parse_suit_from_text("方块") is Suit.DIAMOND


def test_parse_suit_from_text_parses_club_chinese() -> None:
    assert parse_suit_from_text("梅花") is Suit.CLUB


def test_parse_suit_from_text_parses_spade_chinese() -> None:
    assert parse_suit_from_text("黑桃") is Suit.SPADE


def test_parse_suit_from_text_returns_none_when_no_suit_found() -> None:
    assert parse_suit_from_text("I have no idea") is None


def test_build_private_chat_events_contains_two_human_turns() -> None:
    engine = build_suit_engine()

    events = build_private_chat_events(engine, 1, random.Random(7))

    assert sum(1 for event in events if event["type"] == "human_turn") == 2


def test_build_private_chat_events_adds_mock_turn_for_each_alive_mock() -> None:
    engine = build_suit_engine()
    engine.state.players[5].alive = False

    events = build_private_chat_events(engine, 1, random.Random(7))

    assert sum(1 for event in events if event["type"] == "mock_turn") == 4


def test_build_private_chat_events_excludes_human_turn_when_human_is_dead() -> None:
    engine = build_suit_engine()
    engine.state.players[0].alive = False

    events = build_private_chat_events(engine, 1, random.Random(7))

    assert all(event["type"] != "human_turn" for event in events)


def test_build_private_chat_events_mock_turn_speaker_ids_are_unique() -> None:
    engine = build_suit_engine()

    events = build_private_chat_events(engine, 1, random.Random(7))
    speaker_ids = [
        event["speaker_id"] for event in events if event["type"] == "mock_turn"
    ]

    assert len(speaker_ids) == len(set(speaker_ids))


def test_build_private_chat_events_mock_turns_do_not_include_human_player() -> None:
    engine = build_suit_engine()

    events = build_private_chat_events(engine, 1, random.Random(7))

    assert all(
        event.get("speaker_id") != 1
        for event in events
        if event["type"] == "mock_turn"
    )


def test_build_private_chat_events_order_can_be_shuffled_by_rng() -> None:
    engine = build_suit_engine()

    ordered_events = build_private_chat_events(
        engine,
        1,
        SequenceRandom(random_values=[0.0, 0.1, 0.2, 0.3, 0.4, 0.5, 0.6]),
    )
    reversed_events = build_private_chat_events(
        engine,
        1,
        SequenceRandom(random_values=[0.6, 0.5, 0.4, 0.3, 0.2, 0.1, 0.0]),
    )

    assert [event["type"] for event in ordered_events] != [
        event["type"] for event in reversed_events
    ]


def test_record_guess_returns_correct_true_when_guess_matches() -> None:
    engine = build_suit_engine()
    engine.assign_suits_for_round()
    remember_round_suit_assignments(engine)
    assignment = next(
        assignment
        for assignment in engine.state.current_suit_assignments
        if assignment.player_id == 1
    )

    record = engine.record_guess(1, assignment.suit)

    assert record.correct is True


def test_get_true_suit_for_round_finds_target_suit() -> None:
    engine = build_suit_engine()
    assignments = engine.assign_suits_for_round()
    remember_round_suit_assignments(engine)
    target_assignment = next(
        assignment for assignment in assignments if assignment.player_id == 2
    )

    true_suit = get_true_suit_for_round(engine, 1, 2)

    assert true_suit is target_assignment.suit


def test_get_true_suit_for_round_returns_none_when_missing() -> None:
    engine = build_suit_engine()
    engine.assign_suits_for_round()
    remember_round_suit_assignments(engine)

    assert get_true_suit_for_round(engine, 9, 2) is None


def test_classify_private_chat_truth_returns_true_for_matching_suit() -> None:
    engine = build_suit_engine()
    assignments = engine.assign_suits_for_round()
    remember_round_suit_assignments(engine)
    target_assignment = next(
        assignment for assignment in assignments if assignment.player_id == 2
    )
    chat = engine.record_private_chat(1, 2, f"Player 2，你是 {target_assignment.suit.value}。")

    assert classify_private_chat_truth(engine, chat) == "真话"


def test_classify_private_chat_truth_returns_false_for_wrong_suit() -> None:
    engine = build_suit_engine()
    assignments = engine.assign_suits_for_round()
    remember_round_suit_assignments(engine)
    target_assignment = next(
        assignment for assignment in assignments if assignment.player_id == 2
    )
    wrong_suit = next(suit for suit in Suit if suit is not target_assignment.suit)
    chat = engine.record_private_chat(1, 2, f"Player 2，你是 {wrong_suit.value}。")

    assert classify_private_chat_truth(engine, chat) == "假话"


def test_classify_private_chat_truth_returns_unknown_without_suit() -> None:
    engine = build_suit_engine()
    engine.assign_suits_for_round()
    remember_round_suit_assignments(engine)
    chat = engine.record_private_chat(1, 2, "我觉得你不可信。")

    assert classify_private_chat_truth(engine, chat) == "无法判断"


def test_classify_private_chat_truth_returns_unknown_when_true_suit_missing() -> None:
    engine = build_suit_engine()
    engine.assign_suits_for_round()
    engine.advance_round()
    chat = engine.record_private_chat(1, 2, "Player 2，你是 heart。")

    assert classify_private_chat_truth(engine, chat) == "无法判断"


def test_choose_mock_guess_prefers_latest_private_chat() -> None:
    engine = build_suit_engine()
    engine.assign_suits_for_round()
    rng = random.Random(1)
    engine.record_private_chat(1, 2, "你是 红桃")
    engine.record_private_chat(3, 2, "Actually you are 黑桃")

    guessed_suit = choose_mock_guess(engine, 2, rng)

    assert guessed_suit is Suit.SPADE


def test_choose_claimed_suit_for_mock_returns_legal_suit() -> None:
    engine = build_suit_engine()
    engine.assign_suits_for_round()

    suit = choose_claimed_suit_for_mock(engine, 2, 1, FixedRandom([0.0]))

    assert suit in list(Suit)


def test_choose_claimed_suit_for_mock_without_personalities_stays_compatible() -> None:
    engine = build_suit_engine()
    engine.assign_suits_for_round()

    suit = choose_claimed_suit_for_mock(engine, 2, 1, FixedRandom([0.0]))

    assert suit in list(Suit)


def test_choose_claimed_suit_for_mock_lie_never_returns_true_suit() -> None:
    engine = build_suit_engine()
    engine.assign_suits_for_round()
    true_suit = engine.get_player_view(2).visible_other_suits[1]

    lied_suit = choose_claimed_suit_for_mock(engine, 2, 1, FixedRandom([0.95], 0))

    assert lied_suit is not true_suit


def test_prisoner_can_tell_truth_with_controlled_rng() -> None:
    engine = build_suit_engine()
    engine.assign_suits_for_round()
    prisoner = next(player for player in engine.state.players if player.role is Role.PRISONER)
    target_id = next(other.id for other in engine.state.players if other.id != prisoner.id)
    true_suit = engine.get_player_view(prisoner.id).visible_other_suits[target_id]

    chosen_suit = choose_claimed_suit_for_mock(
        engine, prisoner.id, target_id, FixedRandom([0.1])
    )

    assert chosen_suit is true_suit


def test_deceiver_can_lie_with_controlled_rng() -> None:
    engine = build_suit_engine()
    engine.assign_suits_for_round()
    personalities = {2: "deceiver"}
    true_suit = engine.get_player_view(2).visible_other_suits[1]

    chosen_suit = choose_claimed_suit_for_mock(
        engine,
        2,
        1,
        FixedRandom([0.9], 0),
        personalities,
    )

    assert chosen_suit is not true_suit


def test_honest_can_tell_truth_with_controlled_rng() -> None:
    engine = build_suit_engine()
    engine.assign_suits_for_round()
    personalities = {2: "honest"}
    true_suit = engine.get_player_view(2).visible_other_suits[1]

    chosen_suit = choose_claimed_suit_for_mock(
        engine,
        2,
        1,
        FixedRandom([0.1], 0),
        personalities,
    )

    assert chosen_suit is true_suit


def test_heart_j_can_lie_with_controlled_rng() -> None:
    engine = build_suit_engine()
    engine.assign_suits_for_round()
    heart_j = next(player for player in engine.state.players if player.role is Role.HEART_J)
    target_id = next(other.id for other in engine.state.players if other.id != heart_j.id)
    true_suit = engine.get_player_view(heart_j.id).visible_other_suits[target_id]

    chosen_suit = choose_claimed_suit_for_mock(
        engine, heart_j.id, target_id, FixedRandom([0.9], 0)
    )

    assert chosen_suit is not true_suit


def test_heart_j_deceiver_more_easily_returns_false_suit() -> None:
    engine = build_suit_engine()
    engine.assign_suits_for_round()
    heart_j = next(player for player in engine.state.players if player.role is Role.HEART_J)
    target_id = next(other.id for other in engine.state.players if other.id != heart_j.id)
    true_suit = engine.get_player_view(heart_j.id).visible_other_suits[target_id]

    chosen_suit = choose_claimed_suit_for_mock(
        engine,
        heart_j.id,
        target_id,
        FixedRandom([0.2], 0),
        {heart_j.id: "deceiver"},
    )

    assert chosen_suit is not true_suit


def test_mock_public_speech_does_not_contain_suit_words() -> None:
    claim_text = choose_mock_public_speech(2, "deceiver", random.Random(1))

    forbidden_terms = [
        "heart",
        "diamond",
        "club",
        "spade",
        "红桃",
        "方块",
        "梅花",
        "黑桃",
    ]
    assert all(term not in claim_text.lower() for term in forbidden_terms[:4])
    assert all(term not in claim_text for term in forbidden_terms[4:])


def test_different_personalities_can_have_different_public_speech() -> None:
    honest_speech = choose_mock_public_speech(2, "honest", FixedRandom([], 0))
    cautious_speech = choose_mock_public_speech(3, "cautious", FixedRandom([], 0))

    assert honest_speech != cautious_speech


def test_run_interleaved_private_chat_phase_human_turn_records_private_chat(
    monkeypatch,
) -> None:
    engine = build_suit_engine()
    engine.assign_suits_for_round()
    monkeypatch.setattr(
        main_suit,
        "build_private_chat_events",
        lambda _engine, _human_player_id, _rng: [{"type": "human_turn"}],
    )
    inputs = iter(["2", "先聊一下"])
    monkeypatch.setattr("builtins.input", lambda _prompt="": next(inputs))

    run_interleaved_private_chat_phase(engine, 1, SequenceRandom(random_values=[0.0]))

    assert any(
        chat.from_player_id == 1
        and chat.to_player_id == 2
        and chat.message == "先聊一下"
        for chat in engine.state.private_chat_history
    )


def test_run_interleaved_private_chat_phase_records_human_reply_after_mock_message(
    monkeypatch,
) -> None:
    engine = build_suit_engine()
    engine.assign_suits_for_round()
    monkeypatch.setattr(
        main_suit,
        "build_private_chat_events",
        lambda _engine, _human_player_id, _rng: [
            {"type": "mock_turn", "speaker_id": 2}
        ],
    )
    inputs = iter(["y", "收到，我记下了"])
    monkeypatch.setattr("builtins.input", lambda _prompt="": next(inputs))

    run_interleaved_private_chat_phase(
        engine,
        1,
        SequenceRandom(random_values=[0.0], choice_indices=[0, 0]),
    )

    assert any(
        chat.from_player_id == 1
        and chat.to_player_id == 2
        and chat.message == "收到，我记下了"
        for chat in engine.state.private_chat_history
    )


def test_run_interleaved_private_chat_phase_skips_human_reply_when_player_chooses_n(
    monkeypatch,
) -> None:
    engine = build_suit_engine()
    engine.assign_suits_for_round()
    monkeypatch.setattr(
        main_suit,
        "build_private_chat_events",
        lambda _engine, _human_player_id, _rng: [
            {"type": "mock_turn", "speaker_id": 2}
        ],
    )
    inputs = iter(["n"])
    monkeypatch.setattr("builtins.input", lambda _prompt="": next(inputs))

    run_interleaved_private_chat_phase(
        engine,
        1,
        SequenceRandom(random_values=[0.0], choice_indices=[0, 0]),
    )

    assert not any(
        chat.from_player_id == 1 and chat.to_player_id == 2
        for chat in engine.state.private_chat_history
    )


def test_run_interleaved_private_chat_phase_does_not_print_mock_to_mock_content(
    monkeypatch,
    capsys,
) -> None:
    engine = build_suit_engine()
    engine.assign_suits_for_round()
    monkeypatch.setattr(
        main_suit,
        "build_private_chat_events",
        lambda _engine, _human_player_id, _rng: [
            {"type": "mock_turn", "speaker_id": 2}
        ],
    )

    run_interleaved_private_chat_phase(
        engine,
        1,
        SequenceRandom(random_values=[0.0], choice_indices=[1]),
    )

    output = capsys.readouterr().out
    assert "其他玩家正在私下交流" in output
    assert "Player 2 私聊你" not in output
    assert "Player 3，你是" not in output


def test_human_reply_does_not_reduce_human_turn_opportunities(
    monkeypatch,
    capsys,
) -> None:
    engine = build_suit_engine()
    engine.assign_suits_for_round()
    monkeypatch.setattr(
        main_suit,
        "build_private_chat_events",
        lambda _engine, _human_player_id, _rng: [
            {"type": "mock_turn", "speaker_id": 2},
            {"type": "human_turn"},
            {"type": "human_turn"},
        ],
    )
    inputs = iter(["y", "收到", "", ""])
    monkeypatch.setattr("builtins.input", lambda _prompt="": next(inputs))

    run_interleaved_private_chat_phase(
        engine,
        1,
        SequenceRandom(random_values=[0.0], choice_indices=[0, 0]),
    )

    output = capsys.readouterr().out
    assert "你还可以主动私聊 2 次。" in output
    assert "你还可以主动私聊 1 次。" in output


def test_each_mock_initiates_at_most_one_private_chat_per_round(monkeypatch) -> None:
    engine = build_suit_engine()
    engine.assign_suits_for_round()
    monkeypatch.setattr(
        main_suit,
        "build_private_chat_events",
        lambda _engine, _human_player_id, _rng: [
            {"type": "mock_turn", "speaker_id": 2},
            {"type": "mock_turn", "speaker_id": 3},
            {"type": "mock_turn", "speaker_id": 4},
            {"type": "mock_turn", "speaker_id": 5},
            {"type": "mock_turn", "speaker_id": 6},
        ],
    )

    run_interleaved_private_chat_phase(
        engine,
        1,
        SequenceRandom(
            random_values=[0.0],
            choice_indices=[1, 1, 1, 1, 1],
        ),
    )

    current_round = engine.state.round_no
    outgoing_counts: dict[int, int] = {}
    for chat in engine.state.private_chat_history:
        if chat.round_no != current_round or chat.from_player_id == 1:
            continue
        outgoing_counts[chat.from_player_id] = (
            outgoing_counts.get(chat.from_player_id, 0) + 1
        )

    assert outgoing_counts == {2: 1, 3: 1, 4: 1, 5: 1, 6: 1}


def test_dead_mock_speaker_event_is_skipped_without_error(monkeypatch) -> None:
    engine = build_suit_engine()
    engine.assign_suits_for_round()
    engine.state.players[1].alive = False
    monkeypatch.setattr(
        main_suit,
        "build_private_chat_events",
        lambda _engine, _human_player_id, _rng: [
            {"type": "mock_turn", "speaker_id": 2}
        ],
    )

    run_interleaved_private_chat_phase(
        engine,
        1,
        SequenceRandom(random_values=[0.0], choice_indices=[0]),
    )

    assert engine.state.private_chat_history == []


def test_human_turn_cannot_repeat_same_round_private_chat_target(
    monkeypatch,
    capsys,
) -> None:
    engine = build_suit_engine()
    engine.assign_suits_for_round()
    engine.record_private_chat(1, 2, "already chatted")
    engine.record_private_chat(2, 1, "reply")
    monkeypatch.setattr(
        main_suit,
        "build_private_chat_events",
        lambda _engine, _human_player_id, _rng: [{"type": "human_turn"}],
    )
    inputs = iter(["2", ""])
    monkeypatch.setattr("builtins.input", lambda _prompt="": next(inputs))

    run_interleaved_private_chat_phase(engine, 1, SequenceRandom(random_values=[0.0]))

    output = capsys.readouterr().out
    assert "本轮你已经和 Player 2 私聊过，不能重复私聊。" in output
    assert len(
        [
            chat
            for chat in engine.state.private_chat_history
            if {
                chat.from_player_id,
                chat.to_player_id,
            }
            == {1, 2}
        ]
    ) == 2


def test_mock_turn_does_not_choose_already_chatted_target(monkeypatch) -> None:
    engine = build_suit_engine()
    engine.assign_suits_for_round()
    engine.record_private_chat(1, 2, "already chatted")
    engine.record_private_chat(2, 1, "reply")
    monkeypatch.setattr(
        main_suit,
        "build_private_chat_events",
        lambda _engine, _human_player_id, _rng: [
            {"type": "mock_turn", "speaker_id": 2}
        ],
    )

    run_interleaved_private_chat_phase(
        engine,
        1,
        SequenceRandom(random_values=[0.0], choice_indices=[0]),
    )

    current_round = engine.state.round_no
    speaker_targets = [
        chat.to_player_id
        for chat in engine.state.private_chat_history
        if chat.round_no == current_round and chat.from_player_id == 2
    ]
    assert speaker_targets[0] == 1
    assert len(speaker_targets) == 2
    assert speaker_targets[1] != 1


def test_mock_turn_skips_when_no_available_targets(monkeypatch) -> None:
    engine = build_suit_engine()
    engine.assign_suits_for_round()
    for other_id in [1, 3, 4, 5, 6]:
        engine.record_private_chat(2, other_id, f"already chatted with {other_id}")
    monkeypatch.setattr(
        main_suit,
        "build_private_chat_events",
        lambda _engine, _human_player_id, _rng: [
            {"type": "mock_turn", "speaker_id": 2}
        ],
    )

    run_interleaved_private_chat_phase(
        engine,
        1,
        SequenceRandom(random_values=[0.0], choice_indices=[0]),
    )

    current_round = engine.state.round_no
    assert len(
        [
            chat
            for chat in engine.state.private_chat_history
            if chat.round_no == current_round and chat.from_player_id == 2
        ]
    ) == 5


def test_human_chatting_with_heart_j_can_receive_false_suit() -> None:
    engine = build_suit_engine()
    engine.assign_suits_for_round()
    heart_j = next(player for player in engine.state.players if player.role is Role.HEART_J)
    if heart_j.id == 1:
        heart_j = next(player for player in engine.state.players if player.role is Role.PRISONER)
    true_suit = engine.get_player_view(heart_j.id).visible_other_suits[1]

    reply = choose_mock_private_reply(engine, heart_j.id, 1, FixedRandom([0.9], 0))
    replied_suit = parse_suit_from_text(reply)

    assert replied_suit is not None
    assert replied_suit is not true_suit


def test_choose_mock_guess_uses_public_claim_when_no_private_chat() -> None:
    engine = build_suit_engine()
    engine.assign_suits_for_round()
    rng = random.Random(1)
    engine.record_claim(1, 2, "Player 2，我认为你是方块。")

    guessed_suit = choose_mock_guess(engine, 2, rng)

    assert guessed_suit is Suit.DIAMOND


def test_choose_mock_guess_returns_legal_suit_when_no_information() -> None:
    engine = build_suit_engine()
    engine.assign_suits_for_round()
    rng = random.Random(1)

    guessed_suit = choose_mock_guess(engine, 2, rng)

    assert guessed_suit in list(Suit)


def test_choose_mock_guess_with_personalities_none_stays_compatible() -> None:
    engine = build_suit_engine()
    engine.assign_suits_for_round()
    engine.record_private_chat(1, 2, "你是 红桃")

    guessed_suit = choose_mock_guess(engine, 2, random.Random(1), None)

    assert guessed_suit is Suit.HEART


def test_suspicious_personality_may_not_fully_trust_latest_private_chat() -> None:
    engine = build_suit_engine()
    engine.assign_suits_for_round()
    engine.record_private_chat(1, 2, "你是 红桃")

    guessed_suit = choose_mock_guess(
        engine,
        2,
        FixedRandom([0.9], 0),
        {2: "suspicious"},
    )

    assert guessed_suit is not Suit.HEART


def test_personality_does_not_modify_player_role() -> None:
    engine = build_suit_engine()
    original_roles = {player.id: player.role for player in engine.state.players}

    _personalities = assign_mock_personalities(engine.state.players, 1, random.Random(7))

    assert {player.id: player.role for player in engine.state.players} == original_roles


def test_print_player_private_chat_history_works_after_human_death(capsys) -> None:
    engine = build_suit_engine()
    engine.record_private_chat(1, 2, "secret one")
    engine.record_private_chat(2, 1, "secret two")
    engine.state.players[0].alive = False

    print_player_private_chat_history(engine, 1)

    output = capsys.readouterr().out
    assert "你的私聊历史:" in output
    assert "Player 1 -> Player 2: secret one" in output
    assert "Player 2 -> Player 1: secret two" in output


def test_print_player_private_chat_history_excludes_other_players_chats(capsys) -> None:
    engine = build_suit_engine()
    engine.record_private_chat(1, 2, "my chat")
    engine.record_private_chat(3, 4, "hidden chat")

    print_player_private_chat_history(engine, 1)

    output = capsys.readouterr().out
    assert "Player 1 -> Player 2: my chat" in output
    assert "Player 3 -> Player 4: hidden chat" not in output


def test_print_player_private_chat_history_does_not_show_truth_labels(capsys) -> None:
    engine = build_suit_engine()
    engine.assign_suits_for_round()
    remember_round_suit_assignments(engine)
    engine.record_private_chat(1, 2, "Player 2，你是 heart。")

    print_player_private_chat_history(engine, 1)

    output = capsys.readouterr().out
    assert "[真话]" not in output
    assert "[假话]" not in output
    assert "[无法判断]" not in output


def test_print_all_private_chat_history_prints_all_chats(capsys) -> None:
    engine = build_suit_engine()
    assignments = engine.assign_suits_for_round()
    remember_round_suit_assignments(engine)
    suit_for_2 = next(
        assignment.suit for assignment in assignments if assignment.player_id == 2
    )
    engine.record_private_chat(1, 2, f"Player 2，你是 {suit_for_2.value}。")
    engine.record_private_chat(4, 5, "second")

    print_all_private_chat_history(engine)

    output = capsys.readouterr().out
    assert "全局私聊复盘:" in output
    assert "[真话]" in output
    assert "[无法判断]" in output


def test_print_all_private_chat_history_prints_none_when_empty(capsys) -> None:
    engine = build_suit_engine()

    print_all_private_chat_history(engine)

    output = capsys.readouterr().out
    assert "全局私聊复盘:" in output
    assert "- None" in output


def test_print_all_private_chat_history_outputs_false_label(capsys) -> None:
    engine = build_suit_engine()
    assignments = engine.assign_suits_for_round()
    remember_round_suit_assignments(engine)
    suit_for_2 = next(
        assignment.suit for assignment in assignments if assignment.player_id == 2
    )
    wrong_suit = next(suit for suit in Suit if suit is not suit_for_2)
    engine.record_private_chat(1, 2, f"Player 2，你是 {wrong_suit.value}。")

    print_all_private_chat_history(engine)

    output = capsys.readouterr().out
    assert "[假话]" in output


def test_has_private_chat_between_this_round_detects_a_to_b() -> None:
    engine = build_suit_engine()
    engine.record_private_chat(1, 2, "hello")

    assert has_private_chat_between_this_round(engine, 1, 2) is True


def test_has_private_chat_between_this_round_detects_b_to_a() -> None:
    engine = build_suit_engine()
    engine.record_private_chat(2, 1, "hello")

    assert has_private_chat_between_this_round(engine, 1, 2) is True


def test_has_private_chat_between_this_round_ignores_previous_round() -> None:
    engine = build_suit_engine()
    engine.record_private_chat(1, 2, "hello")
    engine.advance_round()

    assert has_private_chat_between_this_round(engine, 1, 2) is False


def test_get_player_view_only_contains_private_chats_for_that_player() -> None:
    engine = build_suit_engine()
    engine.assign_suits_for_round()
    engine.record_private_chat(1, 2, "secret one")
    engine.record_private_chat(2, 1, "secret two")
    engine.record_private_chat(3, 4, "not yours")

    player_view = engine.get_player_view(1)

    assert len(player_view.private_chat_history) == 2
    assert all(
        chat.from_player_id == 1
        or chat.to_player_id == 1
        for chat in player_view.private_chat_history
    )


def test_get_player_view_excludes_other_players_private_chats() -> None:
    engine = build_suit_engine()
    engine.assign_suits_for_round()
    engine.record_private_chat(3, 4, "hidden chat")

    player_view = engine.get_player_view(1)

    assert all(
        not (
            chat.from_player_id == 3 and chat.to_player_id == 4
        )
        for chat in player_view.private_chat_history
    )


def test_private_chat_records_only_store_message_not_true_suit_fields() -> None:
    engine = build_suit_engine()

    record = engine.record_private_chat(1, 2, "You are heart.")

    assert hasattr(record, "message")
    assert not hasattr(record, "suit")
    assert not hasattr(record, "true_suit")


def test_record_guess_returns_correct_false_when_guess_is_wrong() -> None:
    engine = build_suit_engine()
    engine.assign_suits_for_round()
    assignment = next(
        assignment
        for assignment in engine.state.current_suit_assignments
        if assignment.player_id == 1
    )
    wrong_suit = next(suit for suit in Suit if suit is not assignment.suit)

    record = engine.record_guess(1, wrong_suit)

    assert record.correct is False


def test_record_guess_raises_when_player_guesses_twice() -> None:
    engine = build_suit_engine()
    engine.assign_suits_for_round()
    engine.record_guess(1, Suit.HEART)

    try:
        engine.record_guess(1, Suit.SPADE)
    except ValueError as exc:
        assert str(exc) == "Player 1 has already guessed this round."
    else:
        raise AssertionError("Expected ValueError for duplicate round guess.")


def test_resolve_guesses_eliminates_players_with_wrong_guesses() -> None:
    engine = build_suit_engine()
    engine.assign_suits_for_round()
    for assignment in engine.state.current_suit_assignments:
        if assignment.player_id == 1:
            wrong_suit = next(suit for suit in Suit if suit is not assignment.suit)
            engine.record_guess(1, wrong_suit)
            break

    dead_players = engine.resolve_guesses()

    assert any(player.id == 1 for player in dead_players)
    assert engine.state.players[0].alive is False


def test_resolve_guesses_eliminates_players_without_guesses() -> None:
    engine = build_suit_engine()
    engine.assign_suits_for_round()

    dead_players = engine.resolve_guesses()

    assert len(dead_players) == 6
    assert all(player.alive is False for player in engine.state.players)


def test_check_winner_returns_prisoners_when_heart_j_dies() -> None:
    engine = build_suit_engine()
    heart_j_player = next(player for player in engine.state.players if player.role is Role.HEART_J)
    heart_j_player.alive = False

    assert engine.check_winner() == "prisoners"


def test_check_winner_returns_heart_j_when_only_heart_j_is_alive() -> None:
    engine = build_suit_engine()
    heart_j_player = next(player for player in engine.state.players if player.role is Role.HEART_J)
    for player in engine.state.players:
        if player.id != heart_j_player.id:
            player.alive = False

    assert engine.check_winner() == "heart_j"


def test_advance_round_increments_round_number() -> None:
    engine = build_suit_engine()

    new_round = engine.advance_round()

    assert new_round == 2
    assert engine.state.round_no == 2


def test_advance_round_raises_when_game_is_over() -> None:
    engine = build_suit_engine()
    engine.state.game_over = True

    try:
        engine.advance_round()
    except ValueError as exc:
        assert str(exc) == "Cannot advance round after game is over."
    else:
        raise AssertionError("Expected ValueError when game is over.")


def test_build_player_card_data_human_suit_is_hidden() -> None:
    engine = build_suit_engine()
    engine.assign_suits_for_round()
    remember_round_suit_assignments(engine)
    personalities = assign_mock_personalities(engine.state.players, 1, random.Random(7))

    cards = build_player_card_data(engine, 1, personalities)
    human_card = next(card for card in cards if card["player_id"] == 1)

    assert human_card["suit"] == "???"


def test_build_player_card_data_other_alive_players_show_visible_suits() -> None:
    engine = build_suit_engine()
    engine.assign_suits_for_round()
    remember_round_suit_assignments(engine)
    personalities = assign_mock_personalities(engine.state.players, 1, random.Random(7))
    human_view = engine.get_player_view(1)

    cards = build_player_card_data(engine, 1, personalities)
    other_card = next(card for card in cards if card["player_id"] == 2)

    assert other_card["suit"] == human_view.visible_other_suits[2].value


def test_build_player_card_data_mock_role_is_unknown() -> None:
    engine = build_suit_engine()
    engine.assign_suits_for_round()
    remember_round_suit_assignments(engine)
    personalities = assign_mock_personalities(engine.state.players, 1, random.Random(7))

    cards = build_player_card_data(engine, 1, personalities)
    other_card = next(card for card in cards if card["player_id"] == 2)

    assert other_card["role"] == "unknown"


def test_build_player_card_data_human_role_is_visible() -> None:
    engine = build_suit_engine()
    engine.assign_suits_for_round()
    remember_round_suit_assignments(engine)
    personalities = assign_mock_personalities(engine.state.players, 1, random.Random(7))

    cards = build_player_card_data(engine, 1, personalities)
    human_card = next(card for card in cards if card["player_id"] == 1)
    player_one = next(player for player in engine.state.players if player.id == 1)

    assert human_card["role"] == player_one.role.value


def test_build_player_card_data_dead_player_shows_dead_status() -> None:
    engine = build_suit_engine()
    engine.assign_suits_for_round()
    remember_round_suit_assignments(engine)
    engine.state.players[1].alive = False
    personalities = assign_mock_personalities(engine.state.players, 1, random.Random(7))

    cards = build_player_card_data(engine, 1, personalities)
    dead_card = next(card for card in cards if card["player_id"] == 2)

    assert dead_card["status"] == "dead"


def test_build_player_card_data_does_not_leak_human_true_suit() -> None:
    engine = build_suit_engine()
    assignments = engine.assign_suits_for_round()
    remember_round_suit_assignments(engine)
    personalities = assign_mock_personalities(engine.state.players, 1, random.Random(7))
    human_true_suit = next(
        assignment.suit.value for assignment in assignments if assignment.player_id == 1
    )

    cards = build_player_card_data(engine, 1, personalities)
    human_card = next(card for card in cards if card["player_id"] == 1)

    assert human_card["suit"] != human_true_suit
    assert human_card["suit"] == "???"


def test_build_player_card_data_does_not_leak_mock_true_role() -> None:
    engine = build_suit_engine()
    engine.assign_suits_for_round()
    remember_round_suit_assignments(engine)
    personalities = assign_mock_personalities(engine.state.players, 1, random.Random(7))
    mock_player = next(player for player in engine.state.players if player.id == 2)

    cards = build_player_card_data(engine, 1, personalities)
    mock_card = next(card for card in cards if card["player_id"] == 2)

    assert mock_card["role"] == "unknown"
    assert mock_card["role"] != mock_player.role.value


def test_initialize_ui_game_starts_in_private_chat_phase() -> None:
    ui_state = initialize_ui_game("random", random.Random(7))

    assert ui_state["phase"] == "private_chat"
    assert ui_state["human_player_id"] == 1
    assert ui_state["private_chat_events"]


def test_build_ui_private_chat_events_keeps_mock_speaker_binding() -> None:
    engine = build_suit_engine()

    events = build_ui_private_chat_events(engine, 1, random.Random(7))
    mock_events = [event for event in events if event["type"] == "mock_turn"]

    assert all("speaker_id" in event for event in mock_events)
    assert len(mock_events) == 5


def test_get_ui_private_chat_targets_excludes_self_dead_and_previous_chat() -> None:
    engine = build_suit_engine()
    engine.assign_suits_for_round()
    engine.state.players[2].alive = False
    engine.record_private_chat(1, 2, "hello")
    engine.record_private_chat(2, 1, "reply")

    targets = get_ui_private_chat_targets(engine, 1)

    assert 1 not in targets
    assert 2 not in targets
    assert 3 not in targets


def test_process_ui_human_private_chat_records_human_and_mock_reply() -> None:
    engine = build_suit_engine()
    engine.assign_suits_for_round()

    result = process_ui_human_private_chat(
        engine,
        1,
        2,
        "我先问你一句",
        random.Random(7),
        assign_mock_personalities(engine.state.players, 1, random.Random(8)),
    )

    assert result["status"] == "sent"
    assert result["human_chat"].from_player_id == 1
    assert result["mock_reply"].from_player_id == 2


def test_process_ui_human_private_chat_rejects_empty_message() -> None:
    engine = build_suit_engine()
    engine.assign_suits_for_round()

    result = process_ui_human_private_chat(
        engine,
        1,
        2,
        "   ",
        random.Random(7),
        {},
    )

    assert result["status"] == "invalid"
    assert engine.state.private_chat_history == []


def test_process_ui_mock_private_chat_event_skips_dead_speaker() -> None:
    engine = build_suit_engine()
    engine.assign_suits_for_round()
    engine.state.players[1].alive = False

    result = process_ui_mock_private_chat_event(
        engine,
        {"type": "mock_turn", "speaker_id": 2},
        1,
        random.Random(7),
        {},
    )

    assert result["status"] == "skipped"
    assert result["reason"] == "dead_speaker"


def test_process_ui_mock_private_chat_event_returns_human_reply_prompt() -> None:
    engine = build_suit_engine()
    engine.assign_suits_for_round()

    result = process_ui_mock_private_chat_event(
        engine,
        {"type": "mock_turn", "speaker_id": 2},
        1,
        SequenceRandom(choice_indices=[0]),
        {2: "follower"},
    )

    assert result["status"] == "needs_human_reply"
    assert result["target_id"] == 1
    assert "Player 1，你是" in result["message"]


def test_process_ui_mock_private_chat_event_hides_mock_to_mock_content() -> None:
    engine = build_suit_engine()
    engine.assign_suits_for_round()

    result = process_ui_mock_private_chat_event(
        engine,
        {"type": "mock_turn", "speaker_id": 2},
        1,
        SequenceRandom(choice_indices=[1]),
        {2: "follower"},
    )

    assert result["status"] == "hidden"
    assert result["display_message"] == "其他玩家正在私下交流……"
    assert "message" not in result


def test_submit_ui_public_speech_records_all_alive_players() -> None:
    engine = build_suit_engine()
    engine.assign_suits_for_round()
    personalities = assign_mock_personalities(engine.state.players, 1, random.Random(8))

    claims = submit_ui_public_speech(
        engine,
        1,
        "我先说一下我的判断。",
        random.Random(7),
        personalities,
    )

    assert len(claims) == 6
    assert any(claim.speaker_id == 1 for claim in claims)
    assert {claim.speaker_id for claim in claims} == {1, 2, 3, 4, 5, 6}


def test_submit_ui_guess_resolves_deaths() -> None:
    engine = build_suit_engine()
    engine.assign_suits_for_round()
    personalities = assign_mock_personalities(engine.state.players, 1, random.Random(8))
    human_assignment = next(
        assignment
        for assignment in engine.state.current_suit_assignments
        if assignment.player_id == 1
    )
    wrong_suit = next(suit for suit in Suit if suit is not human_assignment.suit)

    result = submit_ui_guess(
        engine,
        1,
        wrong_suit,
        random.Random(7),
        personalities,
    )

    assert 1 in result["dead_player_ids"]
    assert engine.state.players[0].alive is False


def test_submit_ui_guess_can_reach_game_over_when_winner_exists() -> None:
    engine = build_suit_engine()
    engine.assign_suits_for_round()
    personalities = assign_mock_personalities(engine.state.players, 1, random.Random(8))
    human_player = next(player for player in engine.state.players if player.id == 1)
    human_assignment = next(
        assignment
        for assignment in engine.state.current_suit_assignments
        if assignment.player_id == 1
    )
    heart_j_player = next(
        player for player in engine.state.players if player.role is Role.HEART_J
    )
    if heart_j_player.id == 1:
        for player in engine.state.players:
            if player.id != 1:
                player.alive = False
        guessed_suit = human_assignment.suit
    else:
        for player in engine.state.players:
            if player.id not in {1, heart_j_player.id}:
                player.alive = False
        guessed_suit = human_assignment.suit

    result = submit_ui_guess(
        engine,
        1,
        guessed_suit,
        random.Random(7),
        personalities,
    )

    assert result["next_phase"] == "game_over"
    assert result["winner"] in {"heart_j", "prisoners"}


def test_game_over_recap_lines_can_show_truth_labels() -> None:
    engine = build_suit_engine()
    assignments = engine.assign_suits_for_round()
    remember_round_suit_assignments(engine)
    suit_for_2 = next(
        assignment.suit for assignment in assignments if assignment.player_id == 2
    )
    engine.record_private_chat(1, 2, f"Player 2，你是 {suit_for_2.value}。")

    lines = build_ui_all_private_chat_recap_lines(engine, include_truth_labels=True)

    assert any("[真话]" in line for line in lines)


def test_game_over_recap_lines_hide_truth_labels_before_game_over() -> None:
    engine = build_suit_engine()
    assignments = engine.assign_suits_for_round()
    remember_round_suit_assignments(engine)
    suit_for_2 = next(
        assignment.suit for assignment in assignments if assignment.player_id == 2
    )
    engine.record_private_chat(1, 2, f"Player 2，你是 {suit_for_2.value}。")

    lines = build_ui_all_private_chat_recap_lines(engine, include_truth_labels=False)

    assert all("[真话]" not in line and "[假话]" not in line for line in lines)


def test_ui_private_chat_lines_only_show_human_participating_messages() -> None:
    engine = build_suit_engine()
    engine.assign_suits_for_round()
    engine.record_private_chat(1, 2, "hello")
    engine.record_private_chat(3, 4, "hidden")

    lines = build_ui_player_private_chat_lines(engine, 1)

    assert any("Player 1 -> Player 2: hello" in line for line in lines)
    assert all("Player 3 -> Player 4: hidden" not in line for line in lines)


def test_should_show_live_private_chat_records_before_game_over() -> None:
    assert should_show_live_private_chat_records("private_chat") is True
    assert should_show_live_private_chat_records("public_speech") is True
    assert should_show_live_private_chat_records("guess") is True
    assert should_show_live_private_chat_records("round_result") is True


def test_should_show_live_private_chat_records_after_game_over() -> None:
    assert should_show_live_private_chat_records("game_over") is False


def test_format_mock_personalities_sorts_by_player_id() -> None:
    formatted = format_mock_personalities({3: "cautious", 2: "deceiver"})

    assert formatted == "Player 2=deceiver, Player 3=cautious"


def test_format_mock_personalities_returns_none_for_empty_dict() -> None:
    assert format_mock_personalities({}) == "None"


def test_format_suit_symbol_heart_returns_heart_symbol() -> None:
    suit_ui = format_suit_symbol("heart")

    assert suit_ui["symbol"] == "♥"
    assert suit_ui["label"] == "heart"
    assert suit_ui["color_class"] == "red-suit"


def test_format_suit_symbol_diamond_returns_diamond_symbol() -> None:
    suit_ui = format_suit_symbol("diamond")

    assert suit_ui["symbol"] == "♦"
    assert suit_ui["label"] == "diamond"
    assert suit_ui["color_class"] == "red-suit"


def test_format_suit_symbol_club_returns_club_symbol() -> None:
    suit_ui = format_suit_symbol("club")

    assert suit_ui["symbol"] == "♣"
    assert suit_ui["label"] == "club"
    assert suit_ui["color_class"] == "black-suit"


def test_format_suit_symbol_spade_returns_spade_symbol() -> None:
    suit_ui = format_suit_symbol("spade")

    assert suit_ui["symbol"] == "♠"
    assert suit_ui["label"] == "spade"
    assert suit_ui["color_class"] == "black-suit"


def test_format_suit_symbol_question_marks_returns_hidden_suit() -> None:
    suit_ui = format_suit_symbol("???")

    assert suit_ui["label"] == "???"
    assert suit_ui["color_class"] == "hidden-suit"


def test_format_suit_symbol_hidden_returns_hidden_suit() -> None:
    suit_ui = format_suit_symbol("hidden")

    assert suit_ui["label"] == "hidden"
    assert suit_ui["color_class"] == "hidden-suit"


def test_format_suit_symbol_none_returns_hidden_suit() -> None:
    suit_ui = format_suit_symbol(None)

    assert suit_ui["label"] == "hidden"
    assert suit_ui["color_class"] == "hidden-suit"


def test_format_suit_symbol_unknown_string_safely_falls_back_to_hidden() -> None:
    suit_ui = format_suit_symbol("joker")

    assert suit_ui["label"] == "hidden"
    assert suit_ui["color_class"] == "hidden-suit"


def test_build_player_card_data_still_contains_mock_personality() -> None:
    engine = build_suit_engine()
    engine.assign_suits_for_round()
    remember_round_suit_assignments(engine)
    personalities = {2: "deceiver", 3: "cautious", 4: "follower", 5: "honest", 6: "suspicious"}

    cards = build_player_card_data(engine, 1, personalities)
    mock_card = next(card for card in cards if card["player_id"] == 2)

    assert mock_card["personality"] == "deceiver"


def test_game_over_summary_still_has_player_private_history_lines() -> None:
    engine = build_suit_engine()
    engine.assign_suits_for_round()
    engine.record_private_chat(1, 2, "hello")

    lines = build_ui_player_private_chat_lines(engine, 1)

    assert any("Player 1 -> Player 2: hello" in line for line in lines)


def test_game_over_summary_still_has_global_private_chat_recap_lines() -> None:
    engine = build_suit_engine()
    assignments = engine.assign_suits_for_round()
    remember_round_suit_assignments(engine)
    suit_for_2 = next(
        assignment.suit for assignment in assignments if assignment.player_id == 2
    )
    engine.record_private_chat(1, 2, f"Player 2，你是 {suit_for_2.value}。")

    lines = build_ui_all_private_chat_recap_lines(engine, include_truth_labels=True)

    assert any("[真话]" in line for line in lines)


def test_game_over_before_recap_does_not_show_truth_labels() -> None:
    engine = build_suit_engine()
    assignments = engine.assign_suits_for_round()
    remember_round_suit_assignments(engine)
    suit_for_2 = next(
        assignment.suit for assignment in assignments if assignment.player_id == 2
    )
    engine.record_private_chat(1, 2, f"Player 2，你是 {suit_for_2.value}。")

    lines = build_ui_all_private_chat_recap_lines(engine, include_truth_labels=False)

    assert all("[真话]" not in line and "[假话]" not in line for line in lines)
