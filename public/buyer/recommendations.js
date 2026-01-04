// recommendations.js - PERSONAL RECOMMENDATIONS BASED ON USER BEHAVIOR
import { initializeApp } from "https://www.gstatic.com/firebasejs/12.4.0/firebase-app.js";
import {
  getFirestore,
  collection,
  addDoc,
  serverTimestamp,
  getDocs,
  query,
  where,
  limit,
  doc,
  getDoc,
  orderBy
} from "https://www.gstatic.com/firebasejs/12.4.0/firebase-firestore.js";
import {
  getAuth
} from "https://www.gstatic.com/firebasejs/12.4.0/firebase-auth.js";

// Firebase Config
const firebaseConfig = {
  apiKey: "AIzaSyCIfzneDzWVveG8p_0mywoA9D9F5AyzZX4",
  authDomain: "bahai-1b76d.firebaseapp.com",
  projectId: "bahai-1b76d",
  storageBucket: "bahai-1b76d.firebasestorage.app",
  messagingSenderId: "646878644941",
  appId: "1:646878644941:web:5b4ccc3412250337587784"
};

const app = initializeApp(firebaseConfig);
const db = getFirestore(app);
const auth = getAuth(app);

// ---------------------
// Event Logging Functions
// ---------------------
async function logEvent(userId, eventType, metadata = {}) {
  try {
    await addDoc(collection(db, "events"), {
      userId: userId,
      eventType: eventType,
      metadata: metadata,
      timestamp: serverTimestamp()
    });
    console.log(`✅ Logged ${eventType} event for user ${userId}`);
    return true;
  } catch (error) {
    console.error("❌ Failed to log event:", error);
    return false;
  }
}

// Helper function to clean object (remove undefined values)
function cleanObject(obj) {
  const cleaned = {};
  for (const [key, value] of Object.entries(obj)) {
    if (value !== undefined && value !== null && value !== '') {
      cleaned[key] = value;
    }
  }
  return cleaned;
}

export async function logViewEvent(userId, propertyId) {
  return await logEvent(userId, 'view', { propertyId: propertyId });
}

export async function logSaveEvent(userId, propertyId) {
  return await logEvent(userId, 'save', { propertyId: propertyId });
}

export async function logContactEvent(userId, propertyId) {
  return await logEvent(userId, 'contact', { propertyId: propertyId });
}

export async function logSearchEvent(userId, filters) {
  // Clean the filters object to remove undefined/null/empty values
  const cleanedFilters = cleanObject(filters);
  
  // Only log if there are actual filters
  if (Object.keys(cleanedFilters).length > 0) {
    return await logEvent(userId, 'search', { filters: cleanedFilters });
  }
  return true; // Return success if no filters to log
}

// ---------------------
// Get User Preferences from Saved Properties
// ---------------------
async function getUserPreferencesFromSaved(userId) {
  try {
    console.log('🔍 Analyzing saved properties for user:', userId);
    
    // Get user's saved properties
    const savedRef = collection(db, 'savedProperties');
    const q = query(savedRef, where('userId', '==', userId));
    const savedSnapshot = await getDocs(q);
    
    if (savedSnapshot.empty) {
      console.log('📭 No saved properties found');
      return null;
    }
    
    // Fetch full property details for each saved property
    const savedPropertyIds = savedSnapshot.docs.map(doc => doc.data().propertyId);
    console.log(`📋 Found ${savedPropertyIds.length} saved properties`);
    
    const savedProperties = [];
    for (const propId of savedPropertyIds) {
      const propDoc = await getDoc(doc(db, 'properties', propId));
      if (propDoc.exists()) {
        savedProperties.push({ id: propDoc.id, ...propDoc.data() });
      }
    }
    
    if (savedProperties.length === 0) {
      return null;
    }
    
    // Analyze preferences
    const preferences = {
      propertyTypes: {},
      priceRange: { min: Infinity, max: 0 },
      locations: {},
      bedrooms: {},
      listingTypes: { rent: 0, sale: 0 },
      avgPrice: 0,
      totalCount: savedProperties.length
    };
    
    let totalPrice = 0;
    
    savedProperties.forEach(prop => {
      // Property type
      if (prop.propertyType) {
        preferences.propertyTypes[prop.propertyType] = 
          (preferences.propertyTypes[prop.propertyType] || 0) + 1;
      }
      
      // Price analysis
      const price = prop.monthlyRent || prop.pricing || prop.price || 0;
      if (price > 0) {
        preferences.priceRange.min = Math.min(preferences.priceRange.min, price);
        preferences.priceRange.max = Math.max(preferences.priceRange.max, price);
        totalPrice += price;
      }
      
      // Location
      if (prop.location) {
        const city = prop.location.split(',')[0].trim();
        preferences.locations[city] = (preferences.locations[city] || 0) + 1;
      }
      
      // Bedrooms
      if (prop.bedrooms) {
        preferences.bedrooms[prop.bedrooms] = 
          (preferences.bedrooms[prop.bedrooms] || 0) + 1;
      }
      
      // Listing type (rent vs sale)
      if (prop.monthlyRent) {
        preferences.listingTypes.rent++;
      } else {
        preferences.listingTypes.sale++;
      }
    });
    
    preferences.avgPrice = totalPrice / savedProperties.length;
    
    // Expand price range by 30%
    const range = preferences.priceRange.max - preferences.priceRange.min;
    preferences.priceRange.min = Math.max(0, preferences.priceRange.min - range * 0.3);
    preferences.priceRange.max = preferences.priceRange.max + range * 0.3;
    
    console.log('✅ User preferences:', preferences);
    return preferences;
    
  } catch (error) {
    console.error('❌ Error analyzing saved properties:', error);
    return null;
  }
}

