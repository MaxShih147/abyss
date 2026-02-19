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
const gizmoContainer = ref<HTMLDivElement>()

let renderer: THREE.WebGLRenderer
let camera: THREE.PerspectiveCamera
let scene: THREE.Scene
let controls: OrbitControls
let composer: EffectComposer
let raycaster: THREE.Raycaster
let mouse: THREE.Vector2
let animationId: number
let gridHelper: THREE.GridHelper

// Gizmo
let gizmoRenderer: THREE.WebGLRenderer
let gizmoScene: THREE.Scene
let gizmoCamera: THREE.OrthographicCamera
let gizmoCube: THREE.Mesh
let gizmoRaycaster: THREE.Raycaster
const gizmoTentacles: { mesh: THREE.Mesh, origin: THREE.Vector3, dir: THREE.Vector3, phase: number, perpA: THREE.Vector3, perpB: THREE.Vector3, baseRadius: number }[] = []
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
  renderer.toneMappingExposure = 1.2
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

  // Grid (default off)
  gridHelper = new THREE.GridHelper(20, 40, 0x0a3a1a, 0x061a0e)
  gridHelper.position.y = -0.01
  gridHelper.visible = false
  scene.add(gridHelper)

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

  // Eldritch veins radiating from center
  ctx.save()
  ctx.globalAlpha = 0.12
  for (let i = 0; i < 8; i++) {
    const angle = (i / 8) * Math.PI * 2 + 0.3
    ctx.beginPath()
    ctx.moveTo(cx, cy)
    const wobble1 = Math.sin(i * 2.7) * 20
    const wobble2 = Math.cos(i * 1.9) * 15
    ctx.bezierCurveTo(
      cx + Math.cos(angle) * 40 + wobble1, cy + Math.sin(angle) * 40 + wobble2,
      cx + Math.cos(angle) * 90 - wobble2, cy + Math.sin(angle) * 90 + wobble1,
      cx + Math.cos(angle) * 130, cy + Math.sin(angle) * 130
    )
    ctx.strokeStyle = color
    ctx.lineWidth = 1.5
    ctx.stroke()
  }
  ctx.restore()

  // Outer eye shape (almond)
  ctx.save()
  ctx.beginPath()
  ctx.moveTo(cx - 55, cy)
  ctx.bezierCurveTo(cx - 30, cy - 38, cx + 30, cy - 38, cx + 55, cy)
  ctx.bezierCurveTo(cx + 30, cy + 38, cx - 30, cy + 38, cx - 55, cy)
  ctx.closePath()
  ctx.strokeStyle = color
  ctx.lineWidth = 2.5
  ctx.shadowColor = color
  ctx.shadowBlur = 10
  ctx.stroke()
  ctx.restore()

  // Iris circle
  ctx.save()
  ctx.beginPath()
  ctx.arc(cx, cy, 22, 0, Math.PI * 2)
  ctx.strokeStyle = color
  ctx.lineWidth = 1.5
  ctx.shadowColor = color
  ctx.shadowBlur = 6
  ctx.stroke()
  ctx.restore()

  // Pupil — vertical slit
  ctx.save()
  ctx.beginPath()
  ctx.ellipse(cx, cy, 6, 20, 0, 0, Math.PI * 2)
  ctx.fillStyle = color
  ctx.shadowColor = color
  ctx.shadowBlur = 10
  ctx.fill()
  ctx.restore()

  // Direction letter — prominent, readable, matching UI display font
  ctx.save()
  ctx.fillStyle = '#e8e0f0'
  ctx.font = 'bold 42px Cormorant Garamond, Georgia, serif'
  ctx.textAlign = 'center'
  ctx.textBaseline = 'middle'
  ctx.shadowColor = color
  ctx.shadowBlur = 14
  ctx.fillText(label, cx, cy + 2)
  ctx.restore()

  // Corner tentacle curls
  ctx.save()
  ctx.globalAlpha = 0.2
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

