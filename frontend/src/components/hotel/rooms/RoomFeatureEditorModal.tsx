"use client";

import { useCallback, useEffect, useState } from "react";
import { Ban, Check, ListChecks, Plus, RotateCcw, Tag, X } from "lucide-react";

import {
  Alert,
  Button,
  ErrorState,
  FormField,
  Icon,
  LoadingState,
  Modal,
  Select,
} from "@/components/ui";
import { getRoom, updateRoomFeatures } from "@/lib/api/rooms";
import { isApiError, messageForError } from "@/lib/api/errors";
import { useI18n } from "@/lib/i18n/I18nProvider";

import { AMENITY_KEYS } from "./RoomTypesTab";
import { amenityIcon } from "./boardShared";

/**
 * Per-room feature editor (§6.1). A room's EFFECTIVE features are the room
 * type's amenities with this room's `feature_exclusions` removed and
 * `feature_additions` added. This modal exposes that override model in three
 * clearly-separated sections — distinguished by SECTION + LABEL + ICON (never
 * colour alone):
 *   • INHERITED (from the type): each active feature can be turned OFF (→ moves
 *     into feature_exclusions).
 *   • ADDED (room-specific): pick a catalog feature the type lacks; remove ones
 *     you added.
 *   • EXCLUDED: inherited features you turned off — struck through and
 *     restorable.
 * "Reset to type defaults" clears both override lists. Save PATCHes ONLY the two
 * writable arrays via `updateRoomFeatures`; the server's both-lists validation
 * error surfaces inline. The modal reads the FRESH single-room detail on open
 * (the board / list Room shapes omit the writable arrays), so the caller need
 * only pass the room id + number.
 */
