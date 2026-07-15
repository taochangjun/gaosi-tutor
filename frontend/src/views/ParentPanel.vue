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

    <el-collapse class="lab-collapse">
      <el-collapse-item name="rag-lab" title="检索实验（向量 / BM25 / Hybrid）">
        <p class="lab-hint">
          输入一句检索 query，对比三路召回。建议用「借位」「竖式」「小动物」等词试差异。
          限定当前讲次：第 {{ form.lesson_id }} 讲。
        </p>
        <div class="lab-query-row">
          <el-input
            v-model="labQuery"
            placeholder="例如：竖式计算有问题 / 借位哪里薄弱"
            clearable
            @keyup.enter="runLabSearch"
          />
          <el-button type="primary" :loading="labLoading" @click="runLabSearch">
            对比检索
          </el-button>
        </div>
        <p v-if="labError" class="speech-hint error">{{ labError }}</p>
        <p v-else-if="labMessage" class="speech-hint">{{ labMessage }}</p>

        <div v-if="labResult" class="lab-columns">
          <div
            v-for="col in labColumns"
            :key="col.key"
            class="lab-col"
          >
            <h3>
              {{ col.label }}
              <span class="lab-count">{{ col.hits.length }}</span>
            </h3>
            <div v-if="!col.hits.length" class="lab-empty">无命中</div>
            <ul v-else class="lab-hits">
              <li v-for="(hit, i) in col.hits" :key="`${col.key}-${i}`">
                <div class="lab-meta">
                  <span class="lab-rank">#{{ i + 1 }}</span>
                  <span class="lab-score">score {{ formatScore(hit.score) }}</span>
                  <span v-if="hit.lesson_id" class="lab-lesson">第{{ hit.lesson_id }}讲</span>
                </div>
                <p class="lab-snippet">{{ hit.snippet }}</p>
              </li>
            </ul>
          </div>
        </div>
      </el-collapse-item>
    </el-collapse>

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
import { computed, onMounted, reactive, ref, watch } from 'vue'
import { useRouter } from 'vue-router'
import { ElMessage } from 'element-plus'
import {
  compareRagSearch,
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

const labQuery = ref('')
const labLoading = ref(false)
const labError = ref('')
const labMessage = ref('')
const labResult = ref(null)

const labColumns = computed(() => {
  const r = labResult.value
  if (!r) return []
  return [
    { key: 'vector', label: '向量', hits: r.vector?.hits || [] },
    { key: 'bm25', label: 'BM25', hits: r.bm25?.hits || [] },
    { key: 'hybrid', label: 'Hybrid', hits: r.hybrid?.hits || [] },
  ]
})

function formatScore(score) {
  if (score == null || Number.isNaN(Number(score))) return '—'
  return Number(score).toFixed(4)
}

async function runLabSearch() {
  const q = labQuery.value.trim()
  if (!q || labLoading.value) return
  labLoading.value = true
  labError.value = ''
  labMessage.value = ''
  try {
    const out = await compareRagSearch(q, form.lesson_id)
    labResult.value = out
    const msg =
      out.vector?.message || out.bm25?.message || out.hybrid?.message || ''
    labMessage.value = msg
    if (!msg) {
      ElMessage.success('三路检索完成')
    }
  } catch (err) {
    labResult.value = null
    labError.value = err.message || '检索失败'
  } finally {
    labLoading.value = false
  }
}

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

.lab-collapse {
  background: var(--card);
  border: 1px solid var(--border);
  border-radius: 12px;
  padding: 0 12px;
}

.lab-hint {
  margin: 0 0 12px;
  font-size: 13px;
  color: var(--muted);
  line-height: 1.5;
}

.lab-query-row {
  display: flex;
  gap: 8px;
  align-items: center;
  margin-bottom: 12px;
}

.lab-columns {
  display: grid;
  grid-template-columns: repeat(3, 1fr);
  gap: 12px;
}

.lab-col {
  background: var(--bg, #f7f7f8);
  border-radius: 10px;
  padding: 10px;
  min-height: 120px;
}

.lab-col h3 {
  margin: 0 0 8px;
  font-size: 14px;
  display: flex;
  align-items: center;
  gap: 6px;
}

.lab-count {
  font-size: 12px;
  font-weight: 500;
  color: var(--muted);
  background: rgba(0, 0, 0, 0.06);
  border-radius: 999px;
  padding: 1px 7px;
}

.lab-empty {
  font-size: 13px;
  color: var(--muted);
}

.lab-hits {
  list-style: none;
  margin: 0;
  padding: 0;
}

.lab-hits li {
  margin-bottom: 10px;
  padding-bottom: 8px;
  border-bottom: 1px dashed var(--border);
}

.lab-hits li:last-child {
  border-bottom: none;
  margin-bottom: 0;
  padding-bottom: 0;
}

.lab-meta {
  display: flex;
  flex-wrap: wrap;
  gap: 8px;
  font-size: 12px;
  color: var(--muted);
  margin-bottom: 4px;
}

.lab-rank {
  font-weight: 600;
  color: var(--text, #333);
}

.lab-snippet {
  margin: 0;
  font-size: 13px;
  line-height: 1.5;
}

@media (max-width: 720px) {
  .lab-columns {
    grid-template-columns: 1fr;
  }
}
</style>
