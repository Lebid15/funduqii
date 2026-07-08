import type { ReactNode } from "react";

interface PrintMetaItem {
  label: string;
  value: ReactNode;
}

interface PrintDocumentLayoutProps {
  hotelName: string;
  hotelAddress?: string;
  hotelPhone?: string;
  docTitle: string;
  docNumber: string;
  meta: PrintMetaItem[];
  children?: ReactNode;
  totals?: PrintMetaItem[];
  notes?: string;
  notesLabel?: string;
  signatureLabel?: string;
  footer?: string;
}

/** Central print layout for receipts, expense vouchers and invoices: hotel
 * header, document title/number, a meta grid, optional body (tables), totals,
 * notes and an optional signature line. Works inside PrintModal. */
export function PrintDocumentLayout({
  hotelName,
  hotelAddress,
  hotelPhone,
  docTitle,
  docNumber,
  meta,
  children,
  totals,
  notes,
  notesLabel,
  signatureLabel,
  footer,
}: PrintDocumentLayoutProps) {
  return (
    <div className="receipt">
      <h3>{hotelName}</h3>
      {hotelAddress || hotelPhone ? (
        <p className="muted small">
          {[hotelAddress, hotelPhone].filter(Boolean).join(" · ")}
        </p>
      ) : null}
      <p className="muted">{docTitle} · {docNumber}</p>
      <dl className="print-grid">
        {meta.map((item, i) => (
          <div key={i}>
            <dt>{item.label}</dt>
            <dd>{item.value}</dd>
          </div>
        ))}
      </dl>
      {children}
      {totals && totals.length > 0 ? (
        <dl className="print-grid print-grid--totals">
          {totals.map((item, i) => (
            <div key={i}>
              <dt>{item.label}</dt>
              <dd>{item.value}</dd>
            </div>
          ))}
        </dl>
      ) : null}
      {notes ? (
        <p className="print-notes">
          {notesLabel ? <strong>{notesLabel}: </strong> : null}
          {notes}
        </p>
      ) : null}
      {signatureLabel ? (
        <div className="print-signature">
          <span>{signatureLabel}</span>
          <span className="print-signature__line" aria-hidden />
        </div>
      ) : null}
      {footer ? <p className="print-thanks">{footer}</p> : null}
    </div>
  );
}
