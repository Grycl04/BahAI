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


# Set up logging
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)


app = Flask(__name__)
CORS(app, resources={r"/api/*": {"origins": "*"}})


# CONFIGURATION
MODEL_PATH = 'models/nlu_model.pkl'
SHARED_DATA_PATH = 'data/shared'
BATANGAS_DATA_FILE = 'batangas_complete.json'


# Global variables
vectorizer = None
classifier = None
shared_data = None
db = None
_properties_cache = None
_cache_timestamp = None
CACHE_DURATION = 300  # 5 minutes


# Property type mappings based on your database
PROPERTY_TYPE_MAPPINGS = {
    # Residential
    'house': ['house', 'bungalow', 'duplex', 'townhouse', 'village_lot'],
    'condo': ['condo', 'condominium', 'condo_unit', 'penthouse', 'studio', 'loft'],
    'apartment': ['apartment', 'apartment_unit', 'boarding_house', 'room', 'dormitory'],
   
    # Commercial
    'commercial': ['commercial', 'office_unit', 'retail_space', 'food_stall',
                   'shop', 'showroom', 'commercial_building', 'office_space'],
    'warehouse': ['warehouse', 'storage_unit', 'factory', 'workshop'],
   
    # Land
    'land': ['land', 'lot', 'commercial_lot', 'agricultural_land', 'development_land',
             'industrial_lot', 'residential_lot', 'vacant_lot', 'beachfront'],
   
    # Special
    'special': ['resort_property', 'event_venue', 'parking_area',
                'school_property', 'hospitality', 'sports_facility']
}


# Initialize Firebase
try:
    cred = credentials.Certificate('../serviceAccountKey.json')
    firebase_admin.initialize_app(cred)
    db = firestore.client()
    logger.info("✅ Firebase connected successfully")
except Exception as e:
    logger.error(f"❌ Firebase connection failed: {e}")
    db = None


# Load NLU model
def load_nlu_model():
    """Load the trained NLU model"""
    global vectorizer, classifier
    try:
        if os.path.exists(MODEL_PATH):
            with open(MODEL_PATH, 'rb') as f:
                model_data = pickle.load(f)
            vectorizer = model_data.get('vectorizer')
            classifier = model_data.get('classifier')
            logger.info(f"✅ NLU model loaded successfully (v{model_data.get('version', '1.0')})")
            logger.info(f"📊 Model intents: {len(model_data.get('classes', []))}")
        else:
            logger.warning(f"❌ Model file not found: {MODEL_PATH}")
    except Exception as e:
        logger.error(f"❌ Error loading NLU model: {e}")


# Load shared data
def load_shared_data():
    """Load all shared data files"""
    global shared_data
   
    shared_data = {
        'questions': {},
        'synonyms': {},
        'batangas': {},
        'landmarks': {}
    }
   
    try:
        # Load all_questions.json
        questions_file = os.path.join(SHARED_DATA_PATH, 'all_questions.json')
        if os.path.exists(questions_file):
            with open(questions_file, 'r', encoding='utf-8') as f:
                shared_data['questions'] = json.load(f)
            logger.info("✅ Loaded question templates")
       
        # Load synonyms.json
        synonyms_file = os.path.join(SHARED_DATA_PATH, 'synonyms.json')
        if os.path.exists(synonyms_file):
            with open(synonyms_file, 'r', encoding='utf-8') as f:
                shared_data['synonyms'] = json.load(f)
            logger.info("✅ Loaded synonyms data")
       
        # Load batangas_complete.json
        batangas_file = os.path.join(SHARED_DATA_PATH, BATANGAS_DATA_FILE)
        if os.path.exists(batangas_file):
            with open(batangas_file, 'r', encoding='utf-8') as f:
                shared_data['batangas'] = json.load(f)
            logger.info("✅ Loaded Batangas data")
       
        return shared_data
       
    except Exception as e:
        logger.error(f"❌ Error loading shared data: {e}")
        return shared_data


