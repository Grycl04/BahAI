# merge_training_data.py
import json
import os
import glob

def load_member_data(filepath):
    """Load and clean member training data"""
    try:
        with open(filepath, 'r', encoding='utf-8') as f:
            return json.load(f)
    except Exception as e:
        print(f"❌ Error loading {filepath}: {e}")
        return None

def merge_training_data():
    """Merge all member training data into one file"""
    base_path = 'data'
    
    # Find all member files
    member_files = glob.glob(os.path.join(base_path, 'member*', 'training_data.json'))
    
    if not member_files:
        print("❌ No member training files found!")
        return
    
    print(f"📂 Found {len(member_files)} member files")
    
    # Initialize consolidated data structure
    consolidated = {
        "member_id": "all_members_consolidated",
        "assigned_questions": [],
        "training_samples": [],
        "entity_dictionary": {
            "property_types": [],
            "locations": [],
            "financing_types": [],
            "document_terms": [],
            "location_info_terms": [],
            "price_terms": [],
            "bedroom_options": [],
            "bathroom_options": [],
            "ready_terms": [],
            "needs": [],
            "features": [],
            "property_classes": [],
            "conditions": [],
            "sizes": [],
            "lifestyle_types": [],
            "needs_categories": [],
            "process_terms": [],
            "property_process_types": [],
            "budget_ranges": [],
            "space_requirements": []
        },
        "response_templates": {},
        "location_profiles": {},
        "financing_info": {},
        "metadata": {
            "total_samples": 0,
            "intent_distribution": {},
            "created_date": "2024-01-25",
            "version": "5.0",
            "training_notes": "CONSOLIDATED VERSION: All member data merged into one file"
        }
    }
    
    # Track intents for mapping
    intent_mapping = {
        'type_price_features': 'find_property_with_criteria',
        'near_landmark': 'find_near_landmark',
        'ready_to_move': 'find_ready_property',
        'family_needs': 'find_property_for_need',
        'feature_price': 'find_with_feature',
        'process_info': 'process_info',
        'personalized_match': 'match_needs',
        'location_info': 'location_info',
        'financing_info': 'financing',
        'financing': 'financing',
        'find_property': 'find_property',
        'find_property_with_criteria': 'find_property_with_criteria',
        'find_near_landmark': 'find_near_landmark',
        'find_ready_property': 'find_ready_property',
        'find_with_feature': 'find_with_feature',
        'match_needs': 'match_needs'
    }
    
    # Process each member file
    for member_file in member_files:
        member_name = os.path.basename(os.path.dirname(member_file))
        print(f"📦 Processing {member_name}...")
        
        data = load_member_data(member_file)
        if not data:
            continue
        
        # Merge assigned questions
        questions = data.get('assigned_questions', [])
        for q in questions:
            if q not in consolidated['assigned_questions']:
                consolidated['assigned_questions'].append(q)
        
        # Merge training samples (map intents)
        samples = data.get('training_samples', [])
        for sample in samples:
            # Map intent to standard name
            original_intent = sample.get('intent', '')
            mapped_intent = intent_mapping.get(original_intent, original_intent)
            
            # Create new sample with mapped intent
            new_sample = sample.copy()
            new_sample['intent'] = mapped_intent
            
            # Add to consolidated
            consolidated['training_samples'].append(new_sample)
        
        # Merge entity dictionaries
        entity_dict = data.get('entity_dictionary', {})
        for category, items in entity_dict.items():
            if category in consolidated['entity_dictionary']:
                if isinstance(items, list):
                    for item in items:
                        if item not in consolidated['entity_dictionary'][category]:
                            consolidated['entity_dictionary'][category].append(item)
                elif isinstance(items, dict):
                    # For dict items like landmark_types
                    if category not in consolidated['entity_dictionary']:
                        consolidated['entity_dictionary'][category] = {}
                    for subcat, subitems in items.items():
                        if subcat not in consolidated['entity_dictionary'][category]:
                            consolidated['entity_dictionary'][category][subcat] = []
                        for item in subitems:
                            if item not in consolidated['entity_dictionary'][category][subcat]:
                                consolidated['entity_dictionary'][category][subcat].append(item)
        
        # Merge response templates
        templates = data.get('response_templates', {})
        for intent, template in templates.items():
            if intent not in consolidated['response_templates']:
                consolidated['response_templates'][intent] = template
        
        # Merge location profiles
        locations = data.get('location_profiles', {})
        for location, profile in locations.items():
            if location not in consolidated['location_profiles']:
                consolidated['location_profiles'][location] = profile
        
        # Merge financing info
        financing = data.get('financing_info', {})
        for financing_type, info in financing.items():
            if financing_type not in consolidated['financing_info']:
                consolidated['financing_info'][financing_type] = info
    
    # Update metadata
    consolidated['metadata']['total_samples'] = len(consolidated['training_samples'])
    
    # Count intent distribution
    intent_counts = {}
    for sample in consolidated['training_samples']:
        intent = sample.get('intent', 'unknown')
        intent_counts[intent] = intent_counts.get(intent, 0) + 1
    consolidated['metadata']['intent_distribution'] = intent_counts
    
    # Save consolidated data
    output_path = os.path.join('data', 'member1', 'training_data_consolidated.json')
    with open(output_path, 'w', encoding='utf-8') as f:
        json.dump(consolidated, f, indent=2, ensure_ascii=False)
    
    print(f"\n✅ Successfully merged all data!")
    print(f"📊 Statistics:")
    print(f"   • Total samples: {consolidated['metadata']['total_samples']}")
    print(f"   • Unique intents: {len(intent_counts)}")
    print(f"   • Location profiles: {len(consolidated['location_profiles'])}")
    print(f"   • Saved to: {output_path}")
    
    # Also create a simplified version for chatbot_backend.py
    create_simplified_version(consolidated)

def create_simplified_version(full_data):
    """Create a simplified version that works with the current chatbot_backend.py"""
    simplified = {
        "member_id": "member1",
        "assigned_questions": full_data.get('assigned_questions', []),
        "training_samples": full_data.get('training_samples', []),
        "entity_dictionary": full_data.get('entity_dictionary', {}),
        "response_templates": full_data.get('response_templates', {}),
        "location_profiles": full_data.get('location_profiles', {}),
        "financing_info": full_data.get('financing_info', {}),
        "metadata": full_data.get('metadata', {})
    }
    
    # Save as member1's main training_data.json (backup old one first)
    original_path = os.path.join('data', 'member1', 'training_data.json')
    backup_path = os.path.join('data', 'member1', 'training_data_backup.json')
    
    # Backup original if exists
    if os.path.exists(original_path):
        import shutil
        shutil.copy2(original_path, backup_path)
        print(f"📦 Backed up original to: {backup_path}")
    
    # Save simplified version
    with open(original_path, 'w', encoding='utf-8') as f:
        json.dump(simplified, f, indent=2, ensure_ascii=False)
    
    print(f"✅ Created simplified version at: {original_path}")
    print("   This file will be used by chatbot_backend.py")

if __name__ == "__main__":
    print("="*60)
    print("🔄 MERGING ALL TRAINING DATA")
    print("="*60)
    merge_training_data()