"""
Updated LLM-based response generation for PBS WARN RAG using Google GenAI (Gemini).
"""
import os
import logging
from typing import List, Dict, Any

from google import genai
from google.genai import types

logging.basicConfig(
    filename='pbs_warn_scraper.log',
    level=logging.INFO,
    format='%(asctime)s - %(levelname)s - %(message)s'
)


class ResponseGenerator:
    """Generates grounded responses using retrieved context via Gemini (google-genai)."""
    
    def __init__(
        self,
        model: str = "gemini-2.5-flash",
        max_tokens: int = 500,
        temperature: float = 0.1
    ):
        self.model = model
        self.max_tokens = max_tokens
        self.temperature = temperature

        # Load API key from environment variable
        api_key_env = os.getenv("GEMINI_API_KEY") or os.getenv("GOOGLE_API_KEY")
        if not api_key_env:
            raise ValueError(
                "Set GEMINI_API_KEY or GOOGLE_API_KEY environment variable with your Gemini API key."
            )

        # Create the SDK client (sync). The client reads the env var automatically.
        self.client = genai.Client()
        logging.info(f"Initialized generator with model: {model}")
    
    def generate(
        self,
        query: str,
        retrieved_docs: List[Dict[str, Any]]
    ) -> Dict[str, Any]:
        """
        Generate answer grounded in retrieved documents.

        Returns a dict:
            {
                "answer": str,
                "sources": List[dict],
                "tokens_used": int (approx)
            }
        """
        if not retrieved_docs:
            return {
                "answer": "I don't have enough information to answer that question.",
                "sources": [],
                "tokens_used": 0
            }
        
        # Build context from retrieved docs
        context = self._build_context(retrieved_docs)

        # System prompt
        system_prompt = """
        You are an emergency alert assistant.

        Rules:
        - Answer ONLY using the provided context
        - If the context does not contain the answer, say:
        "I don't have information about that"
        - Cite source document IDs when possible
        - Be concise, factual, and neutral
        """.strip()

        # User prompt with context and query
        user_prompt = f"""
        Context:
        {context}

        Question:
        {query}
        """.strip()

        try:
            resp = self.client.models.generate_content(
                model=self.model,
                contents=user_prompt,
                config=types.GenerateContentConfig(
                    system_instruction=system_prompt,
                    temperature=self.temperature,
                    max_output_tokens=self.max_tokens
                )
            )

            answer = resp.text if hasattr(resp, "text") else str(resp)
            # Rough token estimate (words -> tokens is approximate)
            tokens_used = len(user_prompt.split()) + len(answer.split())

            logging.info(f"Generated response (approx. {tokens_used} tokens)")

            return {
                "answer": answer,
                "sources": [
                    {
                        "id": doc.get('id'),
                        "score": doc.get('score'),
                        "metadata": doc.get('metadata')
                    }
                    for doc in retrieved_docs
                ],
                "tokens_used": tokens_used
            }

        except Exception as e:
            logging.error(f"Generation error: {e}", exc_info=True)
            return {
                "answer": "Error generating response. Please try again.",
                "sources": [],
                "tokens_used": 0
            }
    
    def _build_context(self, docs: List[Dict[str, Any]]) -> str:
        """Format retrieved documents into context string."""
        context_parts = []
        for i, doc in enumerate(docs, 1):
            meta = doc.get('metadata', {}) or {}
            context_parts.append(
                f"[Document {i} - ID: {doc.get('id', 'N/A')}]\n"
                f"Event: {meta.get('event', 'N/A')}\n"
                f"Severity: {meta.get('severity', 'N/A')}\n"
                f"Sent: {meta.get('sent', 'N/A')}\n"
                f"Content: {doc.get('text', '')}\n"
            )
        return "\n".join(context_parts)
    
    def check_health(self) -> str:
        """
        Check the health of the response generator.
        
        Verifies that the LLM client is properly configured and can
        communicate with the Gemini API by attempting a minimal request.
        
        Returns:
            str: "healthy" if the generator is operational, "unhealthy" otherwise
        
        Notes:
            - Uses a simple test prompt to verify API connectivity
            - Logs any errors encountered during health check
            - Does not count against rate limits (minimal token usage)
        """
        try:
            # Attempt a minimal API call to verify connectivity
            test_prompt = "Respond with 'ok'"
            resp = self.client.models.generate_content(
                model=self.model,
                contents=test_prompt,
                config=types.GenerateContentConfig(
                    temperature=0,
                    max_output_tokens=5
                )
            )
            
            # If we get any response, the API is working
            if resp and hasattr(resp, 'text'):
                logging.info("Generator health check passed")
                return "healthy"
            else:
                logging.warning("Generator health check: unexpected response format")
                return "unhealthy"
                
        except Exception as e:
            logging.error(f"Generator health check failed: {e}")
            return "unhealthy"
