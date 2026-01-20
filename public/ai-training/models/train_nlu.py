# backend/train_nlu.py (updated with your dependencies)
import json
import spacy
from sklearn.feature_extraction.text import CountVectorizer
from sklearn.naive_bayes import MultinomialNB
import pickle
import os
import glob
import pandas as pd
import numpy as np

class TeamNLUTrainer:
    def __init__(self):
        # Try to load spaCy, fallback if not available
        try:
            self.nlp = spacy.load("en_core_web_sm")
            print("✅ spaCy model loaded")
        except:
            print("⚠️ spaCy model not found. Install with: python -m spacy download en_core_web_sm")
            self.nlp = None
        
        self.vectorizer = CountVectorizer(ngram_range=(1, 2))
        self.classifier = MultinomialNB()
        
        # Team member assignments
        self.team_assignments = {
            'member1': ['find_property', 'financing', 'location_info'],
            'member2': ['find_property_with_criteria', 'find_near_landmark', 'find_ready_property'],
            'member3': ['find_property_for_need', 'find_with_feature', 'process_info', 'match_needs']
        }
    
    def load_team_data(self, base_path='data'):
        """Load training data from all team members"""
        texts = []
        intents = []
        
        print("👥 Loading team training data...")
        
        # Look for member training files
        member_files = glob.glob(os.path.join(base_path, 'member*', 'training_data.json'))
        
        if not member_files:
            print("⚠️ No member training files found!")
            return texts, intents
        
        for member_file in member_files:
            member_name = os.path.basename(os.path.dirname(member_file))
            print(f"📁 Loading {member_name} data...")
            
            try:
                with open(member_file, 'r') as f:
                    data = json.load(f)
                
                # Extract training samples
                for sample in data.get('training_samples', []):
                    # Original query
                    texts.append(sample['query'])
                    intents.append(sample['intent'])
                    
                    # Variations
                    for variation in sample.get('variations', []):
                        texts.append(variation)
                        intents.append(sample['intent'])
                
                print(f"   ✅ Loaded {len(data.get('training_samples', []))} samples")
                
            except Exception as e:
                print(f"   ❌ Error loading {member_file}: {e}")
        
        return texts, intents
    
    def train(self, training_texts, training_intents):
        """Train the NLU model"""
        if not training_texts:
            print("❌ No training data provided!")
            return False
        
        print(f"\n🚀 Training model with {len(training_texts)} samples...")
        
        # Vectorize text
        X = self.vectorizer.fit_transform(training_texts)
        
        # Train classifier
        self.classifier.fit(X, training_intents)
        
        print(f"✅ Model trained successfully!")
        print(f"📊 Total intents: {len(set(training_intents))}")
        print(f"📋 Intent classes: {sorted(set(training_intents))}")
        
        return True
    
    def save_model(self, model_path='models/nlu_model.pkl'):
        """Save trained model with version info"""
        model_data = {
            'vectorizer': self.vectorizer,
            'classifier': self.classifier,
            'classes': self.classifier.classes_.tolist(),
            'version': '2.0',
            'training_date': pd.Timestamp.now().isoformat()
        }
        
        os.makedirs(os.path.dirname(model_path), exist_ok=True)
        
        with open(model_path, 'wb') as f:
            pickle.dump(model_data, f)
        
        print(f"\n💾 Model saved to {model_path}")
        print(f"📊 Model info:")
        print(f"  - Classes: {len(model_data['classes'])} intents")
        print(f"  - Version: {model_data['version']}")
        print(f"  - Date: {model_data['training_date']}")
    
    # ... (rest of your existing train_nlu.py methods)

def main():
    print("=" * 60)
    print("🏠 BAH.AI PROPERTY CHATBOT TRAINING SYSTEM v2.0")
    print("=" * 60)
    
    trainer = TeamNLUTrainer()
    
    # Load and train
    texts, intents = trainer.load_team_data('data')
    
    if texts:
        trainer.train(texts, intents)
        trainer.save_model()
        
        # Test predictions
        print("\n🧪 Testing predictions:")
        test_queries = [
            "find apartments in batangas city",
            "show me properties with bank financing",
            "tell me about lipa city"
        ]
        
        for query in test_queries:
            X = trainer.vectorizer.transform([query])
            intent = trainer.classifier.predict(X)[0]
            proba = trainer.classifier.predict_proba(X).max()
            print(f"'{query}' → {intent} ({proba:.1%})")
    else:
        print("❌ No training data found!")

if __name__ == "__main__":
    main()