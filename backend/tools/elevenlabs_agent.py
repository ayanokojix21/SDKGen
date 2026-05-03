import os
import logging
from typing import Optional
from backend.config import settings

log = logging.getLogger(__name__)

def _is_available() -> bool:
    """Check if ElevenLabs is configured."""
    return bool(settings.ELEVENLABS_API_KEY)

def _get_client():
    """Lazy-initialize the ElevenLabs client."""
    from elevenlabs.client import ElevenLabs
    return ElevenLabs(api_key=settings.ELEVENLABS_API_KEY)

async def create_doc_reader_agent(
    api_name: str, 
    language: str, 
    job_id: str,
    sdk_client_code: str = "",
    schema_json: str = "",
    target_url: str = "",
    page_content: str = ""
) -> Optional[str]:
    """
    Creates an ElevenLabs Conversational Agent configured as a Doc Reader
    for the newly generated SDK. Uploads the SDK code as knowledge base context.

    Returns the agent_id if successful, or None if ElevenLabs is not configured.
    """
    if not _is_available():
        log.info("[elevenlabs_agent] API key not set — skipping agent creation")
        return None

    import asyncio
    try:
        # Run synchronous ElevenLabs SDK calls in a thread
        agent_id = await asyncio.to_thread(
            _sync_create_and_configure_agent, 
            api_name, 
            language, 
            sdk_client_code,
            schema_json,
            target_url,
            page_content
        )
        log.info("[elevenlabs_agent] Created conversational agent with ID: %s", agent_id)
        return agent_id
    except Exception as exc:
        log.warning("[elevenlabs_agent] Agent creation failed (non-critical): %s", exc)
        return None

def _sync_create_and_configure_agent(
    api_name: str, 
    language: str, 
    sdk_client_code: str,
    schema_json: str,
    target_url: str,
    page_content: str
) -> str:
    """Synchronous implementation to create agent and upload KB."""
    client = _get_client()

    prompt = f"""
    You are a highly technical and helpful Conversational Doc Reader assistant.
    You are an expert on the {api_name} API and its newly generated {language} SDK.
    {"The user is currently reading this API documentation page: " + target_url if target_url else ""}
    Your goal is to help developers understand how to use the SDK, how to authenticate,
    and what endpoints are available.
    Keep your responses concise, friendly, and practical.
    If the user asks for examples, provide short, correct code snippets based on the SDK code in your knowledge base.
    Use the page context above to give relevant, specific answers about the documentation the user is reading.
    Respond in the language the user speaks to you in.
    """

    # 1. Create the Agent
    agent = client.conversational_ai.agents.create(
        name=f"SDK Assistant - {api_name}",
        conversation_config={
            "tts": {
                # We can swap this for any voice ID. "aMSt68OGf4xUZAnLpTU8" is the requested voice.
                "voice_id": "aMSt68OGf4xUZAnLpTU8", 
                "model_id": "eleven_flash_v2"
            },
            "agent": {
                "first_message": f"Hey there! I'm your {api_name} SDK assistant. What would you like to build?",
                "prompt": {
                    "prompt": prompt,
                }
            }
        }
    )
    
    agent_id = agent.agent_id

    # 2. Add Knowledge Base Documents (Optional but recommended for full context)
    # We upload the generated client code and the API schema.
    if sdk_client_code:
        try:
            client.conversational_ai.knowledge_base.text.create(
                agent_id=agent_id,
                name="client_code",
                text=sdk_client_code
            )
        except Exception as e:
            log.warning(f"Failed to upload client code to KB: {e}")

    if schema_json:
        try:
            client.conversational_ai.knowledge_base.text.create(
                agent_id=agent_id,
                name="api_schema",
                text=schema_json
            )
        except Exception as e:
            log.warning(f"Failed to upload schema to KB: {e}")

    if page_content:
        try:
            client.conversational_ai.knowledge_base.text.create(
                agent_id=agent_id,
                name="original_page_docs",
                text=page_content
            )
        except Exception as e:
            log.warning(f"Failed to upload page content to KB: {e}")

    return agent_id
