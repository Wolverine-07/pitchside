// Interface labels in every commentary language, so a viewer who picks Hindi sees Hindi throughout,
// not only in the captions. Captions themselves come from the Linguist agent.

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

export type LangId = (typeof LANGUAGES)[number]["id"];

type Key =
  | "commentary" | "ask" | "agents" | "league" | "producer" | "momentum" | "matchStats" | "liveEvents"
  | "possession" | "shots" | "xg" | "passAccuracy" | "corners" | "fouls" | "control" | "chaos"
  | "controlled" | "contested" | "chaotic" | "verified" | "leave" | "voice" | "studio" | "view"
  | "language" | "casual" | "analyst" | "myClub" | "myPlayer" | "myMetric" | "firstHalf" | "secondHalf"
  | "fullTime" | "anotherMatch" | "agentsWriting" | "why" | "howItWorks" | "live" | "waiting";

const S: Record<Key, Partial<Record<LangId, string>>> = {
  commentary: { en: "Commentary", hi: "कमेंट्री", es: "Comentario", fr: "Commentaire", pt: "Comentário", ar: "التعليق", de: "Kommentar", ja: "実況" },
  ask: { en: "Ask", hi: "पूछें", es: "Preguntar", fr: "Demander", pt: "Perguntar", ar: "اسأل", de: "Fragen", ja: "質問" },
  agents: { en: "Agents", hi: "एजेंट", es: "Agentes", fr: "Agents", pt: "Agentes", ar: "الوكلاء", de: "Agenten", ja: "エージェント" },
  league: { en: "League", hi: "लीग", es: "Liga", fr: "Ligue", pt: "Liga", ar: "الدوري", de: "Liga", ja: "リーグ" },
  producer: { en: "Producer", hi: "प्रोड्यूसर", es: "Realización", fr: "Régie", pt: "Produção", ar: "المخرج", de: "Regie", ja: "制作" },
  momentum: { en: "Momentum", hi: "मोमेंटम", es: "Dominio", fr: "Dynamique", pt: "Momento", ar: "الزخم", de: "Momentum", ja: "流れ" },
  matchStats: { en: "Match stats", hi: "मैच आँकड़े", es: "Estadísticas", fr: "Statistiques", pt: "Estatísticas", ar: "إحصاءات المباراة", de: "Statistik", ja: "スタッツ" },
  liveEvents: { en: "Live events", hi: "लाइव घटनाएँ", es: "En directo", fr: "En direct", pt: "Ao vivo", ar: "أحداث مباشرة", de: "Live-Ereignisse", ja: "ライブ" },
  possession: { en: "Possession", hi: "कब्ज़ा", es: "Posesión", fr: "Possession", pt: "Posse", ar: "الاستحواذ", de: "Ballbesitz", ja: "支配率" },
  shots: { en: "Shots (on target)", hi: "शॉट (लक्ष्य पर)", es: "Tiros (a puerta)", fr: "Tirs (cadrés)", pt: "Remates (à baliza)", ar: "التسديدات (على المرمى)", de: "Schüsse (aufs Tor)", ja: "シュート (枠内)" },
  xg: { en: "Expected goals", hi: "अपेक्षित गोल", es: "Goles esperados", fr: "Buts attendus", pt: "Golos esperados", ar: "الأهداف المتوقعة", de: "Erwartete Tore", ja: "期待ゴール" },
  passAccuracy: { en: "Pass accuracy", hi: "पास सटीकता", es: "Precisión de pase", fr: "Passes réussies", pt: "Precisão de passe", ar: "دقة التمرير", de: "Passquote", ja: "パス成功率" },
  corners: { en: "Corners", hi: "कॉर्नर", es: "Córners", fr: "Corners", pt: "Cantos", ar: "الركنيات", de: "Ecken", ja: "コーナー" },
  fouls: { en: "Fouls", hi: "फ़ाउल", es: "Faltas", fr: "Fautes", pt: "Faltas", ar: "الأخطاء", de: "Fouls", ja: "ファウル" },
  control: { en: "Control", hi: "नियंत्रण", es: "Control", fr: "Contrôle", pt: "Controlo", ar: "سيطرة", de: "Kontrolle", ja: "支配" },
  chaos: { en: "Chaos", hi: "अफरा-तफरी", es: "Caos", fr: "Chaos", pt: "Caos", ar: "فوضى", de: "Chaos", ja: "混戦" },
  controlled: { en: "Controlled", hi: "नियंत्रित", es: "Controlado", fr: "Maîtrisé", pt: "Controlado", ar: "منضبط", de: "Kontrolliert", ja: "落ち着いた展開" },
  contested: { en: "Contested", hi: "कड़ा मुकाबला", es: "Disputado", fr: "Disputé", pt: "Disputado", ar: "متكافئ", de: "Umkämpft", ja: "拮抗" },
  chaotic: { en: "Chaotic", hi: "उथल-पुथल", es: "Caótico", fr: "Chaotique", pt: "Caótico", ar: "فوضوي", de: "Chaotisch", ja: "混戦模様" },
  verified: { en: "Verified", hi: "सत्यापित", es: "Verificado", fr: "Vérifié", pt: "Verificado", ar: "موثّق", de: "Geprüft", ja: "検証済み" },
  leave: { en: "Leave", hi: "बाहर निकलें", es: "Salir", fr: "Quitter", pt: "Sair", ar: "خروج", de: "Verlassen", ja: "退出" },
  voice: { en: "Voice", hi: "आवाज़", es: "Voz", fr: "Voix", pt: "Voz", ar: "الصوت", de: "Stimme", ja: "音声" },
  studio: { en: "Studio", hi: "स्टूडियो", es: "Estudio", fr: "Studio", pt: "Estúdio", ar: "الاستوديو", de: "Studio", ja: "スタジオ" },
  view: { en: "View", hi: "दृश्य", es: "Vista", fr: "Vue", pt: "Vista", ar: "العرض", de: "Ansicht", ja: "表示" },
  language: { en: "Language", hi: "भाषा", es: "Idioma", fr: "Langue", pt: "Idioma", ar: "اللغة", de: "Sprache", ja: "言語" },
  casual: { en: "Casual", hi: "आम दर्शक", es: "Casual", fr: "Grand public", pt: "Casual", ar: "عادي", de: "Locker", ja: "ライト" },
  analyst: { en: "Analyst", hi: "विश्लेषक", es: "Analista", fr: "Analyste", pt: "Analista", ar: "محلل", de: "Analyst", ja: "分析" },
  myClub: { en: "My club", hi: "मेरा क्लब", es: "Mi club", fr: "Mon club", pt: "Meu clube", ar: "ناديي", de: "Mein Verein", ja: "マイクラブ" },
  myPlayer: { en: "My player", hi: "मेरा खिलाड़ी", es: "Mi jugador", fr: "Mon joueur", pt: "Meu jogador", ar: "لاعبي", de: "Mein Spieler", ja: "マイ選手" },
  myMetric: { en: "My metric", hi: "मेरा आँकड़ा", es: "Mi métrica", fr: "Ma stat", pt: "Minha métrica", ar: "مؤشري", de: "Meine Kennzahl", ja: "マイ指標" },
  firstHalf: { en: "First half", hi: "पहला हाफ", es: "Primera parte", fr: "Première mi-temps", pt: "Primeira parte", ar: "الشوط الأول", de: "1. Halbzeit", ja: "前半" },
  secondHalf: { en: "Second half", hi: "दूसरा हाफ", es: "Segunda parte", fr: "Seconde mi-temps", pt: "Segunda parte", ar: "الشوط الثاني", de: "2. Halbzeit", ja: "後半" },
  fullTime: { en: "Full-time", hi: "फुल-टाइम", es: "Final", fr: "Fin du match", pt: "Final", ar: "نهاية المباراة", de: "Abpfiff", ja: "試合終了" },
  anotherMatch: { en: "Watch another match", hi: "दूसरा मैच देखें", es: "Ver otro partido", fr: "Voir un autre match", pt: "Ver outro jogo", ar: "شاهد مباراة أخرى", de: "Anderes Spiel ansehen", ja: "別の試合を見る" },
  agentsWriting: { en: "Agents writing", hi: "एजेंट लिख रहे हैं", es: "Los agentes escriben", fr: "Les agents écrivent", pt: "Agentes a escrever", ar: "الوكلاء يكتبون", de: "Agenten schreiben", ja: "エージェント作成中" },
  why: { en: "Why trust this?", hi: "इस पर भरोसा क्यों?", es: "¿Por qué fiarse?", fr: "Pourquoi s'y fier ?", pt: "Porquê confiar?", ar: "لماذا نثق بهذا؟", de: "Warum vertrauen?", ja: "根拠を見る" },
  howItWorks: { en: "How it works", hi: "यह कैसे काम करता है", es: "Cómo funciona", fr: "Comment ça marche", pt: "Como funciona", ar: "كيف يعمل", de: "So funktioniert's", ja: "仕組み" },
  live: { en: "LIVE", hi: "लाइव", es: "EN VIVO", fr: "EN DIRECT", pt: "AO VIVO", ar: "مباشر", de: "LIVE", ja: "ライブ" },
  waiting: { en: "Waiting for kick-off", hi: "किक-ऑफ़ का इंतज़ार", es: "Esperando el inicio", fr: "En attente du coup d'envoi", pt: "À espera do pontapé de saída", ar: "بانتظار صافرة البداية", de: "Warten auf den Anpfiff", ja: "キックオフ待ち" },
};

