import ollama
import json
import re

MODEL_NAME = "qwen2.5:0.5b"

BATCH_REGEX = r"[A-Z]{2}-[A-Z]{2}-\d{3}"

def extract_batch_and_work(transcribed_text: str):
    """
    Extract batch_id and weekly_work using LLM with regex fallback.
    """

    prompt = f"""
You are a STRICT information extraction engine.

Rules:
- Respond ONLY with valid JSON
- No explanations
- No markdown
- No extra text

Extract:
1. batch_id (must match {BATCH_REGEX})
2. weekly_work (natural language summary)

Input text:
{transcribed_text}

Return JSON exactly like:
{{
  "batch_id": "",
  "weekly_work": ""
}}
"""

    response = ollama.chat(
        model=MODEL_NAME,
        messages=[{"role": "user", "content": prompt}]
    )

    content = response["message"]["content"]

    try:
        # Try JSON parse from model
        start = content.find("{")
        end = content.rfind("}") + 1
        data = json.loads(content[start:end])

        # 🔒 Hard safety: regex fallback for batch_id
        if not data.get("batch_id"):
            match = re.search(BATCH_REGEX, transcribed_text)
            data["batch_id"] = match.group(0) if match else None

        # Weekly work fallback
        if not data.get("weekly_work"):
            data["weekly_work"] = transcribed_text

        return data

    except Exception:
        # Absolute fallback (never crash pipeline)
        match = re.search(BATCH_REGEX, transcribed_text)
        return {
            "batch_id": match.group(0) if match else None,
            "weekly_work": transcribed_text
        }
