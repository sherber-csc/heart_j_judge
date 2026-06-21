from controllers.base import Controller
from game.models import PrivatePlayerView


class HumanController(Controller):
    def speak(self, player_view: PrivatePlayerView) -> str:
        alive_players = player_view.public_view.alive_player_ids
        print(
            f"Player {player_view.player_id} | "
            f"Role: {player_view.role.value} | "
            f"Round: {player_view.public_view.round_no} | "
            f"Alive players: {alive_players}"
        )
        while True:
            speech = input("Enter your speech: ").strip()
            if speech:
                return speech
            print("Speech cannot be empty. Please try again.")

    def vote(self, player_view: PrivatePlayerView) -> int:
        alive_players = player_view.public_view.alive_player_ids
        print(f"Alive players: {alive_players}")
        while True:
            raw_value = input("Enter the player id you want to vote for: ").strip()
            if not raw_value.isdigit():
                print("Please enter a valid player id number.")
                continue

            target_id = int(raw_value)
            if target_id == player_view.player_id:
                print("You cannot vote for yourself.")
                continue
            if target_id not in alive_players:
                print("You must vote for a living player.")
                continue
            return target_id
