# backend/chatbot_backend.py - UPDATED VERSION
from flask import Flask, request, jsonify
from flask_cors import CORS
import pickle
import firebase_admin
from firebase_admin import credentials, firestore
import re
import json
import os
from datetime import datetime
import logging
from typing import Dict, List, Any, Optional
import spacy
import numpy as np
import random

# Set up logging
logging.basicConfig(level=logging.DEBUG, format='%(asctime)s - %(name)s - %(levelname)s - %(message)s')
logger = logging.getLogger(__name__)

app = Flask(__name__)
CORS(app, resources={r"/api/*": {"origins": "*"}})

# CONFIGURATION
MODEL_PATH = 'models/nlu_model.pkl'
TRAINING_DATA_PATH = 'data/member1/training_data.json'

# Global variables
vectorizer = None
classifier = None
db = None
nlp = None
model_classes = []  # Store model classes separately
training_data = {}  # Store training data for response templates

# Initialize Firebase
try:
    cred_path = '../serviceAccountKey.json'
    if os.path.exists(cred_path):
        cred = credentials.Certificate(cred_path)
        firebase_admin.initialize_app(cred)
        db = firestore.client()
        logger.info("✅ Firebase connected successfully")
    else:
        logger.warning(f"⚠️ Firebase service account file not found: {cred_path}")
        db = None
except Exception as e:
    logger.error(f"❌ Firebase connection failed: {e}")
    db = None

# Initialize spaCy for entity extraction
try:
    nlp = spacy.load("en_core_web_sm")
    logger.info("✅ spaCy model loaded for entity extraction")
except:
    logger.warning("⚠️ spaCy model not found. Using basic entity extraction.")
    nlp = None

# Load training data for response templates
def load_training_data():
    """Load training data for response templates"""
    global training_data
    
    try:
        if os.path.exists(TRAINING_DATA_PATH):
            with open(TRAINING_DATA_PATH, 'r', encoding='utf-8') as f:
                training_data = json.load(f)
            logger.info(f"✅ Training data loaded from {TRAINING_DATA_PATH}")
            
            # Debug: Check if location profiles have descriptions and lifestyle
            if 'location_profiles' in training_data:
                logger.info(f"📊 Found {len(training_data['location_profiles'])} location profiles")
                for location, profile in training_data['location_profiles'].items():
                    logger.info(f"  📍 {location}: desc={bool(profile.get('description'))}, lifestyle={bool(profile.get('lifestyle'))}")
        else:
            logger.warning(f"⚠️ Training data file not found: {TRAINING_DATA_PATH}")
            training_data = {}
    except Exception as e:
        logger.error(f"❌ Error loading training data: {e}")
        training_data = {}

# Load NLU model
def load_nlu_model():
    """Load the trained NLU model from train_nlu.py"""
    global vectorizer, classifier, model_classes
    
    try:
        if os.path.exists(MODEL_PATH):
            logger.info(f"📂 Loading model from {MODEL_PATH}")
            with open(MODEL_PATH, 'rb') as f:
                model_data = pickle.load(f)
            
            vectorizer = model_data.get('vectorizer')
            classifier = model_data.get('classifier')
            
            if classifier and hasattr(classifier, 'classes_'):
                model_classes = classifier.classes_.tolist()
                logger.info(f"✅ NLU model loaded successfully (v{model_data.get('version', '1.0')})")
                logger.info(f"📊 Model intents: {model_classes}")
                logger.info(f"📊 Feature count: {len(vectorizer.get_feature_names_out()) if vectorizer else 0}")
            else:
                logger.warning("⚠️ Classifier doesn't have classes_ attribute")
                
        else:
            logger.error(f"❌ Model file not found: {MODEL_PATH}")
            logger.error("💡 Run train_nlu.py first to create the model!")
            
    except Exception as e:
        logger.error(f"❌ Error loading NLU model: {e}")
        import traceback
        logger.error(f"Traceback: {traceback.format_exc()}")

# Preprocess text for prediction (same as training)
def preprocess_text(text):
    """Preprocess text for prediction"""
    if not text:
        return ""
    
    text = str(text).lower()
    
    # Remove special characters but keep spaces and basic punctuation
    text = re.sub(r'[^\w\s\?\.]', ' ', text)
    
    # Remove extra spaces
    text = re.sub(r'\s+', ' ', text).strip()
    
    return text

