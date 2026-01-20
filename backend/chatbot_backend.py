# backend/chatbot_backend.py
from flask import Flask, request, jsonify
from flask_cors import CORS
import pickle
import firebase_admin
from firebase_admin import credentials, firestore
import re
import json
import os
from datetime import datetime
from google.cloud import firestore as google_firestore
import functions_framework

app = Flask(__name__)
CORS(app, resources={r"/api/*": {"origins": "*"}})

# ==================== CONFIGURATION ====================
MODEL_PATH = 'models/nlu_model.pkl'
FIREBASE_CREDENTIALS = 'service-account-key.json'

# ==================== LOAD TRAINED MODEL ====================
print("📦 Loading trained NLU model...")
try:
    with open(MODEL_PATH, 'rb') as f:
        model_data = pickle.load(f)
    
    vectorizer = model_data['vectorizer']
    classifier = model_data['classifier']
    print(f"✅ Model loaded! Classes: {classifier.classes_}")
except Exception as e:
    print(f"❌ Error loading model: {e}")
    print("⚠️ Using fallback intent detection")
    vectorizer = None
    classifier = None

# ==================== INITIALIZE FIREBASE ====================
db = None
try:
    if os.path.exists(FIREBASE_CREDENTIALS):
        # Method 1: Use service account
        cred = credentials.Certificate(FIREBASE_CREDENTIALS)
        firebase_admin.initialize_app(cred)
        db = firestore.client()
        print("🔥 Firebase initialized with service account!")
    elif 'GOOGLE_APPLICATION_CREDENTIALS' in os.environ:
        # Method 2: Use environment variable (for cloud deployment)
        cred = credentials.ApplicationDefault()
        firebase_admin.initialize_app(cred)
        db = firestore.client()
        print("🔥 Firebase initialized with environment credentials!")
    else:
        # Method 3: Try Google Cloud Firestore directly
        try:
            db = google_firestore.Client()
            print("🔥 Firebase initialized with Google Cloud credentials!")
        except:
            print("⚠️ Firebase not initialized - using mock data")
except Exception as e:
    print(f"⚠️ Firebase initialization failed: {e}")
    db = None

# ==================== ENTITY DICTIONARIES ====================
PROPERTY_TYPES = [
    'apartment', 'condo', 'condominium', 'house', 'villa', 
    'townhouse', 'bungalow', 'duplex', 'lot', 'land',
    'studio', 'penthouse', 'loft', 'room', 'bedspace',
    'commercial', 'office', 'retail', 'warehouse', 'factory'
]

LOCATIONS = [
    'batangas city', 'lipa city', 'tanauan city', 'bauan',
    'balayan', 'nasugbu', 'san juan', 'taal', 'calaca',
    'lemery', 'talisay', 'alitagtag', 'cuenca', 'laurel',
    'mataasnakahoy', 'san jose', 'san luis', 'san pascual',
    'santo tomas'
]

FINANCING_TYPES = [
    'bank financing', 'pag-ibig', 'in-house financing',
    'cash', 'installment', 'mortgage', 'loan'
]

# ==================== HELPER FUNCTIONS ====================
def extract_entities_from_query(query):
    """Extract entities from user query"""
    query_lower = query.lower()
    entities = {}
    
    # Extract property type
    for prop_type in PROPERTY_TYPES:
        if prop_type in query_lower:
            entities['property_type'] = prop_type
            break
    
    # Extract location
    for location in LOCATIONS:
        if location in query_lower:
            entities['location'] = location.title()
            break
    
    # Extract financing type
    for financing in FINANCING_TYPES:
        if financing in query_lower:
            entities['financing_type'] = financing
            break
    
    # Extract price
    price_patterns = [
        r'under\s+(\d+[kKmM]?)',
        r'below\s+(\d+[kKmM]?)',
        r'less than\s+(\d+[kKmM]?)',
        r'(\d+[kKmM]?)\s*(million|m|k)?'
    ]
    
    for pattern in price_patterns:
        match = re.search(pattern, query_lower)
        if match:
            price_str = match.group(1)
            try:
                if 'k' in price_str.lower():
                    entities['max_price'] = float(price_str.lower().replace('k', '')) * 1000
                elif 'm' in price_str.lower():
                    entities['max_price'] = float(price_str.lower().replace('m', '')) * 1000000
                else:
                    entities['max_price'] = float(price_str)
                break
            except:
                pass
    
    # Extract bedrooms
    bedroom_patterns = [
        r'(\d+)\s*bedroom',
        r'(\d+)\s*bed',
        r'(\d+)\s*br',
        r'studio'
    ]
    
    for pattern in bedroom_patterns:
        match = re.search(pattern, query_lower)
        if match:
            if 'studio' in query_lower:
                entities['bedrooms'] = 'studio'
            else:
                entities['bedrooms'] = match.group(1)
            break
    
    return entities

