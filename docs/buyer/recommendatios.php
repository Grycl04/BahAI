<?php
// Enable error reporting for debugging (disable in production)
error_reporting(0);
ini_set('display_errors', 0);

header('Content-Type: application/json');
header('Access-Control-Allow-Origin: *');
header('Access-Control-Allow-Methods: GET, POST');
header('Access-Control-Allow-Headers: Content-Type');

// Database configuration
$host = 'localhost';
$dbname = 'bahai_db';
$username = 'root';
$password = '';

try {
    $pdo = new PDO("mysql:host=$host;dbname=$dbname;charset=utf8mb4", $username, $password);
    $pdo->setAttribute(PDO::ATTR_ERRMODE, PDO::ERRMODE_EXCEPTION);
    $pdo->setAttribute(PDO::ATTR_DEFAULT_FETCH_MODE, PDO::FETCH_ASSOC);
} catch(PDOException $e) {
    echo json_encode(['error' => 'Database connection failed']);
    exit;
}

// Get request data
$input = json_decode(file_get_contents('php://input'), true);
$userId = isset($input['userId']) ? $input['userId'] : null;
$cookieData = isset($input['cookieData']) ? $input['cookieData'] : null;

// If no user ID and no cookie data, return featured properties
if (!$userId && !$cookieData) {
    echo json_encode(getFeaturedProperties($pdo));
    exit;
}

// Logged in user - check database first
if ($userId) {
    $recommendations = getLoggedInRecommendations($pdo, $userId, $cookieData);
    echo json_encode($recommendations);
    exit;
}

// Guest user - use cookie data only
if ($cookieData) {
    $recommendations = getGuestRecommendations($pdo, $cookieData);
    echo json_encode($recommendations);
    exit;
}

// Fallback - featured properties
echo json_encode(getFeaturedProperties($pdo));

/**
 * Get recommendations for logged-in users
 * Priority: 1. Liked properties, 2. Browsing history, 3. Cookie data
 */
