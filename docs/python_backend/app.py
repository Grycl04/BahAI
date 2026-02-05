import firebase_admin
from firebase_admin import credentials, firestore
from flask import Flask, request, jsonify, render_template
from flask_cors import CORS
import json
import re
from datetime import datetime
import os
from typing import Dict, List, Optional, Any
import logging

# Configure logging
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

app = Flask(__name__)
CORS(app)  # Enable CORS for all routes

# Initialize Firebase
try:
    # Use environment variable or service account file
    service_account_path = os.getenv('FIREBASE_SERVICE_ACCOUNT', 'service-account-key.json')
    cred = credentials.Certificate(service_account_path)
    firebase_admin.initialize_app(cred)
    db = firestore.client()
    logger.info("✅ Firebase initialized successfully")
except Exception as e:
    logger.error(f"❌ Firebase initialization failed: {e}")
    raise

# ==================== NLU & INTENT DETECTION ====================

class PropertyNLU:
    """Natural Language Understanding for property queries"""
    
    def __init__(self):
        # Load synonyms and entity dictionaries
        self.property_types = self._load_property_types()
        self.locations = self._load_locations()
        self.financing_types = self._load_financing_types()
        self.synonyms = self._load_synonyms()
        
    def _load_property_types(self) -> Dict[str, List[str]]:
        """Load property type mappings from your schema"""
        return {
            # RENT property types
            'rent': {
                'residential': ['apartment', 'boarding_house', 'condo', 'room', 
                              'townhouse', 'house', 'dormitory'],
                'commercial': ['office_unit', 'retail_space', 'food_stall', 
                             'shop', 'showroom'],
                'industrial': ['warehouse', 'storage_unit', 'factory', 'workshop']
            },
            # LEASE property types
            'lease': {
                'commercial': ['office_floor', 'retail_space_lease', 'building_lease',
                             'commercial_unit', 'showroom_lease', 'warehouse_lease'],
                'land': ['commercial_lot', 'agricultural_land', 'development_land',
                        'industrial_lot', 'residential_lot', 'vacant_lot'],
                'special': ['resort_property', 'event_venue', 'parking_area',
                          'school_property', 'hospitality', 'sports_facility']
            },
            # SALE property types
            'sale': {
                'residential': ['house', 'townhouse', 'bungalow', 'duplex', 'village_lot'],
                'commercial': ['commercial_building', 'office_space', 'retail_space',
                             'warehouse', 'showroom'],
                'land': ['residential_lot', 'commercial_lot', 'agricultural_land',
                        'industrial_lot', 'beachfront'],
                'condo': ['condo_unit', 'penthouse', 'studio', 'loft']
            }
        }
    
    def _load_locations(self) -> List[str]:
        """Load Batangas locations"""
        return [
            "Batangas City", "Lipa City", "Tanauan City", "Bauan", "Balayan",
            "Nasugbu", "San Juan", "Taal", "Calaca", "Lemery", "Talisay",
            "Alitagtag", "Cuenca", "Laurel", "Mataasnakahoy", "San Jose",
            "San Luis", "San Pascual", "Santo Tomas"
        ]
    
    def _load_financing_types(self) -> List[str]:
        """Load financing options"""
        return [
            "bank financing", "pag-ibig", "in-house financing", 
            "cash", "installment", "mortgage"
        ]
    
    def _load_synonyms(self) -> Dict[str, List[str]]:
        """Load synonyms for better matching"""
        return {
            'find': ['look for', 'search for', 'locate', 'show me', 'need'],
            'apartment': ['flat', 'unit', 'condo', 'condominium'],
            'house': ['home', 'residence', 'dwelling', 'villa', 'bungalow'],
            'condo': ['condominium', 'condo unit', 'apartment'],
            'room': ['bedroom', 'bedspace', 'bed space', 'boarding'],
            'lot': ['land', 'plot', 'property', 'vacant lot'],
            'commercial': ['business', 'office', 'retail', 'shop'],
            'rent': ['rental', 'for rent', 'lease', 'leasing'],
            'sale': ['buy', 'purchase', 'for sale', 'sell'],
            'bank financing': ['bank loan', 'mortgage', 'housing loan'],
            'pag-ibig': ['pagination', 'pagibig', 'pag-ibig financing'],
            'good price': ['affordable', 'cheap', 'reasonable', 'budget']
        }
    
    def parse_query(self, query: str) -> Dict[str, Any]:
        """Parse user query to extract intent and entities"""
        query_lower = query.lower().strip()
        
        # Initialize result
        result = {
            'intent': 'unknown',
            'entities': {},
            'raw_query': query
        }
        
        # ===== INTENT DETECTION =====
        
        # Question 1: Find [type] in [location]
        if any(keyword in query_lower for keyword in ['find', 'look for', 'search', 'show me']):
            result['intent'] = 'find_property'
        
        # Question 2: Show me [type] under [price] with [bedrooms]
        elif any(keyword in query_lower for keyword in ['under', 'below', 'less than', 'maximum']):
            result['intent'] = 'find_property_with_criteria'
        
        # Question 3: Find properties for [need] in [location]
        elif any(keyword in query_lower for keyword in ['family', 'single', 'couple', 'students']):
            result['intent'] = 'find_property_for_need'
        
        # Question 4: Properties near [landmark]
        elif 'near' in query_lower or 'close to' in query_lower:
            result['intent'] = 'find_near_landmark'
        
        # Question 5: Show me [feature] with [good price]
        elif any(keyword in query_lower for keyword in ['pool', 'garden', 'parking', 'with']):
            result['intent'] = 'find_with_feature'
        
        # Question 6: Find [ready] properties for [need] in [location]
        elif any(keyword in query_lower for keyword in ['ready', 'move in', 'immediate']):
            result['intent'] = 'find_ready_property'
        
        # Question 7: Properties that accept [financing]
        elif any(keyword in query_lower for keyword in ['accept', 'financing', 'bank', 'pag-ibig']):
            result['intent'] = 'find_financing_properties'
        
        # Question 8: Steps for [property type]
        elif any(keyword in query_lower for keyword in ['steps', 'process', 'costs', 'timeline']):
            result['intent'] = 'process_info'
        
        # Question 9: Tell me about [location]
        elif any(keyword in query_lower for keyword in ['tell me about', 'information about', 'describe']):
            result['intent'] = 'location_info'
        
        # Question 10: What properties match my [need]
        elif any(keyword in query_lower for keyword in ['match', 'suitable', 'for my']):
            result['intent'] = 'match_needs'
        
        # ===== ENTITY EXTRACTION =====
        
        # Extract property type from all categories
        all_property_types = []
        for transaction in self.property_types.values():
            for category in transaction.values():
                all_property_types.extend(category)
        
        # Also include base types and synonyms
        for prop_type in all_property_types + ['apartment', 'house', 'condo', 'room', 'lot']:
            if prop_type in query_lower:
                result['entities']['property_type'] = prop_type
                break
            # Check synonyms
            if prop_type in self.synonyms:
                for synonym in self.synonyms[prop_type]:
                    if synonym in query_lower:
                        result['entities']['property_type'] = prop_type
                        break
        
        # Extract location
        for location in self.locations:
            if location.lower() in query_lower:
                result['entities']['location'] = location
                break
        
        # Extract transaction type (rent/lease/sale)
        if any(word in query_lower for word in ['rent', 'rental', 'for rent']):
            result['entities']['transaction_type'] = 'rent'
        elif any(word in query_lower for word in ['lease', 'leasing', 'for lease']):
            result['entities']['transaction_type'] = 'lease'
        elif any(word in query_lower for word in ['sale', 'buy', 'purchase', 'for sale']):
            result['entities']['transaction_type'] = 'sale'
        
        # Extract price range
        price_patterns = [
            r'under\s+(\d+[kKmM]?)',
            r'below\s+(\d+[kKmM]?)',
            r'less than\s+(\d+[kKmM]?)',
            r'(\d+[kKmM]?)\s+and below',
            r'(\d+)\s*(million|m|k)'
        ]
        
        for pattern in price_patterns:
            match = re.search(pattern, query_lower)
            if match:
                price_str = match.group(1)
                # Convert to number
                if 'k' in price_str.lower():
                    price = float(price_str.lower().replace('k', '')) * 1000
                elif 'm' in price_str.lower():
                    price = float(price_str.lower().replace('m', '')) * 1000000
                else:
                    price = float(price_str)
                result['entities']['max_price'] = price
                break
        
        # Extract bedrooms
        bedroom_patterns = [
            r'(\d+)\s*bedroom',
            r'(\d+)\s*bed',
            r'studio',
            r'(\d+)\s*br'
        ]
        
        for pattern in bedroom_patterns:
            match = re.search(pattern, query_lower)
            if match:
                if 'studio' in query_lower:
                    result['entities']['bedrooms'] = 'studio'
                else:
                    result['entities']['bedrooms'] = match.group(1)
                break
        
        # Extract financing type
        for financing in self.financing_types:
            if financing in query_lower:
                result['entities']['financing_type'] = financing
                break
            # Check synonyms
            if financing in self.synonyms:
                for synonym in self.synonyms[financing]:
                    if synonym in query_lower:
                        result['entities']['financing_type'] = financing
                        break
        
        # Extract features/amenities
        features = ['pool', 'garden', 'parking', 'elevator', 'security', 
                   'wifi', 'aircon', 'furnished', 'furniture']
        for feature in features:
            if feature in query_lower:
                result['entities']['features'] = result['entities'].get('features', []) + [feature]
        
        # Extract needs
        needs = ['family', 'single', 'couple', 'students', 'professionals', 
                'retirees', 'business', 'office', 'commercial']
        for need in needs:
            if need in query_lower:
                result['entities']['need'] = need
                break
        
        logger.info(f"Parsed query: {result}")
        return result