def extract_entities_from_query(query: str) -> Dict[str, Any]:
    query_lower = query.lower()
    entities = {}
   
    # Extract property type using your database mappings
    for category, variations in PROPERTY_TYPE_MAPPINGS.items():
        for variation in variations:
            if variation in query_lower:
                entities['property_type'] = category
                break
        if 'property_type' in entities:
            break
   
    # If no specific type found, check for generic property terms
    if 'property_type' not in entities:
        generic_terms = ['property', 'properties', 'real estate', 'realestate']
        for term in generic_terms:
            if term in query_lower:
                entities['property_type'] = 'property'
                break
   
    # Extract location - look for city names
    if shared_data and 'batangas' in shared_data:
        batangas_locations = shared_data['batangas'].get('batangas_locations', {})
        for location in batangas_locations.keys():
            if location.lower() in query_lower:
                entities['location'] = location
                break
   
    # Extract price ranges
    price_patterns = [
        r'under\s*(?:p?\s*)?(\d+\.?\d*)\s*(million|m|k|thousand)?',
        r'below\s*(?:p?\s*)?(\d+\.?\d*)\s*(million|m|k|thousand)?',
        r'less than\s*(?:p?\s*)?(\d+\.?\d*)\s*(million|m|k|thousand)?',
        r'(?:p?\s*)?(\d+\.?\d*)\s*(million|m|k|thousand)?',
        r'(\d+\.?\d*)\s*(?:million|m|k|thousand)?\s*pesos',
        r'p?\s*(\d+(?:,\d{3})*(?:\.\d{2})?)\s*(?:php|pesos)?',
    ]
   
    for pattern in price_patterns:
        match = re.search(pattern, query_lower)
        if match:
            price_str = match.group(1).replace(',', '')
            unit = match.group(2) if match.group(2) else ''
           
            try:
                price = float(price_str)
                if 'm' in unit.lower() or 'million' in unit.lower():
                    entities['max_price'] = price * 1000000
                elif 'k' in unit.lower() or 'thousand' in unit.lower():
                    entities['max_price'] = price * 1000
                else:
                    entities['max_price'] = price
                break
            except:
                pass
   
    # Extract bedrooms
    bedroom_patterns = [
        r'(\d+)\s*bedroom',
        r'(\d+)\s*bed',
        r'(\d+)\s*br',
        r'studio',
        r'(\d+)\s*bedrooms'
    ]
   
    for pattern in bedroom_patterns:
        match = re.search(pattern, query_lower)
        if match:
            if 'studio' in query_lower:
                entities['bedrooms'] = 'studio'
            else:
                try:
                    entities['bedrooms'] = int(match.group(1))
                except:
                    pass
            break
   
    # Extract transaction type
    if 'rent' in query_lower or 'rental' in query_lower:
        entities['transaction_type'] = 'rent'
    elif 'sale' in query_lower or 'buy' in query_lower or 'purchase' in query_lower:
        entities['transaction_type'] = 'sale'
    elif 'lease' in query_lower:
        entities['transaction_type'] = 'lease'
   
    # FINANCING DETECTION - IMPROVED
    financing_keywords = [
        'bank financing', 'bank loan', 'mortgage', 'pag-ibig',
        'in-house financing', 'installment', 'financing options',
        'housing loan', 'home loan', 'property loan', 'developer financing',
        'cash', 'financing', 'loan'
    ]
   
    for keyword in financing_keywords:
        if keyword in query_lower:
            entities['financing_type'] = keyword
            # Add a flag that this is a financing query
            entities['is_financing_query'] = True
            break
    
    # Check if it's a financing-related query
    if any(term in query_lower for term in ['financing', 'loan', 'mortgage', 'installment', 'payment method']):
        entities['is_financing_query'] = True
        if 'financing_type' not in entities:
            # Default to bank financing if not specified
            entities['financing_type'] = 'bank financing'
   
    # Check for ready-to-move terms
    ready_terms = ['ready to move in', 'ready for occupancy', 'available now',
                   'immediate occupancy', 'move in ready', 'ready now']
    for term in ready_terms:
        if term in query_lower:
            entities['ready_status'] = True
            break
   
    logger.info(f"📝 Extracted entities: {entities}")
    return entities


