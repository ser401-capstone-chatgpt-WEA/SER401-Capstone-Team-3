"""
End-to-end integration tests for the PBS WARN RAG pipeline.

Tests the full flow: query preprocessing → retrieval → generation,
using mocked external dependencies (ChromaDB, Gemini API).
"""
import time
from unittest.mock import MagicMock, patch

import pytest

from rags.query_utils import preprocess_query
from rags.data_model import RAGDocument, map_alert_to_ragdoc, batch_map_alerts


# ---------------------------------------------------------------------------
# Fixtures
# ---------------------------------------------------------------------------

SAMPLE_ALERT = {
    "identifier": "test-alert-001",
    "sender": "w-nws.webmaster@noaa.gov",
    "sent": "2025-10-24T12:00:00-07:00",
    "status": "Actual",
    "msgType": "Alert",
    "scope": "Public",
    "info": [
        {
            "event": "Severe Thunderstorm Warning",
            "severity": "Severe",
            "urgency": "Immediate",
            "certainty": "Observed",
            "expires": "2025-10-24T13:00:00-07:00",
            "senderName": "NWS Phoenix AZ",
            "headline": "Severe Thunderstorm Warning for Maricopa County",
            "description": "A severe thunderstorm was located near Phoenix moving east.",
            "areaDesc": "Maricopa County, AZ",
        }
    ],
}

SAMPLE_RETRIEVED_DOCS = [
    {
        "id": "test-alert-001",
        "text": "Severe Thunderstorm Warning for Maricopa County. "
                "A severe thunderstorm was located near Phoenix moving east.",
        "metadata": {
            "event": "Severe Thunderstorm Warning",
            "severity": "Severe",
            "sent": "2025-10-24T12:00:00-07:00",
            "sender": "NWS Phoenix AZ",
        },
        "score": 0.87,
    },
    {
        "id": "test-alert-002",
        "text": "Flash Flood Watch for central Arizona.",
        "metadata": {
            "event": "Flash Flood Watch",
            "severity": "Moderate",
            "sent": "2025-10-24T11:00:00-07:00",
            "sender": "NWS Phoenix AZ",
        },
        "score": 0.62,
    },
]


# ---------------------------------------------------------------------------
# Query preprocessing tests
# ---------------------------------------------------------------------------

class TestQueryPreprocessing:
    """Test query normalization, abbreviation expansion, and spelling fixes."""

    def test_basic_cleanup(self):
        result = preprocess_query("   What is the WEATHER alert??   ")
        assert result == "what is the weather alert"

    def test_abbreviation_expansion(self):
        result = preprocess_query("svr wx alert for tx")
        assert "severe" in result
        assert "weather" in result
        assert "texas" in result

    def test_misspelling_correction(self):
        result = preprocess_query("torndo warnning in phoenix")
        assert "tornado" in result
        assert "warning" in result

    def test_state_abbreviation(self):
        result = preprocess_query("alerts in az")
        assert "arizona" in result

    def test_empty_query(self):
        result = preprocess_query("")
        assert result == ""

    def test_special_characters_removed(self):
        result = preprocess_query("alert@#$% for phoenix")
        assert "@" not in result
        assert "#" not in result


# ---------------------------------------------------------------------------
# Data model / mapping tests
# ---------------------------------------------------------------------------

class TestDataModel:
    """Test alert-to-RAGDocument mapping."""

    def test_map_single_alert(self):
        doc = map_alert_to_ragdoc(SAMPLE_ALERT)
        assert doc is not None
        assert isinstance(doc, RAGDocument)
        assert doc.event == "Severe Thunderstorm Warning"
        assert doc.severity == "Severe"

    def test_batch_mapping(self):
        docs = batch_map_alerts([SAMPLE_ALERT, SAMPLE_ALERT])
        assert len(docs) >= 1

    def test_chroma_format_output(self):
        doc = map_alert_to_ragdoc(SAMPLE_ALERT)
        text, metadata, doc_id = doc.to_chroma_format()
        assert isinstance(text, str)
        assert len(text) > 0
        assert isinstance(metadata, dict)
        assert isinstance(doc_id, str)

    def test_empty_alert_list(self):
        docs = batch_map_alerts([])
        assert docs == []


