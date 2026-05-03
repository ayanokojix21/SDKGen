"""
ChatGemmaVertexAI — LangChain ChatModel for Gemma 4 on Vertex AI Model Garden.

Uses the dedicated endpoint domain with the predict API.
The Model Garden vLLM container expects instances with 'prompt' field
and returns predictions with 'Prompt:...Output:...' format.
"""

import json
import logging
from typing import Any, Dict, List, Optional, Type

import google.auth
import google.auth.transport.requests
import httpx

from langchain_core.callbacks import CallbackManagerForLLMRun
from langchain_core.language_models.chat_models import BaseChatModel
from langchain_core.messages import AIMessage, BaseMessage, HumanMessage, SystemMessage
from langchain_core.outputs import ChatGeneration, ChatResult
from langchain_core.runnables import RunnableLambda
from pydantic import BaseModel, Field

log = logging.getLogger(__name__)


class ChatGemmaVertexAI(BaseChatModel):
    """
    LangChain ChatModel for a Gemma 4 model deployed via
    Vertex AI Model Garden (one-click deploy) on a dedicated endpoint.
    """

    project: str = Field(description="GCP project number (numeric)")
    location: str = Field(default="europe-west4")
    endpoint_id: str = Field(description="Vertex AI endpoint ID")
    dedicated_dns: str = Field(description="Dedicated endpoint DNS hostname")
    model_name: str = Field(default="google/gemma-4-31b-it")
    temperature: float = Field(default=0.0)
    max_tokens: int = Field(default=4096)

    @property
    def _llm_type(self) -> str:
        return "gemma-vertex-ai"

    def _get_headers(self) -> dict:
        credentials, _ = google.auth.default()
        credentials.refresh(google.auth.transport.requests.Request())
        return {
            "Authorization": f"Bearer {credentials.token}",
            "Content-Type": "application/json",
        }

    def _build_url(self) -> str:
        return (
            f"https://{self.dedicated_dns}/v1/"
            f"projects/{self.project}/locations/{self.location}/"
            f"endpoints/{self.endpoint_id}:rawPredict"
        )

    def _messages_to_chat_completions(self, messages: List[BaseMessage]) -> List[Dict]:
        """Convert LangChain messages to ChatCompletions format."""
        formatted_messages = []
        for msg in messages:
            if isinstance(msg, SystemMessage):
                formatted_messages.append({
                    "role": "system",
                    "content": [{"type": "text", "text": msg.content}]
                })
            elif isinstance(msg, HumanMessage):
                formatted_messages.append({
                    "role": "user",
                    "content": [{"type": "text", "text": msg.content}]
                })
            elif isinstance(msg, AIMessage):
                formatted_messages.append({
                    "role": "assistant",
                    "content": [{"type": "text", "text": msg.content}]
                })
            else:
                formatted_messages.append({
                    "role": "user",
                    "content": [{"type": "text", "text": str(msg.content)}]
                })
        return formatted_messages

    def _generate(
        self,
        messages: List[BaseMessage],
        stop: Optional[List[str]] = None,
        run_manager: Optional[CallbackManagerForLLMRun] = None,
        **kwargs: Any,
    ) -> ChatResult:
        formatted_messages = self._messages_to_chat_completions(messages)

        instance = {
            "@requestFormat": "chatCompletions",
            "messages": formatted_messages,
            "max_tokens": self.max_tokens,
            "temperature": self.temperature,
        }

        payload = {"instances": [instance]}
        headers = self._get_headers()

        log.info("[GemmaVertexAI] Calling Gemma 4 on dedicated endpoint")
        response = httpx.post(
            self._build_url(),
            content=json.dumps(payload).encode("utf-8"),
            headers=headers,
            timeout=180.0,
        )

        if response.status_code != 200:
            log.error("[GemmaVertexAI] %s: %s", response.status_code, response.text[:500])
            response.raise_for_status()

        data = response.json()
        predictions = data.get("predictions", {})

        # When using rawPredict with chatCompletions, predictions is a dict containing 'choices'
        choices = predictions.get("choices", [])
        if not choices:
            raise ValueError(f"Empty or invalid predictions from Gemma 4: {data}")

        content = choices[0].get("message", {}).get("content", "").strip()

        # Gemma 4 sometimes prefixes output with "thought\n" — only strip if leading
        if content.startswith("thought\n"):
            content = content[len("thought\n"):]
        content = content.strip()

        return ChatResult(
            generations=[
                ChatGeneration(message=AIMessage(content=content))
            ]
        )

    @property
    def _identifying_params(self) -> Dict[str, Any]:
        return {
            "model_name": self.model_name,
            "endpoint_id": self.endpoint_id,
            "dedicated_dns": self.dedicated_dns,
        }

    def with_structured_output(self, schema: Type[BaseModel], **kwargs):
        """
        Returns a Runnable that outputs a Pydantic object.
        Uses JSON prompt injection since tool calling is not configured.
        Uses async implementation to avoid blocking the event loop.
        """
        model = self

        async def _invoke_structured(messages):
            schema_json = json.dumps(schema.model_json_schema(), indent=2)
            json_instruction = (
                "\n\n## REQUIRED OUTPUT FORMAT\n"
                "You MUST respond with ONLY a valid JSON object. "
                "No markdown fences, no explanation, no extra text. "
                f"Match this schema exactly:\n{schema_json}"
            )

            modified = []
            found_system = False
            for msg in messages:
                if isinstance(msg, SystemMessage) and not found_system:
                    modified.append(
                        SystemMessage(content=msg.content + json_instruction)
                    )
                    found_system = True
                else:
                    modified.append(msg)

            if not found_system:
                modified.insert(0, SystemMessage(content=json_instruction))

            result = await model.ainvoke(modified)
            content = _extract_json(result.content)
            return schema.model_validate_json(content)

        return RunnableLambda(_invoke_structured)


def _extract_json(text: str) -> str:
    """Robustly extract JSON from model output."""
    text = text.strip()

    if "```json" in text:
        text = text.split("```json", 1)[1].split("```", 1)[0].strip()
    elif "```" in text:
        text = text.split("```", 1)[1].split("```", 1)[0].strip()

    if not text.startswith("{"):
        start = text.find("{")
        if start != -1:
            depth = 0
            for i, ch in enumerate(text[start:], start):
                if ch == "{":
                    depth += 1
                elif ch == "}":
                    depth -= 1
                    if depth == 0:
                        text = text[start : i + 1]
                        break

    return text.strip()
