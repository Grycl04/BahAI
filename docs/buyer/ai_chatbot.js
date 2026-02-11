import { getAuth } from "https://www.gstatic.com/firebasejs/12.4.0/firebase-auth.js";

// Function to determine the correct backend URL based on environment
const getBackendUrl = () => {
    const hostname = window.location.hostname;
    const port = window.location.port;
    
    console.log("🌐 Detected hostname:", hostname, "Port:", port);
    
    // Check if we're on your frontend domain
    if (hostname.includes('render.com') || 
        hostname.includes('bahai-frontend') ||
        hostname.includes('bahai')) {
        console.log("☁️ Using PRODUCTION backend (Render)");
        return "https://bahai.onrender.com/api/chat";
    } else {
        // For local development
        console.log("🚀 Using LOCAL backend (localhost:5000)");
        return "http://localhost:5000/api/chat";
    }
};

// Initialize chatbot in your dashboard
export function initChatbot() {
    console.log("🤖 AI Chatbot Initializing...");
    
    const chatMessages = document.getElementById('chatMessages');
    
    if (!chatMessages) {
        console.error("❌ Chat messages container not found!");
        return;
    }
    
    // FIX: Ensure chat input area exists even before prompts are clicked
    const chatContainer = chatMessages.closest('.chatbot-container');
    if (chatContainer) {
        // Check if chat input already exists
        let existingInput = chatContainer.querySelector('.chat-input');
        if (!existingInput) {
            console.log("🛠️ Creating chat input area...");
            // Create the chat input area
            const chatInputDiv = document.createElement('div');
            chatInputDiv.className = 'chat-input';
            chatInputDiv.id = 'chatInputContainer';
            chatInputDiv.style.display = 'flex';
            chatInputDiv.innerHTML = `
                <input type="text" id="chatInput" 
                       placeholder="e.g. Family home with yard, under 4M, near Lipa City..." />
                <button id="sendChatBtn"><i class="fas fa-paper-plane"></i> Send</button>
                <button id="voiceInputBtn" class="voice-btn"><i class="fas fa-microphone"></i></button>
            `;
            chatContainer.appendChild(chatInputDiv);
        } else {
            console.log("✅ Chat input area already exists");
        }
    }
    
    // Show backend info for debugging
    const backendUrl = getBackendUrl();
    console.log("🌐 Backend URL:", backendUrl);
    
    // Show welcome message on first load
    showWelcomeMessage();
    
    // FIX: Attach event listeners
    setTimeout(() => {
        attachChatListeners();
        // Add demo prompts
        addDemoPrompts();
    }, 500);
    
    console.log("✅ AI Chatbot Initialized!");
}

// Create a separate function for attaching listeners
function attachChatListeners() {
    const chatInput = document.getElementById('chatInput');
    const sendChatBtn = document.getElementById('sendChatBtn');
    const voiceInputBtn = document.getElementById('voiceInputBtn');
    
    if (!chatInput || !sendChatBtn) {
        console.warn("⚠️ Chat input elements not ready yet, will retry...");
        setTimeout(attachChatListeners, 500);
        return;
    }
    
    console.log("🔗 Attaching chat listeners...");
    
    // Remove existing listeners by cloning elements if needed
    if (chatInput.hasAttribute('data-listener-attached')) {
        const newChatInput = chatInput.cloneNode(true);
        const newSendBtn = sendChatBtn.cloneNode(true);
        
        chatInput.parentNode.replaceChild(newChatInput, chatInput);
        sendChatBtn.parentNode.replaceChild(newSendBtn, sendChatBtn);
        
        // Update references
        window.chatInput = newChatInput;
        window.sendChatBtn = newSendBtn;
    } else {
        window.chatInput = chatInput;
        window.sendChatBtn = sendChatBtn;
    }
    
    // Mark as having listeners attached
    window.chatInput.setAttribute('data-listener-attached', 'true');
    window.sendChatBtn.setAttribute('data-listener-attached', 'true');
    
    // Send message on button click
    window.sendChatBtn.addEventListener('click', async () => {
        const message = window.chatInput.value.trim();
        if (message) {
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
                await processChatMessage(message);
                window.chatInput.value = '';
            }
        }
    });
    
    // Voice input button (optional)
    if (voiceInputBtn) {
        voiceInputBtn.addEventListener('click', () => {
            alert("Voice input would require additional setup with Web Speech API");
        });
    }
    
    console.log("🎯 Chat listeners attached successfully");
}

