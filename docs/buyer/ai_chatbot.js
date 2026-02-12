import { getAuth } from "https://www.gstatic.com/firebasejs/12.4.0/firebase-auth.js";

// ============================================
// BACKEND URL MANAGEMENT - PURE ENVIRONMENT BASED
// ============================================

/**
 * Get the appropriate backend URL based on environment
 * - LOCAL: http://localhost:10000 (when hostname is localhost/127.0.0.1)
 * - PRODUCTION: https://bahai.onrender.com (everywhere else)
 */
const getBackendUrl = () => {
    const hostname = window.location.hostname;
    const port = window.location.port;
    
    // STRICT localhost detection - ONLY these exact conditions
    const isExplicitLocalhost = hostname === 'localhost' || hostname === '127.0.0.1';
    const isLocalIp = hostname.startsWith('192.168.') || hostname.startsWith('10.0.');
    const isEmptyHostname = hostname === '' && port !== '';
    
    // ONLY use local backend if we're ACTUALLY on localhost
    if (isExplicitLocalhost || isLocalIp || isEmptyHostname) {
        console.log("🚀 LOCAL ENVIRONMENT - Using local backend: http://localhost:10000");
        return "http://localhost:10000/api/chat";
    }
    
    // DEFAULT to production for everything else (Render, Netlify, Vercel, GitHub Pages, etc.)
    console.log("☁️ PRODUCTION ENVIRONMENT - Using Render backend: https://bahai.onrender.com");
    return "https://bahai.onrender.com/api/chat";
};

// ============================================
// PROMPT DEFINITIONS
// ============================================

// PHASE 1: Initial "Try these quick prompts"
const INITIAL_PROMPTS = [
    { 
        displayText: "Find apartments", 
        fullPrompt: "Find apartments in Batangas City", 
        emoji: "🏢", 
        id: "init1" 
    },
    { 
        displayText: "Find houses", 
        fullPrompt: "Find houses in Lipa City", 
        emoji: "🏠", 
        id: "init2" 
    },
    { 
        displayText: "About Batangas", 
        fullPrompt: "Tell me about Batangas City", 
        emoji: "ℹ️", 
        id: "init3" 
    },
    { 
        displayText: "Bank financing", 
        fullPrompt: "Properties that accept bank financing", 
        emoji: "💰", 
        id: "init4" 
    },
    { 
        displayText: "Find condos", 
        fullPrompt: "Find condos in Tanauan City", 
        emoji: "🏙️", 
        id: "init5" 
    }
];

// PHASE 2: All 10 quick prompts - 4 shown randomly
const ALL_QUICK_PROMPTS = [
    { 
        displayText: "Apartments in Batangas City", 
        fullPrompt: "Find apartments in Batangas City", 
        emoji: "🏢", 
        id: "q1" 
    },
    { 
        displayText: "Houses under 3M, 3 bedrooms", 
        fullPrompt: "Show me houses under 3M with 3 bedrooms", 
        emoji: "🏠", 
        id: "q2" 
    },
    { 
        displayText: "Family properties in Lipa", 
        fullPrompt: "Family properties in Lipa City", 
        emoji: "👨‍👩‍👧‍👦", 
        id: "q3" 
    },
    { 
        displayText: "Near hospitals in Tanauan", 
        fullPrompt: "Properties near hospitals in Tanauan City", 
        emoji: "🏥", 
        id: "q4" 
    },
    { 
        displayText: "Apartments with parking", 
        fullPrompt: "Apartments with parking in Batangas", 
        emoji: "🚗", 
        id: "q5" 
    },
    { 
        displayText: "Ready for students Batangas", 
        fullPrompt: "Properties ready for students in Batangas", 
        emoji: "🎓", 
        id: "q6" 
    },
    { 
        displayText: "Pag-IBIG financing", 
        fullPrompt: "Properties that accept Pag-IBIG financing", 
        emoji: "💰", 
        id: "q7" 
    },
    { 
        displayText: "Steps to buy condo", 
        fullPrompt: "What are the steps to buy a condo?", 
        emoji: "📋", 
        id: "q8" 
    },
    { 
        displayText: "About Nasugbu", 
        fullPrompt: "Tell me about Nasugbu", 
        emoji: "📍", 
        id: "q9" 
    },
    { 
        displayText: "For single professionals", 
        fullPrompt: "Properties for single professionals in Batangas", 
        emoji: "🎯", 
        id: "q10" 
    }
];

// ============================================
// MAIN CHATBOT INITIALIZATION
// ============================================

