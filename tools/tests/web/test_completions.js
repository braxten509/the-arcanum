// Completion-provider check: stubs monaco, loads web/editor.js, and drives the
// one generic TOML-driven completion provider with the REAL dotnet/java/python
// [completions] tables. Run after touching editor.js completions or a runtime
// TOML:   node tools/tests/web/test_completions.js
// Assert-based, no framework; exits non-zero on the first failure.
const fs = require("fs");
const assert = require("assert");
const { execSync } = require("child_process");
const os = require("os");
const path = require("path");

const ROOT = path.join(__dirname, "..", "..", "..");
// node has no TOML parser; python does — export each runtime's [completions] to JSON
const tmp = fs.mkdtempSync(path.join(os.tmpdir(), "arcanum-completions-"));
execSync("python3 -c \"" + [
  "import tomllib, json, os",
  "root = os.environ['ARCANUM_ROOT']; out = os.environ['ARCANUM_TMP']",
  "for name in ('dotnet','java','python','rust'):",
  "    c = tomllib.load(open(os.path.join(root,'global-configs','runtimes',name+'.toml'),'rb'))",
  "    json.dump({'editorLang': c['editorLang'], 'completions': c.get('completions', {})}, open(os.path.join(out,name+'.json'),'w'))",
].join("\n") + "\"", { env: { ...process.env, ARCANUM_ROOT: ROOT, ARCANUM_TMP: tmp } });
const cfg = (name) => JSON.parse(fs.readFileSync(path.join(tmp, name + ".json")));

const providers = {};
global.monaco = {
  languages: {
    CompletionItemKind: new Proxy({}, { get: (_, k) => String(k) }),
    CompletionItemInsertTextRule: { InsertAsSnippet: 4 },
    registerCompletionItemProvider: (lang, prov) => { providers[lang] = prov; },
    getLanguages: () => [{ id: "csharp" }, { id: "java" }, { id: "python" }, { id: "rust" }],
    register: () => {}, setLanguageConfiguration: () => {}, setMonarchTokensProvider: () => {},
  },
  Range: function (a, b, c, d) { return { sl: a, sc: b, el: c, ec: d }; },
  editor: { defineTheme: () => {} },
};
global.window = {};
require(path.join(ROOT, "web", "editor.js"));

let BUF = "";
window.GhostEditor._getAllBuffers = () => ({ buf: BUF });

function completionsFor(lang, code) {
  BUF = code;
  const lines = code.split("\n");
  const lineNo = lines.length, line = lines[lineNo - 1];
  const column = line.length + 1;
  let ws = column; // word start: scan back over \w
  while (ws > 1 && /\w/.test(line[ws - 2])) ws--;
  const model = {
    getLineContent: (n) => lines[n - 1],
    getValue: () => code,
    getWordUntilPosition: () => ({ word: line.slice(ws - 1, column - 1), startColumn: ws, endColumn: column }),
  };
  return providers[lang].provideCompletionItems(model, { lineNumber: lineNo, column }).suggestions;
}
const labels = (s) => s.map((x) => x.label);
const use = (name) => { window.TOME = { runtime: cfg(name) }; window.GhostEditor._registerCompletions(); };
let s;

