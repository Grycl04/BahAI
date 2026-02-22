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
import hashlib
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
BACKEND_ROOT = os.path.dirname(os.path.abspath(__file__))
PROJECT_ROOT = os.path.dirname(BACKEND_ROOT)
MODEL_PATH = os.path.join(BACKEND_ROOT, 'models', 'nlu_model.pkl')

# Runtime data paths: prefer backend/data (Render-friendly), fallback to training/data
RUNTIME_DATA_ROOT = os.path.join(BACKEND_ROOT, 'data')
LEGACY_DATA_ROOT = os.path.join(PROJECT_ROOT, 'training', 'data')

def _resolve_data_path(*parts: str) -> str:
    """Return backend/data path when available, otherwise fallback to training/data."""
    runtime_path = os.path.join(RUNTIME_DATA_ROOT, *parts)
    if os.path.exists(runtime_path):
        return runtime_path
    return os.path.join(LEGACY_DATA_ROOT, *parts)

TRAINING_DATA_PATH = _resolve_data_path('member1', 'training_data.json')
BUYER_TRAINING_DATA_PATH = _resolve_data_path('member5_buyer', 'training_data.json')
MEMBER2_TRAINING_DATA_PATH = _resolve_data_path('member2', 'training_data.json')
MEMBER3_TRAINING_DATA_PATH = _resolve_data_path('member3', 'training_data.json')
MEMBER4_GENERAL_PATHS = [
    _resolve_data_path('member4_general', 'greetings.json'),
    _resolve_data_path('member4_general', 'thanks.json'),
    _resolve_data_path('member4_general', 'goodbye.json'),
    _resolve_data_path('member4_general', 'about_system.json'),
]

# Global variables
vectorizer = None
classifier = None
db = None
nlp = None
model_classes = []  # Store model classes separately
training_data = {}  # Store training data for response templates
buyer_training_data = {}  # Buyer intents from member5_buyer
intent_templates = {}  # intent -> {'en': template, 'tl': template}

print("\n" + "="*60)
print("🔥 FIREBASE CONNECTION")
print("="*60)
print("MODEL PATH:", MODEL_PATH)
print("MODEL EXISTS:", os.path.exists(MODEL_PATH))

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
                        financing_bank = data.get('financingBank', 'No bank')
                        print(f"   {i+1}. ID: {doc_id[:10]}..., Type: {prop_type}, City: {city}, Status: {status}, SaleType: {sale_type}, Bank: {financing_bank}")
                        
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
def _register_intent_template(intent_name: str, en_template: str = "", tl_template: str = ""):
    """Store one EN/TL template per intent for language-aware responses."""
    if not intent_name:
        return
    if intent_name not in intent_templates:
        intent_templates[intent_name] = {'en': '', 'tl': ''}
    if en_template and not intent_templates[intent_name]['en']:
        intent_templates[intent_name]['en'] = en_template
    if tl_template and not intent_templates[intent_name]['tl']:
        intent_templates[intent_name]['tl'] = tl_template


def _collect_intent_templates(dataset: Dict[str, Any]):
    """Extract templates from dataset-level and sample-level template fields."""
    if not dataset:
        return

    # 1) Sample-level templates
    for sample in dataset.get('training_samples', []):
        intent_name = sample.get('intent')
        en = sample.get('response_template_english') or sample.get('response_template') or ''
        tl = sample.get('response_template_tagalog') or ''
        _register_intent_template(intent_name, en, tl)

    # 2) Dataset-level bilingual template maps
    en_map = dataset.get('response_templates_english', {})
    tl_map = dataset.get('response_templates_tagalog', {})
    legacy_map = dataset.get('response_templates', {})

    for intent_name, template in en_map.items():
        _register_intent_template(intent_name, template, '')
    for intent_name, template in tl_map.items():
        _register_intent_template(intent_name, '', template)
    for intent_name, template in legacy_map.items():
        _register_intent_template(intent_name, template, '')


def load_training_data():
    """Load training data for response templates"""
    global training_data, intent_templates
    intent_templates = {}
    
    print(f"\n🔍 DEBUG: Loading training data from {TRAINING_DATA_PATH}")
    print(f"📁 TRAINING_DATA_PATH exists: {os.path.exists(TRAINING_DATA_PATH)}")
    
    try:
        if os.path.exists(TRAINING_DATA_PATH):
            with open(TRAINING_DATA_PATH, 'r', encoding='utf-8') as f:
                training_data = json.load(f)
            logger.info(f"✅ Training data loaded from {TRAINING_DATA_PATH}")
            _collect_intent_templates(training_data)
            
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

    # Load additional member datasets to unify EN/TL intent templates
    for member_path in [MEMBER2_TRAINING_DATA_PATH, MEMBER3_TRAINING_DATA_PATH]:
        try:
            if os.path.exists(member_path):
                with open(member_path, 'r', encoding='utf-8') as f:
                    member_data = json.load(f)
                _collect_intent_templates(member_data)
                logger.info(f"✅ Additional templates loaded from {member_path}")
        except Exception as e:
            logger.warning(f"⚠️ Could not load templates from {member_path}: {e}")

    for member4_path in MEMBER4_GENERAL_PATHS:
        try:
            if os.path.exists(member4_path):
                with open(member4_path, 'r', encoding='utf-8') as f:
                    member4_data = json.load(f)
                _collect_intent_templates(member4_data)
                logger.info(f"✅ Member4 general templates loaded from {member4_path}")
        except Exception as e:
            logger.warning(f"⚠️ Could not load templates from {member4_path}: {e}")

    # Load buyer training data from member5_buyer for buyer intents
    global buyer_training_data
    try:
        if os.path.exists(BUYER_TRAINING_DATA_PATH):
            with open(BUYER_TRAINING_DATA_PATH, 'r', encoding='utf-8') as f:
                buyer_training_data = json.load(f)
            logger.info(f"✅ Buyer training data loaded from {BUYER_TRAINING_DATA_PATH}")
        else:
            logger.warning(f"⚠️ Buyer training data file not found: {BUYER_TRAINING_DATA_PATH}")
            buyer_training_data = {}
    except Exception as e:
        logger.error(f"❌ Error loading buyer training data: {e}")
        buyer_training_data = {}

# Load NLU model
# Load NLU model - COMPLETE FIXED VERSION with multiple fallback paths and diagnostics
def load_nlu_model():
    """Load the trained NLU model from train_nlu.py with multiple fallback paths"""
    global vectorizer, classifier, model_classes
    
    # Prefer backend-local model for Render/backend-only deployments.
    # Keep fallbacks for local compatibility.
    possible_paths = [
        MODEL_PATH,  # backend/models/nlu_model.pkl
        os.path.join(BACKEND_ROOT, 'models', 'nlu_model.pkl'),
        os.path.join(PROJECT_ROOT, 'backend', 'models', 'nlu_model.pkl'),
        os.path.join(PROJECT_ROOT, 'models', 'nlu_model.pkl'),
        os.path.join(os.path.dirname(PROJECT_ROOT), 'models', 'nlu_model.pkl'),
    ]
    
    model_loaded = False
    
    for model_path in possible_paths:
        if os.path.exists(model_path):
            try:
                logger.info(f"📂 Attempting to load model from: {model_path}")
                with open(model_path, 'rb') as f:
                    model_data = pickle.load(f)
                
                # Try different possible key names
                vectorizer = model_data.get('vectorizer') or model_data.get('tfidf') or model_data.get('vectorizer_obj') or None
                classifier = model_data.get('classifier') or model_data.get('model') or model_data.get('clf') or None
                
                # CRITICAL: Test if vectorizer is actually fitted
                if vectorizer:
                    try:
                        # Test with a simple query
                        test_result = vectorizer.transform(["test query"])
                        logger.info(f"✅ Vectorizer is fitted and working from: {model_path}")
                        
                        # Get feature count
                        try:
                            feature_count = len(vectorizer.get_feature_names_out())
                            logger.info(f"📊 Feature count: {feature_count}")
                        except:
                            pass
                        
                        # Check classifier
                        if classifier and hasattr(classifier, 'classes_'):
                            model_classes = classifier.classes_.tolist()
                            logger.info(f"✅ Classifier loaded with {len(model_classes)} intents")
                            logger.info(f"📊 Model intents: {model_classes}")
                            model_loaded = True
                            break  # Success! Exit the loop
                        else:
                            logger.warning("⚠️ Classifier missing or incomplete, trying next path...")
                            vectorizer = None
                            classifier = None
                            continue
                        
                    except Exception as e:
                        logger.error(f"❌ Vectorizer at {model_path} is NOT fitted: {e}")
                        logger.error("   This indicates the model file is corrupted or saved incorrectly")
                        vectorizer = None
                        classifier = None
                        continue  # Try next path
                else:
                    logger.warning(f"⚠️ No vectorizer found in model file at {model_path}")
                    continue
                    
            except Exception as e:
                logger.error(f"❌ Error loading model from {model_path}: {e}")
                continue
    
    if not model_loaded:
        logger.error("❌ Could not load a valid NLU model from any path!")
        logger.error("💡 Will use fallback intent detection")
        logger.error("📍 Checked paths:")
        for path in possible_paths:
            status = "✅ Exists" if os.path.exists(path) else "❌ Not found"
            logger.error(f"   • {path} - {status}")
        
        # Reset global variables
        vectorizer = None
        classifier = None
        model_classes = []
        
        # Try to load a minimal fallback model if needed
        logger.info("🔄 Attempting to create minimal fallback vectorizer...")
        try:
            from sklearn.feature_extraction.text import TfidfVectorizer
            from sklearn.svm import SVC
            import numpy as np
            
            # Create a minimal fallback model with basic intents
            fallback_texts = [
                "find apartments", "find houses", "find condos",
                "tell me about batangas", "what is lipa city like",
                "properties with bank financing", "how to get a loan"
            ]
            fallback_intents = [
                "find_property", "find_property", "find_property",
                "location_info", "location_info",
                "financing", "process_info"
            ]
            
            # Create and fit a minimal vectorizer
            fallback_vectorizer = TfidfVectorizer(max_features=100)
            fallback_vectorizer.fit(fallback_texts)
            
            # Transform and train a minimal classifier
            X = fallback_vectorizer.transform(fallback_texts)
            fallback_classifier = SVC(kernel='linear', probability=True)
            fallback_classifier.fit(X, fallback_intents)
            
            vectorizer = fallback_vectorizer
            classifier = fallback_classifier
            model_classes = fallback_classifier.classes_.tolist()
            
            logger.info(f"✅ Created fallback model with {len(model_classes)} intents")
            logger.warning("⚠️ This is a minimal fallback - accuracy will be limited")
            
        except Exception as fallback_error:
            logger.error(f"❌ Could not create fallback model: {fallback_error}")
def verify_model_file():
    """Verify which model file is actually being loaded"""
    model_paths = [
        os.path.join(PROJECT_ROOT, 'models', 'nlu_model.pkl'),
        os.path.join(PROJECT_ROOT, 'training', 'models', 'nlu_model.pkl'),
        os.path.join(PROJECT_ROOT, 'backend', 'models', 'nlu_model.pkl'),
    ]
    
    print("\n" + "="*60)
    print("🔍 MODEL FILE VERIFICATION")
    print("="*60)
    
    for path in model_paths:
        if os.path.exists(path):
            size = os.path.getsize(path)
            with open(path, 'rb') as f:
                content = f.read()
                md5 = hashlib.md5(content).hexdigest()
            
            # Try to peek at the intents
            try:
                with open(path, 'rb') as f:
                    data = pickle.load(f)
                intents = data.get('classes', [])
                print(f"📁 {path}")
                print(f"   Size: {size:,} bytes")
                print(f"   MD5: {md5}")
                print(f"   Intents: {len(intents)} - {intents[:5]}...")
                print(f"   Date: {data.get('training_date', 'unknown')}")
                print()
            except Exception as e:
                print(f"❌ {path} - Error: {e}")
                print()
        else:
            print(f"❌ {path} - NOT FOUND")
    
    print("="*60 + "\n")

# Also add this emergency intent list right after load_nlu_model()
def ensure_all_intents():
    """Emergency fix: Ensure model_classes has all 15 intents"""
    global model_classes
    
    all_15_intents = [
        'about_system', 'financing', 'find_near_landmark', 'find_property',
        'find_property_for_need', 'find_property_with_criteria', 'find_ready_property',
        'find_with_feature', 'goodbye', 'greeting', 'help', 'location_info',
        'match_needs', 'process_info', 'thanks'
    ]
    
    if not model_classes or len(model_classes) < 15:
        print("\n" + "="*60)
        print("🚨 EMERGENCY: Model missing intents! Applying emergency fix...")
        print("="*60)
        
        # Keep existing intents if any, add missing ones
        if model_classes:
            existing_intents = set(model_classes)
            model_classes = all_15_intents
            print(f"✅ Preserved: {sorted(existing_intents)}")
            print(f"✅ Added: {sorted(set(all_15_intents) - existing_intents)}")
        else:
            model_classes = all_15_intents
            print(f"✅ Created fallback intent list with all 15 intents")
        
        print(f"📊 Total intents now: {len(model_classes)}")
        print("="*60 + "\n")

def diagnose_model_file():
    """Diagnose what's in the model file for debugging"""
    logger.info("🔍 Running model file diagnostics...")
    
    # Check if MODEL_PATH exists
    if os.path.exists(MODEL_PATH):
        logger.info(f"✅ Model file exists at: {MODEL_PATH}")
        file_size = os.path.getsize(MODEL_PATH)
        logger.info(f"📊 File size: {file_size} bytes")
        
        try:
            with open(MODEL_PATH, 'rb') as f:
                model_data = pickle.load(f)
            
            logger.info(f"📦 Model data keys: {list(model_data.keys())}")
            logger.info(f"📦 Model version: {model_data.get('version', 'unknown')}")
            
            # Check vectorizer
            vec = model_data.get('vectorizer')
            if vec:
                logger.info(f"📦 Vectorizer type: {type(vec)}")
                try:
                    vec.transform(["test"])
                    logger.info("✅ Vectorizer IS fitted!")
                    try:
                        logger.info(f"📊 Feature names: {len(vec.get_feature_names_out())}")
                    except:
                        pass
                except Exception as e:
                    logger.error(f"❌ Vectorizer is NOT fitted: {e}")
            else:
                logger.warning("⚠️ No vectorizer found in model file!")
            
            # Check classifier
            clf = model_data.get('classifier')
            if clf:
                logger.info(f"📦 Classifier type: {type(clf)}")
                if hasattr(clf, 'classes_'):
                    logger.info(f"📊 Classifier classes: {clf.classes_.tolist()}")
                else:
                    logger.warning("⚠️ Classifier has no classes_ attribute")
            else:
                logger.warning("⚠️ No classifier found in model file!")
                
        except Exception as e:
            logger.error(f"❌ Failed to read model file: {e}")
            import traceback
            logger.error(traceback.format_exc())
    else:
        logger.error(f"❌ Model file not found at: {MODEL_PATH}")
        
        # Check if directory exists
        model_dir = os.path.dirname(MODEL_PATH)
        if os.path.exists(model_dir):
            logger.info(f"✅ Model directory exists: {model_dir}")
            logger.info(f"📂 Contents: {os.listdir(model_dir)}")
        else:
            logger.error(f"❌ Model directory does not exist: {model_dir}")

# Preprocess text for prediction (same as training)
def preprocess_text(text):  # ✅ Removed 'self' parameter
    """Simple, reliable preprocessing"""
    if not text:
        return ""
    
    # Convert to lowercase
    text = str(text).lower()
    
    # Remove special characters but KEEP letters, numbers, spaces
    text = re.sub(r'[^a-z0-9\s]', ' ', text)
    
    # Remove extra spaces
    text = re.sub(r'\s+', ' ', text).strip()
    
    return text

# ========== ADD THIS RIGHT HERE - LANGUAGE DETECTION FUNCTION ==========
def detect_language(text):
    """Detect if query is Tagalog or English"""
    if not text:
        return 'en'
    
    text_lower = text.lower()
    
    # Tagalog common words and particles
    tagalog_indicators = [
        'ang', 'ng', 'sa', 'mga', 'ay', 'ito', 'ko', 'ako', 'mo', 'ka',
        'siya', 'tayo', 'kami', 'sila', 'namin', 'ninyo', 'nila',
        'paano', 'mag', 'po', 'opo', 'oo', 'hindi', 'wala', 'may',
        'gusto', 'kailangan', 'meron', 'pwede', 'pwedeng', 'ba', 'na',
        'pa', 'din', 'rin', 'kasi', 'dahil', 'kung', 'kapag', 'pag',
        'para', 'saan', 'kailan', 'bakit', 'sino', 'ano', 'ilan',
        'itong', 'iyan', 'iyon', 'dito', 'diyan', 'doon'
    ]
    
    # Count Tagalog indicators
    words = text_lower.split()
    tagalog_count = sum(1 for word in words if word in tagalog_indicators)
    
    # If we find Tagalog words, return 'tl' (Tagalog)
    if tagalog_count > 0:
        return 'tl'
    
    # Check for common Tagalog question patterns
    tagalog_patterns = [
        r'^paano', r'^saan', r'^kailan', r'^bakit', r'^ano', r'^sino',
        r'\s+ba\s+', r'\s+po\s+', r'\s+opo\s+', r'mag$', r'^mag'
    ]
    
    for pattern in tagalog_patterns:
        if re.search(pattern, text_lower):
            return 'tl'
    
    # Default to English
    return 'en'

