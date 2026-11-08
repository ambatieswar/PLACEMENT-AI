import json
from unittest.mock import patch

import pytest

from app import create_app
from routes.features import FeatureDependencyError


@pytest.fixture()
def client(tmp_path):
    app = create_app({
        'TESTING': True,
        'SECRET_KEY': 'test-secret',
        'MONGO_URI': '',
        'GEMINI_API_KEY': '',
        'MISTRAL_API_KEY': '',
        'FALLBACK_STORAGE_MODE': 'memory',
        'FALLBACK_STORAGE_PATH': str(tmp_path / 'store.json'),
    })
    return app.test_client()


def csrf(client):
    response = client.get('/login')
    assert response.status_code == 200
    with client.session_transaction() as session:
        return session['_csrf_token']


def test_status_reports_local_fallback(client):
    response = client.get('/api/status')
    assert response.status_code == 200
    assert response.json['dependencies']['mongodb']['fallback'] is True


def test_signup_and_login_require_csrf(client):
    payload = {
        'email': 'test@example.com',
        'fullname': 'Test User',
        'password': 'StrongPass123!',
        'confirm_password': 'StrongPass123!',
    }
    assert client.post('/signup', data=payload).status_code == 400

    token = csrf(client)
    payload['csrf_token'] = token
    assert client.post('/signup', data=payload).status_code == 302
    assert client.post('/login', data={
        'csrf_token': token,
        'email': payload['email'],
        'password': payload['password'],
    }).status_code == 302


def test_ai_endpoint_reports_missing_provider(client):
    token = csrf(client)
    payload = {
        'csrf_token': token,
        'email': 'ai@example.com',
        'fullname': 'AI User',
        'password': 'StrongPass123!',
        'confirm_password': 'StrongPass123!',
    }
    client.post('/signup', data=payload)
    client.post('/login', data=payload)
    response = client.post(
        '/api/placement-predictor',
        headers={'X-CSRFToken': token},
        json={'skills': []},
    )
    assert response.status_code == 503
    assert 'GEMINI_API_KEY' in response.json['error']


def test_login_keeps_password_hidden(client):
    response = client.get('/login')
    assert response.status_code == 200
    assert 'type="password"' in response.get_data(as_text=True)


def test_ai_provider_falls_back_to_mistral(tmp_path):
    app = create_app({
        'TESTING': True,
        'SECRET_KEY': 'test-secret',
        'GEMINI_API_KEY': 'expired-gemini',
        'MISTRAL_API_KEY': 'working-mistral',
        'FALLBACK_STORAGE_MODE': 'memory',
        'FALLBACK_STORAGE_PATH': str(tmp_path / 'store.json'),
    })
    client = app.test_client()
    client.get('/login')
    with client.session_transaction() as session:
        token = session['_csrf_token']
    payload = {
        'csrf_token': token,
        'email': 'fallback@example.com',
        'fullname': 'Fallback User',
        'password': 'StrongPass123!',
        'confirm_password': 'StrongPass123!',
    }
    client.post('/signup', data=payload)
    client.post('/login', data=payload)
    result = {
        'overall_probability': 70,
        'tier1_probability': 40,
        'tier2_probability': 70,
        'tier3_probability': 90,
        'strengths': [],
        'weaknesses': [],
        'improvement_areas': [],
        'estimated_package': '8-12 LPA',
        'top_matching_companies': [],
        'reasoning': 'ok',
        'action_plan': [],
    }
    with patch('routes.features._gemini', side_effect=FeatureDependencyError('expired')), \
            patch('routes.features._mistral_request', return_value=json.dumps(result)):
        response = client.post(
            '/api/placement-predictor',
            headers={'X-CSRFToken': token},
            json={'skills': ['Python'], 'target_companies': []},
        )
    assert response.status_code == 200
    assert response.json['data']['overall_probability'] == 70
