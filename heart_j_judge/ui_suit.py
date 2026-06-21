from __future__ import annotations

import random
from typing import Any

from game.models import GameConfig, Suit
from game.suit_engine import SuitGuessEngine
from main_suit import (
    apply_human_role_override,
    assign_mock_personalities,
    build_private_chat_events,
    choose_claimed_suit_for_mock,
    choose_mock_guess,
    choose_mock_public_speech,
    classify_private_chat_truth,
    has_private_chat_between_this_round,
    remember_round_suit_assignments,
)


DEFAULT_UI_SEED = 7
DEFAULT_HUMAN_PLAYER_ID = 1
HUMAN_ROLE_OPTIONS = ["random", "prisoner", "heart_j"]
UI_PHASES = [
    "private_chat",
    "public_speech",
    "guess",
    "round_result",
    "game_over",
]
SUIT_OPTIONS = ["heart", "diamond", "club", "spade"]
SUIT_VALUE_MAP = {
    "heart": Suit.HEART,
    "diamond": Suit.DIAMOND,
    "club": Suit.CLUB,
    "spade": Suit.SPADE,
}
SUIT_SYMBOLS = {
    "heart": "♥",
    "diamond": "♦",
    "club": "♣",
    "spade": "♠",
}
RED_SUITS = {"heart", "diamond"}

try:
    import streamlit as st
except ModuleNotFoundError:  # pragma: no cover - streamlit may be absent in test env
    st = None


def _normalize_human_role_setting(human_role_setting: str | None) -> str:
    normalized = (human_role_setting or "random").strip().lower()
    if normalized not in HUMAN_ROLE_OPTIONS:
        return "random"
    return normalized


def create_ui_engine(
    human_role_setting: str = "random",
    seed: int = DEFAULT_UI_SEED,
) -> tuple[SuitGuessEngine, dict[int, str]]:
    config = GameConfig(
        player_count=6,
        heart_j_count=1,
        traitor_count=0,
        prisoner_count=5,
        seed=seed,
    )
    engine = SuitGuessEngine(config)
    players = engine.create_players()
    normalized_role = _normalize_human_role_setting(human_role_setting)
    apply_human_role_override(
        players,
        DEFAULT_HUMAN_PLAYER_ID,
        None if normalized_role == "random" else normalized_role,
        random.Random(seed),
    )
    personalities = assign_mock_personalities(
        players,
        DEFAULT_HUMAN_PLAYER_ID,
        random.Random(seed + 1),
    )
    engine.assign_suits_for_round()
    remember_round_suit_assignments(engine)
    return engine, personalities


def build_ui_private_chat_events(
    engine: SuitGuessEngine,
    human_player_id: int,
    rng: random.Random,
) -> list[dict[str, Any]]:
    return build_private_chat_events(engine, human_player_id, rng)


def initialize_ui_game(
    human_role_setting: str = "random",
    rng: random.Random | None = None,
) -> dict[str, Any]:
    rng = rng or random.Random(DEFAULT_UI_SEED + 99)
    normalized_role = _normalize_human_role_setting(human_role_setting)
    engine, personalities = create_ui_engine(normalized_role, DEFAULT_UI_SEED)
    human_player_id = DEFAULT_HUMAN_PLAYER_ID
    return {
        "engine": engine,
        "personalities": personalities,
        "human_player_id": human_player_id,
        "human_role_setting": normalized_role,
        "rng": rng,
        "phase": "private_chat",
        "private_chat_events": build_ui_private_chat_events(
            engine, human_player_id, rng
        ),
        "current_private_chat_event_index": 0,
        "human_private_chat_count": 0,
        "pending_mock_speaker_id": None,
        "pending_mock_message": None,
        "winner": None,
        "last_round_deaths": [],
        "death_history": [],
        "game_log": [],
    }


