import json
import spacy
from sklearn.feature_extraction.text import TfidfVectorizer
from sklearn.naive_bayes import MultinomialNB
from sklearn.svm import SVC
from sklearn.pipeline import Pipeline
from sklearn.model_selection import train_test_split
from sklearn.metrics import accuracy_score, classification_report
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
import shutil
import sys


# Set up logging
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

class TeamNLUTrainer:
    def __init__(self):
        self.training_dir = os.path.dirname(os.path.abspath(__file__))
        self.data_dir = os.path.join(self.training_dir, 'data')

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
                ngram_range=(1, 3),
                max_features=2500,
                stop_words='english',
                min_df=2,
                max_df=0.8
            )),
            ('classifier', SVC(
                kernel='linear',
                probability=True,
                random_state=42,
                C=1.0,
                class_weight='balanced'
            ))
        ])
        
        # Team member assignments
        self.team_assignments = {
            'member1': ['find_property', 'financing', 'location_info'],
            'member2': ['find_property_with_criteria', 'find_near_landmark', 'find_ready_property'],
            'member3': ['find_property_for_need', 'find_with_feature', 'process_info', 'match_needs']
        }
        
        # Template to intent mapping
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
                # Add basic intents
            'greeting': 'greeting',
            'thanks': 'thanks',
            'help': 'help',
            'about_system': 'about_system',
            'out_of_scope': 'out_of_scope',
            'goodbye': 'goodbye',
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
                'buyer_signup': 'buyer_signup',
    'buyer_signup_requirements': 'buyer_signup_requirements',
    'buyer_signup_password': 'buyer_signup_password',
    'buyer_signup_phone': 'buyer_signup_phone',
    'buyer_login': 'buyer_login',
    'buyer_login_google': 'buyer_login_google',
    'buyer_forgot_password': 'buyer_forgot_password',
    'buyer_email_verification': 'buyer_email_verification',
    'buyer_verify_otp': 'buyer_verify_otp',
    'buyer_resend_otp': 'buyer_resend_otp',
    'buyer_login_errors': 'buyer_login_errors',
    'buyer_logout': 'buyer_logout',
    'buyer_account_settings': 'buyer_account_settings',
    'buyer_update_profile': 'buyer_update_profile',
    'buyer_guest_access': 'buyer_guest_access',
    'buyer_kyc': 'buyer_kyc',
    'buyer_chatbot_how': 'buyer_chatbot_how',
    'buyer_dashboard_flow': 'buyer_dashboard_flow',
    'buyer_recommendations_how': 'buyer_recommendations_how',
    'buyer_messages_how': 'buyer_messages_how',
    'buyer_liked_saved_how': 'buyer_liked_saved_how',
        }
        
        # Intent keywords for better classification
        self.intent_keywords = {
    'greeting': ['hi', 'hello', 'hey', 'greetings', 'good morning', 'good afternoon', 'good evening', 
                 'how are you', 'what\'s up', 'sup', 'hi there', 'hello there'],
    'thanks': ['thank you', 'thanks', 'thank', 'thanks a lot', 'appreciate', 'grateful'],
    'help': ['help', 'need help', 'can you help', 'assist', 'support', 'guide', 'how to use'],
    'about_system': [
        'what are you', 'who are you', 'what is this', 'what is the system', 
        'what do you do', 'what can you help with', 'tell me about yourself',
        'what is this system about', 'what is this chatbot', 'what is bah.ai',
        'introduce yourself', 'system overview', 'what is your purpose',  # Add these
        'what services do you offer', 'give me an overview', 'explain your features'
    ],
    'goodbye': ['bye', 'goodbye', 'see you', 'farewell', 'exit', 'quit', 'end', 'that is all', 'nothing else', 'done for now', 'talk later'],
            'financing': ['accept bank financing', 'accept financing', 'bank loan', 
                         'mortgage', 'pag-ibig', 'payment method', 'financing type',
                         'documents needed', 'requirements for', 'how to get',
                         'what documents', 'loan requirements', 'bank financing'],
            'find_ready_property': ['ready to move in', 'ready for occupancy', 
                                   'available now', 'immediate occupancy', 
                                   'move in ready', 'ready now', 'ready to occupy',
                                   'immediate move in', 'available immediately',
                                   'rfo', 'pwede na lipatan', 'handa na tirahan', 'lipat agad'],
            'process_info': ['steps for', 'how to', 'process of', 'procedure', 
                            'timeline', 'requirements', 'documents', 'steps to',
                            'how do i', 'what are the steps', 'costs for',
                            'timeline for', 'process for'],
            'find_with_feature': ['with swimming pool', 'with pool', 'with garden', 
                                 'with parking', 'with elevator', 'with security',
                                 'with wifi', 'with furniture', 'with aircon',
                                 'with feature', 'featuring', 'having',
                                 'parking', 'pool', 'garden', 'garage',  
                                 'amenity', 'amenities', 'feature', 'features',
                                 'na may', 'may parking', 'may pool',
                                 'apartments with parking', 'condos with parking' ],
            'find_near_landmark': ['near schools', 'near mall', 'near hospital', 
                                  'near port', 'near beach', 'near church',
                                  'near landmark', 'close to', 'around',
                                  'beside', 'next to', 'adjacent to'],
            'location_info': ['tell me about', 'what is', 'describe', 'about the',
                             'information about', 'living in', 'like to live',
                             'what\'s it like', 'is it good', 'lifestyle',
                             'neighborhood', 'neighbourhood', 'barangay', 'community vibe',
                             'kamusta tumira', 'anong neighborhood', 'living experience',
                             'where to live in', 'best place to live in', 'best neighborhood in',
                             'saan maganda tumira', 'magandang tirhan ba'],
            'find_property': ['find', 'search for', 'show me', 'looking for',
                             'need', 'want', 'locate', 'discover', 
                              'what apartments', 'what houses', 'what condos',  
                     'do you have', 'any properties', 'available properties'], 
            'find_property_for_need': ['for family', 'family of', 'big family',
                                      'large family', 'for couple', 'for couples',
                                      'for single', 'for workers'],
             'find_property_with_criteria': [
        'under', 'below', 'less than', 'maximum', 'up to',
        'with bedroom', 'with bath', 'with bathrooms',
        'with bedrooms', 'bedroom', 'bathroom', 'rooms',
        'price range', 'budget', 'affordable', 'cheap'
    ],
            'match_needs': ['match my', 'suitable for', 'fitting my', 'appropriate for',
                           'compatible with', 'what matches', 'recommendations for',
                           'for students', 'student housing', 'for professionals',
                           'single professional', 'for retirees', 'doctor',
                           'nurse', 'gym', 'active lifestyle'],
                'buyer_signup': [
        'sign up', 'signup', 'register', 'create account', 'become buyer', 
        'join as buyer', 'create buyer', 'registration', 'new account',
        'mag sign up', 'gumawa ng account', 'maging buyer', 'magparehistro'
    ],
    'buyer_signup_requirements': [
        'requirements', 'what info', 'what needed', 'documents', 'prepare',
        'kailangan', 'requirements sa', 'dokumento', 'ihanda', 'what do i need'
    ],
    'buyer_signup_password': [
        'password', 'strong password', 'password requirements', 'password rules',
        'malakas na password', 'requirements sa password', 'special character'
    ],
    'buyer_signup_phone': [
        'phone number', 'mobile number', '0917', '09', '+63', 'contact number',
        'format ng phone', 'phone format', 'paano maglagay ng number'
    ],
    'buyer_login': [
        'login', 'sign in', 'log in', 'access account', 'buyer dashboard',
        'log into account', 'login page', 'where to login', 'where do i login',
        'where can i log in', 'already have an account', 'existing account login',
        'open my account', 'enter my account', 'access my dashboard',
        'buyer portal login', 'member login', 'account sign in',
        'how do i login', 'how can i login', 'how do i sign in',
        'paano mag login', 'pumasok sa account', 'sign in sa buyer'
    ],
    'buyer_login_google': [
        'google login', 'google sign in', 'continue with google', 
        'google account', 'google authentication'
    ],
    'buyer_forgot_password': [
        'forgot password', 'reset password', 'can\'t remember', 'recover account',
        'nakalimutan password', 'i-reset ang password', 'change password'
    ],
    'buyer_email_verification': [
        'verification email', 'verify email', 'didn\'t receive', 'verification code',
        'verify account', 'hindi natanggap', 'verification code', 'otp'
    ],
    'buyer_verify_otp': [
        'verify code', 'enter otp', 'verification code', '6-digit code',
        'i-verify ang email', 'paano gamitin ang code', 'saan ilalagay ang code'
    ],
    'buyer_resend_otp': [
        'resend code', 'resend otp', 'send again', 'new code',
        'resend verification', 'paki-resend', 'paulit yung code'
    ],
    'buyer_login_errors': [
        'can\'t login', 'login failed', 'login error', 'invalid credentials',
        'bakit hindi makapag login', 'ayaw pumasok', 'error sa pag login'
    ],
    'buyer_logout': [
        'logout', 'sign out', 'log out', 'exit account',
        'mag logout', 'mag sign out', 'lumabas sa dashboard'
    ],
    'buyer_account_settings': [
        'account settings', 'profile settings', 'edit profile', 'update info',
        'settings page', 'pwedeng baguhin sa settings', 'profile settings options'
    ],
    'buyer_update_profile': [
        'update profile', 'edit profile', 'change details', 'change name', 
        'update email', 'change phone', 'mag edit ng profile', 'baguhin ang pangalan'
    ],
    'buyer_guest_access': [
        'guest', 'browse without login', 'guest mode', 'view without account',
        'pwede ba mag browse kahit walang account', 'guest access', 'no account',
        'browse as guest', 'can i browse without signing up', 'guest user'
    ],
    'buyer_kyc': [
        'KYC', 'verify identity', 'what is KYC', 'how does KYC work', 'KYC verification',
        'guest vs logged in', 'what can guest access', 'KYC requirements', 'identity verification',
        'ano ang KYC', 'paano mag KYC', 'bakit kailangan KYC', 'pwede ba mag message kahit walang KYC'
    ],
    'buyer_chatbot_how': [
        'how does the chatbot work', 'how does the AI work', 'what is this chatbot',
        'what is the AI assistant', 'who is the AI assistant', 'what is BahAI assistant',
        'how do I use the chatbot', 'what can the AI do', 'explain the chatbot',
        'paano gumagana ang chatbot', 'ano ang ginagawa ng AI', 'paano gamitin ang chatbot',
        'ano ang AI assistant'
    ],
    'buyer_dashboard_flow': [
        'how does the buyer dashboard work', 'what is the buyer dashboard', 'explain buyer dashboard',
        'what can I do on the dashboard', 'after login where do I go', 'what do I see when I log in',
        'successfully logged in then what', 'where am I redirected after login',
        'buyer interface', 'what pages do buyers have',
        'paano gumagana ang buyer dashboard', 'ano ang buyer dashboard', 'anong pwedeng gawin sa dashboard',
        'pagkatapos mag login saan ako mapupunta'
    ],
    'buyer_recommendations_how': [
        'how do recommendations work', 'how are recommendations fetched', 'how do I get recommendations',
        'what are AI recommendations', 'unlock recommendations', 'paano gumagana ang recommendations',
        'bakit kailangan mag login para sa recommendations'
    ],
    'buyer_messages_how': [
        'how do I message brokers', 'how do messages work', 'can I message without KYC',
        'when can I send messages', 'contact broker', 'paano mag message sa broker',
        'pwede ba mag message kahit walang KYC'
    ],
    'buyer_liked_saved_how': [
        'how do I save properties', 'what are saved properties', 'liked properties',
        'where are my saved properties', 'do I need to login to save', 'paano mag save ng property',
        'kailangan ba mag login para mag save'
    ]
        }
        
        # Load Batangas data for location training
        self.batangas_data = self.load_batangas_data()

    def load_batangas_data(self):
        """Load Batangas complete data for location-based training"""
        batangas_file = os.path.join(self.data_dir, 'shared', 'batangas_complete.json')
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
    
    # ========== THIS MUST BE AT THE SAME INDENTATION LEVEL ==========
    def fix_couples_classification(self):
        """OVERRIDE: Force the model to recognize 'properties for couples' as find_property_for_need"""
        
        print("\n" + "="*60)
        print("🔥 CRITICAL FIX: Adding COUPLES-SPECIFIC training samples")
        print("="*60)
        
        # PRIMARY PATTERN - exactly what users type
        couples_samples = [
            ("properties for couples", "find_property_for_need"),
            ("find properties for couples", "find_property_for_need"),
            ("show me properties for couples", "find_property_for_need"),
            ("looking for properties for couples", "find_property_for_need"),
            ("apartments for couples", "find_property_for_need"),
            ("houses for couples", "find_property_for_need"),
            ("condos for couples", "find_property_for_need"),
            ("homes for couples", "find_property_for_need"),
            ("properties for couple", "find_property_for_need"),
            ("bahay para sa mag asawa", "find_property_for_need"),
            ("apartment para sa mag asawa", "find_property_for_need"),
        ]
        
        # NEGATIVE examples - what should NOT be find_property_for_need
        negative_samples = [
            ("find properties", "find_property"),
            ("show me properties", "find_property"),
            ("properties available", "find_property"),
        ]
        
        texts = []
        intents = []
        
        for text, intent in couples_samples:
            processed = self.preprocess_text(text)
            texts.append(processed)
            intents.append(intent)
            print(f"  ✅ Added: '{text}' -> {intent}")
        
        for text, intent in negative_samples:
            processed = self.preprocess_text(text)
            texts.append(processed)
            intents.append(intent)
            print(f"  🔸 Negative: '{text}' -> {intent}")
        
        print(f"\n  📊 Added {len(texts)} total samples")
        print("="*60)
        
        return texts, intents

    def clean_json_file(self, filepath):
        """Fix JSON file by properly loading and saving it"""
        try:
            with open(filepath, 'r', encoding='utf-8') as f:
                content = f.read()
            
            # Remove any trailing commas before closing braces/brackets
            content = re.sub(r',\s*}', '}', content)
            content = re.sub(r',\s*]', ']', content)
            
            # Parse the JSON
            try:
                data = json.loads(content)
            except json.JSONDecodeError:
                # Try to fix by finding the problematic section
                lines = content.split('\n')
                cleaned_lines = []
                for line in lines:
                    if '//' in line:
                        line = line.split('//')[0]
                    cleaned_lines.append(line.strip())
                content = '\n'.join(cleaned_lines)
                data = json.loads(content)
            
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
        
        original_text = text.lower()
        text = str(text).lower()
        
        # FIXED: Properly indented
        tagalog_words = ['paano', 'mag', 'ang', 'mga', 'bilang', 'sa', 'ng', 'ako', 'ko', 
                         'gusto', 'maging', 'gumawa', 'account', 'buyer', 'sign', 'up',
                         'login', 'password', 'email', 'phone', 'verification']
        
        # Remove special characters but keep spaces and basic punctuation
        text = re.sub(r'[^a-z0-9\s]', ' ', text)
        
        # Remove extra spaces
        text = re.sub(r'\s+', ' ', text).strip()
        
        # If spaCy is loaded, do lemmatization
        if self.nlp:
            doc = self.nlp(text)
            tokens = []
            for token in doc:
                # Keep Tagalog words as-is
                if token.text in tagalog_words:
                    tokens.append(token.text)
                elif not token.is_stop and not token.is_punct:
                    tokens.append(token.lemma_)
            return ' '.join(tokens)
        
        return text
    
    def mark_intent_keywords(self, text, original_text):
        """Mark intent keywords in the text"""
        marked_text = text
        
        # Check each intent for keywords
        for intent, keywords in self.intent_keywords.items():
            for keyword in keywords:
                if keyword in original_text:
                    # Replace with marked version
                    marked_text = marked_text.replace(keyword, f"{keyword}_INTENT_{intent}")
        
        return marked_text

    def load_member_data(self, base_path='data'):
        """Load training data from all team members including buyer folder"""
        texts = []
        intents = []
        
        # Look for both patterns: member* AND member*_buyer
        member_files = []
        
        # Pattern 1: Standard member folders (member1, member2, member3, etc.)
        member_files.extend(glob.glob(os.path.join(base_path, 'member[0-9]', 'training_data.json')))
        member_files.extend(glob.glob(os.path.join(base_path, 'member[0-9][0-9]', 'training_data.json')))
        
        # Pattern 2: Explicitly look for member5_buyer and any other buyer folders
        member_files.extend(glob.glob(os.path.join(base_path, 'member*_buyer', 'training_data.json')))
        
        # Also look in the current directory's data folder
        if not member_files:
            member_files.extend(glob.glob(os.path.join(self.data_dir, 'member[0-9]', 'training_data.json')))
            member_files.extend(glob.glob(os.path.join(self.data_dir, 'member*_buyer', 'training_data.json')))
        
        if not member_files:
            logger.warning("❌ No member training files found!")
            # Debug: Print what folders exist
            print(f"\n🔍 Debug: Checking what folders exist in '{self.data_dir}' directory:")
            if os.path.exists(self.data_dir):
                for item in os.listdir(self.data_dir):
                    item_path = os.path.join(self.data_dir, item)
                    if os.path.isdir(item_path):
                        print(f"   Found folder: {item}")
                        # Check if training_data.json exists in this folder
                        if os.path.exists(os.path.join(item_path, 'training_data.json')):
                            print(f"      ✅ Has training_data.json")
                        else:
                            print(f"      ❌ No training_data.json")
            return texts, intents
        
        for member_file in member_files:
            member_name = os.path.basename(os.path.dirname(member_file))
            print(f"📂 Loading {member_name} data...")
            
            # Print the full path for debugging
            print(f"   Path: {member_file}")
            
            # Clean the JSON file first
            self.clean_json_file(member_file)
            
            try:
                with open(member_file, 'r', encoding='utf-8') as f:
                    data = json.load(f)
                
                samples = data.get('training_samples', [])
                print(f"   Found {len(samples)} samples in {member_name}")
                
                # Debug: Show first few intents from buyer folder
                if 'buyer' in member_name.lower() and samples:
                    print(f"   🏷️  First few buyer intents:")
                    for i, sample in enumerate(samples[:3]):
                        print(f"      {i+1}. {sample.get('intent', 'unknown')}")
                
                for sample in samples:
                    # Get intent and map to standard name
                    original_intent = sample.get('intent', '')
                    mapped_intent = self.intent_mapping.get(original_intent, original_intent)
                    
                    # Debug first few buyer intents
                    if original_intent.startswith('buyer_') and len(texts) < 10:
                        print(f"   ✅ Mapped {original_intent} -> {mapped_intent}")
                    
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
                
            except Exception as e:
                print(f"   ❌ Error loading {member_file}: {e}")
        
        # Print summary of all member files loaded
        print(f"\n📊 Total member files loaded: {len(member_files)}")
        for file in member_files:
            print(f"   • {file}")
        
        return texts, intents

    def load_member4_general_data(self):
        """Load Member 4 general intents from separate folder"""
        texts = []
        intents = []
        
        general_files = glob.glob(os.path.join(self.data_dir, 'member4_general', '*.json'))
        
        if not general_files:
            print("   ⚠️ No member4_general files found")
            return texts, intents
        
        for general_file in general_files:
            file_name = os.path.basename(general_file)
            print(f"   📄 Loading {file_name}...")
            
            try:
                with open(general_file, 'r', encoding='utf-8') as f:
                    data = json.load(f)
                
                samples = data.get('training_samples', [])
                
                for sample in samples:
                    # Main query
                    query = sample.get('query', '').strip()
                    if query:
                        texts.append(self.preprocess_text(query))
                        intents.append(sample.get('intent', 'greeting'))
                    
                    # Variations
                    variations = sample.get('variations', [])
                    for variation in variations:
                        if isinstance(variation, str) and variation.strip():
                            texts.append(self.preprocess_text(variation))
                            intents.append(sample.get('intent', 'greeting'))
                
                print(f"      ✅ Added {len(samples)} base samples from {file_name}")
                
            except Exception as e:
                print(f"      ❌ Error loading {file_name}: {e}")
        
        # Print summary
        if texts:
            from collections import Counter
            intent_counts = Counter(intents)
            print(f"      📊 Intent breakdown:")
            for intent, count in intent_counts.most_common():
                print(f"         • {intent}: {count} samples")
        
        return texts, intents

    def add_corrective_training_samples(self):
        """Add specific training samples to fix common misclassifications"""
        print("\n🔧 Adding corrective training samples...")
        
        corrective_samples = [
            # Clear greeting samples (short, simple)
            ("hi", "greeting"),
            ("hello", "greeting"),
            ("hey", "greeting"),
            ("hi there", "greeting"),
            ("hello there", "greeting"),
            ("good morning", "greeting"),
            ("good afternoon", "greeting"),
            ("good evening", "greeting"),
            ("howdy", "greeting"),
            ("yo", "greeting"),
            ("sup", "greeting"),
            ("hello bot", "greeting"),
            ("hi ai", "greeting"),
        
            # Clear about_system samples (asking for information about the system)
            ("what are you", "about_system"),
            ("who are you", "about_system"),
            ("what is this system", "about_system"),
            ("what is this chatbot", "about_system"),
            ("what is bahai", "about_system"),
            ("tell me about yourself", "about_system"),
            ("introduce yourself", "about_system"),
            ("what do you do", "about_system"),
            ("what can you do", "about_system"),
            ("what is your purpose", "about_system"),
            ("system overview", "about_system"),
            ("what services do you offer", "about_system"),
            ("give me an introduction", "about_system"),
            ("explain what you do", "about_system"),
            ("about the system", "about_system"),
            ("what is this about", "about_system"),
            ("tell me more about bah.ai", "about_system"),
            ("what is the system about", "about_system"),
            ("what services do you offer", "about_system"),
            ("give me an introduction", "about_system"),
            ("explain what you do", "about_system"),
            ("what is this about", "about_system"),
            ("tell me more about bahAI", "about_system"),
            ("can you introduce yourself", "about_system"),
            ("describe yourself", "about_system"),
        
            # Negative examples - what should NOT be about_system
            ("hi what is this", "greeting"),  
            ("hello what are you", "greeting"), 
        
            # Let's add these as about_system since they're asking about the system
            ("hi what are you", "about_system"),
            ("hello what is this", "about_system"),
            ("hey what do you do", "about_system"),
            ("what can this system do", "about_system"),
            ("what does bahai do", "about_system"),
            ("what features does this system have", "about_system"),

            # Clear help intent (usage guidance, not system identity)
            ("help me use this", "help"),
            ("how to use this chatbot", "help"),
            ("guide me on using the app", "help"),
            ("assist me with searching", "help"),
            ("i need help using this", "help"),

            # Buyer signup vs login boundary fixes
            ("how do i sign up as a buyer", "buyer_signup"),
            ("i need to create a buyer account", "buyer_signup"),
            ("register new buyer account", "buyer_signup"),
            ("where do i sign up", "buyer_signup"),
            ("how do i register", "buyer_signup"),
            ("how do i log in to my buyer account", "buyer_login"),
            ("i already have account how to sign in", "buyer_login"),
            ("where do i login", "buyer_login"),
            ("where can i login", "buyer_login"),
            ("where can i log in", "buyer_login"),
            ("i already have an account where do i log in", "buyer_login"),
            ("i have an account where can i sign in", "buyer_login"),
            ("access buyer dashboard login", "buyer_login"),
            ("log in existing account", "buyer_login"),

            # Casual goodbye variants that were colliding
            ("nothing else", "goodbye"),
            ("that is all for now", "goodbye"),
            ("okay im done", "goodbye"),
            ("i am done for now", "goodbye"),
            ("talk later", "goodbye"),

            
    
            # Clear examples of find_property_with_criteria
            ("houses under 30 million with 4 bedrooms", "find_property_with_criteria"),
            ("show me properties below 20M with 3 bedrooms", "find_property_with_criteria"),
            ("find condos under 10M with 2 baths", "find_property_with_criteria"),
            
            # Clear examples of find_property (no price/bedroom criteria)
            ("find houses in nasugbu", "find_property"),
            ("show me apartments in batangas city", "find_property"),
            ("look for condos in lipa", "find_property"),
            
            # Boundary cases
            ("houses with 4 bedrooms", "find_property_with_criteria"),  # has bedroom count
            ("houses under 30M", "find_property_with_criteria"),  # has price
            ("houses in batangas", "find_property"),  # only location
            
            # General property searches WITHOUT location
            ("find apartments", "find_property"),
            ("show me houses", "find_property"),
            ("look for condos", "find_property"),
            ("search for properties", "find_property"),
            ("i need a house", "find_property"),
            ("show me available properties", "find_property"),
            ("find beachfront properties", "find_property"),
            ("show me commercial spaces", "find_property"),
            ("looking for townhouses", "find_property"),
            ("need a studio", "find_property"),
            
            # General property type questions
            ("what apartments do you have", "find_property"),
            ("what houses are available", "find_property"),
            ("show me all condos", "find_property"),
            ("what properties do you offer", "find_property"),
            ("do you have any apartments", "find_property"),
            ("any houses for sale", "find_property"),
            ("any condos for rent", "find_property"),
            
            # Financing intent fixes
            ("properties that accept bank financing", "financing"),
            ("show me properties that accept bank financing", "financing"),
            ("houses that accept bank loans", "financing"),
            ("properties with bank financing options", "financing"),
            ("real estate that accepts pag-ibig", "financing"),
            ("condos with in-house financing", "financing"),
            ("how to get bank financing for a house", "financing"),
            ("what documents for pag-ibig loan", "financing"),
            ("bank financing requirements", "financing"),
            ("properties accepting cash payment", "financing"),
            
            # Ready to move property fixes
            ("find ready to move in properties for students in batangas city", "find_ready_property"),
            ("ready to occupy apartments for students", "find_ready_property"),
            ("available now properties for family", "find_ready_property"),
            ("immediate occupancy houses", "find_ready_property"),
            ("move in ready condos for professionals", "find_ready_property"),
            ("properties ready now for couples", "find_ready_property"),
            ("ready for occupancy commercial spaces", "find_ready_property"),
            ("available immediately near schools", "find_ready_property"),
            ("ready to move in with furniture", "find_ready_property"),
            ("properties ready for move in", "find_ready_property"),
            
            # Process info fixes
            ("steps for buying a condo", "process_info"),
            ("how to buy a house step by step", "process_info"),
            ("process of purchasing property", "process_info"),
            ("timeline for renting an apartment", "process_info"),
            ("requirements for commercial space lease", "process_info"),
            ("documents needed for house purchase", "process_info"),
            ("procedure for getting a mortgage", "process_info"),
            ("what are the steps to invest in real estate", "process_info"),
            ("how does the property buying process work", "process_info"),
            ("steps costs timeline for townhouse", "process_info"),
            
            # With feature fixes
            ("properties with swimming pool", "find_with_feature"),
            ("houses with garden", "find_with_feature"),
            ("apartments with parking space", "find_with_feature"),
            ("condos with security", "find_with_feature"),
            ("properties featuring pool", "find_with_feature"),
            ("homes with private pool", "find_with_feature"),
            ("units with elevator", "find_with_feature"),
            ("properties with wifi included", "find_with_feature"),
            ("houses with home office", "find_with_feature"),
            ("apartments with furniture", "find_with_feature"),
            
            # Near landmark fixes
            ("properties near schools", "find_near_landmark"),
            ("houses close to malls", "find_near_landmark"),
            ("apartments near hospitals", "find_near_landmark"),
            ("condos near batangas port", "find_near_landmark"),
            ("properties around universities", "find_near_landmark"),
            ("real estate near beaches", "find_near_landmark"),
            ("housing near industrial parks", "find_near_landmark"),
            ("properties adjacent to churches", "find_near_landmark"),
            ("homes near business districts", "find_near_landmark"),
            ("apartments near transport hubs", "find_near_landmark"),
            
            # Location info fixes
            ("tell me about batangas city", "location_info"),
            ("what is lipa city like", "location_info"),
            ("describe tanauan city", "location_info"),
            ("information about nasugbu", "location_info"),
            ("living in san juan batangas", "location_info"),
            ("about calatagan", "location_info"),
            ("what's it like to live in taal", "location_info"),
            ("describe mabini batangas", "location_info"),
            ("is sto tomas a good place to live", "location_info"),
            ("tell me about the lifestyle in malvar", "location_info"),
        ]
        
        texts = []
        intents = []
        
        for text, intent in corrective_samples:
            texts.append(self.preprocess_text(text))
            intents.append(intent)
        
        print(f"   ✅ Added {len(texts)} corrective samples")
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
                template = q_data.get('template', '')
                if template:
                    texts.append(self.preprocess_text(template))
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
            }
            
            # Use phrases section
            phrases = data.get('phrases', {})
            for category, phrase_list in phrases.items():
                if isinstance(phrase_list, list):
                    intent = phrase_intent_map.get(category, 'find_property')
                    for phrase in phrase_list[:5]:
                        if isinstance(phrase, str) and phrase.strip():
                            texts.append(self.preprocess_text(phrase))
                            intents.append(intent)
            
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
        
        # Generate location-specific queries
        for location_name, location_data in locations.items():
            if isinstance(location_name, str):
                loc_name = location_name.lower()
                
                # Location info queries
                texts.append(f"tell me about {loc_name}")
                intents.append('location_info')
                
                texts.append(f"what is {loc_name} like")
                intents.append('location_info')
                
                # Find property queries
                texts.append(f"find properties in {loc_name}")
                intents.append('find_property')
                
                texts.append(f"show me houses in {loc_name}")
                intents.append('find_property')
        
        print(f"   ✅ Generated {len(texts)} samples from Batangas data")
        return texts, intents

    def load_additional_training(self, filepath=None):
        """Load additional training data"""
        texts = []
        intents = []
        if filepath is None:
            filepath = os.path.join(self.data_dir, 'additional_training.json')
        
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
        
        # Limit to avoid too many samples
        limit = min(50, len(texts))
        
        for i in range(limit):
            text = texts[i]
            intent = intents[i]
            
            # Add question variation
            if not text.endswith('?'):
                new_texts.append(text + '?')
                new_intents.append(intent)
            
            # Add "please" variation
            new_texts.append('please ' + text)
            new_intents.append(intent)
            
            # Add "can you" variation
            new_texts.append('can you ' + text)
            new_intents.append(intent)
            
            # Add "i need" variation
            new_texts.append('i need ' + text)
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
        print(f"   ✅ Loaded {len(member_texts)} samples")
        print(f"   Total so far: {len(all_texts)} samples")

        print("\n📁 Source 1C: Member 4 - General Intents")
        member4_texts, member4_intents = self.load_member4_general_data()
        all_texts.extend(member4_texts)
        all_intents.extend(member4_intents)
        print(f"   ✅ Loaded {len(member4_texts)} general intent samples")
        print(f"   Total so far: {len(all_texts)} samples")
        
        # 2. Add corrective training samples (FIX for your issues)
        print("\n📁 Source 2: Corrective Training Samples")
        corrective_texts, corrective_intents = self.add_corrective_training_samples()
        all_texts.extend(corrective_texts)
        all_intents.extend(corrective_intents)
        print(f"   ✅ Added {len(corrective_texts)} corrective samples")
        print(f"   Total so far: {len(all_texts)} samples")
        
        # 3. Load shared questions
        print("\n📁 Source 3: Shared Question Templates")
        shared_path = os.path.join(base_path, 'shared')
        question_texts, question_intents = self.load_shared_questions(shared_path)
        all_texts.extend(question_texts)
        all_intents.extend(question_intents)
        print(f"   ✅ Generated {len(question_texts)} samples")
        print(f"   Total so far: {len(all_texts)} samples")
        
        # 4. Load synonyms as training data
        print("\n📁 Source 4: Synonyms and Phrases")
        synonym_texts, synonym_intents = self.load_synonyms_as_training(shared_path)
        all_texts.extend(synonym_texts)
        all_intents.extend(synonym_intents)
        print(f"   ✅ Generated {len(synonym_texts)} samples")
        print(f"   Total so far: {len(all_texts)} samples")
        
        # 5. Load Batangas data for training
        print("\n📁 Source 5: Batangas Location Data")
        batangas_texts, batangas_intents = self.load_batangas_training()
        all_texts.extend(batangas_texts)
        all_intents.extend(batangas_intents)
        print(f"   ✅ Generated {len(batangas_texts)} samples")
        print(f"   Total so far: {len(all_texts)} samples")
        
        # 6. Load additional training data
        print("\n📁 Source 6: Additional Training Data")
        additional_texts, additional_intents = self.load_additional_training()
        all_texts.extend(additional_texts)
        all_intents.extend(additional_intents)
        if additional_texts:
            print(f"   ✅ Loaded {len(additional_texts)} samples")
        print(f"   Total so far: {len(all_texts)} samples")
        
        # 7. Generate additional variations
        print("\n📁 Source 7: Generated Variations")
        generated_texts, generated_intents = self.generate_additional_variations(all_texts, all_intents)
        all_texts.extend(generated_texts)
        all_intents.extend(generated_intents)
        print(f"   ✅ Generated {len(generated_texts)} variations")
        
        # ========== ADD THIS SECTION RIGHT HERE ==========
        print("\n" + "="*60)
        print("🚨 APPLYING CRITICAL COUPLES CLASSIFICATION FIX")
        print("="*60)
        
        # Filter out mislabeled couples samples
        filtered_texts = []
        filtered_intents = []
        
        for i, text in enumerate(all_texts):
            intent = all_intents[i]
            query = text.lower() if isinstance(text, str) else ""
            
            # Remove any "properties for couples" that are mislabeled
            if "for couples" in query or "for couple" in query:
                if intent != "find_property_for_need":
                    print(f"  ⚠️ Removing mislabeled: '{text[:50]}...' -> {intent}")
                    continue
            
            filtered_texts.append(text)
            filtered_intents.append(intent)
        
        # Add our CORRECT couples samples
        couples_texts, couples_intents = self.fix_couples_classification()
        filtered_texts.extend(couples_texts)
        filtered_intents.extend(couples_intents)
        
        # DUPLICATE the couples samples for extra weight
        for _ in range(3):
            filtered_texts.extend(couples_texts)
            filtered_intents.extend(couples_intents)
        
        print(f"\n  ✅ After fix: {len(filtered_texts)} total samples")
        print(f"  ✅ 'properties for couples' samples: {couples_texts.count('properties for couples')} copies")
        print("="*60)
        
        all_texts = filtered_texts
        all_intents = filtered_intents

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
        
        # Find target count (average of top 3 classes)
        sorted_counts = sorted(intent_counts.values(), reverse=True)
        target_count = int(np.mean(sorted_counts[:3]))
        
        for intent in intent_counts:
            # Get all samples for this intent
            intent_samples = [(text, intent_label) 
                             for text, intent_label in zip(training_texts, training_intents) 
                             if intent_label == intent]
            
            # Add original samples
            for text, intent_label in intent_samples:
                balanced_texts.append(text)
                balanced_intents.append(intent_label)
            
            # If this class has fewer samples, oversample it
            if len(intent_samples) < target_count:
                needed = target_count - len(intent_samples)
                for _ in range(needed):
                    text, intent_label = random.choice(intent_samples)
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
        
        # Show classification report for problematic intents
        problem_intents = ['financing', 'find_ready_property', 'process_info']
        problem_mask = [y in problem_intents for y in y_val]
        
        if any(problem_mask):
            X_val_problem = [X_val[i] for i in range(len(X_val)) if problem_mask[i]]
            y_val_problem = [y_val[i] for i in range(len(y_val)) if problem_mask[i]]
            
            if X_val_problem:
                val_problem_predictions = self.pipeline.predict(X_val_problem)
                print(f"\n🔍 Classification report for problem intents:")
                print(classification_report(y_val_problem, val_problem_predictions))
        
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
            for i, case in enumerate(misclassified[:10]):
                display_text = case['text'][:60] + '...' if len(case['text']) > 60 else case['text']
                print(f"   {i+1}. '{display_text}'")
                print(f"       → True: {case['true']}, Pred: {case['pred']}")
        
        # FIXED: Buyer intent monitoring - properly indented
        buyer_intents = [intent for intent in self.intent_mapping.values() 
                        if intent.startswith('buyer_')]
        print(f"\n📊 Monitoring {len(buyer_intents)} buyer intents: {buyer_intents}")
        
        buyer_mask = [y in buyer_intents for y in y_val]
        if any(buyer_mask):
            X_val_buyer = [X_val[i] for i in range(len(X_val)) if buyer_mask[i]]
            y_val_buyer = [y_val[i] for i in range(len(y_val)) if buyer_mask[i]]
            
            if X_val_buyer:
                val_buyer_predictions = self.pipeline.predict(X_val_buyer)
                print(f"\n🔍 Classification report for BUYER INTENTS:")
                print(classification_report(y_val_buyer, val_buyer_predictions))
        
        return True  # <-- This return was missing indentation

    def save_model(self):
        """Save trained model to multiple locations"""
        # Get project root directory
        project_root = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
        current_dir = os.path.dirname(os.path.abspath(__file__))
        
        model_data = {
            'vectorizer': self.pipeline.named_steps['tfidf'],
            'classifier': self.pipeline.named_steps['classifier'],
            'classes': self.pipeline.classes_.tolist(),
            'version': '3.4',
            'training_date': datetime.now().isoformat(),
            'feature_count': len(self.pipeline.named_steps['tfidf'].get_feature_names_out()),
            'intent_mapping': self.intent_mapping,
            'template_intent_map': self.template_intent_map,
            'intent_keywords': self.intent_keywords,
            'batangas_data_loaded': bool(self.batangas_data)
        }
        
        # Define ALL paths
        paths_to_save = [
            # 1. Training folder (original)
            os.path.join(current_dir, 'models', 'nlu_model.pkl'),
            # 2. Backend folder (for local development)
            os.path.join(project_root, 'backend', 'models', 'nlu_model.pkl'),
            # 3. Root models folder
            os.path.join(project_root, 'models', 'nlu_model.pkl'),
            # 4. For Render deployment - this is where it's looking!
            os.path.join(project_root, 'training', 'models', 'nlu_model.pkl'),
        ]
        
        saved_paths = []
        for path in paths_to_save:
            try:
                os.makedirs(os.path.dirname(path), exist_ok=True)
                with open(path, 'wb') as f:
                    pickle.dump(model_data, f)
                saved_paths.append(path)
                print(f"✅ Saved to: {path}")
            except Exception as e:
                print(f"❌ Failed to save to {path}: {e}")
        
        print(f"\n📊 Model info:")
        print(f"   • Version: {model_data['version']}")
        print(f"   • Classes: {len(model_data['classes'])} intents")
        print(f"   • Date: {model_data['training_date']}")
        print(f"   • Features: {model_data['feature_count']}")
        
        # Return the most important path (backend folder)
        return os.path.join(project_root, 'backend', 'models', 'nlu_model.pkl')
    
