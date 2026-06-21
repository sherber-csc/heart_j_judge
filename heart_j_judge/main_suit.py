import random
from contextlib import suppress
import os

from game.models import GameConfig, Suit
from game.roles import Role
from game.suit_engine import SuitGuessEngine


DEFAULT_SEED = 7
MOCK_PERSONALITIES = [
    "honest",
    "deceiver",
    "cautious",
    "suspicious",
    "follower",
]


def get_suit_victory_goal(role: str) -> str:
    if role == "heart_j":
        return "混入普通玩家，通过欺骗让其他玩家猜错自己的花色，并活到最后。"
    if role == "traitor":
        return "当前版本 traitor 暂未启用特殊逻辑，请先按普通存活思路游玩。"
    return "通过交流判断自己的花色，持续猜对并找出谁在误导大家。"


def apply_human_role_override(
    players: list, human_player_id: int, human_role: str | None, rng: random.Random
) -> list:
    normalized_role = (human_role or "").strip().lower()
    if not normalized_role:
        return players

    if normalized_role not in {"heart_j", "prisoner"}:
        raise ValueError("HUMAN_ROLE 只支持 heart_j / prisoner")

    human_player = next(
        (player for player in players if player.id == human_player_id),
        None,
    )
    if human_player is None:
        raise ValueError(f"Player {human_player_id} does not exist.")

    other_players = [player for player in players if player.id != human_player_id]

    if normalized_role == "heart_j":
        human_player.role = Role.HEART_J
        for player in other_players:
            player.role = Role.PRISONER
        return players

    human_player.role = Role.PRISONER
    for player in other_players:
        player.role = Role.PRISONER

    if other_players:
        rng.choice(other_players).role = Role.HEART_J

    return players


def parse_suit_input(raw_value: str) -> Suit | None:
    normalized = raw_value.strip().lower()
    suit_map = {
        "heart": Suit.HEART,
        "diamond": Suit.DIAMOND,
        "club": Suit.CLUB,
        "spade": Suit.SPADE,
    }
    return suit_map.get(normalized)


def parse_suit_from_text(text: str) -> Suit | None:
    normalized = text.strip().lower()
    if "heart" in normalized or "红桃" in normalized:
        return Suit.HEART
    if "diamond" in normalized or "方块" in normalized:
        return Suit.DIAMOND
    if "club" in normalized or "梅花" in normalized:
        return Suit.CLUB
    if "spade" in normalized or "黑桃" in normalized:
        return Suit.SPADE
    return None


def assign_mock_personalities(
    players: list, human_player_id: int, rng: random.Random
) -> dict[int, str]:
    mock_players = [player for player in players if player.id != human_player_id]
    if not mock_players:
        return {}

    personalities = ["deceiver"]
    while len(personalities) < len(mock_players):
        personalities.append(rng.choice(MOCK_PERSONALITIES))
    rng.shuffle(personalities)

    return {
        player.id: personalities[index]
        for index, player in enumerate(mock_players)
    }


def remember_round_suit_assignments(engine: SuitGuessEngine) -> None:
    history = getattr(engine, "_suit_assignment_history", [])
    current_round = engine.state.round_no
    history = [
        assignment
        for assignment in history
        if not (
            assignment.round_no == current_round
            and any(
                current.player_id == assignment.player_id
                for current in engine.state.current_suit_assignments
            )
        )
    ]
    history.extend(engine.state.current_suit_assignments)
    setattr(engine, "_suit_assignment_history", history)


