const {Plugin, Notice} = require('obsidian');
const fs = require('fs');
const path = require('path');
const os = require('os');

module.exports = class LumaPlugin extends Plugin {
  async onload() {
    this.assets = path.join(os.homedir(), '.local/share/underlight/luma');
    this.statePath = path.join(os.homedir(), '.config/underlight/luma.json');
    try { this.agents = JSON.parse(fs.readFileSync(path.join(this.assets, 'agents.json'), 'utf8')); }
    catch { new Notice('Luma assets are missing. Install Underlight Luma first.'); return; }
    this.root = document.body.createDiv({cls:'underlight-luma'});
    this.panel = this.root.createDiv({cls:'underlight-luma-panel'});
    this.panel.setAttribute('role', 'dialog'); this.panel.setAttribute('aria-label', 'Luma AI launcher');
    this.panel.createDiv({text:'Luma', cls:'underlight-luma-title'});
    this.panel.createEl('p', {text:'Your notes. Your tools. One familiar face.'});
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
  }
  toggle(value){this.expanded=value===undefined?!this.expanded:value;this.root.classList.toggle('luma-open',this.expanded);this.avatar.setAttribute('aria-expanded',String(!!this.expanded));if(this.expanded)this.buttons.values().next().value?.focus()}
  async openAgent(agent){
    this.save({selected:agent.id});this.status.textContent='Opening '+agent.name+'…';
    try {
      if(agent.agent){
        const client=this.app.plugins.plugins['agent-client'];
        if(!client)throw Error('Enable Agent Client in Community plugins.');
        const leaves=this.app.workspace.getLeavesOfType('agent-client-chat-view');
        const existing=leaves.find(l=>l.view.acpClient?.currentAgentId===agent.agent);
        if(existing)await this.app.workspace.revealLeaf(existing);
        else await client.openNewChatViewWithAgent(agent.agent);
      }else{
        const copilot=this.app.plugins.plugins.copilot;
        if(!copilot)throw Error('Enable Copilot in Community plugins.');
        await copilot.activateAgentView(true);
        if(agent.model){
          const manager=copilot.agentSessionManager;
          const session=await manager.createSession('opencode',undefined,{baseModelId:agent.model,effort:null});await session.ready;
        }
        if(agent.id==='rag')new Notice('Ask your question in OpenCode and request the underlight_rag tool. Its local assistant uses Qwen on your GPU.',9000);
      }
      this.app.workspace.rightSplit.expand();this.status.textContent='Ready';this.toggle(false);
    }catch(error){this.status.textContent=error.message||String(error);new Notice(this.status.textContent)}
  }
  onunload(){this.root?.remove()}
};
