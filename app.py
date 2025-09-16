import os
import json
from flask import Flask, request, render_template, Response, stream_with_context
from flask_cors import CORS
from openai import OpenAI
from dotenv import load_dotenv

load_dotenv()

app = Flask(__name__)
CORS(app)

client = OpenAI(
    api_key=os.getenv("DASHSCOPE_API_KEY"),
    base_url="https://dashscope.aliyuncs.com/compatible-mode/v1",
)

@app.route("/")
def read_root():
    return render_template("index.html")

@app.route("/api/chat", methods=["POST"])
def chat():
    chat_request = request.json
    history = chat_request.get('history', [])
    enable_thinking = chat_request.get('enable_thinking', False)

    def stream_generator():
        try:
            extra_body = {}
            if enable_thinking:
                extra_body["enable_thinking"] = True

            completion = client.chat.completions.create(
                model="qwen-plus-latest",
                messages=history,
                stream=True,
                extra_body=extra_body,
                stream_options={"include_usage": True},
                temperature=0.3,
                presence_penalty=0.3,
                extra_headers={
                    'X-DashScope-DataInspection': '{"input":"cip","output":"cip"}'
                }
            )

            is_answering = False
            full_answer = ""

            for chunk in completion:
                if not chunk.choices:
                    if chunk.usage:
                        print(f"\n[Usage Info] Tokens - Prompt: {chunk.usage.prompt_tokens}, Completion: {chunk.usage.completion_tokens}, Total: {chunk.usage.total_tokens}")
                    continue

                delta = chunk.choices[0].delta
                response_chunk = {"type": None, "content": ""}

                if hasattr(delta, "reasoning_content") and delta.reasoning_content:
                    if not is_answering:
                        response_chunk["type"] = "thinking"
                        response_chunk["content"] = delta.reasoning_content

                elif hasattr(delta, "content") and delta.content is not None:
                    if not is_answering:
                        start_signal = {"type": "start_answer", "content": ""}
                        yield f"data: {json.dumps(start_signal)}\n\n"
                        is_answering = True

                    response_chunk["type"] = "answer"
                    response_chunk["content"] = delta.content
                    full_answer += delta.content

                if response_chunk["type"]:
                    yield f"data: {json.dumps(response_chunk)}\n\n"

            end_signal = {"type": "end", "full_answer": full_answer}
            yield f"data: {json.dumps(end_signal)}\n\n"

        except Exception as e:
            print(f"发生错误: {e}")
            error_signal = {"type": "error", "content": str(e)}
            yield f"data: {json.dumps(error_signal)}\n\n"

    return Response(stream_with_context(stream_generator()), mimetype="text/event-stream")

if __name__ == "__main__":
    app.run(host="127.0.0.1", port=8000, debug=True)
