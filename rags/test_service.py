"""
Integration tests for PBS WARN RAG service.
"""
import pytest
import requests
from rags.retriever import AlertRetriever
from rags.generator import ResponseGenerator


class TestRetriever:
    """Test suite for AlertRetriever."""
    
    def test_retriever_initialization(self):
        """Test that retriever initializes successfully."""
        retriever = AlertRetriever()
        assert retriever.db is not None
        assert retriever.db.collection is not None
    
    def test_retriever_query(self):
        """Test that retriever returns results."""
        retriever = AlertRetriever()
        results = retriever.retrieve("severe weather", top_k=3)
        
        assert isinstance(results, list)
        assert len(results) <= 3
        
        # Check structure if results exist
        if results:
            assert all('id' in r for r in results)
            assert all('text' in r for r in results)
            assert all('metadata' in r for r in results)
            assert all('score' in r for r in results)
    
    def test_retriever_empty_query(self):
        """Test retriever handles empty query gracefully."""
        retriever = AlertRetriever()
        results = retriever.retrieve("", top_k=5)
        assert isinstance(results, list)


class TestGenerator:
    """Test suite for ResponseGenerator."""
    
    def test_generator_initialization(self, pytestconfig):
        """Test that generator initializes with API key."""
        if not pytestconfig.getoption("--run-llm-tests", default=False):
            pytest.skip("Skipping LLM tests (requires GEMINI_API_KEY)")
        try:
            generator = ResponseGenerator()
            assert generator.client is not None
        except ValueError as e:
            pytest.skip(f"GEMINI_API_KEY not set: {e}")
    
    def test_generator_no_docs(self):
        """Test generator handles empty document list."""
        try:
            generator = ResponseGenerator()
            response = generator.generate("test query", [])
            
            assert "answer" in response
            assert "sources" in response
            assert len(response["sources"]) == 0
            assert "don't have" in response["answer"].lower()
        except ValueError:
            pytest.skip("GOOGLE_API_KEY not set")
    
    def test_generator_with_docs(self, pytestconfig):
        """Test generator produces response with documents."""
        if not pytestconfig.getoption("--run-llm-tests", default=False):
            pytest.skip("Skipping LLM tests (requires GOOGLE_API_KEY and API calls)")
        generator = ResponseGenerator()

        mock_docs = [
            {
                'id': 'test-1',
                'text': 'Severe thunderstorm warning for Phoenix',
                'metadata': {'event': 'Severe Thunderstorm', 'severity': 'Severe'},
                'score': 0.95
            }
        ]

        response = generator.generate("What weather alerts are active?", mock_docs)

        assert "answer" in response
        assert "sources" in response
        assert len(response["sources"]) == 1
        assert response["tokens_used"] > 0


class TestServiceEndpoints:
    """Test suite for FastAPI service endpoints (requires running service)."""
    
    BASE_URL = "http://localhost:8000"
    
    def test_health_endpoint(self):
        """Test health check endpoint."""
        try:
            response = requests.get(f"{self.BASE_URL}/health", timeout=5)
            assert response.status_code == 200
            data = response.json()
            assert "status" in data
            assert "documents_indexed" in data
        except requests.exceptions.ConnectionError:
            pytest.skip("Service not running")
    
    def test_root_endpoint(self):
        """Test root endpoint."""
        try:
            response = requests.get(f"{self.BASE_URL}/", timeout=5)
            assert response.status_code == 200
            data = response.json()
            assert "service" in data
            assert "endpoints" in data
        except requests.exceptions.ConnectionError:
            pytest.skip("Service not running")
    
    def test_query_endpoint(self):
        """Test query endpoint."""
        try:
            response = requests.post(
                f"{self.BASE_URL}/query",
                json={"query": "What severe weather alerts are active?", "top_k": 3},
                timeout=30
            )
            assert response.status_code == 200
            data = response.json()
            assert "answer" in data
            assert "sources" in data
            assert isinstance(data["sources"], list)
        except requests.exceptions.ConnectionError:
            pytest.skip("Service not running")


if __name__ == "__main__":
    pytest.main([__file__, "-v"])