# Entity extraction - FIXED VERSION
def extract_entities_from_query(query: str) -> Dict[str, Any]:
    """Extract entities from user query"""
    entities = {
        'property_type': None,
        'location': None,
        'landmark': None,
        'feature': None,  # Fixed typo: was 'feature': Nonee
        'price_range': None,  # Fixed typo: was 'priice_range': None
        'bedrooms': None,
        'bathrooms': None,
        'financing_type': None
    }
    
    query_lower = query.lower()
    
    # Property type detection
    property_types = ['apartment', 'condo', 'condominium', 'house', 'villa', 'townhouse', 
                     'bungalow', 'duplex', 'commercial', 'office', 'retail',
                     'warehouse', 'studio', 'room', 'boarding house', 'dormitory',
                     'penthouse', 'residential', 'industrial', 'farm', 'beachfront',
                     'lakeview', 'heritage', 'resort']
    
    for prop_type in property_types:
        if prop_type in query_lower:
            entities['property_type'] = prop_type
            break
    
    # Location detection - More comprehensive
    batangas_locations = [
        'batangas city', 'lipa city', 'tanauan city', 'bauan', 'balayan',
        'nasugbu', 'san juan', 'taal', 'calatagan', 'mabini', 'rosario',
        'sto. tomas', 'sto tomas', 'santo tomas', 'malvar', 'ibaan', 'tuy', 
        'lian', 'taysan', 'san luis', 'padre garcia', 'laurel', 'agoncillo',
        'san pascual', 'cuenca', 'alitagtag', 'lobo', 'san nicolas',
        'mataasnakahoy', 'talisay', 'la paz', 'lemery'
    ]
    
    for location in batangas_locations:
        if location in query_lower:
            entities['location'] = location.title()
            break
    
    # Feature detection
    features = ['swimming pool', 'pool', 'garden', 'parking', 'elevator', 
                'security', 'wifi', 'furnished', 'aircon', 'parking space',
                'home office', 'furniture', 'private pool', 'backyard']
    
    for feature in features:
        if feature in query_lower:
            entities['feature'] = feature
            break
    
    # Landmark detection
    if 'near' in query_lower or 'close to' in query_lower or 'around' in query_lower or 'beside' in query_lower:
        # Extract word after landmark terms
        match = re.search(r'(?:near|close to|around|beside|next to)\s+(\w+\s*\w*)', query_lower)
        if match:
            entities['landmark'] = match.group(1).strip()
    
    # Price range detection
    price_patterns = [
        (r'under\s+(\d+[kKmM]?)', 'under'),
        (r'below\s+(\d+[kKmM]?)', 'below'),
        (r'less than\s+(\d+[kKmM]?)', 'less than'),
        (r'(\d+[kKmM]?)\s+(pesos|php|million|m)', 'exact'),
        (r'(\d+)\s+million', 'million'),
        (r'(\d+)\s+k', 'thousand')
    ]
    
    for pattern, price_type in price_patterns:
        match = re.search(pattern, query_lower)
        if match:
            entities['price_range'] = f"{price_type} {match.group(1)}"
            break
    
    # Bedroom detection
    bed_match = re.search(r'(\d+)\s+bedroom', query_lower)
    if bed_match:
        entities['bedrooms'] = int(bed_match.group(1))
    elif 'studio' in query_lower:
        entities['bedrooms'] = 'studio'
    
    # Bathroom detection
    bath_match = re.search(r'(\d+)\s+bathroom', query_lower)
    if bath_match:
        entities['bathrooms'] = int(bath_match.group(1))
    
    # Financing type detection
    financing_types = ['bank financing', 'bank loan', 'pag-ibig', 'in-house financing', 
                      'cash', 'installment', 'mortgage', 'loan', 'developer financing',
                      'housing loan', 'home loan', 'property loan', 'pagibig']
    
    for financing in financing_types:
        if financing in query_lower:
            entities['financing_type'] = financing
            break
    
    return entities

