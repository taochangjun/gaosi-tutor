<template>
  <div class="math-diagram">
    <ObserveMatchDiagram
      v-if="spec?.type === 'observe_match'"
      :scene="spec.scene"
      :title="spec.title"
    />

    <template v-else-if="spec?.type === 'views'">
      <p v-if="spec.title" class="diagram-title">{{ spec.title }}</p>
      <div v-if="spec.reference" class="reference">
        <p class="ref-label">参照物</p>
        <svg
          viewBox="0 0 200 72"
          class="ref-svg"
          role="img"
          v-html="referenceSvg(spec.reference)"
        />
      </div>
      <div class="panels" :class="`count-${spec.panels.length}`">
        <div v-for="(panel, i) in spec.panels" :key="i" class="panel">
          <p class="panel-label">{{ panel.label }}</p>
          <svg
            viewBox="0 0 120 110"
            class="panel-svg"
            role="img"
            v-html="panelSvg(panel.icon)"
          />
          <p v-if="panel.caption" class="panel-caption">{{ panel.caption }}</p>
        </div>
      </div>
    </template>
  </div>
</template>

<script setup>
import ObserveMatchDiagram from './ObserveMatchDiagram.vue'

defineProps({
  spec: { type: Object, default: null },
})

function panelSvg(icon) {
  const frame = `
    <defs>
      <linearGradient id="cardBg" x1="0" y1="0" x2="0" y2="1">
        <stop offset="0%" stop-color="#ffffff"/>
        <stop offset="100%" stop-color="#f8f9fa"/>
      </linearGradient>
    </defs>
    <rect x="4" y="4" width="112" height="102" rx="10" fill="url(#cardBg)" stroke="#ffb347" stroke-width="2"/>
  `
  return frame + iconSvg(icon)
}

function referenceSvg(ref) {
  if (ref === 'pencil_horizontal') {
    return `
      <rect width="200" height="72" fill="#fef9e7" rx="8"/>
      <rect x="24" y="28" width="130" height="18" rx="9" fill="#f4d03f" stroke="#d4ac0d" stroke-width="1.5"/>
      <rect x="14" y="25" width="20" height="24" rx="5" fill="#f1948a" stroke="#e74c3c"/>
      <polygon points="154,37 172,28 172,46" fill="#566573" stroke="#2c3e50"/>
      <text x="100" y="62" text-anchor="middle" font-size="11" fill="#636e72">铅笔（侧面）</text>
    `
  }
  if (ref === 'box') {
    return `
      <rect width="200" height="72" fill="#ebf5fb" rx="8"/>
      <rect x="55" y="16" width="90" height="40" fill="#aed6f1" stroke="#3498db" stroke-width="2"/>
    `
  }
  if (ref === 'cube') {
    return `
      <rect width="200" height="72" fill="#f4f6f6" rx="8"/>
      <polygon points="80,38 110,22 140,38 110,54" fill="#d5dbdb" stroke="#7f8c8d"/>
      <polygon points="80,38 80,52 110,68 110,54" fill="#aab7b8" stroke="#7f8c8d"/>
      <polygon points="110,54 110,68 140,52 140,38" fill="#85929e" stroke="#7f8c8d"/>
    `
  }
  if (ref === 'tree_side') {
    return `
      <rect width="200" height="72" fill="#dff9fb" rx="8"/>
      <rect x="92" y="32" width="16" height="32" rx="4" fill="#8B4513"/>
      <ellipse cx="100" cy="28" rx="40" ry="24" fill="#27ae60" stroke="#1e8449"/>
      <ellipse cx="100" cy="18" rx="10" ry="6" fill="#d35400"/>
    `
  }
  return ''
}

