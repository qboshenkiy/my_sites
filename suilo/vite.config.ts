import { defineConfig } from 'vite'
import react from '@vitejs/plugin-react'
import tailwind from '@tailwindcss/vite'
import { VitePWA } from 'vite-plugin-pwa'
export default defineConfig({
  server:{watch:{ignored:['**/android/**']},proxy:{'/api':'http://127.0.0.1:8081'}},
  plugins: [react(), tailwind(), VitePWA({
    registerType:'prompt', injectRegister:null,
    includeManifestIcons:false,
    manifest:{
      id:'/', name:'Сүйлө — кыргызский язык', short_name:'Сүйлө', lang:'ru', start_url:'/', scope:'/',
      description:'1000 кыргызских слов, короткие занятия и интервальное повторение',
      display:'standalone', background_color:'#f7f6ef', theme_color:'#184c3b',
      icons:[
        {src:'/icon-192.png', sizes:'192x192', type:'image/png'},
        {src:'/icon-512.png', sizes:'512x512', type:'image/png'},
        {src:'/icon-mask.png', sizes:'512x512', type:'image/png', purpose:'maskable'},
      ],
    },
    workbox:{globPatterns:['**/*.{html,js,css,svg,png}', 'audio/{01,02,03,04,16,17,18,24}.mp3'], navigateFallbackDenylist:[/^\/api\//]},
  })],
})
