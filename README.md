# TWID Intellisearch API

A microservice for intent classification and natural language processing using Google Gemini AI. Part of the TWID Hackathon project for Universal Search with Chat functionality.

## Features

- Intent classification for user queries
- Historical query storage in Elasticsearch
- Integration with Google Gemini AI
- REST API for easy integration with frontend and other services

## Requirements

- Python 3.10+
- Docker and Docker Compose
- Elasticsearch 8.x
- Google Gemini API key

## Quick Start

1. Clone the repository:
   ```bash
   git clone https://github.com/jashan-twid/twid_intellisearch.git
   cd twid_intellisearch
   ```

2. Copy the example environment file and update with your values:
   ```bash
   cp .env.example .env
   # Edit .env with your configuration
   ```

3. Start the services using Docker Compose:
   ```bash
   docker-compose up -d
   ```

4. The API will be available at `http://localhost:5000`

## API Endpoints

### Classify Intent

```
POST /api/classify-intent
```

Request body:
```json
{
  "user_id": "user123",
  "query": "Pay ₹500 to Rahul for dinner",
  "context": {}
}
```

Response:
```json
{
  "intent": "PAY_TO_PERSON",
  "confidence": 0.95,
  "extracted_data": {
    "payee_name": "Rahul",
    "amount": 500,
    "note": "dinner"
  }
}
```

### Provide Feedback

```
POST /api/feedback
```

Request body:
```json
{
  "user_id": "user123",
  "query": "Pay ₹500 to Rahul for dinner",
  "correct_intent": {
    "intent": "PAY_TO_PERSON",
    "confidence": 1.0,
    "extracted_data": {
      "payee_name": "Rahul",
      "amount": 500,
      "note": "dinner"
    }
  }
}
```

Response:
```json
{
  "status": "feedback recorded successfully"
}
```

## Development

### Local Setup

1. Create a virtual environment:
   ```bash
   python -m venv venv
   source venv/bin/activate  # On Windows: venv\Scripts\activate
   ```

2. Install dependencies:
   ```bash
   pip install -r requirements.txt
   ```

3. Set up environment variables (copy from .env.example)

4. Run the development server:
   ```bash
   python main.py
   ```

### Running Tests

```bash
pytest
```

### Code Style

This project uses Black for code formatting and Flake8 for linting.

```bash
black .
flake8
```

## Integration with TWID MAPI

The intellisearch service is designed to work with the existing TWID MAPI service. The flow is:

1. App sends query to the intellisearch service
2. Intellisearch classifies the intent and extracts structured data
3. MAPI service receives the structured data and performs database operations
4. Results are returned to the app for display

## License

Copyright © 2025 TWID