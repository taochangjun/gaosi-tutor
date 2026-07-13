from functools import lru_cache

from openai import OpenAI

from ..settings import get_settings


@lru_cache()
def get_llm_client() -> OpenAI:
    settings = get_settings()
    return OpenAI(api_key=settings.deepseek_api_key, base_url=settings.deepseek_base_url)


def chat(messages: list[dict], *, model: str, max_tokens: int = 600):
    response = get_llm_client().chat.completions.create(
        model=model,
        messages=messages,
        stream=False,
        max_tokens=max_tokens,
    )
    return response.choices[0].message


def chat_stream(messages: list[dict], *, model: str, max_tokens: int = 600):
    stream = get_llm_client().chat.completions.create(
        model=model,
        messages=messages,
        stream=True,
        max_tokens=max_tokens,
    )
    for chunk in stream:
        if not chunk.choices:
            continue
        delta = chunk.choices[0].delta.content
        if delta:
            yield delta


def chat_with_tools(messages: list[dict], *, model: str, tools: list[dict]):
    response = get_llm_client().chat.completions.create(
        model=model,
        messages=messages,
        stream=False,
        tools=tools,
    )
    return response.choices[0].message