def test_predictions(trainer, test_queries):
    """Test model predictions with the specific problematic queries"""
    print("\n" + "="*60)
    print("🧪 TESTING PROBLEMATIC QUERIES")
    print("="*60)
    
    # Test the specific queries that were misclassified
    specific_queries = [
        "Properties that accept bank financing",
        "Find ready to move in properties for students in Batangas City",
        "Steps for buying a condo",
        "properties with swimming pool",
        "properties near schools",
        "how to get mortgage",
        "tell me about lipa city",
        "available now apartments",
        "houses for big family",
        "condos near malls",
        # FIXED: Added missing comma and proper formatting
        "How do I sign up as a buyer",
        "paano mag sign up bilang buyer",
        "What are the password requirements",
        "I forgot my password",
        "How do I log in to buyer dashboard",
        "I haven't received the verification email",
        "Can you resend the verification code",
    ]
    
    for query in specific_queries:
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
                        if intent_prob > 10:  # Only show significant alternatives
                            print(f"     • {intent_name}: {intent_prob:.1f}%")
            print()
        except Exception as e:
            print(f"❌ Error predicting '{query}': {e}")

def create_additional_training_file(data_dir):
    """Create/update additional training data file"""
    additional_data = {
        "additional_samples": [
            # Basic intents
            {"text": "hi", "intent": "greeting"},
            {"text": "hello", "intent": "greeting"},
            {"text": "hey", "intent": "greeting"},
            {"text": "hello there", "intent": "greeting"},
            {"text": "good morning", "intent": "greeting"},
            {"text": "good afternoon", "intent": "greeting"},
            {"text": "good evening", "intent": "greeting"},
            {"text": "greetings", "intent": "greeting"},
            
            {"text": "thank you", "intent": "thanks"},
            {"text": "thanks", "intent": "thanks"},
            {"text": "thank you very much", "intent": "thanks"},
            {"text": "thanks a lot", "intent": "thanks"},
            {"text": "appreciate it", "intent": "thanks"},
            {"text": "thank you for your help", "intent": "thanks"},
            
            {"text": "help", "intent": "help"},
            {"text": "can you help me", "intent": "help"},
            {"text": "how can you help", "intent": "help"},
            {"text": "assist me", "intent": "help"},
            {"text": "need help", "intent": "help"},
            {"text": "support me", "intent": "help"},
            {"text": "guide me", "intent": "help"},
            {"text": "help me use this", "intent": "help"},
            {"text": "how to use this chatbot", "intent": "help"},
            
            {"text": "what are you", "intent": "about_system"},
            {"text": "who are you", "intent": "about_system"},
            {"text": "what is this", "intent": "about_system"},
            {"text": "what is this system", "intent": "about_system"},
            {"text": "what do you do", "intent": "about_system"},
            {"text": "what can you do", "intent": "about_system"},
            {"text": "what can you help with", "intent": "about_system"},
            {"text": "tell me about yourself", "intent": "about_system"},
            {"text": "what is this system about", "intent": "about_system"},
            {"text": "what is bahAI", "intent": "about_system"},
            {"text": "what is this chatbot", "intent": "about_system"},
            {"text": "what is this service", "intent": "about_system"},
            {"text": "explain what you do", "intent": "about_system"},

                        # ========== CRITICAL BUYER INTENT FIXES ==========
            
            # Clear "sign up" queries (should be buyer_signup, NOT buyer_login)
            {"text": "How do I sign up as a buyer", "intent": "buyer_signup"},
            {"text": "How do I sign up", "intent": "buyer_signup"},
            {"text": "I want to sign up", "intent": "buyer_signup"},
            {"text": "Create a buyer account", "intent": "buyer_signup"},
            {"text": "Register as a buyer", "intent": "buyer_signup"},
            {"text": "Become a buyer", "intent": "buyer_signup"},
            {"text": "Sign up for buyer account", "intent": "buyer_signup"},
            {"text": "New buyer registration", "intent": "buyer_signup"},
            {"text": "How to create buyer account", "intent": "buyer_signup"},
            {"text": "Steps to sign up as buyer", "intent": "buyer_signup"},
            {"text": "paano mag sign up", "intent": "buyer_signup"},
            {"text": "paano maging buyer", "intent": "buyer_signup"},
            
            # Clear "login" queries (should be buyer_login)
            {"text": "how to login", "intent": "buyer_login"},
            {"text": "How do I log in", "intent": "buyer_login"},
            {"text": "Login to my account", "intent": "buyer_login"},
            {"text": "Sign in as buyer", "intent": "buyer_login"},
            {"text": "Access my buyer account", "intent": "buyer_login"},
            {"text": "Log into buyer dashboard", "intent": "buyer_login"},
            {"text": "How to sign in", "intent": "buyer_login"},
            {"text": "How do I login to existing account", "intent": "buyer_login"},
            {"text": "I already have account where to login", "intent": "buyer_login"},
            {"text": "I already have an account where do I log in", "intent": "buyer_login"},
            {"text": "where can i login", "intent": "buyer_login"},
            {"text": "where can i log in", "intent": "buyer_login"},
            {"text": "open login page", "intent": "buyer_login"},
            {"text": "buyer portal login", "intent": "buyer_login"},
            {"text": "log me in to buyer dashboard", "intent": "buyer_login"},
            {"text": "how to access my buyer account", "intent": "buyer_login"},
            {"text": "i have account i need to sign in", "intent": "buyer_login"},
            {"text": "existing account sign in", "intent": "buyer_login"},
            {"text": "Buyer login help", "intent": "buyer_login"},
            {"text": "Can't log in", "intent": "buyer_login_errors"},  # Note: different intent
            {"text": "Login problems", "intent": "buyer_login_errors"},  # Note: different intent
            {"text": "paano mag login", "intent": "buyer_login"},
            
            # Clear "forgot password" queries
            {"text": "I forgot my password", "intent": "buyer_forgot_password"},
            {"text": "Reset my password", "intent": "buyer_forgot_password"},
            {"text": "Change password", "intent": "buyer_forgot_password"},
            {"text": "Forgot password help", "intent": "buyer_forgot_password"},
            {"text": "nakalimutan ko password", "intent": "buyer_forgot_password"},
            
            # Email verification samples
            {"text": "verify my email", "intent": "buyer_email_verification"},
            {"text": "resend verification code", "intent": "buyer_resend_otp"},
            {"text": "where to enter OTP", "intent": "buyer_verify_otp"},
            {"text": "didn't get verification email", "intent": "buyer_email_verification"},
            
            # Account settings samples
            {"text": "update my profile", "intent": "buyer_update_profile"},
            {"text": "change my name", "intent": "buyer_update_profile"},
            {"text": "change my email", "intent": "buyer_update_profile"},
            {"text": "account settings", "intent": "buyer_account_settings"},
            {"text": "edit profile", "intent": "buyer_update_profile"},
            
            # Logout
            {"text": "how to logout", "intent": "buyer_logout"},
            {"text": "sign out", "intent": "buyer_logout"},
            {"text": "log out of dashboard", "intent": "buyer_logout"},
            
            {"text": "bye", "intent": "goodbye"},
            {"text": "goodbye", "intent": "goodbye"},
            {"text": "see you", "intent": "goodbye"},
            {"text": "farewell", "intent": "goodbye"},
            {"text": "bye bye", "intent": "goodbye"},
            {"text": "talk to you later", "intent": "goodbye"},
            {"text": "see you later", "intent": "goodbye"},
            {"text": "nothing else", "intent": "goodbye"},
            {"text": "that is all for now", "intent": "goodbye"},
            {"text": "i am done for now", "intent": "goodbye"},
                        # Force "find [property] in [location]" to be find_property
            {"text": "find apartments in batangas city", "intent": "find_property"},
            {"text": "find apartment in batangas city", "intent": "find_property"},
            {"text": "find apartments in batangas", "intent": "find_property"},
            {"text": "search apartments in batangas city", "intent": "find_property"},
            {"text": "look for apartments in batangas city", "intent": "find_property"},
            {"text": "show me apartments in batangas city", "intent": "find_property"},
            
            # Make "tell me about" clearly location_info
            {"text": "tell me about batangas city apartments", "intent": "location_info"},
            {"text": "information about apartments in batangas", "intent": "location_info"},
            {"text": "what is batangas city like for apartments", "intent": "location_info"},
            
            # Clear distinction between the two patterns:
            # Pattern 1: "find X in Y" = find_property
            {"text": "find house in lipa", "intent": "find_property"},
            {"text": "search house in lipa city", "intent": "find_property"},
            {"text": "look for house in lipa", "intent": "find_property"},
            {"text": "show me houses in lipa city", "intent": "find_property"},
            
            # Pattern 2: "tell me about Y" = location_info
            {"text": "tell me about lipa city houses", "intent": "location_info"},
            {"text": "what is lipa city like for houses", "intent": "location_info"},
            {"text": "information about houses in lipa", "intent": "location_info"},
            
            # Negative examples - what should NOT be location_info
            {"text": "find apartments in the city", "intent": "find_property"},
            {"text": "search for properties in that city", "intent": "find_property"},
            {"text": "looking for houses in the city", "intent": "find_property"},
            
            # Additional problematic patterns from your logs
            {"text": "search property nasugbu", "intent": "find_property"},
            {"text": "condo living in tanauan", "intent": "find_property"},
            
             # General property searches (no location)
            {"text": "find apartments", "intent": "find_property"},
            {"text": "show me houses", "intent": "find_property"},
            {"text": "look for condos", "intent": "find_property"},
            {"text": "search for properties", "intent": "find_property"},
            {"text": "i need a house", "intent": "find_property"},
            {"text": "show me available properties", "intent": "find_property"},
            {"text": "find beachfront properties", "intent": "find_property"},
            {"text": "what apartments do you have", "intent": "find_property"},
            {"text": "what houses are available", "intent": "find_property"},
            {"text": "show me all condos", "intent": "find_property"},
            {"text": "do you have any apartments", "intent": "find_property"},
            {"text": "any houses for sale", "intent": "find_property"},
            {"text": "any condos for rent", "intent": "find_property"},
            {"text": "properties for rent", "intent": "find_property"},
            {"text": "properties for sale", "intent": "find_property"},
            
            # Force "find X in Y" to be find_property (not location_info)
             {"text": "show me house in nasugbu", "intent": "find_property"},
            {"text": "show me houses in nasugbu", "intent": "find_property"},
            {"text": "show me properties in nasugbu", "intent": "find_property"},
            {"text": "show me apartments in batangas city", "intent": "find_property"},
            {"text": "show me condos in lipa city", "intent": "find_property"},
            {"text": "show me beachfront properties in nasugbu", "intent": "find_property"},
            
            # Make "show me" more distinct from location_info
            {"text": "show me what's available in nasugbu", "intent": "find_property"},
            {"text": "show me options in nasugbu", "intent": "find_property"},
            {"text": "show me listings in nasugbu", "intent": "find_property"},
            {"text": "find apartments in batangas city", "intent": "find_property"},
            {"text": "find house in nasugbu", "intent": "find_property"},
            {"text": "find condos in lipa city", "intent": "find_property"},
            {"text": "find townhouses in sto. tomas", "intent": "find_property"},
            {"text": "find commercial spaces in batangas city", "intent": "find_property"},
            {"text": "find beachfront properties in nasugbu", "intent": "find_property"},
            {"text": "find resort properties in nasugbu", "intent": "find_property"},
            {"text": "find agricultural land in nasugbu", "intent": "find_property"},
            {"text": "find apartments in nasugbu", "intent": "find_property"},
            
            # More variations with "find" keyword
            {"text": "look for apartments in batangas city", "intent": "find_property"},
            {"text": "search for apartments in batangas", "intent": "find_property"},
            {"text": "i need apartments in batangas city", "intent": "find_property"},
            {"text": "show me houses in batangas city", "intent": "find_property"},
            {"text": "show me condos in tanauan city", "intent": "find_property"},
            {"text": "i'm looking for a house in lipa", "intent": "find_property"},
            {"text": "can you find apartments in batangas city", "intent": "find_property"},
            {"text": "please locate apartments in batangas", "intent": "find_property"},
            
            # Location info samples should NOT have "find" keyword
            {"text": "tell me about batangas city", "intent": "location_info"},
            {"text": "what is batangas city like", "intent": "location_info"},
            {"text": "describe batangas city", "intent": "location_info"},
            {"text": "living in batangas city", "intent": "location_info"},
            {"text": "about batangas city", "intent": "location_info"},
            {"text": "information about batangas city", "intent": "location_info"},
            {"text": "what's it like in batangas city", "intent": "location_info"},
            {"text": "batangas city lifestyle", "intent": "location_info"},
            {"text": "how is life in batangas city", "intent": "location_info"},
            
            # ============================================
            # ORIGINAL SAMPLES (with improvements)
            # ============================================
            
            # Financing samples - with more variations
            {"text": "properties that accept bank financing", "intent": "financing"},
            {"text": "houses that accept bank loans", "intent": "financing"},
            {"text": "how to get bank financing", "intent": "financing"},
            {"text": "bank financing requirements", "intent": "financing"},
            {"text": "pag-ibig financing requirements", "intent": "financing"},
            {"text": "properties with in-house financing", "intent": "financing"},
            {"text": "properties that accept cash payment", "intent": "financing"},
            {"text": "properties that accept installment payment", "intent": "financing"},
            {"text": "what documents are needed for bank financing", "intent": "financing"},
            
            # Ready property samples - more specific
            {"text": "ready to move in properties", "intent": "find_ready_property"},
            {"text": "available now properties", "intent": "find_ready_property"},
            {"text": "ready to move in properties in batangas", "intent": "find_ready_property"},
            {"text": "mga ready to move in na property", "intent": "find_ready_property"},
            {"text": "pwede na lipatan na properties", "intent": "find_ready_property"},
            {"text": "immediate occupancy houses", "intent": "find_ready_property"},
            {"text": "move in ready condos", "intent": "find_ready_property"},
            {"text": "ready for occupancy apartments", "intent": "find_ready_property"},
            {"text": "ready to occupy units", "intent": "find_ready_property"},
            {"text": "properties available immediately", "intent": "find_ready_property"},
            {"text": "find ready to move in properties", "intent": "find_ready_property"},
            
            # Process info samples
            {"text": "steps for buying", "intent": "process_info"},
            {"text": "how to buy a property", "intent": "process_info"},
            {"text": "property purchase process", "intent": "process_info"},
            {"text": "timeline for buying a house", "intent": "process_info"},
            {"text": "requirements for property purchase", "intent": "process_info"},
            {"text": "steps for buying a condo", "intent": "process_info"},
            {"text": "how to get a mortgage", "intent": "process_info"},
            {"text": "process for renting", "intent": "process_info"},
            
            # With feature samples
            {"text": "properties with swimming pool", "intent": "find_with_feature"},
            {"text": "houses with garden", "intent": "find_with_feature"},
            {"text": "show me properties with amenities", "intent": "find_with_feature"},
            {"text": "find properties with features", "intent": "find_with_feature"},
            {"text": "mga property na may parking", "intent": "find_with_feature"},
            {"text": "apartments with parking", "intent": "find_with_feature"},
            {"text": "condos with security", "intent": "find_with_feature"},
            {"text": "properties with wifi", "intent": "find_with_feature"},
            {"text": "find properties with swimming pool", "intent": "find_with_feature"},
            {"text": "show me houses with garden", "intent": "find_with_feature"},
            {"text": "look for apartments with parking", "intent": "find_with_feature"},
            
            # Near landmark samples
            {"text": "properties near schools", "intent": "find_near_landmark"},
            {"text": "houses near malls", "intent": "find_near_landmark"},
            {"text": "apartments near hospitals", "intent": "find_near_landmark"},
            {"text": "condos near beaches", "intent": "find_near_landmark"},
            {"text": "properties near churches", "intent": "find_near_landmark"},
            {"text": "find properties near schools", "intent": "find_near_landmark"},
            {"text": "show me houses near malls", "intent": "find_near_landmark"},
            {"text": "look for apartments near hospitals", "intent": "find_near_landmark"},
            
            # More location info samples
            {"text": "tell me about lipa city", "intent": "location_info"},
            {"text": "tell me about neighborhoods in lipa city", "intent": "location_info"},
            {"text": "what neighborhood is good in batangas city", "intent": "location_info"},
            {"text": "kamusta tumira sa batangas city neighborhood", "intent": "location_info"},
            {"text": "what is lipa city like", "intent": "location_info"},
            {"text": "describe tanauan city", "intent": "location_info"},
            {"text": "information about nasugbu", "intent": "location_info"},
            {"text": "living in san juan", "intent": "location_info"},
            {"text": "tell me about calatagan", "intent": "location_info"},
            {"text": "what's it like to live in taal", "intent": "location_info"},
            {"text": "describe mabini batangas", "intent": "location_info"},
            {"text": "information about sto. tomas city", "intent": "location_info"},
            {"text": "saan maganda tumira sa batangas city", "intent": "location_info"},
            {"text": "where to live in lipa city", "intent": "location_info"},
            {"text": "best place to live in sto tomas", "intent": "location_info"},
            
            # ============================================
            # ADDITIONAL CONTEXTUAL SAMPLES
            # ============================================
            
            # Clear distinction samples
            {"text": "i want to find a house in batangas", "intent": "find_property"},
            {"text": "i want to know about batangas city", "intent": "location_info"},
            {"text": "search properties in nasugbu", "intent": "find_property"},
            {"text": "give me information about nasugbu", "intent": "location_info"},
            {"text": "show me available properties in lipa", "intent": "find_property"},
            {"text": "tell me about living in lipa", "intent": "location_info"},
            
            # Property for need samples
            {"text": "properties for family needs in lipa", "intent": "find_property_for_need"},
            {"text": "houses for big family", "intent": "find_property_for_need"},
            {"text": "apartments for students in batangas city", "intent": "match_needs"},
            {"text": "condos for professionals", "intent": "match_needs"},
            {"text": "properties for retirees", "intent": "match_needs"},
            
            # Match needs samples
            {"text": "match properties to my budget", "intent": "match_needs"},
            {"text": "recommend properties for me", "intent": "match_needs"},
            {"text": "find suitable properties", "intent": "match_needs"},
            {"text": "what properties match my needs", "intent": "match_needs"},
            {"text": "properties for students near schools", "intent": "match_needs"},
            {"text": "i am a doctor, show properties near hospitals", "intent": "match_needs"},
            {"text": "i like to gym, show properties near gym", "intent": "match_needs"},
            
            # Property with criteria samples
            {"text": "houses under 3M with 3 bedrooms", "intent": "find_property_with_criteria"},
            {"text": "apartments under 15000 pesos", "intent": "find_property_with_criteria"},
            {"text": "condos with 2 bedrooms and 2 bathrooms", "intent": "find_property_with_criteria"},
            {"text": "properties under 10M with swimming pool", "intent": "find_property_with_criteria"},
            
            # ============================================
            # NEGATIVE EXAMPLES (what should NOT match)
            # ============================================
            
            # These should NOT be location_info (they have "find" keywords)
            {"text": "find tell me about batangas city", "intent": "find_property"},  # Edge case
            {"text": "search information about lipa", "intent": "find_property"},     # Mixed intent
            
            # These should NOT be find_property (they don't have search keywords)
            {"text": "about finding houses", "intent": "location_info"},  # Has "finding" but starts with "about"
            {"text": "information on searching properties", "intent": "location_info"},  # Has "searching" but starts with "information"
        ]
    }
    
    os.makedirs(data_dir, exist_ok=True)
    with open(os.path.join(data_dir, 'additional_training.json'), 'w', encoding='utf-8') as f:
        json.dump(additional_data, f, indent=2)
    
    print("✅ Created/updated additional_training.json with specific intent corrections")
    print(f"   Total samples: {len(additional_data['additional_samples'])}")
    print(f"   Focus: Fixing 'find X in Y' vs 'tell me about Y' confusion")
    
