# Windows Scripting Rules

When running in a Unix-style shell on Windows (Git Bash is the default for Claude Code on Windows; Cursor and Copilot may use PowerShell — the same rules apply, adapt path/quoting syntax as needed):

- **ASCII only in `.py` files.** Curly quotes, em dashes, or other non-ASCII characters cause `SyntaxError`. Use straight quotes and regular dashes.
- **No `python -c` for multiline code.** Shell quoting differences between Git Bash and CMD break multiline `python -c` commands. Write a `.py` file instead.
- **PAC CLI may need a PowerShell wrapper.** If `pac` hangs or fails in Git Bash, use `powershell -Command "& pac.cmd <args>"`. See the setup skill for details.
- **Generate GUIDs in Python scripts**, not via shell backtick-substitution: `str(uuid.uuid4())` inside the `.py` file.
- **Background job output may be empty on Windows.** Agent background task runners on Windows (e.g., Claude Code's "Running in the background") can silently produce no output. Always use `python -u` (unbuffered stdout) and `print(..., flush=True)` in long-running scripts. For foreground execution with logging: `python -u scripts/import_data.py 2>&1 | tee /tmp/out.txt`. Do NOT assume a background task succeeded just because it appeared to finish.