# Firestore queries
def search_firestore_properties(entities: Dict[str, Any]) -> List[Dict[str, Any]]:
    """Search properties in Firestore based on entities"""
    properties = []
    
    if not db:
        logger.warning("⚠️ Firebase not connected, returning mock data")
        # Return mock data for testing
        mock_locations = {
            'Batangas City': ['Pallocan', 'Kumintang', 'Bolinao'],
            'Lipa City': ['Banay-banay', 'Antipolo', 'Sabang'],
            'Tanauan City': ['Pantay', 'Sambat', 'Trapiche'],
            'Nasugbu': ['Calayo', 'Wawa', 'Bucana'],
            'Taal': ['Poblacion', 'Caysasay', 'San Isidro']
        }
        
        location = entities.get('location', 'Batangas City')
        property_type = entities.get('property_type', 'house')
        
        # Generate mock properties based on entities
        for i in range(3):
            area = mock_locations.get(location, ['Unknown Area'])[i % len(mock_locations.get(location, ['Unknown Area']))]
            properties.append({
                'id': f'mock_{i+1}',
                'title': f'{property_type.title()} in {area}',
                'type': property_type,
                'location': location,
                'price': f'₱{random.randint(2, 10)}.{random.randint(0, 99)}M',
                'bedrooms': entities.get('bedrooms', random.randint(2, 4)),
                'bathrooms': entities.get('bathrooms', random.randint(1, 3)),
                'features': [entities.get('feature', 'parking')] if entities.get('feature') else ['parking', 'garden'],
                'description': f'Beautiful {property_type} located in {area}, {location}. Perfect for {entities.get("property_type", "residential")} use.'
            })
        return properties
    
    try:
        properties_ref = db.collection('properties')
        
        # Build query filters based on entities
        query_filters = []
        
        if entities.get('property_type'):
            query_filters.append(('property_type', '==', entities['property_type']))
        
        if entities.get('location'):
            query_filters.append(('location', '==', entities['location']))
        
        if entities.get('bedrooms'):
            query_filters.append(('bedrooms', '==', entities['bedrooms']))
        
        # Apply filters
        query = properties_ref
        for field, op, value in query_filters:
            query = query.where(field, op, value)
        
        # Execute query
        docs = query.limit(10).get()
        
        for doc in docs:
            property_data = doc.to_dict()
            property_data['id'] = doc.id
            properties.append(property_data)
            
        logger.info(f"🔍 Found {len(properties)} properties in Firestore")
        
    except Exception as e:
        logger.error(f"❌ Error searching Firestore: {e}")
    
    return properties