export function initChatbot() {
    console.log("🤖 AI Chatbot Initializing...");
    
    const chatMessages = document.getElementById('chatMessages');
    
    if (!chatMessages) {
        console.error("❌ Chat messages container not found!");
        return;
    }
    
    // Initialize prompt phase tracker
    window.chatbotPhase = {
        showInitialPrompts: true,
        initialPromptsUsed: false
    };
    
    // Ensure chat input area exists
    const chatContainer = chatMessages.closest('.chatbot-container');
    if (chatContainer) {
        let existingInput = chatContainer.querySelector('.chat-input');
        if (!existingInput) {
            const chatInputDiv = document.createElement('div');
            chatInputDiv.className = 'chat-input';
            chatInputDiv.id = 'chatInputContainer';
            chatInputDiv.innerHTML = `
                <input type="text" id="chatInput" 
                       placeholder="e.g. Find apartments in Batangas City..." />
                <button id="sendChatBtn"><i class="fas fa-paper-plane"></i> Send</button>
                <button id="voiceInputBtn" class="voice-btn"><i class="fas fa-microphone"></i></button>
            `;
            chatContainer.appendChild(chatInputDiv);
        }
    }
    
    // Log backend info
    const backendUrl = getBackendUrl();
    console.log(`📍 Backend: ${backendUrl.includes('localhost') ? 'LOCAL (http://localhost:10000)' : 'PRODUCTION (Render)'}`);
    
    // Show welcome message on first load
    showWelcomeMessage();
    
    // Attach event listeners and add INITIAL prompts
    setTimeout(() => {
        attachChatListeners();
        addInitialPrompts();
    }, 500);
    
    console.log("✅ AI Chatbot Initialized!");
}

// ============================================
// CHAT LISTENERS
// ============================================

function attachChatListeners() {
    const chatInput = document.getElementById('chatInput');
    const sendChatBtn = document.getElementById('sendChatBtn');
    const voiceInputBtn = document.getElementById('voiceInputBtn');
    
    if (!chatInput || !sendChatBtn) {
        console.warn("⚠️ Chat input elements not ready yet, will retry...");
        setTimeout(attachChatListeners, 500);
        return;
    }
    
    // Remove existing listeners by cloning
    if (chatInput.hasAttribute('data-listener-attached')) {
        const newChatInput = chatInput.cloneNode(true);
        const newSendBtn = sendChatBtn.cloneNode(true);
        chatInput.parentNode.replaceChild(newChatInput, chatInput);
        sendChatBtn.parentNode.replaceChild(newSendBtn, sendChatBtn);
        window.chatInput = newChatInput;
        window.sendChatBtn = newSendBtn;
    } else {
        window.chatInput = chatInput;
        window.sendChatBtn = sendChatBtn;
    }
    
    window.chatInput.setAttribute('data-listener-attached', 'true');
    window.sendChatBtn.setAttribute('data-listener-attached', 'true');
    
    // Send message on button click
    window.sendChatBtn.addEventListener('click', async () => {
        const message = window.chatInput.value.trim();
        if (message) {
            if (window.chatbotPhase?.showInitialPrompts) {
                window.chatbotPhase.showInitialPrompts = false;
                window.chatbotPhase.initialPromptsUsed = true;
            }
            await processChatMessage(message);
            window.chatInput.value = '';
        }
    });
    
    // Send message on Enter key
    window.chatInput.addEventListener('keypress', async (e) => {
        if (e.key === 'Enter' && !e.shiftKey) {
            e.preventDefault();
            const message = window.chatInput.value.trim();
            if (message) {
                if (window.chatbotPhase?.showInitialPrompts) {
                    window.chatbotPhase.showInitialPrompts = false;
                    window.chatbotPhase.initialPromptsUsed = true;
                }
                await processChatMessage(message);
                window.chatInput.value = '';
            }
        }
    });
    
    // Voice input button
    if (voiceInputBtn) {
        const newVoiceBtn = voiceInputBtn.cloneNode(true);
        voiceInputBtn.parentNode.replaceChild(newVoiceBtn, voiceInputBtn);
        newVoiceBtn.addEventListener('click', () => {
            alert("🎤 Voice input requires Web Speech API. Please type your question instead.");
        });
    }
}

// ============================================
// PROCESS CHAT MESSAGES - CLEAN SINGLE ATTEMPT
// ============================================

