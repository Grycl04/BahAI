import json
import os

def load_json_file(filepath):
    """Load a JSON file with error handling"""
    try:
        if not os.path.exists(filepath):
            print(f"❌ File does not exist: {filepath}")
            return None
            
        with open(filepath, 'r', encoding='utf-8') as f:
            data = json.load(f)
            print(f"✅ Loaded: {filepath}")
            return data
    except json.JSONDecodeError as e:
        print(f"❌ JSON error in {filepath}: {e}")
        return None
    except Exception as e:
        print(f"❌ Error loading {filepath}: {e}")
        return None

def main():
    print("=" * 60)
    print("BAHAI AI TRAINING DATA LOADER")
    print("=" * 60)
    
    # Get current directory
    current_dir = os.getcwd()
    print(f"📂 Current directory: {current_dir}")
    print()
    
    # Test paths
    test_paths = [
        "data/member1/training_data.json",
        "data/shared/batangas_complete.json",
        "data/shared/all_questions.json",
        "data/shared/synonyms.json"
    ]
    
    for path in test_paths:
        print(f"📁 Testing: {path}")
        
        # Check if file exists
        if os.path.exists(path):
            print(f"   ✅ File exists")
            
            # Try to load it
            data = load_json_file(path)
            if data:
                print(f"   ✅ JSON is valid")
                
                # Show basic info
                if "member_id" in data:
                    print(f"   👤 Member ID: {data['member_id']}")
                if "batangas_locations" in data:
                    cities = list(data['batangas_locations'].keys())
                    print(f"   🏙️  Cities: {len(cities)} cities")
                if "question_templates" in data:
                    print(f"   ❓ Questions: {len(data['question_templates'])} templates")
                if "verbs" in data:
                    print(f"   📝 Synonyms: {len(data)} categories")
                    
        else:
            print(f"   ❌ File NOT FOUND")
        
        print()

if __name__ == "__main__":
    main()