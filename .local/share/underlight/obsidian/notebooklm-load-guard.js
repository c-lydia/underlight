      // Underlight: expose failed navigations instead of leaving a blank webview.
      this.loadStatus = container.createDiv();
      this.loadStatus.setAttribute('role', 'status');
      this.loadStatus.style.cssText = 'padding:8px 12px;display:none;white-space:pre-wrap';
      container.insertBefore(this.loadStatus, this.webviewEl);
      this.webview.addEventListener('did-start-loading', () => {
        this.loadFailed = false;
        this.loadStatus.textContent = 'Loading NotebookLM…';
        this.loadStatus.style.display = 'block';
      });
      this.webview.addEventListener('did-finish-load', () => {
        if (!this.loadFailed) this.loadStatus.style.display = 'none';
      });
      this.webview.addEventListener('did-fail-load', (event) => {
        if (!event.isMainFrame || event.errorCode === -3) return;
        this.loadFailed = true;
        this.loadStatus.textContent = 'NotebookLM could not load: ' + event.errorDescription + '\nUse Refresh to retry, or Notebook List to return home.';
        this.loadStatus.style.display = 'block';
      });
