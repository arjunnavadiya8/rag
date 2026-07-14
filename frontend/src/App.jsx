import { useState, useRef, useEffect } from 'react';
import ReactMarkdown from 'react-markdown';
import './App.css';

function App() {
  // Application State
  const [sessions, setSessions] = useState(() => {
    const saved = localStorage.getItem('chat_sessions');
    if (saved) return JSON.parse(saved);
    return [];
  });

  const [currentSessionId, setCurrentSessionId] = useState(() => {
    const saved = localStorage.getItem('current_session_id');
    return saved || null;
  });

  const [inputValue, setInputValue] = useState('');
  const [isTyping, setIsTyping] = useState(false);
  const [editingSessionId, setEditingSessionId] = useState(null);
  const [editNameValue, setEditNameValue] = useState('');
  
  const messagesEndRef = useRef(null);
  const editInputRef = useRef(null);

  // Initialize first session if none exists
  useEffect(() => {
    if (sessions.length === 0) {
      handleNewChat();
    } else if (!currentSessionId && sessions.length > 0) {
      setCurrentSessionId(sessions[0].id);
    }
  }, []);

  // Save to localStorage when state changes
  useEffect(() => {
    localStorage.setItem('chat_sessions', JSON.stringify(sessions));
    if (currentSessionId) {
      localStorage.setItem('current_session_id', currentSessionId);
    }
  }, [sessions, currentSessionId]);

  // Focus input when editing starts
  useEffect(() => {
    if (editingSessionId && editInputRef.current) {
      editInputRef.current.focus();
    }
  }, [editingSessionId]);

  const currentSession = sessions.find(s => s.id === currentSessionId) || { messages: [] };

  const scrollToBottom = () => {
    messagesEndRef.current?.scrollIntoView({ behavior: "smooth" });
  };

  useEffect(() => {
    scrollToBottom();
  }, [currentSession.messages, isTyping]);

  const handleNewChat = () => {
    const newId = "session_" + Math.random().toString(36).substr(2, 9);
    const newSession = {
      id: newId,
      name: `Chat ${sessions.length + 1}`,
      messages: [{ text: "Hello! I am your intelligent agent. I can search your documents and the web. How can I help?", sender: 'bot' }]
    };
    setSessions([newSession, ...sessions]);
    setCurrentSessionId(newId);
  };

  const deleteSession = (e, idToDelete) => {
    e.stopPropagation();
    const newSessions = sessions.filter(s => s.id !== idToDelete);
    setSessions(newSessions);
    
    // If we deleted the current active session, switch to the first available one
    if (currentSessionId === idToDelete) {
      if (newSessions.length > 0) {
        setCurrentSessionId(newSessions[0].id);
      } else {
        // If it was the last session, create a new one automatically
        handleNewChat();
      }
    }
  };

  const startEditing = (e, session) => {
    e.stopPropagation();
    setEditingSessionId(session.id);
    setEditNameValue(session.name);
  };

  const saveEditedName = (id) => {
    if (editNameValue.trim()) {
      setSessions(prev => prev.map(s => 
        s.id === id ? { ...s, name: editNameValue.trim() } : s
      ));
    }
    setEditingSessionId(null);
  };

  const handleEditKeyDown = (e, id) => {
    if (e.key === 'Enter') {
      saveEditedName(id);
    } else if (e.key === 'Escape') {
      setEditingSessionId(null);
    }
  };

  const updateSessionMessages = (sessionId, newMessages, titleUpdate = null) => {
    setSessions(prev => prev.map(s => {
      if (s.id === sessionId) {
        return {
          ...s,
          messages: newMessages,
          name: titleUpdate || s.name
        };
      }
      return s;
    }));
  };

  const handleSubmit = async (e) => {
    e.preventDefault();
    const messageText = inputValue.trim();
    if (!messageText || !currentSessionId) return;

    // Generate a title based on the first user message if it's still named "Chat X"
    let newTitle = null;
    if (currentSession.name.startsWith("Chat ") && currentSession.messages.length <= 2) {
      newTitle = messageText.slice(0, 30) + (messageText.length > 30 ? "..." : "");
    }

    const newMessages = [
      ...currentSession.messages, 
      { text: messageText, sender: 'user' },
      { text: '', sender: 'bot' } // Placeholder for streaming
    ];

    updateSessionMessages(currentSessionId, newMessages, newTitle);
    setInputValue('');
    setIsTyping(true);

    try {
      const formData = new FormData();
      formData.append('message', messageText);
      formData.append('session_id', currentSessionId);

      const response = await fetch('http://127.0.0.1:8000/chat', {
        method: 'POST',
        body: formData,
      });

      if (!response.ok) {
        throw new Error('Network response was not ok');
      }

      setIsTyping(false); // Done thinking, start receiving stream

      const reader = response.body.getReader();
      const decoder = new TextDecoder('utf-8');
      let done = false;
      let botResponse = '';
      
      while (!done) {
        const { value, done: doneReading } = await reader.read();
        done = doneReading;
        
        if (value) {
          const chunkValue = decoder.decode(value, { stream: true });
          botResponse += chunkValue;
          
          setSessions(prev => prev.map(s => {
            if (s.id === currentSessionId) {
              const updatedMessages = [...s.messages];
              const lastIndex = updatedMessages.length - 1;
              updatedMessages[lastIndex] = {
                ...updatedMessages[lastIndex],
                text: botResponse
              };
              return { ...s, messages: updatedMessages };
            }
            return s;
          }));
        }
      }
    } catch (error) {
      console.error('Error fetching chat response:', error);
      const errMsgs = [...newMessages];
      errMsgs[errMsgs.length - 1] = { text: "Sorry, I encountered an error connecting to the server.", sender: 'bot' };
      updateSessionMessages(currentSessionId, errMsgs);
      setIsTyping(false);
    }
  };

  return (
    <div className="app-container">
      {/* Sidebar for Sessions */}
      <aside className="sidebar">
        <button className="new-chat-btn" onClick={handleNewChat}>
          + New Chat
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
                  onChange={(e) => setEditNameValue(e.target.value)}
                  onBlur={() => saveEditedName(s.id)}
                  onKeyDown={(e) => handleEditKeyDown(e, s.id)}
                />
              ) : (
                <span className="session-name" title={s.name}>{s.name}</span>
              )}
              
              <div className="session-actions">
                <button 
                  className="action-btn edit-btn"
                  onClick={(e) => startEditing(e, s)}
                  title="Rename"
                >
                  ✎
                </button>
                <button 
                  className="action-btn delete-btn"
                  onClick={(e) => deleteSession(e, s.id)}
                  title="Delete"
                >
                  ✕
                </button>
              </div>
            </div>
          ))}
        </div>
      </aside>

      {/* Main Chat Area */}
      <main className="main-content">
        <header className="app-header">
          <h1>Document Intelligence</h1>
        </header>
        
        <div className="chat-container">
          <div className="messages-wrapper">
            {currentSession.messages.map((msg, index) => (
              <div key={index} className={`message-row ${msg.sender}`}>
                {msg.sender === 'bot' && (
                  <div className="avatar bot-avatar">
                    <svg viewBox="0 0 24 24" width="24" height="24" fill="currentColor">
                      <path d="M12 2a2 2 0 0 1 2 2c0 .74-.4 1.39-1 1.73V7h1a7 7 0 0 1 7 7h1a1 1 0 0 1 1 1v3a1 1 0 0 1-1 1h-1v1a2 2 0 0 1-2 2H5a2 2 0 0 1-2-2v-1H2a1 1 0 0 1-1-1v-3a1 1 0 0 1 1-1h1a7 7 0 0 1 7-7h1V5.73A2 2 0 0 1 12 2z"/>
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
                    <path d="M12 2a2 2 0 0 1 2 2c0 .74-.4 1.39-1 1.73V7h1a7 7 0 0 1 7 7h1a1 1 0 0 1 1 1v3a1 1 0 0 1-1 1h-1v1a2 2 0 0 1-2 2H5a2 2 0 0 1-2-2v-1H2a1 1 0 0 1-1-1v-3a1 1 0 0 1 1-1h1a7 7 0 0 1 7-7h1V5.73A2 2 0 0 1 12 2z"/>
                  </svg>
                </div>
                <div className="message-content typing-indicator">
                  <span></span><span></span><span></span>
                </div>
              </div>
            )}
            <div ref={messagesEndRef} />
          </div>
        </div>

        <div className="input-container">
          <form onSubmit={handleSubmit} className="input-form">
            <input
              type="text"
              value={inputValue}
              onChange={(e) => setInputValue(e.target.value)}
              placeholder="Send a message..."
              autoComplete="off"
              disabled={isTyping}
            />
            <button type="submit" disabled={!inputValue.trim() || isTyping}>
              <svg viewBox="0 0 24 24" width="24" height="24" fill="currentColor">
                <path d="M2.01 21L23 12 2.01 3 2 10l15 2-15 2z" />
              </svg>
            </button>
          </form>
          <p className="footer-text">Agentic AI can use tools. Verify important information.</p>
        </div>
      </main>
    </div>
  );
}

export default App;
