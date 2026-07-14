import { useState, useRef, useEffect, useCallback } from 'react';
import ReactMarkdown from 'react-markdown';
import './App.css';

function App() {
  /* ─── Session State ─────────────────────────────── */
  const [sessions, setSessions] = useState(() => {
    const saved = localStorage.getItem('chat_sessions');
    return saved ? JSON.parse(saved) : [];
  });
  const [currentSessionId, setCurrentSessionId] = useState(() =>
    localStorage.getItem('current_session_id') || null
  );
  const [inputValue, setInputValue] = useState('');
  const [isTyping, setIsTyping] = useState(false);
  const [editingSessionId, setEditingSessionId] = useState(null);
  const [editNameValue, setEditNameValue] = useState('');

  /* ─── Upload State ──────────────────────────────── */
  const [showUpload, setShowUpload] = useState(false);
  const [isDragging, setIsDragging] = useState(false);
  const [uploadStatus, setUploadStatus] = useState(null); // null | 'uploading' | 'success' | 'error'
  const [uploadMessage, setUploadMessage] = useState('');
  const [documents, setDocuments] = useState([]);
  const fileInputRef = useRef(null);

  const messagesEndRef = useRef(null);
  const editInputRef = useRef(null);

  /* ─── Init ──────────────────────────────────────── */
  useEffect(() => {
    if (sessions.length === 0) handleNewChat();
    else if (!currentSessionId && sessions.length > 0) setCurrentSessionId(sessions[0].id);
  }, []);

  useEffect(() => {
    localStorage.setItem('chat_sessions', JSON.stringify(sessions));
    if (currentSessionId) localStorage.setItem('current_session_id', currentSessionId);
  }, [sessions, currentSessionId]);

  useEffect(() => {
    if (editingSessionId && editInputRef.current) editInputRef.current.focus();
  }, [editingSessionId]);

  useEffect(() => {
    messagesEndRef.current?.scrollIntoView({ behavior: 'smooth' });
  }, [sessions, isTyping]);

  /* ─── Load documents list from backend ─────────── */
  const fetchDocuments = useCallback(async () => {
    try {
      const res = await fetch('http://127.0.0.1:8000/documents');
      const data = await res.json();
      setDocuments(data.documents || []);
    } catch { /* silently ignore – server may be starting */ }
  }, []);

  useEffect(() => {
    fetchDocuments();
  }, [fetchDocuments]);

  /* ─── Session helpers ───────────────────────────── */
  const currentSession = sessions.find(s => s.id === currentSessionId) || { messages: [] };

  const handleNewChat = () => {
    const newId = 'session_' + Math.random().toString(36).substr(2, 9);
    const newSession = {
      id: newId,
      name: `Chat ${sessions.length + 1}`,
      messages: [{ text: 'Hello! Upload your documents using the ☁ button, then ask me anything about them.', sender: 'bot' }],
    };
    setSessions(prev => [newSession, ...prev]);
    setCurrentSessionId(newId);
  };

  const deleteSession = (e, id) => {
    e.stopPropagation();
    const next = sessions.filter(s => s.id !== id);
    setSessions(next);
    if (currentSessionId === id) {
      if (next.length > 0) setCurrentSessionId(next[0].id);
      else handleNewChat();
    }
  };

  const startEditing = (e, session) => {
    e.stopPropagation();
    setEditingSessionId(session.id);
    setEditNameValue(session.name);
  };

  const saveEditedName = (id) => {
    if (editNameValue.trim()) {
      setSessions(prev => prev.map(s => s.id === id ? { ...s, name: editNameValue.trim() } : s));
    }
    setEditingSessionId(null);
  };

  const handleEditKeyDown = (e, id) => {
    if (e.key === 'Enter') saveEditedName(id);
    else if (e.key === 'Escape') setEditingSessionId(null);
  };

  const updateLastBotMessage = (sessionId, text) => {
    setSessions(prev => prev.map(s => {
      if (s.id !== sessionId) return s;
      const msgs = [...s.messages];
      msgs[msgs.length - 1] = { ...msgs[msgs.length - 1], text };
      return { ...s, messages: msgs };
    }));
  };

  /* ─── Chat submit ───────────────────────────────── */
  const handleSubmit = async (e) => {
    e.preventDefault();
    const messageText = inputValue.trim();
    if (!messageText || !currentSessionId) return;

    let newTitle = null;
    if (currentSession.name.startsWith('Chat ') && currentSession.messages.length <= 2)
      newTitle = messageText.slice(0, 30) + (messageText.length > 30 ? '...' : '');

    const newMessages = [
      ...currentSession.messages,
      { text: messageText, sender: 'user' },
      { text: '', sender: 'bot' },
    ];

    setSessions(prev => prev.map(s =>
      s.id === currentSessionId
        ? { ...s, messages: newMessages, name: newTitle || s.name }
        : s
    ));
    setInputValue('');
    setIsTyping(true);

    try {
      const fd = new FormData();
      fd.append('message', messageText);
      fd.append('session_id', currentSessionId);

      const response = await fetch('http://127.0.0.1:8000/chat', { method: 'POST', body: fd });
      if (!response.ok) throw new Error();
      setIsTyping(false);

      const reader = response.body.getReader();
      const decoder = new TextDecoder('utf-8');
      let botResponse = '';
      let done = false;

      while (!done) {
        const { value, done: doneReading } = await reader.read();
        done = doneReading;
        if (value) {
          botResponse += decoder.decode(value, { stream: true });
          updateLastBotMessage(currentSessionId, botResponse);
        }
      }
    } catch {
      updateLastBotMessage(currentSessionId, 'Sorry, I encountered an error connecting to the server.');
      setIsTyping(false);
    }
  };

  /* ─── Upload helpers ────────────────────────────── */
  const uploadFile = async (file) => {
    if (!file) return;
    const isValid = file.name.endsWith('.pdf') || file.name.endsWith('.txt');
    if (!isValid) {
      setUploadStatus('error');
      setUploadMessage('Only PDF and TXT files are supported.');
      return;
    }

    setUploadStatus('uploading');
    setUploadMessage(`Uploading "${file.name}"...`);

    const fd = new FormData();
    fd.append('file', file);

    try {
      const res = await fetch('http://127.0.0.1:8000/upload', { method: 'POST', body: fd });
      const data = await res.json();
      if (res.ok) {
        setUploadStatus('success');
        setUploadMessage(`✓ ${data.message} (${data.chunks_added} chunks added)`);
        fetchDocuments(); // refresh the knowledge base list
      } else {
        setUploadStatus('error');
        setUploadMessage(data.detail || 'Upload failed.');
      }
    } catch {
      setUploadStatus('error');
      setUploadMessage('Could not reach the server. Is uvicorn running?');
    }
  };

  const onDrop = (e) => {
    e.preventDefault();
    setIsDragging(false);
    const file = e.dataTransfer.files[0];
    uploadFile(file);
  };

  const onDragOver = (e) => { e.preventDefault(); setIsDragging(true); };
  const onDragLeave = () => setIsDragging(false);
  const onFileChange = (e) => uploadFile(e.target.files[0]);

  /* ─── Render ────────────────────────────────────── */
  return (
    <div className="app-container">
      {/* ── Sidebar ── */}
      <aside className="sidebar">
        <button className="new-chat-btn" onClick={handleNewChat}>+ New Chat</button>

        {/* Upload toggle button */}
        <button
          className={`upload-toggle-btn ${showUpload ? 'active' : ''}`}
          onClick={() => { setShowUpload(v => !v); setUploadStatus(null); }}
          title="Manage Knowledge Base"
        >
          ☁ Knowledge Base
        </button>

        <div className="session-list">
          {sessions.map(s => (
            <div
              key={s.id}
              className={`session-item ${s.id === currentSessionId ? 'active' : ''}`}
              onClick={() => setCurrentSessionId(s.id)}
            >
              {editingSessionId === s.id ? (
                <input
                  ref={editInputRef}
                  className="session-edit-input"
                  value={editNameValue}
                  onChange={e => setEditNameValue(e.target.value)}
                  onBlur={() => saveEditedName(s.id)}
                  onKeyDown={e => handleEditKeyDown(e, s.id)}
                />
              ) : (
                <span className="session-name" title={s.name}>{s.name}</span>
              )}
              <div className="session-actions">
                <button className="action-btn edit-btn" onClick={e => startEditing(e, s)} title="Rename">✎</button>
                <button className="action-btn delete-btn" onClick={e => deleteSession(e, s.id)} title="Delete">✕</button>
              </div>
            </div>
          ))}
        </div>
      </aside>

      {/* ── Main area ── */}
      <main className="main-content">
        <header className="app-header">
          <h1>Document Intelligence</h1>
        </header>

        {/* ── Upload Panel ── */}
        {showUpload && (
          <div className="upload-panel">
            <div
              className={`drop-zone ${isDragging ? 'dragging' : ''}`}
              onDrop={onDrop}
              onDragOver={onDragOver}
              onDragLeave={onDragLeave}
              onClick={() => fileInputRef.current?.click()}
            >
              <input
                ref={fileInputRef}
                type="file"
                accept=".pdf,.txt"
                style={{ display: 'none' }}
                onChange={onFileChange}
              />
              <div className="drop-zone-icon">📄</div>
              <p className="drop-zone-title">Drag & drop a file here</p>
              <p className="drop-zone-sub">or click to browse &nbsp;·&nbsp; PDF or TXT</p>
            </div>

            {uploadStatus && (
              <div className={`upload-status ${uploadStatus}`}>
                {uploadStatus === 'uploading' && <span className="spinner" />}
                {uploadMessage}
              </div>
            )}

            {documents.length > 0 && (
              <div className="doc-list">
                <p className="doc-list-title">📚 Knowledge Base</p>
                {documents.map((d, i) => (
                  <div key={i} className="doc-item">
                    <span className="doc-icon">📄</span>
                    <span className="doc-name" title={d}>{d}</span>
                  </div>
                ))}
              </div>
            )}
          </div>
        )}

        {/* ── Messages ── */}
        <div className="chat-container">
          <div className="messages-wrapper">
            {currentSession.messages.map((msg, index) => (
              <div key={index} className={`message-row ${msg.sender}`}>
                {msg.sender === 'bot' && (
                  <div className="avatar bot-avatar">
                    <svg viewBox="0 0 24 24" width="24" height="24" fill="currentColor">
                      <path d="M12 2a2 2 0 0 1 2 2c0 .74-.4 1.39-1 1.73V7h1a7 7 0 0 1 7 7h1a1 1 0 0 1 1 1v3a1 1 0 0 1-1 1h-1v1a2 2 0 0 1-2 2H5a2 2 0 0 1-2-2v-1H2a1 1 0 0 1-1-1v-3a1 1 0 0 1 1-1h1a7 7 0 0 1 7-7h1V5.73A2 2 0 0 1 12 2z" />
                    </svg>
                  </div>
                )}
                <div className="message-content">
                  {msg.sender === 'bot' && msg.text !== '' ? (
                    <ReactMarkdown>{msg.text}</ReactMarkdown>
                  ) : (
                    <p>{msg.text}</p>
                  )}
                </div>
              </div>
            ))}

            {isTyping && (
              <div className="message-row bot typing">
                <div className="avatar bot-avatar">
                  <svg viewBox="0 0 24 24" width="24" height="24" fill="currentColor">
                    <path d="M12 2a2 2 0 0 1 2 2c0 .74-.4 1.39-1 1.73V7h1a7 7 0 0 1 7 7h1a1 1 0 0 1 1 1v3a1 1 0 0 1-1 1h-1v1a2 2 0 0 1-2 2H5a2 2 0 0 1-2-2v-1H2a1 1 0 0 1-1-1v-3a1 1 0 0 1 1-1h1a7 7 0 0 1 7-7h1V5.73A2 2 0 0 1 12 2z" />
                  </svg>
                </div>
                <div className="message-content typing-indicator">
                  <span /><span /><span />
                </div>
              </div>
            )}
            <div ref={messagesEndRef} />
          </div>
        </div>

        {/* ── Input ── */}
        <div className="input-container">
          <form onSubmit={handleSubmit} className="input-form">
            <input
              type="text"
              value={inputValue}
              onChange={e => setInputValue(e.target.value)}
              placeholder="Ask about your documents..."
              autoComplete="off"
              disabled={isTyping}
            />
            <button type="submit" disabled={!inputValue.trim() || isTyping}>
              <svg viewBox="0 0 24 24" width="24" height="24" fill="currentColor">
                <path d="M2.01 21L23 12 2.01 3 2 10l15 2-15 2z" />
              </svg>
            </button>
          </form>
          <p className="footer-text">Answers are grounded in your personal knowledge base only.</p>
        </div>
      </main>
    </div>
  );
}

export default App;
