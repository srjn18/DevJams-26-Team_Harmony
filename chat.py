"""
Interactive Terminal Chat with Google Gemini.
Run this script to chat directly in your terminal:
    python chat.py
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


def main():
    api_key = os.getenv("GEMINI_API_KEY")
    model = os.getenv("LLM_MODEL", "gemini-3.6-flash")

    if not api_key or api_key == "your_gemini_api_key_here":
        print("\n[ERROR] GEMINI_API_KEY is not configured in .env!")
        print("Please add your key to '.env': GEMINI_API_KEY=AIzaSy...")
        sys.exit(1)

    client = genai.Client(api_key=api_key)

    print("==========================================================")
    print(f" Interactive Terminal Chat - Google Gemini ({model})")
    print(" Type your message and press Enter.")
    print(" Type 'exit' or 'quit' to end the session.")
    print("==========================================================\n")

    chat = client.chats.create(
        model=model,
        config=genai.types.GenerateContentConfig(
            system_instruction="You are a helpful, knowledgeable AI assistant.",
            temperature=float(os.getenv("LLM_TEMPERATURE", 0.7))
        )
    )

    while True:
        try:
            user_input = input("You > ").strip()
            if not user_input:
                continue

            if user_input.lower() in ("exit", "quit", "q"):
                print("\nEnding chat session. Goodbye!")
                break

            print("\nGemini is thinking...", end="", flush=True)
            
            response = chat.send_message(user_input)
            assistant_reply = response.text

            print("\rGemini > " + assistant_reply + "\n")

        except KeyboardInterrupt:
            print("\n\nChat session interrupted. Goodbye!")
            break
        except Exception as e:
            print(f"\n\n[ERROR] {e}\n")


if __name__ == "__main__":
    main()
