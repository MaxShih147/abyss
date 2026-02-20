<script setup lang="ts">
import { ref, onMounted, onBeforeUnmount } from 'vue'
import * as THREE from 'three'
import { OrbitControls } from 'three/examples/jsm/controls/OrbitControls.js'
import { STLLoader } from 'three/examples/jsm/loaders/STLLoader.js'
import { EffectComposer } from 'three/examples/jsm/postprocessing/EffectComposer.js'
import { RenderPass } from 'three/examples/jsm/postprocessing/RenderPass.js'
import { UnrealBloomPass } from 'three/examples/jsm/postprocessing/UnrealBloomPass.js'
import { SSAOPass } from 'three/examples/jsm/postprocessing/SSAOPass.js'
import { useRitualStore } from '@/stores/ritual'

const store = useRitualStore()
const canvasContainer = ref<HTMLDivElement>()
const gizmoContainer = ref<HTMLDivElement>()

let renderer: THREE.WebGLRenderer
let camera: THREE.PerspectiveCamera
let scene: THREE.Scene
let controls: OrbitControls
let composer: EffectComposer
let ssaoPass: InstanceType<typeof SSAOPass>
let raycaster: THREE.Raycaster
let mouse: THREE.Vector2
let animationId: number
let gridHelper: THREE.GridHelper

// Gizmo
let gizmoRenderer: THREE.WebGLRenderer
let gizmoScene: THREE.Scene
let gizmoCamera: THREE.OrthographicCamera
let gizmoCube: THREE.Mesh
let gizmoEdgeGlow: THREE.LineSegments
let gizmoRaycaster: THREE.Raycaster
let gizmoDragging = false
let gizmoDidDrag = false
let gizmoDragOffset = { x: 0, y: 0 }

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
  renderer.toneMappingExposure = 1.3
  renderer.shadowMap.enabled = true
  renderer.shadowMap.type = THREE.PCFSoftShadowMap
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

  // Lighting — deep cavern with dramatic contrast
  const ambient = new THREE.AmbientLight(0x1a1e20, 0.5)
  scene.add(ambient)

  // Key spotlight from above — sharp shadows, dramatic contrast
  const spotLight = new THREE.SpotLight(0xd4cfc0, 3.0, 50, Math.PI / 5, 0.5, 1)
  spotLight.position.set(2, 12, 3)
  spotLight.castShadow = true
  spotLight.shadow.mapSize.width = 1024
  spotLight.shadow.mapSize.height = 1024
  spotLight.shadow.camera.near = 0.5
  spotLight.shadow.camera.far = 50
  spotLight.shadow.bias = -0.001
  spotLight.target.position.set(0, 1, 0)
  scene.add(spotLight)
  scene.add(spotLight.target)

  // Cyan rim light from behind — silhouette outline (critical for depth)
  const cyanRimLight = new THREE.DirectionalLight(0x00ddaa, 0.8)
  cyanRimLight.position.set(-3, 2, -6)
  scene.add(cyanRimLight)

  // Purple accent from gizmo tentacle side
  const purpleAccent = new THREE.PointLight(0x9944ff, 0.5, 30)
  purpleAccent.position.set(4, 5, 4)
  scene.add(purpleAccent)

  // Faint bio-luminescent green fill
  const fillGreen = new THREE.DirectionalLight(0x556b5a, 0.35)
  fillGreen.position.set(3, 1, -4)
  scene.add(fillGreen)

  // Grid (default off)
  gridHelper = new THREE.GridHelper(20, 40, 0x0a3a1a, 0x061a0e)
  gridHelper.position.y = -0.01
  gridHelper.visible = false
  scene.add(gridHelper)

  // Post-processing: RenderPass -> SSAOPass -> UnrealBloomPass
  composer = new EffectComposer(renderer)
  composer.addPass(new RenderPass(scene, camera))

  ssaoPass = new SSAOPass(scene, camera, w, h)
  ssaoPass.kernelRadius = 8
  ssaoPass.minDistance = 0.005
  ssaoPass.maxDistance = 0.1
  composer.addPass(ssaoPass)

  const bloom = new UnrealBloomPass(
    new THREE.Vector2(w, h),
    0.35,  // strength — visible glow on emissive + rim
    0.5,   // radius
    0.55   // threshold — low enough for tentacles + rim to bloom
  )
  composer.addPass(bloom)

  // Raycaster
  raycaster = new THREE.Raycaster()
  mouse = new THREE.Vector2()

  // Events
  renderer.domElement.addEventListener('click', onClick)
  window.addEventListener('resize', onResize)

  // === Gizmo Cube ===
  initGizmo()
}

