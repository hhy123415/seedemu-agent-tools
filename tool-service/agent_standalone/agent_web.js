const $ = id => document.getElementById(id);
const storageKey = 'seedemu.agent.standalone.v1';
let busy = false, started = false, revision = 0;
let browserState = {connected:false}, browserControlPending = false;
let saved = {config: {}};
// 聊天只在当前页面内存中保留，不写入本地存储。
let session = {entries: []};
let hasBrowserConfig = false;
function state(text) { $('status').textContent = text; }
try {
  const data = JSON.parse(localStorage.getItem(storageKey));
  if (data && data.config) {
    // 迁移时只读取模型配置；旧聊天记录会在 persist 时从存储中移除。
    saved = {config: data.config, profiles: data.profiles,
      activeProfile: data.activeProfile, profilesInitialized: data.profilesInitialized}; hasBrowserConfig = Boolean(data.config.api_url);
  }
} catch { state('本地记录读取失败，将使用新对话'); }
saved.profiles = Array.isArray(saved.profiles) ? saved.profiles : [];
// Migrate the previous single-provider browser configuration without saving chat history.
if (!saved.profiles.length && saved.config.api_url && !saved.profilesInitialized) {
  const profile = {id: crypto.randomUUID(), name: '原有配置', ...saved.config};
  delete profile.source;
  saved.profiles.push(profile); saved.activeProfile = profile.id;
}
saved.profilesInitialized = true;
function config() {
  return {api_url: $('apiUrl').value.trim(), api_key: $('apiKey').value,
    max_context_chars: Number($('contextLimit').value || 40960),
    model: $('model').value.trim(), source: $('source').value.trim() || null};
}
// 仅保存模型配置，聊天内容不进入持久化数据。
function persist() {
  saved.config = config();
  try { localStorage.setItem(storageKey, JSON.stringify(saved)); }
  catch { state('本地保存失败（存储空间不足或浏览器禁止存储），请勿关闭页面'); }
}
function profileList() {
  const draft = document.createElement('option'); draft.value = ''; draft.textContent = '未保存的新配置';
  $('profiles').replaceChildren(draft, ...saved.profiles.map(profile => {
    const option = document.createElement('option'); option.value = profile.id;
    option.textContent = profile.name; return option;
  }));
  $('profiles').value = saved.activeProfile || '';
}
function fillProfile(profile) {
  revision++;
  saved.activeProfile = profile?.id || null;
  $('profileName').value = profile?.name || '';
  $('apiUrl').value = profile?.api_url || '';
  $('apiKey').value = profile?.api_key || '';
  $('model').value = profile?.model || '';
  $('contextLimit').value = profile?.max_context_chars || 40960;
  profileList(); persist();
}
function saveProfile() {
  if (busy) return;
  const cfg = config(), name = $('profileName').value.trim();
  if (!name || !/^https?:\/\//i.test(cfg.api_url)) { state('请填写配置名称和 HTTP(S) API URL'); return; }
  if (!validContext()) return;
  const profile = {id: saved.activeProfile || crypto.randomUUID(), name,
    api_url: cfg.api_url, api_key: cfg.api_key, model: cfg.model,
    max_context_chars: cfg.max_context_chars};
  const index = saved.profiles.findIndex(p => p.id === profile.id);
  if (index < 0) saved.profiles.push(profile); else saved.profiles[index] = profile;
  saved.activeProfile = profile.id; profileList(); persist(); state(`已保存浏览器配置：${name}`); syncProfiles();
}
let profileWrites = Promise.resolve();
let profileEdit = 0;
function validContext() {
  const value = config().max_context_chars;
  if (Number.isInteger(value) && value >= 8192 && value <= 2000000) return true;
  state('上下文预算请输入 8192 至 2000000 之间的整数（字符数）'); return false;
}
// 同步模型配置到本机后端文件；聊天内容不写入文件。
function syncProfiles() {
  profileEdit++;
  const snapshot = JSON.stringify({profiles: saved.profiles, activeProfile: saved.activeProfile || null});
  $('configStatus').textContent = '正在保存到本机…';
  profileWrites = profileWrites.catch(() => {}).then(async () => {
    try {
      const response = await fetch('/api/profiles', {method:'PUT',
        headers:{'Content-Type':'application/json','X-Agent-Local':'1'}, body:snapshot});
      if (!response.ok) throw Error();
      $('configStatus').textContent = '已保存到本机 agent_standalone/model_profiles.json';
    } catch { $('configStatus').textContent = '本机保存失败；浏览器副本仍保留，请重试“保存配置”'; }
  });
  return profileWrites;
}
function current() { return session; }
function create() { session = {entries: []}; }
function previewHTML(html) {
  const doc = new DOMParser().parseFromString(html, 'text/html');
  doc.querySelectorAll('script,iframe,frame,frameset,object,embed,link,meta,base,svg,math,template').forEach(el => el.remove());
  doc.querySelectorAll('*').forEach(el => {
    for (const attr of [...el.attributes]) {
      if (!['style','class','id','colspan','rowspan','type','placeholder'].includes(attr.name)) el.removeAttribute(attr.name);
    }
    if (el.matches('input,button,select,textarea')) el.disabled = true;
    if (el.matches('input[type="hidden"],input[type="password"]')) el.remove();
  });
  return '<!doctype html><meta http-equiv="Content-Security-Policy" content="default-src \'none\'; style-src \'unsafe-inline\'; form-action \'none\'; base-uri \'none\'"><style>body{font:14px system-ui;padding:12px;overflow-wrap:anywhere}a{pointer-events:none}</style>' + doc.body.innerHTML;
}
// 将工具开始和返回事件合并展示，方便查看参数与执行结果。
function toolCard(event) {
  const card = document.createElement('article'); card.className = 'tool-card';
  const result = event.result || {}, args = event.arguments || {};
  const failed = event.phase === 'result' && (result.error || result.successful === false || result.transport_successful === false);
  const title = document.createElement('strong');
  const status = event.phase === 'start' ? '执行中' : failed ? '工具返回失败' : '已返回结果';
  title.textContent = `${event.name} · ${status}`; card.append(title);
  const meta = document.createElement('p'); meta.className = 'tool-meta';
  meta.textContent = [args.method || result.method, args.origin || result.origin,
    args.path || result.requested_path, args.source ? `source: ${args.source}` : '',
    result.http_status ? `HTTP ${result.http_status}` : '',
    event.duration_ms != null ? `${event.duration_ms} ms` : ''].filter(Boolean).join(' · ');
  card.append(meta);
  const detail = (label, value) => {
    const el = document.createElement('details'), summary = document.createElement('summary'), pre = document.createElement('pre');
    summary.textContent = label; pre.textContent = typeof value === 'string' ? value : JSON.stringify(value, null, 2);
    el.append(summary, pre); card.append(el);
  };
  detail('请求参数', args);
  if (event.phase === 'result') {
    if (result.http_status) {
      const note = document.createElement('small'); note.textContent = 'HTTP 状态只表示请求结果，不代表登录、付款或域名购买已完成。'; card.append(note);
    }
    if (result.truncated) { const note = document.createElement('p'); note.textContent = '返回正文已截断，预览可能不完整。'; card.append(note); }
    if (typeof result.body === 'string' && (/html/i.test(result.content_type || '') || /^\s*(<!doctype html|<html)/i.test(result.body))) {
      const el = document.createElement('details'), summary = document.createElement('summary');
      summary.textContent = '返回页面预览（静态快照，不可操作）'; el.append(summary);
      // Create the isolated frame only on demand, only when expanded.
      el.addEventListener('toggle', () => {
        if (el.open && !el.querySelector('iframe')) {
          const frame = document.createElement('iframe'); frame.title = '工具返回页面';
          frame.setAttribute('sandbox', ''); frame.referrerPolicy = 'no-referrer';
          frame.srcdoc = previewHTML(result.body); el.append(frame);
        }
      });
      card.append(el);
    }
    detail('工具返回数据', result);
  }
  return card;
}
function recordTool(event) {
  const entries = current().entries;
  const existing = entries.find(e => e.role === 'tool' && e.event.id === event.id);
  if (existing) existing.event = event;
  else entries.push({role: 'tool', event});
  render();
}
function renderEntry(entry) {
  if (entry.role === 'tool') { $('chat').append(toolCard(entry.event)); return; }
  const el = document.createElement(entry.role === 'progress' ? 'details' : 'div');
  if (entry.role === 'progress') {
    const summary = document.createElement('summary'); summary.textContent = entry.text.split('\n')[0];
    const pre = document.createElement('pre'); pre.textContent = entry.text; el.append(summary, pre);
  } else {
    el.className = 'bubble ' + entry.role;
    const label = document.createElement('div'); label.className = 'role';
    label.textContent = entry.role === 'user' ? '你' : entry.role === 'error' ? '执行提示' : 'Agent';
    el.append(label, document.createTextNode(entry.text));
  }
  $('chat').append(el); $('chat').scrollTop = $('chat').scrollHeight;
}
function render() { $('chat').replaceChildren(); current().entries.forEach(renderEntry); }
function append(role, text) {
  const session = current(); session.entries.push({role, text});
  renderEntry({role, text});
}
for (const [id, key] of [['apiUrl','api_url'], ['apiKey','api_key'], ['model','model'], ['source','source']]) {
  $(id).value = saved.config[key] || '';
}
$('contextLimit').value = saved.config.max_context_chars || 40960;
create();
$('source').value = 'as154h-Browser-10.154.0.71';
render(); profileList(); persist();
$('profileName').value = saved.profiles.find(p => p.id === saved.activeProfile)?.name || '';
const socket = new WebSocket(`${location.protocol === 'https:' ? 'wss' : 'ws'}://${location.host}/ws`);
function controls() {
  for (const id of ['send','reset']) $(id).disabled = busy || socket.readyState !== 1;
  for (const id of ['apiUrl','apiKey','model','clearKey','profiles','profileName','profileNew','profileSave','profileDelete','contextLimit']) $(id).disabled = busy;
  $('source').disabled = busy || started || browserState.connected;
  browserControls();
}
socket.onopen = () => { state('已连接，开始新对话'); controls(); };
socket.onclose = () => { busy = false; browserState.connected = false; $('browserFrame').hidden = true; $('browserFrame').removeAttribute?.('src'); controls(); state('连接已断开；刷新将清空当前对话，已执行操作不会撤销。'); };
socket.onerror = () => state('连接失败，请检查后端服务');
socket.onmessage = event => {
  const data = JSON.parse(event.data);
  if (data.type === 'browser') { updateBrowser(data); return; }
  if (data.type === 'browser_error') {
    browserControlPending = false; $('browserInfo').textContent = data.text; browserControls(); return;
  }
  if (data.type === 'notice') { state(data.text); return; }
  if (data.type === 'tool') { recordTool(data); state(data.phase === 'start' ? '工具正在执行…' : '工具已返回，模型继续处理…'); return; }
  if (data.type === 'progress') { append('progress', data.text); state('Agent 正在执行…'); return; }
  if (data.type === 'reset') {
    create();
    started = false; $('source').value = 'as154h-Browser-10.154.0.71'; render();
    state('已清空当前对话并重置浏览器会话；已执行的业务操作不会撤销');
  } else {
    append(data.type === 'error' ? 'error' : 'assistant', data.text);
    state(data.type === 'error' ? '本轮失败，可补充指令核查状态' : '等待下一条指令');
  }
  busy = false; controls(); $('message').focus();
};
$('form').onsubmit = event => {
  event.preventDefault(); const message = $('message').value.trim(), cfg = config();
  if (busy || socket.readyState !== 1 || !message) return;
  if (!cfg.api_url || !cfg.model) { state('请填写 API URL 和模型名称'); return; }
  if (!validContext()) return;
  socket.send(JSON.stringify({...cfg, message}));
  current().source = cfg.source; append('user', message); $('message').value = '';
  busy = true; started = true; controls(); state('模型正在处理…');
};
$('message').onkeydown = event => {
  if (event.key === 'Enter' && !event.shiftKey && !event.isComposing) {
    event.preventDefault(); $('form').requestSubmit();
  }
};
function reset() { busy = true; controls(); socket.send(JSON.stringify({type:'reset'})); }
$('reset').onclick = () => reset();
$('clearKey').onclick = () => {
  revision++; $('apiKey').value = '';
  const profile = saved.profiles.find(p => p.id === saved.activeProfile);
  if (profile) profile.api_key = '';
  persist(); syncProfiles(); state('已清除当前配置保存的 API Key');
};
$('profileNew').onclick = () => {
  if (busy) return;
  fillProfile(null); state('填写新的 URL、Key 和名称后点击保存配置');
};
$('profileSave').onclick = saveProfile;
$('profiles').onchange = () => {
  if (busy) { profileList(); return; }
  const profile = saved.profiles.find(p => p.id === $('profiles').value);
  fillProfile(profile); syncProfiles(); state('已切换配置，当前对话保留');

};
$('profileDelete').onclick = () => {
  if (busy || !saved.activeProfile) return;
  saved.profiles = saved.profiles.filter(p => p.id !== saved.activeProfile);
  fillProfile(saved.profiles[0]); syncProfiles(); state('配置已删除');

};
for (const id of ['apiUrl','apiKey']) {
  $(id).oninput = () => { revision++; persist(); };
}
for (const id of ['model','source','contextLimit']) $(id).onchange = persist;
async function initializeConfig() {
  const initialRevision = revision, initialEdit = profileEdit;
  try {
    const response = await fetch('/api/profiles', {method:'POST', headers:{'X-Agent-Local':'1'}});
    if (!response.ok) throw Error();
    const disk = await response.json();
    if (initialEdit !== profileEdit || initialRevision !== revision) return;
    if (!Array.isArray(disk.profiles)) throw Error();
    // Merge old browser-only profiles, preserving the browser copy on ID conflicts.
    const merged = new Map(disk.profiles.map(p => [p.id, p]));
    saved.profiles.forEach(p => merged.set(p.id, p));
    saved.profiles = [...merged.values()];
    if (!hasBrowserConfig && saved.profiles.length) {
      fillProfile(saved.profiles.find(p => p.id === disk.activeProfile) || saved.profiles[0]);
    } else { profileList(); persist(); }
    if (disk.missing && !saved.profiles.length && !hasBrowserConfig) {
      const fallback = await fetch('/api/local-config', {method:'POST',headers:{'X-Agent-Local':'1'}});
      if (!fallback.ok) throw Error();
      const data = await fallback.json();
      if (initialEdit !== profileEdit || revision !== initialRevision) return;
      if (data.api_url) {
        const profile = {id:crypto.randomUUID(),name:'本机默认配置',...data,model:'',max_context_chars:40960};
        saved.profiles.push(profile); fillProfile(profile);
      }
    }
    await syncProfiles();
  } catch { $('configStatus').textContent = '本机配置读取失败；可继续使用浏览器配置，保存时请重试'; }

}
controls(); initializeConfig();

function setChatFocus(focused) {
  $('sidebar').hidden = focused;
  $('focusChat').textContent = focused ? '显示设置' : '专注聊天';
  $('focusChat').ariaExpanded = String(!focused);
}
$('focusChat').onclick = () => setChatFocus(!$('sidebar').hidden);
if (typeof matchMedia === 'function' && matchMedia('(max-width: 760px)').matches) setChatFocus(true);

function browserControls() {
  const disconnected = socket.readyState !== 1;
  $('browserConnect').disabled = disconnected || browserControlPending || browserState.connected;
  $('browserReconnect').disabled = disconnected || !browserState.connected;
  $('browserClose').disabled = disconnected || browserControlPending || !browserState.connected || busy;
}
// 向同源内嵌画面发送连接信息，不把临时会话令牌持久化。
function notifyViewer() {
  $('browserFrame').contentWindow?.postMessage({type:'browser_view',token:browserState.token}, location.origin);
}
function updateBrowser(data) {
  const changed = browserState.connected !== data.connected || browserState.token !== data.token;
  browserState = data; browserControlPending = false;
  $('browserEmpty').hidden = data.connected;
  $('browserFrame').hidden = !data.connected;
  $('browserInfo').textContent = data.connected
    ? `${data.source} · 只读观看，Agent 自动操作`
    : '浏览器会话已关闭，点击启动可打开新会话';
  if (data.connected) {
    $('source').value = data.source; current().source = data.source; persist();
    if (!$('browserFrame').getAttribute?.('src')) $('browserFrame').src = '/browser/viewer';
    else if (changed) notifyViewer();
  } else { $('browserFrame').removeAttribute?.('src'); }
  controls();
}
function browserCommand(type) {
  if (socket.readyState !== 1 || browserControlPending) return;
  browserControlPending = true; browserControls();
  $('browserInfo').textContent = '正在连接或关闭浏览器会话…';
  socket.send(JSON.stringify({type,source:$('source').value.trim() || null}));
}
$('browserConnect').onclick = () => browserCommand('browser_connect');
$('browserClose').onclick = () => browserCommand('browser_close');
$('browserReconnect').onclick = () => { $('browserFrame').src = '/browser/viewer'; };
if (typeof window !== 'undefined') window.addEventListener('message', event => {
  if (event.origin === location.origin && event.source === $('browserFrame').contentWindow
      && event.data.type === 'browser_viewer_ready' && browserState.connected) notifyViewer();
});

// 独立测试当前模型配置，不改变当前聊天或运行中的 Agent。
$('testModel').onclick = async () => {
  const cfg = config(), button = $('testModel'), output = $('testModelStatus');
  if (!cfg.api_url || !cfg.model) { output.textContent = '请先填写 API URL 和模型名称'; return; }
  button.disabled = true; output.textContent = `正在测试 ${cfg.model}…`;
  const controller = new AbortController();
  const timer = setTimeout(() => controller.abort(), 40000);
  try {
    const response = await fetch('/api/test-model', {
      method: 'POST', headers: {'Content-Type': 'application/json', 'X-Agent-Local': '1'},
      body: JSON.stringify({api_url: cfg.api_url, api_key: cfg.api_key, model: cfg.model}),
      signal: controller.signal,
    });
    if (!response.ok) { output.textContent = `测试请求失败（HTTP ${response.status}），请检查配置格式`; return; }
    const result = await response.json();
    output.textContent = `${cfg.model}：${result.message}` +
      (result.status ? ` · HTTP ${result.status}` : '') +
      (result.elapsed_ms != null ? ` · ${result.elapsed_ms} ms` : '');
  } catch { output.textContent = '测试超时或无法连接本机后端'; }
  finally { clearTimeout(timer); button.disabled = false; }
};
