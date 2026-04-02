import json
import httpx
import re
from agent.browser import BrowserController
from dotenv import load_dotenv
import os
import time

load_dotenv(dotenv_path='/Users/dipakkhade/projects/Browser-Automation/agent/.env')

# OPENROUTER_API_KEY = os.getenv("OPENROUTER_API_KEY")


OPENROUTER_URL = "https://openrouter.ai/api/v1/chat/completions"

# MODEL = "google/gemma-3-27b-it:free"
MODELS = [
    "nvidia/nemotron-nano-12b-v2-vl:free",
    "google/gemma-3-12b-it:free",
    "openrouter/free",
    "google/gemma-3-27b-it:free",
]

SYSTEM_PROMPT = """You are a browser automation agent controlling a real Chromium browser.

Each turn you receive:
- The current page URL and title
- A screenshot of what the browser currently shows
- A numbered list of visible interactive elements with their (x, y) coordinates

You must respond with ONLY a JSON object in this exact format (no other text):

{
  "action": "action_name",
  "args": {
    // action-specific arguments
  }
}

Available actions:

1. navigate
   args: {"url": "https://..."}

2. click
   args: {"x": 100, "y": 200, "reason": "why clicking here"}

3. type_text
   args: {"x": 100, "y": 200, "text": "text to type"}

4. press_key
   args: {"key": "Enter|Tab|Escape|ArrowDown|etc"}

5. scroll
   args: {"direction": "up|down", "amount": 400}

6. done
   args: {"result": "summary of what was accomplished"}

Rules:
- Respond with ONLY the JSON object, no markdown, no explanation.
- Always provide a reason when clicking.
- When the task is fully complete, use the "done" action.
- If you cannot complete the task after 5 attempts, use "done" with an explanation.
"""

class BrowserAgent:
    def __init__(self, emit_log):
        self.emit_log = emit_log
        self.browser = BrowserController()
        self.messages = []
        self.api_key = OPENROUTER_API_KEY
        print('this is my key----', self.api_key)

    async def start(self):
        await self.emit_log("Starting browser...")

        await self.browser.start()
        time.sleep(2)
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

        for model in MODELS:
            payload = {
                "model": model,
                "max_tokens": 1024,
                "messages": [{"role": "system", "content": SYSTEM_PROMPT}] + self.messages,
            }
            async with httpx.AsyncClient(timeout=120) as client:
                resp = await client.post(OPENROUTER_URL, headers=headers, json=payload)
                if resp.status_code == 429:
                    await self.emit_log(f"Model {model} rate limited, trying next...")
                    continue
                resp.raise_for_status()
                return resp.json()

        raise Exception("All models rate limited. Try again later.")

    def _parse_action(self, content: str) -> tuple[str, dict]:
        content = content.strip()
        
        json_match = re.search(r'```json\s*(.*?)\s*```', content, re.DOTALL)
        if json_match:
            content = json_match.group(1)
        else:
            json_match = re.search(r'\{.*\}', content, re.DOTALL)
            if json_match:
                content = json_match.group(0)
        
        parsed = json.loads(content)
        action = parsed.get("action", "")
        args = parsed.get("args", {})
        return action, args

    async def _execute_action(self, name: str, args: dict) -> str:
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
                return f"Unknown action: {name}"
        except Exception as e:
            return f"Error in {name}: {e}"

    async def run(self, task: str, max_steps: int = 25) -> str:
        print('inside the run run========', task)
        await self.emit_log(f"Task: {task}")
        self.messages = []

        for step in range(1, max_steps + 1):
            await self.emit_log(f"\n-- Step {step} --")

            state = await self.browser.get_state()
            print('=====state=====', state['url'])
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

            # print('============-================>>> user_content=======', user_content)
            self.messages.append({"role": "user", "content": user_content})

            try:
                response = await self._call_llm()
                print('llm response -----------', response)
            except Exception as e:
                await self.emit_log(f"LLM error: {e}")
                break

            choice = response["choices"][0]
            message = choice["message"]
            content = message.get("content", "")

            self.messages.append({"role": "assistant", "content": content})

            try:
                action, action_args = self._parse_action(content)
            except json.JSONDecodeError as e:
                await self.emit_log(f"Failed to parse JSON: {e}")
                await self.emit_log(f"Response: {content[:200]}")
                break

            if not action:
                await self.emit_log(f"No action in response: {content[:100]}")
                break

            result = await self._execute_action(action, action_args)

            self.messages.append({
                "role": "user",
                "content": result,
            })

            if result == "DONE":
                final = action_args.get("result", "Task complete.")
                await self.emit_log(f"\nDone: {final}")
                return final

        await self.emit_log("Max steps reached without completion.")
        return "Max steps reached."
