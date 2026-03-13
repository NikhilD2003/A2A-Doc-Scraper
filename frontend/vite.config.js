import { defineConfig } from 'vite'
import react from '@vitejs/plugin-react'

export default defineConfig({
  plugins: [react()],
  css: {
    // This forces Vite to use standard transformer instead of lightningcss
    transformer: 'postcss',
  },
  build: {
    cssMinify: 'esbuild', // Forces esbuild instead of lightningcss
  }
})