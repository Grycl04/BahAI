from firebase_functions import https_fn
from firebase_admin import initialize_app, firestore
import json
import logging
from datetime import datetime
from collections import defaultdict

# Configure logging
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

# Global variables for lazy initialization
_firebase_app = None
_db_client = None

def get_firebase():
    """Lazy initialize Firebase"""
    global _firebase_app, _db_client
    if _firebase_app is None:
        logger.info("Initializing Firebase...")
        _firebase_app = initialize_app()
        _db_client = firestore.client()
    return _db_client

class FirestoreEncoder(json.JSONEncoder):
    """Custom JSON encoder for Firestore data"""
    def default(self, obj):
        if hasattr(obj, 'isoformat'):
            return obj.isoformat()
        return super().default(obj)

# =========================== PERSONALIZED RECOMMENDATIONS ===========================

def get_user_history(db, user_id: str):
    """Get user's history - saved properties and searches"""
    history = {
        "saved_properties": [],  # List of property IDs the user saved
        "saved_details": [],     # Details of saved properties
        "search_patterns": [],   # Search filters used
        "has_history": False
    }
    
    try:
        # 1. GET SAVED PROPERTIES
        saved_ref = db.collection('savedProperties')
        saved_query = saved_ref.where('userId', '==', user_id)
        saved_snapshot = saved_query.get()
        
        saved_ids = []
        for doc in saved_snapshot:
            data = doc.to_dict()
            property_id = data.get('propertyId')
            if property_id:
                saved_ids.append(property_id)
                history["saved_properties"].append(property_id)
        
        # Get details of saved properties
        for prop_id in saved_ids:
            prop_doc = db.collection('properties').document(prop_id).get()
            if prop_doc.exists:
                prop = prop_doc.to_dict()
                prop['id'] = prop_id
                history["saved_details"].append(prop)
        
        # 2. GET SEARCH HISTORY (last 10 searches)
        try:
            events_ref = db.collection('events')
            search_query = events_ref.where('userId', '==', user_id).where('eventType', '==', 'search')
            search_snapshot = search_query.get()
            
            for doc in search_snapshot:
                data = doc.to_dict()
                filters = data.get('metadata', {}).get('filters', {})
                if filters:
                    history["search_patterns"].append(filters)
        except:
            pass
        
        # Check if user has any history
        history["has_history"] = len(history["saved_properties"]) > 0 or len(history["search_patterns"]) > 0
        
        logger.info(f"User {user_id} history - Saved: {len(history['saved_properties'])}, Searches: {len(history['search_patterns'])}")
        return history
        
    except Exception as e:
        logger.error(f"Error getting user history: {str(e)}")
        return history

def find_similar_properties(db, user_history, count: int = 5):
    """Find properties similar to user's history"""
    try:
        # Get all active properties
        properties_ref = db.collection('properties')
        properties_query = properties_ref.where('status', '==', 'active')
        properties_snapshot = properties_query.get()
        
        if not properties_snapshot:
            return []
        
        all_properties = []
        for doc in properties_snapshot:
            prop = doc.to_dict()
            prop['id'] = doc.id
            all_properties.append(prop)
        
        # If user has no saved properties, return empty (no recommendations)
        if not user_history["saved_details"]:
            logger.info("User has no saved properties - no recommendations")
            return []
        
        # Find similar properties based on saved properties
        similar_properties = []
        
        for saved_prop in user_history["saved_details"]:
            # Look for properties with similar characteristics
            for prop in all_properties:
                # Skip if already in similar list
                if prop['id'] in [p['id'] for p in similar_properties]:
                    continue
                
                # Skip if user already saved this
                if prop['id'] in user_history["saved_properties"]:
                    continue
                
                # Check similarity
                similarity_score = 0
                
                # Property type match
                if saved_prop.get('propertyType') and prop.get('propertyType'):
                    if saved_prop['propertyType'].lower() == prop['propertyType'].lower():
                        similarity_score += 3
                
                # Location match (partial)
                if saved_prop.get('location') and prop.get('location'):
                    saved_loc = saved_prop['location'].lower()
                    prop_loc = prop['location'].lower()
                    if saved_loc in prop_loc or prop_loc in saved_loc:
                        similarity_score += 2
                
                # Price range match (within 30%)
                saved_price = saved_prop.get('monthlyRent') or saved_prop.get('pricing') or saved_prop.get('salePrice') or saved_prop.get('price')
                prop_price = prop.get('monthlyRent') or prop.get('pricing') or prop.get('salePrice') or prop.get('price')
                
                if saved_price and prop_price:
                    try:
                        saved_price = float(saved_price)
                        prop_price = float(prop_price)
                        if 0.7 * saved_price <= prop_price <= 1.3 * saved_price:
                            similarity_score += 2
                    except:
                        pass
                
                # Transaction type match
                saved_is_rent = bool(saved_prop.get('monthlyRent'))
                saved_is_lease = bool(saved_prop.get('annualRent'))
                prop_is_rent = bool(prop.get('monthlyRent'))
                prop_is_lease = bool(prop.get('annualRent'))
                
                if (saved_is_rent and prop_is_rent) or (saved_is_lease and prop_is_lease) or \
                   (not saved_is_rent and not saved_is_lease and not prop_is_rent and not prop_is_lease):
                    similarity_score += 1
                
                # If similar enough, add to recommendations
                if similarity_score >= 4:  # Need decent match
                    prop['similarity_score'] = similarity_score
                    prop['similar_to'] = saved_prop.get('title', 'your saved property')
                    similar_properties.append(prop)
                
                # Stop if we have enough
                if len(similar_properties) >= count * 2:
                    break
            
            # Stop checking saved properties if we have enough recommendations
            if len(similar_properties) >= count * 2:
                break
        
        # Sort by similarity score and return top N
        similar_properties.sort(key=lambda x: x.get('similarity_score', 0), reverse=True)
        
        # Return only unique properties
        unique_properties = []
        seen_ids = set()
        for prop in similar_properties:
            if prop['id'] not in seen_ids:
                unique_properties.append(prop)
                seen_ids.add(prop['id'])
            if len(unique_properties) >= count:
                break
        
        logger.info(f"Found {len(unique_properties)} similar properties")
        return unique_properties
        
    except Exception as e:
        logger.error(f"Error finding similar properties: {str(e)}")
        return []

