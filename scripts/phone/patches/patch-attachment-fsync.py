import pathlib, sys

F = pathlib.Path("/data/data/com.termux/files/usr/lib/node_modules/dsh-termux/node_modules/@deepseek-ai/dsh-attachment-local/lib/index.js")
s = F.read_text()

OLD_TAB = "\tconst handle = await open(path, constants.O_RDONLY);\n\ttry {\n\t\tawait handle.sync();\n\t} finally {\n\t\tawait handle.close();\n\t}"

NEW_TAB = """\tlet handle;
\ttry {
\t\thandle = await open(path, constants.O_RDONLY);
\t} catch (error) {
\t\tconst code = error?.code;
\t\t/* Android/Termux: ancestors above the app sandbox (e.g. /data/data) deny O_RDONLY.
\t\t   Durability of those system directories is not ours to claim, so the walk is best-effort there. */
\t\tif (code === "EACCES" || code === "EPERM" || code === "ENOENT" || code === "EISDIR" || code === "ENOTDIR") return;
\t\tthrow error;
\t}
\ttry {
\t\tawait handle.sync();
\t} catch (error) {
\t\tconst code = error?.code;
\t\tif (code !== "EACCES" && code !== "EPERM" && code !== "EINVAL" && code !== "EBADF") throw error;
\t} finally {
\t\tawait handle.close();
\t}"""

if "Android/Termux: ancestors above the app sandbox" in s:
    print("ALREADY_PATCHED")
    sys.exit(0)

n = s.count(OLD_TAB)
print("tab_match", n)
if n == 1:
    bak = F.with_suffix(".js.orig2.bak")
    if not bak.exists():
        bak.write_text(s)
    F.write_text(s.replace(OLD_TAB, NEW_TAB, 1))
    print("PATCHED_OK")
else:
    idx = s.find("const handle = await open(path, constants.O_RDONLY);")
    print("ctx:", repr(s[max(0, idx - 120):idx + 200]) if idx >= 0 else "NOT_FOUND")