def get_ui_private_chat_targets(
    engine: SuitGuessEngine,
    speaker_id: int,
) -> list[int]:
    speaker = next(
        (player for player in engine.state.players if player.id == speaker_id),
        None,
    )
    if speaker is None or not speaker.alive:
        return []

    return [
        player.id
        for player in engine.state.players
        if player.alive
        and player.id != speaker_id
        and not has_private_chat_between_this_round(engine, speaker_id, player.id)
    ]


def process_ui_human_private_chat(
    engine: SuitGuessEngine,
    human_player_id: int,
    target_id: int,
    message: str,
    rng: random.Random,
    personalities: dict[int, str] | None = None,
) -> dict[str, Any]:
    normalized_message = message.strip()
    if not normalized_message:
        return {"status": "invalid", "error": "私聊内容不能为空。"}
    if target_id not in get_ui_private_chat_targets(engine, human_player_id):
        return {"status": "invalid", "error": "目标玩家当前不可私聊。"}

    human_chat = engine.record_private_chat(
        human_player_id,
        target_id,
        normalized_message,
    )
    claimed_suit = choose_claimed_suit_for_mock(
        engine,
        target_id,
        human_player_id,
        rng,
        personalities,
    )
    reply_message = f"Player {human_player_id}，你是 {claimed_suit.value}。"
    mock_reply = engine.record_private_chat(target_id, human_player_id, reply_message)
    return {
        "status": "sent",
        "human_chat": human_chat,
        "mock_reply": mock_reply,
        "reply_message": reply_message,
        "target_id": target_id,
    }


def process_ui_human_private_reply(
    engine: SuitGuessEngine,
    human_player_id: int,
    speaker_id: int,
    message: str,
) -> dict[str, Any]:
    normalized_message = message.strip()
    if not normalized_message:
        return {"status": "invalid", "error": "回复内容不能为空。"}

    reply_record = engine.record_private_chat(
        human_player_id,
        speaker_id,
        normalized_message,
    )
    return {"status": "sent", "reply_record": reply_record}


def process_ui_mock_private_chat_event(
    engine: SuitGuessEngine,
    event: dict[str, Any],
    human_player_id: int,
    rng: random.Random,
    personalities: dict[int, str] | None = None,
) -> dict[str, Any]:
    if event.get("type") != "mock_turn":
        return {"status": "skipped", "reason": "not_mock_turn"}

    speaker_id = event.get("speaker_id")
    if speaker_id is None or speaker_id == human_player_id:
        return {"status": "skipped", "reason": "invalid_speaker"}

    speaker = next(
        (player for player in engine.state.players if player.id == speaker_id),
        None,
    )
    if speaker is None or not speaker.alive:
        return {"status": "skipped", "reason": "dead_speaker"}

    possible_targets = get_ui_private_chat_targets(engine, speaker_id)
    if not possible_targets:
        return {"status": "skipped", "reason": "no_targets"}

    target_id = rng.choice(possible_targets)
    claimed_suit = choose_claimed_suit_for_mock(
        engine,
        speaker_id,
        target_id,
        rng,
        personalities,
    )
    message = f"Player {target_id}，你是 {claimed_suit.value}。"
    chat_record = engine.record_private_chat(speaker_id, target_id, message)

    if target_id != human_player_id:
        return {
            "status": "hidden",
            "speaker_id": speaker_id,
            "target_id": target_id,
            "display_message": "其他玩家正在私下交流……",
            "chat_record": chat_record,
        }

    return {
        "status": "needs_human_reply",
        "speaker_id": speaker_id,
        "target_id": target_id,
        "message": message,
        "chat_record": chat_record,
    }


def submit_ui_public_speech(
    engine: SuitGuessEngine,
    human_player_id: int,
    speech: str,
    rng: random.Random,
    personalities: dict[int, str],
) -> list[Any]:
    normalized_speech = speech.strip()
    if not normalized_speech:
        raise ValueError("公开发言不能为空。")

    round_no = engine.state.round_no
    engine.record_claim(human_player_id, None, normalized_speech)
    for player in engine.state.players:
        if not player.alive or player.id == human_player_id:
            continue
        claim_text = choose_mock_public_speech(
            player.id,
            personalities.get(player.id, "follower"),
            rng,
        )
        engine.record_claim(player.id, None, claim_text, None)

    return [
        claim
        for claim in engine.state.suit_claim_history
        if claim.round_no == round_no
    ]


