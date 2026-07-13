import { onUnmounted, ref, watch } from 'vue'

const AUTO_SPEAK_KEY = 'gaosi_tutor_auto_speak'

function cleanForSpeech(text) {
  return (text || '')
    .replace(/[\u{1F300}-\u{1FAFF}\u2600-\u27BF]/gu, '')
    .replace(/\s+/g, ' ')
    .trim()
}

function pickChineseVoice() {
  if (typeof window === 'undefined' || !window.speechSynthesis) return null
  const voices = window.speechSynthesis.getVoices()
  return (
    voices.find((v) => v.lang === 'zh-CN' && v.localService) ||
    voices.find((v) => v.lang.startsWith('zh-CN')) ||
    voices.find((v) => v.lang.startsWith('zh')) ||
    null
  )
}

/**
 * 浏览器语音播报（Speech Synthesis，中文）
 */
export function useSpeechOutput() {
  const supported = ref(
    typeof window !== 'undefined' && 'speechSynthesis' in window,
  )
  const speaking = ref(false)
  const autoSpeak = ref(localStorage.getItem(AUTO_SPEAK_KEY) !== 'off')

  let utterance = null

  function ensureVoicesLoaded() {
    if (!supported.value) return
    const voices = window.speechSynthesis.getVoices()
    if (!voices.length) {
      window.speechSynthesis.onvoiceschanged = () => {
        window.speechSynthesis.onvoiceschanged = null
      }
    }
  }

  function stopSpeaking() {
    if (!supported.value) return
    window.speechSynthesis.cancel()
    speaking.value = false
    utterance = null
  }

  function speak(text) {
    if (!supported.value || !autoSpeak.value) return
    const content = cleanForSpeech(text)
    if (!content) return

    stopSpeaking()
    utterance = new SpeechSynthesisUtterance(content)
    utterance.lang = 'zh-CN'
    utterance.rate = 0.92
    utterance.pitch = 1.05
    const voice = pickChineseVoice()
    if (voice) utterance.voice = voice

    utterance.onstart = () => {
      speaking.value = true
    }
    utterance.onend = () => {
      speaking.value = false
    }
    utterance.onerror = () => {
      speaking.value = false
    }

    window.speechSynthesis.speak(utterance)
  }

  function toggleAutoSpeak() {
    autoSpeak.value = !autoSpeak.value
    localStorage.setItem(AUTO_SPEAK_KEY, autoSpeak.value ? 'on' : 'off')
    if (!autoSpeak.value) stopSpeaking()
  }

  watch(autoSpeak, (on) => {
    if (!on) stopSpeaking()
  })

  onUnmounted(() => {
    stopSpeaking()
  })

  if (typeof window !== 'undefined') {
    ensureVoicesLoaded()
  }

  return {
    supported,
    speaking,
    autoSpeak,
    speak,
    stopSpeaking,
    toggleAutoSpeak,
  }
}
