import { useCallback, useEffect, useRef, useState } from "react";
import {
  BookOpen as BookIcon,
  CircleHelp as QuizIcon,
  Code2 as CodeIcon,
  Copy as CopyIcon,
  Download as DownloadIcon,
  ExternalLink,
  FileCode2 as CodeFileIcon,
  FileText as DocumentIcon,
  History as HistoryIcon,
  Lock as LockIcon,
  LogOut as LogoutIcon,
  Mail as MailIcon,
  Menu as MenuIcon,
  MoreHorizontal,
  Mic,
  MicOff,
  Paperclip as AttachIcon,
  Pause as PauseIcon,
  Pencil as EditIcon,
  Pin as PinIcon,
  Play as PlayIcon,
  Plus as PlusIcon,
  RotateCcw as RegenerateIcon,
  Search as SearchIcon,
  SendHorizontal as SendIcon,
  Settings2 as SettingsIcon,
  Square as StopIcon,
  ThumbsDown as NotHelpfulIcon,
  ThumbsUp as HelpfulIcon,
  Trash2 as TrashIcon,
  UserRound as ProfileIcon,
  Volume2 as SpeakerIcon,
  X as CloseIcon
} from "lucide-react";
import "./index.css";
import { supabase, supabaseConfigured } from "./supabaseClient";

const DEFAULT_API_BASE = import.meta.env?.VITE_API_BASE_URL || "http://127.0.0.1:8000";
const SESSION_KEY = "febguy_profile_session";
const ACTIVE_SESSION_MODE_KEY = "febguy_active_session_mode";
const DEVICE_ID_KEY = "febguy_device_id";
const SKIP_GUEST_AUTO_START_KEY = "febguy_skip_guest_auto_start";
const ANSWER_LENGTH_KEY = "febguy_answer_length";
const MODEL_MODE_KEY = "febguy_model_mode";
const RESPONSE_MODE_KEY = "febguy_response_mode";
const RESPONSE_FEEDBACK_KEY = "febguy_response_feedback";
const GUEST_LIMIT_MESSAGE = "You\u2019ve reached the guest limit. Sign in to continue.";
const META_PREFIX = "\n\n[[FEBGUY_META:";
const META_SUFFIX = "]]";
const answerLengthOptions = ["short", "standard", "detailed"];
const modelModeOptions = [
  { value: "fast", label: "Fast" },
  { value: "smart", label: "Smart" },
  { value: "deep", label: "Deep" }
];
const responseModeOptions = [
  { value: "balanced", label: "Balanced" },
  { value: "deep", label: "Deep" },
  { value: "creative", label: "Creative" },
  { value: "teacher", label: "Teacher" },
  { value: "human", label: "Human" }
];
const hiddenSuggestions = new Set([
  "Explain this more simply",
  "Give me step-by-step help",
  "Turn this into an action plan"
]);
const CODE_FILE_ACCEPT = ".py,.js,.jsx,.ts,.tsx,.c,.cpp,.h,.hpp,.java,.html,.css,.json,.md,.txt,.sql,.yml,.yaml,.toml,text/plain,text/html,text/css,text/javascript,application/json";
const MAX_CODE_FILES_PER_TURN = 8;
const VOICE_STATES = {
  IDLE: "Idle",
  LISTENING: "Listening",
  THINKING: "Thinking",
  SPEAKING: "Speaking",
  PAUSED: "Paused",
  ERROR: "Error"
};
const voiceSpeedRates = {
  slow: 0.88,
  normal: 1.03,
  fast: 1.18
};
const voiceSpeedLabels = {
  slow: "Slow",
  normal: "Normal",
  fast: "Fast"
};
const BROWSER_RECOGNITION_FALLBACK_ERRORS = new Set([
  "network",
  "service-not-allowed",
  "language-not-supported"
]);
const SHORT_INTERRUPT_COMMANDS = [
  "stop",
  "pause",
  "wait",
  "hold on",
  "one second",
  "no wait",
  "actually",
  "listen"
];

async function readBackendError(response, fallback = "Backend request failed.") {
  try {
    const data = await response.json();
    return data.detail || data.error || data.message || fallback;
  } catch {
    return response.statusText || fallback;
  }
}

function formatClientError(error, fallback = "Something went wrong.") {
  const message = String(error?.message || "");
  if (message.toLowerCase().includes("failed to fetch")) {
    return "Backend unavailable. Start the FastAPI backend and check the app URL.";
  }
  return message || fallback;
}

function isGuestLimitMessage(message) {
  return String(message || "").includes("reached the guest limit");
}

function stripThinkingBlocks(text) {
  return String(text || "")
    .replace(/<think\b[^>]*>[\s\S]*?<\/think>/gi, "")
    .replace(/<\/?think\b[^>]*>/gi, "")
    .replace(/\n{3,}/g, "\n\n")
    .trim();
}