# Generate response from training data templates - IMPROVED VERSION
def generate_response(intent: str, entities: Dict[str, Any], properties: List[Dict[str, Any]]) -> str:
    """Generate response based on intent and entities using training data templates"""
    
    # Default fallback responses
    default_responses = {
        'find_property': "I understand you're looking for properties. Could you specify the location or property type?",
        'find_near_landmark': "I can help you find properties near landmarks. What specific landmark are you interested in?",
        'financing': "I can provide information about financing options. Which type of financing are you interested in?",
        'location_info': "I can tell you about different locations in Batangas. Which location would you like to know about?",
        'find_with_feature': "I can help you find properties with specific features. What feature are you looking for?",
        'find_ready_property': "I can help you find ready-to-move-in properties. What location are you interested in?",
        'process_info': "I can explain property purchase processes. What specific process are you interested in?",
        'match_needs': "I can match properties to your needs. What are your specific requirements?",
        'find_property_for_need': "I can find properties suitable for specific needs. What type of need are you looking for?",
        'find_property_with_criteria': "I can find properties matching specific criteria. What criteria do you have?",
        'unknown': "I understand you're looking for property information in Batangas. Could you provide more details about what you need?"
    }
    
    # Try to find matching template from training data
    if training_data and 'training_samples' in training_data:
        # Look for samples with matching intent
        matching_samples = [s for s in training_data['training_samples'] if s.get('intent') == intent]
        
        if matching_samples:
            # Try to find the best matching sample based on entities
            best_sample = None
            for sample in matching_samples:
                sample_entities = sample.get('entities', {})
                
                # Check if sample entities match query entities
                match_score = 0
                for key, value in sample_entities.items():
                    if entities.get(key) and value and str(value).lower() in str(entities.get(key)).lower():
                        match_score += 1
                
                if match_score > 0 and (not best_sample or match_score > best_sample.get('match_score', 0)):
                    sample['match_score'] = match_score
                    best_sample = sample
            
            if best_sample and 'response_template' in best_sample:
                # Fill the template with actual data
                template = best_sample['response_template']
                
                # Replace placeholders with actual values
                replacements = {
                    '{count}': str(len(properties)),
                    '{property_type}': entities.get('property_type', 'property'),
                    '{location}': entities.get('location', 'the area'),
                    '{financing_type}': entities.get('financing_type', 'financing'),
                    '{feature}': entities.get('feature', 'feature'),
                    '{landmark}': entities.get('landmark', 'landmark'),
                    '{bedrooms}': str(entities.get('bedrooms', '')),
                    '{price_range}': entities.get('price_range', '')
                }
                
                # Add property list if we have properties
                if properties:
                    property_list = "\n"
                    for i, prop in enumerate(properties[:3]):
                        title = prop.get('title', f'Property {i+1}')
                        price = prop.get('price', 'Price not available')
                        location = prop.get('location', 'Location not specified')
                        property_list += f"{i+1}. **{title}** in {location} - {price}\n"
                    replacements['{property_list}'] = property_list
                else:
                    replacements['{property_list}'] = "No specific properties found with those criteria."
                
                # Add sample-specific data from training data
                for key, value in best_sample.items():
                    if key.startswith('location_description') or key.startswith('average_') or key in ['documents_list', 'requirements_list', 'key_features', 'average_prices', 'ideal_for', 'property_types']:
                        if value is not None:
                            if isinstance(value, list):
                                replacements[f'{{{key}}}'] = '\n'.join([f"• {item}" for item in value])
                            else:
                                replacements[f'{{{key}}}'] = str(value)
                
                # Perform replacements
                response = template
                for placeholder, replacement in replacements.items():
                    # Convert None to empty string
                    if replacement is None:
                        replacement = ''
                    response = response.replace(placeholder, str(replacement))
                
                # Also replace generic placeholders like {description} and {lifestyle}
                if intent == 'location_info' and entities.get('location'):
                    location_name = entities['location']
                    if training_data and 'location_profiles' in training_data:
                        location_profile = training_data['location_profiles'].get(location_name)
                        if location_profile:
                            # Replace placeholders from location profile
                            for key, value in location_profile.items():
                                if value is not None:
                                    response = response.replace(f'{{{key}}}', str(value))
                
                return response
    
    # Fallback to default response
    response = default_responses.get(intent, default_responses['unknown'])
    
    # Add location-specific information for location_info intent
    if intent == 'location_info' and entities.get('location'):
        location_name = entities['location']
        if training_data and 'location_profiles' in training_data:
            location_profile = training_data['location_profiles'].get(location_name)
            if location_profile:
                # Get description and lifestyle, provide defaults if missing
                description = location_profile.get('description', 'No description available.')
                lifestyle = location_profile.get('lifestyle', 'No lifestyle information available.')
                
                response = f"📍 **About {location_name}**\n"
                response += f"**Description:** {description}\n\n"
                response += f"**Lifestyle:** {lifestyle}\n\n"
                
                if 'key_features' in location_profile and location_profile['key_features']:
                    response += "**Key Features:**\n"
                    for feature in location_profile['key_features']:
                        response += f"• {feature}\n"
                    response += "\n"
                
                if 'average_prices' in location_profile and location_profile['average_prices']:
                    response += "**Average Property Prices:**\n"
                    for price_info in location_profile['average_prices']:
                        response += f"• {price_info}\n"
                    response += "\n"
                
                if 'ideal_for' in location_profile and location_profile['ideal_for']:
                    response += f"**Ideal For:** {', '.join(location_profile['ideal_for'])}\n\n"
                
                if 'property_types' in location_profile and location_profile['property_types']:
                    response += f"**Property Types Available:** {', '.join(location_profile['property_types'])}\n"
                
                # Add property details if available
                if properties and len(properties) > 0:
                    response += "\n**Available Properties:**\n"
                    for i, prop in enumerate(properties[:3]):
                        title = prop.get('title', f'Property {i+1}')
                        price = prop.get('price', 'Price not available')
                        location = prop.get('location', 'Location not specified')
                        response += f"{i+1}. **{title}** in {location} - {price}\n"
                
                return response
        else:
            # No location profile found, provide generic response
            response = f"I can tell you about {location_name} in Batangas.\n\n"
            response += f"{location_name} is one of the key locations in Batangas province with various property options available.\n\n"
            response += "If you're interested in properties here, you might want to specify what type of property you're looking for (apartment, house, condo, etc.) or your budget range."
    
    # For other intents, add property details if available
    elif properties and len(properties) > 0:
        response += "\n\n**Available Properties:**\n"
        for i, prop in enumerate(properties[:3]):
            title = prop.get('title', f'Property {i+1}')
            price = prop.get('price', 'Price not available')
            location = prop.get('location', 'Location not specified')
            response += f"{i+1}. **{title}** in {location} - {price}\n"
    
    # Add financing information for financing intent
    if intent == 'financing' and entities.get('financing_type'):
        financing_type = entities['financing_type']
        if training_data and 'financing_info' in training_data:
            # Try to find matching financing info
            financing_key = financing_type.lower().replace(' ', '_')
            if financing_key in training_data['financing_info']:
                financing_info = training_data['financing_info'][financing_key]
                response += f"\n\n🏦 **{financing_type.title()} Information**\n"
                
                if 'documents' in financing_info:
                    response += "\n**Required Documents:**\n"
                    for i, doc in enumerate(financing_info['documents'], 1):
                        response += f"{i}. {doc}\n"
                
                if 'requirements' in financing_info:
                    response += "\n**Basic Requirements:**\n"
                    for i, req in enumerate(financing_info['requirements'], 1):
                        response += f"{i}. {req}\n"
    
    return response

