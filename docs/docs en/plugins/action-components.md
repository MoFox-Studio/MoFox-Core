# ⚡ Action Component Details

> **🎉 New Feature: More Flexible Activation Mechanism!**  
> MoFox-Bot now supports customizing Action activation logic through the `go_activate()` method!  
> Details: [Action Activation Mechanism Refactoring Guide](./action-activation-guide.md)

## 📖 What is Action

Action is an intelligent component that provides MoFox_Bot with additional functionality beyond replies, **automatically chosen by MoFox_Bot's decision system**, with random and anthropomorphic calling characteristics. Action is not a direct response to user commands, but lets MoFox_Bot intelligently choose suitable actions based on chat context, making its behavior more natural and realistic.

### Action Characteristics

- 🧠 **Intelligent Activation**: MoFox_Bot intelligently judges whether to use based on multiple conditions
- 🎲 **Randomness Possible**: Can use random numbers to activate, increasing behavior unpredictability, closer to human interaction
- 🤖 **Anthropomorphic**: Makes MoFox_Bot's responses more natural and personalized
- 🔄 **Context Aware**: Makes appropriate responses based on chat context

---

## 🎯 Basic Structure of Action Components

First, all Actions should inherit from the `BaseAction` class.

Second, each Action component should implement the following basic information:
```python
class ExampleAction(BaseAction):
    action_name = "example_action" # Unique identifier for the action
    action_description = "This is a sample action" # Action description
    activation_type = ActionActivationType.ALWAYS # Here using ALWAYS as example
    mode_enable = ChatMode.ALL # Generally use ALL, meaning available in all chat modes
    associated_types = ["text", "emoji", ...] # Associated types
    parallel_action = False # Whether to allow parallel execution with other Actions
    action_parameters = {"param1": "Description of param1", "param2": "Description of param2", ...}
    # Action use case descriptions - helps LLM judge when to "choose" to use
    action_require = ["Use case description 1", "Use case description 2", ...]

    async def execute(self) -> Tuple[bool, str]:
        """
        Main logic for executing Action
        
        Returns:
            Tuple[bool, str]: A tuple with two elements
                - bool: Whether execution was successful (True=success, False=failure)
                - str: Brief description of execution result (for logging)
        
        Notes:
            - Use self.send_text() and similar methods to send messages to users
            - The description in return value is only for internal logging, won't be sent to users
        """
        # Send message to user
        await self.send_text("This is the message sent to user")
        
        # Return execution result (for logging)
        return True, "Successfully executed XX action"
```

#### execute() Return Value vs Command Return Value

⚠️ **Important: Action and Command return values are different!**

| Component Type | Return Value | Explanation |
|----------|----------|------|
| **Action** | `Tuple[bool, str]` | 2 elements: success flag, log description |
| **Command** | `Tuple[bool, Optional[str], bool]` | 3 elements: success flag, log description, intercept flag |

```python
# Action return value
async def execute(self) -> Tuple[bool, str]:
    await self.send_text("Message to user")
    return True, "Log: Executed XX action"  # 2 elements

# Command return value
async def execute(self, args: CommandArgs) -> Tuple[bool, Optional[str], bool]:
    await self.send_text("Message to user")
    return True, "Log: Executed XX command", True  # 3 elements
```

---

#### associated_types: The types of messages this Action will send, such as text, emoji, etc.

This part is passed by Adapter to the handler.

Taking MoFox-Bot-Napcat-Adapter as example, optional items are as follows:
| Type | Explanation | Format |
| --- | --- | --- |
| text | Text message | str |
| emoji | Emoji message | str: Base64 without headers of emoji package|
| image | Image message | str: Base64 without headers of image |
| reply | Reply message | str: Message ID being replied to |
| voice | Voice message | str: Base64 without headers of wav format voice |
| command | Command message | See Adapter documentation |
| voiceurl | Voice URL message | str: URL of wav format voice |
| music | Music message | str: Music ID on NetEase Cloud Music |
| videourl | Video URL message | str: URL of video |
| file | File message | str: File path |

**Please note that different handlers may have different supported message types. Pay attention when developing.**

#### action_parameters: Parameter description for this Action.
This is a dictionary where the key is parameter name and value is parameter description. This field helps LLM understand how to use this Action, and LLM returns corresponding parameters, which are finally passed to the Action's **`action_data`** property. The format is exactly the same as what you defined **(unless LLM messes up and returns incorrect content)**.

---

## Component Info Registration Instructions

### Auto-Generate ComponentInfo (Recommended)