def submit_ui_guess(
    engine: SuitGuessEngine,
    human_player_id: int,
    guessed_suit: Suit,
    rng: random.Random,
    personalities: dict[int, str],
) -> dict[str, Any]:
    if not isinstance(guessed_suit, Suit):
        raise ValueError("Guessed suit must be a Suit.")

    if any(
        guess.round_no == engine.state.round_no and guess.player_id == human_player_id
        for guess in engine.state.suit_guess_history
    ):
        raise ValueError("本轮你已经提交过猜测。")

    human_player = next(
        player for player in engine.state.players if player.id == human_player_id
    )
    if human_player.alive:
        engine.record_guess(human_player_id, guessed_suit)

    for player in engine.state.players:
        if not player.alive or player.id == human_player_id:
            continue
        mock_guess = choose_mock_guess(
            engine,
            player.id,
            rng,
            personalities,
        )
        engine.record_guess(player.id, mock_guess)

    dead_players = engine.resolve_guesses()
    winner = engine.state.winner or engine.check_winner()
    if winner is not None:
        engine.state.winner = winner
        engine.state.game_over = True

    return {
        "dead_players": dead_players,
        "dead_player_ids": [player.id for player in dead_players],
        "dead_summary": [
            {"player_id": player.id, "role": player.role.value}
            for player in dead_players
        ],
        "winner": winner,
        "next_phase": "game_over" if winner is not None else "round_result",
    }


def advance_ui_round(ui_state: dict[str, Any]) -> None:
    engine = ui_state["engine"]
    engine.advance_round()
    engine.assign_suits_for_round()
    remember_round_suit_assignments(engine)
    ui_state["private_chat_events"] = build_ui_private_chat_events(
        engine,
        ui_state["human_player_id"],
        ui_state["rng"],
    )
    ui_state["current_private_chat_event_index"] = 0
    ui_state["human_private_chat_count"] = 0
    ui_state["pending_mock_speaker_id"] = None
    ui_state["pending_mock_message"] = None
    ui_state["last_round_deaths"] = []
    ui_state["phase"] = "private_chat"


def build_player_card_data(
    engine: SuitGuessEngine,
    human_player_id: int,
    personalities: dict[int, str],
    reveal_roles: bool = False,
    reveal_all_suits: bool = False,
) -> list[dict[str, Any]]:
    assignments_by_id = {
        assignment.player_id: assignment.suit.value
        for assignment in engine.state.current_suit_assignments
        if assignment.round_no == engine.state.round_no
    }
    alive_player_ids = {
        player.id for player in engine.state.players if player.alive
    }
    human_player = next(
        player for player in engine.state.players if player.id == human_player_id
    )
    human_alive = human_player.alive
    cards: list[dict[str, Any]] = []

    for player in engine.state.players:
        is_human = player.id == human_player_id
        role_display = player.role.value if (reveal_roles or is_human) else "unknown"
        personality_display = "you" if is_human else personalities.get(player.id, "unknown")

        if reveal_all_suits and player.id in assignments_by_id:
            suit_display = assignments_by_id[player.id]
        elif is_human:
            suit_display = "???"
        elif human_alive and player.id in alive_player_ids and player.id in assignments_by_id:
            suit_display = assignments_by_id[player.id]
        else:
            suit_display = "hidden"

        suit_ui = format_suit_symbol(suit_display)

        cards.append(
            {
                "player_id": player.id,
                "is_human": is_human,
                "title": f"Player {player.id}" + ("（你）" if is_human else ""),
                "role": role_display,
                "personality": personality_display,
                "suit": suit_display,
                "suit_symbol": suit_ui["symbol"],
                "suit_label": suit_ui["label"],
                "suit_class": suit_ui["color_class"],
                "status": "alive" if player.alive else "dead",
            }
        )

    return cards


