import json
import spacy
from sklearn.feature_extraction.text import TfidfVectorizer
from sklearn.naive_bayes import MultinomialNB
from sklearn.svm import SVC
from sklearn.pipeline import Pipeline
from sklearn.model_selection import train_test_split
from sklearn.metrics import accuracy_score
import pickle
import os
import glob
import pandas as pd
import numpy as np
import re
from collections import Counter
import logging
import random
from datetime import datetime

# Set up logging
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

class TeamNLUTrainer:
    def __init__(self):
        # Try to load spaCy, fallback if not available
        try:
            self.nlp = spacy.load("en_core_web_sm")
            logger.info("✅ spaCy model loaded")
        except:
            logger.warning("⚠️ spaCy model not found. Using basic preprocessing.")
            self.nlp = None
        
        # Create pipeline with improved parameters
        self.pipeline = Pipeline([
            ('tfidf', TfidfVectorizer(
                ngram_range=(1, 3),  # Changed from (1,2) to (1,3)
                max_features=2000,    # Increased from 1500
                stop_words='english',
                min_df=2,
                max_df=0.8
            )),
            ('classifier', SVC(
                kernel='linear',
                probability=True,
                random_state=42,
                C=1.0,  # Added regularization parameter
                class_weight='balanced'  # Handle class imbalance
            ))
        ])
        
        # Team member assignments
        self.team_assignments = {
            'member1': ['find_property', 'financing', 'location_info'],
            'member2': ['find_property_with_criteria', 'find_near_landmark', 'find_ready_property'],
            'member3': ['find_property_for_need', 'find_with_feature', 'process_info', 'match_needs']
        }
        
        # Template to intent mapping (updated with correct mapping)
        self.template_intent_map = {
            'question_1': 'find_property',
            'question_2': 'find_property_with_criteria',
            'question_3': 'find_property_for_need',
            'question_4': 'find_near_landmark',
            'question_5': 'find_with_feature',
            'question_6': 'find_ready_property',
            'question_7': 'financing',
            'question_8': 'process_info',
            'question_9': 'location_info',
            'question_10': 'match_needs'
        }
        
        # Intent mapping from old names to standard names
        self.intent_mapping = {
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
            
            # Add these for better classification
            'villa': 'find_property',  # "properties with villa" should be find_property
            'steps': 'process_info',   # "steps for buying" should be process_info
            'how to': 'process_info',  # "how to get mortgage" should be financing or process_info
            'ready': 'find_ready_property',  # "ready to move" should be find_ready_property
        }
        
        # Load Batangas data for location training
        self.batangas_data = self.load_batangas_data()

    def load_batangas_data(self):
        """Load Batangas complete data for location-based training"""
        batangas_file = 'data/shared/batangas_complete.json'
        if not os.path.exists(batangas_file):
            logger.warning(f"⚠️ Batangas data file not found: {batangas_file}")
            return {}
        
        try:
            with open(batangas_file, 'r', encoding='utf-8') as f:
                data = json.load(f)
            logger.info("✅ Batangas data loaded successfully")
            return data
        except Exception as e:
            logger.error(f"❌ Error loading Batangas data: {e}")
            return {}

    def clean_json_file(self, filepath):
        """Fix JSON file by properly loading and saving it"""
        try:
            # Read the file
            with open(filepath, 'r', encoding='utf-8') as f:
                content = f.read()
            
            # Remove any trailing commas before closing braces/brackets
            content = re.sub(r',\s*}', '}', content)
            content = re.sub(r',\s*]', ']', content)
            
            # Fix comment lines (remove // comments)
            lines = content.split('\n')
            cleaned_lines = []
            for line in lines:
                # Remove // comments
                if '//' in line:
                    line = line.split('//')[0]
                cleaned_lines.append(line.strip())
            
            # Join lines
            content = '\n'.join(cleaned_lines)
            
            # Parse the JSON
            try:
                data = json.loads(content)
            except json.JSONDecodeError as e:
                logger.error(f"❌ JSON parsing failed for {filepath}: {e}")
                
                # Try to fix by finding the problematic section
                # Remove any empty lines
                content = '\n'.join([line for line in content.split('\n') if line.strip()])
                
                # Try to load it as a string and manually parse
                # Look for specific patterns that might be causing issues
                content = re.sub(r'(\w+):', r'"\1":', content)  # Add quotes to unquoted keys
                
                try:
                    data = json.loads(content)
                except:
                    # Last resort: create minimal valid JSON
                    logger.warning(f"⚠️ Creating minimal valid JSON for {filepath}")
                    data = {
                        "member_id": "member1",
                        "assigned_questions": [],
                        "training_samples": [],
                        "entity_dictionary": {},
                        "response_templates": {},
                        "metadata": {}
                    }
            
            # Write it back with proper formatting
            with open(filepath, 'w', encoding='utf-8') as f:
                json.dump(data, f, indent=2, ensure_ascii=False)
            
            logger.info(f"✅ Cleaned {filepath}")
            return True
            
        except Exception as e:
            logger.error(f"❌ Error cleaning {filepath}: {e}")
            return False

    def preprocess_text(self, text):
        """Preprocess text for training with keyword preservation"""
        if not text:
            return ""
        
        text = str(text).lower()
        
        # Preserve important intent keywords
        intent_keywords = {
            'process_info': ['steps', 'process', 'procedure', 'timeline', 'how to', 'buying', 'purchase'],
            'financing': ['financing', 'mortgage', 'loan', 'pag-ibig', 'bank', 'payment', 'installment'],
            'find_with_feature': ['with', 'featuring', 'having', 'includes', 'equipped'],
            'find_near_landmark': ['near', 'close to', 'around', 'beside', 'adjacent to'],
            'find_ready_property': ['ready', 'available now', 'immediate', 'move in'],
            'location_info': ['about', 'describe', 'tell me about', 'what is', 'like to live'],
        }
        
        # Keep original text for important keywords
        preserved_text = text
        
        # Remove special characters but keep spaces and basic punctuation
        text = re.sub(r'[^\w\s\?\.]', ' ', text)
        
        # Remove extra spaces
        text = re.sub(r'\s+', ' ', text).strip()
        
        # If spaCy is loaded, do lemmatization but preserve intent keywords
        if self.nlp:
            doc = self.nlp(text)
            tokens = []
            for token in doc:
                token_text = token.text.lower()
                
                # Check if this token is an important keyword
                is_important = False
                for intent, keywords in intent_keywords.items():
                    if any(keyword in preserved_text for keyword in keywords):
                        # If the query contains important keywords for this intent,
                        # preserve the original words
                        is_important = True
                        break
                
                if is_important and token_text in preserved_text:
                    tokens.append(token_text)  # Keep original
                elif not token.is_stop and not token.is_punct:
                    tokens.append(token.lemma_)
            return ' '.join(tokens)
        
        return text

    def load_member_data(self, base_path='data'):
        """Load training data from all team members"""
        texts = []
        intents = []
        
        member_files = glob.glob(os.path.join(base_path, 'member*', 'training_data.json'))
        
        if not member_files:
            logger.warning("❌ No member training files found!")
            return texts, intents
        
        for member_file in member_files:
            member_name = os.path.basename(os.path.dirname(member_file))
            print(f"📂 Loading {member_name} data...")
            
            # Clean the JSON file first
            self.clean_json_file(member_file)
            
            try:
                with open(member_file, 'r', encoding='utf-8') as f:
                    data = json.load(f)
                
                samples = data.get('training_samples', [])
                
                for sample in samples:
                    # Get intent and map to standard name
                    original_intent = sample.get('intent', '')
                    mapped_intent = self.intent_mapping.get(original_intent, original_intent)
                    
                    # Main query
                    query = sample.get('query', '').strip()
                    if query:
                        texts.append(self.preprocess_text(query))
                        intents.append(mapped_intent)
                    
                    # Variations
                    variations = sample.get('variations', [])
                    for variation in variations:
                        if isinstance(variation, str) and variation.strip():
                            texts.append(self.preprocess_text(variation))
                            intents.append(mapped_intent)
                
                print(f"   ✅ Loaded {len(samples)} samples from {member_name}")
                
            except json.JSONDecodeError as e:
                print(f"   ❌ JSON Error in {member_file}: {e}")
                # Try alternative loading
                try:
                    with open(member_file, 'r', encoding='utf-8') as f:
                        content = f.read()
                        # Remove problematic characters more aggressively
                        content = re.sub(r'[^\x20-\x7E]', ' ', content)
                        data = json.loads(content)
                    
                    samples = data.get('training_samples', [])
                    print(f"   ✅ Loaded {len(samples)} samples after cleaning")
                except Exception as e2:
                    print(f"   ❌ Failed to load {member_file}: {e2}")
            except Exception as e:
                print(f"   ❌ Error loading {member_file}: {e}")
        
        return texts, intents

    def load_shared_questions(self, shared_path='data/shared'):
        """Load question templates from all_questions.json"""
        texts = []
        intents = []
        
        questions_file = os.path.join(shared_path, 'all_questions.json')
        
        if not os.path.exists(questions_file):
            print(f"❌ Shared questions file not found: {questions_file}")
            return texts, intents
        
        try:
            with open(questions_file, 'r', encoding='utf-8') as f:
                data = json.load(f)
            
            question_templates = data.get('question_templates', {})
            print(f"📂 Loading {len(question_templates)} question templates...")
            
            templates_loaded = 0
            
            for q_id, q_data in question_templates.items():
                # Get intent from mapping
                intent = self.template_intent_map.get(q_id, 'unknown')
                
                # Add the example query
                example = q_data.get('example', '')
                if example:
                    texts.append(self.preprocess_text(example))
                    intents.append(intent)
                    templates_loaded += 1
                
                # Add templates
                templates = q_data.get('templates', [])
                if isinstance(templates, list):
                    for template in templates:
                        if isinstance(template, str) and template.strip():
                            texts.append(self.preprocess_text(template))
                            intents.append(intent)
                            templates_loaded += 1
                elif isinstance(templates, str) and templates.strip():
                    texts.append(self.preprocess_text(templates))
                    intents.append(intent)
                    templates_loaded += 1
            
            print(f"   ✅ Generated {templates_loaded} samples from templates")
            
        except Exception as e:
            print(f"   ❌ Error loading questions file: {e}")
        
        return texts, intents

    def load_synonyms_as_training(self, shared_path='data/shared'):
        """Load synonyms and generate training samples"""
        texts = []
        intents = []
        
        synonyms_file = os.path.join(shared_path, 'synonyms.json')
        
        if not os.path.exists(synonyms_file):
            print(f"❌ Synonyms file not found: {synonyms_file}")
            return texts, intents
        
        try:
            with open(synonyms_file, 'r', encoding='utf-8') as f:
                data = json.load(f)
            
            print("📂 Loading synonyms data...")
            
            # Map phrase categories to intents
            phrase_intent_map = {
                'property_search': 'find_property',
                'price_inquiry': 'financing',
                'location_specific': 'location_info',
                'feature_requests': 'find_with_feature',
                'process_questions': 'process_info',
                'property_inquiry': 'find_property',
                'budget_planning': 'financing',
                'area_info': 'location_info',
                'amenity_requests': 'find_with_feature',
                'buying_process': 'process_info'
            }
            
            # Use phrases section
            phrases = data.get('phrases', {})
            for category, phrase_list in phrases.items():
                if isinstance(phrase_list, list):
                    intent = phrase_intent_map.get(category, 'find_property')
                    for phrase in phrase_list[:10]:  # Limit to 10 per category
                        if isinstance(phrase, str) and phrase.strip():
                            texts.append(self.preprocess_text(phrase))
                            intents.append(intent)
            
            # Use synonyms to generate variations
            synonyms = data.get('synonyms', {})
            base_queries = [
                "find apartments in batangas",
                "show me houses for sale",
                "properties near school",
                "how much is the rent",
                "tell me about lipa city",
                "steps for buying a house",
                "ready to move in properties"
            ]
            
            for query in base_queries:
                # Map query to intent
                query_intent = 'find_property'
                if 'how much' in query or 'rent' in query:
                    query_intent = 'financing'
                elif 'tell me about' in query:
                    query_intent = 'location_info'
                elif 'steps' in query:
                    query_intent = 'process_info'
                elif 'ready to move' in query:
                    query_intent = 'find_ready_property'
                
                # Add base query
                texts.append(self.preprocess_text(query))
                intents.append(query_intent)
                
                # Generate variations with synonyms
                for category, synonym_list in synonyms.items():
                    if isinstance(synonym_list, list):
                        for synonym in synonym_list[:3]:  # Limit to 3 synonyms per category
                            if isinstance(synonym, str):
                                variation = query.replace(category, synonym)
                                texts.append(self.preprocess_text(variation))
                                intents.append(query_intent)
            
            print(f"   ✅ Generated {len(texts)} samples from synonyms")
            
        except Exception as e:
            print(f"   ❌ Error loading synonyms: {e}")
        
        return texts, intents

    def load_batangas_training(self):
        """Generate training data from Batangas complete data"""
        texts = []
        intents = []
        
        if not self.batangas_data:
            return texts, intents
        
        print("📂 Loading Batangas location data for training...")
        
        # Get locations from batangas data
        locations = self.batangas_data.get('batangas_locations', {})
        landmark_categories = self.batangas_data.get('landmark_categories', {})
        
        # Generate location-specific queries
        for location_name, location_data in locations.items():
            # Location info queries
            texts.append(f"tell me about {location_name.lower()}")
            intents.append('location_info')
            
            texts.append(f"information about {location_name.lower()}")
            intents.append('location_info')
            
            texts.append(f"what's in {location_name.lower()}")
            intents.append('location_info')
            
            # Find property queries with specific locations
            texts.append(f"find properties in {location_name.lower()}")
            intents.append('find_property')
            
            texts.append(f"show me houses in {location_name.lower()}")
            intents.append('find_property')
            
            texts.append(f"apartments for rent in {location_name.lower()}")
            intents.append('find_property')
            
            # Add variations with different property types
            property_types = location_data.get('property_types_common', [])
            for prop_type in property_types[:3]:  # Limit to 3 property types
                if isinstance(prop_type, str):
                    texts.append(f"find {prop_type} in {location_name.lower()}")
                    intents.append('find_property')
        
        # Generate landmark-related queries
        for category, landmarks in landmark_categories.items():
            for landmark in landmarks[:5]:  # Limit to 5 landmarks per category
                if isinstance(landmark, str):
                    texts.append(f"properties near {landmark.lower()}")
                    intents.append('find_near_landmark')
                    
                    texts.append(f"houses close to {landmark.lower()}")
                    intents.append('find_near_landmark')
                    
                    texts.append(f"apartments around {landmark.lower()}")
                    intents.append('find_near_landmark')
        
        # Generate property feature queries
        property_categories = self.batangas_data.get('property_categories', {})
        residential_types = property_categories.get('residential', [])
        
        for prop_type in residential_types[:5]:
            if isinstance(prop_type, str):
                texts.append(f"properties with {prop_type}")
                intents.append('find_with_feature')
        
        print(f"   ✅ Generated {len(texts)} samples from Batangas data")
        return texts, intents

    def load_additional_training(self, filepath='data/additional_training.json'):
        """Load additional training data"""
        texts = []
        intents = []
        
        if not os.path.exists(filepath):
            return texts, intents
        
        try:
            with open(filepath, 'r', encoding='utf-8') as f:
                data = json.load(f)
            
            additional_samples = data.get('additional_samples', [])
            for sample in additional_samples:
                text = sample.get('text', '').strip()
                intent = sample.get('intent', '').strip()
                if text and intent:
                    texts.append(self.preprocess_text(text))
                    intents.append(intent)
            
            logger.info(f"✅ Loaded {len(additional_samples)} additional samples")
        except Exception as e:
            logger.error(f"❌ Error loading additional training: {e}")
        
        return texts, intents

    def generate_additional_variations(self, texts, intents):
        """Generate additional variations for training"""
        new_texts = []
        new_intents = []
        
        # Common variations to generate (limit to first 50 to avoid too many)
        for i, (text, intent) in enumerate(zip(texts[:50], intents[:50])):
            # Add question mark variations
            if not text.endswith('?'):
                new_texts.append(text + '?')
                new_intents.append(intent)
            
            # Add "please" variations
            if not text.startswith('please'):
                new_texts.append('please ' + text)
                new_intents.append(intent)
            
            # Add "can you" variations
            if not text.startswith('can you'):
                new_texts.append('can you ' + text)
                new_intents.append(intent)
            
            # Add "i need" variations
            new_texts.append('i need ' + text)
            new_intents.append(intent)
            
            # Add "looking for" variations for find intents
            if intent.startswith('find'):
                new_texts.append('looking for ' + text.replace('find ', '').replace('show me ', '').replace('search for ', ''))
                new_intents.append(intent)
        
        return new_texts, new_intents

    def load_all_training_data(self, base_path='data'):
        """Load ALL training data from all sources"""
        all_texts = []
        all_intents = []
        
        print("="*60)
        print("🚀 LOADING ALL TRAINING DATA SOURCES")
        print("="*60)
        
        # 1. Load member data
        print("\n📁 Source 1: Member Training Data")
        member_texts, member_intents = self.load_member_data(base_path)
        all_texts.extend(member_texts)
        all_intents.extend(member_intents)
        print(f"   Total so far: {len(all_texts)} samples")
        
        # 2. Load shared questions
        print("\n📁 Source 2: Shared Question Templates")
        shared_path = os.path.join(base_path, 'shared')
        question_texts, question_intents = self.load_shared_questions(shared_path)
        all_texts.extend(question_texts)
        all_intents.extend(question_intents)
        print(f"   Total so far: {len(all_texts)} samples")
        
        # 3. Load synonyms as training data
        print("\n📁 Source 3: Synonyms and Phrases")
        synonym_texts, synonym_intents = self.load_synonyms_as_training(shared_path)
        all_texts.extend(synonym_texts)
        all_intents.extend(synonym_intents)
        print(f"   Total so far: {len(all_texts)} samples")
        
        # 4. Load Batangas data for training
        print("\n📁 Source 4: Batangas Location Data")
        batangas_texts, batangas_intents = self.load_batangas_training()
        all_texts.extend(batangas_texts)
        all_intents.extend(batangas_intents)
        print(f"   Total so far: {len(all_texts)} samples")
        
        # 5. Load additional training data
        print("\n📁 Source 5: Additional Training Data")
        additional_texts, additional_intents = self.load_additional_training()
        all_texts.extend(additional_texts)
        all_intents.extend(additional_intents)
        print(f"   Total so far: {len(all_texts)} samples")
        
        # 6. Generate additional variations
        print("\n📁 Source 6: Generated Variations")
        generated_texts, generated_intents = self.generate_additional_variations(all_texts, all_intents)
        all_texts.extend(generated_texts)
        all_intents.extend(generated_intents)
        
        print("="*60)
        print(f"📊 FINAL TRAINING DATA STATISTICS")
        print("="*60)
        print(f"✅ Total samples: {len(all_texts)}")
        
        # Count unique intents
        unique_intents = set(all_intents)
        print(f"✅ Unique intents: {len(unique_intents)}")
        
        # Count intent distribution
        intent_counts = Counter(all_intents)
        print(f"✅ Intent distribution:")
        for intent, count in intent_counts.most_common():
            print(f"   • {intent}: {count} samples")
        
        return all_texts, all_intents

    def train(self, training_texts, training_intents):
        """Train the NLU model with class balancing"""
        if not training_texts:
            logger.error("❌ No training data provided!")
            return False
        
        print(f"\n🧠 Training model with {len(training_texts)} samples...")
        
        # Check class distribution
        intent_counts = Counter(training_intents)
        print(f"📊 Class distribution before balancing:")
        for intent, count in intent_counts.most_common():
            print(f"   • {intent}: {count} samples")
        
        # Balance the dataset by oversampling minority classes
        balanced_texts = []
        balanced_intents = []
        
        # Find maximum class count
        max_count = max(intent_counts.values())
        
        for intent in intent_counts:
            # Get all samples for this intent
            intent_samples = [(text, intent_label) 
                             for text, intent_label in zip(training_texts, training_intents) 
                             if intent_label == intent]
            
            # If this class has fewer samples, oversample it
            if len(intent_samples) < max_count:
                # Calculate how many additional samples needed
                needed = max_count - len(intent_samples)
                
                # Add original samples
                for text, intent_label in intent_samples:
                    balanced_texts.append(text)
                    balanced_intents.append(intent_label)
                
                # Add oversampled samples
                for _ in range(needed):
                    text, intent_label = random.choice(intent_samples)
                    balanced_texts.append(text)
                    balanced_intents.append(intent_label)
            else:
                # Add all samples as is
                for text, intent_label in intent_samples:
                    balanced_texts.append(text)
                    balanced_intents.append(intent_label)
        
        print(f"📊 After balancing: {len(balanced_texts)} samples")
        
        # Split data for training and validation
        X_train, X_val, y_train, y_val = train_test_split(
            balanced_texts, balanced_intents, 
            test_size=0.2, random_state=42, 
            stratify=balanced_intents
        )
        
        # Train the model
        self.pipeline.fit(X_train, y_train)
        
        # Calculate accuracy
        train_predictions = self.pipeline.predict(X_train)
        train_accuracy = accuracy_score(y_train, train_predictions)
        
        val_predictions = self.pipeline.predict(X_val)
        val_accuracy = accuracy_score(y_val, val_predictions)
        
        print(f"✅ Model trained successfully!")
        print(f"📈 Total intents: {len(set(training_intents))}")
        print(f"📈 Intent classes: {sorted(set(training_intents))}")
        print(f"📈 Training accuracy: {train_accuracy:.2%}")
        print(f"📈 Validation accuracy: {val_accuracy:.2%}")
        
        # Show misclassified examples
        misclassified = []
        for i, (true, pred) in enumerate(zip(y_val, val_predictions)):
            if true != pred:
                misclassified.append({
                    'text': X_val[i],
                    'true': true,
                    'pred': pred
                })
        
        if misclassified:
            print(f"\n⚠️  Found {len(misclassified)} misclassified validation samples:")
            for i, case in enumerate(misclassified[:5]):  # Show first 5
                print(f"   {i+1}. '{case['text'][:50]}...' → True: {case['true']}, Pred: {case['pred']}")
        
        return True

    def save_model(self, model_path='models/nlu_model.pkl'):
        """Save trained model with version info"""
        model_data = {
            'vectorizer': self.pipeline.named_steps['tfidf'],
            'classifier': self.pipeline.named_steps['classifier'],
            'classes': self.pipeline.classes_.tolist(),
            'version': '3.3',  # Updated version
            'training_date': datetime.now().isoformat(),
            'feature_count': len(self.pipeline.named_steps['tfidf'].get_feature_names_out()),
            'intent_mapping': self.intent_mapping,
            'template_intent_map': self.template_intent_map,
            'batangas_data_loaded': bool(self.batangas_data)
        }
        
        os.makedirs(os.path.dirname(model_path), exist_ok=True)
        
        with open(model_path, 'wb') as f:
            pickle.dump(model_data, f)
        
        print(f"\n💾 Model saved to {model_path}")
        print(f"📊 Model info:")
        print(f"   • Version: {model_data['version']}")
        print(f"   • Classes: {len(model_data['classes'])} intents")
        print(f"   • Date: {model_data['training_date']}")
        print(f"   • Features: {model_data['feature_count']}")
        print(f"   • Batangas Data: {'✅ Loaded' if model_data['batangas_data_loaded'] else '❌ Not loaded'}")
        
        return model_path