# API ENDPOINTS
@app.route('/api/chat', methods=['POST'])
def chat():
    """Main chatbot endpoint"""
    try:
        data = request.json
        if not data:
            return jsonify({'error': 'No JSON data provided'}), 400
        
        query = data.get('query', '').strip()
        
        if not query:
            return jsonify({'error': 'No query provided'}), 400
        
        logger.info(f"💬 Query: '{query}'")
        
        # Step 1: Predict intent
        intent = "unknown"
        confidence = 0.0
        
        if vectorizer and classifier:
            try:
                processed_query = preprocess_text(query)
                X = vectorizer.transform([processed_query])
                intent = classifier.predict(X)[0]
                proba = classifier.predict_proba(X)[0]
                confidence = float(max(proba))
                logger.info(f"🎯 Intent: {intent} (confidence: {confidence:.2%})")
                
                # Log alternative intents for low confidence
                if confidence < 0.7:
                    top_indices = np.argsort(proba)[-3:][::-1]
                    logger.info("   Low confidence alternatives:")
                    for idx in top_indices:
                        alt_intent = model_classes[idx] if idx < len(model_classes) else "unknown"
                        alt_prob = proba[idx]
                        logger.info(f"     • {alt_intent}: {alt_prob:.2%}")
                        
            except Exception as e:
                logger.error(f"❌ Model prediction failed: {e}")
                intent = determine_intent_fallback(query)
        else:
            # Model not loaded - use fallback
            intent = determine_intent_fallback(query)
        
        # Step 2: Extract entities
        entities = extract_entities_from_query(query)
        logger.info(f"🏷️ Entities: {entities}")
        
        # Step 3: Search properties if needed
        properties = []
        if intent in ["find_property", "find_near_landmark", "find_with_feature", 
                     "find_ready_property", "find_property_for_need", 
                     "find_property_with_criteria", "match_needs"]:
            properties = search_firestore_properties(entities)
        
        # Step 4: Generate response using training data templates
        response_text = generate_response(intent, entities, properties)
        
        # Step 5: Prepare result
        result = {
            'success': True,
            'query': query,
            'intent': intent,
            'confidence': confidence,
            'entities': entities,
            'response': response_text,
            'properties_found': len(properties),
            'properties': properties[:5],  # Limit to 5 properties
            'model_version': 'trained' if vectorizer else 'fallback'
        }
        
        return jsonify(result)
        
    except Exception as e:
        logger.error(f"❌ Error in chat endpoint: {e}")
        import traceback
        logger.error(f"Traceback: {traceback.format_exc()}")
        
        return jsonify({
            'success': False,
            'error': str(e),
            'response': "I encountered an error processing your request. Please try again with a different query."
        }), 500