def build_ui_player_private_chat_lines(
    engine: SuitGuessEngine,
    player_id: int,
) -> list[str]:
    lines = []
    for chat in engine.state.private_chat_history:
        if chat.from_player_id == player_id or chat.to_player_id == player_id:
            lines.append(
                f"Round {chat.round_no}: Player {chat.from_player_id} -> "
                f"Player {chat.to_player_id}: {chat.message}"
            )
    return lines


def build_ui_all_private_chat_recap_lines(
    engine: SuitGuessEngine,
    include_truth_labels: bool = False,
) -> list[str]:
    lines = []
    for chat in engine.state.private_chat_history:
        suffix = ""
        if include_truth_labels:
            suffix = f" [{classify_private_chat_truth(engine, chat)}]"
        lines.append(
            f"Round {chat.round_no}: Player {chat.from_player_id} -> "
            f"Player {chat.to_player_id}: {chat.message}{suffix}"
        )
    return lines


def get_round_claim_lines(engine: SuitGuessEngine, round_no: int) -> list[str]:
    return [
        f"Player {claim.speaker_id}: {claim.claim_text}"
        for claim in engine.state.suit_claim_history
        if claim.round_no == round_no
    ]


def get_guess_history_lines(engine: SuitGuessEngine) -> list[str]:
    return [
        f"Round {guess.round_no}: Player {guess.player_id} guessed "
        f"{guess.guessed_suit.value}, correct={guess.correct}"
        for guess in engine.state.suit_guess_history
    ]


def get_death_history_lines(death_history: list[dict[str, Any]]) -> list[str]:
    return [
        f"Round {entry['round_no']}: dead={entry['dead_player_ids']}"
        for entry in death_history
    ]


def should_show_live_private_chat_records(phase: str) -> bool:
    return phase != "game_over"


def format_suit_symbol(suit_value: str | None) -> dict[str, str]:
    normalized = (suit_value or "hidden").strip().lower()
    if normalized in RED_SUITS:
        return {
            "symbol": SUIT_SYMBOLS[normalized],
            "label": normalized,
            "color_class": "red-suit",
        }
    if normalized in SUIT_SYMBOLS:
        return {
            "symbol": SUIT_SYMBOLS[normalized],
            "label": normalized,
            "color_class": "black-suit",
        }
    if normalized == "???":
        return {
            "symbol": "🂠",
            "label": "???",
            "color_class": "hidden-suit",
        }
    return {
        "symbol": "🂠",
        "label": "hidden",
        "color_class": "hidden-suit",
    }


def format_mock_personalities(personalities: dict[int, str]) -> str:
    if not personalities:
        return "None"
    return ", ".join(
        f"Player {player_id}={personality}"
        for player_id, personality in sorted(personalities.items())
    )


def sync_ui_state_to_session(ui_state: dict[str, Any]) -> None:
    if st is None:
        return
    for key, value in ui_state.items():
        st.session_state[key] = value


def _current_round_has_activity(engine: SuitGuessEngine) -> bool:
    round_no = engine.state.round_no
    return any(
        chat.round_no == round_no for chat in engine.state.private_chat_history
    ) or any(
        claim.round_no == round_no for claim in engine.state.suit_claim_history
    ) or any(
        guess.round_no == round_no for guess in engine.state.suit_guess_history
    )


