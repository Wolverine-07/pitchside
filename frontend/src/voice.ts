// Spoken commentary: one voice at a time, lines read in order.
//
// Azure AI Speech neural voices come from /api/speak. The browser's own voice is only a fallback
// when that audio genuinely fails to load, never because a newer line interrupted an older one
// (that used to start a second, different voice on top of the first).

type Line = { text: string; lang: string };

const BROWSER_LANG: Record<string, string> = {
  en: "en-GB", hi: "hi-IN", es: "es-ES", fr: "fr-FR", pt: "pt-BR", ar: "ar-SA", de: "de-DE", ja: "ja-JP",
};
const MAX_WAITING = 2; // live commentary: drop stale lines rather than fall behind

let enabled = false;
let queue: Line[] = [];
let playing: HTMLAudioElement | null = null;
let busy = false;

export function setVoice(on: boolean) {
  enabled = on;
  if (!on) stop();
}

export function stop() {
  queue = [];
  if (playing) {
    playing.onended = playing.onerror = null;
    playing.pause();
  }
  playing = null;
  busy = false;
  if ("speechSynthesis" in window) speechSynthesis.cancel();
}

/** Queue a line. `now` interrupts whatever is playing (recaps, answers to a question). */
export function speak(text: string, lang: string, now = false) {
  if (!enabled || !text) return;
  if (now) stop();
  queue.push({ text, lang });
  if (queue.length > MAX_WAITING) queue = queue.slice(-MAX_WAITING);
  next();
}

function done() {
  busy = false;
  playing = null;
  next();
}

function next() {
  if (busy || !queue.length || !enabled) return;
  busy = true;
  const line = queue.shift()!;
  const audio = new Audio(`/api/speak?lang=${line.lang}&text=${encodeURIComponent(line.text)}`);
  playing = audio;
  audio.onended = done;
  audio.onerror = () => {
    if (playing === audio) browserVoice(line);
  };
  audio.play().catch((err: DOMException) => {
    // AbortError means we stopped it ourselves; anything else means it can't play here.
    if (playing === audio && err.name !== "AbortError") browserVoice(line);
  });
}

function browserVoice(line: Line) {
  playing = null;
  if (!("speechSynthesis" in window)) return done();
  const u = new SpeechSynthesisUtterance(line.text);
  u.lang = BROWSER_LANG[line.lang] ?? "en-GB";
  u.onend = done;
  u.onerror = done;
  speechSynthesis.cancel();
  speechSynthesis.speak(u);
}
