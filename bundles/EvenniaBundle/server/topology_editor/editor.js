'use strict';
const $ = id => document.getElementById(id);
const NS = 'http://www.w3.org/2000/svg';
let world = {nodes: [], edges: [], revision: ''};
let level = null, selected = null, editingExit = null;
let positions = new Map(), pan = {x: 0, y: 0}, zoom = 1, drag = null;
let busy = false, formDirty = false, layoutDirty = false;
const byId = id => world.nodes.find(n => n.id === id);
const visible = () => world.nodes.filter(n => n.parent === level);
const children = id => world.nodes.filter(n => n.parent === id);
const num = value => value === '' ? null : Number(value);
const short = (value, max = 13) => [...value].length > max ? [...value].slice(0, max).join('') + '…' : value;
function message(text, error = false) { $('message').textContent = text; $('message').classList.toggle('error', error); }
function pathTo(id) {
  const result = [], seen = new Set();
  while (id !== null && byId(id) && !seen.has(id)) {
    seen.add(id); const node = byId(id); result.unshift(node); id = node.parent;
  }
  return result;
}
const fullName = id => pathTo(id).map(n => n.label).join(' / ') + ` #${id}`;
function inside(id, ancestor) { return pathTo(id).some(n => n.id === ancestor); }
function discardForm() { return !formDirty || window.confirm('表单有未保存的修改，放弃这些修改吗？'); }
function setBusy(value) {
  busy = value;
  document.querySelectorAll('button').forEach(button => {
    if (value) { button.dataset.wasDisabled = button.disabled ? '1' : '0'; button.disabled = true; }
    else { button.disabled = button.dataset.wasDisabled === '1'; delete button.dataset.wasDisabled; }
  });
  if (!value) {
    $('up').disabled = level === null;
    $('delete-room').disabled = !!byId(selected)?.protected;
    if ($('import-dialog').open) updateImportButton();
  }
}
async function jsonResponse(response) {
  if (!response.headers.get('content-type')?.includes('application/json')) throw Error('登录已过期，请重新登录管理员账号后刷新。');
  const payload = await response.json();
  if (!response.ok) throw Error(payload.error || `请求失败 (${response.status})`);
  return payload;
}
function accept(payload, resetPositions = false) {
  world = {...payload, nodes: [...payload.nodes, ...(payload.items || [])]};
  if (level !== null && !byId(level)) level = null;
  if (selected !== null && !byId(selected)) selected = null;
  if (resetPositions) positions.clear();
  for (const node of world.nodes) {
    if (Array.isArray(node.position) && node.position.length === 2 && node.position.every(Number.isFinite)
        && (!positions.has(node.id) || !layoutDirty)) {
      positions.set(node.id, {x: node.position[0], y: node.position[1]});
    }
  }
}
async function load() {
  if (busy || !discardForm() || (layoutDirty && !window.confirm('布局尚未保存，放弃布局修改并刷新吗？'))) return;
  setBusy(true);
  try {
    const payload = await jsonResponse(await fetch('data/', {cache: 'no-store'}));
    layoutDirty = false; accept(payload, true); formDirty = false;
    render(); fillRoom(selected); fit(); message('地图已读取。修改地点、物品和出口后点击保存；拖动布局需要单独保存。');
  } catch (error) { message(error.message, true); }
  finally { setBusy(false); }
}
async function write(body, success) {
  if (busy) return false;
  setBusy(true);
  try {
    const payload = await jsonResponse(await fetch('edit/', {
      method: 'POST', headers: {'Content-Type': 'application/json', 'X-CSRFToken': document.querySelector('meta[name="csrf-token"]').content},
      body: JSON.stringify({...body, revision: world.revision})
    }));
    accept(payload); formDirty = false;
    success?.(payload); render(); message('已保存到世界。'); return true;
  } catch (error) { message(error.message, true); return false; }
  finally { setBusy(false); }
}
function option(select, value, label, disabled = false) {
  const o = document.createElement('option'); o.value = value ?? ''; o.textContent = label; o.disabled = disabled; select.appendChild(o);
}
function showActions(isItem, actions = {}) {
  $('item-interactions').hidden = !isItem;
  const container = $('action-fields');
  container.replaceChildren();
  if (!isItem) return;
  for (const [key, spec] of Object.entries(world.action_types)) {
    const group = document.createElement('div');
    group.dataset.action = key;
    const label = document.createElement('label');
    label.className = 'check';
    const enable = document.createElement('input');
    enable.type = 'checkbox';
    enable.checked = Object.hasOwn(actions, key);
    label.append(enable, spec.label);
    const fields = document.createElement('div');
    for (const [field, title] of Object.entries(spec.fields)) {
      const caption = document.createElement('label');
      const input = document.createElement('textarea');
      input.dataset.field = field;
      input.rows = 2;
      input.maxLength = 2000;
      input.required = true;
      input.value = actions[key]?.[field] ?? '';
      caption.append(title, input);
      fields.appendChild(caption);
    }
    const update = () => {
      fields.hidden = !enable.checked;
      fields.querySelectorAll('textarea').forEach(input => { input.disabled = !enable.checked; });
    };
    enable.onchange = update;
    update();
    group.append(label, fields);
    container.appendChild(group);
  }
}
function collectActions() {
  const actions = {};
  for (const group of $('action-fields').children) {
    if (!group.querySelector('input').checked) continue;
    actions[group.dataset.action] = Object.fromEntries(
      Array.from(group.querySelectorAll('textarea'), input => [input.dataset.field, input.value]));
  }
  return actions;
}
function fillRoom(id, newKind = null) {
  selected = id; const room = byId(id);
  const kind = room?.kind || newKind || 'area';
  const item = kind === 'item';
  $('selection-title').textContent = room ? `${room.label} #${room.id}` : item ? '新建物品' : '新建地点';
  $('selection-hint').textContent = room?.kind === 'area'
    ? '这是区域容器。玩家进入时会到达你指定的入口。'
    : item ? '物品实际放置在所属地点中。游戏内使用 look 查看，get 拾取，drop 放下；固定物品不能被普通角色拿走。' : '地点归属用于分层展示；通行出口决定角色如何移动。';
  $('room-name').value = room?.name || '';
  $('room-description').value = room?.description || '';
  $('room-kind').value = kind; $('room-kind').disabled = !!room;
  $('room-parent').replaceChildren(); if (!item) option($('room-parent'), null, '世界（顶层）');
  for (const node of world.nodes) {
    if (node.kind !== 'item' && (!item || node.kind === 'room') && node.id !== id && (id === null || !inside(node.id, id))) option($('room-parent'), node.id, fullName(node.id));
  }
  const parent = room ? room.parent : level;
  if (!item || byId(parent)?.kind === 'room') $('room-parent').value = parent ?? '';
  showActions(item, room?.actions);
  $('portable-label').hidden = !item; $('item-portable').checked = room?.portable ?? true;
  $('room-entry').replaceChildren(); option($('room-entry'), null, '暂不设置入口');
  if (room) for (const node of world.nodes) {
    if (node.kind === 'room' && node.id !== id && inside(node.id, id)) option($('room-entry'), node.id, fullName(node.id));
  }
  $('room-entry').value = room?.entry ?? '';
  $('entry-label').hidden = $('room-kind').value !== 'area';
  $('enter').hidden = !room || item; $('delete-room').hidden = !room;
  $('delete-room').disabled = !!room?.protected;
  $('save-room').textContent = room ? '保存修改' : item ? '创建物品' : '创建地点';
  $('delete-room').textContent = item ? '删除物品' : '删除地点';
  $('exit-form').hidden = true; editingExit = null; formDirty = false;
  renderExits(); draw();
}
function select(id) {
  if (busy || !discardForm()) return;
  fillRoom(id);
}
function navigate(id) {
  if (busy || !discardForm()) return;
  if (byId(id)?.kind === 'item') { select(id); return; }
  level = id; selected = null; pan = {x: 0, y: 0}; zoom = 1;
  render(); fillRoom(null); fit();
}
function render() {
  $('breadcrumbs').replaceChildren();
  for (const node of [{id: null, label: '世界'}, ...pathTo(level)]) {
    if ($('breadcrumbs').childElementCount) { const separator = document.createElement('span'); separator.textContent = '/'; $('breadcrumbs').appendChild(separator); }
    const b = document.createElement('button'); b.textContent = node.label; b.onclick = () => navigate(node.id); $('breadcrumbs').appendChild(b);
  }
  $('up').disabled = level === null;
  $('level-title').textContent = byId(level)?.label || '世界';
  const nodes = visible();
  $('counts').textContent = `${nodes.filter(n => n.kind !== 'item').length} 个内部地点 · ${nodes.filter(n => n.kind === 'item').length} 个物品`;
  $('empty').hidden = nodes.length > 0;
  $('room-list').replaceChildren();
  nodes.forEach((node, i) => {
    if (!positions.has(node.id)) positions.set(node.id, {x: 160 + (i % 3) * 230, y: 130 + Math.floor(i / 3) * 155});
    const b = document.createElement('button'); b.textContent = `${node.label} #${node.id}`; b.onclick = () => select(node.id); $('room-list').appendChild(b);
  });
  draw(); renderExits();
}
function svg(tag, attrs, parent, text) {
  const e = document.createElementNS(NS, tag);
  for (const [key, value] of Object.entries(attrs)) e.setAttribute(key, value);
  if (text !== undefined) e.textContent = text;
  parent.appendChild(e); return e;
}
function transform() { $('viewport').setAttribute('transform', `translate(${pan.x},${pan.y}) scale(${zoom})`); }
function representative(id) {
  const seen = new Set();
  while (byId(id) && !seen.has(id)) {
    seen.add(id); const node = byId(id);
    if (node.parent === level) return id;
    id = node.parent;
  }
  return null;
}
function draw() {
  $('nodes').replaceChildren(); $('edges').replaceChildren();
  const edges = world.edges.map(e => ({...e, a: representative(e.source), b: representative(e.target)}))
    .filter(e => e.a !== null && e.b !== null && (e.a !== e.b || e.source === e.target));
  edges.forEach(edge => {
    const a = positions.get(edge.a), b = positions.get(edge.b); if (!a || !b) return;
    const siblings = edges.filter(e => e.a === edge.a && e.b === edge.b), i = siblings.indexOf(edge);
    let d, x, y;
    if (edge.a === edge.b) {
      const rise = 115 + i * 35;
      d = `M ${a.x-60} ${a.y-28} C ${a.x-rise} ${a.y-rise},${a.x+rise} ${a.y-rise},${a.x+60} ${a.y-28}`;
      x = a.x; y = a.y - rise * .72;
    } else {
      const dx = b.x-a.x, dy = b.y-a.y, distance = Math.hypot(dx,dy) || 1;
      const offset = 30 + i*30, nx = -dy/distance, ny = dx/distance;
      const boundary = Math.min(90/Math.max(Math.abs(dx)/distance,.001),44/Math.max(Math.abs(dy)/distance,.001));
      const sx = a.x+dx/distance*boundary, sy = a.y+dy/distance*boundary;
      const tx = b.x-dx/distance*(boundary+8), ty = b.y-dy/distance*(boundary+8);
      const cx = (a.x+b.x)/2+nx*offset, cy = (a.y+b.y)/2+ny*offset;
      d = `M ${sx} ${sy} Q ${cx} ${cy} ${tx} ${ty}`; x=(sx+2*cx+tx)/4; y=(sy+2*cy+ty)/4-6;
    }
    const p = svg('path', {d, class: 'edge', 'marker-end': 'url(#arrow)'}, $('edges'));
    svg('title', {}, p, `${fullName(edge.source)} → ${fullName(edge.target)}`);
    svg('text', {x,y,'text-anchor':'middle',class:'edge-label'}, $('edges'), short(edge.label,16));
  });
  for (const node of visible()) {
    const p = positions.get(node.id); if (!p) continue;
    const g = svg('g', {transform:`translate(${p.x},${p.y})`, class:`node ${node.kind}${selected===node.id?' selected':''}`, tabindex:0,role:'button','aria-label':`${node.label}，${node.kind==='area'?'区域':node.kind==='item'?'物品':'地点'}，按 Enter 查看，按右方向键进入内部`}, $('nodes'));
    svg('rect',{x:-90,y:-42,width:180,height:84,rx:12},g);
    svg('title',{},g,node.label);
    svg('text',{x:-75,y:-18,class:'meta'},g,`${node.kind==='area'?'区域':node.kind==='item'?'物品':'地点'} · #${node.id}`);
    svg('text',{x:-75,y:6},g,short(node.label,11));
    svg('text',{x:-75,y:29,class:'meta'},g,node.kind==='item' ? (node.portable?'可查看 · 可拾取':'可查看 · 固定物品') : `${children(node.id).filter(n=>n.kind!=='item').length} 个地点 · ${children(node.id).filter(n=>n.kind==='item').length} 个物品`);
    if (node.kind !== 'item') {
    const enter = svg('text',{x:65,y:29,class:'meta',role:'button','aria-label':'进入内部',style:'pointer-events:auto;cursor:pointer'},g,'↳');
    enter.addEventListener('pointerdown',event=>{event.stopPropagation();navigate(node.id);});
    }
    g.addEventListener('pointerdown', event => {
      if (busy) return;
      event.stopPropagation();
      drag = {id: node.id, x:event.clientX, y:event.clientY, moved:false};
      $('graph').setPointerCapture(event.pointerId);
    });
    g.addEventListener('dblclick', event => { event.stopPropagation(); navigate(node.id); });
    g.addEventListener('keydown', event => {
      if (event.key==='Enter'||event.key===' ') { event.preventDefault(); select(node.id); }
      if (event.key==='ArrowRight') { event.preventDefault(); navigate(node.id); }
    });
  }
  transform();
}
function fit() {
  const nodes = visible(); if (!nodes.length) return;
  const points = nodes.map(n=>positions.get(n.id));
  const minX=Math.min(...points.map(p=>p.x))-130,maxX=Math.max(...points.map(p=>p.x))+130;
  const minY=Math.min(...points.map(p=>p.y))-110,maxY=Math.max(...points.map(p=>p.y))+110;
  const w=$('graph').clientWidth,h=$('graph').clientHeight;
  zoom=Math.min(1.3,w/(maxX-minX),h/(maxY-minY));
  pan={x:w/2-(minX+maxX)/2*zoom,y:h/2-(minY+maxY)/2*zoom}; transform();
}
function renderExits() {
  $('exit-list').replaceChildren();
  const scope = selected ?? level;
  const edges = world.edges.filter(e => scope === null || inside(e.source,scope) || inside(e.target,scope) || e.area_target===scope);
  if (!edges.length) { const p=document.createElement('p'); p.textContent='当前范围暂无出口。'; $('exit-list').appendChild(p); }
  for (const edge of edges) {
    const card=document.createElement('div'); card.className='exit-card';
    const title=document.createElement('strong'); title.textContent=`${edge.label} #${edge.id}`;
    const info=document.createElement('p'); info.textContent=`${fullName(edge.source)} → ${fullName(edge.target)}${edge.area_target ? '（进入区域：'+byId(edge.area_target)?.label+'）':''}`;
    const actions=document.createElement('div'); actions.className='actions';
    const edit=document.createElement('button'); edit.textContent='编辑'; edit.onclick=()=>editExit(edge);
    const remove=document.createElement('button'); remove.textContent='删除'; remove.className='danger';
    remove.onclick=()=>confirmDelete(`删除出口“${edge.label}”？只删除这个方向。`,()=>write({op:'delete_exit',id:edge.id},()=>{$('exit-form').hidden=true;}));
    actions.append(edit,remove);card.append(title,info,actions);$('exit-list').appendChild(card);
  }
}
function editExit(edge=null) {
  if (busy || !discardForm()) return;
  editingExit=edge?.id ?? null; $('exit-form').hidden=false;
  $('exit-name').value=edge?.name || ''; $('exit-source').replaceChildren(); $('exit-target').replaceChildren();
  for (const node of world.nodes.filter(n=>n.kind!=='item')) {
    if (node.kind==='room') option($('exit-source'),node.id,fullName(node.id));
    option($('exit-target'),node.id,fullName(node.id)+(node.kind==='area'?'（区域入口）':''),node.kind==='area'&&!node.entry);
  }
  const source=byId(selected)?.kind==='room' ? selected : byId(selected)?.entry;
  if (edge || source) $('exit-source').value=edge?.source ?? source;
  if (edge) $('exit-target').value=edge.area_target ?? edge.target;
  $('exit-both').checked=false; $('exit-both').disabled=!!edge;
  $('exit-reverse').value='';$('reverse-label').hidden=true;$('exit-reverse').required=false;formDirty=false;
}
function confirmDelete(text, action) {
  if (busy || !discardForm()) return;
  $('confirm-message').textContent=text; $('confirm-dialog').showModal();
  $('confirm-delete').onclick=()=>{$('confirm-dialog').close();action();};
}
$('confirm-cancel').onclick=()=>$('confirm-dialog').close();
$('new-room').onclick=()=>select(null);$('empty-create').onclick=()=>select(null);
$('room-kind').onchange=()=>{ const name=$('room-name').value, desc=$('room-description').value; fillRoom(null,$('room-kind').value); $('room-name').value=name; $('room-description').value=desc; formDirty=true; };
$('new-item').onclick=()=>{if(!busy && discardForm()) fillRoom(null,'item');};
$('room-form').addEventListener('input',()=>{formDirty=true;});
$('exit-form').addEventListener('input',()=>{formDirty=true;});
$('room-form').onsubmit=event=>{
  event.preventDefault();
  write({op:$('room-kind').value==='item' ? (selected===null?'create_item':'update_item') : (selected===null?'create_room':'update_room'),id:selected,name:$('room-name').value,
    ...($('room-kind').value === 'item' ? {actions: collectActions()} : {}),
    portable:$('item-portable').checked,description:$('room-description').value,parent:num($('room-parent').value),kind:$('room-kind').value,
    entry:$('room-kind').value==='area'?num($('room-entry').value):null},payload=>{
      const room=byId(payload.result);level=room.parent;fillRoom(room.id);
    });
};
$('enter').onclick=()=>navigate(selected);$('up').onclick=()=>navigate(byId(level)?.parent ?? null);
$('delete-room').onclick=()=>{
  const id=selected; if(byId(id)?.kind==='item') {confirmDelete(`删除物品“${byId(id).label}”？`,()=>write({op:'delete_item',id},()=>fillRoom(null)));return;} confirmDelete(`删除“${byId(id)?.label}”？仅允许删除没有内部地点、角色、物品和关联出口的地点。`,()=>write({op:'delete_room',id},()=>fillRoom(null)));
};
$('new-exit').onclick=()=>editExit();$('cancel-exit').onclick=()=>{if(discardForm()){$('exit-form').hidden=true;formDirty=false;}};
$('exit-both').onchange=()=>{$('reverse-label').hidden=!$('exit-both').checked;$('exit-reverse').required=$('exit-both').checked;};
$('exit-form').onsubmit=event=>{
  event.preventDefault();write({op:editingExit===null?'create_exit':'update_exit',id:editingExit,
    name:$('exit-name').value,source:num($('exit-source').value),target:num($('exit-target').value),
    bidirectional:$('exit-both').checked,reverse_name:$('exit-reverse').value},()=>{$('exit-form').hidden=true;});
};
$('save-layout').onclick=()=>{
  if (!discardForm()) return;
  write({op:'layout',positions:world.nodes.filter(n=>positions.has(n.id)).map(n=>({id:n.id,...positions.get(n.id)}))},()=>{layoutDirty=false;});
};
$('refresh').onclick=load;$('fit').onclick=fit;
$('graph').addEventListener('pointerdown',event=>{
  if(busy)return;drag={id:null,x:event.clientX,y:event.clientY,moved:false};$('graph').setPointerCapture(event.pointerId);
});
$('graph').addEventListener('pointermove',event=>{
  if(!drag)return;const dx=event.clientX-drag.x,dy=event.clientY-drag.y;
  if(!drag.moved&&Math.hypot(dx,dy)<4)return;drag.moved=true;
  if(drag.id!==null){const p=positions.get(drag.id);p.x+=dx/zoom;p.y+=dy/zoom;layoutDirty=true;}
  else{pan.x+=dx;pan.y+=dy;}drag.x=event.clientX;drag.y=event.clientY;draw();
});
$('graph').addEventListener('pointerup',()=>{
  const end=drag;drag=null;if(end?.id!==null && end?.id!==undefined && !end.moved)select(end.id);
  if(end?.moved&&end.id!==null)message('布局已调整，点击“保存布局”后持久化。');
});
$('graph').addEventListener('pointercancel',()=>{drag=null;});
$('graph').addEventListener('wheel',event=>{
  event.preventDefault();const r=$('graph').getBoundingClientRect(),x=event.clientX-r.left,y=event.clientY-r.top;
  const next=Math.max(.15,Math.min(3,zoom*Math.exp(-event.deltaY*.001)));
  pan={x:x-(x-pan.x)*next/zoom,y:y-(y-pan.y)*next/zoom};zoom=next;transform();
},{passive:false});
window.addEventListener('beforeunload',event=>{if(formDirty||layoutDirty){event.preventDefault();event.returnValue='';}});
let pendingImport = null, importPreviewValid = false;
$('export-map').onclick = async () => {
  if (busy) return;
  if ((formDirty || layoutDirty) && !window.confirm('导出仅包含已保存的数据。继续导出吗？')) return;
  setBusy(true);
  try {
    const response = await fetch('export/', {cache:'no-store'});
    const document = await jsonResponse(response);
    const url = URL.createObjectURL(new Blob([JSON.stringify(document, null, 2)], {type:'application/json'}));
    const link = window.document.createElement('a'); link.href=url; link.download='evennia-map.json';
    window.document.body.appendChild(link); link.click(); link.remove(); setTimeout(()=>URL.revokeObjectURL(url),1000);
    message('已导出整个世界的已保存地图。');
  } catch (error) { message(error.message,true); }
  finally { setBusy(false); }
};
$('import-map').onclick = () => {
  if (busy || !discardForm()) return;
  if (layoutDirty && !window.confirm('布局尚未保存，导入后会重新读取布局。继续吗？')) return;
  $('import-file').value=''; $('import-file').click();
};
$('import-file').onchange = async () => {
  const file=$('import-file').files[0]; if (!file || busy) return;
  setBusy(true); pendingImport=null;
  try {
    if(file.size > 1000000) throw Error('地图文件不能超过 1 MB。');
    const document=JSON.parse((await file.text()).replace(/^\uFEFF/,''));
    const result=await jsonResponse(await fetch('import-preview/',{method:'POST',headers:{'Content-Type':'application/json',
      'X-CSRFToken':window.document.querySelector('meta[name="csrf-token"]').content},body:JSON.stringify(document)}));
    pendingImport=document;
    $('import-mode').value='append';$('import-replace-check').checked=false;
    $('import-spawn').replaceChildren();
    for (const node of document.nodes) if ((node.kind || 'room')==='room') option($('import-spawn'),node.key,node.name);
    importPreviewValid=true;
    $('import-spawn-label').hidden=true;$('import-replace-label').hidden=true;
    $('import-effect').textContent='以新地点追加到世界顶层，保留现有地图和角色。重复导入会创建副本。';
    $('import-summary').textContent=`${file.name}：${result.places} 个地点（${result.areas} 个区域），${result.exits} 个有向出口，${result.items} 件地面物品。顶层：${result.roots.join('、')}`;
    $('import-dialog').showModal();
  } catch(error) { message('导入校验失败：'+error.message,true); }
  finally { setBusy(false); }
};
function updateImportButton() {
  const replace=$('import-mode').value==='replace';
  $('import-confirm').textContent=replace?'确认替换地图':'确认追加导入';
  $('import-confirm').classList.toggle('danger',replace);
  $('import-confirm').disabled=busy || !importPreviewValid || (replace && !$('import-replace-check').checked);
}
async function refreshImportPreview() {
  if (!pendingImport || busy) return;
  const replace=$('import-mode').value==='replace';
  $('import-spawn-label').hidden=!replace;$('import-replace-label').hidden=!replace;
  $('import-replace-check').checked=false;importPreviewValid=false;
  setBusy(true);$('import-effect').textContent='正在核对导入影响…';
  $('import-mode').disabled=true;$('import-spawn').disabled=true;
  try {
    const result=await jsonResponse(await fetch('import-preview/',{method:'POST',headers:{'Content-Type':'application/json',
      'X-CSRFToken':document.querySelector('meta[name="csrf-token"]').content},
      body:JSON.stringify({document:pendingImport,mode:$('import-mode').value,spawn:$('import-spawn').value})}));
    importPreviewValid=true;
    $('import-effect').textContent=replace
      ? `将替换现有 ${result.replace.places} 个地点和 ${result.replace.exits} 个出口，安置 ${result.replace.relocated_objects} 个角色或物品，更新 ${result.replace.updated_homes} 个回家引用和 ${result.replace.offline_locations} 个下线位置。原地图将被移除，账号和角色保留。`
      : '以新地点追加到世界顶层，保留现有地图和角色。重复导入会创建副本。';
  } catch(error) { $('import-effect').textContent=error.message; }
  finally { setBusy(false);$('import-mode').disabled=false;$('import-spawn').disabled=false;updateImportButton(); }
}
$('import-mode').onchange=refreshImportPreview;
$('import-spawn').onchange=refreshImportPreview;
$('import-replace-check').onchange=updateImportButton;
$('import-cancel').onclick=()=>{pendingImport=null;$('import-dialog').close();};
$('import-confirm').onclick=async()=>{
  const mode=$('import-mode').value,spawn=$('import-spawn').value;
  if (!pendingImport || busy || !importPreviewValid || (mode==='replace'&&!$('import-replace-check').checked)) return;
  const document=pendingImport;
  $('import-dialog').close();
  const ok=await write({op:'import_map',document,mode,spawn},payload=>{
    layoutDirty=false; positions.clear(); accept(payload,true); level=null; selected=null; fillRoom(null);
  });
  if(ok){pendingImport=null;fit();message(mode==='replace'?'地图已替换，角色和物品已安置到所选地点。':'地图已追加导入，现有地图和角色已保留。');}
};
load();