def get_all_firestore_properties():
    """Get ALL properties from Firestore with caching"""
    global _properties_cache, _cache_timestamp
   
    # Check cache first
    if (_properties_cache is not None and _cache_timestamp is not None and
        (datetime.now() - _cache_timestamp).total_seconds() < CACHE_DURATION):
        logger.info("♻️ Using cached properties")
        return _properties_cache.copy()
   
    if not db:
        logger.error("❌ No database connection")
        return []
   
    properties = []
    logger.info("📡 Fetching ALL properties from Firestore...")
   
    try:
        # Query ALL properties
        properties_ref = db.collection('properties')
        docs = properties_ref.stream()
       
        for doc in docs:
            try:
                prop_data = doc.to_dict()
                prop_data['id'] = doc.id
               
                # Standardize property data for your database structure
                standardized_prop = standardize_property_data(prop_data)
                properties.append(standardized_prop)
            except Exception as e:
                logger.error(f"❌ Error processing property {doc.id}: {e}")
                continue
       
        # Update cache
        _properties_cache = properties.copy()
        _cache_timestamp = datetime.now()
       
        logger.info(f"✅ Successfully fetched {len(properties)} properties")
        return properties
       
    except Exception as e:
        logger.error(f"❌ Error in get_all_firestore_properties: {e}")
        return []


def standardize_property_data(prop_data: Dict[str, Any]) -> Dict[str, Any]:
    """Standardize property data for your Firestore structure"""
    standardized = {
        'id': prop_data.get('id', ''),
        'title': prop_data.get('title', 'Untitled Property'),
        'propertyType': prop_data.get('propertyType', ''),
        'propertyCategory': prop_data.get('propertyCategory', ''),
        'description': prop_data.get('description', ''),
        'city': prop_data.get('city', ''),
        'address': prop_data.get('address', ''),
        'province': prop_data.get('province', 'Batangas'),
        'type': prop_data.get('type', ''),  # rent, lease, sale
        'status': prop_data.get('status', 'available'),
        'userType': prop_data.get('userType', ''),
        'createdAt': prop_data.get('createdAt'),
        'updatedAt': prop_data.get('updatedAt')
    }
   
    # Handle pricing based on transaction type
    transaction_type = prop_data.get('type', '')
   
    if transaction_type == 'rent':
        standardized['monthlyRent'] = prop_data.get('monthlyRent', 0)
        standardized['pricingType'] = 'rental'
        # Additional rental fields
        standardized['bedrooms'] = prop_data.get('bedrooms', '')
        standardized['bathrooms'] = prop_data.get('bathrooms', '')
        standardized['floorArea'] = prop_data.get('floorArea', 0)
        standardized['furnishing'] = prop_data.get('furnishing', '')
        standardized['amenities'] = prop_data.get('amenities', [])
       
    elif transaction_type == 'sale':
        standardized['salePrice'] = prop_data.get('salePrice', 0)
        standardized['pricingType'] = 'sale'
        standardized['saleType'] = prop_data.get('saleType', '')
        standardized['priceNegotiable'] = prop_data.get('priceNegotiable', 'no')
        # Additional sale fields
        standardized['bedrooms'] = prop_data.get('bedrooms', '')
        standardized['bathrooms'] = prop_data.get('bathrooms', '')
        standardized['floorArea'] = prop_data.get('floorArea', 0)
        standardized['lotArea'] = prop_data.get('lotArea', 0)
        standardized['furnishing'] = prop_data.get('furnishing', '')
       
    elif transaction_type == 'lease':
        standardized['annualRent'] = prop_data.get('annualRent', 0)
        standardized['pricingType'] = 'lease'
        standardized['leaseType'] = prop_data.get('leaseType', '')
        standardized['leaseDuration'] = prop_data.get('leaseDuration', 0)
        standardized['totalArea'] = prop_data.get('totalArea', 0)
   
    # Handle photos
    photos = []
    if 'imageUrls' in prop_data and isinstance(prop_data['imageUrls'], list):
        photos = prop_data['imageUrls']
    elif 'photos' in prop_data and isinstance(prop_data['photos'], list):
        photos = prop_data['photos']
   
    standardized['photos'] = photos[:5] if photos else []
   
    # Create a search-friendly location field
    city = standardized.get('city', '').lower()
    province = standardized.get('province', '').lower()
    standardized['search_location'] = f"{city} {province}".strip()
   
    # Create a search-friendly property type field
    prop_type = standardized.get('propertyType', '').lower()
    prop_category = standardized.get('propertyCategory', '').lower()
    standardized['search_type'] = f"{prop_type} {prop_category}".strip()
   
    return standardized


