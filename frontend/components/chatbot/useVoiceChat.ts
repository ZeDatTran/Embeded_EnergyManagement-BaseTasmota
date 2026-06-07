"use client"

import { useState, useRef, useCallback, useEffect } from "react"

// ─── Web Speech API Type Declarations (not in default TS lib) ───────────────
/* eslint-disable @typescript-eslint/no-empty-interface */
interface SpeechRecognitionEvent extends Event {
  readonly resultIndex: number
  readonly results: SpeechRecognitionResultList
}

interface SpeechRecognitionErrorEvent extends Event {
  readonly error: string
  readonly message: string
}

interface SpeechRecognition extends EventTarget {
  lang: string
  continuous: boolean
  interimResults: boolean
  maxAlternatives: number
  onstart: ((this: SpeechRecognition, ev: Event) => void) | null
  onend: ((this: SpeechRecognition, ev: Event) => void) | null
  onresult: ((this: SpeechRecognition, ev: SpeechRecognitionEvent) => void) | null
  onerror: ((this: SpeechRecognition, ev: SpeechRecognitionErrorEvent) => void) | null
  start(): void
  stop(): void
  abort(): void
}

declare var SpeechRecognition: {
  prototype: SpeechRecognition
  new (): SpeechRecognition
}
/* eslint-enable @typescript-eslint/no-empty-interface */

// ─── Types ──────────────────────────────────────────────────────────────────
export type VoiceStatus = "idle" | "listening" | "processing" | "speaking"

interface UseVoiceChatOptions {
  /** Language for speech recognition (default: "vi-VN") */
  lang?: string
  /** Whether to auto-speak AI responses (default: true) */
  autoSpeak?: boolean
  /** Backend URL for FPT.AI TTS proxy (default: NEXT_PUBLIC_BACKEND_URL) */
  backendUrl?: string
  /** Callback when transcript is ready */
  onTranscript?: (text: string) => void
  /** Callback on recognition error */
  onError?: (error: string) => void
}

interface UseVoiceChatReturn {
  /** Current voice pipeline status */
  status: VoiceStatus
  /** Whether speech recognition is supported in this browser */
  isSTTSupported: boolean
  /** Whether speech synthesis is supported in this browser */
  isTTSSupported: boolean
  /** Interim (in-progress) transcript while user is speaking */
  interimTranscript: string
  /** Start listening to user's microphone */
  startListening: () => void
  /** Stop listening manually */
  stopListening: () => void
  /** Speak text aloud via speech synthesis */
  speak: (text: string) => void
  /** Stop any ongoing speech synthesis */
  stopSpeaking: () => void
  /** Toggle microphone on/off */
  toggleListening: () => void
}

// ─── Helpers ────────────────────────────────────────────────────────────────

/** Strip markdown/HTML for cleaner TTS output */
function stripMarkdownForTTS(text: string): string {
  return text
    .replace(/\*\*(.+?)\*\*/g, "$1")       // bold
    .replace(/\*(.+?)\*/g, "$1")            // italic
    .replace(/`(.+?)`/g, "$1")              // inline code
    .replace(/<br\s*\/?>/gi, ". ")           // line breaks → pause
    .replace(/<[^>]+>/g, "")                 // strip HTML tags
    .replace(/•/g, ". ")                     // bullets → pause
    .replace(/[↑↓]/g, "")                   // trend arrows
    .replace(/\n+/g, ". ")                   // newlines → pause
    .replace(/\s{2,}/g, " ")                // collapse spaces
    .trim()
}

/** Check if SpeechRecognition API exists */
function getSpeechRecognitionAPI(): typeof SpeechRecognition | null {
  if (typeof window === "undefined") return null
  return (
    (window as any).SpeechRecognition ||
    (window as any).webkitSpeechRecognition ||
    null
  )
}

