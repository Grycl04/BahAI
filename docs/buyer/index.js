const functions = require('firebase-functions');
const admin = require('firebase-admin');
admin.initializeApp();

const db = admin.firestore();

exports.getRecommendations = functions.https.onCall(async (data, context) => {
    try {
        const { userId, cookieData } = data;
        
        // Case 1: Logged-in user
        if (userId) {
            return await getLoggedInRecommendations(userId, cookieData);
        }
        
        // Case 2: Guest user with cookie data
        if (cookieData && cookieData.length > 0) {
            return await getGuestRecommendations(cookieData);
        }
        
        // Case 3: No data - return featured
        return await getFeaturedProperties();
        
    } catch (error) {
        console.error('Error in recommendations:', error);
        return {
            type: 'featured',
            message: 'Featured properties',
            recommendations: await getFeaturedProperties()
        };
    }
});

/**
 * Get recommendations for logged-in users
 * Priority: 1. Liked properties, 2. Browsing history, 3. Cookie data
 */
async function getLoggedInRecommendations(userId, cookieData) {
    // Step 1: Check liked properties
    const savedSnapshot = await db.collection('savedProperties')
        .where('userId', '==', userId)
        .orderBy('savedAt', 'desc')
        .limit(10)
        .get();
    
    const likedProperties = [];
    const likedIds = [];
    
    savedSnapshot.forEach(doc => {
        likedIds.push(doc.data().propertyId);
    });
    
    if (likedIds.length > 0) {
        // Get actual property details
        for (const propId of likedIds.slice(0, 5)) {
            const propDoc = await db.collection('properties').doc(propId).get();
            if (propDoc.exists) {
                likedProperties.push({ id: propDoc.id, ...propDoc.data() });
            }
        }
    }
    
    if (likedProperties.length >= 3) {
        const recommendations = await findSimilarProperties(likedProperties);
        if (recommendations.length >= 5) {
            return {
                type: 'liked_based',
                message: 'Based on properties you liked',
                recommendations
            };
        }
    }
    
    // Step 2: Check browsing history (you'll need to create this collection)
    const historySnapshot = await db.collection('browsingHistory')
        .where('userId', '==', userId)
        .orderBy('viewedAt', 'desc')
        .limit(10)
        .get();
    
    const historyProperties = [];
    const historyIds = [];
    
    historySnapshot.forEach(doc => {
        historyIds.push(doc.data().propertyId);
    });
    
    if (historyIds.length > 0) {
        for (const propId of historyIds.slice(0, 5)) {
            const propDoc = await db.collection('properties').doc(propId).get();
            if (propDoc.exists) {
                historyProperties.push({ id: propDoc.id, ...propDoc.data() });
            }
        }
    }
    
    if (historyProperties.length >= 3) {
        const recommendations = await findSimilarProperties(historyProperties);
        if (recommendations.length >= 5) {
            return {
                type: 'history_based',
                message: 'Based on your browsing history',
                recommendations
            };
        }
    }
    
    // Step 3: Use cookie data if available
    if (cookieData && cookieData.length > 0) {
        const recommendations = await getCookieBasedRecommendations(cookieData);
        if (recommendations.length >= 3) {
            return {
                type: 'cookie_based',
                message: 'Based on your recent views',
                recommendations
            };
        }
    }
    
    // Step 4: Fallback to featured
    return {
        type: 'featured',
        message: 'Featured properties for you',
        recommendations: await getFeaturedProperties()
    };
}

/**
 * Get recommendations for guest users using cookie data
 */
async function getGuestRecommendations(cookieData) {
    if (cookieData && cookieData.length > 0) {
        const recommendations = await getCookieBasedRecommendations(cookieData);
        if (recommendations.length >= 3) {
            return {
                type: 'cookie_based',
                message: 'Based on properties you viewed',
                recommendations
            };
        }
    }
    
    return {
        type: 'featured',
        message: 'Featured properties for you',
        recommendations: await getFeaturedProperties()
    };
}

/**
 * Find similar properties based on source properties
 */
async function findSimilarProperties(sourceProperties) {
    if (!sourceProperties || sourceProperties.length === 0) {
        return [];
    }
    
    // Extract preferences
    const locations = [];
    const types = [];
    const priceRanges = [];
    const sourceIds = sourceProperties.map(p => p.id);
    
    sourceProperties.forEach(prop => {
        if (prop.location) locations.push(prop.location);
        if (prop.propertyType) types.push(prop.propertyType);
        if (prop.price || prop.pricing) {
            priceRanges.push(prop.price || prop.pricing);
        }
    });
    
    // Build query
    let query = db.collection('properties')
        .where('status', '==', 'active')
        .limit(20);
    
    const snapshot = await query.get();
    
    let candidates = [];
    snapshot.forEach(doc => {
        if (!sourceIds.includes(doc.id)) {
            candidates.push({ id: doc.id, ...doc.data() });
        }
    });
    
    // Score and filter candidates
    const scored = candidates.map(prop => {
        let score = 0;
        
        // Location match
        if (locations.some(loc => 
            prop.location?.toLowerCase().includes(loc.toLowerCase()) ||
            prop.city?.toLowerCase().includes(loc.toLowerCase())
        )) {
            score += 0.4;
        }
        
        // Property type match
        if (types.some(type => 
            prop.propertyType?.toLowerCase() === type.toLowerCase()
        )) {
            score += 0.3;
        }
        
        // Price range match
        const propPrice = prop.price || prop.pricing || 0;
        if (priceRanges.length > 0) {
            const avgPrice = priceRanges.reduce((a, b) => a + b, 0) / priceRanges.length;
            const priceDiff = Math.abs(propPrice - avgPrice) / avgPrice;
            if (priceDiff < 0.3) {
                score += 0.3 * (1 - priceDiff);
            }
        }
        
        return { ...prop, similarity_score: score };
    });
    
    // Sort by score and return top 8
    return scored
        .filter(p => p.similarity_score > 0.2)
        .sort((a, b) => b.similarity_score - a.similarity_score)
        .slice(0, 8);
}

/**
 * Get recommendations based on cookie data
 */
async function getCookieBasedRecommendations(cookieData) {
    if (!cookieData || cookieData.length === 0) {
        return [];
    }
    
    const propertyIds = cookieData.map(item => item.property_id);
    
    // Get viewed properties details
    const viewedProperties = [];
    for (const propId of propertyIds) {
        const propDoc = await db.collection('properties').doc(propId).get();
        if (propDoc.exists) {
            viewedProperties.push(propDoc.data());
        }
    }
    
    if (viewedProperties.length === 0) {
        return [];
    }
    
    return await findSimilarProperties(viewedProperties);
}

/**
 * Get featured/popular properties
 */
async function getFeaturedProperties() {
    const snapshot = await db.collection('properties')
        .where('status', '==', 'active')
        .orderBy('views', 'desc')
        .limit(8)
        .get();
    
    const properties = [];
    snapshot.forEach(doc => {
        properties.push({ id: doc.id, ...doc.data() });
    });
    
    return properties;
}