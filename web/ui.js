const $ = (id) => document.getElementById(id);
const esc = (value) => String(value ?? '').replace(/[&<>"']/g, c => ({
  '&':'&amp;', '<':'&lt;', '>':'&gt;', '"':'&quot;', "'":'&#39;'
}[c]));
let state, page = 'Dashboard', timer;
const brand = '<div class="brand"><div class="mark">⚙</div><div><b>MIN</b><small>Mantenimiento Industrial del Norte</small></div></div>';
const admin = () => state.me.role === 'Administrador';
const manager = () => state.me.role === 'Gerente';
const tech = () => state.me.role === 'Técnico';
const action = (label, cmd, value = '', style = '') =>
  `<button type="button" class="${style}" data-action="${cmd}" data-value="${esc(value)}">${label}</button>`;

async function api(path, data) {
  const res = await fetch('/api/' + path, data === undefined ? {} : {
    method: 'POST', headers: {'Content-Type':'application/json'}, body: JSON.stringify(data)
  });
  const body = await res.json();
  if (!res.ok) throw Error(body.error);
  return body;
}
function notice(message) {
  $('notice').textContent = message;
  clearTimeout(timer);
  timer = setTimeout(() => $('notice').textContent = '', 3500);
}
function login() {
  $('app').innerHTML = `<div class="login"><section class="login-left">${brand}
    <h1>Control de inventario</h1><p>Consulta existencias, solicita refacciones y da seguimiento a cada movimiento del almacén.</p></section>
    <section class="login-right"><div class="panel"><h2>Inicio de sesión</h2><p>Ingresa con tu cuenta de almacén.</p>
    <form id="login"><label>Usuario<input name="name" autocomplete="username" required></label>
    <label>Contraseña<input name="password" type="password" autocomplete="current-password" required></label><button>Entrar</button></form>
    <div class="demo"><p>Cuentas de demostración</p><div class="row">
    ${['admin','gerente','tecnico'].map(x=>action(x,'demo',x,'quiet')).join('')}</div><p>Contraseña: <strong>Demo2026!</strong></p></div>
    </div></section></div>`;
}
async function refresh() {
  state = await api('state');
  render();
}
function table(headers, entries, empty='Sin registros.') {
  return `<div class="table"><table><thead><tr>${headers.map(x=>`<th scope="col">${x}</th>`).join('')}</tr></thead><tbody>
  ${entries.length ? entries.map(row=>'<tr>'+row.map(cell=>`<td>${cell}</td>`).join('')+'</tr>').join('') :
  `<tr><td colspan="${headers.length}">${empty}</td></tr>`}</tbody></table></div>`;
}
function stock(p) {
  if (!p.qty) return '<span class="badge out">Agotada</span>';
  if (p.qty <= p.minimum) return '<span class="badge low">Bajo</span>';
  return '<span class="badge">Disponible</span>';
}
function heading(title, desc) {
  return `<div class="heading"><h1>${title}</h1><p>${desc}</p></div>`;
}
function dashboard() {
  const low = state.parts.filter(p=>p.qty>0 && p.qty<=p.minimum);
  const out = state.parts.filter(p=>!p.qty);
  const ok = state.parts.length-low.length-out.length;
  const cards = [['Piezas registradas',state.parts.length],['Unidades en almacén',state.parts.reduce((n,p)=>n+p.qty,0)],['Existencias bajas',low.length],['Piezas agotadas',out.length]];
  return heading('Dashboard','Resumen de existencias del almacén principal') + '<div class="row">' +
    (admin() ? action('Agregar pieza','add')+action('Registrar entrada','receive','','quiet') : '') +
    (tech() ? action('Crear solicitud','newRequest') : '') +
    (manager() ? action('Revisar solicitudes','go','Solicitudes') : '') +
    '</div><div class="cards">'+cards.map(([label,n])=>`<div class="card"><span>${label}</span><strong>${n}</strong></div>`).join('')+
    `</div><div class="columns"><section class="panel"><h2>Estado del catálogo</h2><div class="meter" aria-hidden="true">
    ${[ok,low.length,out.length].map(n=>`<span style="flex:${n}"></span>`).join('')}</div>
    <p><span class="badge">Disponible</span> ${ok}</p><p><span class="badge low">Stock bajo</span> ${low.length}</p><p><span class="badge out">Agotada</span> ${out.length}</p></section>
    <section class="panel"><h2>Alertas de inventario</h2>${table(['Código','Pieza','Stock','Mínimo','Estado'],[...out,...low].map(p=>[p.code,p.name,p.qty,p.minimum].map(esc).concat(stock(p))))}</section></div>`;
}
function partRows(filter='') {
  const found = state.parts.filter(p=>[p.code,p.name,p.category,p.location].some(x=>x.toLocaleLowerCase().includes(filter.trim().toLocaleLowerCase())));
  return table(['Código','Pieza','Categoría','Stock','Ubicación','Estado',...(manager()?[]:['Acciones'])],
    found.map(p=>[...[p.code,p.name,p.category,p.qty,p.location].map(esc),stock(p),...(admin()?
      ['<div class="row">'+action('Editar','edit',p.code,'quiet')+action('Entrada','receive',p.code,'green')+action('Eliminar','archive',p.code,'danger')+'</div>']:
      tech()?[p.qty?action('Solicitar','newRequest',p.code):'—']:[])]),'No se encontraron piezas.');
}
function requestView() {
  return heading(tech()?'Mis solicitudes':'Solicitudes de materiales',manager()?'Revisa las solicitudes pendientes y registra tu decisión.':'Consulta el estado y detalle de las solicitudes.') +
    `<section class="panel">${tech()?'<div class="toolbar">'+action('Nueva solicitud','newRequest')+'</div>':''}
    ${table(['Folio','Técnico','Pieza','Cantidad','Motivo','Estado','Revisó',...(manager()?['Acciones']:[])],state.requests.map(r=>[
      ...['SOL-'+String(r.id).padStart(3,'0'),r.user,r.name,r.qty,r.reason].map(esc),`<span class="badge ${r.status.toLowerCase()}">${r.status}</span>`,esc(r.reviewer || '—'),
      ...(manager()?[r.status==='Pendiente'?'<div class="row">'+action('Aprobar','approve',r.id,'green')+action('Rechazar','reject',r.id,'danger')+'</div>':'—']:[])
    ]))}</section>`;
}
function movementView() {
  return heading('Movimientos','Historial de entradas y salidas de inventario.') + '<section class="panel">' +
    table(['Fecha (UTC)','Código','Tipo','Unidades','Saldo','Usuario','Concepto'],state.moves.map(m=>[m.date,m.code,m.delta>0?'Entrada':'Salida',Math.abs(m.delta),m.balance,m.actor,m.reason].map(esc))) + '</section>';
}
function usersView() {
  return heading('Usuarios','Crea cuentas y actualiza sus permisos o estado.') + '<section class="panel"><div class="toolbar">'+action('Agregar usuario','user')+'</div>'+
    table(['Usuario','Perfil','Estado','Acciones'],state.users.map(u=>[esc(u.name),esc(u.role),u.active?'Activo':'Inactivo',action('Editar','user',u.name,'quiet')]))+'</section>';
}
function reportView() {
  return heading('Reportes','Exporta las existencias actuales del almacén.')+
    `<section class="panel"><h2>Inventario actual</h2><p>${state.parts.length} códigos de piezas activas.</p><a class="button" href="/api/report">Descargar CSV</a></section><section class="panel">${partRows()}</section>`;
}
function render() {
  const menu = [['▦','Dashboard'],['◇','Piezas'],['▤','Solicitudes']];
  if (!tech()) menu.push(['⇄','Movimientos']);
  if (manager()) menu.push(['▥','Reportes']);
  if (admin()) menu.push(['♙','Usuarios']);
  if (!menu.some(([,name])=>name===page)) page = 'Dashboard';
  const views = {
    Dashboard:dashboard,
    Piezas:()=>heading('Piezas','Catálogo de refacciones industriales')+
      `<section class="panel"><div class="row spread toolbar"><input id="search" aria-label="Buscar piezas" placeholder="Buscar código, pieza, categoría o ubicación">${admin()?action('Agregar pieza','add'):''}</div><div id="parts">${partRows()}</div></section>`,
    Solicitudes:requestView, Movimientos:movementView, Usuarios:usersView, Reportes:reportView
  };
  $('app').innerHTML = `<div class="layout"><aside>${brand}<nav aria-label="Menú principal">${menu.map(([icon,name])=>action(`<span aria-hidden="true">${icon}</span>${name}`,'go',name,name===page?'active':'')).join('')}</nav></aside>
    <div class="workspace"><header class="top row spread"><strong>Almacén principal</strong><div class="row"><span>${esc(state.me.name)}</span><span class="role">${state.me.role}</span>${action('Cerrar sesión','logout','','quiet')}</div></header><main>${views[page]()}</main></div></div>`;
}
const input = (label,name,value='',attrs='required') =>
  `<label>${label}<input name="${name}" value="${esc(value)}" ${attrs}></label>`;