// ---------------------
// Get User Search Patterns
// ---------------------
async function getUserSearchPatterns(userId) {
  try {
    console.log('🔍 Analyzing search patterns for user:', userId);
    
    const eventsRef = collection(db, 'events');
    const q = query(
      eventsRef,
      where('userId', '==', userId),
      where('eventType', '==', 'search'),
      orderBy('timestamp', 'desc'),
      limit(20)
    );
    
    const snapshot = await getDocs(q);
    
    if (snapshot.empty) {
      console.log('📭 No search history found');
      return null;
    }
    
    const searchPatterns = {
      propertyTypes: {},
      priceRanges: {},
      locations: {},
      listingTypes: {}
    };
    
    snapshot.forEach(doc => {
      const data = doc.data();
      const filters = data.metadata?.filters || {};
      
      if (filters.propertyType) {
        searchPatterns.propertyTypes[filters.propertyType] = 
          (searchPatterns.propertyTypes[filters.propertyType] || 0) + 1;
      }
      
      if (filters.priceRange) {
        searchPatterns.priceRanges[filters.priceRange] = 
          (searchPatterns.priceRanges[filters.priceRange] || 0) + 1;
      }
      
      if (filters.location) {
        searchPatterns.locations[filters.location] = 
          (searchPatterns.locations[filters.location] || 0) + 1;
      }
      
      if (filters.listingType) {
        searchPatterns.listingTypes[filters.listingType] = 
          (searchPatterns.listingTypes[filters.listingType] || 0) + 1;
      }
    });
    
    console.log('✅ Search patterns:', searchPatterns);
    return searchPatterns;
    
  } catch (error) {
    console.log('⚠️ Could not analyze search patterns:', error.message);
    return null;
  }
}

// ---------------------
// Calculate Property Match Score
// ---------------------
function calculateMatchScore(property, preferences, searchPatterns) {
  let score = 0;
  let maxScore = 0;
  
  // Property type match (30 points)
  maxScore += 30;
  if (preferences?.propertyTypes && property.propertyType) {
    const typeCount = preferences.propertyTypes[property.propertyType] || 0;
    const totalTypes = preferences.totalCount || 1;
    score += (typeCount / totalTypes) * 30;
  }
  if (searchPatterns?.propertyTypes && property.propertyType) {
    const typeCount = searchPatterns.propertyTypes[property.propertyType] || 0;
    const totalSearches = Object.values(searchPatterns.propertyTypes).reduce((a, b) => a + b, 0);
    score += (typeCount / totalSearches) * 15;
  }
  
  // Price range match (25 points)
  maxScore += 25;
  if (preferences?.priceRange) {
    const price = property.monthlyRent || property.pricing || property.price || 0;
    if (price >= preferences.priceRange.min && price <= preferences.priceRange.max) {
      score += 25;
      
      // Bonus for being close to average price
      const diff = Math.abs(price - preferences.avgPrice);
      const range = preferences.priceRange.max - preferences.priceRange.min;
      if (range > 0) {
        const proximity = 1 - (diff / range);
        score += proximity * 10;
        maxScore += 10;
      }
    }
  }
  
  // Location match (20 points)
  maxScore += 20;
  if (preferences?.locations && property.location) {
    const city = property.location.split(',')[0].trim();
    const locationCount = preferences.locations[city] || 0;
    const totalLocations = preferences.totalCount || 1;
    score += (locationCount / totalLocations) * 20;
  }
  if (searchPatterns?.locations && property.location) {
    Object.keys(searchPatterns.locations).forEach(searchLocation => {
      if (property.location.toLowerCase().includes(searchLocation.toLowerCase())) {
        score += 10;
        maxScore += 10;
      }
    });
  }
  
  // Bedroom match (15 points)
  maxScore += 15;
  if (preferences?.bedrooms && property.bedrooms) {
    const bedroomCount = preferences.bedrooms[property.bedrooms] || 0;
    const totalBedrooms = preferences.totalCount || 1;
    score += (bedroomCount / totalBedrooms) * 15;
  }
  
  // Listing type match (10 points)
  maxScore += 10;
  if (preferences?.listingTypes) {
    const isRent = !!property.monthlyRent;
    const preferredType = preferences.listingTypes.rent > preferences.listingTypes.sale ? 'rent' : 'sale';
    if ((isRent && preferredType === 'rent') || (!isRent && preferredType === 'sale')) {
      score += 10;
    }
  }
  
  // Normalize score to 0-1 range
  return maxScore > 0 ? score / maxScore : 0;
}

