# backend/chatbot_backend.py - COMPLETE UPDATED VERSION
from flask import Flask, request, jsonify
from pathlib import Path
from flask_cors import CORS
from dotenv import load_dotenv
import pickle
import firebase_admin
import warnings
from firebase_admin import credentials, firestore
import re
import json
import os
from datetime import datetime
import logging
from google.cloud.firestore_v1 import FieldFilter, ArrayRemove, ArrayUnion
from typing import Dict, List, Any, Optional
import numpy as np
import random
import sys
from collections import defaultdict

load_dotenv('.env.local') 
# Debug: Check if env var is loaded
print("\n" + "="*60)
print("🔍 ENVIRONMENT VARIABLE CHECK")
print("="*60)
firebase_env = os.getenv('FIREBASE_SERVICE_ACCOUNT_JSON')
if firebase_env:
    try:
        import json
        data = json.loads(firebase_env)
        print(f"✅ FIREBASE_SERVICE_ACCOUNT_JSON found!")
        print(f"📋 Project ID: {data.get('project_id')}")
        print(f"🔑 Private key ID: {data.get('private_key_id', '')[:10]}...")
    except json.JSONDecodeError as e:
        print(f"❌ Invalid JSON in environment variable: {e}")
    except Exception as e:
        print(f"❌ Error parsing JSON: {e}")
else:
    print("❌ FIREBASE_SERVICE_ACCOUNT_JSON environment variable not found")
    print("💡 Create a .env.local file with your Firebase credentials")
print("="*60 + "\n")

warnings.filterwarnings("ignore", message="Detected filter using positional arguments")
# Set up logging
logging.basicConfig(level=logging.DEBUG, format='%(asctime)s - %(name)s - %(levelname)s - %(message)s')
logger = logging.getLogger(__name__)

app = Flask(__name__)
CORS(app, resources={r"/api/*": {"origins": "*"}})

# CONFIGURATION
PROJECT_ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
MODEL_PATH =  os.path.join(PROJECT_ROOT, 'training', 'models', 'nlu_model.pkl')
TRAINING_DATA_PATH = os.path.join(PROJECT_ROOT, 'training', 'data', 'member1', 'training_data.json')

# Global variables
vectorizer = None
classifier = None
db = None
nlp = None
model_classes = []  # Store model classes separately
training_data = {}  # Store training data for response templates

print("\n" + "="*60)
print("🔥 FIREBASE CONNECTION")
print("="*60)

# Initialize Firebase
try:
    # Try to get Firebase credentials from environment variable
    firebase_json_str = os.environ.get('FIREBASE_SERVICE_ACCOUNT_JSON')
    
    if firebase_json_str:
        print("🔑 Found Firebase credentials in environment variable")
        
        try:
            # Parse the JSON string
            firebase_credentials = json.loads(firebase_json_str)
            
            print(f"✅ Valid JSON format")
            print(f"📋 Project ID: {firebase_credentials.get('project_id')}")
            print(f"📧 Client Email: {firebase_credentials.get('client_email')}")
            
            # IMPORTANT: Check if Firebase Admin SDK is already initialized
            if firebase_admin._DEFAULT_APP_NAME in firebase_admin._apps:
                print("⚠️  Firebase already initialized, using existing app")
                db = firestore.client()
            else:
                # Initialize with credentials from environment variable
                cred = credentials.Certificate(firebase_credentials)
                
                # Initialize with specific parameters
                firebase_admin.initialize_app(cred, {
                    'projectId': firebase_credentials.get('project_id', 'bahai-1b76d'),
                    'databaseURL': 'https://bahai-1b76d.firebaseio.com',
                    'storageBucket': 'bahai-1b76d.appspot.com',
                })
                
                print("✅ Firebase Admin SDK initialized")
                db = firestore.client()
                
            print("✅ Firebase connected successfully!")
            
            # Test connection with error handling
            try:
                print("🔍 Testing Firestore connection...")
                properties_ref = db.collection('properties')
                docs = list(properties_ref.limit(10).get())  # Limit to 10 for testing
                print(f"📊 Found {len(docs)} properties in database")
                
                if docs:
                    print("✅ Firestore connection successful!")
                    
                    # Show property types and count
                    property_types = {}
                    for doc in docs:
                        data = doc.to_dict()
                        prop_type = data.get('propertyType', data.get('type', 'unknown'))
                        if prop_type not in property_types:
                            property_types[prop_type] = 0
                        property_types[prop_type] += 1
                        
                    print(f"🔍 Property types found:")
                    for prop_type, count in property_types.items():
                        print(f"   • {prop_type}: {count} properties")
                    
                    # Show first few properties for debugging
                    print("\n📋 Sample properties:")
                    for i, doc in enumerate(docs[:5]):
                        data = doc.to_dict()
                        doc_id = doc.id
                        prop_type = data.get('propertyType', data.get('type', 'unknown'))
                        city = data.get('city', 'Unknown')
                        status = data.get('status', 'No Status')
                        sale_type = data.get('saleType', 'No saleType')
                        print(f"   {i+1}. ID: {doc_id[:10]}..., Type: {prop_type}, City: {city}, Status: {status}, SaleType: {sale_type}")
                        
                else:
                    print("⚠️ No properties found in database (empty collection)")
                    
            except Exception as e:
                print(f"⚠️ Firestore query warning: {str(e)}")
                print("💡 The connection is established but the query failed")
                print("   This might be normal if the collection structure is different")
                
        except json.JSONDecodeError as e:
            print(f"❌ Invalid JSON in environment variable: {e}")
            print("💡 Make sure FIREBASE_SERVICE_ACCOUNT_JSON contains valid JSON")
            db = None
        except Exception as e:
            print(f"❌ Error loading Firebase credentials: {e}")
            import traceback
            traceback.print_exc()
            db = None
            
    else:
        print("❌ FIREBASE_SERVICE_ACCOUNT_JSON environment variable not found")
        print("💡 Please add your Firebase service account JSON to the environment variable")
        print("   In Render: Environment → Add Environment Variable")
        print("   Name: FIREBASE_SERVICE_ACCOUNT_JSON")
        print("   Value: Your entire service account JSON content")
        db = None
        
except Exception as e:
    print(f"❌ Firebase connection failed: {e}")
    import traceback
    traceback.print_exc()
    print("\n⚠️  Switching to mock data mode")
    db = None

# Load training data for response templates
def load_training_data():
    """Load training data for response templates"""
    global training_data
    
    print(f"\n🔍 DEBUG: Loading training data from {TRAINING_DATA_PATH}")
    print(f"📁 TRAINING_DATA_PATH exists: {os.path.exists(TRAINING_DATA_PATH)}")
    
    try:
        if os.path.exists(TRAINING_DATA_PATH):
            with open(TRAINING_DATA_PATH, 'r', encoding='utf-8') as f:
                training_data = json.load(f)
            logger.info(f"✅ Training data loaded from {TRAINING_DATA_PATH}")
            
            # Debug: Check if location profiles have descriptions and lifestyle
            if 'location_profiles' in training_data:
                logger.info(f"📊 Found {len(training_data['location_profiles'])} location profiles")
        else:
            logger.warning(f"⚠️ Training data file not found: {TRAINING_DATA_PATH}")
            
            # Check if data directory exists
            data_dir = os.path.dirname(TRAINING_DATA_PATH)
            print(f"📁 Checking data directory: {data_dir}")
            print(f"📁 Data directory exists: {os.path.exists(data_dir)}")
            
            if os.path.exists(data_dir):
                print("📁 Contents of data directory:")
                for item in os.listdir(data_dir):
                    item_path = os.path.join(data_dir, item)
                    if os.path.isdir(item_path):
                        print(f"  📁 {item}/")
                    else:
                        print(f"  📄 {item}")
            
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

