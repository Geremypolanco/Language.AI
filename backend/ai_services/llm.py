"""LLM Service - Ollama + Mistral/Llama for conversational AI"""

import httpx
import logging
from typing import Optional
from functools import lru_cache

logger = logging.getLogger(__name__)

class LLMService:
    def __init__(self, ollama_host: str = "http://localhost:11434"):
        self.ollama_host = ollama_host
        self.model = "mistral"  # Default model
        self.client = httpx.AsyncClient(timeout=60.0)

    async def generate_feedback(self, user_answer: str, correct_answer: str) -> str:
        """Generate AI feedback on user's answer"""
        prompt = f"""You are an expert language tutor. Provide constructive feedback.

User's answer: {user_answer}
Correct answer: {correct_answer}

Feedback (be encouraging and specific):"""
        
        return await self._generate(prompt)

    async def explain_concept(self, concept: str, context: str = "") -> str:
        """Explain a language concept in simple terms"""
        prompt = f"""Explain this language concept clearly and concisely:

Concept: {concept}
{f'Context: {context}' if context else ''}

Explanation:"""
        
        return await self._generate(prompt)

    async def generate_lesson_content(self, topic: str, level: str, language: str) -> dict:
        """Generate a complete lesson"""
        prompt = f"""Create a {level} level lesson for learning {language}.

Topic: {topic}

Include:
1. Learning objectives
2. Key vocabulary (5-10 words)
3. Grammar explanation
4. Example sentences
5. Practice exercise

Format as JSON."""
        
        content = await self._generate(prompt)
        return {"content": content, "topic": topic, "level": level}

    async def evaluate_answer(self, question: str, user_answer: str, correct_answer: str) -> dict:
        """Evaluate user's answer and provide score + feedback"""
        prompt = f"""Evaluate this language learning answer:

Question: {question}
User's answer: {user_answer}
Correct answer: {correct_answer}

Provide:
1. Correctness score (0-100)
2. What was good
3. What needs improvement
4. Corrected version

Format as JSON with keys: score, strengths, improvements, corrected_version"""
        
        evaluation = await self._generate(prompt)
        return {"evaluation": evaluation}

    async def _generate(self, prompt: str) -> str:
        """Call Ollama API to generate text"""
        try:
            response = await self.client.post(
                f"{self.ollama_host}/api/generate",
                json={
                    "model": self.model,
                    "prompt": prompt,
                    "stream": False,
                    "temperature": 0.7,
                },
            )
            if response.status_code == 200:
                return response.json()["response"]
            else:
                logger.error(f"Ollama error: {response.text}")
                return "Error generating response"
        except Exception as e:
            logger.error(f"LLM Service error: {e}")
            return "Service temporarily unavailable"

# Singleton instance
_llm_service: Optional[LLMService] = None

def get_llm_service() -> LLMService:
    global _llm_service
    if _llm_service is None:
        _llm_service = LLMService()
    return _llm_service
