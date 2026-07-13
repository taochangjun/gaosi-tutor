<template>
  <div class="parent-page">
    <h1>家长设置</h1>
    <p class="hint">选好消息当前讲次和难度，孩子模式会自动沿用这里的设置。</p>

    <el-form label-width="100px" class="form">
      <el-form-item label="当前讲次">
        <el-select v-model="form.lesson_id" style="width: 100%">
          <el-option
            v-for="l in lessons"
            :key="l.id"
            :label="`第${l.id}讲 ${l.title}（${l.topic}）`"
            :value="l.id"
          />
        </el-select>
      </el-form-item>

      <el-form-item label="练习难度">
        <el-radio-group v-model="form.difficulty">
          <el-radio value="interest">兴趣</el-radio>
          <el-radio value="extend">拓展</el-radio>
        </el-radio-group>
      </el-form-item>

      <el-form-item label="家庭笔记">
        <el-input
          v-model="form.family_notes"
          type="textarea"
          :rows="4"
          placeholder="例如：左右还不太分；拼图需要多练..."
        />
        <p class="rag-hint">
          知识库：{{ ragStats.chunks_in_store ?? 0 }} 条片段
          <span v-if="ragStats.notes_with_content != null">
            （{{ ragStats.notes_with_content }} 讲有笔记）
          </span>
        </p>
      </el-form-item>

      <el-form-item>
        <el-button type="primary" :loading="saving" @click="saveAll">保存设置</el-button>
        <el-button :loading="indexing" @click="syncRag">同步知识库</el-button>
        <el-button @click="goChild">进入孩子模式</el-button>
        <el-button @click="newSession">新对话</el-button>
      </el-form-item>
    </el-form>

    <el-divider />

    <section class="parent-chat">
      <h2>家长提问（可问本讲思路、怎么陪练）</h2>
      <div class="chat-log">
        <div v-for="(msg, idx) in messages" :key="idx" :class="['line', msg.role]">
          <strong>{{ msg.role === 'user' ? '家长' : '小思' }}：</strong>
          <span>{{ msg.content }}</span>
        </div>
        <div v-if="streaming" class="line assistant">
          <strong>小思：</strong>
          <span>{{ streamBuffer }}</span>
        </div>
      </div>
      <div class="input-row">
        <el-button
          :type="listening ? 'danger' : 'default'"
          circle
          :disabled="!speechSupported || loading"
          :title="speechSupported ? '语音输入' : '浏览器不支持语音'"
          @click="toggleListening"
        >
          {{ listening ? '⏹' : '🎤' }}
        </el-button>
        <el-input
          v-model="question"
          :placeholder="listening ? '正在听…' : '例如：第5讲怎么引导孩子理解？'"
          @keyup.enter="ask"
        />
        <el-button type="primary" :loading="loading" @click="ask">发送</el-button>
      </div>
      <p v-if="speechError" class="speech-hint error">{{ speechError }}</p>
      <p v-else-if="listening" class="speech-hint">正在识别：{{ interimText || '…' }}</p>
    </section>
  </div>
</template>

<script setup>
import { onMounted, reactive, ref, watch } from 'vue'
import { useRouter } from 'vue-router'
import { ElMessage } from 'element-plus'
import {
  fetchLessons,
  fetchRagStats,
  indexAllRag,
  loadSettings,
  saveSettings,
  tutorChatStream,
  updateLessonNotes,
} from '../api'
import { useSpeechInput } from '../composables/useSpeechInput'

const SESSION_KEY = 'gaosi_tutor_session_id'
const router = useRouter()

const lessons = ref([])
const form = reactive({
  lesson_id: 1,
  difficulty: 'interest',
  family_notes: '',
})
const saving = ref(false)
const indexing = ref(false)
const ragStats = ref({ chunks_in_store: 0, notes_with_content: 0 })
const loading = ref(false)
const streaming = ref(false)
const streamBuffer = ref('')
const question = ref('')
const sessionId = ref(localStorage.getItem(SESSION_KEY) || null)
const messages = ref([])