def test_predictions(trainer, test_queries):
    """Test model predictions"""
    print("\n" + "="*60)
    print("🧪 TESTING PREDICTIONS")
    print("="*60)
    
    for query in test_queries:
        try:
            intent = trainer.pipeline.predict([query])[0]
            proba = trainer.pipeline.predict_proba([query])[0]
            confidence = max(proba) * 100
            intent_idx = list(trainer.pipeline.classes_).index(intent)
            
            print(f"🔍 '{query}'")
            print(f"   → Intent: {intent} ({confidence:.1f}% confidence)")
            
            # Show top 3 intents for ambiguous queries
            if confidence < 80:
                top_indices = np.argsort(proba)[-3:][::-1]
                print(f"   Top alternatives:")
                for idx in top_indices:
                    if idx != intent_idx:
                        intent_name = trainer.pipeline.classes_[idx]
                        intent_prob = proba[idx] * 100
                        print(f"     • {intent_name}: {intent_prob:.1f}%")
        except Exception as e:
            print(f"❌ Error predicting '{query}': {e}")

def create_additional_training_file():
    """Create additional training data file to fix common issues"""
    additional_data = {
        "additional_samples": [
            {"text": "properties with swimming pool", "intent": "find_with_feature"},
            {"text": "houses with pool", "intent": "find_with_feature"},
            {"text": "apartments with swimming pool", "intent": "find_with_feature"},
            {"text": "condos with pool facility", "intent": "find_with_feature"},
            {"text": "homes with swimming pool", "intent": "find_with_feature"},
            {"text": "properties featuring pool", "intent": "find_with_feature"},
            {"text": "pool properties for sale", "intent": "find_with_feature"},
            {"text": "houses with private pool", "intent": "find_with_feature"},
            {"text": "properties with garden", "intent": "find_with_feature"},
            {"text": "homes with backyard", "intent": "find_with_feature"},
            {"text": "properties with parking space", "intent": "find_with_feature"},
            {"text": "houses with garage", "intent": "find_with_feature"},
            {"text": "apartments with elevator", "intent": "find_with_feature"},
            {"text": "properties with security", "intent": "find_with_feature"},
            {"text": "houses with wifi", "intent": "find_with_feature"},
            {"text": "properties near batangas port", "intent": "find_near_landmark"},
            {"text": "houses close to malls", "intent": "find_near_landmark"},
            {"text": "apartments near hospitals", "intent": "find_near_landmark"},
            {"text": "condos near schools", "intent": "find_near_landmark"},
            {"text": "properties around universities", "intent": "find_near_landmark"},
            {"text": "how to get bank loan", "intent": "financing"},
            {"text": "pag-ibig financing requirements", "intent": "financing"},
            {"text": "mortgage application process", "intent": "financing"},
            {"text": "bank financing options", "intent": "financing"},
            {"text": "in-house financing terms", "intent": "financing"},
            {"text": "steps for property purchase", "intent": "process_info"},
            {"text": "buying process timeline", "intent": "process_info"},
            {"text": "property acquisition steps", "intent": "process_info"},
            {"text": "how to buy a condo", "intent": "process_info"},
            {"text": "house purchase procedure", "intent": "process_info"}
        ]
    }
    
    os.makedirs('data', exist_ok=True)
    with open('data/additional_training.json', 'w', encoding='utf-8') as f:
        json.dump(additional_data, f, indent=2)
    
    print("✅ Created additional_training.json with 30 samples")

