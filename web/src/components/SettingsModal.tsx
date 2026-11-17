import { useEffect, useId, useState, type FormEvent } from "react";
import { api } from "../api";
import type { Model, Settings, SettingsUpdate } from "../types";
import { isSoundOn, playGlop, setSoundOn } from "../sound";
import { ConfirmDialog } from "./ConfirmDialog";
import { Modal } from "./Modal";

interface Props {
  settings: Settings;
  onSaved: (settings: Settings) => void;
  onClose: () => void;
  onError: (error: unknown) => void;
}

interface ModelFieldProps {
  label: string;
  value: string;
  onChange: (value: string) => void;
  /** null = still loading, "failed" = free text only. */
  models: Model[] | "failed" | null;
  disabled?: boolean;
}

/** Model id input; with a loaded list it becomes a searchable combo (datalist). */
function ModelField({ label, value, onChange, models, disabled = false }: ModelFieldProps) {
  const id = useId();
  const listId = `${id}-list`;
  const loaded = Array.isArray(models);
  return (
    <div className="field">
      <label htmlFor={id}>{label}</label>
      <input
        id={id}
        type="text"
        value={value}
        list={loaded ? listId : undefined}
        placeholder={loaded ? "Type to search the free models" : "provider/model-id"}
        spellCheck={false}
        autoComplete="off"
        disabled={disabled}
        onChange={(e) => onChange(e.target.value)}
      />
      {loaded && (
        <datalist id={listId}>
          {models.map((m) => (
            <option key={m.id} value={m.id}>
              {[
                m.name,
                m.context_length ? `${m.context_length.toLocaleString()} tokens` : null,
                m.images ? "images" : null,
              ]
                .filter(Boolean)
                .join(" · ")}
            </option>
          ))}
        </datalist>
      )}
    </div>
  );
}

export function SettingsModal({ settings, onSaved, onClose, onError }: Props) {
  const [apiKey, setApiKey] = useState("");
  const [cap, setCap] = useState(String(settings.spend_cap_usd));
  const [sound, setSound] = useState(isSoundOn());
  const [confirmRemove, setConfirmRemove] = useState(false);
  const [chatModel, setChatModel] = useState(settings.chat_model ?? "");
  const [sameAsChat, setSameAsChat] = useState(settings.takeaway_model === null);
  const [takeawayModel, setTakeawayModel] = useState(settings.takeaway_model ?? "");
  const [models, setModels] = useState<Model[] | "failed" | null>(null);
  const [saving, setSaving] = useState(false);
  const [formError, setFormError] = useState<string | null>(null);
  const keyId = useId();
  const capId = useId();

  useEffect(() => {
    let cancelled = false;
    api
      .models()
      .then((list) => !cancelled && setModels(list))
      .catch(() => !cancelled && setModels("failed"));
    return () => {
      cancelled = true;
    };
  }, []);

  const save = async (e: FormEvent): Promise<void> => {
    e.preventDefault();
    const capValue = Number(cap);
    if (cap.trim() === "" || !Number.isFinite(capValue) || capValue < 0) {
      setFormError("The spend cap must be a number greater than or equal to 0.");
      return;
    }
    const update: SettingsUpdate = { spend_cap_usd: capValue };
    if (!settings.api_key_from_env && apiKey.trim()) update.api_key = apiKey.trim();
    if (chatModel.trim()) update.chat_model = chatModel.trim();
    update.takeaway_model = sameAsChat || !takeawayModel.trim() ? null : takeawayModel.trim();

    setFormError(null);
    setSaving(true);
    try {
      onSaved(await api.putSettings(update));
      onClose();
    } catch (err) {
      onError(err);
      setSaving(false);
    }
  };

  const removeKey = async (): Promise<void> => {
    setConfirmRemove(false);
    try {
      onSaved(await api.deleteApiKey());
    } catch (err) {
      onError(err);
    }
  };

  return (
    <Modal title="Settings" onClose={onClose}>
      <form className="settings-form" onSubmit={(e) => void save(e)}>
        <div className="field">
          <label htmlFor={keyId}>OpenRouter API key</label>
          {settings.api_key_from_env ? (
            <>
              <input
                id={keyId}
                type="password"
                readOnly
                value={settings.api_key_hint ?? "set by the environment"}
              />
              <p className="field-note">
                Set through the OPENROUTER_API_KEY environment variable
                {settings.api_key_hint ? ` (${settings.api_key_hint})` : ""}. It cannot be changed
                here.
              </p>
            </>
          ) : (
            <>
              <input
                id={keyId}
                type="password"
                value={apiKey}
                autoComplete="off"
                placeholder={settings.has_api_key ? "Leave empty to keep the current key" : "sk-or-…"}
                onChange={(e) => setApiKey(e.target.value)}
              />
              {settings.has_api_key && (
                <p className="field-note">
                  Current key: {settings.api_key_hint ?? "set"}{" "}
                  <button type="button" className="link-btn" onClick={() => setConfirmRemove(true)}>
                    Remove
                  </button>
                </p>
              )}
            </>
          )}
          <p className="field-note">
            The key is stored only on this computer and sent only to OpenRouter.
          </p>
        </div>

        <div className="field">
          <label htmlFor={capId}>Monthly spend cap (USD)</label>
          <input
            id={capId}
            type="number"
            min={0}
            step="0.01"
            inputMode="decimal"
            value={cap}
            onChange={(e) => setCap(e.target.value)}
          />
          <p className="field-note">Set it to 0 to use free models only.</p>
        </div>

        <div className="field">
          <label className="check-label">
            <input
              type="checkbox"
              checked={sound}
              onChange={(e) => {
                setSound(e.target.checked);
                setSoundOn(e.target.checked);
                if (e.target.checked) playGlop("merge");
              }}
            />
            Play a sound when a branch is opened or merged
          </label>
          <p className="field-note">Saved in this browser only.</p>
        </div>

        <ModelField label="Chat model" value={chatModel} onChange={setChatModel} models={models} />

        <div className="field">
          <label className="check-label">
            <input
              type="checkbox"
              checked={sameAsChat}
              onChange={(e) => setSameAsChat(e.target.checked)}
            />
            Take-away model: same as chat model
          </label>
        </div>
        {!sameAsChat && (
          <ModelField
            label="Take-away model"
            value={takeawayModel}
            onChange={setTakeawayModel}
            models={models}
          />
        )}

        {models === null && <p className="field-note">Loading the model list…</p>}
        {models === "failed" && (
          <p className="field-note">
            The model list could not be loaded. Type the model id by hand.
          </p>
        )}

        {formError && (
          <p className="form-error" role="alert">
            {formError}
          </p>
        )}

        <div className="form-actions">
          <button type="button" className="btn" onClick={onClose}>
            Cancel
          </button>
          <button type="submit" className="btn btn-primary" disabled={saving}>
            {saving ? "Saving…" : "Save"}
          </button>
        </div>
      </form>
      {confirmRemove && (
        <ConfirmDialog
          title="Remove the API key?"
          message="The stored OpenRouter key will be deleted from this computer. Chats will stop until you add a key again."
          confirmLabel="Remove"
          danger
          onCancel={() => setConfirmRemove(false)}
          onConfirm={() => void removeKey()}
        />
      )}
    </Modal>
  );
}
