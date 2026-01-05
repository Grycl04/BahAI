from firebase_functions import https_fn
from firebase_admin import initialize_app, firestore
import json
import logging
import pickle
import os
from typing import Dict, Any, List
import pandas as pd
import numpy as np
from datetime import datetime
# Initialize Firebase
initialize_app()
# Configure logging
logging.basicConfig(level=logging.INFO)
# Global variables for the model (loaded once per instance)
MODEL = None
VECTORIZER = None
ITEM_FEATURES = None
MODEL_LOADED = False
def load_model():
 """Load the recommender model once when the function instance
starts"""
 global MODEL, VECTORIZER, ITEM_FEATURES, MODEL_LOADED

 if MODEL_LOADED:
 return

 try:
 # Load from your trained model files
 # You can store these in Firebase Storage or bundle with your
function

 # Example: Load from local file (deployed with function)
 model_path = os.path.join(os.path.dirname(__file__), 'model.pkl')

 # For Firebase Storage (recommended for larger models):
 # from google.cloud import storage
 # storage_client = storage.Client()
 # bucket = storage_client.bucket('your-bucket-name')
 # blob = bucket.blob('model.pkl')
 # MODEL = pickle.loads(blob.download_as_bytes())

 logging.info("Model loading initialized")

 # TODO: Load your actual model here
 # MODEL = pickle.load(open(model_path, 'rb'))
 # VECTORIZER = pickle.load(open('vectorizer.pkl', 'rb'))

 MODEL_LOADED = True
 logging.info("Model loaded successfully")

 except Exception as e:
 logging.error(f"Error loading model: {str(e)}")
