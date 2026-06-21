import random

from controllers.base import Controller
from game.models import PrivatePlayerView


class MockController(Controller):
    def __init__(self, rng: random.Random | None = None) -> None:
        self.rng = rng if rng is not None else random.Random()

    def speak(self, player_view: PrivatePlayerView) -> str:
        return "我暂时没有足够信息。"

    def vote(self, player_view: PrivatePlayerView) -> int:
        legal_targets = [
            player_id
            for player_id in player_view.public_view.alive_player_ids
            if player_id != player_view.player_id
        ]
        if not legal_targets:
            raise ValueError("No legal vote targets available.")

        return self.rng.choice(legal_targets)