def filter_properties_by_entities(properties: List[Dict[str, Any]], entities: Dict[str, Any]) -> List[Dict[str, Any]]:
    """Filter properties based on extracted entities with flexible matching"""
    if not properties:
        return []
   
    filtered_properties = []
   
    for prop in properties:
        match = True
       
        # Filter by location
        if 'location' in entities:
            search_location = entities['location'].lower()
            prop_location = prop.get('search_location', '').lower()
           
            # Check if location appears anywhere in the property location
            if search_location not in prop_location:
                # Try checking city separately
                prop_city = prop.get('city', '').lower()
                if search_location not in prop_city:
                    # Try partial matching
                    search_words = search_location.split()
                    if not any(word in prop_location for word in search_words if len(word) > 2):
                        match = False
       
        # Filter by property type
        if match and 'property_type' in entities:
            search_type = entities['property_type'].lower()
            prop_type = prop.get('search_type', '').lower()
           
            # Check if property type matches
            if search_type not in prop_type:
                # Check property category mappings
                if search_type in PROPERTY_TYPE_MAPPINGS:
                    variations = PROPERTY_TYPE_MAPPINGS[search_type]
                    if not any(variation in prop_type for variation in variations):
                        match = False
       
        # Filter by transaction type
        if match and 'transaction_type' in entities:
            search_transaction = entities['transaction_type'].lower()
            prop_transaction = prop.get('type', '').lower()
           
            if search_transaction != prop_transaction:
                match = False
       
        # Filter by max price
        if match and 'max_price' in entities:
            max_price = entities['max_price']
           
            if prop.get('pricingType') == 'sale':
                sale_price = prop.get('salePrice', 0)
                if sale_price > max_price:
                    match = False
            elif prop.get('pricingType') == 'rental':
                monthly_rent = prop.get('monthlyRent', 0)
                if monthly_rent > max_price:
                    match = False
            elif prop.get('pricingType') == 'lease':
                annual_rent = prop.get('annualRent', 0)
                if annual_rent > max_price:
                    match = False
       
        # Filter by bedrooms
        if match and 'bedrooms' in entities:
            search_bedrooms = entities['bedrooms']
            prop_bedrooms = prop.get('bedrooms', '')
           
            if isinstance(search_bedrooms, int):
                if isinstance(prop_bedrooms, str):
                    try:
                        prop_bedrooms_int = int(prop_bedrooms)
                        if prop_bedrooms_int < search_bedrooms:
                            match = False
                    except:
                        # If can't parse bedrooms, include property
                        pass
       
        # FILTER FOR FINANCING - IMPROVED
        if match and entities.get('is_financing_query'):
            financing_type = entities.get('financing_type', '').lower()
           
            if financing_type:
                if 'bank' in financing_type:
                    # Check property for financing indicators
                    sale_type = prop.get('saleType', '').lower()
                    description = prop.get('description', '').lower()
                    user_type = prop.get('userType', '').lower()
                   
                    # Look for financing indicators in the property
                    financing_indicators = [
                        'bank', 'loan', 'mortgage', 'financing', 
                        'pag-ibig', 'installment', 'payment plan',
                        'housing loan', 'home loan', 'property loan'
                    ]
                   
                    has_financing = False
                    # Check description for financing terms
                    if any(term in description for term in financing_indicators):
                        has_financing = True
                    # Check saleType
                    elif any(term in sale_type for term in financing_indicators):
                        has_financing = True
                    # Check userType - if seller, they might offer financing
                    elif 'seller' in user_type or 'owner' in user_type:
                        has_financing = True
                    # For properties with sale type, assume they might have financing
                    elif prop.get('pricingType') == 'sale':
                        has_financing = True
                   
                    if not has_financing:
                        match = False
                elif 'pag-ibig' in financing_type:
                    # Similar logic for Pag-IBIG
                    description = prop.get('description', '').lower()
                    if 'pag-ibig' not in description:
                        match = False
                elif 'cash' in financing_type:
                    # For cash properties, don't filter out
                    pass
            else:
                # General financing query - include all sale properties
                if prop.get('pricingType') != 'sale':
                    match = False
       
        if match:
            filtered_properties.append(prop)
   
    return filtered_properties


