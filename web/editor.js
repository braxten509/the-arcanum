/* ARCANUM editor — Monaco + TOML-driven IntelliSense.
   Not a language server: every language's completions (keywords, snippets, dot-members,
   type inference) come from its runtime TOML's [completions] table — csharp included
   (global-configs/runtimes/dotnet.toml). This file ships zero language data. */

(function () {
  "use strict";

  // member kinds used by the TOML [completions] tables: m=method, p=property, f=field
  const M = "m", P = "p";

  // ---- monaco wiring ---------------------------------------------------
  // fallback skin for the moments before a tome's themes arrive
  const THEME_COLORS = {
    vellum: { bg: "e7d9b5", fg: "3d2b17", ac: "275d4d", dim: "8d7854", warn: "8a5d14", info: "3d4d78", light: true },
  };

  // Monaco editor colors are derived from the tome theme's CSS variables
  // (bg=bg1, fg=tx, accent=ac, dim=tx-faint, warn=warn, info=info) — one source of truth.
  function themeColors() {
    const j = window.TOME;
    const hex = (x) => String(x || "").replace("#", "");
    const out = { vellum: THEME_COLORS.vellum };
    const add = (t) => { // tome [[themes]] and global TOML skins share the vars schema
      const v = t.vars || {};
      out[t.id] = { bg: hex(v.bg1), fg: hex(v.tx), ac: hex(v.ac), dim: hex(v["tx-faint"]), warn: hex(v.warn), info: hex(v.info), light: !!t.light };
    };
    for (const s of (j && j.skins) || []) add(s);
    for (const t of (j && j.themes) || []) add(t);
    return out;
  }

  // Build a Monarch tokenizer for a language monaco doesn't ship, driven by the
  // runtime's optional [syntax] table. Just enough highlighting: keywords, types,
  // comments, strings, numbers — no operators. Keyword/type lookup rides monaco's
  // own `cases` against the @keywords/@types arrays hung on the returned object.
  function buildMonarch(syn, fallbackKw) {
    syn = syn || {};
    const esc = (x) => String(x).replace(/[.*+?^${}()|[\]\\]/g, "\\$&");   // literal regex
    const cls = (x) => String(x).replace(/[\\\]^-]/g, "\\$&");            // literal inside a char class
    const keywords = syn.keywords || fallbackKw || [];
    const types = syn.types || [];
    const strs = syn.strings || ["\"", "'"];
    const hasBlock = Array.isArray(syn.blockComment) && syn.blockComment.length === 2;
    const root = [];
    if (syn.lineComment) root.push([new RegExp(esc(syn.lineComment) + ".*$"), "comment"]);
    if (hasBlock) root.push([new RegExp(esc(syn.blockComment[0])), "comment", "@blockComment"]);
    root.push([/[a-zA-Z_]\w*/, { cases: { "@keywords": "keyword", "@types": "type", "@default": "identifier" } }]);
    root.push([/0[xX][0-9a-fA-F]+/, "number.hex"]);
    root.push([/\d*\.\d+([eE][-+]?\d+)?/, "number.float"]);
    root.push([/\d+/, "number"]);
    const tokenizer = { root };
    if (hasBlock) tokenizer.blockComment = [[new RegExp(esc(syn.blockComment[1])), "comment", "@pop"], [/./, "comment"]];
    strs.forEach((d, i) => {                                              // one state per string delimiter
      const st = "string" + i;
      root.push([new RegExp(esc(d)), { token: "string.quote", next: "@" + st }]);
      tokenizer[st] = [
        [new RegExp("[^\\\\" + cls(d) + "]+"), "string"],
        [/\\./, "string.escape"],
        [new RegExp(esc(d)), { token: "string.quote", next: "@pop" }],
      ];
    });
    root.push([/[ \t\r\n]+/, "white"]);
    return { keywords, types, tokenizer };
  }

  window.GhostEditor = {
    monacoReady: null,
    _getAllBuffers: () => ({}),

    boot(getAllBuffers) {
      this._getAllBuffers = getAllBuffers;
      require.config({ paths: { vs: "/monaco/vs" } });
      this.monacoReady = new Promise((resolve) => {
        require(["vs/editor/editor.main"], () => {
          this._defineThemes();
          this._registerCompletions();
          resolve(window.monaco);
        });
      });
      return this.monacoReady;
    },

    _defineThemes() {
      for (const [name, c] of Object.entries(themeColors())) {
        monaco.editor.defineTheme("gh0st-" + name, {
          base: c.light ? "vs" : "vs-dark", inherit: true,
          rules: [
            { token: "comment", foreground: c.dim, fontStyle: "italic" },
            { token: "keyword", foreground: c.info },
            { token: "string", foreground: c.warn },
            { token: "number", foreground: c.ac },
            { token: "type", foreground: c.ac },
          ],
          colors: {
            "editor.background": "#" + c.bg,
            "editor.foreground": "#" + c.fg,
            "editor.lineHighlightBackground": c.light ? "#00000008" : "#ffffff08",
            "editorLineNumber.foreground": "#" + c.dim,
            "editorCursor.foreground": "#" + c.ac,
            "editor.selectionBackground": "#" + c.ac + "33",
            "editorSuggestWidget.background": "#" + c.bg,
            "editorSuggestWidget.selectedBackground": "#" + c.ac + "22",
            "widget.shadow": "#00000066",
            // command palette / quick-open, keyed to the same palette so it reads as parchment, not default VS
            "editorWidget.background": "#" + c.bg,
            "editorWidget.foreground": "#" + c.fg,
            "editorWidget.border": "#" + c.ac + "55",
            "focusBorder": "#" + c.ac,
            "quickInput.background": "#" + c.bg,
            "quickInput.foreground": "#" + c.fg,
            "quickInputList.focusBackground": "#" + c.ac + "40",
            "quickInputList.focusForeground": "#" + c.fg,
            "pickerGroup.foreground": "#" + c.ac,
            "pickerGroup.border": "#" + c.dim + "44",
            "input.background": c.light ? "#0000000a" : "#ffffff0d",
            "input.foreground": "#" + c.fg,
            "input.border": "#" + c.ac + "55",
            "list.highlightForeground": "#" + c.ac,
            "list.focusHighlightForeground": "#" + c.ac,
            "keybindingLabel.background": c.light ? "#00000012" : "#ffffff14",
            "keybindingLabel.foreground": "#" + c.fg,
            "keybindingLabel.border": "#" + c.dim + "55",
            "keybindingLabel.bottomBorder": "#" + c.dim + "55",
          },
        });
      }
    },

    _registerCompletions() {
      const self = this;
      const Kind = monaco.languages.CompletionItemKind;
      const kindOf = (k) => (k === M ? Kind.Method : k === P ? Kind.Property : Kind.Field);

      // ---- TOML-driven completions for EVERY runtime ------------------------
      // A language ships keywords/snippets/members in its global-configs/runtimes/<name>.toml
      // [completions] table (merged into TOME.runtime server-side); this one
      // provider serves them all — adding a language never requires JS.
      const rt = (window.TOME && window.TOME.runtime) || {};
      const lang = rt.editorLang || "plaintext";
      const C = rt.completions || {};
      // A tome may name a language monaco doesn't ship (e.g. "odin"): register it so
      // the completion provider fires at all, and give it syntax highlighting +
      // closing pairs generated from the runtime's optional [syntax] table. Known
      // ids (javascript, python…) keep monaco's own tokenizer — we don't touch them.
      if (!monaco.languages.getLanguages().some((l) => l.id === lang)) {
        const syn = rt.syntax || {};
        const strs = syn.strings || ["\"", "'"];
        const pairs = [{ open: "(", close: ")" }, { open: "[", close: "]" }, { open: "{", close: "}" }]
          .concat(strs.map((d) => ({ open: d, close: d })));
        const comments = {};
        if (syn.lineComment) comments.lineComment = syn.lineComment;
        if (Array.isArray(syn.blockComment) && syn.blockComment.length === 2) comments.blockComment = syn.blockComment;
        monaco.languages.register({ id: lang });
        monaco.languages.setLanguageConfiguration(lang, {
          comments,
          brackets: [["(", ")"], ["[", "]"], ["{", "}"]],
          autoClosingPairs: pairs,
          surroundingPairs: pairs,
        });
        monaco.languages.setMonarchTokensProvider(lang, buildMonarch(syn, C.keywords));
      }
      const members = C.members || {};
      for (const [k, base] of Object.entries(C.memberExtends || {})) { // shared member surfaces (e.g. LINQ)
        members[k] = (members[k] || []).concat(...[].concat(base).map((b) => members[b] || []));
      }
      const returns = C.returns || {}; // method/function name -> member key, for call chains
      const typeRules = (C.types || []).map(([re, t]) => [new RegExp(re), t]);
      const declRules = (C.declTypes || []).map(([re, t]) => [new RegExp(re), t]); // declared type -> member key
      const enumRe = C.enumRegex ? new RegExp(C.enumRegex, "gm") : null;       // user enums -> value completions
      const recordRe = C.recordRegex ? new RegExp(C.recordRegex, "gm") : null; // positional params -> properties
      const rewrites = C.staticRewrites || {}; // instance-receiver members that become static calls
      const fallbackMem = (C.fallback && members[C.fallback]) || null; // guess for unknown receivers
      const internal = new Set(C.internalKeys || []); // member keys hidden from top-level suggestions
      const classRe = C.classRegex ? new RegExp(C.classRegex, "gm") : null; // groups: name, body
      const methodRe = C.methodRegex ? new RegExp(C.methodRegex, "gm") : null;
      const propRe = C.propRegex ? new RegExp(C.propRegex, "gm") : null;
      const ctorRe = C.ctorRegex ? new RegExp(C.ctorRegex) : null; // rhs -> user class name
      const asSnippet = monaco.languages.CompletionItemInsertTextRule.InsertAsSnippet;

      // user-declared types, parsed with the language's TOML regexes
      function scanTomlTypes(allText) {
        const out = {};
        if (enumRe) { // user enums: Color. offers Red/Green…, like a real editor
          enumRe.lastIndex = 0;
          let em;
          while ((em = enumRe.exec(allText))) {
            const vals = em[2].replace(/\/\*[\s\S]*?\*\//g, "").split(",")
              .map((x) => x.replace(/=[^,]*/, "").replace(/\/\/.*$/gm, "").replace(/\[[^\]]*\]/g, "").trim())
              .filter((x) => /^\w+$/.test(x));
            if (vals.length) out[em[1]] = vals.map((n) => [n, "f", em[1] + "." + n, n]);
          }
        }
        if (recordRe) { // positional record params -> properties
          recordRe.lastIndex = 0;
          let rm;
          while ((rm = recordRe.exec(allText))) {
            const mem = [];
            for (const part of rm[2].split(",")) {
              const bits = part.trim().split(/\s+/);
              if (bits.length >= 2) mem.push([bits[bits.length - 1], P, bits.slice(0, -1).join(" "), bits[bits.length - 1]]);
            }
            if (mem.length) out[rm[1]] = (out[rm[1]] || []).concat(mem);
          }
        }
        if (!classRe) return out;
        classRe.lastIndex = 0;
        let cm;
        while ((cm = classRe.exec(allText))) {
          const mem = [];
          for (const [re, kind] of [[methodRe, M], [propRe, P]]) {
            if (!re) continue;
            re.lastIndex = 0;
            let mm;
            while ((mm = re.exec(cm[2] || ""))) {
              const n = mm[1];
              if (n.startsWith("_") || n === "initialize") continue; // constructors aren't members
              mem.push(kind === M ? [n + "()", M, "your method", n + "($1)$0"] : [n, P, "your field", n]);
            }
          }
          if (mem.length) out[cm[1]] = (out[cm[1]] || []).concat(mem);
        }
        return out;
      }

      monaco.languages.registerCompletionItemProvider(lang, {
        triggerCharacters: ["."],
        provideCompletionItems(model, position) {
          const line = model.getLineContent(position.lineNumber).slice(0, position.column - 1);
          const word = model.getWordUntilPosition(position);
          const range = new monaco.Range(position.lineNumber, word.startColumn, position.lineNumber, word.endColumn);
          const item = ([label, kind, detail, insert]) => ({
            label, kind: kindOf(kind), detail, insertText: insert, insertTextRules: asSnippet, range,
          });
          const allText = Object.values(self._getAllBuffers()).join("\n\n") + "\n" + model.getValue();
          const userTypes = scanTomlTypes(allText);

          // infer a variable's type from its most recent assignment
          const inferVar = (name) => {
            if (declRules.length) { // a typed declaration names the variable's type outright (C-family)
              const dm = new RegExp("([A-Za-z_][\\w<>\\[\\],?]*)\\s+" + name + "\\s*=").exec(allText);
              if (dm) for (const [rx, t] of declRules) if (rx.test(dm[1])) return t;
            }
            const as = new RegExp("\\b" + name + "\\s*:?=\\s*(\\S[^\\n]{0,80})", "g");
            let m, rhs = null;
            while ((m = as.exec(allText))) rhs = m[1];
            if (!rhs) return null;
            const cm = ctorRe && ctorRe.exec(rhs);
            if (cm && userTypes[cm[1]]) return "user:" + cm[1];
            if (cm && members[cm[1]]) return cm[1]; // new HttpClient() -> its member table
            for (const [rx, t] of typeRules) if (rx.test(rhs)) return t;
            const call = /\.(\w+[?!]?)\s*(?:\([^()]*\))?\s*;?\s*$/.exec(rhs); // rhs ends in a call chain (`;` = C-style)
            return (call && returns[call[1]]) || null;
          };

          const dot = /([A-Za-z_]\w*(?:\([^()]*\))?(?:\.[A-Za-z_]\w*(?:\([^()]*\))?)*)\.\s*\w*$/.exec(line);
          if (dot) {
            // walk the chain left to right, like the C# provider: gets.chomp.to_i. -> num
            const segs = dot[1].match(/[A-Za-z_]\w*(?:\([^()]*\))?/g) || [];
            const base = segs[0].replace(/\(.*/, "");
            let key;
            if (segs[0].includes("(")) key = returns[base] || null;
            else if (members[base]) key = base;
            else if (userTypes[base]) key = "user:" + base;
            else key = inferVar(base) || returns[base] || null; // bare-call bases: ruby `gets.`
            for (let i = 1; i < segs.length && key; i++) {
              // chain segments are almost always calls (ruby omits the parens) → returns first
              const nm = segs[i].replace(/\(.*/, "");
              key = returns[nm] || (members[nm] && !segs[i].includes("(") ? nm : null);
            }
            const mem = key && key.startsWith("user:") ? userTypes[key.slice(5)] : members[key];
            // unknown receiver → the language's fallback table if named, else buffer words
            const out = (mem || fallbackMem || []).map(item);
            for (const [label, detail, tpl] of rewrites[key] || []) {
              // really-static members: accepting rewrites `x.IsNull…` into `string.IsNullOrEmpty(x)`;
              // same range as siblings so they rank inline, receiver erased via additionalTextEdits
              out.push({
                label, kind: Kind.Method, detail, range,
                insertText: tpl.replace("{recv}", dot[1]),
                additionalTextEdits: [{ range: new monaco.Range(position.lineNumber, dot.index + 1, position.lineNumber, word.startColumn), text: "" }],
              });
            }
            return { suggestions: out };
          }

          const sugg = [];
          for (const t of Object.keys(userTypes)) sugg.push({ label: t, kind: Kind.Class, detail: "your type", insertText: t, range });
          for (const kw of C.keywords || (rt.syntax && rt.syntax.keywords) || []) sugg.push({ label: kw, kind: Kind.Keyword, insertText: kw, range });
          for (const [label, detail, insert] of C.snippets || []) {
            sugg.push({ label, detail, kind: Kind.Snippet, insertText: insert, insertTextRules: asSnippet, range });
          }
          for (const t of Object.keys(members)) if (!internal.has(t)) sugg.push({ label: t, kind: Kind.Class, insertText: t, range });
          const seen = new Set(C.keywords || (rt.syntax && rt.syntax.keywords) || []);
          for (const w of allText.match(/[A-Za-z_]\w{2,}/g) || []) {
            if (!seen.has(w)) { seen.add(w); sugg.push({ label: w, kind: Kind.Variable, insertText: w, range }); }
          }
          return { suggestions: sugg };
        },
      });
    },

    create(host, themeName) {
      const ed = monaco.editor.create(host, {
        contextmenu: false, // monaco's menu ignores page CSS; we serve our own via window.popMenu
        language: (window.TOME && window.TOME.runtime && window.TOME.runtime.editorLang) || "plaintext",
        theme: "gh0st-" + (themeName || "vellum"),
        fontFamily: '"Fantasque Sans Mono", ui-monospace, monospace',
        fontSize: 15,
        lineHeight: 23,
        minimap: { enabled: false },
        scrollBeyondLastLine: false,
        automaticLayout: true,
        padding: { top: 12 },
        renderLineHighlight: "line",
        suggestSelection: "first",
        fixedOverflowWidgets: true,
        quickSuggestions: { other: true, comments: false, strings: false },
        tabSize: 4,
        insertSpaces: true,
        bracketPairColorization: { enabled: false },
      });
      // contextmenu:false kills monaco's own menu; app.js's document-level contextmenu
      // handler serves our themed menu for right-clicks inside this editor (works in Firefox,
      // where a listener attached to the editor's own DOM node never fired).
      return ed;
    },

    setTheme(name) {
      if (window.monaco) monaco.editor.setTheme("gh0st-" + name);
    },
  };
})();