// ---------------------
// Get Personalized Recommendations
// ---------------------
async function getPersonalizedRecommendations(userId, count = 6) {
  try {
    console.log('🎯 Generating personalized recommendations for:', userId);
    
    // Get user preferences from saved properties
    const preferences = await getUserPreferencesFromSaved(userId);
    
    // Get user search patterns
    const searchPatterns = await getUserSearchPatterns(userId);
    
    if (!preferences && !searchPatterns) {
      console.log('⚠️ No user behavior data found');
      return [];
    }
    
    // Get all active properties
    const propertiesRef = collection(db, 'properties');
    const propertiesQuery = query(
      propertiesRef,
      where('status', '==', 'active'),
      limit(100)
    );
    const propertiesSnapshot = await getDocs(propertiesQuery);
    
    if (propertiesSnapshot.empty) {
      console.log('📭 No properties found');
      return [];
    }
    
    // Get user's saved property IDs to exclude them
    const savedRef = collection(db, 'savedProperties');
    const savedQuery = query(savedRef, where('userId', '==', userId));
    const savedSnapshot = await getDocs(savedQuery);
    const savedPropertyIds = new Set(savedSnapshot.docs.map(doc => doc.data().propertyId));
    
    // Score each property
    const scoredProperties = [];
    propertiesSnapshot.forEach(docSnapshot => {
      const property = { id: docSnapshot.id, ...docSnapshot.data() };
      
      // Skip saved properties
      if (savedPropertyIds.has(property.id)) {
        return;
      }
      
      const matchScore = calculateMatchScore(property, preferences, searchPatterns);
      
      if (matchScore > 0.3) { // Only include properties with >30% match
        scoredProperties.push({
          ...property,
          recoScore: matchScore
        });
      }
    });
    
    // Sort by score and return top N
    scoredProperties.sort((a, b) => b.recoScore - a.recoScore);
    
    const recommendations = scoredProperties.slice(0, count);
    console.log(`✅ Generated ${recommendations.length} personalized recommendations`);
    
    return recommendations;
    
  } catch (error) {
    console.error('❌ Error generating recommendations:', error);
    return [];
  }
}

// ---------------------
// Show Popular/Recent Listings (Fallback)
// ---------------------
async function showPopularListings() {
  try {
    console.log('📊 Showing recent listings as fallback');
    
    const propertiesRef = collection(db, 'properties');
    let snapshot;
    
    try {
      const q = query(
        propertiesRef,
        where('status', '==', 'active'),
        orderBy('createdAt', 'desc'),
        limit(6)
      );
      snapshot = await getDocs(q);
    } catch (orderError) {
      const q = query(
        propertiesRef,
        where('status', '==', 'active'),
        limit(6)
      );
      snapshot = await getDocs(q);
    }
    
    const listings = [];
    snapshot.forEach(doc => {
      listings.push({
        id: doc.id,
        ...doc.data(),
        recoScore: 0.5 + Math.random() * 0.2,
        isRecent: true
      });
    });
    
    if (listings.length > 0) {
      displayRecommendedListings(listings, 'recent');
    } else {
      hideRecommendationsSection();
    }
    
    return listings;
    
  } catch (error) {
    console.error('❌ Error loading popular listings:', error);
    hideRecommendationsSection();
    return [];
  }
}

