/**
 * ClawDesk AI Chat Widget - Premium Edition
 * Zero dependencies, production-ready, <20KB
 * Embed: <script src="/widget.js" data-agent="AGENT_ID" data-color="#818cf8" data-theme="dark"></script>
 */
(function() {
    'use strict';

    // Config from script tag
    const script = document.currentScript;
    const AGENT_ID = script?.getAttribute('data-agent') || '';
    const WIDGET_ID = script?.getAttribute('data-widget') || '';
    const API_BASE = script?.src ? new URL(script.src).origin : '';
    const PRIMARY_COLOR = script?.getAttribute('data-color') || '#818cf8';
    const THEME = script?.getAttribute('data-theme') || 'dark';
    const PRE_CHAT_FORM = script?.getAttribute('data-prechat') === 'true';

    if (!AGENT_ID) { console.warn('[ClawDesk] Missing data-agent'); return; }

    // State
    let isOpen = false;
    let messages = [];
    let agentInfo = null;
    let isTyping = false;
    let unreadCount = 0;
    let lastMessageTime = 0;
    let userInfo = null;
    
    const senderId = localStorage.getItem('_claw_sid') || (() => {
        const id = 'w_' + Date.now() + '_' + Math.random().toString(36).substring(2, 9);
        localStorage.setItem('_claw_sid', id);
        return id;
    })();

    // Load message history from localStorage
    try {
        const saved = localStorage.getItem('_claw_history_' + AGENT_ID);
        if (saved) {
            const parsed = JSON.parse(saved);
            if (Array.isArray(parsed)) messages = parsed.slice(-50);
        }
    } catch(e) {}

    // Load user info
    try {
        const saved = localStorage.getItem('_claw_user_' + AGENT_ID);
        if (saved) userInfo = JSON.parse(saved);
    } catch(e) {}

    // Emojis
    const EMOJIS = ['😊','😃','😄','😁','👍','👏','🙏','❤️','💯','🎉','🔥','✨','💪','👌','✅','🤔','😅','😂','🤗','😎','🙌','💡','⚡','🎯','🚀','⭐','💖','🌟','😍'];

    // Styles
    const isDark = THEME === 'dark';
    const CSS = `
        :root {
            --claw-primary: ${PRIMARY_COLOR};
            --claw-bg: ${isDark ? '#18181b' : '#ffffff'};
            --claw-bg2: ${isDark ? '#27272a' : '#f4f4f5'};
            --claw-bg3: ${isDark ? '#3f3f46' : '#e4e4e7'};
            --claw-text: ${isDark ? '#e4e4e7' : '#18181b'};
            --claw-muted: ${isDark ? '#a1a1aa' : '#71717a'};
            --claw-border: ${isDark ? '#3f3f46' : '#d4d4d8'};
        }

        #claw-root * { box-sizing: border-box; }
        #claw-root { font-family: -apple-system, BlinkMacSystemFont, 'Segoe UI', system-ui, sans-serif; font-size: 14px; line-height: 1.5; }

        #claw-bubble {
            position: fixed; bottom: 24px; right: 24px; z-index: 99998;
            width: 60px; height: 60px; border-radius: 50%;
            background: var(--claw-primary); color: #fff;
            display: flex; align-items: center; justify-content: center;
            cursor: pointer; box-shadow: 0 4px 24px rgba(129,140,248,.4);
            transition: all .3s; border: none; font-size: 26px;
        }
        #claw-bubble:hover { transform: scale(1.08); box-shadow: 0 6px 32px rgba(129,140,248,.5); }
        #claw-bubble.open { transform: rotate(45deg); }
        
        .claw-badge {
            position: absolute; top: -4px; right: -4px;
            background: #ef4444; color: #fff; border-radius: 12px;
            min-width: 20px; height: 20px; padding: 0 6px;
            font-size: 11px; font-weight: 700; line-height: 20px;
            text-align: center; box-shadow: 0 2px 8px rgba(0,0,0,.3);
        }

        #claw-window {
            position: fixed; bottom: 96px; right: 24px; z-index: 99999;
            width: 380px; max-width: calc(100vw - 32px); height: 600px; max-height: calc(100vh - 120px);
            background: var(--claw-bg); border-radius: 16px;
            box-shadow: 0 12px 48px rgba(0,0,0,.5); border: 1px solid var(--claw-border);
            display: none; flex-direction: column; overflow: hidden;
            animation: clawSlideUp .25s ease;
        }
        #claw-window.visible { display: flex; }
        #claw-window.fullscreen { bottom: 0; right: 0; width: 100vw; height: 100vh; max-width: 100vw; max-height: 100vh; border-radius: 0; }

        @keyframes clawSlideUp { from { opacity: 0; transform: translateY(16px); } to { opacity: 1; transform: translateY(0); } }

        @media (max-width: 480px) {
            #claw-window { bottom: 0; right: 0; width: 100vw; height: 100vh; max-width: 100vw; max-height: 100vh; border-radius: 0; }
            #claw-bubble { bottom: 16px; right: 16px; }
        }

        .claw-header {
            background: var(--claw-primary); color: #fff; padding: 16px;
            display: flex; align-items: center; gap: 12px;
            border-bottom: 1px solid rgba(255,255,255,.1);
        }
        .claw-avatar {
            width: 40px; height: 40px; border-radius: 50%;
            background: rgba(255,255,255,.2); display: flex; align-items: center; justify-content: center;
            font-size: 20px; flex-shrink: 0; overflow: hidden;
        }
        .claw-avatar img { width: 100%; height: 100%; object-fit: cover; }
        .claw-header-info { flex: 1; min-width: 0; }
        .claw-agent-name { font-weight: 600; font-size: 15px; }
        .claw-status { font-size: 12px; opacity: .85; display: flex; align-items: center; gap: 6px; }
        .claw-status-dot { width: 8px; height: 8px; border-radius: 50%; background: #22c55e; }
        .claw-status-dot.offline { background: #71717a; }
        .claw-close { background: none; border: none; color: #fff; cursor: pointer; font-size: 24px; opacity: .8; padding: 0; width: 32px; height: 32px; border-radius: 50%; transition: all .2s; }
        .claw-close:hover { opacity: 1; background: rgba(255,255,255,.15); }

        .claw-messages {
            flex: 1; overflow-y: auto; padding: 16px; display: flex; flex-direction: column; gap: 12px;
            scroll-behavior: smooth;
        }
        .claw-message { display: flex; gap: 8px; max-width: 85%; animation: clawFadeIn .3s; }
        .claw-message.user { align-self: flex-end; flex-direction: row-reverse; }
        .claw-message-avatar { width: 32px; height: 32px; border-radius: 50%; background: var(--claw-bg3); flex-shrink: 0; font-size: 16px; display: flex; align-items: center; justify-content: center; }
        .claw-message-content { flex: 1; }
        .claw-message-bubble {
            background: var(--claw-bg2); color: var(--claw-text); padding: 10px 14px; border-radius: 16px; word-wrap: break-word;
        }
        .claw-message.user .claw-message-bubble { background: var(--claw-primary); color: #fff; }
        .claw-message-time { font-size: 11px; color: var(--claw-muted); margin-top: 4px; padding: 0 4px; }
        .claw-typing { background: var(--claw-bg2); padding: 10px 14px; border-radius: 16px; display: inline-flex; gap: 4px; }
        .claw-typing span { width: 6px; height: 6px; border-radius: 50%; background: var(--claw-muted); animation: clawBounce 1.4s infinite ease-in-out both; }
        .claw-typing span:nth-child(1) { animation-delay: -.32s; }
        .claw-typing span:nth-child(2) { animation-delay: -.16s; }

        @keyframes clawFadeIn { from { opacity: 0; transform: translateY(8px); } to { opacity: 1; transform: translateY(0); } }
        @keyframes clawBounce { 0%, 80%, 100% { transform: scale(0); } 40% { transform: scale(1); } }

        .claw-welcome { background: var(--claw-bg2); padding: 12px; border-radius: 12px; margin-bottom: 8px; color: var(--claw-text); }
        .claw-quick-replies { display: flex; flex-wrap: wrap; gap: 8px; margin-top: 8px; }
        .claw-quick-reply { background: var(--claw-bg3); border: 1px solid var(--claw-border); color: var(--claw-text); padding: 8px 12px; border-radius: 20px; cursor: pointer; font-size: 13px; transition: all .2s; }
        .claw-quick-reply:hover { background: var(--claw-primary); color: #fff; border-color: var(--claw-primary); }

        .claw-scroll-btn {
            position: absolute; bottom: 80px; left: 50%; transform: translateX(-50%);
            background: var(--claw-primary); color: #fff; border: none; border-radius: 20px;
            padding: 8px 16px; cursor: pointer; box-shadow: 0 2px 12px rgba(0,0,0,.2);
            font-size: 12px; display: none; align-items: center; gap: 6px; z-index: 10;
        }
        .claw-scroll-btn.visible { display: flex; }

        .claw-input-area {
            border-top: 1px solid var(--claw-border); padding: 12px; display: flex; gap: 8px; align-items: flex-end; background: var(--claw-bg);
        }
        .claw-input-wrapper { flex: 1; position: relative; }
        .claw-input {
            width: 100%; background: var(--claw-bg2); border: 1px solid var(--claw-border); border-radius: 20px;
            padding: 10px 16px; color: var(--claw-text); font-size: 14px; resize: none; max-height: 120px;
            font-family: inherit; outline: none;
        }
        .claw-input:focus { border-color: var(--claw-primary); }
        .claw-btn {
            background: var(--claw-primary); color: #fff; border: none; border-radius: 50%;
            width: 40px; height: 40px; cursor: pointer; display: flex; align-items: center; justify-content: center;
            font-size: 18px; transition: all .2s; flex-shrink: 0;
        }
        .claw-btn:hover:not(:disabled) { transform: scale(1.05); }
        .claw-btn:disabled { opacity: .5; cursor: not-allowed; }
        .claw-btn-secondary { background: var(--claw-bg3); color: var(--claw-text); }
        .claw-btn-secondary:hover { background: var(--claw-bg3); opacity: .8; }

        .claw-emoji-picker {
            position: absolute; bottom: 100%; left: 0; margin-bottom: 8px;
            background: var(--claw-bg); border: 1px solid var(--claw-border); border-radius: 12px;
            padding: 8px; display: none; grid-template-columns: repeat(7, 1fr); gap: 4px;
            box-shadow: 0 4px 16px rgba(0,0,0,.2); max-width: 280px;
        }
        .claw-emoji-picker.visible { display: grid; }
        .claw-emoji { background: none; border: none; font-size: 20px; cursor: pointer; padding: 6px; border-radius: 6px; transition: all .15s; }
        .claw-emoji:hover { background: var(--claw-bg3); transform: scale(1.2); }

        .claw-footer { text-align: center; padding: 8px; font-size: 11px; color: var(--claw-muted); border-top: 1px solid var(--claw-border); }
        .claw-footer a { color: var(--claw-primary); text-decoration: none; }

        .claw-pre-chat {
            padding: 24px; display: flex; flex-direction: column; gap: 16px;
        }
        .claw-pre-chat h3 { margin: 0 0 8px 0; color: var(--claw-text); }
        .claw-pre-chat input { background: var(--claw-bg2); border: 1px solid var(--claw-border); border-radius: 8px; padding: 10px 12px; color: var(--claw-text); font-size: 14px; width: 100%; }
        .claw-pre-chat button { background: var(--claw-primary); color: #fff; border: none; border-radius: 8px; padding: 12px; cursor: pointer; font-size: 14px; font-weight: 600; }

        .claw-attachment-preview { display: flex; align-items: center; gap: 8px; padding: 8px; background: var(--claw-bg2); border-radius: 8px; margin-bottom: 8px; }
        .claw-attachment-preview img { max-width: 60px; max-height: 60px; border-radius: 4px; }
        .claw-attachment-preview button { background: none; border: none; color: var(--claw-muted); cursor: pointer; }

        /* Markdown rendering */
        .claw-md strong { font-weight: 600; }
        .claw-md em { font-style: italic; }
        .claw-md a { color: var(--claw-primary); text-decoration: underline; }
        .claw-md ul, .claw-md ol { margin: 8px 0; padding-left: 20px; }
        .claw-md li { margin: 4px 0; }
        .claw-md code { background: var(--claw-bg3); padding: 2px 6px; border-radius: 4px; font-family: monospace; font-size: 13px; }
    `;

    // Inject styles
    const styleEl = document.createElement('style');
    styleEl.textContent = CSS;
    document.head.appendChild(styleEl);

    // Create widget HTML
    const root = document.createElement('div');
    root.id = 'claw-root';
    root.innerHTML = `
        <button id="claw-bubble" aria-label="Open chat">
            💬
        </button>
        <div id="claw-window">
            <div class="claw-header">
                <div class="claw-avatar">🤖</div>
                <div class="claw-header-info">
                    <div class="claw-agent-name">AI Assistant</div>
                    <div class="claw-status"><span class="claw-status-dot"></span> Online</div>
                </div>
                <button class="claw-close" aria-label="Close">×</button>
            </div>
            <div style="position: relative; flex: 1; display: flex; flex-direction: column;">
                <div class="claw-messages" id="claw-messages"></div>
                <button class="claw-scroll-btn" id="claw-scroll-btn">↓ Tin nhắn mới</button>
            </div>
            <div class="claw-input-area">
                <div class="claw-input-wrapper">
                    <div class="claw-emoji-picker" id="claw-emoji-picker"></div>
                    <textarea class="claw-input" id="claw-input" placeholder="Nhập tin nhắn..." rows="1" aria-label="Message"></textarea>
                </div>
                <button class="claw-btn claw-btn-secondary" id="claw-emoji-btn" aria-label="Emoji">😊</button>
                <button class="claw-btn claw-btn-secondary" id="claw-attach-btn" aria-label="Attach" title="Đính kèm file">📎</button>
                <button class="claw-btn" id="claw-send-btn" aria-label="Send">➤</button>
            </div>
            <div class="claw-footer">Powered by <a href="https://clawdesk.ai" target="_blank">ClawDesk</a></div>
        </div>
    `;
    document.body.appendChild(root);

    // Elements
    const bubble = document.getElementById('claw-bubble');
    const window = document.getElementById('claw-window');
    const messagesEl = document.getElementById('claw-messages');
    const inputEl = document.getElementById('claw-input');
    const sendBtn = document.getElementById('claw-send-btn');
    const closeBtn = window.querySelector('.claw-close');
    const scrollBtn = document.getElementById('claw-scroll-btn');
    const emojiBtn = document.getElementById('claw-emoji-btn');
    const emojiPicker = document.getElementById('claw-emoji-picker');
    const attachBtn = document.getElementById('claw-attach-btn');

    // Populate emoji picker
    EMOJIS.forEach(e => {
        const btn = document.createElement('button');
        btn.className = 'claw-emoji';
        btn.textContent = e;
        btn.type = 'button';
        btn.onclick = () => {
            inputEl.value += e;
            inputEl.focus();
            emojiPicker.classList.remove('visible');
        };
        emojiPicker.appendChild(btn);
    });

    // Utility: simple markdown renderer
    function renderMarkdown(text) {
        return text
            .replace(/\*\*(.+?)\*\*/g, '<strong>$1</strong>')
            .replace(/\*(.+?)\*/g, '<em>$1</em>')
            .replace(/\[(.+?)\]\((.+?)\)/g, '<a href="$2" target="_blank">$1</a>')
            .replace(/\n- /g, '\n• ')
            .replace(/\n/g, '<br>');
    }

    // Utility: format time
    function formatTime(timestamp) {
        const d = new Date(timestamp);
        const now = new Date();
        const diff = now - d;
        if (diff < 60000) return 'Vừa xong';
        if (diff < 3600000) return Math.floor(diff/60000) + ' phút trước';
        if (d.toDateString() === now.toDateString()) return d.toLocaleTimeString('vi-VN', {hour: '2-digit', minute: '2-digit'});
        return d.toLocaleDateString('vi-VN', {day: '2-digit', month: '2-digit'}) + ' ' + d.toLocaleTimeString('vi-VN', {hour: '2-digit', minute: '2-digit'});
    }

    // Render message
    function addMessage(role, content, timestamp = Date.now()) {
        const msg = { role, content, timestamp };
        messages.push(msg);
        saveHistory();

        const div = document.createElement('div');
        div.className = 'claw-message ' + role;
        
        const avatar = document.createElement('div');
        avatar.className = 'claw-message-avatar';
        avatar.textContent = role === 'user' ? '👤' : (agentInfo?.avatar || '🤖');
        
        const contentDiv = document.createElement('div');
        contentDiv.className = 'claw-message-content';
        
        const bubble = document.createElement('div');
        bubble.className = 'claw-message-bubble claw-md';
        bubble.innerHTML = renderMarkdown(content);
        
        const time = document.createElement('div');
        time.className = 'claw-message-time';
        time.textContent = formatTime(timestamp);
        
        contentDiv.appendChild(bubble);
        contentDiv.appendChild(time);
        div.appendChild(avatar);
        div.appendChild(contentDiv);
        
        messagesEl.appendChild(div);
        scrollToBottom();

        if (role === 'assistant' && !isOpen) {
            unreadCount++;
            updateBadge();
            playSound();
        }
    }

    // Typing indicator
    function showTyping() {
        if (isTyping) return;
        isTyping = true;
        const div = document.createElement('div');
        div.className = 'claw-message assistant';
        div.id = 'claw-typing';
        div.innerHTML = `
            <div class="claw-message-avatar">${agentInfo?.avatar || '🤖'}</div>
            <div class="claw-typing"><span></span><span></span><span></span></div>
        `;
        messagesEl.appendChild(div);
        scrollToBottom();
    }

    function hideTyping() {
        isTyping = false;
        const el = document.getElementById('claw-typing');
        if (el) el.remove();
    }

    // Scroll management
    function scrollToBottom(force = false) {
        const isScrolledUp = messagesEl.scrollHeight - messagesEl.scrollTop - messagesEl.clientHeight > 100;
        if (force || !isScrolledUp) {
            messagesEl.scrollTop = messagesEl.scrollHeight;
            scrollBtn.classList.remove('visible');
        } else {
            scrollBtn.classList.add('visible');
        }
    }

    messagesEl.addEventListener('scroll', () => {
        const isScrolledUp = messagesEl.scrollHeight - messagesEl.scrollTop - messagesEl.clientHeight > 100;
        scrollBtn.classList.toggle('visible', isScrolledUp);
    });

    scrollBtn.onclick = () => scrollToBottom(true);

    // Save/load history
    function saveHistory() {
        try {
            localStorage.setItem('_claw_history_' + AGENT_ID, JSON.stringify(messages.slice(-50)));
        } catch(e) {}
    }

    // Badge
    function updateBadge() {
        let badge = bubble.querySelector('.claw-badge');
        if (unreadCount > 0) {
            if (!badge) {
                badge = document.createElement('span');
                badge.className = 'claw-badge';
                bubble.appendChild(badge);
            }
            badge.textContent = unreadCount > 9 ? '9+' : unreadCount;
        } else if (badge) {
            badge.remove();
        }
    }

    // Sound notification
    function playSound() {
        try {
            const ctx = new (window.AudioContext || window.webkitAudioContext)();
            const osc = ctx.createOscillator();
            const gain = ctx.createGain();
            osc.connect(gain);
            gain.connect(ctx.destination);
            osc.frequency.value = 800;
            gain.gain.value = 0.1;
            osc.start(ctx.currentTime);
            osc.stop(ctx.currentTime + 0.1);
        } catch(e) {}
    }

    // Fetch agent info
    async function loadAgentInfo() {
        try {
            const res = await fetch(`${API_BASE}/api/widget/${AGENT_ID}/info`);
            if (res.ok) {
                agentInfo = await res.json();
                window.querySelector('.claw-agent-name').textContent = agentInfo.name || 'AI Assistant';
                const avatarEl = window.querySelector('.claw-avatar');
                if (agentInfo.avatar) {
                    avatarEl.innerHTML = `<img src="${agentInfo.avatar}" alt="">`;
                } else {
                    avatarEl.textContent = agentInfo.emoji || '🤖';
                }
                
                // Show welcome message
                if (messages.length === 0 && agentInfo.welcome_message) {
                    const welcome = document.createElement('div');
                    welcome.className = 'claw-welcome';
                    welcome.innerHTML = renderMarkdown(agentInfo.welcome_message);
                    
                    // Quick replies
                    if (agentInfo.quick_replies && agentInfo.quick_replies.length > 0) {
                        const qr = document.createElement('div');
                        qr.className = 'claw-quick-replies';
                        agentInfo.quick_replies.forEach(reply => {
                            const btn = document.createElement('button');
                            btn.className = 'claw-quick-reply';
                            btn.textContent = reply;
                            btn.onclick = () => {
                                inputEl.value = reply;
                                sendMessage();
                            };
                            qr.appendChild(btn);
                        });
                        welcome.appendChild(qr);
                    }
                    
                    messagesEl.appendChild(welcome);
                }
            }
        } catch(e) {
            console.error('[ClawDesk] Failed to load agent info:', e);
        }
    }

    // Send message
    async function sendMessage() {
        const text = inputEl.value.trim();
        if (!text || lastMessageTime + 1000 > Date.now()) return; // Rate limit
        
        lastMessageTime = Date.now();
        inputEl.value = '';
        inputEl.style.height = 'auto';
        addMessage('user', text);
        sendBtn.disabled = true;

        try {
            showTyping();
            const res = await fetch(`${API_BASE}/api/widget/${AGENT_ID}/chat`, {
                method: 'POST',
                headers: { 'Content-Type': 'application/json' },
                body: JSON.stringify({
                    message: text,
                    sender_id: senderId,
                    user_info: userInfo
                })
            });

            hideTyping();
            
            if (res.ok) {
                const data = await res.json();
                if (data.reply) {
                    addMessage('assistant', data.reply);
                }
            } else {
                addMessage('assistant', 'Xin lỗi, đã có lỗi xảy ra. Vui lòng thử lại.');
            }
        } catch(e) {
            hideTyping();
            addMessage('assistant', 'Không thể kết nối. Vui lòng kiểm tra mạng và thử lại.');
            console.error('[ClawDesk] Send error:', e);
        } finally {
            sendBtn.disabled = false;
        }
    }

    // File upload
    async function handleFileUpload(file) {
        if (file.size > 10 * 1024 * 1024) {
            alert('File quá lớn (tối đa 10MB)');
            return;
        }

        const formData = new FormData();
        formData.append('file', file);
        formData.append('sender_id', senderId);

        try {
            const res = await fetch(`${API_BASE}/api/widget/${AGENT_ID}/upload`, {
                method: 'POST',
                body: formData
            });

            if (res.ok) {
                const data = await res.json();
                addMessage('user', `📎 ${file.name}`);
                addMessage('assistant', data.reply || 'Đã nhận file của bạn!');
            }
        } catch(e) {
            console.error('[ClawDesk] Upload error:', e);
            addMessage('assistant', 'Không thể tải file lên. Vui lòng thử lại.');
        }
    }

    // Event listeners
    bubble.onclick = () => {
        isOpen = !isOpen;
        window.classList.toggle('visible');
        bubble.classList.toggle('open');
        if (isOpen) {
            unreadCount = 0;
            updateBadge();
            inputEl.focus();
            scrollToBottom(true);
        }
    };

    closeBtn.onclick = () => {
        isOpen = false;
        window.classList.remove('visible');
        bubble.classList.remove('open');
    };

    sendBtn.onclick = sendMessage;

    inputEl.addEventListener('keydown', (e) => {
        if (e.key === 'Enter' && !e.shiftKey) {
            e.preventDefault();
            sendMessage();
        }
    });

    inputEl.addEventListener('input', () => {
        inputEl.style.height = 'auto';
        inputEl.style.height = Math.min(inputEl.scrollHeight, 120) + 'px';
    });

    emojiBtn.onclick = (e) => {
        e.stopPropagation();
        emojiPicker.classList.toggle('visible');
    };

    document.addEventListener('click', (e) => {
        if (!emojiPicker.contains(e.target) && e.target !== emojiBtn) {
            emojiPicker.classList.remove('visible');
        }
    });

    attachBtn.onclick = () => {
        const input = document.createElement('input');
        input.type = 'file';
        input.accept = 'image/*,.pdf,.doc,.docx,.txt';
        input.onchange = (e) => {
            const file = e.target.files[0];
            if (file) handleFileUpload(file);
        };
        input.click();
    };

    // Show pre-chat form if enabled
    if (PRE_CHAT_FORM && !userInfo) {
        messagesEl.innerHTML = `
            <div class="claw-pre-chat">
                <h3>Xin chào! 👋</h3>
                <p>Vui lòng cho chúng tôi biết thông tin của bạn:</p>
                <input type="text" id="claw-name" placeholder="Tên của bạn" required>
                <input type="email" id="claw-email" placeholder="Email (tùy chọn)">
                <button id="claw-start">Bắt đầu chat</button>
            </div>
        `;
        
        document.getElementById('claw-start').onclick = () => {
            const name = document.getElementById('claw-name').value.trim();
            const email = document.getElementById('claw-email').value.trim();
            if (name) {
                userInfo = { name, email };
                localStorage.setItem('_claw_user_' + AGENT_ID, JSON.stringify(userInfo));
                messagesEl.innerHTML = '';
                loadAgentInfo();
            }
        };
    } else {
        // Load chat history
        messages.forEach(m => {
            const div = document.createElement('div');
            div.className = 'claw-message ' + m.role;
            div.innerHTML = `
                <div class="claw-message-avatar">${m.role === 'user' ? '👤' : (agentInfo?.avatar || '🤖')}</div>
                <div class="claw-message-content">
                    <div class="claw-message-bubble claw-md">${renderMarkdown(m.content)}</div>
                    <div class="claw-message-time">${formatTime(m.timestamp)}</div>
                </div>
            `;
            messagesEl.appendChild(div);
        });
        loadAgentInfo();
    }

    // Keyboard navigation
    window.addEventListener('keydown', (e) => {
        if (e.key === 'Escape' && isOpen) {
            isOpen = false;
            window.classList.remove('visible');
            bubble.classList.remove('open');
        }
    });

    // Poll for new messages (staff replies) every 3 seconds when open
    let pollInterval;
    let lastPollTime = new Date().toISOString();
    let conversationId = null;

    async function pollNewMessages() {
        if (!isOpen || !conversationId) return;
        
        try {
            const res = await fetch(`${API_BASE}/api/agents/${AGENT_ID}/conversations/${conversationId}/new-messages?after=${encodeURIComponent(lastPollTime)}`);
            if (res.ok) {
                const data = await res.json();
                if (data.messages && data.messages.length > 0) {
                    data.messages.forEach(msg => {
                        if (msg.role === 'assistant' && !messages.some(m => m.timestamp === new Date(msg.created_at).getTime())) {
                            addMessage('assistant', msg.content, new Date(msg.created_at).getTime());
                        }
                    });
                    lastPollTime = new Date().toISOString();
                }
            }
        } catch(e) {
            console.error('[ClawDesk] Poll error:', e);
        }
    }

    // Start/stop polling
    function startPolling() {
        if (!pollInterval) {
            pollInterval = setInterval(pollNewMessages, 3000);
        }
    }

    function stopPolling() {
        if (pollInterval) {
            clearInterval(pollInterval);
            pollInterval = null;
        }
    }

    // Update bubble click to start polling
    const originalBubbleClick = bubble.onclick;
    bubble.onclick = () => {
        originalBubbleClick();
        if (isOpen) {
            startPolling();
        } else {
            stopPolling();
        }
    };

    // Extract conversation ID from chat response
    const originalSendMessage = sendMessage;
    sendMessage = async function() {
        const text = inputEl.value.trim();
        if (!text || lastMessageTime + 1000 > Date.now()) return;
        
        lastMessageTime = Date.now();
        inputEl.value = '';
        inputEl.style.height = 'auto';
        addMessage('user', text);
        sendBtn.disabled = true;

        try {
            showTyping();
            const res = await fetch(`${API_BASE}/api/widget/${AGENT_ID}/chat`, {
                method: 'POST',
                headers: { 'Content-Type': 'application/json' },
                body: JSON.stringify({
                    message: text,
                    sender_id: senderId,
                    user_info: userInfo
                })
            });

            hideTyping();
            
            if (res.ok) {
                const data = await res.json();
                if (data.conversation_id) {
                    conversationId = data.conversation_id;
                }
                if (data.reply) {
                    addMessage('assistant', data.reply);
                }
            } else {
                addMessage('assistant', 'Xin lỗi, đã có lỗi xảy ra. Vui lòng thử lại.');
            }
        } catch(e) {
            hideTyping();
            addMessage('assistant', 'Không thể kết nối. Vui lòng kiểm tra mạng và thử lại.');
            console.error('[ClawDesk] Send error:', e);
        } finally {
            sendBtn.disabled = false;
        }
    };

    console.log('[ClawDesk] Widget loaded for agent:', AGENT_ID);
})();
