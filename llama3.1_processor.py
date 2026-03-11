import ollama
import json
import os

async def test_file_extraction():
    file_path = "test_transcript.txt"
    
    # 1. Check if file exists
    if not os.path.exists(file_path):
        print(f"❌ Error: {file_path} not found in this folder!")
        return

    print(f"📂 Reading {file_path}...")
    with open(file_path, "r", encoding="utf-8") as f:
        content = f.read()

    # 2. Prepare the prompt
    prompt = f"""
    The following is a meeting transcript. Extract a JSON array of objects for EVERY participant mentioned.
    Each object MUST have exactly these keys: "name", "batch_id", "project_id", "update".
    
    Transcript:
    {content}
    
    Return ONLY the raw JSON array.
    """

    try:
        print("🧠 Asking Llama 3.1 to process the file...")
        response = ollama.generate(model='llama3.1', prompt=prompt)
        
        raw_text = response['response'].strip()
        
        # 3. Parse and Print
        data = json.loads(raw_text)
        print("\n✅ AI EXTRACTION SUCCESSFUL:")
        print(json.dumps(data, indent=4)) # This makes the JSON look pretty
        
    except Exception as e:
        print(f"❌ Extraction Failed: {e}")
        print("Raw AI output was:")
        print(response.get('response', 'No response'))

if __name__ == "__main__":
    import asyncio
    asyncio.run(test_file_extraction())