import { useEffect, useRef, useState } from 'react'
import './App.css'

const SESSION_KEY = 'sierra_session_id'
const API = ''

function getSessionId() {
  let id = localStorage.getItem(SESSION_KEY)
  if (!id) {
    id = crypto.randomUUID()
    localStorage.setItem(SESSION_KEY, id)
  }
  return id
}

function setSessionId(id) {
  localStorage.setItem(SESSION_KEY, id)
}

function AttachIcon() {
  return (
    <svg width="20" height="20" viewBox="0 0 24 24" fill="none" aria-hidden="true">
      <path
        d="M12 5v14M5 12h14"
        stroke="currentColor"
        strokeWidth="2"
        strokeLinecap="round"
      />
    </svg>
  )
}

function SendIcon() {
  return (
    <svg width="18" height="18" viewBox="0 0 24 24" fill="none" aria-hidden="true">
      <path
        d="M5 12h12M13 6l6 6-6 6"
        stroke="currentColor"
        strokeWidth="2"
        strokeLinecap="round"
        strokeLinejoin="round"
      />
    </svg>
  )
}

function ProductCarousel({ products }) {
  const trackRef = useRef(null)
  const [canScrollLeft, setCanScrollLeft] = useState(false)
  const [canScrollRight, setCanScrollRight] = useState(false)

  function updateScrollHints() {
    const el = trackRef.current
    if (!el) return
    setCanScrollLeft(el.scrollLeft > 4)
    setCanScrollRight(el.scrollLeft + el.clientWidth < el.scrollWidth - 4)
  }

  useEffect(() => {
    updateScrollHints()
    const el = trackRef.current
    if (!el) return
    el.addEventListener('scroll', updateScrollHints, { passive: true })
    window.addEventListener('resize', updateScrollHints)
    return () => {
      el.removeEventListener('scroll', updateScrollHints)
      window.removeEventListener('resize', updateScrollHints)
    }
  }, [products])

  return (
    <div className={`carousel-wrap ${canScrollLeft ? 'fade-left' : ''} ${canScrollRight ? 'fade-right' : ''}`}>
      <div className="carousel-track" ref={trackRef}>
        {products.map((p) => (
          <article key={p.sku} className="product-card">
            <div className="product-image">
              <img src={p.image} alt={p.name} loading="lazy" />
            </div>
            <div className="product-body">
              <h3>{p.name}</h3>
              <p className="product-desc">{p.description}</p>
              <div className="product-meta">
                <span className="sku">{p.sku}</span>
                {p.inventory > 0 ? (
                  <span className="stock">In stock</span>
                ) : (
                  <span className="stock out">Out of stock</span>
                )}
              </div>
            </div>
          </article>
        ))}
      </div>
    </div>
  )
}

