import { v4 as uuidv4 } from 'https://jspm.dev/uuid'; // Using uuid for robust IDs; fallback if not available

/**
 * SidebarManager – handles sidebar UI, session CRUD, active state, and localStorage persistence.
 * Designed for OmniChat's glassmorphism dark-themed interface.
 */
class SidebarManager {
  /**
   * @param {Object} options
   * @param {string} options.sidebarSelector - CSS selector for the sidebar element
   * @param {string} options.toggleBtnSelector - CSS selector for toggle button
   * @param {string} options.sessionListSelector - CSS selector for the session list container
   * @param {string} options.newChatBtnSelector - CSS selector for "New Chat" button
   * @param {Function} options.onSessionSelect - callback(sessionId) when a session is selected
   * @param {Function} options.onNewSession - callback() when a new session is created
   * @param {Function} options.onSessionDelete - callback(sessionId) after deletion
   * @param {string} [options.storageKey='omni_chat_sessions'] - localStorage key
   */
  constructor(options) {
    this.sidebar = document.querySelector(options.sidebarSelector);
    this.toggleBtn = document.querySelector(options.toggleBtnSelector);
    this.sessionListEl = document.querySelector(options.sessionListSelector);
    this.newChatBtn = document.querySelector(options.newChatBtnSelector);
    this.onSessionSelect = options.onSessionSelect || (() => {});
    this.onNewSession = options.onNewSession || (() => {});
    this.onSessionDelete = options.onSessionDelete || (() => {});
    this.storageKey = options.storageKey || 'omni_chat_sessions';

    this.sessions = [];          // Array of session objects
    this.activeSessionId = null; // Currently selected session ID
    this.isOpen = true;          // Sidebar visibility state
  }

  /** Initialize event listeners and load persisted sessions. */
  init() {
    this._loadSessions();
    this._bindEvents();
    this._renderSessions();
    this._updateSidebarState();
    this._highlightActiveSession();
  }

  // ------------------------------------------------------------------
  // Public API
  // ------------------------------------------------------------------

  /** Toggle sidebar open/close */
  toggle() {
    this.isOpen = !this.isOpen;
    this._updateSidebarState();
  }

  /** Create a new empty session (local only). Returns session object. */
  createSession(title = 'New Chat') {
    const session = {
      id: uuidv4(),
      title: title,
      createdAt: new Date().toISOString(),
      updatedAt: new Date().toISOString(),
    };
    this.sessions.unshift(session);
    this._persistSessions();
    this._renderSessions();
    this.setActiveSession(session.id);
    this.onNewSession();
    return session;
  }

  /** Delete session by ID. Returns boolean success. */
  deleteSession(sessionId) {
    const index = this.sessions.findIndex(s => s.id === sessionId);
    if (index === -1) return false;

    // Confirm deletion (optional, but good UX)
    if (!confirm(`Delete session "${this.sessions[index].title}"?`)) return false;

    this.sessions.splice(index, 1);
    this._persistSessions();
    this._renderSessions();

    // If we deleted the active session, deactivate
    if (this.activeSessionId === sessionId) {
      this.activeSessionId = null;
      this._highlightActiveSession();
    }
    this.onSessionDelete(sessionId);
    return true;
  }

  /** Rename session. Returns boolean success. */
  renameSession(sessionId, newTitle) {
    const session = this.sessions.find(s => s.id === sessionId);
    if (!session || !newTitle.trim()) return false;
    session.title = newTitle.trim();
    session.updatedAt = new Date().toISOString();
    this._persistSessions();
    this._renderSessions();
    // Keep active highlight
    this._highlightActiveSession();
    return true;
  }

  /** Set the active session (by ID or null to deselect) */
  setActiveSession(sessionId) {
    if (sessionId && !this.sessions.find(s => s.id === sessionId)) {
      console.warn(`Session ${sessionId} not found.`);
      return;
    }
    this.activeSessionId = sessionId || null;
    this._highlightActiveSession();
    this._persistSessions(); // persist active session as well
    this.onSessionSelect(sessionId);
  }

  /** Get all sessions */
  getSessions() {
    return [...this.sessions];
  }

  /** Get active session ID */
  getActiveSessionId() {
    return this.activeSessionId;
  }

  /** Get active session object, or null */
  getActiveSession() {
    return this.sessions.find(s => s.id === this.activeSessionId) || null;
  }

  // ------------------------------------------------------------------
  // Private methods
  // ------------------------------------------------------------------

  _bindEvents() {
    // Toggle button
    this.toggleBtn.addEventListener('click', () => this.toggle());

    // New Chat button
    this.newChatBtn.addEventListener('click', () => this.createSession());

    // Click delegation on session list for select/rename/delete
    this.sessionListEl.addEventListener('click', (e) => {
      const sessionItem = e.target.closest('[data-session-id]');
      if (!sessionItem) return;
      const sessionId = sessionItem.dataset.sessionId;

      // Handle delete button
      if (e.target.classList.contains('session-delete-btn')) {
        this.deleteSession(sessionId);
        return;
      }

      // Handle rename button (or double-click, but simpler with a button)
      if (e.target.classList.contains('session-rename-btn')) {
        this._startInlineRename(sessionItem);
        return;
      }

      // Otherwise select session
      this.setActiveSession(sessionId);
    });

    // Handle inline rename submission (blur/enter)
    this.sessionListEl.addEventListener('dblclick', (e) => {
      const sessionItem = e.target.closest('[data-session-id]');
      if (!sessionItem) return;
      // Only if not already editing (prevent duplicate)
      if (!sessionItem.querySelector('.session-title-input')) {
        this._startInlineRename(sessionItem);
      }
    });
  }

