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

/** Render markdown links + bare URLs as clickable anchors; keep the rest as text. */
function MessageText({ text }) {
  if (!text) return null

  const pattern =
    /\[([^\]]+)\]\((https?:\/\/[^\s)]+)\)|(https?:\/\/[^\s<>()]+)/g
  const nodes = []
  let last = 0
  let match
  let key = 0

  while ((match = pattern.exec(text)) !== null) {
    if (match.index > last) {
      nodes.push(text.slice(last, match.index))
    }
    if (match[1] && match[2]) {
      nodes.push(
        <a
          key={key++}
          className="msg-link"
          href={match[2]}
          target="_blank"
          rel="noopener noreferrer"
        >
          {match[1]}
        </a>,
      )
    } else if (match[3]) {
      const href = match[3].replace(/[.,;:!?]+$/, '')
      const trailing = match[3].slice(href.length)
      nodes.push(
        <a
          key={key++}
          className="msg-link"
          href={href}
          target="_blank"
          rel="noopener noreferrer"
        >
          {href}
        </a>,
      )
      if (trailing) nodes.push(trailing)
    }
    last = match.index + match[0].length
  }

  if (last < text.length) nodes.push(text.slice(last))

  return <p className="msg-text">{nodes}</p>
}

function RatingChip({ sessionId, alreadyRated }) {
  const [choice, setChoice] = useState(null)
  const [comment, setComment] = useState('')
  const [done, setDone] = useState(alreadyRated ? 'thanks' : null)
  const [busy, setBusy] = useState(false)

  async function finish(rating, extraComment) {
    if (busy) return
    setBusy(true)
    try {
      await fetch(`${API}/api/rating`, {
        method: 'POST',
        headers: {
          'Content-Type': 'application/json',
          'X-Session-Id': sessionId,
        },
        body: JSON.stringify({
          rating,
          comment: extraComment || undefined,
        }),
      })
      setDone(rating === 'skip' ? 'skipped' : 'thanks')
    } catch {
      setDone(rating === 'skip' ? 'skipped' : 'thanks')
    } finally {
      setBusy(false)
    }
  }

  if (done === 'thanks') {
    return (
      <p className="rating-thanks">Thanks — that helps us train the trail guide.</p>
    )
  }
  if (done === 'skipped') return null

  if (!choice) {
    return (
      <div className="rating-chip">
        <p className="rating-label">How was this trail?</p>
        <div className="rating-actions">
          <button
            type="button"
            className="rating-thumb"
            onClick={() => setChoice('up')}
            aria-label="Thumbs up"
            disabled={busy}
          >
            👍
          </button>
          <button
            type="button"
            className="rating-thumb"
            onClick={() => setChoice('down')}
            aria-label="Thumbs down"
            disabled={busy}
          >
            👎
          </button>
          <button
            type="button"
            className="rating-skip"
            onClick={() => finish('skip')}
            disabled={busy}
          >
            Skip
          </button>
        </div>
      </div>
    )
  }

  return (
    <div className="rating-chip">
      <p className="rating-label">
        {choice === 'up' ? 'Glad it helped.' : 'Sorry it was rocky.'} Optional note:
      </p>
      <div className="rating-followup">
        <input
          type="text"
          maxLength={500}
          value={comment}
          onChange={(e) => setComment(e.target.value)}
          placeholder="Anything we should know?"
          disabled={busy}
        />
        <button
          type="button"
          className="rating-send"
          onClick={() => finish(choice, comment)}
          disabled={busy}
        >
          Send
        </button>
      </div>
    </div>
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
  const [handedOff, setHandedOff] = useState(false)
  const [rated, setRated] = useState(false)
  const [idleSeconds, setIdleSeconds] = useState(300)
  const bottomRef = useRef(null)
  const fileRef = useRef(null)
  const nudgeTimerRef = useRef(null)
  const handedOffRef = useRef(false)
  const nudgedRef = useRef(false)
  const waitingRef = useRef(false)
  const sessionRef = useRef(sessionId)

  useEffect(() => {
    handedOffRef.current = handedOff
  }, [handedOff])
  useEffect(() => {
    waitingRef.current = waiting
  }, [waiting])
  useEffect(() => {
    sessionRef.current = sessionId
  }, [sessionId])

  function clearNudgeTimer() {
    if (nudgeTimerRef.current) {
      clearTimeout(nudgeTimerRef.current)
      nudgeTimerRef.current = null
    }
  }

  async function requestNudge() {
    if (handedOffRef.current || waitingRef.current || nudgedRef.current) return
    try {
      const res = await fetch(`${API}/api/nudge`, {
        method: 'POST',
        headers: { 'X-Session-Id': sessionRef.current },
      })
      const data = await res.json()
      if (data.skipped) return
      nudgedRef.current = true
      if (data.message && !data.already_sent) {
        setMessages((m) => {
          if (m.some((msg) => msg.kind === 'nudge')) return m
          return [
            ...m,
            { role: 'assistant', content: data.message, kind: 'nudge' },
          ]
        })
      }
    } catch {
      /* idle nudge is best-effort */
    }
  }

  function scheduleNudge() {
    clearNudgeTimer()
    if (handedOffRef.current || nudgedRef.current || waitingRef.current) return
    nudgeTimerRef.current = setTimeout(requestNudge, idleSeconds * 1000)
  }

  useEffect(() => {
    let cancelled = false
    async function load() {
      try {
        const [histRes, cfgRes] = await Promise.all([
          fetch(`${API}/api/history`, {
            headers: { 'X-Session-Id': sessionId },
          }),
          fetch(`${API}/api/config`),
        ])
        const data = await histRes.json()
        const cfg = await cfgRes.json()
        if (cancelled) return
        if (typeof cfg.nudge_idle_seconds === 'number') {
          setIdleSeconds(cfg.nudge_idle_seconds)
        }
        if (data.session_id && data.session_id !== sessionId) {
          setSessionId(data.session_id)
          setSid(data.session_id)
        }
        setMessages(data.messages || [])
        setHandedOff(Boolean(data.handed_off))
        setRated(Boolean(data.rated))
        nudgedRef.current = Boolean(data.nudged)
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

  useEffect(() => {
    const hasUser = messages.some((m) => m.role === 'user')
    const hasAsst = messages.some((m) => m.role === 'assistant')
    if (messages.some((m) => m.kind === 'nudge')) {
      nudgedRef.current = true
      clearNudgeTimer()
      return undefined
    }
    if (hasUser && hasAsst && !handedOff && !waiting) {
      scheduleNudge()
    } else {
      clearNudgeTimer()
    }
    return clearNudgeTimer
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [messages, handedOff, waiting, idleSeconds])

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
    clearNudgeTimer()
    setHandedOff(false)
    handedOffRef.current = false
    nudgedRef.current = false
    setRated(false)
    setMessages([])
    setInput('')
    try {
      const res = await fetch(`${API}/api/reset`, {
        method: 'POST',
        headers: { 'X-Session-Id': sessionId },
      })
      const data = await res.json()
      const nextId = data.session_id || crypto.randomUUID()
      setSessionId(nextId)
      setSid(nextId)
      setHandedOff(false)
      handedOffRef.current = false
      nudgedRef.current = false
      setRated(false)
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
    if ((!text && !image) || waiting || handedOff) return

    setWaiting(true)
    setError('')
    clearNudgeTimer()
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

      if (data.handed_off) {
        setHandedOff(true)
        handedOffRef.current = true
        nudgedRef.current = true
        clearNudgeTimer()
      }

      if (data.muted && !data.message) {
        clearImage()
        return
      }

      setMessages((m) => [
        ...m,
        {
          role: 'assistant',
          content: data.message,
          products: data.products || null,
          kind: data.kind || null,
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

        {handedOff && (
          <div className="handoff-banner" role="status">
            <span className="handoff-dot" aria-hidden="true" />
            Waiting for a human trail guide · AI is paused
          </div>
        )}

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
                <div
                  className={`bubble ${msg.role} ${msg.kind === 'nudge' ? 'nudge' : ''} ${
                    msg.kind === 'handoff' || msg.kind === 'handoff_ack' ? 'handoff' : ''
                  }`}
                >
                  {msg.kind === 'nudge' && (
                    <p className="bubble-kicker">Check-in</p>
                  )}
                  {(msg.kind === 'handoff' || msg.kind === 'handoff_ack') && (
                    <p className="bubble-kicker">Human handoff</p>
                  )}
                  {msg.image && (
                    <img className="msg-image" src={msg.image} alt="Uploaded" />
                  )}
                  {msg.content && <MessageText text={msg.content} />}
                </div>
              </div>
              {msg.kind === 'nudge' && (
                <RatingChip sessionId={sessionId} alreadyRated={rated} />
              )}
              {msg.products?.length > 0 && (
                <ProductCarousel products={msg.products} />
              )}
            </div>
          ))}

          {waiting && !handedOff && (
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
                className={`icon-btn attach-btn ${waiting || handedOff ? 'disabled' : ''}`}
                title="Attach image"
                aria-label="Attach image"
                onClick={openFilePicker}
                disabled={waiting || handedOff}
              >
                <AttachIcon />
              </button>
              <textarea
                rows={1}
                value={input}
                onChange={(e) => {
                  setInput(e.target.value)
                  if (!handedOff && !waiting) scheduleNudge()
                }}
                onKeyDown={onKeyDown}
                placeholder={
                  handedOff
                    ? 'Waiting for a human trail guide…'
                    : 'Message your trail guide…'
                }
                disabled={waiting || handedOff}
              />
              <button
                type="button"
                className="icon-btn send-btn"
                onClick={send}
                disabled={waiting || handedOff || (!input.trim() && !image)}
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
