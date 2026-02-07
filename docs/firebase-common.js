import { initializeApp } from 'https://www.gstatic.com/firebasejs/12.4.0/firebase-app.js';
import { 
  getAuth, 
  initializeAuth, 
  browserLocalPersistence,
  browserPopupRedirectResolver,
  browserSessionPersistence,
  setPersistence,
  indexedDBLocalPersistence,
  inMemoryPersistence
} from 'https://www.gstatic.com/firebasejs/12.4.0/firebase-auth.js';
import { getFirestore } from 'https://www.gstatic.com/firebasejs/12.4.0/firebase-firestore.js';
import { getStorage } from 'https://www.gstatic.com/firebasejs/12.4.0/firebase-storage.js';

// Firebase configuration
const firebaseConfig = {
  apiKey: "AIzaSyCIfzneDzWVveG8p_0mywoA9D9F5AyzZX4",
  authDomain: "bahai-1b76d.firebaseapp.com",
  projectId: "bahai-1b76d",
  storageBucket: "bahai-1b76d.firebasestorage.app",
  messagingSenderId: "646878644941",
  appId: "1:646878644941:web:5b4ccc3412250337587784",
  measurementId: "G-PDW1PRZTM9"
};

// Initialize Firebase
const app = initializeApp(firebaseConfig);

// IMPORTANT: Initialize auth with custom settings for mobile compatibility
let auth;
try {
  // Try to initialize with persistence
  auth = initializeAuth(app, {
    persistence: [indexedDBLocalPersistence, browserLocalPersistence, browserSessionPersistence],
    popupRedirectResolver: browserPopupRedirectResolver
  });
} catch (error) {
  console.warn('Auth initialization failed, using getAuth:', error);
  auth = getAuth(app);
}

// Set persistence
try {
  await setPersistence(auth, browserLocalPersistence);
} catch (error) {
  console.warn('Could not set persistence:', error);
}

const db = getFirestore(app);
const storage = getStorage(app);

export { auth, db, storage };