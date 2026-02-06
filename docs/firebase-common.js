import { initializeApp } from 'https://www.gstatic.com/firebasejs/12.4.0/firebase-app.js';
import { getAuth } from 'https://www.gstatic.com/firebasejs/12.4.0/firebase-auth.js';
import { getFirestore } from 'https://www.gstatic.com/firebasejs/12.4.0/firebase-firestore.js';
import { getStorage } from 'https://www.gstatic.com/firebasejs/12.4.0/firebase-storage.js';

// Firebase configuration - TRY BOTH DOMAINS
const firebaseConfig = {
  apiKey: "AIzaSyCIfzneDzWVveG8p_0mywoA9D9F5AyzZX4",
  authDomain: window.location.hostname.includes('localhost') 
    ? "localhost" 
    : "bahai-1b76d.firebaseapp.com", // Use Firebase domain for GitHub
  projectId: "bahai-1b76d",
  storageBucket: "bahai-1b76d.firebasestorage.app",
  messagingSenderId: "646878644941",
  appId: "1:646878644941:web:5b4ccc3412250337587784",
  measurementId: "G-PDW1PRZTM9"
};

// Initialize Firebase
const app = initializeApp(firebaseConfig);
const auth = getAuth(app);

// Configure auth for GitHub Pages
if (window.location.hostname.includes('github.io')) {
  console.log('GitHub Pages detected, configuring auth...');
  auth.settings.appVerificationDisabledForTesting = false;
  
  // Force Firebase to accept the domain
  try {
    // This is a workaround for GitHub Pages
    auth._canInitEmulator = false;
  } catch (e) {
    // Ignore if property doesn't exist
  }
}

const db = getFirestore(app);
const storage = getStorage(app);

export { auth, db, storage };