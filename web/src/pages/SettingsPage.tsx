import { useEffect, useState } from "react";

import { getSettings, saveSettings, validateSettings } from "../api/client";
import { Notice } from "../components/Notice";
import { Panel } from "../components/Panel";
import type { AppConfig, PathPreview, SettingsChange, SettingsChoices, ValidationResult } from "../types";

type SettingsViewState =
  { status: "loading" } | { status: "ready"; data: ReadySettingsState } | { status: "error"; message: string };

type ReadySettingsState = {
  config: AppConfig;
  choices: SettingsChoices;
  validation: ValidationResult;
  preview: PathPreview;
  changes: SettingsChange[];
  errors: string[];
  csrfToken: string;
  statusMessage: string;
};

export function SettingsPage() {
  const [viewState, setViewState] = useState<SettingsViewState>({ status: "loading" });

  useEffect(() => {
    let cancelled = false;
    getSettings()
      .then((data) => {
        if (cancelled) {
          return;
        }
        setViewState({
          status: "ready",
          data: {
            config: data.config,
            choices: data.choices,
            validation: data.validation,
            preview: data.preview,
            changes: [],
            errors: data.errors,
            csrfToken: data.csrf_token,
            statusMessage: ""
          }
        });
      })
      .catch((error: unknown) => {
        if (!cancelled) {
          setViewState({ status: "error", message: error instanceof Error ? error.message : "Settings failed." });
        }
      });
    return () => {
      cancelled = true;
    };
  }, []);

  if (viewState.status === "loading") {
    return <div className="empty-state">Loading settings.</div>;
  }

  if (viewState.status === "error") {
    return <Notice tone="error" messages={[viewState.message]} />;
  }

  const state = viewState.data;
  const setConfig = (config: AppConfig) => {
    setViewState({ status: "ready", data: { ...state, config, statusMessage: "" } });
  };

  const runValidate = () => {
    validateSettings(state.config).then((result) => {
      setViewState({
        status: "ready",
        data: {
          ...state,
          preview: result.preview,
          changes: result.changes,
          errors: result.errors,
          statusMessage: result.valid ? "Settings are valid." : ""
        }
      });
    });
  };

  const runSave = () => {
    saveSettings(state.config, state.csrfToken).then((result) => {
      setViewState({
        status: "ready",
        data: {
          ...state,
          config: result.config ?? state.config,
          validation: result.validation ?? state.validation,
          preview: result.preview ?? state.preview,
          changes: result.changes,
          errors: result.errors,
          statusMessage: result.saved ? "Settings saved." : ""
        }
      });
    });
  };

  return (
    <div className="page">
      <div className="page-heading">
        <h1>Settings</h1>
      </div>
      <Notice tone={state.statusMessage === "Settings saved." ? "success" : "info"} messages={messageList(state)} />
      <div className="settings-layout">
        <div className="settings-form">
          <Panel title="Paths">
            <TextField
              label="Library"
              value={state.config.paths.library ?? ""}
              onChange={(value) => setConfig({ ...state.config, paths: { ...state.config.paths, library: value } })}
            />
            <TextField
              label="Incoming"
              value={state.config.paths.incoming ?? ""}
              onChange={(value) => setConfig({ ...state.config, paths: { ...state.config.paths, incoming: value } })}
            />
          </Panel>
          <Panel title="Commands">
            <SelectField
              label="Add mode"
              value={state.config.add.default_mode}
              options={state.choices.command_modes}
              onChange={(value) => setConfig({ ...state.config, add: { ...state.config.add, default_mode: value } })}
            />
            <CheckboxField
              label="Add auto apply"
              checked={state.config.add.auto_apply}
              onChange={(value) => setConfig({ ...state.config, add: { ...state.config.add, auto_apply: value } })}
            />
            <SelectField
              label="Organize mode"
              value={state.config.organize.default_mode}
              options={state.choices.command_modes}
              onChange={(value) =>
                setConfig({ ...state.config, organize: { ...state.config.organize, default_mode: value } })
              }
            />
            <CheckboxField
              label="Organize auto apply"
              checked={state.config.organize.auto_apply}
              onChange={(value) =>
                setConfig({ ...state.config, organize: { ...state.config.organize, auto_apply: value } })
              }
            />
            <CheckboxField
              label="Organize only misplaced"
              checked={state.config.organize.only_misplaced}
              onChange={(value) =>
                setConfig({ ...state.config, organize: { ...state.config.organize, only_misplaced: value } })
              }
            />
            <SelectField
              label="Refresh mode"
              value={state.config.refresh.default_mode}
              options={state.choices.command_modes}
              onChange={(value) =>
                setConfig({ ...state.config, refresh: { ...state.config.refresh, default_mode: value } })
              }
            />
            <CheckboxField
              label="Refresh auto apply"
              checked={state.config.refresh.auto_apply}
              onChange={(value) =>
                setConfig({ ...state.config, refresh: { ...state.config.refresh, auto_apply: value } })
              }
            />
          </Panel>
          <Panel title="Path Policy">
            <TextField
              label="Template"
              value={state.config.path_policy.template}
              onChange={(value) =>
                setConfig({ ...state.config, path_policy: { ...state.config.path_policy, template: value } })
              }
            />
            <TextField
              label="Unknown artist"
              value={state.config.path_policy.unknown_artist}
              onChange={(value) =>
                setConfig({ ...state.config, path_policy: { ...state.config.path_policy, unknown_artist: value } })
              }
            />
            <TextField
              label="Unknown album"
              value={state.config.path_policy.unknown_album}
              onChange={(value) =>
                setConfig({ ...state.config, path_policy: { ...state.config.path_policy, unknown_album: value } })
              }
            />
            <CheckboxField
              label="Sanitize"
              checked={state.config.path_policy.sanitize}
              onChange={(value) =>
                setConfig({ ...state.config, path_policy: { ...state.config.path_policy, sanitize: value } })
              }
            />
            <NumberField
              label="Max filename length"
              value={state.config.path_policy.max_filename_length}
              onChange={(value) =>
                setConfig({
                  ...state.config,
                  path_policy: { ...state.config.path_policy, max_filename_length: value }
                })
              }
            />
          </Panel>
          <Panel title="Metadata">
            <CheckboxField
              label="Prefer album artist"
              checked={state.config.metadata.prefer_album_artist}
              onChange={(value) =>
                setConfig({ ...state.config, metadata: { ...state.config.metadata, prefer_album_artist: value } })
              }
            />
            <CheckboxField
              label="Require title"
              checked={state.config.metadata.require_title}
              onChange={(value) =>
                setConfig({ ...state.config, metadata: { ...state.config.metadata, require_title: value } })
              }
            />
            <CheckboxField
              label="Require artist"
              checked={state.config.metadata.require_artist}
              onChange={(value) =>
                setConfig({ ...state.config, metadata: { ...state.config.metadata, require_artist: value } })
              }
            />
            <CheckboxField
              label="Require album"
              checked={state.config.metadata.require_album}
              onChange={(value) =>
                setConfig({ ...state.config, metadata: { ...state.config.metadata, require_album: value } })
              }
            />
          </Panel>
          <Panel title="Collision">
            <SelectField
              label="Target exists"
              value={state.config.collision.on_target_exists}
              options={state.choices.target_exists_policies}
              onChange={(value) =>
                setConfig({ ...state.config, collision: { ...state.config.collision, on_target_exists: value } })
              }
            />
            <SelectField
              label="Duplicate hash"
              value={state.config.collision.on_duplicate_hash}
              options={state.choices.duplicate_hash_policies}
              onChange={(value) =>
                setConfig({ ...state.config, collision: { ...state.config.collision, on_duplicate_hash: value } })
              }
            />
            <SelectField
              label="Missing metadata"
              value={state.config.collision.on_missing_metadata}
              options={state.choices.missing_metadata_policies}
              onChange={(value) =>
                setConfig({ ...state.config, collision: { ...state.config.collision, on_missing_metadata: value } })
              }
            />
          </Panel>
          <Panel title="UI">
            <SelectField
              label="Theme"
              value={state.config.ui.theme}
              options={state.choices.ui_themes}
              onChange={(value) => setConfig({ ...state.config, ui: { ...state.config.ui, theme: value } })}
            />
            <CheckboxField
              label="Show advanced settings"
              checked={state.config.ui.show_advanced_settings}
              onChange={(value) =>
                setConfig({ ...state.config, ui: { ...state.config.ui, show_advanced_settings: value } })
              }
            />
          </Panel>
          <div className="action-row">
            <button type="button" onClick={runValidate}>
              Validate
            </button>
            <button type="button" className="button-primary" onClick={runSave}>
              Save
            </button>
          </div>
        </div>
        <aside className="settings-sidebar">
          <Panel title="Validation">
            <dl className="summary-list">
              <dt>Status</dt>
              <dd>{state.validation.valid ? "valid" : "invalid"}</dd>
              <dt>Config hash</dt>
              <dd>{state.validation.config_hash ?? "Not available"}</dd>
            </dl>
            <Notice tone="error" messages={state.validation.errors} />
          </Panel>
          <Panel title="Preview">
            <div className="path-preview">{state.preview.path ?? "No preview."}</div>
            <Notice tone="error" messages={state.preview.errors} />
          </Panel>
          <Panel title="Changes">
            {state.changes.length === 0 ? (
              <div className="empty-state">No changes.</div>
            ) : (
              <table>
                <thead>
                  <tr>
                    <th>Field</th>
                    <th>Before</th>
                    <th>After</th>
                  </tr>
                </thead>
                <tbody>
                  {state.changes.map((change) => (
                    <tr key={change.label}>
                      <td>{change.label}</td>
                      <td>{change.before}</td>
                      <td>{change.after}</td>
                    </tr>
                  ))}
                </tbody>
              </table>
            )}
          </Panel>
        </aside>
      </div>
    </div>
  );
}