def main():
    print("="*60)
    print("🚀 BAH.AI PROPERTY CHATBOT TRAINING SYSTEM v3.3")
    print("="*60)
    
    # Create additional training data file
    create_additional_training_file()
    
    # Initialize trainer
    trainer = TeamNLUTrainer()
    
    # Load and train using ALL data sources
    texts, intents = trainer.load_all_training_data('data')
    
    if texts:
        if trainer.train(texts, intents):
            trainer.save_model()
            
            # Test predictions with common queries (including Batangas locations)
            test_queries = [
                "find apartments in batangas city",
                "show me properties with bank financing",
                "tell me about lipa city",
                "properties near schools",
                "houses under 3M with 3 bedrooms",
                "ready to move in properties for family",
                "steps for buying a house",
                "properties with swimming pool",
                "best properties for family lifestyle",
                "cheap houses for sale",
                "condos near malls",
                "how to get mortgage",
                "available now apartments",
                "properties with garden",
                "what documents for pag-ibig loan",
                "houses for big family",
                "properties in tanauan city",
                "apartments with parking",
                "bank financing requirements",
                "ready to occupy houses",
                "tell me about nasugbu",
                "properties near taal volcano",
                "houses in san juan",
                "apartments near batangas state university",
                "condos in sto tomas city"
            ]
            test_predictions(trainer, test_queries)
    else:
        print("❌ No training data found!")
        print("💡 Make sure your data folder structure is:")
        print("   data/")
        print("   ├── member1/training_data.json")
        print("   ├── member2/training_data.json")
        print("   ├── member3/training_data.json")
        print("   ├── additional_training.json")
        print("   └── shared/")
        print("       ├── all_questions.json")
        print("       ├── synonyms.json")
        print("       └── batangas_complete.json")
    
    print("\n" + "="*60)
    print("✅ TRAINING COMPLETE!")
    print("="*60)

if __name__ == "__main__":
    main()