export async function processChatMessage(userMessage) {
    const chatInput = document.getElementById('chatInput');
    const sendChatBtn = document.getElementById('sendChatBtn');
    
    try {
        const auth = getAuth();
        const currentUser = auth.currentUser;
        
        // Add user message to chat
        addMessageToChat(userMessage, 'user');
        
        // Disable input while processing
        if (chatInput) chatInput.disabled = true;
        if (sendChatBtn) {
            sendChatBtn.disabled = true;
            sendChatBtn.innerHTML = '<i class="fas fa-spinner fa-spin"></i> Sending...';
        }
        
        // Show typing indicator
        const typingMessage = addTypingIndicator();
        
        // Prepare request to backend
        const requestData = {
            query: userMessage,
            user_id: currentUser ? currentUser.uid : 'anonymous'
        };
        
        // Get URL based on environment
        const backendUrl = getBackendUrl();
        const isLocal = backendUrl.includes('localhost');
        
        console.log("🌐 Connecting to:", backendUrl);
        
        // Single attempt with appropriate timeout
        const controller = new AbortController();
        const timeoutMs = isLocal ? 8000 : 30000; // 8s local, 30s production (for cold starts)
        const timeoutId = setTimeout(() => controller.abort(), timeoutMs);
        
        const response = await fetch(backendUrl, {
            method: 'POST',
            headers: {
                'Content-Type': 'application/json',
                'Accept': 'application/json'
            },
            body: JSON.stringify(requestData),
            signal: controller.signal,
            mode: 'cors'
        });
        
        clearTimeout(timeoutId);
        
        if (!response.ok) {
            throw new Error(`HTTP ${response.status}: ${response.statusText}`);
        }
        
        const text = await response.text();
        
        // Clean the response
        const cleanText = text.replace(/undefined/g, 'null');
        let data;
        
        try {
            data = JSON.parse(cleanText);
        } catch (parseError) {
            console.error("❌ JSON parse error:", parseError);
            data = {
                success: false,
                response: "I received your query but had trouble processing the response. Please try again.",
                properties: [],
                intent: 'error'
            };
        }
        
        // Remove typing indicator
        if (typingMessage?.parentNode) {
            typingMessage.remove();
        }
        
        // Display response
        const responseText = data.response || data.message || 
                           "I received your message but couldn't process it properly.";
        addMessageToChat(responseText, 'bot');
        
        // If properties were found, display them
        if (data?.properties?.length > 0) {
            displayPropertiesInChat(data.properties);
        }
        
        // Show quick prompts
        setTimeout(() => {
            if (window.chatbotPhase?.showInitialPrompts) {
                window.chatbotPhase.showInitialPrompts = false;
                window.chatbotPhase.initialPromptsUsed = true;
            }
            addQuickPrompts();
        }, 500);
        
        // Log interaction (non-critical)
        try {
            await logChatInteraction(userMessage, data, currentUser);
        } catch (logError) {
            // Silently fail - logging is non-critical
        }
        
    } catch (error) {
        console.error('💥 Chat error:', error);
        
        // Remove typing indicator
        document.querySelector('.typing-indicator')?.remove();
        
        // Show user-friendly error based on environment
        const isLocal = window.location.hostname === 'localhost' || window.location.hostname === '127.0.0.1';
        
        let errorMessage;
        if (isLocal) {
            errorMessage = "❌ **Cannot connect to local backend**\n\n" +
                          "**To fix this:**\n" +
                          "1️⃣ Open terminal in backend folder\n" +
                          "2️⃣ Run: `python chatbot_backend.py`\n" +
                          "3️⃣ Verify: http://localhost:10000/api/health\n\n" +
                          "**You can still:**\n" +
                          "• Use the search filters above 🔍\n" +
                          "• Browse property categories 🏠\n" +
                          "• Contact brokers directly 💬";
        } else {
            errorMessage = "⏳ **AI service is starting up...**\n\n" +
                          "This can take 30-60 seconds on free hosting.\n\n" +
                          "**Please try again in a moment.**\n\n" +
                          "**You can still:**\n" +
                          "• Use the search filters above 🔍\n" +
                          "• Browse property categories 🏠\n" +
                          "• Contact brokers directly 💬";
        }
        
        addMessageToChat(errorMessage, 'bot');
        setTimeout(addQuickPrompts, 500);
        
    } finally {
        // Re-enable input
        if (chatInput) {
            chatInput.disabled = false;
            chatInput.focus();
        }
        if (sendChatBtn) {
            sendChatBtn.disabled = false;
            sendChatBtn.innerHTML = '<i class="fas fa-paper-plane"></i> Send';
        }
    }
}

// ============================================
// UI HELPER FUNCTIONS
// ============================================

function addMessageToChat(message, sender) {
    const chatMessages = document.getElementById('chatMessages');
    if (!chatMessages) return;
    
    const messageDiv = document.createElement('div');
    messageDiv.className = `message ${sender}`;
    
    const avatar = sender === 'user' ? '👤' : '🤖';
    
    // Format message
    let formattedMessage = message
        .replace(/\n/g, '<br>')
        .replace(/\*\*(.*?)\*\*/g, '<strong>$1</strong>')
        .replace(/\*(.*?)\*/g, '<em>$1</em>')
        .replace(/•/g, '•');
    
    messageDiv.innerHTML = `
        <div class="avatar">${avatar}</div>
        <div class="content">
            ${formattedMessage}
        </div>
    `;
    
    chatMessages.appendChild(messageDiv);
    chatMessages.scrollTop = chatMessages.scrollHeight;
}

function addTypingIndicator() {
    const chatMessages = document.getElementById('chatMessages');
    if (!chatMessages) return null;
    
    const typingDiv = document.createElement('div');
    typingDiv.className = 'message bot typing-indicator';
    typingDiv.innerHTML = `
        <div class="avatar">🤖</div>
        <div class="content">
            <div class="typing">
                <span></span>
                <span></span>
                <span></span>
            </div>
            <p style="font-size: 12px; color: #666; margin-top: 8px; margin-bottom: 0;">
                <i class="fas fa-clock"></i> Processing your request...
            </p>
        </div>
    `;
    chatMessages.appendChild(typingDiv);
    chatMessages.scrollTop = chatMessages.scrollHeight;
    return typingDiv;
}