function makeGizmoFaceTexture(label: string, color: string, bgColor: string): THREE.CanvasTexture {
  const size = 256
  const cx = size / 2, cy = size / 2
  const canvas = document.createElement('canvas')
  canvas.width = size
  canvas.height = size
  const ctx = canvas.getContext('2d')!

  // Dark void background
  ctx.fillStyle = bgColor
  ctx.fillRect(0, 0, size, size)

  // Eldritch veins radiating outward from center
  ctx.save()
  ctx.globalAlpha = 0.1
  for (let i = 0; i < 10; i++) {
    const angle = (i / 10) * Math.PI * 2 + 0.2
    ctx.beginPath()
    ctx.moveTo(cx, cy)
    const w1 = Math.sin(i * 2.7) * 18
    const w2 = Math.cos(i * 1.9) * 14
    ctx.bezierCurveTo(
      cx + Math.cos(angle) * 35 + w1, cy + Math.sin(angle) * 35 + w2,
      cx + Math.cos(angle) * 80 - w2, cy + Math.sin(angle) * 80 + w1,
      cx + Math.cos(angle) * 130, cy + Math.sin(angle) * 130
    )
    ctx.strokeStyle = color
    ctx.lineWidth = 1.2
    ctx.stroke()
  }
  ctx.restore()

  // Inner glow — radial gradient halo behind the letter (the "eye glow")
  ctx.save()
  const glowGrad = ctx.createRadialGradient(cx, cy, 0, cx, cy, 90)
  glowGrad.addColorStop(0, color)
  glowGrad.addColorStop(0.3, color)
  glowGrad.addColorStop(1, 'transparent')
  ctx.globalAlpha = 0.2
  ctx.fillStyle = glowGrad
  ctx.beginPath()
  ctx.arc(cx, cy, 90, 0, Math.PI * 2)
  ctx.fill()
  ctx.restore()

  // Outer almond eye-shape outline — the letter sits inside this "eye"
  ctx.save()
  ctx.beginPath()
  ctx.moveTo(cx - 85, cy)
  ctx.bezierCurveTo(cx - 48, cy - 55, cx + 48, cy - 55, cx + 85, cy)
  ctx.bezierCurveTo(cx + 48, cy + 55, cx - 48, cy + 55, cx - 85, cy)
  ctx.closePath()
  ctx.strokeStyle = color
  ctx.lineWidth = 2.2
  ctx.globalAlpha = 0.35
  ctx.shadowColor = color
  ctx.shadowBlur = 10
  ctx.stroke()
  ctx.restore()

  // The letter IS the pupil — large, glowing, central
  // Layer 1: broad glow
  ctx.save()
  ctx.font = '600 100px Cormorant Garamond, Georgia, serif'
  ctx.textAlign = 'center'
  ctx.textBaseline = 'middle'
  ctx.fillStyle = color
  ctx.shadowColor = color
  ctx.shadowBlur = 36
  ctx.globalAlpha = 0.4
  ctx.fillText(label, cx, cy + 4)
  ctx.restore()

  // Layer 2: medium glow
  ctx.save()
  ctx.font = '600 100px Cormorant Garamond, Georgia, serif'
  ctx.textAlign = 'center'
  ctx.textBaseline = 'middle'
  ctx.fillStyle = color
  ctx.shadowColor = color
  ctx.shadowBlur = 18
  ctx.globalAlpha = 0.6
  ctx.fillText(label, cx, cy + 4)
  ctx.restore()

  // Layer 3: crisp letter on top
  ctx.save()
  ctx.font = '600 100px Cormorant Garamond, Georgia, serif'
  ctx.textAlign = 'center'
  ctx.textBaseline = 'middle'
  ctx.fillStyle = '#f0ecf8'
  ctx.shadowColor = color
  ctx.shadowBlur = 12
  ctx.fillText(label, cx, cy + 4)
  ctx.restore()

  // Corner tentacle curls
  ctx.save()
  ctx.globalAlpha = 0.18
  ctx.strokeStyle = color
  ctx.lineWidth = 1.5
  const corners = [[12, 12, 0], [size - 12, 12, 1], [size - 12, size - 12, 2], [12, size - 12, 3]]
  for (const [x, y, idx] of corners) {
    const a = (idx as number) * Math.PI * 0.5 + Math.PI * 0.25
    ctx.beginPath()
    ctx.moveTo(x as number, y as number)
    ctx.quadraticCurveTo(
      (x as number) + Math.cos(a) * 25, (y as number) + Math.sin(a) * 25,
      (x as number) + Math.cos(a + 1.2) * 18, (y as number) + Math.sin(a + 1.2) * 18
    )
    ctx.stroke()
  }
  ctx.restore()

  const tex = new THREE.CanvasTexture(canvas)
  tex.needsUpdate = true
  return tex
}

