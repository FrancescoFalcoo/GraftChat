import { useState } from "react";
import { playGlop } from "./sound";
import { BranchPanel } from "./components/BranchPanel";
import { ConversationMap } from "./components/ConversationMap";
import { MainChat } from "./components/MainChat";
import { MergeDialog } from "./components/MergeDialog";
import { DevNotice, ReturnBanner, Toasts } from "./components/Notices";
import { SettingsModal } from "./components/SettingsModal";
import { Sidebar } from "./components/Sidebar";
import { useGraft } from "./hooks/useGraft";
import { laneOf } from "./lanes";
import { knownMerges, pendingBranches } from "./util";

export function App() {
  const g = useGraft();
  const { state } = g;
  const panelBranch = state?.branches.find((b) => b.id === g.panelBranchId) ?? null;
  const pendingCount = state ? pendingBranches(state).length : 0;
  const [mapOpen, setMapOpen] = useState(false);

  /** From the map: show the prompt, opening its branch in the side panel if needed. */
  const jumpTo = (messageId: number, branchId: number | null): void => {
    setMapOpen(false);
    if (branchId !== null) g.openPanel(branchId);
    // After the dialog is gone and the panel has rendered (and scrolled to its end).
    window.setTimeout(() => {
      const el = document.querySelector<HTMLElement>(`[data-turn-id="${messageId}"]`);
      if (!el) return;
      const reduce = window.matchMedia?.("(prefers-reduced-motion: reduce)").matches;
      el.scrollIntoView({ block: "center", behavior: reduce ? "auto" : "smooth" });
      el.classList.remove("turn-flash");
      void el.offsetWidth; // restart the animation when the same prompt is chosen again
      el.classList.add("turn-flash");
      window.setTimeout(() => el.classList.remove("turn-flash"), 1700);
    }, 150);
  };

  const showBanner =
    panelBranch === null && pendingCount > 0 && !g.bannerDismissed && g.mergeFocus === null;

  return (
    <div className="app">
      <DevNotice health={g.health} />
      <div className={`layout${panelBranch ? " with-panel" : ""}`}>
        <Sidebar
          conversations={g.conversations}
          activeId={g.activeId}
          settings={g.settings}
          onNewChat={() => void g.newChat()}
          onSelect={(id) => void g.openConversation(id)}
          onOpenSettings={g.openSettings}
          onOpenMap={state && state.main.length > 0 ? () => setMapOpen(true) : null}
        />
        <MainChat
          state={state}
          booting={g.booting}
          pending={g.pendingFor(null)}
          activeBranchId={panelBranch?.id ?? null}
          banner={
            showBanner ? (
              <ReturnBanner
                count={pendingCount}
                onReview={() => g.openMerge("all")}
                onDismiss={g.dismissBanner}
              />
            ) : null
          }
          onSend={(text, files) => g.sendMessage(null, text, files)}
          onRetry={() => void g.retry(null)}
          onDelete={(id) => void g.deleteMessage(id)}
          onOpenBranch={g.openBranch}
          onShowBranch={g.openPanel}
        />
        {panelBranch && (
          <BranchPanel
            branch={panelBranch}
            lane={laneOf(state?.branches ?? [], panelBranch.id)}
            known={state ? knownMerges(state, panelBranch) : []}
            pending={g.pendingFor(panelBranch.id)}
            onClose={g.closePanel}
            onSend={(text, files) => g.sendMessage(panelBranch.id, text, files)}
            onRetry={() => void g.retry(panelBranch.id)}
            onDelete={(id) => void g.deleteMessage(id)}
            onMerge={() => g.openMerge([panelBranch.id])}
            onDiscard={() => void g.discardBranch(panelBranch.id)}
          />
        )}
      </div>

      {g.mergeFocus !== null && state && (
        <MergeDialog
          state={state}
          focus={g.mergeFocus}
          onState={g.applyState}
          onClose={g.closeMerge}
          onApplied={(merged) => {
            if (merged) playGlop("merge");
            g.closeMerge();
            void g.refreshConversations();
          }}
          onError={g.pushError}
          onModelCall={g.afterModelCall}
        />
      )}
      {mapOpen && state && (
        <ConversationMap
          state={state}
          onJump={jumpTo}
          onOpenBranch={(id) => {
            setMapOpen(false);
            g.openPanel(id);
          }}
          onClose={() => setMapOpen(false)}
        />
      )}
      {g.settingsOpen && g.settings && (
        <SettingsModal
          settings={g.settings}
          onSaved={g.setSettings}
          onClose={g.closeSettings}
          onError={g.pushError}
        />
      )}
      <Toasts toasts={g.toasts} onDismiss={g.dismissToast} onOpenSettings={g.openSettings} />
    </div>
  );
}
