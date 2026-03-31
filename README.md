# Browser Automation Agent

A browser automation tool with a Rust TUI frontend and Python backend using Playwright.

## Architecture

- **Rust TUI**: Terminal UI that accepts user prompts and streams live action logs
- **Python Backend**: HTTP server (Flask) that runs the browser automation loop using Playwright
- **LLM**: Uses OpenRouter free models (e.g., `google/gemini-2.0-flash-exp:free`)
- **Browser**: Runs in headed mode so you can watch every action in real time

## Project Structure

```
.
├── agent/                      # Python uv project
│   ├── pyproject.toml
│   ├── src/agent/             # Source package
│   │   ├── __init__.py
│   │   ├── main.py            # TCP server entry point
│   │   ├── browser.py         # Playwright controller
│   │   ├── agent.py           # LLM orchestration loop
│   │   └── tools.py           # Tool definitions for LLM
│   └── .env                   # Environment variables
├── tui/                       # Rust TUI
│   ├── Cargo.toml
│   └── src/
│       └── main.rs
├── README.md
└── .env                       # OpenRouter API key
```

## Setup

### 1. Get OpenRouter API Key

1. Sign up at https://openrouter.ai
2. Go to Keys and create a new key (free tier, no credit card needed)
3. Add it to `.env`:
   ```
   OPENROUTER_API_KEY=sk-or-v1-...
   ```

### 2. Install Python Dependencies

```bash
cd agent
uv sync
uv run playwright install chromium
```

### 3. Build the Rust TUI

```bash
cd tui
cargo build --release
```

The binary will be at `tui/target/release/browser-agent-tui`.

## Running

Open two terminals:

**Terminal 1 - Start the Python agent server:**
```bash
cd agent
uv run agent-server
```

**Terminal 2 - Start the Rust TUI:**
```bash
cd tui
./target/release/browser-agent-tui
```

Type any task into the input box and press Enter. The browser will open visibly, and every action the agent takes will stream live into the log panel.

## Choosing a Free Model

Edit `MODEL` in `agent/agent.py`. Recommended free options:

| Model | Notes |
|-------|-------|
| `google/gemini-2.0-flash-exp:free` | Fast, vision-capable, generous free quota |
| `qwen/qwen2-vl-7b-instruct:free` | Vision-capable, good at following instructions |
| `meta-llama/llama-3.1-8b-instruct:free` | No vision, but very fast for DOM-only mode |
| `mistralai/mistral-7b-instruct:free` | Solid fallback, no vision |

## Troubleshooting

**Browser doesn't open / Playwright error**
```bash
uv run playwright install chromium --with-deps
```

**LLM returns no tool calls**
Switch to a vision-capable model like `gemini-2.0-flash-exp:free`, or add `"tool_choice": "required"` to the payload in `_call_llm`.

**TUI can't connect to server**
Make sure `uv run python -m agent.main` is running before launching the TUI. Check the port isn't in use:
```bash
lsof -i :9000
```

**Rate limits on free tier**
OpenRouter free models have per-minute limits. Add a `await asyncio.sleep(2)` between steps in `agent.py` if you hit 429 errors.

**Page state feels stale**
Increase the `wait_for_timeout` values in `browser.py` for slower sites, or switch `wait_until` from `"domcontentloaded"` to `"networkidle"` in `navigate()`.