def search_firestore_properties(entities):
    """Search properties in Firestore based on extracted entities"""
    if not db:
        print("❌ Firestore not available - returning mock data")
        return get_mock_properties()
    
    try:
        # Start query
        properties_ref = db.collection('properties')
        query_ref = properties_ref
        
        # Filter by status (only active/available properties)
        query_ref = query_ref.where('status', 'in', ['active', 'available', 'Active', 'Available'])
        
        # Apply entity filters
        if 'location' in entities:
            location = entities['location']
            # Try multiple location fields
            query_ref = query_ref.where('city', '==', location)
        
        if 'property_type' in entities:
            prop_type = entities['property_type']
            query_ref = query_ref.where('propertyType', '==', prop_type)
        
        if 'financing_type' in entities:
            # Assuming saleType field exists for financing options
            if entities['financing_type'] == 'bank financing':
                query_ref = query_ref.where('saleType', '==', 'bank_financing')
        
        if 'max_price' in entities:
            max_price = entities['max_price']
            # Check different price fields based on transaction type
            query_ref = query_ref.where('salePrice', '<=', max_price)
        
        if 'bedrooms' in entities:
            bedrooms = entities['bedrooms']
            if bedrooms == 'studio':
                query_ref = query_ref.where('bedrooms', '==', 'studio')
            else:
                query_ref = query_ref.where('bedrooms', '==', int(bedrooms))
        
        # Limit results
        query_ref = query_ref.limit(20)
        
        # Execute query
        results = query_ref.stream()
        
        properties = []
        for doc in results:
            try:
                prop_data = doc.to_dict()
                prop_data['id'] = doc.id
                
                # Add missing essential fields
                if 'title' not in prop_data:
                    city = prop_data.get('city', 'Batangas')
                    prop_type = prop_data.get('propertyType', 'Property')
                    prop_data['title'] = f"{prop_type.title()} in {city}"
                
                # Ensure photos field exists
                if 'photos' not in prop_data and 'imageUrls' in prop_data:
                    prop_data['photos'] = prop_data['imageUrls']
                
                properties.append(prop_data)
            except Exception as e:
                print(f"Error processing property {doc.id}: {e}")
                continue
        
        print(f"✅ Found {len(properties)} properties in Firestore")
        return properties
        
    except Exception as e:
        print(f"❌ Error searching Firestore: {e}")
        return get_mock_properties()

def get_mock_properties():
    """Return mock properties for testing when Firestore is unavailable"""
    mock_properties = [
        {
            'id': 'mock_001',
            'title': 'Modern Apartment in Batangas City',
            'propertyType': 'apartment',
            'city': 'Batangas City',
            'monthlyRent': 15000,
            'bedrooms': '2',
            'bathrooms': '1',
            'floorArea': 45,
            'address': '123 Main Street, Batangas City',
            'description': 'Modern apartment with great amenities',
            'photos': ['https://via.placeholder.com/400x300/0b6e4f/ffffff?text=Apartment']
        },
        {
            'id': 'mock_002',
            'title': 'Family House in Lipa City',
            'propertyType': 'house',
            'city': 'Lipa City',
            'salePrice': 2500000,
            'bedrooms': '3',
            'bathrooms': '2',
            'floorArea': 120,
            'address': '456 Lipa Street, Lipa City',
            'description': 'Spacious family house near schools',
            'photos': ['https://via.placeholder.com/400x300/0b6e4f/ffffff?text=House']
        }
    ]
    return mock_properties

