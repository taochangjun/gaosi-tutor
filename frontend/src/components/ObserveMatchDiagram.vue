<template>
  <div class="observe-match">
    <p v-if="title" class="diagram-title">{{ title }}</p>

    <!-- 场景：小猫 + 大树 + 观察位置 -->
    <div v-if="scene === 'tree_cats'" class="block">
      <p class="block-title">① 先看看：小猫站在哪里？</p>
      <svg viewBox="0 0 360 200" class="scene-svg" role="img" aria-label="三只小猫观察大树的位置">
        <defs>
          <linearGradient id="sky" x1="0" y1="0" x2="0" y2="1">
            <stop offset="0%" stop-color="#dff9fb" />
            <stop offset="100%" stop-color="#c7ecee" />
          </linearGradient>
          <linearGradient id="grass" x1="0" y1="0" x2="0" y2="1">
            <stop offset="0%" stop-color="#badc58" />
            <stop offset="100%" stop-color="#6ab04c" />
          </linearGradient>
        </defs>
        <rect width="360" height="200" fill="url(#sky)" rx="12" />
        <rect y="150" width="360" height="50" fill="url(#grass)" />

        <!-- 大树 -->
        <rect x="168" y="95" width="24" height="65" rx="6" fill="#8B4513" stroke="#5D2906" stroke-width="2" />
        <ellipse cx="180" cy="78" rx="52" ry="38" fill="#27ae60" stroke="#1e8449" stroke-width="2" />
        <ellipse cx="165" cy="88" rx="28" ry="22" fill="#2ecc71" opacity="0.85" />
        <ellipse cx="198" cy="85" rx="26" ry="20" fill="#58d68d" opacity="0.85" />
        <!-- 鸟窝 -->
        <ellipse cx="180" cy="58" rx="14" ry="9" fill="#d35400" stroke="#a04000" stroke-width="1.5" />
        <path d="M172 58 Q180 48 188 58" fill="none" stroke="#8B4513" stroke-width="2" />

        <!-- 小猫 B：正面远处 -->
        <g transform="translate(48, 128)">
          <circle cx="0" cy="0" r="14" fill="#f39c12" stroke="#d68910" stroke-width="2" />
          <polygon points="-8,-10 -4,-16 0,-10 4,-16 8,-10" fill="#f39c12" />
          <circle cx="-5" cy="-2" r="2" fill="#2c3e50" />
          <circle cx="5" cy="-2" r="2" fill="#2c3e50" />
          <path d="M-4 4 Q0 8 4 4" fill="none" stroke="#2c3e50" stroke-width="1.5" />
          <text x="0" y="28" text-anchor="middle" font-size="11" font-weight="700" fill="#2c3e50">B 正前方</text>
        </g>
        <path d="M62 120 L155 100" stroke="#e67e22" stroke-width="2" stroke-dasharray="5 4" marker-end="url(#arrow)" />
        <text x="95" y="108" font-size="9" fill="#e67e22">较远</text>

        <!-- 小猫 C：树后 -->
        <g transform="translate(248, 132)">
          <circle cx="0" cy="0" r="12" fill="#e59866" stroke="#ca6f1e" stroke-width="2" />
          <circle cx="-4" cy="-2" r="1.5" fill="#2c3e50" />
          <circle cx="4" cy="-2" r="1.5" fill="#2c3e50" />
          <text x="0" y="26" text-anchor="middle" font-size="11" font-weight="700" fill="#2c3e50">C 树后面</text>
        </g>

        <!-- 小猫 A：树下抬头 -->
        <g transform="translate(180, 168)">
          <circle cx="0" cy="0" r="15" fill="#f1c40f" stroke="#d4ac0d" stroke-width="2" />
          <polygon points="-9,-11 -5,-18 0,-11 5,-18 9,-11" fill="#f1c40f" />
          <circle cx="-5" cy="-2" r="2" fill="#2c3e50" />
          <circle cx="5" cy="-2" r="2" fill="#2c3e50" />
          <path d="M-12 -6 L-12 -18" stroke="#e74c3c" stroke-width="2" />
          <text x="0" y="-22" font-size="10" fill="#e74c3c">抬头看</text>
          <text x="0" y="28" text-anchor="middle" font-size="11" font-weight="700" fill="#2c3e50">A 大树下</text>
        </g>
      </svg>
    </div>

    <!-- 三张照片 -->
    <div v-if="scene === 'tree_cats'" class="block">
      <p class="block-title">② 再想想：每张照片看到了什么？</p>
      <div class="photos">
        <div class="photo-card">
          <p class="photo-label">照片 1</p>
          <svg viewBox="0 0 100 110" class="photo-svg">
            <rect width="100" height="110" rx="8" fill="#ecf0f1" stroke="#bdc3c7" stroke-width="2" />
            <rect x="32" y="15" width="36" height="80" rx="6" fill="#8B4513" stroke="#5D2906" stroke-width="2" />
            <text x="50" y="105" text-anchor="middle" font-size="9" fill="#636e72">只有粗树干</text>
          </svg>
        </div>
        <div class="photo-card">
          <p class="photo-label">照片 2</p>
          <svg viewBox="0 0 100 110" class="photo-svg">
            <rect width="100" height="110" rx="8" fill="#ecf0f1" stroke="#bdc3c7" stroke-width="2" />
            <rect x="44" y="58" width="12" height="38" fill="#8B4513" />
            <ellipse cx="50" cy="48" rx="38" ry="28" fill="#27ae60" stroke="#1e8449" stroke-width="1.5" />
            <ellipse cx="50" cy="32" rx="10" ry="6" fill="#d35400" />
            <text x="50" y="105" text-anchor="middle" font-size="9" fill="#636e72">树+鸟窝都有</text>
          </svg>
        </div>
        <div class="photo-card">
          <p class="photo-label">照片 3</p>
          <svg viewBox="0 0 100 110" class="photo-svg">
            <rect width="100" height="110" rx="8" fill="#ecf0f1" stroke="#bdc3c7" stroke-width="2" />
            <ellipse cx="50" cy="55" rx="42" ry="32" fill="#2ecc71" stroke="#27ae60" stroke-width="1.5" />
            <ellipse cx="50" cy="38" rx="12" ry="7" fill="#d35400" />
            <text x="50" y="105" text-anchor="middle" font-size="9" fill="#636e72">树叶+鸟窝</text>
          </svg>
        </div>
      </div>
    </div>

    <!-- 铅笔三视图（第4讲等） -->
    <div v-if="scene === 'pencil_views'" class="block">
      <p class="block-title">铅笔长什么样？从三个方向看</p>
      <svg viewBox="0 0 360 160" class="scene-svg" role="img" aria-label="铅笔三视图">
        <rect width="360" height="160" fill="#fef9e7" rx="12" />
        <rect x="40" y="68" width="200" height="24" rx="12" fill="#f4d03f" stroke="#d4ac0d" stroke-width="2" />
        <rect x="28" y="64" width="22" height="32" rx="6" fill="#f1948a" stroke="#e74c3c" stroke-width="1.5" />
        <polygon points="240,80 262,68 262,92" fill="#566573" stroke="#2c3e50" stroke-width="1.5" />
        <text x="140" y="115" text-anchor="middle" font-size="11" fill="#636e72">参照：铅笔侧面</text>
        <g transform="translate(280, 30)">
          <text x="40" y="12" text-anchor="middle" font-size="10" font-weight="700">三视图</text>
          <circle cx="20" cy="50" r="18" fill="#fdebd0" stroke="#e67e22" stroke-width="2" />
          <circle cx="20" cy="50" r="3" fill="#333" />
          <text x="20" y="78" text-anchor="middle" font-size="8">端面</text>
          <rect x="48" y="35" width="36" height="30" rx="3" fill="#d6eaf8" stroke="#3498db" stroke-width="1.5" />
          <rect x="48" y="32" width="36" height="10" rx="4" fill="#f1948a" />
          <text x="66" y="78" text-anchor="middle" font-size="8">橡皮端</text>
          <rect x="92" y="35" width="36" height="28" rx="3" fill="#d6eaf8" stroke="#3498db" stroke-width="1.5" />
          <polygon points="110,78 98,63 122,63" fill="#566573" />
          <text x="110" y="90" text-anchor="middle" font-size="8">笔尖</text>
        </g>
      </svg>
    </div>
  </div>