# Initialize NLU
nlu = PropertyNLU()

# ==================== FIRESTORE SEARCH ====================

class PropertySearch:
    """Search properties in Firestore based on NLU results"""
    
    def __init__(self, db):
        self.db = db
    
    def search_properties(self, intent_data: Dict[str, Any]) -> List[Dict[str, Any]]:
        """Search properties based on intent and entities"""
        entities = intent_data.get('entities', {})
        
        # Start with active properties
        query = self.db.collection('properties')
        
        # Always filter by status
        query = query.where('status', 'in', ['available', 'active', 'pending'])
        
        # Apply filters based on entities
        if 'transaction_type' in entities:
            transaction_type = entities['transaction_type']
            query = query.where('type', '==', transaction_type)
        
        if 'location' in entities:
            location = entities['location']
            # Search in city field
            query = query.where('city', '==', location)
        
        if 'property_type' in entities:
            property_type = entities['property_type']
            # Search in propertyType field
            query = query.where('propertyType', '==', property_type)
        
        if 'max_price' in entities:
            max_price = entities['max_price']
            transaction_type = entities.get('transaction_type', 'sale')
            
            if transaction_type == 'rent':
                query = query.where('monthlyRent', '<=', max_price)
            elif transaction_type == 'lease':
                query = query.where('annualRent', '<=', max_price)
            else:  # sale
                query = query.where('salePrice', '<=', max_price)
        
        if 'bedrooms' in entities:
            bedrooms = entities['bedrooms']
            query = query.where('bedrooms', '==', bedrooms)
        
        if 'financing_type' in entities:
            # This would require a 'financingOptions' array field in Firestore
            query = query.where('saleType', '==', 'bank_financing')
        
        # Execute query with limit
        results = query.limit(50).get()
        
        properties = []
        for doc in results:
            prop = doc.to_dict()
            prop['id'] = doc.id
            
            # Check description for additional criteria if not found in fields
            if self._matches_description(prop, entities):
                properties.append(prop)
        
        return properties
    
    def _matches_description(self, property_data: Dict[str, Any], entities: Dict[str, Any]) -> bool:
        """Check if property matches entities in description field"""
        description = property_data.get('description', '').lower()
        
        # Check for property type in description if not already matched
        if 'property_type' in entities and 'propertyType' not in property_data:
            prop_type = entities['property_type']
            if prop_type in description:
                return True
        
        # Check for features in description
        if 'features' in entities:
            for feature in entities['features']:
                if feature in description:
                    return True
        
        # Check for needs in description
        if 'need' in entities:
            need = entities['need']
            need_keywords = {
                'family': ['family', 'children', 'kids', 'spacious'],
                'single': ['single', 'studio', 'compact', 'bachelor'],
                'students': ['student', 'dormitory', 'near school', 'university'],
                'business': ['commercial', 'business', 'office', 'retail']
            }
            if need in need_keywords:
                for keyword in need_keywords[need]:
                    if keyword in description:
                        return True
        
        return True  # Default to True if no description checks needed
    
    def search_by_description(self, search_text: str) -> List[Dict[str, Any]]:
        """Search properties by keywords in description (fallback method)"""
        all_properties = self.db.collection('properties') \
            .where('status', 'in', ['available', 'active']) \
            .limit(100).get()
        
        matches = []
        for doc in all_properties:
            prop = doc.to_dict()
            prop['id'] = doc.id
            
            # Search in multiple fields
            search_fields = [
                prop.get('description', '').lower(),
                prop.get('title', '').lower(),
                prop.get('propertyType', '').lower(),
                prop.get('amenities', '')
            ]
            
            combined_text = ' '.join([str(field) for field in search_fields])
            
            if search_text.lower() in combined_text:
                matches.append(prop)
        
        return matches

