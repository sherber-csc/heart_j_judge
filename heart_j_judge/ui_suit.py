from __future__ import annotations

import random
from typing import Any

from game.models import GameConfig
from game.suit_engine import SuitGuessEngine
from main_suit import (
    apply_human_role_override,
    assign_mock_personalities,
    remember_round_suit_assignments,
)


DEFAULT_UI_SEED = 7
DEFAULT_HUMAN_PLAYER_ID = 1
HUMAN_ROLE_OPTIONS = ["random", "prisoner", "heart_j"]
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
    apply_human_role_override(
        players,
        DEFAULT_HUMAN_PLAYER_ID,
        None if human_role_setting == "random" else human_role_setting,
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


def build_player_card_data(
    engine: SuitGuessEngine,
    human_player_id: int,
    personalities: dict[int, str],
) -> list[dict[str, Any]]:
    human_view = engine.get_player_view(human_player_id)
    alive_player_ids = set(human_view.alive_player_ids)
    visible_other_suits = human_view.visible_other_suits
    cards: list[dict[str, Any]] = []

    for player in engine.state.players:
        is_human = player.id == human_player_id
        if is_human:
            suit_key = "unknown"
            suit_symbol = "🂠"
            suit_display = "???"
            role_display = player.role.value
            personality_display = "you"
        elif player.id in alive_player_ids:
            suit_key = visible_other_suits[player.id].value
            suit_symbol = SUIT_SYMBOLS[suit_key]
            suit_display = suit_key
            role_display = "unknown"
            personality_display = personalities.get(player.id, "unknown")
        else:
            suit_key = "hidden"
            suit_symbol = "🂠"
            suit_display = "hidden"
            role_display = "unknown"
            personality_display = personalities.get(player.id, "unknown")

        cards.append(
            {
                "player_id": player.id,
                "is_human": is_human,
                "title": f"Player {player.id}" + ("（你）" if is_human else ""),
                "role": role_display,
                "personality": personality_display,
                "suit": suit_display,
                "suit_symbol": suit_symbol,
                "suit_key": suit_key,
                "suit_class": (
                    "red" if suit_key in RED_SUITS else "black" if suit_key in SUIT_SYMBOLS else "hidden"
                ),
                "status": "alive" if player.alive else "dead",
            }
        )

    return cards


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
        .suit-symbol.red {
            color: #c1121f;
        }
        .suit-symbol.black {
            color: #111827;
        }
        .suit-symbol.hidden {
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

    st.sidebar.title("Suit Guess UI")
    selected_human_role = st.sidebar.selectbox(
        "HUMAN_ROLE",
        HUMAN_ROLE_OPTIONS,
        index=HUMAN_ROLE_OPTIONS.index(
            st.session_state.get("ui_human_role", "random")
        ),
    )

    if "ui_engine" not in st.session_state:
        engine, personalities = create_ui_engine(selected_human_role)
        st.session_state.ui_engine = engine
        st.session_state.ui_personalities = personalities
        st.session_state.ui_human_role = selected_human_role

    if st.sidebar.button("开始新游戏", use_container_width=True):
        engine, personalities = create_ui_engine(selected_human_role)
        st.session_state.ui_engine = engine
        st.session_state.ui_personalities = personalities
        st.session_state.ui_human_role = selected_human_role

    if st.sidebar.button("重新分配本轮花色", use_container_width=True):
        engine = st.session_state.ui_engine
        engine.assign_suits_for_round()
        remember_round_suit_assignments(engine)

    engine = st.session_state.ui_engine
    personalities = st.session_state.ui_personalities
    st.session_state.ui_human_role = selected_human_role
    human_player = next(
        player for player in engine.state.players if player.id == DEFAULT_HUMAN_PLAYER_ID
    )

    st.title("Heart J Judge - Suit Guess Mode")
    st.markdown(
        '<div class="prototype-note">CLI 仍然是完整玩法入口。这个页面目前只是卡片式展示原型，不负责完整回合推进。</div>',
        unsafe_allow_html=True,
    )

    alive_player_ids = [player.id for player in engine.state.players if player.alive]
    personality_text = ", ".join(
        f"Player {player_id}={personality}"
        for player_id, personality in sorted(personalities.items())
    )

    info_col, debug_col = st.columns([1.1, 1.2])
    with info_col:
        st.subheader("当前局信息")
        st.write(f"当前轮数: {engine.state.round_no}")
        st.write(f"当前存活玩家: {alive_player_ids}")
        st.write(f"HUMAN_ROLE 设置: {selected_human_role}")
        st.write(f"真人身份: {human_player.role.value}")
    with debug_col:
        st.subheader("Mock personalities")
        st.write(personality_text or "None")

    st.subheader("玩家卡片")
    cards = build_player_card_data(engine, DEFAULT_HUMAN_PLAYER_ID, personalities)
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
                        <span class="suit-text">Suit: {card["suit"]}</span>
                    </div>
                    <div class="status-chip {'dead' if card['status'] == 'dead' else ''}">{card["status"]}</div>
                </div>
                """,
                unsafe_allow_html=True,
            )


def main() -> None:
    render_app()


if __name__ == "__main__":
    main()