# ========== SALE TYPE & SPECIFIC BANK DETECTION ==========
# Bank keywords mapping to official bank names (for filtering)
bank_keywords = {
    'bdo': 'BDO Unibank',
    'bdo unibank': 'BDO Unibank',
    'bpi': 'BPI',
    'bank of the philippine islands': 'BPI',
    'metrobank': 'Metrobank',
    'metro bank': 'Metrobank',
    'landbank': 'Land Bank of the Philippines',
    'land bank': 'Land Bank of the Philippines',
    'unionbank': 'UnionBank',
    'union bank': 'UnionBank',
    'security bank': 'Security Bank',
    'securitybank': 'Security Bank',
    'rcbc': 'RCBC',
    'pnb': 'PNB',
    'philippine national bank': 'PNB',
    'china bank': 'China Bank',
    'maybank': 'Maybank',
}

# Sale type keywords mapping to database values
sale_type_keywords = {
    # Bank financing category
    'bank financing': 'bank_financing',
    'bank loan': 'bank_financing',
    'bank mortgage': 'bank_financing',
    'housing loan': 'bank_financing',
    'home loan': 'bank_financing',
    'bank_financing': 'bank_financing',
    
    # Outright/Cash category
    'outright': 'outright',
    'cash': 'outright',
    'cash payment': 'outright',
    'full payment': 'outright',
    'straight cash': 'outright',
    
    # Installment category
    'installment': 'installment',
    'installment plan': 'installment',
    'in-house financing': 'installment',
    'developer financing': 'installment',
    'monthly payment': 'installment',
    'monthly amortization': 'installment',
}

# Entity extraction - UPDATED WITH FINANCING LEVELS AND QUERY TYPE DISTINCTION
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
        'sale_type': None,
        'bank_name': None,
        'financing_level': None,
        'query_type': None,
        'financing_info_request': False,
        'is_property_search_with_financing': False,
        'has_pagibig_query': False,
        'listing_type': None,
        'has_general_search': False,
        'has_ready_query': False,
        'max_price': None,
        'min_price': None,
        'min_bedrooms': None,
        'exact_bedrooms': None,
        # Member3 detection flags
        'has_need_query': False,
        'need_type': None,
        'family_size': None,
        'has_feature_price_query': False,
        'price_quality': None,
        'has_process_query': False,
        'process_type': None,
        'has_match_query': False,
        'lifestyle': None,
        'lifestyle_focus_landmark': None,
    }
    
    query_lower = query.lower()

    # Detect "ready to move in" style queries early
    ready_query_phrases = [
        'ready to move', 'ready for occupancy', 'available now',
        'immediate occupancy', 'move in ready', 'ready now',
        'ready to occupy', 'immediate move in', 'available immediately',
        'rfo', 'pwede na lipatan', 'handa na tirahan', 'lipat agad'
    ]
    if any(phrase in query_lower for phrase in ready_query_phrases):
        entities['has_ready_query'] = True
    
    # ========== PROPERTY TYPE DETECTION ==========
    # Check for condo variations FIRST
    if any(term in query_lower for term in ['condo', 'condos', 'condominium', 'condominiums', 'kondo']):
        entities['property_type'] = 'condo'
    elif 'apartment' in query_lower or 'apartments' in query_lower:
        entities['property_type'] = 'apartment'
    elif any(term in query_lower for term in ['house', 'houses', 'bahay', 'mga bahay']):
        entities['property_type'] = 'house'
    elif 'townhouse' in query_lower or 'townhouses' in query_lower:
        entities['property_type'] = 'townhouse'
    elif 'commercial' in query_lower:
        entities['property_type'] = 'commercial'
    elif 'land' in query_lower or 'lot' in query_lower:
        entities['property_type'] = 'land'
        
    # ========== Parse numeric price values for filtering ==========
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
    
    # ========== Parse bedroom criteria for filtering ==========
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
    
    # ========== SALE TYPE & SPECIFIC BANK DETECTION ==========
    
    # Check for specific banks FIRST (highest priority)
    for bank_key, bank_name in bank_keywords.items():
        if bank_key in query_lower:
            entities['bank_name'] = bank_name
            entities['sale_type'] = 'bank_financing'  # Implicitly bank_financing
            entities['financing_level'] = 'specific_bank'  # Level 2
            logger.info(f"🏦 Detected specific bank: {bank_name}")
            break

    # Check for Pag-IBIG (special case)
    pagibig_keywords = ['pag-ibig', 'pagibig', 'pag ibig', 'pag-ibig fund', 'pagibig fund']
    if not entities.get('bank_name') and any(keyword in query_lower for keyword in pagibig_keywords):
        entities['has_pagibig_query'] = True
        entities['sale_type'] = 'bank_financing'  # Pag-IBIG is a type of financing
        entities['financing_level'] = 'pagibig'  # Special level
        logger.info("🏠 Detected Pag-IBIG query")

    # Check for other sale types (if no specific bank or Pag-IBIG found)
    if not entities.get('bank_name') and not entities.get('has_pagibig_query'):
        for keyword, sale_type in sale_type_keywords.items():
            if keyword in query_lower:
                entities['sale_type'] = sale_type
                entities['financing_level'] = 'sale_type'  # Level 1
                logger.info(f"💰 Detected sale type: {sale_type}")
                break
    
    # ========== DISTINGUISH PROPERTY SEARCH vs INFORMATION REQUEST ==========
    
    # Check if this is a PROPERTY SEARCH query
    property_search_indicators = [
        'properties that accept',
        'houses that accept', 
        'condos that accept',
        'apartments that accept',
        'show me properties',
        'find properties',
        'properties with',
        'find sale',
        'looking for sale',
        'properties accepting',
        'with bank financing',
        'with outright',
        'with installment',
        'available with',
        'that accept',
        'that offer',
        'list properties',
        'show properties',
    ]

    # Check if this is an INFORMATION REQUEST
    info_request_indicators = [
        'what documents',
        'requirements for',
        'how to get',
        'what are the requirements',
        'documents needed',
        'papers needed',
        'process for',
        'how do i get',
        'what is needed for',
        'requirements to get',
        'how to apply',
        'application process',
        'tell me about',
        'information about',
        'what is pag-ibig',
        'what is bank financing',
        'explain',
        'guide',
    ]

    if entities.get('sale_type') or entities.get('bank_name') or entities.get('has_pagibig_query'):
        query_lower = query.lower()
        
        # Check if it's a property search
        is_property_search = any(indicator in query_lower for indicator in property_search_indicators)
        
        # Check if it's an information request
        is_info_request = any(indicator in query_lower for indicator in info_request_indicators)
        
        if is_property_search and not is_info_request:
            entities['is_property_search_with_financing'] = True
            entities['query_type'] = 'property_search'
            logger.info("🔍 Financing query is PROPERTY SEARCH")
        elif is_info_request:
            entities['financing_info_request'] = True
            entities['query_type'] = 'information_request'
            logger.info("📋 Financing query is INFORMATION REQUEST")
        else:
            # Ambiguous - check for action words
            if any(word in query_lower for word in ['find', 'show', 'search', 'look', 'list']):
                entities['is_property_search_with_financing'] = True
                entities['query_type'] = 'property_search'
                logger.info("🔍 Ambiguous financing query - treating as PROPERTY SEARCH")
            else:
                entities['financing_info_request'] = True
                entities['query_type'] = 'information_request'
                logger.info("📋 Ambiguous financing query - treating as INFORMATION REQUEST")
    
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
        'matangas city': 'Batangas City',
        'matangas': 'Batangas City',
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
        'tingloy': 'Tingloy',
        'balete': 'Balete',
        'san jose': 'San Jose',
        'calaca': 'Calaca'
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
    
    # ========== FEATURE DETECTION ==========
    feature_keywords = {
        'parking': [
            'with parking', 'parking space', 'parking included', 
            'parking', 'car park', 'garage', 'parking lot',
            'with garage', 'carport', 'parking slot'
        ],
        'swimming pool': [
            'with swimming pool', 'with pool', 'pool', 
            'swimming pool', 'swimmingpool', 'swim'
        ],
        'garden': [
            'with garden', 'garden', 'backyard', 'yard',
            'with backyard', 'green space', 'landscaped'
        ],
        'furnished': [
            'furnished', 'fully furnished', 'with furniture',
            'semi-furnished', 'partially furnished'
        ],
        'security': [
            'with security', 'security guard', '24/7 security',
            'cctv', 'gated', 'security camera', 'guarded',
            'with guard', 'secure'
        ],
        'elevator': [
            'with elevator', 'elevator', 'lift',
            'with lift', 'elevator access'
        ],
        'wifi': [
            'with wifi', 'wifi', 'internet', 'broadband',
            'fiber', 'with internet'
        ],
        'aircon': [
            'with aircon', 'air conditioning', 'aircon',
            'ac', 'air conditioner', 'central ac'
        ],
        'balcony': [
            'with balcony', 'balcony', 'terrace',
            'with terrace', 'outdoor space'
        ],
        'maids room': [
            'maids room', 'helpers quarter', 'maids quarter',
            'with maid', 'staff room'
        ]
    }
    
    # Check for features
    for feature, keywords in feature_keywords.items():
        for keyword in keywords:
            # Avoid false positives for very short tokens (e.g., "ac" in "accept")
            if len(keyword) <= 2:
                matched = re.search(rf'\b{re.escape(keyword)}\b', query_lower) is not None
            else:
                matched = keyword in query_lower

            if matched:
                entities['feature'] = feature
                logger.info(f"🏷️ Detected feature: {feature} (keyword: '{keyword}')")
                break
        if entities.get('feature'):
            break
    
    # Additional detection: look for "with X" pattern
    if not entities.get('feature'):
        # Look for "with" followed by a word
        with_match = re.search(r'with\s+(\w+)', query_lower)
        if with_match:
            possible_feature = with_match.group(1).lower()
            # Common features for fallback
            if possible_feature in ['parking', 'pool', 'garden', 'garage', 'balcony', 'wifi']:
                entities['feature'] = possible_feature
                logger.info(f"🏷️ Detected feature from 'with' pattern: {possible_feature}")
    
    # Also check for "parking" as a standalone word (for your specific query)
    if not entities.get('feature') and 'parking' in query_lower:
        entities['feature'] = 'parking'
        logger.info(f"🏷️ Detected feature: parking (standalone)")
    
    # Landmark detection
    if 'near' in query_lower or 'close to' in query_lower or 'around' in query_lower or 'beside' in query_lower:
        # Extract word after landmark terms
        match = re.search(r'(?:near|close to|around|beside|next to)\s+(\w+\s*\w*)', query_lower)
        if match:
            entities['landmark'] = match.group(1).strip()
    
    # Bathroom detection
    bath_match = re.search(r'(\d+)\s+(?:bathroom|bath|banyo)', query_lower)
    if bath_match:
        entities['bathrooms'] = int(bath_match.group(1))
    
    # ========== ADD MEMBER3 DETECTION LOGIC ==========
    
    # Question 3: Family/space needs detection - EXPANDED TO MATCH TRAINING DATA
    family_keywords = [
        'for family', 
        'family of', 
        'family properties',     # ADD THIS - matches "Family properties in Lipa City"
        'family house',          # ADD THIS
        'family home',           # ADD THIS
        'family condo',          # ADD THIS
        'family apartment',      # ADD THIS
        'family sized',          # ADD THIS
        'family-size',           # ADD THIS
        'family ready',          # ADD THIS
        'family appropriate',    # ADD THIS
        'suitable for family',   # ADD THIS
        'big family',            # ADD THIS
        'large family',          # ADD THIS
        'small family'          # ADD THIS
    ]
    
    if any(keyword in query_lower for keyword in family_keywords):
        entities['has_need_query'] = True
        entities['need_type'] = 'family'
        logger.info(f"🎯 Detected family needs query: '{query}'")
        
        # Extract family size if mentioned
        match = re.search(r'family\s+of\s+(\d+)', query_lower)
        if match:
            entities['family_size'] = int(match.group(1))
            logger.info(f"👨‍👩‍👧‍👦 Detected family size: {entities['family_size']}")
        
        # Extract space requirement (e.g., "spacious", "large", "cozy")
        space_keywords = ['spacious', 'large', 'roomy', 'expansive', 'cozy', 'compact']
        for keyword in space_keywords:
            if keyword in query_lower:
                entities['space_requirement'] = keyword
                logger.info(f"🏠 Detected space requirement: {keyword}")
                break
        
    # Check for other needs - independent from family keywords
    needs_map = {
        'for family': 'family',
        'family of': 'family',
        'for couple': 'couple',
        'for couples': 'couple',
        'properties for couples': 'couple',
        'for single': 'single'
    }
    
    for keyword, need_type in needs_map.items():
        if keyword in query_lower:
            entities['has_need_query'] = True
            entities['need_type'] = need_type
            logger.info(f"🎯 Detected need type: {need_type}")
            break

    # Lifestyle-oriented intents (Question 10)
    lifestyle_map = {
        'for students': ('student lifestyle', 'schools'),
        'student housing': ('student lifestyle', 'schools'),
        'student accommodations': ('student lifestyle', 'schools'),
        'properties for students': ('student lifestyle', 'schools'),
        'for professionals': ('professional lifestyle', None),
        'working professionals': ('professional lifestyle', None),
        'single professional': ('single professional lifestyle', None),
        'for retirees': ('retiree lifestyle', 'hospitals'),
        'retirement': ('retiree lifestyle', 'hospitals'),
        'for business': ('business lifestyle', None),
        'home business': ('business lifestyle', None),
        'for investors': ('investor lifestyle', None),
        'doctor': ('medical professional lifestyle', 'hospitals'),
        'nurse': ('medical professional lifestyle', 'hospitals'),
        'medical': ('medical professional lifestyle', 'hospitals'),
        'gym': ('active lifestyle', 'gym'),
        'active lifestyle': ('active lifestyle', 'gym')
    }
    for keyword, (lifestyle_name, default_landmark) in lifestyle_map.items():
        if keyword in query_lower:
            entities['has_match_query'] = True
            entities['lifestyle'] = entities.get('lifestyle') or lifestyle_name
            if default_landmark and not entities.get('landmark'):
                entities['landmark'] = default_landmark
                entities['lifestyle_focus_landmark'] = default_landmark
            break
    
    # Question 5: Feature with good price
    price_quality_keywords = [
        'good price', 'cheap', 'affordable', 'reasonable', 'good value',
        'reasonable cost', 'budget-friendly', 'inexpensive', 'low cost',  # ADDED
        'fair price', 'economical', 'value for money'                    # ADDED
    ]
    for keyword in price_quality_keywords:
        if keyword in query_lower:
            entities['has_feature_price_query'] = True
            entities['price_quality'] = keyword
            logger.info(f"💰 Detected price quality: {keyword}")
            break
    
    # Question 8: Process info
    process_keywords = [
        'steps for', 'how to', 'process of', 'timeline', 'requirements', 
        'documents', 'steps to', 'procedure', 'costs for', 'expenses',   # ADDED
        'fees', 'charges', 'paperwork', 'legal requirements'           # ADDED
    ]
    for keyword in process_keywords:
        if keyword in query_lower:
            entities['has_process_query'] = True
            entities['process_type'] = keyword.split()[0]
            logger.info(f"📋 Detected process query: {keyword}")
            break
    
    # Question 10: Lifestyle matching
    match_keywords = [
        'match my', 'suitable for', 'fitting my', 'what matches', 
        'recommendations', 'appropriate for', 'compatible with',      # ADDED
        'aligned with', 'properties matching', 'match properties'    # ADDED
    ]
    
    for keyword in match_keywords:
        if keyword in query_lower:
            entities['has_match_query'] = True
            
            # Extract lifestyle type from query
            lifestyle_patterns = [
                r'(match my|suitable for|appropriate for)\s+([\w\s]+?)(?:lifestyle|needs|budget)',
                r'([\w\s]+)\s+lifestyle'
            ]
            
            for pattern in lifestyle_patterns:
                lifestyle_match = re.search(pattern, query_lower)
                if lifestyle_match:
                    entities['lifestyle'] = lifestyle_match.group(1).strip()
                    logger.info(f"🎯 Detected lifestyle: {entities['lifestyle']}")
                    break
            
            logger.info("🎯 Detected lifestyle matching query")
            break

    # Allow implicit lifestyle-matching prompts (e.g., "I am a doctor", "student ako")
    implicit_lifestyle_terms = [
        'i am a doctor', 'doctor ako', 'nurse ako', 'medical worker',
        'i am a student', 'student ako', 'single professional', 'young professional',
        'work from home', 'retiree', 'retired'
    ]
    if not entities.get('has_match_query') and any(term in query_lower for term in implicit_lifestyle_terms):
        entities['has_match_query'] = True
        if not entities.get('lifestyle'):
            entities['lifestyle'] = query_lower

    # Map lifestyle to practical matching hints
    if entities.get('has_match_query'):
        # Student lifestyle -> near schools/universities
        if any(term in query_lower for term in ['student', 'students', 'university', 'school', 'estudyante']):
            entities['need_type'] = entities.get('need_type') or 'students'
            entities['lifestyle_focus_landmark'] = 'schools'
            if not entities.get('landmark'):
                entities['landmark'] = 'schools'

        # Doctor/medical lifestyle -> near hospitals
        if any(term in query_lower for term in ['doctor', 'nurse', 'hospital', 'medical', 'healthcare']):
            entities['need_type'] = entities.get('need_type') or 'professionals'
            entities['lifestyle_focus_landmark'] = 'hospitals'
            if not entities.get('landmark'):
                entities['landmark'] = 'hospitals'

        # Single professional lifestyle -> room/apartment/1BR preference
        if any(term in query_lower for term in ['single professional', 'single', 'young professional']):
            entities['need_type'] = 'single'
            if not entities.get('property_type'):
                entities['property_type'] = 'apartment'
        
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

