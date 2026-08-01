 /**
  * TimeCut 前端 SPA 引擎
  * 纯 Vanilla JS 单页应用
  */
 
 // ── API 客户端 ──
 const API = {
   async get(path) {
     const res = await fetch(path);
     if (!res.ok) throw new Error(`GET ${path} ${res.status}`);
     return res.json();
   },
   async put(path, data) {
     const res = await fetch(path, { method: 'PUT', headers: { 'Content-Type': 'application/json' }, body: JSON.stringify(data) });
     if (!res.ok) throw new Error(`PUT ${path} ${res.status}`);
     return res.json();
   },
   async post(path) {
     const res = await fetch(path, { method: 'POST' });
     if (!res.ok) throw new Error(`POST ${path} ${res.status}`);
     return res.json();
   },
   async del(path) {
     const res = await fetch(path, { method: 'DELETE' });
     if (!res.ok) throw new Error(`DELETE ${path} ${res.status}`);
     return res.json();
   }
 };
 
 // ── Toast 通知 ──
 function toast(msg, type = 'info') {
   const c = document.getElementById('toast-container');
   const el = document.createElement('div');
   const colors = { info: 'bg-accent-600', success: 'bg-green-600', error: 'bg-red-600', warning: 'bg-yellow-600' };
   el.className = `${colors[type] || colors.info} text-white px-4 py-2.5 rounded-lg shadow-lg text-sm flex items-center gap-2 animate__fadeIn`;
   el.innerHTML = msg;
   c.appendChild(el);
   setTimeout(() => { el.style.opacity = '0'; el.style.transition = 'opacity 0.3s'; setTimeout(() => el.remove(), 300); }, 3000);
 }
 
 // ── 导航 ──
 const PAGES = ['dashboard', 'live', 'recordings', 'highlights', 'settings'];
 const PAGE_TITLES = { dashboard: '仪表盘', live: '实时画面', recordings: '录像回看', highlights: '精华视频', settings: '系统设置' };
 
 function navigate(page) {
   document.querySelectorAll('.nav-link').forEach(el => el.classList.remove('active'));
   document.querySelectorAll('.page').forEach(el => el.classList.remove('active'));
   const link = document.querySelector(`[data-page="${page}"]`);
   if (link) link.classList.add('active');
   document.getElementById('page-title').textContent = PAGE_TITLES[page] || page;
   renderPage(page);
 }
 
 window.addEventListener('hashchange', () => {
   const page = location.hash.slice(1) || 'dashboard';
   if (PAGES.includes(page)) navigate(page);
 });
 
 // ── 时钟 ──
 function updateClock() {
   document.getElementById('clock').textContent = new Date().toLocaleString('zh-CN', { hour12: false });
 }
 setInterval(updateClock, 1000);
 
 // ── 系统状态 ──
 async function updateStatus() {
   try {
     const h = await API.get('/api/health');
     const dot = document.getElementById('status-dot');
     const txt = document.getElementById('status-text');
     if (h.status === 'ok') {
       dot.className = 'w-2 h-2 rounded-full bg-green-500';
       txt.textContent = h.recording ? '录制中' : '已就绪';
     } else {
       dot.className = 'w-2 h-2 rounded-full bg-yellow-500';
       txt.textContent = '异常';
     }
   } catch { document.getElementById('status-dot').className = 'w-2 h-2 rounded-full bg-red-500'; document.getElementById('status-text').textContent = '离线'; }
 }
 setInterval(updateStatus, 10000);
 
 // ── 页面渲染器 ──
 function renderPage(page) {
   const content = document.getElementById('page-content');
   const renderers = { dashboard: renderDashboard, live: renderLive, recordings: renderRecordings, highlights: renderHighlights, settings: renderSettings };
   if (renderers[page]) renderers[page](content);
 }
 
 // ══════════ 仪表盘 ══════════
 async function renderDashboard(el) {
   el.innerHTML = '<div class="text-timecut-400 text-center py-20"><div class="animate-spin w-8 h-8 border-2 border-accent-500 border-t-transparent rounded-full mx-auto mb-3"></div>加载中...</div>';
   try {
     const [health, stats, highlights, settings] = await Promise.all([
       API.get('/api/health'), API.get('/api/recordings/stats'), API.get('/api/highlights?page_size=5'), API.get('/api/settings'),
     ]);
     el.innerHTML = `
       <div class="grid grid-cols-1 md:grid-cols-3 gap-4 mb-6">
         <div class="stat-card bg-timecut-800 rounded-xl p-5 border border-timecut-700">
           <div class="text-timecut-500 text-xs mb-1">录制状态</div>
           <div class="text-2xl font-bold text-timecut-100 mb-3">${health.recording ? '<span class="text-green-400">●</span> 录制中' : '<span class="text-yellow-400">●</span> 已停止'}</div>
           <button onclick="toggleRecording()" class="btn w-full text-center text-sm px-3 py-2 rounded-lg ${health.recording ? 'bg-red-600/20 text-red-400 hover:bg-red-600/30' : 'bg-green-600 text-white hover:bg-green-500'}">${health.recording ? '■ 停止录制' : '● 开始录制'}</button>
         </div>
         <div class="stat-card bg-timecut-800 rounded-xl p-5 border border-timecut-700 cursor-pointer hover:border-accent-500/50" onclick="navigate('recordings')">
           <div class="text-timecut-500 text-xs mb-1">录像总数</div>
           <div class="flex items-center justify-between">
             <div class="text-2xl font-bold text-timecut-100">${stats.total_recordings}</div>
             <svg class="w-5 h-5 text-timecut-500" fill="none" stroke="currentColor" viewBox="0 0 24 24"><path stroke-linecap="round" stroke-linejoin="round" stroke-width="2" d="M9 5l7 7-7 7"/></svg>
           </div>
           <div class="text-xs text-timecut-500 mt-1">占用 ${stats.total_size_gb} GB · 保留 ${stats.retention_days} 天</div>
         </div>
         <div class="stat-card bg-timecut-800 rounded-xl p-5 border border-timecut-700 cursor-pointer hover:border-accent-500/50" onclick="navigate('highlights')">
           <div class="text-timecut-500 text-xs mb-1">精华视频</div>
           <div class="flex items-center justify-between">
             <div class="text-2xl font-bold text-timecut-100">${highlights.total}</div>
             <svg class="w-5 h-5 text-timecut-500" fill="none" stroke="currentColor" viewBox="0 0 24 24"><path stroke-linecap="round" stroke-linejoin="round" stroke-width="2" d="M9 5l7 7-7 7"/></svg>
           </div>
           <div class="text-xs text-timecut-500 mt-1">${settings.highlight_enabled ? '自动剪辑已开启' : '自动剪辑已关闭'}</div>
         </div>
       </div>
       <div class="bg-timecut-800 rounded-xl p-5 border border-timecut-700">
         <h3 class="text-sm font-semibold text-timecut-300 mb-4">摄像头信息</h3>
         <div class="flex items-center justify-between py-2 border-b border-timecut-700">
           <span class="text-timecut-400">名称</span>
           <span class="text-timecut-200">${settings.camera_name || '未设置'}</span>
         </div>
         <div class="flex items-center justify-between py-2 border-b border-timecut-700">
           <span class="text-timecut-400">RTSP 地址</span>
           <span class="text-timecut-200 font-mono text-xs">${settings.camera_rtsp_url || '未配置'}</span>
         </div>
         <div class="flex items-center justify-between py-2">
           <span class="text-timecut-400">精华检测时间</span>
           <span class="text-timecut-200">每天 ${settings.highlight_schedule_time}</span>
         </div>
       </div>
       ${highlights.items?.length ? `
       <div class="mt-6">
         <h3 class="text-sm font-semibold text-timecut-300 mb-3">最近精华</h3>
         <div class="video-grid">
           ${highlights.items.map(h => `
             <div class="bg-timecut-800 rounded-xl border border-timecut-700 overflow-hidden">
               <div class="p-4">
                 <div class="text-sm font-medium text-timecut-200">${h.date}</div>
                 <div class="text-xs text-timecut-500 mt-1">${h.duration_min} 分钟 · ${h.clip_count} 个片段</div>
               </div>
             </div>
           `).join('')}
         </div>
       </div>` : ''}
     `;
   } catch (e) { el.innerHTML = `<div class="text-red-400 text-center py-20">加载失败: ${e.message}</div>`; }
 }
 
 // ══════════ 录制控制 ══════════
