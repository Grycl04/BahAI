// ai_chatbot.js - Complete Updated Version with Local Python Backend
import { getAuth } from "https://www.gstatic.com/firebasejs/12.4.0/firebase-auth.js";

// Your Python backend URL - LOCAL DEVELOPMENT
const PYTHON_CHAT_API = "http://localhost:5000/api/chat";

// Initialize chatbot in your dashboard
export function initChatbot() {
    console.log("🤖 AI Chatbot Initializing...");
    
    const chatInput = document.getElementById('chatInput');
    const sendChatBtn = document.getElementById('sendChatBtn');
    const voiceInputBtn = document.getElementById('voiceInputBtn');
    const chatMessages = document.getElementById('chatMessages');
    
    if (!chatInput || !sendChatBtn || !chatMessages) {
        console.error("❌ Chatbot elements not found!");
        return;
    }
    
    // Show welcome message on first load
    showWelcomeMessage();
    
    // Send message on button click
    sendChatBtn.addEventListener('click', async () => {
        const message = chatInput.value.trim();
        if (message) {
            await processChatMessage(message);
            chatInput.value = '';
        }
    });
    
    // Send message on Enter key
    chatInput.addEventListener('keypress', async (e) => {
        if (e.key === 'Enter' && !e.shiftKey) {
            e.preventDefault();
            const message = chatInput.value.trim();
            if (message) {
                await processChatMessage(message);
                chatInput.value = '';
            }
        }
    });
    
    // Voice input button (optional)
    if (voiceInputBtn) {
        voiceInputBtn.addEventListener('click', () => {
            alert("Voice input would require additional setup with Web Speech API");
        });
    }
    
    console.log("✅ AI Chatbot Initialized!");
}