# Helper function for bedroom count conversion - UPDATED
def get_bedroom_count_from_string(bedroom_str: str) -> int:
    """Convert bedroom string to numeric count for family filtering"""
    if not bedroom_str:
        return 0
    
    # If it's already a number, return it
    try:
        if isinstance(bedroom_str, (int, float)):
            return int(bedroom_str)
    except:
        pass
    
    bedroom_str = str(bedroom_str).lower().strip()
    
    # Special cases first
    if 'studio' in bedroom_str:
        return 0
    if '5+' in bedroom_str or 'five plus' in bedroom_str:
        return 5
    
    # Extract number using regex
    match = re.search(r'(\d+)', bedroom_str)
    if match:
        return int(match.group(1))
    
    # Word to number mapping
    word_to_num = {
        'zero': 0, 'one': 1, 'two': 2, 'three': 3, 
        'four': 4, 'five': 5, 'six': 6
    }
    
    for word, num in word_to_num.items():
        if word in bedroom_str:
            return num
    
    return 0  # Default

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
    
    # ========== ADD BANK FINANCING INFO ==========
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
        # ========== ADDED: Bank financing fields ==========
        'saleType': property_data.get('saleType', ''),  # Not sale_type
        'financingBank': property_data.get('financingBank', None),  # Not financing_bank
        'has_bank_financing': property_data.get('saleType') == 'bank_financing',
        'price_numeric': property_data.get('price_numeric', 0)  # Add numeric price
    }
    
    return standardized

# Get mock properties when Firebase is not connected - UPDATED WITH COUPLE FILTERING
def get_mock_properties(entities: Dict[str, Any]) -> List[Dict[str, Any]]:
    """Generate mock properties for testing when Firebase is not connected"""
    # MOCK DATA DISABLED - Always return empty list
    logger.warning("⚠️ Mock data is disabled - only showing real database properties")
    return []

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
        logger.info(f"     Bank: {prop.get('financingBank', 'N/A')}")
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
        
        # Check if it matches specific bank
        if entities.get('bank_name'):
            prop_bank = prop.get('financingBank', '')
            query_bank = entities.get('bank_name', '')
            matches_bank = prop_bank == query_bank
            logger.info(f"     Matches bank '{query_bank}': {matches_bank}")


def _haversine_km(lat1: float, lon1: float, lat2: float, lon2: float) -> float:
    """Distance between two points in km (WGS84)."""
    import math
    R = 6371  # Earth radius in km
    phi1, phi2 = math.radians(lat1), math.radians(lat2)
    dphi = math.radians(lat2 - lat1)
    dlam = math.radians(lon2 - lon1)
    a = math.sin(dphi / 2) ** 2 + math.cos(phi1) * math.cos(phi2) * math.sin(dlam / 2) ** 2
    c = 2 * math.atan2(math.sqrt(a), math.sqrt(1 - a))
    return R * c


def _load_landmarks_data() -> Dict[str, Any]:
    """Load landmark categories and points for map-based 'near X' filtering."""
    path = _resolve_data_path('shared', 'landmarks_batangas.json')
    try:
        if os.path.exists(path):
            with open(path, 'r', encoding='utf-8') as f:
                return json.load(f)
    except Exception as e:
        logger.warning(f"⚠️ Could not load landmarks data: {e}")
    return {}


def _landmark_matches_property(
    property_data: Dict[str, Any],
    landmark_query: str,
    landmarks_data: Dict[str, Any],
    radius_km: float = 5.0
) -> bool:
    """
    True if property is considered 'near' the landmark.
    Uses (1) description/address text match, or (2) map distance when property has lat/lng.
    """
    if not landmarks_data or not landmark_query:
        return True
    q = landmark_query.lower().strip()
    categories = landmarks_data.get('categories', {})
    query_to_cat = landmarks_data.get('query_to_category', {})
    radius_km = float(landmarks_data.get('radius_km', radius_km))

    category = query_to_cat.get(q) or query_to_cat.get(q.rstrip('s'))
    if not category or category not in categories:
        desc = (property_data.get('description') or '') + ' ' + (property_data.get('address') or '')
        return q in desc.lower()

    cat_data = categories[category]
    keywords = cat_data.get('keywords_for_description', [])
    desc = (property_data.get('description') or '').lower()
    address = (property_data.get('address') or '').lower()
    searchable = desc + ' ' + address

    if any(kw in searchable for kw in keywords):
        return True
    if q in searchable or category in searchable:
        return True

    try:
        prop_lat = property_data.get('latitude')
        prop_lng = property_data.get('longitude')
        if prop_lat is None or prop_lng is None:
            return False
        prop_lat = float(prop_lat)
        prop_lng = float(prop_lng)
    except (TypeError, ValueError):
        return False

    points = cat_data.get('points', [])
    for pt in points:
        pt_lat = pt.get('lat')
        pt_lng = pt.get('lng')
        if pt_lat is None or pt_lng is None:
            continue
        dist_km = _haversine_km(prop_lat, prop_lng, float(pt_lat), float(pt_lng))
        if dist_km <= radius_km:
            return True
    return False


def _resolve_landmark_category(landmark_query: str, landmarks_data: Dict[str, Any]) -> Optional[str]:
    """Resolve free-text landmark query to a configured landmark category."""
    if not landmark_query or not landmarks_data:
        return None
    q = str(landmark_query).lower().strip()
    query_to_cat = landmarks_data.get('query_to_category', {})
    return query_to_cat.get(q) or query_to_cat.get(q.rstrip('s'))


def _get_nearest_landmark(
    property_data: Dict[str, Any],
    category: str,
    landmarks_data: Dict[str, Any]
) -> Optional[Dict[str, Any]]:
    """Return nearest configured landmark point for a property and category."""
    if not category or not landmarks_data:
        return None

    categories = landmarks_data.get('categories', {})
    cat_data = categories.get(category, {})
    points = cat_data.get('points', [])
    if not points:
        return None

    try:
        prop_lat = float(property_data.get('latitude'))
        prop_lng = float(property_data.get('longitude'))
    except (TypeError, ValueError):
        return None

    nearest = None
    nearest_dist = None
    for pt in points:
        pt_lat = pt.get('lat')
        pt_lng = pt.get('lng')
        if pt_lat is None or pt_lng is None:
            continue
        dist_km = _haversine_km(prop_lat, prop_lng, float(pt_lat), float(pt_lng))
        if nearest_dist is None or dist_km < nearest_dist:
            nearest_dist = dist_km
            nearest = pt

    if nearest is None or nearest_dist is None:
        return None

    return {
        'category': category,
        'name': nearest.get('name', f'Nearest {category}'),
        'city': nearest.get('city', ''),
        'distance_km': round(float(nearest_dist), 2),
    }


# Firestore queries - UPDATED WITH SPECIFIC BANK AND PAG-IBIG FILTERING
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
        
        # ========== SALE TYPE & SPECIFIC BANK FILTERING ==========
        has_sale_type_query = entities.get('sale_type') is not None
        has_specific_bank = entities.get('bank_name') is not None
        has_pagibig_query = entities.get('has_pagibig_query', False)

        # IMPORTANT: For any financing-related query, we ONLY want sale properties
        if has_sale_type_query or has_specific_bank or has_pagibig_query:
            query = query.where(filter=FieldFilter('type', '==', 'sale'))
            logger.info("🔍 Filtering: Sale properties only")

        # Level 1: Filter by saleType
        if has_sale_type_query and not has_specific_bank and not has_pagibig_query:
            sale_type = entities['sale_type']
            try:
                query = query.where(filter=FieldFilter('saleType', '==', sale_type))
                logger.info(f"🔍 Filtering by saleType: {sale_type}")
            except Exception as e:
                logger.warning(f"⚠️ Could not filter by saleType: {e}")

        # Level 2: Filter by specific bank (highest priority)
        if has_specific_bank:
            bank_name = entities['bank_name']
            try:
                # Must have both saleType = bank_financing AND financingBank = specific bank
                query = query.where(filter=FieldFilter('saleType', '==', 'bank_financing'))
                query = query.where(filter=FieldFilter('financingBank', '==', bank_name))
                logger.info(f"🔍 Filtering by specific bank: {bank_name}")
            except Exception as e:
                logger.warning(f"⚠️ Could not filter by specific bank: {e}")
                # Will filter client-side

        # Level 3: Pag-IBIG (show ALL bank_financing properties)
        elif has_pagibig_query and not has_specific_bank:
            try:
                query = query.where(filter=FieldFilter('saleType', '==', 'bank_financing'))
                logger.info(f"🔍 Filtering: Properties eligible for Pag-IBIG (all bank_financing)")
            except Exception as e:
                logger.warning(f"⚠️ Could not filter by bank_financing: {e}")
        
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
            bank = data.get('financingBank', 'NO bank')
            logger.info(f"   • ID: {doc_id[:10]}..., Type: {prop_type}, City: {city}, Status: {status}, Listing: {listing_type}, SaleType: {sale_type}, Bank: {bank}")
        
        # ========== COMPREHENSIVE CLIENT-SIDE FILTERING ==========
        filtered_properties = []
        need_type = (entities.get('need_type') or '').lower()
        landmark_focus = entities.get('lifestyle_focus_landmark') or entities.get('landmark')
        landmarks_data = _load_landmarks_data() if landmark_focus else {}
        focus_category = _resolve_landmark_category(landmark_focus, landmarks_data)

        for property_data in property_data_list:
            matches = True
            
            # ========== CLIENT-SIDE STATUS FILTERING ==========
            status = str(property_data.get('status', '')).lower()
            valid_statuses = ['available', 'active', 'for sale']
            
            # For sale type queries, only show 'available' or 'active' sale properties
            if has_sale_type_query or has_specific_bank or has_pagibig_query:
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
            if has_sale_type_query and not has_specific_bank and not has_pagibig_query:
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
            
            # ========== CLIENT-SIDE BANK FILTERING ==========
            if has_specific_bank and matches:
                prop_bank = property_data.get('financingBank', '')
                requested_bank = entities['bank_name']
                
                # Check 1: Must be a sale property
                if property_data.get('type') != 'sale':
                    logger.debug(f"❌ Property {property_data.get('id', 'unknown')} excluded - not a sale property for bank financing")
                    matches = False
                    continue
                
                # Check 2: Must have financingBank field
                if not prop_bank:
                    logger.debug(f"❌ Property {property_data.get('id', 'unknown')} excluded - no financingBank field")
                    matches = False
                    continue
                # Check 3: Must match the requested bank
                elif prop_bank != requested_bank:
                    logger.debug(f"❌ Property {property_data.get('id', 'unknown')} excluded - bank {prop_bank} != {requested_bank}")
                    matches = False
                    continue
                else:
                    logger.debug(f"✅ Property {property_data.get('id', 'unknown')} matches bank: {prop_bank}")

            # ========== CLIENT-SIDE PAG-IBIG FILTERING ==========
            if has_pagibig_query and not has_specific_bank and matches:
                # Check 1: Must be a sale property
                if property_data.get('type') != 'sale':
                    logger.debug(f"❌ Property {property_data.get('id', 'unknown')} excluded - not a sale property for Pag-IBIG")
                    matches = False
                    continue
                
                # Check 2: Must have saleType = bank_financing
                prop_sale_type = property_data.get('saleType', '')
                if prop_sale_type != 'bank_financing':
                    logger.debug(f"❌ Property {property_data.get('id', 'unknown')} excluded - not bank_financing for Pag-IBIG")
                    matches = False
                    continue
            
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
            
            # Apply couple filtering client-side - ADDED
            if entities.get('has_need_query') and entities.get('need_type') == 'couple' and matches:
                prop_bedrooms = property_data.get('bedrooms', 'Not specified')
                bedrooms = get_bedroom_count_from_string(prop_bedrooms)
                
                # Couples typically need 0-2 bedrooms (studio to 2-bedroom)
                if bedrooms > 2:  # More than 2 bedrooms not ideal for couples
                    matches = False
                    logger.debug(f"❌ Property {property_data.get('id', 'unknown')} excluded - {bedrooms} bedrooms not ideal for couples")

            # Apply student-lifestyle filtering: keep only student-suitable types
            if need_type == 'students' and matches:
                prop_type = str(property_data.get('propertyType', '')).lower()
                student_friendly_types = ['boarding_house', 'apartment', 'condo_unit', 'condominium', 'room', 'studio']
                # Explicitly exclude commercial/industrial options for student queries
                blocked_types = ['commercial', 'warehouse', 'office', 'retail', 'industrial', 'farm', 'land']
                is_blocked = any(bt in prop_type for bt in blocked_types)
                type_ok = any(t in prop_type for t in student_friendly_types)
                if is_blocked or not type_ok:
                    matches = False
                    logger.debug(f"❌ Property {property_data.get('id', 'unknown')} excluded - not student-suitable type: {prop_type}")
                    continue

            # Apply single-professional style filtering (room/studio/1BR/2BR max)
            if (entities.get('need_type') == 'single' or 'single professional' in str(entities.get('lifestyle', '')).lower()) and matches:
                prop_type = str(property_data.get('propertyType', '')).lower()
                prop_bedrooms = property_data.get('bedrooms', 'Not specified')
                bedrooms = get_bedroom_count_from_string(prop_bedrooms)
                single_friendly_types = ['apartment', 'boarding_house', 'condo_unit', 'condominium', 'room', 'studio']
                type_ok = any(t in prop_type for t in single_friendly_types) if prop_type else True
                beds_ok = (bedrooms == 0 or bedrooms <= 2)
                if not (type_ok and beds_ok):
                    matches = False
                    logger.debug(f"❌ Property {property_data.get('id', 'unknown')} excluded - not ideal for single-professional profile")
            
            # ========== CLIENT-SIDE FEATURE/AMENITY FILTERING ==========
            if entities.get('feature') and matches:
                requested_feature = entities['feature'].lower()
                prop_amenities = property_data.get('amenities', []) or []
                prop_furnishing = (property_data.get('furnishing') or '').lower()
                prop_description = (property_data.get('description') or '').lower()
                # Build searchable text from amenities + furnishing + description
                searchable = ' '.join([str(a).lower() for a in prop_amenities]) + ' ' + prop_furnishing + ' ' + prop_description
                # Feature synonyms for flexible matching (query term -> possible DB values)
                feature_synonyms = {
                    'parking': ['parking', 'garage', 'carport', 'car park'],
                    'swimming pool': ['pool', 'swimming pool', 'swimmingpool'],
                    'garden': ['garden', 'backyard', 'yard', 'green space', 'landscaped'],
                    'furnished': ['furnished', 'fully furnished', 'semi-furnished', 'partially furnished'],
                    'security': ['security', 'guard', 'cctv', 'gated', '24/7'],
                    'elevator': ['elevator', 'lift'],
                    'wifi': ['wifi', 'internet', 'broadband', 'fiber'],
                    'aircon': ['aircon', 'air conditioning', 'ac', 'air conditioner'],
                    'balcony': ['balcony', 'terrace'],
                    'maids room': ['maid', 'maids room', 'helpers quarter', 'staff room'],
                }
                match_terms = feature_synonyms.get(requested_feature, [requested_feature])
                feature_found = any(term in searchable for term in match_terms)
                if not feature_found:
                    matches = False
                    logger.debug(f"❌ Property {property_data.get('id', 'unknown')} excluded - no amenity match for '{requested_feature}'")

            # ========== CLIENT-SIDE READY-TO-MOVE FILTERING ==========
            if entities.get('has_ready_query') and matches:
                title_text = (property_data.get('title') or '').lower()
                desc_text = (property_data.get('description') or '').lower()
                status_text = (property_data.get('status') or '').lower()
                furnishing_text = (property_data.get('furnishing') or '').lower()
                searchable_ready = f"{title_text} {desc_text} {status_text}"

                ready_markers = [
                    'ready to move', 'ready for occupancy', 'available now',
                    'immediate occupancy', 'move in ready', 'ready now',
                    'ready to occupy', 'immediate move in', 'available immediately',
                    'rfo', 'pwede na lipatan', 'handa na tirahan', 'lipat agad'
                ]
                is_ready_by_text = any(marker in searchable_ready for marker in ready_markers)
                # Treat fully furnished units as ready-to-move by default
                is_ready_by_furnishing = furnishing_text in ['fully furnished', 'full furnished', 'furnished']
                if not (is_ready_by_text or is_ready_by_furnishing):
                    matches = False
                    logger.debug(f"❌ Property {property_data.get('id', 'unknown')} excluded - no ready-to-move marker in title/description/status")
            
            # ========== CLIENT-SIDE LANDMARK FILTERING (MAP + DESCRIPTION) ==========
            if entities.get('landmark') and matches:
                if not _landmark_matches_property(property_data, entities['landmark'], landmarks_data):
                    matches = False
                    logger.debug(f"❌ Property {property_data.get('id', 'unknown')} excluded - not near landmark '{entities['landmark']}'")
            
            if matches:
                # Standardize property data for chatbot response
                standardized_property = standardize_property_data(property_data_with_price)
                # Add nearest-landmark evidence to support "near X" recommendations
                if landmarks_data:
                    nearest_focus = _get_nearest_landmark(property_data, focus_category, landmarks_data) if focus_category else None
                    if nearest_focus:
                        standardized_property['nearest_landmark'] = nearest_focus

                    nearby_landmarks = []
                    for category in ['school', 'hospital', 'mall']:
                        nearest_item = _get_nearest_landmark(property_data, category, landmarks_data)
                        if nearest_item:
                            nearby_landmarks.append(nearest_item)
                    if nearby_landmarks:
                        standardized_property['nearby_landmarks'] = nearby_landmarks
                filtered_properties.append(standardized_property)
        
        # Update properties with client-side filtered results
        properties = filtered_properties
        logger.info(f"🔍 After client-side filtering: {len(properties)} properties")
        
        # Debug property matching
        debug_property_matching(property_data_list, entities)
        
        # ========== NO FALLBACK FOR SALE TYPE QUERIES ==========
        if len(properties) == 0 and (has_sale_type_query or has_specific_bank or has_pagibig_query):
            logger.info(f"❌ No properties found with specified financing criteria")
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

        # Lifestyle-aware ranking so top results are practical for the user's need.
        if properties:
            def _rank_property(prop: Dict[str, Any]) -> float:
                score = 0.0
                ptype = str(prop.get('type', '')).lower()
                beds = get_bedroom_count_from_string(prop.get('bedrooms', ''))
                price_numeric = float(prop.get('price_numeric') or 0)

                if need_type == 'students':
                    if any(t in ptype for t in ['boarding_house', 'apartment', 'room', 'studio']):
                        score += 30
                    elif 'condo' in ptype:
                        score += 22
                    if beds <= 2:
                        score += 15
                    if 0 < price_numeric <= 20000:
                        score += 12
                    elif 0 < price_numeric <= 40000:
                        score += 5

                nearest_focus = prop.get('nearest_landmark') or {}
                dist = nearest_focus.get('distance_km')
                if isinstance(dist, (int, float)):
                    # closer landmark -> higher score
                    score += max(0, 20 - min(float(dist), 20))
                return score

            properties = sorted(properties, key=_rank_property, reverse=True)
        
    except Exception as e:
        logger.error(f"❌ Error searching Firestore: {e}")
        import traceback
        logger.error(f"Traceback: {traceback.format_exc()}")
    
    return properties

