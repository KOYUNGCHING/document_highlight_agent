"""List Gemini models with the same SDK used by the application."""
import os
from pathlib import Path
from dotenv import load_dotenv
from google import genai


def main():
    load_dotenv(Path(__file__).resolve().parent / ".env")
    with genai.Client(api_key=os.getenv("GEMINI_API_KEY")) as client:
        for model in client.models.list():
            print(model.name)


if __name__ == "__main__":
    main()