In most cases, you don't need to manually create `ActionInfo` objects. The system provides `get_action_info()` method to auto-generate:

```python
# Recommended way - auto-generate
class HelloAction(BaseAction):
    action_name = "hello"
    action_description = "Greeting action"
    # ... other configurations ...

# Register in plugin
def get_plugin_components(self):
    return [
        (HelloAction.get_action_info(), HelloAction),  # Auto-generate ActionInfo
    ]
```

### Manually Create ActionInfo (Advanced Usage)

⚠️ **Important: If manually creating ActionInfo, must specify `component_type` parameter!**

When you need to customize `ActionInfo` (for example, dynamically generate components), must manually specify `component_type`:

```python
from src.plugin_system import ActionInfo, ComponentType

# ❌ Wrong - Missing component_type
action_info = ActionInfo(
    name="hello",
    description="Greeting action"
    # Error: will report "missing required argument: 'component_type'"
)

# ✅ Correct - Must specify component_type
action_info = ActionInfo(
    name="hello",
    description="Greeting action",
    component_type=ComponentType.ACTION  # Must specify!
)
```

**Why manually specify?**

- `get_action_info()` method automatically sets `component_type`
- But when manually creating, system cannot auto-infer type, must explicitly specify

**When need to manually create?**

- Dynamically generate components
- Customize `get_handler_info()` method
- Need special ComponentInfo configuration

In most cases, just use `get_action_info()` directly, no need to manually create.

---

## 🎯 Action Call Decision Mechanism

Action adopts a **two-level decision mechanism** to optimize performance and decision quality:

> Design Purpose: When loading many plugins, reduce LLM decision pressure, avoid MoFox_Bot being confused by too many options.

**Level One: Activation Control**

Activation determines whether MoFox_Bot **"knows"** about this Action's existence, i.e., whether this Action enters the decision candidate pool. Actions that are not activated will never be chosen by MoFox_Bot.

**Level Two: Usage Decision**

After Action activation, usage conditions determine when MoFox_Bot will actually **"choose"** to use this Action.

---

## 🆕 New Activation Mechanism (Recommended)

From now on, it's recommended to use the **`go_activate()` method** to customize Action activation logic. This approach is more flexible and powerful!

### Quick Example

```python
class MyAction(BaseAction):
    action_name = "my_action"
    action_description = "My custom Action"
    
    async def go_activate(self, llm_judge_model=None) -> bool:
        """Judge whether to activate this Action
        
        Note: Chat content is automatically retrieved from instance properties, no need to pass manually
        """
        # Keyword activation
        if await self._keyword_match(["hello", "hi"]):
            return True
        
        # Or 10% random activation probability
        return await self._random_activation(0.1)
    
    async def execute(self) -> tuple[bool, str]:
        await self.send_text("Hello!")
        return True, "Sent successfully"
```

**Provided utility functions:**
- `_random_activation(probability)` - Random activation
- `_keyword_match(keywords)` - Keyword matching (auto-get chat content)
- `_llm_judge_activation(judge_prompt, llm_judge_model)` - LLM smart judging (auto-get chat content)

**📚 Complete Guide:** See [Action Activation Mechanism Refactoring Guide](./action-activation-guide.md) for details and more examples.

---

## 📜 Old Activation Mechanism (Deprecated but Still Compatible)

> ⚠️ **Note:** The following activation type configuration methods are deprecated but still compatible.  
> Recommended to use new `go_activate()` method for more flexible activation logic.

### Decision Parameter Details 🔧

#### Level One: ActivationType Explanation

| Activation Type | Explanation | Use Case |
| ----------- | ---------------------------------------- | ---------------------- |
| [`NEVER`](#never-activation)     | Never activate, Action invisible to MoFox_Bot               | Temporarily disable an Action      |
| [`ALWAYS`](#always-activation)    | Always activate, Action always in MoFox_Bot's candidate pool        | Core features like reply, no reply |
| [`LLM_JUDGE`](#llm_judge-activation) | Intelligently judge via LLM whether current context needs this Action | Complex scenarios needing smart judgment   |
| `RANDOM`    | Decide activation based on random probability                   | Add randomness to behavior     |
| `KEYWORD`   | Activate when detecting specific keywords                   | Features with clear trigger conditions       |

---

## 🆕 Advanced Features

See [Action Activation Mechanism Refactoring Guide](./action-activation-guide.md) for detailed explanation of new activation mechanisms and comprehensive examples.

---

## 📚 Full Reference

See complete examples in `plugins/hello_world_plugin/` and `src/plugins/built_in/`.
