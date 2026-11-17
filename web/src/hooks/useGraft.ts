import { useCallback, useEffect, useRef, useState } from "react";
import { api, toApiError } from "../api";
import type { AnchorSelection } from "../selection";
import type {
  ConversationState,
  ConversationSummary,
  Health,
  FileUpload,
  Settings,
} from "../types";
import {
  isEmptyConversation,
  loadLastConversationId,
  saveLastConversationId,
  threadKey,
  threadMessages,
} from "../util";
import { fileKind, toUpload } from "../files";
import { playGlop } from "../sound";
import { useToasts } from "./useToasts";

/** A model call in flight on a thread. `text` is the optimistic user message, if any. */
export interface PendingRequest {
  text: string | null;
  /** Object URLs of the images sent with it, shown until the server state arrives. */
  images?: string[];
  /** Names of the documents sent with it. */
  documents?: string[];
}

/** Which branches the merge dialog pre-selects for merging. */
export type MergeFocus = number[] | "all";

/** Codes the server answers before storing anything (docs/API.md, "Chat"). */
const REFUSED_BEFORE_STORING = new Set([
  "validation",
  "conflict",
  "no_api_key",
  "no_model",
  "spend_cap_reached",
  "core_not_implemented",
  "not_found",
  "invariant",
]);