# Generate criteria search response
def generate_criteria_search_response(entities: Dict[str, Any], properties: List[Dict[str, Any]], language: str = 'en') -> str:
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
    
    is_tl = language == 'tl'

    # Generate response
    if properties:
        # Group by location
        properties_by_location = {}
        for prop in properties:
            location = prop.get('city', 'Unknown')
            if location not in properties_by_location:
                properties_by_location[location] = []
            properties_by_location[location].append(prop)
        
        if is_tl:
            response = f"🔍 **May nahanap na {len(properties)} {criteria_desc}**\n\n"
        else:
            response = f"🔍 **Found {len(properties)} {criteria_desc}**\n\n"
        
        for location, loc_props in properties_by_location.items():
            if is_tl:
                response += f"📍 **{location}** ({len(loc_props)} available)\n"
            else:
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
            if is_tl:
                response += "💡 **Tips para mas maraming result:**\n"
                response += "   • Palawakin ang budget range mo\n"
                response += "   • Isama ang kalapit na locations\n"
            else:
                response += "💡 **Tips for more results:**\n"
                response += "   • Expand your price range\n"
                response += "   • Consider nearby locations\n"
            if entities.get('exact_bedrooms'):
                response += "   • Subukan ang ibang bilang ng bedroom\n" if is_tl else "   • Try different bedroom counts\n"
        
    else:
        if is_tl:
            response = f"❌ **Walang posted properties para sa: {criteria_desc}**\n\n"
            response += "💡 **Suggestions:**\n"
            response += "   • Subukan ang ibang price range\n"
            response += "   • Isaalang-alang ang kalapit na locations\n"
            response += "   • I-adjust ang bedroom requirements mo\n"
            response += "   • Bumalik ulit mamaya para sa bagong listings\n"
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
    
    # Handle financing information queries (documents, process, etc.)
    elif entities.get('financing_info_request'):
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

# ========== NEW: Generate financing property response (3 levels) ==========
def generate_financing_property_response(entities: Dict[str, Any], properties: List[Dict[str, Any]]) -> str:
    """Generate response for financing-related property searches (3 levels)"""
    
    financing_level = entities.get('financing_level', 'sale_type')
    query_type = entities.get('query_type', 'property_search')
    
    # ========== LEVEL 1: SALE TYPE ONLY ==========
    if financing_level == 'sale_type':
        sale_type = entities['sale_type']
        sale_type_display = sale_type.replace('_', ' ').title()
        
        if sale_type == 'bank_financing':
            response = f"🏦 **Properties with Bank Financing**\n\n"
            response += f"I found {len(properties)} properties that accept bank financing:\n\n"
            
            # Group by bank if available
            bank_counts = {}
            for prop in properties:
                bank = prop.get('financingBank', 'Bank financing')
                if not bank:
                    bank = 'Bank financing'
                bank_counts[bank] = bank_counts.get(bank, 0) + 1
            
            for i, prop in enumerate(properties[:5]):
                title = prop.get('title', f'Property {i+1}')
                price = prop.get('price', 'Price not available')
                location = prop.get('location', 'Location not specified')
                bank = prop.get('financingBank', 'Bank financing')
                
                if not bank:
                    bank = 'Bank financing'
                
                response += f"{i+1}. **{title}** in {location} - {price}\n"
                response += f"   🏦 {bank}\n\n"
            
            if bank_counts:
                response += f"**Available Banks:**\n"
                for bank, count in list(bank_counts.items())[:5]:
                    response += f"• {bank}: {count} {'property' if count == 1 else 'properties'}\n"
        
        elif sale_type == 'outright':
            response = f"💰 **Properties with Outright/Cash Payment**\n\n"
            response += f"I found {len(properties)} properties available for outright purchase:\n\n"
            for i, prop in enumerate(properties[:5]):
                title = prop.get('title', f'Property {i+1}')
                price = prop.get('price', 'Price not available')
                location = prop.get('location', 'Location not specified')
                response += f"{i+1}. **{title}** in {location} - {price}\n"
            
            response += "\n💡 **Outright Payment Benefits:**"
            response += "\n• 5-10% discount typically offered"
            response += "\n• Fastest transaction process"
            response += "\n• No interest or bank fees"
        
        elif sale_type == 'installment':
            response = f"📅 **Properties with Installment Plans**\n\n"
            response += f"I found {len(properties)} properties available with installment terms:\n\n"
            for i, prop in enumerate(properties[:5]):
                title = prop.get('title', f'Property {i+1}')
                price = prop.get('price', 'Price not available')
                location = prop.get('location', 'Location not specified')
                response += f"{i+1}. **{title}** in {location} - {price}\n"
            
            response += "\n💡 **Installment Benefits:**"
            response += "\n• Flexible payment terms (up to 10 years)"
            response += "\n• Easier approval process"
            response += "\n• Direct developer financing"
        
        if not properties:
            response = f"❌ No properties found with {sale_type_display}.\n\n"
            response += "💡 **Try:**\n"
            response += "• Expanding your search area\n"
            if sale_type == 'bank_financing':
                response += "• Checking other financing options (installment/outright)\n"
            response += "• Contacting us for custom property matching\n"
        
        return response
    
    # ========== LEVEL 2: SPECIFIC BANK ==========
    elif financing_level == 'specific_bank':
        bank_name = entities['bank_name']
        
        if properties:
            response = f"🏦 **Properties with {bank_name} Financing**\n\n"
            response += f"I found {len(properties)} properties that offer {bank_name} financing:\n\n"
            
            for i, prop in enumerate(properties[:5]):
                title = prop.get('title', f'Property {i+1}')
                price = prop.get('price', 'Price not available')
                location = prop.get('location', 'Location not specified')
                response += f"{i+1}. **{title}** in {location} - {price}\n"
            
            response += f"\n💡 **{bank_name} Financing Tips:**"
            response += f"\n• Contact {bank_name} directly for current interest rates"
            response += f"\n• Prepare requirements: Valid ID, Proof of Income, Bank Statements"
            response += f"\n• Loanable amount typically up to 80% of property value"
        else:
            response = f"❌ No properties found with {bank_name} financing.\n\n"
            response += "💡 **Try:**\n"
            response += f"• Other banks (BDO, BPI, Metrobank, etc.)\n"
            response += "• Properties with 'bank_financing' sale type\n"
            response += "• Checking back later for new listings\n"
        
        return response
    
    # ========== LEVEL 3: PAG-IBIG ==========
    elif financing_level == 'pagibig':
        if properties:
            response = f"🏠 **Properties Eligible for Pag-IBIG Financing**\n\n"
            response += f"I found {len(properties)} properties that may qualify for Pag-IBIG housing loans:\n\n"
            
            # Group by bank
            bank_counts = {}
            for prop in properties:
                bank = prop.get('financingBank', 'Bank financing')
                if not bank:
                    bank = 'Bank financing'
                bank_counts[bank] = bank_counts.get(bank, 0) + 1
            
            for i, prop in enumerate(properties[:5]):
                title = prop.get('title', f'Property {i+1}')
                price = prop.get('price', 'Price not available')
                location = prop.get('location', 'Location not specified')
                bank = prop.get('financingBank', 'Bank financing')
                
                if not bank:
                    bank = 'Bank financing'
                
                response += f"{i+1}. **{title}** in {location} - {price}\n"
                response += f"   🏦 Partner Bank: {bank}\n\n"
            
            response += f"**Pag-IBIG Quick Info:**\n"
            response += "• Requires 24+ months membership\n"
            response += "• Up to ₱6M loanable amount\n"
            response += "• 3-30 years payment term\n"
            response += "• Interest rates: 5.75% - 11.5%\n\n"
            response += "*Note: Final approval subject to Pag-IBIG evaluation.*"
        else:
            response = f"🏠 **Pag-IBIG Eligible Properties**\n\n"
            response += "No properties currently found with Pag-IBIG eligibility.\n\n"
            response += "💡 **Try:**\n"
            response += "• Looking for properties with 'bank_financing' sale type\n"
            response += "• These may qualify for Pag-IBIG upon approval\n"
            response += "• Contact us for assisted Pag-IBIG applications\n"
        
        return response
    
    return None

# ========== NEW: Generate financing information response ==========
def generate_financing_info_response(entities: Dict[str, Any]) -> str:
    """Generate response for financing information requests"""
    
    # Check for specific bank information
    if entities.get('bank_name'):
        bank_name = entities['bank_name']
        return f"🏦 **{bank_name} Housing Loan Information**\n\n" \
               f"**Typical Requirements:**\n" \
               f"• Valid government-issued ID\n" \
               f"• Proof of income (3-6 months payslips)\n" \
               f"• Certificate of Employment\n" \
               f"• Income Tax Return (ITR)\n" \
               f"• Bank statements (3-6 months)\n" \
               f"• Proof of billing\n" \
               f"• Marriage certificate (if applicable)\n\n" \
               f"**Process:**\n" \
               f"1. Loan pre-qualification\n" \
               f"2. Property appraisal\n" \
               f"3. Submit loan application\n" \
               f"4. Credit investigation\n" \
               f"5. Loan approval (1-2 weeks)\n" \
               f"6. Release of funds\n\n" \
               f"💡 **Looking for {bank_name} properties?**\n" \
               f"Try: 'find properties with {bank_name} financing'"
    
    # Check for Pag-IBIG information
    elif entities.get('has_pagibig_query'):
        return "🏠 **Pag-IBIG Housing Loan Information**\n\n" \
               "**Membership Requirements:**\n" \
               "• Active Pag-IBIG membership (24+ months)\n" \
               "• At least 24 monthly contributions\n" \
               "• No existing Pag-IBIG housing loan\n\n" \
               "**Required Documents:**\n" \
               "• Pag-IBIG MID Number\n" \
               "• Valid IDs (2 valid IDs)\n" \
               "• Proof of income (payslips, ITR)\n" \
               "• Certificate of Employment\n" \
               "• Proof of billing\n" \
               "• Marriage contract (if married)\n" \
               "• Tax Identification Number (TIN)\n\n" \
               "**Loan Details:**\n" \
               "• Maximum loan amount: Up to ₱6M\n" \
               "• Interest rate: 5.75% - 11.5%\n" \
               "• Payment term: 3-30 years\n" \
               "• Loan-to-value: Up to 95%\n\n" \
               "💡 **Find Pag-IBIG eligible properties:**\n" \
               "• Try: 'show properties with bank financing'\n" \
               "• These may qualify for Pag-IBIG upon approval"
    
    # Check for bank financing information
    elif entities.get('sale_type') == 'bank_financing':
        return "🏦 **Bank Financing Overview**\n\n" \
               "**Available Banks:**\n" \
               "• BDO Unibank\n" \
               "• BPI\n" \
               "• Metrobank\n" \
               "• Land Bank of the Philippines\n" \
               "• UnionBank\n" \
               "• Security Bank\n" \
               "• RCBC\n" \
               "• PNB\n" \
               "• China Bank\n" \
               "• Maybank\n\n" \
               "**Common Requirements:**\n" \
               "• Valid ID\n" \
               "• Proof of income (3-6 months)\n" \
               "• Certificate of Employment\n" \
               "• ITR\n" \
               "• Bank statements\n" \
               "• Proof of billing\n\n" \
               "**Typical Terms:**\n" \
               "• Downpayment: 20-30%\n" \
               "• Interest rate: 6-12% annually\n" \
               "• Loan term: 5-20 years\n\n" \
               "💡 **Ask about specific banks:**\n" \
               "• 'requirements for BDO loan'\n" \
               "• 'BPI financing process'\n" \
               "• 'Metrobank housing loan'"
    
    # Check for outright/cash information
    elif entities.get('sale_type') == 'outright':
        return "💰 **Outright/Cash Payment Information**\n\n" \
               "**Advantages:**\n" \
               "• Fastest transaction (1-2 weeks completion)\n" \
               "• 5-10% discount typically offered\n" \
               "• No interest payments\n" \
               "• No bank processing fees\n" \
               "• Stronger negotiating position\n" \
               "• No credit checks required\n\n" \
               "**Requirements:**\n" \
               "• Valid government ID\n" \
               "• Tax Identification Number (TIN)\n" \
               "• Proof of fund source\n" \
               "• Notarized Deed of Sale\n\n" \
               "💡 **Find outright properties:**\n" \
               "• Try: 'find houses with outright payment'\n" \
               "• Or: 'properties with cash payment option'"
    
    # Check for installment information
    elif entities.get('sale_type') == 'installment':
        return "📅 **Installment/In-house Financing Information**\n\n" \
               "**Advantages:**\n" \
               "• Faster approval (1-3 days)\n" \
               "• Less strict credit requirements\n" \
               "• Flexible payment terms (up to 10 years)\n" \
               "• Direct dealing with developer\n" \
               "• Lower processing fees\n" \
               "• Easier to negotiate terms\n\n" \
               "**Requirements:**\n" \
               "• Valid ID\n" \
               "• Proof of Income\n" \
               "• Downpayment (20-30%)\n" \
               "• Post-dated checks\n" \
               "• Buyer Information Sheet\n\n" \
               "**Typical Terms:**\n" \
               "• Interest rate: 6-9% annually\n" \
               "• Monthly amortization based on remaining balance\n\n" \
               "💡 **Find installment properties:**\n" \
               "• Try: 'properties with installment plan'\n" \
               "• Or: 'condos with in-house financing'"
    
    return None

# Generate response from training data templates - UPDATED FOR CRITERIA SEARCHES AND MEMBER3
def render_intent_template(template: str, intent: str, entities: Dict[str, Any], properties: List[Dict[str, Any]], sample_data: Dict[str, Any] = None) -> str:
    """Render an intent template by replacing known placeholders."""
    if not template:
        return ""

    replacements = {
        '{count}': str(len(properties)),
        '{property_type}': entities.get('property_type', 'property'),
        '{location}': entities.get('location', 'the area'),
        '{sale_type}': entities.get('sale_type', 'financing'),
        '{financing_type}': entities.get('financing_type', entities.get('sale_type', 'financing')),
        '{feature}': entities.get('feature', 'feature'),
        '{landmark}': entities.get('landmark', 'landmark'),
        '{bedrooms}': str(entities.get('bedrooms', '')),
        '{price_range}': entities.get('price_range', ''),
        '{need}': entities.get('need', entities.get('need_type', 'need')),
        '{price_quality}': entities.get('price_quality', 'good price'),
        '{neighborhood_info}': '',
    }

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

    if sample_data:
        for key, value in sample_data.items():
            if key.startswith('location_description') or key.startswith('average_') or key in ['documents_list', 'requirements_list', 'key_features', 'average_prices', 'ideal_for', 'property_types']:
                if value is not None:
                    replacements[f'{{{key}}}'] = '\n'.join([f"• {item}" for item in value]) if isinstance(value, list) else str(value)

    response = template
    for placeholder, replacement in replacements.items():
        response = response.replace(placeholder, '' if replacement is None else str(replacement))

    if intent == 'location_info' and entities.get('location') and training_data and 'location_profiles' in training_data:
        location_profile = training_data['location_profiles'].get(entities['location'])
        if location_profile:
            replacements['{neighborhood_info}'] = build_neighborhood_info(entities['location'], location_profile)
            for key, value in location_profile.items():
                if value is not None:
                    response = response.replace(f'{{{key}}}', str(value))

    return response