function initGizmo() {
  const el = gizmoContainer.value!
  const size = 160

  gizmoRenderer = new THREE.WebGLRenderer({ antialias: true, alpha: true })
  gizmoRenderer.setSize(size, size)
  gizmoRenderer.setPixelRatio(Math.min(window.devicePixelRatio, 2))
  gizmoRenderer.setClearColor(0x000000, 0)
  el.appendChild(gizmoRenderer.domElement)

  gizmoScene = new THREE.Scene()
  gizmoCamera = new THREE.OrthographicCamera(-2.2, 2.2, 2.2, -2.2, 0.1, 100)
  gizmoCamera.position.set(3, 3, 3)
  gizmoCamera.lookAt(0, 0, 0)

  // Cthulhu eye faces
  const faces = [
    { label: 'R', color: '#ff4466', bg: '#1a0610' },   // +X
    { label: 'L', color: '#ff4466', bg: '#1a0610' },   // -X
    { label: 'T', color: '#00e0c4', bg: '#061a16' },   // +Y
    { label: 'B', color: '#00e0c4', bg: '#061a16' },   // -Y
    { label: 'F', color: '#a855f7', bg: '#0e0620' },   // +Z
    { label: 'K', color: '#a855f7', bg: '#0e0620' },   // -Z
  ]
  const materials = faces.map(f =>
    new THREE.MeshBasicMaterial({ map: makeGizmoFaceTexture(f.label, f.color, f.bg) })
  )

  gizmoCube = new THREE.Mesh(new THREE.BoxGeometry(1.6, 1.6, 1.6), materials)
  gizmoScene.add(gizmoCube)

  // Purple edge glow outline
  const edgesGeo = new THREE.EdgesGeometry(new THREE.BoxGeometry(1.62, 1.62, 1.62))
  const edgeMat = new THREE.LineBasicMaterial({
    color: 0xb266ff,
    transparent: true,
    opacity: 0.9,
    linewidth: 1,
  })
  gizmoEdgeGlow = new THREE.LineSegments(edgesGeo, edgeMat)
  gizmoScene.add(gizmoEdgeGlow)

  gizmoScene.add(new THREE.AmbientLight(0xffffff, 1))

  gizmoRaycaster = new THREE.Raycaster()
  gizmoRenderer.domElement.addEventListener('click', onGizmoClick)

  // Dragging support
  el.addEventListener('mousedown', onGizmoDragStart)
  document.addEventListener('mousemove', onGizmoDragMove)
  document.addEventListener('mouseup', onGizmoDragEnd)
}