window.toggleRecording = async function() {
  try {
    const h = await API.get('/api/health');
    const action = h.recording ? 'stop' : 'start';
    await API.post(`/api/recordings/control/${action}`);
    toast(action === 'start' ? '已开始录制' : '已停止录制', 'success');
    updateStatus();
    renderDashboard(document.getElementById('page-content'));
  } catch (e) { toast(`操作失败: ${e.message}`, 'error'); }
};

// ══════════ 实时画面 ══════════
async function loadGo2RtcPlayer() {
  const player = document.getElementById('live-player');
  if (!player) return;

  try {
    // 动态获取 go2rtc 流名（从摄像头 RTSP 地址解析，避免硬编码导致 notfound）
    let streamName = 'cam';
    try {
      const s = await API.get('/api/settings');
      if (s.camera_rtsp_url) {
        const path = s.camera_rtsp_url.split('/').pop();
        if (path) streamName = decodeURIComponent(path);
      }
    } catch (e) {
      // 设置接口失败时回退到默认流名 cam
    }
    // 动态加载本地 video-stream 组件（同源加载，避免跨域限制）
    if (!window.customElements.get('video-stream')) {
      await import('/js/video-stream.js');
    }
    // 组件就绪后再动态创建元素(必须用 JS 赋值 src,触发组件连接逻辑)
    const host = window.location.hostname || 'localhost';
    const vs = document.createElement('video-stream');
    vs.style.display = 'block';
    vs.style.width = '100%';
    vs.style.height = '100%';
    vs.mode = 'mse';
    vs.background = false;
    vs.src = `ws://${host}:1984/api/ws?src=${encodeURIComponent(streamName)}`;
    player.innerHTML = '';
    player.appendChild(vs);
  } catch (e) {
    player.innerHTML = `<div class="w-full h-full flex items-center justify-center text-red-400 text-sm">加载失败: ${e.message}</div>`;
  }
}

