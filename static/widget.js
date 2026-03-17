/**
 * AI Agent Webchat Widget
 * Embed: <script src="https://YOUR_DOMAIN/widget.js" data-agent="AGENT_ID" data-widget="WIDGET_ID"></script>
 */
(function() {
    'use strict';

    // Config from script tag
    const script = document.currentScript;
    const AGENT_ID = script?.getAttribute('data-agent') || '';
    const WIDGET_ID = script?.getAttribute('data-widget') || '';
    const API_BASE = script?.src ? new URL(script.src).origin : '';

    if (!AGENT_ID) { console.warn('[AI Widget] Missing data-agent attribute'); return; }

    // State
    let isOpen = false;
    let messages = [];
    let senderId = localStorage.getItem('_aiw_sid') || (() => {
        const id = 'w_' + Math.random().toString(36).substring(2, 10);
        localStorage.setItem('_aiw_sid', id);
        return id;
    })();

    // Styles
    const CSS = `
        #aiw-root { --aiw-accent: #818cf8; --aiw-accent-h: #6366f1; --aiw-bg: #18181b; --aiw-bg2: #27272a; --aiw-bg3: #3f3f46; --aiw-text: #e4e4e7; --aiw-muted: #a1a1aa; --aiw-radius: 16px; font-family: 'Inter', -apple-system, BlinkMacSystemFont, 'Segoe UI', sans-serif; font-size: 14px; line-height: 1.5; }

        #aiw-bubble {
            position: fixed; bottom: 24px; right: 24px; z-index: 99998;
            width: 60px; height: 60px; border-radius: 50%;
            background: var(--aiw-accent); color: #fff;
            display: flex; align-items: center; justify-content: center;
            cursor: pointer; box-shadow: 0 4px 24px rgba(99,102,241,.4);
            transition: all .3s; border: none; font-size: 26px;
        }
        #aiw-bubble:hover { transform: scale(1.08); box-shadow: 0 6px 32px rgba(99,102,241,.5); }
        #aiw-bubble.open { transform: rotate(45deg) scale(1); }

        #aiw-window {
            position: fixed; bottom: 96px; right: 24px; z-index: 99999;
            width: 380px; max-width: calc(100vw - 32px); height: 520px; max-height: calc(100vh - 120px);
            background: var(--aiw-bg); border-radius: var(--aiw-radius);
            box-shadow: 0 12px 48px rgba(0,0,0,.5); border: 1px solid var(--aiw-bg3);
            display: none; flex-direction: column; overflow: hidden;
            animation: aiw-slideUp .25s ease;
        }
        #aiw-window.visible { display: flex; }

        @keyframes aiw-slideUp { from { opacity: 0; transform: translateY(16px); } to { opacity: 1; transform: translateY(0); } }

        .aiw-header {
            padding: 16px 20px; background: var(--aiw-bg2); border-bottom: 1px solid var(--aiw-bg3);
            display: flex; align-items: center; gap: 12px;
        }
        .aiw-header-icon { width: 36px; height: 36px; border-radius: 10px; background: var(--aiw-accent); display: flex; align-items: center; justify-content: center; font-size: 20px; }
        .aiw-header-text h4 { color: #fff; font-size: 15px; font-weight: 600; margin: 0; }
        .aiw-header-text p { color: var(--aiw-muted); font-size: 12px; margin: 0; }

        .aiw-messages {
            flex: 1; overflow-y: auto; padding: 16px; display: flex; flex-direction: column; gap: 10px;
        }
        .aiw-messages::-webkit-scrollbar { width: 4px; }
        .aiw-messages::-webkit-scrollbar-thumb { background: var(--aiw-bg3); border-radius: 4px; }

        .aiw-msg { max-width: 85%; padding: 10px 14px; border-radius: 14px; font-size: 14px; line-height: 1.5; word-break: break-word; }
        .aiw-msg.user { align-self: flex-end; background: var(--aiw-accent); color: #fff; border-bottom-right-radius: 4px; }
        .aiw-msg.assistant { align-self: flex-start; background: var(--aiw-bg2); color: var(--aiw-text); border-bottom-left-radius: 4px; }
        .aiw-msg.typing { color: var(--aiw-muted); font-style: italic; }

        .aiw-input-area {
            padding: 12px 16px; border-top: 1px solid var(--aiw-bg3); display: flex; gap: 8px; background: var(--aiw-bg);
        }
        .aiw-input {
            flex: 1; padding: 10px 14px; border-radius: 12px; border: 1px solid var(--aiw-bg3);
            background: var(--aiw-bg2); color: #fff; font-size: 14px; font-family: inherit;
            outline: none; transition: border-color .2s;
        }
        .aiw-input:focus { border-color: var(--aiw-accent); }
        .aiw-input::placeholder { color: var(--aiw-muted); }

        .aiw-send {
            width: 40px; height: 40px; border-radius: 10px; background: var(--aiw-accent);
            border: none; color: #fff; cursor: pointer; font-size: 18px;
            display: flex; align-items: center; justify-content: center;
            transition: background .2s; flex-shrink: 0;
        }
        .aiw-send:hover { background: var(--aiw-accent-h); }
        .aiw-send:disabled { opacity: .5; cursor: not-allowed; }

        .aiw-welcome { text-align: center; padding: 32px 16px; color: var(--aiw-muted); }
        .aiw-welcome .icon { font-size: 40px; margin-bottom: 12px; }
        .aiw-welcome h4 { color: var(--aiw-text); font-size: 16px; margin: 0 0 6px; }
        .aiw-welcome p { font-size: 13px; margin: 0; }

        .aiw-powered { text-align: center; padding: 6px; font-size: 11px; color: var(--aiw-muted); opacity: .6; }
    `;

    // Inject styles
    const style = document.createElement('style');
    style.textContent = CSS;
    document.head.appendChild(style);

    // Create root
    const root = document.createElement('div');
    root.id = 'aiw-root';
    root.innerHTML = `
        <div id="aiw-bubble" title="Chat với chúng tôi">💬</div>
        <div id="aiw-window">
            <div class="aiw-header">
                <div class="aiw-header-icon">🤖</div>
                <div class="aiw-header-text">
                    <h4>Hỗ trợ AI</h4>
                    <p>Thường trả lời ngay lập tức</p>
                </div>
            </div>
            <div class="aiw-messages" id="aiw-messages">
                <div class="aiw-welcome">
                    <div class="icon">👋</div>
                    <h4>Xin chào!</h4>
                    <p>Bạn cần hỗ trợ gì? Hãy nhắn tin cho chúng tôi.</p>
                </div>
            </div>
            <div class="aiw-input-area">
                <input class="aiw-input" id="aiw-input" type="text" placeholder="Nhập tin nhắn..." autocomplete="off">
                <button class="aiw-send" id="aiw-send" title="Gửi">➤</button>
            </div>
            <div class="aiw-powered">Powered by AI Agent Platform</div>
        </div>
    `;
    document.body.appendChild(root);

    // Elements
    const bubble = document.getElementById('aiw-bubble');
    const window_ = document.getElementById('aiw-window');
    const msgContainer = document.getElementById('aiw-messages');
    const input = document.getElementById('aiw-input');
    const sendBtn = document.getElementById('aiw-send');

    // Toggle
    bubble.addEventListener('click', () => {
        isOpen = !isOpen;
        window_.classList.toggle('visible', isOpen);
        bubble.classList.toggle('open', isOpen);
        bubble.textContent = isOpen ? '✕' : '💬';
        if (isOpen) input.focus();
    });

    // Send message
    async function send() {
        const text = input.value.trim();
        if (!text) return;

        input.value = '';
        addMessage('user', text);

        // Show typing
        const typingEl = addMessage('assistant', '...', true);

        try {
            const res = await fetch(`${API_BASE}/api/agents/${AGENT_ID}/chat`, {
                method: 'POST',
                headers: { 'Content-Type': 'application/json' },
                body: JSON.stringify({
                    message: text,
                    channel: 'webchat',
                    sender_id: senderId,
                    widget_id: WIDGET_ID,
                }),
            });
            const data = await res.json();
            typingEl.remove();
            if (res.ok) {
                addMessage('assistant', data.response);
            } else {
                addMessage('assistant', data.detail || 'Xin lỗi, có lỗi xảy ra.');
            }
        } catch(e) {
            typingEl.remove();
            addMessage('assistant', 'Không thể kết nối. Vui lòng thử lại.');
        }
    }

    function addMessage(role, content, typing = false) {
        // Remove welcome message on first message
        const welcome = msgContainer.querySelector('.aiw-welcome');
        if (welcome) welcome.remove();

        const div = document.createElement('div');
        div.className = `aiw-msg ${role}` + (typing ? ' typing' : '');
        div.textContent = content;
        msgContainer.appendChild(div);
        msgContainer.scrollTop = msgContainer.scrollHeight;
        return div;
    }

    sendBtn.addEventListener('click', send);
    input.addEventListener('keydown', e => { if (e.key === 'Enter' && !e.shiftKey) { e.preventDefault(); send(); } });
})();
