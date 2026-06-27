import os
import json
import google.generativeai as genai

def triage_user_intent(user_message: str) -> str:
    """
    Lightweight few-shot routing gatekeeper. 
    Classifies the user's incoming intent to prevent unnecessary multimodal execution.
    """
    # Fallback to model configuration using the established environment token
    api_key = os.environ.get("GEMINI_API_KEY")
    if not api_key:
        print("⚠️ [Router Warning] GEMINI_API_KEY missing. Defaulting to TEXT_RAG.")
        return "TEXT_RAG"

    genai.configure(api_key=api_key)
    
    # We use the fast Gemini 2.5 Flash for rapid triage gating
    model = genai.GenerativeModel('gemini-2.5-flash')

    system_routing_instruction = """
    You are an elite, high-speed routing gatekeeper for an enterprise asset compliance system.
    Your sole task is to classify the user's input intent into exactly one of two categories:
    
    - TEXT_RAG: The user is asking about corporate policies, rules, tracking statuses, or general questions. No active file/asset inspection is requested.
    - MULTIMODAL_VISION: The user is explicitly submitting an asset for inspection, reporting physical damage, uploading evidence, or initiating a forensic check on a physical device.

    Return ONLY a raw JSON object with a single key 'intent' containing either 'TEXT_RAG' or 'MULTIMODAL_VISION'. No markdown formatting, no prose.
    """

    # Few-Shot Examples to explicitly guide the gating matrix
    few_shot_prompt = f"""
    {system_routing_instruction}
    
    ---
    Example 1:
    User: "Can you tell me what POLICY-002 requires for broken laptops?"
    Output: {{"intent": "TEXT_RAG"}}
    
    Example 2:
    User: "Here is the photo of my smashed screen. Please process my claim."
    Output: {{"intent": "MULTIMODAL_VISION"}}
    
    Example 3:
    User: "How long do I have to submit a claim after a device breaks?"
    Output: {{"intent": "TEXT_RAG"}}

    Example 4:
    User: "Please run a forensic analysis on this attached damage asset picture."
    Output: {{"intent": "MULTIMODAL_VISION"}}
    ---
    
    Actual Input:
    User: "{user_message}"
    Output:
    """

    try:
        response = model.generate_content(
            few_shot_prompt,
            generation_config={"response_mime_type": "application/json"}
        )
        data = json.loads(response.text.strip())
        return data.get("intent", "TEXT_RAG")
    except Exception as e:
        print(f"⚠️ [Router Error] Gating failed ({e}). Defaulting to safety track: TEXT_RAG")
        return "TEXT_RAG"