# Entity extraction - UPDATED TO USE sale_type INSTEAD OF financing_type
def extract_entities_from_query(query: str) -> Dict[str, Any]:
    """Extract entities from user query"""
    entities = {
        'property_type': None,
        'location': None,
        'landmark': None,
        'feature': None,
        'price_range': None,
        'bedrooms': None,
        'bathrooms': None,
        'sale_type': None,  # CHANGED: from financing_type to sale_type
        'listing_type': None,
        'has_general_search': False,
        'max_price': None,
        'min_price': None,
        'min_bedrooms': None,
        'exact_bedrooms': None
    }
    
    query_lower = query.lower()
    
    # ========== PROPERTY TYPE DETECTION ==========
    # Check for condo variations FIRST
    if any(term in query_lower for term in ['condo', 'condos', 'condominium', 'condominiums']):
        entities['property_type'] = 'condo'
    elif 'apartment' in query_lower or 'apartments' in query_lower:
        entities['property_type'] = 'apartment'
    elif 'house' in query_lower or 'houses' in query_lower:
        entities['property_type'] = 'house'
    elif 'townhouse' in query_lower or 'townhouses' in query_lower:
        entities['property_type'] = 'townhouse'
    elif 'commercial' in query_lower:
        entities['property_type'] = 'commercial'
    elif 'land' in query_lower or 'lot' in query_lower:
        entities['property_type'] = 'land'
        
    # ========== NEW: Parse numeric price values for filtering ==========
    max_price = None
    min_price = None
    
    # Patterns for price extraction (convert M to millions, k to thousands)
    price_patterns = [
        # "under 15M" or "under 15 M"
        (r'under\s+(\d+(?:\.\d+)?)\s*([mM])\b', lambda m: float(m.group(1)) * 1000000, 'max'),
        # "below 15 million" or "below 15million"
        (r'below\s+(\d+(?:\.\d+)?)\s*million\b', lambda m: float(m.group(1)) * 1000000, 'max'),
        # "under ₱15M" or "below ₱15M"
        (r'(?:under|below)\s*₱?\s*(\d+(?:\.\d+)?)\s*([mM])\b', lambda m: float(m.group(1)) * 1000000, 'max'),
        # "under 15000000" or "below 15000000"
        (r'(?:under|below)\s+(\d{7,})\b', lambda m: float(m.group(1)), 'max'),
        # "less than 15M"
        (r'less\s+than\s+(\d+(?:\.\d+)?)\s*([mM])\b', lambda m: float(m.group(1)) * 1000000, 'max'),
        # "maximum 15M"
        (r'maximum\s+(\d+(?:\.\d+)?)\s*([mM])\b', lambda m: float(m.group(1)) * 1000000, 'max'),
        # "up to 15M"
        (r'up\s+to\s+(\d+(?:\.\d+)?)\s*([mM])\b', lambda m: float(m.group(1)) * 1000000, 'max'),
        # "above 5M" or "over 5M"
        (r'(?:above|over)\s+(\d+(?:\.\d+)?)\s*([mM])\b', lambda m: float(m.group(1)) * 1000000, 'min'),
        # "minimum 5M"
        (r'minimum\s+(\d+(?:\.\d+)?)\s*([mM])\b', lambda m: float(m.group(1)) * 1000000, 'min'),
        # "from 5M to 10M" or "between 5M and 10M"
        (r'(?:from|between)\s+(\d+(?:\.\d+)?)\s*([mM])?\s*(?:to|and)\s+(\d+(?:\.\d+)?)\s*([mM]?)', 
         lambda m: (float(m.group(1)) * (1000000 if m.group(2) else 1), 
                   float(m.group(3)) * (1000000 if m.group(4) else 1)), 'range'),
        # Simple number with M (e.g., "15M house")
        (r'\b(\d+(?:\.\d+)?)\s*([mM])\b(?!\s*(?:bed|bedroom|bath))', 
         lambda m: float(m.group(1)) * 1000000, 'exact'),
    ]
    
    for pattern, converter, price_type in price_patterns:
        match = re.search(pattern, query_lower)
        if match:
            try:
                if price_type == 'max':
                    max_price = converter(match)
                    entities['max_price'] = max_price
                    entities['price_range'] = f"under ₱{max_price/1000000:.1f}M"
                    logger.info(f"💰 Parsed max price: ₱{max_price:,.0f}")
                elif price_type == 'min':
                    min_price = converter(match)
                    entities['min_price'] = min_price
                    logger.info(f"💰 Parsed min price: ₱{min_price:,.0f}")
                elif price_type == 'range':
                    min_val, max_val = converter(match)
                    entities['min_price'] = min_val
                    entities['max_price'] = max_val
                    entities['price_range'] = f"₱{min_val/1000000:.1f}M to ₱{max_val/1000000:.1f}M"
                    logger.info(f"💰 Parsed price range: ₱{min_val:,.0f} - ₱{max_val:,.0f}")
                elif price_type == 'exact':
                    exact_price = converter(match)
                    entities['price_range'] = f"around ₱{exact_price/1000000:.1f}M"
                    logger.info(f"💰 Parsed approximate price: ₱{exact_price:,.0f}")
                break
            except Exception as e:
                logger.warning(f"⚠️ Could not parse price pattern '{pattern}': {e}")
                continue
    
    # ========== NEW: Parse bedroom criteria for filtering ==========
    bedrooms = None
    exact_bedrooms = None
    
    # Patterns for bedroom extraction
    bedroom_patterns = [
        # "with 3 bedrooms" or "with 3 bedroom"
        (r'with\s+(\d+)\s+bedroom(?:s)?\b', lambda m: int(m.group(1))),
        # "3 bedrooms" or "3 bedroom"
        (r'\b(\d+)\s+bedroom(?:s)?\b(?!\s*(?:bath|bathroom))', lambda m: int(m.group(1))),
        # "3-bedroom" or "3br"
        (r'(\d+)(?:-|\s*)bedroom|(\d+)br\b', lambda m: int(m.group(1)) if m.group(1) else int(m.group(2))),
        # "3 bed"
        (r'(\d+)\s+bed\b', lambda m: int(m.group(1))),
        # "studio" (0 bedrooms)
        (r'\bstudio\b', lambda m: 0),
        # "1 bedroom apartment" pattern
        (r'(\d+)\s+bedroom\s+(?:apartment|condo|house|unit)', lambda m: int(m.group(1))),
    ]
    
    for pattern, converter in bedroom_patterns:
        match = re.search(pattern, query_lower)
        if match:
            try:
                bedrooms = converter(match)
                entities['exact_bedrooms'] = bedrooms
                entities['bedrooms'] = bedrooms
                logger.info(f"🛏️ Parsed bedroom count: {bedrooms}")
                break
            except Exception as e:
                logger.warning(f"⚠️ Could not parse bedroom pattern '{pattern}': {e}")
                continue
    
    # Detect if this is a general search (no location specified)
    has_location_terms = any(term in query_lower for term in ['in ', 'at ', 'within ', 'inside '])
    has_specific_location = False
    
    # ========== SALE TYPE DETECTION (CHANGED from financing_type) ==========
    # Check for your saleType values: outright, installment, bank_financing
    sale_type_keywords = {
        'bank financing': 'bank_financing',
        'bank loan': 'bank_financing',
        'bank mortgage': 'bank_financing',
        'outright': 'outright',
        'cash': 'outright',
        'installment': 'installment',
        'installment plan': 'installment',
        'in-house financing': 'installment',
        'developer financing': 'installment'
    }
    
    for keyword, sale_type in sale_type_keywords.items():
        if keyword in query_lower:
            entities['sale_type'] = sale_type
            break
    
    # Flag for financing information queries (documents, requirements)
    if 'pag-ibig' in query_lower or 'housing loan' in query_lower or 'pagibig' in query_lower:
        entities['has_financing_info_query'] = True  # Flag for info queries only
    
    # Detect listing type
    if 'for rent' in query_lower or 'rental' in query_lower:
        entities['listing_type'] = 'rent'
    elif 'for sale' in query_lower or 'buy' in query_lower:
        entities['listing_type'] = 'sale'
    elif 'for lease' in query_lower:
        entities['listing_type'] = 'lease'
    
    # Property type detection - UPDATED FOR CASE INSENSITIVITY
    property_type_map = {
        'apartment': 'apartment',
        'apartments': 'apartment',  # Add plural
        'condo': 'condo', 'condominium': 'condo', 'condos': 'condo',
        'house': 'house', 'houses': 'house', 'villa': 'house', 'bungalow': 'house',
        'townhouse': 'townhouse', 'townhouses': 'townhouse',
        'commercial': 'commercial_building',
        'office': 'office_unit',
        'retail': 'retail_space',
        'warehouse': 'warehouse',
        'land': 'residential_lot', 'lot': 'residential_lot',
        'beachfront': 'beachfront',
        'resort': 'resort_property'
    }
    
    for key, value in property_type_map.items():
        if key in query_lower:
            entities['property_type'] = value
            break
    
    # Location detection - Batangas locations (from your database)
    batangas_locations = {
        # Major cities
        'batangas city': 'Batangas City',
        'lipa': 'Lipa City', 'lipa city': 'Lipa City',
        'nasugbu': 'Nasugbu',
        'tanauan': 'Tanauan City', 'tanauan city': 'Tanauan City',
        'taal': 'Taal',
        'calatagan': 'Calatagan',
        'mabini': 'Mabini',
        'malvar': 'Malvar',
        'bauan': 'Bauan',
        'balayan': 'Balayan',
        'san juan': 'San Juan',
        'sto tomas': 'Sto. Tomas City', 'santo tomas': 'Sto. Tomas City',
        'sto. tomas': 'Sto. Tomas City',
        
        # Additional locations from training data
        'tuy': 'Tuy', 'tuy batangas': 'Tuy',
        'lian': 'Lian', 'lian batangas': 'Lian',
        'taysan': 'Taysan', 'taysan batangas': 'Taysan',
        'rosario': 'Rosario', 'rosario batangas': 'Rosario',
        'laurel': 'Laurel',
        'agoncillo': 'Agoncillo',
        'san pascual': 'San Pascual',
        'cuenca': 'Cuenca',
        'alitagtag': 'Alitagtag',
        'san luis': 'San Luis',
        'padre garcia': 'Padre Garcia',
        'san nicolas': 'San Nicolas',
        'mataas na kahoy': 'Mataas Na Kahoy', 'mataasnakahoy': 'Mataas Na Kahoy',
        'talisay': 'Talisay',
        'la paz': 'La Paz',
        'lemery': 'Lemery',
        'ibaan': 'Ibaan',
        'lobo': 'Lobo',
        'tingloy': 'Tingloy'
    }
    
    for location_key, location_value in batangas_locations.items():
        # Check for exact match first
        if location_key in query_lower:
            entities['location'] = location_value
            has_specific_location = True
            break
        # Also check if location is a standalone word (with word boundaries)
        elif re.search(r'\b' + re.escape(location_key) + r'\b', query_lower):
            entities['location'] = location_value
            has_specific_location = True
            break
    
    # Feature detection
    if 'with swimming pool' in query_lower or 'with pool' in query_lower:
        entities['feature'] = 'swimming pool'
    elif 'with garden' in query_lower:
        entities['feature'] = 'garden'
    elif 'with parking' in query_lower:
        entities['feature'] = 'parking'
    elif 'furnished' in query_lower:
        entities['feature'] = 'furnished'
    
    # Landmark detection
    if 'near' in query_lower or 'close to' in query_lower or 'around' in query_lower or 'beside' in query_lower:
        # Extract word after landmark terms
        match = re.search(r'(?:near|close to|around|beside|next to)\s+(\w+\s*\w*)', query_lower)
        if match:
            entities['landmark'] = match.group(1).strip()
    
    # Bathroom detection
    bath_match = re.search(r'(\d+)\s+bathroom', query_lower)
    if bath_match:
        entities['bathrooms'] = int(bath_match.group(1))
    
    # NEW: Determine if this is a general search (property type but no location)
    if entities.get('property_type') and not has_specific_location:
        entities['has_general_search'] = True
        logger.info(f"🔍 Detected general search for {entities['property_type']} (no location specified)")
    
    return entities

