# Action Activation Mechanism Refactoring Guide (Summarized)

For full details, see `docs/plugins/action-activation-guide.md`.

## New Activation Method

Override `go_activate()` method for custom activation logic:

```python
class MyAction(BaseAction):
    action_name = "my_action"
    
    async def go_activate(self, llm_judge_model=None) -> bool:
        # Implement your activation logic
        if await self._keyword_match(["hello"]):
            return True
        return await self._random_activation(0.1)
    
    async def execute(self) -> tuple[bool, str]:
        await self.send_text("Action executed!")
        return True, "Success"
```

## Tool Functions

### Random Activation
```python
return await self._random_activation(0.3)  # 30% probability
```

### Keyword Matching
```python
return await self._keyword_match(["key1", "key2"], case_sensitive=False)
```

### LLM Intelligent Judging
```python
return await self._llm_judge_activation(
    judge_prompt="When to activate this action?",
    llm_judge_model=llm_judge_model
)
```

## Migration from Old Style

| Old | New |
|-----|-----|
| `ActionActivationType.ALWAYS` | `return True` |
| `ActionActivationType.NEVER` | `return False` |
| `ActionActivationType.RANDOM` | `return await self._random_activation(prob)` |
| `ActionActivationType.KEYWORD` | `return await self._keyword_match(keys)` |
| `ActionActivationType.LLM_JUDGE` | `return await self._llm_judge_activation(...)` |

## Best Practices

✅ Keep `go_activate()` simple and fast
✅ Use keywords for fast decisions
✅ Use LLM only when needed
✅ Combine multiple strategies
❌ Don't do heavy computation in activation
❌ Don't make API calls in activation