  /** Load sessions from localStorage */
  _loadSessions() {
    try {
      const data = localStorage.getItem(this.storageKey);
      if (data) {
        const parsed = JSON.parse(data);
        this.sessions = parsed.sessions || [];
        this.activeSessionId = parsed.activeSessionId || null;
      }
    } catch (err) {
      console.warn('Failed to load sessions from localStorage:', err);
      this.sessions = [];
      this.activeSessionId = null;
    }
  }

  /** Persist sessions and active state to localStorage */
  _persistSessions() {
    try {
      const data = JSON.stringify({
        sessions: this.sessions,
        activeSessionId: this.activeSessionId,
      });
      localStorage.setItem(this.storageKey, data);
    } catch (err) {
      console.error('Failed to persist sessions:', err);
    }
  }

  /** Render the session list based on current sessions array */
  _renderSessions() {
    if (!this.sessionListEl) return;

    // Clear current list, keeping any non-session child elements (like placeholders)
    const placeholder = this.sessionListEl.querySelector('.session-placeholder');
    this.sessionListEl.innerHTML = '';

    if (this.sessions.length === 0) {
      // Show placeholder if exists, else create one
      if (placeholder) {
        this.sessionListEl.appendChild(placeholder);
      } else {
        const empty = document.createElement('div');
        empty.className = 'session-placeholder';
        empty.textContent = 'No sessions yet. Start a new chat!';
        this.sessionListEl.appendChild(empty);
      }
      return;
    }

    // Create DOM elements for each session
    this.sessions.forEach(session => {
      const item = document.createElement('div');
      item.className = 'session-item';
      item.dataset.sessionId = session.id;

      // Title
      const titleSpan = document.createElement('span');
      titleSpan.className = 'session-title';
      titleSpan.textContent = session.title;
      item.appendChild(titleSpan);

      // Action buttons container
      const actions = document.createElement('div');
      actions.className = 'session-actions';

      // Rename button
      const renameBtn = document.createElement('button');
      renameBtn.className = 'session-rename-btn';
      renameBtn.title = 'Rename';
      renameBtn.innerHTML = '✎'; // Pencil icon
      actions.appendChild(renameBtn);

      // Delete button
      const deleteBtn = document.createElement('button');
      deleteBtn.className = 'session-delete-btn';
      deleteBtn.title = 'Delete';
      deleteBtn.innerHTML = '🗑'; // Trash icon
      actions.appendChild(deleteBtn);

      item.appendChild(actions);
      this.sessionListEl.appendChild(item);
    });

    this._highlightActiveSession();
  }

  /** Highlight the active session in the list */
  _highlightActiveSession() {
    if (!this.sessionListEl) return;
    // Remove active class from all items
    this.sessionListEl.querySelectorAll('.session-item.active')
      .forEach(el => el.classList.remove('active'));

    // Add active class to current
    if (this.activeSessionId) {
      const activeItem = this.sessionListEl.querySelector(
        `[data-session-id="${this.activeSessionId}"]`
      );
      if (activeItem) {
        activeItem.classList.add('active');
      }
    }
  }

  /** Update sidebar CSS classes based on isOpen state */
  _updateSidebarState() {
    if (!this.sidebar) return;
    this.sidebar.classList.toggle('sidebar--closed', !this.isOpen);
    this.sidebar.classList.toggle('sidebar--open', this.isOpen);
  }

  /** Start inline rename mode on a session item */
  _startInlineRename(sessionItem) {
    const titleSpan = sessionItem.querySelector('.session-title');
    if (!titleSpan) return;
    const currentTitle = titleSpan.textContent;

    // Replace span with input
    const input = document.createElement('input');
    input.type = 'text';
    input.className = 'session-title-input';
    input.value = currentTitle;
    input.setAttribute('aria-label', 'Session title');
    titleSpan.replaceWith(input);
    input.focus();
    input.select();

    const sessionId = sessionItem.dataset.sessionId;

    // Function to finish rename
    const finishRename = () => {
      const newTitle = input.value.trim();
      if (newTitle && newTitle !== currentTitle) {
        this.renameSession(sessionId, newTitle);
      } else {
        // Revert to original
        this._renderSessions();
      }
    };

    // Handle blur and Enter key
    input.addEventListener('blur', finishRename);
    input.addEventListener('keydown', (e) => {
      if (e.key === 'Enter') {
        e.preventDefault();
        input.blur(); // triggers finishRename
      } else if (e.key === 'Escape') {
        e.preventDefault();
        // Revert without saving
        this._renderSessions();
      }
    });

    // Cleanup if user clicks outside (blur already handles most cases)
  }
}

export default SidebarManager;