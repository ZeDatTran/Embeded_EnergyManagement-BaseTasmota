"use client"

import { useState, useRef, useEffect, useCallback } from "react"

//  Types 
interface Message {
  id: string
  role: "user" | "assistant"
  content: string
  timestamp: Date
  isError?: boolean
}

// Constants 
const BACKEND_URL = process.env.NEXT_PUBLIC_BACKEND_URL ?? "http://localhost:5000"
const SESSION_KEY = "chatbot_session_id"

function getOrCreateSessionId(): string {
  if (typeof window === "undefined") return "ssr-session"
  let id = sessionStorage.getItem(SESSION_KEY)
  if (!id) {
    id = `sess-${Date.now()}-${Math.random().toString(36).slice(2, 9)}`
    sessionStorage.setItem(SESSION_KEY, id)
  }
  return id
}

// Markdown-lite renderer 
function renderMarkdown(text: string): string {
  return text
    .replace(/\*\*(.+?)\*\*/g, "<strong>$1</strong>")
    .replace(/\*(.+?)\*/g, "<em>$1</em>")
    .replace(/`(.+?)`/g, '<code class="inline-code">$1</code>')
    .replace(/\n/g, "<br/>")
}

// Bubble component
function ChatBubble({ msg }: { msg: Message }) {
  const isUser = msg.role === "user"
  const time = msg.timestamp.toLocaleTimeString("vi-VN", { hour: "2-digit", minute: "2-digit" })

  return (
    <div className={`chat-bubble-row ${isUser ? "row-user" : "row-assistant"}`}>
      {!isUser && (
        <div className="avatar-bot" aria-label="Energy AI avatar">
          ⚡
        </div>
      )}
      <div className={`bubble ${isUser ? "bubble-user" : "bubble-assistant"} ${msg.isError ? "bubble-error" : ""}`}>
        {isUser ? (
          <span>{msg.content}</span>
        ) : (
          <span dangerouslySetInnerHTML={{ __html: renderMarkdown(msg.content) }} />
        )}
        <div className="bubble-time">{time}</div>
      </div>
    </div>
  )
}

// Typing indicator 
function TypingIndicator() {
  return (
    <div className="chat-bubble-row row-assistant">
      <div className="avatar-bot">⚡</div>
      <div className="bubble bubble-assistant typing-bubble">
        <span className="dot" />
        <span className="dot" />
        <span className="dot" />
      </div>
    </div>
  )
}

// Suggestions 
const SUGGESTIONS = [
  "Liệt kê tất cả thiết bị",
  "Tổng tiêu thụ hôm nay là bao nhiêu?",
  "Tính tiền điện tháng này",
  "Bật tất cả thiết bị",
]