function selectPart(code, availableOnly) {
  const parts = state.parts.filter(p=>!availableOnly || p.qty>0);
  return `<label>Pieza<select name="code" required><option value="">Selecciona una pieza</option>
    ${parts.map(p=>`<option value="${esc(p.code)}" ${p.code===code?'selected':''}>${esc(p.code+' · '+p.name+' ('+p.qty+' en stock)')}</option>`).join('')}</select></label>`;
}
function modal(title, path, fields, extra={}, next=page, label='Guardar') {
  $('modal').innerHTML = `<h2>${title}</h2><form id="change">${fields}<p role="alert"></p>
    <div class="row">${action('Cancelar','close','','quiet')}<button>${label}</button></div></form>`;
  $('change').onsubmit = async (event) => {
    event.preventDefault();
    const form = event.currentTarget;
    const button = form.querySelector('button:last-child');
    button.disabled = true;
    try {
      await api(path,{...Object.fromEntries(new FormData(form)),...extra});
      $('dialog').close();
      page = next;
      await refresh();
      notice('Operación registrada.');
    } catch (err) {
      form.querySelector('[role=alert]').textContent = err.message;
      button.disabled = false;
    }
  };
  $('dialog').showModal();
}
document.addEventListener('click',async event=>{
  const btn = event.target.closest('[data-action]');
  if (!btn) return;
  const {action:cmd,value} = btn.dataset;
  try {
    if(cmd==='demo'){
      $('login').elements.name.value=value;
      $('login').elements.password.value='Demo2026!';
      $('login').elements.password.focus();
    }
    if(cmd==='close') $('dialog').close();
    if(cmd==='go'){ page=value; await refresh(); }
    if(cmd==='logout'){ await api('logout',{}); state=null; page='Dashboard'; login(); }
    if(cmd==='add'||cmd==='edit'){
      const p=state.parts.find(x=>x.code===value)||{};
      modal(cmd==='add'?'Agregar pieza':'Editar pieza','part',
        input('Código','code',p.code,cmd==='edit'?'readonly':'required')+
        input('Nombre','name',p.name)+input('Categoría','category',p.category)+input('Ubicación','location',p.location)+
        input('Existencia mínima','minimum',p.minimum ?? 5,'required type="number" min="0"')+
        (cmd==='add'?input('Existencia inicial','qty',0,'required type="number" min="0"'):''),
        {editing:cmd==='edit'},'Piezas');
    }
    if(cmd==='archive') modal('Eliminar pieza','archive',`<p>Se dará de baja ${esc(value)} del catálogo y se conservará su historial.</p>`,{code:value},'Piezas','Eliminar');
    if(cmd==='receive') modal('Registrar entrada','stock',selectPart(value,false)+input('Unidades recibidas','qty',1,'required type="number" min="1"')+input('Concepto','reason','Compra a proveedor'),{},'Movimientos');
    if(cmd==='newRequest') modal('Nueva solicitud','request',selectPart(value,true)+input('Cantidad solicitada','qty',1,'required type="number" min="1"')+input('Motivo de mantenimiento','reason'),{},'Solicitudes','Enviar solicitud');
    if(cmd==='approve'||cmd==='reject'){
      const r=state.requests.find(x=>String(x.id)===value);
      const approve=cmd==='approve';
      modal(approve?'Aprobar solicitud':'Rechazar solicitud','review',`<p>${esc(r.name)} · ${r.qty} unidades · ${esc(r.user)}</p>`,
        {id:r.id,status:approve?'Aprobada':'Rechazada'},'Solicitudes',approve?'Confirmar aprobación':'Confirmar rechazo');
    }
    if(cmd==='user'){
      const u=state.users.find(x=>x.name===value)||{};
      modal(u.name?'Editar usuario':'Agregar usuario','user',
        input('Usuario','name',u.name,u.name?'readonly':'required')+
        input(u.name?'Nueva contraseña (opcional)':'Contraseña','password','','type="password" minlength="8" '+(u.name?'':'required'))+
        `<label>Perfil<select name="role">${['Administrador','Gerente','Técnico'].map(r=>`<option ${r===(u.role||'Técnico')?'selected':''}>${r}</option>`).join('')}</select></label>
        <label>Estado<select name="active"><option value="1">Activo</option><option value="0" ${u.active===0?'selected':''}>Inactivo</option></select></label>`,{},'Usuarios');
    }
  } catch(err) { notice(err.message); }
});
document.addEventListener('input',event=>{
  if(event.target.id==='search') $('parts').innerHTML=partRows(event.target.value);
});
document.addEventListener('submit',async event=>{
  if(event.target.id!=='login') return;
  event.preventDefault();
  try { await api('login',Object.fromEntries(new FormData(event.target))); await refresh(); }
  catch(err) { notice(err.message); }
});
refresh().catch(login);