# Initialize property search
property_search = PropertySearch(db)

# ==================== RESPONSE GENERATION ====================

class ResponseGenerator:
    """Generate natural language responses with property data"""
    
    def __init__(self):
        self.location_data = self._load_location_data()
    
    def _load_location_data(self) -> Dict[str, Dict[str, Any]]:
        """Load location information"""
        return {
            "Batangas City": {
                "description": "Urban center with port, universities, and commercial areas",
                "average_rents": {
                    "apartment": "₱8,000-₱15,000",
                    "house": "₱15,000-₱30,000",
                    "condo": "₱12,000-₱25,000",
                    "room": "₱3,000-₱8,000"
                },
                "key_features": ["Port access", "Universities", "Commercial areas", "Historical sites"],
                "popular_areas": ["Poblacion", "Kumintang Ilaya", "Alangilan", "Bolbok"]
            },
            "Lipa City": {
                "description": "Education hub with cool climate, known as coffee capital",
                "average_rents": {
                    "apartment": "₱7,000-₱14,000",
                    "house": "₱12,000-₱25,000",
                    "condo": "₱10,000-₱20,000"
                },
                "key_features": ["Coffee plantations", "Educational institutions", "Cool climate", "Historical churches"],
                "popular_areas": ["Banay-banay", "Sabang", "Antipolo", "San Carlos"]
            },
            "Tanauan City": {
                "description": "Growing city with modern developments and commercial centers",
                "average_rents": {
                    "apartment": "₱6,000-₱12,000",
                    "house": "₱10,000-₱20,000"
                },
                "key_features": ["Nuvali development", "Ayala Malls", "Residential communities"],
                "popular_areas": ["Poblacion", "Sala", "Talisay", "Boot"]
            }
        }
    
    def generate_response(self, intent_data: Dict[str, Any], properties: List[Dict[str, Any]]) -> str:
        """Generate appropriate response based on intent"""
        intent = intent_data.get('intent', 'unknown')
        entities = intent_data.get('entities', {})
        
        if intent == 'find_property':
            return self._format_property_search_response(entities, properties)
        
        elif intent == 'location_info':
            return self._format_location_response(entities)
        
        elif intent == 'find_financing_properties':
            return self._format_financing_response(entities, properties)
        
        elif intent == 'find_property_with_criteria':
            return self._format_criteria_response(entities, properties)
        
        elif intent == 'find_property_for_need':
            return self._format_needs_response(entities, properties)
        
        else:
            return self._format_general_response(entities, properties)
    
    def _format_property_search_response(self, entities: Dict[str, Any], properties: List[Dict[str, Any]]) -> str:
        """Format response for property search queries"""
        if not properties:
            return self._get_no_results_message(entities)
        
        # Build response
        response = f"🔍 **I found {len(properties)} properties"
        
        # Add qualifiers
        if 'property_type' in entities:
            response += f" of type **{entities['property_type'].replace('_', ' ').title()}**"
        
        if 'location' in entities:
            response += f" in **{entities['location']}**"
        
        if 'transaction_type' in entities:
            transaction_type = entities['transaction_type']
            response += f" **for {transaction_type}**"
        
        response += ":**\n\n"
        
        # Add top 5 properties
        for i, prop in enumerate(properties[:5]):
            response += f"**{i+1}. {prop.get('title', 'Untitled Property')}**\n"
            
            # Price
            price = self._get_display_price(prop)
            response += f"💰 **Price:** {price}\n"
            
            # Location
            address = prop.get('address', prop.get('location', prop.get('city', 'Location not specified')))
            response += f"📍 **Location:** {address}\n"
            
            # Details
            details = []
            if 'bedrooms' in prop:
                details.append(f"{prop['bedrooms']} beds")
            if 'bathrooms' in prop:
                details.append(f"{prop['bathrooms']} baths")
            if 'floorArea' in prop:
                details.append(f"{prop['floorArea']} sqm")
            
            if details:
                response += f"📐 **Details:** {', '.join(details)}\n"
            
            # Type and status
            response += f"🏠 **Type:** {prop.get('propertyType', 'N/A')} | "
            response += f"📋 **Status:** {prop.get('status', 'available').title()}\n"
            
            # Description snippet
            description = prop.get('description', '')
            if description:
                snippet = description[:100] + '...' if len(description) > 100 else description
                response += f"📝 **Description:** {snippet}\n"
            
            # View link
            response += f"🔗 **[View Details & Contact](https://yourdomain.com/broker/property_details.html?id={prop['id']})**\n\n"
        
        if len(properties) > 5:
            response += f"*... and {len(properties) - 5} more properties.*\n\n"
        
        # Add suggestions
        response += self._get_suggestions(entities)
        
        return response
    
    def _format_location_response(self, entities: Dict[str, Any]) -> str:
        """Format response for location information queries"""
        location = entities.get('location')
        
        if not location or location not in self.location_data:
            return "I don't have detailed information about that location yet. Please specify a city in Batangas."
        
        data = self.location_data[location]
        
        response = f"📍 **About {location}:**\n\n"
        response += f"{data['description']}\n\n"
        
        # Average rents
        response += "**💰 Average Monthly Rents:**\n"
        for prop_type, price_range in data.get('average_rents', {}).items():
            response += f"• {prop_type.title()}: {price_range}\n"
        
        response += f"\n**🏘️ Popular Areas:** {', '.join(data.get('popular_areas', []))}\n"
        response += f"\n**🌟 Key Features:** {', '.join(data.get('key_features', []))}\n"
        
        # Add property search suggestion
        response += f"\n**💡 Tip:** Search properties in {location} by asking: 'Find apartments in {location}' or 'Show me houses in {location}'"
        
        return response
    
    def _format_financing_response(self, entities: Dict[str, Any], properties: List[Dict[str, Any]]) -> str:
        """Format response for financing queries"""
        financing_type = entities.get('financing_type', 'bank financing')
        
        # Documents required
        documents = {
            'bank financing': [
                'Valid ID (passport, driver\'s license, etc.)',
                'Proof of income (3 months payslips or ITR)',
                'Bank statements (3-6 months)',
                'Certificate of Employment',
                'Tax Identification Number (TIN)'
            ],
            'pag-ibig': [
                'Valid ID',
                'Pag-IBIG Membership Verification',
                'Proof of income',
                'Marriage certificate (if married)',
                'Birth certificates of dependents'
            ],
            'in-house financing': [
                'Valid ID',
                'Proof of income',
                'Down payment (usually 20-30%)',
                'Post-dated checks'
            ]
        }
        
        doc_list = documents.get(financing_type, documents['bank financing'])
        
        response = f"🏦 **Properties that accept {financing_type.title()}**\n\n"
        
        if properties:
            response += f"I found **{len(properties)} properties** that accept {financing_type}:\n\n"
            
            for i, prop in enumerate(properties[:3]):
                price = self._get_display_price(prop)
                response += f"{i+1}. **{prop.get('title', 'Property')}** - {price}\n"
                response += f"   📍 {prop.get('city', 'Location not specified')}\n"
            
            if len(properties) > 3:
                response += f"\n*... and {len(properties) - 3} more properties.*\n"
        else:
            response += f"No properties found with {financing_type} option. Try a different search.\n"
        
        response += f"\n**📄 Required Documents for {financing_type.title()}:**\n"
        for i, doc in enumerate(doc_list, 1):
            response += f"{i}. {doc}\n"
        
        # Add typical requirements
        if financing_type == 'bank financing':
            response += "\n**📋 Typical Requirements:**\n"
            response += "• Minimum 2 years of continuous employment\n"
            response += "• Good credit history\n"
            response += "• 20-30% down payment\n"
            response += "• Property appraisal required\n"
        
        return response
    
    def _format_criteria_response(self, entities: Dict[str, Any], properties: List[Dict[str, Any]]) -> str:
        """Format response for queries with specific criteria"""
        if not properties:
            return self._get_no_results_message(entities)
        
        response = "🔍 **Properties matching your criteria:**\n\n"
        
        criteria_parts = []
        if 'property_type' in entities:
            criteria_parts.append(f"type: **{entities['property_type']}**")
        if 'max_price' in entities:
            criteria_parts.append(f"under **₱{entities['max_price']:,.0f}**")
        if 'bedrooms' in entities:
            criteria_parts.append(f"with **{entities['bedrooms']} bedrooms**")
        if 'location' in entities:
            criteria_parts.append(f"in **{entities['location']}**")
        
        response += f"**Criteria:** {', '.join(criteria_parts)}\n\n"
        response += f"**Found {len(properties)} properties:**\n\n"
        
        for i, prop in enumerate(properties[:5]):
            price = self._get_display_price(prop)
            response += f"{i+1}. **{prop.get('title', 'Property')}**\n"
            response += f"   {price} | {prop.get('bedrooms', 'N/A')} beds | {prop.get('floorArea', 'N/A')} sqm\n"
            response += f"   📍 {prop.get('city', 'Location')}\n\n"
        
        return response
    
    def _format_needs_response(self, entities: Dict[str, Any], properties: List[Dict[str, Any]]) -> str:
        """Format response for needs-based queries"""
        need = entities.get('need', 'general')
        
        need_descriptions = {
            'family': "🏠 **Properties suitable for families:**\n\n",
            'single': "👤 **Properties suitable for single professionals:**\n\n",
            'students': "🎓 **Properties suitable for students:**\n\n",
            'business': "💼 **Commercial properties for business:**\n\n"
        }
        
        response = need_descriptions.get(need, "**Properties matching your needs:**\n\n")
        
        if properties:
            response += f"Found **{len(properties)} properties** suitable for {need}:\n\n"
            
            for i, prop in enumerate(properties[:5]):
                price = self._get_display_price(prop)
                response += f"{i+1}. **{prop.get('title', 'Property')}**\n"
                response += f"   {price} | {prop.get('city', 'Location')}\n"
                
                # Add relevant details
                if need == 'family' and 'bedrooms' in prop:
                    response += f"   Perfect for families: {prop['bedrooms']} bedrooms\n"
                elif need == 'students':
                    response += f"   Student-friendly location\n"
                
                response += "\n"
        else:
            response += "No properties found matching your specific needs. Try a broader search.\n"
        
        return response
    
    def _get_display_price(self, property_data: Dict[str, Any]) -> str:
        """Get formatted price based on property type"""
        if 'monthlyRent' in property_data and property_data['monthlyRent']:
            return f"₱{property_data['monthlyRent']:,.0f}/month"
        elif 'annualRent' in property_data and property_data['annualRent']:
            return f"₱{property_data['annualRent']:,.0f}/year"
        elif 'salePrice' in property_data and property_data['salePrice']:
            return f"₱{property_data['salePrice']:,.0f}"
        elif 'pricing' in property_data and property_data['pricing']:
            return f"₱{property_data['pricing']:,.0f}"
        return "Price on inquiry"
    
    def _get_no_results_message(self, entities: Dict[str, Any]) -> str:
        """Get message when no properties are found"""
        message = "❌ **No properties found matching your criteria.**\n\n"
        message += "**You searched for:** "
        
        criteria = []
        if 'property_type' in entities:
            criteria.append(entities['property_type'])
        if 'location' in entities:
            criteria.append(f"in {entities['location']}")
        if 'max_price' in entities:
            criteria.append(f"under ₱{entities['max_price']:,.0f}")
        
        if criteria:
            message += ', '.join(criteria) + "\n\n"
        else:
            message += "your query\n\n"
        
        message += "**Suggestions:**\n"
        message += "1. Try a broader search (e.g., 'Find properties in Batangas')\n"
        message += "2. Check your spelling\n"
        message += "3. Use the search filters on the dashboard for more options\n"
        message += "4. Contact a broker for personalized assistance\n"
        
        return message
    
    def _get_suggestions(self, entities: Dict[str, Any]) -> str:
        """Get search suggestions based on entities"""
        suggestions = "\n**💡 Try these searches too:**\n"
        
        location = entities.get('location', 'Batangas')
        prop_type = entities.get('property_type', 'properties')
        
        suggestions += f"• 'Find {prop_type} under 20k in {location}'\n"
        suggestions += f"• 'Show me {prop_type} with 2 bedrooms'\n"
        suggestions += f"• 'Tell me about {location}'\n"
        suggestions += f"• 'Properties that accept bank financing'\n"
        
        return suggestions

