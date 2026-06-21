import json
import os

try:
    from dotenv import load_dotenv
except ImportError:  # pragma: no cover - optional during early setup
    def load_dotenv() -> bool:
        return False


def parse_ai_response(text: str) -> dict:
    try:
        data = json.loads(text)
    except json.JSONDecodeError as exc:
        raise ValueError("AI response must be valid JSON.") from exc

    required_keys = {"speech", "vote", "reason"}
    missing_keys = required_keys - set(data.keys())
    if missing_keys:
        raise ValueError("AI response is missing required fields.")

    speech = data["speech"]
    vote = data["vote"]
    reason = data["reason"]

    if not isinstance(speech, str) or not speech.strip():
        raise ValueError("AI response speech must be a non-empty string.")
    if not isinstance(vote, int):
        raise ValueError("AI response vote must be an int.")
    if not isinstance(reason, str) or not reason.strip():
        raise ValueError("AI response reason must be a non-empty string.")

    return {
        "speech": speech.strip(),
        "vote": vote,
        "reason": reason.strip(),
    }


class LLMClient:
    def __init__(self) -> None:
        load_dotenv()
        self.provider = os.getenv("LLM_PROVIDER", "deepseek")
        self.api_key = os.getenv("DEEPSEEK_API_KEY", "")
        self.base_url = os.getenv("DEEPSEEK_BASE_URL", "https://api.deepseek.com")
        self.model = os.getenv("DEEPSEEK_MODEL", "deepseek-chat")
        self._available = bool(self.api_key)

    def is_available(self) -> bool:
        return self._available

    def generate(self, prompt: str) -> str:
        if not self.is_available():
            raise ValueError("LLM client is not available.")

        if self.provider != "deepseek":
            raise ValueError(f"Unsupported LLM provider: {self.provider}")

        try:
            from openai import OpenAI
        except ImportError as exc:  # pragma: no cover - dependency issue
            raise ValueError("OpenAI SDK is not installed.") from exc

        client = OpenAI(
            api_key=self.api_key,
            base_url=self.base_url,
        )
        response = client.chat.completions.create(
            model=self.model,
            messages=[{"role": "user", "content": prompt}],
        )
        content = response.choices[0].message.content
        if not isinstance(content, str) or not content.strip():
            raise ValueError("LLM returned empty content.")

        return content
