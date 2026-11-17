import { BranchPanel } from "./components/BranchPanel";
import { MainChat } from "./components/MainChat";
import { MergeDialog } from "./components/MergeDialog";
import { DevNotice, ReturnBanner, Toasts } from "./components/Notices";
import { SettingsModal } from "./components/SettingsModal";
import { Sidebar } from "./components/Sidebar";
import { useGraft } from "./hooks/useGraft";
import { laneOf } from "./lanes";
import { pendingBranches } from "./util";

export function App() {
  const g = useGraft();
  const { state } = g;
  const panelBranch = state?.branches.find((b) => b.id === g.panelBranchId) ?? null;
  const pendingCount = state ? pendingBranches(state).length : 0;
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
          onSend={(text) => g.sendMessage(null, text)}
          onRetry={() => void g.retry(null)}
          onDelete={(id) => void g.deleteMessage(id)}
          onOpenBranch={g.openBranch}
          onShowBranch={g.openPanel}
        />
        {panelBranch && (
          <BranchPanel
            branch={panelBranch}
            lane={laneOf(state?.branches ?? [], panelBranch.id)}
            pending={g.pendingFor(panelBranch.id)}
            onClose={g.closePanel}
            onSend={(text) => g.sendMessage(panelBranch.id, text)}
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
          onApplied={() => {
            g.closeMerge();
            void g.refreshConversations();
          }}
          onError={g.pushError}
          onModelCall={g.afterModelCall}
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