# Initialize response generator
response_generator = ResponseGenerator()

# ==================== API ENDPOINTS ====================

@app.route('/api/chat', methods=['POST'])
def chat():
    """Main chatbot endpoint"""
    try:
        data = request.json
        user_query = data.get('query', '').strip()
        user_id = data.get('user_id', 'anonymous')
        
        if not user_query:
            return jsonify({'error': 'No query provided'}), 400
        
        logger.info(f"Chat request from {user_id}: {user_query}")
        
        # Parse the query
        intent_data = nlu.parse_query(user_query)
        
        # Search properties in Firestore
        properties = []
        if intent_data['intent'] in ['find_property', 'find_property_with_criteria', 
                                    'find_property_for_need', 'find_financing_properties']:
            properties = property_search.search_properties(intent_data)
            
            # If no properties found with structured search, try description search
            if not properties and 'property_type' in intent_data['entities']:
                search_text = intent_data['entities']['property_type']
                properties = property_search.search_by_description(search_text)
        
        # Generate response
        response_text = response_generator.generate_response(intent_data, properties)
        
        # Prepare response
        result = {
            'success': True,
            'query': user_query,
            'intent': intent_data['intent'],
            'entities': intent_data['entities'],
            'response': response_text,
            'properties_found': len(properties),
            'properties': properties[:10]  # Limit for response
        }
        
        # Log the interaction
        log_interaction(user_id, user_query, intent_data, result)
        
        return jsonify(result)
        
    except Exception as e:
        logger.error(f"Error in chat endpoint: {e}")
        return jsonify({
            'success': False,
            'error': str(e),
            'response': "I'm having trouble processing your request. Please try again or use the search filters."
        }), 500

