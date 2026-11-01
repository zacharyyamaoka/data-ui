# The public repository

Nothing from this repository's history goes to a public remote. What goes public is a snapshot of one ref.

## Where it stands

- **Public:** https://github.com/zacharyyamaoka/data-ui, first pushed 2026-10-31: one commit, `89a7bfa`, a snapshot of
  `main` @ `76950ee`. Its mirror clone is `~/data-ui-public`, the only clone with a public `origin`.
- **Checked before that push:** the mirror command with the audit's terms exited 0; `node tools/ci-local.mjs --tree` on the
  mirror passed (64 parts, the rack's and the notes' suites skipped by name); its images and videos were looked at. A fresh
  clone from GitHub had the same tree and passed the history scan.
- **Full history:** `/archive/datasets/backups/data-ui/data-ui-2026-10-31.bundle` (every ref, `git bundle verify` clean).
  It is on this machine only, on another disk.

## Updating the public repository

```
node tools/public-export.mjs --ref main --mirror ~/data-ui-public --rules <the audit's terms>
git -C ~/data-ui-public push origin main
```

The export adds one commit to the mirror's `main` and scans its whole history; push only after it exits 0. Read what
changed first (`git -C ~/data-ui-public show --stat`), and look at any new image.

**Why:** `git log -p` hands a stranger every version of every file that ever existed, and a public push cannot be
recalled. This repository's `main` held private data that was fixed forward in October 2026. A fix forward leaves the old
blobs in place, so `tools/history-scan.mjs` fails on `main` and always will. Deleting a file does not change that.

## The gate

```
node tools/history-scan.mjs --ref main                 # every blob and commit a push of main would publish
node tools/public-export.mjs --ref main --mirror DIR   # a filtered snapshot on DIR's main, scanned the same way
```

`tools/history-scan.mjs` reads every blob a ref reaches, and every commit's author, committer and message, through the
deny list outside git, the publisher's rules (`tools/publish-rules.mjs`) and any `--rules FILE`. A hit says whether it is
at the tip (a fix forward removes it) or in history only (nothing but a new history removes it).

`tools/public-export.mjs` builds the snapshot: it keeps private paths out, replaces other people's images with
placeholders (`docs/THIRD-PARTY-DATA.md`), turns the owner's home folder into `~`, strips marked private patterns from the
gates, and commits with GitHub's noreply address. Then it runs the same scan on the mirror's whole history and exits 1 on
a hit. It never pushes. Pushing is a person's decision, one at a time.

## Before the first push

1. Run the mirror command with the audit's own terms as `--rules`. It must exit 0.
2. Run `node tools/test-all.mjs` in the mirror (`docs/CI.md`).
3. Read `git -C DIR ls-files`, and look at the images. Patterns do not read pictures.
4. `gh repo create zacharyyamaoka/data-ui --public`, add it as the mirror's `origin`, and push the mirror's `main`.

Never push `lane/*`, `integrate/*`, `archive/*` or a tag from this repository. Add no remote here that a stray
`git push` could reach; the mirror is the only clone with a public `origin`.

The mirror backs up the tree, not the history. The full history stays in this repository, and it needs a backup of its own:
`git bundle create <another disk>/data-ui.bundle --all`.
