from __future__ import annotations

import json
from typing import Annotated

from kosong import generate
from kosong.chat_provider import ChatProvider
from kosong.message import Message
from pydantic import BaseModel, Field

from kimi_cli.auth.oauth import OAuthManager
from kimi_cli.config import load_config
from kimi_cli.knowledge.models import Category, TemporalType
from kimi_cli.llm import create_llm


class ClassificationResult(BaseModel):
    title: str
    description: str
    tags: list[str] = Field(default_factory=list)
    category: Category
    subcategory: str
    confidence: Annotated[float, Field(ge=0.0, le=1.0)]
    relevance_score: Annotated[int, Field(ge=1, le=10)]
    temporal_type: TemporalType
    key_claims: Annotated[list[str], Field(max_length=5)] = Field(default_factory=list)


class Classifier:
    def __init__(self, model: str | None = None, chat_provider: ChatProvider | None = None):
        if chat_provider:
            self.chat_provider = chat_provider
        else:
            config = load_config()
            model_name = model or config.default_model

            if not model_name:
                raise ValueError("No model specified and no default model found in config.")

            if model_name not in config.models:
                raise ValueError(f"Model '{model_name}' not found in config.")

            llm_model = config.models[model_name]
            llm_provider = config.providers[llm_model.provider]

            oauth = OAuthManager(config)
            llm = create_llm(llm_provider, llm_model, oauth=oauth)
            if not llm:
                raise ValueError(f"Failed to create LLM for model '{model_name}'.")
            self.chat_provider = llm.chat_provider

    async def classify_category(self, content: str) -> Category:
        snippet = content[:2000]
        categories = ", ".join([c.value for c in Category])

        system_prompt = (
            "You are a knowledge base classifier. Your task is to classify the following content "
            f"into one of these categories: {categories}.\n\n"
            "Respond with ONLY the category name in lowercase."
        )

        result = await generate(
            self.chat_provider,
            system_prompt=system_prompt,
            tools=[],
            history=[Message(role="user", content=f"Content:\n{snippet}")],
        )

        category_str = result.message.extract_text().strip().lower()
        # Handle cases where model might return extra text
        for category in Category:
            if category.value in category_str:
                return category

        # Fallback or raise error if none match
        raise ValueError(f"Could not determine category from LLM response: {category_str}")

    async def extract_metadata(self, content: str, category: Category) -> ClassificationResult:
        system_prompt = (
            "You are a knowledge base metadata extractor. "
            "Your task is to extract structured metadata "
            f"from the following content, given its category: {category.value}.\n\n"
            "Extract the following fields in JSON format:\n"
            "- title: A concise and descriptive title.\n"
            "- description: A brief summary (1-2 sentences).\n"
            "- tags: A list of relevant keywords.\n"
            "- subcategory: A more specific classification within the category.\n"
            "- confidence: Your confidence score (0.0 to 1.0).\n"
            "- relevance_score: Importance of this content (1 to 10).\n"
            "- temporal_type: 'evergreen' (long-lasting value) "
            "or 'time_sensitive' (likely to expire).\n"
            "- key_claims: A list of up to 5 key points or claims made in the content.\n\n"
            "Respond with ONLY the JSON object."
        )

        result = await generate(
            self.chat_provider,
            system_prompt=system_prompt,
            tools=[],
            history=[Message(role="user", content=f"Content:\n{content}")],
        )

        json_str = result.message.extract_text().strip()
        # Basic JSON extraction if model adds markdown blocks
        if "```json" in json_str:
            json_str = json_str.split("```json")[1].split("```")[0].strip()
        elif "```" in json_str:
            json_str = json_str.split("```")[1].split("```")[0].strip()

        data = json.loads(json_str)
        data["category"] = category
        return ClassificationResult.model_validate(data)
