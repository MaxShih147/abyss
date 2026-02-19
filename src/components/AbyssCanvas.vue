<script setup lang="ts">
import { ref, onMounted, onBeforeUnmount } from 'vue'
import * as THREE from 'three'
import { OrbitControls } from 'three/examples/jsm/controls/OrbitControls.js'
import { STLLoader } from 'three/examples/jsm/loaders/STLLoader.js'
import { EffectComposer } from 'three/examples/jsm/postprocessing/EffectComposer.js'
import { RenderPass } from 'three/examples/jsm/postprocessing/RenderPass.js'
import { UnrealBloomPass } from 'three/examples/jsm/postprocessing/UnrealBloomPass.js'
import { useRitualStore } from '@/stores/ritual'

const store = useRitualStore()
const canvasContainer = ref<HTMLDivElement>()

let renderer: THREE.WebGLRenderer
let camera: THREE.PerspectiveCamera
let scene: THREE.Scene
let controls: OrbitControls
let composer: EffectComposer
let raycaster: THREE.Raycaster
let mouse: THREE.Vector2
let animationId: number

// Track 3D objects mapped by marker ID
const markerObjects = new Map<string, THREE.Object3D>()
// Group for all markers so raycasting can check them
const markerGroup = new THREE.Group()
// The loaded STL mesh reference for raycasting
let loadedMesh: THREE.Mesh | null = null
// Result mesh overlay
let resultMesh: THREE.Mesh | null = null

function initScene() {
  const container = canvasContainer.value!
  const w = container.clientWidth
  const h = container.clientHeight

  // Renderer
  renderer = new THREE.WebGLRenderer({ antialias: true })
  renderer.setSize(w, h)
  renderer.setPixelRatio(Math.min(window.devicePixelRatio, 2))
  renderer.setClearColor(0x050505)
  renderer.toneMapping = THREE.ACESFilmicToneMapping
  renderer.toneMappingExposure = 1.8
  container.appendChild(renderer.domElement)

  // Scene
  scene = new THREE.Scene()
  scene.fog = new THREE.FogExp2(0x050505, 0.015)
  scene.add(markerGroup)

  // Camera
  camera = new THREE.PerspectiveCamera(60, w / h, 0.1, 1000)
  camera.position.set(5, 4, 5)

  // Controls
  controls = new OrbitControls(camera, renderer.domElement)
  controls.enableDamping = true
  controls.dampingFactor = 0.08
  controls.target.set(0, 0, 0)

  // Lighting
  const ambient = new THREE.AmbientLight(0x666666, 1.0)
  scene.add(ambient)

  const keyLight = new THREE.DirectionalLight(0xffffff, 0.8)
  keyLight.position.set(5, 10, 7)
  scene.add(keyLight)

  const greenLight = new THREE.PointLight(0x00ff66, 0.8, 50)
  greenLight.position.set(-5, 8, -3)
  scene.add(greenLight)

  const purpleLight = new THREE.PointLight(0x9944ff, 0.6, 50)
  purpleLight.position.set(5, 6, 5)
  scene.add(purpleLight)

  // Grid
  const grid = new THREE.GridHelper(20, 40, 0x0a3a1a, 0x061a0e)
  grid.position.y = -0.01
  scene.add(grid)

  // Post-processing
  composer = new EffectComposer(renderer)
  composer.addPass(new RenderPass(scene, camera))

  const bloom = new UnrealBloomPass(
    new THREE.Vector2(w, h),
    0.8,  // strength
    0.4,  // radius
    0.6   // threshold
  )
  composer.addPass(bloom)

  // Raycaster
  raycaster = new THREE.Raycaster()
  mouse = new THREE.Vector2()

  // Events
  renderer.domElement.addEventListener('click', onClick)
  window.addEventListener('resize', onResize)
}

function onResize() {
  const container = canvasContainer.value
  if (!container) return
  const w = container.clientWidth
  const h = container.clientHeight
  camera.aspect = w / h
  camera.updateProjectionMatrix()
  renderer.setSize(w, h)
  composer.setSize(w, h)
}

