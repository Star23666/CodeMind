from app.core.config import settings


class LlmClient:
    async def generate_answer(self, prompt: str) -> str:
        if not settings.llm_api_key or not settings.llm_model:
            return self.generate_local_fallback(prompt)

        from openai import AsyncOpenAI

        client_kwargs = {"api_key": settings.llm_api_key}
        if settings.llm_base_url:
            client_kwargs["base_url"] = settings.llm_base_url

        client = AsyncOpenAI(**client_kwargs)
        response = await client.chat.completions.create(
            model=settings.llm_model,
            messages=[
                {"role": "system", "content": "你是 CodeMind 的严谨知识库问答助手。"},
                {"role": "user", "content": prompt},
            ],
            temperature=0.2,
        )
        content = response.choices[0].message.content
        return content.strip() if content else "知识库中未找到足够依据。"

    def generate_local_fallback(self, prompt: str) -> str:
        source_lines = [
            line
            for line in prompt.splitlines()
            if line.startswith("内容：")
        ]
        if not source_lines:
            return "知识库中未找到足够依据。"

        answer_parts = ["当前未配置在线 LLM API，以下为基于检索片段生成的本地演示回答："]
        for index, line in enumerate(source_lines, start=1):
            answer_parts.append(f"{index}. {line.removeprefix('内容：')} [来源{index}]")
        return "\n".join(answer_parts)


llm_client = LlmClient()

