from flask import Blueprint, request, jsonify
from app import es_manager

bills_bp = Blueprint('bills', __name__)

@bills_bp.route('/bills', methods=['POST'])
def get_bills():
    """
    Request JSON: { "user_id": "40321617", "ai_biller_name": "HDFC Credit Card", "category_name": "CREDIT CARD" }
    Returns: Matched user credit cards for the biller, or generic bill data if no match.
    """
    data = request.get_json()
    user_id = data.get('user_id')
    ai_biller_name = data.get('ai_biller_name')
    category_name = data.get('category_name')

    # 1. Fetch all generic bill data
    generic_bills = []
    try:
        resp = es_manager.es_client.search(
            index="generic_bills",
            body={"size": 1000, "query": {"match_all": {}}}
        )
        generic_bills = [hit["_source"] for hit in resp["hits"]["hits"]]
    except Exception as e:
        return jsonify({"error": f"Failed to fetch generic bills: {str(e)}"}), 500

    # 2. If AI biller_name is present, try to match with user credit cards
    matched_cards = []
    if ai_biller_name and user_id:
        try:
            resp = es_manager.es_client.search(
                index="user_credit_cards",
                body={
                    "size": 100,
                    "query": {
                        "bool": {
                            "must": [
                                {"term": {"customer_id": user_id}},
                                {"match": {"biller_name": ai_biller_name}}
                            ]
                        }
                    }
                }
            )
            matched_cards = [hit["_source"] for hit in resp["hits"]["hits"]]
        except Exception as e:
            return jsonify({"error": f"Failed to fetch user credit cards: {str(e)}"}), 500

    # 3. Return matched cards if found, else generic bill data
    if matched_cards:
        # Add 'additional_data' in extracted_data for each matched card
        response = {
            "matched_cards": [
                {
                    **card,
                    "extracted_data": {
                        "additional_data": card
                    }
                } for card in matched_cards
            ]
        }
        return jsonify(response)
    else:
        # Optionally filter generic bills by category_name if provided
        if category_name:
            filtered_bills = [b for b in generic_bills if any(r.get("category_id") == 22 for r in b.get("request", []))] if category_name.upper() == "CREDIT CARD" else generic_bills
            return jsonify({"generic_bills": filtered_bills})
        return jsonify({"generic_bills": generic_bills})
