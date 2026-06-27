import os
import time
from google import genai
from google.genai import types

def get_gemini_client():
    api_key = os.environ.get("GEMINI_API_KEY")
    if not api_key:
        raise ValueError("❌ [Vision Error] GEMINI_API_KEY environment variable is missing!")
    return genai.Client(api_key=api_key)

def inspect_asset_damage(image_path: str) -> str:
    try:
        client = get_gemini_client()
        if not os.path.exists(image_path):
            return f"❌ [Vision Error] Target image path not found: {image_path}"
            
        print(f"👁️ Loading asset image: {image_path}...")
        with open(image_path, "rb") as f:
            image_bytes = f.read()
            
        forensic_prompt = "You are an elite enterprise forensic asset inspector working for NexusFlow. Analyze this image carefully and provide a rigorous review."
        
        # --- SMART EXPONENTIAL BACKOFF RETRY MECHANISM ---
        max_retries = 3
        base_delay = 5  # Start with a base delay of 5 seconds
        
        for attempt in range(max_retries):
            try:
                print(f"🧠 Transferring multimodal payload to Gemini 2.5 Flash (Attempt {attempt + 1}/{max_retries})...")
                
                response = client.models.generate_content(
                    model="gemini-2.5-flash",
                    contents=[
                        types.Part.from_bytes(data=image_bytes, mime_type="image/jpeg"),
                        forensic_prompt
                    ]
                )
                return response.text  # Success! Return the report immediately.
                
            except Exception as api_err:
                # Check if it's a temporary high demand / unavailable server issue
                if "503" in str(api_err) or "UNAVAILABLE" in str(api_err).upper():
                    if attempt < max_retries - 1:
                        # Calculation: base_delay * (2 ** attempt)
                        # Attempt 1 failed -> wait 5 * 1 = 5s
                        # Attempt 2 failed -> wait 5 * 2 = 10s
                        sleep_time = base_delay * (2 ** attempt)
                        
                        print(f"⚠️ Google API is slammed. Scaling back wait time... Retrying in {sleep_time} seconds...")
                        time.sleep(sleep_time)
                        continue
                # If it's a different error (like 403 or 400), don't bother retrying
                raise api_err
                
    except Exception as e:
        return f"❌ [Vision System Error] Processing failed: {str(e)}"

if __name__ == "__main__":
    print("✨ Vision Module Initialized and running clean execution...")
    print(inspect_asset_damage("/app/src/test_damage.jpg"))