function getDisplayPrice(property) {
    if (!property) return 'Price on inquiry';
    
    if (property.monthlyRent) {
        return `₱${Number(property.monthlyRent).toLocaleString()}/month`;
    } else if (property.annualRent) {
        return `₱${Number(property.annualRent).toLocaleString()}/year`;
    } else if (property.salePrice) {
        return `₱${Number(property.salePrice).toLocaleString()}`;
    } else if (property.pricing) {
        return `₱${Number(property.pricing).toLocaleString()}`;
    }
    return 'Price on inquiry';
}

function displayPropertiesInChat(properties) {
    const chatMessages = document.getElementById('chatMessages');
    if (!chatMessages || !properties?.length) return;
    
    const propertiesDiv = document.createElement('div');
    propertiesDiv.className = 'chat-properties-container';
    
    let html = `
        <div style="margin-bottom: 12px; font-weight: 600; color: var(--text-dark);">
            🏠 Found ${properties.length} matching propert${properties.length > 1 ? 'ies' : 'y'}:
        </div>
        <div class="properties-grid">
    `;
    
    // Show max 3 properties in chat
    properties.slice(0, 3).forEach(prop => {
        const price = getDisplayPrice(prop);
        const bedrooms = prop.bedrooms || 'N/A';
        const area = prop.floorArea || prop.totalArea || 'N/A';
        const title = prop.title || 'Untitled Property';
        const location = prop.location || prop.city || prop.address || 'Location not specified';
        const photo = prop.photos?.[0] || prop.imageUrls?.[0] || 
            `https://via.placeholder.com/300x200/0b2e52/white?text=${encodeURIComponent(title.substring(0, 20))}`;
        
        html += `
            <div class="property-card-chat">
                <div class="property-image">
                    <img src="${photo}" alt="${title}" loading="lazy" onerror="this.src='https://via.placeholder.com/300x200/0b2e52/white?text=Property'">
                </div>
                <div class="property-info">
                    <h4>${title.length > 40 ? title.substring(0, 40) + '...' : title}</h4>
                    <p class="location">📍 ${location.length > 30 ? location.substring(0, 30) + '...' : location}</p>
                    <div class="details">
                        ${bedrooms !== 'N/A' ? `<span>🛏️ ${bedrooms} ${bedrooms === 'Studio' ? '' : 'beds'}</span>` : ''}
                        ${area && area !== 'N/A' ? `<span>📐 ${area} sqm</span>` : ''}
                    </div>
                    <p class="price">${price}</p>
                    <a href="property_details.html?id=${prop.id || prop.property_id || ''}" 
                       target="_blank" 
                       class="view-btn">
                        View Details <i class="fas fa-arrow-right"></i>
                    </a>
                </div>
            </div>
        `;
    });
    
    html += '</div>';
    
    if (properties.length > 3) {
        html += `
            <p style="text-align: center; margin-top: 15px; margin-bottom: 5px;">
                <a href="search_results.html" 
                   style="color: #0b6e4f; text-decoration: underline; font-weight: 600; display: inline-flex; align-items: center; gap: 5px;">
                    🔍 View all ${properties.length} properties <i class="fas fa-arrow-right"></i>
                </a>
            </p>
        `;
    }
    
    propertiesDiv.innerHTML = html;
    chatMessages.appendChild(propertiesDiv);
    chatMessages.scrollTop = chatMessages.scrollHeight;
}

async function logChatInteraction(query, response, user) {
    if (!user) return;
    
    try {
        const { getFirestore, collection, addDoc } = await import("https://www.gstatic.com/firebasejs/12.4.0/firebase-firestore.js");
        const { getApp } = await import("https://www.gstatic.com/firebasejs/12.4.0/firebase-app.js");
        
        const app = getApp();
        const db = getFirestore(app);
        
        await addDoc(collection(db, 'chatbot_logs'), {
            userId: user.uid,
            query: query,
            intent: response?.intent || 'unknown',
            entities: response?.entities || {},
            response: response?.response?.substring(0, 200) || '',
            propertiesFound: response?.properties_found || 0,
            timestamp: new Date(),
            modelUsed: response?.model_used || 'unknown',
            confidence: response?.confidence || 0,
            success: response?.success || false
        });
    } catch (error) {
        // Silently fail - logging is non-critical
    }
}

// ============================================
// PHASE 1: INITIAL PROMPTS
// ============================================