function iconSvg(icon) {
  const dice = {
    dice_1: [[60, 55]],
    dice_2: [[45, 42], [75, 68]],
    dice_3: [[45, 38], [60, 55], [75, 72]],
    dice_4: [[45, 40], [75, 40], [45, 70], [75, 70]],
    dice_5: [[45, 38], [75, 38], [60, 55], [45, 72], [75, 72]],
    dice_6: [[45, 38], [75, 38], [45, 55], [75, 55], [45, 72], [75, 72]],
  }

  if (icon.startsWith('dice_') && dice[icon]) {
    const dots = dice[icon]
      .map(([cx, cy]) => `<circle cx="${cx}" cy="${cy}" r="5" fill="#2c3e50"/>`)
      .join('')
    return `<rect x="26" y="22" width="68" height="68" rx="10" fill="#fff" stroke="#2c3e50" stroke-width="2.5"/>${dots}`
  }

  const map = {
    circle: `<circle cx="60" cy="55" r="34" fill="#fdebd0" stroke="#e67e22" stroke-width="2.5"/>`,
    circle_dot: `<circle cx="60" cy="55" r="34" fill="#fdebd0" stroke="#e67e22" stroke-width="2.5"/><circle cx="60" cy="55" r="5" fill="#2c3e50"/>`,
    rect: `<rect x="26" y="30" width="68" height="50" rx="6" fill="#d6eaf8" stroke="#3498db" stroke-width="2.5"/>`,
    rect_eraser_top: `<rect x="26" y="42" width="68" height="38" rx="6" fill="#d6eaf8" stroke="#3498db" stroke-width="2"/><rect x="26" y="26" width="68" height="20" rx="8" fill="#f1948a" stroke="#e74c3c" stroke-width="1.5"/>`,
    rect_tip_bottom: `<rect x="26" y="30" width="68" height="38" rx="6" fill="#d6eaf8" stroke="#3498db" stroke-width="2"/><polygon points="60,86 42,68 78,68" fill="#566573" stroke="#2c3e50" stroke-width="1.5"/>`,
    square: `<rect x="30" y="30" width="60" height="60" rx="6" fill="#d5f5e3" stroke="#27ae60" stroke-width="2.5"/>`,
    triangle: `<polygon points="60,26 32,82 88,82" fill="#fadbd8" stroke="#e74c3c" stroke-width="2.5"/>`,
    tree_trunk_only: `<rect x="42" y="28" width="36" height="72" rx="6" fill="#8B4513" stroke="#5D2906" stroke-width="2.5"/>`,
    tree_full: `<rect x="50" y="52" width="20" height="48" fill="#8B4513"/><ellipse cx="60" cy="42" rx="38" ry="28" fill="#27ae60" stroke="#1e8449" stroke-width="2"/><ellipse cx="60" cy="28" rx="11" ry="7" fill="#d35400"/>`,
    tree_crown_nest: `<ellipse cx="60" cy="55" rx="42" ry="32" fill="#2ecc71" stroke="#27ae60" stroke-width="2"/><ellipse cx="60" cy="38" rx="12" ry="8" fill="#d35400"/>`,
  }
  return map[icon] || map.rect
}
</script>

<style scoped>
.math-diagram {
  margin: 8px 0 12px;
}

.diagram-title {
  margin: 0 0 10px;
  font-size: 16px;
  font-weight: 800;
  color: #e67e22;
  text-align: center;
}

.ref-label,
.panel-label {
  margin: 0 0 6px;
  font-size: 13px;
  font-weight: 700;
  color: #636e72;
  text-align: center;
}

.reference {
  margin-bottom: 12px;
  padding: 10px;
  background: #fff;
  border-radius: 12px;
  border: 1px solid #ffe0cc;
}

.ref-svg {
  width: 100%;
  max-width: 300px;
  display: block;
  margin: 0 auto;
}

.panels {
  display: grid;
  gap: 12px;
}

.panels.count-1 {
  grid-template-columns: 1fr;
  max-width: 180px;
  margin: 0 auto;
}

.panels.count-2 {
  grid-template-columns: 1fr 1fr;
}

.panels.count-3,
.panels.count-4 {
  grid-template-columns: repeat(3, 1fr);
}

.panel {
  background: #fff;
  border-radius: 12px;
  padding: 8px;
  border: 1px solid #ffe0cc;
  box-shadow: 0 2px 8px rgba(0, 0, 0, 0.04);
}

.panel-svg {
  width: 100%;
  display: block;
}

.panel-caption {
  margin: 6px 0 0;
  font-size: 12px;
  color: #636e72;
  text-align: center;
  line-height: 1.3;
}

@media (max-width: 480px) {
  .panels.count-3,
  .panels.count-4 {
    grid-template-columns: 1fr 1fr;
  }
}
</style>
