// Exercise the actual form handlers without a browser or deployment services.
const fs = require('node:fs');
const vm = require('node:vm');
const assert = require('node:assert/strict');
const nodes = {};
function element() {
  return {value: '', children: [], style: {}, dataset: {},
    classList: {toggle() {}, add() {}, remove() {}},
    append(child) { this.children.push(child); }, insertBefore() {},
    showModal() {}, close() {}, addEventListener() {}, querySelectorAll() { return []; }};
}
const document = {querySelector(selector) { return nodes[selector] ??= element(); },
  addEventListener() {}, createElement: element, body: element()};
const html = fs.readFileSync(__dirname + '/index.html', 'utf8');
const idPattern = html.match(/id="m-id"[^>]*pattern="([^"]+)"/)[1];
const idValidator = new RegExp('^(?:' + idPattern + ')$', 'v');
assert.ok(idValidator.test('chrono-logos'));
assert.ok(!idValidator.test('chrono_logos'));
const script = html.split('<script>')[1].split('</script>')[0]
  .replace('refresh();setInterval(()=>{if(state)refresh()},4000);', '');
const context = vm.createContext({document, assert, nodes, console, URL});
vm.runInContext(script, context);
vm.runInContext(`(async () => {
  state = {config_revision: 'revision', jobs: [], projects: []};
  const project = {id:'chrono-logos',name:'Chrono Logos',kind:'chrono',
    repo:'https://github.com/qboshenkiy/my_sites.git',branch:'main',subdir:'',
    directory:'/opt/chrono-logos',compose:'compose.yaml',services:['web'],profiles:[]};
  openModule(project);
  assert.equal(nodes['#m-id'].readOnly, true);
  assert.equal(nodes['#m-kind'].disabled, true);
  assert.equal(nodes['#m-subdir'].value, 'chrono_logos');
  // Simulate an extension/autofill changing disabled identity controls.
  nodes['#m-id'].value = 'chrono_logos';
  nodes['#m-kind'].value = 'docker';
  let saved;
  api = async (url, payload) => { saved = payload; };
  refresh = async () => {};
  await nodes['#module-form'].onsubmit({preventDefault(){}});
  assert.equal(saved.project.id, 'chrono-logos');
  assert.equal(saved.project.kind, 'chrono');
  assert.equal(saved.project.subdir, 'chrono_logos');
  assert.equal(saved.original_id, 'chrono-logos');
  assert.equal(nodes['#module-error'].textContent, '');
  openModule({...project,subdir:'custom-folder'});
  assert.equal(nodes['#m-subdir'].value, 'custom-folder');
  openModule({...project,repo:'https://example.org/custom.git'});
  assert.equal(nodes['#m-subdir'].value, '');
  openModule(null);
  assert.equal(nodes['#m-id'].readOnly, false);
  nodes['#m-kind'].value = 'chrono';
  nodes['#m-kind'].onchange();
  assert.equal(nodes['#m-subdir'].value, 'chrono_logos');
  assert.equal(nodes['#m-repo'].value, project.repo);
  console.log('PASS: immutable module identity, editable subdirectory, monorepo defaults');
  const select = {value:'',append(){}}, button = {}, small = {};
  const section = {dataset:{},querySelector(s){return {select,button,small}[s]}};
  document.createElement = type => type==='div' ? section : {value:'',textContent:''};
  envDialog.querySelector = () => null;
  nodes['#environment-form'].prepend = () => {};
  envProject = project;
  state.projects = [{id:'marathon',name:'Marathon',kind:'marathon',compose:'compose.https.yaml'}];
  nodes['#env-HTTPS_PROXY_PROJECT'] = {value:''};
  nodes['#env-APP_URL'] = {value:'https://vano.sbena.net:8083/'};
  setupChronoHttpsForm();
  assert.equal(nodes['#env-HTTPS_PROXY_PROJECT'].value, 'marathon');
  button.onclick();
  assert.equal(nodes['#env-HTTPS_PROXY_PROJECT'].value, 'marathon');
  assert.equal(nodes['#env-APP_URL'].value, 'https://chrono.vano.sbena.net/');
  button.onclick();
  assert.equal(nodes['#env-APP_URL'].value, 'https://chrono.vano.sbena.net/');
  nodes['#env-APP_URL'].value='https://game.example.org/';
  button.onclick();
  assert.equal(nodes['#env-APP_URL'].value, 'https://game.example.org/');
  state.projects=[];
  setupChronoHttpsForm();
  assert.equal(button.disabled,true);
  assert.ok(small.textContent.includes('compose.https.yaml'));
  console.log('PASS: HTTPS subdomain preparation, existing custom domain, missing proxy explanation');
  openModule(null);nodes['#m-kind'].value='drawing';nodes['#m-kind'].onchange();
  assert.equal(nodes['#m-subdir'].value,'sketch_game');assert.equal(nodes['#m-directory'].value,'/opt/sketch-game');
  console.log('PASS: drawing module installation defaults');
  state.config_revision='current-config';state.projects=[{id:'marathon',kind:'marathon',compose:'compose.https.yaml'}];
  const writes=[];api=async(url,payload)=>{if(!payload)return {env_revision:'current-env',fields:[{key:'APP_URL',value:'https://chrono.vano.sbena.net/'},{key:'HTTPS_PROXY_PROJECT',value:''}]};writes.push(payload)};
  await repairHttps('chrono-logos');assert.equal(writes.length,1);assert.deepEqual(writes[0].changes,{HTTPS_PROXY_PROJECT:'marathon'});assert.equal(writes[0].env_revision,'current-env');
  state.projects=[];await assert.rejects(()=>repairHttps('chrono-logos'));assert.equal(writes.length,1);
  console.log('PASS: HTTPS repair without opening settings or overwriting other variables');

})()`, context).catch(error => { console.error(error); process.exitCode = 1; });
