<template>
  <div class="child-page">
    <section class="hero">
      <div class="hero-top">
        <h1>你好，小数学家！</h1>
        <button
          v-if="ttsSupported"
          type="button"
          class="tts-toggle"
          :class="{ on: autoSpeak, speaking }"
          @click="toggleAutoSpeak"
        >
          {{ autoSpeak ? (speaking ? '🔊 正在读…' : '🔊 读给我听') : '🔇 已静音' }}
        </button>
      </div>
      <p class="lesson-tag">第 {{ settings.lesson_id }} 讲 · {{ lessonTitle }}</p>
    </section>

    <section class="chat-box">
      <div v-for="(msg, idx) in messages" :key="idx" :class="['bubble', msg.role]">
        <div class="avatar">{{ msg.role === 'user' ? '🙂' : '🦊' }}</div>
        <div class="text-wrap">
          <MathDiagram v-if="msg.diagram" :spec="msg.diagram" />
          <div class="text">{{ msg.content }}</div>
          <button
            v-if="msg.role === 'assistant' && ttsSupported"
            type="button"
            class="replay"
            title="再读一遍"
            @click="speak(msg.content)"
          >
            🔊
          </button>
        </div>
      </div>
      <div v-if="streaming" class="bubble assistant">
        <div class="avatar">🦊</div>
        <div class="text-wrap">
          <MathDiagram v-if="streamDiagram" :spec="streamDiagram" />
          <div class="text">{{ streamBuffer }}<span class="cursor">|</span></div>
        </div>
      </div>
    </section>

    <section class="quick-actions">
      <button v-for="q in quickQuestions" :key="q" :disabled="loading || listening" @click="send(q)">
        {{ q }}
      </button>
    </section>

    <p v-if="speechError" class="speech-tip error">{{ speechError }}</p>
    <p v-else-if="listening" class="speech-tip listening">
      🎤 正在听你说… {{ interimText || '（说说看）' }}
    </p>
    <p v-else-if="speechSupported" class="speech-tip">点 🎤 说话，小思会用 🔊 读回答给你听</p>

    <section class="input-row">
      <button
        type="button"
        class="mic"
        :class="{ active: listening, unsupported: !speechSupported }"
        :disabled="loading || speaking"
        :title="speechSupported ? '点击说话' : '浏览器不支持语音'"
        @click="onToggleListen"
      >
        {{ listening ? '⏹' : '🎤' }}
      </button>
      <input
        v-model="input"
        :placeholder="listening ? '正在识别…' : '也可以打字…'"
        :disabled="loading || listening"
        @keyup.enter="send(input)"
      />
      <button class="send" :disabled="loading || !input.trim()" @click="send(input)">
        发送
      </button>
    </section>
  </div>
</template>

<script setup>
import { computed, onMounted, ref } from 'vue'
import { loadSettings, tutorChatStream, fetchLessons } from '../api'
import { useSpeechInput } from '../composables/useSpeechInput'
import { useSpeechOutput } from '../composables/useSpeechOutput'
import MathDiagram from '../components/MathDiagram.vue'

const SESSION_KEY = 'gaosi_tutor_session_id'

const settings = ref({
  lesson_id: 1,
  difficulty: 'interest',
  session_id: localStorage.getItem(SESSION_KEY) || null,
})
const lessons = ref([])
const messages = ref([
  {
    role: 'assistant',
    content: '我是小思！不懂可以问我，也可以点麦克风说话～',
  },
])
const input = ref('')
const loading = ref(false)
const streaming = ref(false)
const streamBuffer = ref('')
const streamDiagram = ref(null)

const quickQuestions = ['这题不懂', '出一道题', '我答完了', '再出一道']

const {
  supported: ttsSupported,
  speaking,
  autoSpeak,
  speak,
  stopSpeaking,
  toggleAutoSpeak,
} = useSpeechOutput()

const {
  supported: speechSupported,
  listening,
  interimText,
  error: speechError,
  toggleListening,
} = useSpeechInput({
  onFinal: (text) => {
    input.value = text
    send(text)
  },
})

const lessonTitle = computed(() => {
  const found = lessons.value.find((l) => l.id === settings.value.lesson_id)
  return found?.title || '...'
})

function onToggleListen() {
  stopSpeaking()
  toggleListening()
}

async function loadLessons() {
  lessons.value = await fetchLessons()
  const saved = loadSettings()
  settings.value = {
    ...settings.value,
    lesson_id: saved.lesson_id || 1,
    difficulty: saved.difficulty || 'interest',
  }
}

