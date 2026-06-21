# Heart J Judge

Heart J Judge is a command-line MVP for the Heart J Judge deduction game.

## Current scope

- Core game engine
- Human / Mock / AI controllers
- Mock full-game simulation
- AI prompt building and JSON parsing
- DeepSeek-compatible LLM client integration

## Modes

The project currently contains two gameplay directions:

- `Vote Mode`: the earlier vote-based experimental version
- `Suit Guess Mode`: the original Heart J restoration direction

At this stage, Suit Guess Mode only includes the independent engine skeleton. CLI integration and AI integration for that mode are not implemented yet.

## Suit Guess Mode CLI

Run the minimal Suit Guess Mode command-line demo with:

```powershell
python main_suit.py
```

也可以直接双击：

```text
start_suit_cli.bat
```

- `main.py` is the older vote-based experimental mode.
- `main_suit.py` is the original Heart J restoration direction using Suit Guess Mode.
- `main_suit.py` now includes a minimal private chat stage for the human player.
- Each round now uses an interleaved private-chat queue instead of a fixed `human first, mock later` order.
- Human players can actively initiate up to 2 private chats per round, while mock chats may cut in between them.
- If a mock player privately messages the human, the human can choose to reply immediately, and that reply does not consume one of the 2 active chat chances.
- A player pair will not start a second new private chat in the same round once they have already completed one interaction that round.
- `HUMAN_ROLE` can be used to force the human player to experience either the `heart_j` or `prisoner` perspective during demos.
- Private chats are only visible to the participants and are not included in public claim logs.
- After the game ends, the CLI prints a full private-chat recap so you can review who misled whom.
- During the game, private-chat truthfulness is never shown.
- After Game Over, the global private-chat recap labels each message as `真话`, `假话`, or `无法判断`.
- This recap is for debugging and post-game analysis of the Heart J misinformation chain.
- Mock players now also have lightweight personalities in the CLI layer:
  - `honest`
  - `deceiver`
  - `cautious`
  - `suspicious`
  - `follower`
- Personality is not a game identity. It only changes how a Mock tends to speak, lie, and guess.
- `deceiver` does not mean the player is `heart_j`; it may just be a troublemaking prisoner.
- Mock players now guess suits using a simple trust order:
  - first trust the most recent private chat sent to them
  - otherwise trust the most recent public claim about them
  - only guess randomly when they have no usable information
- Suit Guess Mode now treats private chat as the main information source.
- Mock public speeches only express attitude or suspicion and do not publicly announce suit names.
- Mock players may lie in private chat:
  - prisoners usually tell the truth
  - heart_j lies more often

## Suit Guess Mode UI Prototype

CLI 仍然是当前的完整玩法入口。

Streamlit UI 目前只是卡片式展示原型，不替代完整 CLI，也不会改变 `SuitGuessEngine` 规则。

运行方式：

```bash
streamlit run ui_suit.py
```

也可以直接双击：

```text
start_ui_suit.bat
```

当前 UI 原型特性：

- 侧边栏可选择 `HUMAN_ROLE` 为 `random` / `prisoner` / `heart_j`
- 支持“开始新游戏”和“重新分配本轮花色”
- 用卡片网格显示所有玩家
- 卡片会显示真正的扑克牌花色符号 `♥ ♦ ♣ ♠`
- 真人能看到其他存活玩家的花色，但看不到自己的花色
- 非真人玩家的真实身份在游戏中显示为 `unknown`
- 当前不会显示私聊真伪、其他玩家之间私聊、或完整回合流程

### Streamlit Cloud 部署说明

如果你在本地页面右上角点击 `Deploy`，但看到 “Unable to deploy”，通常不是 `ui_suit.py` 本身报错，而是因为当前代码目录还没有连接到一个可发布的 GitHub 远程仓库。

要部署到 Streamlit Community Cloud，至少需要：

1. 把 `heart_j_judge` 放进一个 GitHub repository
2. 把当前分支 push 到 GitHub
3. 确保仓库里包含：
   - `ui_suit.py`
   - `requirements.txt`
