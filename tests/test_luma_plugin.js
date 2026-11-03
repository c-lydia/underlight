// Run with node; mocks only the installed plugin interfaces, not the launch logic.
const assert = require('node:assert/strict');
const fs = require('node:fs');
const path = require('node:path');
const vm = require('node:vm');
const notices = [];
const sandbox = {process:{env:{},pid:process.pid},module:{exports:{}}, require(name){
  return name === 'obsidian' ? {Plugin:class {}, Notice:class {constructor(text){notices.push(text)}}} : require(name);
}};
vm.runInNewContext(fs.readFileSync(path.join(__dirname,'../.local/share/underlight/obsidian/luma-plugin/main.js'),'utf8'), sandbox);
const Luma = sandbox.module.exports;
function fixture(plugins) {
  const app = new Luma();
  app.privacyMode = ()=>'cloud-context';
  app.buttons = new Map([['test', {disabled:false}]]);
  app.status = {textContent:''};
  app.save = () => {};
  app.toggle = value => {app.expanded=value};
  app.app = {plugins:{plugins},workspace:{getLeavesOfType:()=>[],rightSplit:{expand(){}},revealLeaf:async()=>{}}};
  return app;
}
(async()=>{
  let app = fixture({copilot:{activateAgentView:async()=>null}});
  await app.openAgent({id:'opencode',name:'OpenCode'});
  assert.match(app.status.textContent,/did not open Agent Chat/);
  assert.equal(app.expanded,true);
  assert.equal(app.opening,false);
  assert.equal(app.buttons.get('test').disabled,false);
  app = fixture({'agent-client':{openNewChatViewWithAgent:async()=>null}});
  await app.openAgent({id:'hermes',name:'Hermes',agent:'hermes-agent'});
  assert.match(app.status.textContent,/could not open a chat/);
  let calls = 0, complete;
  app = fixture({'agent-client':{openNewChatViewWithAgent:async(id,pane)=>{
    calls++; assert.equal(id,'hermes-agent'); assert.equal(pane,'right-pane');
    return new Promise(resolve=>{complete=resolve});
  }}});
  const first = app.openAgent({id:'hermes',name:'Hermes',agent:'hermes-agent'});
  await app.openAgent({id:'hermes',name:'Hermes',agent:'hermes-agent'});
  assert.equal(calls,1); complete('view-id'); await first;
  assert.equal(app.expanded,false);
  app = fixture({});
  app.save = ()=>{throw Error('Preferences are read-only')};
  await app.openAgent({id:'opencode',name:'OpenCode'});
  assert.match(app.status.textContent,/read-only/);
  assert.equal(app.opening,false);
  let launched=false;
  app=fixture({'agent-client':{openNewChatViewWithAgent:async()=>{launched=true}}});
  app.privacyMode=()=>'local';
  await app.openAgent({id:'hermes',name:'Hermes',agent:'hermes-agent'});
  assert.equal(launched,false);
  assert.match(app.status.textContent,/blocks cloud-capable/);
  app=fixture({});app.privacyMode=()=>'local';
  app.launchLocal=async agent=>{launched=agent.id};
  await app.openAgent({id:'rag',name:'Ask my notes'});
  assert.equal(launched,'rag');assert.equal(app.expanded,false);
  let privacyFile;
  const flatpak={module:{exports:{}},process:{env:{XDG_CONFIG_HOME:'/sandbox/config'}},require(name){
    if(name==='fs')return {existsSync:()=>true,readFileSync(file){privacyFile=file;return '{"mode":"local-answer"}'}};
    if(name==='obsidian')return {Plugin:class {},Notice:class {}};
    return require(name);
  }};
  vm.runInNewContext(fs.readFileSync(path.join(__dirname,'../.local/share/underlight/obsidian/luma-plugin/main.js'),'utf8'),flatpak);
  assert.equal(new flatpak.module.exports().privacyMode(),'local-answer');
  assert.equal(privacyFile,path.join(require('os').homedir(),'.config/underlight/privacy.json'));
  console.log('LUMA_PLUGIN_OK');
})().catch(error=>{console.error(error);process.exitCode=1});