function onClick(event: MouseEvent) {
  if (!loadedMesh) return

  const rect = renderer.domElement.getBoundingClientRect()
  mouse.x = ((event.clientX - rect.left) / rect.width) * 2 - 1
  mouse.y = -((event.clientY - rect.top) / rect.height) * 2 + 1

  raycaster.setFromCamera(mouse, camera)

  // First check if we clicked an existing marker
  const markerHits = raycaster.intersectObjects(markerGroup.children, true)
  if (markerHits.length > 0) {
    // Walk up to find the direct child of markerGroup
    let obj: THREE.Object3D | null = markerHits[0].object
    while (obj && obj.parent !== markerGroup) {
      obj = obj.parent
    }
    if (obj) {
      const markerId = obj.userData.markerId as string
      if (markerId) {
        store.removeMarker(markerId)
        markerGroup.remove(obj)
        disposeObject(obj)
        markerObjects.delete(markerId)
        return
      }
    }
  }

  // Raycast against the loaded mesh
  const meshHits = raycaster.intersectObject(loadedMesh, false)
  if (meshHits.length === 0) return

  const hit = meshHits[0]
  const position = hit.point.clone()
  const normal = hit.face!.normal.clone()
  // Transform normal to world space
  normal.transformDirection(loadedMesh.matrixWorld)

  if (store.mode === 'fixed') {
    spawnTentacle(position, normal)
  } else {
    spawnVoidEye(position, normal)
  }
}

function spawnTentacle(position: THREE.Vector3, normal: THREE.Vector3) {
  const id = store.addFixedSupport(position, normal)

  // Create tentacle: a tapered curved cylinder using CatmullRomCurve3
  const tentacleGroup = new THREE.Group()
  tentacleGroup.userData.markerId = id

  const length = 0.6
  const segments = 12

  // Create a slightly curved path along the normal
  const tangent = new THREE.Vector3().crossVectors(normal, new THREE.Vector3(0, 1, 0))
  if (tangent.length() < 0.01) tangent.crossVectors(normal, new THREE.Vector3(1, 0, 0))
  tangent.normalize()

  const points: THREE.Vector3[] = []
  for (let i = 0; i <= segments; i++) {
    const t = i / segments
    const offset = new THREE.Vector3()
    // Add slight sinusoidal sway
    offset.copy(tangent).multiplyScalar(Math.sin(t * Math.PI * 1.5) * 0.04)
    const p = position.clone().addScaledVector(normal, t * length).add(offset)
    points.push(p)
  }

  const curve = new THREE.CatmullRomCurve3(points)
  const geometry = new THREE.TubeGeometry(curve, segments, 0.03, 8, false)

  // Taper the tube by scaling radii — modify position attribute
  const posAttr = geometry.attributes.position
  const tempVec = new THREE.Vector3()
  for (let i = 0; i < posAttr.count; i++) {
    tempVec.fromBufferAttribute(posAttr, i)
    // Find closest point on curve to determine t
    // Approximate by segment index: each ring has 9 vertices (8 radial + 1 duplicate)
    const ringVerts = 9
    const ringIndex = Math.floor(i / ringVerts)
    const t = ringIndex / segments
    const taper = 1.0 - t * 0.7 // taper from full to 30% at tip

    // Scale relative to curve center at this t
    const center = curve.getPoint(Math.min(t, 1.0))
    tempVec.sub(center).multiplyScalar(taper).add(center)
    posAttr.setXYZ(i, tempVec.x, tempVec.y, tempVec.z)
  }
  posAttr.needsUpdate = true
  geometry.computeVertexNormals()

  const material = new THREE.MeshStandardMaterial({
    color: 0x7a00ff,
    emissive: 0x7a00ff,
    emissiveIntensity: 0.8,
    metalness: 0.4,
    roughness: 0.5,
  })

  const mesh = new THREE.Mesh(geometry, material)
  tentacleGroup.add(mesh)

  // Small sphere at base
  const baseSphere = new THREE.Mesh(
    new THREE.SphereGeometry(0.04, 8, 8),
    material.clone()
  )
  baseSphere.position.copy(position)
  tentacleGroup.add(baseSphere)

  // Store original curve points for animation
  tentacleGroup.userData.curvePoints = points.map(p => p.clone())
  tentacleGroup.userData.tangent = tangent.clone()
  tentacleGroup.userData.normal = normal.clone()
  tentacleGroup.userData.tubeGeometry = geometry
  tentacleGroup.userData.curve = curve

  markerGroup.add(tentacleGroup)
  markerObjects.set(id, tentacleGroup)
}

