import random

import pytest

from game.models import GameState, Player, VoteRecord
from game.roles import ControllerType, Role
from game.voting import choose_eliminated, count_votes, get_top_targets, validate_vote


def build_state() -> GameState:
    return GameState(
        players=[
            Player(id=1, role=Role.PRISONER, controller_type=ControllerType.HUMAN),
            Player(id=2, role=Role.PRISONER, controller_type=ControllerType.AI),
            Player(id=3, role=Role.HEART_J, controller_type=ControllerType.MOCK),
        ]
    )


def test_validate_vote_accepts_valid_vote() -> None:
    state = build_state()

    assert validate_vote(state, voter_id=1, target_id=2) is True


def test_validate_vote_raises_when_voter_missing() -> None:
    state = build_state()

    with pytest.raises(ValueError, match="Voter 99 does not exist"):
        validate_vote(state, voter_id=99, target_id=2)


def test_validate_vote_raises_when_target_missing() -> None:
    state = build_state()

    with pytest.raises(ValueError, match="Target 99 does not exist"):
        validate_vote(state, voter_id=1, target_id=99)


def test_validate_vote_raises_when_voter_dead() -> None:
    state = build_state()
    state.players[0].alive = False

    with pytest.raises(ValueError, match="Voter 1 is not alive"):
        validate_vote(state, voter_id=1, target_id=2)


def test_validate_vote_raises_when_target_dead() -> None:
    state = build_state()
    state.players[1].alive = False

    with pytest.raises(ValueError, match="Target 2 is not alive"):
        validate_vote(state, voter_id=1, target_id=2)


def test_validate_vote_raises_when_voting_for_self() -> None:
    state = build_state()

    with pytest.raises(ValueError, match="Voter cannot vote for self"):
        validate_vote(state, voter_id=1, target_id=1)


def test_count_votes_counts_targets_correctly() -> None:
    votes = [
        VoteRecord(round_no=1, voter_id=1, target_id=2),
        VoteRecord(round_no=1, voter_id=2, target_id=3),
        VoteRecord(round_no=1, voter_id=3, target_id=2),
    ]

    assert count_votes(votes) == {2: 2, 3: 1}


def test_get_top_targets_returns_single_highest_target() -> None:
    vote_counts = {2: 3, 3: 1}

    assert get_top_targets(vote_counts) == [2]


def test_get_top_targets_returns_all_tied_targets() -> None:
    vote_counts = {2: 2, 3: 2, 4: 1}

    assert get_top_targets(vote_counts) == [2, 3]


def test_get_top_targets_returns_empty_list_for_no_votes() -> None:
    assert get_top_targets({}) == []


def test_choose_eliminated_returns_none_for_empty_targets() -> None:
    assert choose_eliminated([]) is None


def test_choose_eliminated_returns_only_target_when_single_top_target() -> None:
    assert choose_eliminated([2]) == 2


def test_choose_eliminated_uses_rng_for_tie_break() -> None:
    rng = random.Random(0)

    assert choose_eliminated([2, 3], rng=rng) == 3