# Add numeric price value to property data
def add_price_numeric_value(property_data: Dict) -> Dict:
    """Add numeric price value to property data for easier filtering"""
    property_data = property_data.copy()
    
    listing_type = property_data.get('type', property_data.get('listingType', 'unknown'))
    
    if listing_type == 'rent' and 'monthlyRent' in property_data:
        property_data['price_numeric'] = property_data['monthlyRent']
    elif listing_type == 'sale' and 'salePrice' in property_data:
        property_data['price_numeric'] = property_data['salePrice']
    elif listing_type == 'lease' and 'annualRent' in property_data:
        property_data['price_numeric'] = property_data['annualRent']
    else:
        # Try to extract from price string
        price_str = str(property_data.get('price', '0'))
        try:
            # Extract numeric value from string like "₱10.0M" or "₱25,000"
            match = re.search(r'[\d\.\,]+', price_str)
            if match:
                numeric_str = match.group().replace(',', '')
                if 'M' in price_str or 'm' in price_str:
                    property_data['price_numeric'] = float(numeric_str) * 1000000
                elif 'K' in price_str or 'k' in price_str:
                    property_data['price_numeric'] = float(numeric_str) * 1000
                else:
                    property_data['price_numeric'] = float(numeric_str)
            else:
                property_data['price_numeric'] = 0
        except:
            property_data['price_numeric'] = 0
    
    return property_data

# Standardize property data from Firestore
def standardize_property_data(property_data: Dict) -> Dict:
    """Standardize property data from Firestore to chatbot format"""
    # Extract basic info
    title = property_data.get('title', 'Untitled Property')
    property_type = property_data.get('propertyType', property_data.get('type', 'unknown'))
    city = property_data.get('city', 'Unknown')
    province = property_data.get('province', 'Batangas')
    
    # Format price based on listing type
    listing_type = property_data.get('type', property_data.get('listingType', 'unknown'))
    price_str = "Price not available"
    
    if listing_type == 'rent' and 'monthlyRent' in property_data:
        price = property_data['monthlyRent']
        price_str = f"₱{price:,.0f}/month"
    elif listing_type == 'sale' and 'salePrice' in property_data:
        price = property_data['salePrice']
        if price >= 1000000:
            price_str = f"₱{price/1000000:.1f}M"
        else:
            price_str = f"₱{price:,.0f}"
    elif listing_type == 'lease' and 'annualRent' in property_data:
        price = property_data['annualRent']
        price_str = f"₱{price:,.0f}/year"
    
    # Extract features
    features = []
    if property_data.get('furnishing'):
        features.append(property_data['furnishing'])
    if property_data.get('amenities'):
        features.extend(property_data['amenities'][:3])  # First 3 amenities
    if property_data.get('bedrooms'):
        features.append(f"{property_data['bedrooms']} bedroom{'s' if property_data['bedrooms'] != '1' else ''}")
    if property_data.get('bathrooms'):
        features.append(f"{property_data['bathrooms']} bathroom{'s' if property_data['bathrooms'] != '1' else ''}")
    
    # Get description or create one
    description = property_data.get('description', '')
    if not description:
        description = f"A {property_type.replace('_', ' ')} located in {city}, {province}."
    
    standardized = {
        'id': property_data.get('id', ''),
        'title': title,
        'type': property_type,
        'location': f"{city}, {province}",
        'city': city,
        'province': province,
        'price': price_str,
        'bedrooms': property_data.get('bedrooms', 'Not specified'),
        'bathrooms': property_data.get('bathrooms', 'Not specified'),
        'features': features,
        'description': description,
        'listing_type': listing_type,
        'status': property_data.get('status', 'unknown'),
        'address': property_data.get('address', ''),
        'imageUrls': property_data.get('imageUrls', []) or property_data.get('photos', []),
        'videoUrls': property_data.get('videoUrls', []),
        'hasVideos': property_data.get('hasVideos', False),
        'floorArea': property_data.get('floorArea', None),
        'lotArea': property_data.get('lotArea', None),
        'sale_type': property_data.get('saleType', ''),  # ADDED: Include sale_type
        'price_numeric': property_data.get('price_numeric', 0)  # Add numeric price
    }
    
    return standardized

# Get mock properties when Firebase is not connected
def get_mock_properties(entities: Dict[str, Any]) -> List[Dict[str, Any]]:
    """Generate mock properties for testing when Firebase is not connected"""
    mock_properties = []
    
    # Base mock data matching your Firestore structure
    base_properties = [
        {
            'id': 'mock_1',
            'title': 'Modern House in Nasugbu',
            'propertyType': 'house',
            'type': 'rent',
            'city': 'Nasugbu',
            'province': 'Batangas',
            'address': '123 Beach Road, Nasugbu',
            'monthlyRent': 25000,
            'bedrooms': '3',
            'bathrooms': '2',
            'floorArea': 120,
            'description': 'Beautiful modern house near the beach',
            'imageUrls': [],
            'status': 'available',
            'amenities': ['Swimming Pool', 'Garden', 'Parking']
        },
        {
            'id': 'mock_2',
            'title': 'Beachfront Condo Unit',
            'propertyType': 'condo',
            'type': 'sale',
            'city': 'Nasugbu',
            'province': 'Batangas',
            'address': '456 Coastal Avenue, Nasugbu',
            'salePrice': 3500000,
            'bedrooms': '2',
            'bathrooms': '2',
            'floorArea': 80,
            'description': 'Luxury beachfront condo with ocean view',
            'imageUrls': [],
            'status': 'available',
            'saleType': 'bank_financing'  # ADDED: Mock sale type
        },
        {
            'id': 'mock_3',
            'title': 'Commercial Space in Lipa',
            'propertyType': 'commercial_building',
            'type': 'lease',
            'city': 'Lipa City',
            'province': 'Batangas',
            'address': '789 Business District, Lipa',
            'annualRent': 1200000,
            'description': 'Prime commercial space for business',
            'imageUrls': [],
            'status': 'available'
        },
        {
            'id': 'mock_4',
            'title': 'Apartment in Batangas City',
            'propertyType': 'apartment',
            'type': 'rent',
            'city': 'Batangas City',
            'province': 'Batangas',
            'address': '101 Main Street, Batangas City',
            'monthlyRent': 12000,
            'bedrooms': '2',
            'bathrooms': '1',
            'floorArea': 50,
            'description': 'Clean and affordable apartment',
            'imageUrls': [],
            'status': 'available'
        },
        {
            'id': 'mock_5',
            'title': 'Townhouse in Sto. Tomas',
            'propertyType': 'townhouse',
            'type': 'sale',
            'city': 'Sto. Tomas City',
            'province': 'Batangas',
            'address': '202 Subdivision, Sto. Tomas',
            'salePrice': 2800000,
            'bedrooms': '3',
            'bathrooms': '2',
            'floorArea': 90,
            'description': 'Modern townhouse with garage',
            'imageUrls': [],
            'status': 'available',
            'saleType': 'outright'  # ADDED: Mock sale type
        }
    ]
    
    # Filter mock properties based on entities
    for prop in base_properties:
        matches = True
        
        # Filter by location (only if specified)
        if entities.get('location'):
            location = entities['location'].lower()
            prop_city = prop.get('city', '').lower()
            if 'nasugbu' in location and 'nasugbu' not in prop_city:
                matches = False
            elif 'lipa' in location and 'lipa' not in prop_city:
                matches = False
            elif 'batangas city' in location and 'batangas city' not in prop_city:
                matches = False
            elif 'sto tomas' in location and 'sto. tomas city' not in prop_city:
                matches = False
        
        # Filter by property type
        if entities.get('property_type') and matches:
            requested_type = entities['property_type'].lower()
            prop_type = prop.get('propertyType', '').lower()
            
            type_mapping = {
                'house': ['house', 'bungalow', 'duplex'],
                'condo': ['condo', 'condominium', 'penthouse', 'studio'],
                'apartment': ['apartment', 'room', 'boarding_house'],
                'commercial': ['commercial', 'office', 'retail', 'warehouse'],
                'townhouse': ['townhouse']
            }
            
            if requested_type in type_mapping:
                if prop_type not in type_mapping[requested_type]:
                    matches = False
        
        # Filter by sale type
        if entities.get('sale_type') and matches:
            requested_sale_type = entities['sale_type']
            prop_sale_type = prop.get('saleType', '')
            
            # Only apply to sale properties
            if prop.get('type') == 'sale':
                if prop_sale_type != requested_sale_type:
                    matches = False
            else:
                # Not a sale property, doesn't match sale type query
                matches = False
        
        # Filter by price if specified
        if entities.get('max_price') and matches:
            price_numeric = 0
            if prop.get('type') == 'rent' and 'monthlyRent' in prop:
                price_numeric = prop['monthlyRent']
            elif prop.get('type') == 'sale' and 'salePrice' in prop:
                price_numeric = prop['salePrice']
            
            if price_numeric > entities['max_price']:
                matches = False
        
        # Filter by bedrooms if specified
        if entities.get('exact_bedrooms') is not None and matches:
            prop_bedrooms = prop.get('bedrooms', '0')
            try:
                if isinstance(prop_bedrooms, str):
                    bed_match = re.search(r'(\d+)', prop_bedrooms)
                    if bed_match:
                        prop_bed_num = int(bed_match.group(1))
                    else:
                        prop_bed_num = 0
                else:
                    prop_bed_num = int(prop_bedrooms)
                
                if prop_bed_num != entities['exact_bedrooms']:
                    matches = False
            except:
                pass
        
        if matches:
            # Add numeric price value
            prop_with_price = add_price_numeric_value(prop)
            mock_properties.append(standardize_property_data(prop_with_price))
    
    # ========== NEW: Return empty if no mock properties match ==========
    if not mock_properties and any([
        entities.get('property_type'),
        entities.get('location'),
        entities.get('max_price'),
        entities.get('exact_bedrooms'),
        entities.get('sale_type')
    ]):
        logger.info("❌ No mock properties match the specified criteria")
        return []
    
    return mock_properties