# ---------------------------------------------------------------------------
# Retriever tests (mocked ChromaDB)
# ---------------------------------------------------------------------------

class TestRetriever:
    """Test retrieval with mocked vector store."""

    @patch("rags.retriever.ChromaDBManager")
    def test_retrieve_returns_results(self, MockDB):
        mock_instance = MockDB.return_value
        mock_instance.collection.count.return_value = 10
        mock_instance.query.return_value = {
            "ids": [["id1", "id2"]],
            "documents": [["doc text 1", "doc text 2"]],
            "metadatas": [[{"event": "Tornado Warning"}, {"event": "Flood Watch"}]],
            "distances": [[0.1, 0.4]],
        }

        from rags.retriever import AlertRetriever

        retriever = AlertRetriever.__new__(AlertRetriever)
        retriever.db = mock_instance
        retriever.min_score = 0.25

        results = retriever.retrieve("tornado warning", top_k=5)
        assert len(results) == 2
        assert results[0]["score"] == pytest.approx(0.9)
        assert results[1]["score"] == pytest.approx(0.6)

    @patch("rags.retriever.ChromaDBManager")
    def test_score_threshold_filters_low_relevance(self, MockDB):
        mock_instance = MockDB.return_value
        mock_instance.collection.count.return_value = 10
        mock_instance.query.return_value = {
            "ids": [["id1", "id2"]],
            "documents": [["doc1", "doc2"]],
            "metadatas": [[{"event": "A"}, {"event": "B"}]],
            "distances": [[0.1, 0.9]],  # scores: 0.9 and 0.1
        }

        from rags.retriever import AlertRetriever

        retriever = AlertRetriever.__new__(AlertRetriever)
        retriever.db = mock_instance
        retriever.min_score = 0.25

        results = retriever.retrieve("test query", min_score=0.5)
        assert len(results) == 1
        assert results[0]["id"] == "id1"

    @patch("rags.retriever.ChromaDBManager")
    def test_retrieve_handles_error_gracefully(self, MockDB):
        mock_instance = MockDB.return_value
        mock_instance.collection.count.return_value = 0
        mock_instance.query.side_effect = Exception("DB error")

        from rags.retriever import AlertRetriever

        retriever = AlertRetriever.__new__(AlertRetriever)
        retriever.db = mock_instance
        retriever.min_score = 0.25

        results = retriever.retrieve("test")
        assert results == []


# ---------------------------------------------------------------------------
# Generator tests (mocked Gemini API)
# ---------------------------------------------------------------------------

class TestGenerator:
    """Test response generation with mocked LLM."""

    @patch.dict("os.environ", {"GEMINI_API_KEY": "test-key"})
    @patch("rags.generator.genai")
    def test_generate_produces_answer(self, mock_genai):
        mock_client = MagicMock()
        mock_genai.Client.return_value = mock_client
        mock_resp = MagicMock()
        mock_resp.text = "There is a severe thunderstorm warning for Maricopa County."
        mock_client.models.generate_content.return_value = mock_resp

        from rags.generator import ResponseGenerator

        gen = ResponseGenerator()
        result = gen.generate("thunderstorm in phoenix", SAMPLE_RETRIEVED_DOCS)

        assert "answer" in result
        assert "sources" in result
        assert "tokens_used" in result
        assert len(result["answer"]) > 0
        assert len(result["sources"]) == 2

    @patch.dict("os.environ", {"GEMINI_API_KEY": "test-key"})
    @patch("rags.generator.genai")
    def test_generate_empty_docs_returns_fallback(self, mock_genai):
        mock_genai.Client.return_value = MagicMock()

        from rags.generator import ResponseGenerator

        gen = ResponseGenerator()
        result = gen.generate("anything", [])

        assert "don't have enough information" in result["answer"].lower()
        assert result["sources"] == []

    @patch.dict("os.environ", {"GEMINI_API_KEY": "test-key"})
    @patch("rags.generator.genai")
    def test_retry_on_api_failure(self, mock_genai):
        mock_client = MagicMock()
        mock_genai.Client.return_value = mock_client

        # Fail twice then succeed
        mock_resp = MagicMock()
        mock_resp.text = "Success after retries"
        mock_client.models.generate_content.side_effect = [
            Exception("Rate limited"),
            Exception("Rate limited"),
            mock_resp,
        ]

        from rags.generator import ResponseGenerator

        gen = ResponseGenerator(max_retries=3, base_delay=0.01)
        result = gen.generate("test query", SAMPLE_RETRIEVED_DOCS)

        assert result["answer"] == "Success after retries"
        assert mock_client.models.generate_content.call_count == 3

    @patch.dict("os.environ", {"GEMINI_API_KEY": "test-key"})
    @patch("rags.generator.genai")
    def test_all_retries_exhausted(self, mock_genai):
        mock_client = MagicMock()
        mock_genai.Client.return_value = mock_client
        mock_client.models.generate_content.side_effect = Exception("Permanent failure")

        from rags.generator import ResponseGenerator

        gen = ResponseGenerator(max_retries=2, base_delay=0.01)
        result = gen.generate("test query", SAMPLE_RETRIEVED_DOCS)

        assert "error" in result["answer"].lower()
        assert mock_client.models.generate_content.call_count == 2