function spawnVoidEye(position: THREE.Vector3, normal: THREE.Vector3) {
  const id = store.addLoadVector(position, normal)

  const eyeGroup = new THREE.Group()
  eyeGroup.userData.markerId = id

  // Outer sphere (the eye)
  const eyeMat = new THREE.MeshStandardMaterial({
    color: 0xff0044,
    emissive: 0xff0044,
    emissiveIntensity: 1.0,
    metalness: 0.3,
    roughness: 0.4,
  })
  const eyeSphere = new THREE.Mesh(new THREE.SphereGeometry(0.06, 16, 16), eyeMat)
  eyeSphere.position.copy(position).addScaledVector(normal, 0.08)
  eyeGroup.add(eyeSphere)

  // Inner pupil (dark slit)
  const pupilMat = new THREE.MeshStandardMaterial({
    color: 0x050505,
    emissive: 0x000000,
    metalness: 0.9,
    roughness: 0.1,
  })
  const pupil = new THREE.Mesh(new THREE.SphereGeometry(0.025, 8, 8), pupilMat)
  pupil.position.copy(eyeSphere.position).addScaledVector(normal, 0.04)
  pupil.scale.set(0.3, 1.0, 1.0)
  // Orient pupil slit perpendicular to normal
  pupil.lookAt(pupil.position.clone().add(normal))
  eyeGroup.add(pupil)

  // Arrow showing load direction
  const arrowOrigin = position.clone().addScaledVector(normal, 0.08)
  const arrow = new THREE.ArrowHelper(
    normal,
    arrowOrigin,
    0.5,     // length
    0xff0044,
    0.1,     // head length
    0.05     // head width
  )
  eyeGroup.add(arrow)

  // Store for animation
  eyeGroup.userData.eyeMesh = eyeSphere
  eyeGroup.userData.pupilMesh = pupil
  eyeGroup.userData.normal = normal.clone()

  markerGroup.add(eyeGroup)
  markerObjects.set(id, eyeGroup)
}

function disposeObject(obj: THREE.Object3D) {
  obj.traverse((child) => {
    if (child instanceof THREE.Mesh) {
      child.geometry.dispose()
      if (Array.isArray(child.material)) {
        child.material.forEach(m => m.dispose())
      } else {
        child.material.dispose()
      }
    }
  })
}

function animate() {
  animationId = requestAnimationFrame(animate)
  const time = performance.now() * 0.001

  controls.update()

  // Animate markers
  markerGroup.children.forEach((obj) => {
    const id = obj.userData.markerId as string
    if (!id) return

    // Tentacle sway
    if (obj.userData.curvePoints) {
      const curvePoints = obj.userData.curvePoints as THREE.Vector3[]
      const tangent = obj.userData.tangent as THREE.Vector3
      const segments = curvePoints.length - 1
      const tubeGeo = obj.userData.tubeGeometry as THREE.TubeGeometry

      const swayPoints: THREE.Vector3[] = []
      for (let i = 0; i <= segments; i++) {
        const t = i / segments
        const sway = Math.sin(time * 2.0 + t * Math.PI * 2) * 0.015 * t
        const p = curvePoints[i].clone().addScaledVector(tangent, sway)
        swayPoints.push(p)
      }

      const newCurve = new THREE.CatmullRomCurve3(swayPoints)
      const newGeo = new THREE.TubeGeometry(newCurve, segments, 0.03, 8, false)

      // Apply same taper
      const posAttr = newGeo.attributes.position
      const tempVec = new THREE.Vector3()
      for (let i = 0; i < posAttr.count; i++) {
        const ringVerts = 9
        const ringIndex = Math.floor(i / ringVerts)
        const rt = ringIndex / segments
        const taper = 1.0 - rt * 0.7

        const center = newCurve.getPoint(Math.min(rt, 1.0))
        tempVec.fromBufferAttribute(posAttr, i)
        tempVec.sub(center).multiplyScalar(taper).add(center)
        posAttr.setXYZ(i, tempVec.x, tempVec.y, tempVec.z)
      }
      posAttr.needsUpdate = true
      newGeo.computeVertexNormals()

      // Update the mesh geometry
      const tentacleMesh = obj.children[0] as THREE.Mesh
      if (tentacleMesh) {
        tentacleMesh.geometry.dispose()
        tentacleMesh.geometry = newGeo
      }

      // Pulse emissive
      const mat = tentacleMesh?.material as THREE.MeshStandardMaterial
      if (mat) {
        mat.emissiveIntensity = 0.6 + Math.sin(time * 3.0) * 0.3
      }
    }

    // Void eye rotation
    if (obj.userData.eyeMesh) {
      const eyeMesh = obj.userData.eyeMesh as THREE.Mesh
      const pupilMesh = obj.userData.pupilMesh as THREE.Mesh
      const normal = obj.userData.normal as THREE.Vector3

      // Slow rotation around the normal axis
      const axis = normal.clone().normalize()
      const rotQ = new THREE.Quaternion().setFromAxisAngle(axis, time * 0.5)
      pupilMesh.quaternion.copy(rotQ)

      // Pulse
      const mat = eyeMesh.material as THREE.MeshStandardMaterial
      mat.emissiveIntensity = 0.7 + Math.sin(time * 2.5) * 0.4
    }
  })

  composer.render()
}