// ---------------------
// Main Recommendation Loader
// ---------------------
export async function loadRecommendations() {
  try {
    const currentUser = auth.currentUser;
    if (!currentUser) {
      console.log('User not authenticated, skipping recommendations');
      hideRecommendationsSection();
      return;
    }
    
    const userId = currentUser.uid;
    console.log('🚀 Loading recommendations for user:', userId);
    
    // Show loading state
    showLoadingState();
    
    // Get personalized recommendations
    const recommendations = await getPersonalizedRecommendations(userId, 6);
    
    if (recommendations.length === 0) {
      console.log('⚠️ No personalized recommendations, showing recent listings');
      await showPopularListings();
    } else {
      displayRecommendedListings(recommendations, 'personalized');
    }
    
  } catch (error) {
    console.error('❌ Error loading recommendations:', error);
    await showPopularListings();
  }
}

// ---------------------
// UI Functions
// ---------------------
function showLoadingState() {
  let recoSection = document.getElementById('recommendedSection');
  if (!recoSection) {
    recoSection = createRecommendationsSection();
  }
  
  const recoContainer = document.getElementById('recommendedListingsContainer');
  if (recoContainer) {
    recoContainer.innerHTML = `
      <div style="grid-column: 1 / -1; text-align: center; padding: 40px 20px;">
        <div class="spinner" style="border: 4px solid var(--bg-light); 
          border-top: 4px solid var(--primary); border-radius: 50%; 
          width: 40px; height: 40px; animation: spin 1s linear infinite; 
          margin: 0 auto 20px;"></div>
        <p style="color: var(--text-light);">Finding properties you'll love...</p>
      </div>
    `;
  }
  
  recoSection.style.display = 'block';
}

function hideRecommendationsSection() {
  const recoSection = document.getElementById('recommendedSection');
  if (recoSection) {
    recoSection.style.display = 'none';
  }
}

function createRecommendationsSection() {
  const recoSection = document.createElement('div');
  recoSection.id = 'recommendedSection';
  recoSection.className = 'recommendations-section';
  recoSection.style.marginBottom = '30px';
  
  const header = document.createElement('h2');
  header.id = 'recommendationsHeader';
  header.className = 'section-title';
  header.style.cssText = `
    font-size: 24px;
    font-weight: 600;
    color: var(--text-dark);
    margin-bottom: 20px;
    padding-bottom: 10px;
    border-bottom: 2px solid var(--primary);
  `;
  recoSection.appendChild(header);
  
  const recoContainer = document.createElement('div');
  recoContainer.id = 'recommendedListingsContainer';
  recoContainer.className = 'listings-grid';
  recoSection.appendChild(recoContainer);
  
  // Insert before stats
  const statsGrid = document.querySelector('.stats-grid');
  if (statsGrid && statsGrid.parentNode) {
    statsGrid.parentNode.insertBefore(recoSection, statsGrid.nextSibling);
  }
  
  return recoSection;
}

export function displayRecommendedListings(recommendations, type = 'personalized') {
  let recoSection = document.getElementById('recommendedSection');
  if (!recoSection) {
    recoSection = createRecommendationsSection();
  }
  
  const header = document.getElementById('recommendationsHeader');
  if (header) {
    if (type === 'personalized') {
      header.innerHTML = '🎯 Recommended For You <span style="font-size: 14px; color: var(--text-light); font-weight: 400; margin-left: 10px;">Based on your saved properties</span>';
    } else if (type === 'recent') {
      header.innerHTML = '🏠 Recent Properties <span style="font-size: 14px; color: var(--text-light); font-weight: 400; margin-left: 10px;">Save properties to get personalized recommendations!</span>';
    }
  }
  
  const recoContainer = document.getElementById('recommendedListingsContainer');
  if (!recoContainer) return;
  
  recoContainer.innerHTML = '';
  
  if (!recommendations || recommendations.length === 0) {
    recoContainer.innerHTML = `
      <div class="empty-state" style="grid-column: 1 / -1; text-align: center; padding: 40px 20px;">
        <div style="font-size: 48px; margin-bottom: 20px;">❤️</div>
        <h3 style="color: var(--text-dark); margin-bottom: 10px;">Start Building Your Preferences</h3>
        <p style="color: var(--text-light); max-width: 500px; margin: 0 auto;">
          Save properties you like to get personalized recommendations!
        </p>
      </div>
    `;
    return;
  }
  
  recommendations.forEach(property => {
    const card = createPropertyCard(property, type);
    if (card) {
      recoContainer.appendChild(card);
    }
  });
  
  recoSection.style.display = 'block';
}