</template>

<script setup>
defineProps({
  scene: { type: String, required: true },
  title: { type: String, default: '' },
})
</script>

<style scoped>
.observe-match {
  background: linear-gradient(180deg, #fff 0%, #fff8f0 100%);
  border: 2px solid #ffb347;
  border-radius: 16px;
  padding: 14px;
  box-shadow: 0 4px 12px rgba(255, 107, 53, 0.12);
}

.diagram-title {
  margin: 0 0 10px;
  font-size: 17px;
  font-weight: 800;
  color: #e67e22;
  text-align: center;
}

.block-title {
  margin: 0 0 8px;
  font-size: 14px;
  font-weight: 700;
  color: #2c3e50;
}

.block + .block {
  margin-top: 14px;
  padding-top: 12px;
  border-top: 1px dashed #ffe0cc;
}

.scene-svg {
  width: 100%;
  display: block;
  border-radius: 10px;
  box-shadow: inset 0 0 0 1px rgba(0, 0, 0, 0.06);
}

.photos {
  display: grid;
  grid-template-columns: repeat(3, 1fr);
  gap: 10px;
}

.photo-card {
  text-align: center;
}

.photo-label {
  margin: 0 0 4px;
  font-size: 13px;
  font-weight: 800;
  color: #e74c3c;
}

.photo-svg {
  width: 100%;
  display: block;
  filter: drop-shadow(0 2px 4px rgba(0, 0, 0, 0.08));
}

@media (max-width: 420px) {
  .photos {
    grid-template-columns: 1fr;
    max-width: 140px;
    margin: 0 auto;
  }
}
</style>