// Main function to process chat messages
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
        
        // Prepare request to Python backend
        const requestData = {
            query: userMessage,
            user_id: currentUser ? currentUser.uid : 'anonymous'
        };
        
        console.log("📤 Sending to backend:", requestData);
        
        let data;
        let backendUrl = getBackendUrl();
        
        try {
            // Call backend with timeout
            const controller = new AbortController();
            const timeoutId = setTimeout(() => controller.abort(), 30000); // 30 second timeout for Render
            
            console.log("🌐 Attempting to connect to:", backendUrl);
            
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
            console.log("📥 Raw response received:", text.substring(0, 200) + "...");
            
            // Clean the response
            const cleanText = text.replace(/undefined/g, 'null');
            try {
                data = JSON.parse(cleanText);
            } catch (parseError) {
                console.error("❌ JSON parse error:", parseError);
                // Create a fallback response
                data = {
                    success: false,
                    response: `I received your query: "${userMessage}", but there was an issue processing the response.`,
                    properties: [],
                    intent: 'error',
                    properties_found: 0
                };
            }
            
        } catch (fetchError) {
            console.error('🌐 Fetch error:', fetchError);
            
            // Remove typing indicator first
            if (typingMessage) typingMessage.remove();
            
            // Show user-friendly error based on error type
            if (fetchError.name === 'AbortError') {
                addMessageToChat(
                    "⏱️ The request timed out. This is common with free hosting services when they're starting up. Please try again in a few moments or use the search filters above to find properties immediately.",
                    'bot'
                );
            } else {
                // Try alternative endpoint
                const alternativeUrl = backendUrl.includes('localhost') 
                    ? "https://bahai.onrender.com/api/chat" 
                    : "http://localhost:10000/api/chat";
                
                console.log("🔄 Trying alternative endpoint:", alternativeUrl);
                
                try {
                    const alternativeController = new AbortController();
                    const alternativeTimeout = setTimeout(() => alternativeController.abort(), 10000);
                    
                    const fallbackResponse = await fetch(alternativeUrl, {
                        method: 'POST',
                        headers: {
                            'Content-Type': 'application/json',
                        },
                        body: JSON.stringify(requestData),
                        signal: alternativeController.signal,
                        mode: 'cors'
                    });
                    
                    clearTimeout(alternativeTimeout);
                    
                    if (fallbackResponse.ok) {
                        const text = await fallbackResponse.text();
                        const cleanText = text.replace(/undefined/g, 'null');
                        data = JSON.parse(cleanText);
                        console.log("✅ Connected to alternative endpoint");
                    } else {
                        throw new Error(`Alternative endpoint failed: ${fallbackResponse.status}`);
                    }
                } catch (fallbackError) {
                    console.error('❌ Fallback also failed:', fallbackError);
                    
                    // Use comprehensive fallback response
                    data = {
                        success: true,
                        response: `I received your query: **"${userMessage}"**\n\n📢 **Important Notice:** The AI service is temporarily experiencing high load or starting up (common with free hosting).\n\n🔍 **In the meantime, here's what you can do:**\n\n1️⃣ **Use the search filters above** - Find properties by location, type, and price\n2️⃣ **Browse by category** - Check out the property category cards below\n3️⃣ **Try these quick searches:**\n   • "Apartments in Batangas City"\n   • "Houses under ₱3M"\n   • "Properties with 3 bedrooms"\n\n💡 **Tip:** The AI service usually becomes available within 30-60 seconds of first access.`,
                        properties: [],
                        intent: 'fallback',
                        properties_found: 0
                    };
                }
            }
        }
        
        // Remove typing indicator if still exists
        if (typingMessage && typingMessage.parentNode) {
            typingMessage.remove();
        }
        
        // Remove demo prompts when user sends a message
        const demoPrompts = document.querySelector('.demo-prompts-container');
        if (demoPrompts) {
            demoPrompts.remove();
        }
        
        // Display response
        if (data && data.response) {
            addMessageToChat(data.response, 'bot');
        } else if (data && data.message) {
            addMessageToChat(data.message, 'bot');
        } else {
            addMessageToChat("I received your message but couldn't process it properly. Please try again.", 'bot');
        }
        
        // If properties were found, display them
        if (data && data.properties && data.properties.length > 0) {
            displayPropertiesInChat(data.properties);
        }
        
        // Show demo prompts again after response
        setTimeout(addDemoPrompts, 500);
        
        // Try to log (non-critical)
        try {
            await logChatInteraction(userMessage, data, currentUser);
        } catch (logError) {
            console.log('Non-critical log error:', logError.message);
        }
        
    } catch (error) {
        console.error('💥 Error in processChatMessage:', error);
        
        // Remove typing indicator
        document.querySelector('.typing-indicator')?.remove();
        
        // Remove demo prompts on error
        document.querySelector('.demo-prompts-container')?.remove();
        
        // Show user-friendly error
        addMessageToChat(
            "I'm having trouble connecting right now. 😔\n\nYou can still:\n• Use the search filters above 🔍\n• Browse property categories 🏠\n• Try again in a moment ⏳\n\nThe backend might be starting up (this is normal with free hosting).",
            'bot'
        );
        
        // Show demo prompts again after error
        setTimeout(addDemoPrompts, 500);
    } finally {
        // Re-enable input
        const chatInput = document.getElementById('chatInput');
        const sendChatBtn = document.getElementById('sendChatBtn');
        
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

// Add messages to chat UI
function addMessageToChat(message, sender) {
    const chatMessages = document.getElementById('chatMessages');
    if (!chatMessages) return;
    
    const messageDiv = document.createElement('div');
    messageDiv.className = `message ${sender}`;
    
    const avatar = sender === 'user' ? '👤' : '🤖';
    
    // Convert newlines to HTML breaks and basic markdown
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

// Add typing indicator
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
            <p style="font-size: 12px; color: #666; margin-top: 5px;">
                Connecting to AI service... This might take a moment on first access.
            </p>
        </div>
    `;
    chatMessages.appendChild(typingDiv);
    chatMessages.scrollTop = chatMessages.scrollHeight;
    return typingDiv;
}

// Display properties in chat
function displayPropertiesInChat(properties) {
    const chatMessages = document.getElementById('chatMessages');
    if (!chatMessages || !properties || properties.length === 0) return;
    
    const propertiesDiv = document.createElement('div');
    propertiesDiv.className = 'chat-properties-container';
    
    let html = `
        <div style="margin-bottom: 10px; font-weight: 600; color: var(--text-dark);">
            🏠 Found ${properties.length} matching properties:
        </div>
        <div class="properties-grid">
    `;
    
    // Show max 3 properties in chat
    properties.slice(0, 3).forEach(prop => {
        const price = getDisplayPrice(prop);
        const bedrooms = prop.bedrooms || 'N/A';
        const area = prop.floorArea || prop.totalArea || 'N/A';
        const title = prop.title || 'Untitled Property';
        const location = prop.address || prop.city || prop.location || 'Location not specified';
        const photo = prop.photos?.[0] || prop.imageUrls?.[0] || 
            `https://via.placeholder.com/300x200/0b2e52/white?text=${encodeURIComponent(title.substring(0, 20))}`;
        
        html += `
            <div class="property-card-chat">
                <div class="property-image">
                    <img src="${photo}" alt="${title}" onerror="this.src='https://via.placeholder.com/300x200/0b2e52/white?text=Property'">
                </div>
                <div class="property-info">
                    <h4>${title.length > 40 ? title.substring(0, 40) + '...' : title}</h4>
                    <p class="location">📍 ${location.length > 30 ? location.substring(0, 30) + '...' : location}</p>
                    <div class="details">
                        ${bedrooms ? `<span>🛏️ ${bedrooms} ${bedrooms === 'Studio' ? '' : 'beds'}</span>` : ''}
                        ${area && area !== 'N/A' ? `<span>📐 ${area} sqm</span>` : ''}
                    </div>
                    <p class="price">${price}</p>
                    <a href="new_property_details.html?id=${prop.id || prop.property_id || ''}" 
                       target="_blank" 
                       class="view-btn">
                        View Details
                    </a>
                </div>
            </div>
        `;
    });
    
    html += '</div>';
    
    if (properties.length > 3) {
        html += `
            <p style="text-align: center; margin-top: 15px;">
                <a href="search_results.html" 
                   style="color: #0b6e4f; text-decoration: underline; font-weight: 600;">
                    🔍 View all ${properties.length} properties in search results →
                </a>
            </p>
        `;
    }
    
    propertiesDiv.innerHTML = html;
    
    chatMessages.appendChild(propertiesDiv);
    chatMessages.scrollTop = chatMessages.scrollHeight;
}

