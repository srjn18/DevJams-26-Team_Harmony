"""
Script to test and access Google Gemini integration.
Reads credentials from .env and makes a test request.
"""

import os
import sys

try:
    from dotenv import load_dotenv
    load_dotenv()
except ImportError:
    pass

try:
    from google import genai
except ImportError:
    print("ERROR: 'google-genai' package is not installed. Please run: pip install google-genai python-dotenv")
    sys.exit(1)


def get_llm_config():
    """Retrieve Gemini configuration from environment variables."""
    api_key = os.getenv("GEMINI_API_KEY")
    model = os.getenv("LLM_MODEL", "gemini-3.6-flash")
    
    if not api_key or api_key == "your_gemini_api_key_here":
        print("\n[WARNING] GEMINI_API_KEY is missing or set to a placeholder in .env!")
        print("Please edit your '.env' file with your actual key:")
        print("  GEMINI_API_KEY=AIzaSy...")
        print("  LLM_MODEL=gemini-3.6-flash\n")
    
    return api_key, model


def call_gemini_chat(prompt: str, system_prompt: str = "You are a helpful assistant.", model: str = None) -> str:
    """
    Send a prompt to Gemini and return the response text.
    """
    api_key, default_model = get_llm_config()
    selected_model = model or default_model

    if not api_key or api_key == "your_gemini_api_key_here":
        raise ValueError("GEMINI_API_KEY is not configured properly in environment or .env file.")

    client = genai.Client(api_key=api_key)

    print(f"Connecting to Gemini model '{selected_model}'...")
    try:
        response = client.models.generate_content(
            model=selected_model,
            contents=[prompt],
            config=genai.types.GenerateContentConfig(
                system_instruction=system_prompt,
                temperature=float(os.getenv("LLM_TEMPERATURE", 0))
            )
        )
        return response.text
    except Exception as e:
        raise e


if __name__ == "__main__":
    print("=== Gemini API Connection Test ===")
    api_key, model = get_llm_config()

    if not api_key or api_key == "your_gemini_api_key_here":
        sys.exit(1)

    test_prompt = "Hello! Please reply with a short confirmation message that Gemini integration works."
    print(f"\nUser Prompt: {test_prompt}\n")

    try:
        reply = call_gemini_chat(test_prompt, model=model)
        print("=== Gemini Response ===")
        print(reply)
        print("\n[SUCCESS] Gemini LLM connection works!")
    except Exception as e:
        print(f"\n[ERROR] Failed to connect to Gemini: {e}")
