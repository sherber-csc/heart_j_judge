# ARCHITECTURE.md

# 架构规范

## 架构原则

采用：

Game Engine + Controller

结构：

Game Engine
├── HumanController
├── AIController
└── MockController

## Game Engine职责

负责：

* 创建游戏
* 分配身份
* 管理轮次
* 记录发言
* 记录投票
* 淘汰玩家
* 判断胜负

Game Engine 不允许：

* 调用OpenAI
* 请求网络
* 读取用户输入
* 输出UI

## Controller职责

Controller负责：

* 获取玩家输入
* 返回玩家决策

统一接口：

```python
class Controller:
    def speak(game_state) -> str
    def vote(game_state) -> int
```

## HumanController

负责：

* 键盘输入
* 未来GUI输入
* 未来手机输入

## AIController

负责：

* OpenAI API调用
* Prompt构建
* JSON解析

## MockController

负责：

* 随机发言
* 随机合法投票

用于：

* 测试
* 离线运行

## 数据模型

Player

```python
id: int
role: Role
alive: bool
controller: Controller
```

不要写：

```python
player.ai_prompt
player.api_key
```

这些属于Controller。

## 推荐目录

heart_j_judge/

main.py

game/
├── models.py
├── engine.py
├── voting.py
├── roles.py

controllers/
├── base.py
├── human.py
├── ai.py
├── mock.py

ai/
├── prompts.py
├── llm_client.py

tests/

## 扩展原则

未来新增：

WebController
MiniProgramController
DiscordController

不允许修改 Game Engine。

新增控制器即可接入系统。