function renderLive(el) {
  el.innerHTML = `
    <div class="max-w-4xl mx-auto">
      <div class="bg-timecut-800 rounded-xl border border-timecut-700 overflow-hidden">
        <div class="aspect-video bg-timecut-900 relative" id="live-player">
          <div class="absolute inset-0 w-full h-full flex items-center justify-center text-timecut-500 text-sm">正在加载实时画面...</div>
        </div>
        <div class="p-3 border-t border-timecut-700 flex justify-between items-center">
          <span class="text-xs text-timecut-500">go2rtc 实时流</span>
          <button onclick="refreshLive()" class="btn text-xs bg-timecut-700 hover:bg-timecut-600 text-timecut-300 px-3 py-1.5 rounded-lg">刷新</button>
        </div>
      </div>
    </div>
  `;
  loadGo2RtcPlayer();
}

function refreshLive() {
  toast('画面刷新中...', 'info');
  renderLive(document.getElementById('page-content'));
}
 
 // ══════════ 录像回看 ══════════
 async function renderRecordings(el) {
   el.innerHTML = '<div class="text-timecut-400 text-center py-20"><div class="animate-spin w-8 h-8 border-2 border-accent-500 border-t-transparent rounded-full mx-auto mb-3"></div>加载中...</div>';
   try {
     const [recs, dates] = await Promise.all([
       API.get('/api/recordings?page_size=100'), API.get('/api/recordings/dates'),
     ]);
     el.innerHTML = `
       <div class="mb-4 flex items-center gap-3 flex-wrap">
         <h3 class="text-sm font-semibold text-timecut-300">录像文件</h3>
         <span class="text-xs text-timecut-500">共 ${recs.total} 个文件</span>
         <div class="flex gap-2 ml-auto flex-wrap">
           ${(dates.dates || []).slice(0, 14).map(d => `<button onclick="filterDate('${d}')" class="btn text-xs bg-timecut-800 hover:bg-timecut-700 text-timecut-400 px-3 py-1.5 rounded-lg border border-timecut-700">${d}</button>`).join('')}
         </div>
       </div>
       ${recs.items?.length ? `
       <div class="bg-timecut-800 rounded-xl border border-timecut-700 overflow-hidden">
         <table class="w-full text-sm">
           <thead><tr class="border-b border-timecut-700 text-timecut-500 text-xs">
             <th class="text-left py-3 px-4">时间</th>
             <th class="text-right py-3 px-4">时长</th>
             <th class="text-right py-3 px-4">大小</th>
             <th class="text-right py-3 px-4">运动</th>
           </tr></thead>
           <tbody>${recs.items.map(r => `
             <tr class="border-b border-timecut-700/50 hover:bg-timecut-700/30 cursor-pointer" onclick="playRecording(${r.id}, '${r.start_time ? new Date(r.start_time).toLocaleString('zh-CN', { hour12: false }) : ''}')">
               <td class="py-2.5 px-4 text-timecut-200">${r.start_time ? new Date(r.start_time).toLocaleString('zh-CN', { hour12: false }) : '-'}</td>
               <td class="py-2.5 px-4 text-right text-timecut-400">${r.duration ? Math.round(r.duration) + 's' : '-'}</td>
               <td class="py-2.5 px-4 text-right text-timecut-400">${r.file_size_mb} MB</td>
               <td class="py-2.5 px-4 text-right">${r.has_motion ? '<span class="text-green-400">●</span>' : '<span class="text-timecut-600">○</span>'}</td>
             </tr>
           `).join('')}</tbody>
         </table>
       </div>` : '<div class="text-timecut-500 text-center py-16 bg-timecut-800 rounded-xl border border-timecut-700"><svg class="w-12 h-12 mx-auto mb-3 text-timecut-600" fill="none" stroke="currentColor" viewBox="0 0 24 24"><path stroke-linecap="round" stroke-linejoin="round" stroke-width="1.5" d="M19 11H5m14 0a2 2 0 012 2v6a2 2 0 01-2 2H5a2 2 0 01-2-2v-6a2 2 0 012-2m14 0V9a2 2 0 00-2-2M5 11V9a2 2 0 012-2m0 0V5a2 2 0 012-2h6a2 2 0 012 2v2M7 7h10"/></svg>暂无录像文件</div>'}
     `;
   } catch (e) { el.innerHTML = `<div class="text-red-400 text-center py-20">加载失败: ${e.message}</div>`; }
 }
 
 window.filterDate = async function(date) {
   const el = document.getElementById('page-content');
   el.innerHTML = '<div class="text-timecut-400 text-center py-20"><div class="animate-spin w-8 h-8 border-2 border-accent-500 border-t-transparent rounded-full mx-auto mb-3"></div>加载中...</div>';
   try {
     const recs = await API.get(`/api/recordings?date=${date}&page_size=100`);
     el.innerHTML = `
       <div class="mb-4 flex items-center gap-3"><button onclick="navigate('recordings')" class="btn text-xs bg-timecut-700 hover:bg-timecut-600 text-timecut-300 px-3 py-1.5 rounded-lg">← 返回</button><span class="text-sm text-timecut-300">${date}</span><span class="text-xs text-timecut-500">${recs.total} 个文件</span></div>
       ${recs.items?.length ? `
       <div class="bg-timecut-800 rounded-xl border border-timecut-700 overflow-hidden">
         <table class="w-full text-sm">
           <thead><tr class="border-b border-timecut-700 text-timecut-500 text-xs">
             <th class="text-left py-3 px-4">时间</th><th class="text-right py-3 px-4">时长</th><th class="text-right py-3 px-4">大小</th>
           </tr></thead>
           <tbody>${recs.items.map(r => `
             <tr class="border-b border-timecut-700/50 hover:bg-timecut-700/30 cursor-pointer" onclick="playRecording(${r.id}, '${r.start_time ? new Date(r.start_time).toLocaleString('zh-CN', { hour12: false }) : ''}')">
               <td class="py-2.5 px-4 text-timecut-200">${r.start_time ? new Date(r.start_time).toLocaleString('zh-CN', { hour12: false }) : '-'}</td>
               <td class="py-2.5 px-4 text-right text-timecut-400">${r.duration ? Math.round(r.duration) + 's' : '-'}</td>
               <td class="py-2.5 px-4 text-right text-timecut-400">${r.file_size_mb} MB</td>
             </tr>
           `).join('')}</tbody>
         </table>
       </div>` : '<div class="text-timecut-500 text-center py-16">该日期无录像</div>'}
     `;
   } catch (e) { el.innerHTML = `<div class="text-red-400 text-center py-20">加载失败: ${e.message}</div>`; }
 };
 
 // ══════════ 精华视频 ══════════
 async function renderHighlights(el) {
   el.innerHTML = '<div class="text-timecut-400 text-center py-20"><div class="animate-spin w-8 h-8 border-2 border-accent-500 border-t-transparent rounded-full mx-auto mb-3"></div>加载中...</div>';
   try {
     const data = await API.get('/api/highlights?page_size=50');
     el.innerHTML = `
       <div class="mb-4 flex items-center gap-3">
         <h3 class="text-sm font-semibold text-timecut-300">精华视频</h3>
         <span class="text-xs text-timecut-500">共 ${data.total} 个</span>
       </div>
       ${data.items?.length ? `
       <div class="video-grid">
         ${data.items.map(h => `
           <div class="bg-timecut-800 rounded-xl border border-timecut-700 overflow-hidden">
             <div class="p-4">
               <div class="flex items-center justify-between mb-3">
                 <span class="text-sm font-medium text-timecut-200">${h.date}</span>
                 <span class="text-xs text-timecut-500">${h.duration_min} 分钟</span>
               </div>
               <div class="text-xs text-timecut-500 mb-3">拼接 ${h.clip_count} 个片段 · ${h.file_size_mb} MB · ${h.strategy} 策略</div>
               <div class="flex gap-2">
                 <a href="/api/highlights/download/${h.id}" class="btn flex-1 text-center text-xs bg-accent-600 hover:bg-accent-500 text-white px-3 py-2 rounded-lg">下载</a>
                 <button onclick="deleteHighlight(${h.id})" class="btn text-xs bg-red-600/20 hover:bg-red-600/30 text-red-400 px-3 py-2 rounded-lg">删除</button>
               </div>
             </div>
           </div>
         `).join('')}
       </div>` : '<div class="text-timecut-500 text-center py-16 bg-timecut-800 rounded-xl border border-timecut-700"><svg class="w-12 h-12 mx-auto mb-3 text-timecut-600" fill="none" stroke="currentColor" viewBox="0 0 24 24"><path stroke-linecap="round" stroke-linejoin="round" stroke-width="1.5" d="M5 3v4M3 5h4M6 17v4m-2-2h4m5-16l2.286 6.857L21 12l-5.714 2.143L13 21l-2.286-6.857L5 12l5.714-2.143L13 3z"/></svg>暂无精华视频</div>'}
     `;
   } catch (e) { el.innerHTML = `<div class="text-red-400 text-center py-20">加载失败: ${e.message}</div>`; }
 }
 
 window.deleteHighlight = async function(id) {
   if (!confirm('确定删除这个精华视频？')) return;
   try {
     await API.del(`/api/highlights/${id}`);
     toast('已删除', 'success');
     renderHighlights(document.getElementById('page-content'));
   } catch (e) { toast(`删除失败: ${e.message}`, 'error'); }
 };
 
 // ══════════ 系统设置 ══════════
 async function renderSettings(el) {
   el.innerHTML = '<div class="text-timecut-400 text-center py-20"><div class="animate-spin w-8 h-8 border-2 border-accent-500 border-t-transparent rounded-full mx-auto mb-3"></div>加载中...</div>';
   try {
     const [s, g] = await Promise.all([
       API.get('/api/settings'),
       API.get('/api/settings/go2rtc/streams').catch(() => ({streams: [], error: 'go2rtc 不可用'})),
     ]);
     el.innerHTML = `
     <div class="max-w-3xl space-y-6">
       <!-- 摄像头设置 -->
       <div class="bg-timecut-800 rounded-xl p-5 border border-timecut-700">
         <h3 class="text-sm font-semibold text-timecut-300 mb-4">摄像头设置</h3>
         <div class="space-y-4">
           <div><label class="block text-xs text-timecut-500 mb-1.5">摄像头名称</label><input id="s-name" class="w-full bg-timecut-900 border border-timecut-700 rounded-lg px-3 py-2 text-sm text-timecut-200 focus:outline-none focus:border-accent-500" value="${s.camera_name || ''}"></div>
           <div><label class="block text-xs text-timecut-500 mb-1.5">RTSP 地址</label><input id="s-rtsp" class="w-full bg-timecut-900 border border-timecut-700 rounded-lg px-3 py-2 text-sm text-timecut-200 font-mono focus:outline-none focus:border-accent-500" value="${s.camera_rtsp_url || ''}" placeholder="rtsp://user:password@ip:554/stream"></div>
           <div>
             <div class="flex items-center justify-between mb-1.5">
               <label class="text-xs text-timecut-500">go2rtc 视频流</label>
               <div class="flex gap-2">
                 <button onclick="openGo2RtcAdd()" class="btn text-xs bg-accent-600 hover:bg-accent-500 text-white px-2.5 py-1 rounded">＋ 添加摄像头</button>
                 <button onclick="refreshGo2RtcStreams()" class="btn text-xs bg-timecut-700 hover:bg-timecut-600 text-timecut-300 px-2.5 py-1 rounded">刷新</button>
               </div>
             </div>
             <div class="space-y-2 max-h-52 overflow-y-auto pr-1">
               ${g.streams.map(st => {
                 const inUse = !!s.camera_rtsp_url && s.camera_rtsp_url.endsWith('/' + st.name);
                 return `
                 <div class="flex items-center justify-between gap-2 bg-timecut-900 border border-timecut-700 rounded-lg px-3 py-2">
                   <div class="min-w-0">
                     <div class="text-xs text-timecut-200 flex items-center gap-1.5">${st.name} <span class="text-[10px] ${st.online ? 'text-green-400' : 'text-timecut-600'}">${st.online ? '●在线' : '○离线'}</span></div>
                     <div class="text-[10px] text-timecut-500 font-mono truncate">${st.rtsp_url}</div>
                   </div>
                   <div class="flex items-center gap-1 shrink-0">
                     <button onclick="deleteGo2RtcStream('${st.name}')" class="btn p-1.5 text-timecut-500 hover:text-red-400 rounded" title="删除该视频流">
                       <svg class="w-4 h-4" fill="none" stroke="currentColor" viewBox="0 0 24 24"><path stroke-linecap="round" stroke-linejoin="round" stroke-width="2" d="M19 7l-.867 12.142A2 2 0 0116.138 21H7.862a2 2 0 01-1.995-1.858L5 7m5 4v6m4-6v6m1-10V4a1 1 0 00-1-1h-4a1 1 0 00-1 1v3M4 7h16"/></svg>
                     </button>
                     ${inUse
                       ? '<span class="text-xs text-green-400 px-2.5 py-1">● 使用中</span>'
                       : `<button onclick="useGo2RtcStream('${st.rtsp_url}')" class="btn text-xs bg-accent-600 hover:bg-accent-500 text-white px-2.5 py-1 rounded">使用</button>`}
                   </div>
                 </div>`;
               }).join('')}
               ${!g.streams.length ? `<div class="text-xs text-timecut-500 text-center py-3">${g.error ? '⚠ ' + g.error : '暂无 go2rtc 视频流'}</div>` : ''}
             </div>
           </div>
         </div>
       </div>
 
       <!-- 录像设置 -->
       <div class="bg-timecut-800 rounded-xl p-5 border border-timecut-700">
         <h3 class="text-sm font-semibold text-timecut-300 mb-4">录像设置</h3>
         <div class="space-y-4">
           <div><label class="block text-xs text-timecut-500 mb-1.5">录像保留天数（超过此天数的旧录像自动删除）</label><input id="s-retention" type="number" min="1" max="365" class="w-32 bg-timecut-900 border border-timecut-700 rounded-lg px-3 py-2 text-sm text-timecut-200 focus:outline-none focus:border-accent-500" value="${s.recording_retention_days}"></div>
           <div><label class="block text-xs text-timecut-500 mb-1.5">分段时长（分钟）</label><input id="s-segment" type="number" min="5" max="1440" class="w-32 bg-timecut-900 border border-timecut-700 rounded-lg px-3 py-2 text-sm text-timecut-200 focus:outline-none focus:border-accent-500" value="${s.recording_segment_minutes}"></div>
         </div>
       </div>

       <!-- 录制规则 -->
       <div class="bg-timecut-800 rounded-xl p-5 border border-timecut-700">
         <h3 class="text-sm font-semibold text-timecut-300 mb-4">录制规则</h3>
         <div class="space-y-4">
           <div><label class="block text-xs text-timecut-500 mb-1.5">录制间隔（分钟，0 = 连续录制）</label>
            <div class="flex items-center gap-3">
              <input id="s-interval" type="number" min="0" max="1440" class="w-32 bg-timecut-900 border border-timecut-700 rounded-lg px-3 py-2 text-sm text-timecut-200 focus:outline-none focus:border-accent-500" value="${s.recording_interval_minutes ?? 0}">
              <span class="text-xs text-timecut-500">每录一段「分段时长」分钟后，间隔该分钟数再录下一段</span>
            </div>
          </div>
           <div class="grid grid-cols-2 gap-4">
             <div><label class="block text-xs text-timecut-500 mb-1.5">每天开始录制</label><input id="s-start-time" type="time" class="w-full bg-timecut-900 border border-timecut-700 rounded-lg px-3 py-2 text-sm text-timecut-200 focus:outline-none focus:border-accent-500" value="${s.recording_start_time || '00:00'}"></div>
             <div><label class="block text-xs text-timecut-500 mb-1.5">每天结束录制</label><input id="s-end-time" type="time" class="w-full bg-timecut-900 border border-timecut-700 rounded-lg px-3 py-2 text-sm text-timecut-200 focus:outline-none focus:border-accent-500" value="${s.recording_end_time || '23:59'}"></div>
           </div>
           <div class="text-xs text-timecut-500">支持跨午夜时段，如 22:00 至 06:00 表示夜间录制。</div>
         </div>
       </div>
 
       <!-- 精华设置 -->
       <div class="bg-timecut-800 rounded-xl p-5 border border-timecut-700">
         <h3 class="text-sm font-semibold text-timecut-300 mb-4">精华视频设置</h3>
         <div class="space-y-4">
           <div class="flex items-center gap-3"><label class="text-xs text-timecut-500">自动剪辑</label><button id="s-highlight-toggle" onclick="toggleHighlight()" class="btn relative w-12 h-6 rounded-full transition-colors ${s.highlight_enabled ? 'bg-accent-600' : 'bg-timecut-600'}"><span class="absolute left-0 top-0.5 w-5 h-5 bg-white rounded-full transition-transform ${s.highlight_enabled ? 'translate-x-[26px]' : 'translate-x-0.5'}"></span></button></div>
           <div><label class="block text-xs text-timecut-500 mb-1.5">精华视频时长（分钟）</label><input id="s-hl-duration" type="number" min="1" max="30" class="w-32 bg-timecut-900 border border-timecut-700 rounded-lg px-3 py-2 text-sm text-timecut-200 focus:outline-none focus:border-accent-500" value="${s.highlight_duration_minutes}"></div>
           <div><label class="block text-xs text-timecut-500 mb-1.5">每日检测时间</label><input id="s-hl-time" type="time" class="w-36 bg-timecut-900 border border-timecut-700 rounded-lg px-3 py-2 text-sm text-timecut-200 focus:outline-none focus:border-accent-500" value="${s.highlight_schedule_time}"></div>
           <div><label class="block text-xs text-timecut-500 mb-1.5">运动检测灵敏度（1-100，越高越灵敏）</label>
             <div class="flex items-center gap-3">
               <input id="s-sensitivity" type="range" min="1" max="100" class="flex-1 accent-accent-500" value="${s.detection_sensitivity}">
               <span class="text-xs text-timecut-400 w-8 text-right" id="sens-value">${s.detection_sensitivity}</span>
             </div>
           </div>
         </div>
       </div>
 
       <div class="flex gap-3">
         <button onclick="saveSettings()" class="btn bg-accent-600 hover:bg-accent-500 text-white px-6 py-2.5 rounded-lg text-sm font-medium">保存设置</button>
       </div>
     </div>`;
 
     document.getElementById('s-sensitivity')?.addEventListener('input', function() {
       document.getElementById('sens-value').textContent = this.value;
     });
 
   } catch (e) { el.innerHTML = `<div class="text-red-400 text-center py-20">加载失败: ${e.message}</div>`; }
 }
 
 window.toggleHighlight = function() {
  const btn = document.getElementById('s-highlight-toggle');
  const enabled = !btn.classList.contains('bg-accent-600');
  btn.className = `btn relative w-12 h-6 rounded-full transition-colors ${enabled ? 'bg-accent-600' : 'bg-timecut-600'}`;
  btn.querySelector('span').className = `absolute left-0 top-0.5 w-5 h-5 bg-white rounded-full transition-transform ${enabled ? 'translate-x-[26px]' : 'translate-x-0.5'}`;
};
 
 window.useGo2RtcStream = async function(rtsp) {
  const input = document.getElementById('s-rtsp');
  if (!input) return;
  input.value = rtsp;
  toast('已选用 go2rtc 视频流，正在保存...', 'info');
  await saveSettings();
};

