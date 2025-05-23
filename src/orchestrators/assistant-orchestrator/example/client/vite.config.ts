import { defineConfig } from 'vite';
import react from '@vitejs/plugin-react-swc';

// https://vite.dev/config/
export default defineConfig({
  resolve: {
    alias: {
      '@': '/src',
    },
  },
  plugins: [react()],
  base: '/client',
  server: {
    port: 3000
  },
  preview: {
    port: 3000
  }
});
