# Custom Pack Example — SummariserPack

This example shows how to build and wire up a custom domain pack.

## Register and use

```python
from platform.registry import PackRegistry
from examples.custom_pack.pack import SummariserPack

# Register once at application startup (not in platform/__init__.py)
PackRegistry.register(SummariserPack)

# Retrieve and instantiate
Pack = PackRegistry.get("summariser")
pack = Pack(run_id="my-run", llm=llm, checkpointer=checkpointer)

# Synchronous
result = pack.run("Your long text here...")

# Asynchronous
result = await pack.arun("Your long text here...")

# Streaming
async for event in pack.stream_events("Your long text here..."):
    print(event)
```

## Via API (after registration at startup)

```
POST /packs/summariser/run
{"text": "Your long text here...", "bullet_count": 3}
```
