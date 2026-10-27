// Commentary languages. The interface itself stays in English; captions, voice and Ask answers
// come in the viewer's chosen language.

export const LANGUAGES = [
  { id: "en", label: "English", short: "EN", dir: "ltr" },
  { id: "hi", label: "हिन्दी", short: "हिं", dir: "ltr" },
  { id: "es", label: "Español", short: "ES", dir: "ltr" },
  { id: "fr", label: "Français", short: "FR", dir: "ltr" },
  { id: "pt", label: "Português", short: "PT", dir: "ltr" },
  { id: "ar", label: "العربية", short: "ع", dir: "rtl" },
  { id: "de", label: "Deutsch", short: "DE", dir: "ltr" },
  { id: "ja", label: "日本語", short: "日", dir: "ltr" },
] as const;

export function dirOf(lang: string): "ltr" | "rtl" {
  return LANGUAGES.find((l) => l.id === lang)?.dir ?? "ltr";
}