function createPropertyCard(property, type) {
  if (!property || !property.id) return null;
  
  const card = document.createElement('div');
  card.className = 'listing-card';
  card.style.cssText = `
    background: white;
    border-radius: 12px;
    overflow: hidden;
    box-shadow: 0 4px 12px rgba(0,0,0,0.08);
    transition: transform 0.3s ease, box-shadow 0.3s ease;
    cursor: pointer;
    height: 100%;
    display: flex;
    flex-direction: column;
  `;
  
  card.addEventListener('mouseenter', () => {
    card.style.transform = 'translateY(-4px)';
    card.style.boxShadow = '0 8px 24px rgba(0,0,0,0.12)';
  });
  
  card.addEventListener('mouseleave', () => {
    card.style.transform = 'translateY(0)';
    card.style.boxShadow = '0 4px 12px rgba(0,0,0,0.08)';
  });
  
  const price = property.monthlyRent || property.pricing || property.price || 0;
  const isForRent = !!property.monthlyRent;
  const photo = property.photos?.[0] || property.imageUrls?.[0] || 
    `https://via.placeholder.com/400x200/0b2e52/white?text=${encodeURIComponent(property.title || 'Property')}`;
  
  const matchScore = property.recoScore ? Math.round(property.recoScore * 100) : null;
  
  card.innerHTML = `
    <div style="position: relative; flex-shrink: 0;">
      <img src="${photo}" alt="${property.title || 'Property'}" 
        style="width: 100%; height: 200px; object-fit: cover;">
      
      ${matchScore && matchScore > 50 ? `
        <div style="position: absolute; top: 12px; left: 12px; 
          background: linear-gradient(135deg, #10b981, #059669); 
          color: white; padding: 6px 12px; border-radius: 20px; 
          font-size: 12px; font-weight: 600; box-shadow: 0 2px 8px rgba(0,0,0,0.2);">
          ${matchScore}% Match
        </div>
      ` : ''}
      
      ${type === 'personalized' ? `
        <div style="position: absolute; top: 12px; right: 12px; 
          background: var(--secondary); color: white; 
          padding: 4px 12px; border-radius: 20px; 
          font-size: 12px; font-weight: 600;">
          ⭐ For You
        </div>
      ` : ''}
    </div>
    
    <div style="padding: 20px; flex-grow: 1; display: flex; flex-direction: column;">
      <div style="display: flex; justify-content: space-between; align-items: flex-start; margin-bottom: 10px;">
        <div style="flex-grow: 1;">
          <h3 style="font-size: 18px; font-weight: 600; color: var(--text-dark); margin-bottom: 5px;">
            ${property.title || 'Untitled Property'}
          </h3>
          <div style="color: var(--text-light); font-size: 14px; display: flex; align-items: center; gap: 5px;">
            <span>📍</span> ${property.location || 'Location not specified'}
          </div>
        </div>
        <div style="font-size: 20px; font-weight: 700; color: ${isForRent ? 'var(--rent-color)' : 'var(--sale-color)'}; white-space: nowrap; margin-left: 10px;">
          ₱${price.toLocaleString()}${isForRent ? '/month' : ''}
        </div>
      </div>
      
      <div style="display: flex; gap: 15px; margin-bottom: 15px; flex-wrap: wrap;">
        ${property.bedrooms ? `
          <div style="display: flex; align-items: center; gap: 5px; font-size: 14px; color: var(--text-light);">
            <span>🛏</span> ${property.bedrooms} ${property.bedrooms === 'Studio' ? '' : 'beds'}
          </div>
        ` : ''}
        ${property.bathrooms ? `
          <div style="display: flex; align-items: center; gap: 5px; font-size: 14px; color: var(--text-light);">
            <span>🚿</span> ${property.bathrooms} baths
          </div>
        ` : ''}
        ${property.squareFootage ? `
          <div style="display: flex; align-items: center; gap: 5px; font-size: 14px; color: var(--text-light);">
            <span>📐</span> ${property.squareFootage}
          </div>
        ` : ''}
      </div>
      
      <div style="margin-top: auto;">
        <button class="view-details-btn" 
          style="width: 100%; padding: 12px; background: var(--secondary); 
            color: white; border: none; border-radius: 8px; cursor: pointer; 
            font-weight: 500; transition: background 0.3s;">
          View Details
        </button>
      </div>
    </div>
  `;
  
  card.addEventListener('click', () => {
    if (auth.currentUser) {
      logViewEvent(auth.currentUser.uid, property.id);
    }
    window.showListingDetails(property.id);
  });
  
  return card;
}

// Add CSS animations
const style = document.createElement('style');
style.textContent = `
  @keyframes spin {
    0% { transform: rotate(0deg); }
    100% { transform: rotate(360deg); }
  }
`;
document.head.appendChild(style);

export { db, auth };