@app.route('/api/properties/search', methods=['GET'])
def search_properties():
    """Direct property search endpoint"""
    try:
        # Get search parameters
        property_type = request.args.get('type')
        location = request.args.get('location')
        transaction_type = request.args.get('transaction_type')
        max_price = request.args.get('max_price')
        
        # Build query
        query = db.collection('properties')
        query = query.where('status', 'in', ['available', 'active'])
        
        if property_type:
            query = query.where('propertyType', '==', property_type)
        if location:
            query = query.where('city', '==', location)
        if transaction_type:
            query = query.where('type', '==', transaction_type)
        if max_price:
            max_price = float(max_price)
            if transaction_type == 'rent':
                query = query.where('monthlyRent', '<=', max_price)
            elif transaction_type == 'lease':
                query = query.where('annualRent', '<=', max_price)
            else:
                query = query.where('salePrice', '<=', max_price)
        
        # Execute query
        results = query.limit(50).get()
        
        properties = []
        for doc in results:
            prop = doc.to_dict()
            prop['id'] = doc.id
            properties.append(prop)
        
        return jsonify({
            'success': True,
            'count': len(properties),
            'properties': properties
        })
        
    except Exception as e:
        logger.error(f"Error in property search: {e}")
        return jsonify({'success': False, 'error': str(e)}), 500