def main():
    print("="*60)
    print("🚀 BAH.AI PROPERTY CHATBOT TRAINING SYSTEM v3.4")
    print("   (With intent classification fixes)")
    print("="*60)
    
    training_dir = os.path.dirname(os.path.abspath(__file__))
    data_dir = os.path.join(training_dir, 'data')

    # Create/update additional training data file
    create_additional_training_file(data_dir)
    
    # Initialize trainer
    trainer = TeamNLUTrainer()
    
    # Load and train using ALL data sources
    texts, intents = trainer.load_all_training_data(data_dir)
    
    if texts:
        if trainer.train(texts, intents):
            backend_model_path = trainer.save_model()
            
            # Test with the specific problematic queries
            test_predictions(trainer, [
                "Properties that accept bank financing",
                "Find ready to move in properties for students in Batangas City",
                "Steps for buying a condo",
                "properties with swimming pool",
                "properties near schools",
                "how to get mortgage",
                "tell me about lipa city",
                "available now apartments",
                "houses for big family",
                "condos near malls",
                # buyer_guest_access
                "can I browse without signing up",
                "pwede ba mag browse kahit walang account",
                "what can guest access",
                # buyer_kyc
                "what is KYC",
                "how does KYC work",
                "ano ang KYC",
                "bakit kailangan KYC"
            ])
            
            # Also test with some general queries
            print("\n" + "="*60)
            print("🧪 TESTING GENERAL QUERIES")
            print("="*60)
            
            general_queries = [
                "find apartments in batangas city",
                "show me houses under 3M with 3 bedrooms",
                "properties for family needs in lipa",
                "ready to move in condos",
                "how to get a pag-ibig loan",
                "tell me about tanauan city",
                "properties with garden at reasonable cost",
                "match properties to my budget as single professional",
                "houses under 10M with swimming pool",
                "what documents are needed for bank financing"
            ]
            
            for query in general_queries:
                try:
                    intent = trainer.pipeline.predict([query])[0]
                    proba = trainer.pipeline.predict_proba([query])[0]
                    confidence = max(proba) * 100
                    print(f"🔍 '{query}'")
                    print(f"   → Intent: {intent} ({confidence:.1f}% confidence)")
                except Exception as e:
                    print(f"❌ Error predicting '{query}': {e}")
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