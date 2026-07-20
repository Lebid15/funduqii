"use client";

import { useCallback, useState } from "react";

import { Badge, Button, Card, SectionHeader, Switch } from "@/components/ui";
import type { PermissionRegistrySection } from "@/lib/api/types";
import { useI18n } from "@/lib/i18n/I18nProvider";

type Translations = ReturnType<typeof useI18n>["t"];

/** Translated label for a registry section with a safe fallback so future
 * registry additions never break the editor. */
function sectionLabel(t: Translations, section: string): string {
  const labels = t.staff.registry.sections as Record<string, string>;
  return labels[section] ?? section;
}

/** Translated label for a registry operation with a safe fallback. */
function opLabel(t: Translations, op: string): string {
  const labels = t.staff.registry.ops as Record<string, string>;
  return labels[op] ?? op;
}

/**
 * Shared Set-based selection state for permission codes — the single home for
 * the toggle / flip-a-section / reset-to-baseline logic that BOTH the two-step
 * create modal and the manage-permissions modal need. Keeps the grouping and
 * dirty-tracking rules in one place instead of duplicated per modal.
 */
export function useCodeSelection(initial: Iterable<string> = []) {
  const [selected, setSelected] = useState<Set<string>>(() => new Set(initial));

  const toggle = useCallback((code: string, on: boolean) => {
    setSelected((prev) => {
      const next = new Set(prev);
      if (on) next.add(code);
      else next.delete(code);
      return next;
    });
  }, []);

  const setSection = useCallback((codes: string[], on: boolean) => {
    setSelected((prev) => {
      const next = new Set(prev);
      for (const code of codes) {
        if (on) next.add(code);
        else next.delete(code);
      }
      return next;
    });
  }, []);

  const reset = useCallback(
    (codes: Iterable<string>) => setSelected(new Set(codes)),
    [],
  );

  return { selected, toggle, setSection, reset };
}

/**
 * The section-grouped permission switch grid (extracted from the old
 * PermissionsMatrixTab). Purely presentational and props-driven: the caller owns
 * the selection Set and decides whether the whole editor is `disabled` (e.g. a
 * member editing their own grants). Built entirely from the backend registry
 * shape (`{section, operations, codes}`), so it never hardcodes permissions.
 *
 * `idPrefix` keeps the generated switch ids unique when two editors could ever
 * be mounted at once (create step-2 vs manage modal).
 */
export function PermissionSectionsEditor({
  registry,
  selected,
  onToggle,
  onSection,
  disabled = false,
  idPrefix = "perm",
}: {
  registry: PermissionRegistrySection[];
  selected: Set<string>;
  onToggle: (code: string, on: boolean) => void;
  onSection: (codes: string[], on: boolean) => void;
  disabled?: boolean;
  idPrefix?: string;
}) {
  const { t } = useI18n();
  const m = t.staff.matrix;

  return (
    <div className="workflow-grid">
      {registry.map((section) => {
        const grantedInSection = section.codes.filter((c) => selected.has(c)).length;
        return (
          <Card key={section.section}>
            <SectionHeader
              title={sectionLabel(t, section.section)}
              actions={
                <Badge tone={grantedInSection > 0 ? "primary" : "neutral"}>
                  {m.grantedCount.replace("{count}", String(grantedInSection))}
                </Badge>
              }
            />
            <div className="cluster">
              <Button
                size="sm"
                variant="secondary"
                disabled={disabled}
                onClick={() => onSection(section.codes, true)}
              >
                {m.selectSection}
              </Button>
              <Button
                size="sm"
                variant="secondary"
                disabled={disabled}
                onClick={() => onSection(section.codes, false)}
              >
                {m.clearSection}
              </Button>
            </div>
            <div className="stack">
              {section.operations.map((op, index) => {
                const code = section.codes[index];
                return (
                  <Switch
                    key={code}
                    id={`${idPrefix}-${code}`}
                    checked={selected.has(code)}
                    disabled={disabled}
                    onChange={(on) => onToggle(code, on)}
                    label={opLabel(t, op)}
                  />
                );
              })}
            </div>
          </Card>
        );
      })}
    </div>
  );
}