function addInitialPrompts() {
    const existingPrompts = document.querySelector('.demo-prompts-container');
    if (existingPrompts) existingPrompts.remove();
    
    const chatMessages = document.getElementById('chatMessages');
    if (!chatMessages) return;
    
    if (!window.chatbotPhase) {
        window.chatbotPhase = {
            showInitialPrompts: true,
            initialPromptsUsed: false
        };
    }
    
    if (!window.chatbotPhase.showInitialPrompts) {
        addQuickPrompts();
        return;
    }
    
    const demoSection = document.createElement('div');
    demoSection.className = 'demo-prompts-container initial-prompts';
    demoSection.innerHTML = `
        <div class="demo-prompts-title">
            <i class="fas fa-lightbulb" style="color: #667eea;"></i> Try these quick prompts
        </div>
        <div class="demo-prompts-buttons" style="grid-template-columns: repeat(3, 1fr);">
            ${INITIAL_PROMPTS.map(prompt => `
                <button class="demo-prompt-btn initial-prompt-btn" 
                        data-full-prompt="${prompt.fullPrompt}" 
                        data-id="${prompt.id}"
                        title="${prompt.fullPrompt}">
                    <span class="prompt-icon">${prompt.emoji}</span>
                    <span class="prompt-text">${prompt.displayText}</span>
                </button>
            `).join('')}
        </div>
    `;
    
    chatMessages.parentNode.insertBefore(demoSection, chatMessages.nextSibling);
    
    setTimeout(() => {
        document.querySelectorAll('.initial-prompt-btn').forEach(btn => {
            btn.addEventListener('click', function(e) {
                e.preventDefault();
                e.stopPropagation();
                
                const fullPrompt = this.getAttribute('data-full-prompt');
                const chatInput = document.getElementById('chatInput');
                
                if (chatInput && fullPrompt) {
                    chatInput.value = fullPrompt;
                    chatInput.focus();
                    
                    this.style.transform = 'scale(0.95)';
                    this.style.boxShadow = '0 0 0 2px rgba(212, 175, 55, 0.3)';
                    setTimeout(() => {
                        this.style.transform = '';
                        this.style.boxShadow = '';
                    }, 200);
                }
            });
        });
    }, 100);
}

// ============================================
// PHASE 2: QUICK PROMPTS - 4 RANDOM
// ============================================

function addQuickPrompts() {
    const existingPrompts = document.querySelector('.demo-prompts-container');
    if (existingPrompts) existingPrompts.remove();
    
    const chatMessages = document.getElementById('chatMessages');
    if (!chatMessages) return;
    
    // Shuffle and select 4 random prompts
    const shuffled = [...ALL_QUICK_PROMPTS].sort(() => Math.random() - 0.5);
    const selectedPrompts = shuffled.slice(0, 4);
    
    const demoSection = document.createElement('div');
    demoSection.className = 'demo-prompts-container quick-prompts';
    demoSection.innerHTML = `
        <div class="demo-prompts-title">
            <i class="fas fa-bolt" style="color: #667eea;"></i> Quick Prompts
            <span class="prompt-count-badge">
                <i class="fas fa-sync-alt"></i> 4 random questions
            </span>
        </div>
        <div class="demo-prompts-buttons" style="grid-template-columns: repeat(2, 1fr);">
            ${selectedPrompts.map(prompt => `
                <button class="demo-prompt-btn quick-prompt-btn" 
                        data-full-prompt="${prompt.fullPrompt}" 
                        data-id="${prompt.id}"
                        title="${prompt.fullPrompt}">
                    <span class="prompt-icon">${prompt.emoji}</span>
                    <span class="prompt-text">${prompt.displayText}</span>
                </button>
            `).join('')}
        </div>
        <div class="prompts-footer">
            <div class="prompts-info">
                <i class="fas fa-info-circle"></i> New set every time
            </div>
            <button id="refreshPrompts" class="shuffle-button">
                <i class="fas fa-redo-alt"></i> New set
            </button>
        </div>
    `;
    
    chatMessages.parentNode.insertBefore(demoSection, chatMessages.nextSibling);
    
    setTimeout(() => {
        document.querySelectorAll('.quick-prompt-btn').forEach(btn => {
            btn.addEventListener('click', function(e) {
                e.preventDefault();
                e.stopPropagation();
                
                const fullPrompt = this.getAttribute('data-full-prompt');
                const chatInput = document.getElementById('chatInput');
                
                if (chatInput && fullPrompt) {
                    chatInput.value = fullPrompt;
                    chatInput.focus();
                    
                    this.style.transform = 'scale(0.95)';
                    this.style.boxShadow = '0 0 0 2px rgba(212, 175, 55, 0.3)';
                    setTimeout(() => {
                        this.style.transform = '';
                        this.style.boxShadow = '';
                    }, 200);
                }
            });
        });
        
        const refreshBtn = document.getElementById('refreshPrompts');
        if (refreshBtn) {
            const newRefreshBtn = refreshBtn.cloneNode(true);
            refreshBtn.parentNode.replaceChild(newRefreshBtn, refreshBtn);
            
            newRefreshBtn.addEventListener('click', (e) => {
                e.preventDefault();
                e.stopPropagation();
                addQuickPrompts();
                
                newRefreshBtn.innerHTML = '<i class="fas fa-spinner fa-spin"></i> Loading...';
                setTimeout(() => {
                    newRefreshBtn.innerHTML = '<i class="fas fa-redo-alt"></i> New set';
                }, 500);
            });
        }
    }, 100);
}

// ============================================
// WELCOME MESSAGE
// ============================================

