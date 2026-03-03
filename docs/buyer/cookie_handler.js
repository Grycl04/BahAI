/**
 * Cookie handler for storing recent property views
 * Stores up to 5 properties in a JSON cookie
 * No sensitive data stored
 */
const PropertyCookie = {
    // Cookie name
    COOKIE_NAME: 'recent_properties',
    
    // Max number of properties to store
    MAX_ITEMS: 5,
    
    // Cookie expiry (30 days)
    COOKIE_EXPIRY: 30,
    
    /**
     * Get all recent properties from cookie
     * @returns {Array} Array of property objects
     */
    getRecentProperties() {
        const cookieValue = this.getCookie(this.COOKIE_NAME);
        if (!cookieValue) {
            return [];
        }
        
        try {
            // Decode and parse JSON
            const decoded = decodeURIComponent(cookieValue);
            const properties = JSON.parse(decoded);
            
            // Validate array
            if (Array.isArray(properties)) {
                return properties;
            }
        } catch (e) {
            console.warn('Failed to parse property cookie:', e);
            this.clearCookie();
        }
        
        return [];
    },
    
    /**
     * Add a property to recent views
     * @param {Object} property - Property data {property_id, location, property_type, price_range}
     */
    addProperty(property) {
        if (!property || !property.property_id) {
            console.warn('Invalid property data');
            return;
        }
        
        // Validate required fields
        const safeProperty = {
            property_id: property.property_id,
            location: property.location || '',
            property_type: property.property_type || '',
            price_range: property.price_range || '',
            viewed_at: new Date().toISOString()
        };
        
        // Get current properties
        let properties = this.getRecentProperties();
        
        // Remove if already exists (to move to front)
        properties = properties.filter(p => p.property_id !== safeProperty.property_id);
        
        // Add new property to beginning
        properties.unshift(safeProperty);
        
        // Limit to max items
        if (properties.length > this.MAX_ITEMS) {
            properties = properties.slice(0, this.MAX_ITEMS);
        }
        
        // Save to cookie
        this.saveProperties(properties);
    },
    
    /**
     * Save properties array to cookie
     * @param {Array} properties 
     */
    saveProperties(properties) {
        try {
            const jsonString = JSON.stringify(properties);
            const encoded = encodeURIComponent(jsonString);
            this.setCookie(this.COOKIE_NAME, encoded, this.COOKIE_EXPIRY);
        } catch (e) {
            console.error('Failed to save property cookie:', e);
        }
    },
    
    /**
     * Clear the cookie
     */
    clearCookie() {
        this.setCookie(this.COOKIE_NAME, '', -1);
    },
    
    /**
     * Set a cookie
     * @param {string} name 
     * @param {string} value 
     * @param {number} days 
     */
    setCookie(name, value, days) {
        let expires = '';
        if (days) {
            const date = new Date();
            date.setTime(date.getTime() + (days * 24 * 60 * 60 * 1000));
            expires = '; expires=' + date.toUTCString();
        }
        
        // Secure settings
        const secure = window.location.protocol === 'https:' ? '; Secure' : '';
        document.cookie = name + '=' + (value || '') + expires + '; path=/; SameSite=Lax' + secure;
    },
    
    /**
     * Get a cookie value
     * @param {string} name 
     * @returns {string|null}
     */
    getCookie(name) {
        const nameEQ = name + '=';
        const ca = document.cookie.split(';');
        
        for (let i = 0; i < ca.length; i++) {
            let c = ca[i];
            while (c.charAt(0) === ' ') {
                c = c.substring(1, c.length);
            }
            if (c.indexOf(nameEQ) === 0) {
                return c.substring(nameEQ.length, c.length);
            }
        }
        
        return null;
    },
    
    /**
     * Get cookie size in bytes
     * @returns {number}
     */
    getCookieSize() {
        const cookie = this.getCookie(this.COOKIE_NAME);
        if (!cookie) return 0;
        return new Blob([cookie]).size;
    },
    
    /**
     * Check if cookie is within size limits
     * @returns {boolean}
     */
    isWithinSizeLimit() {
        const MAX_COOKIE_SIZE = 4000; // 4KB limit
        return this.getCookieSize() < MAX_COOKIE_SIZE;
    }
};

// Make available globally
window.PropertyCookie = PropertyCookie;