def choose_claimed_suit_for_mock(
    engine: SuitGuessEngine,
    speaker_id: int,
    target_id: int,
    rng: random.Random,
    personalities: dict[int, str] | None = None,
) -> Suit:
    speaker = next(player for player in engine.state.players if player.id == speaker_id)
    speaker_view = engine.get_player_view(speaker_id)
    true_suit = speaker_view.visible_other_suits[target_id]
    personality = (personalities or {}).get(speaker_id, "follower")

    truth_probabilities = {
        "honest": {
            Role.PRISONER: 0.95,
            Role.HEART_J: 0.5,
        },
        "deceiver": {
            Role.PRISONER: 0.5,
            Role.HEART_J: 0.15,
        },
        "cautious": {
            Role.PRISONER: 0.85,
            Role.HEART_J: 0.35,
        },
        "suspicious": {
            Role.PRISONER: 0.7,
            Role.HEART_J: 0.25,
        },
        "follower": {
            Role.PRISONER: 0.8,
            Role.HEART_J: 0.3,
        },
    }
    if speaker.role is Role.TRAITOR:
        tell_truth = True
    else:
        truth_probability = truth_probabilities.get(
            personality,
            truth_probabilities["follower"],
        ).get(speaker.role, 1.0)
        tell_truth = rng.random() < truth_probability

    if tell_truth:
        return true_suit

    false_suits = [suit for suit in Suit if suit is not true_suit]
    return rng.choice(false_suits)


def choose_mock_public_speech(
    player_id: int, personality: str, rng: random.Random
) -> str:
    del player_id
    speech_map = {
        "honest": [
            "我倾向相信刚才直接交换信息的人。",
            "我不会公开细节，但我给出的信息比较可靠。",
        ],
        "deceiver": [
            "现在有人装得太诚实，反而更可疑。",
            "我不认为所有私聊信息都值得相信。",
        ],
        "cautious": [
            "我先不站队，继续观察大家的反应。",
            "这轮我会保守一点，不轻易相信单一来源。",
        ],
        "suspicious": [
            "我怀疑有人在私聊里故意给假信息。",
            "刚才的信息链里一定有人在误导。",
        ],
        "follower": [
            "我会参考多数人的态度来判断。",
            "我更倾向跟随目前看起来稳定的信息。",
        ],
    }
    return rng.choice(speech_map.get(personality, speech_map["follower"]))


def choose_mock_guess(
    engine: SuitGuessEngine,
    player_id: int,
    rng: random.Random,
    personalities: dict[int, str] | None = None,
) -> Suit:
    current_round = engine.state.round_no
    personality = (personalities or {}).get(player_id, "follower")

    private_messages = [
        chat
        for chat in engine.state.private_chat_history
        if chat.round_no == current_round and chat.to_player_id == player_id
    ]
    latest_private_suit = None
    for chat in reversed(private_messages):
        parsed_suit = parse_suit_from_text(chat.message)
        if parsed_suit is not None:
            latest_private_suit = parsed_suit
            break

    public_claims = [
        claim
        for claim in engine.state.suit_claim_history
        if claim.round_no == current_round and claim.target_id == player_id
    ]
    latest_public_suit = None
    for claim in reversed(public_claims):
        if claim.claimed_suit is not None:
            latest_public_suit = claim.claimed_suit
            break
        parsed_suit = parse_suit_from_text(claim.claim_text)
        if parsed_suit is not None:
            latest_public_suit = parsed_suit
            break

    if personality in {"honest", "follower", "cautious"}:
        if latest_private_suit is not None:
            return latest_private_suit
        if latest_public_suit is not None:
            return latest_public_suit
        return rng.choice(list(Suit))

    if personality == "deceiver":
        if latest_private_suit is not None:
            if rng.random() < 0.7:
                return latest_private_suit
            return rng.choice(list(Suit))
        if latest_public_suit is not None:
            return latest_public_suit
        return rng.choice(list(Suit))

    if personality == "suspicious":
        if latest_private_suit is not None:
            if rng.random() < 0.5:
                return latest_private_suit
            alternative_suits = [suit for suit in Suit if suit is not latest_private_suit]
            return rng.choice(alternative_suits)
        if latest_public_suit is not None:
            return latest_public_suit
        return rng.choice(list(Suit))

    return rng.choice(list(Suit))


def choose_mock_private_reply(
    engine: SuitGuessEngine,
    mock_player_id: int,
    target_player_id: int,
    rng: random.Random,
    personalities: dict[int, str] | None = None,
) -> str:
    claimed_suit = choose_claimed_suit_for_mock(
        engine, mock_player_id, target_player_id, rng, personalities
    )
    return f"Player {target_player_id}，你是 {claimed_suit.value}。"


