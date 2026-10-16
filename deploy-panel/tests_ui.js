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
const script = html.split('<script>')[1].split('</script>')[0]
  .replace('refresh();setInterval(()=>{if(state)refresh()},4000);', '');
const context = vm.createContext({document, assert, nodes, console});
vm.runInContext(script, context);
vm.runInContext(`(async () => {
  state = {config_revision: 'revision', jobs: [], projects: []};
  const project = {id:'chrono-logos',name:'Chrono Logos',kind:'chrono',
    repo:'https://github.com/qboshenkiy/my_sites.git',branch:'main',subdir:'',
    directory:'/opt/chrono-logos',compose:'compose.yaml',services:['web'],profiles:[]};
  openModule(project);
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
  nodes['#m-kind'].value = 'chrono';
  nodes['#m-kind'].onchange();
  assert.equal(nodes['#m-subdir'].value, 'chrono_logos');
  assert.equal(nodes['#m-repo'].value, project.repo);
  console.log('PASS: immutable module identity, editable subdirectory, monorepo defaults');
})()`, context).catch(error => { console.error(error); process.exitCode = 1; });
