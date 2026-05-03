import asyncio
from backend.config import settings
from backend.llm import get_llm, get_structured_llm
from pydantic import BaseModel

class Dummy(BaseModel):
    name: str

async def main():
    llm = get_llm()
    print("Normal LLM class:", type(llm).__name__)
    print("Fallbacks:", len(llm.fallbacks) if hasattr(llm, 'fallbacks') else 0)

    sllm = get_structured_llm(Dummy)
    print("Structured LLM class:", type(sllm).__name__)
    print("Fallbacks:", len(sllm.fallbacks) if hasattr(sllm, 'fallbacks') else 0)

asyncio.run(main())