def build_private_chat_events(
    engine: SuitGuessEngine, human_player_id: int, rng: random.Random
) -> list[dict]:
    events: list[dict] = []
    human_player = next(
        (player for player in engine.state.players if player.id == human_player_id),
        None,
    )
    if human_player is not None and human_player.alive:
        events.extend([{"type": "human_turn"}, {"type": "human_turn"}])

    alive_mock_players = [
        player
        for player in engine.state.players
        if player.alive and player.id != human_player_id
    ]
    events.extend(
        {"type": "mock_turn", "speaker_id": player.id} for player in alive_mock_players
    )
    events.sort(key=lambda _event: rng.random())
    return events


def has_private_chat_between_this_round(
    engine: SuitGuessEngine, player_a_id: int, player_b_id: int
) -> bool:
    current_round = engine.state.round_no
    return any(
        chat.round_no == current_round
        and (
            (
                chat.from_player_id == player_a_id
                and chat.to_player_id == player_b_id
            )
            or (
                chat.from_player_id == player_b_id
                and chat.to_player_id == player_a_id
            )
        )
        for chat in engine.state.private_chat_history
    )


def run_interleaved_private_chat_phase(
    engine: SuitGuessEngine,
    human_player_id: int,
    rng: random.Random,
    personalities: dict[int, str] | None = None,
) -> None:
    events = build_private_chat_events(engine, human_player_id, rng)
    hidden_chat_happened = False

    print("私聊阶段开始。私聊事件会穿插发生。")
    print("私聊内容不会公开给所有玩家。")

    for index, event in enumerate(events):
        human_player = next(
            (player for player in engine.state.players if player.id == human_player_id),
            None,
        )
        if event["type"] == "human_turn":
            if human_player is None or not human_player.alive:
                continue

            remaining_human_turns = sum(
                1
                for future_event in events[index:]
                if future_event["type"] == "human_turn"
            )
            print(f"你还可以主动私聊 {remaining_human_turns} 次。")

            while True:
                choice = input(
                    "是否发起私聊？输入目标玩家编号，或直接回车跳过: "
                ).strip()
                if not choice:
                    break
                if not choice.isdigit():
                    print("请输入有效的玩家编号，或直接回车跳过。")
                    continue

                target_id = int(choice)
                valid_targets = [
                    player.id
                    for player in engine.state.players
                    if player.alive and player.id != human_player_id
                ]
                if target_id not in valid_targets:
                    print("你只能选择其他存活玩家。")
                    continue
                if has_private_chat_between_this_round(
                    engine, human_player_id, target_id
                ):
                    print(f"本轮你已经和 Player {target_id} 私聊过，不能重复私聊。")
                    continue

                while True:
                    message = input(
                        f"请输入你发给 Player {target_id} 的私聊内容: "
                    ).strip()
                    if message:
                        break
                    print("私聊内容不能为空。")

                engine.record_private_chat(human_player_id, target_id, message)
                reply_message = choose_mock_private_reply(
                    engine, target_id, human_player_id, rng, personalities
                )
                engine.record_private_chat(target_id, human_player_id, reply_message)
                print(f"Player {target_id} 的私聊回复: {reply_message}")
                break

        if event["type"] != "mock_turn":
            continue

        speaker_id = event.get("speaker_id")
        if speaker_id is None or speaker_id == human_player_id:
            continue

        speaker = next(
            (player for player in engine.state.players if player.id == speaker_id),
            None,
        )
        if speaker is None or not speaker.alive:
            continue

        possible_targets = [
            player.id
            for player in engine.state.players
            if player.alive
            and player.id != speaker_id
            and not has_private_chat_between_this_round(engine, speaker_id, player.id)
        ]
        if not possible_targets:
            continue

        target_id = rng.choice(possible_targets)
        claimed_suit = choose_claimed_suit_for_mock(
            engine, speaker_id, target_id, rng, personalities
        )
        message = f"Player {target_id}，你是 {claimed_suit.value}。"
        engine.record_private_chat(speaker_id, target_id, message)

        if target_id != human_player_id:
            hidden_chat_happened = True
            continue

        print(f"Player {speaker_id} 私聊你：{message}")
        while True:
            should_reply = input(f"是否回复 Player {speaker_id}？(y/n): ").strip().lower()
            if should_reply in {"y", "n"}:
                break
            print("请输入 y 或 n。")

        if should_reply == "n":
            print(f"你没有回复 Player {speaker_id}。")
            continue

        while True:
            reply_message = input(f"请输入你回复 Player {speaker_id} 的内容: ").strip()
            if reply_message:
                break
            print("私聊内容不能为空。")

        engine.record_private_chat(human_player_id, speaker_id, reply_message)
        print(f"你已回复 Player {speaker_id}。")

    if hidden_chat_happened:
        print("其他玩家正在私下交流……")


