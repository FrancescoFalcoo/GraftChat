import type { ConversationSummary, Settings } from "../types";
import { formatUsd } from "../util";

interface Props {
  conversations: ConversationSummary[];
  activeId: number | null;
  settings: Settings | null;
  onNewChat: () => void;
  onSelect: (id: number) => void;
  onOpenSettings: () => void;
}

function spendLine(settings: Settings | null): string {
  if (!settings) return "";
  if (settings.spend_cap_usd === 0) return "Free models only";
  return `This month: ${formatUsd(settings.month_spend_usd)} / ${formatUsd(settings.spend_cap_usd)}`;
}

export function Sidebar({
  conversations,
  activeId,
  settings,
  onNewChat,
  onSelect,
  onOpenSettings,
}: Props) {
  return (
    <nav className="sidebar" aria-label="Conversations">
      <div className="sidebar-top">
        <div className="brand">
          <span className="brand-name">
            <span aria-hidden="true">⑂</span> GraftChat
          </span>
          {settings?.fake_llm && (
            <span className="tag-fake" title="The server answers with a fake model">
              FAKE LLM
            </span>
          )}
        </div>
        <button type="button" className="btn btn-primary btn-block" onClick={onNewChat}>
          New chat
        </button>
      </div>

      <ul className="conv-list">
        {conversations.length === 0 && <li className="conv-empty muted">No conversations yet</li>}
        {conversations.map((c) => (
          <li key={c.id}>
            <button
              type="button"
              className={`conv-item${c.id === activeId ? " conv-active" : ""}`}
              aria-current={c.id === activeId ? "page" : undefined}
              onClick={() => onSelect(c.id)}
            >
              <span className="conv-title">{c.title}</span>
              {c.open_branches > 0 && (
                <span
                  className="badge"
                  title={`${c.open_branches} open branch${c.open_branches === 1 ? "" : "es"}`}
                >
                  {c.open_branches}
                </span>
              )}
            </button>
          </li>
        ))}
      </ul>

      <div className="sidebar-bottom">
        <button type="button" className="btn btn-block" onClick={onOpenSettings}>
          Settings
        </button>
        <p className="spend-line">{spendLine(settings)}</p>
      </div>
    </nav>
  );
}
