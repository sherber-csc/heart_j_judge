from __future__ import annotations

from abc import ABC, abstractmethod

from game.models import GameState


class Controller(ABC):
    @abstractmethod
    def speak(self, game_state: GameState) -> str:
        """Return the player's speech for the current round."""

    @abstractmethod
    def vote(self, game_state: GameState) -> int:
        """Return the target player id for the current vote."""