def print_round_claims(engine: SuitGuessEngine, round_no: int) -> None:
    print("本轮发言记录:")
    round_claims = [
        claim for claim in engine.state.suit_claim_history if claim.round_no == round_no
    ]
    for claim in round_claims:
        if claim.target_id is None:
            print(f"- Player {claim.speaker_id}: {claim.claim_text}")
        else:
            print(
                f"- Player {claim.speaker_id} -> Player {claim.target_id}: "
                f"{claim.claim_text}"
            )


def print_player_private_chat_history(engine: SuitGuessEngine, player_id: int) -> None:
    print("你的私聊历史:")
    player_chats = [
        chat
        for chat in engine.state.private_chat_history
        if chat.from_player_id == player_id or chat.to_player_id == player_id
    ]
    if not player_chats:
        print("- None")
        return

    for chat in player_chats:
        print(
            f"- Round {chat.round_no}: Player {chat.from_player_id} -> "
            f"Player {chat.to_player_id}: {chat.message}"
        )


def get_true_suit_for_round(
    engine: SuitGuessEngine, round_no: int, player_id: int
) -> Suit | None:
    history = getattr(engine, "_suit_assignment_history", [])
    for assignment in history:
        if assignment.round_no == round_no and assignment.player_id == player_id:
            return assignment.suit

    for assignment in engine.state.current_suit_assignments:
        if assignment.round_no == round_no and assignment.player_id == player_id:
            return assignment.suit

    return None


def classify_private_chat_truth(engine: SuitGuessEngine, chat) -> str:
    claimed_suit = parse_suit_from_text(chat.message)
    if claimed_suit is None:
        return "无法判断"

    true_suit = get_true_suit_for_round(engine, chat.round_no, chat.to_player_id)
    if true_suit is None:
        return "无法判断"

    if claimed_suit is true_suit:
        return "真话"
    return "假话"


def print_all_private_chat_history(engine: SuitGuessEngine) -> None:
    print("全局私聊复盘:")
    if not engine.state.private_chat_history:
        print("- None")
        return

    for chat in engine.state.private_chat_history:
        truth_label = classify_private_chat_truth(engine, chat)
        print(
            f"- Round {chat.round_no}: Player {chat.from_player_id} -> "
            f"Player {chat.to_player_id}: {chat.message} [{truth_label}]"
        )


def print_guess_history(engine: SuitGuessEngine) -> None:
    print("每轮猜测历史:")
    for guess in engine.state.suit_guess_history:
        print(
            f"- Round {guess.round_no}: Player {guess.player_id} guessed "
            f"{guess.guessed_suit.value}, correct={guess.correct}"
        )


def print_death_history(death_history: list[tuple[int, list[int]]]) -> None:
    print("每轮死亡情况:")
    for round_no, dead_player_ids in death_history:
        print(f"- Round {round_no}: dead={dead_player_ids}")