// ─── Hook ───────────────────────────────────────────────────────────────────
export function useVoiceChat(options: UseVoiceChatOptions = {}): UseVoiceChatReturn {
  const {
    lang = "vi-VN",
    autoSpeak = true,
    backendUrl = process.env.NEXT_PUBLIC_BACKEND_URL ?? "http://localhost:5000",
    onTranscript,
    onError,
  } = options

  const [status, setStatus] = useState<VoiceStatus>("idle")
  const [interimTranscript, setInterimTranscript] = useState("")

  // Refs to persist across renders
  const recognitionRef = useRef<SpeechRecognition | null>(null)
  const audioRef = useRef<HTMLAudioElement | null>(null)
  const isMountedRef = useRef(true)
  /** Signals that the current TTS playback has been cancelled by the user. */
  const ttsCancelledRef = useRef(false)
  /** Keeps the latest status value accessible without stale closures. */
  const statusRef = useRef<VoiceStatus>(status)
  statusRef.current = status

  // Browser support detection
  const isSTTSupported = typeof window !== "undefined" && !!getSpeechRecognitionAPI()
  const isTTSSupported = true  // FPT.AI TTS works via backend, always available

  // Cleanup on unmount
  useEffect(() => {
    isMountedRef.current = true
    return () => {
      isMountedRef.current = false
      ttsCancelledRef.current = true
      if (recognitionRef.current) {
        try { recognitionRef.current.abort() } catch { /* noop */ }
      }
      // Stop any playing audio
      if (audioRef.current) {
        audioRef.current.pause()
        audioRef.current = null
      }
    }
  }, [])

  // ── Stop Speaking ─────────────────────────────────────────────────────────
  const stopSpeaking = useCallback(() => {
    // Signal any in-progress retry loop / pending fetch to abort
    ttsCancelledRef.current = true

    if (audioRef.current) {
      audioRef.current.pause()
      audioRef.current.currentTime = 0
      audioRef.current.onended = null
      audioRef.current.onerror = null
      audioRef.current.oncanplaythrough = null
      audioRef.current = null
    }
    // Use ref instead of closure value to avoid stale-closure problem
    if (isMountedRef.current && statusRef.current === "speaking") {
      setStatus("idle")
    }
  }, [])  // no dependency on `status` — uses statusRef instead

  // ── Start Listening ───────────────────────────────────────────────────────
  const startListening = useCallback(() => {
    const SpeechRecognitionAPI = getSpeechRecognitionAPI()
    if (!SpeechRecognitionAPI) {
      onError?.("Trình duyệt không hỗ trợ Speech Recognition. Hãy dùng Chrome hoặc Edge.")
      return
    }

    // If AI is speaking, stop it first (user interruption)
    if (statusRef.current === "speaking") {
      stopSpeaking()
    }

    // If already listening, do nothing
    if (recognitionRef.current) {
      return
    }

    const recognition = new SpeechRecognitionAPI()
    recognition.lang = lang
    recognition.continuous = false        // Stop after one phrase
    recognition.interimResults = true     // Show live transcript
    recognition.maxAlternatives = 1

    recognition.onstart = () => {
      if (isMountedRef.current) {
        setStatus("listening")
        setInterimTranscript("")
      }
    }

    recognition.onresult = (event: SpeechRecognitionEvent) => {
      let interim = ""
      let final = ""

      for (let i = event.resultIndex; i < event.results.length; i++) {
        const transcript = event.results[i][0].transcript
        if (event.results[i].isFinal) {
          final += transcript
        } else {
          interim += transcript
        }
      }

      if (isMountedRef.current) {
        setInterimTranscript(interim)
      }

      if (final) {
        if (isMountedRef.current) {
          setInterimTranscript("")
          setStatus("processing")
        }
        onTranscript?.(final.trim())
      }
    }

    recognition.onerror = (event: SpeechRecognitionErrorEvent) => {
      if (!isMountedRef.current) return

      recognitionRef.current = null
      setInterimTranscript("")

      switch (event.error) {
        case "not-allowed":
        case "service-not-allowed":
          onError?.("🎤 Quyền truy cập microphone bị từ chối. Vui lòng cho phép trong cài đặt trình duyệt.")
          break
        case "no-speech":
          // Silent timeout — not really an error
          break
        case "network":
          onError?.("🌐 Lỗi mạng khi nhận diện giọng nói. Kiểm tra kết nối internet.")
          break
        case "aborted":
          // User manually stopped — not an error
          break
        default:
          onError?.(`⚠️ Lỗi nhận diện giọng nói: ${event.error}`)
      }
      setStatus("idle")
    }

    recognition.onend = () => {
      recognitionRef.current = null
      if (isMountedRef.current && statusRef.current === "listening") {
        setStatus("idle")
        setInterimTranscript("")
      }
    }

    recognitionRef.current = recognition

    try {
      recognition.start()
    } catch (err) {
      recognitionRef.current = null
      onError?.("Không thể bắt đầu nhận diện giọng nói. Hãy thử lại.")
      setStatus("idle")
    }
  }, [lang, stopSpeaking, onTranscript, onError])

  // ── Stop Listening ────────────────────────────────────────────────────────
  const stopListening = useCallback(() => {
    if (recognitionRef.current) {
      try {
        recognitionRef.current.stop()
      } catch { /* noop */ }
      recognitionRef.current = null
    }
    if (isMountedRef.current) {
      setStatus("idle")
      setInterimTranscript("")
    }
  }, [])

  // ── Toggle Listening ──────────────────────────────────────────────────────
  const toggleListening = useCallback(() => {
    if (statusRef.current === "listening") {
      stopListening()
    } else {
      startListening()
    }
  }, [startListening, stopListening])

  // ── Speak via FPT.AI TTS ──────────────────────────────────────────────────
  const speak = useCallback(
    async (text: string) => {
      if (!text) return

      // Stop any ongoing audio & reset cancellation flag for this new request
      if (audioRef.current) {
        audioRef.current.pause()
        audioRef.current = null
      }
      ttsCancelledRef.current = false

      const cleanText = stripMarkdownForTTS(text)
      if (!cleanText) return

      if (isMountedRef.current) setStatus("speaking")

      try {
        // Call backend TTS proxy
        const res = await fetch(`${backendUrl}/api/tts`, {
          method: "POST",
          headers: { "Content-Type": "application/json" },
          body: JSON.stringify({ text: cleanText }),
        })

        // Check cancellation after async fetch
        if (ttsCancelledRef.current) return

        const data = await res.json()

        if (data.status !== "success" || !data.audio_url) {
          throw new Error(data.message || "Không nhận được audio URL")
        }

        // FPT.AI generates audio ASYNCHRONOUSLY — the URL is returned before
        // the file is ready on their CDN. We must wait before playing.
        const delay = (ms: number) => new Promise((r) => setTimeout(r, ms))

        // Wait 1.5s for FPT.AI to finish generating the audio file
        await delay(1500)

        // Check cancellation after delay
        if (ttsCancelledRef.current) return

        // Retry playback up to 5 times with 1.5s gaps
        const playWithRetry = async (url: string, retries = 5): Promise<void> => {
          // Abort if user pressed stop during retry loop
          if (ttsCancelledRef.current) return

          return new Promise((resolve, reject) => {
            // Double-check cancellation inside the promise
            if (ttsCancelledRef.current) return resolve()

            // Add cache-buster to prevent browser caching a failed response
            const bustUrl = `${url}${url.includes("?") ? "&" : "?"}t=${Date.now()}`
            const audio = new Audio(bustUrl)
            audioRef.current = audio

            audio.oncanplaythrough = () => {
              if (!isMountedRef.current || ttsCancelledRef.current) {
                audio.pause()
                return resolve()
              }
              audio.play().catch(() => {})
            }

            audio.onended = () => {
              audioRef.current = null
              if (isMountedRef.current) setStatus("idle")
              resolve()
            }

            audio.onerror = () => {
              audioRef.current = null
              // Don't retry if cancelled
              if (ttsCancelledRef.current) {
                return resolve()
              }
              if (retries > 0) {
                // Audio file not ready yet — wait and retry
                setTimeout(() => {
                  playWithRetry(url, retries - 1).then(resolve).catch(reject)
                }, 1500)
              } else {
                if (isMountedRef.current) setStatus("idle")
                reject(new Error("Audio không thể phát sau nhiều lần thử"))
              }
            }

            audio.load()
          })
        }

        await playWithRetry(data.audio_url)
      } catch (err) {
        if (isMountedRef.current && !ttsCancelledRef.current) setStatus("idle")
        onError?.(`Lỗi TTS: ${err instanceof Error ? err.message : String(err)}`)
      }
    },
    [backendUrl, onError],
  )

  return {
    status,
    isSTTSupported,
    isTTSSupported,
    interimTranscript,
    startListening,
    stopListening,
    speak,
    stopSpeaking,
    toggleListening,
  }
}