def build_neighborhood_info(location_name: str, location_profile: Dict[str, Any]) -> str:
    """Return neighborhood/living-area context for location_info responses."""
    known_neighborhoods = {
        'Batangas City': ['Poblacion', 'Alangilan', 'Balagtas', 'Kumintang', 'Bolbok'],
        'Lipa City': ['Poblacion', 'Marauoy', 'Sabang', 'Tambo', 'Balintawak'],
        'Nasugbu': ['Poblacion', 'Wawa', 'Punta Fuego area', 'Papaya', 'Natipuan'],
        'Tanauan City': ['Poblacion', 'Darasa', 'Sambat', 'Ambulong', 'Pagaspas'],
        'Sto. Tomas City': ['Poblacion', 'San Miguel', 'San Vicente', 'Sta. Anastacia', 'San Felix'],
        'Taal': ['Poblacion', 'Balisong', 'Halang', 'Caysasay', 'Ilog'],
        'Bauan': ['Poblacion', 'Aplaya', 'Manghinao', 'Sinala', 'San Roque'],
        'Balayan': ['Poblacion', 'Calan', 'Dalig', 'Gumamela', 'Sambat'],
        'San Juan': ['Poblacion', 'Subukin', 'Buhay na Sapa', 'Lipahan', 'Calubcub'],
        'Calatagan': ['Poblacion', 'Bucal', 'Balibago', 'Talisay', 'Lucsuhin'],
        'Mabini': ['Poblacion', 'Anilao East', 'Anilao Proper', 'Bagalangit', 'Mainit'],
        'Malvar': ['Poblacion', 'Santiago', 'San Juan', 'Luta Sur', 'Luta Norte'],
        'Rosario': ['Poblacion', 'Nasi', 'Mavalor', 'Bayawang', 'Quilib'],
        'Tuy': ['Poblacion', 'Acle', 'Bolbok', 'Luna', 'Rillo'],
        'Lian': ['Poblacion', 'Binubusan', 'Matabungkay', 'Lumaniag', 'Malaruhatan'],
        'Taysan': ['Poblacion', 'Bilogo', 'Palanas', 'Piña', 'Santo Niño'],
        'San Luis': ['Poblacion', 'Balite', 'Luya', 'Abiacao', 'San Isidro'],
        'Padre Garcia': ['Poblacion', 'Banaba', 'Maugat East', 'Maugat West', 'Payapa'],
        'Laurel': ['Poblacion', 'As-is', 'Niyugan', 'Ticub', 'Leviste'],
        'Agoncillo': ['Poblacion', 'Banyaga', 'Bilibinwang', 'Pansipit', 'Subic Ibaba'],
        'San Pascual': ['Poblacion', 'San Antonio', 'Sambat', 'Alalum', 'Pook ni Banal'],
        'Cuenca': ['Poblacion', 'Bungahan', 'Calzada', 'Dalipit East', 'Dalipit West'],
        'Alitagtag': ['Poblacion', 'Concepcion', 'Dominador East', 'Dominador West', 'Mabini'],
        'San Nicolas': ['Poblacion', 'Abelo', 'Balete', 'Bancoro', 'Poblacion East'],
        'Mataas Na Kahoy': ['Poblacion', 'Kinalaglagan', 'Nangkaan', 'Santol', 'Lumang Lipa'],
        'Talisay': ['Poblacion', 'Aya', 'Banga', 'Buco', 'Quiling'],
        'La Paz': ['Poblacion', 'Bugaan', 'Calaocan', 'Maugat', 'Tambo'],
        'Lemery': ['Poblacion', 'Bagong Pook', 'Bukal', 'Matingain', 'Payapa Ilaya'],
        'Ibaan': ['Poblacion', 'Bago', 'Bungahan', 'Calamias', 'Lapu-lapu'],
        'Lobo': ['Poblacion', 'Balatbat', 'Calumpit', 'Nagtalongtong', 'Sawang'],
        'Tingloy': ['Poblacion', 'Gamao', 'Mataas na Bayan', 'Papaya', 'San Jose']
    }

    if location_name in known_neighborhoods:
        return ', '.join(known_neighborhoods[location_name])

    key_features = location_profile.get('key_features', []) if location_profile else []
    if key_features:
        short = [str(x) for x in key_features[:3]]
        return "Mixed barangay areas; nearby strengths include: " + '; '.join(short)
    return "Mixed residential and commercial barangays; visit the area to compare traffic, access, and amenities."


def build_best_places_to_live(location_name: str, location_profile: Dict[str, Any], is_tl: bool = False) -> str:
    """Build top recommended places in a city/municipality with reasons."""
    neighborhood_text = build_neighborhood_info(location_name, location_profile or {})
    raw_places = [p.strip() for p in neighborhood_text.split(',') if p.strip()]
    top_places = raw_places[:3] if raw_places else ['Poblacion', 'Central area', 'Accessible barangay']

    key_features = ' '.join([str(x).lower() for x in (location_profile or {}).get('key_features', [])])
    lifestyle = str((location_profile or {}).get('lifestyle', '')).lower()
    signal_text = f"{key_features} {lifestyle}"

    if any(k in signal_text for k in ['school', 'university', 'college', 'educational']):
        reason = "malapit sa schools, daily essentials, at commuting routes" if is_tl else "close to schools, daily essentials, and commuting routes"
    elif any(k in signal_text for k in ['hospital', 'medical', 'healthcare']):
        reason = "malapit sa hospitals/clinics at essential services" if is_tl else "close to hospitals/clinics and essential services"
    elif any(k in signal_text for k in ['beach', 'coastal', 'resort']):
        reason = "may relaxed coastal lifestyle at tourism-driven amenities" if is_tl else "offers a relaxed coastal lifestyle with tourism-driven amenities"
    elif any(k in signal_text for k in ['industrial', 'business', 'commercial']):
        reason = "maganda para sa trabaho dahil sa access sa industrial/business zones" if is_tl else "works well for working professionals due to access to industrial/business zones"
    else:
        reason = "balanced ang access sa amenities, transport, at neighborhood convenience" if is_tl else "has balanced access to amenities, transport, and neighborhood convenience"

    if is_tl:
        lines = [f"• {place} — {reason}" for place in top_places]
        return "🏘️ **Top places na puwedeng pag-consider sa " + location_name + ":**\n" + '\n'.join(lines)

    lines = [f"• {place} — {reason}" for place in top_places]
    return "🏘️ **Top places to consider in " + location_name + ":**\n" + '\n'.join(lines)


