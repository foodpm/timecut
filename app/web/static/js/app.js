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
function escapeHtml(s) {
  return String(s ?? '').replace(/[&<>"']/g, c => ({ '&': '&amp;', '<': '&lt;', '>': '&gt;', '"': '&quot;', "'": '&#39;' }[c]));
}

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
 const PAGES = ['dashboard', 'live', 'recordings', 'highlights', 'diary', 'settings'];
const PAGE_TITLES = { dashboard: '仪表盘', live: '实时画面', recordings: '录像回看', highlights: '精华视频', diary: '日记', settings: '系统设置' };
 
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
   const renderers = { dashboard: renderDashboard, live: renderLive, recordings: renderRecordings, highlights: renderHighlights, diary: renderDiary, settings: renderSettings };
   if (renderers[page]) renderers[page](content);
 }
 
 // ══════════ 仪表盘 ══════════
 async function renderDashboard(el) {
   el.innerHTML = '<div class="text-timecut-400 text-center py-20"><div class="animate-spin w-8 h-8 border-2 border-accent-500 border-t-transparent rounded-full mx-auto mb-3"></div>加载中...</div>';
   try {
     const [health, stats, highlights, settings] = await Promise.all([
       API.get('/api/health'), API.get('/api/recordings/stats'), API.get('/api/highlights?page_size=5&sort=desc'), API.get('/api/settings'),
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
            <th class="text-left py-3 px-4">画面</th>
            <th class="text-left py-3 px-4">时间</th>
            <th class="text-right py-3 px-4">时长</th>
            <th class="text-right py-3 px-4">大小</th>
            <th class="text-right py-3 px-4">运动</th>
          </tr></thead>
          <tbody>${recs.items.map(r => `
            <tr class="border-b border-timecut-700/50 hover:bg-timecut-700/30 cursor-pointer" onclick="playRecording(${r.id}, '${r.start_time ? new Date(r.start_time).toLocaleString('zh-CN', { hour12: false }) : ''}')">
              <td class="py-2 px-4"><img src="/api/recordings/${r.id}/thumbnail" class="w-24 h-14 object-cover rounded border border-timecut-700" loading="lazy" onerror="this.style.display='none'"></td>
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
            <th class="text-left py-3 px-4">画面</th><th class="text-left py-3 px-4">时间</th><th class="text-right py-3 px-4">时长</th><th class="text-right py-3 px-4">大小</th>
          </tr></thead>
          <tbody>${recs.items.map(r => `
            <tr class="border-b border-timecut-700/50 hover:bg-timecut-700/30 cursor-pointer" onclick="playRecording(${r.id}, '${r.start_time ? new Date(r.start_time).toLocaleString('zh-CN', { hour12: false }) : ''}')">
              <td class="py-2 px-4"><img src="/api/recordings/${r.id}/thumbnail" class="w-24 h-14 object-cover rounded border border-timecut-700" loading="lazy" onerror="this.style.display='none'"></td>
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
function strategyLabel(s) {
  return { ai: '大模型筛选', motion: '运动检测' }[s] || (s + ' 策略');
}

async function renderHighlights(el) {
   el.innerHTML = '<div class="text-timecut-400 text-center py-20"><div class="animate-spin w-8 h-8 border-2 border-accent-500 border-t-transparent rounded-full mx-auto mb-3"></div>加载中...</div>';
   try {
     const data = await API.get('/api/highlights?page_size=50');
     el.innerHTML = `
       <div class="mb-4 flex items-center gap-3">
         <h3 class="text-sm font-semibold text-timecut-300">精华视频</h3>
         <span class="text-xs text-timecut-500">共 ${data.total} 个</span>
         <button onclick="triggerHighlight()" class="btn ml-auto text-xs bg-accent-600 hover:bg-accent-500 text-white px-4 py-2 rounded-lg">手动生成精华视频</button>
       </div>
       ${data.items?.length ? `
      <div class="video-grid">
        ${data.items.map(h => `
          <div class="bg-timecut-800 rounded-xl border border-timecut-700 overflow-hidden">
            <div class="relative group cursor-pointer" onclick="playHighlight(${h.id}, '${h.date}')">
              <img src="/api/highlights/${h.id}/thumbnail" class="w-full aspect-video object-cover" loading="lazy" onerror="this.src='data:image/svg+xml;utf8,<svg xmlns=%22http://www.w3.org/2000/svg%22 viewBox=%220 0 320 180%22><rect fill=%22%230f172a%22 width=%22320%22 height=%22180%22/><text x=%22160%22 y=%2295%22 fill=%22%23475569%22 font-size=%2214%22 text-anchor=%22middle%22>暂无预览</text></svg>'">
              <div class="absolute inset-0 bg-black/30 opacity-0 group-hover:opacity-100 transition-opacity flex items-center justify-center">
                <div class="w-14 h-14 rounded-full bg-white/90 flex items-center justify-center">
                  <svg class="w-6 h-6 text-black ml-1" fill="currentColor" viewBox="0 0 24 24"><path d="M8 5v14l11-7z"/></svg>
                </div>
              </div>
            </div>
            <div class="p-4">
              <div class="flex items-center justify-between mb-2">
                <span class="text-sm font-medium text-timecut-200">${h.date}</span>
                <span class="text-xs text-timecut-500">${h.duration_min} 分钟</span>
              </div>
              <div class="text-xs text-timecut-500 mb-3">拼接 ${h.clip_count} 个片段 · ${h.file_size_mb} MB · ${strategyLabel(h.strategy)}</div>
              <div class="flex gap-2">
                <button onclick="playHighlight(${h.id}, '${h.date}')" class="btn flex-1 text-center text-xs bg-accent-600 hover:bg-accent-500 text-white px-3 py-2 rounded-lg">播放</button>
                <button onclick="deleteHighlight(${h.id})" class="btn text-xs bg-red-600/20 hover:bg-red-600/30 text-red-400 px-3 py-2 rounded-lg">删除</button>
              </div>
            </div>
          </div>
        `).join('')}
      </div>` : '<div class="text-timecut-500 text-center py-16 bg-timecut-800 rounded-xl border border-timecut-700"><svg class="w-12 h-12 mx-auto mb-3 text-timecut-600" fill="none" stroke="currentColor" viewBox="0 0 24 24"><path stroke-linecap="round" stroke-linejoin="round" stroke-width="1.5" d="M5 3v4M3 5h4M6 17v4m-2-2h4m5-16l2.286 6.857L21 12l-5.714 2.143L13 21l-2.286-6.857L5 12l5.714-2.143L13 3z"/></svg>暂无精华视频</div>'}
    `;
    // 若已有生成任务在运行，自动弹出进度面板
    try {
      const [j, d] = await Promise.all([
        API.get('/api/highlights/job'),
        API.get('/api/diary/job').catch(() => ({ running: false })),
      ]);
      if (!document.getElementById('job-panel')) {
        if (j.running) openJobPanel('highlight');
        else if (d.running) openJobPanel('diary');
      }
    } catch (e) { /* 忽略 */ }
  } catch (e) { el.innerHTML = `<div class="text-red-400 text-center py-20">加载失败: ${e.message}</div>`; }
}

window.playHighlight = function(id, dateStr) {
  const modal = document.getElementById('player-modal');
  const video = document.getElementById('player-video');
  const title = document.getElementById('player-title');
  title.textContent = `精华视频 - ${dateStr || ''}`;
  video.src = `/api/highlights/play/${id}`;
  video.load();
  modal.classList.remove('hidden');
};
 
 window.triggerHighlight = async function() {
  if (!confirm('手动生成精华视频：将分析最近一天有录像的文件，可能需要几分钟，确定继续？')) return;
  try {
    const res = await fetch('/api/highlights/trigger', { method: 'POST' });
    const data = await res.json();
    if (data.status === 'ok') {
      toast(data.message || '已开始生成精华视频', 'success');
      openJobPanel('highlight');
    } else {
      toast(data.message || '触发失败', 'error');
    }
  } catch (e) {
    toast(`触发失败: ${e.message}`, 'error');
  }
};

// ══════════ 生成任务进度面板（多 tab：精华视频 / 日记，进度条 + 滚动日志）══════════
const JOB_TABS = { highlight: '精华视频', diary: '日记' };
let jobTimer = null;
let jobLogCounts = { highlight: 0, diary: 0 };
let jobActiveTab = null;

function openJobPanel(kind) {
  if (!JOB_TABS[kind]) return;
  let panel = document.getElementById('job-panel');
  if (!panel) {
    document.body.insertAdjacentHTML('beforeend', `
      <div id="job-panel" class="fixed bottom-4 right-4 z-40 w-[400px] max-w-[92vw] bg-timecut-900 border border-timecut-700 rounded-xl shadow-2xl overflow-hidden">
        <div class="flex items-center justify-between px-3 py-2 border-b border-timecut-700">
          <span class="text-xs font-medium text-timecut-200">生成任务</span>
          <button onclick="closeJobPanel()" class="text-timecut-500 hover:text-timecut-300 text-lg leading-none px-1">✕</button>
        </div>
        <div class="flex" id="job-tabs"></div>
        ${Object.keys(JOB_TABS).map(k => `
        <div class="p-3 hidden" id="job-tab-${k}">
          <div class="flex items-center justify-between mb-1.5">
            <span id="job-${k}-stage" class="text-xs text-timecut-300">准备中...</span>
            <span id="job-${k}-pct-text" class="text-xs text-timecut-500">0%</span>
          </div>
          <div class="w-full h-2 bg-timecut-700 rounded-full overflow-hidden">
            <div id="job-${k}-pct" class="h-full bg-accent-500 transition-all duration-500" style="width:0%"></div>
          </div>
          <div id="job-${k}-current" class="text-[11px] text-timecut-500 mt-1.5 truncate"></div>
          <div id="job-${k}-log" class="mt-2 h-44 overflow-y-auto bg-black/40 rounded-lg p-2 font-mono text-[11px] leading-relaxed text-timecut-400"></div>
        </div>`).join('')}
      </div>`);
  }
  jobLogCounts[kind] = 0;
  jobActiveTab = kind;
  renderJobTabs();
  switchJobTab(kind);
  pollJobs();
  if (jobTimer) clearInterval(jobTimer);
  jobTimer = setInterval(pollJobs, 1500);
}

function renderJobTabs() {
  const tabs = document.getElementById('job-tabs');
  if (!tabs) return;
  tabs.innerHTML = Object.entries(JOB_TABS).map(([k, label]) => `
    <button onclick="switchJobTab('${k}')" class="flex-1 px-3 py-2 text-xs transition-colors ${jobActiveTab === k ? 'text-accent-400 border-b-2 border-accent-500' : 'text-timecut-500 hover:text-timecut-300 border-b-2 border-transparent'}">${label}</button>`).join('');
}

window.switchJobTab = function(kind) {
  if (!JOB_TABS[kind]) return;
  jobActiveTab = kind;
  Object.keys(JOB_TABS).forEach(k => {
    const tab = document.getElementById('job-tab-' + k);
    if (tab) tab.classList.toggle('hidden', k !== kind);
  });
  renderJobTabs();
  pollJobOne(kind);
};

window.closeJobPanel = function() {
  if (jobTimer) { clearInterval(jobTimer); jobTimer = null; }
  const p = document.getElementById('job-panel');
  if (p) p.remove();
};

async function pollJobs() {
  const jobs = await Promise.all([
    API.get('/api/highlights/job').catch(() => null),
    API.get('/api/diary/job').catch(() => null),
  ]);
  if (jobs[0]) renderJobContent('highlight', jobs[0]);
  if (jobs[1]) renderJobContent('diary', jobs[1]);
  // 两个任务都结束（或都为空）后停止轮询
  if (jobs.every(j => !j || !j.running)) {
    if (jobTimer) { clearInterval(jobTimer); jobTimer = null; }
  }
}

async function pollJobOne(kind) {
  try {
    const url = kind === 'highlight' ? '/api/highlights/job' : '/api/diary/job';
    const j = await API.get(url);
    renderJobContent(kind, j);
  } catch (e) { /* 忽略 */ }
}

function renderJobContent(kind, j) {
  const pct = document.getElementById('job-' + kind + '-pct');
  const pctText = document.getElementById('job-' + kind + '-pct-text');
  const stageEl = document.getElementById('job-' + kind + '-stage');
  const curEl = document.getElementById('job-' + kind + '-current');
  if (pct) pct.style.width = (j.percent || 0) + '%';
  if (pctText) pctText.textContent = j.running ? (j.percent || 0) + '%' : (j.error ? '失败' : '完成');
  if (stageEl) stageEl.textContent = (j.stage || '') + (j.running && j.total ? ` ${j.done}/${j.total}` : '');
  if (curEl) curEl.textContent = j.current || '';
  const logBox = document.getElementById('job-' + kind + '-log');
  if (logBox && Array.isArray(j.log) && j.log.length > (jobLogCounts[kind] || 0)) {
    const frag = document.createDocumentFragment();
    for (let i = jobLogCounts[kind] || 0; i < j.log.length; i++) {
      const d = document.createElement('div');
      d.textContent = `${j.log[i].t}  ${j.log[i].text}`;
      frag.appendChild(d);
    }
    logBox.appendChild(frag);
    logBox.scrollTop = logBox.scrollHeight;
    jobLogCounts[kind] = j.log.length;
  }
  // 结束条件：任务停止且有终态信息
  const finished = !j.running && (j.message || j.error || j.percent === 100);
  if (finished && pct) {
    pct.className = 'h-full ' + (j.error ? 'bg-red-500' : 'bg-green-500');
    pct.style.width = '100%';
    const page = location.hash.slice(1) || 'dashboard';
    // 仅当停留在对应页面时刷新列表，避免覆盖其他页面内容
    if (kind === 'highlight' && page === 'highlights') renderHighlights(document.getElementById('page-content'));
    if (kind === 'diary' && page === 'diary') renderDiary(document.getElementById('page-content'));
  }
}

window.deleteHighlight = async function(id) {
   if (!confirm('确定删除这个精华视频？')) return;
   try {
     await API.del(`/api/highlights/${id}`);
     toast('已删除', 'success');
     renderHighlights(document.getElementById('page-content'));
   } catch (e) { toast(`删除失败: ${e.message}`, 'error'); }
 };
 
 // ══════════ 日记 ══════════
 async function renderDiary(el) {
   el.innerHTML = '<div class="text-timecut-400 text-center py-20"><div class="animate-spin w-8 h-8 border-2 border-accent-500 border-t-transparent rounded-full mx-auto mb-3"></div>加载中...</div>';
   try {
     const [data, status, settings] = await Promise.all([
       API.get('/api/diary'), API.get('/api/diary/status'), API.get('/api/settings'),
     ]);
     const items = data.items || [];
     el.innerHTML = `
       <div class="mb-4 flex items-center gap-3">
         <h3 class="text-sm font-semibold text-timecut-300">日记</h3>
         <span class="text-xs text-timecut-500">共 ${items.length} 篇</span>
         <button onclick="triggerDiary()" class="btn ml-auto text-xs bg-accent-600 hover:bg-accent-500 text-white px-4 py-2 rounded-lg">生成日记</button>
       </div>
       ${settings.diary_enabled ? '' : '<div class="mb-4 text-xs text-timecut-500 bg-timecut-800 border border-timecut-700 rounded-lg px-3 py-2">日记功能未开启，可在「系统设置」中开启。开启后每天自动生成前一天日记。</div>'}
       ${status.running ? '<div class="mb-4 flex items-center gap-2 text-xs text-accent-400"><div class="animate-spin w-4 h-4 border-2 border-accent-500 border-t-transparent rounded-full"></div>正在生成日记：' + (status.current || status.date || '') + '</div>' : ''}
       ${items.length ? `
       <div class="grid grid-cols-1 sm:grid-cols-2 lg:grid-cols-3 xl:grid-cols-4 gap-4">
         ${items.map(d => `
           <div class="bg-timecut-800 rounded-xl border border-timecut-700 p-4 cursor-pointer hover:border-accent-500/60 transition-colors" onclick="openDiary('${d.date}')">
             <div class="text-sm font-medium text-timecut-200 mb-1">${d.date}</div>
             <div class="text-xs text-timecut-500 leading-relaxed line-clamp-3" style="display:-webkit-box;-webkit-line-clamp:3;-webkit-box-orient:vertical;overflow:hidden">${d.preview || '（空）'}</div>
           </div>`).join('')}
       </div>` : '<div class="text-timecut-500 text-center py-16 bg-timecut-800 rounded-xl border border-timecut-700">暂无日记，点击右上角「生成日记」分析最近的录像</div>'}
     `;
     // 生成中时轮询状态，完成后刷新
     if (status.running) {
       clearTimeout(diaryPollTimer);
       diaryPollTimer = setTimeout(pollDiaryStatus, 1500);
     }
   } catch (e) { el.innerHTML = `<div class="text-red-400 text-center py-20">加载失败: ${e.message}</div>`; }
 }

 let diaryPollTimer = null;

 async function pollDiaryStatus() {
   try {
     const status = await API.get('/api/diary/status');
     if (!status.running) {
       toast(status.message || '日记生成完成', status.error ? 'error' : 'success');
       renderDiary(document.getElementById('page-content'));
       return;
     }
     renderDiary(document.getElementById('page-content'));
   } catch (e) { /* 忽略 */ }
 }

 window.triggerDiary = async function() {
   try {
     const res = await fetch('/api/diary/trigger', { method: 'POST' });
     const data = await res.json();
     if (data.status === 'ok') {
       toast(data.message || '已开始生成日记', 'success');
       openJobPanel('diary');
       renderDiary(document.getElementById('page-content'));
     } else {
       toast(data.message || '触发失败', 'error');
     }
   } catch (e) { toast(`触发失败: ${e.message}`, 'error'); }
 };

 window.openDiary = async function(date) {
   try {
     const d = await API.get(`/api/diary/${date}`);
     let modal = document.getElementById('diary-modal');
     if (!modal) {
       modal = document.createElement('div');
       modal.id = 'diary-modal';
       modal.className = 'fixed inset-0 z-50 hidden';
       modal.innerHTML = `
         <div class="absolute inset-0 bg-black/80" onclick="closeDiary()"></div>
         <div class="relative z-10 max-w-2xl mx-auto h-full flex items-center p-4">
           <div class="w-full bg-timecut-900 rounded-xl border border-timecut-700 overflow-hidden flex flex-col h-[85vh]">
             <div class="flex items-center justify-between px-4 py-3 border-b border-timecut-700">
               <span class="text-sm text-timecut-200">日记</span>
               <button onclick="closeDiary()" class="text-timecut-500 hover:text-timecut-300 text-lg leading-none px-1">✕</button>
             </div>
             <div class="flex-1 overflow-y-auto p-5" id="diary-body"></div>
           </div>
         </div>`;
       document.body.appendChild(modal);
     }
     document.getElementById('diary-body').innerHTML = `
       <div class="text-sm text-timecut-400 mb-4">${d.date}</div>
       <div class="text-timecut-200 text-[15px] leading-8 whitespace-pre-wrap">${escapeHtml(d.content || '（空）')}</div>`;
     modal.classList.remove('hidden');
   } catch (e) { toast(`加载日记失败: ${e.message}`, 'error'); }
 };

 window.closeDiary = function() {
   const modal = document.getElementById('diary-modal');
   if (modal) modal.classList.add('hidden');
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
           <div class="pt-4 border-t border-timecut-700">
             <div class="text-xs font-semibold text-timecut-300 mb-3">精华筛选方式</div>
             <div class="flex items-center gap-5 mb-3">
               <label class="flex items-center gap-2 text-xs text-timecut-300 cursor-pointer"><input type="radio" name="s-ai-mode" id="s-ai-off" class="accent-accent-500" ${!s.ai_enabled ? 'checked' : ''} onchange="toggleAiConfig()">系统自动（运动检测）</label>
               <label class="flex items-center gap-2 text-xs text-timecut-300 cursor-pointer"><input type="radio" name="s-ai-mode" id="s-ai-on" class="accent-accent-500" ${s.ai_enabled ? 'checked' : ''} onchange="toggleAiConfig()">大模型识别</label>
             </div>
             <div id="ai-config" class="space-y-3 ${s.ai_enabled ? '' : 'hidden'}">
               <div><label class="block text-xs text-timecut-500 mb-1.5">API 地址（OpenAI 兼容）</label><input id="s-ai-url" class="w-full bg-timecut-900 border border-timecut-700 rounded-lg px-3 py-2 text-sm text-timecut-200 focus:outline-none focus:border-accent-500" value="${s.ai_base_url || ''}" placeholder="https://dashscope.aliyuncs.com/compatible-mode/v1"></div>
               <div class="flex gap-3">
                 <div class="flex-1"><label class="block text-xs text-timecut-500 mb-1.5">模型 ID</label><input id="s-ai-model" class="w-full bg-timecut-900 border border-timecut-700 rounded-lg px-3 py-2 text-sm text-timecut-200 focus:outline-none focus:border-accent-500" value="${s.ai_model || ''}" placeholder="qwen-vl-plus"></div>
                 <div class="flex-1"><label class="block text-xs text-timecut-500 mb-1.5">最大分析片段数</label><input id="s-ai-max" type="number" min="1" max="50" class="w-full bg-timecut-900 border border-timecut-700 rounded-lg px-3 py-2 text-sm text-timecut-200 focus:outline-none focus:border-accent-500" value="${s.ai_max_segments ?? 20}"></div>
               </div>
               <div><label class="block text-xs text-timecut-500 mb-1.5">API Key</label><input id="s-ai-key" type="password" class="w-full bg-timecut-900 border border-timecut-700 rounded-lg px-3 py-2 text-sm text-timecut-200 focus:outline-none focus:border-accent-500" value="${s.ai_api_key || ''}" placeholder="sk-..."></div>
               <div class="flex items-center gap-3">
                 <button onclick="testAiConnection()" class="btn bg-timecut-700 hover:bg-timecut-600 text-timecut-200 px-4 py-2 rounded-lg text-xs">测试连接</button>
                 <span id="ai-test-result" class="text-xs text-timecut-500"></span>
               </div>
               <div class="text-[11px] text-timecut-500 leading-relaxed">大模型模式：对运动片段抽帧，调用多模态模型判断画面价值（人/车/包裹等），只分析分数最高的片段以控制成本。支持 OpenAI 兼容接口，如通义千问 qwen-vl、豆包等具有视觉理解能力的多模态模型。</div>
             </div>
           </div>
           <div class="pt-4 border-t border-timecut-700">
             <div class="text-xs font-semibold text-timecut-300 mb-3">日记（大模型总结当天事件）</div>
             <div class="flex items-center gap-3"><label class="text-xs text-timecut-500">自动生成日记</label><button id="s-diary-toggle" onclick="toggleDiary()" class="btn relative w-12 h-6 rounded-full transition-colors ${s.diary_enabled ? 'bg-accent-600' : 'bg-timecut-600'}"><span class="absolute left-0 top-0.5 w-5 h-5 bg-white rounded-full transition-transform ${s.diary_enabled ? 'translate-x-[26px]' : 'translate-x-0.5'}"></span></button></div>
             <div class="text-[11px] text-timecut-500 leading-relaxed mt-2">开启后每天与精华检测同时分析前一天录像：对每个运动片段抽帧，用大模型描述画面中发生的事，再汇总成一篇日记。复用上方大模型的 API 地址 / 模型 / Key，每日最多分析的片段数与精华识别一致。</div>
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

window.toggleDiary = function() {
  const btn = document.getElementById('s-diary-toggle');
  const enabled = !btn.classList.contains('bg-accent-600');
  btn.className = `btn relative w-12 h-6 rounded-full transition-colors ${enabled ? 'bg-accent-600' : 'bg-timecut-600'}`;
  btn.querySelector('span').className = `absolute left-0 top-0.5 w-5 h-5 bg-white rounded-full transition-transform ${enabled ? 'translate-x-[26px]' : 'translate-x-0.5'}`;
};

window.toggleAiConfig = function() {
  const cfg = document.getElementById('ai-config');
  if (cfg) cfg.classList.toggle('hidden', !document.getElementById('s-ai-on').checked);
};

window.testAiConnection = async function() {
  const result = document.getElementById('ai-test-result');
  const url = document.getElementById('s-ai-url')?.value;
  const key = document.getElementById('s-ai-key')?.value;
  if (!url) { result.textContent = '✗ 请先填写 API 地址'; result.className = 'text-xs text-red-400'; return; }
  if (!key) { result.textContent = '✗ 请先填写 API Key'; result.className = 'text-xs text-red-400'; return; }
  result.textContent = '测试中...';
  result.className = 'text-xs text-timecut-500';
  try {
    const res = await fetch('/api/settings/ai/test', {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({
        ai_base_url: url,
        ai_model: document.getElementById('s-ai-model')?.value,
        ai_api_key: key,
      }),
    });
    const data = await res.json();
    if (data.status === 'ok') {
      result.textContent = '✓ ' + data.message;
      result.className = 'text-xs text-green-400';
    } else {
      result.textContent = '✗ ' + (data.message || '测试失败');
      result.className = 'text-xs text-red-400';
    }
  } catch (e) {
    result.textContent = '✗ 测试失败: ' + e.message;
    result.className = 'text-xs text-red-400';
  }
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
        <div class="w-full bg-timecut-900 rounded-xl border border-timecut-700 overflow-hidden flex flex-col h-[92vh] max-h-[92vh]">
          <div class="flex items-center justify-between px-4 py-3 border-b border-timecut-700">
            <span class="text-sm text-timecut-200">添加摄像头</span>
            <button onclick="closeGo2RtcAdd()" class="text-timecut-500 hover:text-timecut-300 text-lg leading-none">✕</button>
          </div>
          <iframe id="go2rtc-add-frame" class="flex-1 w-full border-0 min-h-0" src="/add-camera.html"></iframe>
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
     ai_enabled: document.getElementById('s-ai-on')?.checked,
     ai_base_url: document.getElementById('s-ai-url')?.value,
     ai_model: document.getElementById('s-ai-model')?.value,
     ai_api_key: document.getElementById('s-ai-key')?.value,
     ai_max_segments: parseInt(document.getElementById('s-ai-max')?.value) || 20,
    diary_enabled: document.getElementById('s-diary-toggle')?.classList.contains('bg-accent-600') || false,
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