// Helper function to format price
function getDisplayPrice(property) {
    if (!property) return 'Price on inquiry';
    
    if (property.monthlyRent) {
        return `₱${property.monthlyRent.toLocaleString()}/month`;
    } else if (property.annualRent) {
        return `₱${property.annualRent.toLocaleString()}/year`;
    } else if (property.salePrice) {
        return `₱${property.salePrice.toLocaleString()}`;
    } else if (property.pricing) {
        return `₱${property.pricing.toLocaleString()}`;
    }
    return 'Price on inquiry';
}

// Log chat interactions (optional)
async function logChatInteraction(query, response, user) {
    try {
        if (!user) return;
        
        // Import Firestore inside function to avoid initialization issues
        const { getFirestore, collection, addDoc } = await import("https://www.gstatic.com/firebasejs/12.4.0/firebase-firestore.js");
        const { getApp } = await import("https://www.gstatic.com/firebasejs/12.4.0/firebase-app.js");
        
        // Get initialized app and Firestore
        const app = getApp();
        const db = getFirestore(app);
        
        await addDoc(collection(db, 'chatbot_logs'), {
            userId: user.uid,
            query: query,
            intent: response.intent || 'unknown',
            entities: response.entities || {},
            response: response.response?.substring(0, 200) || '',
            propertiesFound: response.properties_found || 0,
            timestamp: new Date(),
            modelUsed: response.model_used || 'unknown',
            confidence: response.confidence || 0,
            success: response.success || false
        });
        
        console.log('✅ Chat interaction logged');
    } catch (error) {
        console.log('Could not log chat interaction (non-critical):', error.message);
        // This is non-critical, so don't throw error
    }
}