// ---- C# (dotnet.toml) — the ported hand-written provider ----------------
use("dotnet");
s = labels(completionsFor("csharp", "Console."));
assert(s.includes("WriteLine()"), "Console.WriteLine missing");
s = labels(completionsFor("csharp", 'string s = Console.ReadLine();\ns.'));
assert(s.includes("Trim()") && s.includes("Length"), "declared string -> str members");
s = labels(completionsFor("csharp", 'var name = Console.ReadLine();\nname.Trim().'));
assert(s.includes("ToUpper()"), "chain Trim(). -> str members");
s = labels(completionsFor("csharp", "List<string> xs = new List<string>();\nxs."));
assert(s.includes("Add()") && s.includes("Where()"), "List decl -> list+linq members");
s = labels(completionsFor("csharp", "var parts = line.Split(',');\nparts."));
assert(s.includes("Length") && s.includes("Select()"), "Split rhs -> array members");
s = labels(completionsFor("csharp", "enum Color { Red, Green = 3, Blue }\nColor."));
assert(s.includes("Red") && s.includes("Blue") && !s.includes("3"), "enum values complete");
s = labels(completionsFor("csharp", 'public record Verse(string Line, int Number);\nvar v = new Verse("x", 1);\nv.'));
assert(s.includes("Line") && s.includes("Number"), "record positional params -> properties");
s = labels(completionsFor("csharp", 'public class Tome\n{\n    public string Read(int page) { return ""; }\n    public int Pages { get; set; }\n}\nvar t = new Tome();\nt.'));
assert(s.includes("Read()") && s.includes("Pages"), "user class methods+props");
const rw = completionsFor("csharp", 'string s = "x";\ns.IsNull').find((x) => x.label === "IsNullOrEmpty()");
assert(rw && rw.insertText === "string.IsNullOrEmpty(s)" && rw.additionalTextEdits.length, "static rewrite");
s = labels(completionsFor("csharp", "mystery."));
assert(s.includes("Where()") && s.includes("ToString()"), "unknown receiver -> linq fallback");
s = labels(completionsFor("csharp", "Environment.SpecialFolder."));
assert(s.includes("UserProfile"), "nested static chain");
s = labels(completionsFor("csharp", "int."));
assert(s.includes("Parse()"), "int.Parse");
s = labels(completionsFor("csharp", "cw"));
assert(s.includes("cw") && s.includes("foreach") && s.includes("Console"), "top-level snippets/keywords/types");
assert(!s.includes("str") && !s.includes("linq"), "internal keys hidden");
s = labels(completionsFor("csharp", "var client = new HttpClient();\nclient."));
assert(s.includes("GetStringAsync()"), "new HttpClient() ctor -> member table");
// `string` (static type: Join/IsNullOrEmpty) and `str` (instance: Trim/Length) must not collide:
// `string.` is the static type, a string-typed variable is the instance receiver
s = labels(completionsFor("csharp", "string."));
assert(s.includes("Join()") && s.includes("IsNullOrEmpty()") && !s.includes("Trim()"), "string. -> static members only");
s = labels(completionsFor("csharp", 'string greeting = "hi";\ngreeting.'));
assert(s.includes("Trim()") && !s.includes("Join()"), "string-typed variable -> instance members only");
console.log("csharp: 16 scenarios OK");

// ---- Java (java.toml) ---------------------------------------------------
use("java");
s = labels(completionsFor("java", "System.out."));
assert(s.includes("println()"), "System.out.println");
s = labels(completionsFor("java", "Scanner scanner = new Scanner(System.in);\nscanner."));
assert(s.includes("nextLine()"), "new Scanner -> Scanner members");
s = labels(completionsFor("java", 'String line = scanner.nextLine();\nline.trim().'));
assert(s.includes("toLowerCase()"), "java chain -> str members");
s = labels(completionsFor("java", "Math."));
assert(s.includes("abs()"), "Math.abs");
s = labels(completionsFor("java", 'String[] parts = line.split(",");\nparts.'));
assert(s.includes("length"), "String[] decl -> array members");
s = labels(completionsFor("java", 'Map<String, Integer> hardness = new HashMap<String, Integer>();\nhardness.'));
assert(s.includes("getOrDefault()"), "Map decl -> map members");
s = labels(completionsFor("java", "enum Rune { SHARD, STONE, WAYFINDER }\nRune."));
assert(s.includes("SHARD") && s.includes("WAYFINDER"), "java enum values");
s = labels(completionsFor("java", "hi"));
assert(!s.includes("str") && !s.includes("printstream") && s.includes("Math"), "java internal keys hidden");
console.log("java: 8 scenarios OK");

// ---- Python (python.toml, unchanged config — regression) ----------------
use("python");
s = labels(completionsFor("python", 'text = "hello"\ntext.'));
assert(s.includes("upper()"), "python str members");
s = labels(completionsFor("python", 'parts = text.split(",")\nparts.'));
assert(s.includes("append()"), "python split -> list");
s = labels(completionsFor("python", "class Dog:\n    def bark(self):\n        pass\n\nd = Dog()\nd."));
assert(s.includes("bark()"), "python user class");
console.log("python: 3 scenarios OK");

// ---- Rust (rust.toml) ----------------------------------------------------
use("rust");
s = labels(completionsFor("rust", 'let s = String::from("hello");\ns.'));
assert(s.includes("push_str()") && s.includes("len()"), "Rust String members");
s = labels(completionsFor("rust", 'let mut map = HashMap::new();\nmap.'));
assert(s.includes("insert()") && s.includes("get()"), "Rust HashMap members");
s = labels(completionsFor("rust", 'struct LogEntry { message: String }\nlet entry = LogEntry { message: String::new() };\nentry.'));
assert(s.includes("message"), "Rust struct field completion");
console.log("rust: 3 scenarios OK");

fs.rmSync(tmp, { recursive: true, force: true });
console.log("ALL COMPLETION TESTS PASS");
