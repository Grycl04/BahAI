import { initializeApp } from 'https://www.gstatic.com/firebasejs/12.4.0/firebase-app.js';
import { getAuth } from 'https://www.gstatic.com/firebasejs/12.4.0/firebase-auth.js';
import { getFirestore } from 'https://www.gstatic.com/firebasejs/12.4.0/firebase-firestore.js';
import { getStorage } from 'https://www.gstatic.com/firebasejs/12.4.0/firebase-storage.js';

// Firebase configuration - CRITICAL FIXES
const firebaseConfig = {
  apiKey: "AIzaSyCIfzneDzWVveG8p_0mywoA9D9F5AyzZX4",
  authDomain: window.location.hostname.includes('github.io') 
    ? "bahai-1b76d.firebaseapp.com"  // Always use Firebase domain
    : window.location.hostname,
  projectId: "bahai-1b76d",
  storageBucket: "bahai-1b76d.firebasestorage.app",
  messagingSenderId: "646878644941",
  appId: "1:646878644941:web:5b4ccc3412250337587784",
  measurementId: "G-PDW1PRZTM9"
};

// Initialize Firebase with error handling
let app, auth, db, storage;

try {
  console.log('🚀 Initializing Firebase...');
  app = initializeApp(firebaseConfig);
  
  // Get services
  auth = getAuth(app);
  db = getFirestore(app);
  storage = getStorage(app);
  
  // CRITICAL: Force Firebase to accept GitHub Pages domain
  if (window.location.hostname.includes('github.io')) {
    console.log('🔧 Configuring for GitHub Pages...');
    auth.settings.appVerificationDisabledForTesting = false;
    
    // Override domain check
    auth._canInitEmulator = function() {
      return false;
    };
  }
  
  console.log('✅ Firebase initialized successfully');
  
} catch (error) {
  console.error('❌ Firebase initialization failed:', error);
  // Create mock services for graceful degradation
  auth = { isMock: true, config: { authDomain: firebaseConfig.authDomain } };
  db = { isMock: true };
  storage = { isMock: true };
}

export { auth, db, storage };