def _render_styles() -> None:
    st.markdown(
        """
        <style>
        .stApp {
            background:
                radial-gradient(circle at 15% 10%, rgba(177, 216, 255, 0.10), transparent 22%),
                radial-gradient(circle at 85% 15%, rgba(255, 150, 150, 0.10), transparent 18%),
                linear-gradient(180deg, #111827 0%, #0b1220 100%);
        }
        .player-card {
            position: relative;
            overflow: hidden;
            border: 1px solid rgba(15, 23, 42, 0.12);
            border-radius: 24px;
            padding: 20px;
            min-height: 220px;
            background:
                linear-gradient(145deg, rgba(255, 255, 255, 0.98) 0%, rgba(248, 244, 239, 0.98) 100%);
            color: #0f172a;
            box-shadow: 0 18px 44px rgba(15, 23, 42, 0.18);
        }
        .player-card::after {
            content: "";
            position: absolute;
            inset: 0;
            background:
                radial-gradient(circle at 85% 18%, rgba(255, 214, 214, 0.95), transparent 24%),
                radial-gradient(circle at 16% 82%, rgba(219, 234, 254, 0.70), transparent 24%);
            pointer-events: none;
        }
        .player-title {
            position: relative;
            z-index: 1;
            font-size: 1.1rem;
            font-weight: 700;
            margin-bottom: 12px;
            color: #111827;
        }
        .player-meta {
            position: relative;
            z-index: 1;
            margin: 0.35rem 0;
            font-size: 0.98rem;
            color: #334155;
        }
        .player-suit {
            position: relative;
            z-index: 1;
            display: flex;
            align-items: baseline;
            gap: 0.55rem;
            margin: 1rem 0 0.5rem;
        }
        .suit-symbol {
            font-size: 3rem;
            line-height: 1;
            font-weight: 700;
        }
        .suit-symbol.red-suit {
            color: #c1121f;
        }
        .suit-symbol.black-suit {
            color: #111827;
        }
        .suit-symbol.hidden-suit {
            color: #64748b;
        }
        .suit-text {
            font-size: 1.02rem;
            font-weight: 600;
            color: #0f172a;
        }
        .status-chip {
            position: absolute;
            top: 16px;
            right: 16px;
            z-index: 1;
            padding: 0.28rem 0.65rem;
            border-radius: 999px;
            font-size: 0.85rem;
            font-weight: 700;
            background: rgba(15, 23, 42, 0.08);
            color: #0f172a;
        }
        .status-chip.dead {
            background: rgba(127, 29, 29, 0.12);
            color: #991b1b;
        }
        .prototype-note {
            padding: 0.9rem 1rem;
            border-radius: 16px;
            background: #fff4e6;
            border: 1px solid #ffd8a8;
        }
        </style>
        """,
        unsafe_allow_html=True,
    )


def _render_cards(
    engine: SuitGuessEngine,
    personalities: dict[int, str],
    human_player_id: int,
    reveal_roles: bool,
    reveal_all_suits: bool,
) -> None:
    cards = build_player_card_data(
        engine,
        human_player_id,
        personalities,
        reveal_roles=reveal_roles,
        reveal_all_suits=reveal_all_suits,
    )
    columns = st.columns(3)
    for index, card in enumerate(cards):
        with columns[index % 3]:
            st.markdown(
                f"""
                <div class="player-card">
                    <div class="player-title">{card["title"]}</div>
                    <div class="player-meta">Role: {card["role"]}</div>
                    <div class="player-meta">Personality: {card["personality"]}</div>
                    <div class="player-suit">
                        <span class="suit-symbol {card["suit_class"]}">{card["suit_symbol"]}</span>
                        <span class="suit-text">Suit: {card["suit_label"]}</span>
                    </div>
                    <div class="status-chip {'dead' if card['status'] == 'dead' else ''}">{card["status"]}</div>
                </div>
                """,
                unsafe_allow_html=True,
            )