export function useGraft() {
  const { toasts, pushError, dismissToast } = useToasts();
  const [settings, setSettings] = useState<Settings | null>(null);
  const [health, setHealth] = useState<Health | null>(null);
  const [conversations, setConversations] = useState<ConversationSummary[]>([]);
  const [activeId, setActiveId] = useState<number | null>(null);
  const [state, setState] = useState<ConversationState | null>(null);
  const [booting, setBooting] = useState(true);
  const [pending, setPending] = useState<Record<string, PendingRequest>>({});
  const [panelBranchId, setPanelBranchId] = useState<number | null>(null);
  const [bannerDismissed, setBannerDismissed] = useState(false);
  const [mergeFocus, setMergeFocus] = useState<MergeFocus | null>(null);
  const [settingsOpen, setSettingsOpen] = useState(false);
  const activeRef = useRef<number | null>(null);

  /** Replaces the whole state, unless the user moved to another conversation meanwhile. */
  const applyState = useCallback((next: ConversationState) => {
    if (activeRef.current === next.conversation.id) setState(next);
  }, []);

  const refreshConversations = useCallback(async () => {
    try {
      setConversations(await api.listConversations());
    } catch (e) {
      pushError(e);
    }
  }, [pushError]);

  const refreshSettings = useCallback(async () => {
    try {
      setSettings(await api.getSettings());
    } catch {
      // The month spend line is informative only; the next refresh will catch up.
    }
  }, []);

  const activate = useCallback((id: number | null) => {
    activeRef.current = id;
    setActiveId(id);
    saveLastConversationId(id);
    setPanelBranchId(null);
    setMergeFocus(null);
    setBannerDismissed(false);
  }, []);

  const reload = useCallback(
    async (id: number): Promise<ConversationState | null> => {
      try {
        const fresh = await api.getConversation(id);
        applyState(fresh);
        return fresh;
      } catch (e) {
        pushError(e);
        return null;
      }
    },
    [applyState, pushError],
  );

  const openConversation = useCallback(
    async (id: number) => {
      if (activeRef.current === id) return;
      activate(id);
      try {
        applyState(await api.getConversation(id));
      } catch (e) {
        pushError(e);
        if (activeRef.current === id) {
          activate(null);
          setState(null);
        }
      }
    },
    [activate, applyState, pushError],
  );

  const adopt = useCallback(
    (created: ConversationState) => {
      activate(created.conversation.id);
      setState(created);
    },
    [activate],
  );

  const newChat = useCallback(async () => {
    if (state && activeRef.current === state.conversation.id && isEmptyConversation(state)) return;
    try {
      adopt(await api.createConversation());
      void refreshConversations();
    } catch (e) {
      pushError(e);
    }
  }, [adopt, pushError, refreshConversations, state]);

  // First load: health, settings, conversation list, then the last opened conversation.
  useEffect(() => {
    let cancelled = false;
    void (async () => {
      const [h, s, list] = await Promise.allSettled([
        api.health(),
        api.getSettings(),
        api.listConversations(),
      ]);
      if (cancelled) return;
      if (h.status === "fulfilled") setHealth(h.value);
      if (s.status === "fulfilled") {
        setSettings(s.value);
        if (!s.value.has_api_key && !s.value.fake_llm) setSettingsOpen(true);
      } else {
        pushError(s.reason);
      }
      if (list.status === "fulfilled") {
        setConversations(list.value);
        const last = loadLastConversationId();
        const first = list.value.find((c) => c.id === last) ?? list.value[0];
        if (first) await openConversation(first.id);
      } else if (s.status === "fulfilled") {
        pushError(list.reason);
      }
      if (!cancelled) setBooting(false);
    })();
    return () => {
      cancelled = true;
    };
  }, [openConversation, pushError]);

  const setThreadPending = useCallback((key: string, value: PendingRequest | null) => {
    setPending((map) => {
      const next = { ...map };
      if (value) next[key] = value;
      else delete next[key];
      return next;
    });
  }, []);

  const afterModelCall = useCallback(() => {
    void refreshConversations();
    void refreshSettings();
  }, [refreshConversations, refreshSettings]);

  /** Resolves to true when the text is now stored server-side (the composer may clear). */
  const sendMessage = useCallback(
    async (branchId: number | null, text: string, files: File[] = []): Promise<boolean> => {
      let conversationId = activeRef.current;
      if (conversationId === null) {
        try {
          const created = await api.createConversation();
          adopt(created);
          conversationId = created.conversation.id;
        } catch (e) {
          pushError(e);
          return false;
        }
      }
      const key = threadKey(conversationId, branchId);
      const previews = files.filter((f) => fileKind(f) === "image").map((f) => URL.createObjectURL(f));
      const documents = files.filter((f) => fileKind(f) === "document").map((f) => f.name);
      setThreadPending(key, { text, images: previews, documents });
      try {
        let uploads: FileUpload[] = [];
        try {
          uploads = await Promise.all(files.map(toUpload));
        } catch (e) {
          pushError(e);
          return false; // nothing was sent
        }
        applyState(await api.sendMessage(conversationId, text, branchId, uploads));
        return true;
      } catch (e) {
        const err = toApiError(e);
        pushError(err);
        const fresh = await reload(conversationId);
        if (err.code.startsWith("provider_")) return true;
        if (REFUSED_BEFORE_STORING.has(err.code) || !fresh) return false;
        // Unknown failure (network drop, proxy error): trust what the server now holds.
        const last = threadMessages(fresh, branchId).at(-1);
        return last?.role === "user" && last.content.trim() === text.trim();
      } finally {
        setThreadPending(key, null);
        previews.forEach((url) => URL.revokeObjectURL(url));
        afterModelCall();
      }
    },
    [adopt, afterModelCall, applyState, pushError, reload, setThreadPending],
  );

  const retry = useCallback(
    async (branchId: number | null) => {
      const conversationId = activeRef.current;
      if (conversationId === null) return;
      const key = threadKey(conversationId, branchId);
      setThreadPending(key, { text: null });
      try {
        applyState(await api.generate(conversationId, branchId));
      } catch (e) {
        pushError(e);
        await reload(conversationId);
      } finally {
        setThreadPending(key, null);
        afterModelCall();
      }
    },
    [afterModelCall, applyState, pushError, reload, setThreadPending],
  );

  const deleteMessage = useCallback(
    async (messageId: number) => {
      const conversationId = activeRef.current;
      try {
        applyState(await api.deleteMessage(messageId));
      } catch (e) {
        pushError(e);
        if (conversationId !== null) await reload(conversationId);
      }
    },
    [applyState, pushError, reload],
  );

  const openBranch = useCallback(
    async (messageId: number, selection: AnchorSelection): Promise<boolean> => {
      const conversationId = activeRef.current;
      if (conversationId === null) return false;
      try {
        const res = await api.openBranch(conversationId, {
          anchor_message_id: messageId,
          start: selection.start,
          end: selection.end,
          quote: selection.quote,
        });
        if (activeRef.current !== conversationId) return false;
        applyState(res.state);
        setPanelBranchId(res.branch_id);
        playGlop("branch");
        void refreshConversations();
        return true;
      } catch (e) {
        pushError(e);
        return false;
      }
    },
    [applyState, pushError, refreshConversations],
  );

  const discardBranch = useCallback(
    async (branchId: number) => {
      try {
        applyState(await api.discardBranch(branchId));
        void refreshConversations();
      } catch (e) {
        pushError(e);
      }
    },
    [applyState, pushError, refreshConversations],
  );

  const closePanel = useCallback(() => {
    setPanelBranchId(null);
    setBannerDismissed(false);
  }, []);

  const pendingFor = useCallback(
    (branchId: number | null): PendingRequest | null =>
      activeId === null ? null : (pending[threadKey(activeId, branchId)] ?? null),
    [activeId, pending],
  );

  return {
    booting,
    settings,
    setSettings,
    health,
    conversations,
    activeId,
    state: state && state.conversation.id === activeId ? state : null,
    applyState,
    pendingFor,
    toasts,
    pushError,
    dismissToast,
    panelBranchId,
    openPanel: setPanelBranchId,
    closePanel,
    bannerDismissed,
    dismissBanner: useCallback(() => setBannerDismissed(true), []),
    mergeFocus,
    openMerge: setMergeFocus,
    closeMerge: useCallback(() => setMergeFocus(null), []),
    settingsOpen,
    openSettings: useCallback(() => setSettingsOpen(true), []),
    closeSettings: useCallback(() => setSettingsOpen(false), []),
    openConversation,
    newChat,
    sendMessage,
    retry,
    deleteMessage,
    openBranch,
    discardBranch,
    refreshConversations,
    afterModelCall,
  };
}

export type Graft = ReturnType<typeof useGraft>;