# ========== MAIN RECOMMENDATIONS FUNCTION ==========
@https_fn.on_request()
def recommendations(req: https_fn.Request) -> https_fn.Response:
 """
 Main endpoint for getting recommendations
 This function handles ALL recommendation routes based on firebase.json
rewrites:
 - /recommendations
 - /recommendations/**
 - /api/**
 """
 # Load model on first request
 load_model()

 # Handle CORS preflight requests
 if req.method == "OPTIONS":
 return https_fn.Response(
 "",
 headers={
 "Access-Control-Allow-Origin": "*",
 "Access-Control-Allow-Methods": "GET, POST, PUT, DELETE,
OPTIONS",
 "Access-Control-Allow-Headers": "Content-Type,
Authorization",
 "Access-Control-Max-Age": "3600"
 }
 )

 try:
 # Parse the request path to understand what's being requested
 path = req.path
 logging.info(f"Recommendations request: {req.method} {path}")

 # Handle different HTTP methods
 if req.method == "GET":
 # GET /recommendations?user_id=123&count=10
 user_id = req.args.get('user_id')
 count = int(req.args.get('count', 10))
 item_id = req.args.get('item_id')

 elif req.method == "POST":
 # POST /recommendations with JSON body
 try:
 data = req.get_json()
 user_id = data.get('user_id')
 count = data.get('count', 10)
 item_id = data.get('item_id')
 context = data.get('context', {})
 except Exception as e:
 return https_fn.Response(
 json.dumps({"error": "Invalid JSON format", "details":
str(e)}),
 status=400,
 headers={"Content-Type": "application/json",
"Access-Control-Allow-Origin": "*"}
 )
 else:
 return https_fn.Response(
 json.dumps({"error": "Method not allowed",
"allowed_methods": ["GET", "POST", "OPTIONS"]}),
 status=405,
 headers={"Content-Type": "application/json",
"Access-Control-Allow-Origin": "*"}
 )

 # Validate user_id
 if not user_id:
 return https_fn.Response(
 json.dumps({
 "error": "user_id is required",
 "usage_examples": {
 "GET":
"/recommendations?user_id=USER_ID&count=10",
 "POST": "/recommendations with JSON body:
{\"user_id\": \"USER_ID\", \"count\": 10}"
 }
 }),
 status=400,
 headers={"Content-Type": "application/json",
"Access-Control-Allow-Origin": "*"}
 )

 # Get user data from Firestore (if needed)
 db = firestore.client()
 user_data = {}
 try:
 user_ref = db.collection('users').document(user_id)
 user_doc = user_ref.get()
 if user_doc.exists:
 user_data = user_doc.to_dict()
 except Exception as e:
 logging.warning(f"Could not fetch user data for {user_id}:
{str(e)}")

 # Generate recommendations
 recommendations_list = generate_recommendations(
 user_id=user_id,
 user_data=user_data,
 item_id=item_id,
 count=count,
 context=locals().get('context', {})
 )

 # Log recommendation request (optional)
 try:
 log_ref = db.collection('recommendation_logs').document()
 log_ref.set({
 'user_id': user_id,
 'item_ids': [r['item_id'] for r in recommendations_list],
 'timestamp': firestore.SERVER_TIMESTAMP,
 'count': len(recommendations_list),
 'method': req.method
 })
 except Exception as e:
 logging.warning(f"Failed to log recommendation: {str(e)}")

 # Return recommendations
 response = {
 "success": True,
 "user_id": user_id,
 "recommendations": recommendations_list,
 "count": len(recommendations_list),
 "timestamp": datetime.now().isoformat(),
 "version": "0.5.0",
 "endpoint": path
 }

 return https_fn.Response(
 json.dumps(response, indent=2),
 status=200,
 headers={
 "Content-Type": "application/json",
 "Access-Control-Allow-Origin": "*",
 "Cache-Control": "no-cache, max-age=0"
 }
 )

 except Exception as e:
 logging.error(f"Error in recommendation endpoint: {str(e)}")
 return https_fn.Response(
 json.dumps({"error": str(e), "type": type(e).__name__}),
 status=500,
 headers={"Content-Type": "application/json",
"Access-Control-Allow-Origin": "*"}
 )
# ========== HEALTH CHECK FUNCTION ==========
@https_fn.on_request()
def health(req: https_fn.Request) -> https_fn.Response:
 """
 Health check endpoint for monitoring
 Accessible at: /health
 """
 health_status = {
 "status": "healthy",
 "service": "recommender-api",
 "timestamp": datetime.now().isoformat(),
 "model_loaded": MODEL_LOADED,
 "firebase_functions": "0.5.0",
 "endpoints": {
 "get_recommendations": "GET /recommendations?user_id=USER_ID",
 "post_recommendations": "POST /recommendations with JSON
body",
 "health_check": "GET /health"
 }
 }

 return https_fn.Response(
 json.dumps(health_status, indent=2),
 headers={
 "Content-Type": "application/json",
 "Access-Control-Allow-Origin": "*"
 }
 )
# ========== HELPER FUNCTIONS ==========
def generate_recommendations(user_id: str, user_data: Dict = None,
 item_id: str = None, count: int = 10,
 context: Dict = None) -> List[Dict]:
 """
 Generate recommendations for a user
 Replace this with your actual recommendation logic
 """
 # Example dummy data - replace with your model predictions
 dummy_items = [
 {"item_id": "item_001", "score": 0.95, "title": "Premium
Headphones", "category": "electronics", "price": 299.99},
 {"item_id": "item_002", "score": 0.88, "title": "Smart Watch",
"category": "electronics", "price": 249.99},
 {"item_id": "item_003", "score": 0.82, "title": "Laptop Stand",
"category": "accessories", "price": 89.99},
 {"item_id": "item_004", "score": 0.78, "title": "Wireless Mouse",
"category": "accessories", "price": 59.99},
 {"item_id": "item_005", "score": 0.75, "title": "USB-C Hub",
"category": "accessories", "price": 79.99},
 {"item_id": "item_006", "score": 0.72, "title": "Backpack",
"category": "fashion", "price": 129.99},
 {"item_id": "item_007", "score": 0.68, "title": "Water Bottle",
"category": "lifestyle", "price": 34.99},
 {"item_id": "item_008", "score": 0.65, "title": "Notebook",
"category": "stationery", "price": 24.99},
 {"item_id": "item_009", "score": 0.62, "title": "Desk Lamp",
"category": "home", "price": 149.99},
 {"item_id": "item_010", "score": 0.60, "title": "Phone Case",
"category": "accessories", "price": 39.99}
 ]

 # If item_id is provided, simulate item-based recommendations
 if item_id:
 return [
 {"item_id": f"similar_to_{item_id}_{i}", "score": 0.9 - (i *
0.1),
 "title": f"Similar to {item_id}", "reason": "item-based"}
 for i in range(1, count + 1)
 ]

 # Return user-based recommendations
 return dummy_items[:count]
def log_recommendation_request(user_id: str, recommendations: List[Dict]):
 """Log recommendation requests to Firestore for analytics"""
 try:
 db = firestore.client()
 log_ref = db.collection('recommendation_logs').document()

 log_ref.set({
 'user_id': user_id,
 'recommendations': [r['item_id'] for r in recommendations],
 'timestamp': firestore.SERVER_TIMESTAMP,
 'count': len(recommendations)
 })
 except Exception as e:
 logging.warning(f"Failed to log recommendation: {str(e)}")
# Note: In firebase-functions v0.5.0, each @https_fn.on_request()
# creates a separate Cloud Function. The function names must match
# what's in firebase.json rewrites.