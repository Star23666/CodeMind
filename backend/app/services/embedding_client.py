import hashlib
import math

from app.core.config import settings


class EmbeddingClient:
    local_dimension = 384

    def embed_texts(self, texts: list[str]) -> list[list[float]]:
        if not texts:
            return []

        if settings.embedding_api_key and settings.embedding_model:
            return self._embed_with_api(texts)

        return [self._embed_locally(text) for text in texts]

    def _embed_with_api(self, texts: list[str]) -> list[list[float]]:
        from openai import OpenAI

        client_kwargs = {"api_key": settings.embedding_api_key}
        if settings.embedding_base_url:
            client_kwargs["base_url"] = settings.embedding_base_url

        client = OpenAI(**client_kwargs)
        response = client.embeddings.create(model=settings.embedding_model, input=texts)
        return [list(item.embedding) for item in response.data]

    def _embed_locally(self, text: str) -> list[float]:
        vector = [0.0] * self.local_dimension
        tokens = self._tokenize(text)

        if not tokens:
            tokens = [text]

        for token in tokens:
            digest = hashlib.sha256(token.encode("utf-8")).digest()
            index = int.from_bytes(digest[:4], "big") % self.local_dimension
            sign = 1.0 if digest[4] % 2 == 0 else -1.0
            vector[index] += sign

        norm = math.sqrt(sum(value * value for value in vector))
        if norm == 0:
            return vector

        return [value / norm for value in vector]

    def _tokenize(self, text: str) -> list[str]:
        lowered = text.lower()
        ascii_tokens: list[str] = []
        current: list[str] = []
        cjk_chars: list[str] = []

        for char in lowered:
            if char.isascii() and char.isalnum():
                current.append(char)
                continue

            if current:
                ascii_tokens.append("".join(current))
                current = []

            if "\u4e00" <= char <= "\u9fff":
                cjk_chars.append(char)

        if current:
            ascii_tokens.append("".join(current))

        cjk_tokens = ["".join(cjk_chars[index : index + 2]) for index in range(max(len(cjk_chars) - 1, 0))]
        return ascii_tokens + cjk_tokens


embedding_client = EmbeddingClient()