async function send(question) {
  const text = (question || '').trim()
  if (!text || loading.value) return

  stopSpeaking()
  messages.value.push({ role: 'user', content: text })
  input.value = ''
  loading.value = true
  streaming.value = true
  streamBuffer.value = ''
  streamDiagram.value = null

  let answer = ''
  let answerDiagram = null

  try {
    const done = await tutorChatStream(
      {
        question: text,
        session_id: settings.value.session_id,
        mode: 'child',
        lesson_id: settings.value.lesson_id,
        difficulty: settings.value.difficulty,
      },
      (event, data) => {
        if (event === 'delta') {
          streamBuffer.value += data.content || ''
        }
        if (event === 'tool_start') {
          streamBuffer.value = '小思正在想题目...'
        }
        if (event === 'tool_end' && data.tool === 'generate_practice' && data.diagram) {
          streamDiagram.value = data.diagram
          answerDiagram = data.diagram
        }
        if (event === 'done' && data.diagram) {
          streamDiagram.value = data.diagram
          answerDiagram = data.diagram
        }
      },
    )

    if (done?.session_id) {
      settings.value.session_id = done.session_id
      localStorage.setItem(SESSION_KEY, done.session_id)
    }

    answer = streamBuffer.value || done?.answer || '（无回答）'
    messages.value.push({ role: 'assistant', content: answer, diagram: answerDiagram })
  } catch (err) {
    answer = `哎呀，出错了：${err.message}`
    messages.value.push({ role: 'assistant', content: answer })
  } finally {
    streaming.value = false
    streamBuffer.value = ''
    streamDiagram.value = null
    loading.value = false
    if (answer) speak(answer)
  }
}

onMounted(loadLessons)
</script>

<style scoped>
.child-page {
  max-width: 720px;
  margin: 0 auto;
  padding: 16px;
}

.hero-top {
  display: flex;
  align-items: center;
  justify-content: space-between;
  gap: 12px;
}

.hero h1 {
  margin: 0;
  font-size: 28px;
  color: var(--primary);
}

.tts-toggle {
  border: 2px solid var(--border);
  background: #fff;
  border-radius: 999px;
  padding: 8px 14px;
  font-size: 14px;
  font-weight: 700;
  cursor: pointer;
  white-space: nowrap;
}

.tts-toggle.on {
  background: #e8f8f5;
  border-color: var(--accent);
  color: #0d7377;
}

.tts-toggle.speaking {
  animation: pulse 1s ease-in-out infinite;
}

.lesson-tag {
  margin-top: 8px;
  color: var(--muted);
  font-size: 16px;
}

.chat-box {
  margin-top: 16px;
  background: var(--card);
  border: 2px solid var(--border);
  border-radius: 16px;
  padding: 16px;
  min-height: 320px;
  max-height: 50vh;
  overflow-y: auto;
}

.bubble {
  display: flex;
  gap: 10px;
  margin-bottom: 14px;
}

.bubble.user {
  flex-direction: row-reverse;
}

.avatar {
  font-size: 28px;
  line-height: 1;
}

.text-wrap {
  display: flex;
  flex-direction: column;
  align-items: flex-start;
  max-width: 85%;
}

.bubble.user .text-wrap {
  align-items: flex-end;
}

.text {
  background: var(--primary-soft);
  padding: 12px 14px;
  border-radius: 14px;
  font-size: 18px;
  line-height: 1.5;
  white-space: pre-wrap;
}

.bubble.user .text {
  background: #e8f8f5;
}

.replay {
  margin-top: 4px;
  border: none;
  background: transparent;
  font-size: 16px;
  cursor: pointer;
  opacity: 0.7;
  padding: 2px 6px;
}

.replay:hover {
  opacity: 1;
}

.cursor {
  animation: blink 1s step-end infinite;
}

@keyframes blink {
  50% {
    opacity: 0;
  }
}

.quick-actions {
  display: grid;
  grid-template-columns: 1fr 1fr;
  gap: 10px;
  margin-top: 14px;
}

.quick-actions button {
  font-size: 17px;
  padding: 14px;
  border: none;
  border-radius: 12px;
  background: var(--accent);
  color: #fff;
  font-weight: 700;
  cursor: pointer;
}

.quick-actions button:disabled {
  opacity: 0.6;
  cursor: not-allowed;
}

.speech-tip {
  margin: 10px 0 0;
  font-size: 15px;
  color: var(--muted);
  text-align: center;
}

.speech-tip.listening {
  color: var(--primary);
  font-weight: 600;
}

.speech-tip.error {
  color: #e74c3c;
}

.input-row {
  display: flex;
  gap: 8px;
  margin-top: 8px;
  align-items: stretch;
}

.mic {
  width: 52px;
  min-width: 52px;
  font-size: 22px;
  border: 2px solid var(--border);
  border-radius: 12px;
  background: #fff;
  cursor: pointer;
}

.mic.active {
  background: #ffe8de;
  border-color: var(--primary);
  animation: pulse 1s ease-in-out infinite;
}

.mic.unsupported {
  opacity: 0.45;
  cursor: not-allowed;
}

@keyframes pulse {
  50% {
    transform: scale(1.05);
  }
}

.input-row input {
  flex: 1;
  font-size: 18px;
  padding: 12px 14px;
  border: 2px solid var(--border);
  border-radius: 12px;
}

.send {
  font-size: 17px;
  padding: 0 18px;
  border: none;
  border-radius: 12px;
  background: var(--primary);
  color: #fff;
  font-weight: 700;
  cursor: pointer;
}
</style>
