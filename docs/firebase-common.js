import { initializeApp } from 'https://www.gstatic.com/firebasejs/12.4.0/firebase-app.js';
import { 
  getAuth, 
  browserLocalPersistence,
  setPersistence,
  GoogleAuthProvider  // ADD THIS IMPORT
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

// Initialize Auth
const auth = getAuth(app);

// Initialize Google Provider with proper configuration
const googleProvider = new GoogleAuthProvider();
// Add these important scopes
googleProvider.addScope('profile');
googleProvider.addScope('email');
// Force account selection
googleProvider.setCustomParameters({
  prompt: 'select_account'
});

// Set persistence
(async () => {
  try {
    await setPersistence(auth, browserLocalPersistence);
    console.log('Auth persistence set to local');
  } catch (error) {
    console.warn('Could not set persistence:', error);
  }
})();

const db = getFirestore(app);
const storage = getStorage(app);

// Export all three
export { auth, db, storage, googleProvider };