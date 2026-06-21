from __future__ import annotations

import random

from game.models import GameState, VoteRecord


def validate_vote(state: GameState, voter_id: int, target_id: int) -> bool:
    players_by_id = {player.id: player for player in state.players}

    voter = players_by_id.get(voter_id)
    if voter is None:
        raise ValueError(f"Voter {voter_id} does not exist.")

    target = players_by_id.get(target_id)
    if target is None:
        raise ValueError(f"Target {target_id} does not exist.")

    if not voter.alive:
        raise ValueError(f"Voter {voter_id} is not alive.")

    if not target.alive:
        raise ValueError(f"Target {target_id} is not alive.")

    if voter_id == target_id:
        raise ValueError("Voter cannot vote for self.")

    return True


def count_votes(votes: list[VoteRecord]) -> dict[int, int]:
    vote_counts: dict[int, int] = {}
    for vote in votes:
        vote_counts[vote.target_id] = vote_counts.get(vote.target_id, 0) + 1
    return vote_counts


def get_top_targets(vote_counts: dict[int, int]) -> list[int]:
    if not vote_counts:
        return []

    max_votes = max(vote_counts.values())
    return [target_id for target_id, count in vote_counts.items() if count == max_votes]


def choose_eliminated(
    top_targets: list[int], rng: random.Random | None = None
) -> int | None:
    if not top_targets:
        return None

    if len(top_targets) == 1:
        return top_targets[0]

    chooser = rng if rng is not None else random
    return chooser.choice(top_targets)
