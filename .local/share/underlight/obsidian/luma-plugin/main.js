const {Plugin, Notice} = require('obsidian');
const fs = require('fs');
const path = require('path');
const os = require('os');
const {spawn} = require('child_process');
function hostConfigRoot(){
  const fallback=path.join(os.homedir(),'.config');
  const root=process.env.UNDERLIGHT_HOST_XDG_CONFIG_HOME ||
    (fs.existsSync('/.flatpak-info')?fallback:(process.env.XDG_CONFIG_HOME||fallback));
  return path.join(root,'underlight');
}

module.exports = class LumaPlugin extends Plugin {
  async onload() {
    this.assets = path.join(os.homedir(), '.local/share/underlight/luma');
    this.configRoot = hostConfigRoot();
    this.statePath = path.join(this.configRoot, 'luma.json');
    this.privacyPath = path.join(this.configRoot, 'privacy.json');
    try { this.agents = JSON.parse(fs.readFileSync(path.join(this.assets, 'agents.json'), 'utf8')); }
    catch { new Notice('Luma assets are missing. Install Underlight Luma first.'); return; }
    this.root = document.body.createDiv({cls:'underlight-luma'});
    this.panel = this.root.createDiv({cls:'underlight-luma-panel'});
    this.panel.setAttribute('role', 'dialog'); this.panel.setAttribute('aria-label', 'Luma AI launcher');
    this.panel.createDiv({text:'Luma', cls:'underlight-luma-title'});
    this.panel.createEl('p', {text:'Your notes. Your tools. One familiar face.'});
    this.privacyLabel = this.panel.createEl('p', {cls:'underlight-luma-status'});
    const privacySelect = this.panel.createEl('select', {attr:{'aria-label':'AI privacy mode'}});
    for(const [value,label] of [['local','Local tools only'],['local-answer','Share local answers and sources'],['cloud-context','Allow raw excerpts in cloud clients']]){
      privacySelect.createEl('option',{attr:{value},text:label});
    }
    privacySelect.onchange=()=>{
      const temp=this.privacyPath+`.${process.pid}.tmp`;
      try{
        fs.mkdirSync(this.configRoot,{recursive:true});
        fs.writeFileSync(temp,JSON.stringify({mode:privacySelect.value})+'\n',{mode:0o600});
        fs.renameSync(temp,this.privacyPath);this.sync();
      }catch(error){new Notice(error.message)}
    };
    this.privacySelect=privacySelect;
    this.buttons = new Map();
    for (const agent of this.agents) {
      const button = this.panel.createEl('button', {cls:'underlight-luma-choice'});
      button.createSpan({text:agent.name}); button.createEl('small', {text:agent.detail});
      button.onclick = () => this.openAgent(agent);
      this.buttons.set(agent.id, button);
    }
    this.status = this.panel.createEl('p', {cls:'underlight-luma-status',text:'Choose an AI to open it.'});
    this.status.setAttribute('aria-live','polite');
    const controls = this.panel.createDiv({cls:'underlight-luma-controls'});
    for (const [label, action] of [
      ['Motion',()=>this.save({motion:this.read().motion===false})],
      ['Dock',()=>this.save({dock:this.read().dock === 'left'?'right':'left'})],
      ['Hide',()=>this.save({obsidianHidden:true})],
      ['Close',()=>this.toggle(false)]]) {
      const b = controls.createEl('button',{text:label}); b.onclick=action;
    }
    this.avatar = this.root.createEl('button',{cls:'underlight-luma-avatar',attr:{'aria-label':'Luma — open AI tools','aria-expanded':'false'}});
    const image = fs.readFileSync(path.join(this.assets,'avatar.png')).toString('base64');
    this.avatar.style.backgroundImage = `url("data:image/png;base64,${image}")`;
    this.avatar.onclick=()=>this.toggle();
    this.registerDomEvent(document,'keydown',e=>{if(e.key==='Escape')this.toggle(false)});
    this.addCommand({id:'toggle',name:'Show or hide Luma',callback:()=>this.save({obsidianHidden:!this.read().obsidianHidden})});
    this.addCommand({id:'open-launcher',name:'Open Luma AI launcher',callback:()=>{this.save({obsidianHidden:false});this.toggle(true)}});
    this.addRibbonIcon('sparkles','Luma',()=>{this.save({obsidianHidden:false});this.toggle()});
    this.registerInterval(window.setInterval(()=>this.sync(),1000));
    this.sync();
  }
  read(){try{const s=JSON.parse(fs.readFileSync(this.statePath,'utf8'));return s&&typeof s==='object'&&!Array.isArray(s)?s:{}}catch{return {}}}
  save(changes){
    const state={...this.read(),...changes};fs.mkdirSync(path.dirname(this.statePath),{recursive:true});
    const temp=this.statePath+`.${process.pid}.tmp`;fs.writeFileSync(temp,JSON.stringify(state,null,2)+'\n');fs.renameSync(temp,this.statePath);this.sync();
  }
  sync(){
    const state=this.read();this.root.hidden=!!state.obsidianHidden;
    this.root.classList.toggle('luma-left',state.dock==='left');
    this.root.classList.toggle('luma-still',state.motion===false);
    for(const [id,b] of this.buttons)b.setAttribute('aria-pressed',String(id===(state.selected||'opencode')));
    try{
      const mode=this.privacyMode();this.privacySelect.value=mode;
      this.privacyLabel.textContent=mode==='local'?'Local tools only. External AI launches are blocked.':mode==='local-answer'?'RAG shares answers and source paths. External clients retain their own file access.':'RAG may send raw note excerpts to cloud clients.';
      if(process.env.UNDERLIGHT_PRIVACY)this.privacyLabel.textContent+=' Session override is active.';
    }catch(error){this.privacyLabel.textContent=error.message}
  }
  privacyMode(){
    const file=this.privacyPath || path.join(hostConfigRoot(),'privacy.json');
    let selected=process.env.UNDERLIGHT_PRIVACY;
    if(selected===undefined){
      try{selected=JSON.parse(fs.readFileSync(file,'utf8')).mode || 'local'}
      catch(error){if(error.code==='ENOENT')selected='local';else throw Error('Cannot read privacy settings; cloud launch blocked.')}
    }
    if(!['local','local-answer','cloud-context'].includes(selected))throw Error('Invalid privacy mode; cloud launch blocked.');
    return selected;
  }
  launchLocal(agent){
    const helper=path.join(os.homedir(),'.local/bin/underlight-ai');
    const vault=this.app.vault.adapter.getBasePath();
    const args=agent.id==='qwen'?['ollama','qwen3:4b']:['rag'];
    const env={...process.env};
    const rag=path.join(vault,'.obsidian/underlight-rag.yaml');
    if(fs.existsSync(rag))env.RAG_CONFIG=rag;
    let executable=helper, argv=args;
    if(fs.existsSync('/.flatpak-info')){
      executable='flatpak-spawn';argv=['--host','env'];
      if(env.RAG_CONFIG)argv.push('RAG_CONFIG='+env.RAG_CONFIG);
      if(env.UNDERLIGHT_PRIVACY)argv.push('UNDERLIGHT_PRIVACY='+env.UNDERLIGHT_PRIVACY);
      argv.push(helper,...args);
    }
    return new Promise((resolve,reject)=>{
      const child=spawn(executable,argv,{cwd:vault,env,detached:true,stdio:'ignore'});
      child.once('error',reject);child.once('spawn',()=>{child.unref();resolve()});
      child.once('exit',code=>{if(code)new Notice('Local AI launcher failed. Run underlight-ai status in a terminal.')});
    });
  }
  toggle(value){this.expanded=value===undefined?!this.expanded:value;this.root.classList.toggle('luma-open',this.expanded);this.avatar.setAttribute('aria-expanded',String(!!this.expanded));if(this.expanded)this.buttons.values().next().value?.focus()}
  async openAgent(agent){
    if(this.opening)return;
    this.opening=true;
    for(const button of this.buttons.values())button.disabled=true;
    try {
      this.save({selected:agent.id});this.status.textContent='Opening '+agent.name+'…';
      const local=agent.id==='qwen'||agent.id==='rag';
      if(!local&&this.privacyMode()==='local')throw Error('Local privacy mode blocks cloud-capable agents. Select local-answer or cloud-context to allow this launch.');
      if(local){
        await this.launchLocal(agent);
      }else if(agent.agent){
        const client=this.app.plugins.plugins['agent-client'];
        if(!client)throw Error('Enable Agent Client in Community plugins.');
        if(typeof client.openNewChatViewWithAgent!=='function')throw Error('This Agent Client version does not support Luma. Update Agent Client.');
        const leaves=this.app.workspace.getLeavesOfType('agent-client-chat-view');
        const existing=leaves.find(l=>l.view.acpClient?.currentAgentId===agent.agent);
        if(existing)await this.app.workspace.revealLeaf(existing);
        else if(!await client.openNewChatViewWithAgent(agent.agent,'right-pane'))throw Error('Agent Client could not open a chat. Check its agent configuration.');
      }else{
        const copilot=this.app.plugins.plugins.copilot;
        if(!copilot)throw Error('Enable Copilot in Community plugins.');
        if(typeof copilot.activateAgentView!=='function')throw Error('Luma requires Copilot V4 with Agent Chat enabled.');
        if(!await copilot.activateAgentView(true))throw Error('Copilot did not open Agent Chat. Enable Agent Mode and configure OpenCode in Copilot settings.');
        if(agent.model){
          const manager=copilot.agentSessionManager;
          if(!manager?.createSession)throw Error('Copilot Agent Mode is not ready. Configure its OpenCode backend first.');
          const session=await manager.createSession('opencode',undefined,{baseModelId:agent.model,effort:null});await session.ready;
        }
        if(agent.id==='rag')new Notice('Ask your question in OpenCode and request the underlight_rag tool. Its local assistant uses Qwen on your GPU.',9000);
      }
      this.app.workspace.rightSplit?.expand();this.status.textContent='Ready';this.toggle(false);
    }catch(error){this.status.textContent=error.message||String(error);this.toggle(true);new Notice(this.status.textContent)}
    finally{this.opening=false;for(const button of this.buttons.values())button.disabled=false}
  }
  onunload(){this.root?.remove()}
};
