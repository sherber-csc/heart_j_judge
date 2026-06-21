import os
import random

from ai.llm_client import LLMClient
from controllers.ai import AIController
from controllers.human import HumanController
from controllers.mock import MockController
from game.engine import GameEngine
from game.models import GameConfig, Player


def get_victory_goal(role: str) -> str:
    if role == "heart_j":
        return "存活到第4轮结束，或让场上存活人数降到3人及以下。"
    if role == "traitor":
        return "协助红桃J阵营获胜：保护红桃J存活到第4轮结束，或让场上存活人数降到3人及以下。"
    return "淘汰红桃J。"


def create_controllers(players: list[Player], game_mode: str) -> dict[int, object]:
    normalized_mode = game_mode.strip().lower()
    controllers: dict[int, object] = {}

    for player in players:
        if player.id == 1:
            controllers[player.id] = HumanController()
            continue

        if normalized_mode == "mock":
            controllers[player.id] = MockController(random.Random(player.id))
        elif normalized_mode == "ai":
            controllers[player.id] = AIController(rng=random.Random(player.id))
        else:
            raise ValueError(f"Unsupported GAME_MODE: {game_mode}")

    return controllers


def maybe_use_human_observe_card(engine: GameEngine, player_one: Player) -> None:
    if engine.state.round_no != 1:
        return
    if not player_one.alive:
        return
    if player_one.action_card is None:
        return
    if player_one.action_card.name != "observe" or player_one.action_card.used:
        return

    print("你有一张行动牌: observe")
    while True:
        choice = input("是否在第一轮发言前使用观察牌？(y/n): ").strip().lower()
        if choice in {"y", "n"}:
            break
        print("请输入 y 或 n。")

    if choice == "n":
        return

    alive_player_ids = [player.id for player in engine.state.players if player.alive]
    legal_targets = [player_id for player_id in alive_player_ids if player_id != 1]
    while True:
        print(f"可观察目标玩家: {legal_targets}")
        raw_value = input("请输入你要观察的玩家编号: ").strip()
        if not raw_value.isdigit():
            print("请输入有效的玩家编号。")
            continue

        target_id = int(raw_value)
        if target_id not in legal_targets:
            print("你只能观察其他存活玩家。")
            continue

        result = engine.use_observe_card(1, target_id)
        if result["is_heart_j_camp"]:
            print(f"观察结果：Player {result['target_id']} 属于红桃J阵营。")
            print("以下只是发言建议，你不需要照读：")
            print("- 我观察了 Player X，他的阵营结果不干净，我建议优先听他的解释。")
            print("- 我手里有一条信息指向 Player X，但我不直接说死，先看他的发言和投票。")
            print("- Player X 在我这里优先级很高，今天可以先围绕他聊。")
        else:
            print(f"观察结果：Player {result['target_id']} 不属于红桃J阵营。")
            print("以下只是发言建议，你不需要照读：")
            print("- 我观察了 Player X，暂时没有发现阵营问题，我今天不优先投他。")
            print("- Player X 在我这里优先级较低，我更想看其他人的发言。")
            print("- 我不打算公开全部信息，但我暂时不怀疑 Player X。")

        print("额外提醒：")
        print("- 你可以说真话。")
        print("- 你可以隐瞒。")
        print("- 你可以撒谎。")
        print("- 但撒谎会影响后续信誉。")
        return


def main() -> None:
    config = GameConfig()
    engine = GameEngine(config)
    players = engine.create_players()
    engine.deal_action_cards()
    game_mode = os.getenv("GAME_MODE", "mock").strip().lower()
    ai_debug = os.getenv("AI_DEBUG", "false").strip().lower()
    controllers = create_controllers(players, game_mode)
    llm_client = LLMClient() if game_mode == "ai" else None

    player_one = next(player for player in players if player.id == 1)
    print("Heart J Judge Demo")
    print("Game Start")
    print(f"玩家总数: {len(players)}")
    print(f"当前 GAME_MODE: {game_mode}")
    if game_mode == "mock":
        print("当前模式: 1 Human + 5 Mock")
    elif game_mode == "ai":
        print("当前模式: 1 Human + 5 AI")
        print(f"LLM 可用: {llm_client.is_available() if llm_client is not None else False}")
        print(f"AI_DEBUG: {ai_debug}")
    else:
        raise ValueError(f"Unsupported GAME_MODE: {game_mode}")
    print("你的玩家编号: 1")
    print(f"你的身份: {player_one.role.value}")
    print(f"胜利目标: {get_victory_goal(player_one.role.value)}")
    if player_one.action_card is not None:
        print(
            f"你的行动牌: {player_one.action_card.name} "
            f"(used={player_one.action_card.used})"
        )

    while not engine.state.game_over:
        current_round = engine.state.round_no
        alive_player_ids = [player.id for player in engine.state.players if player.alive]
        player_one_alive = any(
            player.id == 1 and player.alive for player in engine.state.players
        )
        print()
        print(f"Round {current_round} Start")
        print(f"当前轮数: {current_round}")
        print(f"当前存活玩家: {alive_player_ids}")
        if not player_one_alive:
            print("你已被淘汰，进入旁观模式。")
        else:
            maybe_use_human_observe_card(engine, player_one)

        result = engine.run_round_with_controllers(controllers)
        eliminated = result["eliminated"]
        round_speeches = [
            record for record in engine.state.speech_history if record.round_no == current_round
        ]
        round_votes = [
            record for record in engine.state.vote_history if record.round_no == current_round
        ]
        elimination_record = next(
            (
                record
                for record in engine.state.elimination_history
                if record.round_no == current_round
            ),
            None,
        )

        print(f"Round {current_round} End")
        print("本轮发言记录:")
        for record in round_speeches:
            print(f"- Player {record.player_id}: {record.speech}")

        print("本轮投票记录:")
        for record in round_votes:
            print(f"- Player {record.voter_id} -> Player {record.target_id}")

        if eliminated is None:
            print("被淘汰玩家编号: None")
            print("被淘汰玩家身份: None")
            print("是否平票淘汰: False")
        else:
            print(f"被淘汰玩家编号: {eliminated.id}")
            print(f"被淘汰玩家身份: {eliminated.role.value}")
            print(
                "是否平票淘汰: "
                f"{elimination_record.by_tie_break if elimination_record is not None else False}"
            )

        current_winner = result["winner"] if result["winner"] is not None else "None"
        print(f"当前胜负状态: {current_winner}")

    print()
    print("Game Over")
    if not player_one.alive:
        print("你已被淘汰，本局只能旁观至结束。")
    print(f"Winner: {engine.state.winner}")
    print("所有玩家最终身份:")
    for player in engine.state.players:
        print(
            f"- Player {player.id}: role={player.role.value}, alive={player.alive}"
        )
    print("淘汰历史:")
    for record in engine.state.elimination_history:
        eliminated_player = next(
            player for player in engine.state.players if player.id == record.player_id
        )
        print(
            f"- Round {record.round_no}: "
            f"Player {record.player_id} ({eliminated_player.role.value}), "
            f"tie_break={record.by_tie_break}"
        )


if __name__ == "__main__":
    main()