function buildTaperedTube(curve: THREE.CatmullRomCurve3, tubSegs: number, radSegs: number, radiusBase: number, radiusTip: number): THREE.BufferGeometry {
  const geo = new THREE.TubeGeometry(curve, tubSegs, 1, radSegs, false)
  const pos = geo.attributes.position
  const frames = curve.computeFrenetFrames(tubSegs, false)
  const vPerRing = radSegs + 1
  for (let i = 0; i <= tubSegs; i++) {
    const t = i / tubSegs
    const radius = radiusBase + (radiusTip - radiusBase) * t
    const center = curve.getPointAt(t)
    for (let j = 0; j < vPerRing; j++) {
      const idx = i * vPerRing + j
      const vx = pos.getX(idx)
      const vy = pos.getY(idx)
      const vz = pos.getZ(idx)
      // Get offset from center, normalize, scale by desired radius
      const dx = vx - center.x
      const dy = vy - center.y
      const dz = vz - center.z
      const len = Math.sqrt(dx * dx + dy * dy + dz * dz)
      if (len > 0.0001) {
        pos.setXYZ(idx, center.x + (dx / len) * radius, center.y + (dy / len) * radius, center.z + (dz / len) * radius)
      }
    }
  }
  pos.needsUpdate = true
  geo.computeVertexNormals()
  return geo
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

  gizmoScene.add(new THREE.AmbientLight(0xffffff, 1))

  // 3D tentacles sprouting from cube edges — tapered, varied thickness
  const tentacleMat = new THREE.MeshBasicMaterial({
    color: 0x9b30ff,
    transparent: true,
    opacity: 0.85,
  })

  // Edge midpoints at half-cube-size = 0.8
  const edgeOrigins: [number, number, number, number, number, number][] = [
    [0.8, 0.8, 0,    1, 1, 0],
    [-0.8, 0.8, 0,   -1, 1, 0],
    [0, 0.8, 0.8,    0, 1, 1],
    [0, 0.8, -0.8,   0, 1, -1],
    [0.8, -0.8, 0,   1, -1, 0],
    [-0.8, -0.8, 0,  -1, -1, 0],
    [0, -0.8, 0.8,   0, -1, 1],
    [0, -0.8, -0.8,  0, -1, -1],
    [0.8, 0, 0.8,    1, 0, 1],
    [-0.8, 0, 0.8,   -1, 0, 1],
    [0.8, 0, -0.8,   1, 0, -1],
    [-0.8, 0, -0.8,  -1, 0, -1],
  ]

  // Per-tentacle thickness variation: some thick, some thin
  const radiusVariants = [0.07, 0.05, 0.06, 0.04, 0.065, 0.045, 0.055, 0.07, 0.04, 0.06, 0.05, 0.065]

  for (let i = 0; i < edgeOrigins.length; i++) {
    const [ox, oy, oz, ddx, ddy, ddz] = edgeOrigins[i]
    const origin = new THREE.Vector3(ox, oy, oz)
    const dir = new THREE.Vector3(ddx, ddy, ddz).normalize()
    const phase = i * 1.7
    const baseRadius = radiusVariants[i]

    // Pre-compute stable perpendicular axes
    const arbitrary = Math.abs(dir.y) < 0.9 ? new THREE.Vector3(0, 1, 0) : new THREE.Vector3(1, 0, 0)
    const perpA = new THREE.Vector3().crossVectors(dir, arbitrary).normalize()
    const perpB = new THREE.Vector3().crossVectors(dir, perpA).normalize()

    // Initial geometry (replaced every frame)
    const points: THREE.Vector3[] = []
    const segs = 12
    for (let s = 0; s <= segs; s++) {
      const t = s / segs
      points.push(origin.clone().addScaledVector(dir, t * 0.4))
    }
    const curve = new THREE.CatmullRomCurve3(points)
    const geo = buildTaperedTube(curve, segs, 6, baseRadius, baseRadius * 0.15)
    const mesh = new THREE.Mesh(geo, tentacleMat.clone())
    gizmoScene.add(mesh)
    gizmoTentacles.push({ mesh, origin: origin.clone(), dir: dir.clone(), phase, perpA, perpB, baseRadius })
  }

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

  // Animate gizmo tentacles + sync rotation
  if (gizmoCube && gizmoCamera) {
    gizmoCube.quaternion.copy(camera.quaternion).invert()

    // Writhe tentacles — short, tapered, curling
    for (const t of gizmoTentacles) {
      const segs = 12
      const points: THREE.Vector3[] = []
      // Short breathing cycle
      const breathe = 0.35 + 0.15 * Math.sin(time * 1.4 + t.phase)
      for (let s = 0; s <= segs; s++) {
        const frac = s / segs
        const extension = frac * breathe
        const p = t.origin.clone().addScaledVector(t.dir, extension)
        // Lateral writhing
        const wiggle1 = Math.sin(time * 2.8 + t.phase + frac * Math.PI * 3) * 0.12 * frac * frac
        const wiggle2 = Math.cos(time * 2.0 + t.phase * 1.3 + frac * Math.PI * 2) * 0.1 * frac * frac
        p.addScaledVector(t.perpA, wiggle1)
        p.addScaledVector(t.perpB, wiggle2)
        // Curl at tip
        if (frac > 0.6) {
          const curlFrac = (frac - 0.6) / 0.4
          const curlStrength = curlFrac * curlFrac * 0.2 * (0.8 + 0.5 * Math.sin(time * 2.2 + t.phase))
          p.addScaledVector(t.dir, -curlStrength)
          const spiralAngle = time * 3.5 + t.phase + curlFrac * Math.PI * 1.5
          p.addScaledVector(t.perpA, Math.sin(spiralAngle) * curlStrength * 0.6)
          p.addScaledVector(t.perpB, Math.cos(spiralAngle) * curlStrength * 0.6)
        }
        points.push(p)
      }
      const curve = new THREE.CatmullRomCurve3(points)
      // Tapered: thick at base, thin at tip
      const newGeo = buildTaperedTube(curve, segs, 6, t.baseRadius, t.baseRadius * 0.12)
      t.mesh.geometry.dispose()
      t.mesh.geometry = newGeo

      // Rotate with cube
      t.mesh.quaternion.copy(gizmoCube.quaternion)

      // Pulse opacity
      const mat = t.mesh.material as THREE.MeshBasicMaterial
      mat.opacity = 0.5 + 0.35 * Math.sin(time * 1.5 + t.phase)
    }

    gizmoRenderer.render(gizmoScene, gizmoCamera)
  }
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
      metalness: 0.2,
      roughness: 0.5,
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
  border-radius: 14px;
  overflow: visible;
  border: 1.5px solid rgba(168, 85, 247, 0.4);
  background: rgba(4, 4, 7, 0.7);
  cursor: grab;
  z-index: 10;
  box-shadow:
    0 0 30px rgba(155, 48, 255, 0.3),
    0 0 60px rgba(155, 48, 255, 0.15),
    0 0 100px rgba(155, 48, 255, 0.08),
    inset 0 0 20px rgba(0, 0, 0, 0.6);
  animation: gizmo-pulse 3s ease-in-out infinite;
  user-select: none;
}
.gizmo-wrap canvas {
  border-radius: 14px;
}
@keyframes gizmo-pulse {
  0%, 100% {
    border-color: rgba(155, 48, 255, 0.35);
    box-shadow:
      0 0 25px rgba(155, 48, 255, 0.25),
      0 0 50px rgba(155, 48, 255, 0.12),
      0 0 80px rgba(155, 48, 255, 0.06),
      inset 0 0 20px rgba(0, 0, 0, 0.6);
  }
  50% {
    border-color: rgba(155, 48, 255, 0.7);
    box-shadow:
      0 0 40px rgba(155, 48, 255, 0.45),
      0 0 80px rgba(155, 48, 255, 0.25),
      0 0 120px rgba(155, 48, 255, 0.12),
      inset 0 0 20px rgba(0, 0, 0, 0.6);
  }
}
</style>