def search_firestore_properties(entities: Dict[str, Any]) -> List[Dict[str, Any]]:
    """Main function to search properties"""
    try:
        # Get ALL properties
        all_properties = get_all_firestore_properties()
       
        if not all_properties:
            logger.warning("⚠️ No properties found in Firestore")
            return []
       
        logger.info(f"📊 Total properties in database: {len(all_properties)}")
       
        # Filter properties based on entities
        filtered_properties = filter_properties_by_entities(all_properties, entities)
       
        logger.info(f"✅ Found {len(filtered_properties)} properties matching criteria")
       
        # Sort by price (lowest first)
        def get_sort_price(prop):
            if prop.get('pricingType') == 'sale':
                return prop.get('salePrice', float('inf'))
            elif prop.get('pricingType') == 'rental':
                return prop.get('monthlyRent', float('inf'))
            elif prop.get('pricingType') == 'lease':
                return prop.get('annualRent', float('inf'))
            return float('inf')
       
        filtered_properties.sort(key=get_sort_price)
       
        return filtered_properties
       
    except Exception as e:
        logger.error(f"❌ Error in search_firestore_properties: {e}")
        return []


def generate_response(intent: str, entities: Dict[str, Any], properties: List[Dict[str, Any]]) -> str:
    """Generate natural language response based on intent"""
   
    batangas_data = shared_data.get('batangas', {}).get('batangas_locations', {}) if shared_data else {}
   
    if intent == "find_property":
        if properties:
            prop_type = entities.get('property_type', 'properties')
            location = entities.get('location', 'Batangas area')
            count = len(properties)
           
            response_parts = [f"I found {count} {prop_type}{'s' if count != 1 else ''} in {location}."]
           
            # Add summary of properties
            top_properties = properties[:5]
            for i, prop in enumerate(top_properties, 1):
                title = prop.get('title', 'Property')
                city = prop.get('city', 'Location')
               
                # Format price
                price_info = ""
                if prop.get('pricingType') == 'sale':
                    price = prop.get('salePrice', 0)
                    price_info = f"₱{price:,.0f}"
                elif prop.get('pricingType') == 'rental':
                    price = prop.get('monthlyRent', 0)
                    price_info = f"₱{price:,.0f}/month"
                elif prop.get('pricingType') == 'lease':
                    price = prop.get('annualRent', 0)
                    price_info = f"₱{price:,.0f}/year"
               
                bedrooms = prop.get('bedrooms', '')
                if bedrooms:
                    response_parts.append(f"{i}. {title} in {city} - {bedrooms} bedroom{'s' if bedrooms != '1' else ''} - {price_info}")
                else:
                    response_parts.append(f"{i}. {title} in {city} - {price_info}")
           
            if count > 5:
                response_parts.append(f"\n... and {count - 5} more properties.")
           
            return " ".join(response_parts)
        else:
            prop_type = entities.get('property_type', 'properties')
            location = entities.get('location', 'that area')
           
            # Get all properties to suggest alternatives
            all_properties = get_all_firestore_properties()
            cities = {}
            for prop in all_properties:
                city = prop.get('city', 'Unknown')
                if city:
                    cities[city] = cities.get(city, 0) + 1
           
            if cities:
                top_cities = sorted(cities.items(), key=lambda x: x[1], reverse=True)[:3]
                suggestions = [f"{city} ({count} properties)" for city, count in top_cities]
                return f"No {prop_type} properties found in {location}. Try these areas: {', '.join(suggestions)}"
           
            return f"No {prop_type} properties found in {location}. Try broadening your search criteria."
   
    elif intent == "financing":
        financing_type = entities.get('financing_type', 'financing')
       
        # Document requirements
        document_templates = {
            'bank financing': [
                "Valid ID (passport, driver's license, etc.)",
                "Proof of Income (3 months payslips)",
                "Bank Statements (3-6 months)",
                "Income Tax Return (ITR)",
                "Proof of Billing"
            ],
            'pag-ibig': [
                "Pag-IBIG Membership ID",
                "Valid ID",
                "Proof of Income",
                "Proof of Billing",
                "Marriage Certificate (if applicable)"
            ],
            'in-house financing': [
                "Valid ID",
                "Proof of Income",
                "Downpayment (usually 20-30%)",
                "Post-dated checks",
                "Employment Certificate"
            ]
        }
       
        # Get appropriate documents
        if 'bank' in financing_type.lower():
            docs = document_templates['bank financing']
            doc_type = "bank financing"
        elif 'pag-ibig' in financing_type.lower():
            docs = document_templates['pag-ibig']
            doc_type = "Pag-IBIG financing"
        elif 'in-house' in financing_type.lower():
            docs = document_templates['in-house financing']
            doc_type = "in-house financing"
        else:
            docs = document_templates['bank financing']
            doc_type = "property financing"
       
        documents_list = "\n• " + "\n• ".join(docs)
       
        # Check properties with financing
        if properties:
            # Filter for sale properties (financing usually applies to sale)
            sale_props = [p for p in properties if p.get('pricingType') == 'sale']
            
            if sale_props:
                response = f"**Properties with {doc_type} options:**\n\n"
                response += f"🏠 **Available Properties ({len(sale_props)}):**\n"
                
                for i, prop in enumerate(sale_props[:5], 1):
                    title = prop.get('title', 'Property')
                    city = prop.get('city', 'Location')
                    price = f"₱{prop.get('salePrice', 0):,}" if prop.get('salePrice') else "Price on inquiry"
                    bedrooms = prop.get('bedrooms', '')
                    
                    if bedrooms:
                        response += f"{i}. {title} in {city} - {bedrooms} BR - {price}\n"
                    else:
                        response += f"{i}. {title} in {city} - {price}\n"
                
                if len(sale_props) > 5:
                    response += f"\n... and {len(sale_props) - 5} more properties with {doc_type} options."
            else:
                response = f"I couldn't find specific properties with {doc_type} in the database, but here are some available properties that might offer financing:\n\n"
                
                for i, prop in enumerate(properties[:3], 1):
                    title = prop.get('title', 'Property')
                    city = prop.get('city', 'Location')
                    price = f"₱{prop.get('salePrice', prop.get('monthlyRent', 0)):,}" if prop.get('salePrice') or prop.get('monthlyRent') else "Price on inquiry"
                    response += f"{i}. {title} in {city} - {price}\n"
            
            response += f"\n📋 **Required documents for {doc_type}:**{documents_list}"
            return response
        else:
            # If no properties found, still show document requirements
            return f"For {doc_type}, you'll typically need:{documents_list}\n\nMost properties for sale in Batangas offer financing options. Try asking: 'Find houses for sale in Batangas City' to see available properties."
   
    elif intent == "location_info":
        location = entities.get('location', 'Batangas')
       
        if location in batangas_data:
            info = batangas_data[location]
            response = f"📍 **{location}**\n\n"
           
            if 'lifestyle_description' in info:
                response += f"{info['lifestyle_description']}\n\n"
           
            if 'average_rents' in info:
                response += "**Average Rents:**\n"
                rents = info['average_rents']
                if isinstance(rents, dict):
                    for category, price in rents.items():
                        if isinstance(price, dict):
                            for subcategory, subprice in price.items():
                                response += f"• {subcategory}: {subprice}\n"
                        else:
                            response += f"• {category}: {price}\n"
           
            return response
        else:
            return f"{location} is part of Batangas province with diverse property options. You can find residential, commercial, and agricultural properties here."
   
    elif intent == "find_near_landmark":
        landmark = entities.get('landmark', 'landmark')
        location = entities.get('location', 'area')
       
        if properties:
            count = len(properties)
            return f"I found {count} properties near {landmark} in {location}."
        else:
            return f"No properties found near {landmark} in {location}. Try searching in a different area."
   
    else:
        if properties:
            count = len(properties)
            return f"I found {count} properties matching your criteria."
        else:
            all_props = get_all_firestore_properties()
            total = len(all_props)
           
            if total > 0:
                cities = {}
                for prop in all_props:
                    city = prop.get('city', 'Unknown')
                    if city:
                        cities[city] = cities.get(city, 0) + 1
               
                top_cities = sorted(cities.items(), key=lambda x: x[1], reverse=True)[:3]
                city_list = ", ".join([f"{city} ({count})" for city, count in top_cities])
               
                return f"I can help you find properties in Batangas! We have {total} properties listed. Popular areas: {city_list}."
            else:
                return "I can help you find properties in Batangas province. Try asking about specific property types or locations!"


