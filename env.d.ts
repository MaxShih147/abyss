/// <reference types="vite/client" />

declare module '*.vue' {
  import type { DefineComponent } from 'vue'
  const component: DefineComponent<{}, {}, any>
  export default component
}

declare module 'three/examples/jsm/controls/OrbitControls.js' {
  export { OrbitControls } from 'three/examples/jsm/controls/OrbitControls.js'
}

declare module 'three/examples/jsm/loaders/STLLoader.js' {
  export { STLLoader } from 'three/examples/jsm/loaders/STLLoader.js'
}

declare module 'three/examples/jsm/postprocessing/EffectComposer.js' {
  export { EffectComposer } from 'three/examples/jsm/postprocessing/EffectComposer.js'
}

declare module 'three/examples/jsm/postprocessing/RenderPass.js' {
  export { RenderPass } from 'three/examples/jsm/postprocessing/RenderPass.js'
}

declare module 'three/examples/jsm/postprocessing/UnrealBloomPass.js' {
  export { UnrealBloomPass } from 'three/examples/jsm/postprocessing/UnrealBloomPass.js'
}