def log_interaction(user_id: str, query: str, intent_data: Dict[str, Any], result: Dict[str, Any]):
    """Log chatbot interaction to Firestore"""
    try:
        log_data = {
            'user_id': user_id,
            'query': query,
            'intent': intent_data.get('intent'),
            'entities': intent_data.get('entities', {}),
            'response': result.get('response', '')[:500],  # Limit response length
            'properties_found': result.get('properties_found', 0),
            'timestamp': datetime.now(),
            'success': result.get('success', True)
        }
        
        db.collection('chatbot_logs').add(log_data)
        logger.info(f"Logged interaction for {user_id}")
        
    except Exception as e:
        logger.error(f"Error logging interaction: {e}")

# ==================== HEALTH & INFO ENDPOINTS ====================

@app.route('/api/health', methods=['GET'])
def health_check():
    """Health check endpoint"""
    return jsonify({
        'status': 'healthy',
        'service': 'BahAI Property Chatbot',
        'version': '1.0.0',
        'timestamp': datetime.now().isoformat()
    })

@app.route('/api/capabilities', methods=['GET'])
def capabilities():
    """Get chatbot capabilities"""
    return jsonify({
        'capabilities': [
            'Find properties by type and location',
            'Search with price criteria',
            'Get location information',
            'Find properties with specific financing',
            'Search based on needs (family, students, etc.)',
            'Find properties with specific features'
        ],
        'supported_locations': nlu.locations,
        'supported_property_types': ['apartment', 'house', 'condo', 'room', 'lot', 'commercial', 'industrial'],
        'supported_transactions': ['rent', 'lease', 'sale']
    })

