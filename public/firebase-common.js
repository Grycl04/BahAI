import { initializeApp } from 'https://www.gstatic.com/firebasejs/12.4.0/firebase-app.js';
import { getAuth } from 'https://www.gstatic.com/firebasejs/12.4.0/firebase-auth.js';
import { getFirestore } from 'https://www.gstatic.com/firebasejs/12.4.0/firebase-firestore.js';
import { getStorage } from 'https://www.gstatic.com/firebasejs/12.4.0/firebase-storage.js';

const firebaseConfig = {
 apiKey: "AIzaSyCIfzneDzWVveG8p_0mywoA9D9F5AyzZX4",
  authDomain: "bahai-1b76d.firebaseapp.com",
  projectId: "bahai-1b76d",
  storageBucket: "bahai-1b76d.firebasestorage.app",
  messagingSenderId: "646878644941",
  appId: "1:646878644941:web:5b4ccc3412250337587784",
  measurementId: "G-PDW1PRZTM9"
};

const app = initializeApp(firebaseConfig);
const auth = getAuth(app);
const db = getFirestore(app);
const storage = getStorage(app);

// NO emulator connections - use production

export { auth, db, storage };