const {
  supported: speechSupported,
  listening,
  interimText,
  error: speechError,
  toggleListening,
} = useSpeechInput({
  onFinal: (text) => {
    question.value = text
  },
})

watch(
  () => form.lesson_id,
  (id) => {
    const lesson = lessons.value.find((l) => l.id === id)
    if (lesson) form.family_notes = lesson.family_notes || ''
  },
)

async function load() {
  lessons.value = await fetchLessons()
  const saved = loadSettings()
  form.lesson_id = saved.lesson_id || 1
  form.difficulty = saved.difficulty || 'interest'
  const lesson = lessons.value.find((l) => l.id === form.lesson_id)
  form.family_notes = lesson?.family_notes || ''
  try {
    ragStats.value = await fetchRagStats()
  } catch {
    ragStats.value = { chunks_in_store: 0, notes_with_content: 0 }
  }
}

async function syncRag() {
  indexing.value = true
  try {
    const out = await indexAllRag()
    ragStats.value = await fetchRagStats()
    ElMessage.success(`已同步 ${out.chunks_indexed ?? 0} 条笔记片段`)
  } catch (err) {
    ElMessage.error(err.message)
  } finally {
    indexing.value = false
  }
}

async function saveAll() {
  saving.value = true
  try {
    const result = await updateLessonNotes(form.lesson_id, form.family_notes)
    saveSettings({
      lesson_id: form.lesson_id,
      difficulty: form.difficulty,
    })
    const idx = lessons.value.findIndex((l) => l.id === form.lesson_id)
    if (idx >= 0) lessons.value[idx].family_notes = form.family_notes
    if (result.rag?.chunks_indexed != null) {
      ragStats.value = await fetchRagStats()
    }
    ElMessage.success('已保存')
  } catch (err) {
    ElMessage.error(err.message)
  } finally {
    saving.value = false
  }
}

function goChild() {
  router.push('/')
}

function newSession() {
  sessionId.value = null
  localStorage.removeItem(SESSION_KEY)
  messages.value = []
  ElMessage.success('已开始新对话')
}

async function ask() {
  const text = question.value.trim()
  if (!text || loading.value) return
  messages.value.push({ role: 'user', content: text })
  question.value = ''
  loading.value = true
  streaming.value = true
  streamBuffer.value = ''

  try {
    const done = await tutorChatStream(
      {
        question: text,
        session_id: sessionId.value,
        mode: 'parent',
        lesson_id: form.lesson_id,
        difficulty: form.difficulty,
      },
      (event, data) => {
        if (event === 'delta') streamBuffer.value += data.content || ''
      },
    )
    if (done?.session_id) {
      sessionId.value = done.session_id
      localStorage.setItem(SESSION_KEY, done.session_id)
    }
    messages.value.push({
      role: 'assistant',
      content: streamBuffer.value || done?.answer || '（无回答）',
    })
  } catch (err) {
    messages.value.push({ role: 'assistant', content: err.message })
  } finally {
    streaming.value = false
    streamBuffer.value = ''
    loading.value = false
  }
}

onMounted(load)
</script>

<style scoped>
.parent-page {
  max-width: 800px;
  margin: 0 auto;
  padding: 20px;
}

.hint {
  color: var(--muted);
}

.rag-hint {
  margin: 8px 0 0;
  font-size: 13px;
  color: var(--muted);
}

.form {
  margin-top: 16px;
  background: var(--card);
  padding: 20px;
  border-radius: 12px;
  border: 1px solid var(--border);
}

.parent-chat h2 {
  font-size: 18px;
}

.chat-log {
  background: var(--card);
  border: 1px solid var(--border);
  border-radius: 12px;
  padding: 12px;
  min-height: 160px;
  max-height: 280px;
  overflow-y: auto;
}

.line {
  margin-bottom: 10px;
  line-height: 1.6;
}

.input-row {
  display: flex;
  gap: 8px;
  margin-top: 12px;
  align-items: center;
}

.speech-hint {
  margin: 8px 0 0;
  font-size: 13px;
  color: var(--muted);
}

.speech-hint.error {
  color: #e74c3c;
}
</style>
