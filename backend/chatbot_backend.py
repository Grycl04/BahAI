# backend/chatbot_backend.py - COMPLETE UPDATED VERSION
from flask import Flask, request, jsonify
from pathlib import Path
from flask_cors import CORS
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
import spacy
import numpy as np
import random
import sys
from collections import defaultdict

warnings.filterwarnings("ignore", message="Detected filter using positional arguments")
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

print("\n" + "="*60)
print("🔥 FIREBASE CONNECTION")
print("="*60)

# Initialize Firebase
try:
    # Get absolute path to serviceAccountKey.json in root
    current_dir = os.path.dirname(os.path.abspath(__file__))  # backend directory
    root_dir = os.path.dirname(current_dir)                    # project root
    cred_path = os.path.join(root_dir, 'serviceAccountKey.json')
    
    print(f"🔑 Key path: {cred_path}")
    
    if os.path.exists(cred_path):
        # Load credentials
        cred = credentials.Certificate(cred_path)
        
        # Initialize Firebase
        firebase_admin.initialize_app(cred, {
            'projectId': 'bahai-1b76d',
        })
        
        # Get Firestore client
        db = firestore.client()
        print("✅ Firebase connected successfully!")
        
        # Test connection by counting properties
        try:
            properties_ref = db.collection('properties')
            docs = list(properties_ref.limit(5).get())
            print(f"📊 Found {len(docs)} properties in database")
            
            # Show property types for debugging
            property_types = set()
            for doc in docs:
                data = doc.to_dict()
                prop_type = data.get('propertyType', data.get('type', 'unknown'))
                property_types.add(prop_type)
            
            if property_types:
                print(f"🔍 Property types found: {', '.join(property_types)}")
            
        except Exception as e:
            print(f"⚠️ Database query warning: {e}")
            
    else:
        print(f"❌ ERROR: serviceAccountKey.json not found!")
        db = None
        
except Exception as e:
    print(f"❌ Firebase connection failed: {e}")
    import traceback
    traceback.print_exc()
    print("\n⚠️  Switching to mock data mode")
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

# Entity extraction - UPDATED FOR BETTER PRICE AND BEDROOM PARSING
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
        'financing_type': None,
        'listing_type': None,  # rent, sale, lease
        'has_general_search': False,  # NEW: Flag for general search
        'max_price': None,  # NEW: Numeric max price for filtering
        'min_price': None,  # NEW: Numeric min price for filtering
        'min_bedrooms': None,  # NEW: Numeric bedroom count for filtering
        'exact_bedrooms': None  # NEW: Exact bedroom count
    }
    
    query_lower = query.lower()
    
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
    
    # Detect listing type
    if 'for rent' in query_lower or 'rental' in query_lower:
        entities['listing_type'] = 'rent'
    elif 'for sale' in query_lower or 'buy' in query_lower:
        entities['listing_type'] = 'sale'
    elif 'for lease' in query_lower:
        entities['listing_type'] = 'lease'
    
    # Property type detection - updated for your categories
    property_type_map = {
        'apartment': 'apartment',
        'condo': 'condo', 'condominium': 'condo',
        'house': 'house', 'villa': 'house', 'bungalow': 'house',
        'townhouse': 'townhouse',
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
        'batangas city': 'Batangas City',
        'lipa': 'Lipa City', 'lipa city': 'Lipa City',
        'nasugbu': 'Nasugbu',
        'tanauan': 'Tanauan City', 'tanauan city': 'Tanauan City',
        'taal': 'Taal',
        'calatagan': 'Calatagan',
        'mabini': 'Mabini',
        'malvar': 'Malvar',
        'mataas na kahoy': 'Mataas Na Kahoy', 'mataasnakahoy': 'Mataas Na Kahoy',
        'bauan': 'Bauan',
        'balayan': 'Balayan',
        'san juan': 'San Juan',
        'sto tomas': 'Sto. Tomas City', 'santo tomas': 'Sto. Tomas City',
        'sto. tomas': 'Sto. Tomas City'
    }
    
    for location_key, location_value in batangas_locations.items():
        if location_key in query_lower:
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
    
    # Financing type detection - check for your financing options
    financing_keywords = {
        'bank financing': 'bank_financing',
        'bdo': 'BDO',
        'metrobank': 'Metrobank',
        'unionbank': 'UnionBank',
        'rcbc': 'RCBC',
        'pag-ibig': 'pag_ibig',
        'housing loan': 'housing_loan'
    }
    
    for keyword, financing_type in financing_keywords.items():
        if keyword in query_lower:
            entities['financing_type'] = financing_type
            break
    
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
        'financingOptions': property_data.get('financingOptions', []),
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
            'financingOptions': ['Bank Financing - BDO', 'Pag-IBIG Housing Loan']
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
            'status': 'available'
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
    
    return mock_properties