# Debug function for property matching
def debug_property_matching(properties, entities):
    """Debug why properties are/aren't being matched"""
    logger.info(f"🔍 DEBUG PROPERTY MATCHING:")
    logger.info(f"   Query entities: {entities}")
    
    for i, prop in enumerate(properties):
        logger.info(f"\n   Property {i+1}:")
        logger.info(f"     ID: {prop.get('id')}")
        logger.info(f"     Title: {prop.get('title')}")
        logger.info(f"     Property Type: {prop.get('propertyType', prop.get('type'))}")
        logger.info(f"     City: {prop.get('city')}")
        logger.info(f"     Status: {prop.get('status')}")
        logger.info(f"     Sale Type: {prop.get('saleType', 'N/A')}")
        logger.info(f"     Type (listing): {prop.get('type')}")
        
        # Check if it matches location
        if entities.get('location'):
            prop_city = prop.get('city', '').lower()
            query_city = entities.get('location', '').lower()
            matches_location = query_city in prop_city or prop_city in query_city
            logger.info(f"     Matches location '{query_city}': {matches_location}")
        
        # Check if it matches property type
        if entities.get('property_type'):
            prop_type = prop.get('propertyType', prop.get('type', '')).lower()
            query_type = entities.get('property_type', '').lower()
            matches_type = query_type in prop_type or prop_type in query_type
            logger.info(f"     Matches type '{query_type}': {matches_type}")
        
        # Check if it matches sale type
        if entities.get('sale_type'):
            prop_sale_type = prop.get('saleType', '').lower()
            query_sale_type = entities.get('sale_type', '').lower()
            matches_sale_type = query_sale_type in prop_sale_type or prop_sale_type in query_sale_type
            logger.info(f"     Matches sale type '{query_sale_type}': {matches_sale_type}")