function messageList(state: ReadySettingsState): string[] {
  return [...(state.statusMessage === "" ? [] : [state.statusMessage]), ...state.errors];
}

function TextField({ label, value, onChange }: { label: string; value: string; onChange: (value: string) => void }) {
  return (
    <label className="field">
      <span>{label}</span>
      <input value={value} onChange={(event) => onChange(event.target.value)} />
    </label>
  );
}

function NumberField({ label, value, onChange }: { label: string; value: number; onChange: (value: number) => void }) {
  return (
    <label className="field">
      <span>{label}</span>
      <input type="number" value={value} onChange={(event) => onChange(Number(event.target.value))} />
    </label>
  );
}

function SelectField({
  label,
  value,
  options,
  onChange
}: {
  label: string;
  value: string;
  options: string[];
  onChange: (value: string) => void;
}) {
  return (
    <label className="field">
      <span>{label}</span>
      <select value={value} onChange={(event) => onChange(event.target.value)}>
        {options.map((option) => (
          <option key={option} value={option}>
            {option}
          </option>
        ))}
      </select>
    </label>
  );
}

function CheckboxField({
  label,
  checked,
  onChange
}: {
  label: string;
  checked: boolean;
  onChange: (value: boolean) => void;
}) {
  return (
    <label className="check-field">
      <input type="checkbox" checked={checked} onChange={(event) => onChange(event.target.checked)} />
      <span>{label}</span>
    </label>
  );
}
