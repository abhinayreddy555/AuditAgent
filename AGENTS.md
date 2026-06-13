# AGENTS.md — Claude Code Context

This file is read by Claude Code to understand conventions for this project.
For the full learning guide, diagrams, and phase explanations see [README.md](README.md).

---

## Project Summary

A LangGraph reconciliation agent built as an interactive learning session.
One working file (`main.py`) that grows one phase at a time.

## Key Conventions

- **Schemas before nodes.** Define all Pydantic models and `AgentState` before writing any node logic.
- **`with_structured_output()` always.** Never parse LLM free-text with regex or string splitting.
- **Deterministic logic in code, judgment in the LLM.** Filter by date in Python. Ask Claude whether two merchant names are the same vendor.
- **Low confidence → escalate, never auto-resolve.** Every LLM judgment call needs a human exit path.
- **Debug state first, then prompt.** Print `AgentState` at the failing node before touching the system prompt.

## Human-in-the-Loop Pattern

```python
app = graph.compile(checkpointer=MemorySaver(), interrupt_before=["human_review_node"])
app.invoke(state, config)               # run until interrupt
app.update_state(config, {...})         # inject human decisions
app.invoke(None, config)               # resume from checkpoint
```

## File Map

```
Agents/
├── README.md      ← learning guide, Mermaid diagram, phase explanations
├── AGENTS.md      ← this file — Claude Code context
├── PLAN.md        ← step-level task checklist
├── .env           ← API keys (never commit)
├── main.py        ← the agent, grows one phase at a time
└── .venv/         ← virtual environment
```

## Run Command

```
.venv\Scripts\python.exe main.py
```