function getLoggedInRecommendations($pdo, $userId, $cookieData = null) {
    $recommendations = [];
    
    // Step 1: Check liked properties from database
    $stmt = $pdo->prepare("
        SELECT p.*, sp.created_at as liked_date 
        FROM saved_properties sp
        JOIN properties p ON sp.property_id = p.id
        WHERE sp.user_id = ?
        ORDER BY sp.created_at DESC
        LIMIT 10
    ");
    $stmt->execute([$userId]);
    $likedProperties = $stmt->fetchAll();
    
    if (count($likedProperties) >= 3) {
        // Use liked properties to find similar ones
        $recommendations = getSimilarProperties($pdo, $likedProperties);
        if (count($recommendations) >= 5) {
            return [
                'type' => 'liked_based',
                'message' => 'Based on properties you liked',
                'recommendations' => $recommendations
            ];
        }
    }
    
    // Step 2: Check browsing history from database
    $stmt = $pdo->prepare("
        SELECT p.*, bh.viewed_at 
        FROM browsing_history bh
        JOIN properties p ON bh.property_id = p.id
        WHERE bh.user_id = ?
        ORDER BY bh.viewed_at DESC
        LIMIT 10
    ");
    $stmt->execute([$userId]);
    $historyProperties = $stmt->fetchAll();
    
    if (count($historyProperties) >= 3) {
        // Use browsing history to find similar ones
        $recommendations = getSimilarProperties($pdo, $historyProperties);
        if (count($recommendations) >= 5) {
            return [
                'type' => 'history_based',
                'message' => 'Based on your browsing history',
                'recommendations' => $recommendations
            ];
        }
    }
    
    // Step 3: Use cookie data if available
    if ($cookieData && !empty($cookieData)) {
        $recommendations = getCookieBasedRecommendations($pdo, $cookieData);
        if (count($recommendations) >= 3) {
            return [
                'type' => 'cookie_based',
                'message' => 'Based on your recent views',
                'recommendations' => $recommendations
            ];
        }
    }
    
    // Step 4: Fallback to featured properties
    return [
        'type' => 'featured',
        'message' => 'Featured properties for you',
        'recommendations' => getFeaturedProperties($pdo)
    ];
}

/**
 * Get recommendations for guest users using only cookie data
 */
function getGuestRecommendations($pdo, $cookieData) {
    if (!empty($cookieData)) {
        $recommendations = getCookieBasedRecommendations($pdo, $cookieData);
        if (count($recommendations) >= 3) {
            return [
                'type' => 'cookie_based',
                'message' => 'Based on properties you viewed',
                'recommendations' => $recommendations
            ];
        }
    }
    
    return [
        'type' => 'featured',
        'message' => 'Featured properties for you',
        'recommendations' => getFeaturedProperties($pdo)
    ];
}

/**
 * Get recommendations based on cookie data
 */
function getCookieBasedRecommendations($pdo, $cookieData) {
    $propertyIds = array_column($cookieData, 'property_id');
    
    if (empty($propertyIds)) {
        return [];
    }
    
    // Get viewed properties details
    $placeholders = implode(',', array_fill(0, count($propertyIds), '?'));
    $stmt = $pdo->prepare("
        SELECT location, property_type, 
               MIN(price) as min_price, 
               MAX(price) as max_price 
        FROM properties 
        WHERE id IN ($placeholders)
        GROUP BY location, property_type
    ");
    $stmt->execute($propertyIds);
    $viewedPreferences = $stmt->fetchAll();
    
    if (empty($viewedPreferences)) {
        return [];
    }
    
    // Build query based on viewed properties preferences
    $sql = "SELECT * FROM properties WHERE status = 'active' AND id NOT IN ($placeholders)";
    $params = $propertyIds;
    
    $conditions = [];
    foreach ($viewedPreferences as $pref) {
        $conds = [];
        if (!empty($pref['location'])) {
            $conds[] = "location LIKE ?";
            $params[] = '%' . $pref['location'] . '%';
        }
        if (!empty($pref['property_type'])) {
            $conds[] = "property_type = ?";
            $params[] = $pref['property_type'];
        }
        if (!empty($pref['min_price']) && !empty($pref['max_price'])) {
            $conds[] = "(price BETWEEN ? AND ?)";
            $params[] = $pref['min_price'] * 0.8; // 20% lower
            $params[] = $pref['max_price'] * 1.2; // 20% higher
        }
        
        if (!empty($conds)) {
            $conditions[] = '(' . implode(' AND ', $conds) . ')';
        }
    }
    
    if (!empty($conditions)) {
        $sql .= ' AND (' . implode(' OR ', $conditions) . ')';
    }
    
    $sql .= " ORDER BY created_at DESC LIMIT 8";
    
    $stmt = $pdo->prepare($sql);
    $stmt->execute($params);
    
    return $stmt->fetchAll();
}

/**
 * Get similar properties based on liked/history properties
 */
function getSimilarProperties($pdo, $sourceProperties) {
    if (empty($sourceProperties)) {
        return [];
    }
    
    $sourceIds = array_column($sourceProperties, 'id');
    $placeholders = implode(',', array_fill(0, count($sourceIds), '?'));
    
    // Extract preferences from source properties
    $locations = [];
    $types = [];
    $priceRanges = [];
    
    foreach ($sourceProperties as $prop) {
        if (!empty($prop['location'])) {
            $locations[] = $prop['location'];
        }
        if (!empty($prop['property_type'])) {
            $types[] = $prop['property_type'];
        }
        if (!empty($prop['price'])) {
            $priceRanges[] = $prop['price'];
        }
    }
    
    // Build query based on preferences
    $sql = "SELECT * FROM properties WHERE status = 'active' AND id NOT IN ($placeholders)";
    $params = $sourceIds;
    
    $conditions = [];
    
    if (!empty($locations)) {
        $locationConds = [];
        foreach (array_slice($locations, 0, 3) as $loc) {
            $locationConds[] = "location LIKE ?";
            $params[] = '%' . $loc . '%';
        }
        if (!empty($locationConds)) {
            $conditions[] = '(' . implode(' OR ', $locationConds) . ')';
        }
    }
    
    if (!empty($types)) {
        $typeConds = [];
        foreach (array_slice($types, 0, 3) as $type) {
            $typeConds[] = "property_type = ?";
            $params[] = $type;
        }
        if (!empty($typeConds)) {
            $conditions[] = '(' . implode(' OR ', $typeConds) . ')';
        }
    }
    
    if (!empty($priceRanges)) {
        $avgPrice = array_sum($priceRanges) / count($priceRanges);
        $conditions[] = "(price BETWEEN ? AND ?)";
        $params[] = $avgPrice * 0.7;
        $params[] = $avgPrice * 1.3;
    }
    
    if (!empty($conditions)) {
        $sql .= ' AND ' . implode(' AND ', $conditions);
    }
    
    $sql .= " ORDER BY created_at DESC LIMIT 8";
    
    $stmt = $pdo->prepare($sql);
    $stmt->execute($params);
    
    return $stmt->fetchAll();
}

/**
 * Get featured/popular properties
 */
function getFeaturedProperties($pdo) {
    $stmt = $pdo->prepare("
        SELECT * FROM properties 
        WHERE status = 'active' 
        ORDER BY views DESC, created_at DESC 
        LIMIT 8
    ");
    $stmt->execute();
    return $stmt->fetchAll();
}
?>