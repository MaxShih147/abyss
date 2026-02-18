<script setup lang="ts">
import { ref, computed } from 'vue'
import AbyssCanvas from './components/AbyssCanvas.vue'
import { useRitualStore } from './stores/ritual'

const store = useRitualStore()
const canvasRef = ref<InstanceType<typeof AbyssCanvas>>()
const fileInput = ref<HTMLInputElement>()
const isDragging = ref(false)
const panelCollapsed = ref(false)

const totalMarkers = computed(() => store.fixedSupports.length + store.loadVectors.length)

function onLoadSTL() {
  fileInput.value?.click()
}

function onFileChange(event: Event) {
  const input = event.target as HTMLInputElement
  const file = input.files?.[0]
  if (file) {
    canvasRef.value?.loadSTL(file)
    input.value = ''
  }
}

function onClearAll() {
  canvasRef.value?.clearMarkers()
}

function onDragOver(e: DragEvent) {
  e.preventDefault()
  isDragging.value = true
}

function onDragLeave() {
  isDragging.value = false
}

function onDrop(e: DragEvent) {
  e.preventDefault()
  isDragging.value = false
  const file = e.dataTransfer?.files[0]
  if (file && file.name.toLowerCase().endsWith('.stl')) {
    canvasRef.value?.loadSTL(file)
  }
}
</script>

<template>
  <div
    class="app-root"
    @dragover="onDragOver"
    @dragleave="onDragLeave"
    @drop="onDrop"
  >
    <!-- Full-bleed 3D viewport -->
    <AbyssCanvas ref="canvasRef" />

    <!-- Drop overlay -->
    <Transition name="fade">
      <div v-if="isDragging" class="drop-overlay">
        <div class="drop-ring">
          <svg viewBox="0 0 120 120" class="drop-icon">
            <circle cx="60" cy="60" r="50" fill="none" stroke="currentColor" stroke-width="1" stroke-dasharray="6 4" />
            <path d="M60 35 v30 M45 55 l15 15 l15-15" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round" />
          </svg>
          <span class="drop-text">Release to summon</span>
        </div>
      </div>
    </Transition>

    <!-- Floating control panel -->
    <aside :class="['panel', { collapsed: panelCollapsed }]">
      <!-- Panel header -->
      <div class="panel-header">
        <div class="brand">
          <h1 class="logo">Abyss</h1>
          <div class="logo-rule"></div>
          <p class="subtitle">Topology Optimization</p>
        </div>
        <button class="collapse-btn" @click="panelCollapsed = !panelCollapsed" :title="panelCollapsed ? 'Expand' : 'Collapse'">
          <svg width="16" height="16" viewBox="0 0 16 16" fill="none">
            <path :d="panelCollapsed ? 'M6 3l5 5-5 5' : 'M10 3l-5 5 5 5'" stroke="currentColor" stroke-width="1.5" stroke-linecap="round" stroke-linejoin="round"/>
          </svg>
        </button>
      </div>

      <div class="panel-body" v-show="!panelCollapsed">
        <!-- Mode Selector -->
        <div class="section">
          <div class="section-label">Mode</div>
          <div class="mode-toggle">
            <button
              :class="['mode-btn', { active: store.mode === 'fixed' }]"
              @click="store.setMode('fixed')"
            >
              <span class="mode-indicator fixed"></span>
              <span class="mode-text">
                <span class="mode-name">Anchor</span>
                <span class="mode-desc">Fixed support</span>
              </span>
            </button>
            <button
              :class="['mode-btn', { active: store.mode === 'load' }]"
              @click="store.setMode('load')"
            >
              <span class="mode-indicator load"></span>
              <span class="mode-text">
                <span class="mode-name">Force</span>
                <span class="mode-desc">Load vector</span>
              </span>
            </button>
          </div>
        </div>

        <!-- Volume Fraction -->
        <div class="section">
          <div class="section-label">
            Volume Fraction
            <span class="section-value">{{ (store.volumeFraction * 100).toFixed(0) }}%</span>
          </div>
          <div class="slider-wrap">
            <input
              type="range"
              min="0.05"
              max="0.95"
              step="0.01"
              v-model.number="store.volumeFraction"
              class="slider"
            />
            <div class="slider-track">
              <div class="slider-fill" :style="{ width: ((store.volumeFraction - 0.05) / 0.9 * 100) + '%' }"></div>
            </div>
          </div>
        </div>

        <!-- Markers count -->
        <div class="section" v-if="totalMarkers > 0">
          <div class="markers-grid">
            <div class="marker-stat">
              <div class="marker-dot fixed"></div>
              <div class="marker-info">
                <span class="marker-count">{{ store.fixedSupports.length }}</span>
                <span class="marker-label">anchors</span>
              </div>
            </div>
            <div class="marker-stat">
              <div class="marker-dot load"></div>
              <div class="marker-info">
                <span class="marker-count">{{ store.loadVectors.length }}</span>
                <span class="marker-label">forces</span>
              </div>
            </div>
          </div>
        </div>

        <!-- Actions -->
        <div class="section actions">
          <button class="btn btn-primary" @click="onLoadSTL">
            <svg width="16" height="16" viewBox="0 0 16 16" fill="none">
              <path d="M2 10v3a1 1 0 001 1h10a1 1 0 001-1v-3M8 2v8M5 7l3 3 3-3" stroke="currentColor" stroke-width="1.5" stroke-linecap="round" stroke-linejoin="round"/>
            </svg>
            Import STL
          </button>
          <input
            ref="fileInput"
            type="file"
            accept=".stl"
            style="display: none"
            @change="onFileChange"
          />
          <button
            class="btn btn-ghost"
            @click="onClearAll"
            :disabled="totalMarkers === 0"
          >
            Clear All
          </button>
        </div>

        <!-- Hint -->
        <div class="hint">
          <p>Click surface to place</p>
          <p>Click marker to remove</p>
        </div>
      </div>
    </aside>

    <!-- Floating mode badge (bottom center) -->
    <div class="mode-badge">
      <span :class="['badge-dot', store.mode]"></span>
      {{ store.mode === 'fixed' ? 'Anchor Mode' : 'Force Mode' }}
    </div>

    <!-- Noise texture overlay for depth -->
    <div class="noise"></div>
  </div>
