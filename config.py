from dotenv import load_dotenv
import os

load_dotenv()

OPENAI_API_KEY = os.getenv("OPENAI_API_KEY")
APP_NAME = os.getenv("APP_NAME", "Magicpin AI Agent")
DEBUG = os.getenv("DEBUG", "False") == "True"
HOST = os.getenv("HOST", "0.0.0.0")
PORT = int(os.getenv("PORT", 8000))