def generate_response(intent, entities, properties):
    """Generate natural language response based on intent"""
    
    if intent == "find_property":
        if properties:
            prop_type = entities.get('property_type', 'properties')
            location = entities.get('location', 'Batangas')
            return f"I found {len(properties)} {prop_type} properties in {location}. Here are some options:"
        else:
            return f"No {entities.get('property_type', 'properties')} found in {entities.get('location', 'that area')}. Try adjusting your search criteria."
    
    elif intent == "financing":
        if properties:
            financing = entities.get('financing_type', 'this financing option')
            return f"Found {len(properties)} properties that accept {financing}. Required documents usually include: Valid ID, Proof of Income, Bank Statements, and ITR."
        else:
            return f"No properties found that accept {entities.get('financing_type', 'this financing option')}."
    
    elif intent == "location_info":
        location = entities.get('location', 'Batangas')
        
        location_data = {
            'Batangas City': {
                'description': "Urban center with port, universities, and commercial areas.",
                'rents': "₱8,000-₱15,000 for apartments",
                'features': ["Port access", "Universities", "Commercial areas"]
            },
            'Lipa City': {
                'description': "Known as the 'Little Rome of the Philippines' and coffee capital.",
                'rents': "₱7,000-₱14,000 for apartments", 
                'features': ["Coffee plantations", "Educational institutions", "Cool climate"]
            },
            'Tanauan City': {
                'description': "Growing city with modern developments and commercial centers.",
                'rents': "₱6,000-₱12,000 for apartments",
                'features': ["Nuvali development", "Ayala Malls", "Residential communities"]
            }
        }
        
        if location in location_data:
            data = location_data[location]
            return f"About {location}: {data['description']} Average rents: {data['rents']}. Key features: {', '.join(data['features'])}."
        else:
            return f"{location} is part of Batangas province. It offers a mix of urban and rural living with affordable property options."
    
    else:
        if properties:
            return f"Found {len(properties)} properties matching your criteria."
        else:
            return "I can help you find properties in Batangas. Try asking about specific property types, locations, or financing options."

# Also update the chat endpoint to ensure proper JSON:
@app.route('/api/chat', methods=['POST'])
def chat():
    try:
        data = request.json
        query = data.get('query', '').strip()
        user_id = data.get('user_id', 'anonymous')
        
        if not query:
            return jsonify({'error': 'No query provided'}), 400
        
        print(f"\n📝 Query from {user_id}: '{query}'")
        
        # Step 1: Predict intent using trained model
        if vectorizer and classifier:
            try:
                X = vectorizer.transform([query])
                intent = classifier.predict(X)[0]
                confidence = float(classifier.predict_proba(X).max())
                print(f"🎯 Intent: {intent} (confidence: {confidence:.2%})")
            except Exception as e:
                print(f"⚠️ Model prediction failed: {e}")
                intent = "unknown"
                confidence = 0.0
        else:
            intent = "unknown"
            confidence = 0.0
            print(f"🎯 Fallback intent: {intent}")
        
        # Step 2: Extract entities
        entities = extract_entities_from_query(query)
        print(f"🏷️ Entities: {entities}")
        
        # Step 3: Search properties if needed
        properties = []
        if intent in ["find_property", "financing"]:
            properties = search_firestore_properties(entities)
        
        # Step 4: Generate response
        response_text = generate_response(intent, entities, properties)
        
        # Step 5: Prepare and return result
        result = {
            'success': True,
            'query': query,
            'intent': str(intent),  # Ensure string
            'entities': entities,
            'response': str(response_text),  # Ensure string
            'properties_found': len(properties),
            'properties': properties[:10],  # Limit to 10 properties
            'timestamp': datetime.now().isoformat(),
            'model_used': 'trained' if vectorizer else 'fallback',
            'confidence': float(confidence)  # Add confidence
        }
        
        print(f"📤 Returning {len(properties)} properties")
        return jsonify(result)
        
    except Exception as e:
        print(f"💥 Error in chat endpoint: {e}")
        return jsonify({
            'success': False,
            'error': str(e),
            'response': "I'm having trouble processing your request. Please try again or use the search filters."
        }), 500

