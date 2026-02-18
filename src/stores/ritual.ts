import { defineStore } from 'pinia'
import { ref, shallowRef } from 'vue'
import * as THREE from 'three'

export interface FixedSupport {
  id: string
  position: THREE.Vector3
  normal: THREE.Vector3
}

export interface LoadVector {
  id: string
  position: THREE.Vector3
  direction: THREE.Vector3
  magnitude: number
}

export const useRitualStore = defineStore('ritual', () => {
  const mode = ref<'fixed' | 'load'>('fixed')
  const fixedSupports = ref<FixedSupport[]>([])
  const loadVectors = ref<LoadVector[]>([])
  const stlMesh = shallowRef<THREE.Mesh | null>(null)
  const volumeFraction = ref(0.3)

  let nextId = 0
  function genId() {
    return `marker-${nextId++}`
  }

  function setMode(m: 'fixed' | 'load') {
    mode.value = m
  }

  function addFixedSupport(position: THREE.Vector3, normal: THREE.Vector3): string {
    const id = genId()
    fixedSupports.value.push({ id, position: position.clone(), normal: normal.clone() })
    return id
  }

  function addLoadVector(position: THREE.Vector3, direction: THREE.Vector3, magnitude = 1.0): string {
    const id = genId()
    loadVectors.value.push({ id, position: position.clone(), direction: direction.clone(), magnitude })
    return id
  }

  function removeMarker(id: string) {
    const fi = fixedSupports.value.findIndex(s => s.id === id)
    if (fi !== -1) {
      fixedSupports.value.splice(fi, 1)
      return
    }
    const li = loadVectors.value.findIndex(l => l.id === id)
    if (li !== -1) {
      loadVectors.value.splice(li, 1)
    }
  }

  function clearAll() {
    fixedSupports.value = []
    loadVectors.value = []
  }

  return {
    mode,
    fixedSupports,
    loadVectors,
    stlMesh,
    volumeFraction,
    setMode,
    addFixedSupport,
    addLoadVector,
    removeMarker,
    clearAll,
  }
})
