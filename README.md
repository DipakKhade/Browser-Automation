# Browser Automation Agent

Control a browser through natural language. Tell it what to do, watch it do it.

## What it does

- Rust TUI for the interface (logs stream in real-time)
- Python backend runs the automation via Playwright
- Connects to OpenRouter for LLM reasoning (free models work fine)
- Browser runs in headed mode so you can see everything

## Quick Start

**1. Get an OpenRouter key** at openrouter.ai (free tier available)

**2. Add your key to `.env`:**
```
OPENROUTER_API_KEY=sk-or-v1-...
```

**3. Install dependencies:**
```bash
cd agent && uv sync && uv run playwright install chromium
```

**4. Build the TUI:**
```bash
cd tui && cargo build --release
```

**5. Run** (two terminals needed):

Terminal 1:
```bash
cd agent && uv run agent-server
```

Terminal 2:
```bash
./tui/target/release/browser-agent-tui
```

Type a task, hit enter, watch it work.

## Free Models

Edit `MODEL` in `agent/agent.py`:

| Model | Best for |
|-------|----------|
| `google/gemini-2.0-flash-exp:free` | Fast, vision, most reliable free option |
| `qwen/qwen2-vl-7b-instruct:free` | Vision tasks |
| `meta-llama/llama-3.1-8b-instruct:free` | Text-only, fastest |

## Common Issues

**Browser won't launch:**
```bash
uv run playwright install chromium --with-deps
```

**Getting 429 rate limit errors:**
Add a small delay in `agent.py` between steps:
```python
await asyncio.sleep(2)
```

**Actions feel slow:**
Increase `wait_for_timeout` in `browser.py`, or switch `wait_until` to `"networkidle"` in `navigate()`.

**Stale page state:**
Increase `wait_for_timeout` values for slower sites.