def _render_private_chat_phase() -> None:
    engine = st.session_state.engine
    human_player_id = st.session_state.human_player_id
    personalities = st.session_state.personalities
    rng = st.session_state.rng
    events = st.session_state.private_chat_events
    event_index = st.session_state.current_private_chat_event_index
    pending_speaker_id = st.session_state.pending_mock_speaker_id
    total_events = len(events)

    st.subheader("私聊阶段")
    st.write(f"私聊阶段：事件 {min(event_index + 1, total_events) if total_events else total_events} / {total_events}")

    if pending_speaker_id is not None:
        st.info(st.session_state.pending_mock_message)
        with st.form("mock_reply_form"):
            reply_text = st.text_area("回复内容", key="ui_mock_reply_text")
            reply_button = st.form_submit_button("发送回复")
            skip_button = st.form_submit_button("不回复")
        if reply_button:
            result = process_ui_human_private_reply(
                engine,
                human_player_id,
                pending_speaker_id,
                reply_text,
            )
            if result["status"] == "sent":
                st.session_state.game_log.append(
                    f"Round {engine.state.round_no}: you replied to Player {pending_speaker_id}."
                )
                st.session_state.pending_mock_speaker_id = None
                st.session_state.pending_mock_message = None
                st.session_state.current_private_chat_event_index += 1
                st.rerun()
            else:
                st.error(result["error"])
        if skip_button:
            st.session_state.game_log.append(
                f"Round {engine.state.round_no}: you skipped replying to Player {pending_speaker_id}."
            )
            st.session_state.pending_mock_speaker_id = None
            st.session_state.pending_mock_message = None
            st.session_state.current_private_chat_event_index += 1
            st.rerun()
        return

    if event_index >= total_events:
        st.success("本轮私聊事件已处理完。")
        if st.button("进入公开发言阶段", use_container_width=True):
            st.session_state.phase = "public_speech"
            st.rerun()
        return

    event = events[event_index]
    if event["type"] == "human_turn":
        remaining_turns = sum(
            1 for future_event in events[event_index:] if future_event["type"] == "human_turn"
        )
        st.write(f"你还可以主动私聊 {remaining_turns} 次。")
        valid_targets = get_ui_private_chat_targets(engine, human_player_id)
        if valid_targets:
            with st.form(f"human_private_chat_form_{event_index}"):
                target_id = st.selectbox(
                    "选择私聊目标",
                    options=valid_targets,
                    format_func=lambda value: f"Player {value}",
                )
                message = st.text_area("私聊内容")
                send_button = st.form_submit_button("发送私聊")
                skip_button = st.form_submit_button("跳过本次主动私聊")
            if send_button:
                result = process_ui_human_private_chat(
                    engine,
                    human_player_id,
                    target_id,
                    message,
                    rng,
                    personalities,
                )
                if result["status"] == "sent":
                    st.session_state.human_private_chat_count += 1
                    st.session_state.current_private_chat_event_index += 1
                    st.session_state.game_log.append(
                        f"Round {engine.state.round_no}: you privately chatted with Player {target_id}."
                    )
                    st.success(f"Player {target_id} 回复你：{result['reply_message']}")
                    st.rerun()
                else:
                    st.error(result["error"])
            if skip_button:
                st.session_state.current_private_chat_event_index += 1
                st.rerun()
        else:
            st.info("本轮没有可私聊的目标了。")
            if st.button("跳过本次主动私聊", use_container_width=True):
                st.session_state.current_private_chat_event_index += 1
                st.rerun()
        return

    st.write("当前事件由 Mock 发起。")
    if st.button("处理下一个私聊事件", use_container_width=True):
        result = process_ui_mock_private_chat_event(
            engine,
            event,
            human_player_id,
            rng,
            personalities,
        )
        if result["status"] == "needs_human_reply":
            st.session_state.pending_mock_speaker_id = result["speaker_id"]
            st.session_state.pending_mock_message = (
                f"Player {result['speaker_id']} 私聊你：{result['message']}"
            )
        else:
            st.session_state.current_private_chat_event_index += 1
            if result["status"] == "hidden":
                st.info(result["display_message"])
            elif result["status"] == "skipped":
                st.info("该私聊事件已跳过。")
        st.rerun()


