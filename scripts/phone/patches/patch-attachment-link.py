import pathlib, sys

F = pathlib.Path("/data/data/com.termux/files/usr/lib/node_modules/dsh-termux/node_modules/@deepseek-ai/dsh-attachment-local/lib/index.js")
s = F.read_text()

HELPER = """
/**
 * Android/Termux: SELinux denies `link()` inside the app data directory, so the
 * content-addressed store degrades to a byte copy instead of failing the write.
 */
async function linkOrCopy(source, target) {
	try {
		await link(source, target);
		return;
	} catch (error) {
		const code = error && error.code;
		if (code !== "EACCES" && code !== "EPERM" && code !== "EXDEV" && code !== "ENOSYS" && code !== "EMLINK" && code !== "EOPNOTSUPP") throw error;
	}
	const bytes = await readFile(source);
	await writeFile(target, bytes, { flag: "wx", mode: 384 });
}
"""

if "async function linkOrCopy(" in s:
    print("ALREADY_PATCHED")
    sys.exit(0)

marker = 'import { chmod, link, mkdir, open, readFile, rename, rm, unlink, writeFile } from "node:fs/promises";'
n_marker = s.count(marker)
print("import_marker", n_marker)
if n_marker != 1:
    print("IMPORT_NOT_FOUND")
    sys.exit(1)

s = s.replace(marker, marker + "\n" + HELPER, 1)

n_link = s.count("await link(")
print("link_calls", n_link)
s = s.replace("await link(", "await linkOrCopy(")

bak = F.with_suffix(".js.orig3.bak")
if not bak.exists():
    bak.write_text(F.read_text())
F.write_text(s)
print("PATCHED_OK")