export function t(lang: string, key: Key): string {
  return S[key][lang as LangId] ?? S[key].en ?? key;
}

export function dirOf(lang: string): "ltr" | "rtl" {
  return LANGUAGES.find((l) => l.id === lang)?.dir ?? "ltr";
}

const MOMENTS: Record<string, Partial<Record<LangId, string>>> = {
  goal: { hi: "गोल", es: "Gol", fr: "But", pt: "Golo", ar: "هدف", de: "Tor", ja: "ゴール" },
  big_chance: { hi: "बड़ा मौका", es: "Ocasión clara", fr: "Grosse occasion", pt: "Grande oportunidade", ar: "فرصة كبيرة", de: "Großchance", ja: "決定機" },
  pressing_spell: { hi: "दबाव का दौर", es: "Presión alta", fr: "Pressing", pt: "Pressão alta", ar: "ضغط عالٍ", de: "Pressingphase", ja: "ハイプレス" },
  momentum_swing: { hi: "मोमेंटम बदला", es: "Cambio de dominio", fr: "Bascule", pt: "Viragem", ar: "تحوّل الزخم", de: "Momentum kippt", ja: "流れが変わる" },
  chaos_spike: { hi: "नियंत्रण खोया", es: "Descontrol", fr: "Perte de contrôle", pt: "Descontrolo", ar: "فقدان السيطرة", de: "Kontrollverlust", ja: "混戦" },
  card: { hi: "कार्ड", es: "Tarjeta", fr: "Carton", pt: "Cartão", ar: "بطاقة", de: "Karte", ja: "カード" },
  milestone: { hi: "उपलब्धि", es: "Hito", fr: "Cap", pt: "Marco", ar: "إنجاز", de: "Meilenstein", ja: "節目" },
  player_speed: { hi: "सबसे तेज़", es: "Velocidad punta", fr: "Pointe de vitesse", pt: "Velocidade máxima", ar: "أعلى سرعة", de: "Topspeed", ja: "最高速度" },
  around_the_league: { hi: "लीग में और", es: "En la liga", fr: "Ailleurs", pt: "Na liga", ar: "في الدوري", de: "Rund um die Liga", ja: "他会場" },
  half_time_recap: { hi: "हाफ-टाइम सार", es: "Resumen del descanso", fr: "Bilan à la pause", pt: "Resumo ao intervalo", ar: "ملخص الشوط الأول", de: "Halbzeitfazit", ja: "前半のまとめ" },
  full_time_recap: { hi: "मैच का सार", es: "Resumen final", fr: "Bilan du match", pt: "Resumo final", ar: "ملخص المباراة", de: "Spielfazit", ja: "試合のまとめ" },
  player_spotlight: { hi: "खिलाड़ी पर नज़र", es: "Protagonista", fr: "Joueur en vue", pt: "Destaque", ar: "لاعب تحت الضوء", de: "Spieler im Fokus", ja: "注目選手" },
  match_preview: { hi: "किक-ऑफ़", es: "Previa", fr: "Coup d'envoi", pt: "Antevisão", ar: "صافرة البداية", de: "Anpfiff", ja: "キックオフ" },
  match_pulse: { hi: "मैच का हाल", es: "Cómo va el partido", fr: "Le point du match", pt: "Como está o jogo", ar: "مجريات المباراة", de: "Spielstand-Analyse", ja: "試合の流れ" },
  great_save: { hi: "शानदार बचाव", es: "Paradón", fr: "Superbe arrêt", pt: "Grande defesa", ar: "تصدٍّ رائع", de: "Glanzparade", ja: "好セーブ" },
};

export function momentIn(lang: string, type: string, english: string): string {
  return MOMENTS[type]?.[lang as LangId] ?? english;
}