def _render_public_speech_phase() -> None:
    engine = st.session_state.engine
    if st.session_state.human_player_id not in [
        player.id for player in engine.state.players if player.alive
    ]:
        st.info("你已死亡，本轮不再公开发言。")
        st.session_state.phase = "guess"
        st.rerun()
        return

    st.subheader("公开发言阶段")
    with st.form("public_speech_form"):
        speech = st.text_area("请输入你的公开发言")
        submit_button = st.form_submit_button("提交公开发言")
    if submit_button:
        try:
            claims = submit_ui_public_speech(
                engine,
                st.session_state.human_player_id,
                speech,
                st.session_state.rng,
                st.session_state.personalities,
            )
        except ValueError as exc:
            st.error(str(exc))
            return
        st.session_state.game_log.append(
            f"Round {engine.state.round_no}: public speech phase completed with {len(claims)} speeches."
        )
        st.session_state.phase = "guess"
        st.rerun()

    round_claim_lines = get_round_claim_lines(engine, engine.state.round_no)
    if round_claim_lines:
        st.write("本轮公开发言记录：")
        for line in round_claim_lines:
            st.write(f"- {line}")


def _render_guess_phase() -> None:
    engine = st.session_state.engine
    st.subheader("猜测阶段")

    round_claim_lines = get_round_claim_lines(engine, engine.state.round_no)
    if round_claim_lines:
        st.write("本轮公开发言记录：")
        for line in round_claim_lines:
            st.write(f"- {line}")

    human_player = next(
        player for player in engine.state.players if player.id == st.session_state.human_player_id
    )
    if human_player.alive:
        with st.form("guess_form"):
            guessed_suit_name = st.radio("请选择你的花色猜测", SUIT_OPTIONS, horizontal=True)
            submit_button = st.form_submit_button("提交猜测")
        if not submit_button:
            return
        guessed_suit = SUIT_VALUE_MAP[guessed_suit_name]
    else:
        st.info("你已死亡，本轮由剩余 Mock 继续猜测。")
        if not st.button("让剩余玩家完成猜测", use_container_width=True):
            return
        guessed_suit = Suit.HEART

    result = submit_ui_guess(
        engine,
        st.session_state.human_player_id,
        guessed_suit,
        st.session_state.rng,
        st.session_state.personalities,
    )
    st.session_state.last_round_deaths = result["dead_summary"]
    st.session_state.death_history.append(
        {
            "round_no": engine.state.round_no,
            "dead_player_ids": result["dead_player_ids"],
        }
    )
    st.session_state.winner = result["winner"]
    st.session_state.phase = result["next_phase"]
    st.rerun()


def _render_round_result_phase() -> None:
    engine = st.session_state.engine
    st.subheader("回合结算")
    deaths = st.session_state.last_round_deaths
    if deaths:
        for death in deaths:
            st.write(f"- Player {death['player_id']}: role={death['role']}")
    else:
        st.write("- None")

    if st.button("进入下一轮", use_container_width=True):
        advance_ui_round(st.session_state)
        st.rerun()


def _render_game_over_phase() -> None:
    engine = st.session_state.engine
    human_player_id = st.session_state.human_player_id
    st.subheader("Game Over")
    st.write(f"Winner: {st.session_state.winner}")

    st.write("所有玩家最终身份：")
    for player in engine.state.players:
        st.write(f"- Player {player.id}: role={player.role.value}, alive={player.alive}")

    st.write("每轮猜测历史：")
    guess_lines = get_guess_history_lines(engine)
    if guess_lines:
        for line in guess_lines:
            st.write(f"- {line}")
    else:
        st.write("- None")

    st.write("每轮死亡情况：")
    death_lines = get_death_history_lines(st.session_state.death_history)
    if death_lines:
        for line in death_lines:
            st.write(f"- {line}")
    else:
        st.write("- None")

    st.write("你的私聊历史：")
    player_chat_lines = build_ui_player_private_chat_lines(engine, human_player_id)
    if player_chat_lines:
        for line in player_chat_lines:
            st.write(f"- {line}")
    else:
        st.write("- None")

    st.write("全局私聊复盘：")
    recap_lines = build_ui_all_private_chat_recap_lines(
        engine,
        include_truth_labels=True,
    )
    if recap_lines:
        for line in recap_lines:
            st.write(f"- {line}")
    else:
        st.write("- None")