window.deleteGo2RtcStream = async function(name) {
  if (!confirm(`确定删除视频流「${name}」？`)) return;
  try {
    const res = await API.del(`/api/settings/go2rtc/streams/${encodeURIComponent(name)}`);
    if (res.status === 'error') { toast(res.message || '删除失败', 'error'); return; }
    toast(res.message || `已删除视频流「${name}」`, 'success');
    setTimeout(() => renderSettings(document.getElementById('page-content')), 800);
  } catch (e) { toast(`删除失败: ${e.message}`, 'error'); }
};

// ══════════ 添加摄像头向导（本地中文版）══════════
function openGo2RtcAdd() {
  let modal = document.getElementById('go2rtc-add-modal');
  if (!modal) {
    modal = document.createElement('div');
    modal.id = 'go2rtc-add-modal';
    modal.className = 'fixed inset-0 z-50 hidden';
    modal.innerHTML = `
      <div class="absolute inset-0 bg-black/80" onclick="closeGo2RtcAdd()"></div>
      <div class="relative z-10 max-w-3xl mx-auto h-full flex items-center p-4">
        <div class="w-full bg-timecut-900 rounded-xl border border-timecut-700 overflow-hidden flex flex-col h-[85vh]">
          <div class="flex items-center justify-between px-4 py-3 border-b border-timecut-700">
            <span class="text-sm text-timecut-200">添加摄像头</span>
            <button onclick="closeGo2RtcAdd()" class="text-timecut-500 hover:text-timecut-300 text-lg leading-none">✕</button>
          </div>
          <iframe id="go2rtc-add-frame" class="flex-1 w-full border-0" src="/add-camera.html"></iframe>
        </div>
      </div>`;
    document.body.appendChild(modal);
  }
  const frame = document.getElementById('go2rtc-add-frame');
  // 避免重复设置 src 导致页面重复加载
  if (frame.getAttribute('src') !== '/add-camera.html') {
    frame.src = '/add-camera.html';
  }
  modal.classList.remove('hidden');
}

