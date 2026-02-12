import os
from dotenv import load_dotenv
from openai import OpenAI

# Load .env file explicitly
load_dotenv()

api_key = os.getenv("OPENAI_API_KEY")

if not api_key:
    raise RuntimeError("OPENAI_API_KEY not found in environment")

client = OpenAI(api_key=api_key)


def generate_reply(
    user_message: str,
    history: str = "",
    business_name: str = "our business",
    business_goal: str = "help customers"
):
    system_prompt = f"""
You are a friendly WhatsApp assistant for {business_name}.

Your main goal is to {business_goal}.

Rules:
- Be polite, short, and friendly
- Use simple language
- Ask one question at a time
- Never mention AI or OpenAI
"""

    messages = [{"role": "system", "content": system_prompt}]

    if history:
        messages.append({"role": "assistant", "content": history})

    messages.append({"role": "user", "content": user_message})

    response = client.chat.completions.create(
        model="gpt-4o-mini",
        messages=messages,
        temperature=0.4
    )

    return response.choices[0].message.content.strip()