4. 在 Streamlit Community Cloud 里选择该仓库，并把入口文件设为：

```text
ui_suit.py
```

当前项目已经把 `streamlit` 写进 `requirements.txt`，所以推到 GitHub 后就具备基础部署条件了。

### Suit Guess Mode role override

Prisoner perspective:

```powershell
$env:HUMAN_ROLE="prisoner"
python main_suit.py
```

Heart J perspective:

```powershell
$env:HUMAN_ROLE="heart_j"
python main_suit.py
```

Back to random role assignment:

```powershell
Remove-Item Env:HUMAN_ROLE
python main_suit.py
```

## Run tests

```bash
python -m pytest
```

## Run in mock mode

Default mode is `mock`, which runs `1 Human + 5 Mock`.

```bash
python main.py
```

Or explicitly:

```bash
set GAME_MODE=mock
python main.py
```

## Run in AI mode

AI mode runs `1 Human + 5 AI`.

```bash
set GAME_MODE=ai
python main.py
```

If `DEEPSEEK_API_KEY` is missing, AI players will not crash the game. They will automatically fall back to legal default behavior.

## Run in AI debug mode

Use `AI_DEBUG=true` to print the AI player id, prompt, raw LLM output, parsed `speech / vote / reason`, and fallback reason.

```bash
set GAME_MODE=ai
set AI_DEBUG=true
python main.py
```

Normal mode does not print prompt details or AI reason fields, so the console stays readable.

## DeepSeek .env example

```env
GAME_MODE=ai
AI_DEBUG=false
LLM_PROVIDER=deepseek
DEEPSEEK_API_KEY=your_api_key_here
DEEPSEEK_BASE_URL=https://api.deepseek.com
DEEPSEEK_MODEL=deepseek-chat
```

## Troubleshooting non-JSON DeepSeek output

- Set `AI_DEBUG=true`.
- Re-run the game and inspect the raw LLM output in the terminal.
- If the model returns prose, Markdown code fences, or extra explanation text, the controller will safely fallback instead of crashing.
- The prompt now explicitly requires plain JSON only, integer votes, legal alive-player targets, and no extra text.

## AI terminology note

- AI players may still occasionally use the wrong genre terms.
- If you see terms like `法官`, `处刑人`, `狼人`, or `预言家`, first tighten the prompt.
- Do not fix this by changing the rule engine, because the engine already uses the correct game roles and rules.

## Observe card

- Each player starts with one `observe` action card.
- The card can be used only once.
- `observe` lets the user choose one target player and learn whether that target belongs to the 红桃J camp.
- 红桃J camp includes:
  - `heart_j`
  - `traitor`
- 囚犯 camp includes:
  - `prisoner`
- The result is private to the user and is not automatically announced.
- A player may tell the truth, hide the result, or lie about it in their speech.
- In the current MVP, only the human player is prompted to use the observe card. AI players do not actively use it yet.

## Observe card speech examples

If you observed that a target belongs to the 红桃J camp:

- “我观察了 Player X，他的阵营结果不干净，我建议优先听他的解释。”
- “我手里有一条信息指向 Player X，但我不直接说死，先看他的发言和投票。”
- “Player X 在我这里优先级很高，今天可以先围绕他聊。”

If you observed that a target does not belong to the 红桃J camp:

- “我观察了 Player X，暂时没有发现阵营问题，我今天不优先投他。”
- “Player X 在我这里优先级较低，我更想看其他人的发言。”
- “我不打算公开全部信息，但我暂时不怀疑 Player X。”

## Truth / hide / lie

- 说真话：你直接公开观察结果，推进团队共识，但也会暴露你的信息来源。
- 隐瞒：你不直接说结果，只通过投票倾向或轻度带节奏影响局面。
- 撒谎：你故意给出错误引导，可能制造收益，但后续一旦被识破会影响信誉。

In Suit Guess Mode, this tradeoff now appears mainly in private chat rather than in public suit declarations.