function loadSTL(file: File) {
  const reader = new FileReader()
  reader.onload = (e) => {
    const arrayBuffer = e.target!.result as ArrayBuffer
    // Save raw bytes for sending to server
    store.stlArrayBuffer = arrayBuffer.slice(0)

    const loader = new STLLoader()
    const geometry = loader.parse(arrayBuffer)

    // Remove old mesh
    if (loadedMesh) {
      scene.remove(loadedMesh)
      disposeObject(loadedMesh)
    }

    // Center and scale
    geometry.computeBoundingBox()
    const box = geometry.boundingBox!
    const center = new THREE.Vector3()
    box.getCenter(center)
    geometry.translate(-center.x, -center.y, -center.z)

    const size = new THREE.Vector3()
    box.getSize(size)
    const maxDim = Math.max(size.x, size.y, size.z)
    const scale = 3.0 / maxDim
    geometry.scale(scale, scale, scale)

    // Re-center vertically so it sits on the grid
    geometry.computeBoundingBox()
    const newBox = geometry.boundingBox!
    geometry.translate(0, -newBox.min.y, 0)

    const material = new THREE.MeshStandardMaterial({
      color: 0x00e0c4,
      emissive: 0x00e0c4,
      emissiveIntensity: 0.6,
      metalness: 0.3,
      roughness: 0.4,
      flatShading: false,
    })

    geometry.computeVertexNormals()
    loadedMesh = new THREE.Mesh(geometry, material)
    scene.add(loadedMesh)
    store.stlMesh = loadedMesh

    // Clear existing markers when loading a new mesh
    clearMarkers()

    // Adjust camera to look at the model
    controls.target.set(0, (newBox.max.y - newBox.min.y) * 0.5 * scale, 0)
    controls.update()
  }
  reader.readAsArrayBuffer(file)
}

function clearMarkers() {
  markerObjects.forEach((obj) => {
    markerGroup.remove(obj)
    disposeObject(obj)
  })
  markerObjects.clear()
  store.clearAll()
}

function displayResult(buffer: ArrayBuffer) {
  // Remove old result if any
  clearResult()

  const loader = new STLLoader()
  const geometry = loader.parse(buffer)
  geometry.computeVertexNormals()

  const material = new THREE.MeshStandardMaterial({
    color: 0x00e0c4,
    emissive: 0x00e0c4,
    emissiveIntensity: 0.6,
    metalness: 0.4,
    roughness: 0.3,
    transparent: true,
    opacity: 0.9,
  })

  resultMesh = new THREE.Mesh(geometry, material)
  scene.add(resultMesh)

  // Fade original mesh to 15% opacity
  if (loadedMesh) {
    const mat = loadedMesh.material as THREE.MeshStandardMaterial
    mat.transparent = true
    mat.opacity = 0.15
    mat.needsUpdate = true
  }
}

function clearResult() {
  if (resultMesh) {
    scene.remove(resultMesh)
    disposeObject(resultMesh)
    resultMesh = null
  }
  // Restore original mesh opacity
  if (loadedMesh) {
    const mat = loadedMesh.material as THREE.MeshStandardMaterial
    mat.transparent = false
    mat.opacity = 1.0
    mat.needsUpdate = true
  }
}

// Expose for parent
defineExpose({ loadSTL, clearMarkers, displayResult, clearResult })

onMounted(() => {
  initScene()
  animate()
})

onBeforeUnmount(() => {
  cancelAnimationFrame(animationId)
  renderer.domElement.removeEventListener('click', onClick)
  window.removeEventListener('resize', onResize)

  // Dispose everything
  markerObjects.forEach((obj) => disposeObject(obj))
  markerObjects.clear()
  if (loadedMesh) disposeObject(loadedMesh)
  renderer.dispose()
  composer.dispose()
})
</script>

<template>
  <div ref="canvasContainer" class="abyss-canvas"></div>
</template>

<style scoped>
.abyss-canvas {
  width: 100%;
  height: 100%;
  overflow: hidden;
}
.abyss-canvas canvas {
  display: block;
}
</style>