# Firestore queries - UPDATED WITH PROPER PRICE AND BEDROOM FILTERING
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
        
        # Always filter by available status
        query = query.where(filter=FieldFilter('status', '==', 'available'))
        
        # NEW: Handle general searches (no location specified)
        is_general_search = not entities.get('location') and entities.get('has_general_search')
        
        # Filter by location if specified
        if entities.get('location'):
            location = entities['location']
            
            # Map chatbot locations to your Firestore city values
            location_map = {
                'Batangas City': 'Batangas City',
                'Lipa City': 'Lipa City',
                'Nasugbu': 'Nasugbu',
                'Malvar': 'Malvar',
                'Mataas Na Kahoy': 'Mataas Na Kahoy',
                'Tanauan City': 'Tanauan City',
                'Taal': 'Taal',
                'Calatagan': 'Calatagan',
                'Mabini': 'Mabini',
                'Bauan': 'Bauan',
                'Balayan': 'Balayan',
                'San Juan': 'San Juan',
                'Sto. Tomas City': 'Sto. Tomas City',
                'Santo Tomas': 'Sto. Tomas City',
                'Sto Tomas': 'Sto. Tomas City'
            }
            
            if location in location_map:
                query = query.where(filter=FieldFilter('city', '==', location_map[location]))
                logger.info(f"🔍 Filtering by city: {location_map[location]}")
            else:
                # Try case-insensitive match
                location_lower = location.lower()
                for map_key, map_value in location_map.items():
                    if map_key.lower() == location_lower:
                        query = query.where(filter=FieldFilter('city', '==', map_value))
                        logger.info(f"🔍 Filtering by city (case-insensitive): {map_value}")
                        break
        else:
            if is_general_search:
                logger.info(f"🔍 General search for {entities.get('property_type', 'properties')} (no location filter)")
            else:
                logger.info("🔍 No location specified - showing properties from all locations")
        
        # Filter by property type if specified
        if entities.get('property_type'):
            property_type = entities['property_type']
            
            # Map chatbot property types to your Firestore propertyType values
            type_map = {
                'apartment': 'apartment',
                'condo': 'condo_unit',  # Your database uses 'condo_unit'
                'condominium': 'condo_unit',
                'house': 'house',
                'townhouse': 'townhouse',
                'commercial': 'commercial_building',
                'commercial_building': 'commercial_building',
                'office': 'office_unit',
                'retail': 'retail_space',
                'warehouse': 'warehouse',
                'land': 'residential_lot',
                'lot': 'residential_lot',
                'residential_lot': 'residential_lot',
                'beachfront': 'beachfront',
                'resort': 'resort_property',
                'resort_property': 'resort_property'
            }
            
            if property_type in type_map:
                mapped_type = type_map[property_type]
                query = query.where(filter=FieldFilter('propertyType', '==', mapped_type))
                logger.info(f"🔍 Filtering by property type: {mapped_type}")
            else:
                # Try case-insensitive match
                prop_type_lower = property_type.lower()
                for map_key, map_value in type_map.items():
                    if map_key.lower() == prop_type_lower:
                        query = query.where(filter=FieldFilter('propertyType', '==', map_value))
                        logger.info(f"🔍 Filtering by property type (case-insensitive): {map_value}")
                        break
        
        # ========== APPLY PRICE FILTERS IF SPECIFIED ==========
        if entities.get('max_price'):
            max_price = entities['max_price']
            logger.info(f"💰 Applying max price filter: ₱{max_price:,.0f}")
            
            # Try to filter by monthlyRent for rentals
            try:
                query = query.where(filter=FieldFilter('monthlyRent', '<=', max_price))
                logger.info(f"🔍 Filtering by max monthly rent: ₱{max_price:,.0f}")
            except Exception as rent_error:
                logger.warning(f"⚠️ Could not filter by monthlyRent: {rent_error}")
                # Try salePrice for sales
                try:
                    query = query.where(filter=FieldFilter('salePrice', '<=', max_price))
                    logger.info(f"🔍 Filtering by max sale price: ₱{max_price:,.0f}")
                except Exception as sale_error:
                    logger.warning(f"⚠️ Could not filter by salePrice: {sale_error}")
                    # Try annualRent for leases
                    try:
                        query = query.where(filter=FieldFilter('annualRent', '<=', max_price))
                        logger.info(f"🔍 Filtering by max annual rent: ₱{max_price:,.0f}")
                    except Exception as annual_error:
                        logger.warning(f"⚠️ Could not filter by annualRent: {annual_error}")
        
        # ========== APPLY BEDROOM FILTER IF SPECIFIED ==========
        if entities.get('exact_bedrooms') is not None:
            bedrooms = entities['exact_bedrooms']
            bed_str = str(bedrooms) if bedrooms <= 5 else '5+'
            
            try:
                query = query.where(filter=FieldFilter('bedrooms', '==', bed_str))
                logger.info(f"🛏️ Filtering by exact bedroom count: {bed_str}")
            except Exception as bed_error:
                logger.warning(f"⚠️ Could not filter by bedrooms: {bed_error}")
        
        # Filter by financing if specified
        if entities.get('financing_type'):
            financing_type = entities['financing_type'].lower()
            logger.info(f"🔍 Looking for financing: {financing_type}")
            
            # Try different financing options
            financing_terms = []
            if 'bank' in financing_type:
                financing_terms.extend(['Bank Financing', 'bank', 'loan'])
            if 'pag' in financing_type or 'ibig' in financing_type:
                financing_terms.extend(['Pag-IBIG', 'pagibig', 'housing loan'])
            if 'in-house' in financing_type:
                financing_terms.extend(['In-House', 'developer financing'])
            
            if financing_terms:
                # Try to find properties with any of these financing options
                for term in financing_terms[:3]:  # Try first 3 terms
                    try:
                        temp_query = query.where(filter=FieldFilter('financingOptions', 'array_contains', term))
                        # Test if this query would return results
                        test_docs = list(temp_query.limit(1).get())
                        if test_docs:
                            query = temp_query
                            logger.info(f"🔍 Filtering by financing term: {term}")
                            break
                    except:
                        continue
        
        # Execute query with appropriate limit
        limit_count = 20 if is_general_search else 10  # More results for general searches
        logger.info(f"🔍 Executing Firestore query (limit: {limit_count})...")
        docs = query.limit(limit_count).get()
        
        found_count = 0
        for doc in docs:
            property_data = doc.to_dict()
            property_data['id'] = doc.id
            
            # Add numeric price value before standardizing
            property_data_with_price = add_price_numeric_value(property_data)
            
            # Standardize property data for chatbot response
            standardized_property = standardize_property_data(property_data_with_price)
            properties.append(standardized_property)
            found_count += 1
        
        logger.info(f"🔍 Found {found_count} properties matching criteria")
        
        # ========== CLIENT-SIDE FILTERING AS FALLBACK ==========
        # If Firestore filtering didn't work properly, filter client-side
        filtered_properties = []
        for prop in properties:
            matches = True
            
            # Apply max price filter client-side
            if entities.get('max_price'):
                price_numeric = prop.get('price_numeric', 0)
                if price_numeric > entities['max_price']:
                    matches = False
            
            # Apply exact bedroom filter client-side
            if entities.get('exact_bedrooms') is not None and matches:
                prop_bedrooms = prop.get('bedrooms', 'Not specified')
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
                    # If can't parse bedrooms, skip this filter
                    pass
            
            if matches:
                filtered_properties.append(prop)
        
        # Update properties with client-side filtered results
        properties = filtered_properties
        logger.info(f"🔍 After client-side filtering: {len(properties)} properties")
        
        # If no properties found and it's a general search, try broader search
        if len(properties) == 0:
            logger.info("🔄 No exact matches found, trying broader search...")
            
            # Broaden search: remove some filters but keep status=available
            broad_query = properties_ref.where(filter=FieldFilter('status', '==', 'available'))
            
            # Keep location filter if it exists
            if entities.get('location'):
                location = entities['location']
                for map_key, map_value in location_map.items():
                    if location.lower() == map_key.lower():
                        broad_query = broad_query.where(filter=FieldFilter('city', '==', map_value))
                        break
            
            # Keep property type filter if it exists
            if entities.get('property_type'):
                property_type = entities['property_type']
                if property_type in type_map:
                    broad_query = broad_query.where(filter=FieldFilter('propertyType', '==', type_map[property_type]))
            
            # Get random available properties
            broad_docs = broad_query.limit(limit_count).get()
            
            for doc in broad_docs:
                property_data = doc.to_dict()
                property_data['id'] = doc.id
                
                property_data_with_price = add_price_numeric_value(property_data)
                standardized_property = standardize_property_data(property_data_with_price)
                properties.append(standardized_property)
            
            logger.info(f"🔄 Found {len(properties)} properties in broader search")
        
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
        response = f"❌ **No properties found matching: {criteria_desc}**\n\n"
        response += "💡 **Suggestions:**\n"
        response += "   • Try a different price range\n"
        response += "   • Consider nearby locations\n"
        response += "   • Adjust your bedroom requirements\n"
        response += "   • Check back later for new listings\n"
    
    return response

