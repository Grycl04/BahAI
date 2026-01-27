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
    print(f"📁 File exists: {os.path.exists(cred_path)}")
    
    if os.path.exists(cred_path):
        # Read and check the key
        try:
            with open(cred_path, 'r') as f:
                key_data = json.load(f)
            
            print(f"✅ Valid JSON format")
            print(f"📋 Project ID: {key_data.get('project_id')}")
            print(f"📧 Client Email: {key_data.get('client_email')}")
            
            # IMPORTANT: Check if Firebase Admin SDK is already initialized
            if firebase_admin._DEFAULT_APP_NAME in firebase_admin._apps:
                print("⚠️  Firebase already initialized, using existing app")
                db = firestore.client()
            else:
                # Initialize with explicit configuration
                cred = credentials.Certificate(cred_path)
                
                # Initialize with specific parameters
                firebase_admin.initialize_app(cred, {
                    'projectId': 'bahai-1b76d',
                    'databaseURL': 'https://bahai-1b76d.firebaseio.com',  # Add this
                    'storageBucket': 'bahai-1b76d.appspot.com',  # Add this
                })
                
                print("✅ Firebase Admin SDK initialized")
                db = firestore.client()
                
            print("✅ Firebase connected successfully!")
            
            # Test connection with error handling
            try:
                print("🔍 Testing Firestore connection...")
                properties_ref = db.collection('properties')
                docs = list(properties_ref.get())  # REMOVED .limit(5) to get ALL
                print(f"📊 Found {len(docs)} properties in database")
                
                if docs:
                    print("✅ Firestore connection successful!")
                    
                    # Show ALL property types and count by type
                    property_types = {}
                    for doc in docs:
                        data = doc.to_dict()
                        prop_type = data.get('propertyType', data.get('type', 'unknown'))
                        if prop_type not in property_types:
                            property_types[prop_type] = 0
                        property_types[prop_type] += 1
                        
                    print(f"🔍 Property types found ({len(property_types)} types):")
                    for prop_type, count in property_types.items():
                        print(f"   • {prop_type}: {count} properties")
                    
                    # Show first few properties for debugging
                    print("\n📋 Sample properties (first 8):")
                    for i, doc in enumerate(docs[:8]):
                        data = doc.to_dict()
                        doc_id = doc.id
                        prop_type = data.get('propertyType', data.get('type', 'unknown'))
                        city = data.get('city', 'Unknown')
                        status = data.get('status', 'No Status')
                        sale_type = data.get('saleType', 'Not set')
                        logger.info(f"   {i+1}. ID: {doc_id[:10]}..., Type: {prop_type}, City: {city}, Status: {status}, SaleType: {sale_type}")
                        
                else:
                    print("⚠️ No properties found in database (empty collection)")
                    
            except Exception as e:
                print(f"⚠️ Firestore query warning: {str(e)}")
                print("💡 The connection is established but the query failed")
                print("   This might be normal if the collection is empty")
                
        except json.JSONDecodeError as e:
            print(f"❌ Invalid JSON in service account key: {e}")
            db = None
        except Exception as e:
            print(f"❌ Error loading service account: {e}")
            import traceback
            traceback.print_exc()
            db = None
            
    else:
        print(f"❌ ERROR: serviceAccountKey.json not found at {cred_path}")
        print("💡 Make sure the file is in your project root directory")
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
        'sale_type': None,     # NEW: outright, installment, bank_financing
        'financing_options': None,  # NEW: specific financing options (BDO, Metrobank, etc.)
        'has_general_search': False,
        'max_price': None,
        'min_price': None,
        'min_bedrooms': None,
        'exact_bedrooms': None
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
    
    # ========== NEW: Detect sale type (outright, installment, bank_financing) ==========
    # Check for saleType values
    if 'installment' in query_lower or 'installment plan' in query_lower or 'installment payment' in query_lower:
        entities['sale_type'] = 'installment'
        entities['financing_type'] = 'installment'
        logger.info(f"💰 Detected sale_type: installment")
    
    elif 'outright' in query_lower or 'cash' in query_lower or 'straight cash' in query_lower:
        entities['sale_type'] = 'outright'
        entities['financing_type'] = 'cash'
        logger.info(f"💰 Detected sale_type: outright")
    
    elif 'bank financing' in query_lower or 'bank loan' in query_lower or 'mortgage' in query_lower:
        entities['sale_type'] = 'bank_financing'
        entities['financing_type'] = 'bank_financing'
        logger.info(f"💰 Detected sale_type: bank_financing")
    
    # ========== NEW: Detect specific financing options ==========
    # Check for specific banks in financingOptions array
    if 'bdo' in query_lower:
        entities['financing_options'] = 'BDO'
        entities['financing_type'] = 'bank_financing'
        logger.info(f"🏦 Detected financing_option: BDO")
    elif 'metrobank' in query_lower:
        entities['financing_options'] = 'Metrobank'
        entities['financing_type'] = 'bank_financing'
        logger.info(f"🏦 Detected financing_option: Metrobank")
    elif 'unionbank' in query_lower or 'union bank' in query_lower:
        entities['financing_options'] = 'UnionBank'
        entities['financing_type'] = 'bank_financing'
        logger.info(f"🏦 Detected financing_option: UnionBank")
    elif 'rcbc' in query_lower:
        entities['financing_options'] = 'RCBC'
        entities['financing_type'] = 'bank_financing'
        logger.info(f"🏦 Detected financing_option: RCBC")
    elif 'pag-ibig' in query_lower or 'pagibig' in query_lower:
        entities['financing_options'] = 'Pag-IBIG'
        entities['financing_type'] = 'pag_ibig'
        logger.info(f"🏦 Detected financing_option: Pag-IBIG")
    elif 'housing loan' in query_lower:
        entities['financing_options'] = 'Housing Loan'
        entities['financing_type'] = 'housing_loan'
        logger.info(f"🏦 Detected financing_option: Housing Loan")
    
    # ========== Property type detection ==========
    property_type_map = {
        'apartment': 'apartment',
        'apartments': 'apartment',
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
    
    # ========== Location detection ==========
    batangas_locations = {
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
        if location_key in query_lower:
            entities['location'] = location_value
            has_specific_location = True
            break
        elif re.search(r'\b' + re.escape(location_key) + r'\b', query_lower):
            entities['location'] = location_value
            has_specific_location = True
            break
    
    # ========== Feature detection ==========
    if 'with swimming pool' in query_lower or 'with pool' in query_lower:
        entities['feature'] = 'swimming pool'
    elif 'with garden' in query_lower:
        entities['feature'] = 'garden'
    elif 'with parking' in query_lower:
        entities['feature'] = 'parking'
    elif 'furnished' in query_lower:
        entities['feature'] = 'furnished'
    
    # ========== Landmark detection ==========
    if 'near' in query_lower or 'close to' in query_lower or 'around' in query_lower or 'beside' in query_lower:
        match = re.search(r'(?:near|close to|around|beside|next to)\s+(\w+\s*\w*)', query_lower)
        if match:
            entities['landmark'] = match.group(1).strip()
    
    # ========== Bathroom detection ==========
    bath_match = re.search(r'(\d+)\s+bathroom', query_lower)
    if bath_match:
        entities['bathrooms'] = int(bath_match.group(1))
    
    # ========== General search detection ==========
    if entities.get('property_type') and not has_specific_location:
        entities['has_general_search'] = True
        logger.info(f"🔍 Detected general search for {entities['property_type']} (no location specified)")
    
    logger.info(f"✅ Entities extracted: {entities}")
    return entities

# Add price numeric value
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

# Calculate installment payment details
def calculate_installment_payment(property_data: Dict) -> Optional[Dict]:
    """Calculate installment payment details for a property"""
    sale_price = property_data.get('salePrice')
    if not sale_price or sale_price <= 0:
        return None
    
    # Standard installment terms: 30% downpayment, 5 years term, 6% interest
    downpayment_percentage = 0.30  # 30% downpayment
    loan_term_years = 5  # 5 years
    annual_interest_rate = 0.06  # 6% per annum
    
    downpayment = sale_price * downpayment_percentage
    loan_amount = sale_price - downpayment
    
    # Calculate monthly payment using simple interest formula
    total_interest = loan_amount * annual_interest_rate * loan_term_years
    total_payment = loan_amount + total_interest
    monthly_payment = total_payment / (loan_term_years * 12)
    
    return {
        'downpayment': round(downpayment, 2),
        'loan_amount': round(loan_amount, 2),
        'monthly_payment': round(monthly_payment, 2),
        'interest_rate': f"{annual_interest_rate * 100}%",
        'term_years': loan_term_years,
        'total_payment': round(total_payment, 2)
    }

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
        'saleType': property_data.get('saleType', 'Not specified'),  # ADDED THIS
        'salePrice': property_data.get('salePrice', 0),  # ADDED THIS
        'price_numeric': property_data.get('price_numeric', 0)  # Add numeric price
    }
    
    # Add installment details if available
    if property_data.get('installment_details'):
        standardized['installment_details'] = property_data['installment_details']
    
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
            'saleType': 'installment',  # ADDED: This is an installment property
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
            'saleType': 'bank_financing',  # ADDED: This uses bank financing
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
            'financingOptions': ['Bank Financing - Metrobank', 'Outright Payment']
        },
        {
            'id': 'mock_6',  # ADDED: Another installment property
            'title': 'Family House in Lipa',
            'propertyType': 'house',
            'type': 'sale',
            'saleType': 'installment',
            'city': 'Lipa City',
            'province': 'Batangas',
            'address': '303 Family Subdivision, Lipa',
            'salePrice': 4500000,
            'bedrooms': '4',
            'bathrooms': '3',
            'floorArea': 150,
            'description': 'Spacious family house with installment payment option',
            'imageUrls': [],
            'status': 'available',
            'financingOptions': ['In-house Installment Plan', 'Bank Financing - UnionBank']
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
        
        # Filter by sale type (installment, bank_financing, outright)
        if entities.get('sale_type') and matches:
            prop_type = prop.get('type', '')
            prop_sale_type = prop.get('saleType', '')
            
            # Only check sale_type for sale properties
            if prop_type == 'sale':
                if prop_sale_type != entities['sale_type']:
                    matches = False
            else:
                # Not a sale property, can't have sale_type
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
            
            # Add installment calculation if it's an installment property
            if entities.get('sale_type') == 'installment' and prop.get('type') == 'sale':
                installment_details = calculate_installment_payment(prop_with_price)
                if installment_details:
                    prop_with_price['installment_details'] = installment_details
            
            mock_properties.append(standardize_property_data(prop_with_price))
    
    return mock_properties

# Firestore queries - UPDATED WITH PROPER saleType FILTERING
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
        
        logger.info("🔍 Status filtering will be done client-side")
        
        # ========== CRITICAL FIX: FILTER BY SALE TYPE ==========
        sale_type = entities.get('sale_type')
        logger.info(f"🔍 Looking for sale_type: {sale_type}")
        
        if sale_type:
            # First filter by type: sale
            try:
                query = query.where(filter=FieldFilter('type', '==', 'sale'))
                logger.info("✅ Filtered by type: sale")
                
                # Then filter by saleType (installment, bank_financing, outright)
                query = query.where(filter=FieldFilter('saleType', '==', sale_type))
                logger.info(f"✅ Filtered by saleType: {sale_type}")
            except Exception as e:
                logger.warning(f"⚠️ Could not filter by saleType: {e}")
                # We'll filter client-side
        else:
            logger.info("🔍 No sale_type specified in query")
        
        # ========== FILTER BY SPECIFIC FINANCING OPTIONS ==========
        if entities.get('financing_options') and not sale_type:
            # If user asked for specific bank financing but not a specific sale_type
            financing_option = entities['financing_options']
            logger.info(f"🔍 Looking for {financing_option} financing...")
            
            # Map query terms to possible database values
            financing_map = {
                'BDO': ['BDO', 'Bank Financing - BDO', 'BDO Bank'],
                'Metrobank': ['Metrobank', 'Bank Financing - Metrobank', 'Metrobank Bank'],
                'UnionBank': ['UnionBank', 'Bank Financing - UnionBank', 'Union Bank'],
                'RCBC': ['RCBC', 'Bank Financing - RCBC', 'RCBC Bank'],
                'Pag-IBIG': ['Pag-IBIG', 'Pag-IBIG Housing Loan', 'Pag-IBIG Loan', 'Pagibig'],
                'Housing Loan': ['Housing Loan', 'Home Loan', 'Property Loan']
            }
            
            if financing_option in financing_map:
                search_terms = financing_map[financing_option]
                logger.info(f"🔍 Search terms for {financing_option}: {search_terms}")
                
                # Try each search term
                for term in search_terms:
                    try:
                        # Use array_contains to search in financingOptions array
                        temp_query = query.where(filter=FieldFilter('financingOptions', 'array_contains', term))
                        test_docs = list(temp_query.limit(1).get())
                        if test_docs:
                            query = temp_query
                            logger.info(f"✅ Found properties with financing term: {term}")
                            break
                    except Exception as e:
                        logger.debug(f"⚠️ Could not search for {term}: {e}")
                        continue
        
        # ========== FILTER BY LOCATION ==========
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
            if entities.get('has_general_search'):
                logger.info(f"🔍 General search for {entities.get('property_type', 'properties')} (no location filter)")
            else:
                logger.info("🔍 No location specified - showing properties from all locations")
        
        # ========== FILTER BY PROPERTY TYPE ==========
        if entities.get('property_type'):
            property_type = entities['property_type']
            
            type_map = {
                'apartment': 'apartment',
                'apartments': 'apartment',
                'condo': 'condo_unit',
                'condos': 'condo_unit',
                'condominium': 'condo_unit',
                'condominiums': 'condo_unit',
                'house': 'house',
                'houses': 'house',
                'townhouse': 'townhouse',
                'townhouses': 'townhouse',
                'commercial': 'commercial_building',
                'commercial_space': 'commercial_building',
                'office': 'office_unit',
                'retail': 'retail_space',
                'warehouse': 'warehouse',
                'industrial': 'warehouse',
                'land': 'residential_lot',
                'lot': 'residential_lot',
                'residential_lot': 'residential_lot',
                'commercial_lot': 'commercial_lot',
                'agricultural': 'agricultural_land',
                'agricultural_land': 'agricultural_land',
                'beachfront': 'beachfront',
                'resort': 'resort_property',
                'resort_property': 'resort_property',
                'commercial_building': 'commercial_building',
                'office_unit': 'office_unit',
                'retail_space': 'retail_space'
            }
            
            mapped_type = type_map.get(property_type, property_type)
            try:
                query = query.where(filter=FieldFilter('propertyType', '==', mapped_type))
                logger.info(f"🔍 Filtering by property type: {mapped_type}")
            except Exception as e:
                logger.warning(f"⚠️ Could not filter by property type {mapped_type}: {e}")
        
        # ========== APPLY PRICE FILTERS ==========
        if entities.get('max_price'):
            max_price = entities['max_price']
            logger.info(f"💰 Applying max price filter: ₱{max_price:,.0f}")
            
            # Try different price fields
            price_fields = ['salePrice', 'monthlyRent', 'annualRent']
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
        
        # ========== EXECUTE QUERY ==========
        limit_count = 20
        logger.info(f"🔍 Executing Firestore query (limit: {limit_count})...")
        docs = query.limit(limit_count).get()
        
        property_data_list = []
        status_counts = {}
        
        for doc in docs:
            property_data = doc.to_dict()
            property_data['id'] = doc.id
            property_data_list.append(property_data)
            
            status = property_data.get('status', 'NO STATUS')
            status_counts[status] = status_counts.get(status, 0) + 1
        
        logger.info(f"🔍 Found {len(property_data_list)} properties from Firestore")
        logger.info(f"🔍 Status breakdown: {status_counts}")
        
        # ========== CLIENT-SIDE FILTERING ==========
        filtered_properties = []
        
        for property_data in property_data_list:
            matches = True
            
            # Filter by status
            status = str(property_data.get('status', '')).lower()
            valid_statuses = ['available', 'active', 'for rent', 'for sale', 'for lease', 'listed']
            if status not in valid_statuses:
                logger.debug(f"❌ Property {property_data.get('id', 'unknown')} excluded - status: {status}")
                matches = False
                continue
            
            # For sale_type queries, verify the saleType matches
            if sale_type and matches:
                prop_type = property_data.get('type', property_data.get('listingType', ''))
                prop_sale_type = property_data.get('saleType', '').lower()
                
                if prop_type != 'sale' or prop_sale_type != sale_type:
                    logger.debug(f"❌ Sale type mismatch: {prop_type}/{prop_sale_type} != sale/{sale_type}")
                    matches = False
            
            # Check financing options for specific bank queries
            if entities.get('financing_options') and matches:
                financing_options = property_data.get('financingOptions', [])
                search_term = entities['financing_options'].lower()
                
                has_financing = False
                for option in financing_options:
                    if isinstance(option, str) and search_term in option.lower():
                        has_financing = True
                        break
                
                if not has_financing and sale_type != 'installment':  # For installment, we already checked saleType
                    matches = False
                    logger.debug(f"❌ No {entities['financing_options']} financing found: {financing_options}")
            
            if not matches:
                continue
            
            # Add numeric price value
            property_data_with_price = add_price_numeric_value(property_data)
            
            # Apply price filter client-side if not applied in query
            if entities.get('max_price') and matches:
                price_numeric = property_data_with_price.get('price_numeric', 0)
                if price_numeric > entities['max_price']:
                    matches = False
                    logger.debug(f"❌ Price too high: {price_numeric} > {entities['max_price']}")
            
            # Apply min price filter client-side
            if entities.get('min_price') and matches:
                price_numeric = property_data_with_price.get('price_numeric', 0)
                if price_numeric < entities['min_price']:
                    matches = False
                    logger.debug(f"❌ Price too low: {price_numeric} < {entities['min_price']}")
            
            # Apply bedroom filter client-side
            if entities.get('exact_bedrooms') is not None and matches:
                prop_bedrooms = property_data.get('bedrooms', 'Not specified')
                try:
                    if isinstance(prop_bedrooms, str):
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
                        logger.debug(f"❌ Bedroom mismatch: {prop_bed_num} != {entities['exact_bedrooms']}")
                except Exception as e:
                    logger.debug(f"⚠️ Could not parse bedrooms: {e}")
            
            if matches:
                # Calculate installment details if needed
                if sale_type == 'installment':
                    installment_details = calculate_installment_payment(property_data_with_price)
                    if installment_details:
                        property_data_with_price['installment_details'] = installment_details
                
                standardized_property = standardize_property_data(property_data_with_price)
                filtered_properties.append(standardized_property)
        
        properties = filtered_properties
        logger.info(f"🔍 After client-side filtering: {len(properties)} properties")
        
        # ========== SMART FALLBACK FOR NO RESULTS ==========
        if len(properties) == 0 and sale_type:
            logger.info("🔄 No exact matches found, trying fallback search...")
            
            # Try to find sale properties that might accept the requested sale type
            fallback_query = properties_ref.where(filter=FieldFilter('type', '==', 'sale'))
            
            if entities.get('location'):
                location = entities['location']
                location_map = {
                    'Batangas City': 'Batangas City',
                    'Lipa City': 'Lipa City',
                    'Nasugbu': 'Nasugbu',
                    'Sto. Tomas City': 'Sto. Tomas City',
                }
                if location in location_map:
                    fallback_query = fallback_query.where(filter=FieldFilter('city', '==', location_map[location]))
            
            fallback_docs = fallback_query.limit(10).get()
            
            for doc in fallback_docs:
                property_data = doc.to_dict()
                property_data['id'] = doc.id
                
                # Check if property has the requested sale type
                prop_sale_type = property_data.get('saleType', '').lower()
                if prop_sale_type == sale_type:
                    property_data_with_price = add_price_numeric_value(property_data)
                    
                    # Calculate installment details if needed
                    if sale_type == 'installment':
                        installment_details = calculate_installment_payment(property_data_with_price)
                        if installment_details:
                            property_data_with_price['installment_details'] = installment_details
                    
                    standardized_property = standardize_property_data(property_data_with_price)
                    properties.append(standardized_property)
            
            logger.info(f"🔄 Found {len(properties)} properties in fallback search")
        
        # ========== DEDUPLICATION ==========
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
        
        properties = get_mock_properties(entities)
    
    return properties

# Generate response for financing queries
def generate_financing_response(entities: Dict[str, Any], properties: List[Dict[str, Any]]) -> str:
    """Generate response for financing-related queries"""
    
    sale_type = entities.get('sale_type')
    financing_option = entities.get('financing_options')
    
    if sale_type == 'installment':
        if properties:
            response = f"🏦 **Properties Available for Installment Purchase**\n\n"
            response += f"I found {len(properties)} properties that can be purchased via installment:\n\n"
            
            for i, prop in enumerate(properties[:5]):
                title = prop.get('title', f'Property {i+1}')
                price = prop.get('price', 'Price not available')
                location = prop.get('location', 'Location not specified')
                
                response += f"{i+1}. **{title}** in {location}\n"
                response += f"   💰 Sale Price: {price}\n"
                
                # Add installment details if available
                installment_details = prop.get('installment_details')
                if installment_details:
                    response += f"   📊 **Installment Estimate:**\n"
                    response += f"      • Downpayment: ₱{installment_details['downpayment']:,.0f} (30%)\n"
                    response += f"      • Monthly: ₱{installment_details['monthly_payment']:,.0f} for 5 years\n"
                    response += f"      • Interest Rate: {installment_details['interest_rate']}\n"
                
                financing_options = prop.get('financingOptions', [])
                if financing_options:
                    response += f"   🏦 **Financing Options:** {', '.join(financing_options[:3])}\n"
                
                response += "\n"
            
            response += "\n**📝 Installment Purchase Process:**\n"
            response += "1. Submit reservation with downpayment (usually 20-30%)\n"
            response += "2. Sign Contract to Sell\n"
            response += "3. Submit required documents\n"
            response += "4. Issue post-dated checks for monthly payments\n"
            response += "5. Receive property title upon full payment\n\n"
            
            response += "**📋 Required Documents:**\n"
            response += "• Valid ID (passport, driver's license)\n"
            response += "• Proof of Income (3 months payslips)\n"
            response += "• Certificate of Employment\n"
            response += "• Post-dated checks\n"
            response += "• 2x2 ID pictures\n"
            
        else:
            response = "❌ **No installment properties found**\n\n"
            response += "💡 **Try these alternatives:**\n"
            response += "• Check properties with **bank financing**\n"
            response += "• Look at **outright cash** properties\n"
            response += "• Ask about **developer in-house financing**\n"
            response += "• Consider **Pag-IBIG housing loans**\n\n"
            response += "You can also try:\n"
            response += "• *'show me properties with bank financing'*\n"
            response += "• *'find houses for outright purchase'*\n"
            response += "• *'properties with Pag-IBIG financing'*\n"
        
        return response
    
    elif sale_type == 'bank_financing':
        if properties:
            response = f"🏦 **Properties with Bank Financing**\n\n"
            response += f"I found {len(properties)} properties that accept bank financing:\n\n"
            
            for i, prop in enumerate(properties[:5]):
                title = prop.get('title', f'Property {i+1}')
                price = prop.get('price', 'Price not available')
                location = prop.get('location', 'Location not specified')
                
                response += f"{i+1}. **{title}** in {location}\n"
                response += f"   💰 Sale Price: {price}\n"
                
                financing_options = prop.get('financingOptions', [])
                if financing_options:
                    response += f"   🏦 **Bank Options:** {', '.join(financing_options[:3])}\n"
                
                response += "\n"
            
            response += "\n**🏦 Popular Banks for Property Financing:**\n"
            response += "• **BDO** - (02) 8631-8000 | www.bdo.com.ph\n"
            response += "• **Metrobank** - (02) 8888-7000 | www.metrobank.com.ph\n"
            response += "• **UnionBank** - (02) 8841-8600 | www.unionbankph.com\n"
            response += "• **RCBC** - (02) 8557-9515 | www.rcbc.com\n\n"
            
            response += "**📋 Common Requirements for Bank Financing:**\n"
            response += "1. Valid ID\n"
            response += "2. Proof of Income (3-6 months)\n"
            response += "3. Certificate of Employment\n"
            response += "4. ITR (Income Tax Return)\n"
            response += "5. Bank Statements\n"
            response += "6. Property Documents\n"
            
        else:
            response = "❌ **No properties found with bank financing**\n\n"
            response += "💡 **Try searching for sale properties first:**\n"
            response += "• *'find houses for sale in Batangas City'*\n"
            response += "• *'show me condos for sale'*\n"
            response += "• *'properties for sale with financing options'*\n"
        
        return response
    
    elif sale_type == 'outright':
        if properties:
            response = f"💰 **Properties for Outright Purchase (Cash)**\n\n"
            response += f"I found {len(properties)} properties available for outright cash purchase:\n\n"
            
            for i, prop in enumerate(properties[:5]):
                title = prop.get('title', f'Property {i+1}')
                price = prop.get('price', 'Price not available')
                location = prop.get('location', 'Location not specified')
                
                response += f"{i+1}. **{title}** in {location}\n"
                response += f"   💰 Sale Price: {price}\n"
                response += f"   📋 Payment: Cash/Outright\n\n"
            
            response += "\n**💰 Benefits of Outright Purchase:**\n"
            response += "• No interest payments\n"
            response += "• Faster transaction process\n"
            response += "• Potential for price negotiation\n"
            response += "• Immediate property transfer\n"
            
        else:
            response = "❌ **No properties found for outright purchase**\n\n"
            response += "💡 **Most properties accept multiple payment options. Try:**\n"
            response += "• *'show me properties for sale'*\n"
            response += "• *'find houses with different payment options'*\n"
            response += "• *'what payment methods do you accept'*\n"
        
        return response
    
    elif financing_option:
        # Specific financing option like BDO, Pag-IBIG, etc.
        if properties:
            response = f"🏦 **Properties with {financing_option} Financing**\n\n"
            response += f"I found {len(properties)} properties that accept {financing_option}:\n\n"
            
            for i, prop in enumerate(properties[:5]):
                title = prop.get('title', f'Property {i+1}')
                price = prop.get('price', 'Price not available')
                location = prop.get('location', 'Location not specified')
                
                response += f"{i+1}. **{title}** in {location}\n"
                response += f"   💰 Price: {price}\n"
                
                financing_options = prop.get('financingOptions', [])
                if financing_options:
                    response += f"   🏦 **Available Options:** {', '.join(financing_options[:3])}\n"
                
                response += "\n"
            
            # Add specific information for each financing option
            if 'BDO' in financing_option:
                response += "\n**🏦 BDO Home Loan Features:**\n"
                response += "• Loan Amount: Up to 80% of property value\n"
                response += "• Term: Up to 25 years\n"
                response += "• Interest Rate: Competitive rates\n"
                response += "• Contact: (02) 8631-8000\n"
                
            elif 'Pag-IBIG' in financing_option:
                response += "\n**🏦 Pag-IBIG Housing Loan:**\n"
                response += "• Membership: At least 24 months\n"
                response += "• Maximum Loan: ₱6M\n"
                response += "• Term: Up to 30 years\n"
                response += "• Interest: As low as 3% per annum\n"
                response += "• Hotline: (02) 8724-4244\n"
            
        else:
            response = f"❌ **No properties found with {financing_option} financing**\n\n"
            response += "💡 **Try these suggestions:**\n"
            response += f"• Ask about other banks or financing options\n"
            response += "• Check if properties accept multiple financing options\n"
            response += "• Look for sale properties and inquire about financing\n"
        
        return response
    
    else:
        # General financing information
        response = "🏦 **Financing Options for Property Purchase**\n\n"
        response += "We offer various financing options for property purchases:\n\n"
        response += "**1. Installment Plans**\n"
        response += "   • Developer in-house financing\n"
        response += "   • Flexible payment terms\n"
        response += "   • Usually 20-30% downpayment\n\n"
        
        response += "**2. Bank Financing**\n"
        response += "   • **BDO** - (02) 8631-8000\n"
        response += "   • **Metrobank** - (02) 8888-7000\n"
        response += "   • **UnionBank** - (02) 8841-8600\n"
        response += "   • **RCBC** - (02) 8557-9515\n\n"
        
        response += "**3. Pag-IBIG Housing Loan**\n"
        response += "   • For members with 24+ months contributions\n"
        response += "   • Up to ₱6M loan amount\n"
        response += "   • As low as 3% interest\n"
        response += "   • Hotline: (02) 8724-4244\n\n"
        
        response += "**4. Outright/Cash Purchase**\n"
        response += "   • No interest payments\n"
        response += "   • Faster transaction\n"
        response += "   • Potential discounts\n\n"
        
        response += "💡 **To see properties with specific financing, try:**\n"
        response += "• *'show me properties that accept installment'*\n"
        response += "• *'find houses with bank financing'*\n"
        response += "• *'properties with Pag-IBIG loan'*\n"
        response += "• *'outright purchase properties'*\n"
        
        return response

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

# Generate response from training data templates - UPDATED FOR FINANCING
def generate_response(intent: str, entities: Dict[str, Any], properties: List[Dict[str, Any]]) -> str:
    """Generate response based on intent and entities using training data templates"""

    # Handle financing intents specifically
    if intent == 'financing':
        return generate_financing_response(entities, properties)
    
    # Handle criteria-based searches
    if intent == 'find_property_with_criteria':
        return generate_criteria_search_response(entities, properties)
    
    # Handle general property searches (no location)
    if intent == 'find_property' and entities.get('has_general_search'):
        return generate_general_search_response(entities, properties)
    
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
    
    return response

# Generate response for general searches (no location)
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
                     "find_property_with_criteria", "match_needs", "financing"]:  # ADDED financing here
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
            'properties': properties[:10],
            'model_version': 'trained' if vectorizer else 'fallback',
            'is_general_search': entities.get('has_general_search', False),
            'is_criteria_search': intent == 'find_property_with_criteria',
            'is_financing_query': intent == 'financing'  # ADDED: Flag for financing queries
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
    
    # Check for financing-related queries
    financing_keywords = [
        'installment', 'bank financing', 'mortgage', 'loan',
        'financing', 'payment plan', 'pag-ibig', 'bdo',
        'metrobank', 'unionbank', 'rcbc', 'housing loan',
        'accept bank', 'accept installment', 'outright', 'cash'
    ]
    
    for keyword in financing_keywords:
        if keyword in query_lower:
            return 'financing'
    
    # Check for property searches
    if any(term in query_lower for term in ['find', 'search', 'looking for', 'show me', 'need', 'want']):
        return 'find_property'
    
    # Check for location info
    if any(term in query_lower for term in ['tell me about', 'information about', 'describe', 'about']):
        return 'location_info'
    
    return 'unknown'

