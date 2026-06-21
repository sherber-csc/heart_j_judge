from game.models import PrivatePlayerView


def build_player_prompt(player_view: PrivatePlayerView) -> str:
    public_view = player_view.public_view
    speech_lines = [
        f"- Round {record.round_no} | Player {record.player_id}: {record.speech}"
        for record in public_view.speech_history
    ]
    vote_lines = [
        f"- Round {record.round_no} | Player {record.voter_id} -> Player {record.target_id}"
        for record in public_view.vote_history
    ]
    elimination_lines = [
        (
            f"- Round {record.round_no} | Player {record.player_id} "
            f"| tie_break={record.by_tie_break}"
        )
        for record in public_view.elimination_history
    ]

    speech_block = "\n".join(speech_lines) if speech_lines else "- None"
    vote_block = "\n".join(vote_lines) if vote_lines else "- None"
    elimination_block = "\n".join(elimination_lines) if elimination_lines else "- None"

    return (
        "You are a player in Heart J Judge.\n"
        "This game only has these roles:\n"
        "- heart_j: 红桃J\n"
        "- traitor: 内鬼\n"
        "- prisoner: 囚犯\n"
        "This game also has a one-time observe action card.\n"
        "A human player may use the observe card to learn whether a target belongs to the 红桃J camp.\n"
        "Players may tell the truth, hide the result, or lie about the result.\n"
        "Do not claim that you used an observe card unless you truly received that information from the system.\n"
        "Do not automatically assume that you have used any action card.\n"
        "Do not use any other role terms such as 法官, 处刑人, 狼人, 预言家, 杀手, 警长.\n"
        "Your reasoning must only focus on 红桃J, 内鬼, 囚犯, voting behavior, and contradictions in speeches.\n"
        f"Your player id: {player_view.player_id}\n"
        f"Your role: {player_view.role.value}\n"
        f"Current round: {public_view.round_no}\n"
        f"Alive players: {public_view.alive_player_ids}\n"
        "Historical speeches:\n"
        f"{speech_block}\n"
        "Historical votes:\n"
        f"{vote_block}\n"
        "Historical eliminations:\n"
        f"{elimination_block}\n"
        "You must not assume or reveal other players' hidden roles.\n"
        'Keep "speech" to 1 to 3 sentences.\n'
        'Avoid repetitive long summaries of the full history.\n'
        'Do not say "我是囚犯" unless it is strategically necessary.\n'
        'Return valid JSON only with exactly these keys: "speech", "vote", "reason".\n'
        '"vote" must be an integer.\n'
        f'"vote" must be one of these alive players: {public_view.alive_player_ids}.\n'
        f'"vote" must not be your own player id: {player_view.player_id}.\n'
        'Do not output Markdown code fences.\n'
        'Do not output explanations, notes, or any extra text outside the JSON object.'
    )