export default function App() {
  const [sessionId, setSid] = useState(() => getSessionId())
  const [messages, setMessages] = useState([])
  const [input, setInput] = useState('')
  const [image, setImage] = useState(null)
  const [preview, setPreview] = useState(null)
  const [waiting, setWaiting] = useState(false)
  const [error, setError] = useState('')
  const bottomRef = useRef(null)
  const fileRef = useRef(null)

  useEffect(() => {
    let cancelled = false
    async function load() {
      try {
        const res = await fetch(`${API}/api/history`, {
          headers: { 'X-Session-Id': sessionId },
        })
        const data = await res.json()
        if (cancelled) return
        if (data.session_id && data.session_id !== sessionId) {
          setSessionId(data.session_id)
          setSid(data.session_id)
        }
        setMessages(data.messages || [])
      } catch {
        if (!cancelled) setError('Could not reach the trail basecamp (API). Is the server running?')
      }
    }
    load()
    return () => {
      cancelled = true
    }
  }, [sessionId])

  useEffect(() => {
    bottomRef.current?.scrollIntoView({ behavior: 'smooth' })
  }, [messages, waiting])

  function onPickImage(e) {
    const file = e.target.files?.[0]
    if (!file) return
    setImage(file)
    setPreview(URL.createObjectURL(file))
  }

  function openFilePicker() {
    if (waiting) return
    fileRef.current?.click()
  }

  function clearImage() {
    setImage(null)
    if (preview) URL.revokeObjectURL(preview)
    setPreview(null)
    if (fileRef.current) fileRef.current.value = ''
  }

  function useSuggestion(text) {
    setInput(text)
  }

  async function resetChat() {
    setWaiting(true)
    setError('')
    try {
      const res = await fetch(`${API}/api/reset`, {
        method: 'POST',
        headers: { 'X-Session-Id': sessionId },
      })
      const data = await res.json()
      setSessionId(data.session_id)
      setSid(data.session_id)
      setMessages([])
      clearImage()
      setInput('')
    } catch {
      setError('Reset failed — try again.')
    } finally {
      setWaiting(false)
    }
  }

  async function send() {
    const text = input.trim()
    if ((!text && !image) || waiting) return

    setWaiting(true)
    setError('')
    const optimistic = {
      role: 'user',
      content: text,
      image: preview,
    }
    setMessages((m) => [...m, optimistic])
    setInput('')

    const form = new FormData()
    form.append('message', text)
    if (image) form.append('image', image)

    try {
      const res = await fetch(`${API}/api/chat`, {
        method: 'POST',
        headers: { 'X-Session-Id': sessionId },
        body: form,
      })
      const data = await res.json()
      if (!res.ok) throw new Error(data.detail || 'Chat failed')

      if (data.session_id && data.session_id !== sessionId) {
        setSessionId(data.session_id)
        setSid(data.session_id)
      }

      setMessages((m) => [
        ...m,
        {
          role: 'assistant',
          content: data.message,
          products: data.products || null,
        },
      ])
      clearImage()
    } catch (err) {
      setError(err.message || 'Something went wrong on the trail.')
      setMessages((m) => m.slice(0, -1))
      setInput(text)
    } finally {
      setWaiting(false)
    }
  }

  function onKeyDown(e) {
    if (e.key === 'Enter' && !e.shiftKey) {
      e.preventDefault()
      send()
    }
  }

  const suggestions = [
    { label: 'Track order #W001', text: "What's the status of order #W001?" },
    { label: 'Hiking recommendations', text: 'Recommend hiking gear for a weekend trek' },
    { label: 'Early Risers promo', text: "I'd like the Early Risers Promotion please" },
  ]

  return (
    <div className="page">
      <div className="app">
        <header className="topbar">
          <div className="brand">
            <img
              className="logo"
              src="/assets/sierra_outfitters_logo.png"
              alt="Sierra Outfitters"
            />
            <div>
              <h1>Sierra Outfitters</h1>
              <p>Adventure basecamp chat</p>
            </div>
          </div>
          <button type="button" className="reset" onClick={resetChat} disabled={waiting}>
            Reset
          </button>
        </header>

        <main className="chat">
          {messages.length === 0 && !waiting && (
            <div className="welcome">
              <img
                className="welcome-mark"
                src="/assets/sierra_outfitters_logo.png"
                alt=""
              />
              <p className="welcome-kicker">Your trail guide is ready</p>
              <h2 className="welcome-title">Onward into the unknown!</h2>
              <p className="welcome-copy">
                Orders, gear picks, and Early Risers promos — ask away, or start with a
                suggestion below.
              </p>
              <div className="suggestions">
                {suggestions.map((s) => (
                  <button
                    key={s.label}
                    type="button"
                    className="suggestion"
                    onClick={() => useSuggestion(s.text)}
                  >
                    {s.label}
                  </button>
                ))}
              </div>
            </div>
          )}

          {messages.map((msg, i) => (
            <div key={i} className={`message-block ${msg.role}`}>
              <div className={`bubble-row ${msg.role}`}>
                <div className={`bubble ${msg.role}`}>
                  {msg.image && (
                    <img className="msg-image" src={msg.image} alt="Uploaded" />
                  )}
                  {msg.content && <p className="msg-text">{msg.content}</p>}
                </div>
              </div>
              {msg.products?.length > 0 && (
                <ProductCarousel products={msg.products} />
              )}
            </div>
          ))}

          {waiting && (
            <div className="bubble-row assistant">
              <div className="bubble assistant waiting">Scouting the trail…</div>
            </div>
          )}
          <div ref={bottomRef} />
        </main>

        {error && <div className="error">{error}</div>}

        <footer className="composer">
          <input
            ref={fileRef}
            className="sr-only"
            type="file"
            accept="image/*"
            onChange={onPickImage}
            disabled={waiting}
            tabIndex={-1}
          />
          <div className="composer-shell">
            {preview && (
              <div className="attachment-chip">
                <img src={preview} alt="Attachment preview" />
                <span>{image?.name || 'Image'}</span>
                <button
                  type="button"
                  className="chip-remove"
                  onClick={clearImage}
                  disabled={waiting}
                  aria-label="Remove attachment"
                >
                  ×
                </button>
              </div>
            )}
            <div className="composer-row">
              <button
                type="button"
                className={`icon-btn attach-btn ${waiting ? 'disabled' : ''}`}
                title="Attach image"
                aria-label="Attach image"
                onClick={openFilePicker}
                disabled={waiting}
              >
                <AttachIcon />
              </button>
              <textarea
                rows={1}
                value={input}
                onChange={(e) => setInput(e.target.value)}
                onKeyDown={onKeyDown}
                placeholder="Message your trail guide…"
                disabled={waiting}
              />
              <button
                type="button"
                className="icon-btn send-btn"
                onClick={send}
                disabled={waiting || (!input.trim() && !image)}
                aria-label="Send message"
              >
                <SendIcon />
              </button>
            </div>
          </div>
        </footer>
      </div>
    </div>
  )
}