@app.route('/api/health', methods=['GET'])
def health_check():
    """Health check endpoint"""
    return jsonify({
        'status': 'healthy',
        'service': 'Bah.AI Property Chatbot',
        'version': '3.6.1',  # Updated version with financing fixes
        'model_loaded': vectorizer is not None and classifier is not None,
        'training_data_loaded': bool(training_data),
        'firebase_connected': db is not None,
        'model_intents': model_classes,
        'model_features': len(vectorizer.get_feature_names_out()) if vectorizer else 0,
        'spacy_loaded': nlp is not None,
        'supports_general_searches': True,
        'supports_criteria_searches': True,
        'supports_financing_queries': True,  # NEW
        'timestamp': datetime.now().isoformat()
    })

@app.route('/api/test', methods=['GET'])
def test_endpoint():
    """Test endpoint to verify the model is working"""
    test_queries = [
        # Financing queries
        "show me properties that accept installment",
        "find properties with bank financing",
        "properties that accept outright payment",
        "houses with BDO financing",
        "condos with Pag-IBIG loan",
        
        # Criteria-based searches
        "show me houses under 15M with 3 bedrooms",
        "find condos below 10M with 2 bedrooms",
        
        # General searches (no location)
        "find apartments",
        "show me houses",
        
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
                    'sale_type': entities.get('sale_type'),
                    'financing_options': entities.get('financing_options'),
                    'has_location': entities.get('location') is not None,
                    'property_type': entities.get('property_type'),
                    'max_price': entities.get('max_price'),
                    'exact_bedrooms': entities.get('exact_bedrooms'),
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
        'supports_financing_queries': True
    })

# ==================== MAIN ====================
if __name__ == '__main__':
    print("\n" + "="*60)
    print("🚀 BAH.AI PROPERTY CHATBOT BACKEND v3.6.1")
    print("   (With saleType filtering for financing queries)")
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
    print(f"🏦 Financing Queries: {'✅ Supported (installment, bank_financing, outright)'}")
    
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
    print("   • 'show me properties that accept installment'")
    print("   • 'find properties with bank financing'")
    print("   • 'properties that accept outright payment'")
    print("   • 'show me houses under 15M with 3 bedrooms'")
    print("   • 'find apartments in batangas city'")
    
    print("="*60 + "\n")
    
    app.run(host='0.0.0.0', port=5000, debug=True)