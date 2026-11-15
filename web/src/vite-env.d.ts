/// <reference types="vite/client" />

interface ImportMetaEnv {
  readonly VITE_API_URL?: string
  readonly VITE_STATIC?: string
}

declare const __BUILD_DATE__: string

interface ImportMeta {
  readonly env: ImportMetaEnv
}
