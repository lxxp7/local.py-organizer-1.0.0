const vscode = require("vscode");
const { execFile } = require("child_process");
const path = require("path");

function activate(context) {
  const scriptPath = path.join(context.extensionPath, "scripts", "organize.py");
  console.log("[py-organizer] activated, script:", scriptPath);

  const runOrganizer = (document) => {
    return new Promise((resolve) => {
      const originalText = document.getText();
      const pythonCmd = getPythonCommand();

      const args = [scriptPath, document.fileName];
      const extraLocal = getLocalModules();
      if (extraLocal) {
        args.push("--local", extraLocal);
      }

      execFile(pythonCmd, args, { timeout: 10000 }, (error, stdout, stderr) => {
        if (error || !stdout) {
          if (stderr)
            vscode.window.showErrorMessage(`[py-organizer] ${stderr}`);
          return resolve([]);
        }
        if (stdout === originalText) return resolve([]);

        const fullRange = new vscode.Range(
          document.positionAt(0),
          document.positionAt(originalText.length),
        );
        resolve([vscode.TextEdit.replace(fullRange, stdout)]);
      });
    });
  };

  // ── Manual command only (no on-save) ─────────────────────────────────────
  const cmdDisposable = vscode.commands.registerCommand(
    "py-organizer.organize",
    () => {
      const editor = vscode.window.activeTextEditor;
      if (!editor || editor.document.languageId !== "python") {
        vscode.window.showWarningMessage(
          "[py-organizer] Open a Python file first.",
        );
        return;
      }

      runOrganizer(editor.document).then((edits) => {
        if (!edits || edits.length === 0) {
          vscode.window.showInformationMessage(
            "[py-organizer] Already organized.",
          );
          return;
        }
        editor.edit((eb) => {
          for (const edit of edits) eb.replace(edit.range, edit.newText);
        });
        vscode.window.showInformationMessage("[py-organizer] File organized ✓");
      });
    },
  );

  context.subscriptions.push(cmdDisposable);
}

function getPythonCommand() {
  return (
    vscode.workspace.getConfiguration("py-organizer").get("pythonPath") ||
    "python3"
  );
}

function getLocalModules() {
  return (
    vscode.workspace.getConfiguration("py-organizer").get("localModules") || ""
  );
}

function deactivate() {}

module.exports = { activate, deactivate };