function addDemoPrompts() {
    // Remove ALL existing prompt sections
    const existingPromptSections = document.querySelectorAll('.demo-prompts-container, .demo-prompts, .quick-prompts-section, .ai-quick-questions');
    existingPromptSections.forEach(section => section.remove());
    
    const chatMessages = document.getElementById('chatMessages');
    if (!chatMessages) return;
    
    // Your original 10 questions
    const ALL_PROMPTS = [
        { text: "Apartments in Batangas City", emoji: "🏢", id: "q1" },
        { text: "Houses under 3M, 3 bedrooms", emoji: "🏠", id: "q2" },
        { text: "Family properties in Lipa", emoji: "👨‍👩‍👧‍👦", id: "q3" },
        { text: "Near hospitals in Tanauan", emoji: "🏥", id: "q4" },
        { text: "Apartments with parking", emoji: "🚗", id: "q5" },
        { text: "Ready for students Batangas", emoji: "🎓", id: "q6" },
        { text: "Pag-IBIG financing", emoji: "💰", id: "q7" },
        { text: "Steps to buy condo", emoji: "📋", id: "q8" },
        { text: "About Nasugbu", emoji: "📍", id: "q9" },
        { text: "For single professionals", emoji: "🎯", id: "q10" }
    ];
    
    // The 5 initial "Try these" prompts
    const INITIAL_PROMPTS = [
        { text: "Find apartments", emoji: "🏢", id: "init1" },
        { text: "Find houses", emoji: "🏠", id: "init2" },
        { text: "About Batangas", emoji: "📍", id: "init3" },
        { text: "Bank financing", emoji: "💰", id: "init4" },
        { text: "Find condos", emoji: "🏙️", id: "init5" }
    ];
    
    // Initialize global tracking
    if (!window.promptTracker) {
        window.promptTracker = {
            usedQuestions: new Set(),
            showInitial: true,
            allQuestions: ALL_PROMPTS,
            initialPrompts: INITIAL_PROMPTS,
            usedInitialPrompts: new Set() // Track used initial prompts
        };
    }
    
    let selectedPrompts;
    let titleText;
    let showCount = false;
    let showShuffleButton = false;
    let gridColumns = "repeat(3, 1fr)";
    
    if (window.promptTracker.showInitial) {
        // FIRST LOAD: Show ONLY the 5 initial "Try these" prompts
        titleText = "Try these quick prompts";
        showCount = false;
        showShuffleButton = false;
        gridColumns = "repeat(3, 1fr)";
        
        // Get available initial prompts (not used yet)
        const availableInitialPrompts = window.promptTracker.initialPrompts.filter(
            p => !window.promptTracker.usedInitialPrompts.has(p.id)
        );
        
        if (availableInitialPrompts.length === 0) {
            // All initial prompts used, switch to quick prompts
            window.promptTracker.showInitial = false;
            window.promptTracker.usedInitialPrompts.clear();
            // Recursively call to show quick prompts
            addDemoPrompts();
            return;
        }
        
        selectedPrompts = availableInitialPrompts.slice(0, 5);
    } else {
        // AFTER FIRST USE: Show 4 random questions from your 10 questions
        titleText = "Quick Prompts";
        showCount = true;
        showShuffleButton = true;
        gridColumns = "repeat(2, 1fr)";
        
        // Get available questions (not used yet)
        const availableQuestions = window.promptTracker.allQuestions.filter(
            q => !window.promptTracker.usedQuestions.has(q.id)
        );
        
        // If less than 4 available, reset used questions
        if (availableQuestions.length < 4) {
            window.promptTracker.usedQuestions.clear();
            selectedPrompts = window.promptTracker.allQuestions
                .sort(() => Math.random() - 0.5)
                .slice(0, 4);
        } else {
            // Shuffle and take 4 random questions
            selectedPrompts = availableQuestions
                .sort(() => Math.random() - 0.5)
                .slice(0, 4);
        }
        
        // Mark these 4 as used
        selectedPrompts.forEach(q => window.promptTracker.usedQuestions.add(q.id));
    }
    
    const demoSection = document.createElement('div');
    demoSection.className = 'demo-prompts-container';
    demoSection.innerHTML = `
        <div class="demo-prompts-title">
            <i class="fas fa-bolt"></i> ${titleText}
            ${showCount ? `
                <span class="prompt-count-badge">
                    ${window.promptTracker.usedQuestions.size}/10 Questions
                </span>
            ` : ''}
        </div>
        <div class="demo-prompts-buttons" style="grid-template-columns: ${gridColumns};">
            ${selectedPrompts.map(prompt => `
                <button class="demo-prompt-btn" data-prompt="${prompt.text}" data-id="${prompt.id}" 
                        title="Click to use: ${prompt.text}">
                    <span class="prompt-icon">${prompt.emoji}</span>
                    <span class="prompt-text">${prompt.text}</span>
                </button>
            `).join('')}
        </div>
        ${showShuffleButton ? `
            <div class="prompts-footer">
                <div class="prompts-info">
                    <i class="fas fa-sync-alt fa-xs"></i> Prompts shuffle after use
                </div>
                <button id="refreshPrompts" class="shuffle-button">
                    <i class="fas fa-random"></i> New set
                </button>
            </div>
        ` : ''}
    `;
    
    chatMessages.parentNode.insertBefore(demoSection, chatMessages.nextSibling);
    
    // Add event listeners to prompt buttons
    setTimeout(() => {
        document.querySelectorAll('.demo-prompt-btn').forEach(btn => {
            btn.addEventListener('click', function() {
                const prompt = this.getAttribute('data-prompt');
                const promptId = this.getAttribute('data-id');
                const chatInput = document.getElementById('chatInput');
                
                if (chatInput) {
                    chatInput.value = prompt;
                    chatInput.focus();
                    
                    // Track used prompts
                    if (window.promptTracker.showInitial) {
                        // Mark initial prompt as used
                        window.promptTracker.usedInitialPrompts.add(promptId);
                        
                        // If all initial prompts are used, switch to quick prompts next time
                        if (window.promptTracker.usedInitialPrompts.size >= window.promptTracker.initialPrompts.length) {
                            window.promptTracker.showInitial = false;
                        }
                    } else {
                        // Mark question as used
                        if (promptId && promptId.startsWith('q')) {
                            window.promptTracker.usedQuestions.add(promptId);
                        }
                    }
                    
                    // Auto-send after a brief delay
                    setTimeout(() => {
                        processChatMessage(prompt);
                        chatInput.value = '';
                        
                        // Update prompts after sending
                        setTimeout(() => {
                            addDemoPrompts();
                        }, 1000);
                    }, 300);
                    
                    // Visual feedback
                    this.style.transform = 'scale(0.95)';
                    this.style.boxShadow = '0 0 0 2px rgba(102, 126, 234, 0.3)';
                    setTimeout(() => {
                        this.style.transform = '';
                        this.style.boxShadow = '';
                    }, 300);
                }
            });
        });
        
        // Add shuffle button functionality
        const refreshBtn = document.getElementById('refreshPrompts');
        if (refreshBtn) {
            refreshBtn.addEventListener('click', (e) => {
                e.preventDefault();
                e.stopPropagation();
                
                // Get new random set
                if (!window.promptTracker.showInitial) {
                    addDemoPrompts();
                }
                
                // Button feedback
                refreshBtn.innerHTML = '<i class="fas fa-spinner fa-spin"></i>';
                setTimeout(() => {
                    refreshBtn.innerHTML = '<i class="fas fa-random"></i> New set';
                }, 500);
            });
        }
        
        // Ensure chat input is visible
        const chatInput = document.getElementById('chatInput');
        if (chatInput) {
            chatInput.style.display = 'block';
            chatInput.style.visibility = 'visible';
            chatInput.style.opacity = '1';
        }
    }, 100);
}