// Main widget 
export function ChatWidget() {
  const [open, setOpen] = useState(false)
  const [messages, setMessages] = useState<Message[]>([
    {
      id: "welcome",
      role: "assistant",
      content:
        "Xin chào! Tôi là **Energy AI** 👋\nTôi có thể giúp bạn:\n• ⚡ Điều khiển thiết bị bật/tắt\n• 📊 Xem tiêu thụ điện & tiền điện\n• 🔌 Tra thông số điện tức thời\n• 💡 Tư vấn tiết kiệm điện\n\nBạn muốn làm gì?",
      timestamp: new Date(),
    },
  ])
  const [input, setInput] = useState("")
  const [loading, setLoading] = useState(false)
  const [sessionId] = useState(getOrCreateSessionId)
  const messagesEndRef = useRef<HTMLDivElement>(null)
  const inputRef = useRef<HTMLTextAreaElement>(null)

  // Auto-scroll
  useEffect(() => {
    messagesEndRef.current?.scrollIntoView({ behavior: "smooth" })
  }, [messages, loading])

  // Focus input when opened
  useEffect(() => {
    if (open) setTimeout(() => inputRef.current?.focus(), 150)
  }, [open])

  const sendMessage = useCallback(
    async (text?: string) => {
      const content = (text ?? input).trim()
      if (!content || loading) return

      const userMsg: Message = {
        id: `u-${Date.now()}`,
        role: "user",
        content,
        timestamp: new Date(),
      }
      setMessages((prev) => [...prev, userMsg])
      setInput("")
      setLoading(true)

      const controller = new AbortController()
      const timeoutId = setTimeout(() => controller.abort(), 120_000) // 120s timeout

      try {
        const res = await fetch(`${BACKEND_URL}/api/chat`, {
          method: "POST",
          headers: { "Content-Type": "application/json" },
          body: JSON.stringify({ message: content, session_id: sessionId }),
          signal: controller.signal,
        })
        clearTimeout(timeoutId)
        const data = await res.json()
        const reply = data.reply || data.message || "Không có phản hồi từ AI."
        setMessages((prev) => [
          ...prev,
          {
            id: `a-${Date.now()}`,
            role: "assistant",
            content: reply,
            timestamp: new Date(),
            isError: data.status !== "success",
          },
        ])
      } catch (err: unknown) {
        clearTimeout(timeoutId)
        const isTimeout = err instanceof Error && err.name === "AbortError"
        setMessages((prev) => [
          ...prev,
          {
            id: `err-${Date.now()}`,
            role: "assistant",
            content: isTimeout
              ? "⏱️ Yêu cầu mất quá nhiều thời gian (>120s). AI đang xử lý nhiều dữ liệu — thử lại hoặc đặt câu hỏi đơn giản hơn."
              : "❌ Lỗi kết nối backend. Vui lòng kiểm tra server đang chạy.",
            timestamp: new Date(),
            isError: true,
          },
        ])
      } finally {
        setLoading(false)
        setTimeout(() => inputRef.current?.focus(), 100)
      }
    },
    [input, loading, sessionId],
  )

  const handleKeyDown = (e: React.KeyboardEvent<HTMLTextAreaElement>) => {
    if (e.key === "Enter" && !e.shiftKey) {
      e.preventDefault()
      sendMessage()
    }
  }

  const clearChat = () => {
    setMessages([
      {
        id: "welcome-reset",
        role: "assistant",
        content: "Cuộc trò chuyện đã được xóa. Bắt đầu lại nhé! ✨",
        timestamp: new Date(),
      },
    ])
    fetch(`${BACKEND_URL}/api/chat/sessions/${sessionId}`, { method: "DELETE" }).catch(() => { })
  }

  return (
    <>
      {/* ── Styles ── */}
      <style>{`
        /* FAB Button */
        .chat-fab {
          position: fixed;
          bottom: 28px;
          right: 28px;
          z-index: 9999;
          width: 60px;
          height: 60px;
          border-radius: 50%;
          background: linear-gradient(135deg, #6366f1, #8b5cf6);
          border: none;
          cursor: pointer;
          display: flex;
          align-items: center;
          justify-content: center;
          font-size: 26px;
          box-shadow: 0 8px 32px rgba(99,102,241,0.45);
          transition: transform 0.2s, box-shadow 0.2s;
        }
        .chat-fab:hover { transform: scale(1.1); box-shadow: 0 12px 40px rgba(99,102,241,0.6); }
        .chat-fab-badge {
          position: absolute;
          top: -2px; right: -2px;
          background: #10b981;
          width: 14px; height: 14px;
          border-radius: 50%;
          border: 2px solid white;
          animation: pulse-dot 2s infinite;
        }
        @keyframes pulse-dot {
          0%,100% { transform: scale(1); opacity: 1; }
          50% { transform: scale(1.3); opacity: 0.7; }
        }

        /* Panel */
        .chat-panel {
          position: fixed;
          bottom: 100px;
          right: 28px;
          z-index: 9998;
          width: 380px;
          max-height: 600px;
          border-radius: 20px;
          background: #0f172a;
          border: 1px solid rgba(99,102,241,0.3);
          box-shadow: 0 24px 80px rgba(0,0,0,0.6);
          display: flex;
          flex-direction: column;
          overflow: hidden;
          transition: opacity 0.2s, transform 0.25s;
        }
        .chat-panel.closed {
          opacity: 0;
          transform: translateY(16px) scale(0.97);
          pointer-events: none;
        }
        @media (max-width: 480px) {
          .chat-panel {
            right: 12px; left: 12px; width: auto; bottom: 90px;
          }
        }

        /* Header */
        .chat-header {
          display: flex;
          align-items: center;
          gap: 10px;
          padding: 14px 16px;
          background: linear-gradient(135deg, #1e1b4b, #312e81);
          border-bottom: 1px solid rgba(99,102,241,0.25);
        }
        .chat-header-icon {
          font-size: 22px;
          background: rgba(99,102,241,0.2);
          border-radius: 10px;
          width: 38px; height: 38px;
          display: flex; align-items: center; justify-content: center;
        }
        .chat-header-info { flex: 1; }
        .chat-header-title {
          font-weight: 700; font-size: 14px; color: #e0e7ff;
          margin: 0;
        }
        .chat-header-sub {
          font-size: 11px; color: #6366f1; margin: 0;
          display: flex; align-items: center; gap: 4px;
        }
        .online-dot {
          width: 6px; height: 6px; border-radius: 50%;
          background: #10b981;
          display: inline-block;
          animation: pulse-dot 2s infinite;
        }
        .chat-header-btn {
          background: none; border: none; cursor: pointer;
          color: #94a3b8; font-size: 16px;
          width: 30px; height: 30px;
          border-radius: 8px;
          display: flex; align-items: center; justify-content: center;
          transition: background 0.15s, color 0.15s;
        }
        .chat-header-btn:hover { background: rgba(255,255,255,0.08); color: #e0e7ff; }

        /* Messages */
        .chat-messages {
          flex: 1;
          overflow-y: auto;
          padding: 16px 12px;
          display: flex;
          flex-direction: column;
          gap: 10px;
          scrollbar-width: thin;
          scrollbar-color: rgba(99,102,241,0.3) transparent;
        }
        .chat-messages::-webkit-scrollbar { width: 4px; }
        .chat-messages::-webkit-scrollbar-thumb { background: rgba(99,102,241,0.3); border-radius: 4px; }

        /* Bubbles */
        .chat-bubble-row {
          display: flex;
          align-items: flex-end;
          gap: 8px;
        }
        .row-user { flex-direction: row-reverse; }
        .avatar-bot {
          width: 32px; height: 32px;
          background: linear-gradient(135deg, #4f46e5, #7c3aed);
          border-radius: 10px;
          display: flex; align-items: center; justify-content: center;
          font-size: 15px; flex-shrink: 0;
        }
        .bubble {
          max-width: 80%;
          padding: 10px 14px;
          border-radius: 14px;
          font-size: 13.5px;
          line-height: 1.55;
          position: relative;
          word-break: break-word;
        }
        .bubble-user {
          background: linear-gradient(135deg, #4f46e5, #7c3aed);
          color: #f0edff;
          border-bottom-right-radius: 4px;
        }
        .bubble-assistant {
          background: #1e293b;
          color: #cbd5e1;
          border-bottom-left-radius: 4px;
          border: 1px solid rgba(99,102,241,0.15);
        }
        .bubble-error { border-color: rgba(239,68,68,0.4) !important; background: #1c1010 !important; }
        .bubble-time {
          font-size: 10px;
          color: rgba(255,255,255,0.35);
          margin-top: 4px;
          text-align: right;
        }
        .inline-code {
          background: rgba(99,102,241,0.15);
          border-radius: 4px;
          padding: 1px 5px;
          font-size: 12px;
          font-family: monospace;
          color: #a5b4fc;
        }

        /* Typing */
        .typing-bubble { display: flex; align-items: center; gap: 5px; padding: 12px 16px; }
        .dot {
          width: 7px; height: 7px; border-radius: 50%;
          background: #6366f1;
          animation: bounce-dot 1.3s infinite ease-in-out;
        }
        .dot:nth-child(2) { animation-delay: 0.2s; }
        .dot:nth-child(3) { animation-delay: 0.4s; }
        @keyframes bounce-dot {
          0%,80%,100% { transform: translateY(0); opacity: 0.4; }
          40% { transform: translateY(-6px); opacity: 1; }
        }

        /* Suggestions */
        .suggestions {
          padding: 6px 12px 10px;
          display: flex;
          flex-wrap: wrap;
          gap: 6px;
        }
        .suggestion-chip {
          background: rgba(99,102,241,0.12);
          border: 1px solid rgba(99,102,241,0.3);
          color: #a5b4fc;
          border-radius: 20px;
          padding: 4px 12px;
          font-size: 11.5px;
          cursor: pointer;
          transition: all 0.15s;
          white-space: nowrap;
        }
        .suggestion-chip:hover {
          background: rgba(99,102,241,0.28);
          border-color: #6366f1;
          color: #e0e7ff;
        }

        /* Input */
        .chat-input-area {
          padding: 10px 12px 14px;
          border-top: 1px solid rgba(99,102,241,0.15);
          background: #0f172a;
          display: flex;
          gap: 8px;
          align-items: flex-end;
        }
        .chat-textarea {
          flex: 1;
          background: #1e293b;
          border: 1px solid rgba(99,102,241,0.25);
          border-radius: 12px;
          padding: 10px 13px;
          color: #e2e8f0;
          font-size: 13.5px;
          resize: none;
          max-height: 100px;
          outline: none;
          line-height: 1.5;
          font-family: inherit;
          transition: border-color 0.15s;
        }
        .chat-textarea::placeholder { color: #475569; }
        .chat-textarea:focus { border-color: rgba(99,102,241,0.6); }
        .send-btn {
          width: 40px; height: 40px;
          background: linear-gradient(135deg, #4f46e5, #7c3aed);
          border: none;
          border-radius: 12px;
          cursor: pointer;
          display: flex; align-items: center; justify-content: center;
          font-size: 16px;
          flex-shrink: 0;
          transition: transform 0.15s, opacity 0.15s;
        }
        .send-btn:hover:not(:disabled) { transform: scale(1.08); }
        .send-btn:disabled { opacity: 0.45; cursor: not-allowed; }
      `}</style>

      {/* ── FAB Button ── */}
      <button
        className="chat-fab"
        onClick={() => setOpen((o) => !o)}
        aria-label={open ? "Đóng chatbot" : "Mở chatbot Energy AI"}
        title={open ? "Đóng" : "Energy AI Chatbot"}
      >
        {open ? "✕" : "🤖"}
        <span className="chat-fab-badge" />
      </button>

      {/* ── Chat Panel ── */}
      <div className={`chat-panel ${open ? "" : "closed"}`} role="dialog" aria-label="Energy AI Chatbot">
        {/* Header */}
        <div className="chat-header">
          <div className="chat-header-icon">⚡</div>
          <div className="chat-header-info">
            <p className="chat-header-title">Energy AI</p>
            <p className="chat-header-sub">
              <span className="online-dot" />
              Gemini · Luôn sẵn sàng
            </p>
          </div>
          <button className="chat-header-btn" onClick={clearChat} title="Xóa lịch sử chat">
            🗑
          </button>
          <button className="chat-header-btn" onClick={() => setOpen(false)} title="Đóng">
            ✕
          </button>
        </div>

        {/* Messages */}
        <div className="chat-messages" role="log" aria-live="polite">
          {messages.map((m) => (
            <ChatBubble key={m.id} msg={m} />
          ))}
          {loading && <TypingIndicator />}
          <div ref={messagesEndRef} />
        </div>

        {/* Quick suggestions (only show when no conversation yet) */}
        {messages.length <= 1 && !loading && (
          <div className="suggestions">
            {SUGGESTIONS.map((s) => (
              <button
                key={s}
                className="suggestion-chip"
                onClick={() => sendMessage(s)}
                disabled={loading}
              >
                {s}
              </button>
            ))}
          </div>
        )}

        {/* Input */}
        <div className="chat-input-area">
          <textarea
            ref={inputRef}
            className="chat-textarea"
            placeholder="Nhập câu hỏi... (Enter để gửi)"
            value={input}
            rows={1}
            onChange={(e) => {
              setInput(e.target.value)
              // Auto-resize
              e.target.style.height = "auto"
              e.target.style.height = `${Math.min(e.target.scrollHeight, 100)}px`
            }}
            onKeyDown={handleKeyDown}
            disabled={loading}
            aria-label="Nhập tin nhắn"
          />
          <button
            className="send-btn"
            onClick={() => sendMessage()}
            disabled={loading || !input.trim()}
            aria-label="Gửi tin nhắn"
            title="Gửi (Enter)"
          >
            {loading ? "⏳" : "➤"}
          </button>
        </div>
      </div>
    </>
  )
}