@app.route('/api/health', methods=['GET'])
def health_check():
    """Health check endpoint"""
    return jsonify({
        'status': 'healthy',
        'service': 'Bah.AI Property Chatbot',
        'model_loaded': vectorizer is not None,
        'firebase_connected': db is not None,
        'timestamp': datetime.now().isoformat(),
        'version': '2.0.0'
    })

@app.route('/api/test', methods=['GET'])
def test_endpoint():
    """Test endpoint for debugging"""
    test_queries = [
        "find apartments in batangas city",
        "properties that accept bank financing",
        "tell me about lipa city",
        "show me houses under 3M with 3 bedrooms"
    ]
    
    results = []
    for query in test_queries:
        if vectorizer and classifier:
            X = vectorizer.transform([query])
            intent = classifier.predict(X)[0]
            confidence = classifier.predict_proba(X).max()
        else:
            intent = "unknown"
            confidence = 0
        
        entities = extract_entities_from_query(query)
        
        results.append({
            'query': query,
            'intent': intent,
            'confidence': float(confidence),
            'entities': entities
        })
    
    return jsonify({
        'test_results': results,
        'model_status': 'loaded' if vectorizer else 'not loaded',
        'firebase_status': 'connected' if db else 'not connected'
    })

@app.route('/api/properties/search', methods=['GET'])
def search_properties():
    """Direct property search endpoint"""
    try:
        # Get search parameters
        location = request.args.get('location')
        property_type = request.args.get('property_type')
        transaction_type = request.args.get('transaction_type')
        max_price = request.args.get('max_price')
        
        entities = {}
        if location:
            entities['location'] = location
        if property_type:
            entities['property_type'] = property_type
        
        properties = search_firestore_properties(entities)
        
        return jsonify({
            'success': True,
            'count': len(properties),
            'properties': properties
        })
        
    except Exception as e:
        return jsonify({
            'success': False,
            'error': str(e)
        }), 500

# ==================== CLOUD FUNCTIONS SUPPORT ====================
@functions_framework.http
def cloud_function_chat(request):
    """Google Cloud Functions entry point"""
    # Set CORS headers for the preflight request
    if request.method == 'OPTIONS':
        headers = {
            'Access-Control-Allow-Origin': '*',
            'Access-Control-Allow-Methods': 'POST, GET, OPTIONS',
            'Access-Control-Allow-Headers': 'Content-Type',
            'Access-Control-Max-Age': '3600'
        }
        return ('', 204, headers)
    
    # Set CORS headers for main request
    headers = {'Access-Control-Allow-Origin': '*'}
    
    # Route to appropriate function
    if request.path == '/api/chat' and request.method == 'POST':
        with app.test_request_context(path=request.path, 
                                     method=request.method,
                                     json=request.get_json(silent=True)):
            response = chat()
            return (response.get_data(), response.status_code, headers)
    
    elif request.path == '/api/health' and request.method == 'GET':
        with app.test_request_context(path=request.path, 
                                     method=request.method):
            response = health_check()
            return (response.get_data(), response.status_code, headers)
    
    return ('Not Found', 404, headers)

# ==================== MAIN ====================
if __name__ == '__main__':
    print("\n" + "="*60)
    print("🚀 BAH.AI PROPERTY CHATBOT BACKEND v2.0")
    print("="*60)
    print(f"📂 Model: {'Loaded' if vectorizer else 'Not loaded'}")
    print(f"🔥 Firebase: {'Connected' if db else 'Mock mode'}")
    print(f"🌐 Local URL: http://localhost:5000")
    print(f"☁️  Cloud Functions: Ready")
    print("="*60 + "\n")
    
    # Run the Flask server
    app.run(host='0.0.0.0', port=5000, debug=True)