# API ENDPOINTS
@app.route('/api/chat', methods=['POST'])
def chat():
    try:
        data = request.json
        query = data.get('query', '').strip()
        user_id = data.get('user_id', 'anonymous')
       
        if not query:
            return jsonify({'error': 'No query provided'}), 400
       
        logger.info(f"\n💬 Query from {user_id}: '{query}'")
       
        # Step 1: Predict intent
        intent = "unknown"
        confidence = 0.0
        
        if vectorizer and classifier:
            try:
                X = vectorizer.transform([query])
                intent = classifier.predict(X)[0]
                confidence = float(classifier.predict_proba(X).max())
                logger.info(f"🎯 Intent: {intent} (confidence: {confidence:.2%})")
                
                # Log top 3 intents for debugging
                probas = classifier.predict_proba(X)[0]
                top_indices = probas.argsort()[-3:][::-1]
                logger.info("📊 Top 3 intents:")
                for idx in top_indices:
                    intent_name = classifier.classes_[idx]
                    intent_prob = probas[idx] * 100
                    logger.info(f"   • {intent_name}: {intent_prob:.1f}%")
                    
            except Exception as e:
                logger.error(f"❌ Model prediction failed: {e}")
       
        # Step 2: Extract entities
        entities = extract_entities_from_query(query)
        logger.info(f"📝 Entities: {entities}")
       
        # Step 3: Search properties if needed
        properties = []
        should_search = (
            intent in ["find_property", "find_near_landmark", "find_property_with_criteria",
                      "find_property_for_need", "find_ready_property", "find_with_feature", "financing"] or
            any(keyword in query.lower() for keyword in ['find', 'search', 'property', 'house',
                                                         'apartment', 'condo', 'land', 'lot', 'financing'])
        )
       
        if should_search:
            properties = search_firestore_properties(entities)
            logger.info(f"🏠 Found {len(properties)} properties")
       
        # Step 4: Generate response
        response_text = generate_response(intent, entities, properties)
       
        # Step 5: Prepare result
        result = {
            'success': True,
            'query': query,
            'intent': intent,
            'entities': entities,
            'response': response_text,
            'properties_found': len(properties),
            'properties': properties[:10],  # Limit to 10 for response
            'total_in_db': len(get_all_firestore_properties()),
            'timestamp': datetime.now().isoformat(),
            'model_used': 'trained' if vectorizer else 'fallback',
            'confidence': confidence,
            'version': '3.1 - Fixed Financing Query'
        }
       
        return jsonify(result)
       
    except Exception as e:
        logger.error(f"❌ Error in chat endpoint: {e}")
        return jsonify({
            'success': False,
            'error': str(e),
            'response': "I encountered an error. Please try again."
        }), 500