def generate_response(intent: str, entities: Dict[str, Any], properties: List[Dict[str, Any]]) -> str:
    """Generate response based on intent and entities using training data templates"""

    original_query = entities.get('original_query', '')
    language = detect_language(original_query)
    is_tl = language == 'tl'
    
    # ========== HANDLE MEMBER3 INTENTS FIRST ==========
    if intent == 'find_property_for_need':
        return generate_family_needs_response(entities, properties, language)
    
    elif intent == 'find_with_feature':
        return generate_feature_price_response(entities, properties, language)
    
    elif intent == 'process_info':
        return generate_process_info_response(entities, properties, language)
    
    elif intent == 'match_needs':
        return generate_match_needs_response(entities, properties, language)
    
    
    # ========== HANDLE BASIC INTENTS FIRST ==========
    if intent == 'greeting':
        dataset_template = intent_templates.get('greeting', {}).get('tl' if is_tl else 'en', '')
        if dataset_template:
            return render_intent_template(dataset_template, intent, entities, properties)
        greeting_responses = [
            "👋 Kumusta! Ako si BahAI, ang iyong property assistant para sa Batangas.",
            "👋 Hi! Nandito ako para tulungan kang maghanap ng properties sa Batangas.",
            "👋 Welcome! Gabay mo ako sa paghanap ng properties sa Batangas.",
            "👋 Kumusta! Matutulungan kitang humanap ng house, condo, at apartment sa Batangas.",
            "👋 Hello! Paano kita matutulungan sa property search mo ngayon?"
        ] if is_tl else [
            "👋 Hello! I'm BahAI, your property assistant for Batangas.",
            "👋 Hi there! I'm here to help you find properties in Batangas.",
            "👋 Welcome! I'm BahAI, your guide to properties in Batangas.",
            "👋 Greetings! I can help you find houses, condos, and apartments in Batangas.",
            "👋 Hello! How can I assist you with property search in Batangas today?"
        ]
        return random.choice(greeting_responses)
    
    elif intent == 'thanks':
        dataset_template = intent_templates.get('thanks', {}).get('tl' if is_tl else 'en', '')
        if dataset_template:
            return render_intent_template(dataset_template, intent, entities, properties)
        thanks_responses = [
            "😊 Walang anuman! Masaya akong makatulong.",
            "😊 Walang problema! Sabihin mo lang kung may kailangan ka pa.",
            "😊 Buti nakatulong ako! Huwag mahiyang magtanong pa.",
            "😊 You're welcome! Kailangan mo pa ba ng ibang tulong?",
            "😊 Anytime! Nandito ako para sa property needs mo."
        ] if is_tl else [
            "😊 You're welcome! Happy to help.",
            "😊 My pleasure! Let me know if you need anything else.",
            "😊 Glad I could assist! Feel free to ask more questions.",
            "😊 You're most welcome! Need help with anything else?",
            "😊 Anytime! I'm here to help with all your property needs."
        ]
        return random.choice(thanks_responses)
    
    elif intent == 'help':
        if is_tl:
            return (
                "🤖 **BahAI Property Assistant**\n\n"
                "Matutulungan kita sa:\n"
                "• Paghahanap ng properties ayon sa location, budget, at features\n"
                "• Financing info (bank financing, installment, cash)\n"
                "• Impormasyon tungkol sa mga lugar sa Batangas\n"
                "• Matching ng property base sa needs mo (family, students, professionals)\n"
                "• Steps, requirements, at timeline sa pagbili/pag-rent\n\n"
                "Subukan mo: *'maghanap ng apartment sa Batangas City'* o *'bahay under 3M'*"
            )
        help_response = "🤖 **BahAI Property Assistant**\n\n"
        help_response += "I can help you with:\n\n"
        help_response += "🔍 **Property Search**\n"
        help_response += "• Find houses, condos, apartments\n"
        help_response += "• Search by location (Batangas City, Lipa, Nasugbu, etc.)\n"
        help_response += "• Filter by price range and bedrooms\n"
        help_response += "• Find properties with specific features\n\n"
        
        help_response += "💰 **Financing Information**\n"
        help_response += "• Properties with bank financing\n"
        help_response += "• Outright payment options\n"
        help_response += "• Installment plans\n"
        help_response += "• Specific bank filtering (BDO, BPI, Metrobank, etc.)\n\n"
        
        help_response += "📍 **Location Information**\n"
        help_response += "• Learn about different areas in Batangas\n"
        help_response += "• Lifestyle and amenities\n"
        help_response += "• Property types available\n\n"
        
        help_response += "👨‍👩‍👧‍👦 **Personalized Matching**\n"
        help_response += "• Properties for families\n"
        help_response += "• Homes for couples\n"
        help_response += "• Student accommodations\n"
        help_response += "• Professional housing needs\n\n"
        
        help_response += "📋 **Process Guidance**\n"
        help_response += "• Buying process steps\n"
        help_response += "• Required documents\n"
        help_response += "• Timeline information\n\n"
        
        help_response += "💡 **Try these examples:**\n"
        help_response += "• 'Find apartments in Batangas City'\n"
        help_response += "• 'Show me houses under 15M with 3 bedrooms'\n"
        help_response += "• 'Properties with BDO financing'\n"
        help_response += "• 'Show me properties with bank financing'\n"
        help_response += "• 'Tell me about Lipa City'\n"
        help_response += "• 'Find properties for family of 4'\n"
        
        return help_response
    
    elif intent == 'about_system':
        dataset_template = intent_templates.get('about_system', {}).get('tl' if is_tl else 'en', '')
        if dataset_template:
            return render_intent_template(dataset_template, intent, entities, properties)
        if is_tl:
            return (
                "🏠 **BahAI - Property Assistant mo sa Batangas**\n\n"
                "Isa akong AI chatbot na tumutulong sa paghahanap at pag-explore ng properties sa Batangas.\n\n"
                "**Ano ang kaya ko:**\n"
                "• Maghanap ng properties ayon sa location, type, at budget\n"
                "• Magbigay ng financing at payment info\n"
                "• Magbigay ng location insights at lifestyle notes\n"
                "• Mag-match ng properties sa needs mo\n\n"
                "Sabihin mo lang ang hinahanap mo, at tutulungan kita step by step."
            )
        about_response = "🏠 **BahAI - Your Batangas Property Assistant** 🏝️\n\n"
        about_response += "Hi there! I'm an AI-powered chatbot designed to help you find and explore "
        about_response += "properties in Batangas province, Philippines. I'm here to make your property search easy and enjoyable! 😊\n\n"
    
        about_response += "**✨ What I Can Do For You:**\n"
        about_response += "• 🔍 **Search properties** across Batangas cities and municipalities\n"
        about_response += "• 📋 **Provide detailed property information** and features\n"
        about_response += "• 💰 **Offer financing options** and payment information\n"
        about_response += "• 🏦 **Filter by specific banks** (BDO, BPI, Metrobank, etc.)\n"
        about_response += "• 🏖️ **Give location insights** and lifestyle information\n"
        about_response += "• 🎯 **Match properties** to your specific needs and preferences\n\n"
    
        about_response += "**📍 Coverage Areas:**\n"
        about_response += "• 🏙️ **Major Cities:** Batangas City, Lipa City, Tanauan City, Sto. Tomas City\n"
        about_response += "• 🏖️ **Beach Areas:** Nasugbu, Calatagan, Mabini, San Juan\n"
        about_response += "• 🏞️ **Heritage Towns:** Taal, Balayan, Lemery\n"
        about_response += "• 🌄 **And many more!** Malvar, Bauan, Taysan, Rosario, and across the province\n\n"
    
        about_response += "**🏡 Property Types I Can Help With:**\n"
        about_response += "• 🏠 Houses, Condos, Apartments, Townhouses\n"
        about_response += "• 💼 Commercial spaces, Offices, Retail stores\n"
        about_response += "• 🌊 Beachfront properties, Resort properties\n"
        about_response += "• 🌾 Residential lots, Agricultural land\n\n"
    
        about_response += "**💬 Just tell me what you're looking for!**\n"
        about_response += "Try saying something like:\n"
        about_response += "• *'Find apartments in Batangas City'*\n"
        about_response += "• *'Show me houses under 3M with 3 bedrooms'*\n"
        about_response += "• *'Properties with BDO financing'*\n"
        about_response += "• *'Tell me about Lipa City'*\n"
        about_response += "• *'Properties near beaches in Nasugbu'*\n\n"
    
        about_response += "I'm here to help you every step of the way. What kind of property are you looking for today? 😊🎉"
    
        return about_response

    # ========== BUYER ACCOUNT INTENTS WITH LANGUAGE DETECTION ==========
    elif intent.startswith('buyer_'):
        # Build buyer_responses from member5_buyer training data
        buyer_responses = {}
        if buyer_training_data and 'training_samples' in buyer_training_data:
            for sample in buyer_training_data['training_samples']:
                intent_name = sample.get('intent')
                if intent_name and intent_name.startswith('buyer_'):
                    en = sample.get('response_template_english', '')
                    tl = sample.get('response_template_tagalog', '')
                    if intent_name not in buyer_responses:
                        buyer_responses[intent_name] = {'en': en, 'tl': tl}
        
        # Get the response in the appropriate language
        intent_response = buyer_responses.get(intent, {})
        if language == 'tl' and 'tl' in intent_response:
            response = intent_response['tl']
        else:
            response = intent_response.get('en', f"👤 **Buyer Account: {intent.replace('buyer_', '').replace('_', ' ').title()}**\n\nI can help you with this buyer account feature. What specific information do you need?")
        
        return response

    elif intent == 'goodbye':
        dataset_template = intent_templates.get('goodbye', {}).get('tl' if is_tl else 'en', '')
        if dataset_template:
            return render_intent_template(dataset_template, intent, entities, properties)
        goodbye_responses = [
            "👋 Paalam! Bumalik ka lang anytime kung kailangan mo ng tulong sa property.",
            "👋 Ingat! Sana nakatulong ako sa property search mo sa Batangas.",
            "👋 Kita-kits! Nandito lang ako para sa property needs mo.",
            "👋 Take care! Balik ka lang kung kailangan mo pa ng property information.",
            "👋 Bye! Good luck sa paghahanap ng perfect property mo."
        ] if is_tl else [
            "👋 Goodbye! Feel free to return anytime for property assistance.",
            "👋 Farewell! Hope I helped with your property search in Batangas.",
            "👋 See you! Remember, I'm here to help with all your property needs.",
            "👋 Take care! Come back if you need more property information.",
            "👋 Bye! Wishing you success in finding your perfect property."
        ]
        return random.choice(goodbye_responses)
        
    # ========== HANDLE MEMBER3'S QUESTIONS FIRST ==========
    
    # Question 3: Family/space needs
    if entities.get('has_need_query'):
        need_type = entities.get('need_type', '')
        family_size = entities.get('family_size')
        
        # Filter properties for family size
        if need_type == 'family' and family_size:
            filtered_props = []
            for prop in properties:
                prop_bedrooms = prop.get('bedrooms', '')
                bedrooms = get_bedroom_count_from_string(prop_bedrooms)
                
                # Simple rule: need at least (family_size / 2) bedrooms
                min_bedrooms = max(1, family_size // 2)
                if bedrooms >= min_bedrooms:
                    filtered_props.append(prop)
            
            properties = filtered_props
        
        # ========== UPDATED: COUPLE-SPECIFIC RESPONSE ==========
        elif need_type == 'couple':
            filtered_props = []
            for prop in properties:
                # Try to get bedroom count from various sources
                prop_bedrooms = prop.get('bedrooms', '')
                prop_title = prop.get('title', '')
                
                # Extract from title if bedrooms field is empty
                if not prop_bedrooms or prop_bedrooms == 'Not specified':
                    # Look for bedroom patterns in title
                    title_lower = prop_title.lower()
                    bedroom_match = re.search(r'(\d+)\s*(?:bedroom|bed|br)', title_lower)
                    if bedroom_match:
                        prop_bedrooms = bedroom_match.group(1)
                
                bedrooms = get_bedroom_count_from_string(prop_bedrooms)
                
                # Couples typically need 0-2 bedrooms (studio to 2-bedroom)
                if bedrooms <= 2:  # Allow studio (0), 1-bedroom, 2-bedroom
                    filtered_props.append(prop)
                # If we can't determine bedroom count, include it anyway
                elif bedrooms == 0:  # Couldn't determine
                    filtered_props.append(prop)
            
            properties = filtered_props
            
            response = f"💑 **Properties for Couples**\n\n"
            if properties:
                # Sort by bedroom count (smaller first for couples)
                properties.sort(key=lambda x: get_bedroom_count_from_string(x.get('bedrooms', '')))
                
                response += f"I found {len(properties)} cozy properties perfect for couples:\n\n"
                for i, prop in enumerate(properties[:3]):
                    title = prop.get('title', f'Property {i+1}')
                    price = prop.get('price', 'Price not available')
                    location = prop.get('location', 'Location not specified')
                    bedrooms = prop.get('bedrooms', 'Not specified')
                    
                    # Add emoji based on bedroom count
                    bed_count = get_bedroom_count_from_string(bedrooms)
                    if bed_count == 0:
                        bed_emoji = "🏢 Studio"
                    elif bed_count == 1:
                        bed_emoji = "💑 1-Bedroom"
                    else:
                        bed_emoji = f"🏡 {bed_count}-Bedroom"
                        
                    response += f"{i+1}. **{title}** in {location}\n"
                    response += f"   {bed_emoji} - {price}\n\n"
                
                # Add couple-specific tips
                response += "💡 **Couple Tips:**\n"
                response += "   • Look for 1-2 bedroom units for coziness\n"
                response += "   • Consider romantic locations like beachfront\n"
                response += "   • Check for couple-friendly amenities (balcony, views)\n"
                response += "   • Look for properties with privacy features\n"
                response += "   • Consider proximity to dining and entertainment\n"
            else:
                response += "No properties found specifically for couples.\n\n"
                response += "💡 **Try:**\n"
                response += "   • Looking for 'studio' or '1-bedroom' properties\n"
                response += "   • Searching in romantic locations like Nasugbu\n"
                response += "   • Using 'find apartments' for more options\n"
            return response
        # ========== END COUPLE RESPONSE ==========
        
        # Generate response for other needs
        elif need_type:
            response = f"🏠 **Properties for {need_type}**\n\n"
            if properties:
                response += f"I found {len(properties)} properties:\n\n"
                for i, prop in enumerate(properties[:3]):
                    title = prop.get('title', f'Property {i+1}')
                    price = prop.get('price', 'Price not available')
                    location = prop.get('location', 'Location not specified')
                    response += f"{i+1}. **{title}** in {location} - {price}\n"
                
                # Add need-specific tips
                if need_type == 'students':
                    response += "\n💡 **Student Tips:**\n"
                    response += "   • Look for properties near universities\n"
                    response += "   • Check for WiFi and study areas\n"
                    response += "   • Consider shared accommodations\n"
                elif need_type == 'professionals':
                    response += "\n💡 **Professional Tips:**\n"
                    response += "   • Look for properties near business districts\n"
                    response += "   • Check for security and amenities\n"
                    response += "   • Consider commute time to work\n"
                elif need_type == 'retirees':
                    response += "\n💡 **Retiree Tips:**\n"
                    response += "   • Look for single-story properties\n"
                    response += "   • Check for medical facilities nearby\n"
                    response += "   • Consider peaceful neighborhoods\n"
                elif need_type == 'business':
                    response += "\n💡 **Business Tips:**\n"
                    response += "   • Look for high-traffic locations\n"
                    response += "   • Check for commercial zoning\n"
                    response += "   • Consider customer accessibility\n"
            else:
                response += "No properties found.\n"
            return response
    
    # Question 5: Feature with price quality
    elif entities.get('has_feature_price_query'):
        price_quality = entities.get('price_quality', 'good price')
        feature = entities.get('feature', 'features')
        
        response = f"✅ **Properties with {feature} at {price_quality}**\n\n"
        if properties:
            # Filter for affordable properties
            filtered_props = []
            for prop in properties:
                price_numeric = prop.get('price_numeric', 0)
                # Apply affordability threshold
                if price_quality in ['cheap', 'affordable']:
                    if prop.get('listing_type') == 'rent' and price_numeric <= 15000:
                        filtered_props.append(prop)
                    elif prop.get('listing_type') == 'sale' and price_numeric <= 3000000:
                        filtered_props.append(prop)
                    else:
                        continue
                else:
                    filtered_props.append(prop)
            
            properties = filtered_props
            
            if properties:
                response += f"I found {len(properties)} properties:\n\n"
                for i, prop in enumerate(properties[:3]):
                    title = prop.get('title', f'Property {i+1}')
                    price = prop.get('price', 'Price not available')
                    location = prop.get('location', 'Location not specified')
                    response += f"{i+1}. **{title}** in {location} - {price}\n"
                
                response += "\n💡 **Price Tips:**\n"
                response += "   • Compare similar properties\n"
                response += "   • Check for hidden costs\n"
                response += "   • Consider long-term value\n"
            else:
                response += f"No properties found at {price_quality}.\n\n"
                response += "💡 Try:\n"
                response += "   • Adjusting your price expectations\n"
                response += "   • Looking in different areas\n"
                response += "   • Considering smaller units\n"
        else:
            response += "No properties found.\n"
        return response
    
    # Question 8: Process info
    elif entities.get('has_process_query'):
        process_type = entities.get('process_type', 'process')
        property_type = entities.get('property_type', 'property')
        
        response = f"📋 **{process_type.title()} Information for {property_type}**\n\n"
        
        if process_type == 'steps':
            response += "**Typical Steps:**\n1. Search & selection\n2. Due diligence\n3. Offer & negotiation\n4. Financing\n5. Payment\n6. Registration\n"
        elif process_type == 'how':
            response += "**How to proceed:**\n• Determine your budget\n• Choose location\n• Select property type\n• Arrange financing\n• Complete paperwork\n"
        elif process_type == 'timeline':
            response += "**Typical Timeline:**\n• Search: 1-4 weeks\n• Processing: 2-8 weeks\n• Total: 1-3 months\n"
        elif process_type == 'requirements':
            response += "**Basic Requirements:**\n• Valid IDs\n• Proof of income\n• Financial documents\n• Property documents\n"
        
        response += "\n💡 Contact us for specific details.\n"
        return response
    
    # Question 10: Lifestyle matching
    elif entities.get('has_match_query'):
        response = "🎯 **Properties Matching Your Needs**\n\n"
        if properties:
            response += f"I found {len(properties)} properties that could work for you:\n\n"
            for i, prop in enumerate(properties[:3]):
                title = prop.get('title', f'Property {i+1}')
                price = prop.get('price', 'Price not available')
                location = prop.get('location', 'Location not specified')
                features = prop.get('features', [])
                features_str = ", ".join(features[:3]) if features else "Standard features"
                response += f"{i+1}. **{title}** in {location} - {price}\n   Features: {features_str}\n"
            
            response += "\n💡 **Matching Tips:**\n"
            response += "   • Consider your daily routine\n"
            response += "   • Think about commute times\n"
            response += "   • Match amenities to your lifestyle\n"
        else:
            response += "No matching properties found.\n\n"
            response += "💡 Try:\n"
            response += "   • Being more specific about your needs\n"
            response += "   • Adjusting your budget\n"
            response += "   • Considering different locations\n"
        return response
    
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
        
        if is_tl:
            response = f"❌ **Walang posted properties para sa {criteria_desc}**\n\n"
            response += "Wala akong nahanap na properties na tumutugma sa search mo.\n\n"
            response += "💡 **Suggestions:**\n"
        else:
            response = f"❌ **No posted properties for {criteria_desc}**\n\n"
            response += "I couldn't find any properties matching your search.\n\n"
            response += "💡 **Suggestions:**\n"
        
        if location and location != 'the specified location':
            response += f"   • Subukan ang nearby locations imbes na {location}\n" if is_tl else f"   • Try nearby locations instead of {location}\n"
        
        if entities.get('max_price'):
            response += "   • Taasan ang budget o price range mo\n" if is_tl else "   • Increase your budget or price range\n"
        
        if entities.get('exact_bedrooms') is not None:
            response += "   • Subukan ang ibang bedroom count\n" if is_tl else "   • Try different bedroom counts\n"
        
        response += "   • Bumalik mamaya para sa bagong listings\n" if is_tl else "   • Check back later for new listings\n"
        response += "   • Makipag-ugnayan para sa custom property search\n" if is_tl else "   • Contact us for custom property searches\n"
        
        return response
    
    # ========== NEW: Handle criteria-based searches ==========
    if intent == 'find_property_with_criteria':
        return generate_criteria_search_response(entities, properties, language)
    
    # ========== Handle general property searches (no location) ==========
    if intent == 'find_property' and entities.get('has_general_search'):
        return generate_general_search_response(entities, properties, language)
    
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
    if is_tl:
        default_responses = {
            'find_property': "Naiintindihan ko na naghahanap ka ng properties. Pwede mo bang i-specify ang location o property type?",
            'find_near_landmark': "Matutulungan kitang maghanap ng properties malapit sa landmarks. Anong landmark ang gusto mo?",
            'financing': "Makakapagbigay ako ng financing options. Aling financing type ang gusto mo?",
            'location_info': "Maaari kitang bigyan ng impormasyon tungkol sa mga lugar sa Batangas. Anong location ang gusto mong malaman?",
            'find_with_feature': "Matutulungan kitang maghanap ng properties na may specific feature. Anong feature ang hanap mo?",
            'find_ready_property': "Matutulungan kitang maghanap ng ready-to-move-in properties. Saang location ka interesado?",
            'process_info': "Maipapaliwanag ko ang proseso sa pagbili ng property. Anong process ang gusto mong malaman?",
            'match_needs': "Matutulungan kitang mag-match ng properties sa needs mo. Ano ang specific requirements mo?",
            'find_property_for_need': "Makakahanap ako ng properties para sa specific needs. Anong need ang hinahanap mo?",
            'find_property_with_criteria': "Makakahanap ako ng properties ayon sa criteria mo. Ano ang criteria mo?",
            'unknown': "Naiintindihan ko na naghahanap ka ng property information sa Batangas. Pwede mo bang i-detail ang kailangan mo?"
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
            
            if best_sample and (
                'response_template' in best_sample
                or 'response_template_english' in best_sample
                or 'response_template_tagalog' in best_sample
            ):
                if is_tl and best_sample.get('response_template_tagalog'):
                    template = best_sample.get('response_template_tagalog', '')
                elif best_sample.get('response_template_english'):
                    template = best_sample.get('response_template_english', '')
                else:
                    template = best_sample.get('response_template', '')

                return render_intent_template(template, intent, entities, properties, best_sample)
    
    # Fallback to dataset-level intent templates (member1/member2/member3/member4_general)
    dataset_template = intent_templates.get(intent, {}).get('tl' if is_tl else 'en', '')
    if not dataset_template:
        dataset_template = intent_templates.get(intent, {}).get('en', '')
    if dataset_template:
        return render_intent_template(dataset_template, intent, entities, properties)

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
                neighborhood_info = build_neighborhood_info(location_name, location_profile)
                best_places_block = build_best_places_to_live(location_name, location_profile, is_tl=is_tl)

                if is_tl:
                    response = f"📍 **Tungkol sa {location_name}**\n"
                    response += f"**Description:** {description}\n\n"
                    response += f"**Lifestyle:** {lifestyle}\n\n"
                    response += f"**Neighborhood at Living Experience:** {neighborhood_info}\n\n"
                    response += f"{best_places_block}\n\n"
                else:
                    response = f"📍 **About {location_name}**\n"
                    response += f"**Description:** {description}\n\n"
                    response += f"**Lifestyle:** {lifestyle}\n\n"
                    response += f"**Neighborhoods & Living Experience:** {neighborhood_info}\n\n"
                    response += f"{best_places_block}\n\n"
                
                if 'key_features' in location_profile and location_profile['key_features']:
                    response += "**Key Features:**\n" if not is_tl else "**Mga Key Features:**\n"
                    for feature in location_profile['key_features']:
                        response += f"• {feature}\n"
                    response += "\n"
                
                if 'average_prices' in location_profile and location_profile['average_prices']:
                    response += "**Average Property Prices:**\n" if not is_tl else "**Average na Presyo ng Property:**\n"
                    for price_info in location_profile['average_prices']:
                        response += f"• {price_info}\n"
                    response += "\n"
                
                if 'ideal_for' in location_profile and location_profile['ideal_for']:
                    response += (f"**Ideal For:** {', '.join(location_profile['ideal_for'])}\n\n"
                                 if not is_tl else
                                 f"**Ideal Para Kanino:** {', '.join(location_profile['ideal_for'])}\n\n")
                
                if 'property_types' in location_profile and location_profile['property_types']:
                    response += (f"**Property Types Available:** {', '.join(location_profile['property_types'])}\n"
                                 if not is_tl else
                                 f"**Mga Available na Uri ng Property:** {', '.join(location_profile['property_types'])}\n")
                
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
            neighborhood_info = build_neighborhood_info(location_name, {})
            best_places_block = build_best_places_to_live(location_name, {}, is_tl=is_tl)
            if is_tl:
                response = f"📍 **Tungkol sa {location_name}**\n\n"
                response += f"{location_name} ay isa sa mga mahalagang lugar sa Batangas na may iba't ibang property options.\n\n"
                response += f"**Neighborhood at Living Experience:** {neighborhood_info}\n\n"
                response += f"{best_places_block}\n\n"
                response += "💡 Para mas accurate, maaari mong sabihin kung ang hanap mo ay student-friendly, family-friendly, o malapit sa work/schools/hospitals."
            else:
                response = f"📍 **About {location_name}**\n\n"
                response += f"{location_name} is one of the key locations in Batangas with a mix of property options.\n\n"
                response += f"**Neighborhoods & Living Experience:** {neighborhood_info}\n\n"
                response += f"{best_places_block}\n\n"
                response += "💡 For more precise recommendations, tell me if you prefer student-friendly, family-friendly, or near work/schools/hospitals areas."
    
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
            response += "• BDO Unibank\n• BPI\n• Metrobank\n• UnionBank\n• RCBC\n• Security Bank\n• Other accredited banks\n"
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
def generate_general_search_response(entities: Dict[str, Any], properties: List[Dict[str, Any]], language: str = 'en') -> str:
    """Generate response for general property searches without location"""
    
    property_type = entities.get('property_type', 'properties')
    property_type_display = property_type.replace('_', ' ').title() if property_type else 'properties'
    
    is_tl = language == 'tl'

    if properties:
        # Group properties by city for better organization
        properties_by_city = defaultdict(list)
        for prop in properties:
            city = prop.get('city', 'Unknown City')
            properties_by_city[city].append(prop)
        
        # Sort cities by number of properties
        sorted_cities = sorted(properties_by_city.items(), key=lambda x: len(x[1]), reverse=True)
        
        if is_tl:
            response = f"🔍 **Mga available na {property_type_display} sa Batangas**\n\n"
            response += f"May nahanap akong {len(properties)} {property_type_display.lower()} sa iba't ibang locations:\n\n"
        else:
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
        if is_tl:
            response += "\n💡 **Tips para mas magandang result:**\n"
            response += "   • Maglagay ng location: *'find apartments in Batangas City'*\n"
            response += "   • I-specify ang budget: *'find houses under 3M'*\n"
            response += "   • Magdagdag ng features: *'find condos with swimming pool'*\n"
            response += "   • I-specify ang needs: *'find properties for family'*\n"
        else:
            response += "\n💡 **Tips for better results:**\n"
            response += "   • Add a location: *'find apartments in Batangas City'*\n"
            response += "   • Specify budget: *'find houses under 3M'*\n"
            response += "   • Add features: *'find condos with swimming pool'*\n"
            response += "   • Specify needs: *'find properties for family'*\n"
        
        # Suggest popular locations based on property type
        if property_type in ['house', 'condo', 'apartment']:
            if is_tl:
                response += "\n📍 **Mga sikat na location para sa " + property_type_display.lower() + ":**\n"
                response += "   • Batangas City (urban living, malapit sa port)\n"
                response += "   • Lipa City (cool climate, educational hub)\n"
                response += "   • Nasugbu (beachfront, vacation homes)\n"
                response += "   • Sto. Tomas City (malapit sa Metro Manila)\n"
                response += "   • Tanauan City (Taal Lake views)\n"
            else:
                response += "\n📍 **Popular locations for " + property_type_display.lower() + ":**\n"
                response += "   • Batangas City (urban living, near port)\n"
                response += "   • Lipa City (cool climate, educational hub)\n"
                response += "   • Nasugbu (beachfront, vacation homes)\n"
                response += "   • Sto. Tomas City (near Metro Manila)\n"
                response += "   • Tanauan City (Taal Lake views)\n"
        
    else:
        if is_tl:
            response = f"❌ **Walang posted na available na {property_type_display.lower()}**\n\n"
            response += "💡 **Subukan ito:**\n"
            response += "   • I-check kung tama ang spelling ng property type\n"
            response += "   • Subukan ang mas broad na search: *'find properties'*\n"
            response += f"   • Maglagay ng location: *'find {property_type_display.lower()} in Lipa City'*\n"
            response += "   • Bumalik mamaya para sa bagong listings\n"
        else:
            response = f"❌ **No posted {property_type_display.lower()} available**\n\n"
            response += "💡 **Try these suggestions:**\n"
            response += "   • Check if the property type is spelled correctly\n"
            response += "   • Try a broader search: *'find properties'*\n"
            response += f"   • Specify a location: *'find {property_type_display.lower()} in Lipa City'*\n"
            response += "   • Check back later for new listings\n"
    
    return response

# Placeholder functions for Member3 responses
def generate_family_needs_response(entities: Dict[str, Any], properties: List[Dict[str, Any]], language: str = 'en') -> str:
    """Generate response for family needs queries"""
    need_type = entities.get('need_type') or 'family'
    family_size = entities.get('family_size') or 4
    
    is_tl = language == 'tl'
    response = f"👨‍👩‍👧‍👦 **Mga property para sa {need_type.title()}**\n\n" if is_tl else f"👨‍👩‍👧‍👦 **Properties for {need_type.title()}**\n\n"
    
    if properties:
        response += f"May nahanap akong {len(properties)} properties na bagay para sa pamilyang may {family_size} miyembro:\n\n" if is_tl else f"I found {len(properties)} properties suitable for a family of {family_size}:\n\n"
        for i, prop in enumerate(properties[:3]):
            title = prop.get('title', f'Property {i+1}')
            price = prop.get('price', 'Price not available')
            location = prop.get('location', 'Location not specified')
            bedrooms = prop.get('bedrooms', 'Not specified')
            response += f"{i+1}. **{title}** in {location} - {price}\n"
            response += f"   🛏️ {bedrooms} bedroom{'s' if bedrooms != '1' else ''}\n\n"
        
        if is_tl:
            response += "💡 **Family Tips:**\n"
            response += "   • Maghanap ng properties na malapit sa schools at parks\n"
            response += "   • Pumili ng neighborhoods na may family-friendly amenities\n"
            response += "   • I-check ang safety at security features\n"
        else:
            response += "💡 **Family Tips:**\n"
            response += "   • Look for properties near schools and parks\n"
            response += "   • Consider neighborhoods with family-friendly amenities\n"
            response += "   • Check for safety and security features\n"
    else:
        if is_tl:
            response += f"Walang nahanap na properties para sa pamilyang may {family_size} miyembro.\n\n"
            response += "💡 **Subukan:**\n"
            response += "   • I-adjust ang family size\n"
            response += "   • Tumingin sa ibang locations\n"
            response += "   • Subukan ang ibang needs\n"
        else:
            response += f"No properties found for a family of {family_size}.\n\n"
            response += "💡 **Try:**\n"
            response += "   • Adjusting your family size\n"
            response += "   • Looking in different locations\n"
            response += "   • Considering smaller families or different needs\n"
    
    return response

def generate_feature_price_response(entities: Dict[str, Any], properties: List[Dict[str, Any]], language: str = 'en') -> str:
    """Generate response for feature with price quality queries"""
    feature = entities.get('feature') or 'feature'
    price_quality = entities.get('price_quality') or 'good price'
    
    is_tl = language == 'tl'
    response = f"💰 **Mga property na may {feature.title()} at {price_quality.title()} na presyo**\n\n" if is_tl else f"💰 **{feature.title()} Properties at {price_quality.title()} Prices**\n\n"
    
    if properties:
        response += f"May nahanap akong {len(properties)} properties:\n\n" if is_tl else f"I found {len(properties)} properties:\n\n"
        for i, prop in enumerate(properties[:3]):
            title = prop.get('title', f'Property {i+1}')
            price = prop.get('price', 'Price not available')
            location = prop.get('location', 'Location not specified')
            response += f"{i+1}. **{title}** in {location} - {price}\n"
    else:
        if is_tl:
            response += f"Walang nahanap na properties na may {feature} at {price_quality} na presyo.\n\n"
            response += "💡 **Subukan:**\n"
            response += "   • I-adjust ang budget expectations mo\n"
            response += "   • Tumingin ng ibang features\n"
            response += "   • Isama ang kalapit na areas\n"
        else:
            response += f"No properties found with {feature} at {price_quality} prices.\n\n"
            response += "💡 **Try:**\n"
            response += "   • Adjusting your budget expectations\n"
            response += "   • Looking for different features\n"
            response += "   • Considering nearby areas\n"
    
    return response

def generate_process_info_response(entities: Dict[str, Any], properties: List[Dict[str, Any]], language: str = 'en') -> str:
    """Generate response for process information queries"""
    process_type = entities.get('process_type') or 'process'
    
    is_tl = language == 'tl'
    response = f"📋 **Impormasyon sa Property {process_type.title()}**\n\n" if is_tl else f"📋 **Property {process_type.title()} Information**\n\n"
    
    if 'step' in process_type or 'process' in process_type:
        response += "**Standard Property Buying Process:**\n"
        response += "1️⃣ **Search & Selection** - Find properties that match your needs\n"
        response += "2️⃣ **Due Diligence** - Verify property documents and ownership\n"
        response += "3️⃣ **Negotiation** - Discuss price and terms with the seller\n"
        response += "4️⃣ **Reservation** - Pay reservation fee to secure the property\n"
        response += "5️⃣ **Financing** - Secure loan or prepare full payment\n"
        response += "6️⃣ **Contract Signing** - Execute Deed of Absolute Sale\n"
        response += "7️⃣ **Payment** - Complete the payment\n"
        response += "8️⃣ **Transfer of Title** - Register property in your name\n\n"
    
    elif 'document' in process_type or 'requirement' in process_type:
        response += "**Common Requirements:**\n"
        response += "• 📄 Valid government-issued IDs\n"
        response += "• 💼 Proof of income (payslips, ITR, bank statements)\n"
        response += "• 🏢 Certificate of Employment\n"
        response += "• 📍 Proof of billing\n"
        response += "• 💍 Marriage certificate (if applicable)\n"
        response += "• 🔢 Tax Identification Number (TIN)\n\n"
    
    elif 'timeline' in process_type:
        response += "**Typical Timeline:**\n"
        response += "• Property Search: 1-4 weeks\n"
        response += "• Due Diligence: 3-7 days\n"
        response += "• Loan Approval: 1-2 weeks\n"
        response += "• Document Processing: 2-4 weeks\n"
        response += "• Total Process: 1-3 months\n\n"
    
    response += "💡 Makipag-ugnayan sa amin para sa mas specific na gabay sa pagbili ng property!" if is_tl else "💡 Contact us for specific guidance on your property purchase journey!"
    return response

def generate_match_needs_response(entities: Dict[str, Any], properties: List[Dict[str, Any]], language: str = 'en') -> str:
    """Generate response for lifestyle matching queries"""
    lifestyle = entities.get('lifestyle') or 'your needs'
    budget_hint = None
    if entities.get('max_price'):
        max_price = entities['max_price']
        budget_hint = f"under ₱{max_price/1000000:.1f}M" if max_price >= 1000000 else f"under ₱{max_price:,.0f}"
    focus_landmark = entities.get('lifestyle_focus_landmark') or entities.get('landmark')
    
    is_tl = language == 'tl'
    response = f"🎯 **Mga property na match sa {lifestyle.title()}**\n\n" if is_tl else f"🎯 **Properties Matching {lifestyle.title()}**\n\n"
    if budget_hint or focus_landmark:
        if is_tl:
            if budget_hint:
                response += f"• Budget filter: {budget_hint}\n"
            if focus_landmark:
                response += f"• Lifestyle location focus: near {focus_landmark}\n"
            response += "\n"
        else:
            if budget_hint:
                response += f"• Budget filter: {budget_hint}\n"
            if focus_landmark:
                response += f"• Lifestyle location focus: near {focus_landmark}\n"
            response += "\n"
    
    if properties:
        response += f"May nahanap akong {len(properties)} properties na tugma sa preferences mo:\n\n" if is_tl else f"I found {len(properties)} properties that align with your preferences:\n\n"
        for i, prop in enumerate(properties[:3]):
            title = prop.get('title', f'Property {i+1}')
            price = prop.get('price', 'Price not available')
            location = prop.get('location', 'Location not specified')
            features = prop.get('features', [])
            features_str = ", ".join(features[:2]) if features else "Standard features"
            response += f"{i+1}. **{title}** in {location} - {price}\n"
            response += f"   ✨ {features_str}\n\n"
        
        if is_tl:
            response += "💡 **Gaano ito ka-match?**\n"
            response += "   • Isaalang-alang ang daily commute mo\n"
            response += "   • I-check ang nearby amenities\n"
            response += "   • Bisitahin ang neighborhood\n"
        else:
            response += "💡 **How well does it match?**\n"
            response += "   • Consider your daily commute\n"
            response += "   • Check nearby amenities\n"
            response += "   • Visit the neighborhood\n"
    else:
        if is_tl:
            response += "Walang nahanap na properties na tugma sa lifestyle preferences mo.\n\n"
            response += "💡 **Subukan:**\n"
            response += "   • Ilarawan ang ideal lifestyle mo\n"
            response += "   • I-specify ang preferred features\n"
            response += "   • Pumili ng ibang location\n"
            response += "   • Maglagay ng budget (hal. under 2M)\n"
        else:
            response += "No properties found matching your lifestyle preferences.\n\n"
            response += "💡 **Try:**\n"
            response += "   • Describing your ideal lifestyle\n"
            response += "   • Specifying preferred features\n"
            response += "   • Selecting a different location\n"
            response += "   • Adding a specific budget (e.g., under 2M)\n"
    
    return response

# API ENDPOINTS
@app.route('/api/nearby_landmarks', methods=['GET'])
def nearby_landmarks():
    """Return nearest landmarks (school/hospital/mall/etc.) for map proof in property details."""
    try:
        lat = request.args.get('lat', type=float)
        lng = request.args.get('lng', type=float)
        category_filter = (request.args.get('category', 'all') or 'all').lower().strip()
        limit = request.args.get('limit', default=3, type=int)
        limit = max(1, min(limit, 8))

        if lat is None or lng is None:
            return jsonify({'success': False, 'error': 'lat and lng are required'}), 400

        landmarks_data = _load_landmarks_data()
        categories = landmarks_data.get('categories', {})
        if not categories:
            return jsonify({'success': True, 'results': []})

        if category_filter != 'all' and category_filter not in categories:
            return jsonify({'success': False, 'error': f"unknown category '{category_filter}'"}), 400

        categories_to_scan = [category_filter] if category_filter != 'all' else list(categories.keys())
        results = []
        for category in categories_to_scan:
            points = categories.get(category, {}).get('points', [])
            for pt in points:
                pt_lat = pt.get('lat')
                pt_lng = pt.get('lng')
                if pt_lat is None or pt_lng is None:
                    continue
                dist_km = _haversine_km(float(lat), float(lng), float(pt_lat), float(pt_lng))
                results.append({
                    'category': category,
                    'name': pt.get('name', f'{category.title()} point'),
                    'city': pt.get('city', ''),
                    'lat': float(pt_lat),
                    'lng': float(pt_lng),
                    'distance_km': round(float(dist_km), 2)
                })

        results.sort(key=lambda x: x['distance_km'])
        return jsonify({'success': True, 'results': results[:limit]})
    except Exception as e:
        logger.error(f"❌ Error in /api/nearby_landmarks: {e}")
        return jsonify({'success': False, 'error': str(e)}), 500


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

                # Buyer auth/account overrides (higher priority than model confusion)
                if any(phrase in query_lower for phrase in [
                    'sign up requirements', 'what do i need to sign up',
                    'requirements for sign up', 'ano requirements para mag sign up',
                    'anong kailangan para mag sign up'
                ]):
                    if intent != 'buyer_signup_requirements':
                        logger.info(f"⚠️ FORCE OVERRIDE: Changing intent from {intent} to buyer_signup_requirements")
                    intent = 'buyer_signup_requirements'
                    confidence = 0.99
                elif any(phrase in query_lower for phrase in [
                    'password requirements', 'password rules', 'requirements sa password',
                    'ano dapat laman ng password', 'strong password'
                ]):
                    if intent != 'buyer_signup_password':
                        logger.info(f"⚠️ FORCE OVERRIDE: Changing intent from {intent} to buyer_signup_password")
                    intent = 'buyer_signup_password'
                    confidence = 0.99
                elif any(phrase in query_lower for phrase in [
                    'phone number format', 'mobile number format', 'format ng phone',
                    'paano format ng phone number'
                ]):
                    if intent != 'buyer_signup_phone':
                        logger.info(f"⚠️ FORCE OVERRIDE: Changing intent from {intent} to buyer_signup_phone")
                    intent = 'buyer_signup_phone'
                    confidence = 0.99
                elif any(phrase in query_lower for phrase in [
                    'how to sign up', 'sign up', 'signup', 'register', 'create account',
                    'create buyer account', 'buyer registration', 'paano mag sign up',
                    'paano gumawa ng account', 'magparehistro', 'gusto ko mag sign up'
                ]):
                    if intent != 'buyer_signup':
                        logger.info(f"⚠️ FORCE OVERRIDE: Changing intent from {intent} to buyer_signup")
                    intent = 'buyer_signup'
                    confidence = 0.99
                elif any(phrase in query_lower for phrase in [
                    'how do save properties work', 'how do liked properties work', 'how do like properties work',
                    'how do saved properties work', 'how to save properties', 'saved properties',
                    'liked properties', 'like properties', 'save properties', 'favorite properties',
                    'paano mag save ng property', 'paano gumagana ang liked properties'
                ]):
                    if intent != 'buyer_liked_saved_how':
                        logger.info(f"⚠️ FORCE OVERRIDE: Changing intent from {intent} to buyer_liked_saved_how")
                    intent = 'buyer_liked_saved_how'
                    confidence = 0.99
                elif any(phrase in query_lower for phrase in [
                    'for family', 'family of', 'for couples', 'for couple', 'for single'
                ]):
                    if intent != 'find_property_for_need':
                        logger.info(f"⚠️ FORCE OVERRIDE: Family/space query detected, changing intent from {intent} to find_property_for_need")
                    intent = 'find_property_for_need'
                    confidence = 0.99
                elif any(phrase in query_lower for phrase in [
                    'for students', 'properties for students', 'student housing', 'student accommodations',
                    'for professionals', 'working professionals', 'single professional',
                    'for retirees', 'for investors', 'doctor', 'nurse', 'gym', 'active lifestyle'
                ]):
                    if intent != 'match_needs':
                        logger.info(f"⚠️ FORCE OVERRIDE: Lifestyle query detected, changing intent from {intent} to match_needs")
                    intent = 'match_needs'
                    confidence = 0.99
                
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

                # Pattern 1B: generic property search ("find apartments", "show me houses", etc.)
                property_verbs = ['find', 'search', 'look for', 'show me', 'i need', 'need', 'want']
                property_types = [
                    'apartment', 'apartments', 'house', 'houses', 'home', 'homes',
                    'condo', 'condos', 'condominium', 'townhouse', 'townhouses',
                    'commercial', 'office', 'retail', 'warehouse', 'lot', 'land',
                    'bahay', 'kondo'
                ]
                info_only_terms = ['about', 'what is', 'who are you', 'system', 'chatbot', 'ai assistant']
                has_property_verb = any(v in query_lower for v in property_verbs)
                has_property_type = any(t in query_lower for t in property_types)
                has_info_only_term = any(t in query_lower for t in info_only_terms)
                if has_property_verb and has_property_type and not has_info_only_term:
                    if intent != 'find_property':
                        logger.info(f"⚠️ FORCE OVERRIDE: Generic property search detected, changing intent from {intent} to find_property")
                    intent = 'find_property'
                    confidence = max(confidence, 0.99)

                # Pattern 1C: criteria search with bed/bath/price should be find_property_with_criteria
                has_price_criteria = bool(re.search(r'\b(under|below|less than|maximum|max|up to|\d+\s*m)\b', query_lower))
                has_bed_criteria = bool(re.search(r'\b(\d+)\s*(bed|bedroom|br)s?\b', query_lower))
                has_bath_criteria = bool(re.search(r'\b(\d+)\s*(bath|bathroom|banyo)s?\b', query_lower))
                if has_property_type and (has_price_criteria or has_bed_criteria or has_bath_criteria):
                    if intent != 'find_property_with_criteria':
                        logger.info(f"⚠️ FORCE OVERRIDE: Criteria pattern detected, changing intent from {intent} to find_property_with_criteria")
                    intent = 'find_property_with_criteria'
                    confidence = max(confidence, 0.99)
                
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
        entities['original_query'] = query
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
            has_specific_bank = entities.get('bank_name') is not None
            has_pagibig = entities.get('has_pagibig_query', False)
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
            
            if (has_sale_type or has_specific_bank or has_pagibig) and (is_property_search or (has_search_action and has_property_type)):
                # User is asking for properties with specific sale type or bank
                logger.info(f"🔍 Financing query is a property search - searching Firestore")
                properties = search_firestore_properties(entities)
            elif entities.get('financing_info_request'):
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
        
        # ========== UPDATED: Generate response using appropriate function ==========
        # Check for financing-related queries first
        if entities.get('sale_type') or entities.get('bank_name') or entities.get('has_pagibig_query'):
            
            if entities.get('query_type') == 'property_search':
                # Property search with financing criteria
                financing_response = generate_financing_property_response(entities, properties)
                if financing_response:
                    response_text = financing_response
                else:
                    response_text = generate_response(intent, entities, properties)
            
            elif entities.get('financing_info_request'):
                # Information request about financing
                info_response = generate_financing_info_response(entities)
                if info_response:
                    response_text = info_response
                else:
                    response_text = generate_response(intent, entities, properties)
            
            else:
                # Fallback
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
            'has_sale_type_query': entities.get('sale_type') is not None,
            'has_specific_bank': entities.get('bank_name') is not None,
            'has_pagibig_query': entities.get('has_pagibig_query', False),
            'financing_level': entities.get('financing_level'),
            'query_type': entities.get('query_type'),
            'has_member3_query': any([
                entities.get('has_need_query'),
                entities.get('has_feature_price_query'),
                entities.get('has_process_query'),
                entities.get('has_match_query')
            ])
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

    # Check for SIMPLE greetings first (single word or very short)
    simple_greetings = ['hi', 'hello', 'hey', 'howdy', 'yo', 'sup']
    if query_lower in simple_greetings or query_lower in ['hi there', 'hello there', 'hey there']:
        return 'greeting'
    
    # Check for time-based greetings
    if any(query_lower.startswith(g) for g in ['good morning', 'good afternoon', 'good evening']):
        return 'greeting'
    
    # NOW check for about_system queries (these are longer and ask about the system)
    about_system_indicators = [
        'what are you', 'who are you', 'what is this system', 'what is this chatbot',
        'what is bahAI', 'tell me about yourself', 'introduce yourself', 'what do you do',
        'what can you do', 'what is your purpose', 'system overview', 'about the system',
        'what is the system about',
        'what services do you offer', 'give me an introduction', 'explain what you do'
    ]
    
    for indicator in about_system_indicators:
        if indicator in query_lower:
            return 'about_system'

    # ========== BUYER ACCOUNT INTENTS ==========
    if any(phrase in query_lower for phrase in [
        'sign up requirements', 'what do i need to sign up',
        'requirements for sign up', 'ano requirements para mag sign up',
        'anong kailangan para mag sign up'
    ]):
        return 'buyer_signup_requirements'

    if any(phrase in query_lower for phrase in [
        'password requirements', 'password rules', 'requirements sa password',
        'ano dapat laman ng password', 'strong password'
    ]):
        return 'buyer_signup_password'

    if any(phrase in query_lower for phrase in [
        'phone number format', 'mobile number format', 'format ng phone',
        'paano format ng phone number'
    ]):
        return 'buyer_signup_phone'

    if any(phrase in query_lower for phrase in [
        'how to sign up', 'sign up', 'signup', 'register', 'create account',
        'sign up buyer', 'buyer sign up', 'create buyer account',
        'become a buyer', 'register as buyer', 'buyer registration',
        'paano mag sign up', 'paano gumawa ng account', 'magparehistro'
    ]):
        return 'buyer_signup'

    if any(phrase in query_lower for phrase in [
        'buyer login', 'login to buyer', 'sign in buyer',
        'log in as buyer', 'buyer sign in'
    ]):
        return 'buyer_login'

    if any(phrase in query_lower for phrase in [
        'login with google', 'google login', 'sign in with google',
        'continue with google'
    ]):
        return 'buyer_login_google'

    if any(phrase in query_lower for phrase in [
        'forgot password', 'reset password', 'can\'t remember password',
        'change password', 'new password'
    ]):
        return 'buyer_forgot_password'

    if any(phrase in query_lower for phrase in [
        'email verification', 'verify email', 'verification email',
        'didn\'t receive email', 'confirm email'
    ]):
        return 'buyer_email_verification'

    if any(phrase in query_lower for phrase in [
        'verify otp', 'enter otp', 'otp code', '6-digit code',
        'verification code'
    ]):
        return 'buyer_verify_otp'

    if any(phrase in query_lower for phrase in [
        'resend otp', 'resend code', 'send again', 'new code'
    ]):
        return 'buyer_resend_otp'

    if any(phrase in query_lower for phrase in [
        'login error', 'can\'t login', 'login failed',
        'invalid credentials', 'wrong password'
    ]):
        return 'buyer_login_errors'

    # REMOVED: account locked section

    if any(phrase in query_lower for phrase in [
        'logout', 'sign out', 'log out', 'exit account'
    ]):
        return 'buyer_logout'


    if any(phrase in query_lower for phrase in [
        'account settings', 'profile settings', 'edit profile',
        'update settings', 'change settings'
    ]):
        return 'buyer_account_settings'

    if any(phrase in query_lower for phrase in [
        'update profile', 'edit profile', 'change name',
        'update email', 'change phone', 'update information'
    ]):
        return 'buyer_update_profile'

    if any(phrase in query_lower for phrase in [
        'guest', 'browse without login', 'guest mode', 'view without account',
        'pwede ba mag browse kahit walang account', 'guest access', 'browse as guest'
    ]):
        return 'buyer_guest_access'

    if any(phrase in query_lower for phrase in [
        'kyc', 'verify identity', 'what is kyc', 'how does kyc work',
        'kyc verification', 'guest vs logged in', 'what can guest access',
        'ano ang kyc', 'paano mag kyc', 'bakit kailangan kyc'
    ]):
        return 'buyer_kyc'

    if any(phrase in query_lower for phrase in [
        'how does the chatbot work', 'how does the ai work', 'what is this chatbot',
        'what is the ai assistant', 'who is the ai assistant', 'what is bahai assistant',
        'how do i use the chatbot', 'what can the ai do', 'explain the chatbot',
        'paano gumagana ang chatbot', 'paano gamitin ang chatbot', 'ano ang ai assistant'
    ]):
        return 'buyer_chatbot_how'

    if any(phrase in query_lower for phrase in [
        'how does the buyer dashboard work', 'what is the buyer dashboard',
        'after login where do i go', 'what do i see when i log in',
        'successfully logged in then what', 'where am i redirected after login',
        'buyer interface', 'what pages do buyers have', 'paano gumagana ang buyer dashboard',
        'pagkatapos mag login saan ako mapupunta'
    ]):
        return 'buyer_dashboard_flow'

    if any(phrase in query_lower for phrase in [
        'how do recommendations work', 'how are recommendations fetched',
        'unlock recommendations', 'paano gumagana ang recommendations'
    ]):
        return 'buyer_recommendations_how'

    if any(phrase in query_lower for phrase in [
        'how do i message brokers', 'how do messages work', 'can i message without kyc',
        'contact broker', 'paano mag message sa broker'
    ]):
        return 'buyer_messages_how'

    if any(phrase in query_lower for phrase in [
        'how do i save properties', 'what are saved properties', 'liked properties',
        'where are my saved properties', 'paano mag save ng property',
        'how do save properties work', 'how do like properties work',
        'how do liked properties work', 'save properties', 'like properties',
        'favorite properties', 'bookmarked properties'
    ]):
        return 'buyer_liked_saved_how'
        
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
        r'^where\s+to\s+live\s+in\s+\w+',
        r'^best\s+place\s+to\s+live\s+in\s+\w+',
        r'^saan\s+maganda\s+tumira\s+sa\s+\w+',
    ]
    
    for pattern in location_info_patterns:
        if re.search(pattern, query_lower):
            return 'location_info'
    
    # ========== CHECK FOR MEMBER3 QUERIES ==========
    
    # Family/needs queries - EXPANDED TO MATCH TRAINING DATA
    if any(phrase in query_lower for phrase in [
        'for family', 
        'family of', 
        'family properties',
        'family house',
        'family home',
        'family condo',
        'family apartment',
        'family sized',
        'family-size',
        'big family',
        'large family',
        'small family'
    ]):
        return 'find_property_for_need'

    # Lifestyle matching queries routed to Question 10 intent
    if any(phrase in query_lower for phrase in [
        'for students', 'student housing', 'student accommodations',
        'for professionals', 'working professionals', 'single professional',
        'for retirees', 'retirement', 'for business', 'home business',
        'for investors', 'doctor', 'nurse', 'medical worker',
        'gym', 'active lifestyle'
    ]):
        return 'match_needs'
    
    # Price quality queries
    if any(keyword in query_lower for keyword in ['good price', 'cheap', 'affordable', 'reasonable', 'good value']):
        return 'find_with_feature'
    
    # Process info queries
    if any(keyword in query_lower for keyword in ['steps for', 'how to', 'process of', 'timeline', 'requirements', 'documents']):
        return 'process_info'
    
    # Lifestyle matching queries
    if any(keyword in query_lower for keyword in ['match my', 'suitable for', 'fitting my', 'what matches', 'recommendations']):
        return 'match_needs'
    
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
    
    # Specific bank detection
    bank_names = [
        'bdo', 'bpi', 'metrobank', 'landbank', 'unionbank', 
        'security bank', 'rcbc', 'pnb', 'china bank', 'maybank'
    ]
    for bank in bank_names:
        if bank in query_lower:
            return 'financing'
    
    # Pag-IBIG detection
    if 'pag-ibig' in query_lower or 'pagibig' in query_lower:
        return 'financing'
    
    # Financing information queries
    if any(phrase in query_lower for phrase in [
        'what documents', 'requirements for', 'how to get loan',
        'housing loan', 'mortgage documents',
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
    
    # Prioritize ready-to-move intent before generic property-search fallback
    if any(phrase in query_lower for phrase in [
        'ready to move', 'ready for occupancy', 'available now',
        'immediate occupancy', 'move in ready', 'ready now',
        'ready to occupy', 'immediate move in', 'available immediately',
        'rfo', 'pwede na lipatan', 'handa na tirahan', 'lipat agad'
    ]):
        return 'find_ready_property'

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
    
    # Property for need intent (Question 3: family/space count)
    if any(phrase in query_lower for phrase in [
        'for family', 'family of', 'big family', 'large family',
        'for couple', 'for couples', 'for single', 'for workers'
    ]):
        return 'find_property_for_need'
    
    # Match needs intent
    if any(phrase in query_lower for phrase in [
        'match my', 'suitable for', 'fitting my', 'appropriate for',
        'compatible with', 'what matches', 'recommendations for'
    ]):
        return 'match_needs'

    if any(phrase in query_lower for phrase in [
        'for students', 'student housing', 'student accommodations',
        'for professionals', 'working professionals', 'single professional',
        'for retirees', 'for business', 'for investors', 'doctor',
        'nurse', 'medical worker', 'gym', 'active lifestyle'
    ]):
        return 'match_needs'

    # Implicit lifestyle matching intent
    if any(phrase in query_lower for phrase in [
        'i am a doctor', 'doctor ako', 'nurse ako', 'medical worker',
        'i am a student', 'student ako', 'single professional', 'young professional',
        'retiree', 'retired'
    ]) and any(term in query_lower for term in ['property', 'properties', 'bahay', 'apartment', 'condo', 'house']):
        return 'match_needs'
    
    # Property with criteria intent
    if re.search(r'\b(\d+)\s*(bed|bedroom|br|bath|bathroom|banyo)s?\b', query_lower) and any(word in query_lower for word in [
        'apartment', 'apartments', 'house', 'houses', 'condo', 'condos', 'property', 'properties', 'bahay'
    ]):
        return 'find_property_with_criteria'

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
        'about', 'information on', 'details about',
        'neighborhood', 'neighbourhood', 'barangay', 'community vibe',
        'kamusta tumira', 'living experience',
        'where to live in', 'best place to live in', 'best neighborhood in',
        'saan maganda tumira', 'magandang tirhan ba'
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
        'service': 'BahAI Property Chatbot',
        'version': '3.9',  # Updated version with specific bank filtering and 3-level financing
        'deployed_url': 'https://bahai.onrender.com',
        'firebase_connected': db is not None,
        'firebase_env_exists': firebase_env_exists,
        'model_loaded': vectorizer is not None and classifier is not None,
        'model_intents': model_classes if vectorizer else [],
        'training_data_loaded': bool(training_data),
        'supports_general_searches': True,
        'supports_criteria_searches': True,
        'supports_sale_type_filtering': True,
        'supports_specific_bank_filtering': True,
        'supports_pagibig_filtering': True,
        'financing_levels_supported': ['sale_type', 'specific_bank', 'pagibig'],
        'member3_features': True,
        'member3_questions_supported': [
            'Family/space needs detection',
            'Feature with price quality',
            'Process information',
            'Lifestyle matching'
        ],
        'buyer_intents_supported': [
    'buyer_signup',
    'buyer_signup_requirements',
    'buyer_signup_password',
    'buyer_signup_phone',
    'buyer_login',
    'buyer_guest_access',
    'buyer_login_google',
    'buyer_forgot_password',
    'buyer_email_verification',
    'buyer_verify_otp',
    'buyer_resend_otp',
    'buyer_login_errors',
    'buyer_logout',
    'buyer_account_settings',
    'buyer_update_profile',
    'buyer_kyc',
    'buyer_chatbot_how',
    'buyer_dashboard_flow',
    'buyer_recommendations_how',
    'buyer_messages_how',
    'buyer_liked_saved_how'
],
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
        # Member3 test queries
        "show me properties for family of 4",
        "find affordable apartments",
        "what are the steps to buy a house",
        "find properties that match my lifestyle",
        
        # Sale type queries - Level 1
        "show me properties with bank financing",
        "find houses with outright payment",
        "properties with installment plan",
        
        # Specific bank queries - Level 2
        "properties with BDO financing",
        "find condos with BPI loan",
        "houses with Metrobank financing",
        "properties that accept UnionBank",
        
        # Pag-IBIG queries - Level 3
        "pag-ibig financing properties",
        "show me properties eligible for pag-ibig",
        "houses with pag-ibig loan",
        
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

        # Buyer account test queries
        "how do I sign up as a buyer",
        "paano mag sign up bilang buyer",
        "what are the password requirements",
        "I forgot my password",
        "how to login to buyer dashboard",
        "verify my email",
        "resend verification code",
        "contact buyer support"
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
                    'sale_type': entities.get('sale_type'),
                    'bank_name': entities.get('bank_name'),
                    'has_pagibig_query': entities.get('has_pagibig_query', False),
                    'financing_level': entities.get('financing_level'),
                    'query_type': entities.get('query_type'),
                    'max_price': entities.get('max_price'),
                    'exact_bedrooms': entities.get('exact_bedrooms'),
                    'has_need_query': entities.get('has_need_query'),
                    'need_type': entities.get('need_type'),
                    'family_size': entities.get('family_size'),
                    'has_feature_price_query': entities.get('has_feature_price_query'),
                    'has_process_query': entities.get('has_process_query'),
                    'has_match_query': entities.get('has_match_query'),
                    'is_member3_query': any([
                        entities.get('has_need_query'),
                        entities.get('has_feature_price_query'),
                        entities.get('has_process_query'),
                        entities.get('has_match_query')
                    ]),
                    'is_criteria_search': intent == 'find_property_with_criteria',
                    'is_financing_query': entities.get('sale_type') is not None or entities.get('bank_name') is not None or entities.get('has_pagibig_query', False)
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
        'supports_sale_type_filtering': True,
        'supports_specific_bank_filtering': True,
        'supports_pagibig_filtering': True,
        'member3_features_available': True
    })

# ==================== MODEL LOADING (RUNS ON IMPORT) ====================
print("\n" + "="*60)
print("🚀 BAHAI PROPERTY CHATBOT BACKEND v3.9")
print("   (Added: Specific Bank Filtering & 3-Level Financing)")
print("="*60)

print("📝 Step 1: Loading NLU model...")
load_nlu_model()
diagnose_model_file()
verify_model_file() 
ensure_all_intents() 


print("📝 Step 2: Loading training data...")
load_training_data()

print("📝 Step 3: Printing status...")
print(f"\n📂 NLU Model: {'✅ Loaded' if vectorizer else '❌ Not loaded'}")
print(f"📚 Training Data: {'✅ Loaded' if training_data else '❌ Not loaded'}")
print(f"🔥 Firebase: {'✅ Connected' if db else '❌ Not connected'}")
print(f"🔍 General Searches: {'✅ Supported'}")
print(f"🔍 Criteria Searches: {'✅ Supported'}")
print(f"💰 Sale Type Filtering: {'✅ Supported (bank_financing, outright, installment)'}")
print(f"🏦 Specific Bank Filtering: {'✅ Supported (BDO, BPI, Metrobank, etc.)'}")
print(f"🏠 Pag-IBIG Filtering: {'✅ Supported'}")
print(f"📊 Financing Levels: {['sale_type', 'specific_bank', 'pagibig']}")
print(f"👨‍👩‍👧‍👦 Member3 Features: {'✅ Enabled'}")
print(f"   • Family/space needs detection")
print(f"   • Feature with price quality")
print(f"   • Process information")
print(f"   • Lifestyle matching")

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

print("\n🔍 Example Member3 queries to try:")
print("   • 'show me properties for family of 4' (family needs)")
print("   • 'find affordable apartments' (price quality)")
print("   • 'what are the steps to buy a house' (process info)")
print("   • 'find properties that match my lifestyle' (lifestyle matching)")

print("\n🔍 Example FINANCING queries (3 levels):")
print("   • Level 1 - Sale Type: 'show me properties with bank financing'")
print("   • Level 2 - Specific Bank: 'properties with BDO financing'")
print("   • Level 3 - Pag-IBIG: 'show me pag-ibig eligible properties'")
print("   • Info Request: 'what are the requirements for BDO housing loan'")

print("\n🔍 Other example queries:")
print("   • 'show me houses under 15M with 3 bedrooms' (criteria search)")
print("   • 'find condos below 10M with 2 bedrooms' (criteria search)")
print("   • 'find apartments' (general search)")
print("   • 'find apartments in batangas city' (location-specific)")

print("="*60 + "\n")

# ==================== MAIN BLOCK (for local development only) ====================
if __name__ == '__main__':
    port = int(os.environ.get("PORT", 10000))
    app.run(host="0.0.0.0", port=port)