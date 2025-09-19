import json
import pytest
from app import create_app
from config.settings import TestingConfig

@pytest.fixture
def client():
    app = create_app(TestingConfig)
    with app.test_client() as client:
        yield client

def test_health_check(client):
    response = client.get('/health')
    assert response.status_code == 200
    data = json.loads(response.data)
    assert data['status'] == 'healthy'
    assert data['service'] == 'twid_intellisearch'

def test_classify_intent_missing_fields(client):
    response = client.post('/api/classify-intent', 
                          json={'user_id': 'test_user'})
    assert response.status_code == 400
    data = json.loads(response.data)
    assert 'error' in data
    assert 'Missing required fields' in data['error']