@app.route('/api/health', methods=['GET'])
def health_check():
    """Health check endpoint"""
    all_properties = get_all_firestore_properties()
    total_count = len(all_properties)
   
    # Get statistics
    cities = {}
    types = {}
    for prop in all_properties:
        city = prop.get('city', 'Unknown')
        if city:
            cities[city] = cities.get(city, 0) + 1
       
        prop_type = prop.get('propertyType', 'Unknown')
        types[prop_type] = types.get(prop_type, 0) + 1
   
    top_cities = sorted(cities.items(), key=lambda x: x[1], reverse=True)[:5]
    top_types = sorted(types.items(), key=lambda x: x[1], reverse=True)[:5]
   
    return jsonify({
        'status': 'healthy',
        'service': 'Bah.AI Property Chatbot - Fixed Financing Query',
        'model_loaded': vectorizer is not None,
        'firebase_connected': db is not None,
        'shared_data_loaded': shared_data is not None,
        'total_properties': total_count,
        'top_locations': dict(top_cities),
        'top_property_types': dict(top_types),
        'cache_valid': _properties_cache is not None,
        'cache_size': len(_properties_cache) if _properties_cache else 0,
        'timestamp': datetime.now().isoformat()
    })


@app.route('/api/properties/all', methods=['GET'])
def get_all_properties_api():
    """Get ALL properties"""
    try:
        all_properties = get_all_firestore_properties()
        return jsonify({
            'success': True,
            'count': len(all_properties),
            'properties': all_properties
        })
    except Exception as e:
        return jsonify({
            'success': False,
            'error': str(e)
        }), 500