def main() -> None:
    config = GameConfig(
        player_count=6,
        heart_j_count=1,
        traitor_count=0,
        prisoner_count=5,
        seed=DEFAULT_SEED,
    )
    engine = SuitGuessEngine(config)
    players = engine.create_players()
    human_role_setting = os.getenv("HUMAN_ROLE")
    apply_human_role_override(players, 1, human_role_setting, random.Random(DEFAULT_SEED))
    player_one = next(player for player in players if player.id == 1)
    mock_rng = random.Random(DEFAULT_SEED)
    personalities = assign_mock_personalities(players, 1, random.Random(DEFAULT_SEED + 1))
    death_history: list[tuple[int, list[int]]] = []

    print("Heart J Judge - Suit Guess Mode")
    print(f"玩家总数: {len(players)}")
    print("真人玩家编号: 1")
    print(f"HUMAN_ROLE 设置: {human_role_setting or 'random'}")
    print(f"真人身份: {player_one.role.value}")
    print(
        "Mock personalities: "
        + ", ".join(
            f"Player {player_id}={personality}"
            for player_id, personality in sorted(personalities.items())
        )
    )
    print(f"胜利目标: {get_suit_victory_goal(player_one.role.value)}")
    print("规则说明:")
    print("- 你看不到自己的花色。")
    print("- 你能看到其他存活玩家的花色。")
    print("- 每轮结束时你都要猜自己的花色。")
    print("- 猜错会死亡。")

    while not engine.state.game_over:
        round_no = engine.state.round_no
        engine.assign_suits_for_round()
        remember_round_suit_assignments(engine)
        alive_player_ids = [player.id for player in engine.state.players if player.alive]

        print()
        print(f"Round {round_no} Start")
        print(f"当前轮数: {round_no}")
        print(f"当前存活玩家: {alive_player_ids}")

        if player_one.alive:
            player_view = engine.get_player_view(1)
            print("你能看到的其他玩家花色:")
            for other_id, suit in player_view.visible_other_suits.items():
                print(f"- Player {other_id}: {suit.value}")

            run_interleaved_private_chat_phase(engine, 1, mock_rng, personalities)

            while True:
                speech = input("请输入你的发言: ").strip()
                if speech:
                    break
                print("发言不能为空。")
            engine.record_claim(1, None, speech)
        else:
            print("你已死亡，进入旁观模式。")

        for player in engine.state.players:
            if not player.alive or player.id == 1:
                continue
            claim_text = choose_mock_public_speech(
                player.id,
                personalities.get(player.id, "follower"),
                mock_rng,
            )
            engine.record_claim(player.id, None, claim_text, None)

        print_round_claims(engine, round_no)

        if player_one.alive:
            while True:
                raw_guess = input(
                    "请输入你猜测自己的花色 (heart/diamond/club/spade): "
                )
                guessed_suit = parse_suit_input(raw_guess)
                if guessed_suit is not None:
                    break
                print("请输入有效花色：heart / diamond / club / spade")
            engine.record_guess(1, guessed_suit)

        for player in engine.state.players:
            if not player.alive or player.id == 1:
                continue
            mock_guess = choose_mock_guess(engine, player.id, mock_rng, personalities)
            engine.record_guess(player.id, mock_guess)

        dead_players = engine.resolve_guesses()
        dead_player_ids = [player.id for player in dead_players]
        death_history.append((round_no, dead_player_ids))

        print("本轮死亡玩家:")
        if dead_player_ids:
            for player in dead_players:
                print(f"- Player {player.id}: role={player.role.value}")
        else:
            print("- None")

        winner = engine.check_winner()
        if winner is not None:
            engine.state.winner = winner
            engine.state.game_over = True
            print(f"Winner: {winner}")
            break

        engine.advance_round()

    print()
    print("Game Over")
    print(f"Winner: {engine.state.winner}")
    print("所有玩家最终身份:")
    for player in engine.state.players:
        print(f"- Player {player.id}: role={player.role.value}, alive={player.alive}")
    print_guess_history(engine)
    print_death_history(death_history)
    if player_one.alive:
        print_player_private_chat_history(engine, 1)
    else:
        print("你已死亡，以下仅显示你参与过的私聊历史。")
        print_player_private_chat_history(engine, 1)
    print_all_private_chat_history(engine)


if __name__ == "__main__":
    main()
