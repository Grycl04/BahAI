/**
 * Shared buyer sidebar loader - ensures consistent sidebar and user profile across all buyer pages.
 * Usage: After including sidebar-user.js, call loadBuyerSidebar('page_name.html')
 * Page names: buyer_dashboard.html, search_results.html, messages.html, liked_properties.html, settings.html
 */
(function() {
  'use strict';

  var SIDEBAR_FALLBACK_HTML = '<div class="sidebar" style="padding: 20px; background: #f8f9fa; color: #dc3545;">' +
    '<p>Unable to load navigation. Please refresh the page.</p></div>';

  function setupMobileMenu() {
    /* Top nav has its own hamburger - no separate mobile toggle needed */
  }

  function setupLogoutButton() {
    var logoutBtn = document.getElementById('logoutBtn');
    if (!logoutBtn) {
      setTimeout(setupLogoutButton, 100);
      return;
    }
    var newBtn = logoutBtn.cloneNode(true);
    logoutBtn.parentNode.replaceChild(newBtn, logoutBtn);
    newBtn.addEventListener('click', function(e) {
      e.preventDefault();
      e.stopPropagation();
      if (confirm('Are you sure you want to log out?')) {
        if (typeof window.performLogout === 'function') {
          window.performLogout();
        } else {
          window.location.href = '../login.html';
        }
      }
    });
  }

  function setupLoginRedirect(redirectPath) {
    var loginBtn = document.getElementById('logoutBtn');
    if (loginBtn && loginBtn.classList.contains('login-btn')) {
      loginBtn.addEventListener('click', function(e) {
        e.preventDefault();
        e.stopImmediatePropagation();
        var redirect = encodeURIComponent(window.location.pathname + (window.location.search || '') || redirectPath);
        window.location.href = '../login.html?redirect=' + redirect;
      });
    }
  }
async function loadBuyerSidebar(activePage = 'buyer_dashboard.html') {
    const sidebarContainer = document.getElementById('sidebar-container');
    if (!sidebarContainer) return;

    try {
        // Fetch the sidebar HTML
        const response = await fetch('buyer_sidebar.html');
        const sidebarHtml = await response.text();
        
        // Inject sidebar HTML
        sidebarContainer.innerHTML = sidebarHtml;
        
        // Highlight active menu item
        setTimeout(() => {
            highlightActiveMenuItem(activePage);
        }, 100);
        
        // Setup sidebar event listeners
        setupSidebarEventListeners();
        
        // Update user profile in sidebar if logged in
        if (typeof window.updateSidebarUserProfile === 'function') {
            window.updateSidebarUserProfile();
        }
        
        // Update sidebar stats (saved properties, messages, etc.)
        if (typeof window.updateSidebarStats === 'function') {
            window.updateSidebarStats();
        }
        
    } catch (error) {
        console.error('Error loading buyer sidebar:', error);
        sidebarContainer.innerHTML = `
            <div class="sidebar-error">
                <i class="fas fa-exclamation-triangle"></i>
                <p>Failed to load sidebar</p>
            </div>
        `;
    }
}

function highlightActiveMenuItem(activePage) {
    // Remove active class from all nav items
    document.querySelectorAll('.sidebar-nav a, .sidebar-menu-item').forEach(item => {
        item.classList.remove('active');
    });
    
    // Add active class to current page link
    document.querySelectorAll(`.sidebar-nav a[href="${activePage}"], .sidebar-menu-item a[href="${activePage}"]`).forEach(item => {
        item.classList.add('active');
        // Also add active class to parent li if it exists
        if (item.parentElement && item.parentElement.tagName === 'LI') {
            item.parentElement.classList.add('active');
        }
    });
}

function setupSidebarEventListeners() {
    // Mobile menu toggle
    const mobileToggle = document.getElementById('mobileMenuToggle');
    const sidebar = document.querySelector('.sidebar');
    
    if (mobileToggle && sidebar) {
        mobileToggle.addEventListener('click', function(e) {
            e.stopPropagation();
            sidebar.classList.toggle('show');
        });
    }
    
    // Close sidebar when clicking outside on mobile
    document.addEventListener('click', function(e) {
        const sidebar = document.querySelector('.sidebar');
        const mobileToggle = document.getElementById('mobileMenuToggle');
        
        if (sidebar && sidebar.classList.contains('show')) {
            if (!sidebar.contains(e.target) && !mobileToggle?.contains(e.target)) {
                sidebar.classList.remove('show');
            }
        }
    });
    
    // Logout button
    const logoutBtn = document.getElementById('logoutBtn');
    if (logoutBtn && typeof window.performLogout === 'function') {
        logoutBtn.addEventListener('click', async function(e) {
            e.preventDefault();
            await window.performLogout();
        });
    }
    
    // ===== UPDATED: AI Assistant link in sidebar - NOW OPENS FULL PAGE =====
    const aiAssistantLink = document.querySelector('a[href="#ai-chatbot-section"], a[href="#ai-assistant"], a[href="ai_assistant.html"]');
    if (aiAssistantLink) {
        aiAssistantLink.addEventListener('click', function(e) {
            e.preventDefault();
            
            // Call function to expand AI Assistant to full page
            if (typeof window.expandAIToFullPage === 'function') {
                window.expandAIToFullPage();
            } else {
                // Fallback: add a parameter to current page
                window.location.href = 'buyer_dashboard.html?mode=ai-full';
            }
            
            // Close sidebar on mobile after clicking
            const sidebar = document.querySelector('.sidebar');
            if (sidebar) sidebar.classList.remove('show');
        });
    }
}

// Make functions available globally
window.loadBuyerSidebar = loadBuyerSidebar;
window.highlightActiveMenuItem = highlightActiveMenuItem;
window.setupSidebarEventListeners = setupSidebarEventListeners;

// Auto-load sidebar when DOM is ready
document.addEventListener('DOMContentLoaded', function() {
    // Check if sidebar container exists and hasn't been loaded yet
    if (document.getElementById('sidebar-container') && 
        document.getElementById('sidebar-container').children.length === 0) {
        
        // Get current page filename
        const currentPage = window.location.pathname.split('/').pop() || 'buyer_dashboard.html';
        loadBuyerSidebar(currentPage);
    }
    
    // Check URL parameter for AI full page mode
    const urlParams = new URLSearchParams(window.location.search);
    if (urlParams.get('mode') === 'ai-full') {
        setTimeout(() => {
            if (typeof window.expandAIToFullPage === 'function') {
                window.expandAIToFullPage();
            }
        }, 500);
    }
});
  function loadBuyerSidebar(activePage, options) {
    options = options || {};
    var sidebarFile = options.sidebarFile || 'sidebar.html';
    var redirectPath = options.redirectPath || ('buyer/' + activePage);
    var highlightActive = options.highlightActive !== false;

    setupMobileMenu();

    return fetch(sidebarFile)
      .then(function(r) {
        if (!r.ok) throw new Error('Sidebar ' + r.status);
        return r.text();
      })
      .then(function(html) {
        var container = document.getElementById('sidebar-container');
        if (!container) return;
        container.innerHTML = html;

        // Execute sidebar scripts (innerHTML doesn't run scripts)
        container.querySelectorAll('script').forEach(function(oldScript) {
          var newScript = document.createElement('script');
          if (oldScript.src) newScript.src = oldScript.src;
          else newScript.textContent = oldScript.textContent;
          document.body.appendChild(newScript);
        });

        // Initialize sidebar - fetches user from Firebase auth (handles guest vs logged-in)
        if (typeof window.initializeSidebar === 'function') {
          window.initializeSidebar();
        }
        // Fallback: update from localStorage when user data exists
        if (typeof window.updateSidebarUserProfile === 'function') {
          window.updateSidebarUserProfile();
        }

        // Highlight active link (only for buyer sidebar - broker/agent navs differ)
        if (highlightActive) {
          var links = document.querySelectorAll('.sidebar-link');
          links.forEach(function(link) {
            var href = link.getAttribute('href');
            if (href === activePage || (href && href.indexOf(activePage) !== -1)) {
              link.classList.add('active');
            } else {
              link.classList.remove('active');
            }
          });
        }

        // Setup login/logout buttons
        var loginBtn = document.getElementById('logoutBtn');
        if (loginBtn && loginBtn.classList.contains('login-btn')) {
          setupLoginRedirect(redirectPath);
        } else {
          setupLogoutButton();
        }
      })
      .catch(function(err) {
        console.error('Sidebar load error:', err);
        var container = document.getElementById('sidebar-container');
        if (container) container.innerHTML = SIDEBAR_FALLBACK_HTML;
      });
  }

  window.loadBuyerSidebar = loadBuyerSidebar;
})();