# Generate response from training data templates - UPDATED FOR CRITERIA SEARCHES
def generate_response(intent: str, entities: Dict[str, Any], properties: List[Dict[str, Any]]) -> str:
    """Generate response based on intent and entities using training data templates"""
    
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

# NEW: Generate response for general searches (no location)
def generate_general_search_response(entities: Dict[str, Any], properties: List[Dict[str, Any]]) -> str:
    """Generate response for general property searches without location"""
    
    property_type = entities.get('property_type', 'properties')
    property_type_display = property_type.replace('_', ' ').title()
    
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
        response = f"I couldn't find any {property_type_display.lower()} matching your criteria.\n\n"
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
            'properties': properties[:10],  # Increased limit for general searches
            'model_version': 'trained' if vectorizer else 'fallback',
            'is_general_search': entities.get('has_general_search', False),
            'is_criteria_search': intent == 'find_property_with_criteria'
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
    
    # Check for property search terms first (general or specific)
    has_property_terms = any(word in query_lower for word in ['find', 'search', 'show me', 'looking for', 'need', 
                                                              'want', 'locate', 'what apartments', 'what houses', 
                                                              'what condos', 'do you have', 'any properties'])
    
    # Check if it's specifically asking about property type
    has_property_type = any(word in query_lower for word in ['apartment', 'condo', 'house', 'townhouse', 
                                                             'commercial', 'office', 'retail', 'warehouse', 
                                                             'land', 'lot', 'beachfront', 'resort'])
    
    # If it has property terms, it's likely a find_property intent
    if has_property_terms or has_property_type:
        return 'find_property'
    
    # Check other intents
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
    
    return 'unknown'