function onGizmoDragStart(event: MouseEvent) {
  const el = gizmoContainer.value!
  const rect = el.getBoundingClientRect()
  gizmoDragging = true
  gizmoDidDrag = false
  gizmoDragOffset.x = event.clientX - rect.left
  gizmoDragOffset.y = event.clientY - rect.top
  el.style.cursor = 'grabbing'
  event.preventDefault()
}

function onGizmoDragMove(event: MouseEvent) {
  if (!gizmoDragging) return
  gizmoDidDrag = true
  const el = gizmoContainer.value!
  const parent = el.parentElement!
  const parentRect = parent.getBoundingClientRect()
  let newLeft = event.clientX - parentRect.left - gizmoDragOffset.x
  let newTop = event.clientY - parentRect.top - gizmoDragOffset.y
  newLeft = Math.max(0, Math.min(parentRect.width - el.offsetWidth, newLeft))
  newTop = Math.max(0, Math.min(parentRect.height - el.offsetHeight, newTop))
  el.style.left = newLeft + 'px'
  el.style.top = newTop + 'px'
  el.style.right = 'auto'
}

function onGizmoDragEnd() {
  if (!gizmoDragging) return
  gizmoDragging = false
  const el = gizmoContainer.value
  if (el) el.style.cursor = 'grab'
}

function onGizmoClick(event: MouseEvent) {
  if (gizmoDidDrag) return  // Was a drag, not a click
  const rect = gizmoRenderer.domElement.getBoundingClientRect()
  const mouse2 = new THREE.Vector2(
    ((event.clientX - rect.left) / rect.width) * 2 - 1,
    -((event.clientY - rect.top) / rect.height) * 2 + 1,
  )
  gizmoRaycaster.setFromCamera(mouse2, gizmoCamera)
  const hits = gizmoRaycaster.intersectObject(gizmoCube)
  if (hits.length === 0) return

  const faceIndex = hits[0].face!.materialIndex
  const dist = camera.position.distanceTo(controls.target)
  const target = controls.target.clone()

  // Snap camera to face direction
  const dirs: THREE.Vector3[] = [
    new THREE.Vector3(1, 0, 0),   // 0: +X (R)
    new THREE.Vector3(-1, 0, 0),  // 1: -X (L)
    new THREE.Vector3(0, 1, 0),   // 2: +Y (T)
    new THREE.Vector3(0, -1, 0),  // 3: -Y (B)
    new THREE.Vector3(0, 0, 1),   // 4: +Z (F)
    new THREE.Vector3(0, 0, -1),  // 5: -Z (K)
  ]
  const dir = dirs[faceIndex]
  const newPos = target.clone().addScaledVector(dir, dist)

  // Smooth transition
  const startPos = camera.position.clone()
  const startTime = performance.now()
  const duration = 400

  function animateSnap() {
    const t = Math.min((performance.now() - startTime) / duration, 1)
    const ease = 1 - Math.pow(1 - t, 3) // easeOutCubic
    camera.position.lerpVectors(startPos, newPos, ease)
    camera.lookAt(target)
    controls.update()
    if (t < 1) requestAnimationFrame(animateSnap)
  }
  animateSnap()
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

  // Update stone idol material time uniforms
  if (loadedMesh) {
    const mat = loadedMesh.material as THREE.MeshStandardMaterial
    if (mat.userData.timeUniform) mat.userData.timeUniform.value = time
  }
  if (resultMesh) {
    const mat = resultMesh.material as THREE.MeshStandardMaterial
    if (mat.userData.timeUniform) mat.userData.timeUniform.value = time
  }

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

  // Animate gizmo cube + edge glow
  if (gizmoCube && gizmoCamera) {
    gizmoCube.quaternion.copy(camera.quaternion).invert()
    gizmoEdgeGlow.quaternion.copy(gizmoCube.quaternion)

    // Pulse edge glow opacity
    const edgeMat = gizmoEdgeGlow.material as THREE.LineBasicMaterial
    edgeMat.opacity = 0.5 + 0.4 * Math.sin(time * 2.0)

    gizmoRenderer.render(gizmoScene, gizmoCamera)
  }
}