// Show welcome message on first load
function showWelcomeMessage() {
    const chatMessages = document.getElementById('chatMessages');
    if (chatMessages && chatMessages.children.length === 0) {
        // Ensure chat input is visible
        const chatInputContainer = chatMessages.closest('.chatbot-container');
        if (chatInputContainer) {
            const chatInputDiv = chatInputContainer.querySelector('.chat-input');
            if (chatInputDiv) {
                chatInputDiv.style.display = 'flex';
                chatInputDiv.style.opacity = '1';
            }
        }
        
        setTimeout(() => {
            const welcomeMessage = `
                <div class="welcome-message">
                    <div style="display: flex; align-items: center; gap: 10px; margin-bottom: 15px;">
                        <div style="width: 50px; height: 50px; border-radius: 50%; background: linear-gradient(135deg, #667eea 0%, #764ba2 100%); 
                            display: flex; align-items: center; justify-content: center; font-size: 24px;">
                            🤖
                        </div>
                        <div>
                            <h4 style="margin: 0; color: var(--text-dark);">AI Property Assistant</h4>
                            <p style="margin: 0; font-size: 12px; color: #666;">Specialized in Batangas Properties</p>
                        </div>
                    </div>
                    <p style="color: var(--text-dark); margin-bottom: 15px; line-height: 1.5;">
                        Hello! I'm your AI property assistant for Batangas. I can help you with:
                    </p>
                    <div style="display: grid; grid-template-columns: repeat(2, 1fr); gap: 10px; margin-bottom: 20px;">
                        <div style="background: white; padding: 10px; border-radius: 8px; border: 1px solid rgba(0,0,0,0.1);">
                            <div style="font-weight: 600; color: #667eea;">🔍</div>
                            <div style="font-size: 11px; margin-top: 5px;">Find properties</div>
                        </div>
                        <div style="background: white; padding: 10px; border-radius: 8px; border: 1px solid rgba(0,0,0,0.1);">
                            <div style="font-weight: 600; color: #667eea;">💰</div>
                            <div style="font-size: 11px; margin-top: 5px;">Financing info</div>
                        </div>
                        <div style="background: white; padding: 10px; border-radius: 8px; border: 1px solid rgba(0,0,0,0.1);">
                            <div style="font-weight: 600; color: #667eea;">📍</div>
                            <div style="font-size: 11px; margin-top: 5px;">Location details</div>
                        </div>
                        <div style="background: white; padding: 10px; border-radius: 8px; border: 1px solid rgba(0,0,0,0.1);">
                            <div style="font-weight: 600; color: #667eea;">🏠</div>
                            <div style="font-size: 11px; margin-top: 5px;">Property features</div>
                        </div>
                    </div>
                    <p style="color: #666; font-size: 12px; font-style: italic; margin-top: 15px; padding: 10px; background: rgba(102, 126, 234, 0.05); border-radius: 8px;">
                        <i class="fas fa-info-circle"></i> <strong>Note:</strong> On first use, the AI service may take 30-60 seconds to start (free hosting). Try the quick prompts below!
                    </p>
                </div>
            `;
            
            const welcomeDiv = document.createElement('div');
            welcomeDiv.className = 'message bot';
            welcomeDiv.innerHTML = `
                <div class="avatar">🤖</div>
                <div class="content">${welcomeMessage}</div>
            `;
            chatMessages.appendChild(welcomeDiv);
        }, 300);
    }
}