window.closeGo2RtcAdd = function() {
  const modal = document.getElementById('go2rtc-add-modal');
  if (modal) modal.classList.add('hidden');
};

// 监听添加向导的完成消息：自动填入 RTSP 地址并保存
window.addEventListener('message', async (e) => {
  if (!e.data || e.data.type !== 'stream-added') return;
  const input = document.getElementById('s-rtsp');
  if (input) input.value = e.data.rtsp;
  toast(`已添加摄像头「${e.data.name}」，正在应用配置...`, 'success');
  closeGo2RtcAdd();
  setTimeout(() => saveSettings(), 300);
});

window.refreshGo2RtcStreams = function() {
  toast('正在刷新视频流...', 'info');
  renderSettings(document.getElementById('page-content'));
};

window.saveSettings = async function() {
   const data = {
     camera_name: document.getElementById('s-name')?.value,
     camera_rtsp_url: document.getElementById('s-rtsp')?.value,
     recording_retention_days: parseInt(document.getElementById('s-retention')?.value),
     recording_segment_minutes: parseInt(document.getElementById('s-segment')?.value),
     recording_interval_minutes: parseInt(document.getElementById('s-interval')?.value) || 0,
     recording_start_time: document.getElementById('s-start-time')?.value || '00:00',
     recording_end_time: document.getElementById('s-end-time')?.value || '23:59',
     highlight_enabled: document.getElementById('s-highlight-toggle')?.classList.contains('bg-accent-600'),
     highlight_duration_minutes: parseInt(document.getElementById('s-hl-duration')?.value),
     highlight_schedule_time: document.getElementById('s-hl-time')?.value,
     detection_sensitivity: parseInt(document.getElementById('s-sensitivity')?.value),
   };
   try {
     await API.put('/api/settings', data);
     toast('设置已保存', 'success');
     // 如果是 RTSP 地址变了，触发录制重启
     if (data.camera_rtsp_url) {
       await API.post('/api/settings/restart-recording');
       toast('录制已重启', 'info');
     }
     updateStatus();
   } catch (e) { toast(`保存失败: ${e.message}`, 'error'); }
 };
 
 // ══════════ 视频播放器 ══════════