function normalizeVoiceText(text) {
  return String(text || "")
    .toLowerCase()
    .replace(/https?:\/\/\S+/g, " ")
    .replace(/[^a-z0-9\s']/g, " ")
    .replace(/\s+/g, " ")
    .trim();
}

function voiceTokens(text) {
  return normalizeVoiceText(text)
    .split(/\s+/)
    .filter(token => token.length > 2);
}

function isShortInterruptCommand(text) {
  const normalized = normalizeVoiceText(text);
  return SHORT_INTERRUPT_COMMANDS.some(command => (
    normalized === command || normalized.startsWith(`${command} `)
  ));
}

function hasHighEchoOverlap(transcript, spokenText) {
  const heardTokens = voiceTokens(transcript);
  if (heardTokens.length < 3) {
    return false;
  }

  const spokenTokenSet = new Set(voiceTokens(spokenText));
  if (!spokenTokenSet.size) {
    return false;
  }

  const overlapCount = heardTokens.filter(token => spokenTokenSet.has(token)).length;
  return overlapCount / heardTokens.length >= 0.6;
}

function isMeaningfulVoiceInterrupt(transcript, confidence, spokenText) {
  const normalized = normalizeVoiceText(transcript);
  if (normalized.length < 3) {
    return false;
  }

  const command = isShortInterruptCommand(normalized);
  if (typeof confidence === "number" && confidence > 0) {
    if (command && confidence < 0.35) {
      return false;
    }
    if (!command && confidence < 0.55) {
      return false;
    }
  }

  if (command) {
    return true;
  }

  const tokens = voiceTokens(normalized);
  if (tokens.length < 3 && normalized.length < 14) {
    return false;
  }

  if (hasHighEchoOverlap(normalized, spokenText)) {
    return false;
  }

  return true;
}

function generateDeviceId() {
  if (window.crypto?.randomUUID) {
    return window.crypto.randomUUID();
  }

  const bytes = new Uint8Array(16);
  if (window.crypto?.getRandomValues) {
    window.crypto.getRandomValues(bytes);
  } else {
    for (let index = 0; index < bytes.length; index += 1) {
      bytes[index] = Math.floor(Math.random() * 256);
    }
  }

  bytes[6] = (bytes[6] & 0x0f) | 0x40;
  bytes[8] = (bytes[8] & 0x3f) | 0x80;

  const hex = Array.from(bytes, byte => byte.toString(16).padStart(2, "0")).join("");
  return `${hex.slice(0, 8)}-${hex.slice(8, 12)}-${hex.slice(12, 16)}-${hex.slice(16, 20)}-${hex.slice(20)}`;
}

function loadDeviceId() {
  const uuidPattern = /^[0-9a-f]{8}-[0-9a-f]{4}-[1-5][0-9a-f]{3}-[89ab][0-9a-f]{3}-[0-9a-f]{12}$/i;

  try {
    const saved = window.localStorage.getItem(DEVICE_ID_KEY);
    if (saved && uuidPattern.test(saved)) {
      return saved.toLowerCase();
    }

    const nextDeviceId = generateDeviceId();
    window.localStorage.setItem(DEVICE_ID_KEY, nextDeviceId);
    return nextDeviceId;
  } catch {
    return generateDeviceId();
  }
}

function loadAnswerLength() {
  try {
    const value = window.localStorage.getItem(ANSWER_LENGTH_KEY);
    return answerLengthOptions.includes(value) ? value : "standard";
  } catch {
    return "standard";
  }
}

function loadStoredOption(key, options, fallback) {
  try {
    const value = window.localStorage.getItem(key);
    return options.some(option => option.value === value) ? value : fallback;
  } catch {
    return fallback;
  }
}

function loadResponseFeedback() {
  try {
    const value = JSON.parse(window.localStorage.getItem(RESPONSE_FEEDBACK_KEY) || "{}");
    return value && typeof value === "object" ? value : {};
  } catch {
    return {};
  }
}

function lastMessageIndex(messages, role) {
  for (let index = messages.length - 1; index >= 0; index -= 1) {
    if (messages[index]?.role === role) {
      return index;
    }
  }
  return -1;
}

function profileWithSessionMode(profile, sessionMode) {
  if (!profile) {
    return profile;
  }
  return { ...profile, mode: sessionMode || profile.mode || "profile" };
}

function initialsFor(value) {
  const initials = String(value || "")
    .split(/\s+/)
    .filter(Boolean)
    .slice(0, 2)
    .map(part => part[0])
    .join("")
    .toUpperCase();
  return initials || "FG";
}

function getSpeechRecognitionConstructor() {
  return window.SpeechRecognition || window.webkitSpeechRecognition || null;
}

function voiceFriendlyName(voice) {
  if (!voice) {
    return "Browser default";
  }
  const localLabel = voice.localService ? "system" : "online";
  return `${voice.name} (${voice.lang || "auto"}, ${localLabel})`;
}

function scoreBrowserVoice(voice) {
  const name = String(voice?.name || "").toLowerCase();
  const lang = String(voice?.lang || "").toLowerCase();
  let score = 0;

  if (lang.startsWith("en-us")) score += 120;
  if (lang.startsWith("en-gb")) score += 110;
  if (lang.startsWith("en")) score += 90;
  if (name.includes("natural")) score += 70;
  if (name.includes("neural")) score += 65;
  if (name.includes("premium")) score += 55;
  if (name.includes("online")) score += 40;
  if (name.includes("google")) score += 35;
  if (name.includes("microsoft")) score += 35;
  if (name.includes("apple")) score += 20;
  if (name.includes("david") || name.includes("guy") || name.includes("ryan")) score += 15;
  if (name.includes("robot") || name.includes("compact")) score -= 45;
  if (!voice?.localService) score += 10;
  return score;
}

function pickPreferredBrowserVoice(voices = [], selectedVoiceName = "") {
  const list = Array.from(voices || []);
  const selected = selectedVoiceName
    ? list.find(voice => voice.name === selectedVoiceName)
    : null;

  if (selected) {
    return selected;
  }

  return list
    .filter(voice => String(voice.lang || "").toLowerCase().startsWith("en"))
    .sort((a, b) => scoreBrowserVoice(b) - scoreBrowserVoice(a))[0]
    || list.sort((a, b) => scoreBrowserVoice(b) - scoreBrowserVoice(a))[0]
    || null;
}

const defaultSettings = {
  voiceEnabled: true,
  sentenceVoice: true,
  searchEnabled: true,
  ragEnabled: true,
  voiceName: "",
  voiceSpeed: "normal",
  lastSpokenResponse: "",
  theme: "midnight"
};

function StarterPromptIcon({ label }) {
  if (label === "Research") {
    return <SearchIcon />;
  }
  if (label === "Document") {
    return <AttachIcon />;
  }
  if (label === "Quiz") {
    return <QuizIcon />;
  }
  if (label === "Study") {
    return <BookIcon />;
  }
  return <CodeIcon />;
}

const starterPrompts = [
  {
    label: "Study",
    title: "Explain a topic",
    prompt: "Explain computer networking basics in simple language with examples."
  },
  {
    label: "Research",
    title: "Search the web",
    prompt: "Search the web for the latest useful AI tools for students and summarize with sources."
  },
  {
    label: "Quiz",
    title: "Practice Quiz",
    prompt: "Create quiz questions from a topic so I can practice."
  },
  {
    label: "Document",
    title: "Analyze a file",
    prompt: "I want to upload a file. Tell me what you can analyze from it."
  }
];

const codeStarterPrompts = [
  {
    label: "Write",
    title: "Create a script",
    prompt: "Write a Python script that organizes files in a folder by extension."
  },
  {
    label: "Debug",
    title: "Fix an error",
    prompt: "Help me debug this code. Ask me for the code and exact error first."
  },
  {
    label: "Explain",
    title: "Understand code",
    prompt: "Explain this code in simple terms and point out any improvements."
  },
  {
    label: "Convert",
    title: "Change language",
    prompt: "Convert this Python code to C++ and explain the important differences."
  }
];

const codeExtensions = {
  python: "py",
  py: "py",
  c: "c",
  cpp: "cpp",
  "c++": "cpp",
  javascript: "js",
  js: "js",
  typescript: "ts",
  ts: "ts",
  java: "java",
  html: "html",
  css: "css",
  sql: "sql",
  bash: "sh",
  shell: "sh",
  powershell: "ps1",
  json: "json",
  markdown: "md",
  md: "md"
};

function App() {
  const [apiBase] = useState(DEFAULT_API_BASE);
  const [deviceId] = useState(loadDeviceId);
  const [profileToken, setProfileToken] = useState("");
  const [profile, setProfile] = useState(null);
  const [sessionMode, setSessionMode] = useState("");
  const [profiles, setProfiles] = useState([]);
  const [sidebarCollapsed, setSidebarCollapsed] = useState(false);
  const [sidebarRecentOpen, setSidebarRecentOpen] = useState(false);
  const [authMode, setAuthMode] = useState("login");
  const [profileName, setProfileName] = useState("");
  const [selectedProfileId, setSelectedProfileId] = useState("");
  const [legacyProfileName, setLegacyProfileName] = useState("");
  const [legacyLoginEnabled, setLegacyLoginEnabled] = useState(false);
  const [pin, setPin] = useState("");
  const [authError, setAuthError] = useState("");
  const [onboardingAccount, setOnboardingAccount] = useState(null);
  const [onboardingLoading, setOnboardingLoading] = useState(false);
  const [accountSelectingProfile, setAccountSelectingProfile] = useState(false);
  const [accountIdentity, setAccountIdentity] = useState(null);
  const [accountEmail, setAccountEmail] = useState("");
  const [accountAuthLoading, setAccountAuthLoading] = useState(false);
  const [emailLinkSent, setEmailLinkSent] = useState(false);
  const [bootstrapping, setBootstrapping] = useState(true);
  const [profileLoading, setProfileLoading] = useState(false);

  const [message, setMessage] = useState("");
  const [workspace, setWorkspace] = useState("chat");
  const [workspaceMotionKey, setWorkspaceMotionKey] = useState(0);
  const [chat, setChat] = useState([]);
  const [chats, setChats] = useState([]);
  const [activeChatId, setActiveChatId] = useState(null);
  const [codeChat, setCodeChat] = useState([]);
  const [codeChats, setCodeChats] = useState([]);
  const [activeCodeChatId, setActiveCodeChatId] = useState(null);
  const [loading, setLoading] = useState(false);
  const [processingFile, setProcessingFile] = useState(false);
  const [appError, setAppError] = useState("");
  const [answerLength, setAnswerLength] = useState(loadAnswerLength);
  const [modelMode, setModelMode] = useState(() => loadStoredOption(MODEL_MODE_KEY, modelModeOptions, "smart"));
  const [responseMode, setResponseMode] = useState(() => loadStoredOption(RESPONSE_MODE_KEY, responseModeOptions, "balanced"));
  const [copiedMessageKey, setCopiedMessageKey] = useState("");
  const [responseFeedback, setResponseFeedback] = useState(loadResponseFeedback);
  const [editingTurn, setEditingTurn] = useState(null);
  const [responseSpeaking, setResponseSpeaking] = useState(false);
  const [messageActionMenuKey, setMessageActionMenuKey] = useState("");
  const [sourcesDrawer, setSourcesDrawer] = useState(null);
  const [documentsDrawer, setDocumentsDrawer] = useState(null);

  const [settings, setSettings] = useState(defaultSettings);
  const [health, setHealth] = useState(null);
  const [memory, setMemory] = useState({ name: "", role: "", facts: [] });
  const [memoryDraft, setMemoryDraft] = useState({ name: "", role: "" });
  const [factDraft, setFactDraft] = useState("");
  const [activePanel, setActivePanel] = useState(null);
  const [guestLimits, setGuestLimits] = useState(null);
  const [guestLimitModalOpen, setGuestLimitModalOpen] = useState(false);
  const [actionDialog, setActionDialog] = useState(null);
  const [actionDialogValue, setActionDialogValue] = useState("");
  const [actionDialogBusy, setActionDialogBusy] = useState(false);
  const [deleteProfileOpen, setDeleteProfileOpen] = useState(false);
  const [deleteProfilePin, setDeleteProfilePin] = useState("");
  const [deleteProfileBusy, setDeleteProfileBusy] = useState(false);
  const [deleteProfileError, setDeleteProfileError] = useState("");
  const [pinResetOpen, setPinResetOpen] = useState(false);
  const [pinResetStep, setPinResetStep] = useState("start");
  const [pinResetCode, setPinResetCode] = useState("");
  const [pinResetNewPin, setPinResetNewPin] = useState("");
  const [pinResetConfirmPin, setPinResetConfirmPin] = useState("");
  const [pinResetBusy, setPinResetBusy] = useState(false);
  const [pinResetError, setPinResetError] = useState("");
  const [pinResetInfo, setPinResetInfo] = useState("");
  const [pinResetDevCode, setPinResetDevCode] = useState("");

  const [selectedFile, setSelectedFile] = useState(null);
  const [filePreview, setFilePreview] = useState(null);
  const [selectedCodeFiles, setSelectedCodeFiles] = useState([]);

  const [voiceMode, setVoiceMode] = useState(false);
  const [voiceStatus, setVoiceStatus] = useState(VOICE_STATES.IDLE);
  const [voiceMicOn, setVoiceMicOn] = useState(true);
  const [voiceTranscript, setVoiceTranscript] = useState("");
  const [voiceConfidence, setVoiceConfidence] = useState(null);
  const [voiceError, setVoiceError] = useState("");
  const [voiceSpokenWasSummarized, setVoiceSpokenWasSummarized] = useState(false);
  const [availableVoices, setAvailableVoices] = useState([]);

  const messagesEndRef = useRef(null);
  const composerRef = useRef(null);
  const fileInputRef = useRef(null);
  const mediaRecorderRef = useRef(null);
  const voiceStreamRef = useRef(null);
  const voiceChunksRef = useRef([]);
  const voiceTimerRef = useRef(null);
  const previewUrlRef = useRef(null);
  const chatPreviewUrlsRef = useRef([]);
  const voiceModeRef = useRef(false);
  const voiceMicRef = useRef(true);
  const preferredVoiceRef = useRef(null);
  const recognitionRef = useRef(null);
  const interruptRecognitionRef = useRef(null);
  const voiceRestartTimerRef = useRef(null);
  const lastSpokenResponseRef = useRef("");
  const fullSpeechTextRef = useRef("");
  const currentSpokenTextRef = useRef("");
  const browserRecognitionFallbackRef = useRef(false);
  const voiceSendingRef = useRef(false);
  const voiceManualStopRef = useRef(false);
  const announcedGuestLimitsRef = useRef(new Set());
  const accountExchangeRef = useRef("");
  const activeRequestControllerRef = useRef(null);
  const activeStreamReaderRef = useRef(null);
  const stoppedStreamReaderRef = useRef(null);
  const copiedStateTimerRef = useRef(null);
  const speechRequestRef = useRef(0);

  const isCodeWorkspace = workspace === "code";
  const activeMessages = isCodeWorkspace ? codeChat : chat;
  const activeChats = isCodeWorkspace ? codeChats : chats;
  const activeId = isCodeWorkspace ? activeCodeChatId : activeChatId;
  const activeCodeChatItem = codeChats.find(item => item.id === activeCodeChatId);
  const activeCodeProjectFiles = activeCodeChatItem?.projectFiles || [];

  const releasePreviewUrls = useCallback(() => {
    if (previewUrlRef.current) {
      URL.revokeObjectURL(previewUrlRef.current);
      previewUrlRef.current = null;
    }

    chatPreviewUrlsRef.current.forEach(url => URL.revokeObjectURL(url));
    chatPreviewUrlsRef.current = [];
  }, []);

  const authHeaders = useCallback((tokenOverride) => {
    const token = tokenOverride === null ? "" : (tokenOverride || profileToken);
    return {
      ...(token ? { Authorization: `Bearer ${token}` } : {}),
      "X-FebGuy-Device-ID": deviceId
    };
  }, [deviceId, profileToken]);

  const setWorkspaceMessages = useCallback((targetWorkspace, updater) => {
    if (targetWorkspace === "code") {
      setCodeChat(updater);
    } else {
      setChat(updater);
    }
  }, []);

  const setWorkspaceChats = useCallback((targetWorkspace, updater) => {
    if (targetWorkspace === "code") {
      setCodeChats(updater);
    } else {
      setChats(updater);
    }
  }, []);

  const setWorkspaceActiveId = useCallback((targetWorkspace, value) => {
    if (targetWorkspace === "code") {
      setActiveCodeChatId(value);
    } else {
      setActiveChatId(value);
    }
  }, []);

  const requestJson = useCallback(async (path, options = {}, tokenOverride) => {
    const headers = {
      ...(options.headers || {}),
      ...authHeaders(tokenOverride)
    };

    const res = await fetch(`${apiBase}${path}`, {
      ...options,
      headers
    });

    if (!res.ok) {
      let detail = `Request failed with ${res.status}`;
      try {
        const data = await res.json();
        detail = data.detail || data.error || detail;
      } catch {
        detail = res.statusText || detail;
      }
      throw new Error(detail);
    }

    return res.json();
  }, [apiBase, authHeaders]);

  const loadProfiles = useCallback(async (tokenOverride) => {
    try {
      const data = await requestJson("/profiles", {}, tokenOverride);
      const loadedProfiles = data.profiles || [];
      const canUseLegacyLogin = Boolean(data.legacy_login_enabled);
      setProfiles(loadedProfiles);
      setLegacyLoginEnabled(canUseLegacyLogin);
      setSelectedProfileId(current => current || loadedProfiles[0]?.id || "");
      setAuthMode(loadedProfiles.length || canUseLegacyLogin ? "login" : "create");
    } catch {
      setAuthError("Could not load profiles. Make sure the backend is running.");
    }
  }, [requestJson]);

  const refreshChatsList = useCallback(async (tokenOverride) => {
    const data = await requestJson("/chats", {}, tokenOverride);
    setChats(data.chats || []);
    return data.chats || [];
  }, [requestJson]);

  const refreshCodeChatsList = useCallback(async (tokenOverride) => {
    const data = await requestJson("/code/chats", {}, tokenOverride);
    setCodeChats(data.chats || []);
    return data.chats || [];
  }, [requestJson]);

  const loadMemory = useCallback(async (tokenOverride) => {
    const data = await requestJson("/memory", {}, tokenOverride);
    const nextMemory = data.memory || { name: "", role: "", facts: [] };
    setMemory(nextMemory);
    setMemoryDraft({
      name: nextMemory.name || "",
      role: nextMemory.role || ""
    });
  }, [requestJson]);

  const loadSettings = useCallback(async (tokenOverride) => {
    const data = await requestJson("/settings", {}, tokenOverride);
    setSettings({ ...defaultSettings, ...(data.settings || {}) });
  }, [requestJson]);

  const loadHealth = useCallback(async () => {
    try {
      const data = await requestJson("/health");
      setHealth(data);
    } catch {
      setHealth(null);
    }
  }, [requestJson]);

  const applyGuestLimits = useCallback((data) => {
    if (!data?.guest) {
      setGuestLimits(null);
      setGuestLimitModalOpen(false);
      announcedGuestLimitsRef.current.clear();
      return;
    }

    const exhaustedKeys = Object.entries(data.limits || {})
      .filter(([, limit]) => limit.remaining <= 0)
      .map(([key]) => key);
    const hasNewlyExhaustedLimit = exhaustedKeys.some(
      key => !announcedGuestLimitsRef.current.has(key)
    );
    exhaustedKeys.forEach(key => announcedGuestLimitsRef.current.add(key));
    setGuestLimits(data);

    if (hasNewlyExhaustedLimit) {
      setGuestLimitModalOpen(true);
    }
  }, []);

  const loadGuestLimits = useCallback(async (tokenOverride, isGuest) => {
    if (!isGuest) {
      applyGuestLimits(null);
      return;
    }

    try {
      const data = await requestJson("/guest/limits", {}, tokenOverride);
      applyGuestLimits(data);
    } catch {
      // Usage counters are optional UI; backend enforcement remains authoritative.
    }
  }, [applyGuestLimits, requestJson]);

  const showGuestLimitReached = useCallback(async () => {
    setAppError(GUEST_LIMIT_MESSAGE);
    setGuestLimitModalOpen(true);
    await loadGuestLimits(undefined, true);
  }, [loadGuestLimits]);

  const loadAfterAuth = useCallback(async (tokenOverride, profileOverride, accountOverride = null) => {
    const activeMode = profileOverride?.mode || "profile";
    const retainedAccount = profileOverride?.device_bound ? accountOverride : null;
    const loadedChats = await refreshChatsList(tokenOverride);
    const loadedCodeChats = await refreshCodeChatsList(tokenOverride);
    await loadSettings(tokenOverride);
    await loadMemory(tokenOverride);
    await loadHealth();
    await loadGuestLimits(tokenOverride, activeMode === "guest");

    setProfile(profileOverride);
    setProfileToken(tokenOverride);
    setSessionMode(activeMode);
    setOnboardingAccount(null);
    setAccountSelectingProfile(false);
    setAccountIdentity(retainedAccount);
    setAppError("");
    window.localStorage.setItem(ACTIVE_SESSION_MODE_KEY, activeMode);
    window.localStorage.setItem(
      SESSION_KEY,
      JSON.stringify({
        token: tokenOverride,
        profile: profileOverride,
        mode: activeMode,
        accountIdentity: retainedAccount
      })
    );

    if (loadedChats.length > 0) {
      setActiveChatId(loadedChats[0].id);
      setChat(loadedChats[0].messages || []);
    } else {
      setActiveChatId(null);
      setChat([]);
    }

    if (loadedCodeChats.length > 0) {
      setActiveCodeChatId(loadedCodeChats[0].id);
      setCodeChat(loadedCodeChats[0].messages || []);
    } else {
      setActiveCodeChatId(null);
      setCodeChat([]);
    }
  }, [loadGuestLimits, loadHealth, loadMemory, loadSettings, refreshChatsList, refreshCodeChatsList]);

  const enterAuthenticatedSession = useCallback(async (tokenOverride, profileOverride, accountOverride = null) => {
    if (profileOverride?.mode !== "account") {
      await loadAfterAuth(tokenOverride, profileOverride, accountOverride);
      return;
    }

    const status = await requestJson("/onboarding/status", {}, tokenOverride);
    setProfileToken(tokenOverride);
    setSessionMode("account");
    setProfile(null);
    setAuthError("");
    setAppError("");
    setGuestLimits(null);
    setGuestLimitModalOpen(false);
    setAccountIdentity(profileOverride);
    announcedGuestLimitsRef.current.clear();
    window.localStorage.setItem(ACTIVE_SESSION_MODE_KEY, "account");
    window.localStorage.setItem(
      SESSION_KEY,
      JSON.stringify({ token: tokenOverride, profile: profileOverride, mode: "account" })
    );

    if (status.available && !status.onboarding_completed) {
      setOnboardingAccount({ token: tokenOverride, profile: profileOverride });
      setAccountSelectingProfile(false);
      return;
    }

    setOnboardingAccount(null);
    setAccountSelectingProfile(true);
    await loadProfiles(tokenOverride);
  }, [loadAfterAuth, loadProfiles, requestJson]);

  const exchangeSupabaseAccountSession = useCallback(async (authSession) => {
    const accessToken = authSession?.access_token;
    if (!accessToken) {
      return false;
    }

    if (accountExchangeRef.current === accessToken) {
      return true;
    }

    accountExchangeRef.current = accessToken;
    setAccountAuthLoading(true);
    setAuthError("");

    try {
      const data = await requestJson("/auth/supabase/session", {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ access_token: accessToken })
      });
      window.localStorage.setItem(SKIP_GUEST_AUTO_START_KEY, "true");
      await enterAuthenticatedSession(
        data.token,
        profileWithSessionMode(data.profile, data.session_mode)
      );
      return true;
    } catch (error) {
      accountExchangeRef.current = "";
      setAuthError(formatClientError(error, "Account sign-in could not be completed."));
      return false;
    } finally {
      setAccountAuthLoading(false);
    }
  }, [enterAuthenticatedSession, requestJson]);

  const resumeSupabaseAccountSession = useCallback(async () => {
    if (!supabase) {
      return false;
    }

    const { data, error } = await supabase.auth.getSession();
    if (error) {
      setAuthError("Your account session could not be restored. Please sign in again.");
      return false;
    }

    if (!data.session) {
      return false;
    }

    return exchangeSupabaseAccountSession(data.session);
  }, [exchangeSupabaseAccountSession]);

  const startGuestSession = useCallback(async () => {
    const data = await requestJson("/guest/start", { method: "POST" });
    await enterAuthenticatedSession(
      data.token,
      profileWithSessionMode(data.profile, data.session_mode)
    );
    setAuthError("");
  }, [enterAuthenticatedSession, requestJson]);

  const bootstrap = useCallback(async () => {
    const savedSession = window.localStorage.getItem(SESSION_KEY);
    if (savedSession) {
      try {
        const parsed = JSON.parse(savedSession);
        if (parsed.token) {
          const me = await requestJson("/me", {}, parsed.token);
          await enterAuthenticatedSession(
            parsed.token,
            profileWithSessionMode(me.profile, me.session_mode || parsed.mode),
            parsed.accountIdentity || null
          );
          return;
        }
      } catch {
        window.localStorage.removeItem(SESSION_KEY);
        window.localStorage.removeItem(ACTIVE_SESSION_MODE_KEY);
      }
    }

    if (await resumeSupabaseAccountSession()) {
      return;
    }

    if (window.localStorage.getItem(SKIP_GUEST_AUTO_START_KEY) === "true") {
      return;
    }

    try {
      await startGuestSession();
    } catch (error) {
      setAuthError(formatClientError(error, "Could not start guest mode. Make sure the backend is running."));
    }
  }, [enterAuthenticatedSession, requestJson, resumeSupabaseAccountSession, startGuestSession]);

  useEffect(() => {
    const timer = window.setTimeout(() => {
      bootstrap().finally(() => setBootstrapping(false));
    }, 0);

    return () => window.clearTimeout(timer);
  }, [bootstrap]);

  useEffect(() => {
    if (!supabase) {
      return undefined;
    }

    const { data: { subscription } } = supabase.auth.onAuthStateChange((event, session) => {
      const hasStoredWorkspaceSession = Boolean(window.localStorage.getItem(SESSION_KEY));
      const shouldExchange = event === "SIGNED_IN"
        || (event === "INITIAL_SESSION" && !hasStoredWorkspaceSession);
      if (shouldExchange && session) {
        window.setTimeout(() => {
          exchangeSupabaseAccountSession(session);
        }, 0);
      }
    });

    return () => subscription.unsubscribe();
  }, [exchangeSupabaseAccountSession]);

  useEffect(() => {
    if ("speechSynthesis" in window) {
      const speechSynthesis = window.speechSynthesis;
      const refreshPreferredVoice = () => {
        const voices = speechSynthesis.getVoices();
        setAvailableVoices(voices);
        preferredVoiceRef.current = pickPreferredBrowserVoice(voices, settings.voiceName);
      };
      refreshPreferredVoice();
      speechSynthesis.addEventListener("voiceschanged", refreshPreferredVoice);

      return () => {
        speechSynthesis.removeEventListener("voiceschanged", refreshPreferredVoice);
      };
    }

    return undefined;
  }, [settings.voiceName]);

  useEffect(() => releasePreviewUrls, [releasePreviewUrls]);

  useEffect(() => {
    lastSpokenResponseRef.current = settings.lastSpokenResponse || "";
  }, [settings.lastSpokenResponse]);

  useEffect(() => {
    voiceModeRef.current = voiceMode;
  }, [voiceMode]);

  useEffect(() => {
    voiceMicRef.current = voiceMicOn;
  }, [voiceMicOn]);

  useEffect(() => {
    if (!activeMessages.length && !loading && !processingFile) {
      return;
    }
    messagesEndRef.current?.scrollIntoView({ behavior: "smooth" });
  }, [activeMessages, workspace, loading, processingFile]);

  const createProfile = async (event) => {
    event.preventDefault();
    setAuthError("");
    setProfileLoading(true);

    try {
      const data = await requestJson("/profiles", {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ name: profileName, pin })
      });

      setPin("");
      setProfileName("");
      await loadProfiles();
      await enterAuthenticatedSession(
        data.token,
        profileWithSessionMode(data.profile, data.session_mode),
        accountIdentity
      );
    } catch (error) {
      setAuthError(error.message || "Could not create profile.");
    } finally {
      setProfileLoading(false);
    }
  };

  const loginProfile = async (event) => {
    event.preventDefault();
    setAuthError("");
    setProfileLoading(true);

    try {
      const data = await requestJson("/profiles/login", {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({
          profile_id: legacyLoginEnabled ? null : selectedProfileId,
          profile_name: legacyLoginEnabled ? legacyProfileName : null,
          pin
        })
      });

      setPin("");
      setLegacyProfileName("");
      await enterAuthenticatedSession(
        data.token,
        profileWithSessionMode(data.profile, data.session_mode),
        accountIdentity
      );
    } catch (error) {
      setAuthError(error.message || "Could not log in.");
    } finally {
      setProfileLoading(false);
    }
  };

  const logoutProfile = async () => {
    if (sessionMode === "guest") {
      window.localStorage.setItem(SKIP_GUEST_AUTO_START_KEY, "true");
    }

    try {
      await requestJson("/profiles/logout", { method: "POST" });
    } catch {
      // Local logout should still clear the browser state.
    }
    if (supabase && (sessionMode === "account" || profile?.device_bound)) {
      try {
        await supabase.auth.signOut();
      } catch {
        // The local and backend session should still be cleared if sign-out is offline.
      }
      accountExchangeRef.current = "";
    }

    window.localStorage.removeItem(SESSION_KEY);
    window.localStorage.removeItem(ACTIVE_SESSION_MODE_KEY);
    setProfileToken("");
    setProfile(null);
    setSessionMode("");
    setChats([]);
    setChat([]);
    setActiveChatId(null);
    setCodeChats([]);
    setCodeChat([]);
    setActiveCodeChatId(null);
    setWorkspace("chat");
    setActivePanel(null);
    setGuestLimits(null);
    setGuestLimitModalOpen(false);
    setOnboardingAccount(null);
    setAccountSelectingProfile(false);
    setAccountIdentity(null);
    announcedGuestLimitsRef.current.clear();
    setPin("");
    setProfiles([]);
    setLegacyLoginEnabled(false);
    setAuthMode("login");
  };

  const openAccountSignIn = async () => {
    setGuestLimitModalOpen(false);
    setAuthError("");
    if (sessionMode === "guest") {
      await logoutProfile();
      return;
    }
    setAccountSelectingProfile(false);
  };

  const switchProfile = async () => {
    if (!profile?.device_bound || profileLoading) {
      return;
    }
    setProfileLoading(true);
    setAuthError("");
    setActivePanel(null);
    try {
      await loadProfiles(profileToken);
      setAccountSelectingProfile(true);
      setPin("");
    } catch (error) {
      setAppError(formatClientError(error, "Could not load your profiles on this device."));
    } finally {
      setProfileLoading(false);
    }
  };

  const openDeleteProfileModal = () => {
    setDeleteProfilePin("");
    setDeleteProfileError("");
    setDeleteProfileOpen(true);
  };

  const closeDeleteProfileModal = () => {
    if (deleteProfileBusy) {
      return;
    }
    setDeleteProfileOpen(false);
    setDeleteProfilePin("");
    setDeleteProfileError("");
  };

  const deleteCurrentProfile = async (event) => {
    event.preventDefault();
    if (!deleteProfilePin.trim() || deleteProfileBusy) {
      return;
    }

    setDeleteProfileBusy(true);
    setDeleteProfileError("");
    try {
      const data = await requestJson("/profiles/current", {
        method: "DELETE",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ pin: deleteProfilePin })
      });

      setDeleteProfileOpen(false);
      setDeleteProfilePin("");
      setChats([]);
      setChat([]);
      setActiveChatId(null);
      setCodeChats([]);
      setCodeChat([]);
      setActiveCodeChatId(null);
      setWorkspace("chat");
      await enterAuthenticatedSession(
        data.token,
        profileWithSessionMode(data.profile, data.session_mode),
        accountIdentity
      );
      setAuthError("Profile deleted. You can create a new profile if you are below the 3 profile limit.");
    } catch (error) {
      setDeleteProfileError(formatClientError(error, "Could not delete this profile."));
    } finally {
      setDeleteProfileBusy(false);
    }
  };

  const openPinResetModal = () => {
    if (!selectedProfileId) {
      setAuthError("Select a profile first.");
      return;
    }
    setPinResetStep("start");
    setPinResetCode("");
    setPinResetNewPin("");
    setPinResetConfirmPin("");
    setPinResetError("");
    setPinResetInfo("");
    setPinResetDevCode("");
    setPinResetOpen(true);
  };

  const closePinResetModal = () => {
    if (pinResetBusy) {
      return;
    }
    setPinResetOpen(false);
    setPinResetError("");
    setPinResetInfo("");
    setPinResetDevCode("");
  };

  const startPinReset = async () => {
    if (!selectedProfileId || pinResetBusy) {
      return;
    }
    setPinResetBusy(true);
    setPinResetError("");
    setPinResetInfo("");
    setPinResetDevCode("");
    try {
      const data = await requestJson("/profiles/pin-reset/start", {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ profile_id: selectedProfileId })
      });
      setPinResetInfo(data.message || "Verification code prepared for your signed-in email.");
      setPinResetDevCode(data.dev_code || "");
      setPinResetStep("verify");
    } catch (error) {
      setPinResetError(formatClientError(error, "Could not start PIN reset."));
    } finally {
      setPinResetBusy(false);
    }
  };

  const verifyPinReset = async (event) => {
    event.preventDefault();
    if (!pinResetCode.trim() || pinResetBusy) {
      return;
    }
    setPinResetBusy(true);
    setPinResetError("");
    try {
      await requestJson("/profiles/pin-reset/verify", {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ profile_id: selectedProfileId, code: pinResetCode })
      });
      setPinResetStep("new-pin");
      setPinResetInfo("Code confirmed. Choose a new PIN for this profile.");
    } catch (error) {
      setPinResetError(formatClientError(error, "Verification code could not be confirmed."));
    } finally {
      setPinResetBusy(false);
    }
  };

  const completePinReset = async (event) => {
    event.preventDefault();
    if (pinResetNewPin !== pinResetConfirmPin) {
      setPinResetError("New PIN and confirmation do not match.");
      return;
    }
    if (pinResetNewPin.trim().length < 4) {
      setPinResetError("New PIN must be at least 4 characters.");
      return;
    }
    setPinResetBusy(true);
    setPinResetError("");
    try {
      const data = await requestJson("/profiles/pin-reset/complete", {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({
          profile_id: selectedProfileId,
          code: pinResetCode,
          new_pin: pinResetNewPin
        })
      });
      setPin("");
      setPinResetOpen(false);
      setPinResetCode("");
      setPinResetNewPin("");
      setPinResetConfirmPin("");
      if (data.token && data.profile) {
        await enterAuthenticatedSession(
          data.token,
          profileWithSessionMode(data.profile, data.session_mode),
          accountIdentity
        );
      }
      setAuthError(data.message || "PIN reset successfully. Enter your new PIN to unlock this profile.");
    } catch (error) {
      setPinResetError(formatClientError(error, "Could not reset the profile PIN."));
    } finally {
      setPinResetBusy(false);
    }
  };

  const cancelProfileSwitch = () => {
    setAccountSelectingProfile(false);
    setAuthError("");
    setPin("");
  };

  const closeActionDialog = () => {
    if (actionDialogBusy) {
      return;
    }
    setActionDialog(null);
    setActionDialogValue("");
  };

  const openActionDialog = (dialog) => {
    setActionDialog(dialog);
    setActionDialogValue(dialog.initialValue || "");
  };

  const submitActionDialog = async (event) => {
    event?.preventDefault();
    if (!actionDialog || actionDialogBusy) {
      return;
    }

    const value = actionDialogValue.trim();
    if (actionDialog.kind === "input" && !value) {
      return;
    }

    setActionDialogBusy(true);
    try {
      await actionDialog.onConfirm(value);
      setActionDialog(null);
      setActionDialogValue("");
    } catch (error) {
      setAppError(formatClientError(error, "Could not complete this action."));
    } finally {
      setActionDialogBusy(false);
    }
  };

  const confirmAccountLogout = () => {
    openActionDialog({
      tone: "danger",
      title: "Log out of FebGuy AI?",
      description: "This account session will close on this browser. You can still continue in Guest Mode.",
      confirmLabel: "Logout",
      onConfirm: logoutProfile
    });
  };

  useEffect(() => {
    if (!actionDialog) {
      return undefined;
    }

    const closeOnEscape = (event) => {
      if (event.key === "Escape" && !actionDialogBusy) {
        setActionDialog(null);
        setActionDialogValue("");
      }
    };
    window.addEventListener("keydown", closeOnEscape);
    return () => window.removeEventListener("keydown", closeOnEscape);
  }, [actionDialog, actionDialogBusy]);

  const continueAsGuest = async () => {
    setAuthError("");
    window.localStorage.removeItem(SKIP_GUEST_AUTO_START_KEY);

    try {
      if (sessionMode === "account" && profileToken) {
        try {
          await requestJson("/profiles/logout", { method: "POST" });
        } catch {
          // Moving to guest mode should continue even if the account token expired.
        }
        window.localStorage.removeItem(SESSION_KEY);
        window.localStorage.removeItem(ACTIVE_SESSION_MODE_KEY);
        setProfileToken("");
        setSessionMode("");
      }
      if (supabase && accountIdentity) {
        await supabase.auth.signOut();
        accountExchangeRef.current = "";
        setAccountIdentity(null);
      }
      await startGuestSession();
    } catch (error) {
      setAuthError(formatClientError(error, "Could not start guest mode. Make sure the backend is running."));
    }
  };

  const signInWithGoogle = async () => {
    setAuthError("");
    setEmailLinkSent(false);

    if (!supabaseConfigured || !supabase) {
      setAuthError("Account sign-in is not configured yet. Add the public Supabase settings and restart the frontend.");
      return;
    }

    setAccountAuthLoading(true);
    window.localStorage.setItem(SKIP_GUEST_AUTO_START_KEY, "true");

    const { error } = await supabase.auth.signInWithOAuth({
      provider: "google",
      options: { redirectTo: window.location.origin }
    });

    if (error) {
      setAccountAuthLoading(false);
      setAuthError(error.message || "Google sign-in could not be started.");
    }
  };

  const signInWithEmail = async (event) => {
    event.preventDefault();
    setAuthError("");
    setEmailLinkSent(false);

    if (!supabaseConfigured || !supabase) {
      setAuthError("Account sign-in is not configured yet. Add the public Supabase settings and restart the frontend.");
      return;
    }

    const email = accountEmail.trim();
    if (!email) {
      setAuthError("Enter your email address to continue.");
      return;
    }

    setAccountAuthLoading(true);
    window.localStorage.setItem(SKIP_GUEST_AUTO_START_KEY, "true");
    const { error } = await supabase.auth.signInWithOtp({
      email,
      options: {
        emailRedirectTo: window.location.origin,
        shouldCreateUser: true
      }
    });
    setAccountAuthLoading(false);

    if (error) {
      setAuthError(error.message || "Email sign-in link could not be sent.");
      return;
    }

    setEmailLinkSent(true);
  };

  const completeOnboarding = async () => {
    if (!onboardingAccount?.token || onboardingLoading) {
      return;
    }

    setOnboardingLoading(true);
    setAuthError("");

    try {
      await requestJson(
        "/onboarding/complete",
        { method: "POST" },
        onboardingAccount.token
      );
      setOnboardingAccount(null);
      setAccountSelectingProfile(true);
      await loadProfiles(onboardingAccount.token);
    } catch (error) {
      setAuthError(formatClientError(error, "Could not complete setup. Please try again."));
    } finally {
      setOnboardingLoading(false);
    }
  };

  const createChatOnBackend = async (targetWorkspace = workspace) => {
    const isCode = targetWorkspace === "code";
    const newChat = await requestJson(isCode ? "/code/chats/new" : "/chats/new", {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ title: isCode ? "New Code Chat" : "New Chat" })
    });

    setWorkspaceChats(targetWorkspace, prev => [newChat, ...prev]);
    return newChat;
  };

  const createNewChat = async () => {
    try {
      const targetWorkspace = workspace;
      const newChat = await createChatOnBackend(targetWorkspace);
      setWorkspaceActiveId(targetWorkspace, newChat.id);
      setWorkspaceMessages(targetWorkspace, []);
      setMessage("");
      setEditingTurn(null);
      setMessageActionMenuKey("");
      setSourcesDrawer(null);
      setDocumentsDrawer(null);
      setAppError("");
      resetFileInput();
    } catch (error) {
      setAppError(error.message || "Could not create a new chat.");
    }
  };

  const openChat = (chatItem) => {
    setWorkspaceActiveId(workspace, chatItem.id);
    setWorkspaceMessages(workspace, chatItem.messages || []);
    setMessage("");
    setEditingTurn(null);
    setMessageActionMenuKey("");
    setSourcesDrawer(null);
    setDocumentsDrawer(null);
    setAppError("");
    resetFileInput();
  };

  const switchWorkspace = (nextWorkspace) => {
    if (nextWorkspace === workspace) {
      return;
    }

    if (nextWorkspace === "code") {
      setVoiceMode(false);
      setVoiceMicOn(false);
      setVoiceStatus(VOICE_STATES.IDLE);
      stopVoiceRecorder();
      stopResponseAudio();
    }

    setWorkspace(nextWorkspace);
    setSidebarRecentOpen(false);
    setWorkspaceMotionKey(key => key + 1);
    setMessage("");
    setEditingTurn(null);
    setMessageActionMenuKey("");
    setSourcesDrawer(null);
    setDocumentsDrawer(null);
    setAppError("");
    resetFileInput();
  };

  const updateChatAction = async (chatId, payload) => {
    const targetWorkspace = workspace;
    const data = await requestJson(`${targetWorkspace === "code" ? "/code" : ""}/chats/${chatId}`, {
      method: "PATCH",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify(payload)
    });
    setWorkspaceChats(targetWorkspace, data.chats || []);

    const currentActiveId = targetWorkspace === "code" ? activeCodeChatId : activeChatId;
    if (data.chat?.id === currentActiveId) {
      setWorkspaceMessages(targetWorkspace, data.chat.messages || []);
    }
  };

  const renameChat = (chatItem) => {
    openActionDialog({
      kind: "input",
      title: "Rename chat",
      description: "Choose a clear title so this conversation is easy to find later.",
      inputLabel: "Chat title",
      initialValue: chatItem.title || "New Chat",
      confirmLabel: "Save name",
      onConfirm: async (title) => {
        try {
          await updateChatAction(chatItem.id, { title });
        } catch {
          setAppError("Could not rename chat.");
        }
      }
    });
  };

  const togglePinChat = async (chatItem) => {
    try {
      await updateChatAction(chatItem.id, { pinned: !chatItem.pinned });
    } catch {
      setAppError("Could not pin this chat.");
    }
  };

  const deleteChat = (chatItem) => {
    openActionDialog({
      tone: "danger",
      title: "Delete this chat?",
      description: `"${chatItem.title || "New Chat"}" will be removed from this workspace.`,
      confirmLabel: "Delete chat",
      onConfirm: async () => {
        try {
          const targetWorkspace = workspace;
          const data = await requestJson(`${targetWorkspace === "code" ? "/code" : ""}/chats/${chatItem.id}`, { method: "DELETE" });
          const remaining = data.chats || [];
          setWorkspaceChats(targetWorkspace, remaining);

          const currentActiveId = targetWorkspace === "code" ? activeCodeChatId : activeChatId;
          if (currentActiveId === chatItem.id) {
            setWorkspaceActiveId(targetWorkspace, remaining[0]?.id || null);
            setWorkspaceMessages(targetWorkspace, remaining[0]?.messages || []);
          }
        } catch {
          setAppError("Could not delete chat.");
        }
      }
    });
  };

  const exportChat = async (chatItem) => {
    try {
      const targetWorkspace = workspace;
      const res = await fetch(`${apiBase}${targetWorkspace === "code" ? "/code" : ""}/chats/${chatItem.id}/export`, {
        headers: authHeaders()
      });

      if (!res.ok) {
        throw new Error("Export failed");
      }

      const blob = await res.blob();
      const url = URL.createObjectURL(blob);
      const link = document.createElement("a");
      link.href = url;
      link.download = `${(chatItem.title || (targetWorkspace === "code" ? "code_chat" : "chat")).replace(/[^a-z0-9_-]+/gi, "_")}.txt`;
      document.body.appendChild(link);
      link.click();
      link.remove();
      URL.revokeObjectURL(url);
    } catch {
      setAppError("Could not export chat.");
    }
  };

  const downloadOwnedFile = async (message) => {
    try {
      const res = await fetch(message.downloadUrl, {
        headers: authHeaders()
      });

      if (!res.ok) {
        let detail = "This file is not available in your workspace.";
        try {
          const data = await res.json();
          detail = data.detail || data.error || detail;
        } catch {
          // Keep the user-facing fallback when an error body is not JSON.
        }
        throw new Error(detail);
      }

      const blob = await res.blob();
      const url = URL.createObjectURL(blob);
      const link = document.createElement("a");
      link.href = url;
      link.download = message.fileName || "febguy-download";
      document.body.appendChild(link);
      link.click();
      link.remove();
      URL.revokeObjectURL(url);
    } catch (error) {
      setAppError(error.message || "Could not download this file.");
    }
  };

  const getBestBrowserVoice = () => {
    if (!("speechSynthesis" in window)) {
      return null;
    }

    const voices = window.speechSynthesis.getVoices();
    if (voices.length) {
      setAvailableVoices(voices);
    }

    const selected = pickPreferredBrowserVoice(voices, settings.voiceName);
    if (selected) {
      preferredVoiceRef.current = selected;
    }
    return selected || preferredVoiceRef.current;
  };

  const waitForPreferredVoice = () => {
    const current = getBestBrowserVoice();
    if (current || !("speechSynthesis" in window)) {
      return Promise.resolve(current);
    }

    return new Promise(resolve => {
      const speechSynthesis = window.speechSynthesis;
      let timer = null;
      const finish = () => {
        if (timer) {
          window.clearTimeout(timer);
        }
        speechSynthesis.removeEventListener("voiceschanged", finish);
        resolve(getBestBrowserVoice());
      };
      timer = window.setTimeout(finish, 500);
      speechSynthesis.addEventListener("voiceschanged", finish);
      speechSynthesis.getVoices();
    });
  };

  const cleanTextForSpeech = (text) => {
    const withoutCode = stripThinkingBlocks(text)
      .replace(/```[\s\S]*?```/g, " I included a code block in the chat. ")
      .replace(/`([^`]+)`/g, "$1");
    return withoutCode
      .split("\n")
      .filter(line => {
        const trimmed = line.trim();
        if (!trimmed) return true;
        if (/^https?:\/\//i.test(trimmed)) return false;
        if (/^(source|sources|citation|citations|references?)\s*:/i.test(trimmed)) return false;
        if (/^\|.*\|$/.test(trimmed)) return false;
        if (/^[{}[\],:"\s-]+$/.test(trimmed)) return false;
        return true;
      })
      .join(" ")
      .replace(/\[(.*?)\]\((?:https?:\/\/|mailto:).*?\)/g, "$1")
      .replace(/https?:\/\/\S+/gi, "")
      .replace(/\[\d+\]|\(\d+\)/g, "")
      .replace(/[#*_>`~|]/g, "")
      .replace(/\s+([,.!?;:])/g, "$1")
      .replace(/\s+/g, " ")
      .trim();
  };

  const prepareSpokenText = (text, { forceFull = false } = {}) => {
    const cleaned = cleanTextForSpeech(text);
    if (!cleaned) {
      return { spokenText: "", fullText: "", summarized: false };
    }

    const wordCount = cleaned.split(/\s+/).filter(Boolean).length;
    if (forceFull || cleaned.length < 900 && wordCount < 150) {
      return { spokenText: cleaned, fullText: cleaned, summarized: false };
    }

    const sentences = cleaned
      .split(/(?<=[.!?])\s+/)
      .filter(Boolean)
      .slice(0, 3)
      .join(" ");
    const summary = sentences || cleaned.slice(0, 520);
    return {
      spokenText: `I have a longer answer in the chat. Quick summary: ${summary}`,
      fullText: cleaned,
      summarized: true
    };
  };

  const stopInterruptRecognition = () => {
    const recognizer = interruptRecognitionRef.current;
    interruptRecognitionRef.current = null;
    if (recognizer) {
      try {
        recognizer.onresult = null;
        recognizer.onerror = null;
        recognizer.onend = null;
        recognizer.stop();
      } catch {
        // Browser speech recognition can throw if it already stopped.
      }
    }
  };

  const startInterruptRecognition = () => {
    const Recognition = getSpeechRecognitionConstructor();
    if (!voiceModeRef.current || !voiceMicRef.current || !Recognition || browserRecognitionFallbackRef.current) {
      return;
    }

    stopInterruptRecognition();
    window.setTimeout(() => {
      if (!voiceModeRef.current || !voiceMicRef.current || !window.speechSynthesis?.speaking) {
        return;
      }

      let interrupted = false;
      const recognizer = new Recognition();
      interruptRecognitionRef.current = recognizer;
      recognizer.lang = "en-US";
      recognizer.continuous = false;
      recognizer.interimResults = true;
      recognizer.maxAlternatives = 1;
      recognizer.onresult = (event) => {
        let captured = "";
        let confidence = null;
        for (let index = event.resultIndex; index < event.results.length; index += 1) {
          const alternative = event.results[index]?.[0];
          captured += alternative?.transcript || "";
          if (typeof alternative?.confidence === "number" && alternative.confidence > 0) {
            confidence = alternative.confidence;
          }
        }
        if (
          !interrupted
          && isMeaningfulVoiceInterrupt(captured, confidence, currentSpokenTextRef.current)
        ) {
          interrupted = true;
          stopResponseAudio();
          setVoiceTranscript(captured.trim());
          setVoiceError("");
          setVoiceStatus(VOICE_STATES.LISTENING);
          window.clearTimeout(voiceRestartTimerRef.current);
          voiceRestartTimerRef.current = window.setTimeout(() => {
            voiceRestartTimerRef.current = null;
            if (voiceModeRef.current && voiceMicRef.current && !voiceSendingRef.current) {
              startVoiceListening();
            }
          }, 180);
        }
      };
      recognizer.onerror = () => {};
      recognizer.onend = () => {
        if (interruptRecognitionRef.current === recognizer) {
          interruptRecognitionRef.current = null;
        }
      };

      try {
        recognizer.start();
      } catch {
        interruptRecognitionRef.current = null;
      }
    }, 800);
  };

  const createUtterance = (text, resolve, voiceOverride = null) => {
    const speech = new SpeechSynthesisUtterance(text);
    const bestVoice = voiceOverride || getBestBrowserVoice();

    if (bestVoice) {
      speech.voice = bestVoice;
      speech.lang = bestVoice.lang || "en-US";
    } else {
      speech.lang = "en-US";
    }

    speech.rate = voiceSpeedRates[settings.voiceSpeed] || voiceSpeedRates.normal;
    speech.pitch = 0.98;
    speech.volume = 1;
    const finish = () => {
      stopInterruptRecognition();
      if (!window.speechSynthesis.speaking && !window.speechSynthesis.pending) {
        setResponseSpeaking(false);
        if (currentSpokenTextRef.current === text) {
          currentSpokenTextRef.current = "";
        }
      }
      if (resolve) {
        resolve();
      }
    };
    speech.onend = finish;
    speech.onerror = finish;
    return speech;
  };

  const speakQueued = (text) => {
    if (!settings.voiceEnabled || !("speechSynthesis" in window)) {
      return;
    }

    const { spokenText } = prepareSpokenText(text, { forceFull: true });
    if (!spokenText) {
      return;
    }

    setResponseSpeaking(true);
    window.speechSynthesis.speak(createUtterance(spokenText));
  };

  const speakText = async (text, options = {}) => {
    if (!settings.voiceEnabled || !("speechSynthesis" in window)) {
      return;
    }

    const prepared = prepareSpokenText(text, options);
    const spokenText = prepared.spokenText;
    if (!spokenText) {
      return;
    }

    const rememberedSpokenText = spokenText.slice(0, 2800);
    lastSpokenResponseRef.current = rememberedSpokenText;
    fullSpeechTextRef.current = prepared.fullText;
    setVoiceSpokenWasSummarized(prepared.summarized);
    if (settings.lastSpokenResponse !== rememberedSpokenText) {
      updateSettings({ lastSpokenResponse: rememberedSpokenText }).catch(() => {});
    }

    const speechRequest = speechRequestRef.current + 1;
    speechRequestRef.current = speechRequest;
    const preferredVoice = await waitForPreferredVoice();
    if (speechRequest !== speechRequestRef.current) {
      return;
    }

    return new Promise(resolve => {
      window.speechSynthesis.cancel();
      setResponseSpeaking(true);
      if (voiceModeRef.current) {
        setVoiceStatus(VOICE_STATES.SPEAKING);
      }
      currentSpokenTextRef.current = spokenText;
      window.speechSynthesis.speak(createUtterance(spokenText, resolve, preferredVoice));
      startInterruptRecognition();
    });
  };

  const stopResponseAudio = () => {
    speechRequestRef.current += 1;
    stopInterruptRecognition();
    if ("speechSynthesis" in window) {
      window.speechSynthesis.pause();
      window.speechSynthesis.cancel();
      window.setTimeout(() => {
        try {
          window.speechSynthesis.cancel();
        } catch {
          // Some browsers need a second cancel tick after pausing.
        }
      }, 50);
    }
    currentSpokenTextRef.current = "";
    setResponseSpeaking(false);
  };

  const queueCompletedSentences = (text, spokenUpTo) => {
    if (!settings.voiceEnabled || !settings.sentenceVoice) {
      return spokenUpTo;
    }

    const remaining = text.slice(spokenUpTo);
    const match = remaining.match(/^([\s\S]*?[.!?])(\s|$)/);
    if (!match) {
      return spokenUpTo;
    }

    const sentence = match[1].trim();
    if (sentence) {
      speakQueued(sentence);
    }

    return queueCompletedSentences(text, spokenUpTo + match[0].length);
  };

  const setPreviewUrl = (url) => {
    if (previewUrlRef.current) {
      URL.revokeObjectURL(previewUrlRef.current);
    }

    previewUrlRef.current = url;
    setFilePreview(url);
  };

  const handleFileSelect = (event) => {
    const files = Array.from(event.target.files || []);

    if (!files.length) {
      return;
    }

    if (isCodeWorkspace) {
      setSelectedCodeFiles(files.slice(0, MAX_CODE_FILES_PER_TURN));
      setSelectedFile(null);
      setPreviewUrl(null);
      setEditingTurn(null);
      setAppError("");
      return;
    }

    const file = files[0];
    setSelectedFile(file);
    setSelectedCodeFiles([]);
    setEditingTurn(null);
    setAppError("");

    if (file.type.startsWith("image/")) {
      setPreviewUrl(URL.createObjectURL(file));
    } else {
      setPreviewUrl(null);
    }
  };

  const resetFileInput = () => {
    setSelectedFile(null);
    setSelectedCodeFiles([]);
    setPreviewUrl(null);

    if (fileInputRef.current) {
      fileInputRef.current.value = "";
    }
  };

  const updateChatsFromPayload = (payload, targetWorkspace = workspace) => {
    if (payload.chats) {
      setWorkspaceChats(targetWorkspace, payload.chats);
      return;
    }

    if (payload.chat) {
      setWorkspaceChats(targetWorkspace, prev => {
        const withoutActive = prev.filter(item => item.id !== payload.chat.id);
        return [payload.chat, ...withoutActive];
      });
    }
  };

  const appendAiMessage = (messagePayload, targetWorkspace = workspace) => {
    const payload = typeof messagePayload === "string"
      ? { role: "ai", text: messagePayload }
      : { role: "ai", ...messagePayload };
    setWorkspaceMessages(targetWorkspace, prev => [...prev, payload]);
  };

  const updateLastAiMessage = (payload, targetWorkspace = workspace) => {
    setWorkspaceMessages(targetWorkspace, prev => {
      const updated = [...prev];
      updated[updated.length - 1] = {
        ...updated[updated.length - 1],
        ...payload
      };
      return updated;
    });
  };

  const parseMetaFromText = (rawText) => {
    const start = rawText.indexOf(META_PREFIX);
    if (start === -1) {
      return { displayText: rawText, meta: null, rawText };
    }

    const metaStart = start + META_PREFIX.length;
    const end = rawText.indexOf(META_SUFFIX, metaStart);
    if (end === -1) {
      return { displayText: rawText.slice(0, start), meta: null, rawText };
    }

    try {
      const meta = JSON.parse(rawText.slice(metaStart, end));
      return {
        displayText: rawText.slice(0, start),
        meta,
        rawText: rawText.slice(0, start)
      };
    } catch {
      return { displayText: rawText.slice(0, start), meta: null, rawText };
    }
  };

  const handleJsonResponse = async (payload, isVoice, targetWorkspace = workspace) => {
    setLoading(false);
    setProcessingFile(false);

    if (payload.type === "file") {
      appendAiMessage({
        text: payload.message || "File converted successfully.",
        fileResult: true,
        fileName: payload.file_name,
        downloadUrl: payload.download_url
      }, targetWorkspace);
      await refreshChatsList();
      return "";
    }

    const aiText = payload.response || "Done.";
    appendAiMessage({
      text: aiText,
      citations: payload.citations || [],
      documentHits: payload.documentHits || [],
      suggestions: payload.suggestions || [],
      projectFiles: payload.projectFiles || [],
      generatedFiles: payload.generatedFiles || []
    }, targetWorkspace);
    updateChatsFromPayload(payload, targetWorkspace);

    const canSpeakResponse = targetWorkspace !== "code";

    if (isVoice && canSpeakResponse) {
      setVoiceStatus(VOICE_STATES.SPEAKING);
    }

    if (canSpeakResponse) {
      await speakText(aiText);
    }
    return aiText;
  };

  const handleStreamingResponse = async (res, isVoice, targetWorkspace = workspace) => {
    const reader = res.body?.getReader();

    if (!reader) {
      throw new Error("Streaming response was empty.");
    }
    activeStreamReaderRef.current = reader;

    const canSpeakResponse = targetWorkspace !== "code";

    if ((canSpeakResponse && settings.voiceEnabled && settings.sentenceVoice && !isVoice) || !canSpeakResponse) {
      stopResponseAudio();
    }

    const decoder = new TextDecoder();

    const readNextChunk = async (state) => {
      const { done, value } = await reader.read();

      if (done) {
        return state;
      }

      const rawText = `${state.rawText}${decoder.decode(value, { stream: true })}`;
      const parsed = parseMetaFromText(rawText);
      const displayText = parsed.displayText;

      if (!state.hasStarted) {
        setLoading(false);
        setProcessingFile(false);
        appendAiMessage({ text: "", citations: [], suggestions: [] }, targetWorkspace);
      }

      const spokenUpTo = canSpeakResponse && !isVoice
        ? queueCompletedSentences(displayText, state.spokenUpTo)
        : state.spokenUpTo;

      updateLastAiMessage({
        text: displayText,
        citations: parsed.meta?.citations || [],
        documentHits: parsed.meta?.documentHits || [],
        suggestions: parsed.meta?.suggestions || [],
        codeTask: parsed.meta?.codeTask,
        codeLanguage: parsed.meta?.codeLanguage,
        projectFiles: parsed.meta?.projectFiles || [],
        generatedFiles: parsed.meta?.generatedFiles || []
      }, targetWorkspace);

      return readNextChunk({
        rawText: parsed.rawText,
        displayText,
        meta: parsed.meta || state.meta,
        hasStarted: true,
        spokenUpTo
      });
    };

    let finalState;
    try {
      finalState = await readNextChunk({
        rawText: "",
        displayText: "",
        meta: null,
        hasStarted: false,
        spokenUpTo: 0
      });
    } finally {
      if (activeStreamReaderRef.current === reader) {
        activeStreamReaderRef.current = null;
      }
    }

    if (stoppedStreamReaderRef.current === reader) {
      stoppedStreamReaderRef.current = null;
      return finalState.displayText;
    }

    if (!finalState.hasStarted) {
      setLoading(false);
      setProcessingFile(false);
      appendAiMessage("I did not receive a response from the model.", targetWorkspace);
      return "";
    }

    if (isVoice && canSpeakResponse) {
      setVoiceStatus(VOICE_STATES.SPEAKING);
    }

    if (canSpeakResponse) {
      if (settings.voiceEnabled && settings.sentenceVoice && !isVoice) {
        const remainder = finalState.displayText.slice(finalState.spokenUpTo).trim();
        if (remainder) {
          speakQueued(remainder);
        }
      } else {
        await speakText(finalState.displayText);
      }
    }

    if (targetWorkspace === "code") {
      await refreshCodeChatsList();
    } else {
      await refreshChatsList();
    }
    return finalState.displayText;
  };

  const finishVoiceTurn = () => {
    if (voiceManualStopRef.current) {
      voiceManualStopRef.current = false;
      if (voiceModeRef.current) {
        setVoiceStatus(VOICE_STATES.IDLE);
      }
      return;
    }

    if (voiceModeRef.current && voiceMicRef.current) {
      if (voiceRestartTimerRef.current) {
        window.clearTimeout(voiceRestartTimerRef.current);
      }
      voiceRestartTimerRef.current = window.setTimeout(() => {
        voiceRestartTimerRef.current = null;
        startVoiceListening();
      }, 160);
    } else if (voiceModeRef.current) {
      setVoiceStatus(VOICE_STATES.IDLE);
    }
  };

  const sendToBackend = async (
    text,
    fileToSend = null,
    isVoice = false,
    previewUrl = null,
    options = {}
  ) => {
    const targetWorkspace = options.targetWorkspace || workspace;
    const isCode = targetWorkspace === "code";
    const replaceLastTurn = Boolean(options.replaceLastTurn);
    const replaceUserText = Boolean(options.replaceUserText);
    const codeFilesToSend = isCode ? (options.codeFiles || []) : [];
    let currentChatId = isCode ? activeCodeChatId : activeChatId;

    if (!currentChatId) {
      const newChat = await createChatOnBackend(targetWorkspace);
      currentChatId = newChat.id;
      setWorkspaceActiveId(targetWorkspace, currentChatId);
    }

    const userMessage = {
      role: "user",
      text,
      fileName: fileToSend ? fileToSend.name : null,
      fileType: fileToSend ? fileToSend.type : null,
      filePreview: fileToSend && previewUrl ? previewUrl : null,
      codeFiles: codeFilesToSend.map(fileItem => ({
        fileName: fileItem.name,
        sizeBytes: fileItem.size,
        language: fileItem.name.split(".").pop() || "text"
      }))
    };

    if (replaceLastTurn) {
      setWorkspaceMessages(targetWorkspace, prev => {
        const userIndex = lastMessageIndex(prev, "user");
        if (userIndex < 0) {
          return [...prev, userMessage];
        }
        const precedingTurns = prev.slice(0, userIndex + 1);
        if (replaceUserText) {
          precedingTurns[userIndex] = { ...precedingTurns[userIndex], text };
        }
        return precedingTurns;
      });
    } else {
      setWorkspaceMessages(targetWorkspace, prev => [...prev, userMessage]);
    }
    setMessageActionMenuKey("");
    setAppError("");
    stopResponseAudio();

    if (fileToSend || codeFilesToSend.length) {
      setProcessingFile(true);
    } else {
      setLoading(true);
    }

    const formData = new FormData();
    formData.append("chat_id", currentChatId);
    formData.append("message", text);
    formData.append("device_id", deviceId);
    formData.append("answer_length", options.answerLength || answerLength);
    if (!isCode) {
      formData.append("model_mode", options.modelMode || modelMode);
      formData.append("response_mode", options.responseMode || responseMode);
    }
    if (replaceLastTurn) {
      formData.append("replace_last_turn", "true");
    }

    if (fileToSend) {
      formData.append("file", fileToSend);
    }
    if (isCode && codeFilesToSend.length) {
      codeFilesToSend.forEach(fileItem => formData.append("code_files", fileItem));
    }

    const controller = new AbortController();
    activeRequestControllerRef.current = controller;

    try {
      const res = await fetch(`${apiBase}${isCode ? "/code-chat-stream" : "/chat-stream"}`, {
        method: "POST",
        headers: authHeaders(),
        body: formData,
        signal: controller.signal
      });

      if (!res.ok) {
        const detail = await readBackendError(res, `Backend returned ${res.status}`);
        throw new Error(detail);
      }

      const contentType = res.headers.get("content-type") || "";

      if (contentType.includes("application/json")) {
        const payload = await res.json();
        await handleJsonResponse(payload, isVoice, targetWorkspace);
      } else {
        await handleStreamingResponse(res, isVoice, targetWorkspace);
      }

      await loadGuestLimits(undefined, sessionMode === "guest");

      if (isVoice) {
        finishVoiceTurn();
      }
    } finally {
      if (activeRequestControllerRef.current === controller) {
        activeRequestControllerRef.current = null;
      }
      setLoading(false);
      setProcessingFile(false);
    }
  };

  const sendSuggestion = async (text) => {
    if (isBusy || !text) {
      return;
    }

    try {
      await sendToBackend(text, null, false);
    } catch (error) {
      setLoading(false);
      setProcessingFile(false);
      if (error?.name === "AbortError") {
        return;
      }
      await loadGuestLimits(undefined, sessionMode === "guest");
      const errorMessage = formatClientError(error, "Backend Error. Please check FastAPI, internet access, and backend .env API keys.");
      if (isGuestLimitMessage(errorMessage)) {
        await showGuestLimitReached();
        return;
      }
      appendAiMessage(errorMessage);
    }
  };

  const focusComposer = () => {
    composerRef.current?.focus();
    composerRef.current?.scrollIntoView({ behavior: "smooth", block: "nearest" });
  };

  const sendMessage = async () => {
    const hasCodeFiles = isCodeWorkspace && selectedCodeFiles.length > 0;
    if (isBusy || (!message.trim() && !selectedFile && !hasCodeFiles)) {
      return;
    }

    const text = message.trim() || (hasCodeFiles ? "Add these code files to this Code Studio project context." : "Please analyze this file.");
    const fileToSend = selectedFile;
    const previewToKeep = filePreview;
    const codeFilesToSend = hasCodeFiles ? selectedCodeFiles : [];
    const replaceEditedTurn = Boolean(editingTurn && editingTurn.workspace === workspace && !fileToSend);

    if (replaceEditedTurn) {
      removeResponseFeedback(`${workspace}:${activeId || "draft"}:${lastMessageIndex(activeMessages, "ai")}`);
    }

    if (previewToKeep) {
      chatPreviewUrlsRef.current.push(previewToKeep);
      previewUrlRef.current = null;
    }

    setMessage("");
    setEditingTurn(null);
    resetFileInput();

    try {
      await sendToBackend(text, fileToSend, false, previewToKeep, {
        replaceLastTurn: replaceEditedTurn,
        replaceUserText: replaceEditedTurn,
        codeFiles: codeFilesToSend
      });
    } catch (error) {
      setLoading(false);
      setProcessingFile(false);
      if (error?.name === "AbortError") {
        return;
      }
      await loadGuestLimits(undefined, sessionMode === "guest");
      const errorMessage = formatClientError(error, "Backend Error. Please check FastAPI, internet access, and backend .env API keys.");
      if (isGuestLimitMessage(errorMessage)) {
        await showGuestLimitReached();
        return;
      }
      appendAiMessage(errorMessage);
    }
  };

  const releaseVoiceStream = () => {
    if (voiceTimerRef.current) {
      clearTimeout(voiceTimerRef.current);
      voiceTimerRef.current = null;
    }

    if (voiceStreamRef.current) {
      voiceStreamRef.current.getTracks().forEach(track => track.stop());
      voiceStreamRef.current = null;
    }
  };

  const stopVoiceRecorder = () => {
    if (voiceRestartTimerRef.current) {
      window.clearTimeout(voiceRestartTimerRef.current);
      voiceRestartTimerRef.current = null;
    }

    stopInterruptRecognition();

    const recognizer = recognitionRef.current;
    recognitionRef.current = null;
    if (recognizer) {
      try {
        recognizer.onresult = null;
        recognizer.onerror = null;
        recognizer.onend = null;
        recognizer.stop();
      } catch {
        // Recognition may already be stopped by the browser.
      }
    }

    if (voiceTimerRef.current) {
      clearTimeout(voiceTimerRef.current);
      voiceTimerRef.current = null;
    }

    const recorder = mediaRecorderRef.current;
    if (recorder && recorder.state !== "inactive") {
      try {
        recorder.stop();
      } catch {
        releaseVoiceStream();
      }
      return;
    }

    releaseVoiceStream();
  };

  const sendVoiceAudio = async (audioBlob) => {
    if (!audioBlob || audioBlob.size < 512) {
      throw new Error("No audio detected. Please try speaking again.");
    }

    let currentChatId = activeChatId;
    if (!currentChatId) {
      const newChat = await createChatOnBackend("chat");
      currentChatId = newChat.id;
      setWorkspaceActiveId("chat", currentChatId);
    }

    const formData = new FormData();
    formData.append("chat_id", currentChatId);
    formData.append("device_id", deviceId);
    formData.append("answer_length", answerLength);
    formData.append("model_mode", modelMode);
    formData.append("response_mode", responseMode);
    formData.append("audio", audioBlob, "voice.webm");

    setLoading(true);
    setAppError("");
    stopResponseAudio();
    const controller = new AbortController();
    activeRequestControllerRef.current = controller;

    try {
      const res = await fetch(`${apiBase}/voice-chat`, {
        method: "POST",
        headers: authHeaders(),
        body: formData,
        signal: controller.signal
      });

      if (!res.ok) {
        const detail = await readBackendError(res, `Voice request failed with ${res.status}.`);
        throw new Error(detail);
      }

      const payload = await res.json();
      const transcript = (payload.transcript || "").trim();
      const aiText = payload.response || "I heard you, but I could not create a response.";

      if (transcript) {
        setVoiceTranscript(transcript);
        setWorkspaceMessages("chat", prev => [...prev, { role: "user", text: transcript }]);
      }

      appendAiMessage({
        text: aiText,
        citations: payload.citations || [],
        documentHits: payload.documentHits || [],
        suggestions: payload.suggestions || []
      }, "chat");

      updateChatsFromPayload(payload, "chat");
      setLoading(false);
      await refreshChatsList();
      await loadGuestLimits(undefined, sessionMode === "guest");

      if (voiceModeRef.current) {
        setVoiceStatus(VOICE_STATES.SPEAKING);
        await speakText(aiText);
      }

      return aiText;
    } finally {
      if (activeRequestControllerRef.current === controller) {
        activeRequestControllerRef.current = null;
      }
      setLoading(false);
      setProcessingFile(false);
    }
  };

  const sendVoiceTranscript = async (transcript) => {
    const cleanTranscript = String(transcript || "").trim();
    if (!cleanTranscript || voiceSendingRef.current) {
      return;
    }

    voiceSendingRef.current = true;
    setVoiceTranscript("");
    setVoiceConfidence(null);
    setVoiceError("");
    setVoiceStatus(VOICE_STATES.THINKING);
    try {
      await sendToBackend(cleanTranscript, null, true, null, { targetWorkspace: "chat" });
    } catch (error) {
      if (error?.name === "AbortError") {
        setVoiceStatus(VOICE_STATES.IDLE);
        return;
      }
      await loadGuestLimits(undefined, sessionMode === "guest");
      const message = formatClientError(error, "Voice request failed. Check microphone access and backend status.");
      if (isGuestLimitMessage(message)) {
        voiceMicRef.current = false;
        setVoiceMicOn(false);
        setVoiceStatus(VOICE_STATES.ERROR);
        setVoiceError(GUEST_LIMIT_MESSAGE);
        await showGuestLimitReached();
        return;
      }
      setVoiceStatus(VOICE_STATES.ERROR);
      setVoiceError(message);
      appendAiMessage(message, "chat");
    } finally {
      voiceSendingRef.current = false;
    }
  };

  const startRecorderVoiceListening = async () => {
    if (!voiceModeRef.current || !voiceMicRef.current) {
      return;
    }

    if (!navigator.mediaDevices?.getUserMedia || !window.MediaRecorder) {
      setVoiceStatus(VOICE_STATES.ERROR);
      setVoiceError("Voice recording is not supported in this browser.");
      return;
    }

    try {
      setVoiceStatus(VOICE_STATES.LISTENING);
      setVoiceError("");
      const stream = await navigator.mediaDevices.getUserMedia({ audio: true });
      if (!voiceModeRef.current || !voiceMicRef.current) {
        stream.getTracks().forEach(track => track.stop());
        return;
      }

      voiceStreamRef.current = stream;
      voiceChunksRef.current = [];

      const preferredType = "audio/webm;codecs=opus";
      const options = window.MediaRecorder.isTypeSupported(preferredType)
        ? { mimeType: preferredType }
        : undefined;
      const recorder = new MediaRecorder(stream, options);
      mediaRecorderRef.current = recorder;

      recorder.ondataavailable = (event) => {
        if (event.data?.size) {
          voiceChunksRef.current.push(event.data);
        }
      };

      recorder.onerror = () => {
        setVoiceStatus(VOICE_STATES.ERROR);
        setVoiceError("Microphone error. Please retry or reconnect your microphone.");
        releaseVoiceStream();
      };

      recorder.onstop = async () => {
        releaseVoiceStream();

        if (!voiceModeRef.current || !voiceMicRef.current) {
          return;
        }

        const mimeType = recorder.mimeType || "audio/webm";
        const audioBlob = new Blob(voiceChunksRef.current, { type: mimeType });
        voiceChunksRef.current = [];

        try {
          setVoiceStatus(VOICE_STATES.THINKING);
          await sendVoiceAudio(audioBlob);
        } catch (error) {
          if (error?.name === "AbortError") {
            setVoiceStatus(VOICE_STATES.IDLE);
            return;
          }
          await loadGuestLimits(undefined, sessionMode === "guest");
          const message = formatClientError(error, "Voice request failed. Check backend and API keys.");
          if (isGuestLimitMessage(message)) {
            voiceMicRef.current = false;
            setVoiceMicOn(false);
            setVoiceStatus(VOICE_STATES.ERROR);
            setVoiceError(GUEST_LIMIT_MESSAGE);
            await showGuestLimitReached();
            return;
          }
          setVoiceStatus(VOICE_STATES.ERROR);
          setVoiceError(message.toLowerCase().includes("permission")
            ? "Microphone permission denied. Allow microphone access and try again."
            : message);
          appendAiMessage(message, "chat");
        } finally {
          finishVoiceTurn();
        }
      };

      recorder.onstart = () => {
        setVoiceStatus(VOICE_STATES.LISTENING);
      };

      recorder.start();
      voiceTimerRef.current = setTimeout(() => {
        if (mediaRecorderRef.current?.state === "recording") {
          mediaRecorderRef.current.stop();
        }
      }, 5500);
    } catch (error) {
      const blocked = error?.name === "NotAllowedError" || error?.name === "PermissionDeniedError";
      setVoiceStatus(VOICE_STATES.ERROR);
      if (blocked) {
        const message = "Microphone permission was denied. Allow microphone access in the browser to use voice mode.";
        setVoiceError(message);
        setAppError(message);
      } else {
        const message = "Could not start the microphone. Please check or reconnect your input device.";
        setVoiceError(message);
        setAppError(message);
      }
      releaseVoiceStream();
    }
  };

  const startBrowserVoiceRecognition = () => {
    const Recognition = getSpeechRecognitionConstructor();
    if (!Recognition || !voiceModeRef.current || !voiceMicRef.current) {
      return false;
    }

    stopVoiceRecorder();
    let finalTranscript = "";
    let interimTranscript = "";
    let submitted = false;
    let hadFatalError = false;
    let shouldUseRecorderFallback = false;
    let recorderFallbackScheduled = false;
    const recognizer = new Recognition();
    recognitionRef.current = recognizer;
    recognizer.lang = "en-US";
    recognizer.continuous = false;
    recognizer.interimResults = true;
    recognizer.maxAlternatives = 1;

    recognizer.onstart = () => {
      setVoiceStatus(VOICE_STATES.LISTENING);
      setVoiceError("");
      setVoiceTranscript("");
      setVoiceConfidence(null);
    };

    recognizer.onresult = (event) => {
      interimTranscript = "";
      let confidence = null;
      for (let index = event.resultIndex; index < event.results.length; index += 1) {
        const result = event.results[index];
        const alternative = result?.[0];
        const transcript = alternative?.transcript || "";
        if (typeof alternative?.confidence === "number" && alternative.confidence > 0) {
          confidence = Math.round(alternative.confidence * 100);
        }
        if (result?.isFinal) {
          finalTranscript += ` ${transcript}`;
        } else {
          interimTranscript += ` ${transcript}`;
        }
      }
      setVoiceTranscript(`${finalTranscript} ${interimTranscript}`.trim());
      setVoiceConfidence(confidence);
    };

    const scheduleRecorderFallback = () => {
      if (recorderFallbackScheduled || !voiceModeRef.current || !voiceMicRef.current) {
        return;
      }
      recorderFallbackScheduled = true;
      window.clearTimeout(voiceRestartTimerRef.current);
      voiceRestartTimerRef.current = window.setTimeout(() => {
        voiceRestartTimerRef.current = null;
        startRecorderVoiceListening();
      }, 180);
    };

    recognizer.onerror = (event) => {
      if (event.error === "no-speech") {
        return;
      }

      hadFatalError = true;
      if (BROWSER_RECOGNITION_FALLBACK_ERRORS.has(event.error)) {
        shouldUseRecorderFallback = true;
        browserRecognitionFallbackRef.current = true;
        setVoiceStatus(VOICE_STATES.LISTENING);
        setVoiceError("");
        setVoiceTranscript("Live recognition is unavailable in this browser. Using recorder fallback...");
        scheduleRecorderFallback();
        try {
          recognizer.stop();
        } catch {
          // Some browsers stop the recognizer automatically after this error.
        }
        return;
      }

      const messageMap = {
        "not-allowed": "Microphone permission was denied. Allow microphone access and retry.",
        "audio-capture": "No microphone was detected. Connect a microphone and retry.",
        network: "Speech recognition had a network issue. You can retry the microphone."
      };
      setVoiceStatus(VOICE_STATES.ERROR);
      setVoiceError(messageMap[event.error] || "Speech recognition failed. Please retry.");
    };

    recognizer.onend = () => {
      if (recognitionRef.current === recognizer) {
        recognitionRef.current = null;
      }

      if (!voiceModeRef.current || !voiceMicRef.current) {
        return;
      }

      if (shouldUseRecorderFallback) {
        scheduleRecorderFallback();
        return;
      }

      const transcript = finalTranscript.trim();
      if (transcript && !submitted) {
        submitted = true;
        sendVoiceTranscript(transcript);
        return;
      }

      if (!hadFatalError && !voiceSendingRef.current) {
        voiceRestartTimerRef.current = window.setTimeout(() => {
          voiceRestartTimerRef.current = null;
          startVoiceListening();
        }, 240);
      }
    };

    try {
      recognizer.start();
      return true;
    } catch {
      recognitionRef.current = null;
      return false;
    }
  };

  const startVoiceListening = async () => {
    if (!voiceModeRef.current || !voiceMicRef.current || voiceSendingRef.current) {
      return;
    }

    if (recognitionRef.current || mediaRecorderRef.current?.state === "recording") {
      return;
    }

    if ("speechSynthesis" in window && window.speechSynthesis.speaking) {
      stopResponseAudio();
    }

    const browserRecognitionStarted = browserRecognitionFallbackRef.current
      ? false
      : startBrowserVoiceRecognition();
    if (!browserRecognitionStarted) {
      await startRecorderVoiceListening();
    }
  };

  const openVoiceMode = () => {
    setWorkspace("chat");
    voiceModeRef.current = true;
    voiceMicRef.current = true;
    voiceManualStopRef.current = false;
    setVoiceMode(true);
    setVoiceMicOn(true);
    setVoiceStatus(VOICE_STATES.IDLE);
    setVoiceError("");
    setVoiceTranscript("");
    setTimeout(() => startVoiceListening(), 180);
  };

  const closeVoiceMode = () => {
    voiceModeRef.current = false;
    voiceMicRef.current = false;
    voiceManualStopRef.current = false;
    setVoiceMode(false);
    setVoiceStatus(VOICE_STATES.IDLE);
    setVoiceError("");
    setVoiceTranscript("");
    setVoiceMicOn(false);
    stopVoiceRecorder();
    stopResponseAudio();
  };

  const toggleVoiceMic = () => {
    if (voiceMicOn) {
      voiceMicRef.current = false;
      setVoiceMicOn(false);
      setVoiceStatus(VOICE_STATES.IDLE);
      stopVoiceRecorder();
      return;
    }

    voiceMicRef.current = true;
    voiceManualStopRef.current = false;
    setVoiceMicOn(true);
    setVoiceError("");
    setTimeout(() => startVoiceListening(), 160);
  };

  const pauseVoicePlayback = () => {
    if (!("speechSynthesis" in window) || !window.speechSynthesis.speaking) {
      return;
    }
    window.speechSynthesis.pause();
    setVoiceStatus(VOICE_STATES.PAUSED);
  };

  const resumeVoicePlayback = () => {
    if (!("speechSynthesis" in window)) {
      return;
    }
    window.speechSynthesis.resume();
    setVoiceStatus(VOICE_STATES.SPEAKING);
  };

  const replayLastAnswer = () => {
    const lastAnswer = lastSpokenResponseRef.current || settings.lastSpokenResponse;
    if (!lastAnswer) {
      setVoiceStatus(VOICE_STATES.ERROR);
      setVoiceError("There is no spoken answer to replay yet.");
      return;
    }
    speakText(lastAnswer, { forceFull: true });
  };

  const continueReadingLastAnswer = () => {
    const fullText = fullSpeechTextRef.current;
    if (!fullText) {
      return;
    }
    speakText(fullText, { forceFull: true });
  };

  const retryVoiceMicrophone = () => {
    setVoiceMicOn(true);
    voiceMicRef.current = true;
    voiceManualStopRef.current = false;
    setVoiceError("");
    setVoiceTranscript("");
    setVoiceStatus(VOICE_STATES.IDLE);
    stopVoiceRecorder();
    window.setTimeout(() => startVoiceListening(), 160);
  };

  const stopGenerating = () => {
    activeRequestControllerRef.current?.abort();
    activeRequestControllerRef.current = null;
    stoppedStreamReaderRef.current = activeStreamReaderRef.current;
    activeStreamReaderRef.current?.cancel().catch(() => {});
    activeStreamReaderRef.current = null;
    setLoading(false);
    setProcessingFile(false);
    stopResponseAudio();
    if (voiceModeRef.current) {
      voiceManualStopRef.current = true;
      voiceSendingRef.current = false;
      stopVoiceRecorder();
      setVoiceStatus(VOICE_STATES.IDLE);
    }
  };

  const setResponseLengthPreference = (value) => {
    if (!answerLengthOptions.includes(value)) {
      return;
    }
    setAnswerLength(value);
    try {
      window.localStorage.setItem(ANSWER_LENGTH_KEY, value);
    } catch {
      // The selected style still works for the open tab when storage is unavailable.
    }
  };

  const setModelModePreference = (value) => {
    if (!modelModeOptions.some(option => option.value === value)) {
      return;
    }
    setModelMode(value);
    try {
      window.localStorage.setItem(MODEL_MODE_KEY, value);
    } catch {
      // The selected model quality still works for the open tab when storage is unavailable.
    }
  };

  const setResponseModePreference = (value) => {
    if (!responseModeOptions.some(option => option.value === value)) {
      return;
    }
    setResponseMode(value);
    try {
      window.localStorage.setItem(RESPONSE_MODE_KEY, value);
    } catch {
      // The selected response style still works for the open tab when storage is unavailable.
    }
  };

  const beginEditLastMessage = (text) => {
    setMessage(text || "");
    setEditingTurn({ workspace });
    stopResponseAudio();
    setTimeout(() => focusComposer(), 0);
  };

  const removeResponseFeedback = (messageKey) => {
    if (!messageKey || !responseFeedback[messageKey]) {
      return;
    }
    const nextFeedback = { ...responseFeedback };
    delete nextFeedback[messageKey];
    setResponseFeedback(nextFeedback);
    try {
      window.localStorage.setItem(RESPONSE_FEEDBACK_KEY, JSON.stringify(nextFeedback));
    } catch {
      // The UI is already updated if local storage is unavailable.
    }
  };

  const regenerateLastResponse = async (nextAnswerLength = answerLength) => {
    if (isBusy) {
      return;
    }
    const userIndex = lastMessageIndex(activeMessages, "user");
    const aiIndex = lastMessageIndex(activeMessages, "ai");
    const userMessage = activeMessages[userIndex];
    if (userIndex < 0 || aiIndex < userIndex || userMessage?.fileName) {
      setAppError("Regenerate is available for your latest text prompt.");
      return;
    }

    removeResponseFeedback(`${workspace}:${activeId || "draft"}:${aiIndex}`);
    setMessageActionMenuKey("");
    try {
      await sendToBackend(userMessage.text, null, false, null, {
        replaceLastTurn: true,
        answerLength: nextAnswerLength
      });
    } catch (error) {
      if (error?.name === "AbortError") {
        return;
      }
      const errorMessage = formatClientError(error, "Could not regenerate this response.");
      if (isGuestLimitMessage(errorMessage)) {
        await showGuestLimitReached();
        return;
      }
      appendAiMessage(errorMessage, workspace);
    }
  };

  const regenerateWithLength = (nextAnswerLength) => {
    setResponseLengthPreference(nextAnswerLength);
    regenerateLastResponse(nextAnswerLength);
  };

  const viewSources = (messageKey, citations) => {
    setMessageActionMenuKey("");
    setDocumentsDrawer(null);
    setSourcesDrawer({ messageKey, citations });
  };

  const viewDocumentReferences = (messageKey, documentHits) => {
    setMessageActionMenuKey("");
    setSourcesDrawer(null);
    setDocumentsDrawer({ messageKey, documentHits });
  };

  const saveResponseFeedback = (messageKey, value) => {
    const nextFeedback = {
      ...responseFeedback,
      [messageKey]: { value, recordedAt: new Date().toISOString() }
    };
    setResponseFeedback(nextFeedback);
    try {
      window.localStorage.setItem(RESPONSE_FEEDBACK_KEY, JSON.stringify(nextFeedback));
    } catch {
      // Feedback remains visible for the current session if local storage is blocked.
    }
  };

  const copyMessage = async (text, messageKey = "") => {
    try {
      await navigator.clipboard.writeText(text || "");
      if (messageKey) {
        setCopiedMessageKey(messageKey);
        if (copiedStateTimerRef.current) {
          window.clearTimeout(copiedStateTimerRef.current);
        }
        copiedStateTimerRef.current = window.setTimeout(() => setCopiedMessageKey(""), 1500);
      }
    } catch {
      setAppError("Could not copy message.");
    }
  };

  const updateSettings = async (patch) => {
    const nextSettings = { ...settings, ...patch };
    setSettings(nextSettings);

    try {
      const data = await requestJson("/settings", {
        method: "PUT",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify(patch)
      });
      setSettings({ ...defaultSettings, ...(data.settings || {}) });
    } catch {
      setAppError("Could not save settings.");
    }
  };

  const saveMemoryProfile = async () => {
    try {
      const data = await requestJson("/memory", {
        method: "PUT",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify(memoryDraft)
      });
      const nextMemory = data.memory || memory;
      setMemory(nextMemory);
      setMemoryDraft({ name: nextMemory.name || "", role: nextMemory.role || "" });
    } catch {
      setAppError("Could not save memory.");
    }
  };

  const addMemoryFact = async () => {
    if (!factDraft.trim()) {
      return;
    }

    try {
      const data = await requestJson("/memory/facts", {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ text: factDraft.trim() })
      });
      setMemory(data.memory || memory);
      setFactDraft("");
    } catch {
      setAppError("Could not add memory.");
    }
  };

  const forgetMemoryFact = async (factId) => {
    try {
      const data = await requestJson(`/memory/facts/${factId}`, { method: "DELETE" });
      setMemory(data.memory || memory);
    } catch {
      setAppError("Could not forget memory.");
    }
  };

  const downloadCodeSnippet = (code, language = "txt", index = 0) => {
    const cleanLanguage = String(language || "txt").toLowerCase().trim();
    const extension = codeExtensions[cleanLanguage] || "txt";
    const blob = new Blob([code], { type: "text/plain;charset=utf-8" });
    const url = URL.createObjectURL(blob);
    const link = document.createElement("a");
    link.href = url;
    link.download = `febguy-code-${index + 1}.${extension}`;
    document.body.appendChild(link);
    link.click();
    link.remove();
    URL.revokeObjectURL(url);
  };

  const renderInlineMarkdown = (content, keyPrefix = "inline") => {
    const text = String(content || "");
    const parts = [];
    const inlinePattern = /(`[^`]+`|\*\*[^*]+?\*\*|__[^_]+?__)/g;
    let lastIndex = 0;
    let match;

    while ((match = inlinePattern.exec(text)) !== null) {
      if (match.index > lastIndex) {
        parts.push(text.slice(lastIndex, match.index));
      }

      const token = match[0];
      if (token.startsWith("`")) {
        parts.push(
          <code className="inline-code" key={`${keyPrefix}-code-${match.index}`}>
            {token.slice(1, -1)}
          </code>
        );
      } else {
        parts.push(
          <strong key={`${keyPrefix}-strong-${match.index}`}>
            {token.slice(2, -2)}
          </strong>
        );
      }

      lastIndex = inlinePattern.lastIndex;
    }

    if (lastIndex < text.length) {
      parts.push(text.slice(lastIndex));
    }

    return parts.length ? parts : text;
  };

  const getMarkdownDepth = (line) => {
    const indent = (line.match(/^\s*/) || [""])[0].replace(/\t/g, "    ").length;
    return Math.min(3, Math.floor(indent / 2));
  };

  const splitMarkdownTableRow = (line) => {
    const trimmed = String(line || "").trim();
    if (!trimmed.includes("|")) {
      return [];
    }

    const row = trimmed.replace(/^\|/, "").replace(/\|$/, "");
    return row.split("|").map(cell => cell.trim());
  };

  const isMarkdownTableDivider = (line) => {
    const cells = splitMarkdownTableRow(line);
    return cells.length > 1 && cells.every(cell => /^:?-{3,}:?$/.test(cell));
  };

  const normalizeTableCells = (cells, columnCount) => {
    if (cells.length === columnCount) {
      return cells;
    }

    if (cells.length > columnCount) {
      return [
        ...cells.slice(0, columnCount - 1),
        cells.slice(columnCount - 1).join(" | ")
      ];
    }

    return [...cells, ...Array.from({ length: columnCount - cells.length }, () => "")];
  };

  const renderMarkdownTable = (headers, rows, keyPrefix) => (
    <div className="markdown-table-wrap" key={`${keyPrefix}-table`}>
      <table className="markdown-table">
        <thead>
          <tr>
            {headers.map((header, index) => (
              <th key={`${keyPrefix}-head-${index}`}>
                {renderInlineMarkdown(header, `${keyPrefix}-head-${index}`)}
              </th>
            ))}
          </tr>
        </thead>
        <tbody>
          {rows.map((row, rowIndex) => (
            <tr key={`${keyPrefix}-row-${rowIndex}`}>
              {normalizeTableCells(row, headers.length).map((cell, cellIndex) => (
                <td key={`${keyPrefix}-cell-${rowIndex}-${cellIndex}`}>
                  {renderInlineMarkdown(cell, `${keyPrefix}-cell-${rowIndex}-${cellIndex}`)}
                </td>
              ))}
            </tr>
          ))}
        </tbody>
      </table>
    </div>
  );

  const renderPlainTextLines = (text, keyPrefix = "text") => {
    const lines = String(text || "").split("\n");
    const renderedLines = [];

    for (let index = 0; index < lines.length; index += 1) {
      const line = lines[index];
      const trimmed = line.trim();
      const nextLine = lines[index + 1] || "";
      const possibleTableHeaders = splitMarkdownTableRow(line);

      if (possibleTableHeaders.length > 1 && isMarkdownTableDivider(nextLine)) {
        const tableRows = [];
        let rowIndex = index + 2;

        while (rowIndex < lines.length) {
          const rowCells = splitMarkdownTableRow(lines[rowIndex]);
          if (rowCells.length <= 1 || isMarkdownTableDivider(lines[rowIndex])) {
            break;
          }
          tableRows.push(rowCells);
          rowIndex += 1;
        }

        if (tableRows.length) {
          renderedLines.push(renderMarkdownTable(
            possibleTableHeaders,
            tableRows,
            `${keyPrefix}-${index}`
          ));
          index = rowIndex - 1;
          continue;
        }
      }

      if (!trimmed) {
        renderedLines.push(<div className="text-gap" key={`${keyPrefix}-gap-${index}`} />);
        continue;
      }

      if (/^[-_*]{3,}$/.test(trimmed)) {
        renderedLines.push(<hr className="markdown-divider" key={`${keyPrefix}-divider-${index}`} />);
        continue;
      }

      const headingMatch = trimmed.match(/^(#{1,4})\s+(.+)/);
      if (headingMatch) {
        const depth = Math.min(4, headingMatch[1].length);
        const HeadingTag = depth <= 2 ? "h3" : "h4";
        renderedLines.push(
          <HeadingTag className={`markdown-heading heading-${depth}`} key={`${keyPrefix}-heading-${index}`}>
            {renderInlineMarkdown(headingMatch[2], `${keyPrefix}-heading-${index}`)}
          </HeadingTag>
        );
        continue;
      }

      const bulletMatch = line.match(/^\s*[-*•]\s+(.+)/);
      if (bulletMatch) {
        const depth = getMarkdownDepth(line);
        renderedLines.push(
          <div className={`bullet-line list-line depth-${depth}`} key={`${keyPrefix}-bullet-${index}`}>
            <span className="bullet-dot" aria-hidden="true" />
            <span>{renderInlineMarkdown(bulletMatch[1], `${keyPrefix}-bullet-${index}`)}</span>
          </div>
        );
        continue;
      }

      const numberedMatch = line.match(/^\s*(\d+)[.)]\s+(.+)/);
      if (numberedMatch) {
        const depth = getMarkdownDepth(line);
        renderedLines.push(
          <div className={`numbered-line list-line depth-${depth}`} key={`${keyPrefix}-number-${index}`}>
            <span>{numberedMatch[1]}.</span>
            <span>{renderInlineMarkdown(numberedMatch[2], `${keyPrefix}-number-${index}`)}</span>
          </div>
        );
        continue;
      }

      const alphaMatch = line.match(/^\s*([a-zA-Z])[.)]\s+(.+)/);
      if (alphaMatch) {
        const depth = getMarkdownDepth(line);
        renderedLines.push(
          <div className={`numbered-line list-line alpha-line depth-${depth}`} key={`${keyPrefix}-alpha-${index}`}>
            <span>{alphaMatch[1].toLowerCase()}.</span>
            <span>{renderInlineMarkdown(alphaMatch[2], `${keyPrefix}-alpha-${index}`)}</span>
          </div>
        );
        continue;
      }

      renderedLines.push(
        <p key={`${keyPrefix}-line-${index}`}>{renderInlineMarkdown(line, `${keyPrefix}-line-${index}`)}</p>
      );
    }

    return renderedLines;
  };

  const renderMessageText = (text) => {
    const raw = stripThinkingBlocks(text);
    const segments = [];
    const codePattern = /```([a-zA-Z0-9+#._-]*)?\n([\s\S]*?)```/g;
    let lastIndex = 0;
    let match;

    while ((match = codePattern.exec(raw)) !== null) {
      if (match.index > lastIndex) {
        segments.push({ type: "text", content: raw.slice(lastIndex, match.index) });
      }
      segments.push({
        type: "code",
        language: (match[1] || "text").trim() || "text",
        content: match[2].replace(/\n$/, "")
      });
      lastIndex = codePattern.lastIndex;
    }

    if (lastIndex < raw.length) {
      segments.push({ type: "text", content: raw.slice(lastIndex) });
    }

    if (!segments.length) {
      segments.push({ type: "text", content: raw });
    }

    return (
      <div className="formatted-text">
        {segments.map((segment, index) => {
          if (segment.type === "code") {
            return (
              <div className="code-block" key={`code-${index}`}>
                <div className="code-toolbar">
                  <span>{segment.language}</span>
                  <div>
                    <button type="button" onClick={() => copyMessage(segment.content)}>
                      Copy
                    </button>
                    <button type="button" onClick={() => downloadCodeSnippet(segment.content, segment.language, index)}>
                      Download
                    </button>
                  </div>
                </div>
                <pre><code>{segment.content}</code></pre>
              </div>
            );
          }

          return (
            <div className="text-segment" key={`text-segment-${index}`}>
              {renderPlainTextLines(segment.content, `segment-${index}`)}
            </div>
          );
        })}
      </div>
    );
  };

  const getChatSubtitle = (chatItem) => {
    if (chatItem.summary) {
      return chatItem.summary.slice(0, 70);
    }

    const firstText = chatItem.messages?.find(item => item.text)?.text;
    return firstText ? firstText.slice(0, 70) : "No summary yet";
  };

  const renderSourcesDrawer = () => {
    const citations = sourcesDrawer?.citations || [];
    if (!citations.length) {
      return null;
    }

    const checkedAt = citations.find(citation => citation.retrievedAt)?.retrievedAt;
    const checkedLabel = checkedAt
      ? new Date(checkedAt).toLocaleString([], { dateStyle: "medium", timeStyle: "short" })
      : "";

    return (
      <aside className="sources-drawer" aria-label="Sources">
        <div className="sources-drawer-header">
          <div>
            <span>Sources</span>
            <h2>Web references</h2>
          </div>
          <button type="button" aria-label="Close sources" onClick={() => setSourcesDrawer(null)}>
            <CloseIcon />
          </button>
        </div>
        <div className="sources-drawer-meta">
          <small>
            {citations.length} web source{citations.length === 1 ? "" : "s"}
            {checkedLabel ? ` | checked ${checkedLabel}` : ""}
          </small>
        </div>
        <div className="sources-drawer-list">
          {citations.map(citation => (
            <a
              key={`${citation.id}-${citation.url}`}
              href={citation.url}
              target="_blank"
              rel="noreferrer"
              className="source-drawer-card"
            >
              <span className="citation-index">{citation.id}</span>
              <span className="citation-body">
                <strong>{citation.title}</strong>
                <small>
                  {citation.domain || citation.url}
                  {citation.sourceType === "primary" ? " | Primary source" : ""}
                </small>
                {citation.snippet && <em>{citation.snippet}</em>}
              </span>
              <ExternalLink />
            </a>
          ))}
        </div>
      </aside>
    );
  };

  const renderCodeFiles = (files = []) => {
    if (!files.length) {
      return null;
    }

    return (
      <div className="code-file-list" aria-label="Code files attached to this turn">
        {files.map((fileItem, index) => (
          <span className="code-file-chip" key={`${fileItem.id || fileItem.fileName}-${index}`}>
            <CodeFileIcon />
            <span>{fileItem.fileName || fileItem.name}</span>
            {fileItem.language && <small>{fileItem.language}</small>}
          </span>
        ))}
      </div>
    );
  };

  const renderGeneratedFiles = (files = []) => {
    if (!files.length) {
      return null;
    }

    return (
      <div className="generated-files" aria-label="Generated code downloads">
        <span className="generated-files-label">Generated files</span>
        {files.map((fileItem, index) => (
          <button
            type="button"
            className="generated-file-card"
            key={`${fileItem.downloadUrl || fileItem.fileName}-${index}`}
            onClick={() => downloadOwnedFile(fileItem)}
          >
            <CodeFileIcon />
            <span>
              <strong>{fileItem.fileName}</strong>
              <small>{fileItem.language || "code"}{fileItem.sizeBytes ? ` | ${Math.ceil(fileItem.sizeBytes / 1024)} KB` : ""}</small>
            </span>
            <DownloadIcon />
          </button>
        ))}
      </div>
    );
  };

  const uniqueDocumentReferences = (hits = []) => {
    const references = new Map();
    hits.forEach((hit, index) => {
      const fileName = hit.fileName || "Uploaded file";
      const pageLabel = hit.pageNumber ? `page-${hit.pageNumber}` : "file";
      const key = `${hit.documentId || fileName}:${pageLabel}`;
      if (!references.has(key)) {
        references.set(key, { ...hit, referenceIndex: index + 1, fileName });
      }
    });
    return [...references.values()];
  };

  const getDocumentReferenceCount = (hits = []) => uniqueDocumentReferences(hits).length;

  const renderDocumentsDrawer = () => {
    const references = uniqueDocumentReferences(documentsDrawer?.documentHits || []);
    if (!references.length) {
      return null;
    }

    return (
      <aside className="sources-drawer documents-drawer" aria-label="Document references">
        <div className="sources-drawer-header">
          <div>
            <span>Documents</span>
            <h2>Used in this answer</h2>
          </div>
          <button type="button" aria-label="Close documents" onClick={() => setDocumentsDrawer(null)}>
            <CloseIcon />
          </button>
        </div>
        <div className="sources-drawer-meta">
          <small>{references.length} referenced file location{references.length === 1 ? "" : "s"}</small>
        </div>
        <div className="sources-drawer-list">
          {references.map(reference => (
            <article
              key={`${reference.documentId || reference.fileName}-${reference.pageNumber || "file"}`}
              className="source-drawer-card document-reference-card"
            >
              <DocumentIcon />
              <span className="citation-body">
                <strong>{reference.fileName}</strong>
                <small>
                  {reference.pageNumber ? `Page ${reference.pageNumber}` : "File reference"}
                  {reference.isImage ? " | Image" : ""}
                </small>
                {reference.preview && <em>{reference.preview}</em>}
                {reference.ocrUsed && !reference.textUnavailable && (
                  <b className={reference.ocrUncertain ? "ocr-warning uncertain" : "ocr-warning"}>
                    OCR-derived text{reference.ocrUncertain ? " - verify unclear details" : ""}
                  </b>
                )}
                {reference.textUnavailable && !reference.isImage && (
                  <b className="ocr-warning uncertain">
                    No readable text extracted - OCR may be unavailable or failed
                  </b>
                )}
                {reference.textUnavailable && reference.isImage && (
                  <b className="ocr-warning">
                    Visual analysis used; OCR text was unavailable
                  </b>
                )}
              </span>
            </article>
          ))}
        </div>
      </aside>
    );
  };

  const renderSuggestions = (suggestions = []) => {
    const cleanSuggestions = suggestions
      .filter(Boolean)
      .map(item => String(item).trim())
      .filter(item => item && !hiddenSuggestions.has(item))
      .slice(0, 3);

    if (!cleanSuggestions.length) {
      return null;
    }

    return (
      <div className="suggestion-chips" aria-label="Follow-up suggestions">
        {cleanSuggestions.map(item => (
          <button
            key={item}
            type="button"
            onClick={() => sendSuggestion(item)}
            disabled={isBusy}
          >
            {item}
          </button>
        ))}
      </div>
    );
  };

  const renderLoadingScreen = () => (
    <div className="auth-shell flow-screen">
      <section className="loading-card" aria-live="polite">
        <div className="auth-brand">
          <div className="logo-mark">FGAI</div>
          <div>
            <div className="auth-title-row">
              <h1>FebGuy AI</h1>
              <span>By Pranav Amble</span>
            </div>
            <p>Private AI workspace</p>
          </div>
        </div>
        <div className="skeleton-line wide" />
        <div className="skeleton-line" />
        <div className="skeleton-cards">
          <span />
          <span />
          <span />
        </div>
        <p className="loading-label">Checking session...</p>
      </section>
    </div>
  );

  const renderSignInScreen = () => (
    <div className="auth-shell flow-screen">
      <div className="auth-layout">
        <section className="auth-showcase">
          <div className="auth-brand">
            <div className="logo-mark">FGAI</div>
            <div>
              <div className="auth-title-row">
                <h1>FebGuy AI</h1>
                <span>By Pranav Amble</span>
              </div>
              <p>Private AI workspace</p>
            </div>
          </div>
          <span className="screen-badge"><LockIcon /> Private workspace</span>
          <h2>Research, learn, and build with a workspace that stays yours.</h2>
          <p className="showcase-copy">
            Keep conversations organized, explore files, and use Code Studio from one focused space.
          </p>
          <div className="benefit-grid">
            <article>
              <LockIcon />
              <strong>Private profiles</strong>
              <small>PIN-protected spaces on your device.</small>
            </article>
            <article>
              <SearchIcon />
              <strong>Research tools</strong>
              <small>Search, documents, and cited answers.</small>
            </article>
            <article>
              <CodeIcon />
              <strong>Code Studio</strong>
              <small>A focused workspace for programming help.</small>
            </article>
          </div>
        </section>

        <section className="auth-card sign-in-card">
          <span className="screen-badge">Sign in</span>
          <h2>Continue securely</h2>
          <p>Sign in to create private profiles and keep your work organized.</p>
          <section className="account-auth" aria-label="Account sign in">
            <button
              type="button"
              className="google-signin"
              onClick={signInWithGoogle}
              disabled={accountAuthLoading}
            >
              <span className="google-mark" aria-hidden="true">G</span>
              <span>{accountAuthLoading ? "Signing in..." : "Continue with Google"}</span>
            </button>
            <div className="account-divider"><span>or continue with email</span></div>
            <form className="email-signin" onSubmit={signInWithEmail}>
              <label className="email-field">
                <MailIcon />
                <input
                  type="email"
                  autoComplete="email"
                  value={accountEmail}
                  onChange={(event) => setAccountEmail(event.target.value)}
                  placeholder="Email address"
                  aria-label="Email address"
                />
              </label>
              <button type="submit" className="email-action" disabled={accountAuthLoading}>
                <MailIcon />
                <span>Continue with Email</span>
              </button>
            </form>
            {emailLinkSent && (
              <small className="email-sent">Check your email for your secure sign-in link.</small>
            )}
          </section>
          <p className="auth-privacy">
            <LockIcon />
            Your workspace stays private to your profile.
          </p>
          <button type="button" className="guest-text-link" onClick={continueAsGuest}>
            Continue as Guest
          </button>
          {authError && <div className="auth-error" role="alert">{authError}</div>}
        </section>
      </div>
    </div>
  );

  const profileLimitReached = profiles.length >= 3;
  const renderProfileScreen = () => (
    <div className="auth-shell flow-screen">
      <section className="auth-card profile-auth-card">
        <div className="auth-brand">
          <div className="logo-mark">FGAI</div>
          <div>
            <div className="auth-title-row">
              <h1>FebGuy AI</h1>
              <span>By Pranav Amble</span>
            </div>
            <p>Private AI workspace</p>
          </div>
        </div>

        <div className="account-ready">
          <span className="identity-badge signed">Signed in</span>
          <strong>{accountIdentity?.email || "Your account"}</strong>
          <p>Select a profile on this device or create a private workspace.</p>
        </div>
        <div className="privacy-note">
          <LockIcon />
          <p>
            <strong>PIN privacy</strong>
            Profiles are device-bound and protected by a PIN. You can create up to 3 profiles per device.
          </p>
        </div>

        <div className="auth-tabs">
          <button
            type="button"
            className={authMode === "login" ? "active" : ""}
            onClick={() => setAuthMode("login")}
          >
            Existing Profile
          </button>
          <button
            type="button"
            className={authMode === "create" ? "active" : ""}
            onClick={() => setAuthMode("create")}
          >
            Create New
          </button>
        </div>

        {authMode === "login" && profiles.length > 0 ? (
          <form className="auth-form" onSubmit={loginProfile}>
            <label>
              Profile
              <select
                value={selectedProfileId}
                onChange={(event) => setSelectedProfileId(event.target.value)}
              >
                {profiles.map(item => (
                  <option key={item.id} value={item.id}>{item.name}</option>
                ))}
              </select>
            </label>
            <label>
              PIN
              <input
                type="password"
                value={pin}
                minLength={4}
                onChange={(event) => setPin(event.target.value)}
                placeholder="Enter PIN"
              />
            </label>
            {!legacyLoginEnabled && selectedProfileId && (
              <button type="button" className="forgot-pin-action" onClick={openPinResetModal}>
                Forgot PIN?
              </button>
            )}
            <button type="submit" disabled={profileLoading}>
              {profileLoading ? "Unlocking profile..." : "Unlock Profile"}
            </button>
          </form>
        ) : authMode === "login" ? (
          <div className="profile-empty">
            <ProfileIcon />
            <strong>No profiles on this device yet</strong>
            <p>Create your first private workspace to begin.</p>
            <button type="button" onClick={() => setAuthMode("create")}>Create Profile</button>
          </div>
        ) : (
          <form className="auth-form" onSubmit={createProfile}>
            <label>
              Profile name
              <input
                value={profileName}
                onChange={(event) => setProfileName(event.target.value)}
                placeholder="Your profile name"
              />
            </label>
            <label>
              PIN
              <input
                type="password"
                value={pin}
                minLength={4}
                onChange={(event) => setPin(event.target.value)}
                placeholder="At least 4 characters"
              />
            </label>
            {profileLimitReached && (
              <div className="limit-note">Maximum 3 profiles reached on this device.</div>
            )}
            <button type="submit" disabled={profileLimitReached || profileLoading}>
              {profileLoading ? "Opening workspace..." : "Create and Enter"}
            </button>
          </form>
        )}

        {profile?.device_bound && (
          <button type="button" className="text-action" onClick={cancelProfileSwitch}>
            Back to current workspace
          </button>
        )}
        {authError && (
          <div
            className={`auth-error ${authError.includes("does not exist on this device") ? "device-error" : ""}`}
            role="alert"
          >
            {authError}
          </div>
        )}
      </section>

      {pinResetOpen && (
        <div className="dialog-overlay" role="presentation">
          <section
            className="action-dialog profile-security-dialog"
            role="dialog"
            aria-modal="true"
            aria-labelledby="pin-reset-title"
          >
            <div className="dialog-icon">
              <LockIcon />
            </div>
            <h2 id="pin-reset-title">Reset profile PIN</h2>
            <p>
              {selectedProfile
                ? `Reset PIN for ${selectedProfile.name}. We will confirm your signed-in account first.`
                : "Select a profile to reset its PIN."}
            </p>

            {pinResetStep === "start" && (
              <div className="pin-reset-step">
                <p className="dialog-muted">
                  A short-lived verification code will be prepared for your signed-in email.
                </p>
                <div className="dialog-actions">
                  <button type="button" onClick={closePinResetModal} disabled={pinResetBusy}>
                    Cancel
                  </button>
                  <button
                    type="button"
                    className="primary-dialog-action"
                    onClick={startPinReset}
                    disabled={pinResetBusy || !selectedProfileId}
                  >
                    {pinResetBusy ? "Preparing..." : "Send Code"}
                  </button>
                </div>
              </div>
            )}

            {pinResetStep === "verify" && (
              <form className="pin-reset-step" onSubmit={verifyPinReset}>
                {pinResetInfo && <div className="dialog-info">{pinResetInfo}</div>}
                {pinResetDevCode && (
                  <div className="dialog-info dev-code">
                    Local testing code: <strong>{pinResetDevCode}</strong>
                  </div>
                )}
                <label className="dialog-field">
                  Verification code
                  <input
                    autoFocus
                    inputMode="numeric"
                    value={pinResetCode}
                    onChange={(event) => setPinResetCode(event.target.value)}
                    placeholder="Enter code"
                  />
                </label>
                <div className="dialog-actions">
                  <button type="button" onClick={closePinResetModal} disabled={pinResetBusy}>
                    Cancel
                  </button>
                  <button
                    type="submit"
                    className="primary-dialog-action"
                    disabled={pinResetBusy || !pinResetCode.trim()}
                  >
                    {pinResetBusy ? "Checking..." : "Verify Code"}
                  </button>
                </div>
              </form>
            )}

            {pinResetStep === "new-pin" && (
              <form className="pin-reset-step" onSubmit={completePinReset}>
                {pinResetInfo && <div className="dialog-info">{pinResetInfo}</div>}
                <label className="dialog-field">
                  New PIN
                  <input
                    autoFocus
                    type="password"
                    minLength={4}
                    value={pinResetNewPin}
                    onChange={(event) => setPinResetNewPin(event.target.value)}
                    placeholder="At least 4 characters"
                  />
                </label>
                <label className="dialog-field">
                  Confirm new PIN
                  <input
                    type="password"
                    minLength={4}
                    value={pinResetConfirmPin}
                    onChange={(event) => setPinResetConfirmPin(event.target.value)}
                    placeholder="Re-enter new PIN"
                  />
                </label>
                <div className="dialog-actions">
                  <button type="button" onClick={closePinResetModal} disabled={pinResetBusy}>
                    Cancel
                  </button>
                  <button
                    type="submit"
                    className="primary-dialog-action"
                    disabled={pinResetBusy || !pinResetNewPin || !pinResetConfirmPin}
                  >
                    {pinResetBusy ? "Saving..." : "Save New PIN"}
                  </button>
                </div>
              </form>
            )}

            {pinResetError && <div className="dialog-error">{pinResetError}</div>}
          </section>
        </div>
      )}
    </div>
  );

  const renderOnboardingScreen = () => (
    <div className="auth-shell flow-screen">
      <section className="onboarding-card">
        <div className="auth-brand">
          <div className="logo-mark">FGAI</div>
          <div>
            <div className="auth-title-row">
              <h1>FebGuy AI</h1>
              <span>By Pranav Amble</span>
            </div>
            <p>Private and secure Profiles</p>
          </div>
        </div>

        <span className="onboarding-kicker"><LockIcon /> Before you continue</span>
        <h2>Set up your private workspaces</h2>
        <p className="onboarding-copy">
          Profiles keep your FebGuy workspace personal and separate on the devices you use.
        </p>

        <div className="onboarding-list">
          <div>
            <strong>Private workspaces</strong>
            <p>Each profile is a separate space for your chats, files, settings, and memory.</p>
          </div>
          <div>
            <strong>Protected by a PIN</strong>
            <p>Every profile has its own PIN so another person cannot simply open your workspace.</p>
          </div>
          <div>
            <strong>Maximum 3 profiles</strong>
            <p>An account can use up to three profiles per device.</p>
          </div>
          <div>
            <strong>Privacy on shared devices</strong>
            <p>PIN access helps protect your information if a device is shared, misplaced, or stolen.</p>
          </div>
          <div>
            <strong>Device-bound by default</strong>
            <p>Profiles are designed to stay connected to the device where they are created.</p>
          </div>
        </div>

        <button
          type="button"
          className="onboarding-continue"
          onClick={completeOnboarding}
          disabled={onboardingLoading}
        >
          {onboardingLoading ? "Continuing..." : "Continue"}
        </button>

        {authError && <div className="auth-error">{authError}</div>}
      </section>
    </div>
  );

  const renderPanel = () => {
    if (!activePanel) {
      return null;
    }

    return (
      <div className="side-panel">
        <div className="panel-header">
          <div>
            <h2>{activePanel === "memory" ? "Memory" : "Settings"}</h2>
            <p>{activePanel === "memory" ? "Profile-specific memory" : "Local app controls"}</p>
          </div>
          <button type="button" aria-label="Close settings" onClick={() => setActivePanel(null)}>
            <CloseIcon />
          </button>
        </div>

        {activePanel === "memory" ? (
          <div className="panel-body">
            <label>
              Name
              <input
                value={memoryDraft.name}
                onChange={(event) => setMemoryDraft(prev => ({ ...prev, name: event.target.value }))}
              />
            </label>
            <label>
              Role
              <input
                value={memoryDraft.role}
                onChange={(event) => setMemoryDraft(prev => ({ ...prev, role: event.target.value }))}
              />
            </label>
            <button type="button" className="primary-action" onClick={saveMemoryProfile}>Save Memory</button>

            <div className="memory-add">
              <input
                value={factDraft}
                onChange={(event) => setFactDraft(event.target.value)}
                placeholder="Remember this..."
              />
              <button type="button" onClick={addMemoryFact}>Add</button>
            </div>

            <div className="memory-list">
              {(memory.facts || []).map(fact => (
                <div className="memory-item" key={fact.id}>
                  <span>{fact.text}</span>
                  <button type="button" onClick={() => forgetMemoryFact(fact.id)}>Forget</button>
                </div>
              ))}
              {!(memory.facts || []).length && <small>No remembered facts yet.</small>}
            </div>
          </div>
        ) : (
          <div className="panel-body settings-panel">
            <section className="settings-identity">
              <div className="profile-avatar">{initialsFor(profile?.name || accountIdentity?.email || "Guest")}</div>
              <div>
                <span>{sessionMode === "guest" ? "Guest workspace" : "Current profile"}</span>
                <strong>{sessionMode === "guest" ? "Guest" : profile?.name}</strong>
                <small>
                  {sessionMode === "guest"
                    ? "Temporary browser session"
                    : accountIdentity?.email || "Signed-in workspace"}
                </small>
              </div>
            </section>

            {profile?.device_bound && (
              <section className="settings-section-card settings-profile-actions">
                <span className="setting-section-title">Profile</span>
                <div className="profile-security-actions">
                  <button type="button" className="panel-switch-action danger" onClick={openDeleteProfileModal}>
                    <TrashIcon />
                    Delete Profile
                  </button>
                  <button type="button" className="panel-switch-action" onClick={switchProfile}>
                    <ProfileIcon />
                    Switch Profile
                  </button>
                </div>
              </section>
            )}

            <section className="settings-section-card">
              <span className="setting-section-title">General</span>
              {sessionMode === "guest" && (
                <button type="button" className="panel-switch-action" onClick={openAccountSignIn}>
                  <LockIcon />
                  Sign In
                </button>
              )}
              <label className="setting-row">
                <span>Web search</span>
                <input
                  type="checkbox"
                  className="toggle-switch"
                  checked={settings.searchEnabled}
                  onChange={(event) => updateSettings({ searchEnabled: event.target.checked })}
                />
              </label>

              <label className="setting-row">
                <span>Document search</span>
                <input
                  type="checkbox"
                  className="toggle-switch"
                  checked={settings.ragEnabled}
                  onChange={(event) => updateSettings({ ragEnabled: event.target.checked })}
                />
              </label>
            </section>

            <section className="settings-section-card">
              <span className="setting-section-title">Voice</span>
              <label className="setting-row">
                <span>Voice replies</span>
                <input
                  type="checkbox"
                  className="toggle-switch"
                  checked={settings.voiceEnabled}
                  onChange={(event) => updateSettings({ voiceEnabled: event.target.checked })}
                />
              </label>

              <label className="setting-row">
                <span>Sentence-by-sentence voice</span>
                <input
                  type="checkbox"
                  className="toggle-switch"
                  checked={settings.sentenceVoice}
                  onChange={(event) => updateSettings({ sentenceVoice: event.target.checked })}
                />
              </label>

              <label>
                Voice
                <select
                  value={settings.voiceName || ""}
                  onChange={(event) => updateSettings({ voiceName: event.target.value })}
                >
                  <option value="">Best available voice</option>
                  {availableVoices.map(voice => (
                    <option key={`${voice.name}-${voice.lang}`} value={voice.name}>
                      {voiceFriendlyName(voice)}
                    </option>
                  ))}
                </select>
              </label>

              <label>
                Voice speed
                <select
                  value={settings.voiceSpeed || "normal"}
                  onChange={(event) => updateSettings({ voiceSpeed: event.target.value })}
                >
                  {Object.entries(voiceSpeedLabels).map(([value, label]) => (
                    <option key={value} value={value}>{label}</option>
                  ))}
                </select>
              </label>
            </section>

            <section className="settings-section-card">
              <span className="setting-section-title">Appearance</span>
              <label>
                Theme
                <select
                  value={settings.theme}
                  onChange={(event) => updateSettings({ theme: event.target.value })}
                >
                  <option value="midnight">Midnight</option>
                  <option value="obsidian">Polished Dark</option>
                  <option value="aurora">Aurora</option>
                  <option value="graphite">Graphite</option>
                </select>
              </label>
            </section>

            {sessionMode !== "guest" && (
              <section className="settings-section-card logout-zone">
                <span className="setting-section-title">Logout</span>
                <p>
                  Logging out will close this account session on this browser. Guest mode is still available.
                </p>
                <button type="button" className="logout-action" onClick={confirmAccountLogout}>
                  <LogoutIcon />
                  Logout
                </button>
              </section>
            )}
          </div>
        )}
      </div>
    );
  };

  const isBusy = loading || processingFile;
  const latestUserIndex = lastMessageIndex(activeMessages, "user");
  const latestAiIndex = lastMessageIndex(activeMessages, "ai");
  const showStopControl = isBusy || responseSpeaking;
  const guestLimitError = isGuestLimitMessage(appError);
  const showGuestLimitUi = sessionMode === "guest" && guestLimits?.guest;
  const guestLimitItems = [
    { key: "chat", label: "Chat messages left" },
    { key: "code", label: "Code messages left" },
    { key: "upload", label: "File uploads left" }
  ];
  const isAccountProfile = sessionMode === "profile" && Boolean(profile?.device_bound);
  const selectedProfile = profiles.find(item => item.id === selectedProfileId) || profiles[0] || null;

  if (bootstrapping) {
    return renderLoadingScreen();
  }

  if (onboardingAccount) {
    return renderOnboardingScreen();
  }

  if (accountSelectingProfile) {
    return renderProfileScreen();
  }

  if (!profileToken || !profile) {
    return renderSignInScreen();
  }

  return (
    <div className={`app-shell theme-${settings.theme} ${isCodeWorkspace ? "workspace-code" : "workspace-chat"} ${sidebarCollapsed ? "sidebar-collapsed" : ""}`}>
      <aside className="sidebar" aria-label="Workspace sidebar" aria-expanded={!sidebarCollapsed}>
        <div className="brand">
          <div className="logo-mark">FGAI</div>

          <div className="brand-copy">
            <h2>FebGuy</h2>
            <p>{sessionMode === "guest" ? "Private workspace" : profile.name}</p>
          </div>
          <button
            type="button"
            className="sidebar-collapse-btn"
            aria-label={sidebarCollapsed ? "Expand sidebar" : "Collapse sidebar"}
            title={sidebarCollapsed ? "Expand sidebar" : "Collapse sidebar"}
            onClick={() => setSidebarCollapsed(current => {
              const next = !current;
              if (!next) setSidebarRecentOpen(false);
              return next;
            })}
          >
            <MenuIcon />
          </button>
        </div>
        <div className="sidebar-account">
          <span className={`identity-badge ${sessionMode === "guest" ? "guest" : "signed"}`}>
            {sessionMode === "guest" ? "Guest" : "Signed in"}
          </span>
          <small>
            <LockIcon />
            {sessionMode === "guest" ? "Private browser session" : "Profile protected"}
          </small>
        </div>

        <button
          className="new-chat-btn"
          type="button"
          onClick={() => {
            setSidebarRecentOpen(false);
            createNewChat();
          }}
          data-tooltip={isCodeWorkspace ? "New Code Chat" : "New Chat"}
        >
          <PlusIcon />
          <span className="sidebar-label">{isCodeWorkspace ? "New Code Chat" : "New Chat"}</span>
        </button>

        <div className="workspace-switcher" aria-label="Workspace switcher">
          <button
            type="button"
            className={!isCodeWorkspace ? "active" : ""}
            onClick={() => switchWorkspace("chat")}
            data-tooltip="Chat"
          >
            <span className="workspace-icon-badge">AI</span>
            <span className="sidebar-label">Chat</span>
          </button>
          <button
            type="button"
            className={isCodeWorkspace ? "active code-active" : ""}
            onClick={() => switchWorkspace("code")}
            data-tooltip="Code Studio"
          >
            <span className="workspace-icon-badge"><CodeIcon /></span>
            <span className="sidebar-label">Code Studio</span>
          </button>
        </div>

        <div className="sidebar-tools">
          <button type="button" onClick={() => setActivePanel("settings")} data-tooltip="Settings">
            <SettingsIcon />
            <span className="sidebar-label">Settings</span>
          </button>
          {sessionMode === "guest" ? (
            <button type="button" className="sign-in-action" onClick={openAccountSignIn} data-tooltip="Sign In">
              <LockIcon />
              <span className="sidebar-label">Sign In</span>
            </button>
          ) : isAccountProfile ? (
            <button type="button" onClick={switchProfile} data-tooltip="Switch Profile">
              <ProfileIcon />
              <span className="sidebar-label">Switch Profile</span>
            </button>
          ) : null}
        </div>

        <div className="collapsed-rail-actions">
          <button
            type="button"
            className={sidebarRecentOpen ? "active" : ""}
            aria-label={isCodeWorkspace ? "Recent code chats" : "Recent chats"}
            title={isCodeWorkspace ? "Recent code chats" : "Recent chats"}
            data-tooltip={isCodeWorkspace ? "Recent code chats" : "Recent chats"}
            onClick={() => setSidebarRecentOpen(current => !current)}
          >
            <HistoryIcon />
          </button>
        </div>

        <div className="history-title"><span className="sidebar-label">{isCodeWorkspace ? "Code Studio Chats" : "Previous Chats"}</span></div>

        <div className="chat-list">
          {!activeChats.length && (
            <div className="history-empty">
              <strong>{isCodeWorkspace ? "No code chats yet" : "No chats yet"}</strong>
              <p>{isCodeWorkspace ? "Start a new coding request." : "Your conversations will appear here."}</p>
            </div>
          )}
          {activeChats.map((chatItem, index) => (
            <div
              key={chatItem.id}
              className={activeId === chatItem.id ? "chat-card active" : "chat-card"}
              data-tooltip={chatItem.title || "New Chat"}
            >
              <button type="button" className="chat-open" onClick={() => openChat(chatItem)}>
                <span className="chat-index">
                  {chatItem.pinned ? <PinIcon /> : index + 1}
                </span>

                <span className="chat-meta">
                  <strong>{chatItem.title || "New Chat"}</strong>
                  <small>{getChatSubtitle(chatItem)}</small>
                </span>
              </button>

              <div className="chat-actions">
                <button type="button" title={chatItem.pinned ? "Unpin chat" : "Pin chat"} aria-label={chatItem.pinned ? "Unpin chat" : "Pin chat"} onClick={() => togglePinChat(chatItem)}>
                  <PinIcon />
                </button>
                <button type="button" title="Rename chat" aria-label="Rename chat" onClick={() => renameChat(chatItem)}>
                  <EditIcon />
                </button>
                <button type="button" title="Export TXT" aria-label="Export TXT" onClick={() => exportChat(chatItem)}>
                  <DownloadIcon />
                </button>
                <button type="button" title="Delete chat" aria-label="Delete chat" onClick={() => deleteChat(chatItem)}>
                  <TrashIcon />
                </button>
              </div>
            </div>
          ))}
        </div>
      </aside>

      {sidebarCollapsed && sidebarRecentOpen && (
        <div
          className="collapsed-recents-panel"
          role="dialog"
          aria-label={isCodeWorkspace ? "Recent code chats" : "Recent chats"}
          onMouseDown={(event) => event.stopPropagation()}
        >
          <div className="collapsed-recents-header">
            <div>
              <span>Recent</span>
              <strong>{isCodeWorkspace ? "Code Studio" : "AI Chat"}</strong>
            </div>
            <button
              type="button"
              aria-label="Close recent chats"
              onMouseDown={(event) => {
                event.preventDefault();
                event.stopPropagation();
              }}
              onClick={(event) => {
                event.stopPropagation();
                setSidebarRecentOpen(false);
              }}
            >
              <CloseIcon />
            </button>
          </div>

          <div className="collapsed-recents-list">
            {!activeChats.length && (
              <div className="collapsed-recents-empty">
                {isCodeWorkspace ? "No code chats yet." : "No chats yet."}
              </div>
            )}
            {activeChats.slice(0, 12).map((chatItem, index) => (
              <button
                type="button"
                key={chatItem.id}
                className={activeId === chatItem.id ? "collapsed-recent-item active" : "collapsed-recent-item"}
                onMouseDown={(event) => event.stopPropagation()}
                onClick={(event) => {
                  event.stopPropagation();
                  openChat(chatItem);
                  setSidebarRecentOpen(false);
                }}
              >
                <span className="chat-index">{chatItem.pinned ? <PinIcon /> : index + 1}</span>
                <span>
                  <strong>{chatItem.title || "New Chat"}</strong>
                  <small>{getChatSubtitle(chatItem)}</small>
                </span>
              </button>
            ))}
          </div>
        </div>
      )}

      <main
        key={workspaceMotionKey}
        className={`main-area workspace-panel ${activeMessages.length === 0 ? "is-empty" : ""}`}
      >
        <header className="top-bar">
          <div className="workspace-heading">
            <span className="workspace-label">
              {isCodeWorkspace ? <CodeIcon /> : <LockIcon />}
              {isCodeWorkspace ? "Focused coding workspace" : "Private AI workspace"}
            </span>
            <h1>{isCodeWorkspace ? "Code Studio" : "FebGuy AI"}</h1>
            <p>By Pranav Amble</p>
          </div>

          <div className="header-controls">
            <div className="header-profile">
              <div className="profile-avatar">{initialsFor(sessionMode === "guest" ? "Guest" : profile.name)}</div>
              <div>
                <strong>{sessionMode === "guest" ? "Guest workspace" : profile.name}</strong>
                <small>{sessionMode === "guest" ? "Temporary session" : "Current profile"}</small>
              </div>
            </div>
            <div className="workspace-status" aria-label="Workspace status">
              {isCodeWorkspace ? (
                <>
                  <span className="account-pill">{sessionMode === "guest" ? "Guest Code Studio" : "Full Code Studio"}</span>
                  <span>Auto Detect</span>
                </>
              ) : (
                <>
                  <span className="account-pill">{sessionMode === "guest" ? "Guest" : "Signed in"}</span>
                  <span>{health?.search_available ? "Search Ready" : "Search Off"}</span>
                </>
              )}
            </div>
          </div>
        </header>

        {appError && !guestLimitError && (
          <div className="toast-stack" role="status">
            <div className="toast-notice">
              <span>{appError}</span>
              <button type="button" aria-label="Dismiss notification" onClick={() => setAppError("")}>
                <CloseIcon />
              </button>
            </div>
          </div>
        )}

        {activeMessages.length === 0 && sessionMode === "guest" && !isCodeWorkspace ? (
          <section className="guest-welcome">
            <span className="empty-kicker"><LockIcon /> Guest workspace</span>
            <h2>Private AI workspace</h2>
            <p>
              Ask questions, research the web, or explore a document. Sign in when you are ready
              for protected profiles and saved workspaces.
            </p>
            <div className="guest-actions">
              <button type="button" onClick={focusComposer} disabled={isBusy}>
                Start a conversation
              </button>
              <button type="button" onClick={openAccountSignIn}>Sign In</button>
            </div>
            <div className="benefit-grid compact">
              <article><SearchIcon /><strong>Research</strong><small>Search with source-aware answers.</small></article>
              <article><AttachIcon /><strong>Files</strong><small>Upload documents and images.</small></article>
              <article><CodeIcon /><strong>Code Studio</strong><small>Build and debug in a focused mode.</small></article>
            </div>
            <div className="starter-grid guest-starters">
              {starterPrompts.map(item => (
                <button
                  key={item.title}
                  type="button"
                  onClick={() => sendSuggestion(item.prompt)}
                  disabled={isBusy}
                >
                  <span className="starter-icon"><StarterPromptIcon label={item.label} /></span>
                  <span className="starter-label">{item.label}</span>
                  <strong>{item.title}</strong>
                  <small>{item.prompt}</small>
                </button>
              ))}
            </div>
            <div className="file-empty-hint">
              <AttachIcon />
              <span>
                <strong>No files uploaded</strong>
                <small>Attach a document or image to analyze it here.</small>
              </span>
            </div>
          </section>
        ) : activeMessages.length === 0 && (
          <section className="empty-state">
            <span className="empty-kicker">{isCodeWorkspace ? "Code Studio" : "AI Workspace"}</span>
            <h2>{isCodeWorkspace ? "What are we building?" : "What are we solving today?"}</h2>
            <p>
              {isCodeWorkspace
                ? "Ask naturally. Code Studio detects the task and language from your prompt."
                : "Start with a focused request or choose a workspace starter."}
            </p>
            <div className="starter-grid">
              {(isCodeWorkspace ? codeStarterPrompts : starterPrompts).map(item => (
                <button
                  key={item.title}
                  type="button"
                  onClick={() => sendSuggestion(item.prompt)}
                  disabled={isBusy}
                >
                  <span className="starter-icon"><StarterPromptIcon label={item.label} /></span>
                  <span className="starter-label">{item.label}</span>
                  <strong>{item.title}</strong>
                  <small>{item.prompt}</small>
                </button>
              ))}
            </div>
            {!isCodeWorkspace && (
              <div className="file-empty-hint">
                <AttachIcon />
                <span>
                  <strong>No files uploaded</strong>
                  <small>Attach a document or image to analyze it here.</small>
                </span>
              </div>
            )}
          </section>
        )}

        {isCodeWorkspace && activeCodeProjectFiles.length > 0 && (
          <div className="code-context-strip" aria-label="Current Code Studio project files">
            <div>
              <CodeFileIcon />
              <span>
                <strong>Project context</strong>
                <small>{activeCodeProjectFiles.length} file{activeCodeProjectFiles.length === 1 ? "" : "s"} scoped to this code chat</small>
              </span>
            </div>
            <div className="code-context-files">
              {activeCodeProjectFiles.slice(0, 6).map(fileItem => (
                <span key={fileItem.id || fileItem.fileName}>{fileItem.fileName}</span>
              ))}
              {activeCodeProjectFiles.length > 6 && <span>+{activeCodeProjectFiles.length - 6} more</span>}
            </div>
          </div>
        )}

        <section className="messages" aria-live="polite">
          {activeMessages.map((msg, index) => {
            const messageKey = `${workspace}:${activeId || "draft"}:${index}`;
            const feedbackValue = responseFeedback[messageKey]?.value;
            return (
              <div
                key={`${msg.role}-${index}`}
                className={msg.role === "user" ? "bubble-row user-row" : "bubble-row ai-row"}
              >
              <div className={msg.role === "user" ? "bubble user-bubble" : "bubble ai-bubble"}>
                {msg.fileName && (
                  <div className="attachment-card">
                    {msg.filePreview ? (
                      <img src={msg.filePreview} alt="Uploaded preview" />
                    ) : (
                      <div className="file-pill">
                        <span>File</span>
                        {msg.fileName}
                      </div>
                    )}
                  </div>
                )}
                {renderCodeFiles(msg.codeFiles)}

                {msg.fileResult ? (
                  <div className="download-card">
                    <div className="download-icon">OK</div>

                    <div className="download-info">
                      <strong>{msg.text}</strong>
                      <span>{msg.fileName}</span>

                      <button
                        type="button"
                        onClick={() => downloadOwnedFile(msg)}
                        className="download-btn"
                      >
                        Download File
                      </button>
                    </div>
                  </div>
                ) : (
                  <>
                    {renderMessageText(msg.text)}
                    {renderSuggestions(msg.suggestions)}
                    {renderGeneratedFiles(msg.generatedFiles)}
                  </>
                )}
              </div>

              {msg.role === "user" && !msg.fileResult && (
                <div className="message-actions user-message-actions">
                  <button
                    type="button"
                    className="icon-action"
                    title="Copy message"
                    aria-label="Copy message"
                    onClick={() => copyMessage(msg.text, messageKey)}
                  >
                    <CopyIcon />
                  </button>
                  {copiedMessageKey === messageKey && <span className="action-feedback">Copied</span>}
                  {index === latestUserIndex && !msg.fileName && !isBusy && (
                  <button
                    type="button"
                    className="icon-action"
                    title="Edit last message"
                    aria-label="Edit last message"
                    onClick={() => beginEditLastMessage(msg.text)}
                  >
                    <EditIcon />
                  </button>
                  )}
                </div>
              )}

              {msg.role === "ai" && !msg.fileResult && (
                <div className="message-actions ai-message-actions">
                  {!!msg.documentHits?.length && (
                    <button
                      type="button"
                      className="document-context-pill"
                      title={`View ${getDocumentReferenceCount(msg.documentHits)} uploaded document reference${getDocumentReferenceCount(msg.documentHits) === 1 ? "" : "s"}`}
                      onClick={() => viewDocumentReferences(messageKey, msg.documentHits)}
                    >
                      <DocumentIcon />
                      <span>Docs</span>
                      <b>{getDocumentReferenceCount(msg.documentHits)}</b>
                    </button>
                  )}
                  {!isCodeWorkspace && (
                    <button
                      type="button"
                      className="icon-action"
                      title="Read aloud"
                      aria-label="Read aloud"
                      onClick={() => speakText(stripThinkingBlocks(msg.text))}
                    >
                      <SpeakerIcon />
                    </button>
                  )}
                  <button
                    type="button"
                    className="icon-action"
                    title="Copy response"
                    aria-label="Copy response"
                    onClick={() => copyMessage(stripThinkingBlocks(msg.text), messageKey)}
                  >
                    <CopyIcon />
                  </button>
                  {copiedMessageKey === messageKey && <span className="action-feedback">Copied</span>}
                  <button
                    type="button"
                    className={`icon-action ${feedbackValue === "helpful" ? "selected-action" : ""}`}
                    title="Helpful"
                    aria-label="Helpful"
                    aria-pressed={feedbackValue === "helpful"}
                    onClick={() => saveResponseFeedback(messageKey, "helpful")}
                  >
                    <HelpfulIcon />
                  </button>
                  <button
                    type="button"
                    className={`icon-action ${feedbackValue === "not_helpful" ? "selected-action" : ""}`}
                    title="Not helpful"
                    aria-label="Not helpful"
                    aria-pressed={feedbackValue === "not_helpful"}
                    onClick={() => saveResponseFeedback(messageKey, "not_helpful")}
                  >
                    <NotHelpfulIcon />
                  </button>
                  <div className="more-actions-wrap">
                    <button
                      type="button"
                      className="icon-action"
                      title="More actions"
                      aria-label="More actions"
                      aria-expanded={messageActionMenuKey === messageKey}
                      onClick={() => setMessageActionMenuKey(current => current === messageKey ? "" : messageKey)}
                    >
                      <MoreHorizontal />
                    </button>
                    {messageActionMenuKey === messageKey && (
                      <div className="message-more-menu" role="menu">
                        {index === latestAiIndex && latestAiIndex > latestUserIndex && !activeMessages[latestUserIndex]?.fileName && (
                          <>
                            <button type="button" role="menuitem" onClick={() => regenerateLastResponse()} disabled={isBusy}>
                              <RegenerateIcon />
                              Regenerate
                            </button>
                            <span className="more-menu-label">Response length</span>
                            <button type="button" role="menuitem" onClick={() => regenerateWithLength("short")} disabled={isBusy}>
                              Make shorter
                            </button>
                            <button type="button" role="menuitem" onClick={() => regenerateWithLength("standard")} disabled={isBusy}>
                              Make standard
                            </button>
                            <button type="button" role="menuitem" onClick={() => regenerateWithLength("detailed")} disabled={isBusy}>
                              Make detailed
                            </button>
                          </>
                        )}
                        {!!msg.citations?.length && (
                          <button type="button" role="menuitem" onClick={() => viewSources(messageKey, msg.citations)}>
                            <ExternalLink />
                            View sources
                          </button>
                        )}
                        {!!msg.documentHits?.length && (
                          <button type="button" role="menuitem" onClick={() => viewDocumentReferences(messageKey, msg.documentHits)}>
                            <DocumentIcon />
                            View document references
                          </button>
                        )}
                        {index !== latestAiIndex && !msg.citations?.length && !msg.documentHits?.length && (
                          <span className="more-menu-empty">No additional actions</span>
                        )}
                      </div>
                    )}
                  </div>
                </div>
              )}
              </div>
            );
          })}

          {loading && (
            <div className="bubble-row ai-row">
              <div className="bubble ai-bubble thinking">
                {isCodeWorkspace ? "Code Studio is thinking..." : "FebGuy is thinking..."}
              </div>
            </div>
          )}

          {processingFile && (
            <div className="bubble-row ai-row">
              <div className="bubble ai-bubble thinking">Processing your file...</div>
            </div>
          )}

          <div ref={messagesEndRef} />
        </section>

        {selectedFile && !isCodeWorkspace && (
          <div className="selected-file">
            <div className="selected-file-preview">
              {filePreview ? (
                <img src={filePreview} alt="Selected preview" />
              ) : (
                <span>{selectedFile.name}</span>
              )}
            </div>

            <button type="button" onClick={resetFileInput} title="Remove file" aria-label="Remove file">
              <CloseIcon />
            </button>
          </div>
        )}

        {isCodeWorkspace && selectedCodeFiles.length > 0 && (
          <div className="selected-code-files">
            <div>
              <CodeFileIcon />
              <span>
                <strong>{selectedCodeFiles.length} code file{selectedCodeFiles.length === 1 ? "" : "s"} ready</strong>
                <small>These will be added only to this Code Studio chat.</small>
              </span>
            </div>
            <div className="selected-code-file-list">
              {selectedCodeFiles.map(fileItem => (
                <span key={`${fileItem.name}-${fileItem.size}`}>{fileItem.name}</span>
              ))}
            </div>
            <button type="button" onClick={resetFileInput} title="Remove code files" aria-label="Remove code files">
              <CloseIcon />
            </button>
          </div>
        )}

        {!isCodeWorkspace && (
          <div className="ai-control-strip" aria-label="AI response controls">
            <div className="ai-control-group" aria-label="Model quality">
              <span className="ai-control-label">Quality</span>
              <div className="ai-chip-row">
                {modelModeOptions.map(option => (
                  <button
                    key={option.value}
                    type="button"
                    className={`ai-mode-chip ${modelMode === option.value ? "active" : ""}`}
                    onClick={() => setModelModePreference(option.value)}
                    aria-pressed={modelMode === option.value}
                  >
                    {option.label}
                  </button>
                ))}
              </div>
            </div>

            <label className="ai-control-group ai-style-control">
              <span className="ai-control-label">Style</span>
              <select
                value={responseMode}
                onChange={(event) => setResponseModePreference(event.target.value)}
                aria-label="Response style"
              >
                {responseModeOptions.map(option => (
                  <option key={option.value} value={option.value}>{option.label}</option>
                ))}
              </select>
            </label>
          </div>
        )}

        {showGuestLimitUi && (
          <div className="guest-limit-strip" aria-label="Guest usage remaining">
            {guestLimitItems.map(item => {
              const limit = guestLimits.limits?.[item.key];
              return (
                <div
                  key={item.key}
                  className={`guest-limit-item ${limit?.remaining === 0 ? "exhausted" : ""}`}
                >
                  <span>{item.label}</span>
                  <strong>{limit?.remaining ?? "-"}</strong>
                </div>
              );
            })}
          </div>
        )}

        {guestLimitError && <div className="app-error composer-error">{GUEST_LIMIT_MESSAGE}</div>}

        {editingTurn?.workspace === workspace && (
          <div className="editing-message-bar">
            <span><EditIcon /> Editing your last message</span>
            <button type="button" onClick={() => { setEditingTurn(null); setMessage(""); }}>
              Cancel
            </button>
          </div>
        )}

        <form
          className={`input-dock ${isCodeWorkspace ? "code-input" : ""}`}
          onSubmit={(event) => {
            event.preventDefault();
            sendMessage();
          }}
        >
          <textarea
            ref={composerRef}
            placeholder={isCodeWorkspace ? "Ask Code Studio to write, debug, explain, convert, or optimize code..." : "Ask FebGuy anything..."}
            value={message}
            rows={1}
            onChange={(event) => setMessage(event.target.value)}
            onKeyDown={(event) => {
              if (event.key === "Enter" && !event.shiftKey) {
                event.preventDefault();
                sendMessage();
              }
            }}
          />

          {showStopControl ? (
            <button type="button" className="stop-action" onClick={stopGenerating}>
              <StopIcon />
              Stop
            </button>
          ) : (
            <button type="submit" className="send-action">
              <SendIcon />
              Send
            </button>
          )}
          {!isCodeWorkspace && (
            <button type="button" className="voice-action" onClick={openVoiceMode} disabled={isBusy}>
              <SpeakerIcon />
              Voice
            </button>
          )}

          {isCodeWorkspace ? (
            <>
              <input
                ref={fileInputRef}
                id="codeFileUpload"
                type="file"
                multiple
                accept={CODE_FILE_ACCEPT}
                onChange={handleFileSelect}
              />

              <button
                type="button"
                className="attach-action code-attach-action"
                onClick={() => fileInputRef.current?.click()}
                disabled={isBusy}
              >
                <CodeFileIcon />
                Files
              </button>
            </>
          ) : (
            <>
              <input
                ref={fileInputRef}
                id="fileUpload"
                type="file"
                accept=".pdf,.docx,.png,.jpg,.jpeg,.txt,application/pdf,application/vnd.openxmlformats-officedocument.wordprocessingml.document,image/png,image/jpeg,text/plain"
                onChange={handleFileSelect}
              />

              <button
                type="button"
                className="attach-action"
                onClick={() => fileInputRef.current?.click()}
                disabled={isBusy}
              >
                <AttachIcon />
                Attach
              </button>
            </>
          )}
        </form>
      </main>

      {renderPanel()}
      {renderSourcesDrawer()}
      {renderDocumentsDrawer()}

      {actionDialog && (
        <div className="dialog-overlay" role="presentation">
          <form
            className={`action-dialog ${actionDialog.tone === "danger" ? "danger" : ""}`}
            role="dialog"
            aria-modal="true"
            aria-labelledby="action-dialog-title"
            onSubmit={submitActionDialog}
          >
            <div className="dialog-icon">
              {actionDialog.tone === "danger" ? <LogoutIcon /> : <EditIcon />}
            </div>
            <h2 id="action-dialog-title">{actionDialog.title}</h2>
            <p>{actionDialog.description}</p>
            {actionDialog.kind === "input" && (
              <label className="dialog-field">
                {actionDialog.inputLabel}
                <input
                  autoFocus
                  maxLength={80}
                  value={actionDialogValue}
                  onChange={(event) => setActionDialogValue(event.target.value)}
                />
              </label>
            )}
            <div className="dialog-actions">
              <button type="button" onClick={closeActionDialog} disabled={actionDialogBusy}>
                Cancel
              </button>
              <button
                type="submit"
                className={actionDialog.tone === "danger" ? "danger-action" : "primary-dialog-action"}
                disabled={actionDialogBusy || (actionDialog.kind === "input" && !actionDialogValue.trim())}
              >
                {actionDialogBusy ? "Working..." : actionDialog.confirmLabel}
              </button>
            </div>
          </form>
        </div>
      )}

      {deleteProfileOpen && (
        <div className="dialog-overlay" role="presentation">
          <form
            className="action-dialog danger profile-security-dialog"
            role="dialog"
            aria-modal="true"
            aria-labelledby="delete-profile-title"
            onSubmit={deleteCurrentProfile}
          >
            <div className="dialog-icon">
              <TrashIcon />
            </div>
            <h2 id="delete-profile-title">Delete current profile?</h2>
            <p>
              Deleting this profile will permanently delete all chats, uploads, preferences,
              and saved data for this profile. This cannot be undone.
            </p>
            <label className="dialog-field">
              Current profile PIN
              <input
                autoFocus
                type="password"
                value={deleteProfilePin}
                onChange={(event) => setDeleteProfilePin(event.target.value)}
                placeholder="Enter PIN to confirm"
              />
            </label>
            {deleteProfileError && <div className="dialog-error">{deleteProfileError}</div>}
            <div className="dialog-actions">
              <button type="button" onClick={closeDeleteProfileModal} disabled={deleteProfileBusy}>
                Cancel
              </button>
              <button
                type="submit"
                className="danger-action"
                disabled={deleteProfileBusy || !deleteProfilePin.trim()}
              >
                {deleteProfileBusy ? "Deleting..." : "Delete Profile"}
              </button>
            </div>
          </form>
        </div>
      )}

      {guestLimitModalOpen && sessionMode === "guest" && (
        <div className="upgrade-overlay" role="presentation">
          <section className="upgrade-modal" role="dialog" aria-modal="true" aria-labelledby="guest-limit-title">
            <button
              className="upgrade-close"
              type="button"
              aria-label="Close"
              onClick={() => setGuestLimitModalOpen(false)}
            >
              <CloseIcon />
            </button>
            <span className="upgrade-kicker">Guest limit reached</span>
            <h2 id="guest-limit-title">Sign in to continue</h2>
            <p>Your guest access has reached a current usage limit.</p>
            <ul>
              <li>Save chats to a profile</li>
              <li>Unlock profiles</li>
              <li>Unlock full Code Studio</li>
              <li>Unlock more file tools</li>
            </ul>
            <div className="upgrade-actions">
              <button type="button" onClick={openAccountSignIn}>Sign in / Upgrade</button>
              <button type="button" onClick={() => setGuestLimitModalOpen(false)}>Not now</button>
            </div>
            <small>Your guest chats are not deleted when you open sign in.</small>
          </section>
        </div>
      )}

      {voiceMode && (
        <div className="voice-overlay">
          <div className="voice-panel">
            <button className="voice-close" type="button" onClick={closeVoiceMode}>
              <CloseIcon />
            </button>

            <div
              className={`voice-orb ${
                voiceStatus === VOICE_STATES.LISTENING ? "listening" : ""
              } ${voiceStatus === VOICE_STATES.SPEAKING ? "speaking" : ""} ${
                voiceStatus === VOICE_STATES.PAUSED ? "paused" : ""
              } ${voiceStatus === VOICE_STATES.ERROR ? "error" : ""}`}
            >
              <div className="orb-ring" />
              <div className="orb-core" />
            </div>

            <h2>FebGuy Voice</h2>
            <span className={`voice-state-pill state-${voiceStatus.toLowerCase()}`}>
              {voiceStatus}
            </span>
            <p>
              {voiceStatus === VOICE_STATES.LISTENING
                ? "Speak naturally. I will send your question automatically."
                : voiceStatus === VOICE_STATES.THINKING
                  ? "Thinking through your question..."
                : voiceStatus === VOICE_STATES.SPEAKING
                  ? "You can interrupt me by speaking."
                  : voiceStatus === VOICE_STATES.PAUSED
                    ? "Playback is paused."
                    : voiceStatus === VOICE_STATES.ERROR
                      ? "Voice needs attention. You can retry the microphone."
                      : "Hands-free voice mode is ready."}
            </p>

            <div className="voice-live-card">
              <span>Live transcript</span>
              <strong>{voiceTranscript || "Waiting for your voice..."}</strong>
              {voiceConfidence !== null && (
                <small>Confidence: {voiceConfidence}%</small>
              )}
            </div>

            {voiceSpokenWasSummarized && voiceStatus !== VOICE_STATES.LISTENING && (
              <button type="button" className="voice-link-action" onClick={continueReadingLastAnswer}>
                Continue reading full answer
              </button>
            )}

            {voiceError && (
              <div className="voice-error">
                {voiceError}
              </div>
            )}

            <div className="voice-settings-mini">
              <label>
                Voice
                <select
                  value={settings.voiceName || ""}
                  onChange={(event) => updateSettings({ voiceName: event.target.value })}
                >
                  <option value="">Best available</option>
                  {availableVoices.map(voice => (
                    <option key={`voice-modal-${voice.name}-${voice.lang}`} value={voice.name}>
                      {voiceFriendlyName(voice)}
                    </option>
                  ))}
                </select>
              </label>
              <label>
                Speed
                <select
                  value={settings.voiceSpeed || "normal"}
                  onChange={(event) => updateSettings({ voiceSpeed: event.target.value })}
                >
                  {Object.entries(voiceSpeedLabels).map(([value, label]) => (
                    <option key={`voice-speed-${value}`} value={value}>{label}</option>
                  ))}
                </select>
              </label>
            </div>

            <div className="voice-controls">
              <button type="button" onClick={toggleVoiceMic}>
                {voiceMicOn ? <Mic /> : <MicOff />}
                {voiceMicOn ? "Mic On" : "Mic Off"}
              </button>

              {voiceStatus === VOICE_STATES.PAUSED ? (
                <button type="button" onClick={resumeVoicePlayback}>
                  <PlayIcon />
                  Resume
                </button>
              ) : (
                <button type="button" onClick={pauseVoicePlayback} disabled={!responseSpeaking}>
                  <PauseIcon />
                  Pause
                </button>
              )}

              <button type="button" onClick={replayLastAnswer}>
                <RegenerateIcon />
                Replay
              </button>

              <button type="button" onClick={stopGenerating}>
                <StopIcon />
                Stop
              </button>

              <button type="button" onClick={retryVoiceMicrophone}>
                <Mic />
                Retry Mic
              </button>
            </div>
          </div>
        </div>
      )}
    </div>
  );
}

export default App;