@app.route('/api/clear_cache', methods=['POST'])
def clear_cache():
    """Clear properties cache"""
    global _properties_cache, _cache_timestamp
    _properties_cache = None
    _cache_timestamp = None
    return jsonify({'success': True, 'message': 'Cache cleared'})


# ==================== MAIN ====================
if __name__ == '__main__':
    print("\n" + "="*60)
    print("🚀 BAH.AI PROPERTY CHATBOT BACKEND - FIXED FINANCING QUERY")
    print("="*60)
   
    # Load NLU model
    load_nlu_model()
   
    # Load shared data
    shared_data = load_shared_data()
   
    print(f"📂 NLU Model: {'✅ Loaded' if vectorizer else '❌ Not loaded'}")
    print(f"🔥 Firebase: {'✅ Connected' if db else '❌ Not connected'}")
    print(f"📊 Shared Data: {'✅ Loaded' if shared_data else '❌ Not loaded'}")
   
    if db:
        # Load properties on startup
        all_properties = get_all_firestore_properties()
        total_count = len(all_properties)
       
        if total_count > 0:
            print(f"\n📈 PROPERTY DATABASE STATISTICS")
            print("-"*40)
           
            # Top cities
            cities = {}
            for prop in all_properties:
                city = prop.get('city', 'Unknown')
                if city:
                    cities[city] = cities.get(city, 0) + 1
           
            top_cities = sorted(cities.items(), key=lambda x: x[1], reverse=True)[:5]
            print("📍 Top Locations:")
            for city, count in top_cities:
                print(f"   {city}: {count} properties")
           
            # Property types
            types = {}
            for prop in all_properties:
                prop_type = prop.get('propertyType', 'Unknown')
                types[prop_type] = types.get(prop_type, 0) + 1
           
            top_types = sorted(types.items(), key=lambda x: x[1], reverse=True)[:5]
            print("\n🏠 Property Types:")
            for prop_type, count in top_types:
                print(f"   {prop_type}: {count} properties")
           
            # Transaction types
            transactions = {}
            for prop in all_properties:
                trans_type = prop.get('type', 'unknown')
                transactions[trans_type] = transactions.get(trans_type, 0) + 1
           
            print("\n💰 Transaction Types:")
            for trans_type, count in transactions.items():
                print(f"   {trans_type}: {count} properties")
   
    print("\n🌐 API Endpoints:")
    print("   POST /api/chat        - Main chatbot endpoint")
    print("   GET  /api/health      - Health check with statistics")
    print("   GET  /api/properties/all - Get ALL properties")
    print("   POST /api/clear_cache - Clear properties cache")
    print("="*60 + "\n")
    
    print("💡 TEST QUERIES:")
    print("   1. 'Properties that accept bank financing'")
    print("   2. 'Find apartments in Batangas City'")
    print("   3. 'Show me houses under 3M'")
    print("   4. 'Tell me about Lipa City'")
    print("="*60 + "\n")
   
    app.run(host='0.0.0.0', port=5000, debug=True)