# =========================== CLOUD FUNCTIONS ===========================

@https_fn.on_request()
def personalized_recommendations(req: https_fn.Request) -> https_fn.Response:
    """TRUE personalized recommendations - only for users with history"""
    
    # Handle CORS
    if req.method == "OPTIONS":
        return https_fn.Response(
            headers={
                "Access-Control-Allow-Origin": "*",
                "Access-Control-Allow-Methods": "GET, POST, OPTIONS",
                "Access-Control-Allow-Headers": "Content-Type, Authorization",
                "Access-Control-Max-Age": "3600"
            }
        )
    
    try:
        # Get user ID
        if req.method == "POST":
            data = req.get_json() or {}
            user_id = data.get('user_id')
        else:
            user_id = req.args.get('user_id')
        
        if not user_id:
            return https_fn.Response(
                json.dumps({"success": False, "error": "user_id is required"}),
                status=400,
                headers={"Content-Type": "application/json", "Access-Control-Allow-Origin": "*"}
            )
        
        count = int(req.args.get('count', 5) if req.method == "GET" else (req.get_json() or {}).get('count', 5))
        
        logger.info(f"Getting TRUE personalized recommendations for: {user_id}")
        
        # Get Firebase
        db = get_firebase()
        
        # Get user history
        user_history = get_user_history(db, user_id)
        
        # If user has NO history, return empty array
        if not user_history["has_history"]:
            response = {
                "success": True,
                "user_id": user_id,
                "has_history": False,
                "message": "No saved properties or search history yet. Save properties you like to get personalized recommendations!",
                "recommendations": [],
                "count": 0,
                "timestamp": datetime.now().isoformat()
            }
            return https_fn.Response(
                json.dumps(response, cls=FirestoreEncoder, indent=2),
                status=200,
                headers={
                    "Content-Type": "application/json",
                    "Access-Control-Allow-Origin": "*"
                }
            )
        
        # Find similar properties
        recommendations = find_similar_properties(db, user_history, count)
        
        response = {
            "success": True,
            "user_id": user_id,
            "has_history": True,
            "saved_count": len(user_history["saved_properties"]),
            "search_count": len(user_history["search_patterns"]),
            "recommendations": recommendations,
            "count": len(recommendations),
            "message": f"Found {len(recommendations)} properties similar to what you've saved" if recommendations else "No similar properties found yet",
            "timestamp": datetime.now().isoformat()
        }
        
        return https_fn.Response(
            json.dumps(response, cls=FirestoreEncoder, indent=2),
            status=200,
            headers={
                "Content-Type": "application/json",
                "Access-Control-Allow-Origin": "*"
            }
        )
        
    except Exception as e:
        logger.error(f"Error in personalized recommendations: {str(e)}")
        return https_fn.Response(
            json.dumps({"success": False, "error": str(e)}),
            status=500,
            headers={"Content-Type": "application/json", "Access-Control-Allow-Origin": "*"}
        )

@https_fn.on_request()
def check_user_history(req: https_fn.Request) -> https_fn.Response:
    """Check if user has history for recommendations"""
    user_id = req.args.get('user_id')
    if not user_id:
        return https_fn.Response(
            json.dumps({"error": "user_id required"}),
            status=400,
            headers={"Content-Type": "application/json", "Access-Control-Allow-Origin": "*"}
        )
    
    db = get_firebase()
    history = get_user_history(db, user_id)
    
    return https_fn.Response(
        json.dumps({
            "user_id": user_id,
            "has_history": history["has_history"],
            "saved_properties": len(history["saved_properties"]),
            "search_history": len(history["search_patterns"]),
            "message": "Save properties you like to get personalized recommendations!" if not history["has_history"] else "You have history! Getting personalized recommendations..."
        }, cls=FirestoreEncoder, indent=2),
        headers={"Content-Type": "application/json", "Access-Control-Allow-Origin": "*"}
    )

@https_fn.on_request()
def health(req: https_fn.Request) -> https_fn.Response:
    """Health check"""
    return https_fn.Response(
        json.dumps({
            "status": "healthy",
            "service": "true-personalized-recommender",
            "timestamp": datetime.now().isoformat(),
            "endpoints": {
                "recommendations": "GET /personalized_recommendations?user_id=USER_ID",
                "check_history": "GET /check_user_history?user_id=USER_ID"
            }
        }),
        headers={"Content-Type": "application/json", "Access-Control-Allow-Origin": "*"}
    )