# Firestore queries - UPDATED TO USE saleType INSTEAD OF financingOptions
def search_firestore_properties(entities: Dict[str, Any]) -> List[Dict[str, Any]]:
    """Search properties in Firestore based on entities"""
    properties = []
    
    if not db:
        logger.warning("⚠️ Firebase not connected, returning mock data")
        return get_mock_properties(entities)
    
    try:
        from google.cloud.firestore_v1 import FieldFilter
        
        properties_ref = db.collection('properties')
        
        # Build query based on available entities
        query = properties_ref
        
        # Firestore doesn't support 'in' operator with FieldFilter for status
        logger.info("🔍 Status filtering will be done client-side (Firestore doesn't support 'in' operator)")
        
        # NEW: Handle general searches (no location specified)
        is_general_search = not entities.get('location') and entities.get('has_general_search')
        
        # ========== FIXED: SALE TYPE FILTERING (replaces financing filter) ==========
        has_sale_type_query = entities.get('sale_type') is not None
        
        if has_sale_type_query:
            sale_type = entities['sale_type']
            logger.info(f"💰 SALE TYPE QUERY DETECTED: {sale_type}")
            
            # IMPORTANT: For sale type queries, ONLY show sale properties
            query = query.where(filter=FieldFilter('type', '==', 'sale'))
            logger.info("🔍 Filtering: Sale properties only (sale_type applies only to sale)")
            
            # Try to filter by saleType field
            try:
                query = query.where(filter=FieldFilter('saleType', '==', sale_type))
                logger.info(f"🔍 Filtering by saleType: {sale_type}")
            except Exception as e:
                logger.warning(f"⚠️ Could not filter by saleType: {e}")
                # Will filter client-side if Firestore query fails
        
        # Filter by location if specified
        if entities.get('location'):
            location = entities['location']
            
            # Enhanced location mapping with more flexibility
            location_map = {
                'Batangas City': 'Batangas City',
                'Lipa City': 'Lipa City',
                'Tanauan City': 'Tanauan City',
                'Tanauan': 'Tanauan City',
                'Nasugbu': 'Nasugbu',
                'Malvar': 'Malvar',
                'Mataas Na Kahoy': 'Mataas Na Kahoy',
                'Mataasnakahoy': 'Mataas Na Kahoy',
                'Taal': 'Taal',
                'Calatagan': 'Calatagan',
                'Mabini': 'Mabini',
                'Bauan': 'Bauan',
                'Balayan': 'Balayan',
                'San Juan': 'San Juan',
                'Sto. Tomas City': 'Sto. Tomas City',
                'Sto Tomas': 'Sto. Tomas City',
                'Santo Tomas': 'Sto. Tomas City',
                'Lobo': 'Lobo',
                # Add more from your database
                'Malvar': 'Malvar',
                'Mataas Na Kahoy': 'Mataas Na Kahoy',
            }
            
            if location in location_map:
                query = query.where(filter=FieldFilter('city', '==', location_map[location]))
                logger.info(f"🔍 Filtering by city: {location_map[location]}")
            else:
                # Try case-insensitive match
                location_lower = location.lower()
                found_match = False
                for map_key, map_value in location_map.items():
                    if map_key.lower() == location_lower:
                        query = query.where(filter=FieldFilter('city', '==', map_value))
                        logger.info(f"🔍 Filtering by city (case-insensitive): {map_value}")
                        found_match = True
                        break
                
                if not found_match:
                    # Try partial match
                    for map_key, map_value in location_map.items():
                        if location_lower in map_key.lower() or map_key.lower() in location_lower:
                            query = query.where(filter=FieldFilter('city', '==', map_value))
                            logger.info(f"🔍 Filtering by city (partial match): {map_value}")
                            break
        else:
            if is_general_search:
                logger.info(f"🔍 General search for {entities.get('property_type', 'properties')} (no location filter)")
            else:
                logger.info("🔍 No location specified - showing properties from all locations")
        
        # Filter by property type if specified - ENHANCED CONDO MATCHING
        if entities.get('property_type'):
            property_type = entities['property_type'].lower()
            
            # ENHANCED property type mapping with better condo support
            type_map = {
                # For apartments category
                'apartment': ['apartment', 'Apartment'],
                'apartments': ['apartment', 'Apartment'],
                
                # For condos category - PRIORITIZE 'condo_unit' AS IN YOUR DATABASE
                'condo': ['condo_unit', 'condominium', 'Condo', 'condo'],
                'condos': ['condo_unit', 'condominium', 'Condo', 'condo'],
                'condominium': ['condo_unit', 'condominium', 'Condo', 'condo'],
                'condominiums': ['condo_unit', 'condominium', 'Condo', 'condo'],
                
                # For houses category
                'house': ['house', 'House'],
                'houses': ['house', 'House'],
                
                # For townhouses category
                'townhouse': ['townhouse', 'Townhouse'],
                'townhouses': ['townhouse', 'Townhouse'],
                
                # For commercial category
                'commercial': ['commercial_unit', 'commercial_building'],
                'commercial_unit': ['commercial_unit'],
                'commercial_space': ['commercial_unit', 'commercial_building'],
                'commercial_building': ['commercial_building'],
                
                # For warehouses category
                'warehouse': ['warehouse'],
                'industrial': ['warehouse'],
                
                # For land category
                'land': ['residential_lot', 'commercial_lot', 'agricultural_land'],
                'lot': ['residential_lot', 'commercial_lot', 'agricultural_land'],
                'residential_lot': ['residential_lot'],
                'commercial_lot': ['commercial_lot'],
                'agricultural': ['agricultural_land'],
                'agricultural_land': ['agricultural_land'],
                
                # Special categories
                'beachfront': ['beachfront'],
                'resort': ['resort_property'],
                'resort_property': ['resort_property'],
                
                # Direct mappings (from your database samples)
                'condo_unit': 'condo_unit',
                'commercial_unit': 'commercial_unit',
            }
            
            # Get possible property types for this category
            possible_types = type_map.get(property_type)
            
            if possible_types:
                if isinstance(possible_types, list):
                    # For multiple possible types, try each one in order
                    logger.info(f"🔍 Will filter client-side for property types: {possible_types}")
                    
                    # Try each possible type in sequence until one works
                    filter_applied = False
                    for i, type_option in enumerate(possible_types):
                        try:
                            temp_query = query.where(filter=FieldFilter('propertyType', '==', type_option))
                            # Test with a small limit to see if query works
                            test_docs = list(temp_query.limit(1).get())
                            if test_docs or i == 0:  # Use first type even if no results yet
                                query = temp_query
                                logger.info(f"🔍 Filtering by property type: {type_option}")
                                filter_applied = True
                                break
                        except Exception as e:
                            logger.debug(f"⚠️ Could not filter by {type_option}: {e}")
                            continue
                    
                    if not filter_applied:
                        logger.info("💡 Will apply property type filtering client-side")
                else:
                    # Single type mapping
                    try:
                        query = query.where(filter=FieldFilter('propertyType', '==', possible_types))
                        logger.info(f"🔍 Filtering by property type: {possible_types}")
                    except Exception as e:
                        logger.warning(f"⚠️ Could not filter by property type {possible_types}: {e}")
            else:
                # Try direct match if not found in map
                try:
                    query = query.where(filter=FieldFilter('propertyType', '==', property_type))
                    logger.info(f"🔍 Direct filtering by property type: {property_type}")
                except Exception as e:
                    logger.warning(f"⚠️ Could not filter by property type {property_type}: {e}")
        
        # ========== APPLY PRICE FILTERS IF SPECIFIED ==========
        if entities.get('max_price'):
            max_price = entities['max_price']
            logger.info(f"💰 Applying max price filter: ₱{max_price:,.0f}")
            
            # Try all possible price fields
            price_fields = ['monthlyRent', 'salePrice', 'annualRent', 'price']
            price_filter_applied = False
            
            for field in price_fields:
                try:
                    query = query.where(filter=FieldFilter(field, '<=', max_price))
                    logger.info(f"🔍 Filtering by max {field}: ₱{max_price:,.0f}")
                    price_filter_applied = True
                    break
                except Exception as price_error:
                    logger.debug(f"⚠️ Could not filter by {field}: {price_error}")
                    continue
            
            if not price_filter_applied:
                logger.info("💡 Will apply price filtering client-side")
        
        # ========== APPLY BEDROOM FILTER IF SPECIFIED ==========
        if entities.get('exact_bedrooms') is not None:
            bedrooms = entities['exact_bedrooms']
            bed_str = str(bedrooms) if bedrooms <= 5 else '5+'
            
            try:
                query = query.where(filter=FieldFilter('bedrooms', '==', bed_str))
                logger.info(f"🛏️ Filtering by exact bedroom count: {bed_str}")
            except Exception as bed_error:
                logger.warning(f"⚠️ Could not filter by bedrooms: {bed_error}")
                # Will apply client-side filtering
        
        # Execute query with appropriate limit
        limit_count = 20 if is_general_search else 15
        logger.info(f"🔍 Executing Firestore query (limit: {limit_count})...")
        docs = query.limit(limit_count).get()
        
        found_count = 0
        property_data_list = []
        status_counts = {}
        
        for doc in docs:
            property_data = doc.to_dict()
            property_data['id'] = doc.id
            property_data_list.append(property_data)
            found_count += 1
            
            # Track status for debugging
            status = property_data.get('status', 'NO STATUS')
            status_counts[status] = status_counts.get(status, 0) + 1
        
        logger.info(f"🔍 Found {found_count} properties from Firestore")
        logger.info(f"🔍 Status breakdown: {status_counts}")
        
        # DEBUG: Show raw properties
        logger.info(f"🔍 DEBUG: Raw properties from Firestore (before filtering):")
        for doc in docs:
            data = doc.to_dict()
            doc_id = doc.id
            prop_type = data.get('propertyType', data.get('type', 'NO TYPE'))
            city = data.get('city', 'NO CITY')
            status = data.get('status', 'NO STATUS')
            listing_type = data.get('type', 'NO TYPE')
            sale_type = data.get('saleType', 'NO saleType')
            logger.info(f"   • ID: {doc_id[:10]}..., Type: {prop_type}, City: {city}, Status: {status}, Listing: {listing_type}, SaleType: {sale_type}")
        
        # ========== COMPREHENSIVE CLIENT-SIDE FILTERING ==========
        filtered_properties = []
        
        for property_data in property_data_list:
            matches = True
            
            # ========== CLIENT-SIDE STATUS FILTERING ==========
            status = str(property_data.get('status', '')).lower()
            valid_statuses = ['available', 'active', 'for sale']
            
            # For sale type queries, only show 'available' or 'active' sale properties
            if has_sale_type_query:
                if status not in ['available', 'active']:
                    logger.debug(f"❌ Property {property_data.get('id', 'unknown')} excluded - wrong status for sale type query: {status}")
                    matches = False
                    continue
            else:
                # For non-sale type queries, allow broader statuses
                extended_valid_statuses = valid_statuses + ['for rent', 'for lease', 'listed']
                if status not in extended_valid_statuses:
                    logger.debug(f"❌ Property {property_data.get('id', 'unknown')} excluded - status: {status}")
                    matches = False
                    continue
            
            # ========== CRITICAL: SALE TYPE FILTERING ==========
            if has_sale_type_query:
                sale_type = entities['sale_type']
                
                # Check 1: Must be a sale property
                if property_data.get('type') != 'sale':
                    logger.debug(f"❌ Property {property_data.get('id', 'unknown')} excluded - not a sale property (type: {property_data.get('type')})")
                    matches = False
                    continue
                
                # Check 2: Must have saleType field
                prop_sale_type = property_data.get('saleType')
                if not prop_sale_type:
                    logger.debug(f"❌ Property {property_data.get('id', 'unknown')} excluded - no saleType field")
                    matches = False
                    continue
                
                # Check 3: Must match the requested sale_type
                if prop_sale_type != sale_type:
                    logger.debug(f"❌ Property {property_data.get('id', 'unknown')} excluded - saleType {prop_sale_type} != {sale_type}")
                    matches = False
                    continue
                
                logger.debug(f"✅ Property {property_data.get('id', 'unknown')} matches sale type: {sale_type}")
            
            # Apply property type filtering (for categories with multiple types)
            if entities.get('property_type') and property_type in type_map:
                prop_type = property_data.get('propertyType', '').lower()
                possible_types = type_map[property_type]
                
                if isinstance(possible_types, list):
                    possible_types_lower = [pt.lower() for pt in possible_types]
                    if prop_type not in possible_types_lower:
                        # Special handling for condo matching
                        if property_type in ['condo', 'condos', 'condominium', 'condominiums']:
                            # Check if it's a condo-like property
                            is_condo_like = any(condo_term in prop_type for condo_term in ['condo', 'condominium', 'unit'])
                            if not is_condo_like:
                                matches = False
                                logger.debug(f"❌ Property {property_data.get('id', 'unknown')} type '{prop_type}' not in {possible_types_lower}")
                                continue
                        else:
                            matches = False
                            logger.debug(f"❌ Property {property_data.get('id', 'unknown')} type '{prop_type}' not in {possible_types_lower}")
                            continue
            
            # Add numeric price value before further filtering
            property_data_with_price = add_price_numeric_value(property_data)
            
            # Apply max price filter client-side
            if entities.get('max_price') and matches:
                price_numeric = property_data_with_price.get('price_numeric', 0)
                if price_numeric > entities['max_price']:
                    matches = False
                    logger.debug(f"❌ Property {property_data.get('id', 'unknown')} price {price_numeric} > {entities['max_price']}")
            
            # Apply min price filter client-side
            if entities.get('min_price') and matches:
                price_numeric = property_data_with_price.get('price_numeric', 0)
                if price_numeric < entities['min_price']:
                    matches = False
                    logger.debug(f"❌ Property {property_data.get('id', 'unknown')} price {price_numeric} < {entities['min_price']}")
            
            # Apply exact bedroom filter client-side
            if entities.get('exact_bedrooms') is not None and matches:
                prop_bedrooms = property_data.get('bedrooms', 'Not specified')
                try:
                    if isinstance(prop_bedrooms, str):
                        # Handle 'studio', '1', '2', '3', '4', '5+'
                        if prop_bedrooms.lower() == 'studio':
                            prop_bed_num = 0
                        elif prop_bedrooms.lower() == '5+':
                            prop_bed_num = 5
                        else:
                            bed_match = re.search(r'(\d+)', prop_bedrooms)
                            if bed_match:
                                prop_bed_num = int(bed_match.group(1))
                            else:
                                prop_bed_num = 0
                    else:
                        prop_bed_num = int(prop_bedrooms)
                    
                    if prop_bed_num != entities['exact_bedrooms']:
                        matches = False
                        logger.debug(f"❌ Property {property_data.get('id', 'unknown')} bedrooms {prop_bed_num} != {entities['exact_bedrooms']}")
                except Exception as e:
                    logger.debug(f"⚠️ Could not parse bedrooms for filtering: {e}")
                    # Skip bedroom filtering if we can't parse
                    pass
            
            # Apply bathroom filter client-side
            if entities.get('bathrooms') and matches:
                prop_bathrooms = property_data.get('bathrooms', 'Not specified')
                try:
                    if isinstance(prop_bathrooms, str):
                        bath_match = re.search(r'(\d+)', prop_bathrooms)
                        if bath_match:
                            prop_bath_num = int(bath_match.group(1))
                        else:
                            prop_bath_num = 0
                    else:
                        prop_bath_num = int(prop_bathrooms)
                    
                    if prop_bath_num != entities['bathrooms']:
                        matches = False
                except:
                    # Skip bathroom filtering if we can't parse
                    pass
            
            if matches:
                # Standardize property data for chatbot response
                standardized_property = standardize_property_data(property_data_with_price)
                filtered_properties.append(standardized_property)
        
        # Update properties with client-side filtered results
        properties = filtered_properties
        logger.info(f"🔍 After client-side filtering: {len(properties)} properties")
        
        # Debug property matching
        debug_property_matching(property_data_list, entities)
        
        # ========== NO FALLBACK FOR SALE TYPE QUERIES ==========
        if len(properties) == 0 and has_sale_type_query:
            logger.info(f"❌ No properties found with sale type: {entities['sale_type']}")
            return []
        
        # ========== DEDUPLICATION ==========
        # Remove duplicates by property ID
        unique_properties = []
        seen_ids = set()
        
        for prop in properties:
            prop_id = prop.get('id')
            if prop_id and prop_id not in seen_ids:
                seen_ids.add(prop_id)
                unique_properties.append(prop)
        
        properties = unique_properties
        logger.info(f"🔍 After deduplication: {len(properties)} unique properties")
        
    except Exception as e:
        logger.error(f"❌ Error searching Firestore: {e}")
        import traceback
        logger.error(f"Traceback: {traceback.format_exc()}")
        
        # Fall back to mock data on error
        properties = get_mock_properties(entities)
    
    return properties

