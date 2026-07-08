"use client";

import { useCallback, useEffect, useState } from "react";
import { BookOpenCheck } from "lucide-react";

import {
  Alert,
  Badge,
  Card,
  ErrorState,
  LoadingState,
  SectionHeader,
} from "@/components/ui";
import { getPermissionRegistry } from "@/lib/api/staff";
import { messageForError } from "@/lib/api/errors";
import type { PermissionRegistrySection } from "@/lib/api/types";
import { useI18n } from "@/lib/i18n/I18nProvider";

/** Read-only reference: what each section/operation means, and the two core
 * facts — job titles never grant access; permission grants are the single
 * source of truth. Built entirely from the backend registry (no hardcoding). */
export function RegistryTab() {
  const { t } = useI18n();
  const r = t.staff.registry;
  const [sections, setSections] = useState<PermissionRegistrySection[]>([]);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);

  const load = useCallback(async () => {
    setLoading(true);
    setError(null);
    try {
      const data = await getPermissionRegistry();
      setSections(data.sections);
    } catch (err) {
      setError(messageForError(err, t));
    } finally {
      setLoading(false);
    }
  }, [t]);

  useEffect(() => {
    load();
  }, [load]);

  if (loading) return <LoadingState label={t.common.loading} />;
  if (error)
    return (
      <ErrorState
        title={t.states.errorTitle}
        message={error}
        retryLabel={t.common.retry}
        onRetry={load}
      />
    );

  const sectionLabels = r.sections as Record<string, string>;
  const opLabels = r.ops as Record<string, string>;

  return (
    <>
      <Alert tone="info">{r.sourceOfTruth}</Alert>
      <Alert tone="warning">{r.jobTitleNote}</Alert>
      <Card>
        <SectionHeader title={r.title} />
        <p className="muted">{r.hint}</p>
        <div className="workflow-grid">
          {sections.map((section) => (
            <Card key={section.section}>
              <SectionHeader
                title={sectionLabels[section.section] ?? section.section}
                actions={<BookOpenCheck aria-hidden size={18} />}
              />
              <div className="cluster">
                {section.operations.map((op, index) => (
                  <Badge key={section.codes[index]} tone="neutral">
                    {opLabels[op] ?? op}
                  </Badge>
                ))}
              </div>
            </Card>
          ))}
        </div>
      </Card>
    </>
  );
}