</template>

<style scoped>
.app-root {
  position: relative;
  width: 100%;
  height: 100%;
  overflow: hidden;
}

/* ============ NOISE OVERLAY ============ */
.noise {
  position: fixed;
  inset: 0;
  pointer-events: none;
  z-index: 1000;
  opacity: 0.025;
  background-image: url("data:image/svg+xml,%3Csvg viewBox='0 0 256 256' xmlns='http://www.w3.org/2000/svg'%3E%3Cfilter id='n'%3E%3CfeTurbulence type='fractalNoise' baseFrequency='0.9' numOctaves='4' stitchTiles='stitch'/%3E%3C/filter%3E%3Crect width='100%25' height='100%25' filter='url(%23n)'/%3E%3C/svg%3E");
  background-repeat: repeat;
  background-size: 200px;
}

/* ============ DROP OVERLAY ============ */
.drop-overlay {
  position: absolute;
  inset: 0;
  z-index: 500;
  background: rgba(4, 4, 7, 0.85);
  display: flex;
  align-items: center;
  justify-content: center;
  backdrop-filter: blur(8px);
}

.drop-ring {
  display: flex;
  flex-direction: column;
  align-items: center;
  gap: 16px;
  color: var(--accent-cyan);
  animation: breathe 2s ease-in-out infinite;
}

.drop-icon {
  width: 80px;
  height: 80px;
}

.drop-text {
  font-family: var(--font-display);
  font-size: 18px;
  font-weight: 300;
  font-style: italic;
  letter-spacing: 2px;
}

@keyframes breathe {
  0%, 100% { opacity: 0.6; transform: scale(1); }
  50% { opacity: 1; transform: scale(1.04); }
}

.fade-enter-active, .fade-leave-active {
  transition: opacity 0.3s ease;
}
.fade-enter-from, .fade-leave-to {
  opacity: 0;
}

/* ============ FLOATING PANEL ============ */
.panel {
  position: absolute;
  top: 20px;
  left: 20px;
  bottom: 20px;
  width: 260px;
  z-index: 100;
  display: flex;
  flex-direction: column;
  background: var(--bg-glass);
  backdrop-filter: blur(var(--blur));
  -webkit-backdrop-filter: blur(var(--blur));
  border: 1px solid var(--border-glass);
  border-radius: var(--radius-lg);
  overflow: hidden;
  transition: width var(--transition), background var(--transition);
}

