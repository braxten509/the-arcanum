/* Lifecycle-owned editor/file session shared by Workings and mastery labs. */
export class WorkbenchSession {
  constructor(kind) {
    this.kind = kind;
    this.editor = null;
    this.models = new Map();
    this.activePath = "";
    this.onActive = () => {};
    this.onChange = () => {};
  }

  mount(host, files, languageForPath, theme) {
    this.dispose();
    this.editor = window.GhostEditor.create(host, theme);
    for (const file of files || []) {
      const model = monaco.editor.createModel(
        String(file.content || ""), languageForPath(file.path));
      model.onDidChangeContent(() => this.onChange(file.path, model.getValue()));
      this.models.set(file.path, model);
    }
    this.switchTo(this.models.keys().next().value || "");
    return this;
  }

  switchTo(path) {
    const model = this.models.get(path);
    if (!model || !this.editor) return;
    this.activePath = path;
    this.editor.setModel(model);
    this.editor.focus();
    this.onActive(path);
  }

  files() {
    return [...this.models].map(([path, model]) => ({ path, content: model.getValue() }));
  }

  dispose() {
    if (this.editor) this.editor.dispose();
    for (const model of this.models.values()) model.dispose();
    this.editor = null;
    this.models.clear();
    this.activePath = "";
  }
}