@app.route('/api/health', methods=['GET'])
def health_check():
    """Health check endpoint"""
    return jsonify({
        'status': 'healthy',
        'service': 'Bah.AI Property Chatbot',
        'version': '3.6',  # Updated version
        'model_loaded': vectorizer is not None and classifier is not None,
        'training_data_loaded': bool(training_data),
        'firebase_connected': db is not None,
        'model_intents': model_classes,
        'model_features': len(vectorizer.get_feature_names_out()) if vectorizer else 0,
        'spacy_loaded': nlp is not None,
        'supports_general_searches': True,
        'supports_criteria_searches': True,  # NEW
        'timestamp': datetime.now().isoformat()
    })

@app.route('/api/test', methods=['GET'])
def test_endpoint():
    """Test endpoint to verify the model is working"""
    test_queries = [
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
        "how to get a mortgage",
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
                    'max_price': entities.get('max_price'),
                    'exact_bedrooms': entities.get('exact_bedrooms'),
                    'is_criteria_search': intent == 'find_property_with_criteria'
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
        'supports_general_searches': True
    })

# ==================== MAIN ====================
if __name__ == '__main__':
    print("\n" + "="*60)
    print("🚀 BAH.AI PROPERTY CHATBOT BACKEND v3.6")
    print("   (Supports price & bedroom criteria filtering)")
    print("="*60)
    
    # Load the trained model
    load_nlu_model()
    
    # Load training data for response templates
    load_training_data()
    
    print(f"\n📂 NLU Model: {'✅ Loaded' if vectorizer else '❌ Not loaded'}")
    print(f"📚 Training Data: {'✅ Loaded' if training_data else '❌ Not loaded'}")
    print(f"🔥 Firebase: {'✅ Connected' if db else '❌ Not connected'}")
    print(f"📊 spaCy: {'✅ Loaded' if nlp else '❌ Not loaded'}")
    print(f"🔍 General Searches: {'✅ Supported'}")
    print(f"🔍 Criteria Searches: {'✅ Supported'}")
    
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
    print("   • 'show me houses under 15M with 3 bedrooms' (criteria search)")
    print("   • 'find condos below 10M with 2 bedrooms' (criteria search)")
    print("   • 'find apartments' (general search)")
    print("   • 'show me houses' (general search)")
    print("   • 'find apartments in batangas city' (location-specific)")
    
    print("="*60 + "\n")
    
    app.run(host='0.0.0.0', port=5000, debug=True)