function showWelcomeMessage() {
    const chatMessages = document.getElementById('chatMessages');
    if (!chatMessages || chatMessages.children.length > 0) return;
    
    const isLocal = window.location.hostname === 'localhost' || window.location.hostname === '127.0.0.1';
    const backendUrl = getBackendUrl();
    
    const welcomeMessage = `
        <div class="welcome-message">
            <div style="display: flex; align-items: center; gap: 12px; margin-bottom: 15px;">
                <div style="width: 50px; height: 50px; border-radius: 50%; background: linear-gradient(135deg, #667eea 0%, #764ba2 100%); 
                    display: flex; align-items: center; justify-content: center; font-size: 24px; box-shadow: 0 4px 12px rgba(102, 126, 234, 0.2);">
                    🤖
                </div>
                <div>
                    <h4 style="margin: 0; color: var(--text-dark); font-size: 18px;">AI Property Assistant</h4>
                    <p style="margin: 0; font-size: 12px; color: #666;">Specialized in Batangas Properties</p>
                </div>
            </div>
            <p style="color: var(--text-dark); margin-bottom: 15px; line-height: 1.5;">
                Hello! I'm your AI assistant for Batangas real estate. 
                ${isLocal ? '🖥️ Local development mode' : '☁️ Production mode'}
            </p>
            ${!isLocal ? `
                <p style="color: #856404; background-color: #fff3cd; border: 1px solid #ffeeba; padding: 12px; border-radius: 8px; font-size: 12px; margin-top: 15px;">
                    <i class="fas fa-clock"></i> <strong>First-time startup:</strong> The AI service may take 30-60 seconds to respond initially (free hosting).
                </p>
            ` : `
                <p style="color: #004085; background-color: #cce5ff; border: 1px solid #b8daff; padding: 12px; border-radius: 8px; font-size: 12px; margin-top: 15px;">
                    <i class="fas fa-code"></i> <strong>Local Backend:</strong> ${backendUrl}
                </p>
            `}
        </div>
    `;
    
    const welcomeDiv = document.createElement('div');
    welcomeDiv.className = 'message bot';
    welcomeDiv.innerHTML = `
        <div class="avatar">🤖</div>
        <div class="content" style="background: white; padding: 0; overflow: hidden;">
            ${welcomeMessage}
        </div>
    `;
    chatMessages.appendChild(welcomeDiv);
}

// ============================================
// KEEP BACKEND ALIVE - PRODUCTION ONLY
// ============================================

function keepBackendAlive() {
    // ONLY run in production (Render, etc.)
    const isProduction = !(window.location.hostname === 'localhost' || 
                          window.location.hostname === '127.0.0.1');
    
    if (!isProduction) {
        console.log("⏸️ Local development - keep-alive disabled");
        return;
    }
    
    console.log("⏰ Setting up keep-alive for production backend...");
    
    async function pingBackend() {
        try {
            const controller = new AbortController();
            const timeoutId = setTimeout(() => controller.abort(), 10000);
            
            const response = await fetch('https://bahai.onrender.com/api/health', { 
                method: 'GET',
                mode: 'cors',
                cache: 'no-cache',
                headers: { 'Content-Type': 'application/json' },
                signal: controller.signal
            });
            
            clearTimeout(timeoutId);
            
            if (response.ok) {
                console.log('✅ Production backend keep-alive successful');
            }
        } catch (err) {
            // Silent fail in production - don't spam console
        }
    }
    
    // Initial ping after 5 seconds
    setTimeout(pingBackend, 5000);
    
    // Ping every 5 minutes
    setInterval(pingBackend, 5 * 60 * 1000);
}

// ============================================
// STYLES
// ============================================