// Main function to process chat messages
export async function processChatMessage(userMessage) {
    try {
        const auth = getAuth();
        const currentUser = auth.currentUser;
        
        // Add user message to chat
        addMessageToChat(userMessage, 'user');
        
        // Show typing indicator
        const typingMessage = addTypingIndicator();
        
        // Prepare request to Python backend
        const requestData = {
            query: userMessage,
            user_id: currentUser ? currentUser.uid : 'anonymous'
        };
        
        console.log("📤 Sending to Python backend:", requestData);
        
        let data;
        try {
            // Call Python backend with timeout
            const controller = new AbortController();
            const timeoutId = setTimeout(() => controller.abort(), 10000); // 10 second timeout
            
            const response = await fetch(PYTHON_CHAT_API, {
                method: 'POST',
                headers: {
                    'Content-Type': 'application/json',
                },
                body: JSON.stringify(requestData),
                signal: controller.signal
            });
            
            clearTimeout(timeoutId);
            
            if (!response.ok) {
                throw new Error(`HTTP ${response.status}: ${response.statusText}`);
            }
            
            const text = await response.text();
            console.log("📥 Raw response:", text.substring(0, 200));
            
            // Clean the response
            const cleanText = text.replace(/undefined/g, 'null');
            data = JSON.parse(cleanText);
            
        } catch (fetchError) {
            console.error('Fetch error:', fetchError);
            // Use fallback response
            data = {
                success: true,
                response: `I received your query: "${userMessage}". The AI backend is being optimized. Try using the search filters for now.`,
                properties: [],
                intent: 'fallback',
                properties_found: 0
            };
        }
        
        // Remove typing indicator
        typingMessage.remove();
        
        // Remove demo prompts when user sends a message
        const demoPrompts = document.querySelector('.demo-prompts');
        if (demoPrompts) {
            demoPrompts.remove();
        }
        
        // Display response
        addMessageToChat(data.response, 'bot');
        
        // If properties were found, display them
        if (data.properties && data.properties.length > 0) {
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
        console.error('Error in processChatMessage:', error);
        
        // Remove typing indicator
        document.querySelector('.typing-indicator')?.remove();
        
        // Remove demo prompts on error
        document.querySelector('.demo-prompts')?.remove();
        
        // Show user-friendly error
        addMessageToChat(
            "I'm currently learning! Try asking: 'Find apartments in Batangas City' or use the search filters above.", 
            'bot'
        );
        
        // Show demo prompts again after error
        setTimeout(addDemoPrompts, 500);
    }
}

// Add messages to chat UI
function addMessageToChat(message, sender) {
    const chatMessages = document.getElementById('chatMessages');
    
    const messageDiv = document.createElement('div');
    messageDiv.className = `message ${sender}`;
    
    const avatar = sender === 'user' ? '👤' : '🤖';
    
    messageDiv.innerHTML = `
        <div class="avatar">${avatar}</div>
        <div class="content">
            <p>${message}</p>
        </div>
    `;
    
    chatMessages.appendChild(messageDiv);
    chatMessages.scrollTop = chatMessages.scrollHeight;
}

// Add typing indicator
function addTypingIndicator() {
    const chatMessages = document.getElementById('chatMessages');
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
        </div>
    `;
    chatMessages.appendChild(typingDiv);
    chatMessages.scrollTop = chatMessages.scrollHeight;
    return typingDiv;
}

// Display properties in chat
function displayPropertiesInChat(properties) {
    const chatMessages = document.getElementById('chatMessages');
    
    const propertiesDiv = document.createElement('div');
    propertiesDiv.className = 'chat-properties-container';
    
    let html = '<div class="properties-grid">';
    
    // Show max 3 properties in chat
    properties.slice(0, 3).forEach(prop => {
        const price = getDisplayPrice(prop);
        const bedrooms = prop.bedrooms || 'N/A';
        const area = prop.floorArea || prop.totalArea || 'N/A';
        const photo = prop.photos?.[0] || prop.imageUrls?.[0] || 'https://via.placeholder.com/200x150';
        
        html += `
            <div class="property-card-chat">
                <div class="property-image">
                    <img src="${photo}" alt="${prop.title}" onerror="this.src='https://via.placeholder.com/200x150'">
                </div>
                <div class="property-info">
                    <h4>${prop.title || 'Untitled Property'}</h4>
                    <p class="location">📍 ${prop.address || prop.city || 'Location not specified'}</p>
                    <div class="details">
                        <span>🛏️ ${bedrooms} ${bedrooms === 'Studio' ? '' : 'beds'}</span>
                        ${area && area !== 'N/A' ? `<span>📐 ${area} sqm</span>` : ''}
                    </div>
                    <p class="price">${price}</p>
                    <a href="property_details.html?id=${prop.id}" target="_blank" class="view-btn">View Details</a>
                </div>
            </div>
        `;
    });
    
    html += '</div>';
    
    if (properties.length > 3) {
        html += `<p style="text-align: center; margin-top: 10px;">
                    <a href="search_results.html" style="color: var(--primary); text-decoration: underline;">
                        View all ${properties.length} properties →
                    </a>
                 </p>`;
    }
    
    propertiesDiv.innerHTML = html;
    
    chatMessages.appendChild(propertiesDiv);
    chatMessages.scrollTop = chatMessages.scrollHeight;
}

// Helper function to format price
function getDisplayPrice(property) {
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
            confidence: response.confidence || 0
        });
        
        console.log('✅ Chat interaction logged');
    } catch (error) {
        console.log('Could not log chat interaction (non-critical):', error.message);
        // This is non-critical, so don't throw error
    }
}

// Add demo prompts to chat interface covering all 10 questions
function addDemoPrompts() {
    const chatInput = document.getElementById('chatInput');
    const chatMessages = document.getElementById('chatMessages');
    
    if (!chatInput || !chatMessages) return;
    
    // Remove existing demo prompts if any
    const existingPrompts = document.querySelector('.demo-prompts');
    if (existingPrompts) {
        existingPrompts.remove();
    }
    
    // Quick prompts covering ALL 10 questions
    const quickPrompts = [
        // Question 1 (Member 1) - Basic search
        {
            text: "Find apartments in Batangas City",
            question: 1,
            member: "member1",
            emoji: "🏢"
        },
        // Question 2 (Member 2) - Detailed criteria
        {
            text: "Show me houses under 3M with 3 bedrooms",
            question: 2,
            member: "member2",
            emoji: "🏠"
        },
        // Question 3 (Member 3) - Family needs
        {
            text: "Find properties for family needs in Lipa City",
            question: 3,
            member: "member3",
            emoji: "👨‍👩‍👧‍👦"
        },
        // Question 4 (Member 2) - Near landmarks
        {
            text: "Properties near hospitals in Tanauan",
            question: 4,
            member: "member2",
            emoji: "🏥"
        },
        // Question 5 (Member 3) - Features with price
        {
            text: "Show me apartments with parking at good price",
            question: 5,
            member: "member3",
            emoji: "🚗"
        },
        // Question 6 (Member 2) - Ready to move
        {
            text: "Find ready to move in properties for students in Batangas City",
            question: 6,
            member: "member2",
            emoji: "🎓"
        },
        // Question 7 (Member 1) - Financing
        {
            text: "Properties that accept Pag-IBIG financing",
            question: 7,
            member: "member1",
            emoji: "💰"
        },
        // Question 8 (Member 3) - Process info
        {
            text: "Steps for buying a condo",
            question: 8,
            member: "member3",
            emoji: "📋"
        },
        // Question 9 (Member 1) - Location info
        {
            text: "Tell me about Nasugbu",
            question: 9,
            member: "member1",
            emoji: "📍"
        },
        // Question 10 (Member 3) - Lifestyle match
        {
            text: "What properties match my budget as a single professional?",
            question: 10,
            member: "member3",
            emoji: "🎯"
        }
    ];
    
    // Shuffle the prompts for variety
    const shuffledPrompts = [...quickPrompts].sort(() => Math.random() - 0.5);
    
    // Create demo prompts section
    const demoSection = document.createElement('div');
    demoSection.className = 'demo-prompts';
    demoSection.style.cssText = `
        margin-top: 15px;
        padding: 15px;
        background: linear-gradient(135deg, rgba(102, 126, 234, 0.1) 0%, rgba(118, 75, 162, 0.1) 100%);
        border-radius: 12px;
        border: 1px solid rgba(102, 126, 234, 0.2);
        animation: fadeIn 0.5s ease;
    `;
    
    let buttonsHTML = '';
    // Show 6 random prompts from the shuffled list
    for (let i = 0; i < 6 && i < shuffledPrompts.length; i++) {
        const prompt = shuffledPrompts[i];
        buttonsHTML += `
            <button class="demo-prompt-btn" data-prompt="${prompt.text}">
                ${prompt.emoji} ${prompt.text}
            </button>
        `;
    }
    
demoSection.innerHTML = `
    <div style="display: flex; align-items: center; justify-content: space-between; flex-wrap: wrap; gap: 10px; margin-bottom: 12px;">
        <div style="display: flex; align-items: center; gap: 10px;">
            <div style="font-size: 14px; color: var(--text-dark); font-weight: 600;">
                <i class="fas fa-bolt"></i> Quick Prompts
            </div>
            <div style="font-size: 11px; color: #666; background: rgba(255,255,255,0.7); padding: 2px 8px; border-radius: 10px;">
                All 10 Questions Covered
            </div>
        </div>
        <div style="font-size: 11px; color: #888;">
            Click any prompt to try
        </div>
    </div>
    <div style="display: flex; overflow-x: auto; gap: 10px; padding-bottom: 10px; scrollbar-width: thin;">
        ${buttonsHTML}
    </div>
    <div style="margin-top: 8px; font-size: 11px; color: #888; text-align: center;">
        Prompts change on refresh
    </div>
`;
    
    chatMessages.parentNode.insertBefore(demoSection, chatMessages.nextSibling);
    
    // Add event listeners to demo prompt buttons
    setTimeout(() => {
        document.querySelectorAll('.demo-prompt-btn').forEach(btn => {
            btn.addEventListener('click', function() {
                const prompt = this.getAttribute('data-prompt');
                chatInput.value = prompt;
                chatInput.focus();
                
                // Highlight the button briefly
                this.style.transform = 'scale(0.95)';
                this.style.boxShadow = '0 0 0 2px rgba(102, 126, 234, 0.3)';
                setTimeout(() => {
                    this.style.transform = '';
                    this.style.boxShadow = '';
                }, 300);
            });
        });
    }, 100);
}

// Show welcome message on first load
function showWelcomeMessage() {
    const chatMessages = document.getElementById('chatMessages');
    if (chatMessages && chatMessages.children.length === 0) {
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
                    <p style="color: var(--text-dark); margin-bottom: 15px;">
                        Hello! I'm your AI property assistant for Batangas. I can help you with all 10 types of property questions:
                    </p>
                    <div style="display: grid; grid-template-columns: repeat(2, 1fr); gap: 10px; margin-bottom: 20px;">
                        <div style="background: white; padding: 10px; border-radius: 8px; border: 1px solid var(--border);">
                            <div style="font-weight: 600; color: var(--primary);">Q1</div>
                            <div style="font-size: 11px;">Basic property search</div>
                        </div>
                        <div style="background: white; padding: 10px; border-radius: 8px; border: 1px solid var(--border);">
                            <div style="font-weight: 600; color: var(--primary);">Q2</div>
                            <div style="font-size: 11px;">Detailed criteria</div>
                        </div>
                        <div style="background: white; padding: 10px; border-radius: 8px; border: 1px solid var(--border);">
                            <div style="font-weight: 600; color: var(--primary);">Q3-6</div>
                            <div style="font-size: 11px;">Special needs & features</div>
                        </div>
                        <div style="background: white; padding: 10px; border-radius: 8px; border: 1px solid var(--border);">
                            <div style="font-weight: 600; color: var(--primary);">Q7-10</div>
                            <div style="font-size: 11px;">Financing & lifestyle</div>
                        </div>
                    </div>
                    <p style="color: var(--text-dark); margin-bottom: 10px;">
                        <strong>Try asking about:</strong>
                    </p>
                    <ul style="color: var(--text-dark); font-size: 13px; margin: 0 0 15px 15px; padding: 0;">
                        <li>Finding specific properties</li>
                        <li>Financing options & documents</li>
                        <li>Location information</li>
                        <li>Property features & amenities</li>
                    </ul>
                    <p style="color: #666; font-size: 12px; font-style: italic;">
                        <i class="fas fa-lightbulb"></i> Try the quick prompts below to get started!
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
            
            // Show demo prompts after welcome message
            setTimeout(addDemoPrompts, 500);
        }, 300);
    }
}

// Add CSS for chatbot styling
const chatbotStyles = document.createElement('style');
chatbotStyles.textContent = `
    /* Chat messages styling */
    .chat-messages {
        height: 400px;
        overflow-y: auto;
        padding: 15px;
        background: #f8f9fa;
        border-radius: 10px;
        margin-bottom: 15px;
        border: 1px solid #e9ecef;
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
    }
    
    .message.user .avatar {
        background: linear-gradient(135deg, #4f46e5 0%, #7c3aed 100%);
    }
    
    .message .content {
        max-width: 70%;
        padding: 12px 16px;
        border-radius: 18px;
        background: white;
        box-shadow: 0 2px 8px rgba(0,0,0,0.1);
    }
    
    .message.user .content {
        background: linear-gradient(135deg, #4f46e5 0%, #7c3aed 100%);
        color: white;
    }
    
    .message.bot .content {
        background: white;
        color: #333;
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
    }
    
    .chat-input input:focus {
        outline: none;
        border-color: #667eea;
    }
    
    .chat-input button {
        padding: 12px 24px;
        background: linear-gradient(135deg, #667eea 0%, #764ba2 100%);
        color: white;
        border: none;
        border-radius: 10px;
        cursor: pointer;
        font-weight: 600;
        transition: transform 0.3s;
    }
    
    .chat-input button:hover {
        transform: translateY(-2px);
        box-shadow: 0 4px 12px rgba(102, 126, 234, 0.3);
    }
    
    .chat-input .voice-btn {
        padding: 12px;
        background: #f8f9fa;
        border: 2px solid #e9ecef;
        color: #666;
    }
    
    /* Demo prompt buttons */
    .demo-prompt-btn {
        padding: 8px 12px;
        background: white;
        border: 1px solid var(--border);
        border-radius: 8px;
        font-size: 13px;
        color: var(--text-dark);
        cursor: pointer;
        transition: all 0.3s ease;
        display: flex;
        align-items: center;
        gap: 6px;
        white-space: nowrap;
        border-left: 3px solid #667eea;
    }
    
    .demo-prompt-btn:hover {
        background: var(--primary);
        color: white;
        border-color: var(--primary);
        transform: translateY(-2px);
        box-shadow: 0 4px 8px rgba(11, 46, 82, 0.15);
    }
    
    /* Team member color coding for buttons */
    .demo-prompt-btn[data-prompt*="apartments in Batangas"],
    .demo-prompt-btn[data-prompt*="financing"],
    .demo-prompt-btn[data-prompt*="Nasugbu"] {
        border-left-color: #667eea; /* Member 1 - Blue */
    }
    
    .demo-prompt-btn[data-prompt*="houses under 3M"],
    .demo-prompt-btn[data-prompt*="hospitals"],
    .demo-prompt-btn[data-prompt*="ready to move"] {
        border-left-color: #4CAF50; /* Member 2 - Green */
    }
    
    .demo-prompt-btn[data-prompt*="family needs"],
    .demo-prompt-btn[data-prompt*="parking at good"],
    .demo-prompt-btn[data-prompt*="Steps for buying"],
    .demo-prompt-btn[data-prompt*="match my budget"] {
        border-left-color: #FF9800; /* Member 3 - Orange */
    }
    
    /* Property cards in chat */
    .chat-properties-container {
        margin: 15px 0;
        padding: 15px;
        background: #f8f9fa;
        border-radius: 10px;
        border: 1px solid #e9ecef;
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
    }
    
    .property-card-chat .property-info {
        padding: 15px;
    }
    
    .property-card-chat h4 {
        margin: 0 0 8px 0;
        font-size: 16px;
        color: #333;
    }
    
    .property-card-chat .location {
        font-size: 14px;
        color: #666;
        margin: 0 0 10px 0;
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
    }
    
    .property-card-chat .view-btn {
        display: inline-block;
        background: #0b6e4f;
        color: white;
        padding: 8px 15px;
        border-radius: 5px;
        text-decoration: none;
        font-size: 14px;
        transition: background 0.3s;
    }
    
    .property-card-chat .view-btn:hover {
        background: #094d38;
    }
    
    /* Typing indicator */
    .typing-indicator .typing {
        display: flex;
        gap: 4px;
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
    
    .welcome-message ul li {
        margin-bottom: 5px;
        line-height: 1.4;
    }
    
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
`;

document.head.appendChild(chatbotStyles);

// Make functions available globally
window.processChatMessage = processChatMessage;
window.initChatbot = initChatbot;

console.log("🚀 AI Chatbot Script Loaded Successfully!");