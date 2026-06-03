/**
 * review-notify — push-based "wake the agent" plugin.
 *
 * Replaces the old polling pattern (the agent re-reading .review-status.json
 * inside a turn). Instead this plugin watches the state file with an OS-level
 * fs.watch (zero LLM tokens) and, the moment review-run.sh finishes the
 * mechanical steps and writes its "Mechanical checks complete" note, injects a
 * new turn into the active session via the server's promptAsync API. opencode
 * then starts a turn on its own and the agent continues the judgment steps.
 *
 * Lives in the repo so it is versioned with the rest of the debpr tooling.
 * Loaded via an absolute entry in ~/.config/opencode/opencode.jsonc so it is
 * active no matter which directory opencode is launched from.
 */
import type { Plugin } from "@opencode-ai/plugin"
import { watch } from "node:fs"
import { readFile } from "node:fs/promises"
import { fileURLToPath } from "node:url"
import { dirname, join, basename } from "node:path"

// .review-status.json lives at the repo root, two levels up from
// <repo>/.opencode/plugin/. Resolve relative to this file so the watched
// path is correct regardless of the process cwd.
const HERE = dirname(fileURLToPath(import.meta.url))
const STATE_FILE = join(HERE, "..", "..", ".review-status.json")
const STATE_DIR = dirname(STATE_FILE)
const STATE_NAME = basename(STATE_FILE)

// The note review-run.sh writes when the scriptable steps are done.
const COMPLETE_PREFIX = "Mechanical checks complete"

// Pull a sessionID out of whatever bus event shape we get. Different events
// carry it in different places:
//   session.idle / session.status / message.removed -> properties.sessionID
//   message.updated                                 -> properties.info.sessionID (Message)
//   message.part.updated                            -> properties.part.sessionID
//   session.created / session.updated               -> properties.info.id (Session)
function sessionIdFromEvent(event: any): string | undefined {
  const p = event?.properties
  if (!p) return undefined
  if (typeof p.sessionID === "string") return p.sessionID
  if (typeof p.part?.sessionID === "string") return p.part.sessionID
  if (typeof p.info?.sessionID === "string") return p.info.sessionID // Message
  if (typeof event.type === "string" && event.type.startsWith("session.")) {
    if (typeof p.info?.id === "string") return p.info.id // Session
  }
  return undefined
}

export default (async ({ client }) => {
  // Most recent session we saw activity from. Every bus event that concerns a
  // session carries properties.sessionID; we just remember the latest one so
  // we know where to inject the continuation prompt.
  let lastSessionID: string | undefined
  // Signature of the last completion we already notified about, so repeated
  // file writes (the agent updating individual steps) don't re-fire.
  let lastNotified: string | undefined
  let debounce: ReturnType<typeof setTimeout> | undefined

  async function check() {
    let state: any
    try {
      state = JSON.parse(await readFile(STATE_FILE, "utf8"))
    } catch {
      return // file mid-write or absent; the next watch event will retry
    }
    const note: string = state?.note ?? ""
    if (!note.startsWith(COMPLETE_PREFIX)) return

    const pkg: string = state?.package ?? "package"
    const signature = `${pkg}::${note}`
    if (signature === lastNotified) return // already woke the agent for this run

    // Prefer the session we saw activity from; otherwise fall back to the most
    // recently updated top-level session (handles fresh starts / restarts where
    // no bus event has fired yet).
    let sessionID = lastSessionID
    if (!sessionID) {
      try {
        const res: any = await client.session.list()
        const sessions: any[] = res?.data ?? res ?? []
        const top = sessions
          .filter((s) => s && !s.parentID)
          .sort((a, b) => (b?.time?.updated ?? 0) - (a?.time?.updated ?? 0))
        sessionID = top[0]?.id
      } catch {
        /* ignore; retry on next change */
      }
    }
    if (!sessionID) return // no session to talk to yet

    lastNotified = signature
    const text =
      `Mechanical PPA-review steps just completed for ${pkg}. ` +
      `Continue the review now: work through the remaining judgment steps ` +
      `(classification, debian/* files, symbols & ABI) and write Result_${pkg}.md, ` +
      `then mark the Report step done so the panel reaches N/N.`

    try {
      await client.session.promptAsync({
        path: { id: sessionID },
        body: { parts: [{ type: "text", text }] },
      })
      // best-effort visual cue; ignore if the TUI isn't attached
      try {
        await client.tui?.showToast?.({
          body: { message: `review-notify: woke agent for ${pkg}`, variant: "info" },
        })
      } catch {
        /* no TUI attached / headless server */
      }
    } catch (err) {
      // Don't let a failed inject crash the plugin; allow a retry next change.
      lastNotified = undefined
      console.error("review-notify: promptAsync failed:", err)
    }
  }

  // Watch the directory (not the file) so the watcher survives in-place
  // rewrites and atomic replaces; filter for our filename.
  try {
    watch(STATE_DIR, (_event, filename) => {
      if (filename && basename(filename.toString()) !== STATE_NAME) return
      clearTimeout(debounce)
      debounce = setTimeout(() => void check(), 200)
    })
  } catch (err) {
    console.error("review-notify: could not watch", STATE_DIR, err)
  }

  return {
    event: async ({ event }) => {
      const sid = sessionIdFromEvent(event)
      if (sid) lastSessionID = sid
    },
  }
}) satisfies Plugin