export function RoomFeatureEditorModal({
  open,
  roomId,
  roomNumber,
  onClose,
  onSaved,
}: {
  open: boolean;
  roomId: number;
  roomNumber: string;
  onClose: () => void;
  onSaved: () => void;
}) {
  const { t } = useI18n();
  const b = t.rooms.board;
  const f = b.features;
  const amenityLabels = b.amenity as Record<string, string>;

  const [inherited, setInherited] = useState<string[]>([]);
  const [additions, setAdditions] = useState<string[]>([]);
  const [exclusions, setExclusions] = useState<string[]>([]);
  // THREE distinct states: loading (fetch in flight) / loaded (a getRoom
  // SUCCEEDED — the only state in which Save is permitted) / loadError (fetch
  // failed). `error` is kept SEPARATE for SAVE errors so a load failure never
  // masquerades as one and vice-versa.
  const [loading, setLoading] = useState(false);
  const [loaded, setLoaded] = useState(false);
  const [loadError, setLoadError] = useState<string | null>(null);
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState<string | null>(null);

  /** Fetch the FRESH single-room detail. Save stays impossible until this
   * succeeds (loaded=true), so a failed load can NEVER PATCH the un-loaded
   * ([]/[]) state and silently wipe the room's stored feature overrides. */
  const loadRoom = useCallback(() => {
    setLoadError(null);
    setLoaded(false);
    setLoading(true);
    getRoom(roomId)
      .then((room) => {
        const inh = room.inherited_features ?? [];
        setInherited(inh);
        // The two override lists are PERMANENT per-room state (owner rule): keep
        // them intact — a DORMANT exclusion (a feature not currently in the type)
        // and a redundant addition are PRESERVED here and re-sent on save, never
        // silently dropped. Only the DISPLAY derivations below filter against the
        // live inherited set.
        setAdditions(room.feature_additions ?? []);
        setExclusions(room.feature_exclusions ?? []);
        setLoaded(true);
      })
      .catch((err) => setLoadError(messageForError(err, t)))
      .finally(() => setLoading(false));
    // eslint-disable-next-line react-hooks/exhaustive-deps -- t is stable per locale
  }, [roomId]);

  useEffect(() => {
    if (!open) return;
    setError(null);
    loadRoom();
  }, [open, loadRoom]);

  const label = (key: string) => amenityLabels[key] ?? key;

  const activeInherited = inherited.filter((k) => !exclusions.includes(k));
  // DISPLAY-only view of the additions: a redundant addition that the type now
  // provides is hidden from the ADDED section + preview (it's already shown as
  // inherited) but stays in `additions` state so save preserves it.
  const addedRoomSpecific = additions.filter((k) => !inherited.includes(k));
  // The picker offers catalog features the type does NOT already provide and the
  // room has not already added (checked against the FULL additions state).
  const available = AMENITY_KEYS.filter(
    (k) => !inherited.includes(k) && !additions.includes(k),
  );
  const effective = [...activeInherited, ...addedRoomSpecific];

  function excludeFeature(key: string) {
    setError(null);
    setExclusions((prev) => (prev.includes(key) ? prev : [...prev, key]));
  }
  function restoreFeature(key: string) {
    setError(null);
    setExclusions((prev) => prev.filter((k) => k !== key));
  }
  function addFeature(key: string) {
    setError(null);
    if (!key) return;
    setAdditions((prev) => (prev.includes(key) ? prev : [...prev, key]));
  }
  function removeAddition(key: string) {
    setError(null);
    setAdditions((prev) => prev.filter((k) => k !== key));
  }
  function resetToType() {
    setError(null);
    setAdditions([]);
    setExclusions([]);
  }

  /** Map the server's field-keyed 400 details to a translated inline message.
   * The normalize helper raises the both-lists conflict on `feature_additions`. */
  function describeError(err: unknown): string {
    if (isApiError(err) && err.details && typeof err.details === "object") {
      const d = err.details as Record<string, unknown>;
      if ("feature_additions" in d) return f.errorBothLists;
    }
    return messageForError(err, t);
  }

  async function save() {
    // Belt-and-suspenders with the disabled Save button: never PATCH before a
    // successful load, or we would overwrite the stored overrides with empty lists.
    if (!loaded) return;
    setBusy(true);
    setError(null);
    try {
      await updateRoomFeatures(roomId, {
        feature_additions: additions,
        feature_exclusions: exclusions,
      });
      onSaved();
    } catch (err) {
      setError(describeError(err));
    } finally {
      setBusy(false);
    }
  }

  return (
    <Modal
      open={open}
      onClose={busy ? () => undefined : onClose}
      title={`${f.editorTitle} — ${roomNumber}`}
      closeLabel={t.common.close}
      size="lg"
      preventClose={busy}
      footer={
        <>
          <Button
            variant="ghost"
            icon={RotateCcw}
            onClick={resetToType}
            disabled={busy || loading || !loaded}
          >
            {f.reset}
          </Button>
          <Button variant="secondary" onClick={onClose} disabled={busy}>
            {t.common.cancel}
          </Button>
          <Button onClick={save} loading={busy} disabled={busy || loading || !loaded}>
            {t.common.save}
          </Button>
        </>
      }
    >
      <div className="stack">
        {error ? <Alert tone="error">{error}</Alert> : null}
        {loading ? (
          // Guard the body while the fresh room detail loads, so stale/empty
          // sections never flash before inherited/added/excluded are known.
          <LoadingState label={t.common.loading} />
        ) : loadError ? (
          // Load FAILED: never render the sections (which would show the un-loaded
          // []/[] state) and never enable Save — offer a retry that re-fetches.
          <ErrorState
            title={t.states.errorTitle}
            message={loadError}
            retryLabel={t.common.retry}
            onRetry={loadRoom}
          />
        ) : (
        <>
        <p className="muted">{f.editorHelp}</p>

        {/* INHERITED (active) — from the room type; each can be turned off. */}
        <section className="stack feature-editor__section">
          <div className="feature-editor__heading">
            <Icon icon={Tag} size="sm" />
            <span className="feature-editor__title">{f.inherited}</span>
          </div>
          <p className="muted feature-editor__help">{f.inheritedHelp}</p>
          {inherited.length === 0 ? (
            <p className="muted">{f.noneInherited}</p>
          ) : activeInherited.length === 0 ? (
            <p className="muted">{f.allExcluded}</p>
          ) : (
            <ul className="feature-chip-list">
              {activeInherited.map((key) => (
                <li key={key} className="feature-chip">
                  <Icon icon={amenityIcon(key)} size="sm" className="feature-chip__icon" />
                  <span>{label(key)}</span>
                  <button
                    type="button"
                    className="feature-chip__action"
                    aria-label={`${f.turnOff} — ${label(key)}`}
                    onClick={() => excludeFeature(key)}
                  >
                    <Icon icon={Ban} size="sm" />
                  </button>
                </li>
              ))}
            </ul>
          )}
        </section>

        {/* ADDED — room-specific extras the type does not provide. */}
        <section className="stack feature-editor__section">
          <div className="feature-editor__heading">
            <Icon icon={Plus} size="sm" />
            <span className="feature-editor__title">{f.added}</span>
          </div>
          <p className="muted feature-editor__help">{f.addedHelp}</p>
          <FormField label={f.addFeature} htmlFor="feature-add-picker">
            <Select
              id="feature-add-picker"
              value=""
              placeholder={f.selectFeature}
              options={available.map((key) => ({ value: key, label: label(key) }))}
              onChange={(e) => addFeature(e.target.value)}
            />
          </FormField>
          {addedRoomSpecific.length > 0 ? (
            <ul className="feature-chip-list">
              {addedRoomSpecific.map((key) => (
                <li key={key} className="feature-chip">
                  <Icon icon={Check} size="sm" className="feature-chip__icon" />
                  <span>{label(key)}</span>
                  <button
                    type="button"
                    className="feature-chip__action"
                    aria-label={`${f.remove} — ${label(key)}`}
                    onClick={() => removeAddition(key)}
                  >
                    <Icon icon={X} size="sm" />
                  </button>
                </li>
              ))}
            </ul>
          ) : null}
        </section>

        {/* EXCLUDED — inherited features turned off; struck through, restorable. */}
        {exclusions.length > 0 ? (
          <section className="stack feature-editor__section">
            <div className="feature-editor__heading">
              <Icon icon={Ban} size="sm" />
              <span className="feature-editor__title">{f.excluded}</span>
            </div>
            <p className="muted feature-editor__help">{f.excludedHelp}</p>
            <ul className="feature-chip-list">
              {exclusions.map((key) => (
                <li key={key} className="feature-chip feature-chip--excluded">
                  <Icon icon={Ban} size="sm" className="feature-chip__icon" />
                  <span>{label(key)}</span>
                  <button
                    type="button"
                    className="feature-chip__action"
                    aria-label={`${f.turnOn} — ${label(key)}`}
                    onClick={() => restoreFeature(key)}
                  >
                    <Icon icon={RotateCcw} size="sm" />
                  </button>
                </li>
              ))}
            </ul>
          </section>
        ) : null}

        {/* Effective preview — exactly what the card + drawer will show. */}
        <section className="stack feature-editor__section">
          <div className="feature-editor__heading">
            <Icon icon={ListChecks} size="sm" />
            <span className="feature-editor__title">{f.effectivePreview}</span>
          </div>
          {effective.length > 0 ? (
            // Read-only chips, rendered like the other sections (icon + label) so
            // the list carries an accurate aria-label instead of the
            // roomTypeFeatures fallback that AmenityChips would apply.
            <ul className="feature-chip-list" aria-label={f.effectivePreview}>
              {effective.map((key) => (
                <li key={key} className="feature-chip">
                  <Icon icon={amenityIcon(key)} size="sm" className="feature-chip__icon" />
                  <span>{label(key)}</span>
                </li>
              ))}
            </ul>
          ) : (
            <p className="muted">{f.noneEffective}</p>
          )}
        </section>
        </>
        )}
      </div>
    </Modal>
  );
}