# ---------------------------------------------------------------------------
# End-to-end pipeline test (all mocked externals)
# ---------------------------------------------------------------------------

class TestEndToEndPipeline:
    """Test the full query → preprocess → retrieve → generate pipeline."""

    @patch.dict("os.environ", {"GEMINI_API_KEY": "test-key"})
    @patch("rags.generator.genai")
    @patch("rags.retriever.ChromaDBManager")
    def test_full_pipeline(self, MockDB, mock_genai):
        # Setup mock retriever
        mock_db = MockDB.return_value
        mock_db.collection.count.return_value = 100
        mock_db.query.return_value = {
            "ids": [["alert-001"]],
            "documents": [["Severe Thunderstorm Warning for Phoenix."]],
            "metadatas": [[{"event": "Severe Thunderstorm Warning", "severity": "Severe", "sent": "2025-10-24"}]],
            "distances": [[0.15]],
        }

        # Setup mock generator
        mock_client = MagicMock()
        mock_genai.Client.return_value = mock_client
        mock_resp = MagicMock()
        mock_resp.text = "A severe thunderstorm warning is active for Phoenix."
        mock_client.models.generate_content.return_value = mock_resp

        # Run the full pipeline
        from rags.retriever import AlertRetriever
        from rags.generator import ResponseGenerator

        raw_query = "SVR wx alert in AZ"
        processed = preprocess_query(raw_query)
        assert "severe" in processed
        assert "arizona" in processed

        retriever = AlertRetriever.__new__(AlertRetriever)
        retriever.db = mock_db
        retriever.min_score = 0.25
        docs = retriever.retrieve(processed, top_k=5)
        assert len(docs) == 1
        assert docs[0]["score"] == pytest.approx(0.85)

        generator = ResponseGenerator()
        result = generator.generate(processed, docs)
        assert "thunderstorm" in result["answer"].lower()
        assert len(result["sources"]) == 1

    @patch.dict("os.environ", {"GEMINI_API_KEY": "test-key"})
    @patch("rags.generator.genai")
    @patch("rags.retriever.ChromaDBManager")
    def test_pipeline_no_relevant_results(self, MockDB, mock_genai):
        mock_db = MockDB.return_value
        mock_db.collection.count.return_value = 100
        mock_db.query.return_value = {
            "ids": [["alert-999"]],
            "documents": [["Unrelated content"]],
            "metadatas": [[{"event": "Test"}]],
            "distances": [[0.95]],  # very low similarity (0.05)
        }

        mock_genai.Client.return_value = MagicMock()

        from rags.retriever import AlertRetriever
        from rags.generator import ResponseGenerator

        retriever = AlertRetriever.__new__(AlertRetriever)
        retriever.db = mock_db
        retriever.min_score = 0.25
        docs = retriever.retrieve("very specific obscure query", top_k=5)
        assert len(docs) == 0  # filtered out by threshold

        generator = ResponseGenerator()
        result = generator.generate("very specific obscure query", docs)
        assert "don't have enough information" in result["answer"].lower()
