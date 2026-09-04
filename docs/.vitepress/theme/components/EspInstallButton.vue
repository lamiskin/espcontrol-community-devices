<template>
  <!-- Adapted from upstream EspControl's docs component
       (github.com/jtenniswood/espcontrol, docs/.vitepress/theme). -->
  <div class="esp-install-wrapper">
    <div v-if="!supported" class="unsupported">
      Your browser does not support WebSerial. Use Chrome or Edge on desktop.
    </div>
    <div v-else-if="loadError" class="unsupported">
      Failed to load installer. {{ loadError }}
    </div>
    <div v-else class="install-button">
      <esp-web-install-button :manifest="manifestUrl">
        <button slot="activate" class="brand-button">{{ buttonLabel }}</button>
      </esp-web-install-button>
    </div>
  </div>
</template>

<script setup>
import { ref, onMounted, computed } from 'vue'
import { withBase } from 'vitepress'

const props = defineProps({
  slug: { type: String, required: true },
  // 'install' (default): the regular factory image. 'recovery': the P4 C6
  // co-processor repair image (issue #98) — a full USB reflash, never an
  // OTA, so it lives at a separate manifest path that the device's own
  // update entity never points at.
  variant: { type: String, default: 'install' }
})
const manifestPath = computed(() => props.variant === 'recovery'
  ? `recovery-manifest.json`
  : `manifest.json`)
const manifestUrl = computed(() => withBase(`/firmware/${props.slug}/${manifestPath.value}`))
const buttonLabel = computed(() => props.variant === 'recovery'
  ? 'Repair C6 & reinstall firmware'
  : 'Install community firmware')
const supported = ref(false)
const loadError = ref(null)

onMounted(async () => {
  supported.value = 'serial' in navigator
  if (!supported.value) return
  try {
    await import('https://unpkg.com/esp-web-tools@10/dist/web/install-button.js')
  } catch (err) {
    loadError.value = err?.message || 'Network or script load error.'
  }
})
</script>

<style scoped>
.esp-install-wrapper {
  margin: 1.5rem 0;
}

.brand-button {
  display: inline-block;
  border: 1px solid transparent;
  text-align: center;
  font-weight: 600;
  white-space: nowrap;
  transition: color 0.25s, border-color 0.25s, background-color 0.25s;
  border-radius: 20px;
  padding: 0 20px;
  line-height: 38px;
  font-size: 14px;
  color: var(--vp-button-brand-text);
  background-color: var(--vp-button-brand-bg);
  cursor: pointer;
}

.brand-button:hover {
  background-color: var(--vp-button-brand-hover-bg);
}

.unsupported {
  padding: 12px 16px;
  border-radius: 8px;
  background-color: var(--vp-c-warning-soft);
  color: var(--vp-c-warning-1);
  font-size: 14px;
}
</style>
