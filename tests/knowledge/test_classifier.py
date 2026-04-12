import pytest
from unittest.mock import AsyncMock, MagicMock, patch
from kimi_cli.knowledge.classifier import Classifier, ClassificationResult
from kimi_cli.knowledge.models import Category, TemporalType
from kosong.message import Message, TextPart

@pytest.fixture
def mock_chat_provider():
    mock = MagicMock()
    mock.generate = AsyncMock()
    return mock

class MockMessage:
    def __init__(self, content):
        self.content = content
    def extract_text(self):
        return self.content

class MockGenerateResult:
    def __init__(self, content):
        self.message = MockMessage(content)
        self.usage = None

@pytest.mark.asyncio
async def test_classify_category(mock_chat_provider):
    classifier = Classifier(chat_provider=mock_chat_provider)
    
    with patch("kimi_cli.knowledge.classifier.generate", new_callable=AsyncMock) as mock_generate:
        mock_generate.return_value = MockGenerateResult("concept")
    
        content = "A neural network is a series of algorithms that endeavors to recognize underlying relationships in a set of data through a process that mimics the way the human brain operates."
        category = await classifier.classify_category(content)
        
        assert category == Category.Concept
        assert mock_generate.called

@pytest.mark.asyncio
async def test_extract_metadata(mock_chat_provider):
    classifier = Classifier(chat_provider=mock_chat_provider)
    
    json_output = """
    {
        "title": "Introduction to Neural Networks",
        "description": "A basic overview of how neural networks mimic the human brain to recognize data relationships.",
        "tags": ["AI", "neural networks", "machine learning"],
        "subcategory": "Foundations",
        "confidence": 0.95,
        "relevance_score": 9,
        "temporal_type": "evergreen",
        "key_claims": [
            "Mimics human brain operation",
            "Recognizes underlying relationships in data",
            "Series of algorithms"
        ]
    }
    """
    with patch("kimi_cli.knowledge.classifier.generate", new_callable=AsyncMock) as mock_generate:
        mock_generate.return_value = MockGenerateResult(json_output)
    
        content = "A neural network is a series of algorithms..."
        result = await classifier.extract_metadata(content, Category.Concept)
        
        assert result.title == "Introduction to Neural Networks"
        assert result.category == Category.Concept
        assert result.temporal_type == TemporalType.Evergreen
        assert len(result.key_claims) == 3
        assert result.confidence == 0.95

@pytest.mark.asyncio
async def test_classifier_with_model_name():
    with patch("kimi_cli.knowledge.classifier.load_config") as mock_load_config, \
         patch("kimi_cli.knowledge.classifier.OAuthManager") as mock_oauth, \
         patch("kimi_cli.knowledge.classifier.create_llm") as mock_create_llm:
        
        mock_config = MagicMock()
        mock_config.default_model = "test-model"
        mock_config.models = {"test-model": MagicMock(provider="test-provider")}
        mock_config.providers = {"test-provider": MagicMock()}
        mock_load_config.return_value = mock_config
        
        mock_llm = MagicMock()
        mock_llm.chat_provider = MagicMock()
        mock_create_llm.return_value = mock_llm
        
        classifier = Classifier(model="test-model")
        assert classifier.chat_provider == mock_llm.chat_provider
