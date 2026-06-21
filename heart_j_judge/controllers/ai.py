import os
import random

from ai.llm_client import LLMClient, parse_ai_response
from ai.prompts import build_player_prompt
from controllers.base import Controller
from game.models import PrivatePlayerView


class AIController(Controller):
    def __init__(
        self,
        fake_response: str | None = None,
        rng: random.Random | None = None,
        llm_client: LLMClient | None = None,
    ) -> None:
        self.fake_response = fake_response
        self.rng = rng if rng is not None else random.Random()
        self.llm_client = llm_client if llm_client is not None else LLMClient()
        self._decision_cache: dict[tuple[int, int], dict] = {}
        self.ai_debug = os.getenv("AI_DEBUG", "false").strip().lower() == "true"

    def _debug_log(self, message: str) -> None:
        if self.ai_debug:
            print(message)

    def _fallback_decision(
        self, player_view: PrivatePlayerView, reason: str
    ) -> dict:
        legal_targets = [
            player_id
            for player_id in player_view.public_view.alive_player_ids
            if player_id != player_view.player_id
        ]
        if not legal_targets:
            raise ValueError("No legal vote targets available.")

        decision = {
            "speech": "我暂时没有足够信息。",
            "vote": self.rng.choice(legal_targets),
            "reason": "fallback",
        }
        self._debug_log(f"[AI_DEBUG] Player {player_view.player_id} fallback reason: {reason}")
        self._debug_log(
            "[AI_DEBUG] "
            f"Player {player_view.player_id} parsed decision: "
            f"speech={decision['speech']!r}, vote={decision['vote']}, reason={decision['reason']!r}"
        )
        return decision

    def _get_decision(self, player_view: PrivatePlayerView) -> dict:
        cache_key = (player_view.player_id, player_view.public_view.round_no)
        if cache_key in self._decision_cache:
            return self._decision_cache[cache_key]

        if self.fake_response is not None:
            response_text = self.fake_response
            self._debug_log(
                f"[AI_DEBUG] Player {player_view.player_id} using fake_response."
            )
        else:
            prompt = build_player_prompt(player_view)
            self._debug_log(f"[AI_DEBUG] Player {player_view.player_id} prompt:\n{prompt}")
            try:
                response_text = self.llm_client.generate(prompt)
            except ValueError as exc:
                decision = self._fallback_decision(
                    player_view,
                    f"LLM generate failed: {exc}",
                )
                self._decision_cache[cache_key] = decision
                return decision

        self._debug_log(
            f"[AI_DEBUG] Player {player_view.player_id} raw LLM response:\n{response_text}"
        )
        try:
            decision = parse_ai_response(response_text)
        except ValueError as exc:
            decision = self._fallback_decision(
                player_view,
                f"JSON parse failed: {exc}",
            )
            self._decision_cache[cache_key] = decision
            return decision

        legal_targets = [
            player_id
            for player_id in player_view.public_view.alive_player_ids
            if player_id != player_view.player_id
        ]
        if decision["vote"] not in legal_targets:
            decision = self._fallback_decision(
                player_view,
                (
                    f"Illegal vote target: {decision['vote']} "
                    f"not in legal targets {legal_targets}"
                ),
            )
            self._decision_cache[cache_key] = decision
            return decision

        self._debug_log(
            "[AI_DEBUG] "
            f"Player {player_view.player_id} parsed decision: "
            f"speech={decision['speech']!r}, vote={decision['vote']}, reason={decision['reason']!r}"
        )
        self._decision_cache[cache_key] = decision
        return decision

    def speak(self, player_view: PrivatePlayerView) -> str:
        return self._get_decision(player_view)["speech"]

    def vote(self, player_view: PrivatePlayerView) -> int:
        return self._get_decision(player_view)["vote"]