# Generate criteria search response
def generate_criteria_search_response(entities: Dict[str, Any], properties: List[Dict[str, Any]]) -> str:
    """Generate response for property searches with specific criteria"""
    
    # Filter properties client-side as a fallback
    filtered_properties = []
    for prop in properties:
        matches = True
        
        # Apply price filter
        if entities.get('max_price'):
            price_numeric = prop.get('price_numeric', 0)
            if price_numeric > entities['max_price']:
                matches = False
        
        # Apply bedroom filter
        if entities.get('exact_bedrooms') is not None:
            prop_bedrooms = prop.get('bedrooms', 'Not specified')
            # Try to extract numeric bedrooms
            try:
                if isinstance(prop_bedrooms, str):
                    bed_match = re.search(r'(\d+)', str(prop_bedrooms))
                    if bed_match:
                        prop_bed_num = int(bed_match.group(1))
                    else:
                        prop_bed_num = 0
                else:
                    prop_bed_num = int(prop_bedrooms)
                
                if prop_bed_num != entities['exact_bedrooms']:
                    matches = False
            except:
                # If can't parse bedrooms, don't filter
                pass
        
        if matches:
            filtered_properties.append(prop)
    
    # Use filtered properties
    properties = filtered_properties
    
    # Build criteria description
    criteria_parts = []
    
    if entities.get('property_type'):
        prop_type = entities['property_type'].replace('_', ' ').title()
        criteria_parts.append(f"{prop_type}")
    else:
        criteria_parts.append("properties")
    
    if entities.get('max_price'):
        max_price = entities['max_price']
        if max_price >= 1000000:
            criteria_parts.append(f"under ₱{max_price/1000000:.1f}M")
        else:
            criteria_parts.append(f"under ₱{max_price:,.0f}")
    
    if entities.get('exact_bedrooms') is not None:
        bedrooms = entities['exact_bedrooms']
        criteria_parts.append(f"with {bedrooms} bedroom{'s' if bedrooms != 1 else ''}")
    
    if entities.get('location'):
        criteria_parts.append(f"in {entities['location']}")
    
    criteria_desc = " ".join(criteria_parts)
    
    # Generate response
    if properties:
        # Group by location
        properties_by_location = {}
        for prop in properties:
            location = prop.get('city', 'Unknown')
            if location not in properties_by_location:
                properties_by_location[location] = []
            properties_by_location[location].append(prop)
        
        response = f"🔍 **Found {len(properties)} {criteria_desc}**\n\n"
        
        for location, loc_props in properties_by_location.items():
            response += f"📍 **{location}** ({len(loc_props)} available)\n"
            
            for prop in loc_props[:3]:  # Show max 3 per location
                title = prop.get('title', 'Property')
                price = prop.get('price', 'Price not available')
                prop_type = prop.get('type', '').replace('_', ' ')
                
                # Extract bedrooms for display
                prop_bedrooms = prop.get('bedrooms', '')
                if prop_bedrooms:
                    bed_display = f" | 🛏️ {prop_bedrooms}"
                else:
                    bed_display = ""
                
                response += f"   • **{title}** ({prop_type}) - {price}{bed_display}\n"
            
            response += "\n"
        
        # Add summary
        if len(properties) > 10:
            response += f"*Showing {min(len(properties), 10)} of {len(properties)} properties.*\n\n"
        
        # Add tips if few results
        if len(properties) < 3:
            response += "💡 **Tips for more results:**\n"
            response += "   • Expand your price range\n"
            response += "   • Consider nearby locations\n"
            if entities.get('exact_bedrooms'):
                response += "   • Try different bedroom counts\n"
        
    else:
        response = f"❌ **No posted properties for: {criteria_desc}**\n\n"
        response += "💡 **Suggestions:**\n"
        response += "   • Try a different price range\n"
        response += "   • Consider nearby locations\n"
        response += "   • Adjust your bedroom requirements\n"
        response += "   • Check back later for new listings\n"
    
    return response

# Generate appropriate response for sale_type queries
def generate_sale_type_response(entities: Dict[str, Any], properties: List[Dict[str, Any]], query: str) -> str:
    """Generate appropriate response for sale_type queries"""
    query_lower = query.lower()
    
    # Check if user is asking for properties WITH specific sale type
    has_property_search_words = any(keyword in query_lower for keyword in [
        'properties that accept', 
        'show me properties', 
        'find properties', 
        'properties with',
        'houses that accept',
        'condos with',
        'properties with sale type',
        'properties accepting',
        'find sale',
        'looking for sale'
    ])
    
    # Check if it's a sale_type query
    sale_type = entities.get('sale_type')
    
    if sale_type and has_property_search_words and properties:
        # User wants to see properties with specific sale type
        sale_type_display = sale_type.replace('_', ' ').title()
        
        response = f"🏦 **Properties with {sale_type_display}**\n\n"
        response += f"I found {len(properties)} properties available with {sale_type_display.lower()}:\n\n"
        
        for i, prop in enumerate(properties[:5]):
            title = prop.get('title', f'Property {i+1}')
            price = prop.get('price', 'Price not available')
            location = prop.get('location', 'Location not specified')
            response += f"{i+1}. **{title}** in {location} - {price}\n"
        
        if not properties:
            response += f"❌ No properties found with {sale_type_display}.\n\n"
            response += "💡 Try:\n• Expanding your search area\n• Checking back later\n• Contacting us for custom search\n"
        
        return response
    
    # Handle financing information queries (documents, requirements)
    elif entities.get('has_financing_info_query'):
        # User is asking ABOUT financing (documents, process, etc.)
        query_lower = query.lower()
        
        # Check what type of financing info they want
        if 'pag-ibig' in query_lower or 'housing loan' in query_lower or 'pagibig' in query_lower:
            # Provide Pag-IBIG information
            return "🏦 **Pag-IBIG Housing Loan Information**\n\n" \
                   "For Pag-IBIG housing loans, you typically need:\n\n" \
                   "**Required Documents:**\n" \
                   "• Valid IDs (at least 2)\n" \
                   "• Proof of income (payslips, ITR)\n" \
                   "• Proof of billing\n" \
                   "• Marriage contract (if married)\n" \
                   "• Tax Identification Number (TIN)\n\n" \
                   "**Basic Requirements:**\n" \
                   "• Must be a Pag-IBIG member\n" \
                   "• At least 24 months membership\n" \
                   "• Active membership status\n" \
                   "• Meet minimum income requirements\n\n" \
                   "**Note:** Properties marked with 'bank_financing' sale type may also work with Pag-IBIG loans upon approval."
        
        elif 'bank financing' in query_lower or 'bank loan' in query_lower:
            # Provide bank financing information
            return "🏦 **Bank Financing Information**\n\n" \
                   "For bank financing, requirements vary by bank but generally include:\n\n" \
                   "**Common Requirements:**\n" \
                   "• Valid IDs\n" \
                   "• Proof of income (3-6 months)\n" \
                   "• Proof of billing\n" \
                   "• Bank statements\n" \
                   "• Tax documents (ITR, 2316)\n" \
                   "• Employment certificate\n\n" \
                   "**Process:**\n" \
                   "1. Pre-qualification\n" \
                   "2. Property appraisal\n" \
                   "3. Loan application submission\n" \
                   "4. Credit investigation\n" \
                   "5. Loan approval\n" \
                   "6. Release of funds\n\n" \
                   "Look for properties marked with 'bank_financing' sale type."
    
    return None  # Let the main generate_response handle it

# Generate response from training data templates - UPDATED FOR CRITERIA SEARCHES
def generate_response(intent: str, entities: Dict[str, Any], properties: List[Dict[str, Any]]) -> str:
    """Generate response based on intent and entities using training data templates"""

    # ========== NEW: Handle "No Properties Found" First ==========
    if intent == 'find_property' and len(properties) == 0:
        location = entities.get('location', 'the specified location')
        property_type = entities.get('property_type', 'properties')
        
        # Format property type for display
        property_type_display = property_type.replace('_', ' ').title() if property_type else 'properties'
        
        # Build criteria description
        criteria_parts = []
        if property_type_display:
            criteria_parts.append(property_type_display.lower())
        
        if entities.get('max_price'):
            max_price = entities['max_price']
            if max_price >= 1000000:
                criteria_parts.append(f"under ₱{max_price/1000000:.1f}M")
            else:
                criteria_parts.append(f"under ₱{max_price:,.0f}")
        
        if entities.get('exact_bedrooms') is not None:
            bedrooms = entities['exact_bedrooms']
            criteria_parts.append(f"with {bedrooms} bedroom{'s' if bedrooms != 1 else ''}")
        
        if location and location != 'the specified location':
            criteria_parts.append(f"in {location}")
        
        criteria_desc = " ".join(criteria_parts) if criteria_parts else "your search criteria"
        
        response = f"❌ **No posted properties for {criteria_desc}**\n\n"
        response += "I couldn't find any properties matching your search.\n\n"
        response += "💡 **Suggestions:**\n"
        
        if location and location != 'the specified location':
            response += f"   • Try nearby locations instead of {location}\n"
        
        if entities.get('max_price'):
            response += "   • Increase your budget or price range\n"
        
        if entities.get('exact_bedrooms') is not None:
            response += "   • Try different bedroom counts\n"
        
        response += "   • Check back later for new listings\n"
        response += "   • Contact us for custom property searches\n"
        
        return response
    
    # ========== NEW: Handle criteria-based searches ==========
    if intent == 'find_property_with_criteria':
        return generate_criteria_search_response(entities, properties)
    
    # ========== Handle general property searches (no location) ==========
    if intent == 'find_property' and entities.get('has_general_search'):
        return generate_general_search_response(entities, properties)
    
    # ========== Existing code for other intents ==========
    
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
                    '{sale_type}': entities.get('sale_type', 'financing'),  # CHANGED: from financing_type to sale_type
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
    if intent == 'financing' and entities.get('sale_type'):
        sale_type = entities['sale_type']
        sale_type_display = sale_type.replace('_', ' ').title()
        
        response += f"\n\n🏦 **{sale_type_display} Information**\n"
        
        if sale_type == 'bank_financing':
            response += "\n**Bank Financing Options:**\n"
            response += "• BDO\n• Metrobank\n• UnionBank\n• RCBC\n• Other accredited banks\n"
            response += "\n**Typical Requirements:**\n"
            response += "• Valid IDs\n• Proof of income\n• Bank statements\n• Proof of billing\n"
        
        elif sale_type == 'outright':
            response += "\n**Outright/Cash Payment:**\n"
            response += "• Full payment upon purchase\n• Usually offers discounts\n• Faster transaction process\n"
        
        elif sale_type == 'installment':
            response += "\n**Installment/In-house Financing:**\n"
            response += "• Developer-assisted financing\n• Flexible payment terms\n• Usually higher interest rates\n"
    
    return response

