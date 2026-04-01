import json
import httpx
from agent.browser import BrowserController
from agent.tools import TOOLS
from dotenv import load_dotenv
import os

load_dotenv()

OPENROUTER_API_KEY = os.getenv("OPENROUTER_API_KEY")

OPENROUTER_URL = "https://openrouter.ai/api/v1/chat/completions"

MODEL = "google/gemma-3-27b-it:free"

SYSTEM_PROMPT = """You are a browser automation agent controlling a real Chromium browser.

Each turn you receive:
- The current page URL and title
- A screenshot of what the browser currently shows
- A numbered list of visible interactive elements with their (x, y) coordinates

Rules:
- Call exactly ONE tool per turn.
- Always fill in the `reason` field explaining your decision.
- If a page is loading or the state looks the same after your last action, wait (call scroll down then re-observe).
- When the task is fully complete, call `done` with a clear summary of what was accomplished.
- If you cannot complete the task after 5 attempts, call `done` with an explanation of what blocked you.
"""

class BrowserAgent:
    def __init__(self, emit_log):
        self.emit_log = emit_log
        self.browser = BrowserController()
        self.messages = []
        import os
        self.api_key = os.environ.get("OPENROUTER_API_KEY", OPENROUTER_API_KEY)

    async def start(self):
        await self.emit_log("Starting browser...")
        await self.browser.start()
        await self.emit_log("Browser ready.")

    async def stop(self):
        await self.browser.stop()

    async def _call_llm(self) -> dict:
        headers = {
            "Authorization": f"Bearer {self.api_key}",
            "Content-Type": "application/json",
            "HTTP-Referer": "https://github.com/dipakkhade/browser-agent",
            "X-Title": "Browser Agent",
        }
        payload = {
            "model": MODEL,
            "max_tokens": 1024,
            "tools": TOOLS,
            "tool_choice": "auto",
            "messages": [{"role": "system", "content": SYSTEM_PROMPT}] + self.messages,
        }

        async with httpx.AsyncClient(timeout=60) as client:
            print("REQUEST URL:", OPENROUTER_URL)

            resp = await client.post(OPENROUTER_URL, headers=headers, json=payload)

            print("STATUS CODE:", resp.status_code)
            print("RESPONSE TEXT:", resp.text)

            resp.raise_for_status()
            return resp.json()

    async def _execute_tool(self, name: str, args: dict) -> str:
        try:
            if name == "navigate":
                await self.emit_log(f"Navigate -> {args['url']}")
                await self.browser.navigate(args["url"])
                return f"Navigated to {args['url']}"
            elif name == "click":
                await self.emit_log(f"Click ({args['x']}, {args['y']}) - {args.get('reason','')}")
                await self.browser.click(args["x"], args["y"])
                return f"Clicked at ({args['x']}, {args['y']})"
            elif name == "type_text":
                await self.emit_log(f"Type '{args['text'][:40]}' at ({args['x']}, {args['y']})")
                await self.browser.type_text(args["x"], args["y"], args["text"])
                return f"Typed '{args['text']}'"
            elif name == "press_key":
                await self.emit_log(f"Press key: {args['key']}")
                await self.browser.press_key(args["key"])
                return f"Pressed {args['key']}"
            elif name == "scroll":
                await self.emit_log(f"Scroll {args['direction']} {args.get('amount', 400)}px")
                await self.browser.scroll(args["direction"], args.get("amount", 400))
                return f"Scrolled {args['direction']}"
            elif name == "done":
                return "DONE"
            else:
                return f"Unknown tool: {name}"
        except Exception as e:
            return f"Error in {name}: {e}"

    async def run(self, task: str, max_steps: int = 25) -> str:
        await self.emit_log(f"Task: {task}")
        self.messages = []

        for step in range(1, max_steps + 1):
            await self.emit_log(f"\n-- Step {step} --")

            state = await self.browser.get_state()
            await self.emit_log(f"URL: {state['url'][:70]}")

            elements_text = "\n".join(
                f"  [{el['id']}] <{el['tag']}> \"{el['text']}\" at ({el['x']},{el['y']})"
                for el in state["elements"]
            )

            user_content = [
                {
                    "type": "image_url",
                    "image_url": {
                        "url": f"data:image/png;base64,{state['screenshot_b64']}"
                    }
                },
                {
                    "type": "text",
                    "text": (
                        f"URL: {state['url']}\n"
                        f"Title: {state['title']}\n\n"
                        f"Visible interactive elements:\n{elements_text}\n\n"
                        f"Task: {task}"
                    )
                }
            ]

            self.messages.append({"role": "user", "content": user_content})

            try:
                response = await self._call_llm()
            except Exception as e:
                await self.emit_log(f"LLM error: {e}")
                break

            choice = response["choices"][0]
            message = choice["message"]
            self.messages.append(message)

            tool_calls = message.get("tool_calls") or []
            if not tool_calls:
                text = message.get("content", "No tool call returned.")
                await self.emit_log(f"{text}")
                return text

            tc = tool_calls[0]
            tool_name = tc["function"]["name"]
            tool_args = json.loads(tc["function"]["arguments"])

            result = await self._execute_tool(tool_name, tool_args)

            self.messages.append({
                "role": "tool",
                "tool_call_id": tc["id"],
                "content": result,
            })

            if result == "DONE":
                final = tool_args.get("result", "Task complete.")
                await self.emit_log(f"\nDone: {final}")
                return final

        await self.emit_log("Max steps reached without completion.")
        return "Max steps reached."
