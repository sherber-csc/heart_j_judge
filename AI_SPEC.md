# AI_SPEC.md

# AI Controller规范

## AI定位

AI是玩家。

不是裁判。

不是主持人。

不是规则引擎。

## AI可见信息

允许：

* 自己编号
* 自己身份
* 自己性格
* 当前轮数
* 存活玩家
* 历史发言
* 历史投票
* 历史淘汰记录

禁止：

* 其他玩家真实身份
* 完整身份表
* 隐藏阵营信息

## 输出格式

统一JSON：

```json
{
  "speech": "本轮发言",
  "vote": 3,
  "reason": "投票理由"
}
```

## 约束

vote必须：

* 为整数
* 为存活玩家
* 不等于自己

speech必须：

* 非空
* 不直接暴露隐藏身份

## Prompt原则

Prompt只描述：

* 当前身份
* 当前局势
* 当前目标

不要描述：

* 所有身份
* 完整真相

## Fallback机制

如果AI返回非法JSON：

第一次：

重试

第二次：

进入Fallback

Fallback：

```json
{
  "speech": "我暂时没有足够信息。",
  "vote": 随机合法目标,
  "reason": "fallback"
}
```

## Mock兼容

如果不存在OPENAI_API_KEY：

自动切换MockController。

程序必须能够完整运行。

## 调试模式

Debug模式：

显示：

* speech
* vote
* reason

正式模式：

显示：

* speech
* vote

隐藏reason。

## 成本控制

当前MVP：

每个AI每轮最多调用一次模型。

禁止：

* 长上下文记忆
* Agent循环
* 多轮自我反思
* AI之间私聊

先保证规则正确和游戏可运行。
