"""
TCP server - listens on localhost:9000.
Protocol (newline-delimited JSON):
  Client -> Server:  {"task": "search for X and tell me the first result"}
  Server -> Client:  {"log": "Navigate -> https://..."}\n  (streamed, one per line)
                    {"done": "The first result is..."}\n    (final message)
"""

import asyncio
import json
import os
from agent import BrowserAgent

HOST = "127.0.0.1"
PORT = 9000

async def handle_client(reader: asyncio.StreamReader, writer: asyncio.StreamWriter):
    addr = writer.get_extra_info("peername")
    print(f"[server] connection from {addr}")

    try:
        raw = await reader.readline()
        if not raw:
            return
        request = json.loads(raw.decode())
        task = request.get("task", "").strip()
        if not task:
            writer.write(b'{"error": "empty task"}\n')
            await writer.drain()
            return

        async def emit_log(line: str):
            msg = json.dumps({"log": line}) + "\n"
            writer.write(msg.encode())
            await writer.drain()

        agent = BrowserAgent(emit_log=emit_log)
        await agent.start()
        try:
            result = await agent.run(task)
        finally:
            await agent.stop()

        writer.write((json.dumps({"done": result}) + "\n").encode())
        await writer.drain()

    except Exception as e:
        writer.write((json.dumps({"error": str(e)}) + "\n").encode())
        await writer.drain()
    finally:
        writer.close()
        await writer.wait_closed()

async def main():
    server = await asyncio.start_server(handle_client, HOST, PORT)
    print(f"[server] listening on {HOST}:{PORT}")
    async with server:
        await server.serve_forever()

if __name__ == "__main__":
    asyncio.run(main())