// Add CSS for chatbot styling
const chatbotStyles = document.createElement('style');
chatbotStyles.textContent = `
    /* Chat messages styling */
    .chat-messages {
        height: 420px;
        overflow-y: auto;
        padding: 15px;
        background: #f8f9fa;
        border-radius: 10px;
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
    }
    
    .message.user .avatar {
        background: linear-gradient(135deg, #0b2e52 0%, #1e3a5f 100%);
    }
    
    .message .content {
        max-width: 70%;
        padding: 12px 16px;
        border-radius: 18px;
        background: white;
        box-shadow: 0 2px 8px rgba(0,0,0,0.1);
        line-height: 1.5;
    }
    
    .message.user .content {
        background: linear-gradient(135deg, #0b2e52 0%, #1e3a5f 100%);
        color: white;
    }
    
    .message.bot .content {
        background: white;
        color: #333;
    }
    
    .message .content strong {
        color: inherit;
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
        transition: border-color 0.3s;
        font-family: inherit;
    }
    
    .chat-input input:focus {
        outline: none;
        border-color: #667eea;
        box-shadow: 0 0 0 3px rgba(102, 126, 234, 0.1);
    }
    
    .chat-input input:disabled {
        background: #f8f9fa;
        cursor: not-allowed;
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
    }
    
    .chat-input button:hover:not(:disabled) {
        transform: translateY(-2px);
        box-shadow: 0 4px 12px rgba(102, 126, 234, 0.3);
    }
    
    .chat-input button:disabled {
        opacity: 0.7;
        cursor: not-allowed;
    }
    
    .chat-input .voice-btn {
        padding: 12px;
        background: #f8f9fa;
        border: 2px solid #e9ecef;
        color: #666;
    }
    
    /* Property cards in chat */
    .chat-properties-container {
        margin: 15px 0;
        padding: 15px;
        background: #f8f9fa;
        border-radius: 10px;
        border: 1px solid #e9ecef;
        animation: slideIn 0.5s ease;
    }
    
    .properties-grid {
        display: grid;
        grid-template-columns: repeat(auto-fill, minmax(250px, 1fr));
        gap: 15px;
        margin-top: 10px;
    }
    
    .property-card-chat {
        background: white;
        border-radius: 8px;
        overflow: hidden;
        box-shadow: 0 2px 8px rgba(0,0,0,0.1);
        transition: transform 0.2s;
        border: 1px solid #e9ecef;
    }
    
    .property-card-chat:hover {
        transform: translateY(-2px);
        box-shadow: 0 4px 12px rgba(0,0,0,0.15);
    }
    
    .property-card-chat .property-image {
        height: 150px;
        overflow: hidden;
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
        color: #333;
        line-height: 1.3;
    }
    
    .property-card-chat .location {
        font-size: 14px;
        color: #666;
        margin: 0 0 10px 0;
        line-height: 1.3;
    }
    
    .property-card-chat .details {
        display: flex;
        gap: 15px;
        margin: 10px 0;
        font-size: 13px;
        color: #666;
    }
    
    .property-card-chat .price {
        font-weight: bold;
        color: #0b6e4f;
        margin: 10px 0;
        font-size: 16px;
    }
    
    .property-card-chat .view-btn {
        display: inline-block;
        background: linear-gradient(135deg, #0b6e4f 0%, #0d8a63 100%);
        color: white;
        padding: 8px 15px;
        border-radius: 5px;
        text-decoration: none;
        font-size: 14px;
        transition: all 0.3s;
        border: none;
        cursor: pointer;
        text-align: center;
        width: 100%;
        box-sizing: border-box;
    }
    
    .property-card-chat .view-btn:hover {
        background: #094d38;
        transform: translateY(-1px);
    }
    
    /* Typing indicator */
    .typing-indicator .typing {
        display: flex;
        gap: 4px;
        margin-bottom: 5px;
    }
    
    .typing-indicator .typing span {
        width: 8px;
        height: 8px;
        background: #ccc;
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
        background: linear-gradient(135deg, rgba(102, 126, 234, 0.05) 0%, rgba(118, 75, 162, 0.05) 100%);
        padding: 20px;
        border-radius: 12px;
        border: 1px solid rgba(102, 126, 234, 0.1);
    }
    
    .welcome-message h4 {
        color: var(--text-dark) !important;
        font-size: 18px;
        margin-bottom: 5px !important;
    }
    
    .welcome-message p {
        line-height: 1.5;
    }
    
    /* DEMO PROMPTS - COMPACT STYLING */
    .demo-prompts-container {
        margin-top: 10px;
        padding: 12px;
        background: linear-gradient(135deg, rgba(102, 126, 234, 0.05) 0%, rgba(118, 75, 162, 0.05) 100%);
        border-radius: 8px;
        border: 1px solid rgba(102, 126, 234, 0.1);
        animation: fadeIn 0.3s ease;
        max-height: 160px;
        overflow: hidden;
    }
    
    .demo-prompts-title {
        font-size: 13px;
        color: var(--text-dark);
        font-weight: 600;
        margin-bottom: 8px;
        display: flex;
        align-items: center;
        gap: 6px;
    }
    
    .prompt-count-badge {
        font-size: 11px;
        background: rgba(102, 126, 234, 0.15);
        padding: 2px 8px;
        border-radius: 10px;
        font-weight: 600;
        color: #667eea;
        margin-left: 6px;
    }
    
    .demo-prompts-buttons {
        display: grid;
        gap: 6px;
        margin-bottom: 8px;
    }
    
    .demo-prompt-btn {
        background: white;
        border: 1px solid rgba(102, 126, 234, 0.15);
        border-radius: 6px;
        padding: 8px 10px;
        cursor: pointer;
        text-align: left;
        transition: all 0.2s;
        display: flex;
        align-items: center;
        gap: 6px;
        font-size: 12px;
        color: #333;
        overflow: hidden;
        text-overflow: ellipsis;
        white-space: nowrap;
        height: 36px;
    }
    
    .demo-prompt-btn:hover {
        background: rgba(102, 126, 234, 0.08);
        border-color: rgba(102, 126, 234, 0.3);
        transform: translateY(-1px);
    }
    
    .demo-prompt-btn .prompt-icon {
        font-size: 13px;
        flex-shrink: 0;
        width: 18px;
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
        margin-top: 8px;
        padding-top: 8px;
        border-top: 1px solid rgba(102, 126, 234, 0.1);
    }
    
    .prompts-info {
        font-size: 11px;
        color: #888;
        display: flex;
        align-items: center;
        gap: 4px;
    }
    
    .shuffle-button {
        font-size: 11px;
        background: rgba(102, 126, 234, 0.1);
        border: 1px solid rgba(102, 126, 234, 0.2);
        color: #667eea;
        cursor: pointer;
        padding: 4px 10px;
        border-radius: 12px;
        font-weight: 500;
        display: flex;
        align-items: center;
        gap: 4px;
        transition: all 0.2s;
    }
    
    .shuffle-button:hover {
        background: rgba(102, 126, 234, 0.15);
        border-color: rgba(102, 126, 234, 0.3);
    }
    
    /* Animations */
    @keyframes typing {
        0%, 60%, 100% {
            transform: translateY(0);
            background: #ccc;
        }
        30% {
            transform: translateY(-5px);
            background: #0b6e4f;
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
`;