const chatbotStyles = document.createElement('style');
chatbotStyles.id = 'chatbot-styles';
chatbotStyles.textContent = `
    /* Chat messages styling */
    .chat-messages {
        height: 420px;
        overflow-y: auto;
        padding: 15px;
        background: #f8f9fa;
        border-radius: 12px;
        margin-bottom: 15px;
        border: 1px solid #e9ecef;
        scroll-behavior: smooth;
    }
    
    .message {
        display: flex;
        margin-bottom: 15px;
        animation: fadeIn 0.3s ease;
    }
    
    .message.user {
        flex-direction: row-reverse;
    }
    
    .message .avatar {
        width: 40px;
        height: 40px;
        border-radius: 50%;
        background: linear-gradient(135deg, #667eea 0%, #764ba2 100%);
        display: flex;
        align-items: center;
        justify-content: center;
        font-size: 20px;
        margin: 0 10px;
        flex-shrink: 0;
        color: white;
        box-shadow: 0 2px 8px rgba(102, 126, 234, 0.2);
    }
    
    .message.user .avatar {
        background: linear-gradient(135deg, #0b2e52 0%, #1e3a5f 100%);
    }
    
    .message .content {
        max-width: 70%;
        padding: 12px 16px;
        border-radius: 18px;
        background: white;
        box-shadow: 0 2px 8px rgba(0,0,0,0.05);
        line-height: 1.5;
        font-size: 14px;
    }
    
    .message.user .content {
        background: linear-gradient(135deg, #0b2e52 0%, #1e3a5f 100%);
        color: white;
    }
    
    .message.bot .content {
        background: white;
        color: #2c3e50;
        border: 1px solid rgba(102, 126, 234, 0.1);
    }
    
    /* Chat input area */
    .chat-input {
        display: flex;
        gap: 10px;
        margin-top: 15px;
    }
    
    .chat-input input {
        flex: 1;
        padding: 12px 16px;
        border: 2px solid #e9ecef;
        border-radius: 10px;
        font-size: 15px;
        transition: all 0.3s;
        font-family: inherit;
    }
    
    .chat-input input:focus {
        outline: none;
        border-color: #667eea;
        box-shadow: 0 0 0 3px rgba(102, 126, 234, 0.1);
    }
    
    .chat-input input:disabled {
        background: #f1f3f5;
        cursor: not-allowed;
        opacity: 0.7;
    }
    
    .chat-input button {
        padding: 12px 24px;
        background: linear-gradient(135deg, #667eea 0%, #764ba2 100%);
        color: white;
        border: none;
        border-radius: 10px;
        cursor: pointer;
        font-weight: 600;
        transition: all 0.3s;
        font-family: inherit;
        display: flex;
        align-items: center;
        gap: 8px;
        box-shadow: 0 2px 8px rgba(102, 126, 234, 0.2);
    }
    
    .chat-input button:hover:not(:disabled) {
        transform: translateY(-2px);
        box-shadow: 0 4px 12px rgba(102, 126, 234, 0.3);
    }
    
    .chat-input button:disabled {
        opacity: 0.7;
        cursor: not-allowed;
        transform: none;
        box-shadow: none;
    }
    
    .chat-input .voice-btn {
        padding: 12px;
        background: white;
        border: 2px solid #e9ecef;
        color: #666;
        box-shadow: none;
    }
    
    .chat-input .voice-btn:hover {
        background: #f8f9fa;
        border-color: #667eea;
        color: #667eea;
    }
    
    /* Property cards in chat */
    .chat-properties-container {
        margin: 15px 0;
        padding: 15px;
        background: white;
        border-radius: 12px;
        border: 1px solid #e9ecef;
        animation: slideIn 0.5s ease;
    }
    
    .properties-grid {
        display: grid;
        grid-template-columns: repeat(auto-fill, minmax(260px, 1fr));
        gap: 15px;
        margin-top: 10px;
    }
    
    .property-card-chat {
        background: white;
        border-radius: 10px;
        overflow: hidden;
        box-shadow: 0 2px 8px rgba(0,0,0,0.05);
        transition: transform 0.2s, box-shadow 0.2s;
        border: 1px solid #e9ecef;
    }
    
    .property-card-chat:hover {
        transform: translateY(-3px);
        box-shadow: 0 6px 16px rgba(0,0,0,0.1);
    }
    
    .property-card-chat .property-image {
        height: 160px;
        overflow: hidden;
        background: #f8f9fa;
    }
    
    .property-card-chat .property-image img {
        width: 100%;
        height: 100%;
        object-fit: cover;
        transition: transform 0.3s;
    }
    
    .property-card-chat:hover .property-image img {
        transform: scale(1.05);
    }
    
    .property-card-chat .property-info {
        padding: 15px;
    }
    
    .property-card-chat h4 {
        margin: 0 0 8px 0;
        font-size: 16px;
        color: #2c3e50;
        line-height: 1.3;
        font-weight: 600;
    }
    
    .property-card-chat .location {
        font-size: 13px;
        color: #666;
        margin: 0 0 10px 0;
        line-height: 1.4;
    }
    
    .property-card-chat .details {
        display: flex;
        gap: 15px;
        margin: 10px 0;
        font-size: 13px;
        color: #666;
    }
    
    .property-card-chat .price {
        font-weight: 700;
        color: #0b6e4f;
        margin: 12px 0;
        font-size: 17px;
    }
    
    .property-card-chat .view-btn {
        display: inline-flex;
        align-items: center;
        justify-content: center;
        gap: 5px;
        background: linear-gradient(135deg, #0b6e4f 0%, #0d8a63 100%);
        color: white;
        padding: 8px 15px;
        border-radius: 6px;
        text-decoration: none;
        font-size: 14px;
        font-weight: 500;
        transition: all 0.3s;
        width: 100%;
        box-sizing: border-box;
        border: none;
        cursor: pointer;
    }
    
    .property-card-chat .view-btn:hover {
        background: #094d38;
        transform: translateY(-1px);
        box-shadow: 0 2px 8px rgba(11, 110, 79, 0.3);
    }
    
    /* Typing indicator */
    .typing-indicator .typing {
        display: flex;
        gap: 5px;
        margin-bottom: 5px;
    }
    
    .typing-indicator .typing span {
        width: 8px;
        height: 8px;
        background: #a0a0a0;
        border-radius: 50%;
        animation: typing 1.4s infinite;
    }
    
    .typing-indicator .typing span:nth-child(2) {
        animation-delay: 0.2s;
    }
    
    .typing-indicator .typing span:nth-child(3) {
        animation-delay: 0.4s;
    }
    
    /* Welcome message styling */
    .welcome-message {
        background: linear-gradient(135deg, rgba(102, 126, 234, 0.03) 0%, rgba(118, 75, 162, 0.03) 100%);
        padding: 20px;
    }
    
    .welcome-message h4 {
        color: #2c3e50 !important;
        font-size: 18px;
        margin-bottom: 5px !important;
    }
    
    .welcome-message p {
        line-height: 1.6;
        color: #4a5568;
    }
    
    /* DEMO PROMPTS */
    .demo-prompts-container {
        margin-top: 15px;
        padding: 15px;
        background: white;
        border-radius: 10px;
        border: 1px solid #e9ecef;
        animation: fadeIn 0.3s ease;
        box-shadow: 0 2px 8px rgba(0,0,0,0.02);
    }
    
    .demo-prompts-title {
        font-size: 14px;
        color: #2c3e50;
        font-weight: 600;
        margin-bottom: 12px;
        display: flex;
        align-items: center;
        gap: 8px;
    }
    
    .prompt-count-badge {
        font-size: 11px;
        background: rgba(102, 126, 234, 0.1);
        padding: 3px 10px;
        border-radius: 20px;
        font-weight: 500;
        color: #667eea;
        display: inline-flex;
        align-items: center;
        gap: 5px;
    }
    
    .demo-prompts-buttons {
        display: grid;
        gap: 8px;
        margin-bottom: 12px;
    }
    
    .demo-prompt-btn {
        background: #f8f9fa;
        border: 1px solid #e9ecef;
        border-radius: 8px;
        padding: 10px 12px;
        cursor: pointer;
        text-align: left;
        transition: all 0.2s;
        display: flex;
        align-items: center;
        gap: 10px;
        font-size: 13px;
        color: #2c3e50;
        overflow: hidden;
        text-overflow: ellipsis;
        white-space: nowrap;
        height: 44px;
    }
    
    .demo-prompt-btn:hover {
        background: white;
        border-color: rgba(102, 126, 234, 0.3);
        box-shadow: 0 2px 8px rgba(102, 126, 234, 0.1);
    }
    
    .demo-prompt-btn .prompt-icon {
        font-size: 16px;
        flex-shrink: 0;
        width: 22px;
        text-align: center;
    }
    
    .demo-prompt-btn .prompt-text {
        overflow: hidden;
        text-overflow: ellipsis;
        white-space: nowrap;
        flex: 1;
    }
    
    .prompts-footer {
        display: flex;
        justify-content: space-between;
        align-items: center;
        margin-top: 10px;
        padding-top: 12px;
        border-top: 1px solid #e9ecef;
    }
    
    .prompts-info {
        font-size: 11px;
        color: #888;
        display: flex;
        align-items: center;
        gap: 5px;
    }
    
    .shuffle-button {
        font-size: 12px;
        background: rgba(102, 126, 234, 0.08);
        border: 1px solid rgba(102, 126, 234, 0.2);
        color: #667eea;
        cursor: pointer;
        padding: 6px 14px;
        border-radius: 20px;
        font-weight: 500;
        display: flex;
        align-items: center;
        gap: 6px;
        transition: all 0.2s;
    }
    
    .shuffle-button:hover {
        background: rgba(102, 126, 234, 0.15);
        border-color: rgba(102, 126, 234, 0.4);
    }
    
    /* Animations */
    @keyframes typing {
        0%, 60%, 100% {
            transform: translateY(0);
            background: #a0a0a0;
        }
        30% {
            transform: translateY(-5px);
            background: #667eea;
        }
    }
    
    @keyframes fadeIn {
        from { opacity: 0; transform: translateY(10px); }
        to { opacity: 1; transform: translateY(0); }
    }
    
    @keyframes slideIn {
        from { opacity: 0; transform: translateY(20px); }
        to { opacity: 1; transform: translateY(0); }
    }
    
    /* Scrollbar styling */
    .chat-messages::-webkit-scrollbar {
        width: 6px;
    }
    
    .chat-messages::-webkit-scrollbar-track {
        background: #f1f1f1;
        border-radius: 3px;
    }
    
    .chat-messages::-webkit-scrollbar-thumb {
        background: #c1c1c1;
        border-radius: 3px;
    }
    
    .chat-messages::-webkit-scrollbar-thumb:hover {
        background: #a8a8a8;
    }
    
    /* Responsive adjustments */
    @media (max-width: 768px) {
        .message .content {
            max-width: 85%;
        }
        
        .properties-grid {
            grid-template-columns: 1fr;
        }
        
        .demo-prompts-buttons {
            grid-template-columns: 1fr !important;
        }
    }
`;

// ============================================
// INITIALIZE
// ============================================

// Add styles to document
if (!document.querySelector('#chatbot-styles')) {
    document.head.appendChild(chatbotStyles);
}

// Start keep-alive (automatically only runs in production)
keepBackendAlive();

// Make functions available globally
window.processChatMessage = processChatMessage;
window.initChatbot = initChatbot;

console.log("🚀 AI Chatbot Script Loaded Successfully!");
console.log(`🌍 Environment: ${window.location.hostname.includes('localhost') ? 'LOCAL' : 'PRODUCTION'}`);
console.log(`🔌 Backend: ${getBackendUrl().includes('localhost') ? 'Localhost:10000' : 'Render.com'}`);
console.log(`⏱️  Timeout: ${getBackendUrl().includes('localhost') ? '8s' : '30s'} (for cold starts)`);