const PLAYER_MODAL_HTML = `
<div id="player-modal" class="fixed inset-0 z-50 hidden">
  <div class="absolute inset-0 bg-black/80" onclick="closePlayer()"></div>
  <div class="relative z-10 max-w-5xl mx-auto h-full flex items-center p-4">
    <div class="w-full bg-timecut-900 rounded-xl border border-timecut-700 overflow-hidden">
      <div class="flex items-center justify-between px-4 py-3 border-b border-timecut-700">
        <span class="text-sm text-timecut-200" id="player-title">播放录像</span>
        <button onclick="closePlayer()" class="text-timecut-500 hover:text-timecut-300">
          <svg class="w-5 h-5" fill="none" stroke="currentColor" viewBox="0 0 24 24"><path stroke-linecap="round" stroke-linejoin="round" stroke-width="2" d="M6 18L18 6M6 6l12 12"/></svg>
        </button>
      </div>
      <div class="bg-black">
        <video id="player-video" class="w-full max-h-[70vh]" controls autoplay playsinline></video>
      </div>
    </div>
  </div>
</div>`;

document.body.insertAdjacentHTML('beforeend', PLAYER_MODAL_HTML);

window.playRecording = function(id, timeStr) {
  const modal = document.getElementById('player-modal');
  const video = document.getElementById('player-video');
  const title = document.getElementById('player-title');
  title.textContent = `录像 - ${timeStr || '未知时间'}`;
  video.src = `/api/recordings/play/${id}`;
  video.load();
  modal.classList.remove('hidden');
};

window.closePlayer = function() {
  const modal = document.getElementById('player-modal');
  const video = document.getElementById('player-video');
  video.pause();
  video.src = '';
  modal.classList.add('hidden');
};

// ══════════ 初始化 ══════════
document.addEventListener('DOMContentLoaded', () => {
  const page = location.hash.slice(1) || 'dashboard';
  if (PAGES.includes(page)) navigate(page); else navigate('dashboard');
  updateStatus();
  updateClock();
});