def render_app() -> None:
    if st is None:
        raise ModuleNotFoundError(
            "streamlit is not installed. Install it first, then run `streamlit run ui_suit.py`."
        )

    st.set_page_config(
        page_title="Heart J Judge - Suit UI Prototype",
        page_icon="♥",
        layout="wide",
    )
    _render_styles()

    st.sidebar.title("Suit Guess UI")
    selected_human_role = st.sidebar.selectbox(
        "HUMAN_ROLE",
        HUMAN_ROLE_OPTIONS,
        index=HUMAN_ROLE_OPTIONS.index(
            _normalize_human_role_setting(
                st.session_state.get("human_role_setting", "random")
            )
        ),
    )

    if "engine" not in st.session_state:
        sync_ui_state_to_session(
            initialize_ui_game(
                selected_human_role,
                random.Random(DEFAULT_UI_SEED + 99),
            )
        )

    if st.sidebar.button("开始新游戏", use_container_width=True):
        sync_ui_state_to_session(
            initialize_ui_game(
                selected_human_role,
                random.Random(DEFAULT_UI_SEED + 99),
            )
        )
        st.rerun()

    reassign_disabled = _current_round_has_activity(st.session_state.engine)
    if st.sidebar.button(
        "重新分配本轮花色",
        use_container_width=True,
        disabled=reassign_disabled,
    ):
        engine = st.session_state.engine
        engine.assign_suits_for_round()
        remember_round_suit_assignments(engine)
        st.session_state.private_chat_events = build_ui_private_chat_events(
            engine,
            st.session_state.human_player_id,
            st.session_state.rng,
        )
        st.session_state.current_private_chat_event_index = 0
        st.session_state.human_private_chat_count = 0
        st.session_state.pending_mock_speaker_id = None
        st.session_state.pending_mock_message = None
        st.session_state.phase = "private_chat"
        st.rerun()

    engine = st.session_state.engine
    personalities = st.session_state.personalities
    human_player = next(
        player for player in engine.state.players if player.id == st.session_state.human_player_id
    )
    reveal_game_over = st.session_state.phase == "game_over"

    st.title("Heart J Judge - Suit Guess Mode")
    alive_player_ids = [player.id for player in engine.state.players if player.alive]
    personality_text = format_mock_personalities(personalities)

    st.subheader("当前局信息")
    st.write(f"当前轮数: {engine.state.round_no}")
    st.write(f"当前存活玩家: {alive_player_ids}")
    st.write(f"HUMAN_ROLE 设置: {st.session_state.human_role_setting}")
    st.write(f"真人身份: {human_player.role.value}")
    st.write(f"当前阶段: {st.session_state.phase}")

    with st.expander("调试信息：Mock personalities", expanded=False):
        st.write(personality_text)

    st.subheader("玩家卡片")
    _render_cards(
        engine,
        personalities,
        st.session_state.human_player_id,
        reveal_roles=reveal_game_over,
        reveal_all_suits=reveal_game_over,
    )

    if should_show_live_private_chat_records(st.session_state.phase):
        st.subheader("你的私聊记录")
        live_chat_lines = build_ui_player_private_chat_lines(
            engine,
            st.session_state.human_player_id,
        )
        for line in live_chat_lines[-8:]:
            st.write(f"- {line}")
        if not live_chat_lines:
            st.write("- None")

    if st.session_state.phase == "private_chat":
        _render_private_chat_phase()
    elif st.session_state.phase == "public_speech":
        _render_public_speech_phase()
    elif st.session_state.phase == "guess":
        _render_guess_phase()
    elif st.session_state.phase == "round_result":
        _render_round_result_phase()
    elif st.session_state.phase == "game_over":
        _render_game_over_phase()


def main() -> None:
    render_app()


if __name__ == "__main__":
    main()