.panel::before {
  content: '';
  position: absolute;
  inset: 0;
  border-radius: var(--radius-lg);
  padding: 1px;
  background: linear-gradient(
    160deg,
    rgba(0, 224, 196, 0.08) 0%,
    transparent 40%,
    transparent 60%,
    rgba(168, 85, 247, 0.06) 100%
  );
  -webkit-mask: linear-gradient(#fff 0 0) content-box, linear-gradient(#fff 0 0);
  -webkit-mask-composite: xor;
  mask-composite: exclude;
  pointer-events: none;
}

.panel.collapsed {
  width: 56px;
}

/* Panel header */
.panel-header {
  display: flex;
  align-items: flex-start;
  justify-content: space-between;
  padding: 24px 20px 16px;
  border-bottom: 1px solid var(--border-glass);
}

.brand {
  overflow: hidden;
}

.collapsed .brand {
  opacity: 0;
  width: 0;
}

.logo {
  font-family: var(--font-display);
  font-size: 32px;
  font-weight: 300;
  letter-spacing: 3px;
  color: var(--text-primary);
  line-height: 1;
  background: linear-gradient(135deg, var(--text-primary) 0%, var(--accent-cyan) 100%);
  -webkit-background-clip: text;
  -webkit-text-fill-color: transparent;
  background-clip: text;
}

.logo-rule {
  width: 32px;
  height: 1px;
  background: linear-gradient(90deg, var(--accent-cyan), transparent);
  margin: 8px 0 6px;
}

.subtitle {
  font-size: 10px;
  font-weight: 400;
  color: var(--text-tertiary);
  letter-spacing: 2.5px;
  text-transform: uppercase;
}

.collapse-btn {
  flex-shrink: 0;
  width: 28px;
  height: 28px;
  display: flex;
  align-items: center;
  justify-content: center;
  border: none;
  background: transparent;
  color: var(--text-tertiary);
  cursor: pointer;
  border-radius: var(--radius-sm);
  transition: color var(--transition), background var(--transition);
}

.collapse-btn:hover {
  color: var(--text-primary);
  background: rgba(255, 255, 255, 0.05);
}

/* Panel body */
.panel-body {
  flex: 1;
  display: flex;
  flex-direction: column;
  padding: 16px 20px 20px;
  gap: 20px;
  overflow-y: auto;
}

/* Sections */
.section {
  display: flex;
  flex-direction: column;
  gap: 10px;
}

.section-label {
  display: flex;
  justify-content: space-between;
  align-items: baseline;
  font-size: 10px;
  font-weight: 500;
  color: var(--text-tertiary);
  text-transform: uppercase;
  letter-spacing: 1.5px;
}

.section-value {
  font-family: var(--font-display);
  font-size: 16px;
  font-weight: 500;
  color: var(--accent-cyan);
  text-transform: none;
  letter-spacing: 0;
}

/* ============ MODE TOGGLE ============ */
.mode-toggle {
  display: flex;
  flex-direction: column;
  gap: 6px;
}

.mode-btn {
  display: flex;
  align-items: center;
  gap: 12px;
  width: 100%;
  padding: 10px 14px;
  border: 1px solid var(--border-glass);
  border-radius: var(--radius-md);
  background: transparent;
  color: var(--text-secondary);
  cursor: pointer;
  transition: all var(--transition);
  font-family: var(--font-body);
  font-size: 13px;
  text-align: left;
}

.mode-btn:hover {
  background: var(--bg-control);
  border-color: rgba(255, 255, 255, 0.1);
}

.mode-btn.active {
  background: var(--bg-control-active);
  border-color: var(--border-glow);
  color: var(--text-primary);
}

.mode-indicator {
  width: 8px;
  height: 8px;
  border-radius: 50%;
  flex-shrink: 0;
  transition: box-shadow var(--transition);
}

.mode-indicator.fixed {
  background: var(--accent-purple);
}

.mode-indicator.load {
  background: var(--accent-amber);
}

.mode-btn.active .mode-indicator.fixed {
  box-shadow: 0 0 8px var(--accent-purple), 0 0 16px var(--accent-purple-dim);
}

.mode-btn.active .mode-indicator.load {
  box-shadow: 0 0 8px var(--accent-amber), 0 0 16px var(--accent-amber-dim);
}

.mode-text {
  display: flex;
  flex-direction: column;
  gap: 1px;
}

.mode-name {
  font-weight: 500;
  font-size: 13px;
  line-height: 1.2;
}

.mode-desc {
  font-size: 10px;
  color: var(--text-tertiary);
  font-weight: 300;
}

.mode-btn.active .mode-desc {
  color: var(--text-secondary);
}

/* ============ SLIDER ============ */
.slider-wrap {
  position: relative;
  height: 20px;
  display: flex;
  align-items: center;
}

.slider {
  position: relative;
  z-index: 2;
  -webkit-appearance: none;
  appearance: none;
  width: 100%;
  height: 20px;
  background: transparent;
  outline: none;
  cursor: pointer;
}

.slider::-webkit-slider-thumb {
  -webkit-appearance: none;
  appearance: none;
  width: 16px;
  height: 16px;
  border-radius: 50%;
  background: var(--accent-cyan);
  border: 2px solid var(--bg-void);
  box-shadow: 0 0 10px rgba(0, 224, 196, 0.4);
  cursor: pointer;
  transition: box-shadow 0.2s;
}

.slider::-webkit-slider-thumb:hover {
  box-shadow: 0 0 16px rgba(0, 224, 196, 0.6);
}

.slider-track {
  position: absolute;
  left: 0;
  right: 0;
  top: 50%;
  transform: translateY(-50%);
  height: 3px;
  background: rgba(255, 255, 255, 0.06);
  border-radius: 2px;
  overflow: hidden;
  pointer-events: none;
}

.slider-fill {
  height: 100%;
  background: linear-gradient(90deg, var(--accent-cyan), rgba(0, 224, 196, 0.4));
  border-radius: 2px;
  transition: width 0.05s;
}

/* ============ MARKERS ============ */
.markers-grid {
  display: grid;
  grid-template-columns: 1fr 1fr;
  gap: 8px;
}

.marker-stat {
  display: flex;
  align-items: center;
  gap: 10px;
  padding: 10px 12px;
  background: var(--bg-control);
  border: 1px solid var(--border-glass);
  border-radius: var(--radius-md);
}

.marker-dot {
  width: 6px;
  height: 6px;
  border-radius: 50%;
  flex-shrink: 0;
}

.marker-dot.fixed {
  background: var(--accent-purple);
  box-shadow: 0 0 6px var(--accent-purple-dim);
}

.marker-dot.load {
  background: var(--accent-amber);
  box-shadow: 0 0 6px var(--accent-amber-dim);
}

.marker-info {
  display: flex;
  flex-direction: column;
}

.marker-count {
  font-family: var(--font-display);
  font-size: 20px;
  font-weight: 500;
  line-height: 1;
  color: var(--text-primary);
}

.marker-label {
  font-size: 9px;
  color: var(--text-tertiary);
  text-transform: uppercase;
  letter-spacing: 1px;
  margin-top: 2px;
}

/* ============ BUTTONS ============ */
.actions {
  gap: 8px;
}

.btn {
  display: flex;
  align-items: center;
  justify-content: center;
  gap: 8px;
  width: 100%;
  padding: 11px 16px;
  border: 1px solid var(--border-glass);
  border-radius: var(--radius-md);
  font-family: var(--font-body);
  font-size: 13px;
  font-weight: 400;
  cursor: pointer;
  transition: all var(--transition);
}

.btn-primary {
  background: linear-gradient(135deg, rgba(0, 224, 196, 0.12) 0%, rgba(0, 224, 196, 0.04) 100%);
  border-color: rgba(0, 224, 196, 0.2);
  color: var(--accent-cyan);
}

.btn-primary:hover {
  background: linear-gradient(135deg, rgba(0, 224, 196, 0.2) 0%, rgba(0, 224, 196, 0.08) 100%);
  border-color: rgba(0, 224, 196, 0.35);
  box-shadow: 0 0 20px rgba(0, 224, 196, 0.1);
}

.btn-ghost {
  background: transparent;
  color: var(--text-tertiary);
  border-color: transparent;
}

.btn-ghost:hover:not(:disabled) {
  color: var(--accent-rose);
  background: rgba(244, 63, 94, 0.06);
}

.btn-ghost:disabled {
  opacity: 0.3;
  cursor: not-allowed;
}

/* ============ HINT ============ */
.hint {
  margin-top: auto;
  padding-top: 16px;
  border-top: 1px solid var(--border-glass);
  font-size: 11px;
  color: var(--text-tertiary);
  line-height: 1.8;
  font-weight: 300;
}

/* ============ MODE BADGE (bottom center) ============ */
.mode-badge {
  position: absolute;
  bottom: 20px;
  left: 50%;
  transform: translateX(-50%);
  z-index: 100;
  display: flex;
  align-items: center;
  gap: 8px;
  padding: 8px 18px;
  background: var(--bg-glass);
  backdrop-filter: blur(var(--blur));
  -webkit-backdrop-filter: blur(var(--blur));
  border: 1px solid var(--border-glass);
  border-radius: var(--radius-pill);
  font-size: 11px;
  font-weight: 400;
  color: var(--text-secondary);
  letter-spacing: 0.5px;
  pointer-events: none;
  transition: all var(--transition);
}

.badge-dot {
  width: 6px;
  height: 6px;
  border-radius: 50%;
  animation: pulse-dot 2s ease-in-out infinite;
}

.badge-dot.fixed {
  background: var(--accent-purple);
  box-shadow: 0 0 6px var(--accent-purple);
}

.badge-dot.load {
  background: var(--accent-amber);
  box-shadow: 0 0 6px var(--accent-amber);
}

@keyframes pulse-dot {
  0%, 100% { opacity: 1; }
  50% { opacity: 0.5; }
}
</style>