# NEW: Generate response for general searches (no location)
def generate_general_search_response(entities: Dict[str, Any], properties: List[Dict[str, Any]]) -> str:
    """Generate response for general property searches without location"""
    
    property_type = entities.get('property_type', 'properties')
    property_type_display = property_type.replace('_', ' ').title() if property_type else 'properties'
    
    if properties:
        # Group properties by city for better organization
        properties_by_city = defaultdict(list)
        for prop in properties:
            city = prop.get('city', 'Unknown City')
            properties_by_city[city].append(prop)
        
        # Sort cities by number of properties
        sorted_cities = sorted(properties_by_city.items(), key=lambda x: len(x[1]), reverse=True)
        
        response = f"🔍 **{property_type_display} Available in Batangas**\n\n"
        response += f"I found {len(properties)} {property_type_display.lower()} across different locations:\n\n"
        
        # Show top locations with properties
        displayed_count = 0
        for city, city_props in sorted_cities[:5]:  # Top 5 cities
            if displayed_count >= 15:  # Limit total properties shown
                break
                
            response += f"**📍 {city}** ({len(city_props)} available)\n"
            
            # Show top 3 properties from this city
            for i, prop in enumerate(city_props[:3]):
                title = prop.get('title', f'{property_type_display} {i+1}')
                price = prop.get('price', 'Price not available')
                prop_type = prop.get('type', property_type).replace('_', ' ')
                
                response += f"   • **{title}** ({prop_type}) - {price}\n"
                displayed_count += 1
            
            response += "\n"
        
        # Show summary
        if len(properties) > displayed_count:
            response += f"\n*Showing {displayed_count} of {len(properties)} {property_type_display.lower()}. "
            response += f"Properties found in {len(properties_by_city)} different locations.*\n"
        else:
            response += f"\n*Properties found in {len(properties_by_city)} different locations.*\n"
        
        # Add helpful tips
        response += "\n💡 **Tips for better results:**\n"
        response += "   • Add a location: *'find apartments in Batangas City'*\n"
        response += "   • Specify budget: *'find houses under 3M'*\n"
        response += "   • Add features: *'find condos with swimming pool'*\n"
        response += "   • Specify needs: *'find properties for family'*\n"
        
        # Suggest popular locations based on property type
        if property_type in ['house', 'condo', 'apartment']:
            response += "\n📍 **Popular locations for " + property_type_display.lower() + ":**\n"
            response += "   • Batangas City (urban living, near port)\n"
            response += "   • Lipa City (cool climate, educational hub)\n"
            response += "   • Nasugbu (beachfront, vacation homes)\n"
            response += "   • Sto. Tomas City (near Metro Manila)\n"
            response += "   • Tanauan City (Taal Lake views)\n"
        
    else:
        response = f"❌ **No posted {property_type_display.lower()} available**\n\n"
        response += "💡 **Try these suggestions:**\n"
        response += "   • Check if the property type is spelled correctly\n"
        response += "   • Try a broader search: *'find properties'*\n"
        response += "   • Specify a location: *'find {property_type_display.lower()} in Lipa City'*\n"
        response += "   • Check back later for new listings\n"
    
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
                
                # ========== CRITICAL FIX: AGGRESSIVE INTENT OVERRIDE ==========
                query_lower = query.lower()
                
                # Pattern 1: "find X in Y" should ALWAYS be find_property, not location_info
                find_in_patterns = [
                    r'^find\s+\w+\s+in\s+\w+',
                    r'^search\s+\w+\s+in\s+\w+',
                    r'^look\s+for\s+\w+\s+in\s+\w+',
                    r'^show\s+me\s+\w+\s+in\s+\w+',
                    r'^need\s+\w+\s+in\s+\w+',
                    r'^want\s+\w+\s+in\s+\w+',
                ]
                
                for pattern in find_in_patterns:
                    if re.search(pattern, query_lower):
                        if intent != 'find_property':
                            logger.info(f"⚠️ FORCE OVERRIDE: Changing intent from {intent} to find_property")
                            intent = 'find_property'
                            confidence = 0.99  # Very high confidence
                        break
                
                # If still not fixed and query has "find apartments" or similar
                if intent == 'location_info' and any(term in query_lower for term in ['find ', 'search ', 'looking for']):
                    logger.info(f"⚠️ OVERRIDE: Query has search terms but got {intent}, forcing to find_property")
                    intent = 'find_property'
                
                # Also handle "apartments in batangas city" without "find"
                if intent == 'location_info' and any(term in query_lower for term in ['apartments in', 'houses in', 'condos in']):
                    logger.info(f"⚠️ OVERRIDE: Property type + location should be find_property, not {intent}")
                    intent = 'find_property'
                
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

        # List of intents that ALWAYS need property search
        search_intents = ["find_property", "find_near_landmark", "find_with_feature", 
                         "find_ready_property", "find_property_for_need", 
                         "find_property_with_criteria", "match_needs"]

        if intent in search_intents:
            # Always search for these intents
            properties = search_firestore_properties(entities)
            
        elif intent == "financing":
            # Special handling for financing queries
            query_lower = query.lower()
            
            # Check if user is asking for properties with specific sale type
            has_sale_type = entities.get('sale_type') is not None
            is_property_search = any(phrase in query_lower for phrase in [
                'properties that accept',
                'houses that accept', 
                'condos that accept',
                'apartments that accept',
                'show me properties',
                'find properties',
                'properties with',
                'real estate with',
                'find sale',
                'looking for sale'
            ])
            
            # Also check for action words that indicate property search
            has_search_action = any(word in query_lower for word in [
                'find', 'search', 'look for', 'show me', 'need', 'want'
            ])
            
            # Also check if it mentions property types
            has_property_type = any(word in query_lower for word in [
                'properties', 'houses', 'condos', 'apartments', 'units', 'spaces'
            ])
            
            if (has_sale_type and (is_property_search or (has_search_action and has_property_type))):
                # User is asking for properties with specific sale type
                logger.info(f"🔍 Sale type query is a property search - searching Firestore")
                properties = search_firestore_properties(entities)
            elif entities.get('has_financing_info_query'):
                # User is asking ABOUT financing (documents, process, etc.)
                logger.info(f"🔍 Financing query is information-only - NOT searching Firestore")
                properties = []  # No property search needed
            else:
                # Regular financing query, search properties
                properties = search_firestore_properties(entities)
            
        elif intent == "location_info":
            # For location_info, only search if there's a property type mentioned
            query_lower = query.lower()
            has_property_type = any(word in query_lower for word in [
                'apartment', 'house', 'condo', 'property', 'properties'
            ])
            
            if has_property_type:
                properties = search_firestore_properties(entities)
            else:
                properties = []  # Just location info, no properties
        
        # Step 4: Generate response using appropriate function
        # Check for sale_type or financing info queries first
        if entities.get('sale_type') or entities.get('has_financing_info_query'):
            sale_type_response = generate_sale_type_response(entities, properties, query)
            if sale_type_response:
                response_text = sale_type_response
            else:
                response_text = generate_response(intent, entities, properties)
        else:
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
            'properties': properties[:10],  # Increased limit for general searches
            'model_version': 'trained' if vectorizer else 'fallback',
            'is_general_search': entities.get('has_general_search', False),
            'is_criteria_search': intent == 'find_property_with_criteria',
            'has_sale_type_query': entities.get('sale_type') is not None
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

