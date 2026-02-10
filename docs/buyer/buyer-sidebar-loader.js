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