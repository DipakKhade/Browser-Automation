import base64
from playwright.async_api import async_playwright, Page

class BrowserController:
    def __init__(self):
        self.playwright = None
        self.browser = None
        self.page: Page = None

    async def start(self):
        self.playwright = await async_playwright().start()
        self.browser = await self.playwright.chromium.launch(
            headless=False,
            args=["--window-size=1280,800"]
        )
        context = await self.browser.new_context(viewport={"width": 1280, "height": 800})
        self.page = await context.new_page()

    async def stop(self):
        if self.browser:
            await self.browser.close()
        if self.playwright:
            await self.playwright.stop()

    async def get_state(self) -> dict:
        """
        Returns current page state:
        - screenshot as base64 PNG (for vision-capable models)
        - list of interactive elements with coordinates
        - current URL and title
        """
        screenshot = await self.page.screenshot(type="png", full_page=False)
        screenshot_b64 = base64.b64encode(screenshot).decode()

        elements = await self.page.evaluate("""() => {
            const results = [];
            const selector = 'a, button, input, select, textarea, [role="button"], [role="link"], [role="menuitem"]';
            document.querySelectorAll(selector).forEach((el, i) => {
                const rect = el.getBoundingClientRect();
                if (rect.width > 0 && rect.height > 0 && rect.top >= 0 && rect.top < window.innerHeight) {
                    results.push({
                        id: i,
                        tag: el.tagName.toLowerCase(),
                        text: (el.innerText || el.value || el.placeholder || el.title || '').trim().slice(0, 100),
                        type: el.type || '',
                        href: el.href || '',
                        x: Math.round(rect.x + rect.width / 2),
                        y: Math.round(rect.y + rect.height / 2),
                    });
                }
            });
            return results.slice(0, 50);
        }""")

        return {
            "url": self.page.url,
            "title": await self.page.title(),
            "screenshot_b64": screenshot_b64,
            "elements": elements,
        }

    async def navigate(self, url: str):
        await self.page.goto(url, wait_until="domcontentloaded", timeout=15000)
        await self.page.wait_for_timeout(1000)

    async def click(self, x: int, y: int):
        await self.page.mouse.click(x, y)
        await self.page.wait_for_timeout(1200)

    async def type_text(self, x: int, y: int, text: str):
        await self.page.mouse.click(x, y)
        await self.page.wait_for_timeout(300)
        await self.page.keyboard.type(text, delay=40)

    async def press_key(self, key: str):
        await self.page.keyboard.press(key)
        await self.page.wait_for_timeout(800)

    async def scroll(self, direction: str, amount: int = 400):
        delta = -amount if direction == "up" else amount
        await self.page.mouse.wheel(0, delta)
        await self.page.wait_for_timeout(500)
