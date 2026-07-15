const STORAGE_KEY = 'gaosi_tutor_settings'

export function loadSettings() {
  try {
    return JSON.parse(localStorage.getItem(STORAGE_KEY) || '{}')
  } catch {
    return {}
  }
}

export function saveSettings(partial) {
  const next = { ...loadSettings(), ...partial }
  localStorage.setItem(STORAGE_KEY, JSON.stringify(next))
  return next
}

export async function fetchLessons() {
  const res = await fetch('/api/lessons')
  if (!res.ok) throw new Error('加载讲次失败')
  return res.json()
}

export async function updateLessonNotes(lessonId, familyNotes) {
  const res = await fetch(`/api/lessons/${lessonId}/notes`, {
    method: 'PATCH',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify({ family_notes: familyNotes }),
  })
  if (!res.ok) throw new Error('保存笔记失败')
  return res.json()
}

export async function fetchRagStats() {
  const res = await fetch('/api/rag/stats')
  if (!res.ok) throw new Error('加载知识库状态失败')
  return res.json()
}

export async function indexAllRag() {
  const res = await fetch('/api/rag/index', { method: 'POST' })
  if (!res.ok) throw new Error('同步知识库失败')
  return res.json()
}

export async function searchRag(query, lessonId = null) {
  const res = await fetch('/api/rag/search', {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify({ query, lesson_id: lessonId }),
  })
  if (!res.ok) throw new Error('检索失败')
  return res.json()
}

/** 三路对比：vector / bm25 / hybrid */
export async function compareRagSearch(query, lessonId = null) {
  const res = await fetch('/api/rag/search/compare', {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify({ query, lesson_id: lessonId }),
  })
  if (!res.ok) {
    const text = await res.text()
    throw new Error(text || '三路检索对比失败')
  }
  return res.json()
}

export function tutorChatStream(payload, onEvent) {
  return new Promise((resolve, reject) => {
    fetch('/api/chat/stream', {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify(payload),
    })
      .then(async (res) => {
        if (!res.ok) {
          reject(new Error(await res.text()))
          return
        }
        const reader = res.body.getReader()
        const decoder = new TextDecoder()
        let buffer = ''
        let donePayload = null

        while (true) {
          const { value, done } = await reader.read()
          if (done) break
          buffer += decoder.decode(value, { stream: true })
          const parts = buffer.split('\n\n')
          buffer = parts.pop() || ''

          for (const block of parts) {
            const lines = block.split('\n')
            let event = 'message'
            let dataLine = ''
            for (const line of lines) {
              if (line.startsWith('event:')) event = line.slice(6).trim()
              if (line.startsWith('data:')) dataLine = line.slice(5).trim()
            }
            if (!dataLine) continue
            const data = JSON.parse(dataLine)
            onEvent?.(event, data)
            if (event === 'done') donePayload = data
            if (event === 'error') reject(new Error(data.message || 'stream error'))
          }
        }
        resolve(donePayload)
      })
      .catch(reject)
  })
}