# Simple fallback if model isn't loaded - UPDATED
def determine_intent_fallback(query: str) -> str:
    """Simple rule-based intent detection as fallback"""
    query_lower = query.lower()
    
    # ========== CRITICAL FIX: CHECK SPECIFIC PATTERNS FIRST ==========
    
    # PATTERN 1: "find X in Y" - This MUST be find_property
    # Match: "find apartments in batangas city", "find house in lipa city"
    find_in_patterns = [
        r'^find\s+\w+\s+in\s+\w+',  # Starts with "find X in Y"
        r'^search\s+\w+\s+in\s+\w+',  # Starts with "search X in Y"
        r'^look\s+for\s+\w+\s+in\s+\w+',  # Starts with "look for X in Y"
        r'^show\s+me\s+\w+\s+in\s+\w+',  # Starts with "show me X in Y"
        r'^need\s+\w+\s+in\s+\w+',  # Starts with "need X in Y"
        r'^want\s+\w+\s+in\s+\w+',  # Starts with "want X in Y"
        r'^find\s+apartments?\s+in\s+',  # Specifically "find apartment(s) in"
        r'^find\s+houses?\s+in\s+',  # Specifically "find house(s) in"
        r'^find\s+condos?\s+in\s+',  # Specifically "find condo(s) in"
    ]
    
    for pattern in find_in_patterns:
        if re.search(pattern, query_lower):
            return 'find_property'
    
    # PATTERN 2: "tell me about X" - This MUST be location_info
    # Match: "tell me about batangas city", "information about lipa"
    location_info_patterns = [
        r'^tell\s+me\s+about\s+\w+',  # Starts with "tell me about"
        r'^what\s+is\s+\w+\s+like$',  # "what is X like"
        r'^describe\s+\w+$',  # "describe X"
        r'^how\s+is\s+life\s+in\s+\w+',  # "how is life in X"
        r'^information\s+about\s+\w+',  # "information about X"
        r'^about\s+\w+\s+city$',  # "about X city"
        r'^about\s+\w+\s+town$',  # "about X town"
    ]
    
    for pattern in location_info_patterns:
        if re.search(pattern, query_lower):
            return 'location_info'
    
    # ========== CHECK FOR SALE TYPE/FINANCING QUERIES ==========
    
    # Sale type detection (bank_financing, outright, installment)
    sale_type_keywords = [
        'bank financing', 'bank loan', 'bank mortgage', 'bank_financing',
        'outright', 'cash payment', 'full payment',
        'installment', 'installment plan', 'in-house financing', 'developer financing',
        'sale type', 'payment option'
    ]
    
    for keyword in sale_type_keywords:
        if keyword in query_lower:
            return 'financing'
    
    # Financing information queries
    if any(phrase in query_lower for phrase in [
        'what documents', 'requirements for', 'how to get loan',
        'pag-ibig', 'housing loan', 'mortgage documents',
        'loan requirements', 'financing documents', 'bank requirements'
    ]):
        return 'financing'
    
    # ========== CHECK FOR SPECIFIC PROPERTY SEARCH QUERIES ==========
    
    # Clear property search patterns (no location)
    if any(query_lower.startswith(prefix) for prefix in [
        'find apartments', 'find houses', 'find condos',
        'search apartments', 'search houses', 'search condos',
        'looking for apartments', 'looking for houses', 'looking for condos',
        'show me apartments', 'show me houses', 'show me condos',
    ]):
        return 'find_property'
    
    # ========== CHECK FOR GENERAL SEARCH INTENTS ==========
    
    # Strong indicators of find_property intent
    strong_property_indicators = [
        'find apartment', 'find house', 'find condo',
        'search apartment', 'search house', 'search condo',
        'looking for apartment', 'looking for house', 'looking for condo',
        'need apartment', 'need house', 'need condo',
        'want apartment', 'want house', 'want condo',
        'do you have apartments', 'do you have houses', 'do you have condos',
        'any apartments', 'any houses', 'any condos',
        'what apartments', 'what houses', 'what condos',
    ]
    
    for indicator in strong_property_indicators:
        if indicator in query_lower:
            return 'find_property'
    
    # Check for property search terms
    has_property_terms = any(word in query_lower for word in [
        'find', 'search', 'looking for', 'need', 'want',
        'locate', 'show me', 'available', 'properties',
        'real estate', 'property listing', 'house for',
        'apartment for', 'condo for'
    ])
    
    # Check for specific property types
    has_property_type = any(word in query_lower for word in [
        'apartment', 'condo', 'condominium', 'house', 'home',
        'townhouse', 'commercial', 'office', 'retail', 'warehouse',
        'land', 'lot', 'beachfront', 'resort', 'villa', 'bungalow',
        'studio', 'penthouse', 'loft', 'duplex'
    ])
    
    # If it has both property terms and property type, it's find_property
    if has_property_terms and has_property_type:
        return 'find_property'
    
    # If it has strong property search verbs, it's find_property
    if any(verb in query_lower for verb in ['find', 'search', 'look for', 'show me']):
        # But not if it's asking "about" something
        if not any(word in query_lower for word in ['about', 'information', 'describe', 'what is']):
            return 'find_property'
    
    # ========== CHECK FOR OTHER INTENTS ==========
    
    # Ready property intent
    if any(phrase in query_lower for phrase in [
        'ready to move', 'ready for occupancy', 'available now',
        'immediate occupancy', 'move in ready', 'ready now',
        'ready to occupy', 'immediate move in', 'available immediately'
    ]):
        return 'find_ready_property'
    
    # Process info intent
    if any(phrase in query_lower for phrase in [
        'steps for', 'how to', 'process of', 'procedure',
        'timeline', 'requirements', 'documents', 'steps to',
        'how do i', 'what are the steps', 'costs for',
        'timeline for', 'process for'
    ]):
        return 'process_info'
    
    # With feature intent
    if any(phrase in query_lower for phrase in [
        'with swimming pool', 'with pool', 'with garden',
        'with parking', 'with elevator', 'with security',
        'with wifi', 'with furniture', 'with aircon',
        'with feature', 'featuring', 'having'
    ]):
        return 'find_with_feature'
    
    # Near landmark intent
    if any(phrase in query_lower for phrase in [
        'near schools', 'near mall', 'near hospital',
        'near port', 'near beach', 'near church',
        'near landmark', 'close to', 'around',
        'beside', 'next to', 'adjacent to'
    ]):
        return 'find_near_landmark'
    
    # Property for need intent
    if any(phrase in query_lower for phrase in [
        'for family', 'for students', 'for professionals',
        'for couple', 'for retirees', 'for business',
        'for investors', 'for single', 'for workers'
    ]):
        return 'find_property_for_need'
    
    # Match needs intent
    if any(phrase in query_lower for phrase in [
        'match my', 'suitable for', 'fitting my', 'appropriate for',
        'compatible with', 'what matches', 'recommendations for'
    ]):
        return 'match_needs'
    
    # Property with criteria intent
    if any(phrase in query_lower for phrase in [
        'under', 'below', 'less than', 'maximum', 'up to',
        'with bedroom', 'with bath', 'with bathrooms',
        'with bedrooms', 'bedroom', 'bathroom', 'rooms',
        'price range', 'budget', 'affordable', 'cheap'
    ]):
        return 'find_property_with_criteria'
    
    # Location info intent (catch-all for location queries)
    location_indicators = [
        'tell me about', 'what is', 'describe', 'about the',
        'information about', 'living in', 'like to live',
        'what\'s it like', 'is it good', 'lifestyle',
        'about', 'information on', 'details about'
    ]
    
    for indicator in location_indicators:
        if indicator in query_lower:
            return 'location_info'
    
    # ========== FINAL CHECKS ==========
    
    # Check if query contains a known Batangas location
    batangas_locations = [
        'batangas city', 'lipa city', 'nasugbu', 'tanauan',
        'taal', 'calatagan', 'mabini', 'malvar', 'bauan',
        'balayan', 'san juan', 'sto tomas', 'santo tomas'
    ]
    
    # If query contains a location and property terms, it's find_property
    has_location = any(loc in query_lower for loc in batangas_locations)
    if has_location and (has_property_terms or has_property_type):
        return 'find_property'
    
    # If query contains only a location, it's location_info
    if has_location and not (has_property_terms or has_property_type):
        return 'location_info'
    
    # Default to find_property for general property queries
    if has_property_terms or has_property_type:
        return 'find_property'
    
    # If query is about a location (ends with "city" or contains location words)
    if any(word in query_lower for word in ['city', 'town', 'municipality', 'province']):
        return 'location_info'
    
    return 'unknown'

@app.route('/api/health', methods=['GET'])
def health_check():
    """Health check endpoint"""
    # Check if Firebase environment variable exists
    firebase_env_exists = 'FIREBASE_SERVICE_ACCOUNT_JSON' in os.environ
    
    return jsonify({
        'status': 'healthy',
        'service': 'Bah.AI Property Chatbot',
        'version': '3.7',  # Updated version
        'deployed_url': 'https://bahai.onrender.com',
        'firebase_connected': db is not None,
        'firebase_env_exists': firebase_env_exists,
        'model_loaded': vectorizer is not None and classifier is not None,
        'model_intents': model_classes if vectorizer else [],
        'training_data_loaded': bool(training_data),
        'supports_general_searches': True,
        'supports_criteria_searches': True,
        'supports_sale_type_filtering': True,  # Added
        'mock_data_mode': db is None,  # True if using mock data
        'timestamp': datetime.now().isoformat(),
        'endpoints': {
            'chat': '/api/chat (POST)',
            'health': '/api/health (GET)',
            'test': '/api/test (GET)'
        }
    })

@app.route('/api/test', methods=['GET'])
def test_endpoint():
    """Test endpoint to verify the model is working"""
    test_queries = [
        # Sale type queries
        "show me properties with bank financing",
        "find houses with outright payment",
        "properties with installment plan",
        
        # Criteria-based searches
        "show me houses under 15M with 3 bedrooms",
        "find condos below 10M with 2 bedrooms",
        "properties under 5M with 1 bedroom",
        
        # General searches (no location)
        "find apartments",
        "show me houses",
        "what condos do you have",
        
        # Location-specific searches
        "find apartments in batangas city",
        "properties near schools",
    ]
    
    results = []
    for query in test_queries:
        try:
            if vectorizer and classifier:
                processed = preprocess_text(query)
                X = vectorizer.transform([processed])
                intent = classifier.predict(X)[0]
                confidence = float(classifier.predict_proba(X).max())
                
                # Extract entities
                entities = extract_entities_from_query(query)
                
                results.append({
                    'query': query,
                    'intent': intent,
                    'confidence': confidence,
                    'has_location': entities.get('location') is not None,
                    'property_type': entities.get('property_type'),
                    'sale_type': entities.get('sale_type'),  # Added
                    'max_price': entities.get('max_price'),
                    'exact_bedrooms': entities.get('exact_bedrooms'),
                    'is_criteria_search': intent == 'find_property_with_criteria',
                    'is_sale_type_query': entities.get('sale_type') is not None
                })
        except Exception as e:
            results.append({
                'query': query,
                'error': str(e)
            })
    
    return jsonify({
        'test_results': results,
        'model_status': 'loaded' if vectorizer else 'not loaded',
        'training_data_status': 'loaded' if training_data else 'not loaded',
        'supports_criteria_searches': True,
        'supports_general_searches': True,
        'supports_sale_type_filtering': True  # Added
    })

# ==================== MODEL LOADING (RUNS ON IMPORT) ====================
print("\n" + "="*60)
print("🚀 BAH.AI PROPERTY CHATBOT BACKEND v3.7")
print("   (Fixed: Using saleType instead of financingOptions)")
print("="*60)

print("📝 Step 1: Loading NLU model...")
load_nlu_model()

print("📝 Step 2: Loading training data...")
load_training_data()

print("📝 Step 3: Printing status...")
print(f"\n📂 NLU Model: {'✅ Loaded' if vectorizer else '❌ Not loaded'}")
print(f"📚 Training Data: {'✅ Loaded' if training_data else '❌ Not loaded'}")
print(f"🔥 Firebase: {'✅ Connected' if db else '❌ Not connected'}")
print(f"🔍 General Searches: {'✅ Supported'}")
print(f"🔍 Criteria Searches: {'✅ Supported'}")
print(f"💰 Sale Type Filtering: {'✅ Supported (bank_financing, outright, installment)'}")

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

print("\n🔍 Example queries to try:")
print("   • 'show me properties with bank financing' (sale type filter)")
print("   • 'find houses with outright payment' (sale type filter)")
print("   • 'properties with installment plan' (sale type filter)")
print("   • 'show me houses under 15M with 3 bedrooms' (criteria search)")
print("   • 'find condos below 10M with 2 bedrooms' (criteria search)")
print("   • 'find apartments' (general search)")
print("   • 'find apartments in batangas city' (location-specific)")

print("="*60 + "\n")

# ==================== MAIN BLOCK (for local development only) ====================
if __name__ == '__main__':
    port = int(os.environ.get("PORT", 5000))
    app.run(host="0.0.0.0", port=port)