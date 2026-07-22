import os
from dotenv import load_dotenv

load_dotenv()

# -------------------------
# Conversation Configuration
# -------------------------

SESSION_TIMEOUT_MINUTES = 30
MAX_HISTORY_MESSAGES = 20

# -------------------------
# LLM Configuration
# -------------------------

GROQ_API_KEY = os.getenv("GROQ_API_KEY")