function createStoneIdolMaterial(variant: 'primary' | 'result'): THREE.MeshStandardMaterial {
  const isPrimary = variant === 'primary'
  const material = new THREE.MeshStandardMaterial({
    color: isPrimary ? 0x3D4D3D : 0x354535,
    emissive: isPrimary ? 0x1a2e1a : 0x0f1f0f,
    emissiveIntensity: isPrimary ? 0.12 : 0.08,
    roughness: isPrimary ? 0.9 : 0.85,
    metalness: 0.2,
    flatShading: false,
  })

  const timeUniform = { value: 0.0 }
  material.userData.timeUniform = timeUniform

  material.onBeforeCompile = (shader) => {
    shader.uniforms.uTime = timeUniform

    // --- Vertex shader: pass world position + world normal ---
    shader.vertexShader = shader.vertexShader.replace(
      '#include <common>',
      `#include <common>
varying vec3 vWorldPos;
varying vec3 vWorldNormal;`
    )
    shader.vertexShader = shader.vertexShader.replace(
      '#include <fog_vertex>',
      `#include <fog_vertex>
vWorldPos = (modelMatrix * vec4(position, 1.0)).xyz;
vWorldNormal = normalize(mat3(modelMatrix) * normal);`
    )

    // --- Fragment preamble: time uniform + simplex noise ---
    shader.fragmentShader = shader.fragmentShader.replace(
      '#include <common>',
      `#include <common>
uniform float uTime;
varying vec3 vWorldPos;
varying vec3 vWorldNormal;

// Ashima Arts simplex 3D noise
vec3 mod289(vec3 x) { return x - floor(x * (1.0 / 289.0)) * 289.0; }
vec4 mod289(vec4 x) { return x - floor(x * (1.0 / 289.0)) * 289.0; }
vec4 permute(vec4 x) { return mod289(((x*34.0)+1.0)*x); }
vec4 taylorInvSqrt(vec4 r) { return 1.79284291400159 - 0.85373472095314 * r; }

float snoise(vec3 v) {
  const vec2 C = vec2(1.0/6.0, 1.0/3.0);
  const vec4 D = vec4(0.0, 0.5, 1.0, 2.0);
  vec3 i  = floor(v + dot(v, C.yyy));
  vec3 x0 = v - i + dot(i, C.xxx);
  vec3 g = step(x0.yzx, x0.xyz);
  vec3 l = 1.0 - g;
  vec3 i1 = min(g.xyz, l.zxy);
  vec3 i2 = max(g.xyz, l.zxy);
  vec3 x1 = x0 - i1 + C.xxx;
  vec3 x2 = x0 - i2 + C.yyy;
  vec3 x3 = x0 - D.yyy;
  i = mod289(i);
  vec4 p = permute(permute(permute(
    i.z + vec4(0.0, i1.z, i2.z, 1.0))
  + i.y + vec4(0.0, i1.y, i2.y, 1.0))
  + i.x + vec4(0.0, i1.x, i2.x, 1.0));
  float n_ = 0.142857142857;
  vec3 ns = n_ * D.wyz - D.xzx;
  vec4 j = p - 49.0 * floor(p * ns.z * ns.z);
  vec4 x_ = floor(j * ns.z);
  vec4 y_ = floor(j - 7.0 * x_);
  vec4 x = x_ * ns.x + ns.yyyy;
  vec4 y = y_ * ns.x + ns.yyyy;
  vec4 h = 1.0 - abs(x) - abs(y);
  vec4 b0 = vec4(x.xy, y.xy);
  vec4 b1 = vec4(x.zw, y.zw);
  vec4 s0 = floor(b0)*2.0 + 1.0;
  vec4 s1 = floor(b1)*2.0 + 1.0;
  vec4 sh = -step(h, vec4(0.0));
  vec4 a0 = b0.xzyw + s0.xzyw*sh.xxyy;
  vec4 a1 = b1.xzyw + s1.xzyw*sh.zzww;
  vec3 p0 = vec3(a0.xy,h.x);
  vec3 p1 = vec3(a0.zw,h.y);
  vec3 p2 = vec3(a1.xy,h.z);
  vec3 p3 = vec3(a1.zw,h.w);
  vec4 norm = taylorInvSqrt(vec4(dot(p0,p0), dot(p1,p1), dot(p2,p2), dot(p3,p3)));
  p0 *= norm.x; p1 *= norm.y; p2 *= norm.z; p3 *= norm.w;
  vec4 m = max(0.6 - vec4(dot(x0,x0), dot(x1,x1), dot(x2,x2), dot(x3,x3)), 0.0);
  m = m * m;
  return 42.0 * dot(m*m, vec4(dot(p0,x0), dot(p1,x1), dot(p2,x2), dot(p3,x3)));
}`
    )

    // --- Color modulation: stone layers + animated slime + cheap AO + purple reflection ---
    shader.fragmentShader = shader.fragmentShader.replace(
      '#include <color_fragment>',
      `#include <color_fragment>
{
  vec3 wp = vWorldPos;

  // Layer 1: Large-scale stone color variation (warm <-> cool grey)
  float n1 = snoise(wp * 0.7);
  diffuseColor.rgb = mix(
    diffuseColor.rgb * vec3(1.08, 1.0, 0.92),
    diffuseColor.rgb * vec3(0.88, 0.93, 1.08),
    n1 * 0.5 + 0.5
  );

  // Layer 2: Moss patches — dark green overlay, 50% max
  float n2 = snoise(wp * 2.5);
  float mossMask = smoothstep(0.05, 0.55, n2);
  diffuseColor.rgb = mix(diffuseColor.rgb, vec3(0.10, 0.16, 0.06), mossMask * 0.5);

  // Layer 3: Fine stone grain — brightness variation
  float n3 = snoise(wp * 8.0);
  diffuseColor.rgb += n3 * 0.04;

  // Layer 4: Verdigris spots — teal patina
  float n4 = snoise(wp * 4.0);
  float verdigrisMask = smoothstep(0.5, 0.7, n4);
  diffuseColor.rgb = mix(diffuseColor.rgb, vec3(0.25, 0.50, 0.42), verdigrisMask);

  // Layer 5: Animated slime/seaweed — slow organic shifting
  float slimeNoise = snoise(wp * 3.0 + vec3(uTime * 0.04, uTime * 0.02, uTime * 0.03));
  float slimeMask = smoothstep(0.2, 0.7, slimeNoise);
  vec3 slimeColor = mix(vec3(0.08, 0.14, 0.05), vec3(0.15, 0.10, 0.04), slimeNoise * 0.5 + 0.5);
  diffuseColor.rgb = mix(diffuseColor.rgb, slimeColor, slimeMask * 0.25);

  // Layer 6: Cheap AO — multi-octave noise crevice darkening
  float crevice = snoise(wp * 5.0) * 0.5 + snoise(wp * 10.0) * 0.3 + snoise(wp * 20.0) * 0.2;
  float aoFactor = smoothstep(-0.4, 0.3, crevice);
  diffuseColor.rgb *= mix(0.50, 1.0, aoFactor);

  // Layer 7: Subtle purple emissive reflection from tentacles
  float purpleNoise = snoise(wp * 1.5 + vec3(0.0, uTime * 0.06, 0.0));
  float purpleMask = smoothstep(0.6, 0.9, purpleNoise);
  diffuseColor.rgb += vec3(0.06, 0.0, 0.10) * purpleMask;
}`
    )

    // --- Normal perturbation: scaly / rough stone grain ---
    shader.fragmentShader = shader.fragmentShader.replace(
      '#include <normal_fragment_maps>',
      `#include <normal_fragment_maps>
{
  vec3 wp = vWorldPos;
  float nA = snoise(wp * 15.0);
  float nB = snoise(wp * 15.0 + vec3(17.3, 0.0, 0.0));
  float nC = snoise(wp * 15.0 + vec3(0.0, 0.0, 31.7));
  normal = normalize(normal + vec3(nA, nB, nC) * 0.12);
}`
    )

    // --- Roughness modulation: verdigris smooth + wet slime patches ---
    shader.fragmentShader = shader.fragmentShader.replace(
      '#include <roughnessmap_fragment>',
      `#include <roughnessmap_fragment>
{
  vec3 wp = vWorldPos;
  float n4 = snoise(wp * 4.0);
  float verdigrisMask = smoothstep(0.5, 0.7, n4);
  roughnessFactor = mix(0.98, 0.82, verdigrisMask);

  // Wet slime patches — glistening low-roughness spots
  float slimeWet = snoise(wp * 3.0 + vec3(uTime * 0.04, uTime * 0.02, uTime * 0.03));
  float wetMask = smoothstep(0.6, 0.85, slimeWet);
  roughnessFactor = mix(roughnessFactor, 0.08, wetMask * 0.5);
}`
    )

    // --- Enhanced dual rim lighting: cyan + purple ---
    shader.fragmentShader = shader.fragmentShader.replace(
      '#include <opaque_fragment>',
      `// Enhanced dual rim lighting
vec3 viewDir = normalize(cameraPosition - vWorldPos);
float rim = 1.0 - max(dot(viewDir, vWorldNormal), 0.0);
float rimPow = pow(rim, 2.5);

// Cyan rim — primary silhouette glow (#00FFBB)
float cyanPulse = 0.85 + 0.15 * sin(uTime * 1.5);
vec3 cyanRim = vec3(0.0, 0.9, 0.6) * rimPow * 0.45 * cyanPulse;

// Purple rim — secondary eldritch glow
float purplePulse = 0.8 + 0.2 * sin(uTime * 2.0 + 1.5);
vec3 purpleRim = vec3(0.4, 0.0, 0.7) * rimPow * 0.2 * purplePulse;

outgoingLight += cyanRim + purpleRim;

// Reproduce opaque_fragment
#ifdef OPAQUE
diffuseColor.a = 1.0;
#endif
#ifdef USE_TRANSMISSION
diffuseColor.a *= material.transmissionAlpha;
#endif
gl_FragColor = vec4(outgoingLight, diffuseColor.a);`
    )
  }

  material.customProgramCacheKey = () => variant
  return material
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

    const material = createStoneIdolMaterial('primary')

    geometry.computeVertexNormals()
    loadedMesh = new THREE.Mesh(geometry, material)
    loadedMesh.castShadow = true
    loadedMesh.receiveShadow = true
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

  const material = createStoneIdolMaterial('result')
  material.transparent = true
  material.opacity = 0.9

  resultMesh = new THREE.Mesh(geometry, material)
  resultMesh.castShadow = true
  resultMesh.receiveShadow = true
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

function toggleOriginal(visible: boolean) {
  if (loadedMesh) loadedMesh.visible = visible
}

function toggleResult(visible: boolean) {
  if (resultMesh) resultMesh.visible = visible
}

function toggleGrid(visible: boolean) {
  if (gridHelper) gridHelper.visible = visible
}

// Expose for parent
defineExpose({ loadSTL, clearMarkers, displayResult, clearResult, toggleOriginal, toggleResult, toggleGrid })

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
  gizmoRenderer?.domElement.removeEventListener('click', onGizmoClick)
  gizmoContainer.value?.removeEventListener('mousedown', onGizmoDragStart)
  document.removeEventListener('mousemove', onGizmoDragMove)
  document.removeEventListener('mouseup', onGizmoDragEnd)
  gizmoRenderer?.dispose()
})
</script>

<template>
  <div ref="canvasContainer" class="abyss-canvas">
    <div ref="gizmoContainer" class="gizmo-wrap"></div>
  </div>
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
.gizmo-wrap {
  position: absolute;
  top: 16px;
  right: 16px;
  width: 160px;
  height: 160px;
  overflow: visible;
  background: transparent;
  cursor: grab;
  z-index: 10;
  user-select: none;
}
</style>