# Simple fallback if model isn't loaded
def determine_intent_fallback(query: str) -> str:
    """Simple rule-based intent detection as fallback"""
    query_lower = query.lower()
    
    if any(word in query_lower for word in ['steps', 'process', 'procedure', 'how to', 'timeline']):
        return 'process_info'
    elif any(word in query_lower for word in ['financing', 'loan', 'mortgage', 'pag-ibig', 'bank', 'installment']):
        return 'financing'
    elif any(word in query_lower for word in ['near', 'close to', 'around', 'beside', 'next to']):
        return 'find_near_landmark'
    elif any(word in query_lower for word in ['ready', 'available now', 'immediate', 'move in']):
        return 'find_ready_property'
    elif any(word in query_lower for word in ['with', 'featuring', 'having', 'includes']):
        return 'find_with_feature'
    elif any(word in query_lower for word in ['family', 'student', 'professional', 'retiree', 'couple']):
        return 'find_property_for_need'
    elif any(word in query_lower for word in ['under', 'below', 'less than', 'budget', 'affordable']):
        return 'find_property_with_criteria'
    elif any(word in query_lower for word in ['about', 'describe', 'tell me about', 'information about']):
        return 'location_info'
    elif any(word in query_lower for word in ['find', 'search', 'show me', 'looking for', 'need']):
        return 'find_property'
    
    return 'unknown'

@app.route('/api/health', methods=['GET'])
def health_check():
    """Health check endpoint"""
    return jsonify({
        'status': 'healthy',
        'service': 'Bah.AI Property Chatbot',
        'version': '3.4',
        'model_loaded': vectorizer is not None and classifier is not None,
        'training_data_loaded': bool(training_data),
        'firebase_connected': db is not None,
        'model_intents': model_classes,
        'model_features': len(vectorizer.get_feature_names_out()) if vectorizer else 0,
        'spacy_loaded': nlp is not None,
        'timestamp': datetime.now().isoformat()
    })

@app.route('/api/test', methods=['GET'])
def test_endpoint():
    """Test endpoint to verify the model is working"""
    test_queries = [
        "find apartments in batangas city",
        "properties near schools",
        "how to get a mortgage",
        "tell me about lipa city",
        "houses with swimming pool"
    ]
    
    results = []
    for query in test_queries:
        try:
            if vectorizer and classifier:
                processed = preprocess_text(query)
                X = vectorizer.transform([processed])
                intent = classifier.predict(X)[0]
                confidence = float(classifier.predict_proba(X).max())
                results.append({
                    'query': query,
                    'intent': intent,
                    'confidence': confidence
                })
        except Exception as e:
            results.append({
                'query': query,
                'error': str(e)
            })
    
    return jsonify({
        'test_results': results,
        'model_status': 'loaded' if vectorizer else 'not loaded',
        'training_data_status': 'loaded' if training_data else 'not loaded'
    })

# ==================== MAIN ====================
if __name__ == '__main__':
    print("\n" + "="*60)
    print("🚀 BAH.AI PROPERTY CHATBOT BACKEND v3.4")
    print("   (Uses trained NLU model + response templates)")
    print("="*60)
    
    # Load the trained model
    load_nlu_model()
    
    # Load training data for response templates
    load_training_data()
    
    print(f"\n📂 NLU Model: {'✅ Loaded' if vectorizer else '❌ Not loaded'}")
    print(f"📚 Training Data: {'✅ Loaded' if training_data else '❌ Not loaded'}")
    print(f"🔥 Firebase: {'✅ Connected' if db else '❌ Not connected'}")
    print(f"📊 spaCy: {'✅ Loaded' if nlp else '❌ Not loaded'}")
    
    if vectorizer:
        print(f"📊 Model intents: {len(model_classes)} intents")
        print(f"📊 Available intents: {', '.join(model_classes)}")
    else:
        print("\n⚠️  WARNING: NLU model not loaded!")
        print("💡 To fix this:")
        print("   1. Run: python train_nlu.py")
        print("   2. Make sure models/nlu_model.pkl exists")
        print("   3. Check the model file path")
    
    print("\n🌐 API Endpoints:")
    print("   POST /api/chat   - Chatbot endpoint")
    print("   GET  /api/health - Health check")
    print("   GET  /api/test   - Test model predictions")
    print("="*60 + "\n")
    
    app.run(host='0.0.0.0', port=5000, debug=True)