# ==================== WEBHOOK FOR FRONTEND ====================

@app.route('/webhook/chatbot', methods=['POST'])
def chatbot_webhook():
    """Webhook endpoint for frontend integration"""
    try:
        data = request.json
        
        # Extract user message
        user_message = data.get('message', '').strip()
        session_id = data.get('session_id', 'default')
        
        if not user_message:
            return jsonify({'error': 'No message provided'}), 400
        
        # Process through chatbot
        intent_data = nlu.parse_query(user_message)
        properties = property_search.search_properties(intent_data)
        response_text = response_generator.generate_response(intent_data, properties)
        
        # Format response for webhook
        webhook_response = {
            'session_id': session_id,
            'response': {
                'text': response_text,
                'intent': intent_data['intent'],
                'has_properties': len(properties) > 0,
                'property_count': len(properties)
            }
        }
        
        # Add properties if requested
        if data.get('include_properties', False) and properties:
            webhook_response['properties'] = properties[:5]
        
        return jsonify(webhook_response)
        
    except Exception as e:
        logger.error(f"Webhook error: {e}")
        return jsonify({'error': 'Internal server error'}), 500

# ==================== MAIN ====================

if __name__ == '__main__':
    port = int(os.getenv('PORT', 5000))
    app.run(host='0.0.0.0', port=port, debug=True)