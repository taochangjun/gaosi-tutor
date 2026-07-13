import { onUnmounted, ref } from 'vue'

function getRecognitionCtor() {
  if (typeof window === 'undefined') return null
  return window.SpeechRecognition || window.webkitSpeechRecognition || null
}

/**
 * 浏览器语音输入（Web Speech API，中文 zh-CN）
 * @param {{ onFinal?: (text: string) => void, lang?: string }} options
 */
export function useSpeechInput(options = {}) {
  const lang = options.lang || 'zh-CN'
  const supported = ref(Boolean(getRecognitionCtor()))
  const listening = ref(false)
  const interimText = ref('')
  const error = ref('')

  let recognition = null

  function ensureRecognition() {
    const Ctor = getRecognitionCtor()
    if (!Ctor) {
      supported.value = false
      return null
    }
    if (!recognition) {
      recognition = new Ctor()
      recognition.lang = lang
      recognition.continuous = false
      recognition.interimResults = true
      recognition.maxAlternatives = 1

      recognition.onresult = (event) => {
        let interim = ''
        let final = ''
        for (let i = event.resultIndex; i < event.results.length; i += 1) {
          const transcript = event.results[i][0].transcript
          if (event.results[i].isFinal) final += transcript
          else interim += transcript
        }
        interimText.value = interim || final
        if (final.trim()) {
          options.onFinal?.(final.trim())
          interimText.value = ''
        }
      }

      recognition.onerror = (event) => {
        const map = {
          'not-allowed': '请允许使用麦克风',
          'service-not-allowed': '当前浏览器不支持语音，请换 Chrome 或让家长帮忙打字',
          'no-speech': '没听到声音，再试一次吧',
          aborted: '',
        }
        error.value = map[event.error] || '语音识别出错了，请重试'
        listening.value = false
      }

      recognition.onend = () => {
        listening.value = false
      }
    }
    return recognition
  }

  function startListening() {
    error.value = ''
    const rec = ensureRecognition()
    if (!rec) {
      error.value = '当前浏览器不支持语音输入，请用 Chrome，或让家长帮忙打字'
      return
    }
    try {
      interimText.value = ''
      listening.value = true
      rec.start()
    } catch {
      // 连续 start 会抛错，先 stop 再 start
      try {
        rec.stop()
        setTimeout(() => {
          listening.value = true
          rec.start()
        }, 120)
      } catch {
        error.value = '无法启动麦克风，请检查权限'
        listening.value = false
      }
    }
  }

  function stopListening() {
    if (recognition && listening.value) {
      recognition.stop()
    }
    listening.value = false
  }

  function toggleListening() {
    if (listening.value) stopListening()
    else startListening()
  }

  onUnmounted(() => {
    stopListening()
    recognition = null
  })

  return {
    supported,
    listening,
    interimText,
    error,
    startListening,
    stopListening,
    toggleListening,
  }
}