// Add styles to document
if (!document.querySelector('#chatbot-styles')) {
    chatbotStyles.id = 'chatbot-styles';
    document.head.appendChild(chatbotStyles);
}

// Function to ping backend and keep it awake (for Render free tier)
function keepBackendAlive() {
    // Only ping in production
    if (window.location.hostname.includes('render.com') || 
        window.location.hostname.includes('bahai-frontend')) {
        
        // Initial ping after page load
        setTimeout(() => {
            fetch('https://bahai.onrender.com/api/health', { 
                method: 'GET',
                mode: 'cors',
                cache: 'no-cache'
            })
            .then(res => console.log('✅ Backend pinged successfully'))
            .catch(err => console.log('⚠️ Backend ping failed:', err.message));
        }, 2000);
        
        // Regular pings every 5 minutes
        setInterval(() => {
            fetch('https://bahai.onrender.com/api/health', { 
                method: 'GET',
                mode: 'cors',
                cache: 'no-cache'
            })
            .then(() => console.log('✅ Backend kept alive'))
            .catch(err => console.log('⚠️ Keep-alive failed:', err.message));
        }, 5 * 60 * 1000); // Every 5 minutes
    }
}

// Start keep-alive when DOM is loaded
if (document.readyState === 'loading') {
    document.addEventListener('DOMContentLoaded', keepBackendAlive);
} else {
    keepBackendAlive();
}

// Make functions available globally
window.processChatMessage = processChatMessage;
window.initChatbot = initChatbot;

console.log("🚀 AI Chatbot Script Loaded Successfully!");