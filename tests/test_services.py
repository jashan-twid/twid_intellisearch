import pytest
from app.services.intent_classifier import classify_intent
from unittest.mock import MagicMock, patch

@pytest.fixture
def mock_genai_model():
    model = MagicMock()
    response = MagicMock()
    response.text = '{"intent": "PAY_TO_PERSON", "confidence": 0.95, "extracted_data": {"payee_name": "Rahul", "amount": 500}}'
    model.generate_content.return_value = response
    return model

def test_classify_intent(mock_genai_model):
    result = classify_intent(mock_genai_model, "Pay ₹500 to Rahul")
    
    assert result['intent'] == 'PAY_TO_PERSON'
    assert result['confidence'] == 0.95
    assert result['extracted_data']['payee_name'] == 'Rahul'
    assert result['extracted_data']['amount'] == 500
    
    mock_genai_model.generate_content.assert_called_once()

@patch('app.services.vector_store.es_client')
def test_search_similar_intent(mock_es):
    from app.services.vector_store import search_similar_intent
    
    # Mock Elasticsearch response
    mock_es.search.return_value = {
        'hits': {
            'total': {'value': 1},
            'hits': [
                {
                    '_source': {
                        'intent_data': {
                            'intent': 'PAY_TO_PERSON',
                            'confidence': 0.95,
                            'extracted_data': {'payee_name': 'Rahul', 'amount': 500}
                        }
                    }
                }
            ]
        }
    }
    
    result = search_similar_intent(mock_es, 'user123', 'Pay ₹500 to Rahul')
    
    assert result['intent'] == 'PAY_TO_PERSON'
    assert result['confidence'] == 0.95
    assert result['extracted_data']['payee_name'] == 'Rahul'
    
    mock_es.search.assert_called_once()