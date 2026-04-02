import json
import queue
from flask import Flask, request, Response
from agent.agent import BrowserAgent
import asyncio

app = Flask(__name__)

tasks = {}
task_id_counter = 0

@app.route("/task", methods=["POST"])
def create_task():
    global task_id_counter
    print('----------------------------------control at /task ----------------------------------')
    print(f'tasks -----------------{tasks}')
    print(f'task_id_counter --------------{task_id_counter}')
    data = request.get_json()
    task = data.get("task", "").strip()
    
    if not task:
        return {"error": "empty task"}, 400
    
    task_id = task_id_counter
    task_id_counter += 1
    
    task_queue = queue.Queue()
    tasks[task_id] = {"queue": task_queue, "completed": False}
    
    async def run_agent():
        async def emit_log(line):
            task_queue.put({"log": line})
        
        agent = BrowserAgent(emit_log=emit_log)
        try:
            await agent.start()
            result = await agent.run(task)
            task_queue.put({"done": result})
        finally:
            await agent.stop()
            tasks[task_id]["completed"] = True
    
    asyncio.run(run_agent())
    
    return {"task_id": task_id}

@app.route("/task/<int:task_id>/stream")
def stream_task(task_id):
    print('----------------------------------task/<int:task_id>/stream----------------------------------')
    if task_id not in tasks:
        return {"error": "task not found"}, 404
    
    task_data = tasks[task_id]
    print(f'task data ---------------------{task_data}')
    def generate():
        while True:
            try:
                msg = task_data["queue"].get(timeout=1)
                yield f"data: {json.dumps(msg)}\n\n"
                if "done" in msg:
                    break
            except queue.Empty:
                if task_data["completed"]:
                    break
                continue
    
    return Response(generate(), mimetype="text/event-stream")

def run():
    app.run(host="127.0.0.1", port=9000, threaded=True, use_reloader=False)

if __name__ == "__main__":
    run()
